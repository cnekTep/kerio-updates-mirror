import html
import re
from dataclasses import dataclass

from fastapi import HTTPException, status
from markupsafe import Markup

from app.config import settings, templates, BASE_DIR
from app.utils.app_logging import log_event
from app.utils.internet_utils import make_request_with_retries

# Telegram limit for the whole rich message (in characters)
RICH_MAX_LENGTH = 32768

# If the rendered message is too long, every line is cut to these lengths
# one step at a time (None = no cutting) until the result fits
_TRUNCATION_STEPS = (None, 2000, 1500, 1000, 500, 250, 100)

# Cells like "err=ConnectError(...)" or "status=404" are technical values: templates show them as <code>
_CODE_CELL = re.compile(r"\w+=")

# Deterministic API errors: trying other proxies won't help, handle them here
_SKIP_STATUS_CODES = [400, 401, 403, 404, 429]


@dataclass
class TelegramConfig:
    """Ad-hoc Telegram config, used to override settings.telegram (e.g. for test sends)."""

    bot_api_url: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None


class TelegramService:
    """
    Service layer for sending outbound notifications to Telegram (Bot API)
    as rich messages rendered from templates/telegram/*.html.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def send_notification(
        self,
        subject: str,
        context: dict,
        template_name: str = "default.html",
        config: TelegramConfig | None = None,
    ) -> None:
        """
        Render a Telegram template and send the result as a rich message.

        Args:
            subject: Message title (available in the template as `subject`).
            context: Values to render into the template
                (action_name, status, message, details).
            template_name: Template file name, relative to templates/telegram/
                (e.g. "default.html").
            config: Telegram config to use instead of settings.telegram
                (e.g. unsaved values currently typed in the settings form).

        Raises:
            HTTPException: 400 if Telegram is not configured or the template
                does not exist, 500 on any other failure (all connection
                attempts failed, API error, etc.).
        """
        try:
            await self._send(
                subject=subject,
                template_name=template_name,
                context=context,
                config=config,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except Exception as exc:
            # No notify=True here: this runs inside the notification pipeline
            log_event(
                log_type=["system", "errors"],
                message=f"Telegram | Error: Failed to send message '{subject}': {exc}",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send Telegram message: {exc}",
            ) from exc

        log_event(log_type=["system"], message=f"Telegram | Sent: '{subject}'")

    @staticmethod
    def list_telegram_templates() -> list[str]:
        """
        List .html files in the Telegram templates directory.

        Returns:
            Sorted list of full template filenames (with extension).
        """
        templates_dir = BASE_DIR / "templates" / "telegram"
        if not templates_dir.is_dir():
            return []

        return sorted(
            p.name
            for p in templates_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".html"
        )

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_configured(tg_config) -> None:
        """
        Validate that the minimum required Telegram settings are present.

        Raises:
            ValueError: If any required setting is missing.
        """
        if not tg_config.bot_token:
            raise ValueError("Telegram bot token is not configured")
        if not tg_config.chat_id:
            raise ValueError("Telegram chat ID is not configured")

    async def _send(
        self,
        subject: str,
        template_name: str,
        context: dict,
        config: TelegramConfig | None,
    ) -> None:
        """Render the template and send it with sendRichMessage."""
        # Use the passed-in (e.g. unsaved form) config if given, otherwise fall back to app settings
        tg_config = config or settings.telegram
        self._ensure_configured(tg_config=tg_config)

        if template_name not in self.list_telegram_templates():
            raise ValueError(f"Telegram template '{template_name}' not found")

        rich_html = self._render_fitting(
            template_name=template_name, context={**context, "subject": subject}
        )
        message_thread_id = self._get_message_thread_id(context)
        bot_api_url = tg_config.bot_api_url or "api.telegram.org"

        response = await make_request_with_retries(
            url=f"https://{bot_api_url}/bot{tg_config.bot_token}/sendRichMessage",
            method="POST",
            json={
                "chat_id": str(tg_config.chat_id),
                "message_thread_id": message_thread_id,
                "rich_message": {"html": rich_html},
            },
            context="Telegram | sendRichMessage",
            skip_status_codes=_SKIP_STATUS_CODES,
            notify=False,  # we are inside the notification pipeline
        )

        if response is None:
            # Details of every attempt are already in the system/errors logs
            raise RuntimeError("all connection attempts failed")

        if response.status_code != 200:
            try:
                description = response.json().get("description", "")
            except ValueError:
                description = response.text[:200]
            raise RuntimeError(f"Telegram API {response.status_code}: {description}")

    @staticmethod
    def _get_message_thread_id(context: dict) -> int | None:
        """
        Get the message thread ID from the context or settings.
        """
        # Explicit thread from context always wins
        if thread_id := context.get("thread_id"):
            return thread_id

        # Threads are disabled, so send to the main chat
        if not settings.telegram.thread_enabled:
            return None

        # Route by action type
        if context.get("action_name") == "Mirror Update":
            return settings.telegram.thread_updates_id
        return settings.telegram.thread_errors_id

    # ------------------------------------------------------------------
    # Rendering: lines -> blocks (paragraphs and tables) -> template
    # ------------------------------------------------------------------
    @staticmethod
    def _escape(text) -> Markup:
        """
        Escape text for Rich HTML. Only <, > and & are replaced (the entities every
        Telegram HTML mode understands); quotes are left alone. Returned as Markup,
        so Jinja does not escape it a second time (and does not turn ' into &#39;).
        """
        return Markup(html.escape(str(text), quote=False))

    @staticmethod
    def _cut(text: str, cap: int | None) -> str:
        """Shorten text to `cap` characters (None = keep as is)."""
        if cap is None or len(text) <= cap:
            return text
        return text[: cap - 1] + "…"

    @staticmethod
    def _normalize_lines(items) -> list[dict]:
        """
        Turn a str / dict / list of both into a flat list of single-line dicts
        with 'text' and 'success' keys. Multi-line texts are split into lines,
        blank lines are dropped.
        """
        if items is None:
            items = []
        elif not isinstance(items, list):
            items = [items]

        lines = []
        for item in items:
            data = dict(item) if isinstance(item, dict) else {"text": item}
            data.setdefault("success", True)
            for part in str(data.get("text", "")).splitlines():
                if part.strip():
                    lines.append({**data, "text": part.strip()})
        return lines

    def _split_cells(self, text: str) -> list[dict]:
        """Split a line into cells by '|'. Each cell has an escaped 'text' and a 'code' flag."""
        cells = [cell.strip() for cell in text.split("|")]
        while len(cells) > 1 and not cells[-1]:  # trailing separator
            cells.pop()
        return [
            {"text": self._escape(cell or "—"), "code": bool(_CODE_CELL.match(cell))}
            for cell in cells
        ]

    @staticmethod
    def _build_table(rows: list[dict], merge_first_column: bool) -> dict:
        """
        Build a table block from rows of parts.

        Rows with fewer cells than the widest row get a colspan on their last
        cell. With merge_first_column, consecutive rows with the same first
        cell share it through a rowspan (e.g. several errors of one operation).
        Each row keeps all its `parts` (the original cells) next to the laid-out
        `cells`, for templates that do not draw tables.
        """
        columns = max(len(row["parts"]) for row in rows)

        # spans[i]: rowspan of the first cell of row i, 0 = covered by a row above
        spans = [1] * len(rows)
        if merge_first_column:
            i = 0
            while i < len(rows):
                j = i + 1
                while (
                    len(rows[i]["parts"]) > 1
                    and j < len(rows)
                    and len(rows[j]["parts"]) > 1
                    and rows[j]["parts"][0]["text"] == rows[i]["parts"][0]["text"]
                ):
                    j += 1
                spans[i] = j - i
                for k in range(i + 1, j):
                    spans[k] = 0
                i = j

        table_rows = []
        for row, span in zip(rows, spans):
            covered = span == 0
            parts = row["parts"][1:] if covered else row["parts"]
            cells = [
                {**part, "colspan": 1, "rowspan": 1, "head": False} for part in parts
            ]
            if not covered:
                cells[0]["head"] = True
                cells[0]["rowspan"] = span
            # The last cell stretches over the columns this row does not fill
            used = len(cells) + (1 if covered else 0)
            cells[-1]["colspan"] = 1 + columns - used
            table_rows.append(
                {"success": row["success"], "parts": row["parts"], "cells": cells}
            )

        return {"kind": "table", "rows": table_rows}

    def _build_blocks(
        self, lines: list[dict], merge_first_column: bool = False
    ) -> list[dict]:
        """
        Group lines into blocks: consecutive lines containing '|' become one
        table (the '|' separates columns), every other line a paragraph.
        """
        blocks: list[dict] = []
        rows: list[dict] = []

        def flush_table() -> None:
            if rows:
                blocks.append(self._build_table(list(rows), merge_first_column))
                rows.clear()

        for line in lines:
            text = line["text"]
            if "|" in text:
                rows.append(
                    {"parts": self._split_cells(text), "success": line["success"]}
                )
            else:
                flush_table()
                blocks.append(
                    {
                        "kind": "text",
                        "text": self._escape(text),
                        "success": line["success"],
                    }
                )
        flush_table()
        return blocks

    def _build_context(
        self,
        base: dict,
        lines: list[dict],
        detail_lines: list[dict],
        cap: int | None,
    ) -> dict:
        """Build the template context; every line is shortened to `cap` characters."""
        lines = [{**line, "text": self._cut(line["text"], cap)} for line in lines]
        detail_lines = [
            {**line, "text": self._cut(line["text"], cap)} for line in detail_lines
        ]

        context = dict(base["context"])
        context.update(
            subject=self._escape(self._cut(str(context.get("subject") or ""), cap)),
            status=context.get("status") or "success",
            action_name=self._escape(
                self._cut(str(context.get("action_name") or ""), cap)
            ),
            # Ready-made paragraphs and tables (all texts are already escaped)
            blocks=self._build_blocks(lines),
            detail_blocks=self._build_blocks(detail_lines, merge_first_column=True),
            details_count=base["details_count"],
        )
        return context

    @staticmethod
    def _render_template(template_name: str, context: dict) -> str:
        """Render a Telegram template with the given context."""
        template = templates.env.get_template(f"telegram/{template_name}")
        rendered = template.render(**context)
        # Line breaks between tags are template formatting, not content
        return re.sub(r">\s*\n\s*<", "><", rendered).strip()

    def _render_fitting(self, template_name: str, context: dict) -> str:
        """
        Render the template so that the result fits the Telegram length limit,
        shortening long lines step by step if it does not.

        Raises:
            RuntimeError: If the message is too long even with the shortest lines.
        """
        details = context.get("details")
        if details is None:
            details = []
        elif not isinstance(details, list):
            details = [details]

        lines = self._normalize_lines(context.get("message"))
        detail_lines = self._normalize_lines(details)
        base = {
            "context": context,
            # Blank items are not shown, so they are not counted either
            "details_count": sum(
                1 for item in details if self._normalize_lines([item])
            ),
        }

        for cap in _TRUNCATION_STEPS:
            rendered = self._render_template(
                template_name, self._build_context(base, lines, detail_lines, cap)
            )
            if len(rendered) <= RICH_MAX_LENGTH:
                return rendered

        raise RuntimeError(
            f"rendered message is longer than {RICH_MAX_LENGTH} characters "
            "even after truncation"
        )

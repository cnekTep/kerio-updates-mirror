from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage

import aiosmtplib
from fastapi import status, HTTPException

from app.config import settings, templates, BASE_DIR
from app.utils.app_logging import log_event


@dataclass
class SMTPConfig:
    """Ad-hoc SMTP config, used to override settings.email (e.g. for test sends)."""

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_from_name: str | None = None
    smtp_timeout: int | None = None
    smtp_use_tls: bool = False
    email_to: list[str] | None = None


class EmailService:
    """
    Service layer for sending outbound notification emails (admin
    notifications, error reports, test messages) over SMTP.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def send_notification(
        self,
        subject: str,
        context: dict,
        template_name: str = "default.html",
        to: list[str] | None = None,
        config: SMTPConfig | None = None,
    ) -> None:
        """
        Render an email template and send the resulting HTML email.

        Args:
            subject: Email subject line.
            context: Values to render into the template.
            template_name: Template file name, relative to templates/email/
                (e.g. "default.html").
            to: Override recipient list; defaults to settings.email.email_to.
            config: SMTP config to use instead of settings.email
                (e.g. unsaved values currently typed in the settings form).

        Raises:
            HTTPException: 400 if SMTP is not configured, 500 on any
                other failure (connection error, auth error, etc.).
        """
        try:
            await self._send(
                subject=subject,
                template_name=template_name,
                context=context,
                to=to,
                config=config,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except Exception as exc:
            log_event(
                log_type=["system", "errors"],
                message=f"Email | Error: Failed to send email '{subject}': {exc}",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send email: {exc}",
            ) from exc

        log_event(
            log_type=["system"],
            message=f"Email | Sent: '{subject}'",
        )

    @staticmethod
    def list_email_templates() -> list[str]:
        """
        List .html and .txt files in the email templates directory.

        Returns:
                Sorted list of full email template filenames (with extension).
        """

        templates_dir = BASE_DIR / "templates" / "email"

        # Keep only regular files with .html or .txt extension
        return sorted(
            p.name
            for p in templates_dir.iterdir()
            if p.is_file() and p.suffix.lower() in (".html", ".txt")
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_configured(email_config) -> None:
        """
        Validate that the minimum required SMTP settings are present.

        Raises:
            ValueError: If any required setting is missing.
        """
        if not email_config.smtp_host:
            raise ValueError("SMTP host is not configured")
        if not email_config.smtp_port:
            raise ValueError("SMTP port is not configured")
        if not email_config.smtp_from:
            raise ValueError("SMTP from address is not configured")
        if not email_config.email_to:
            raise ValueError("No recipient email addresses configured")

    async def _send(
        self,
        subject: str,
        template_name: str,
        context: dict,
        to: list[str] | None,
        config: SMTPConfig | None,
    ) -> None:
        """Render the template and dispatch the message over SMTP."""
        # Use the passed-in (e.g. unsaved form) config if given, otherwise fall back to app settings
        email_config = config or settings.email
        self._ensure_configured(email_config)
        recipients = to or email_config.email_to
        sender = (
            Address(
                display_name=email_config.smtp_from_name,
                addr_spec=email_config.smtp_from,
            )
            if email_config.smtp_from_name
            else email_config.smtp_from
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.add_alternative(
            self._render_template(template_name=template_name, context=context),
            subtype="html" if template_name.endswith(".html") else "plain",
        )

        await aiosmtplib.send(
            message,
            hostname=email_config.smtp_host,
            port=email_config.smtp_port,
            username=email_config.smtp_username or None,
            password=email_config.smtp_password or None,
            start_tls=email_config.smtp_use_tls,
            timeout=email_config.smtp_timeout,
        )

    @staticmethod
    def _normalize_line(line: str | dict) -> dict:
        """
        Normalize a single message line into a dict with 'text' and
        'success' keys, so templates can render each line consistently
        regardless of whether callers passed a plain string or an
        already-structured dict (e.g. {"text": ..., "success": ...}).
        """
        if isinstance(line, dict):
            return line
        return {"text": line, "success": True}

    def _normalize_message_lines(self, context: dict) -> dict:
        """
        Ensure context['message'], if present, is a list of dicts with
        'text' and 'success' keys, so templates can render each line
        consistently regardless of whether callers passed a single string,
        a single dict, or a list mixing plain strings and dicts.
        """
        if "message" not in context:
            return context

        message = context["message"]
        # Wrap a bare str/dict into a single-item list so we don't end up
        # iterating over individual characters of a plain string
        lines = message if isinstance(message, list) else [message]

        normalized = dict(context)
        normalized["message"] = [self._normalize_line(line) for line in lines]
        return normalized

    def _render_template(self, template_name: str, context: dict) -> str:
        """Render an email template with the given context."""
        context = self._normalize_message_lines(context)
        template = templates.env.get_template(f"email/{template_name}")
        return template.render(**context)

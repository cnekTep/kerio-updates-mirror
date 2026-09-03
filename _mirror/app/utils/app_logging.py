import asyncio
import logging
from datetime import datetime

from fastapi import BackgroundTasks, HTTPException

# Keeps references to fire-and-forget tasks created outside a request
# context (no BackgroundTasks available), so they aren't garbage-collected
# before completion. Tasks remove themselves once done.
_background_notification_tasks: set[asyncio.Task] = set()


def log_event(
    log_type: str | list[str] | None,
    message: str | list[str | dict[str, str | bool]],
    date: bool = True,
    ip: str | None = None,
    write: bool = True,
    notify: bool = False,
    subject: str = "Kerio Updates Mirror",
    action_name: str = "",
    status: str = "success",
    background_tasks: BackgroundTasks | None = None,
) -> None:
    """
    Public API for logging + optional notifications.

    Args:
        log_type: Log destination(s) to write to (e.g., "system", ["system", "updates"])
        message: Message text to write to the log file(s)
        date: Whether to prefix the message with current timestamp
        ip: Optional IP address to include in the log entry
        write: whether to write the message to log file(s)
        notify: whether to send the message to all notification channels
        subject: Optional subject for notifications
        action_name: Optional action name for notifications
        status: Optional status for notifications (e.g., "success", "error")
        background_tasks: Optional background tasks manager
    """
    if write and log_type:
        if isinstance(message, list):
            message = "\n".join(message)
        _write_log(log_type, message, date, ip)

    if notify:
        if isinstance(message, str):
            message = message.strip().split("\n")
        if log_type and "errors" in log_type:
            subject = "Error | Kerio Updates Mirror"
            status = "error"
        if background_tasks is not None:
            # FastAPI keeps the task alive until the request finishes; no manual tracking needed
            background_tasks.add_task(
                _send_notifications, subject, action_name, status, message
            )
        else:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                _write_log(
                    log_type=["errors"],
                    message="No running event loop, notifications not sent",
                )
                return

            task = loop.create_task(
                _send_notifications(subject, action_name, status, message)
            )
            _background_notification_tasks.add(task)
            task.add_done_callback(_background_notification_tasks.discard)


def read_last_lines(log_type: str, encoding="utf-8", lines=1000):
    """Reads the last lines from the file"""
    try:
        with open(f"./logs/{log_type}.log", "r", encoding=encoding) as file:
            all_lines = file.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"File reading error: {e}"


def _write_log(
    log_type: str | list[str],
    message: str,
    date: bool = True,
    ip: str | None = None,
) -> None:
    """
    Write a formatted message to one or more log files with optional timestamp and IP.

    Args:
        log_type: Log destination(s) to write to (e.g., "system", ["system", "updates"])
        message: Message text to write to the log file(s)
        date: Whether to prefix the message with current timestamp
        ip: Optional IP address to include in the log entry
    """
    now_date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
    logging.warning(f"[{ip}] {message}" if ip else message)

    prefix = ""
    if date:
        prefix = f"[{now_date}] "
    if ip:
        prefix += f"[{ip}] "
    log_message = f"{prefix}{message}\n"

    log_types = [log_type] if isinstance(log_type, str) else log_type

    for log_type in log_types:
        with open(f"./logs/{log_type}.log", "a", encoding="utf-8") as f:
            f.write(log_message)


async def _send_notifications(
    subject: str,
    action_name: str,
    status: str,
    message: list[str],
) -> None:
    """Send message to all configured notification channels."""
    try:
        await _send_email(
            subject=subject,
            action_name=action_name,
            status=status,
            message=message,
        )
    except HTTPException:
        # Already logged inside the underlying notification service before being raised.
        # This is a fire-and-forget notification - there's no client to respond to, so
        # just swallow it here to avoid an unhandled-exception traceback.
        pass
    except Exception as exc:
        # Safety net for anything a notification channel failed to catch/log itself.
        _write_log(
            log_type=["system", "errors"],
            message=f"Notification | Unexpected error sending notification: {exc}",
        )


async def _send_email(
    subject: str,
    action_name: str,
    status: str,
    message: list[str],
) -> None:
    """Send an admin notification email. Raises on failure - caller handles that."""
    # Lazy import to avoid a circular import between app_logging and email
    # service (EmailService itself logs through plain write_log, not this).
    from app.service.email import EmailService

    email_service = EmailService()
    await email_service.send_notification(
        subject=subject,
        template_name="default_html.html",
        context={"action_name": action_name, "status": status, "message": message},
    )

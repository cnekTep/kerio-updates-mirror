from typing import Annotated, Any, Literal

from fastapi import status, APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import get_email_service, get_telegram_service
from app.service.email import EmailService, SMTPConfig
from app.service.telegram import TelegramConfig, TelegramService

router = APIRouter(prefix="/notifications")


@router.post(
    path="/test_email",
    response_class=JSONResponse,
    summary="Send a test email",
    description="Sends a test email synchronously using the SMTP values currently entered in the form (unsaved).",
    status_code=status.HTTP_200_OK,
    name="send_test_email",
    responses={
        200: {
            "description": "Test email sent",
            "content": {"application/json": {"example": {"detail": "Test email sent"}}},
        },
        400: {
            "description": "SMTP is not configured (host, port, from address or recipients are missing)",
            "content": {
                "application/json": {
                    "example": {"detail": "SMTP host is not configured"}
                }
            },
        },
        500: {
            "description": "Failed to send the email (connection error, authentication error, etc.)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to send email: [Errno 111] Connection refused"
                    }
                }
            },
        },
    },
)
async def send_test_email(
    email_service: Annotated[EmailService, Depends(get_email_service)],
    email_to: Annotated[str, Form()] = "",
    smtp_host: Annotated[str, Form()] = "",
    smtp_port: Annotated[int | None, Form()] = None,
    smtp_username: Annotated[str, Form()] = "",
    smtp_password: Annotated[str, Form()] = "",
    smtp_from: Annotated[str, Form()] = "",
    smtp_from_name: Annotated[str, Form()] = "",
    smtp_timeout: Annotated[int | None, Form()] = None,
    smtp_use_tls: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    # Build config from the raw (unsaved) values currently sitting in the form,
    # instead of falling back to settings.email
    config = SMTPConfig(
        smtp_host=smtp_host or None,
        smtp_port=smtp_port,
        smtp_username=smtp_username or None,
        smtp_password=smtp_password or None,
        smtp_from=smtp_from or None,
        smtp_from_name=smtp_from_name or None,
        smtp_timeout=smtp_timeout,
        smtp_use_tls=smtp_use_tls,
        email_to=[addr.strip() for addr in email_to.split(",") if addr.strip()],
    )

    # Send a test email synchronously to verify current SMTP configuration
    await email_service.send_notification(
        subject="Test email from Kerio Updates Mirror",
        context={
            "action_name": "Test email from Kerio Updates Mirror",
            "status": "success",
            "message": "If you received this email, your SMTP settings are working correctly.",
        },
        template_name=settings.notification.email_template,
        config=config,
    )
    return {"detail": "Test email sent"}


@router.post(
    path="/test_telegram",
    response_class=JSONResponse,
    summary="Send a test Telegram message",
    description="Sends a test Telegram message synchronously using the values currently entered in the form (unsaved).",
    status_code=status.HTTP_200_OK,
    name="send_test_telegram",
    responses={
        200: {
            "description": "Test message sent",
            "content": {
                "application/json": {"example": {"detail": "Test message sent"}}
            },
        },
        400: {
            "description": (
                "Telegram is not configured (bot token or chat ID is missing), "
                "the template does not exist, or a thread was chosen "
                "but its thread ID is empty"
            ),
            "content": {
                "application/json": {
                    "example": {"detail": "Telegram bot token is not configured"}
                }
            },
        },
        500: {
            "description": "Failed to send the message (all connection attempts failed, API error, etc.)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to send Telegram message: all connection attempts failed"
                    }
                }
            },
        },
    },
)
async def send_test_telegram(
    telegram_service: Annotated[TelegramService, Depends(get_telegram_service)],
    bot_api_url: Annotated[str, Form()] = "",
    bot_token: Annotated[str, Form()] = "",
    chat_id: Annotated[str, Form()] = "",
    thread_updates_id: Annotated[int | None, Form()] = None,
    thread_errors_id: Annotated[int | None, Form()] = None,
    target: Annotated[Literal["", "updates", "errors"], Form()] = "",
) -> dict[str, Any]:
    # Build config from the raw (unsaved) values currently sitting in the form,
    # instead of falling back to settings.telegram
    config = TelegramConfig(
        bot_api_url=bot_api_url or None,
        bot_token=bot_token or None,
        chat_id=chat_id or None,
    )

    # Pick the thread explicitly from the form; None means the main chat.
    # Without an explicit thread_id the service would fall back to the saved settings.
    thread_id = {"updates": thread_updates_id, "errors": thread_errors_id}.get(target)

    context = {
        "action_name": "Test message from Kerio Updates Mirror",
        "status": "success",
        "message": "If you received this message, your Telegram settings are working correctly.",
        "thread_id": thread_id,
    }

    if target == "updates":
        context["action_name"] = (
            "Test message from Kerio Updates Mirror in Updates Thread"
        )
    elif target == "errors":
        context["action_name"] = (
            "Test message from Kerio Updates Mirror in Errors Thread"
        )

    # A thread was chosen but its ID is empty: refuse instead of silently
    # sending to the main chat under a "... Thread" title
    if target and thread_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thread ID is not specified",
        )

    # Send a test message synchronously to verify current Telegram configuration
    await telegram_service.send_notification(
        subject="Test message from Kerio Updates Mirror",
        context=context,
        template_name=settings.notification.telegram_template,
        config=config,
    )
    return {"detail": "Test message sent"}

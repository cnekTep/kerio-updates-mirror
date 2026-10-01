from typing import Annotated, Any

from fastapi import status, APIRouter, Depends, Form
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import get_email_service
from app.service.email import EmailService, SMTPConfig

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

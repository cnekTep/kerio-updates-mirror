from typing import Annotated

from fastapi import APIRouter, Request, Depends, Form, Header

from app.config import settings
from app.dependencies import get_kerio_update_service
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/registration", tags=["registration"])


@router.post(
    path="",
)
async def get_registration_info(
    request: Request,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    command: str = Form(...),
    content_type: str = Header(...),
    base_id: str = Form(default=""),
    token: str = Form(default=""),
):
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system", "connections"],
        message=f"Registration | {command.capitalize()} request received",
        ip=client_ip if settings.logging.log_ip else None,
    )

    if command.lower() == "connect":
        return await kerio_update_service.get_command_info(
            client_ip=client_ip, content_type=content_type
        )
    elif command.lower() == "lookup":
        return await kerio_update_service.get_lookup_info(
            client_ip=client_ip, base_id=base_id, token=token
        )

    return ""

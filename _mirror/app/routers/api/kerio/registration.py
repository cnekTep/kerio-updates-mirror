from random import randint
from typing import Annotated

from fastapi import APIRouter, Depends, Form

from app.dependencies import get_kerio_update_service, get_client_ip
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/registration", tags=["registration"])


@router.head(
    path="",
)
async def head_registration_info(
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
):
    write_log(
        log_type=["system", "connections"],
        message=f"Registration | HEAD request received",
        ip=client_ip,
    )

    return await kerio_update_service.get_registration_head_info(client_ip=client_ip)


@router.post(
    path="",
)
async def get_registration_info(
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    command: str = Form(...),
    base_id: str = Form(default=""),
    token: str = Form(default=""),
):
    write_log(
        log_type=["system", "connections"],
        message=f"Registration | {command.capitalize()} request received",
        ip=client_ip,
    )

    if command.lower() == "connect":
        return await kerio_update_service.get_registration_connect_info(
            client_ip=client_ip,
            host_id=":".join(f"{randint(0, 255):02X}" for _ in range(6)),
        )
    elif command.lower() == "lookup":
        return await kerio_update_service.get_static_registration_lookup_info(
            client_ip=client_ip,
            base_id=base_id,
            token=token,
        )
    elif command.lower() == "readinfo":
        return await kerio_update_service.get_registration_readinfo_info(
            client_ip=client_ip,
            base_id=base_id,
            token=token,
        )
    elif command.lower() == "stored":
        return await kerio_update_service.get_registration_stored_info(
            client_ip=client_ip,
            base_id=base_id,
            token=token,
        )

    return ""

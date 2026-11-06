from random import randint
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response

from app.dependencies import get_kerio_update_service, get_client_ip
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import log_event, sanitize_for_log

router = APIRouter(prefix="/updates/registration", tags=["registration"])


@router.head(
    path="",
    response_class=Response,
    responses={
        200: {
            "description": "Empty body; Kerio status is passed in the X-Kerio-* headers"
        },
        404: {"description": "Registration updates are disabled"},
    },
)
async def head_registration_info(
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
):
    log_event(
        log_type=["system", "connections"],
        message="Registration | HEAD request received",
        ip=client_ip,
    )

    return await kerio_update_service.get_registration_head_info(client_ip=client_ip)


@router.post(
    path="",
    response_class=Response,
    responses={
        200: {
            "description": "Kerio reply; status is passed in the X-Kerio-* headers",
            "content": {
                "application/x-kerio-registration": {"schema": {"type": "string"}},
                "application/x-kerio-signed-png": {"schema": {"type": "string"}},
            },
        },
        404: {"description": "Registration updates are disabled"},
        502: {"description": "kerio.com is unreachable (connect command)"},
    },
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
    log_event(
        log_type=["system", "connections"],
        message=f"Registration | {sanitize_for_log(command.capitalize())} request received",
        ip=client_ip,
    )

    command_name = command.lower()

    if command_name == "connect":
        return await kerio_update_service.get_registration_connect_info(
            client_ip=client_ip,
            host_id=":".join(f"{randint(0, 255):02X}" for _ in range(6)),
        )
    elif command_name == "lookup":
        return await kerio_update_service.get_static_registration_lookup_info(
            client_ip=client_ip,
            base_id=base_id,
            token=token,
        )
    elif command_name == "readinfo":
        return await kerio_update_service.get_registration_readinfo_info(
            client_ip=client_ip,
            base_id=base_id,
            token=token,
        )
    elif command_name == "stored":
        return await kerio_update_service.get_registration_stored_info(
            client_ip=client_ip,
            base_id=base_id,
            token=token,
        )

    # Unknown command: empty plain body
    return Response(content="")

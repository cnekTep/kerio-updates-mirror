from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse

from app.dependencies import get_kerio_update_service, get_client_ip
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/webfilter", tags=["web filter"])


@router.get(
    path="/key",
    response_class=PlainTextResponse,
    summary="Get Kerio Web Filter key",
    description=(
        "Returns a plain-text web filter activation key for Kerio Control. "
        "Returns 404 if the key is not found or Web Filter updates are disabled."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Web Filter activation key",
            "content": {"text/plain": {"example": "x:xx:xxxxxx:xxxxxxxxxx:xxxxx"}},
        },
        404: {"description": "Web Filter key not found or updates are disabled"},
    },
)
async def get_web_filter_key(
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> str:
    write_log(
        log_type=["system", "connections"],
        message="Web Filter | Key request received",
        ip=client_ip,
    )

    return await kerio_update_service.get_web_filter_key(client_ip=client_ip)

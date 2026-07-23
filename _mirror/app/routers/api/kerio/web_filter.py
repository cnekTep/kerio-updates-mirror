from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.dependencies import get_kerio_update_service
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
    request: Request,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
) -> str:
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system", "connections"],
        message="Web Filter | Key request received",
        ip=client_ip if settings.logging.log_ip else None,
    )

    return await kerio_update_service.get_web_filter_key(client_ip=client_ip)

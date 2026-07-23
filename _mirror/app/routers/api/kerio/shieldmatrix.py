from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.dependencies import get_kerio_update_service
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/shieldmatrix", tags=["shieldmatrix"])


@router.get(
    path="/link",
    response_class=PlainTextResponse,
    summary="Get ShieldMatrix update link",
    description=(
        "Returns a plain-text ShieldMatrix update link for Kerio Control. "
        "Returns 404 if ShieldMatrix updates are disabled."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "ShieldMatrix update link",
            "content": {
                "text/plain": {
                    "example": '{"available": true, "url": "http://kerio-updates-mirror.local/api/kerio/updates/shieldmatrix/files"}'
                }
            },
        },
        404: {"description": "Updates for ShieldMatrix are disabled"},
    },
)
async def get_update_link(
    request: Request,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    last_update: Annotated[
        str, Query(alias="last-update", description="Last update timestamp")
    ] = 0,
) -> str:
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system", "connections"],
        message="ShieldMatrix | Update link request received",
        ip=client_ip if settings.logging.log_ip else None,
    )

    return await kerio_update_service.get_shieldmatrix_update_info(
        client_ip=client_ip, updates_version=last_update
    )


@router.get(
    path="/files/version",
    response_class=PlainTextResponse,
    summary="Get ShieldMatrix update version",
    description="Returns the currently cached ShieldMatrix version string.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "ShieldMatrix version string",
            "content": {"text/plain": {"example": "20240510"}},
        },
        404: {
            "description": "ShieldMatrix updates are disabled or version not yet cached"
        },
    },
)
async def get_update_version(
    request: Request,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
) -> str:
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system"],
        message="ShieldMatrix | Update version request received",
        ip=client_ip if settings.logging.log_ip else None,
    )

    return await kerio_update_service.get_shieldmatrix_update_version(
        client_ip=client_ip
    )


@router.get(
    path="/files/{full_path:path}",
    summary="Download ShieldMatrix update file",
    description=(
        "Serves a ShieldMatrix update file by its path. "
        "Files are served from local disk and downloaded from upstream on demand. "
        "Returns 404 if ShieldMatrix updates are disabled or the file is not found, "
        "400 if the path format is invalid, "
        "502 if the upstream request fails."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "ShieldMatrix update file content"},
        400: {"description": "Path format is invalid"},
        404: {"description": "ShieldMatrix updates are disabled or file not found"},
        502: {"description": "Failed to download ShieldMatrix file"},
    },
)
async def get_update_file(
    request: Request,
    full_path: str,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
):
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system"],
        message=f"ShieldMatrix | Update file request received: {request.url}",
        ip=client_ip if settings.logging.log_ip else None,
    )

    return await kerio_update_service.get_shieldmatrix_update_file(
        client_ip=client_ip, full_path=full_path
    )

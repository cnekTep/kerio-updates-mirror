from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.dependencies import get_kerio_update_service, get_client_ip
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/antivirus", tags=["antivirus"])


@router.get(
    path="/link",
    response_class=PlainTextResponse,
    summary="Get antivirus update link",
    description=(
        "Returns a plain-text antivirus update link for Kerio Control. "
        "Depending on configuration, the link points either to the local mirror "
        "or to external servers. "
        "Returns 404 if antivirus updates are disabled, "
        "403 if the license number is missing or invalid."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Antivirus update link",
            "content": {
                "text/plain": {
                    "example": "THDdir=http://kerio-updates-mirror.local/api/kerio/updates/antivirus/files"
                }
            },
        },
        403: {"description": "License number is missing or invalid"},
        404: {"description": "Updates for Antivirus are disabled"},
    },
)
async def get_update_link(
    version: Annotated[str, Query(description="Kerio Control version")],
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> str:
    write_log(
        log_type=["system", "connections"],
        message="Antivirus | Update link request received",
        ip=client_ip,
    )

    return await kerio_update_service.get_antivirus_update_info(
        client_ip=client_ip,
        version=version,
    )


@router.get(
    path="/files/{full_path:path}",
    summary="Download antivirus update file",
    description=(
        "Serves an antivirus update file by its relative path. "
        "In cache mode, files are served from local disk and downloaded from Kerio CDN on demand; "
        "versions.id is refreshed based on the antivirus TTL, and all sibling versions.* files are evicted "
        "and re-fetched when versions.id expires. "
        "versions.dat.gz is intentionally skipped to force the client to fall back to the uncompressed variant. "
        "In proxy mode, every request is forwarded directly to Kerio CDN. "
        "Returns 404 if antivirus updates are disabled or the file is not found, "
        "502 if the upstream CDN request fails, "
        "503 if stale versions.* files could not be evicted (retry later)."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Antivirus update file content"},
        404: {"description": "Antivirus updates are disabled or file not found"},
        502: {"description": "Upstream CDN request failed"},
        503: {"description": "Failed to evict stale versions files, retry later"},
    },
)
async def get_update_file(
    request: Request,
    full_path: str,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
):
    write_log(
        log_type=["system"],
        message=f"Antivirus | Update file request received: {request.url}",
        ip=client_ip,
    )

    return await kerio_update_service.get_antivirus_update_file(
        client_ip=client_ip,
        full_path=full_path,
    )

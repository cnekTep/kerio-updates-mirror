from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, Response

from app.dependencies import get_kerio_update_service, get_client_ip
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/antispam", tags=["antispam"])


@router.get(
    path="/files/{full_path:path}",
    summary="Download antispam update file",
    description=(
        "Serves an antispam update file by its relative path. "
        "In cache mode, files are served from local disk and downloaded from the upstream CDN on demand; "
        "versions.id is refreshed based on the antispam TTL, and all sibling versions.* files are evicted "
        "and re-fetched when versions.id expires. "
        "versions.dat.gz is intentionally skipped to force the client to fall back to the uncompressed variant. "
        "In proxy mode, every request is forwarded directly to the upstream CDN. "
        "Returns 404 if antispam updates are disabled or the file is not found, "
        "502 if the upstream CDN request fails, "
        "503 if stale versions.* files could not be evicted (retry later)."
    ),
    status_code=status.HTTP_200_OK,
    response_model=None,
    responses={
        200: {"description": "Antispam update file content"},
        404: {"description": "Antispam updates are disabled or file not found"},
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
) -> Response | FileResponse:
    write_log(
        log_type=["system"],
        message=f"Antispam | Update file request received: {request.url}",
        ip=client_ip,
    )

    return await kerio_update_service.get_antispam_update_file(
        client_ip=client_ip,
        full_path=full_path,
    )

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse, PlainTextResponse

from app.dependencies import get_kerio_update_service, get_client_ip
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/geoip", tags=["geoip"])


@router.get(
    path="/link",
    response_class=PlainTextResponse,
    summary="Get GeoIP update link",
    description=(
        "Returns a plain-text GeoIP version and update link for Kerio Control. "
        "Returns 400 if the version format is invalid, "
        "404 if no update is available for the requested version."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "GeoIP version and update link",
            "content": {
                "text/plain": {
                    "example": (
                        "0:5.20260101\n"
                        "full:https://kerio-updates-mirror.local/api/kerio/updates/geoip/files/geoip_5_20260101.gz"
                    )
                }
            },
        },
        400: {"description": "Invalid version format"},
        404: {"description": "Update not available for this version or file not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_update_link(
    version: Annotated[str, Query(description="GeoIP version (x.y)")],
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> str:
    write_log(
        log_type=["system", "connections"],
        message=f"GeoIP v{version} | Update link request received",
        ip=client_ip,
    )

    return await kerio_update_service.get_geoip_update_info(
        version=version,
        client_ip=client_ip,
    )


@router.get(
    path="/files/{file_name}",
    summary="Download GeoIP update file",
    description=(
        "Serves a GeoIP update file by its name from local disk. "
        "Returns 400 if the file name is invalid, "
        "404 if the file is not found."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "GeoIP update file content"},
        400: {"description": "Invalid file name"},
        404: {"description": "Update file not found on disk"},
    },
)
async def get_update_file(
    request: Request,
    file_name: str,
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> FileResponse:
    write_log(
        log_type=["system"],
        message=f"GeoIP | Update file request received: {request.url}",
        ip=client_ip,
    )

    file_path = kerio_update_service.validate_and_get_file_path(
        file_name=file_name,
        client_ip=client_ip,
    )
    return FileResponse(file_path)

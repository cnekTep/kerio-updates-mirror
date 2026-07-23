from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse, PlainTextResponse

from app.config import settings
from app.dependencies import get_kerio_update_service
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/ids", tags=["ids"])


@router.get(
    path="/link",
    response_class=PlainTextResponse,
    summary="Get IDS/IPS update link",
    description=(
        "Returns a plain-text IDS/IPS version and update link for Kerio Control. "
        "Returns 400 if the version format is invalid, "
        "404 if no update is available for the requested version."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "IDS/IPS version and update link",
            "content": {
                "text/plain": {
                    "example": (
                        "0:5.114\n"
                        "full:https://kerio-updates-mirror.local/api/kerio/updates/ids/files/ids_5_114.gz"
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
    request: Request,
    version: Annotated[str, Query(description="IDS version (x.y)")],
    kerio_update_service: Annotated[
        KerioUpdateService, Depends(get_kerio_update_service)
    ],
) -> str:
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system", "connections"],
        message=f"IDS v{version} | Update link request received",
        ip=client_ip if settings.logging.log_ip else None,
    )

    return await kerio_update_service.get_ids_update_info(
        version=version, client_ip=client_ip
    )


@router.get(
    path="/files/{file_name}",
    summary="Download IDS/IPS update file",
    description=(
        "Serves an IDS/IPS update file by its name from local disk. "
        "Returns 400 if the file name is invalid, "
        "404 if the file is not found."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "IDS/IPS update file content"},
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
) -> FileResponse:
    client_ip = request.client.host if request.client else None

    write_log(
        log_type=["system"],
        message=f"IDS | Update file request received: {request.url}",
        ip=client_ip if settings.logging.log_ip else None,
    )

    file_path = kerio_update_service.validate_and_get_file_path(file_name=file_name)
    return FileResponse(file_path)

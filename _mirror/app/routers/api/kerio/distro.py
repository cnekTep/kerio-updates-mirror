from typing import Annotated

from fastapi import APIRouter, Depends, Form, status
from fastapi.responses import PlainTextResponse, FileResponse, Response

from app.dependencies import get_distro_service, get_client_ip
from app.service.distro import DistroService
from app.utils.app_logging import log_event

router = APIRouter(prefix="/updates/distro", tags=["distro"])

SELECT_IDS: dict[str, str] = {
    "control": "kerio_control_update_file",
    "connect_win": "kerio_connect_update_file_win",
    "connect_deb": "kerio_connect_update_file_deb",
}


@router.post(
    path="/check",
    response_class=PlainTextResponse,
    summary="Kerio Control/Connect distribution version-check callback",
    description=(
        "Handles the form-encoded version-check request sent by Kerio Control "
        "and Kerio Connect appliances themselves. Returns a 'no update' response "
        "if distro updates are disabled in settings, the caller doesn't identify "
        "as a supported product (prod_code not in {'KWF', 'KMS'}), or - for "
        "Kerio Connect - the reported os_platform/InstallationType combination "
        "isn't one of the supported platforms (Windows x64, or Linux x64 with "
        "InstallationType='deb'); otherwise compares versions and returns the "
        "reminder-protocol response. Returns 400 if version fields are missing, "
        "422 if they're present but not valid integers, and 500 if the "
        "configured target version can't be resolved."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Update availability info",
            "content": {
                "text/plain": {
                    "example": "--INFO--\nReminderId='1'\nReminderAuth='1'\nVersion='0'"
                }
            },
        },
        400: {"description": "Version fields are missing"},
        422: {"description": "Version fields present but not valid integers"},
        500: {"description": "Target update version misconfigured"},
    },
)
async def check_update(
    distro_service: Annotated[DistroService, Depends(get_distro_service)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    prod_code: str = Form(default=""),
    prod_major: int | None = Form(default=None),
    prod_minor: int | None = Form(default=None),
    prod_build: int | None = Form(default=None),
    prod_build_number: int | None = Form(default=None),
    os_platform: str | None = Form(default=None),
    installation_type: str | None = Form(default=None, alias="InstallationType"),
) -> str:
    log_event(
        log_type=["system", "connections"],
        message="Distro | Update link request received",
        ip=client_ip,
    )

    return await distro_service.get_distro_update_info(
        prod_code=prod_code,
        prod_major=prod_major,
        prod_minor=prod_minor,
        prod_build=prod_build,
        prod_build_number=prod_build_number,
        os_platform=os_platform,
        installation_type=installation_type,
        client_ip=client_ip,
    )


@router.get(
    path="/files/{file_name}",
    summary="Download a Kerio Control/Connect distribution file",
    description=(
        "Serves a Kerio Control/Connect distribution (.deb, .exe or .img) or "
        "signature (.sig) file by its name."
        "Returns 400 if the file name is invalid, 404 if the file is not found."
    ),
    status_code=status.HTTP_200_OK,
    response_model=None,
    responses={
        200: {"description": "Distribution file content"},
        400: {"description": "Invalid file name"},
        404: {"description": "Distribution file not found on disk"},
    },
)
async def get_update_file(
    file_name: str,
    distro_service: Annotated[DistroService, Depends(get_distro_service)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> Response | FileResponse:
    log_event(
        log_type=["system", "connections"],
        message="Distro | Update file request received",
        ip=client_ip,
    )

    return distro_service.get_distro_file(
        file_name=file_name,
        client_ip=client_ip,
    )

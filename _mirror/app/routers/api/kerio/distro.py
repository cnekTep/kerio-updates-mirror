from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse, Response

from app.config import templates
from app.dependencies import get_distro_service, get_client_ip
from app.service.distro import DistroService
from app.utils.app_logging import write_log

router = APIRouter(prefix="/updates/distro", tags=["distro"])


@router.post(
    path="/check",
    response_class=PlainTextResponse,
    summary="Kerio Control distribution version-check callback",
    description=(
        "Handles the form-encoded version-check request sent by Kerio Control "
        "appliances themselves. Returns a 'no update' response if distro updates "
        "are disabled in settings or the caller doesn't identify as Kerio Control "
        "(prod_code != 'KWF'); otherwise compares versions and returns the "
        "reminder-protocol response. Returns 400 if prod_code is 'KWF' but version "
        "fields are missing, 422 if they're present but not valid integers, and 500 "
        "if the configured target version can't be resolved."
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
        400: {"description": "prod_code is 'KWF' but version fields are missing"},
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
) -> str:
    write_log(
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
        client_ip=client_ip,
    )


@router.get(
    path="/files/{file_name}",
    summary="Download a Kerio Control distribution file",
    description=(
        "Serves a Kerio Control distribution (.img) or signature (.sig) file by its name. "
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
    write_log(
        log_type=["system", "connections"],
        message="Distro | Update file request received",
        ip=client_ip,
    )

    return distro_service.get_distro_file(
        file_name=file_name,
        client_ip=client_ip,
    )


@router.post(
    path="/upload",
    name="upload_distro",
    summary="Upload a Kerio Control distributive file",
    description=(
        "Uploads and digitally signs a Kerio Control upgrade image. "
        "Expected filename format: kerio-control-upgrade-{version}.img"
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "File uploaded and signed successfully"},
        400: {"description": "Invalid filename format"},
        500: {"description": "Internal server error"},
    },
)
async def upload_distro(
    request: Request,
    distro_file: Annotated[UploadFile, File(description="Distributive image")],
    distro_service: Annotated[DistroService, Depends(get_distro_service)],
) -> HTMLResponse:
    filename = await distro_service.upload_distro_file(file=distro_file)

    distro_list = distro_service.list_distros()
    return templates.TemplateResponse(
        request=request,
        name="components/settings/update/_distro_select.html",
        context={
            "distro_list": distro_list,
            "update_kerio_control_distro": True,
            "kerio_control_update_file": filename,
            "oob": True,
        },
    )

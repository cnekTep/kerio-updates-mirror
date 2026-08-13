from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import get_client_ip, require_write_token
from app.utils.app_logging import write_log

router = APIRouter(prefix="/license", tags=["license"])


@router.patch(
    path="/key",
    response_class=JSONResponse,
    summary="Update Mirror license key",
    description=(
        "Sets the Kerio Control product license number used for update checks. "
        "Requires a write-scoped API token (X-API-Key header)."
    ),
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write_token)],
    responses={
        200: {
            "description": "License number updated",
            "content": {
                "application/json": {"example": {"license_number": "XXXX-XXXX-XXXX"}}
            },
        },
        401: {"description": "Missing or invalid API key"},
        503: {"description": "Write API token is not configured on the server"},
    },
)
async def update_mirror_key(
    license_number: Annotated[str, Body(embed=True)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> dict[str, Any]:
    write_log(
        log_type=["system", "connections"],
        message="API | License | Key updated",
        ip=client_ip,
    )

    settings.bulk_update(
        {
            f"updates.license_number": license_number,
            f"updates.license_number_last_update": date.today(),
        }
    )
    return {"license_number": settings.updates.license_number}

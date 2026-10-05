from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.dependencies import get_client_ip, require_write_token, get_license_service
from app.service.license import LICENSE_KEY_PATTERN, LicenseService
from app.utils.app_logging import log_event

router = APIRouter(prefix="/license", tags=["license"])


class LicenseKeyUpdate(BaseModel):
    license_number: str
    expiration_date: date | None = None

    @field_validator("license_number")
    @classmethod
    def validate_license_number(cls, value: str) -> str:
        value = value.strip()
        if not LICENSE_KEY_PATTERN.fullmatch(value):
            raise ValueError(
                "Invalid license number format (expected NNNNN-XXXXX-XXXXX)"
            )
        # Normalize to upper case so stored values are consistent
        return value.upper()


@router.patch(
    path="/key",
    response_class=JSONResponse,
    summary="Update Mirror license key",
    description=(
        "Sets the Kerio Control product license number used for update checks. "
        "The previously stored expiration date is always reset, since it belongs "
        "to the old key. "
        "If expiration_date is provided, it is stored as is. "
        "If expiration_date is omitted or null, the expiration date is fetched in the "
        "background (only if autocheck is enabled in settings). "
        "Requires a write-scoped API token (X-API-Key header)."
    ),
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_write_token)],
    responses={
        200: {
            "description": "License key updated",
            "content": {
                "application/json": {
                    "examples": {
                        "manual": {
                            "summary": "expiration_date provided",
                            "value": {
                                "detail": "License key and expiration date updated"
                            },
                        },
                        "auto": {
                            "summary": "expiration_date omitted, autocheck enabled",
                            "value": {
                                "detail": "License key updated, expiration date lookup started"
                            },
                        },
                        "no_autocheck": {
                            "summary": "expiration_date omitted, autocheck disabled",
                            "value": {"detail": "License key updated"},
                        },
                    }
                }
            },
        },
        401: {"description": "Missing or invalid API key"},
        422: {"description": "Invalid license number format or date"},
        503: {"description": "Write API token is not configured on the server"},
    },
)
async def update_mirror_key(
    payload: LicenseKeyUpdate,
    license_service: Annotated[LicenseService, Depends(get_license_service)],
    background_tasks: BackgroundTasks,
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> dict[str, Any]:
    # Without an explicit date, the old one belongs to the previous key, so reset it
    updates: dict[str, Any] = {
        "updates.license_number": payload.license_number,
        "updates.license_number_last_update": date.today(),
        "updates.license_exp_date": payload.expiration_date,
    }
    settings.bulk_update(updates)

    log_event(
        log_type=["system", "connections"],
        message="API | License | Key updated",
        ip=client_ip,
    )

    if payload.expiration_date is not None:
        return {"detail": "License key and expiration date updated"}

    if settings.updates.license_exp_date_autocheck:
        # Runs after the response is sent; settings are already saved
        background_tasks.add_task(
            license_service.update_expiration_date,
            license_number=payload.license_number,
            notify=False,
        )
        return {"detail": "License key updated, expiration date lookup started"}

    return {"detail": "License key updated"}

from typing import Annotated

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.responses import RedirectResponse

from app.dependencies import get_mirror_update_service
from app.service.mirror_update import MirrorUpdateService

router = APIRouter(prefix="/updates")


@router.post(
    path="/full",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start full mirror update",
    response_description="Update started successfully",
    name="full_mirror_update",
)
async def update_mirror(
    background_tasks: BackgroundTasks,
    mirror_update_service: Annotated[
        MirrorUpdateService, Depends(get_mirror_update_service)
    ],
) -> RedirectResponse:
    # Add full mirror update to background tasks queue
    background_tasks.add_task(mirror_update_service.full_mirror_update)

    return RedirectResponse(
        url="/web/logs/updates", status_code=status.HTTP_303_SEE_OTHER
    )

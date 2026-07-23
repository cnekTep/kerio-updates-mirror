from fastapi import APIRouter

from .auth import router as auth_router
from .pages import router as pages_router
from .updates import router as updates_router

router = APIRouter(prefix="/web", tags=["web"], include_in_schema=False)

router.include_router(auth_router)
router.include_router(updates_router)
router.include_router(pages_router)

from fastapi import APIRouter

from .license import router as license_router

router = APIRouter(prefix="/settings")

router.include_router(license_router)

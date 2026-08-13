from fastapi import APIRouter

from .kerio import router as kerio_router
from .settings import router as settings_router

router = APIRouter(prefix="/api")


router.include_router(kerio_router)
router.include_router(settings_router)

from fastapi import APIRouter

from .kerio import router as kerio_router

router = APIRouter(prefix="/api")


router.include_router(kerio_router)

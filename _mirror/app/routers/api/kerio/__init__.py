from fastapi import APIRouter

from .antispam import router as update_antispam_router
from .antivirus import router as update_antivirus_router
from .distro import router as update_distro_router
from .geoip import router as update_geoip_router
from .ids import router as update_ids_router
from .registration import router as update_registration_router
from .shieldmatrix import router as update_shieldmatrix_router
from .web_filter import router as update_web_filter_router

router = APIRouter(prefix="/kerio")

router.include_router(update_antispam_router)
router.include_router(update_antivirus_router)
router.include_router(update_distro_router)
router.include_router(update_geoip_router)
router.include_router(update_ids_router)
router.include_router(update_registration_router)
router.include_router(update_shieldmatrix_router)
router.include_router(update_web_filter_router)

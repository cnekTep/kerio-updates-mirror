from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.requests import Request

from app.config import settings
from app.service.auth import AuthService
from app.service.distro import DistroService
from app.service.geoip import GeoIPService
from app.service.ids import IDSService
from app.service.kerio_update import KerioUpdateService
from app.service.mirror_update import MirrorUpdateService
from app.service.nginx_acl import NginxACLService
from app.service.settings import SettingsService
from app.service.web_filter import WebFilterService


async def get_kerio_update_service() -> KerioUpdateService:
    """Get KerioUpdateService instance."""
    return KerioUpdateService()


async def get_mirror_update_service() -> MirrorUpdateService:
    """Get MirrorUpdateService instance."""
    return MirrorUpdateService(
        geoip_service=GeoIPService(),
        ids_service=IDSService(),
        kerio_update_service=KerioUpdateService(),
        web_filter_service=WebFilterService(),
    )


def get_nginx_acl_service() -> NginxACLService:
    """Get NginxACLService instance."""
    return NginxACLService()


def get_auth_service() -> AuthService:
    """Get AuthService instance."""
    return AuthService(
        enabled=settings.security.auth,
        username=settings.security.username,
        password_hash=settings.security.password_hash,
        secret_key=settings.security.secret_key,
    )


async def get_settings_service(
    nginx_acl_service: Annotated[NginxACLService, Depends(get_nginx_acl_service)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    distro_service: Annotated[DistroService, Depends(get_distro_service)],
) -> SettingsService:
    """Get SettingsService instance."""
    return SettingsService(
        nginx_acl_service=nginx_acl_service,
        auth_service=auth_service,
        distro_service=distro_service,
    )


async def get_distro_service() -> DistroService:
    """Get DistroService instance."""
    return DistroService()


def require_auth(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> bool:
    """
    Dependency that protects a route. Skips the check entirely when auth is
    disabled in settings. HTMX requests get an HX-Redirect header instead of
    a standard Location redirect, since HTMX does not follow those automatically.
    """
    if not auth_service.enabled:
        return True

    if auth_service.is_authenticated(request):
        return True

    if request.headers.get("HX-Request"):
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Redirecting to login",
            headers={"HX-Redirect": "/web/login"},
        )

    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/web/login"},
    )

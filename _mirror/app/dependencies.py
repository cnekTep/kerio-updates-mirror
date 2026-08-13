import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.requests import Request
from fastapi.security import APIKeyHeader

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

# =============================================================================
# Security schemes
#
# Module-level singletons describing *how* credentials are extracted from a
# request. FastAPI builds these once at import time and reuses them.
# =============================================================================

# Reads the X-API-Key header. auto_error=False so a missing header doesn't
# trigger FastAPI's default 403 - instead api_key comes through as None and
# require_write_token below decides how to respond (keeps error handling
# consistent: same 401 for "missing" and "invalid" cases).
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Write-access API token",
)


# =============================================================================
# Service providers
#
# Simple factory functions that build service instances from current settings.
# =============================================================================


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


async def get_distro_service() -> DistroService:
    """Get DistroService instance."""
    return DistroService()


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


# =============================================================================
# Route guards
#
# Dependencies that protect routes: they validate the request and either
# return normally (access granted) or raise an HTTPException.
# =============================================================================


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


def require_write_token(
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> None:
    """
    Dependency that protects write endpoints via a single static API token
    (X-API-Key header). Raises 401 if the header is missing or doesn't match,
    503 if no token has been configured on the server at all.
    """
    if not settings.security.api_write_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Write API token is not configured",
        )

    # constant-time comparison to avoid leaking the token via timing attacks
    if not api_key or not secrets.compare_digest(
        api_key, settings.security.api_write_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# =============================================================================
# Misc request-scoped helpers
# =============================================================================


def get_client_ip(request: Request) -> str | None:
    """
    Dependency that extracts the client's IP address from the request.

    Returns None if IP logging is disabled in settings or if client info
    is unavailable (e.g. request came through a test client without connection info).
    """
    client = request.client
    return client.host if settings.logging.log_ip and client else None

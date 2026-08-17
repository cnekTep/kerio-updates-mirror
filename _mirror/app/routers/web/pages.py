import secrets
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.config import templates, settings
from app.dependencies import (
    get_settings_service,
    get_nginx_acl_service,
    require_auth,
    get_distro_service,
)
from app.service.distro import DistroService
from app.service.nginx_acl import NginxACLService
from app.service.settings import SettingsService
from app.utils.app_logging import read_last_lines
from app.utils.file_utils import delete_file

router = APIRouter(dependencies=[Depends(require_auth)])

GENERAL_SECTIONS = {"main", "information"}
LOG_SECTIONS = {"system", "updates", "connections", "errors"}
SETTINGS_SECTIONS = {"update", "connection", "security"}


def _active_priority() -> list[str]:
    """Returns download_priority filtered to only currently enabled connection methods."""
    if_tor_enabled = settings.network.tor if settings.has_tor else False
    if_xray_enabled = settings.network.xray if settings.has_xray else False

    active = {
        m
        for m, enabled in [
            ("direct", settings.network.direct),
            ("xray", if_xray_enabled),
            ("tor", if_tor_enabled),
            ("proxy", settings.network.proxy),
        ]
        if enabled
    }
    return [m for m in settings.network.download_priority.split(",") if m in active]


def _security_context(nginx_acl_service: NginxACLService) -> dict:
    """Reads nginx ACL files and returns security settings context for templates."""
    web_restricted, web_ips = nginx_acl_service.read("web")
    api_restricted, api_ips = nginx_acl_service.read("api")
    return {
        "web_allowed_ips": web_restricted,
        "web_allowed_ips_list": web_ips,
        "api_allowed_ips": api_restricted,
        "api_allowed_ips_list": api_ips,
    }


def _get_license_display_data(
    license_last_update: date | None,
    license_exp_date: date | None,
    days_to_expiration: int,
) -> dict[str, date | None | str | bool]:
    """Pick the more recent of two license-related dates and prepare display data."""
    candidates = [
        ("exp_date", license_exp_date, "License expiration date"),
        ("last_update", license_last_update, "Last update date of license number"),
    ]
    present = [c for c in candidates if c[1] is not None]

    if not present:
        return {
            "lic_display_date": None,
            "lic_number_tooltip": None,
            "lic_date_is_expiring": False,
        }

    # Pick entry with the max date
    field_name, value, tooltip = max(present, key=lambda item: item[1])

    # Highlight in red only if the winning date is the expiration date
    # and it expires in less than days_to_expiration days
    is_expiring = False
    if field_name == "exp_date":
        days_left = (value - date.today()).days
        is_expiring = days_left <= days_to_expiration

    return {
        "lic_display_date": value,
        "lic_number_tooltip": tooltip,
        "lic_date_is_expiring": is_expiring,
    }


@router.get(path="/", response_class=HTMLResponse, name="main_page")
async def index():
    return RedirectResponse(url="/web/general/main")


@router.get(path="/404", response_class=HTMLResponse)
async def not_found(request: Request):
    if not request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request, name="pages/index.html", context={"active": "web/404"}
        )
    return templates.TemplateResponse(request=request, name="components/404.html")


@router.get(path="/general/{name}", response_class=HTMLResponse)
async def general(request: Request, name: str):
    if name not in GENERAL_SECTIONS:
        return RedirectResponse(url="/web/404")

    if not request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="pages/index.html",
            context={"active": f"web/general/{name}"},
        )

    license_display_data = _get_license_display_data(
        license_last_update=settings.updates.license_number_last_update,
        license_exp_date=settings.updates.license_exp_date,
        days_to_expiration=settings.updates.license_expiration_days,
    )

    return templates.TemplateResponse(
        request=request,
        name=f"components/general/{name}.html",
        context={
            "license_number": settings.updates.license_number,
            "license_display_date": license_display_data["lic_display_date"],
            "license_number_tooltip": license_display_data["lic_number_tooltip"],
            "license_date_is_expiring": license_display_data["lic_date_is_expiring"],
            "update_web_filter_key": settings.updates.update_web_filter_key,
            "web_filter_key": settings.updates.web_filter_key,
            "web_filter_key_last_update": settings.updates.web_filter_key_last_update,
            "ids_2_version": settings.updates.ids_2_version,
            "ids_2_last_update": settings.updates.ids_2_last_update,
            "update_ids_3": settings.updates.update_ids_3,
            "ids_3_version": settings.updates.ids_3_version,
            "ids_3_last_update": settings.updates.ids_3_last_update,
            "update_ids_5": settings.updates.update_ids_5,
            "ids_5_version": settings.updates.ids_5_version,
            "ids_5_last_update": settings.updates.ids_5_last_update,
            "update_geoip_4": settings.updates.update_geoip_4,
            "geoip_4_version": settings.updates.geoip_4_version,
            "geoip_4_last_update": settings.updates.geoip_4_last_update,
            "update_geoip_5": settings.updates.update_geoip_5,
            "geoip_5_version": settings.updates.geoip_5_version,
            "geoip_5_last_update": settings.updates.geoip_5_last_update,
        },
    )


@router.get(path="/logs/{name}", response_class=HTMLResponse)
async def get_logs(
    request: Request,
    name: str,
    partial: bool = Query(default=False),
):
    if name not in LOG_SECTIONS:
        return RedirectResponse(url="/web/404")

    if not request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="pages/index.html",
            context={"active": f"web/logs/{name}"},
        )

    log = read_last_lines(log_type=name, lines=settings.user.log_lines)

    if partial:
        return templates.TemplateResponse(
            request=request, name="components/log/log_lines.html", context={"log": log}
        )
    return templates.TemplateResponse(
        request=request, name="components/log/log.html", context={"log": log}
    )


@router.post(path="/logs/{name}", response_class=HTMLResponse)
async def clear_logs(request: Request, name: str):
    delete_file(settings.logging.log_dir / f"{name}.log")
    return templates.TemplateResponse(
        request=request,
        name="components/log/log_lines.html",
        context={"log": "Log cleared"},
    )


@router.get(path="/settings/{name}", response_class=HTMLResponse)
async def get_settings(
    request: Request,
    name: str,
    nginx_acl_service: Annotated[NginxACLService, Depends(get_nginx_acl_service)],
    distro_service: Annotated[DistroService, Depends(get_distro_service)],
):
    if name not in SETTINGS_SECTIONS:
        return RedirectResponse(url="/web/404")

    settings_data = {
        # Update settings
        "license_number": settings.updates.license_number,
        "license_exp_date": settings.updates.license_exp_date,
        "update_ids_3": settings.updates.update_ids_3,
        "update_ids_5": settings.updates.update_ids_5,
        "update_geoip_4": settings.updates.update_geoip_4,
        "geoip_custom_url": settings.updates.geoip_custom_url,
        "update_geoip_5": settings.updates.update_geoip_5,
        "geoip_5_copy_geoname_id": settings.updates.geoip_5_copy_geoname_id,
        "update_web_filter_key": settings.updates.update_web_filter_key,
        "forced_web_filter_key": settings.updates.forced_web_filter_key,
        "update_shieldmatrix": settings.updates.update_shieldmatrix,
        "update_antivirus": settings.updates.update_antivirus,
        "antivirus_url": settings.updates.antivirus_url,
        "antivirus_through_mirror": settings.updates.antivirus_through_mirror,
        "antivirus_cache": settings.updates.antivirus_cache,
        "update_antispam": settings.updates.update_antispam,
        "antispam_url": settings.updates.antispam_url,
        "antispam_cache": settings.updates.antispam_cache,
        "update_kerio_control_distro": settings.updates.update_kerio_control_distro,
        "kerio_control_update_file": settings.updates.kerio_control_update_file,
        "distro_list": distro_service.list_distros(),
        # Connection settings
        "direct": settings.network.direct,
        "xray": settings.network.xray if settings.has_xray else False,
        "has_xray": settings.has_xray,
        "tor": settings.network.tor if settings.has_tor else False,
        "has_tor": settings.has_tor,
        "proxy": settings.network.proxy,
        "proxy_type": settings.network.proxy_type,
        "proxy_host": settings.network.proxy_host,
        "proxy_port": settings.network.proxy_port,
        "proxy_username": settings.network.proxy_username,
        "proxy_password": settings.network.proxy_password,
        "download_priority": _active_priority(),
        # Privacy settings
        "auth": settings.security.auth,
        "username": settings.security.username,
        "password": bool(settings.security.password_hash),
        **_security_context(nginx_acl_service),
        "has_nginx": settings.has_nginx,
        "api_write_token": settings.security.api_write_token,
    }

    if not request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="pages/index.html",
            context={"active": f"web/settings/{name}"},
        )

    return templates.TemplateResponse(
        request=request,
        name=f"components/settings/{name}.html",
        context={**settings_data},
    )


@router.post(
    path="/settings/api-token/generate",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    name="generate_api_token",
)
async def generate_api_token(request: Request) -> HTMLResponse:
    token = secrets.token_urlsafe(32)  # Generate a secure random token

    return templates.TemplateResponse(
        request=request,
        name="components/settings/security/api_token_input.html",
        context={"api_write_token": token},
    )


@router.post(
    path="/settings/{name}",
    response_class=Response,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def save_settings(
    request: Request,
    name: str,
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
) -> Response:
    if name not in SETTINGS_SECTIONS:
        return RedirectResponse(url="/404")

    form = await request.form()
    result = await settings_service.save(name=name, form=form)
    if result:
        return Response(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"HX-Redirect": "/web/login"},
        )
    return templates.TemplateResponse(
        request=request,
        name="partials/navbar.html",
        context={"auth": settings.security.auth},
    )


# Catch-all route
@router.get("/{path:path}")
async def catch_all():
    return RedirectResponse(url="/web/404")

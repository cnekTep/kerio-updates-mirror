import requests
from flask import Response
from flask import request
from flask_babel import gettext as _

from config.config_env import config
from db.database import get_webfilter_key, add_webfilter_key
from utils.internet_utils import add_proxy_to_params, prepare_request_params
from utils.logging import write_log


def handle_webfilter():
    """Handler for Web Filter key request"""
    write_log(
        log_type="system",
        message=_("Received request for Web Filter key"),
        ip=request.remote_addr if config.ip_logging else None,
    )
    webfilter_key = get_webfilter_key(lic_number=config.license_number)

    if not webfilter_key:
        return Response(response="404 Not found", status=404, mimetype="text/plain")

    # Create and return response with status code 200 and Web Filter key as response body
    return Response(response=webfilter_key, status=200)


def update_web_filter_key() -> None:
    """Updates Web Filter key by fetching it from Kerio server"""
    if not config.license_number:
        log_message = _("Web Filter: passing because license key is not configured")
        write_log(log_type=["system", "updates"], message=log_message)
        return

    webfilter_key = get_webfilter_key(lic_number=config.license_number)

    if webfilter_key:
        log_message = _("Web Filter: database already contains an actual Web Filter key")
        write_log(log_type=["system", "updates"], message=log_message)
        return

    write_log(log_type="system", message=_("Fetching new Web Filter key from wf-activation.kerio.com server"))
    target_host = "wf-activation.kerio.com"
    url = f"https://wf-activation.kerio.com/getkey.php?id={config.license_number}&tag="
    headers = {"Host": target_host}

    # Attempt order: direct, TOR (if enabled), proxy (if enabled)
    connection_attempts = [{"type": "direct"}]

    if config.tor:
        connection_attempts.append({"type": "tor"})

    if config.proxy:
        connection_attempts.append({"type": "proxy"})

    for attempt in connection_attempts:
        try:
            request_params = prepare_request_params(url=url, headers=headers)

            # Apply proxy settings for TOR or regular proxy
            if attempt["type"] in ("tor", "proxy"):
                request_params = add_proxy_to_params(proxy_type=attempt["type"], params=request_params)

            # Send HTTP request
            response = requests.get(**request_params)

            if "Invalid product license" in response.text:
                log_message = _("Web Filter: invalid license key. %(lic_number)s", lic_number=config.license_number)
                write_log(log_type=["system", "updates"], message=log_message)
                config.license_number = None
                return

            if "Product Software Maintenance expired" in response.text:
                log_message = _("Web Filter: license key expired. %(lic_number)s", lic_number=config.license_number)
                write_log(log_type=["system", "updates"], message=log_message)
                config.license_number = None
                return

            if response.ok:
                add_webfilter_key(lic_number=config.license_number, key=response.text)  # Save key to database
                log_message = _("Web Filter: received new key - %(key)s", key=response.text.strip())
                write_log(log_type=["system", "updates"], message=log_message)
                return
        except requests.RequestException as err:
            attempt_desc = {
                "direct": "without proxy",
                "tor": "via TOR",
                "proxy": "with proxy",
            }[attempt["type"]]

            write_log(
                log_type="system",
                message=_(
                    "Error fetching Web Filter key %(proxy_status)s: %(err)s", proxy_status=attempt_desc, err=str(err)
                ),
            )
    # All attempts failed
    write_log(log_type="updates", message=_("Web Filter: error fetching Web Filter key"))

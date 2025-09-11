from flask import Response
from flask import request
from flask_babel import gettext as _

from config.config_env import config
from db.database import get_webfilter_key, add_webfilter_key, add_stat_mirror_update, add_stat_kerio_update
from utils.internet_utils import make_request_with_retries
from utils.app_logging import write_log


def handle_webfilter():
    """Handler for Web Filter key request"""
    write_log(
        log_type=["system", "connections"],
        message=_("Received request for Web Filter key"),
        ip=request.remote_addr if config.ip_logging else None,
    )

    webfilter_key = (
        get_webfilter_key(lic_number=config.license_number)
        if not config.forced_web_filter_key
        else config.forced_web_filter_key
    )

    if not webfilter_key:
        return Response(response="404 Not found", status=404, mimetype="text/plain")

    add_stat_kerio_update(ip_address=request.remote_addr, update_type="web_filter", bytes_transferred=0)
    # Create and return response with status code 200 and Web Filter key as response body
    return Response(response=webfilter_key, status=200)


def update_web_filter_key() -> None:
    """Updates Web Filter key by fetching it from Kerio server"""
    if not config.license_number:
        log_message = _("Web Filter: passing because license key is not configured")
        write_log(log_type=["system", "updates"], message=log_message)
        return

    write_log(log_type="system", message=_("Fetching Web Filter key from wf-activation.kerio.com server"))

    url = f"https://wf-activation.kerio.com/getkey.php?id={config.license_number}&tag="
    headers = {"Host": "wf-activation.kerio.com"}

    response = make_request_with_retries(url=url, headers=headers, context="Web Filter key")

    if not response:
        write_log(log_type="updates", message=_("Web Filter: error fetching Web Filter key"))
        return

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

    add_webfilter_key(lic_number=config.license_number, key=response.text)  # Save key to database
    log_message = _("Web Filter: received key - %(key)s", key=response.text.strip())
    write_log(log_type=["system", "updates"], message=log_message)
    add_stat_mirror_update(update_type="web_filter", bytes_downloaded=0)  # Add update to statistics

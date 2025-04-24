import base64

import requests
from flask import Response
from flask_babel import gettext as _

from config.config_env import config
from db.database import get_webfilter_key, add_webfilter_key
from utils.logging import write_log


def handle_webfilter():
    """Handler for Web Filter key request"""
    write_log(log_type="system", message=_("Received request for Web Filter key"))
    webfilter_key = get_webfilter_key(lic_number=config.license_number)

    if not webfilter_key:
        return Response(response="404 Not found", status=404, mimetype="text/plain")

    # Create and return response with status code 200 and Web Filter key as response body
    return Response(response=webfilter_key, status=200)


def update_web_filter_key() -> None:
    """Updates Web Filter key by fetching it from Kerio server"""
    if not config.license_number:
        log_message = _("Web Filter: passing because license key is not configured")
        write_log(log_type="system", message=log_message)
        write_log(log_type="updates", message=log_message)
        return

    webfilter_key = get_webfilter_key(lic_number=config.license_number)

    if webfilter_key:
        log_message = _("Web Filter: database already contains an actual Web Filter key")
        write_log(log_type="system", message=log_message)
        write_log(log_type="updates", message=log_message)
        return

    write_log(log_type="system", message=_("Fetching new Web Filter key from wf-activation.kerio.com server"))
    target_host = "wf-activation.kerio.com"
    url = f"https://wf-activation.kerio.com/getkey.php?id={config.license_number}&tag="
    headers = {"Host": target_host}

    # First attempt without proxy, then with proxy if configured
    for use_proxy in [False, True]:
        # Skip proxy attempt if proxy is not configured
        if use_proxy and not config.proxy:
            break

        try:
            request_params = {
                "url": url,
                "headers": headers,
                "timeout": 30,
            }

            # Add proxy configuration if needed
            if use_proxy:
                request_params["proxies"] = {
                    "http": f"http://{config.proxy_host}:{config.proxy_port}",
                    "https": f"http://{config.proxy_host}:{config.proxy_port}",
                }

                # Add proxy authentication if configured
                if config.proxy_login:
                    auth_str = f"{config.proxy_login}:{config.proxy_password}"
                    headers["Proxy-Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"

            response = requests.get(**request_params)

            # Check for specific error messages in response
            if "Invalid product license" in response.text:
                log_message = _("Web Filter: invalid license key. %(lic_number)s", lic_number=config.license_number)
                write_log(log_type="system", message=log_message)
                write_log(log_type="updates", message=log_message)
                config.license_number = None
                return

            if "Product Software Maintenance expired" in response.text:
                log_message = _("Web Filter: license key expired. %(lic_number)s", lic_number=config.license_number)
                write_log(log_type="system", message=log_message)
                write_log(log_type="updates", message=log_message)
                config.license_number = None
                return

            if response.ok:
                add_webfilter_key(lic_number=config.license_number, key=response.text)  # Save key to database
                log_message = _("Web Filter: received new key - %(key)s", key=response.text.strip())
                write_log(log_type="system", message=log_message)
                write_log(log_type="updates", message=log_message)
                return
        except requests.RequestException as err:
            proxy_status = "with proxy" if use_proxy else "without proxy"
            write_log(
                log_type="system",
                message=_(
                    "Error fetching Web Filter key %(proxy_status)s: %(err)s", proxy_status=proxy_status, err=str(err)
                ),
            )

            # Log to mkc only after all attempts failed
            if use_proxy or not config.proxy:
                write_log(log_type="updates", message=_("Web Filter: error fetching Web Filter key"))

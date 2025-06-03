import re

import requests
from flask import request, Response
from flask_babel import gettext as _

from config.config_env import config
from utils.internet_utils import prepare_request_params, add_proxy_to_params
from utils.logging import write_log


def handle_bitdefender() -> Response:
    """
    Handles Bitdefender requests (antivirus or antispam signatures).

    This function processes incoming requests,
    logs the request type based on the Host header,
    and forwards the request to the Bitdefender upgrade server with appropriate headers and proxy settings.

    Returns:
        Response: Flask Response object with the proxied content, or a 404 error response on failure.
    """
    host = request.headers.get("Host", "")

    # Determine the type of request based on the Host header
    if "bdupdate.kerio.com" in host:
        write_log(
            log_type="system",
            message=_("Received antivirus signatures request"),
            ip=request.remote_addr if config.ip_logging else None,
        )
    elif "bda-update.kerio.com" in host:
        write_log(
            log_type="system",
            message=_("Received antispam signatures request"),
            ip=request.remote_addr if config.ip_logging else None,
        )
    else:
        write_log(
            log_type="system",
            message=_("Received unknown download request: %(request_path)s", request_path=request.path),
            ip=request.remote_addr if config.ip_logging else None,
        )
        return Response("404 Not found", status=404, mimetype="text/plain")

    if config.alternative_mode:
        if "bdupdate.kerio.com" in host:
            if "bdupdate.kerio.com" in config.antivirus_update_url:
                target_url = config.kerio_cdn_url
                target_host = "bdupdate-cdn.kerio.com"
            else:
                target_url = config.antivirus_update_url.strip().rstrip("/")
                target_host = target_url.split("//")[1]
        else:
            target_url = config.antispam_update_url.strip().rstrip("/")
            target_host = target_url.split("//")[1]
    else:
        target_url = "http://upgrade.bitdefender.com"
        target_host = "upgrade.bitdefender.com"

    # Remove leading slashes and dots from the request path
    clean_path = re.sub(r"^(?:[./]+|(?:\.\./)+)*", "", request.path)
    url = f"{target_url}/{clean_path}"

    # Create default headers for the outgoing request
    default_headers = {
        "User-Agent": "WSLib 1.4 [3, 0, 0, 94]",
        "Host": target_host,
        "Accept": "*/*",
        "Referer": request.headers.get("Referer", ""),
    }

    # Merge additional headers from the incoming request (excluding specific ones)
    excluded_headers = {"host", "user-agent", "accept", "referer"}
    additional_headers = {key: value for key, value in request.headers.items() if key.lower() not in excluded_headers}
    headers = {**default_headers, **additional_headers}

    try:
        request_params = prepare_request_params(
            url=url,
            headers=headers,
            data=request.get_data(),
            params=request.args,
            stream=True,
        )
        # Setup proxy if configured
        if config.tor:
            request_params = add_proxy_to_params(proxy_type="tor", params=request_params)
        elif config.proxy:
            request_params = add_proxy_to_params(proxy_type="proxy", params=request_params)

        # Forward the request to the Bitdefender server
        response = requests.get(**request_params)

        # Enable automatic decompression of gzip stream
        response.raw.decode_content = True

        write_log(log_type="system", message=_("Downloading file: %(request_path)s", request_path=clean_path))

        # Copy and clear headers
        response_headers = dict(response.headers)
        for h in ("Content-Encoding", "Content-Length"):
            response_headers.pop(h, None)

        flask_response = Response(
            response=response.iter_content(chunk_size=1024),
            status=response.status_code,
            headers=response_headers,
        )
        return flask_response
    except requests.RequestException as e:
        write_log(
            log_type="system",
            message=_("Error %(err)s while loading file %(request_path)s", err=str(e), request_path=clean_path),
        )
        return Response(response="404 Not found", status=404, mimetype="text/plain")

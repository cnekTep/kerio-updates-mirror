import base64

import requests
from flask import request, Response

from config.config_env import config
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
        write_log(log_type="system", message=f"Received antivirus signatures request")
    elif "bda-update.kerio.com" in host:
        write_log(log_type="system", message=f"Received antispam signatures request")
    else:
        write_log(log_type="system", message=f"Received unknown download request: {request.path}")
        return Response("404 Not found", status=404, mimetype="text/plain")

    target_host = "upgrade.bitdefender.com"
    clean_path = request.path.lstrip("/")  # Remove leading slash from the request path
    url = f"http://{target_host}/{clean_path}"

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

    # Setup proxy if configured
    proxies = {}
    if config.proxy:
        proxy_url = f"http://{config.proxy_host}:{config.proxy_port}"
        proxies = {"http": proxy_url, "https": proxy_url}
        if config.proxy_login:
            auth_str = f"{config.proxy_login}:{config.proxy_password}"
            headers["Proxy-Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"

    try:
        # Forward the request to the Bitdefender server
        response = requests.get(
            url=url,
            headers=headers,
            proxies=proxies,
            data=request.get_data(),
            params=request.args,
            timeout=30,
            stream=True,
        )
        write_log(log_type="system", message=f"Downloading file: {request.path}")

        # Build response preserving the headers from the external response
        response_headers = dict(response.headers)
        flask_response = Response(
            response=response.iter_content(chunk_size=1024),
            status=response.status_code,
            headers=response_headers,
        )
        return flask_response
    except requests.RequestException as e:
        write_log(log_type="system", message=f"Error '{str(e)}' while loading file {request.path}")
        return Response(response="404 Not found", status=404, mimetype="text/plain")

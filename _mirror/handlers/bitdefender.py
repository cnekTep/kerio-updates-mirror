import os
import re
from pathlib import Path

from flask import request, Response
from flask_babel import gettext as _

from config.config_env import config
from db.database import get_bitdefender_cache, add_bitdefender_cache, add_stat_mirror_update, add_stat_kerio_update
from utils.internet_utils import make_request_with_retries
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

    # Check if caching is enabled
    if config.bitdefender_update_mode == "via_mirror_cache" and "versions." not in clean_path:
        return handle_cached_file(clean_path=clean_path, url=url, headers=headers)

    # Forward the request to the Bitdefender server
    response = make_request_with_retries(
        url=url, headers=headers, skip_error_codes=[404], context=f"downloading bitdefender file: {url}"
    )

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


def handle_cached_file(clean_path: str, url: str, headers: dict) -> Response:
    """
    Handle file caching for Bitdefender files.

    Args:
        clean_path: Cleaned file path from request
        url: Target URL for downloading
        headers: Headers for the request

    Returns:
        Response: Flask Response object with cached or downloaded content
    """
    # Create cache directory if it doesn't exist
    cache_dir = Path("update_files/bitdefender_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = clean_path.split("/")[-1]
    local_file_path = cache_dir / filename

    # Check if file exists in cache
    cache_entry = get_bitdefender_cache(filename)

    if cache_entry:
        if os.path.exists(local_file_path):
            write_log(log_type="system", message=_("Sending cached file: %(filename)s", filename=filename))

            add_stat_kerio_update(ip_address=request.remote_addr, update_type="antivirus", bytes_transferred=os.path.getsize(local_file_path))
            # Serve cached file
            with open(local_file_path, "rb") as f:
                return Response(
                    response=f.read(),
                    status=200,
                    headers={
                        "Content-Type": "application/octet-stream",
                    },
                )

    # File not in cache, download it
    write_log(log_type="system", message=_("Downloading and caching file: %(file_path)s", file_path=clean_path))

    response = make_request_with_retries(
        url=url, headers=headers, skip_error_codes=[404], context=f"downloading bitdefender file: {url}"
    )

    if response.status_code == 404:
        return Response(response="404 Not found", status=404, mimetype="text/plain")

    # Save file to cache
    file_content = response.content

    with open(local_file_path, "wb") as f:
        f.write(file_content)

    # Add to database
    add_bitdefender_cache(filename)
    add_stat_mirror_update(update_type="antivirus", bytes_downloaded=len(file_content))
    add_stat_kerio_update(ip_address=request.remote_addr, update_type="antivirus", bytes_transferred=len(file_content))

    # Copy and clear headers for response
    response_headers = dict(response.headers)
    for h in ("Content-Encoding", "Content-Length"):
        response_headers.pop(h, None)

    return Response(
        response=file_content,
        status=response.status_code,
        headers=response_headers,
    )

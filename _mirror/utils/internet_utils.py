import os
from typing import Optional, Dict, Any, Callable

import requests
from flask_babel import gettext as _

from config.config_env import config
from utils.app_logging import write_log


def get_ssl_context(cert_dir: str = "certs") -> tuple[str, str] | str:
    """
    Returns the SSL context if valid certificates are found, otherwise 'adhoc'.

    Args:
        cert_dir: Directory with certificates

    Returns:
        Tuple(str, str) or the string 'adhoc'
    """
    cert1 = os.path.join(cert_dir, "cert.pem")
    key1 = os.path.join(cert_dir, "key.pem")
    cert2 = os.path.join(cert_dir, "Certificate.crt")
    key2 = os.path.join(cert_dir, "Certificate.key")

    if os.path.exists(cert1) and os.path.exists(key1):
        return cert1, key1
    elif os.path.exists(cert2) and os.path.exists(key2):
        return cert2, key2
    else:
        write_log(log_type="system", message=_("No certificates were found, temporary SSL (adhoc) is used"))
        return "adhoc"


def prepare_request_params(
    url: str,
    headers: Optional[Dict[str, Any]] = None,
    data: Any = None,
    params: Any = None,
    timeout: int = 30,
    stream: bool = False,
) -> Dict[str, Any]:
    """
    Prepares request parameters.

    Args:
        url: URL for the request
        headers: Headers for the request
        data: Data for the request
        params: Parameters for the request
        timeout: Timeout for the request
        stream: Whether to stream the response

    Returns:
        dict: Dictionary with request parameters
    """
    params: Dict[str, Any] = {
        "url": url,
        "data": data,
        "params": params,
        "timeout": timeout,
        "stream": stream,
    }

    if headers:
        params["headers"] = headers

    return params


def add_proxy_to_params(proxy_type: str, params: dict) -> dict:
    """
    Adds proxy configuration to request parameters.

    Args:
        proxy_type: Proxy type
        params: Request parameters to modify

    Returns:
        dict: Modified request parameters with proxy settings
    """
    if proxy_type == "tor":
        proxy_scheme = "socks5h"  # SOCKS5 через Tor с DNS
        proxy_host = config.tor_host
        proxy_port = config.tor_port
        proxy_login = None
        proxy_password = None
    elif proxy_type == "proxy":
        proxy_scheme = "http"
        proxy_host = config.proxy_host
        proxy_port = config.proxy_port
        proxy_login = config.proxy_login
        proxy_password = config.proxy_password
    else:
        raise ValueError(f"Unsupported proxy type: {proxy_type}")

    # Create proxy URL with authorization, if required
    if proxy_login and proxy_password:
        proxy_auth = f"{proxy_login}:{proxy_password}@"
    else:
        proxy_auth = ""

    proxy_url = f"{proxy_scheme}://{proxy_auth}{proxy_host}:{proxy_port}"

    params["proxies"] = {
        "http": proxy_url,
        "https": proxy_url,
    }

    return params


def get_connection_attempts() -> list:
    """
    Generate connection attempts list based on download priority and available configurations.

    Returns:
        List of connection attempt dictionaries with 'type' key
    """
    connection_attempts = []

    # Parse priority string and create attempts based on available configs
    priorities = [p.strip() for p in config.download_priority.split(",")]
    for priority in priorities:
        if priority == "direct" and config.direct:
            connection_attempts.append({"type": "direct"})
        elif priority == "tor" and config.tor:
            connection_attempts.append({"type": "tor"})
        elif priority == "proxy" and config.proxy:
            connection_attempts.append({"type": "proxy"})

    return connection_attempts


def make_request_with_retries(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, Any]] = None,
    success_validator: Optional[Callable[[requests.Response], bool]] = None,
    skip_error_codes: Optional[list[int]] = None,
    context: str = "request",
) -> Optional[requests.Response]:
    """
    Makes HTTP request with automatic retries through different connection methods.

    Args:
        url: URL to request
        method: HTTP method (GET, POST, HEAD, etc.)
        headers: Optional headers
        success_validator: Function to validate response success (default: response.ok)
        skip_error_codes: List of HTTP status codes to return immediately without retrying (e.g. 404, 429)
        context: Context description for logging

    Returns:
        Response object if successful, None if all attempts failed
    """
    skip_error_codes = skip_error_codes or []
    connection_attempts = get_connection_attempts()

    for attempt in connection_attempts:
        try:
            request_params = prepare_request_params(url=url, headers=headers)

            # Apply proxy settings for TOR or regular proxy
            if attempt["type"] in ("tor", "proxy"):
                request_params = add_proxy_to_params(proxy_type=attempt["type"], params=request_params)

            # Use appropriate HTTP method
            response = requests.request(method=method, **request_params)
            # response = requests.get(**request_params)

            # Return response if status code is in skip_error_codes
            if response.status_code in skip_error_codes:
                return response

            # Use custom validator if provided, otherwise check response.ok
            if success_validator:
                if not success_validator(response):
                    continue
            else:
                if not response.ok:
                    continue

            return response

        except requests.RequestException as err:
            attempt_desc = {
                "direct": "without proxy",
                "tor": "via TOR",
                "proxy": "with proxy",
            }[attempt["type"]]

            write_log(
                log_type="system",
                message=_(
                    "[%(proxy_status)s] Error %(context)s: %(err)s",
                    context=context,
                    proxy_status=attempt_desc,
                    err=str(err),
                ),
            )

    return None


def download_file_with_retries(url: str, save_path: str, context: str = "file") -> bool:
    """
    Downloads a file with automatic retries through different connection methods.

    Args:
        url: URL to download from
        save_path: Path to save the file to
        context: Context description for logging

    Returns:
        bool: True if download successful, False otherwise
    """
    connection_attempts = get_connection_attempts()

    for attempt in connection_attempts:
        try:
            request_params = prepare_request_params(url=url, stream=True)

            if attempt["type"] in ("tor", "proxy"):
                request_params = add_proxy_to_params(proxy_type=attempt["type"], params=request_params)

            response = requests.get(**request_params)
            response.raise_for_status()

            # Save the file
            with open(save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            return True

        except requests.RequestException as err:
            attempt_desc = {
                "direct": "without proxy",
                "tor": "via TOR",
                "proxy": "with proxy",
            }[attempt["type"]]

            write_log(
                log_type="system",
                message=_(
                    "[%(proxy_status)s] Error downloading %(context)s: %(err)s",
                    context=context,
                    proxy_status=attempt_desc,
                    err=str(err),
                ),
            )

    return False

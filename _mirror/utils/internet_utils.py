import os
from typing import Optional, Dict, Any

from flask_babel import gettext as _

from config.config_env import config
from utils.logging import write_log


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

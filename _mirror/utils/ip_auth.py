from functools import wraps

from flask import request, Response
from flask_babel import gettext as _

from config.config_env import config
from utils.logging import write_log


def get_allowed_ips() -> list:
    """
    Getting the list of allowed IP addresses from the configuration.

    Returns:
        List of allowed IP addresses
    """
    if not hasattr(config, "allowed_ips") or not config.allowed_ips:
        return []

    return [ip.strip() for ip in config.allowed_ips.split(",")]


def check_ip():
    """
    Decorator for verifying the client's IP address.
    If the IP is not in the allowed list, it returns 403 Forbidden.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            allowed_ips = get_allowed_ips()

            # If the list is empty, allow access to all
            if not allowed_ips:
                return f(*args, **kwargs)

            client_ip = request.remote_addr

            if client_ip not in allowed_ips:
                write_log(log_type="updates", message=_("Access is denied for IP: %(ip)s", ip=client_ip))
                return Response(response="403 Access denied", status=403, mimetype="text/plain")

            return f(*args, **kwargs)

        return decorated_function

    return decorator

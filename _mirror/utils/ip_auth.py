import ipaddress
from functools import wraps

from flask import request, Response
from flask_babel import gettext as _

from config.config_env import config
from utils.logging import write_log


def get_allowed_ips(access_type: str) -> list:
    """
    Getting the list of allowed IP addresses from the configuration.

    Args:
        access_type: Type of access, e.g., 'web' or 'kerio'

    Returns:
        List of allowed IP addresses, ranges, or CIDR networks.
    """
    allowed = getattr(config, f"{access_type}_allowed_ips", "")
    return [ip.strip().replace(" ", "") for ip in allowed.split(",")] if allowed else []


def parse_ip_range(ip_range: str) -> tuple:
    """
    Parsing an IPv4 address range in the "start-end" format.

    Args:
        ip_range: String with a range of IP addresses, for example "192.168.1.1-192.168.1.10"

    Returns:
        A tuple of the starting and ending IP addresses in numerical representation
    """
    start, end = ip_range.split("-")
    start_ip = ipaddress.IPv4Address(start.strip())
    end_ip = ipaddress.IPv4Address(end.strip())

    # Make sure that start_ip is less than end_ip
    if start_ip > end_ip:
        start_ip, end_ip = end_ip, start_ip

    return int(start_ip), int(end_ip)


def is_ip_allowed(client_ip: str, allowed_ips: list) -> bool:
    """
    Checking whether access is allowed for this IPv4 address.

    Args:
        client_ip: Client IP address
        allowed_ips: List of allowed IP addresses, ranges, and networks

    Returns:
        True if access is allowed, otherwise False
    """
    if not allowed_ips:
        return True

    try:
        # Verify that this is an IPv4 address
        client_ip_obj = ipaddress.IPv4Address(client_ip)
        client_ip_int = int(client_ip_obj)

        # Always allow access from the local TOR proxy
        if client_ip_obj == ipaddress.IPv4Address(config.tor_host):
            return True

        for allowed_ip_entry in allowed_ips:
            try:
                # Checking for CIDR (network by mask)
                if "/" in allowed_ip_entry:
                    network = ipaddress.IPv4Network(address=allowed_ip_entry, strict=False)
                    if client_ip_obj in network:
                        return True
                # Checking for a range of IP addresses
                elif "-" in allowed_ip_entry:
                    start_ip_int, end_ip_int = parse_ip_range(allowed_ip_entry)
                    if start_ip_int <= client_ip_int <= end_ip_int:
                        return True
                # Checking for a separate IP address
                else:
                    allowed_ip = ipaddress.IPv4Address(allowed_ip_entry)
                    if client_ip_obj == allowed_ip:
                        return True
            except ValueError:
                # Skipping incorrect entries
                write_log(
                    log_type="system",
                    message=_("Incorrect IP address format in the allowed list: %(ip)s", ip=allowed_ip_entry),
                )
                continue

        return False
    except ValueError:
        # Invalid client IP address
        write_log(log_type="system", message=_("Incorrect format of the client's IP address: %(ip)s", ip=client_ip))
        return False


def check_ip(access_type: str) -> callable:
    """
    Decorator for verifying the client's IP address against allowed IPs for a given access type.
    If the IP is not in the allowed list, it returns 403 Forbidden.

    Supports:
    - Individual IP addresses: 192.168.1.1
    - IP address ranges: 192.168.1.1-192.168.1.10
    - CIDR networks: 192.168.1.0/24

    Args:
        access_type: Type of access, e.g., 'web' or 'kerio'

    Returns:
        Decorated function
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            allowed_ips = get_allowed_ips(access_type)

            # If the list is empty, allow access to all
            if not allowed_ips:
                return f(*args, **kwargs)

            client_ip = request.remote_addr

            if not is_ip_allowed(client_ip=client_ip, allowed_ips=allowed_ips):
                write_log(log_type="system", message=_("Access is denied for IP: %(ip)s", ip=client_ip))
                return Response(response="403 Access denied", status=403, mimetype="text/plain")

            return f(*args, **kwargs)

        return decorated_function

    return decorator

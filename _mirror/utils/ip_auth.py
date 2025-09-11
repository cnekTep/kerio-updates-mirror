import ipaddress
import socket
from datetime import datetime, timedelta
from functools import wraps

from flask import request, Response
from flask_babel import gettext as _

from config.config_env import config
from utils.app_logging import write_log


def get_allowed_ips(access_type: str) -> list:
    """
    Getting the list of allowed IP addresses from the configuration.
    For 'web' access type, also handles DDNS resolution

    Args:
        access_type: Type of access, e.g., 'web' or 'kerio'

    Returns:
        List of allowed IP addresses, ranges, or CIDR networks.
    """
    # Get basic allowed IPs list
    allowed = getattr(config, f"{access_type}_allowed_ips", "")
    ip_list = [ip.strip().replace(" ", "") for ip in allowed.split(",")] if allowed else []

    # Handle DDNS for web access type
    if access_type == "web":
        ddns_domain = config.web_allowed_ddns

        if ddns_domain:  # DDNS is enabled
            current_time = datetime.now()
            last_check_str = config.web_allowed_ddns_last_check
            cached_ip = config.web_allowed_ddns_ip

            should_resolve = True

            # Check if we have a valid last check time
            if last_check_str:
                last_check = datetime.fromisoformat(last_check_str)
                time_diff = current_time - last_check

                # If less than 10 minutes passed, use cached IP
                if time_diff < timedelta(minutes=10):
                    should_resolve = False
                    ip_list.append(cached_ip)
                    # write_log(log_type="system", message=_("Using cached DDNS IP: %(ip)s", ip=cached_ip))

            # Resolve domain if needed
            if should_resolve:
                resolved_ip = resolve_domain_to_ip(ddns_domain)

                if resolved_ip:
                    ip_list.append(resolved_ip)
                    # Update config with new IP and timestamp
                    config.web_allowed_ddns_ip = resolved_ip
                    config.web_allowed_ddns_last_check = current_time.isoformat()
                    write_log(
                        log_type="system",
                        message=_("Updated DDNS IP: %(ip)s for domain %(domain)s", ip=resolved_ip, domain=ddns_domain),
                    )
                else:
                    write_log(
                        log_type="system", message=_("Failed to resolve DDNS domain %(domain)s", domain=ddns_domain)
                    )
                    ip_list.append(cached_ip)

    # Remove empty strings and duplicates
    ip_list = list(set(filter(None, ip_list)))

    return ip_list


def resolve_domain_to_ip(domain: str) -> str:
    """
    Resolve domain name to IP address
    Returns empty string if resolution fails
    """
    try:
        ip = socket.gethostbyname(domain.strip())
        return ip
    except Exception:
        return ""


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

            client_ip = request.headers.get("X-Real-Ip", request.remote_addr)

            if not is_ip_allowed(client_ip=client_ip, allowed_ips=allowed_ips):
                write_log(log_type="system", message=_("Access is denied for IP: %(ip)s", ip=client_ip))
                return Response(response="403 Access denied", status=403, mimetype="text/plain")

            return f(*args, **kwargs)

        return decorated_function

    return decorator

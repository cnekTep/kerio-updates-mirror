import time

from config.config_env import config


def delayed_restart():
    """Delayed update of HAProxy allowed IPs and restart after 1 second"""
    time.sleep(1)
    # Updating HAProxy allowed IPs
    if (
        config.restricted_haproxy_access
        and config.kerio_allowed_ips
        and config.web_allowed_ips
        and not config.web_allowed_ddns
    ):
        allowed_ips = ["172.222.0.0/24"] + config.kerio_allowed_ips.split(",") + config.web_allowed_ips.split(",")
        allowed_ips = [ip.strip() for ip in allowed_ips if ip.strip()]
        with open("./config/haproxy/allowed_ips.acl", "w") as f:
            f.write("\n".join(allowed_ips))
    else:
        with open("./config/haproxy/allowed_ips.acl", "w") as f:
            f.write("0.0.0.0/0")

    # Updating HAProxy reload trigger
    with open("./config/haproxy/reload.trigger", "w") as f:
        f.write("")

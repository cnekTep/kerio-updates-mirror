import uuid

from flask import request, render_template, redirect
from flask_babel import gettext as _
from werkzeug.security import generate_password_hash

from config.config_env import config
from utils.distributes_update import get_distributes_list, get_kerio_version_from_filename
from utils.logging import write_log, read_last_lines
from utils.tor_check import tor_checker
from utils.update_check import checker


def main_page():
    """
    Render the main page with logs and current settings.

    Returns:
        Rendered HTML template with logs and configuration data.
    """
    # Read recent logs
    system_log = read_last_lines(file_path="./logs/system.log", encoding="utf8")
    updates_log = read_last_lines(file_path="./logs/updates.log", encoding="utf8")

    # Preparing data for the template
    template_data = {
        "system_log_content": system_log,
        "updates_log_content": updates_log,
        "license_number": config.license_number,
        "update_ids_1": config.update_ids_1,
        "update_ids_2": config.update_ids_2,
        "update_ids_3": config.update_ids_3,
        "update_ids_4": config.update_ids_4,
        "update_ids_5": config.update_ids_5,
        "geoip_github": config.geoip_github,
        "update_web_filter_key": config.update_web_filter_key,
        "update_snort_template": config.update_snort_template,
        "direct": config.direct,
        "tor": config.tor,
        "proxy": config.proxy,
        "proxy_host": config.proxy_host,
        "proxy_port": config.proxy_port,
        "proxy_login": config.proxy_login,
        "proxy_password": config.proxy_password,
        "download_priority": config.download_priority,
        "restricted_access": config.restricted_access,
        "web_allowed_ips": config.web_allowed_ips,
        "kerio_allowed_ips": config.kerio_allowed_ips,
        "ip_logging": config.ip_logging,
        "tor_status": tor_checker.get_status(),
        "locale": config.locale,
        "compile": config.compile,
        "alternative_mode": config.alternative_mode,
        "antivirus_update_url": config.antivirus_update_url,
        "antispam_update_url": config.antispam_update_url,
        "bitdefender_mode": config.bitdefender_update_mode,
        "current_version": checker.get_current_version(),
        "auth": config.auth,
        "auth_username": config.admin_username,
        "distro_update": config.update_kerio_control,
        "distro_list": get_distributes_list(),
        "distro_file": config.kerio_control_update_file,
    }

    return render_template(template_name_or_list="index.html", **template_data)


def save_settings():
    """
    Save settings received from the form submission.

    Returns:
        Redirect to the settings section of the main page.
    """
    # Update license number
    config.license_number = request.form.get("LicenseNo") or None

    # Update checkboxes (will be True if the checkbox is checked and passed in the form)
    config.update_ids_1 = "IDSv1" in request.form
    config.update_ids_2 = "IDSv2" in request.form
    config.update_ids_3 = "IDSv3" in request.form
    config.update_ids_4 = "IDSv4" in request.form
    config.update_ids_5 = "IDSv5" in request.form
    config.geoip_github = "geo_github" in request.form
    config.update_web_filter_key = "wfkey" in request.form
    config.update_snort_template = "snort_template" in request.form
    config.ip_logging = "ip_logging" in request.form
    config.tor = "use_tor" in request.form
    config.direct = "use_direct" in request.form
    config.download_priority = build_connection_order(request.form.get("download_priority"))

    if "distro_update" in request.form and request.form.get("distro_select"):
        config.update_kerio_control = "distro_update" in request.form
        config.kerio_control_update_file = request.form.get("distro_select")
        config.kerio_control_update_version = get_kerio_version_from_filename(
            filename=request.form.get("distro_select")
        )
    else:
        config.update_kerio_control = False
        config.kerio_control_update_file = None
        config.kerio_control_update_version = None

    # Update proxy settings if enabled
    config.proxy = "use_proxy" in request.form
    if config.proxy:
        config.proxy_host = request.form.get("proxy_host") or config.proxy_host
        config.proxy_port = request.form.get("proxy_port") or config.proxy_port
        config.proxy_login = request.form.get("proxy_login") or None
        config.proxy_password = request.form.get("proxy_password") or None

    # Update alternative methods if enabled
    config.alternative_mode = "alternative_mode" in request.form
    if config.alternative_mode:
        config.antivirus_update_url = request.form.get("antivirus_url")
        config.antispam_update_url = request.form.get("antispam_url")
        config.bitdefender_update_mode = request.form.get("bitdefender_mode", "no_mirror")

    # Update authentication
    if "use_auth" in request.form:
        auth_username = request.form.get("auth_username") or None
        auth_password = request.form.get("auth_password") or None
        if auth_username and auth_password:
            config.auth = True
            config.admin_id = str(uuid.uuid4())
            config.admin_username = auth_username
            config.admin_password_hash = generate_password_hash(auth_password)
    else:
        config.auth = False
        config.admin_id = None
        config.admin_username = None
        config.admin_password_hash = None

    # Update allowed IPs if enabled
    config.restricted_access = "restricted_access" in request.form
    if config.restricted_access:
        config.kerio_allowed_ips = (
            request.form.get("kerio_allowed_ips") if "kerio_allowed_ips_enabled" in request.form else ""
        )
        config.web_allowed_ips = (
            request.form.get("web_allowed_ips") if "web_allowed_ips_enabled" in request.form else ""
        )
    else:
        config.kerio_allowed_ips = config.web_allowed_ips = ""

    write_log(log_type="system", message=_("Settings have been changed"))

    return redirect("/#settings")


def build_connection_order(connection_str: str) -> str:
    """
    Build a complete connection order by adding missing connection types.

    Args:
        connection_str: Partial connection order, e.g. "tor,direct".

    Returns:
        Full connection order including all types, e.g. "tor,direct,proxy".
    """
    all_options = ["tor", "proxy", "direct"]
    parts = [part.strip() for part in connection_str.split(",") if part.strip()]
    missing = [opt for opt in all_options if opt not in parts]
    return ", ".join(parts + missing)

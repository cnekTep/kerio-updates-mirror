from flask import request, render_template, redirect, send_from_directory

from config.config_env import config
from utils.logging import write_log, read_last_lines


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
        "proxy": config.proxy,
        "proxy_host": config.proxy_host,
        "proxy_port": config.proxy_port,
        "proxy_login": config.proxy_login,
        "proxy_password": config.proxy_password,
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

    # Update proxy settings if enabled
    config.proxy = "avir_proxy" in request.form
    if config.proxy:
        config.proxy_host = request.form.get("avir_host") or config.proxy_host
        config.proxy_port = request.form.get("avir_port") or config.proxy_port
        config.proxy_login = request.form.get("avir_login") or None
        config.proxy_password = request.form.get("avir_passw") or None

    write_log(log_type="system", message=f"Settings have been changed")

    return redirect("/#settings")


def favicon():
    """Returns the favicon.ico file."""
    return send_from_directory(directory="", path="favicon.ico", mimetype="image/vnd.microsoft.icon")

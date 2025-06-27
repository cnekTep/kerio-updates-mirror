from flask import Blueprint, request, redirect, url_for
from flask_babel import gettext as _

from config.config_env import config
from handlers.auth import conditional_login_required
from handlers.log_content import get_system_log, get_updates_log
from handlers.pages import save_settings, main_page
from handlers.update_mirror import handler_update_mirror
from utils.ip_auth import check_ip
from utils.logging import write_log
from utils.tor_check import tor_checker
from utils.update_check import checker

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/", methods=["GET", "POST"])
@check_ip("web")
@conditional_login_required
def main():
    """Home Administration page"""
    # Handling saving settings
    if request.method == "POST" and request.args.get("action") == "save_settings":
        return save_settings()

    return main_page()


@admin_bp.route("/set_language")
@check_ip("web")
@conditional_login_required
def set_language():
    """Changing interface language"""
    lang = request.args.get("lang")
    if lang in ["en", "ru"]:  # Supported languages
        config.locale = lang
        write_log(log_type="system", message=_("Language changed to: %(lang)s", lang=lang))

        # Checking if it was an AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"status": "success", "language": lang}

        # Redirect to the previous page or the main page
        return redirect(request.referrer or url_for("admin.main"))

    return redirect(url_for("admin.main"))


@admin_bp.route("/update_mirror")
@check_ip("web")
@conditional_login_required
def update_mirror():
    """Mirror update"""
    return handler_update_mirror()


@admin_bp.route("/update_mirror_force")
@check_ip("web")
@conditional_login_required
def update_mirror_force():
    """Force mirror update"""
    return handler_update_mirror(forced=True)


@admin_bp.route("/get_system_log")
@check_ip("web")
@conditional_login_required
def system_log():
    """Getting system log"""
    return get_system_log()


@admin_bp.route("/get_updates_log")
@check_ip("web")
@conditional_login_required
def updates_log():
    """Getting update log"""
    return get_updates_log()


@admin_bp.route("/tor_status")
@check_ip("web")
@conditional_login_required
def tor_status():
    """Checking Tor Status"""
    return tor_checker.check_connection()


@admin_bp.route("/check_update_status")
@check_ip("web")
@conditional_login_required
def check_update_status():
    """Checking the status of updates"""
    return checker.get_latest_results()


@admin_bp.route("/check_for_updates")
@check_ip("web")
@conditional_login_required
def check_for_updates():
    """Manual check for updates"""
    return checker.manual_update_check()

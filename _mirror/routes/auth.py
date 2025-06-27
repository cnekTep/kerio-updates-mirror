from flask import Blueprint

from handlers.auth import handle_login, handle_logout
from utils.ip_auth import check_ip

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@check_ip("web")
def login():
    """Login processing"""
    return handle_login()


@auth_bp.route("/logout")
@check_ip("web")
def logout():
    """Logout processing"""
    return handle_logout()

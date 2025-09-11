from functools import wraps

from flask import request, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import UserMixin, LoginManager, login_user, logout_user, current_user
from werkzeug.security import check_password_hash

from config.config_env import config
from utils.app_logging import write_log


def conditional_login_required(func):
    """Decorate routes to require login."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not config.auth:
            return func(*args, **kwargs)
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


class User(UserMixin):
    """Simple user model"""

    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash


def get_user(username):
    """Get user by username"""
    if username == config.admin_username:
        return User(id=config.admin_id, username=config.admin_username, password_hash=config.admin_password_hash)
    return None


def init_auth(app):
    """Initialize authentication system"""
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        if user_id == config.admin_id:
            return User(id=config.admin_id, username=config.admin_username, password_hash=config.admin_password_hash)
        return None

    return login_manager


def handle_login():
    """System login handler"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = get_user(username)
        if user and check_password_hash(pwhash=user.password_hash, password=password):
            login_user(user)
            write_log(
                log_type="system",
                message=_("User logged in: %(username)s", username=username),
                ip=request.remote_addr if config.ip_logging else None,
            )
            next_page = request.args.get("next")
            return redirect(next_page or "/")
        else:
            write_log(
                log_type="system",
                message=_("Failed login attempt for user: %(username)s", username=username),
                ip=request.remote_addr if config.ip_logging else None,
            )
            return render_template(template_name_or_list="login.html", error=_("Invalid username or password"))

    return render_template("login.html")


def handle_logout():
    """System logout handler"""
    username = current_user.username if current_user.is_authenticated else "Unknown user"
    logout_user()
    write_log(
        log_type="system",
        message=_("User logged out: %(username)s", username=username),
        ip=request.remote_addr if config.ip_logging else None,
    )
    return redirect("/login")

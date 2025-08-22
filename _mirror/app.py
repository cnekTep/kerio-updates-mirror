import threading
from typing import Tuple

from flask import Flask, request, Response
from flask_babel import Babel
from flask_babel import gettext as _
from werkzeug.middleware.proxy_fix import ProxyFix

from config.config_env import config
from db.database import close_connection, init_db
from handlers.auth import init_auth
from routes import admin_bp, auth_bp, kerio_bp
from utils.internet_utils import get_ssl_context
from utils.logging import write_log, setup_logging
from utils.schedulers import setup_scheduler


def get_locale():
    """Get current locale from configuration."""
    return config.locale


app = Flask(__name__)
app.config["BABEL_DEFAULT_LOCALE"] = config.locale
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"
if config.trusted_proxy_count is not None and int(config.trusted_proxy_count) > 0:
    app.wsgi_app = ProxyFix(
        app=app.wsgi_app,
        x_for=int(config.trusted_proxy_count),
        x_host=int(config.trusted_proxy_count),
        x_port=int(config.trusted_proxy_count),
        x_prefix=int(config.trusted_proxy_count),
        x_proto=int(config.trusted_proxy_count),
    )

babel = Babel(app=app, locale_selector=get_locale)

# Initialize database and tables
with app.app_context():
    init_db()

# Close database connection when request ends
app.teardown_appcontext(close_connection)

# Initialize authentication
app.secret_key = config.secret_key
login_manager = init_auth(app)

# Registration of all Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(kerio_bp)
app.register_blueprint(admin_bp)


@app.errorhandler(404)
def global_not_found(error) -> Response:
    """
    Global 404 handler (if no Blueprint has processed the request)

    Args:
        error: Flask error

    Returns:
        404 Not found response
    """
    write_log(
        log_type="system",
        message=_("No handler found for request: %(request_url)s", request_url=request.url),
        ip=request.remote_addr if config.ip_logging else None,
    )
    return Response(response="404 Not found", status=404, mimetype="text/plain")


def run_server(port: int, ssl: bool = False) -> None:
    """
    Run Flask server with specified configuration.

    Args:
        port: Port number to listen on
        ssl: Whether to use SSL/HTTPS
    """
    with app.app_context():
        kwargs = {"port": port, "host": "0.0.0.0", "threaded": True}
        if ssl:
            kwargs["ssl_context"] = get_ssl_context()

        protocol = "HTTPS" if ssl else "HTTP"
        write_log(
            log_type="system", message=_("%(protocol)s server started on port %(port)s", protocol=protocol, port=port)
        )
        app.run(**kwargs)


def start_servers(http_port: int = 80, https_port: int = 443) -> Tuple[threading.Thread, threading.Thread]:
    """
    Start both HTTP and HTTPS servers in separate threads.

    Args:
        http_port: Port for HTTP server
        https_port: Port for HTTPS server

    Returns:
        Tuple: References to both server threads
    """
    https_thread = threading.Thread(target=run_server, args=(https_port, True), daemon=True)
    http_thread = threading.Thread(target=run_server, args=(http_port, False), daemon=True)

    https_thread.start()
    http_thread.start()

    return http_thread, https_thread


if __name__ == "__main__":
    setup_logging()

    # Launching the Scheduler
    # Option 1: Daily launch at 3:00 a.m.
    scheduler = setup_scheduler(app=app, schedule_type="daily", hour=3, minute=0)

    # Option 2: Run every 8 hours
    # scheduler = setup_scheduler(schedule_type="interval", interval_minutes=480)

    try:
        http_thread, https_thread = start_servers()

        # Keep main thread alive until interrupted
        http_thread.join()
        https_thread.join()
    except KeyboardInterrupt:
        with app.app_context():
            write_log(log_type="system", message=_("Server shutdown initiated"))
    except Exception as e:
        with app.app_context():
            write_log(log_type="system", message=_("Critical error: %(error)s", error=str(e)))

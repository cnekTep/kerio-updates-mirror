import threading
from typing import Tuple

from flask import Flask, request, Response
from flask import redirect, url_for
from flask_babel import Babel
from flask_babel import gettext as _

from config.config_env import config
from db.database import close_connection
from handlers.bitdefender import handle_bitdefender
from handlers.ids import handler_control_update, handler_checknew, handle_update
from handlers.log_content import get_system_log, get_updates_log
from handlers.pages import save_settings, main_page, favicon
from handlers.update_mirror import handler_update_mirror
from handlers.webfilter import handle_webfilter
from utils.ip_auth import check_ip
from utils.logging import write_log, setup_logging
from utils.schedulers import setup_scheduler
from utils.tor_check import tor_checker


def get_locale():
    """Get current locale from configuration."""
    return config.locale


app = Flask(__name__)
app.config["BABEL_DEFAULT_LOCALE"] = config.locale
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

babel = Babel(app=app, locale_selector=get_locale)


# Close database connection when request ends
app.teardown_appcontext(close_connection)


# Main router for all requests
@app.route(rule="/", defaults={"path": ""}, methods=["GET", "POST"])
@app.route(rule="/<path:path>", methods=["GET", "POST"])
@check_ip()  # Decorator for IP verification
def router(path: str) -> str | Response:
    """
    Unified router for all incoming requests.

    Args:
        path: Request path

    Returns:
        Response: Appropriate response based on the request
    """
    host = request.headers.get("Host", "")

    # Handle settings save
    if request.method == "POST" and request.args.get("action") == "save_settings":
        return save_settings()

    # Handle language change
    if path == "set_language" and request.args.get("lang"):
        lang = request.args.get("lang")
        if lang in ["en", "ru"]:  # Supported languages
            config.locale = lang
            write_log(log_type="system", message=_("Language changed to: %(lang)s", lang=lang))

            # Checking if it was an AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return {"status": "success", "language": lang}

            # Otherwise, redirect to the previous page or to the main page
            return redirect(request.referrer or url_for("router"))

    if path == "":
        return main_page()
    elif path == "favicon.ico":
        return favicon()
    elif path == "update_mirror":
        return handler_update_mirror()
    elif path == "get_system_log":
        return get_system_log()
    elif path == "get_updates_log":
        return get_updates_log()
    elif path == "tor_status":
        return tor_checker.check_connection()
    elif path == "update.php":
        return handle_update()
    elif path == "getkey.php":
        return handle_webfilter()
    elif path == "checknew.php":
        return handler_checknew()
    elif "control-update" in path:
        return handler_control_update()
    elif "bdupdate.kerio.com" in host or "bda-update.kerio.com" in host:
        return handle_bitdefender()
    else:
        write_log(log_type="system", message=_("No handler for request: %(request_url)s", request_url=request.url))
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
            kwargs["ssl_context"] = "adhoc"

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

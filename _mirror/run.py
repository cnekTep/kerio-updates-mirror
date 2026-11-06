from app.config import settings
from app.utils.app_logging import log_event
from app.utils.server_manager import start_single_server, start_dual_servers

if __name__ == "__main__":
    log_event(
        log_type="system",
        message="Starting Kerio Updates Mirror with Granian server",
    )

    # If there are migrations, run them here BEFORE starting the server

    try:
        if settings.has_nginx:
            # Single server mode (default: 8000 port)
            start_single_server()
        else:
            # Dual server mode (default: 80 and 443 ports)
            start_dual_servers()
    except KeyboardInterrupt:
        log_event(log_type="system", message="Server shutdown initiated")
    except Exception as e:
        log_event(log_type=["system", "errors"], message=f"Critical error: {str(e)}")

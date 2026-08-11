from app.config import settings
from app.utils.app_logging import write_log
from app.utils.server_manager import start_single_server, start_dual_servers

if __name__ == "__main__":
    write_log(
        log_type="system",
        message=f"Starting Kerio Updates Mirror with Granian server",
    )

    # Apply migrations BEFORE starting the server
    # apply_migrations()

    try:
        if settings.has_nginx:
            # Single server mode (default: 8000 port)
            start_single_server()
        else:
            # Dual server mode (default: 80 and 443 ports)
            start_dual_servers()
    except KeyboardInterrupt:
        write_log(log_type="system", message="Server shutdown initiated")
    except Exception as e:
        write_log(log_type=["system", "errors"], message=f"Critical error: {str(e)}")

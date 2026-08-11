import multiprocessing
import os
import sys
from pathlib import Path

from granian import Granian
from granian.constants import Interfaces

from app.config import settings
from app.utils.app_logging import write_log


def get_ssl_context(cert_dir: str = "certs") -> tuple[Path, Path] | None:
    """
    Check for SSL certificates and return their paths.

    Args:
        cert_dir: Directory containing SSL certificates (default: "certs")

    Returns:
        Tuple with paths to certificate and key files, or None if not found
    """
    cert_path = Path(cert_dir) / "cert.pem"
    key_path = Path(cert_dir) / "key.pem"

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    write_log(log_type="system", message="No certificates for HTTPS were found")
    return None


def verify_ssl_or_exit() -> tuple[Path, Path]:
    """
    Verify that SSL certificates exist before starting the server,
    otherwise exit the application.

    Returns:
        Tuple with paths to certificate and key files

    Raises:
        SystemExit: If SSL certificates are not found
    """
    ssl_context = get_ssl_context()
    if ssl_context is None:
        write_log(
            log_type="system",
            message="Application startup aborted: SSL certificates not found",
        )
        # Exit the application if SSL certificates are not found
        sys.exit(1)
    return ssl_context


def run_granian_server(
    port: int,
    ssl: bool = False,
    run_scheduler: bool = False,
) -> None:
    """Run a single Granian server instance.

    Args:
        port: Port number to listen on
        ssl: Whether to use SSL/HTTPS (default: False)
        run_scheduler: Whether this process should own the scheduler
    """
    # Pass the flag down via env var, since granian spawns this in a fresh process
    os.environ["RUN_SCHEDULER"] = "1" if run_scheduler else "0"

    config = {
        "target": "app.main:app",
        "address": settings.run.host,
        "port": port,
        "reload": False,
        "interface": Interfaces.ASGI,
        "workers": 1,
        "log_level": "debug",
        "log_access": True,
    }

    if ssl:  # Configure SSL if requested
        ssl_context = get_ssl_context()
        if ssl_context is None:
            write_log(
                log_type="system",
                message="Cannot start HTTPS server without certificates",
            )
            sys.exit(1)
        config["ssl_cert"] = ssl_context[0]
        config["ssl_key"] = ssl_context[1]
        config["ssl_protocol_min"] = "tls1.2"

    protocol = "HTTPS" if ssl else "HTTP"
    write_log(
        log_type="system",
        message=f"{protocol} Granian server started on port {port}",
    )

    Granian(**config).serve()


def start_dual_granian_servers() -> (
    tuple[multiprocessing.Process, multiprocessing.Process]
):
    """ "
    Start both HTTP and HTTPS Granian servers in separate processes.

    Returns:
        Tuple: References to both server processes

    Raises:
        SystemExit: If SSL certificates are not found
    """
    # Verify SSL certificates exist before starting servers
    verify_ssl_or_exit()

    try:
        http_process = multiprocessing.Process(
            target=run_granian_server,
            args=(settings.run.dual_http_port, False, True),
        )
        https_process = multiprocessing.Process(
            target=run_granian_server,
            args=(settings.run.dual_https_port, True, False),
        )

        http_process.start()
        https_process.start()

        return http_process, https_process
    except Exception as err:
        write_log(
            log_type="system",
            message=f"Failed to start Granian servers: {str(err)}",
        )
        raise


def start_single_server() -> None:
    """Start a single server instance (HTTP only)."""
    Granian(
        target="app.main:app",
        address=settings.run.host,
        port=settings.run.single_port,
        interface=Interfaces.ASGI,
        reload=False,
        workers=1,
        log_level="debug",
        log_access=True,
    ).serve()


def start_dual_servers() -> None:
    """Start dual HTTP/HTTPS servers and keep them running."""
    http_proc, https_proc = start_dual_granian_servers()
    try:
        http_proc.join()
        https_proc.join()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        http_proc.terminate()
        https_proc.terminate()
        http_proc.join()
        https_proc.join()

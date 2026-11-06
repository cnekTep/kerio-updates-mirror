import multiprocessing
import os
import sys
from multiprocessing.connection import wait
from pathlib import Path

from granian import Granian
from granian.constants import Interfaces

from app.config import settings, BASE_DIR
from app.utils.app_logging import log_event

CERT_DIR = BASE_DIR.parent / "certs"


def get_ssl_context(cert_dir: Path | None = None) -> tuple[Path, Path] | None:
    """
    Check for SSL certificates and return their paths.

    Args:
        cert_dir: Directory containing SSL certificates (default: CERT_DIR)

    Returns:
        Tuple with paths to certificate and key files, or None if not found
    """
    base_dir = Path(cert_dir) if cert_dir is not None else CERT_DIR
    cert_path = base_dir / "cert.pem"
    key_path = base_dir / "key.pem"

    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path

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
        log_event(
            log_type=["system", "errors"],
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

    ssl_context = None
    if ssl:
        ssl_context = get_ssl_context()
        if ssl_context is None:
            log_event(
                log_type=["system", "errors"],
                message="Cannot start HTTPS server without certificates",
            )
            sys.exit(1)

    protocol = "HTTPS" if ssl else "HTTP"
    log_event(
        log_type="system",
        message=f"Starting {protocol} Granian server on port {port}",
    )

    Granian(**_build_granian_config(port, ssl_context)).serve()


def start_dual_granian_servers() -> (
    tuple[multiprocessing.Process, multiprocessing.Process]
):
    """
    Start both HTTP and HTTPS Granian servers in separate processes.

    Returns:
        Tuple: References to both server processes

    Raises:
        SystemExit: If SSL certificates are not found
    """
    # Verify SSL certificates exist before starting servers
    verify_ssl_or_exit()

    http_process = https_process = None
    try:
        http_process = multiprocessing.Process(
            target=run_granian_server,
            args=(settings.run.dual_http_port, False, False),
        )
        https_process = multiprocessing.Process(
            target=run_granian_server,
            args=(settings.run.dual_https_port, True, True),
        )

        http_process.start()
        https_process.start()

        return http_process, https_process
    except Exception as err:
        log_event(
            log_type=["system", "errors"],
            message=f"Failed to start Granian servers: {str(err)}",
        )
        # Stop whatever was already started so no orphan is left behind
        for process in (http_process, https_process):
            if process is not None and process.is_alive():
                process.terminate()
                process.join()
        raise


def start_single_server() -> None:
    """Start a single server instance (HTTP only)."""
    Granian(**_build_granian_config(settings.run.single_port)).serve()


def start_dual_servers() -> None:
    """Start dual HTTP/HTTPS servers; stop both if either one exits."""
    processes = list(start_dual_granian_servers())
    exit_code = 0
    try:
        # Blocks until at least one server process has exited
        wait([process.sentinel for process in processes])
        # Servers must run until we stop them, so any exit here is unexpected
        exit_code = 1
        exited = [p for p in processes if p.exitcode is not None]
        log_event(
            log_type=["system", "errors"],
            message="Granian server process exited unexpectedly: "
            + ", ".join(f"pid={p.pid} code={p.exitcode}" for p in exited),
        )
    except KeyboardInterrupt:
        print("\nShutting down servers...")
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join()
    sys.exit(exit_code)


def _build_granian_config(
    port: int, ssl_context: tuple[Path, Path] | None = None
) -> dict:
    """Build Granian arguments shared by single and dual modes."""
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
    if ssl_context is not None:
        config["ssl_cert"], config["ssl_key"] = ssl_context
        config["ssl_protocol_min"] = "tls1.2"
    return config

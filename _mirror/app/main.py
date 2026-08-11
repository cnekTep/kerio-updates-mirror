import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from granian.utils.proxies import wrap_asgi_with_proxy_headers

from app.config import BASE_DIR
from app.middleware.config_reload import ConfigReloadMiddleware
from app.middleware.host_router import HostRoutingMiddleware
from app.middleware.requests_logging import RequestsLoggingMiddleware
from app.routers import routers
from app.utils.app_logging import write_log
from app.utils.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI startup and shutdown events.
    """
    # Startup
    write_log(log_type="system", message="Application started")

    # Only the designated process owns the scheduler in dual-server mode
    run_scheduler = os.environ.get("RUN_SCHEDULER", "1") == "1"
    scheduler = None
    if run_scheduler:
        scheduler = create_scheduler()
        scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()
    write_log(log_type="system", message="Application shutdown")


def create_app():
    """
    Factory function to create and configure FastAPI application instance.
    """
    app = FastAPI(title="Kerio Updates Mirror", lifespan=lifespan)

    # Serve static files (CSS, JS, images)
    app.mount(
        path="/web/static",
        app=StaticFiles(directory=BASE_DIR / "static"),
        name="static",
    )

    # Add middleware
    # Executes LAST (innermost) - routing decisions use fresh config
    app.add_middleware(HostRoutingMiddleware)
    # Executes SECOND - config reloaded before routing
    app.add_middleware(ConfigReloadMiddleware)
    # Executes FIRST (outermost) - logs everything including errors from inner layers
    app.add_middleware(RequestsLoggingMiddleware)

    # Register routers
    for router in routers:
        app.include_router(router)

    return wrap_asgi_with_proxy_headers(app, trusted_hosts="172.200.0.0/24")


# Create application instance
app = create_app()

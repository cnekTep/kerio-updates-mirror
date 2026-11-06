from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.utils.app_logging import log_event


class ConfigReloadMiddleware:
    """
    Keeps per-process settings in sync with the .env file.

    On every request, calls settings.reload_if_stale(), which compares the
    .env file mtime against the value recorded at last load. The check is
    throttled by config_reload_interval - at most one stat() syscall per
    interval per worker.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            try:
                # Cheap throttled check - reloads only when .env mtime has changed
                settings.reload_if_stale()
            except Exception as exc:
                # Keep serving with the previous settings if .env is broken or locked
                log_event(
                    log_type=["errors"],
                    message=f"Failed to reload settings: {exc}",
                    notify=False
                )

        await self.app(scope, receive, send)

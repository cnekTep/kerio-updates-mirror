from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings


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
            # Cheap throttled check - reloads only when .env mtime has changed
            settings.reload_if_stale()

        await self.app(scope, receive, send)

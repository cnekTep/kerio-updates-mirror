import time

import anyio
from fastapi import Request, Response, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.utils.app_logging import write_log
from app.utils.logging_utils import safe_body_str


class RequestsLoggingMiddleware:
    """
    Pure ASGI middleware: logs requests and responses when debug logging is enabled.
    Unlike BaseHTTPMiddleware, does not buffer or interfere with response body iteration,
    which makes it safe for FileResponse, StreamingResponse, and pathsend ASGI events.

    After reading the request body for logging, replaces `receive` with a replay function
    so that downstream consumers (endpoint, form parsers) can read the body again.
    This is necessary because Starlette's built-in ServerErrorMiddleware sits above this
    middleware and reads from the same `receive` stream before passing it down.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not settings.logging.debug:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Handle CONNECT method
        if request.method == "CONNECT":
            client_ip = request.client.host if request.client else "unknown"
            headers = dict(request.headers)
            write_log(
                log_type="debug",
                message=f"|CONNECT| Full URL: {request.url} "
                f"Path: {request.url.path} "
                f"Host header: {request.headers.get('host', 'N/A')} "
                f"Client IP: {client_ip} "
                f"Headers: {headers}",
            )
            response = Response(
                content="CONNECT method not supported",
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
            await response(scope, receive, send)
            return

        # Read and cache request body.
        # request.body() caches result in scope["_body"] for the Request object itself,
        # but any middleware or internal Starlette code that reads `receive` directly
        # (e.g. ServerErrorMiddleware, form parsers) will get an empty stream.
        # We fix this by replacing `receive` with a one-shot replay function below.
        body_bytes = await request.body()
        req_body_too_large = len(body_bytes) > settings.logging.log_body_limit

        _log_request(
            request=request,
            body_bytes=body_bytes,
            body_too_large=req_body_too_large,
        )

        # --- Replace receive with a replay of the cached body ---
        # Any downstream code that calls `receive` directly will get the cached bytes
        # on the first call, then block forever (standard ASGI convention: no more data).
        body_replayed = False

        async def receive_with_cached_body() -> Message:
            nonlocal body_replayed
            if not body_replayed:
                body_replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            # No more data - suspend forever (ASGI convention for exhausted stream)
            await anyio.sleep(float("inf"))
            return {}  # unreachable, but satisfies the type checker

        # --- Wrap send to intercept response without touching body ---
        start = time.perf_counter()
        response_status: int = 0
        response_headers: dict[str, str] = {}
        resp_body_chunks: list[bytes] = []
        resp_body_too_large = False
        resp_total_size = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal response_status, response_headers
            nonlocal resp_body_too_large, resp_total_size

            if message["type"] == "http.response.start":
                response_status = message["status"]
                # Headers are list of (name_bytes, value_bytes) tuples
                response_headers = {
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                }

            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    resp_total_size += len(chunk)
                    if not resp_body_too_large:
                        resp_body_chunks.append(chunk)
                        if resp_total_size > settings.logging.log_body_limit:
                            resp_body_too_large = True

                # Log on last chunk (more_body=False or absent)
                if not message.get("more_body", False):
                    process_ms = (time.perf_counter() - start) * 1000
                    resp_body = b"".join(resp_body_chunks)
                    _log_response(
                        request=request,
                        status_code=response_status,
                        headers=response_headers,
                        body=resp_body,
                        body_total_size=resp_total_size,
                        process_ms=process_ms,
                        body_too_large=resp_body_too_large,
                    )

            # Always pass message through untouched - never modify or drop it
            await send(message)

        try:
            await self.app(scope, receive_with_cached_body, send_wrapper)
        except Exception as e:
            process_ms = (time.perf_counter() - start) * 1000
            write_log(
                log_type="debug",
                message=f"|response| {request.method} {request.url.path} "
                f"ERROR time_ms={process_ms:.2f} "
                f"error={type(e).__name__}: {str(e)}",
            )
            raise


def _log_request(request: Request, body_bytes: bytes, body_too_large: bool):
    """Log request details."""
    client_ip = request.client.host if request.client else "unknown"
    content_type = request.headers.get("content-type")
    user_agent = request.headers.get("user-agent", "unknown")

    req_body_snip = (
        safe_body_str(
            body=body_bytes,
            content_type=content_type,
            limit=settings.logging.log_body_limit,
            is_too_large=body_too_large,
        )
        if settings.logging.log_requests_body
        else "<not logged>"
    )

    query = dict(request.query_params) if request.query_params else {}
    path_params = dict(request.path_params) if request.path_params else {}
    headers = dict(request.headers) if request.headers else {}

    write_log(
        log_type="debug",
        message=f"|request| {request.method} {request.url} from {client_ip} "
        f"user_agent={user_agent} "
        f"query={query} path_params={path_params} "
        f"content_type={content_type or 'none'} body_size={len(body_bytes)} "
        f"headers={headers} body={req_body_snip}",
    )


def _log_response(
    request: Request,
    status_code: int,
    headers: dict[str, str],
    body: bytes,
    body_total_size: int,
    process_ms: float,
    body_too_large: bool = False,
):
    """Log response details using raw ASGI message data."""
    content_type = headers.get("content-type")

    resp_body_snip = (
        safe_body_str(
            body=body,
            content_type=content_type,
            limit=settings.logging.log_body_limit,
            is_too_large=body_too_large,
        )
        if settings.logging.log_responses_body
        else "<not logged>"
    )

    write_log(
        log_type="debug",
        message=f"|response| {request.method} {request.url} "
        f"status={status_code} time_ms={process_ms:.2f} "
        f"content_type={content_type or 'none'} body_size={body_total_size} "
        f"headers={headers} body={resp_body_snip}",
    )

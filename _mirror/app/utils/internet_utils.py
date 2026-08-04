import asyncio
import time
import traceback
from contextvars import ContextVar

import httpx
from socksio.exceptions import ProtocolError as SocksProtocolError

from app.config import settings
from app.utils.app_logging import write_log
from app.utils.logging_utils import safe_body_str

# Context variable to store request start time
_request_start_time: ContextVar[float] = ContextVar("request_start_time", default=0.0)


async def log_outgoing_request(request: httpx.Request):
    """Log outgoing HTTP request."""
    if not settings.logging.debug:
        return

    # Store start time for this request
    _request_start_time.set(time.perf_counter())

    content_type = request.headers.get("content-type")
    body_bytes = request.content if hasattr(request, "content") else b""
    is_too_large = len(body_bytes) > settings.logging.log_body_limit

    req_body_snip = (
        safe_body_str(
            body=body_bytes,
            content_type=content_type,
            limit=settings.logging.log_body_limit,
            is_too_large=is_too_large,
        )
        if settings.logging.log_requests_body
        else "<not logged>"
    )

    headers = dict(request.headers) if request.headers else {}

    write_log(
        log_type="debug",
        message=f"|outgoing_request| {request.method} {request.url} "
        f"content_type={content_type or 'none'} body_size={len(body_bytes)} "
        f"headers={headers} body={req_body_snip}",
    )


async def log_outgoing_response(response: httpx.Response):
    """Log outgoing HTTP response."""
    if not settings.logging.debug:
        return

    # Calculate request duration
    start = _request_start_time.get(0.0)
    process_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0.0

    content_type = response.headers.get("content-type")

    # Force read the response body if not already read
    await response.aread()
    body_bytes = response.content
    is_too_large = len(body_bytes) > settings.logging.log_body_limit

    resp_body_snip = (
        safe_body_str(
            body=body_bytes,
            content_type=content_type,
            limit=settings.logging.log_body_limit,
            is_too_large=is_too_large,
        )
        if settings.logging.log_responses_body
        else "<not logged>"
    )

    headers = dict(response.headers) if response.headers else {}

    write_log(
        log_type="debug",
        message=f"|outgoing_response| {response.request.method} {response.request.url} "
        f"status={response.status_code} time_ms={process_ms:.2f} "
        f"content_type={content_type or 'none'} body_size={len(body_bytes)} "
        f"headers={headers} body={resp_body_snip}",
    )


def _get_httpx_event_hooks() -> dict:
    """
    Get event hooks for httpx client with logging support.

    Returns empty dict if debug logging is disabled.
    """
    if not settings.logging.debug:
        return {}

    return {
        "request": [log_outgoing_request],
        "response": [log_outgoing_response],
    }


async def _get_connection_attempts() -> list[dict[str, str]]:
    """
    Generate connection attempts list based on download priority and available configurations.

    Returns:
        List of connection attempt dictionaries with 'type' key
    """
    connection_attempts = []

    # Parse priority string and create attempts based on available configs
    priorities = [p.strip() for p in settings.network.download_priority.split(",")]
    for priority in priorities:
        if priority == "direct" and settings.network.direct:
            connection_attempts.append({"type": "direct"})
        elif priority == "tor" and settings.network.tor:
            connection_attempts.append({"type": "tor"})
        elif priority == "proxy" and settings.network.proxy:
            connection_attempts.append({"type": "proxy"})

    return connection_attempts


def _get_attempt_description(attempt_type: str) -> str:
    """Get human-readable description for connection attempt type."""
    if attempt_type == "direct":
        return "without proxy"
    elif attempt_type == "tor":
        return "via TOR"
    else:  # proxy
        return f"via {settings.network.proxy_type.upper()} proxy"


def _get_proxy_url(proxy_type: str) -> str | None:
    """
    Get proxy URL based on proxy type.

    Args:
        proxy_type: Type of proxy ('tor' or 'proxy')

    Returns:
        Proxy URL string or None
    """
    if proxy_type == "tor":
        return f"socks5://{settings.network.tor_host}:{settings.network.tor_port}"

    elif proxy_type == "proxy":
        host = settings.network.proxy_host
        port = settings.network.proxy_port
        username = settings.network.proxy_username
        password = settings.network.proxy_password
        protocol = settings.network.proxy_type  # "http" or "socks5"

        # Validate proxy_type
        if protocol not in ("http", "socks5"):
            write_log(
                log_type=["system", "errors"],
                message=f"Invalid proxy_type: {protocol}.",
            )
            raise ValueError(f"Invalid proxy_type: {protocol}")

        if username and password:
            return f"{protocol}://{username}:{password}@{host}:{port}"
        return f"{protocol}://{host}:{port}"

    return None


def _prepare_client(
    attempt_type: str, timeout: float
) -> tuple[dict, httpx.AsyncHTTPTransport | None]:
    """
    Prepare httpx client kwargs and transport for given attempt type.

    Args:
        attempt_type: Connection attempt type ('direct', 'tor', or 'proxy')
        timeout: Request timeout in seconds

    Returns:
        Tuple of (client_kwargs, transport)
    """
    client_kwargs = {
        "timeout": timeout,
        "event_hooks": _get_httpx_event_hooks(),
    }

    transport = None
    if attempt_type != "direct":
        proxy_url = _get_proxy_url(attempt_type)
        if proxy_url:
            transport = httpx.AsyncHTTPTransport(proxy=proxy_url)

    return client_kwargs, transport


def _log_error(context: str, attempt_desc: str, error: Exception):
    """Log error with appropriate format based on error type."""
    if isinstance(error, httpx.HTTPStatusError):
        body_preview = (
            error.response.text[:1000] if error.response.content else "<no body>"
        )
        write_log(
            log_type=["system", "errors"],
            message=f"{context} | HTTPStatusError [{attempt_desc}] | "
            f"status={error.response.status_code} | body_preview={body_preview}",
        )
    elif isinstance(error, httpx.ProtocolError):
        write_log(
            log_type=["system", "errors"],
            message=f"{context} | ProtocolError [{attempt_desc}] | err={repr(error)}",
        )
    elif isinstance(error, httpx.RequestError):
        write_log(
            log_type=["system", "errors"],
            message=f"{context} | RequestError [{attempt_desc}] | err={repr(error)}",
        )
    elif isinstance(error, SocksProtocolError):
        write_log(
            log_type=["system", "errors"],
            message=f"{context} | SocksProtocolError [{attempt_desc}] | err={repr(error)}",
        )
    elif isinstance(error, OSError):
        write_log(
            log_type=["system", "errors"],
            message=f"{context} | OSError [{attempt_desc}] | err={repr(error)}",
        )
    else:
        tb = traceback.format_exc()
        write_log(
            log_type=["system", "errors"],
            message=f"{context} | UnexpectedError [{attempt_desc}] | "
            f"err={repr(error)}\n{tb}",
        )


def _log_all_attempts_failed(context: str):
    """Log that all connection attempts have failed."""
    write_log(
        log_type=["system", "errors"],
        message=f"{context} | All connection attempts failed.",
    )


async def make_request_with_retries(
    url: str,
    method: str = "GET",
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    files: dict[str, tuple[None, str]] | None = None,
    context: str = "request",
    timeout: float = 10.0,
    skip_status_codes: list[int] | None = None,
) -> httpx.Response | None:
    """
    Makes HTTP request with automatic retries through different connection methods.

    Args:
        url: URL to request
        method: HTTP method (GET, POST, etc.)
        params: Parameters for the request
        headers: Headers for the request
        files: Files or form data for the request
        context: Context description for logging
        timeout: Request timeout in seconds
        skip_status_codes: List of HTTP status codes to return immediately without retrying (e.g. 404, 429)

    Returns:
        Response object on success, None on failure after all retries
    """
    params = params or {}
    headers = headers or {}
    skip_status_codes = skip_status_codes or []
    connection_attempts = await _get_connection_attempts()

    for attempt in connection_attempts:
        attempt_desc = _get_attempt_description(attempt["type"])

        try:
            client_kwargs, transport = _prepare_client(
                attempt_type=attempt["type"], timeout=timeout
            )

            async with httpx.AsyncClient(
                **client_kwargs, transport=transport
            ) as client:
                client.headers.clear()  # Clear default headers
                response: httpx.Response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    files=files,
                )
                # Return immediately for expected "not found" or similar codes
                if response.status_code in skip_status_codes:
                    return response
                response.raise_for_status()
                return response

        except Exception as err:
            _log_error(context=context, attempt_desc=attempt_desc, error=err)

    _log_all_attempts_failed(context)
    return None


async def download_file_with_retries(
    url: str,
    save_path: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    context: str = "Downloading file",
    timeout: float = 30.0,
    chunk_size: int = 8192,
) -> bool:
    """
    Downloads a file with automatic retries through different connection methods.

    Args:
        url: URL to download from
        save_path: Path to save the file to
        params: Optional URL parameters
        headers: Optional request headers
        context: Context description for logging
        timeout: Request timeout in seconds (higher for file downloads)
        chunk_size: Size of chunks to write (bytes)

    Returns:
        True if download successful, False otherwise
    """
    params = params or {}
    headers = headers or {}
    connection_attempts = await _get_connection_attempts()

    for attempt in connection_attempts:
        attempt_desc = _get_attempt_description(attempt["type"])

        try:
            client_kwargs, transport = _prepare_client(
                attempt_type=attempt["type"], timeout=timeout
            )

            async with httpx.AsyncClient(
                **client_kwargs, transport=transport
            ) as client:
                client.headers.clear()  # Clear default headers

                # Stream the download
                async with client.stream(
                    method="GET", url=url, params=params, headers=headers
                ) as response:
                    await response.aread()
                    response.raise_for_status()

                    # Write to file in chunks. file.write() is a blocking call,
                    # so run each write in the default executor to avoid
                    # blocking the event loop on large downloads.
                    loop = asyncio.get_running_loop()
                    with open(save_path, "wb") as file:
                        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                            await loop.run_in_executor(None, file.write, chunk)

                return True

        except Exception as err:
            # For file write errors, add save_path to context
            if isinstance(err, OSError):
                _log_error(
                    context=f"{context} | save_path={save_path}",
                    attempt_desc=attempt_desc,
                    error=err,
                )
            else:
                _log_error(context=context, attempt_desc=attempt_desc, error=err)

    _log_all_attempts_failed(context)
    return False

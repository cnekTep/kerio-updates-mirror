import asyncio
import contextlib
import os
import tempfile
import time
import traceback
from contextvars import ContextVar
from typing import Any
from urllib.parse import quote

import httpx
from socksio.exceptions import ProtocolError as SocksProtocolError

from app.config import settings
from app.utils.app_logging import log_event
from app.utils.file_utils import PART_SUFFIX
from app.utils.logging_utils import safe_body_str

# Context variable to store request start time
_request_start_time: ContextVar[float] = ContextVar("request_start_time", default=0.0)

# Windows: the target of os.replace (or the freshly closed temp file) may be briefly
# locked by an antivirus, the search indexer or a reader, so PermissionError is retried
_REPLACE_ATTEMPTS = 5
_REPLACE_RETRY_DELAY = 0.2  # seconds, multiplied by the attempt number

# tempfile creates files as 0600, but finished cache files must stay readable by other
# processes/containers (e.g. nginx), as they were with a plain open(). Has no effect
# on Windows, where only the read-only flag is honoured, and is skipped silently on
# filesystems without POSIX permissions
_CACHE_FILE_MODE = 0o644


class _LocalFileError(Exception):
    """
    Raised when the downloaded file cannot be written locally (disk full, no access, etc.).

    Retrying through another connection route cannot fix such an error.
    """

    def __init__(self, original: OSError):
        super().__init__(str(original))
        self.original = original


@contextlib.contextmanager
def _local_io():
    """Mark any OSError raised inside the block as a local file error."""
    try:
        yield
    except OSError as err:
        raise _LocalFileError(err) from err


async def log_outgoing_request(request: httpx.Request):
    """Log outgoing HTTP request."""
    if not settings.logging.debug:
        return

    # Store start time for this request
    _request_start_time.set(time.perf_counter())

    # Logging must never break the request itself
    try:
        content_type = request.headers.get("content-type")

        try:
            body_bytes: bytes | None = request.content
        except httpx.RequestNotRead:
            # Multipart/streaming bodies cannot be read without consuming them
            body_bytes = None

        if body_bytes is None:
            body_size: int | str = "unknown"
            req_body_snip = "<streaming body>"
        else:
            body_size = len(body_bytes)
            is_too_large = body_size > settings.logging.log_body_limit
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

        log_event(
            log_type="debug",
            message=f"|outgoing_request| {request.method} {request.url} "
            f"content_type={content_type or 'none'} body_size={body_size} "
            f"headers={headers} body={req_body_snip}",
        )
    except Exception as err:
        log_event(
            log_type=["system", "errors"],
            message=f"Failed to log outgoing request: {err!r}",
            notify=False,
        )


async def log_outgoing_response(response: httpx.Response, read_body: bool = True):
    """
    Log outgoing HTTP response.

    With read_body=False the body is not read (used for streamed downloads, so a large
    file is not loaded into memory just for logging) and is logged as a placeholder.
    """
    if not settings.logging.debug:
        return

    if read_body:
        # Force read the response body if not already read.
        # Outside of try on purpose: a network error here is a real request failure
        # and must reach the caller instead of being swallowed by the logging code.
        await response.aread()

    # Logging must never break the request itself
    try:
        # Calculate request duration
        start = _request_start_time.get(0.0)
        process_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0.0

        content_type = response.headers.get("content-type")

        if read_body:
            body_bytes = response.content
            body_size: int | str = len(body_bytes)
            is_too_large = body_size > settings.logging.log_body_limit

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
        else:
            body_size = "unknown"
            resp_body_snip = "<streaming body>"

        headers = dict(response.headers) if response.headers else {}

        log_event(
            log_type="debug",
            message=f"|outgoing_response| {response.request.method} {response.request.url} "
            f"status={response.status_code} time_ms={process_ms:.2f} "
            f"content_type={content_type or 'none'} body_size={body_size} "
            f"headers={headers} body={resp_body_snip}",
        )
    except Exception as err:
        log_event(
            log_type=["system", "errors"],
            message=f"Failed to log outgoing response: {err!r}",
            notify=False,
        )


async def log_outgoing_stream_response(response: httpx.Response):
    """Log outgoing HTTP response of a streamed download without reading its body."""
    await log_outgoing_response(response, read_body=False)


def _get_httpx_event_hooks(stream: bool = False) -> dict:
    """
    Get event hooks for httpx client with logging support.

    Args:
        stream: True for streamed downloads (the response body is not read for logging)

    Returns empty dict if debug logging is disabled.
    """
    if not settings.logging.debug:
        return {}

    return {
        "request": [log_outgoing_request],
        "response": [log_outgoing_stream_response if stream else log_outgoing_response],
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
        elif priority == "xray" and settings.network.xray:
            connection_attempts.append({"type": "xray"})
        elif priority == "tor" and settings.network.tor:
            connection_attempts.append({"type": "tor"})
        elif priority == "proxy" and settings.network.proxy:
            connection_attempts.append({"type": "proxy"})

    return connection_attempts


def _get_attempt_description(attempt_type: str) -> str:
    """Get human-readable description for connection attempt type."""
    if attempt_type == "direct":
        return "without proxy"
    elif attempt_type == "xray":
        return "via Xray"
    elif attempt_type == "tor":
        return "via TOR"
    else:  # proxy
        return f"via {settings.network.proxy_type.upper()} proxy"


def _get_proxy_url(proxy_type: str) -> str | None:
    """
    Get proxy URL based on proxy type.

    Args:
        proxy_type: Type of proxy ('xray', 'tor' or 'proxy')

    Returns:
        Proxy URL string or None
    """
    if proxy_type == "xray":
        return f"socks5://{settings.network.xray_host}:{settings.network.xray_port}"

    elif proxy_type == "tor":
        return f"socks5://{settings.network.tor_host}:{settings.network.tor_port}"

    elif proxy_type == "proxy":
        host = settings.network.proxy_host
        port = settings.network.proxy_port
        username = settings.network.proxy_username
        password = settings.network.proxy_password
        protocol = settings.network.proxy_type  # "http" or "socks5"

        # Validate proxy_type
        if protocol not in ("http", "socks5"):
            log_event(
                log_type=["system", "errors"],
                message=f"Invalid proxy_type: {protocol}.",
            )
            raise ValueError(f"Invalid proxy_type: {protocol}")

        if username and password:
            # Percent-encode credentials: special characters (@ : / #) would break the URL
            return (
                f"{protocol}://{quote(username, safe='')}:{quote(password, safe='')}"
                f"@{host}:{port}"
            )
        return f"{protocol}://{host}:{port}"

    return None


def _prepare_client(
    attempt_type: str, timeout: float, stream: bool = False
) -> tuple[dict, httpx.AsyncHTTPTransport | None]:
    """
    Prepare httpx client kwargs and transport for given attempt type.

    Args:
        attempt_type: Connection attempt type ('direct', 'xray', 'tor', or 'proxy')
        timeout: Request timeout in seconds
        stream: True for streamed downloads (affects debug logging of the response body)

    Returns:
        Tuple of (client_kwargs, transport)
    """
    client_kwargs = {
        "timeout": timeout,
        "event_hooks": _get_httpx_event_hooks(stream=stream),
    }

    transport = None
    if attempt_type != "direct":
        proxy_url = _get_proxy_url(attempt_type)
        if proxy_url:
            transport = httpx.AsyncHTTPTransport(proxy=proxy_url)

    return client_kwargs, transport


def _log_error(
    context: str,
    attempt_desc: str,
    error: Exception,
    notify: bool = True,
):
    """Log error with appropriate format based on error type."""
    if isinstance(error, httpx.HTTPStatusError):
        body_preview = (
            error.response.text[:1000] if error.response.content else "<no body>"
        )
        log_event(
            log_type=["system", "errors"],
            message=f"{context} | HTTPStatusError [{attempt_desc}] | "
            f"status={error.response.status_code} | body_preview={body_preview}",
            notify=notify,
            action_name=f"{context} | HTTPStatusError",
        )
    elif isinstance(error, httpx.ProtocolError):
        log_event(
            log_type=["system", "errors"],
            message=f"{context} | ProtocolError [{attempt_desc}] | err={repr(error)}",
            notify=notify,
            action_name=f"{context} | ProtocolError",
        )
    elif isinstance(error, httpx.RequestError):
        log_event(
            log_type=["system", "errors"],
            message=f"{context} | RequestError [{attempt_desc}] | err={repr(error)}",
            notify=notify,
            action_name=f"{context} | RequestError",
        )
    elif isinstance(error, SocksProtocolError):
        log_event(
            log_type=["system", "errors"],
            message=f"{context} | SocksProtocolError [{attempt_desc}] | err={repr(error)}",
            notify=notify,
            action_name=f"{context} | SocksProtocolError",
        )
    elif isinstance(error, OSError):
        # filename/winerror are not part of repr(): they show which file and step failed
        details = ""
        if error.filename or getattr(error, "winerror", None):
            details = (
                f" | filename={error.filename!r} filename2={error.filename2!r} "
                f"winerror={getattr(error, 'winerror', None)!r}"
            )
        log_event(
            log_type=["system", "errors"],
            message=f"{context} | OSError [{attempt_desc}] | err={repr(error)}{details}",
            notify=notify,
            action_name=f"{context} | OSError",
        )
    else:
        tb = traceback.format_exc()
        log_event(
            log_type=["system", "errors"],
            message=f"{context} | UnexpectedError [{attempt_desc}] | "
            f"err={repr(error)}\n{tb}",
            notify=notify,
            action_name=f"{context} | UnexpectedError",
        )


def _log_all_attempts_failed(context: str, notify: bool = True):
    """Log that all connection attempts have failed."""
    log_event(
        log_type=["system", "errors"],
        message=f"{context} | All connection attempts failed.",
        notify=notify,
        action_name=f"{context} | All connection attempts failed",
    )


async def make_request_with_retries(
    url: str,
    method: str = "GET",
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    files: dict[str, tuple[None, str]] | None = None,
    json: dict[str, Any] | None = None,
    context: str = "request",
    timeout: float = 10.0,
    skip_status_codes: list[int] | None = None,
    notify: bool = True,
) -> httpx.Response | None:
    """
    Makes HTTP request with automatic retries through different connection methods.

    Args:
        url: URL to request
        method: HTTP method (GET, POST, etc.)
        params: Parameters for the request
        headers: Headers for the request
        files: Files or form data for the request
        json: JSON body for the request
        context: Context description for logging
        timeout: Request timeout in seconds
        skip_status_codes: List of HTTP status codes to return immediately without retrying (e.g. 404, 429)
        notify: Whether failures should trigger notifications. Pass False when the
            request itself is part of the notification pipeline (avoids notification loops)

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
                    json=json,
                )
                # Return immediately for expected "not found" or similar codes
                if response.status_code in skip_status_codes:
                    return response
                response.raise_for_status()
                return response

        except Exception as err:
            _log_error(
                context=context,
                attempt_desc=attempt_desc,
                error=err,
                notify=notify,
            )

    _log_all_attempts_failed(context, notify=notify)
    return None


async def _replace_with_retries(src: str, dst: str) -> None:
    """Replace dst with src; PermissionError is retried (temporary Windows file locks)."""
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError as err:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise _LocalFileError(err) from err
            await asyncio.sleep(_REPLACE_RETRY_DELAY * (attempt + 1))
        except OSError as err:
            raise _LocalFileError(err) from err


async def _save_response(
    response: httpx.Response, save_path: str, chunk_size: int
) -> None:
    """
    Stream the response body to save_path through a unique temporary file.

    The temporary file has a random name, so concurrent downloads of the same target
    never share it. The target is replaced only after a complete download, so a failed
    attempt never leaves a partial file and never destroys an existing one.

    Raises:
        _LocalFileError: if the file cannot be written locally
        (network errors are raised as they are)
    """
    loop = asyncio.get_running_loop()

    # The temporary file lives next to the target, so os.replace stays atomic
    # (same filesystem)
    with _local_io():
        file = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{os.path.basename(save_path)}.",
            suffix=PART_SUFFIX,
            dir=os.path.dirname(os.path.abspath(save_path)),
            delete=False,
        )
    tmp_path = file.name

    try:
        with file:
            # Give the file regular permissions before it becomes the final one.
            # Best effort: some filesystems (SMB/CIFS, FAT mounts) do not support
            # chmod, and that must not fail the download
            with contextlib.suppress(OSError):
                os.chmod(tmp_path, _CACHE_FILE_MODE)

            async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                # file.write() is a blocking call, so run each write in the default
                # executor to avoid blocking the event loop on large downloads.
                with _local_io():
                    await loop.run_in_executor(None, file.write, chunk)

        await _replace_with_retries(tmp_path, save_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


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

    A local write error (disk full, no access) stops the retries: another connection
    route cannot fix it.

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
                attempt_type=attempt["type"], timeout=timeout, stream=True
            )

            async with httpx.AsyncClient(
                **client_kwargs, transport=transport
            ) as client:
                client.headers.clear()  # Clear default headers

                # Stream the download
                async with client.stream(
                    method="GET", url=url, params=params, headers=headers
                ) as response:
                    if not response.is_success:
                        # Read the body only on errors so that _log_error can show a preview
                        await response.aread()
                        response.raise_for_status()

                    await _save_response(
                        response=response, save_path=save_path, chunk_size=chunk_size
                    )

                return True

        except _LocalFileError as err:
            # Disk problem: other routes cannot fix it, so stop instead of re-downloading
            _log_error(
                context=f"{context} | save_path={save_path}",
                attempt_desc=attempt_desc,
                error=err.original,
            )
            return False

        except Exception as err:
            _log_error(context=context, attempt_desc=attempt_desc, error=err)

    _log_all_attempts_failed(context)
    return False

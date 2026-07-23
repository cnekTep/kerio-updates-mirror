"""
Shared utilities for HTTP request/response logging.
Provides common constants and functions used across different logging modules.
"""

from app.config import settings

# Binary content type patterns
BINARY_CONTENT_PATTERNS = [
    "application/pgp-signature",
    "application/x-gzip",
]


def is_binary_content(content_type: str | None) -> bool:
    """
    Check if content type represents binary data that shouldn't be decoded to text.

    Args:
        content_type: The Content-Type header value

    Returns:
        True if content is binary, False otherwise
    """
    if not content_type:
        return False

    content_type_lower = content_type.lower()
    return any(pattern in content_type_lower for pattern in BINARY_CONTENT_PATTERNS)


def safe_body_str(
    body: bytes,
    content_type: str | None = None,
    limit: int = settings.logging.log_body_limit,
    is_too_large: bool = False,
) -> str:
    """
    Convert body bytes to safe loggable string with truncation.

    Args:
        body: Raw body bytes
        content_type: Content-Type header value
        limit: Maximum characters to include before truncation
        is_too_large: Whether body exceeds log body limit

    Returns:
        Safe string representation of body for logging
    """
    if is_too_large:
        return f"<body too large, size={len(body):,} bytes>"

    if not body:
        return "<empty>"

    # Check if content is binary
    if is_binary_content(content_type):
        return f"<binary data: {content_type}, {len(body):,} bytes>"

    try:
        decoded = body.decode(encoding="utf-8", errors="replace")
        if len(decoded) > limit:
            return decoded[:limit] + f"...(truncated from {len(decoded)} chars)"
        return decoded
    except Exception:
        return f"<binary data, {len(body):,} bytes>"

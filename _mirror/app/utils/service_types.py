"""Shared types used across services and utilities.

This module holds small, dependency-free types that are passed between
services (e.g. update results) or between services and templates (e.g.
notification lines), so they don't belong to any single service module.
"""

from typing import NamedTuple


class UpdateResult(NamedTuple):
    """
    Result of a single update step (Web Filter key, IDS, GeoIP, etc.).

    Returned by service methods such as
    `WebFilterService.update_web_filter_key` or
    `IDSService.download_ids_update_files`, and consumed by
    `MirrorUpdateService` to build the notification email and compute
    overall success across all steps.

    Attributes:
        success: True if the update succeeded (or was already up to date).
        message: Human-readable description of the result, shown in logs
            and in the notification email.

    Example:
        >>> result = UpdateResult(success=True, message="Already up to date: 3.549")
        >>> result.success
        True
        >>> result.message
        'Already up to date: 3.549'
    """

    success: bool
    message: str


class VersionCheckResult(NamedTuple):
    """
    Result of checking whether a newer version is available upstream.

    Shared shape returned by `_check_ids_update`, `_check_geoip_update`,
    and `_check_kerio_update` (the common implementation behind the
    first two, for endpoints that share the same request structure,
    license error handling, response format, and version comparison logic).

    Attributes:
        ok: False if the check itself failed (network/license/parse error).
            True if the check succeeded, regardless of whether a newer
            version is actually available.
        up_to_date: True if the check succeeded and no newer version is
            available (i.e. the current version is already the latest).
        version: New minor version number, if a newer one is available;
            None if not checked, unavailable, or already up to date.
        download_link: URL to download the new version, if available;
            None under the same conditions as `version`.
        message: Human-readable description of the outcome, used in
            logs and notifications.

    Example:
        >>> result = VersionCheckResult(
        ...     ok=True, up_to_date=True, version=None,
        ...     download_link=None, message="Already up to date: 3.456",
        ... )
        >>> result.up_to_date
        True
    """

    ok: bool
    up_to_date: bool
    version: int | None
    download_link: str | None
    message: str


# A notification line is either a plain string, or a dict with 'text' and
# 'success' keys. EmailService normalizes both forms before rendering, and
# the email template renders 'text' in bold when 'success' is False.
#
# Example:
#     lines: list[NotificationLine] = [
#         "Using license key: 20339-1K3IL-8V8GA",           # plain line
#         {"text": "Failed to reach mirror", "success": False},  # highlighted
#     ]
NotificationLine = str | dict[str, str | bool]

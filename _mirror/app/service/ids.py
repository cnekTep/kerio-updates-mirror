from datetime import date
from pathlib import Path

from app.config import settings
from app.utils.app_logging import log_event
from app.utils.file_utils import ensure_dir
from app.utils.internet_utils import (
    make_request_with_retries,
    download_file_with_retries,
)
from app.utils.service_types import UpdateResult, VersionCheckResult


class IDSService:
    """
    Service layer for IDS/IPS operations.

    Handles business logic related to IDS management,
    acting as an intermediary between the API layer and data repository.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def download_ids_update_files(
        self,
        version: str,
        notify: bool = True,
    ) -> UpdateResult:
        """
        Download IDS update files from Kerio server.

        Checks for a new version against the current,
        downloads the main file and its signature, then updates in .env.

        Args:
            version: IDS major version to download (e.g. ``"5"``).
            notify (bool, optional): Whether to notify on failure.

        Returns:
            UpdateResult: success flag and a message describing the IDS
            update result (e.g. "IDS v3 Update | Already up to date: 3.456").
        """
        if not settings.updates.license_number:
            message = (
                f"IDS v{version} Update | Error: "
                f"Skipping: license key is not configured"
            )
            log_event(
                log_type=["system", "updates", "errors"],
                message=message,
                notify=notify,
                action_name="IDS Update",
            )
            return UpdateResult(success=False, message=message)

        log_event(
            log_type=["system"],
            message=f"IDS v{version} Update | Downloading update files from Kerio server",
        )

        # Get current version from settings based on incoming version
        current_version = getattr(settings.updates, f"ids_{version}_version") or 0

        # Check for a newer version upstream
        check = await self._check_ids_update(
            version=version,
            current_version=current_version,
            notify=notify,
        )

        if not check.ok or check.up_to_date:
            # message already contains the specific reason (unreachable, invalid
            # license, expired, unexpected response, or "already up to date")
            return UpdateResult(success=check.ok, message=check.message)

        # At this point check_ok is True and up_to_date is False, so both fields
        # are guaranteed to be populated by _check_kerio_update - narrow the types
        # explicitly since the dict itself can't express that guarantee.
        new_version = check.version
        download_link = check.download_link
        assert isinstance(new_version, int)
        assert isinstance(download_link, str)

        update_dir = ensure_dir(path=settings.updates.update_dir)
        filename = f"ids_{version}_{new_version}.gz"

        # Download main file
        if not await self._download_ids_file(
            url=download_link,
            save_path=update_dir / filename,
            version=version,
            notify=notify,
        ):
            message = f"IDS v{version} Update | Failed to download main archive"
            return UpdateResult(success=False, message=message)

        # Download signature file
        if not await self._download_ids_file(
            url=f"{download_link}.sig",
            save_path=update_dir / f"{filename}.sig",
            version=version,
            is_signature=True,
            notify=notify,
        ):
            message = f"IDS v{version} Update | Failed to download signature"
            return UpdateResult(success=False, message=message)

        settings.bulk_update(
            {
                f"updates.ids_{version}_version": new_version,
                f"updates.ids_{version}_last_update": date.today(),
            }
        )

        message = (
            f"IDS v{version} Update | Downloaded new version: {version}.{new_version}"
        )
        log_event(log_type=["system", "updates"], message=message)
        return UpdateResult(success=True, message=message)

    @staticmethod
    async def download_snort_template(notify: bool = True) -> UpdateResult:
        """
        Download Snort template files from the Kerio server.

        Args:
            notify (bool, optional): Whether to notify on failure. Defaults to True.

        Returns:
            UpdateResult: success flag and a message describing the Snort
            template update result (e.g. "Snort Template Update | Downloaded latest version").
        """
        log_event(
            log_type=["system"],
            message="Snort Template Update | Downloading update files from Kerio server",
        )

        base_url = "http://download.kerio.com/control-update/config/v1"
        filenames = ["snort.tpl", "snort.tpl.md5"]

        update_dir = ensure_dir(path=settings.updates.update_dir)

        for filename in filenames:
            if not await download_file_with_retries(
                url=f"{base_url}/{filename}",
                save_path=str(update_dir / filename),
                context="Snort Template Update",
            ):
                message = (
                    f"Snort Template Update | Error: Failed to download {filename}"
                )
                log_event(
                    log_type=["system", "updates", "errors"],
                    message=message,
                    notify=notify,
                    action_name="IDS Update",
                )
                return UpdateResult(success=False, message=message)

        message = "Snort Template Update | Downloaded latest version"
        log_event(log_type=["system", "updates"], message=message)
        return UpdateResult(success=True, message=message)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_ids_update(
        version: str,
        current_version: int,
        notify: bool = True,
    ) -> VersionCheckResult:
        """
        Check whether a new IDS version is available upstream.

        Args:
            version: IDS major version string (e.g. ``"5"``).
            current_version: Minor version number currently stored in the database.
            notify: Whether to trigger a notification on failure. Defaults to True.

        Returns:
            VersionCheckResult: Outcome of the check.
        """
        return await _check_kerio_update(
            url="https://ids-update.kerio.com/update.php",
            version=version,
            current_version=current_version,
            label=f"IDS v{version}",
            notify=notify,
        )

    @staticmethod
    async def _download_ids_file(
        url: str,
        save_path: Path,
        version: str,
        is_signature: bool = False,
        notify: bool = True,
    ) -> bool:
        """
        Download an IDS file and return success status.

        Args:
            url: Download URL.
            save_path: Local path to save the file.
            version: IDS major version string, used in log messages.
            is_signature: ``True`` for the ``.sig`` file, ``False`` for the main archive.
            notify: Whether to trigger a notification on failure. Defaults to True.

        Returns:
            ``True`` if the download succeeded, ``False`` otherwise.
        """
        file_type = "signature" if is_signature else "main archive"

        if await download_file_with_retries(
            url=url, save_path=str(save_path), context=f"IDS v{version} {file_type}"
        ):
            return True

        log_event(
            log_type=["system", "errors"],
            message=f"IDS v{version} Update | Failed to download {file_type}",
            notify=notify,
            action_name="IDS Update",
        )
        return False


async def _check_kerio_update(
    url: str,
    version: str,
    current_version: int,
    label: str,
    notify: bool = True,
) -> VersionCheckResult:
    """
    Check whether a new version is available on a Kerio update endpoint.

    Shared by IDS and GeoIP update checks - both use the same request structure,
    license error handling, response format, and version comparison logic.

    Args:
        url: Kerio update endpoint URL.
        version: Major version string to include in the request (e.g. ``"5"``).
        current_version: Minor version number currently stored in the database.
        label: Human-readable label for log messages (e.g. ``"IDS v5"``).
        notify: Whether to trigger a notification on failure. Defaults to True.

    Returns:
        VersionCheckResult: Outcome of the check.
    """
    params = {
        "id": settings.updates.license_number,
        "version": f"{version}.{current_version}",
        "tag": "",
    }
    headers = {
        "accept": "*/*",
        "host": "ids-update.kerio.com",
    }

    response = await make_request_with_retries(
        url=url, params=params, headers=headers, context=f"{label} Update"
    )

    if not response:
        message = f"{label} Update | Error: Failed to reach Kerio server"
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="IDS / GeoIP Update",
        )
        return VersionCheckResult(
            ok=False,
            up_to_date=False,
            version=None,
            download_link=None,
            message=message,
        )

    # Handle license errors
    if "Invalid product license" in response.text:
        message = (
            f"{label} Update | Error: "
            f"Invalid product license: {settings.updates.license_number}"
        )
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="IDS / GeoIP Update",
        )
        settings.update("updates.license_number", None)
        return VersionCheckResult(
            ok=False,
            up_to_date=False,
            version=None,
            download_link=None,
            message=message,
        )

    if "Product Software Maintenance expired" in response.text:
        message = (
            f"{label} Update | Error: "
            f"License key expired: {settings.updates.license_number}"
        )
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="IDS / GeoIP Update",
        )
        settings.update("updates.license_number", None)
        return VersionCheckResult(
            ok=False,
            up_to_date=False,
            version=None,
            download_link=None,
            message=message,
        )

    # Parse the response body
    result = _parse_kerio_update_response(response.text)
    if result is None:
        message = (
            f"{label} Update | Error: "
            f"Unexpected response from Kerio server: {response.text.strip()}"
        )
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="IDS / GeoIP Update",
        )
        return VersionCheckResult(
            ok=False,
            up_to_date=False,
            version=None,
            download_link=None,
            message=message,
        )

    new_version = result["version"]
    if current_version >= new_version:
        message = f"{label} Update | Already up to date: {version}.{current_version}"
        log_event(log_type=["system", "updates"], message=message)
        return VersionCheckResult(
            ok=True,
            up_to_date=True,
            version=None,
            download_link=None,
            message=message,
        )

    if "download_link" not in result:
        message = (
            f"{label} Update | Error: New version {version}.{new_version} reported "
            f"but no download link provided"
        )
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="IDS / GeoIP Update",
        )
        return VersionCheckResult(
            ok=False,
            up_to_date=False,
            version=None,
            download_link=None,
            message=message,
        )

    message = f"{label} Update | New version available: {version}.{new_version}"
    log_event(log_type=["system"], message=message)
    return VersionCheckResult(
        ok=True,
        up_to_date=False,
        version=new_version,
        download_link=result["download_link"],
        message=message,
    )


def _parse_kerio_update_response(text: str) -> dict | None:
    """
    Parse a Kerio update server response into a dict with ``version`` and ``download_link``.

    Expected response format::

        0:<major>.<minor>
        full:<download_url>

    The ``full:`` line may be absent when the server acknowledges the request but
    provides no file to download (version is up to date). In that case only
    ``"version"`` is present in the returned dict.

    Args:
        text: Raw response text from the Kerio update server.

    Returns:
        ``{"version": <int>, "download_link": <str>}`` on success, ``None`` on parse error.
    """
    result: dict = {}

    for line in text.strip().splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", maxsplit=1)

        if key == "0":
            try:
                # Extract the minor version number (the part after the dot)
                result["version"] = int(value.split(".")[1])
            except (IndexError, ValueError):
                return None

        elif key == "full":
            result["download_link"] = value

    return result if "version" in result else None

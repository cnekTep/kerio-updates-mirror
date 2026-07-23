from datetime import date
from pathlib import Path

from app.config import settings
from app.utils.app_logging import write_log
from app.utils.file_utils import ensure_dir
from app.utils.internet_utils import (
    make_request_with_retries,
    download_file_with_retries,
)


class IDSService:
    """
    Service layer for IDS/IPS operations.

    Handles business logic related to IDS management,
    acting as an intermediary between the API layer and data repository.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def download_ids_update_files(self, version: str) -> None:
        """
        Download IDS update files from Kerio server.

        Checks for a new version against the current,
        downloads the main file and its signature, then updates in .env.

        Args:
            version: IDS major version to download (e.g. ``"5"``).
        """
        if not settings.updates.license_number:
            write_log(
                log_type=["system", "updates"],
                message=f"IDS v{version} Update | Skipping: license key is not configured",
            )
            return

        write_log(
            log_type=["system"],
            message=f"IDS v{version} Update | Downloading update files from Kerio server",
        )

        # Get current version from settings based on incoming version
        current_version = getattr(settings.updates, f"ids_{version}_version") or 0

        # Check for a newer version upstream
        update_info = await self._check_ids_update(
            version=version, current_version=current_version
        )
        if not update_info:
            return

        new_version, download_link = update_info

        update_dir = ensure_dir(path=settings.updates.update_dir)
        filename = f"ids_{version}_{new_version}.gz"

        # Download main file
        if not await self._download_ids_file(
            url=download_link, save_path=update_dir / filename, version=version
        ):
            return

        # Download signature file
        if not await self._download_ids_file(
            url=f"{download_link}.sig",
            save_path=update_dir / f"{filename}.sig",
            version=version,
            is_signature=True,
        ):
            return

        settings.bulk_update(
            {
                f"updates.ids_{version}_version": new_version,
                f"updates.ids_{version}_last_update": date.today(),
            }
        )
        write_log(
            log_type=["system", "updates"],
            message=f"IDS v{version} Update | Downloaded new version: {version}.{new_version}",
        )

    @staticmethod
    async def download_snort_template() -> None:
        """Download Snort template files from the Kerio server."""
        write_log(
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
                write_log(
                    log_type=["system", "updates"],
                    message=f"Snort Template Update | Failed to download {filename}",
                )
                return

        write_log(
            log_type=["system", "updates"],
            message="Snort Template Update | Successfully downloaded new version",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_ids_update(
        version: str, current_version: int
    ) -> tuple[int, str] | None:
        """
        Check whether a new IDS version is available upstream.

        Args:
            version: IDS major version string (e.g. ``"5"``).
            current_version: Minor version number currently stored in the database.

        Returns:
            ``(new_version, download_link)`` if a newer version exists, ``None`` otherwise.
        """
        return await _check_kerio_update(
            url="https://ids-update.kerio.com/update.php",
            version=version,
            current_version=current_version,
            label=f"IDS v{version}",
        )

    @staticmethod
    async def _download_ids_file(
        url: str, save_path: Path, version: str, is_signature: bool = False
    ) -> bool:
        """
        Download an IDS file and return success status.

        Args:
            url: Download URL.
            save_path: Local path to save the file.
            version: IDS major version string, used in log messages.
            is_signature: ``True`` for the ``.sig`` file, ``False`` for the main archive.

        Returns:
            ``True`` if the download succeeded, ``False`` otherwise.
        """
        file_type = "signature" if is_signature else "main archive"

        if await download_file_with_retries(
            url=url, save_path=str(save_path), context=f"IDS v{version} {file_type}"
        ):
            return True

        write_log(
            log_type=["system"],
            message=f"IDS v{version} Update | Failed to download {file_type}",
        )
        return False


async def _check_kerio_update(
    url: str,
    version: str,
    current_version: int,
    label: str,
) -> tuple[int, str] | None:
    """
    Check whether a new version is available on a Kerio update endpoint.

    Shared by IDS and GeoIP update checks - both use the same request structure,
    license error handling, response format, and version comparison logic.

    Args:
        url: Kerio update endpoint URL.
        version: Major version string to include in the request (e.g. ``"5"``).
        current_version: Minor version number currently stored in the database.
        label: Human-readable label for log messages (e.g. ``"IDS v5"``).

    Returns:
        ``(new_version, download_link)`` if a newer version exists, ``None`` otherwise.
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
        write_log(
            log_type=["system", "updates"],
            message=f"{label} Update | Failed to reach Kerio server",
        )
        return None

    # Handle license errors
    if "Invalid product license" in response.text:
        write_log(
            log_type=["system", "updates"],
            message=f"{label} Update | Invalid product license: {settings.updates.license_number}",
        )
        settings.update("updates.license_number", None)
        return None

    if "Product Software Maintenance expired" in response.text:
        write_log(
            log_type=["system", "updates"],
            message=f"{label} Update | License key expired: {settings.updates.license_number}",
        )
        settings.update("updates.license_number", None)
        return None

    # Parse the response body
    result = _parse_kerio_update_response(response.text)
    if result is None:
        write_log(
            log_type=["system", "updates"],
            message=f"{label} Update | Unexpected response from Kerio server: {response.text.strip()}",
        )
        return None

    new_version = result["version"]
    if current_version >= new_version:
        write_log(
            log_type=["system", "updates"],
            message=f"{label} Update | Already up to date: {version}.{current_version}",
        )
        return None

    if "download_link" not in result:
        write_log(
            log_type=["system", "updates"],
            message=(
                f"{label} Update | New version {version}.{new_version} reported "
                f"but no download link provided"
            ),
        )
        return None

    write_log(
        log_type=["system"],
        message=f"{label} Update | New version available: {version}.{new_version}",
    )
    return new_version, result["download_link"]


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

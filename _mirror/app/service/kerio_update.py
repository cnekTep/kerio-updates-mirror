import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from random import randint
from typing import TypedDict, ClassVar

from fastapi import HTTPException, Response, status
from fastapi.responses import FileResponse

from app.config import settings
from app.utils.app_logging import write_log
from app.utils.file_utils import clean_directory, ensure_dir
from app.utils.internet_utils import (
    download_file_with_retries,
    make_request_with_retries,
)


class ParsedFileName(TypedDict):
    type: str
    version: int | None


class KerioUpdateService:
    """
    Service for handling Kerio Control update requests.

    Supports the following update types:
    - Web Filter: activation key served from settings.
    - IDS/IPS: versions 2, 3, 5 - served from local mirror.
    - GeoIP: versions 4–5 - served from local mirror.
    - Antivirus: proxied from Kerio CDN or cached on local mirror.
    - ShieldMatrix: fetched from upstream and cached locally.
    - Registration: fetched from upstream and cached locally.

    CDN URL and antivirus versions.id TTL are tracked via files on disk, so the
    cache is shared across all worker processes without inter-process communication.
    """

    # For each update type, maps a supported major version to the settings
    # flag(s) that must be enabled for it to be served. If several flags are
    # listed, the version is served if ANY of them is enabled (e.g. IDS v2
    # piggybacks on v3/v5 availability). Types with no numeric version (e.g.
    # "snort") use `None` as the version key.
    _VERSION_ENABLE_FLAGS: dict[str, dict[int | None, tuple[str, ...]]] = {
        "ids": {
            2: ("update_ids_3", "update_ids_5"),
            3: ("update_ids_3",),
            5: ("update_ids_5",),
        },
        "geoip": {
            4: ("update_geoip_4",),
            5: ("update_geoip_5",),
        },
        "snort": {
            None: ("update_ids_5",),
        },
    }

    # Special case: snort.tpl / snort.tpl.md5 have no numeric version
    _SNORT_FILENAME_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^snort\.tpl(\.md5)?$", re.IGNORECASE
    )

    # Matches patterns like "geoip_4_20260803.gz", "ids_2_3471.gz":
    # <type>_<major_version>_<sub_version>.<ext>
    _VERSION_FROM_FILENAME_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^([A-Za-z0-9]+)_(\d+)_"
    )

    # ------------------------------------------------------------------
    # Web Filter
    # ------------------------------------------------------------------

    @staticmethod
    async def get_web_filter_key(client_ip: str | None) -> str:
        """
        Return the Web Filter activation key from settings or forced settings.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Web Filter key string in the format expected by Kerio Control.

        Raises:
            HTTPException: 404 if Web Filter updates are disabled or key not found.
        """
        if not settings.updates.update_web_filter_key:
            write_log(
                log_type=["system", "errors"],
                message="Web Filter | Error: Updates for Web Filter are disabled",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Updates for Web Filter are disabled",
            )

        if settings.updates.forced_web_filter_key:
            return settings.updates.forced_web_filter_key

        web_filter_key = settings.updates.web_filter_key
        if not web_filter_key:
            write_log(
                log_type=["system", "errors"],
                message="Web Filter | Error: Web Filter key not found",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Web Filter key not found",
            )

        return web_filter_key

    # ------------------------------------------------------------------
    # IDS / IPS
    # ------------------------------------------------------------------

    async def get_ids_update_info(self, version: str, client_ip: str | None) -> str:
        """
        Return IDS/IPS update information for the requested version.

        Args:
            version: Client-reported version string (e.g. "5.1" or "9.3").
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Update response string in the format expected by Kerio Control.

        Raises:
            HTTPException: 400 if the version string is malformed,
                           404 if updates are disabled or the version is unsupported.
        """
        major_version = self._parse_major_version(version=version, client_ip=client_ip)
        enabled = self._resolve_enabled_flag(
            update_type="ids",
            version=version,
            major_version=major_version,
            client_ip=client_ip,
        )
        label = self._format_update_label(
            update_type="ids",
            version=version,
        )
        self._check_update_enabled(enabled=enabled, service=label, client_ip=client_ip)

        return self._make_update_response(
            major_version=major_version,
            url_prefix="ids",
            label=label,
        )

    # ------------------------------------------------------------------
    # GeoIP
    # ------------------------------------------------------------------

    async def get_geoip_update_info(self, version: str, client_ip: str | None) -> str:
        """
        Return GeoIP update information for the requested version.

        Args:
            version: Client-reported version string (e.g. "4.1" or "5.3").
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Update response string in the format expected by Kerio Control.

        Raises:
            HTTPException: 400 if the version string is malformed,
                           404 if updates are disabled or the version is unsupported.
        """
        major_version = self._parse_major_version(version=version, client_ip=client_ip)
        enabled = self._resolve_enabled_flag(
            update_type="geoip",
            version=version,
            major_version=major_version,
            client_ip=client_ip,
        )
        label = self._format_update_label(
            update_type="geoip",
            version=version,
        )
        self._check_update_enabled(enabled=enabled, service=label, client_ip=client_ip)

        return self._make_update_response(
            major_version=major_version,
            url_prefix="geoip",
            label=label,
        )

    # ------------------------------------------------------------------
    # File serving (IDS / GeoIP shared)
    # ------------------------------------------------------------------

    def validate_and_get_file_path(self, file_name: str, client_ip: str | None) -> Path:
        """
        Validate a file name from the request and return a safe local path.

        Performs path-traversal checks, extension allowlist validation, type
        allowlist validation, and an enabled-updates check before resolving
        the final path.

        Args:
            file_name: Raw file name from the client request (URL path segment).
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Resolved Path object pointing to the validated file.

        Raises:
                HTTPException: 400 if the update type parsed from the file name is
                                   not recognized,
                               400 if the file name contains illegal characters,
                               400 if the resolved path escapes the update directory,
                               400 if the file extension is not allowed,
                               400 if the path is not a regular file,
                               404 if the type/version is unsupported,
                               404 if updates for the parsed type/version are disabled,
                               404 if the file does not exist.
        """
        parsed = self._parse_type_and_version_from_filename(file_name, client_ip)
        update_type = parsed["type"]
        major_version = parsed["version"]

        if update_type not in self._VERSION_ENABLE_FLAGS:
            write_log(
                log_type=["system", "errors"],
                message=f"Unknown update type '{update_type}' parsed from file_name '{file_name}'",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown update type '{update_type}'",
            )

        enabled = self._resolve_enabled_flag(
            update_type=update_type,
            version=None,
            major_version=major_version,
            client_ip=client_ip,
        )
        label = self._format_update_label(
            update_type=update_type,
            version=major_version,
        )
        self._check_update_enabled(enabled=enabled, service=label, client_ip=client_ip)

        # Security: reject path separators and traversal sequences
        if "/" in file_name or "\\" in file_name or ".." in file_name:
            write_log(
                log_type=["system", "errors"],
                message=f"Path traversal attempt in file_name '{file_name}'",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file name",
            )

        file_path = settings.updates.update_dir / file_name

        # Security: ensure resolved path stays within the allowed directory
        try:
            file_path = file_path.resolve()
            file_path.relative_to(settings.updates.update_dir.resolve())
        except (ValueError, RuntimeError):
            write_log(
                log_type=["system", "errors"],
                message=f"Resolved path escapes update directory for file_name '{file_name}'",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file path",
            )

        allowed_extensions = {".gz", ".md5", ".sig", ".tpl"}
        if file_path.suffix.lower() not in allowed_extensions:
            write_log(
                log_type=["system", "errors"],
                message=f"Disallowed file extension '{file_path.suffix}' for file_name '{file_name}'",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File type not allowed",
            )

        if not file_path.exists():
            write_log(
                log_type=["system", "errors"],
                message=f"File not found: '{file_path}'",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        if not file_path.is_file():
            write_log(
                log_type=["system", "errors"],
                message=f"Path is not a regular file: '{file_path}'",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file",
            )

        return file_path

    # ------------------------------------------------------------------
    # ShieldMatrix
    # ------------------------------------------------------------------

    async def get_shieldmatrix_update_url(self) -> None:
        """
        Fetch the current ShieldMatrix download URL from upstream and store it.

        Raises:
                HTTPException: 404 if ShieldMatrix updates are disabled.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_shieldmatrix,
            service="ShieldMatrix",
            client_ip=None,
        )

        params = {
            "client-id": "control",
            "version": "9.5.0",
            "last-update": "0",
        }
        headers = {
            "user-agent": "KerioControl",
            "accept": "*/*",
        }

        response = await make_request_with_retries(
            url=settings.updates.shieldmatrix_link.rstrip("/") + "/check_update/",
            params=params,
            headers=headers,
            context="get ShieldMatrix update URL",
        )

        if not response:
            write_log(
                log_type=["system", "updates"],
                message=f"ShieldMatrix Update | Failed to get update URL",
            )
            return

        data = response.json()  # Response body: {"available": bool, "url": str}
        if not data.get("available") or not data.get("url"):
            write_log(
                log_type=["system", "updates"],
                message="ShieldMatrix Update | No URL available",
            )
            return

        write_log(
            log_type=["system", "updates"],
            message=f"ShieldMatrix Update | Received URL",
        )
        settings.update("updates.shieldmatrix_url", data["url"].rstrip("/"))

    async def get_shieldmatrix_update_info(
        self,
        client_ip: str | None,
        updates_version: str,
    ) -> str:
        """
        Return ShieldMatrix update availability by comparing versions with upstream.

        Fetches the current version from the configured upstream URL, respecting
        TTL via file mtime, and compares it with the version reported by the client.
        When a newer version is detected, the ipv4 and ipv6 cache directories are
        purged so stale files are re-downloaded on the next request.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            updates_version: Current version reported by the Kerio client.

        Returns:
            JSON string - ``{"available": true, "url": "..."}`` if an update is
            available, ``{"available": false}`` otherwise.

        Raises:
            HTTPException: 404 if ShieldMatrix updates are disabled.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_shieldmatrix,
            service="ShieldMatrix",
            client_ip=client_ip,
        )

        headers = {
            "user-agent": "KerioControl",
            "accept": "*/*",
        }

        upstream_version = await self._get_shieldmatrix_version_cached(headers)

        if not upstream_version or upstream_version > updates_version:
            return (
                '{"available": true, '
                '"url": "http://kerio-updates-mirror.local/api/kerio/updates/shieldmatrix/files"}'
            )

        return '{"available": false}'

    async def get_shieldmatrix_update_version(self, client_ip: str | None) -> str:
        """
        Return the currently cached ShieldMatrix version string.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Version string as plain text (e.g. "20240510").

        Raises:
            HTTPException: 404 if ShieldMatrix updates are disabled or the version
                           has not been cached yet.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_shieldmatrix,
            service="ShieldMatrix",
            client_ip=client_ip,
        )

        version_cache_file = (
            settings.updates.update_dir / "matrix_cache" / "shieldmatrix_version.cache"
        )
        if not version_cache_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ShieldMatrix version not yet cached",
            )

        return version_cache_file.read_text().strip()

    async def get_shieldmatrix_update_file(
        self,
        client_ip: str | None,
        full_path: str,
    ) -> FileResponse:
        """
        Serve a ShieldMatrix update file from cache, downloading it if absent.

        Handles paths of the form ``ipv4/<file>`` or ``ipv6/<file>``. Files are
        served from ``update_dir/matrix_cache/<proto>/<file>`` when present,
        otherwise downloaded from the configured upstream URL and cached for
        subsequent requests.

        Cache invalidation is handled by ``get_shieldmatrix_update_info``:
        when a newer upstream version is detected the ipv4/ipv6 directories are
        purged, forcing a re-download on the next file request.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            full_path: Request path segment, e.g. ``ipv4/threat_data_1.dat``.

        Returns:
            FileResponse with the requested file content.

        Raises:
            HTTPException: 404 if ShieldMatrix updates are disabled or file not found,
                           400 if the path format is invalid,
                           502 if the upstream download fails.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_shieldmatrix,
            service="ShieldMatrix",
            client_ip=client_ip,
        )

        path_parts = full_path.split("/", 1)
        if len(path_parts) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid ShieldMatrix path: {full_path}",
            )

        proto, file_name = path_parts
        if proto not in ("ipv4", "ipv6"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown ShieldMatrix proto: {proto}",
            )

        cache_dir = ensure_dir(settings.updates.update_dir / "matrix_cache" / proto)
        file_path = cache_dir / file_name

        if file_path.exists():
            return FileResponse(file_path)

        # File not cached - download from upstream
        upstream_url = f"{settings.updates.shieldmatrix_url.rstrip('/')}/{full_path}"
        headers = {
            "user-agent": "KerioControl",
            "accept": "*/*",
        }
        await download_file_with_retries(
            url=upstream_url,
            save_path=str(file_path),
            headers=headers,
            context=f"Downloading ShieldMatrix file: {upstream_url}",
        )

        if not file_path.exists():
            write_log(
                log_type=["system"],
                message=f"ShieldMatrix | Failed to download: {full_path}",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to download ShieldMatrix file: {full_path}",
            )

        return FileResponse(file_path)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def get_registration_head_info(self, client_ip: str | None) -> Response:
        """
        Handle HEAD probe requests to the registration endpoint.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Empty response with Kerio-specific headers and status code 200.

        Raises:
            HTTPException: 404 if registration updates are disabled.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_registration,
            service="Registration",
            client_ip=client_ip,
        )

        response_headers = {
            "X-Kerio-Token": "",
            "X-Kerio-Reply-Code": "500",
            "X-Kerio-Reply-Message": "Internal Server Error",
        }

        return Response(content="", status_code=200, headers=response_headers)

    async def get_registration_connect_info(
        self,
        client_ip: str | None,
        content_type: str,
    ) -> Response:
        """
        Handle 'connect' command: serve captcha from file or download from kerio.com.

        Attempts to load captcha data from the local cache file. If the file is
        missing or corrupted, fetches fresh captcha from kerio.com and caches it.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            content_type: Content-Type header value forwarded to the upstream request.

        Returns:
            Response with captcha content and Kerio headers on success,
            or empty response with error headers if captcha is unavailable.

        Raises:
            HTTPException: 404 if registration updates are disabled,
                           502 if all upstream connection attempts failed.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_registration,
            service="Registration",
            client_ip=client_ip,
        )

        try:
            captcha_data = (settings.updates.update_dir / "security_image").read_text(
                encoding="utf-8"
            )
        except OSError:
            captcha_data = ""

        if not all(
            key in captcha_data
            for key in ("security_image", "image_signature", "show_image")
        ):
            captcha_data = await self._fetch_captcha(content_type=content_type)

        return self._make_registration_connect_response(captcha_data)

    async def get_registration_lookup_info(
        self,
        client_ip: str | None,
        base_id: str,
        token: str,
    ) -> Response:
        """
        Handle 'lookup' command by returning registration and license information.

        Verifies that registration updates are enabled and returns a static
        registration response containing license details.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            base_id: Registration base identifier included in the response body.
            token: Kerio session token returned in the response headers.

        Returns:
            Response containing registration information with Kerio-specific
            headers and status code 200.

        Raises:
            HTTPException: 404 if registration updates are disabled.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_registration,
            service="Registration",
            client_ip=client_ip,
        )

        expiry_date = self._get_expiry_date()
        response_content = (
            f"base_id: {base_id}\n"
            "type: Server\n"
            "users: Kerio Control server\n"
            f"expires: {expiry_date}\n"
            "total_users: UNLIMITED\n"
            "edu_version: 0\n"
            "extensions: Kerio Antivirus for Kerio Control server,Kerio Web Filter server\n"
            "license_update: 0\n"
            "product: Kerio Control\n"
            "company: GFI Software\n"
            "reg_type: TRIAL\n"
            f"dwn_trial_expires: {expiry_date}\n"
        )

        response_headers = {
            "X-Kerio-Token": token,
            "X-Kerio-Reply-Code": "200",
            "X-Kerio-Reply-Message": "OK",
            "Content-Type": "application/x-kerio-registration",
        }

        return Response(
            content=response_content, status_code=200, headers=response_headers
        )

    async def get_registration_readinfo_info(
        self,
        client_ip: str | None,
        base_id: str,
        token: str,
    ) -> Response:
        """
        Handle 'readinfo' command by returning the registration profile.

        Verifies that registration updates are enabled and returns a static
        set of registration/company fields expected by Kerio Control. Most
        fields are intentionally left empty since no real registration data
        is stored.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            base_id: Registration base identifier included in the addon_list entry.
            token: Kerio session token returned in the response headers.

        Returns:
            Response containing registration profile information with
            Kerio-specific headers and status code 200.

        Raises:
            HTTPException: 404 if registration updates are disabled.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_registration,
            service="Registration",
            client_ip=client_ip,
        )

        response_content = (
            "company:\n"
            "person:\n"
            "address:\n"
            "city:\n"
            "zipcode:\n"
            "country:\n"
            "phone:\n"
            "email:\n"
            "website:\n"
            "os: 2\n"
            "lang_id: en\n"
            "comment:\n"
            "eduinfo:\n"
            "state:\n"
            "ico:\n"
            "serialnumber:\n"
            "reseller_company:\n"
            "reseller_address:\n"
            "reseller_city:\n"
            "reseller_phone:\n"
            "reseller_email:\n"
            f"expires: {self._get_expiry_date()}\n"
            "users: UNLIMITED\n"
            f"addon_list[]: {base_id};Server;Kerio Control server\n"
            "show_questions: 0"
        )

        response_headers = {
            "X-Kerio-Token": token,
            "X-Kerio-Reply-Code": "200",
            "X-Kerio-Reply-Message": "OK, registration data follows",
            "Content-Type": "application/x-kerio-registration",
        }

        return Response(
            content=response_content, status_code=200, headers=response_headers
        )

    async def get_registration_stored_info(
        self,
        client_ip: str | None,
        base_id: str,
        token: str,
    ) -> Response:
        """
        Handle 'stored' command by confirming the stored registration base_id.

        Verifies that registration updates are enabled and echoes back the
        base_id to confirm it has been "stored" server-side.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            base_id: Registration base identifier to echo back.
            token: Kerio session token returned in the response headers.

        Returns:
            Response confirming the stored base_id with Kerio-specific
            headers and status code 200.

        Raises:
            HTTPException: 404 if registration updates are disabled.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_registration,
            service="Registration",
            client_ip=client_ip,
        )

        response_content = f"base_id: {base_id}"

        response_headers = {
            "X-Kerio-Token": token,
            "X-Kerio-Reply-Code": "200",
            "X-Kerio-Reply-Message": "OK, verified",
        }

        return Response(
            content=response_content, status_code=200, headers=response_headers
        )

    # ------------------------------------------------------------------
    # Antivirus
    # ------------------------------------------------------------------

    async def get_antivirus_update_info(
        self,
        client_ip: str | None,
        version: str,
    ) -> str:
        """
        Return antivirus update information for the requested client version.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            version: Antivirus version string reported by the client
                     (e.g. "9.5.0-T3-9017").

        Returns:
            Update response string in the format expected by Kerio Control.

        Raises:
            HTTPException: 404 if antivirus updates are disabled,
                           403 if the Kerio CDN is selected and the license number is missing.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_antivirus,
            service="Antivirus",
            client_ip=client_ip,
        )
        return await self._make_antivirus_update_response(
            version=version,
            client_ip=client_ip,
        )

    async def get_antivirus_update_file(
        self,
        client_ip: str | None,
        full_path: str,
    ) -> FileResponse | Response:
        """
        Serve an antivirus update file from cache or proxy it from upstream.

        Two modes depending on ``settings.updates.antivirus_cache``:

        - **Cache mode**: files are stored in ``update_dir/antivirus_cache/`` and served
          from disk. ``versions.id`` is re-downloaded when its TTL
          (``settings.updates.antivirus_version_ttl``) expires; on expiry all sibling
          ``versions.*`` files are evicted so they are re-fetched on the next request.
          ``versions.dat.gz`` is intentionally skipped to force the client to fall back
          to the uncompressed variant (for consistency).
          All other files are cached on first download and served from disk.
        - **Proxy mode**: every request is forwarded directly to the upstream CDN.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            full_path: Relative path forwarded to upstream (e.g. ``"9.3/versions.avd"``).

        Returns:
            ``FileResponse`` (cache mode) or ``Response`` (proxy mode) with file content.

        Raises:
            HTTPException: 404 if antivirus updates are disabled or the file is not found,
                           502 if the upstream request fails,
                           503 if stale ``versions.*`` files could not be evicted.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_antivirus,
            service="Antivirus",
            client_ip=client_ip,
        )

        # Resolve the target URL: use Kerio CDN or the custom URL from settings
        if "bdupdate.kerio.com" in settings.updates.antivirus_url:
            target_host = "bdupdate-cdn.kerio.com"
            target_url = f"{settings.updates.kerio_cdn_url}/{full_path}"
        else:
            target_host = settings.updates.antivirus_url.split("//")[1]
            target_url = f"{settings.updates.antivirus_url}/{full_path}"

        return await self._serve_update_file(
            full_path=full_path,
            target_url=target_url,
            target_host=target_host,
            user_agent="WSLib 1.4 [3, 0, 0, 94]",
            use_cache=settings.updates.antivirus_cache,
            cache_subdir="antivirus_cache",
            version_ttl=settings.updates.antivirus_version_ttl,
        )

    # ------------------------------------------------------------------
    # Antispam
    # ------------------------------------------------------------------

    async def get_antispam_update_file(
        self,
        client_ip: str | None,
        full_path: str,
    ) -> FileResponse | Response:
        """
        Serve an antispam update file from cache or proxy it from upstream.

        Two modes depending on ``settings.updates.antispam_cache``:

        - **Cache mode**: files are stored in ``update_dir/antispam_cache/`` and served
          from disk. ``versions.id`` is re-downloaded when its TTL
          (``settings.updates.antispam_version_ttl``) expires; on expiry all sibling
          ``versions.*`` files are evicted so they are re-fetched on the next request.
          ``versions.dat.gz`` is intentionally skipped to force the client to fall back
          to the uncompressed variant (for consistency).
          All other files are cached on first download and served from disk.
        - **Proxy mode**: every request is forwarded directly to the upstream CDN.

        Args:
            client_ip: Client IP address, used for logging if enabled in settings.
            full_path: Relative path forwarded to upstream
                       (e.g. ``"v2/repository/4/1/C/9/ace.am.41c9d20c61c98415feb47ad9641ef08a.gzip"``).

        Returns:
            ``FileResponse`` (cache mode) or ``Response`` (proxy mode) with file content.

        Raises:
            HTTPException: 404 if antispam updates are disabled or the file is not found,
                           502 if the upstream request fails,
                           503 if stale ``versions.*`` files could not be evicted.
        """
        self._check_update_enabled(
            enabled=settings.updates.update_antispam,
            service="Antispam",
            client_ip=client_ip,
        )
        return await self._serve_update_file(
            full_path=full_path,
            target_url=f"{settings.updates.antispam_url}/{full_path}",
            target_host=settings.updates.antispam_url.split("//")[1],
            user_agent="WSLib 1.4 [3, 0, 0, 317]",
            use_cache=settings.updates.antispam_cache,
            cache_subdir="antispam_cache",
            version_ttl=settings.updates.antispam_version_ttl,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _serve_update_file(
        self,
        full_path: str,
        target_url: str,
        target_host: str,
        user_agent: str,
        use_cache: bool,
        cache_subdir: str,
        version_ttl: int,
    ) -> FileResponse | Response:
        """
        Serve an update file from local cache or proxy it from upstream.

        Two modes depending on ``use_cache``:

        - **Cache mode**: files are stored in ``update_dir/<cache_subdir>/`` and served
          from disk. ``versions.id`` TTL is controlled by ``version_ttl``; on expiry all
          sibling ``versions.*`` files are evicted and re-fetched on their next request.
          ``versions.dat.gz`` is intentionally skipped so the client falls back to the
          uncompressed variant.
        - **Proxy mode**: every request is forwarded directly to upstream.

        Args:
            full_path: Relative path forwarded to upstream (e.g. ``"9.3/versions.avd"``).
            target_url: Full upstream URL for this file.
            target_host: Value for the ``Host`` request header.
            user_agent: Value for the ``User-Agent`` request header.
            use_cache: ``True`` for cache mode, ``False`` for proxy mode.
            cache_subdir: Subdirectory under ``update_dir`` used for caching
                          (e.g. ``"antivirus_cache"``).
            version_ttl: Cache TTL in seconds for ``versions.id``. Use
                         ``settings.updates.antivirus_version_ttl`` for antivirus or
                         ``settings.updates.antispam_version_ttl`` for antispam.

        Returns:
            ``FileResponse`` (cache mode) or ``Response`` (proxy mode) with file content.

        Raises:
            HTTPException: 404 if the file is not found,
                           502 if the upstream request fails,
                           503 if stale ``versions.*`` files could not be evicted.
        """
        request_headers = {
            "User-Agent": user_agent,
            "Host": target_host,
            "Accept": "*/*",
            "Connection": "Keep-Alive",
        }

        file_name = full_path.split("/")[-1]

        # Cache mode: serve files from local disk
        if use_cache:
            cache_dir = ensure_dir(settings.updates.update_dir / cache_subdir)
            file_path = cache_dir / file_name

            if file_name == "versions.id":
                await self._download_versions_id_if_stale(
                    file_path=file_path,
                    cdn_url=target_url,
                    request_headers=request_headers,
                    version_ttl=version_ttl,
                )
            elif file_name == "versions.dat.gz":
                # Skip .gz variant so the client falls back to the uncompressed file
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found",
                )
            elif not file_path.exists():
                await download_file_with_retries(
                    url=target_url,
                    save_path=str(file_path),
                    headers=request_headers,
                    context=f"Downloading Antivirus/Antispam file: {target_url}",
                )

            if not file_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found",
                )
            return FileResponse(file_path)

        # Proxy mode: forward every request directly to update servers
        response = await make_request_with_retries(
            url=target_url,
            headers=request_headers,
            skip_status_codes=[404],
        )
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="All connection attempts failed",
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    def _resolve_enabled_flag(
        self,
        update_type: str,
        version: str | None,
        major_version: int | None,
        client_ip: str | None,
    ) -> bool:
        """
        Resolve whether the given update type/major_version is enabled.

        Args:
            update_type: Update family, e.g. "ids", "geoip", or "snort".
            version: Requested full version, or None for version-less types.
            major_version: Requested major version, or None for version-less types.
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            True if any of the settings flags for this type/version are enabled.

        Raises:
            HTTPException: 404 if the type/version combination is unsupported.
        """
        flags = self._VERSION_ENABLE_FLAGS.get(update_type, {}).get(major_version)

        if flags is None:
            label = self._format_update_label(
                update_type=update_type,
                version=version if version else major_version,
            )
            write_log(
                log_type=["system", "errors"],
                message=f"{label} | Error: Updates for {label} are not available",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Updates for {label} are not available.",
            )

        return any(getattr(settings.updates, flag) for flag in flags)

    @staticmethod
    def _format_update_label(update_type: str, version: int | str | None) -> str:
        """Build a display label like 'GeoIP v4.20260101', 'IDS v5.123' or 'Snort Template' (no version)."""
        if update_type == "snort":
            return "Snort Template"
        if version is None:
            return update_type.capitalize()
        if update_type == "geoip":
            return f"GeoIP v{version}"
        return f"{update_type.upper()} v{version}"

    @staticmethod
    def _check_update_enabled(
        enabled: bool,
        service: str,
        client_ip: str | None,
    ) -> None:
        """Raise HTTP 404 if the given service is disabled."""
        if not enabled:
            write_log(
                log_type=["system", "errors"],
                message=f"{service} | Error: Updates for {service} are disabled",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Updates for {service} are disabled",
            )

    @staticmethod
    def _parse_major_version(version: str, client_ip: str | None) -> int:
        """
        Parse the major version number from a dotted version string.

        Args:
            version: Version string to parse (expected format: ``x.y``).
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Major version number as int (e.g. ``5`` for ``"5.1"``).

        Raises:
            HTTPException: 400 if the version string cannot be parsed.
        """
        try:
            return int(version.split(".")[0])
        except (IndexError, ValueError) as err:
            write_log(
                log_type=["system", "errors"],
                message=f"Version parse error for '{version}': {err}",
                ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid version format '{version}': {err}. Expected format: x.y",
            )

    def _parse_type_and_version_from_filename(
        self,
        file_name: str,
        client_ip: str | None,
    ) -> ParsedFileName:
        """
        Parse the type and major version number from a file name that
        encodes them (e.g. "geoip_4_20260803.gz").

        Args:
            file_name: File name to extract the type/version from (expected
                format: ``type_x_rest.ext``). Special case: "snort.tpl" /
                "snort.tpl.md5" have no numeric version and return "snort".
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            ParsedFileName with keys "type" (str) and "version" (int or None), e.g.
            {"type": "geoip", "version": 4} or {"type": "snort", "version": None}.

        Raises:
            HTTPException: 400 if the file name cannot be parsed.
        """
        if self._SNORT_FILENAME_RE.match(file_name):
            return {"type": "snort", "version": None}

        match = self._VERSION_FROM_FILENAME_RE.match(file_name)
        if match:
            return {"type": match.group(1), "version": int(match.group(2))}

        write_log(
            log_type=["system", "errors"],
            message=f"Version parse error: could not extract type/version from file_name '{file_name}'",
            ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Could not extract type/version from file name '{file_name}'. "
                "Expected format: type_x_rest.ext"
            ),
        )

    @staticmethod
    def _make_update_response(major_version: int, url_prefix: str, label: str) -> str:
        """
        Get update version from settings and format the response string.

        The response format is expected by the Kerio Control update client::

            0:<version>.<build>
            full:<download_url>

        Used by both IDS/IPS and GeoIP update handlers.

        Args:
            major_version: Major version number to query (e.g. ``5``).
            url_prefix: URL path segment and database key prefix (``"ids"`` or ``"geoip"``).
            label: Human-readable label for log messages (e.g. ``"IDS v5"``).

        Returns:
            Formatted update response with version and download URL.

        Raises:
            HTTPException: 404 if no version is stored in settings,
                           500 on unexpected errors.
        """
        # Get current update version from settings based on incoming version
        update_version = getattr(
            settings.updates, f"{url_prefix}_{major_version}_version"
        )
        ext = ".tar.gz" if url_prefix == "geoip" and major_version == 5 else ".gz"
        file_name = f"{url_prefix}_{major_version}_{update_version}{ext}"

        if update_version is None:
            write_log(
                log_type=["system"],
                message=(
                    f"{label} | Update version not found in settings. "
                    "Run a manual mirror update or wait for the scheduled update."
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Update file not found",
            )

        return (
            f"0:{major_version}.{update_version}\n"
            f"full:http://kerio-updates-mirror.local/api/kerio/updates"
            f"/{url_prefix}/files/{file_name}"
        )

    async def _make_antivirus_update_response(
        self,
        version: str,
        client_ip: str | None,
    ) -> str:
        """
        Build the antivirus update response string for Kerio Control.

        Decision tree:

        - ``antivirus_url`` points to ``bdupdate.kerio.com``:

          - License is required; raises 403 if missing.
          - CDN URL is fetched and cached via ``_get_kerio_cdn_cached`` **always**,
            because ``get_antivirus_update_file`` uses ``kerio_cdn_url`` to build
            the target URL even when files are served through the local mirror.
          - ``antivirus_through_mirror=True`` → return the local mirror URL.
          - ``antivirus_through_mirror=False`` → return the real CDN URL directly.

        - ``antivirus_url`` is a custom URL (no CDN lookup needed):

          - ``antivirus_through_mirror=True`` → return the local mirror URL.
          - ``antivirus_through_mirror=False`` → return ``antivirus_url`` as-is.

        Args:
            version: Full version string forwarded to the CDN request (e.g. "9.3").
            client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
            Update response string in the format expected by Kerio Control.

        Raises:
            HTTPException: 403 if the Kerio CDN is selected and the license number
                           is missing or invalid.
        """
        # When antivirus_url points to Kerio CDN, the real CDN URL must be fetched
        # and cached regardless of mirror mode - get_antivirus_update_file uses
        # kerio_cdn_url to build target_url even when serving files through the mirror.
        if "bdupdate.kerio.com" in settings.updates.antivirus_url:
            if not settings.updates.license_number:
                write_log(
                    log_type=["system"],
                    message="Antivirus | Error: License number is missing",
                    ip=client_ip,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="License number is missing",
                )
            kerio_cdn = await self._get_kerio_cdn_cached(version)
            direct_url = f"THDdir={kerio_cdn or settings.updates.kerio_cdn_url}"
        else:
            # Custom upstream URL - no CDN lookup needed
            direct_url = f"THDdir={settings.updates.antivirus_url}"

        if settings.updates.antivirus_through_mirror:
            return "THDdir=http://kerio-updates-mirror.local/api/kerio/updates/antivirus/files"

        return direct_url

    async def _get_kerio_cdn_cached(self, version: str) -> str | None:
        """
        Return a cached Kerio CDN URL, refreshing it if the TTL has expired.

        File (``update_files/kerio_cdn.cache``) mtime is used as the cache timestamp, so
        the TTL is shared across all worker processes without inter-process communication.

        Args:
            version: Version string forwarded to ``_get_kerio_cdn`` on a cache miss.

        Returns:
            Cached or freshly fetched CDN URL, or ``None`` if the request failed.
        """
        ttl = settings.updates.kerio_cdn_url_cache_ttl
        update_dir = ensure_dir(settings.updates.update_dir)
        cdn_cache_file = update_dir / "kerio_cdn.cache"

        if cdn_cache_file.exists():
            age = time.time() - cdn_cache_file.stat().st_mtime
            if age < ttl:
                return settings.updates.kerio_cdn_url

        result = await self._get_kerio_cdn(version)
        if result:
            cdn_cache_file.write_text(str(time.time()))

        return result

    @staticmethod
    async def _get_kerio_cdn(version: str) -> str | None:
        """
        Fetch the current antivirus CDN URL from the Kerio update server.

        On a successful response, updates ``settings.updates.kerio_cdn_url`` in place.
        On a license error, clears ``settings.updates.license_number`` and raises 403.

        Args:
            version: Full client version string sent as a query parameter (e.g. "9.3").

        Returns:
            CDN base URL string, or ``None`` on a network failure.

        Raises:
            HTTPException: 403 if the license is invalid or expired.
        """
        url = "https://bdupdate.kerio.com/update.php"
        params = {
            "id": settings.updates.license_number,
            "product": "KWF",
            "version": version,
        }
        headers = {
            "accept": "*/*",
            "host": "bdupdate.kerio.com",
            "user-agent": "Kerio Updater",
        }

        response = await make_request_with_retries(
            url=url,
            params=params,
            headers=headers,
            context="get Kerio CDN URL",
        )

        if not response:
            write_log(
                log_type=["system"],
                message="Antivirus | Error: Failed to get Kerio CDN URL",
            )
            return None

        license_number = settings.updates.license_number

        if "Invalid product license" in response.text:
            write_log(
                log_type=["system"],
                message=f"Antivirus | Error: Invalid product license: {license_number}, removing from settings",
            )
            settings.update("updates.license_number", None)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid product license: {license_number}",
            )

        if "Product Software Maintenance expired" in response.text:
            write_log(
                log_type=["system"],
                message=f"Antivirus | Error: License key expired: {license_number}, removing from settings",
            )
            settings.update("updates.license_number", None)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"License key expired: {license_number}",
            )

        kerio_cdn_url = response.text.replace("THDdir=", "").strip()
        settings.update("updates.kerio_cdn_url", kerio_cdn_url)

        return kerio_cdn_url

    @staticmethod
    async def _get_shieldmatrix_version_cached(headers: dict) -> str | None:
        """
        Return the current ShieldMatrix version, refreshing it when TTL expires.

        The version is stored as plain text in ``matrix_cache/shieldmatrix_version.cache``.
        File mtime is used as the cache timestamp, so the TTL is shared across all
        worker processes without inter-process communication.

        When a newer version is detected, the ipv4 and ipv6 cache directories are
        purged so their files are re-downloaded on the next request.

        Args:
            headers: HTTP headers to use for the upstream request.

        Returns:
            Version string (e.g. ``"20240510"``), or ``None`` on a network failure.
        """
        ttl = settings.updates.shieldmatrix_version_ttl
        cache_dir = ensure_dir(settings.updates.update_dir / "matrix_cache")
        version_cache_file = cache_dir / "shieldmatrix_version.cache"

        # Fast path: cache file is fresh - serve from disk without a network request
        if (
            version_cache_file.exists()
            and (time.time() - version_cache_file.stat().st_mtime) < ttl
        ):
            return version_cache_file.read_text().strip()

        response = await make_request_with_retries(
            url=settings.updates.shieldmatrix_url.rstrip("/") + "/version",
            headers=headers,
            context="get ShieldMatrix version",
        )

        if not response:
            write_log(
                log_type=["system"],
                message="ShieldMatrix | Error: Failed to fetch version from upstream",
            )
            return None

        new_version = response.text.strip()

        # Purge ipv4/ipv6 cache when a newer version is detected
        if version_cache_file.exists():
            cached_version = version_cache_file.read_text().strip()
            if new_version > cached_version:
                for proto in ("ipv4", "ipv6"):
                    proto_dir = ensure_dir(
                        settings.updates.update_dir / "matrix_cache" / proto
                    )
                    clean_directory(proto_dir)

        # Write the new version; file mtime becomes the new TTL anchor
        version_cache_file.write_text(new_version)

        return new_version

    @staticmethod
    async def _download_versions_id_if_stale(
        file_path: Path,
        cdn_url: str,
        request_headers: dict,
        version_ttl: int,
    ) -> None:
        """
        Download ``versions.id`` only if it is missing or its TTL has expired.

        Uses file mtime as the cache timestamp, which is visible to all worker
        processes - no in-process state or inter-process communication needed.

        On TTL expiry, all ``versions.*`` files in the same directory are deleted
        before the fresh ``versions.id`` is downloaded. This ensures sibling files
        (``versions.sig``, ``versions.dat``, etc.) are re-fetched on their next
        request via the standard "file missing → download" path.

        On Windows, a file held open by another process cannot be deleted.
        In that case HTTP 503 is raised so the client retries; the file mtime
        is not updated, so the next request will re-attempt eviction.

        Args:
            file_path: Local path where ``versions.id`` should be stored.
            cdn_url: Full CDN URL to download ``versions.id`` from.
            request_headers: HTTP headers to send with the download request.
            version_ttl: Cache TTL in seconds. Use ``settings.updates.antivirus_version_ttl``
                         for antivirus or ``settings.updates.antispam_version_ttl``
                         for antispam.

        Raises:
            HTTPException: 503 if stale ``versions.*`` files could not be evicted.
        """
        # Fast path: file exists and TTL has not expired yet
        if (
            file_path.exists()
            and (time.time() - file_path.stat().st_mtime) < version_ttl
        ):
            return

        # Evict all versions.* siblings before downloading the fresh file
        for stale_file in file_path.parent.glob("versions.*"):
            try:
                stale_file.unlink()
            except (PermissionError, OSError):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to evict stale versions files, retry later",
                )

        await download_file_with_retries(
            url=cdn_url,
            save_path=str(file_path),
            headers=request_headers,
            context=f"Downloading Antivirus/Antispam file: {cdn_url}",
        )

    @staticmethod
    async def _fetch_captcha(content_type: str) -> str:
        """
        Download captcha from kerio.com and cache it locally.

        Args:
            content_type: Content-Type header value forwarded from the original request.

        Returns:
            Captcha file content as string, or empty string if download failed
            or response is too short.

        Raises:
            HTTPException: 502 if all connection attempts failed.
        """
        write_log(
            log_type=["system"],
            message="Registration | Captcha file is missing or "
            "corrupted, trying to download from kerio.com",
        )
        response = await make_request_with_retries(
            url="https://register.kerio.com/registration/LD.php",
            method="POST",
            files={
                "command": (None, "connect"),
                "host_id": (None, ":".join(f"{randint(0, 255):02X}" for _ in range(6))),
                "product_code": (None, "KWF"),
                "type": (None, "image/png"),
                "protocol_version": (None, "21"),
                "lang_id": (None, ""),
                "show_image": (None, "0"),
                "product_version": (None, "0.0.0..0"),
            },
            headers={
                "User-Agent": "Kerio License Downloader (LicenseManager)",
                "Accept": "*/*",
                "Content-Type": content_type,
            },
        )
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="All connection attempts failed",
            )

        captcha_data = (
            response.text
            if response.status_code == 200 and len(response.text) > 1000
            else ""
        )

        if captcha_data:
            try:
                (settings.updates.update_dir / "security_image").write_text(
                    captcha_data, encoding="utf-8"
                )
            except OSError as e:
                write_log(
                    log_type=["system"],
                    message=f"Registration | Failed to save captcha: {e}",
                )

        return captcha_data

    @staticmethod
    def _make_registration_connect_response(captcha_data: str) -> Response:
        """Build HTTP response with captcha data or internal error response.

        Args:
            captcha_data: Captcha file content. Empty string if unavailable.

        Returns:
            Response with captcha content and Kerio headers on success,
            or empty response with error headers if captcha is unavailable.
        """
        if captcha_data:
            return Response(
                content=captcha_data,
                status_code=200,
                headers={
                    "X-Kerio-Token": "ac561fb1a7c3627c62f561db9bdebba8",
                    "X-Kerio-Reply-Code": "200",
                    "X-Kerio-Reply-Message": "OK",
                    "Content-Type": "application/x-kerio-signed-png",
                },
            )

        write_log(
            log_type=["system"],
            message="Registration | Captcha unavailable",
        )
        return Response(
            content="",
            status_code=200,
            headers={
                "X-Kerio-Token": "",
                "X-Kerio-Reply-Code": "500",
                "X-Kerio-Reply-Message": "Internal Server Error",
            },
        )

    @staticmethod
    def _get_expiry_date() -> str:
        """Return expiry date (30 days from now) in ISO format (YYYY-MM-DD)."""
        now = datetime.now(timezone.utc)
        return (now + timedelta(days=30)).strftime("%Y-%m-%d")

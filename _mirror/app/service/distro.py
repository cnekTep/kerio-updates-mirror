import json
import re
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils
from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.config import settings
from app.utils.app_logging import log_event
from app.utils.file_utils import ensure_dir, build_file_response

_FILENAME_PATTERN = re.compile(
    r"^kerio-(?:control-upgrade|connect)"  # product name (add more if needed)
    r"-(\d+\.\d+\.\d+-\d+)"  # version-build, e.g. 10.0.9-10320
    r"(?:-[a-zA-Z0-9]+)*"  # optional suffixes like linux, win64, etc.
    r"\.(?:deb|img|exe)$"  # allowed extensions
)
_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9_.\-]+")

# Map file extensions to distro types
_DISTRO_TYPE_BY_EXTENSION: dict[str, str] = {
    ".img": "control",
    ".exe": "connect_win",
    ".deb": "connect_deb",
}

# Read/hash the upload in fixed-size chunks instead of loading it fully into
# memory - distro images can be several hundred MB.
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB

# Sent when updates are disabled, the caller isn't Kerio Control, or the
# client is already on the latest version.
NO_UPDATE_RESPONSE = "--INFO--\nReminderId='1'\nReminderAuth='1'\nVersion='0'"


class DistroService:
    """
    Service layer for Kerio Control distribution (firmware image) operations.

    Handles uploading and signing distribution images, listing available
    distributions, serving them for download, and answering version-check
    requests coming from Kerio Control appliances.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def upload_distro_file(self, file: UploadFile) -> tuple[str, str]:
        """
        Validate, store and sign an uploaded Kerio Control/Connect distribution file.

        Args:
            file: Uploaded distribution image: ``kerio-control-upgrade-{version}.img``,
                ``kerio-connect-{version}.exe`` or ``kerio-connect-{version}.deb``

        Returns:
            tuple[str, str]: The filename of the uploaded and signed
                distribution file, and the distro type it was recognized as.

        Raises:
            HTTPException: 400 if the filename format is invalid, 500 on any
                other failure (disk error, signing-key issue, etc.).
        """
        try:
            filename, distro_type = await self._store_and_sign_file(file=file)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except Exception as exc:
            log_event(
                log_type=["system", "errors"],
                message=f"Distro Update | Error: Upload failed: {exc}",
                notify=True,
                action_name="Distributive Upload",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

        log_event(
            log_type=["system"],
            message=f"Distro Update | File uploaded and signed: {filename}",
        )
        return filename, distro_type

    @staticmethod
    def list_distros(distro_type: str) -> list[str]:
        """
        List uploaded distribution files that have a matching ``.sig`` file,
        filtered by distribution type.

        Args:
            distro_type: One of "control", "connect_win", "connect_deb".

        Returns:
            Sorted list of distribution filenames.
        """
        # Map distro type to (prefix, suffix) filter rules
        type_rules = {
            "control": ("kerio-control-upgrade", ".img"),
            "connect_win": ("kerio-connect", ".exe"),
            "connect_deb": ("kerio-connect", ".deb"),
        }

        if distro_type not in type_rules:
            return []

        prefix, suffix = type_rules[distro_type]

        distro_dir = settings.updates.update_dir / "distros"
        try:
            entries = [p for p in distro_dir.iterdir() if p.is_file()]
        except FileNotFoundError:
            return []

        names = {p.name for p in entries}
        matched_files = [
            name for name in names if name.startswith(prefix) and name.endswith(suffix)
        ]
        return sorted(name for name in matched_files if f"{name}.sig" in names)

    @staticmethod
    def extract_version(filename: str) -> str | None:
        """
        Extract the Kerio Control/Connect version from a distribution filename.

        Args:
            filename: Sanitized distribution filename.

        Returns:
            Version string (e.g. ``"9.5.0-9017"``) if the filename matches, ``None`` otherwise.
        """
        match = _FILENAME_PATTERN.match(filename)
        return match.group(1) if match else None

    async def get_distro_update_info(
        self,
        prod_code: str,
        prod_major: int | None,
        prod_minor: int | None,
        prod_build: int | None,
        prod_build_number: int | None,
        os_platform: str | None,
        installation_type: str | None,
        client_ip: str | None,
    ) -> str:
        """
        Handle a Kerio Control/Connect version-check callback end to end.

        Applies the update kill switch for the product identified by
        ``prod_code``, resolves the target platform variant (Kerio Connect
        only - Windows or Linux/deb), validates that version fields are
        present, logs the check, and returns a reminder-protocol response
        comparing the client's version against the configured target version.

        Args:
            prod_code: Client-reported product code (``"KWF"`` for Kerio
                Control, ``"KMS"`` for Kerio Connect); anything else gets a
                "no update" reply.
            prod_major: Client-reported major version.
            prod_minor: Client-reported minor version.
            prod_build: Client-reported build/patch number.
            prod_build_number: Client-reported internal build number.
            os_platform: Client-reported platform (only relevant for Kerio
                Connect, e.g. ``"WIN64.64"``, ``"LINUX.X64"``).
            installation_type: Client-reported installation type (only relevant
                for Kerio Connect on Linux, expected to be ``"deb"``).
            client_ip: Client IP address, used for logging only.

        Returns:
            Plain-text response in the Kerio reminder-protocol format.
        """
        if prod_code == "KWF":
            enabled = settings.updates.update_kerio_control_distro
            update_file = settings.updates.kerio_control_update_file
            versions_file = settings.updates.kerio_control_distro_versions_file
            build_number_variant = None
            update_version = settings.updates.kerio_control_update_version
            product_label = "Kerio Control"
            info_url = "https://support.keriocontrol.gfi.com"
        elif prod_code == "KMS":
            # Kerio Connect ships for multiple platforms, but only two are
            # actually supported here: Windows, and Linux via a .deb package.
            # Anything else (macOS, other Linux packaging, unrecognized
            # platform strings) is treated as unsupported.
            if os_platform == "WIN64.64":
                update_file = settings.updates.kerio_connect_update_file_win
                update_version = settings.updates.kerio_connect_update_version_win
                build_number_variant = "win"
            elif os_platform == "LINUX.X64" and installation_type == "deb":
                update_file = settings.updates.kerio_connect_update_file_deb
                update_version = settings.updates.kerio_connect_update_version_deb
                build_number_variant = "deb"
            else:
                log_event(
                    log_type=["system", "connections", "errors"],
                    message=(
                        f"Distro | Update check received (KMS): unsupported platform "
                        f"os_platform={os_platform!r} installation_type={installation_type!r}"
                    ),
                    ip=client_ip,
                    notify=True,
                    action_name="Distributive Update",
                )
                return NO_UPDATE_RESPONSE

            enabled = settings.updates.update_kerio_connect_distro
            versions_file = settings.updates.kerio_connect_distro_versions_file
            product_label = "Kerio Connect"
            info_url = "https://support.kerioconnect.gfi.com"
        else:
            log_event(
                log_type=["system", "connections", "errors"],
                message=f"Distro | Update check received: unknown product code {prod_code!r}",
                ip=client_ip,
                notify=True,
                action_name="Distributive Update",
            )
            return NO_UPDATE_RESPONSE

        if not enabled:
            log_event(
                log_type=["system", "connections"],
                message=f"Distro | Update disabled ({prod_code})",
                ip=client_ip,
            )
            return NO_UPDATE_RESPONSE

        if None in (prod_major, prod_minor, prod_build, prod_build_number):
            log_event(
                log_type=["system", "connections", "errors"],
                message=f"Distro | Update check received ({prod_code}): missing version fields - "
                f"{prod_major}.{prod_minor}.{prod_build} (build number: {prod_build_number})",
                ip=client_ip,
                notify=True,
                action_name="Distributive Update",
            )
            return NO_UPDATE_RESPONSE

        log_event(
            log_type=["system", "connections"],
            message=(
                f"Distro | Update check received ({prod_code}): "
                f"v{prod_major}.{prod_minor}.{prod_build} (build number: {prod_build_number})"
            ),
            ip=client_ip,
        )

        try:
            update_info = self._get_target_update_info(
                versions_file=versions_file,
                update_version=update_version,
                product_label=product_label,
                build_number_variant=build_number_variant,
            )
        except RuntimeError as exc:
            log_event(
                log_type=["system", "errors"],
                message=f"Distro Update | Error: Failed to parse version from config ({prod_code}): {exc}",
                ip=client_ip,
                notify=True,
                action_name="Distributive Update",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

        current_version = (prod_major, prod_minor, prod_build, prod_build_number)
        available_version = (
            int(update_info["prod_major"]),
            int(update_info["prod_minor"]),
            int(update_info["prod_build"]),
            int(update_info["prod_build_number"]),
        )
        if current_version >= available_version:
            return NO_UPDATE_RESPONSE

        package_code = (
            f"{prod_code}:{update_info['prod_major'].zfill(3)}."
            f"{update_info['prod_minor'].zfill(3)}."
            f"{update_info['prod_build'].zfill(5)}.T.000.000"
        )
        base_url = "http://kerio-updates-mirror.local/api/kerio/updates/distro/files"
        download_url = f"{base_url}/{update_file}"

        return (
            "--INFO--\n"
            "ReminderId='1'\n"
            "ReminderAuth='1'\n"
            "Version='1'\n"
            "LicenseUsageReceived='1'\n"
            "--VERSION_BEGIN--\n"
            f"PackageCode='{package_code}'\n"
            f"Description='{update_info['description']}'\n"
            f"Comment='{update_info['description']}'\n"
            f"DownloadURL='{download_url}'\n"
            "DownloadURLtext='Download from here!'\n"
            f"InfoURL='{info_url}'\n"
            "InfoURLtext='View more information!'\n"
            "--VERSION_END--"
        )

    @staticmethod
    def get_distro_file(
        file_name: str,
        client_ip: str | None,
    ) -> Response | FileResponse:
        """
        Validate a requested distro file name and serve it from disk.

        Args:
                file_name: Requested file name (``*.deb, *.exe, *.img`` or ``*.sig``).
                client_ip: Client IP address, used for logging if enabled in settings.

        Returns:
                FileResponse with the requested file content.

        Raises:
                HTTPException: 400 if the file name has an unexpected format or
                        resolves outside the distro directory, 404 if it doesn't exist.
        """

        if not re.fullmatch(
            pattern=r"[A-Za-z0-9.\-]+\.(deb|exe|img|sig)",
            string=file_name,
            flags=re.IGNORECASE,
        ):
            log_event(
                log_type=["system", "errors"],
                message=f"Invalid distro file_name format: '{file_name}'",
                ip=client_ip,
                notify=True,
                action_name="Distributive Update",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name"
            )

        distro_dir = (settings.updates.update_dir / "distros").resolve()
        file_path = (distro_dir / file_name).resolve()

        # Defense in depth: the regex above already rejects "/" and "..", and
        # resolving both paths also guards against symlinks pointing outside
        # distro_dir.
        if not file_path.is_relative_to(distro_dir):
            log_event(
                log_type=["system", "errors"],
                message=f"Resolved path escapes distro dir for file_name '{file_name}'",
                ip=client_ip,
                notify=True,
                action_name="Distributive Update",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name"
            )

        if not file_path.is_file():
            log_event(
                log_type=["system", "errors"],
                message=f"Distro update file not found: '{file_path}'",
                ip=client_ip,
                notify=True,
                action_name="Distributive Update",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Update file not found"
            )

        return build_file_response(file_path=file_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    async def _store_and_sign_file(self, file: UploadFile) -> tuple[str, str]:
        """
        Stream an uploaded distro file to disk and sign it.

        The upload is streamed to a temporary file while a SHA-256 digest is
        computed on the fly, so the whole image is never held in memory at
        once. The temp file is only published under its final name (and the
        detached signature only written) once signing succeeds, so a failed
        or interrupted upload never leaves a servable-but-unsigned image
        behind.

        Args:
            file: Uploaded distribution image.

        Returns:
            The stored (sanitized) filename, and the distro type it belongs to.

        Raises:
            ValueError: If the filename does not match the expected format.
        """
        filename = self._secure_filename(file.filename or "")
        version = self.extract_version(filename=filename)
        if version is None:
            raise ValueError("Invalid filename format")

        distro_type = _DISTRO_TYPE_BY_EXTENSION[Path(filename).suffix]
        distro_dir = ensure_dir(settings.updates.update_dir / "distros")
        file_path = distro_dir / filename
        temp_path = file_path.with_name(file_path.name + ".tmp")

        try:
            digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
            with open(temp_path, "wb") as out_file:
                while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
                    out_file.write(chunk)
                    digest.update(chunk)

            signature = self._sign_digest(digest=digest.finalize())

            temp_path.replace(file_path)  # Atomic publish, only after a full read
            file_path.with_name(file_path.name + ".sig").write_bytes(signature)
        finally:
            if temp_path.exists():
                temp_path.unlink()

        return filename, distro_type

    @staticmethod
    def _secure_filename(filename: str) -> str:
        """
        Strip any path components and unsafe characters from a client-supplied filename.

        Args:
            filename: Raw filename as received from the client.

        Returns:
            A sanitized, path-safe filename.
        """
        basename = Path(filename).name
        return _SAFE_FILENAME_PATTERN.sub("_", basename)

    @staticmethod
    def _sign_digest(digest: bytes) -> bytes:
        """
        Sign a pre-computed SHA-256 digest with the distro signing key.

        Signing a digest (rather than re-reading the whole file) avoids a
        second full pass over a potentially large image.

        Args:
            digest: SHA-256 digest of the file to sign.

        Returns:
            Detached PKCS#1 v1.5 signature bytes.
        """
        with open("certs/key.pem", "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                data=key_file.read(), password=None, backend=default_backend()
            )

        return private_key.sign(
            digest, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256())
        )

    @staticmethod
    def _get_target_update_info(
        versions_file: str,
        update_version: str,
        product_label: str,
        build_number_variant: str | None = None,
    ) -> dict[str, str]:
        """
        Resolve the configured target distro version into a version-info dict.

        Looks up ``update_version`` in the version mapping file. Falls back
        to parsing the version string directly (e.g. ``"9.5.0-8778"``) when
        it is not present in the mapping.

        Args:
            versions_file: Path to the product's version mapping JSON file.
            update_version: The configured target version string.
            product_label: Product name used in the description when
                falling back to parsing (e.g. "Kerio Control").
            build_number_variant: Platform variant whose build number to
                use - ``"win"`` or ``"deb"`` for Kerio Connect (mapping
                entries always carry both ``prod_build_number_win`` and
                ``prod_build_number_deb``), or ``None`` for products
                without a platform split (Kerio Control, which uses a
                plain ``prod_build_number``).

        Returns:
            Dict with ``prod_major``, ``prod_minor``, ``prod_build``,
            ``prod_build_number`` and ``description`` keys.

        Raises:
            RuntimeError: If the version string cannot be parsed and there
                is no mapping data available for it.
            KeyError: If the mapping entry is missing the expected
                ``prod_build_number`` key for the given variant.
        """

        # Load version mapping
        with open(versions_file, encoding="utf-8") as f:
            mapping = json.load(f)

        # Get update info from mapping or parse from version string
        if update_version in mapping:
            entry = mapping[update_version]
            build_number_key = (
                f"prod_build_number_{build_number_variant}"
                if build_number_variant is not None
                else "prod_build_number"
            )
            return {
                "prod_major": entry["prod_major"],
                "prod_minor": entry["prod_minor"],
                "prod_build": entry["prod_build"],
                "prod_build_number": entry[build_number_key],
                "description": entry["description"],
            }

        try:
            version_part, build_part = update_version.split("-")
            major, minor, build = version_part.split(".")
        except Exception as exc:
            raise RuntimeError(
                f"parse version {update_version!r} and no mapping data available"
            ) from exc

        return {
            "prod_major": major,
            "prod_minor": minor,
            "prod_build": build,
            "prod_build_number": "99999",  # Default when parsing from string
            "description": f"{product_label} {version_part} ({build_part})",
        }

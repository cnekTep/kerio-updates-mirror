import json
import re
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils
from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.utils.app_logging import write_log
from app.utils.file_utils import ensure_dir

# Expected filename format: kerio-control-upgrade-{version}.img
_FILENAME_PATTERN = re.compile(r"^kerio-control-upgrade-(\d+\.\d+\.\d+-\d+).*\.img$")
_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9_.\-]+")

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
    async def upload_distro_file(self, file: UploadFile) -> str:
        """
        Validate, store and sign an uploaded Kerio Control distribution file.

        Args:
            file: Uploaded distribution image (``kerio-control-upgrade-{version}.img``).

        Returns:
            str: The filename of the uploaded and signed distribution file.

        Raises:
            HTTPException: 400 if the filename format is invalid, 500 on any
                other failure (disk error, signing-key issue, etc.).
        """
        try:
            filename = await self._store_and_sign_file(file=file)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except Exception as exc:
            write_log(
                log_type=["system", "errors"],
                message=f"Distro Update | Error: Upload failed: {exc}",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

        write_log(
            log_type=["system"],
            message=f"Distro Update | File uploaded and signed: {filename}",
        )
        return filename

    @staticmethod
    def list_distros() -> list[str]:
        """
        List uploaded distribution files that have a matching ``.sig`` file.

        Returns:
            Sorted list of distribution filenames.
        """
        distro_dir = settings.updates.update_dir / "distros"

        try:
            entries = [p for p in distro_dir.iterdir() if p.is_file()]
        except FileNotFoundError:
            return []

        names = {p.name for p in entries}
        img_files = [name for name in names if name.endswith(".img")]
        return sorted(name for name in img_files if f"{name}.sig" in names)

    @staticmethod
    def extract_version(filename: str) -> str | None:
        """
        Extract the Kerio Control version from a distribution filename.

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
        client_ip: str | None,
    ) -> str:
        """
        Handle a Kerio Control version-check callback end to end.

        Applies the update kill switch and the ``prod_code == "KWF"`` gate,
        validates that version fields are present, logs the check, and
        returns a Kerio Control reminder-protocol response comparing the
        client's version against the configured target version.

        Args:
            prod_code: Client-reported product code; only ``"KWF"`` (Kerio
                Control) is handled, everything else gets a "no update" reply.
            prod_major: Client-reported major version.
            prod_minor: Client-reported minor version.
            prod_build: Client-reported build/patch number.
            prod_build_number: Client-reported internal build number.
            client_ip: Client IP address, used for logging only.

        Returns:
            Plain-text response in the Kerio Control reminder protocol format.
        """
        if not settings.updates.update_kerio_control_distro:
            write_log(
                log_type=["system", "connections"],
                message="Distro | Update disabled",
                ip=client_ip,
            )
            return NO_UPDATE_RESPONSE

        if prod_code != "KWF":
            write_log(
                log_type=["system", "connections"],
                message="Distro | Update check received: non-Kerio Control product",
                ip=client_ip,
            )
            return NO_UPDATE_RESPONSE

        if None in (prod_major, prod_minor, prod_build, prod_build_number):
            write_log(
                log_type=["system", "connections"],
                message="Distro | Update check received: missing version fields - "
                f"{prod_major}.{prod_minor}.{prod_build} (build number: {prod_build_number})",
                ip=client_ip,
            )
            return NO_UPDATE_RESPONSE

        write_log(
            log_type=["system", "connections"],
            message=(
                f"Distro | Update check received: v{prod_major}.{prod_minor}.{prod_build} "
                f"(build number: {prod_build_number})"
            ),
            ip=client_ip,
        )

        try:
            update_info = self._get_target_update_info()
        except RuntimeError as exc:
            write_log(
                log_type=["system", "errors"],
                message=f"Distro Update | Error: Failed to parse version from config: {exc}",
                ip=client_ip,
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
            f"KWF:{update_info['prod_major'].zfill(3)}."
            f"{update_info['prod_minor'].zfill(3)}."
            f"{update_info['prod_build'].zfill(5)}.T.000.000"
        )
        base_url = "http://kerio-updates-mirror.local/api/kerio/updates/distro/files"
        download_url = f"{base_url}/{settings.updates.kerio_control_update_file}"

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
            "InfoURL='https://support.keriocontrol.gfi.com'\n"
            "InfoURLtext='View more information!'\n"
            "--VERSION_END--"
        )

    @staticmethod
    def validate_and_get_file_path(file_name: str) -> Path:
        """
        Validate a requested distro file name and resolve its path on disk.

        Args:
            file_name: Requested file name (``*.img`` or ``*.sig``).

        Returns:
            Absolute path to the file on disk.

        Raises:
            HTTPException: 400 if the file name has an unexpected format or
                resolves outside the distro directory, 404 if it doesn't exist.
        """
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.(img|sig)", file_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name"
            )

        distro_dir = (settings.updates.update_dir / "distros").resolve()
        file_path = (distro_dir / file_name).resolve()

        # Defense in depth: the regex above already rejects "/" and "..", and
        # resolving both paths also guards against symlinks pointing outside
        # distro_dir.
        if not file_path.is_relative_to(distro_dir):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name"
            )

        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Update file not found"
            )

        return file_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    async def _store_and_sign_file(self, file: UploadFile) -> str:
        """
        Stream an uploaded distro file to disk and sign it.

        The upload is streamed to a temporary file while a SHA-256 digest is
        computed on the fly, so the whole image is never held in memory at
        once. The temp file is only published under its final name (and the
        detached signature only written) once signing succeeds, so a failed
        or interrupted upload never leaves a servable-but-unsigned image
        behind (``list_distros`` only returns ``.img`` files with a matching
        ``.sig``).

        Args:
            file: Uploaded distribution image.

        Returns:
            The stored (sanitized) filename.

        Raises:
            ValueError: If the filename does not match the expected format.
        """
        filename = self._secure_filename(file.filename or "")
        version = self.extract_version(filename=filename)
        if version is None:
            raise ValueError("Invalid filename format")

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

        return filename

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
    def _get_target_update_info() -> dict[str, str]:
        """
        Resolve the configured target distro version into a version-info dict.

        Looks up ``settings.updates.distro_update_version`` in the version
        mapping file. Falls back to parsing the version string directly
        (e.g. ``"9.5.0-8778"``) when it is not present in the mapping.

        Returns:
            Dict with ``prod_major``, ``prod_minor``, ``prod_build``,
            ``prod_build_number`` and ``description`` keys.

        Raises:
            RuntimeError: If the version string cannot be parsed and there is
                no mapping data available for it.
        """

        # Load version mapping
        with open(
            settings.updates.kerio_control_distro_versions_file, encoding="utf-8"
        ) as f:
            mapping = json.load(f)

        # Get update info from mapping or parse from version string
        update_version = settings.updates.kerio_control_update_version
        if update_version in mapping:
            return mapping[update_version]

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
            "description": f"Kerio Control {version_part} ({build_part})",
        }

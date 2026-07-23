import gzip
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.service.geoip import GeoIPService
from app.service.ids import IDSService
from app.service.kerio_update import KerioUpdateService
from app.service.web_filter import WebFilterService
from app.utils.app_logging import write_log
from app.utils.file_utils import clean_directory


@dataclass
class MirrorUpdateService:
    """
    Service for handling Mirror update requests.
    """

    geoip_service: GeoIPService
    ids_service: IDSService
    kerio_update_service: KerioUpdateService
    web_filter_service: WebFilterService

    async def full_mirror_update(self, scheduled: bool = False) -> None:
        # Reload config before update
        settings.reload()

        # Archive oversized log files before starting the update
        self._archive_logs()

        write_log(log_type="updates", message="", date=False)
        write_log(
            log_type=["updates"],
            message="----------------------------------------------------------------",
        )
        write_log(
            log_type=["system", "updates"],
            message=(
                "Scheduled Mirror update process started"
                if scheduled
                else "Manual Mirror update process started"
            ),
        )
        write_log(
            log_type=["updates"],
            message=f"Using license key: {settings.updates.license_number}",
        )
        write_log(
            log_type=["updates"],
            message="----------------------------------------------------------------",
        )

        if settings.updates.update_web_filter_key:  # Update Web Filter key
            await self.web_filter_service.update_web_filter_key()

        if settings.updates.update_ids_3:  # IPS/IDS Snort (Kerio Control < 9.5)
            await self.ids_service.download_ids_update_files(version="3")

        if settings.updates.update_ids_5:  # IPS/IDS Snort (Kerio Control >= 9.5)
            await self.ids_service.download_ids_update_files(version="5")
            if settings.updates.update_snort_template:
                await self.ids_service.download_snort_template()

        if (
            settings.updates.update_ids_3 or settings.updates.update_ids_5
        ):  # Lists of compromised addresses for blocking
            await self.ids_service.download_ids_update_files(version="2")

        if settings.updates.update_geoip_4:  # GeoIP v4 database files
            if settings.updates.geoip_custom_url:
                await self.geoip_service.download_geoip_update_files(
                    version="4", via_custom_url=True
                )
            else:
                await self.geoip_service.download_geoip_update_files(
                    version="4", via_custom_url=False
                )
        if settings.updates.update_geoip_5:  # GeoIP v5 database files
            await self.geoip_service.download_geoip_update_files(
                version="5", via_custom_url=False
            )

        if settings.updates.update_shieldmatrix:  # ShieldMatrix updates URL
            await self.kerio_update_service.get_shieldmatrix_update_url()

        await self._clean_update_files()  # Clean update files directory

        write_log(
            log_type=["system", "updates"],
            message=(
                "Scheduled mirror update process completed"
                if scheduled
                else "Manual mirror update process completed"
            ),
        )
        write_log(
            log_type=["updates"],
            message="----------------------------------------------------------------",
        )

    @staticmethod
    def _archive_logs() -> None:
        """
        Check all log files in logs_dir and archive those exceeding maximum file size.

        Archiving strategy (safe for external writers):
          1. Atomically rename the log file to a timestamped name.
             External writers that already have the file open will continue
             writing to the renamed file via their open fd - no data is lost.
          2. Compress the renamed file into a .gz archive.
          3. Delete the renamed (now fully read) intermediate file.
        New writes from external processes will create a fresh log file
        under the original name automatically.

        Already compressed files (.gz) are skipped.
        """
        logs_dir = settings.logging.log_dir

        for log_file in sorted(logs_dir.iterdir()):
            # Skip directories and already-compressed files
            if not log_file.is_file() or log_file.suffix == ".gz":
                continue

            file_size = log_file.stat().st_size
            if file_size <= settings.logging.log_rotation_size_bytes:
                continue

            # Build names: e.g. system_2026-01-15T12-30-00.log.gz
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            renamed = logs_dir / f"{log_file.stem}_{timestamp}{log_file.suffix}"
            archive = renamed.with_suffix(renamed.suffix + ".gz")

            try:
                # Step 1: atomic rename - external writers keep writing here
                log_file.rename(renamed)

                # Step 2: compress the renamed file
                with renamed.open("rb") as src, gzip.open(archive, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                # Step 3: remove the intermediate renamed file
                renamed.unlink()

                write_log(
                    log_type=["system"],
                    message=(
                        f"Log archived: {log_file.name} "
                        f"({file_size / 1024 / 1024:.1f} MB) → {archive.name}"
                    ),
                )

            except PermissionError:
                # Windows: file is held open by another process, will retry next time
                write_log(
                    log_type=["system", "errors"],
                    message=(
                        f"Log archiving skipped for {log_file.name}: "
                        f"file is locked by another process"
                    ),
                )
            except OSError as exc:
                # Do not interrupt the update process on rotation failure
                write_log(
                    log_type=["system", "errors"],
                    message=f"Log rotation failed for {log_file.name}: {exc}",
                )

    async def _clean_update_files(self) -> None:
        """Clean update files directory."""
        files_to_keep = self._get_update_files_to_keep()
        clean_directory(
            dir_path=settings.updates.update_dir, files_to_keep=files_to_keep
        )
        write_log(
            log_type=["system", "updates"],
            message="IDS/IPS/GeoIP update files directory cleaned",
        )

        antivirus_cache_dir = settings.updates.update_dir / "antivirus_cache"
        if (antivirus_cache_dir / "versions.dat").exists():
            files_to_keep = self._parse_antivirus_files_to_keep(
                dat_path=antivirus_cache_dir / "versions.dat"
            )
            clean_directory(dir_path=antivirus_cache_dir, files_to_keep=files_to_keep)
            write_log(
                log_type=["system", "updates"],
                message="Antivirus update files directory cleaned",
            )

    @staticmethod
    def _get_update_files_to_keep() -> set[str]:
        """Build set of files to keep in update_files directory."""
        update_files_static = {
            ".gitkeep",
            "kerio_cdn.cache",
            "locations.csv",
            "v4.csv",
            "v6.csv",
            "security_image",
            "snort.tpl",
            "snort.tpl.md5",
        }

        # Collect IDS filenames from settings versions
        ids_files_with_signatures = set()
        for ver in ("2", "3", "5"):
            version = getattr(settings.updates, f"ids_{ver}_version", None)
            filename = f"ids_{ver}_{version}.gz"
            if filename:
                ids_files_with_signatures.add(filename)
                ids_files_with_signatures.add(f"{filename}.sig")

        # Collect GeoIP filenames from settings versions
        geoip_files = set()
        for ver in ("4", "5"):
            version = getattr(settings.updates, f"geoip_{ver}_version", None)
            for ext in (".tar.gz", ".gz"):
                filename = f"geoip_{ver}_{version}{ext}"
                if filename:
                    geoip_files.add(filename)

        return update_files_static | ids_files_with_signatures | geoip_files

    @staticmethod
    def _parse_antivirus_files_to_keep(dat_path: Path) -> set[str]:
        """
        Parse versions.dat and return a set of filenames to keep.

        Lines starting with '+' or '0' are active files.
        Disk filename format: {name}.{hash}.gzip
        Example: 7zip.xmd.d450132d92e9d77bcd453997bb5d80bc.gzip

        Args:
            dat_path: Path to the versions.dat file.

        Returns:
            A set of filenames to keep.
        """
        files_to_keep = {"versions.dat", "versions.id", "versions.sig"}

        with open(dat_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 3 or parts[0] not in ("+", "0"):
                    continue

                hash_val = parts[1]
                file_name = Path(parts[2]).name  # strip "Plugins/" if present

                files_to_keep.add(f"{file_name}.{hash_val}.gzip")

        return files_to_keep

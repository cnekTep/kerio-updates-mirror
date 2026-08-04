import asyncio
import csv
import gzip
import tarfile
from datetime import datetime, date
from io import BytesIO, StringIO
from pathlib import Path

from app.config import settings
from app.service.ids import _check_kerio_update
from app.utils.app_logging import write_log
from app.utils.file_utils import delete_file, ensure_dir
from app.utils.internet_utils import download_file_with_retries


class GeoIPService:
    """
    Service layer for GeoIP operations.

    Handles business logic related to GeoIP management,
    acting as an intermediary between the API layer and data repository.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def download_geoip_update_files(
        self, version: str, via_custom_url: bool = False
    ) -> None:
        """
        Entry point for GeoIP update. Dispatches to the appropriate
        handler based on the ``via_custom_url`` flag.

        Args:
            version: GeoIP major version string (e.g. ``"5"``).
            via_custom_url: ``True`` to download from custom URL, ``False`` for Kerio server.
        """
        if via_custom_url:
            await self._download_geoip_via_custom_url()
        else:
            await self._download_geoip_via_kerio(version=version)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _download_geoip_via_kerio(self, version: str) -> None:
        """
        Download GeoIP update files from the Kerio server.

        Checks for a new version against the current database record,
        downloads the update file, then updates the database.

        Args:
            version: GeoIP major version string (e.g. ``"5"``).
        """
        if not settings.updates.license_number:
            write_log(
                log_type=["system", "updates"],
                message=f"GeoIP v{version} Update | Skipping: license key is not configured",
            )
            return

        write_log(
            log_type=["system"],
            message=f"GeoIP v{version} Update | Downloading update files from Kerio server",
        )

        # Get current GeoIP version from settings based on incoming version
        current_version = getattr(settings.updates, f"geoip_{version}_version") or 0

        # Check for a newer version upstream
        update_info = await self._check_geoip_update(
            version=version, current_version=current_version
        )
        if not update_info:
            return

        new_version, download_link = update_info

        update_dir = ensure_dir(path=settings.updates.update_dir)
        ext = ".tar.gz" if download_link.endswith(".tar.gz") else ".gz"
        filename = f"geoip_{version}_{new_version}{ext}"

        if not await self._download_geoip_file(
            url=download_link, save_path=update_dir / filename, version=version
        ):
            return

        # Process the archive if modification is enabled in config
        if version == "5" and settings.updates.geoip_5_copy_geoname_id:
            # This does blocking tar/CSV I/O over potentially large files,
            # so run it in a worker thread to avoid blocking the event loop.
            if not await asyncio.to_thread(
                self._copy_geoname_id_in_v5_archive,
                archive_path=update_dir / filename,
            ):
                return

        settings.bulk_update(
            {
                f"updates.geoip_{version}_version": new_version,
                f"updates.geoip_{version}_last_update": date.today(),
            }
        )
        write_log(
            log_type=["system", "updates"],
            message=f"GeoIP v{version} Update | Downloaded new version: {version}.{new_version}",
        )

    async def _download_geoip_via_custom_url(self) -> None:
        """
        Download GeoIP database files from custom URL and package them for Kerio.

        Downloads IPv4, IPv6, and geolocation CSV files, processes them,
        combines and compresses them into a single gzipped file.
        """
        # Get current GeoIP version from settings
        current_version = settings.updates.geoip_4_version or 0
        current_dt = datetime.now().strftime("%Y%m%d")

        if current_version >= int(current_dt):
            write_log(
                log_type=["system", "updates"],
                message=f"GeoIP v4 Update | Already up to date: 4.{current_version}",
            )
            return

        write_log(
            log_type=["system"],
            message=f"GeoIP v4 Update | Downloading update files: 4.{current_dt}",
        )

        update_dir = ensure_dir(path=settings.updates.update_dir)

        # (url, output_filename, process_columns)
        geo_files = [
            (settings.updates.geoip4_url, "v4.csv", True),
            (settings.updates.geoip6_url, "v6.csv", True),
            (settings.updates.geoloc_url, "locations.csv", False),
        ]

        for url, filename, process in geo_files:
            if not await self._download_and_process_geo(
                url=url, output_path=update_dir / filename, process=process
            ):
                return

        # This reads/writes/compresses potentially large CSV files, so run it
        # in a worker thread to avoid blocking the event loop.
        if not await asyncio.to_thread(
            self._combine_and_compress_geo_files,
            v4_path=update_dir / "v4.csv",
            v6_path=update_dir / "v6.csv",
            version=current_dt,
        ):
            write_log(
                log_type=["system", "updates"],
                message="GeoIP v4 Update | Failed to create archive",
            )

    def _copy_geoname_id_in_v5_archive(self, archive_path: Path) -> bool:
        """
        Repack a GeoIP v5 .tar.gz archive, copying ``geoname_id`` into
        ``registered_country_geoname_id`` for each IPv4/IPv6 block CSV.

        For each target CSV file (IPv4 and IPv6 blocks):
          - If ``geoname_id`` (col2) is present, copy it to ``registered_country_geoname_id`` (col3).
          - If ``geoname_id`` is empty but ``registered_country_geoname_id`` (col3) is present,
            copy col3 back into col2 as a fallback.
          - Drop rows where both columns are empty.
        All other files in the archive are copied through as-is.

        Args:
            archive_path: Path to the downloaded .tar.gz archive (modified in place).

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        targets = {
            "GeoIP2-Country-Blocks-IPv4.csv",
            "GeoIP2-Country-Blocks-IPv6.csv",
        }

        temp_path = archive_path.with_suffix(archive_path.suffix + ".tmp")

        try:
            with tarfile.open(archive_path, "r:gz") as tar_in:
                with tarfile.open(temp_path, "w:gz") as tar_out:
                    for member in tar_in.getmembers():
                        filename = Path(member.name).name

                        if filename not in targets:
                            # Copy non-target files (e.g. location CSVs) unchanged
                            tar_out.addfile(member, tar_in.extractfile(member))
                            continue

                        write_log(
                            log_type=["system"],
                            message=f"GeoIP v5 Update | Processing {filename}",
                        )

                        fileobj = tar_in.extractfile(member)
                        if fileobj is None:
                            raise ValueError(f"Failed to read {filename} from archive")

                        reader = csv.reader(StringIO(fileobj.read().decode("utf-8")))
                        header = next(reader)  # Save header unchanged

                        processed_rows = []
                        for row in reader:
                            if len(row) < 3:
                                processed_rows.append(row)
                                continue
                            row = self._normalize_geoname_row(row)
                            if row is not None:
                                processed_rows.append(row)

                        # Serialize processed CSV back to bytes for the archive
                        buf = StringIO()
                        writer = csv.writer(buf, lineterminator="\n")
                        writer.writerow(header)
                        writer.writerows(processed_rows)
                        encoded = buf.getvalue().encode("utf-8")

                        # Write into the new archive under the same internal path
                        info = tarfile.TarInfo(name=member.name)
                        info.size = len(encoded)
                        info.mtime = member.mtime
                        tar_out.addfile(info, BytesIO(encoded))

                        write_log(
                            log_type=["system"],
                            message=f"GeoIP v5 Update | Packed {filename} into archive",
                        )

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise FileNotFoundError(
                    f"Temp archive was not created or is empty: {temp_path}"
                )

            temp_path.replace(archive_path)  # Atomic replace only after full success
            write_log(
                log_type=["system"],
                message=(
                    f"GeoIP v5 Update | Archive processed: "
                    f"{archive_path.name} ({archive_path.stat().st_size} bytes)"
                ),
            )
            return True

        except Exception as e:
            write_log(
                log_type=["system", "errors"],
                message=f"GeoIP v5 Update | Error processing archive: {e}",
            )
            return False

        finally:
            # Always clean up the temp file
            if temp_path.exists():
                delete_file(temp_path)

    @staticmethod
    def _normalize_geoname_row(row: list[str]) -> list[str] | None:
        """
        Normalize ``geoname_id`` (col2) and ``registered_country_geoname_id`` (col3) in a CSV row.

        - If col2 is present, copy it to col3.
        - If col2 is empty but col3 is present, copy col3 back into col2.
        - If both are empty, return ``None`` (row should be dropped).

        Args:
            row: A mutable CSV row with at least 3 columns.

        Returns:
            The modified row, or ``None`` if the row should be dropped.
        """
        if row[1]:
            row[2] = row[1]
        elif row[2]:
            row[1] = row[2]
        else:
            return None
        return row

    @staticmethod
    async def _check_geoip_update(
        version: str, current_version: int
    ) -> tuple[int, str] | None:
        """
        Check whether a new GeoIP version is available upstream.

        Args:
            version: GeoIP major version string (e.g. ``"5"``).
            current_version: Minor version number currently stored in the database.

        Returns:
            ``(new_version, download_link)`` if a newer version exists, ``None`` otherwise.
        """
        base = "geoip/update.php" if version == "5" else "update.php"
        return await _check_kerio_update(
            url=f"https://ids-update.kerio.com/{base}",
            version=version,
            current_version=current_version,
            label=f"GeoIP v{version}",
        )

    @staticmethod
    async def _download_geoip_file(url: str, save_path: Path, version: str) -> bool:
        """
        Download a GeoIP file and return success status.

        Args:
            url: Download URL.
            save_path: Local path to save the file.
            version: GeoIP major version string, used in log messages.

        Returns:
            ``True`` if the download succeeded, ``False`` otherwise.
        """
        if await download_file_with_retries(
            url=url, save_path=str(save_path), context=f"GeoIP v{version}"
        ):
            return True

        write_log(
            log_type=["system"],
            message=f"GeoIP v{version} Update | Failed to download file",
        )
        return False

    async def _download_and_process_geo(
        self, url: str, output_path: Path, process: bool
    ) -> bool:
        """
        Download and optionally process a GeoIP CSV file.

        When ``process=True``, normalizes columns 2 and 3 so that a non-empty
        value in either column is mirrored to the other.

        Args:
            url: Download URL.
            output_path: Final path to save the processed file.
            process: Whether to normalize columns 2 and 3.

        Returns:
            ``True`` if the operation succeeded, ``False`` otherwise.
        """
        write_log(
            log_type=["system"],
            message=f"GeoIP v4 Update | Downloading file: {url}",
        )

        # Use a temp file to avoid partial writes on failure
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        try:
            if not await download_file_with_retries(
                url=url,
                save_path=str(temp_path),
                context=f"GeoIP download: {url}",
                headers={"Accept-Encoding": "gzip"},
            ):
                write_log(
                    log_type=["system"],
                    message=f"GeoIP v4 Update | Failed to download file: {url}",
                )
                return False

            # No processing needed - just move temp file into place
            if not process:
                temp_path.replace(output_path)
                return True

            # Normalize columns 2 and 3: copy non-empty value to the other column.
            # This reads/writes potentially large CSV files, so run it in a
            # worker thread to avoid blocking the event loop.
            await asyncio.to_thread(
                self._normalize_csv_file, temp_path=temp_path, output_path=output_path
            )

            write_log(
                log_type=["system"],
                message=f"GeoIP v4 Update | File processed successfully: {output_path}",
            )
            return True

        except Exception as e:
            write_log(
                log_type=["system", "errors"],
                message=f"GeoIP v4 Update | Error processing file: {e}",
            )
            return False

        finally:
            # Always clean up the temp file
            if temp_path.exists():
                delete_file(temp_path)

    def _normalize_csv_file(self, temp_path: Path, output_path: Path) -> None:
        """
        CSV normalization: copy non-empty value between columns 2 and 3.

        Args:
            temp_path: Path to the raw downloaded CSV file.
            output_path: Path to write the normalized CSV file to.
        """
        with open(temp_path, "r", encoding="utf-8", newline="") as infile:
            reader = csv.reader(infile)

            with open(output_path, "w", newline="", encoding="utf-8") as outfile:
                writer = csv.writer(outfile)
                writer.writerow(next(reader))  # Copy header as-is

                for row in reader:
                    if len(row) < 3:
                        writer.writerow(row)
                        continue
                    row = self._normalize_geoname_row(row)
                    if row is not None:
                        writer.writerow(row)

    def _combine_and_compress_geo_files(
        self, v4_path: Path, v6_path: Path, version: str
    ) -> bool:
        """
        Combine IPv4 and IPv6 data into a single gzipped file.

        Reads the first two columns from each CSV (skipping headers) and
        writes them into a compressed archive named ``geoip_4_<version>.gz``.

        Args:
            v4_path: Path to the processed IPv4 CSV file.
            v6_path: Path to the processed IPv6 CSV file.
            version: Date string used in the output file name (e.g. ``"20260101"``).

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        output_path = settings.updates.update_dir / f"geoip_4_{version}.gz"
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        try:
            with gzip.open(
                filename=temp_path, mode="wt", encoding="utf-8", newline=""
            ) as gz_file:
                writer = csv.writer(gz_file)
                for path in (v4_path, v6_path):
                    self._write_first_two_columns(input_path=path, writer=writer)

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise FileNotFoundError(
                    f"Output file was not created or is empty: {temp_path}"
                )

            temp_path.replace(output_path)  # Atomic replace only after full success

            write_log(
                log_type=["system"],
                message=(
                    f"GeoIP v4 Update | Archive created: "
                    f"{output_path.name} ({output_path.stat().st_size} bytes)"
                ),
            )

            settings.bulk_update(
                {
                    "updates.geoip_4_version": version,
                    "updates.geoip_4_last_update": date.today(),
                }
            )
            write_log(
                log_type=["system", "updates"],
                message=f"GeoIP v4 Update | Downloaded new version: 4.{version}",
            )
            return True

        except Exception as e:
            write_log(
                log_type=["system", "updates"],
                message=f"GeoIP v4 Update | Error during compression: {e}",
            )
            return False

        finally:
            # Always clean up the temp file
            if temp_path.exists():
                delete_file(temp_path)

    @staticmethod
    def _write_first_two_columns(input_path: Path, writer: "csv.writer") -> None:
        """
        Read a CSV file and write its first two columns, skipping the header.

        Args:
            input_path: Path to the input CSV file.
            writer: CSV writer to receive the output rows.
        """
        if not input_path.exists():
            write_log(
                log_type=["system"],
                message=f"GeoIP v4 Update | File not found: {input_path}",
            )
            return

        with open(input_path, "r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 2:
                    writer.writerow(row[:2])

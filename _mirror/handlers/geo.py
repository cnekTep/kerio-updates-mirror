import csv
import datetime
import gzip
import os
import tarfile
import time
from io import StringIO, BytesIO

from flask_babel import gettext as _

from db.database import update_ids
from utils.app_logging import write_log
from utils.internet_utils import make_request_with_retries


def download_and_process_geo(url: str, output_filename: str, modify: bool = True) -> int:
    """
    Downloads a CSV file from the provided URL, processes its content, and saves the result.
    This function avoids the creation of temporary files.

    Args:
        url (str): URL for downloading the CSV file.
        output_filename (str): Name of the output file to save the processed data.
        modify (bool): Flag indicating whether to modify the data.

    Returns:
         int: File size in bytes.
    """
    # Directory for saving files; create if it does not exist.
    save_directory = "update_files"
    os.makedirs(name=save_directory, exist_ok=True)
    output_path = os.path.join(save_directory, output_filename)  # full path to save the processed file

    # Download the file
    write_log(log_type="system", message=_("Downloading file: %(url)s", url=url))
    response = make_request_with_retries(url=url, context=f"downloading geo: {url}")

    if modify:  # Processing the data
        # Process data in memory without creating a temporary file
        content = response.content.decode("utf-8")
        file_size = len(content)
        csv_data = StringIO(content)

        reader = csv.reader(csv_data)
        header = next(reader)  # Save header
        rows = list(reader)  # Read all the lines

        # Process rows: if second column is non-empty, copy its value to the third column;
        # if the second is empty and third is present, copy third to second.
        for row in rows:
            if len(row) >= 3:
                if row[1]:
                    row[2] = row[1]
                elif not row[1] and row[2]:
                    row[1] = row[2]

        # Write processed data to the output file
        with open(output_path, "w", newline="\n") as outfile:
            writer = csv.writer(outfile)
            writer.writerow(header)
            writer.writerows(rows)

    else:
        # Save file without modifications.
        with open(output_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        file_size = os.path.getsize(output_path)

    write_log(
        log_type="system",
        message=_("File downloaded, processed and saved successfully at %(output_path)s", output_path=output_path),
    )
    return file_size


def combine_and_compress_geo_files(v4_filename: str, v6_filename: str) -> str or None:
    """
    Combines data from IPv4 and IPv6 files by extracting the first two columns,
    skipping headers, and compresses the result into a gzipped file.
    Retries automatically on failure.

    Args:
        v4_filename: Filename for the IPv4 CSV file.
        v6_filename: Filename for the IPv6 CSV file.

    Returns:
        The path to the compressed output file, or None if the operation fails.
    """
    max_attempts = 5  # Maximum number of attempts
    delay = 2  # Delay between attempts in seconds

    # Directory for saving files and constructing file paths.
    save_directory = "update_files"
    v4_path = os.path.join(save_directory, v4_filename)
    v6_path = os.path.join(save_directory, v6_filename)

    file_version = datetime.datetime.now().strftime("%Y%m%d")
    output_gz_path = os.path.join(save_directory, f"full-4-{file_version}.gz")

    for attempt in range(max_attempts):
        try:
            # Open gzip file for writing
            with gzip.open(filename=output_gz_path, mode="wt", encoding="utf-8", newline="") as gz_file:
                csv_writer = csv.writer(gz_file)
                # Process IPv4 file.
                _write_csv_rows_from_file(input_path=v4_path, writer=csv_writer)
                # Process IPv6 file.
                _write_csv_rows_from_file(input_path=v6_path, writer=csv_writer)

            # Verify that the file was created and is non-empty
            if os.path.exists(output_gz_path) and os.path.getsize(output_gz_path) > 0:
                file_size = os.path.getsize(output_gz_path)
                write_log(
                    log_type="system",
                    message=_("File created successfully. Size: %(file_size)s bytes", file_size=file_size),
                )
            else:
                raise FileNotFoundError(
                    _("File %(output_gz_path)s was not created or is empty", output_gz_path=output_gz_path)
                )

            # Update version information in the database
            update_ids(name="ids4", version=int(file_version), file_name=f"full-4-{file_version}.gz")
            log_message = _("IDSv4: new version loaded (from GitHub) - 4.%(file_version)s", file_version=file_version)
            write_log(log_type=["system", "updates"], message=log_message)
            return output_gz_path

        except Exception as e:
            write_log(
                log_type="system",
                message=_(
                    "Attempt %(attempt)s/%(max_attempts)s: error during file processing and compression: %(err)s",
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    err=str(e),
                ),
            )

            if attempt == max_attempts - 1:  # If this is the last attempt
                log_message = _("IDSv4: error during download")
                write_log(log_type=["system", "updates"], message=log_message)
                return None

            write_log(
                log_type="system", message=_("Pausing for %(delay)s seconds before the next attempt...", delay=delay)
            )
            time.sleep(delay)
    return None


def extract_and_process_geo_tar(tar_name: str) -> str | None:
    """
    Extracts GeoIP2 CSV files from a .tar.gz archive, processes them,
    and repackages them back into a new .tar.gz archive.
    Retries automatically on failure.

    Processing steps per file:
      - Fill columns 2 and 3: if col2 is non-empty, copy to col3 (and vice versa),
        without overwriting existing values.
      - Drop rows where both col2 and col3 are empty.
      - Swap col2 and col3 in data rows (header is left unchanged).

    Args:
        tar_name: Name of the .tar.gz archive (e.g. "GeoIP2-Country-CSV_20260311.tar.gz").

    Returns:
        Path to the new .tar.gz archive, or None on failure.
    """
    max_attempts = 5  # Maximum number of attempts
    delay = 2  # Delay between attempts in seconds

    save_directory = "update_files"
    os.makedirs(name=save_directory, exist_ok=True)

    targets = {
        "GeoIP2-Country-Blocks-IPv4.csv",
        "GeoIP2-Country-Blocks-IPv6.csv",
    }

    output_tar_path = os.path.join(save_directory, tar_name)
    temp_tar_path = output_tar_path + ".tmp"  # Write to temp file to avoid clobbering the input

    for attempt in range(max_attempts):
        try:
            with tarfile.open(output_tar_path, "r:gz") as tar_in:
                with tarfile.open(temp_tar_path, "w:gz") as tar_out:  # Write to temp
                    for member in tar_in.getmembers():
                        filename = os.path.basename(member.name)

                        if filename not in targets:
                            # Copy non-target files (e.g. GeoIP2-Country-Locations-*.csv) as-is
                            fileobj = tar_in.extractfile(member)
                            tar_out.addfile(member, fileobj)
                            continue

                        write_log(log_type="system", message=_("GeoIP v5: processing %(name)s", name=filename))

                        fileobj = tar_in.extractfile(member)
                        if fileobj is None:
                            raise ValueError(_("GeoIP v5: failed to read %(name)s from archive", name=filename))

                        content = fileobj.read().decode("utf-8")
                        reader = csv.reader(StringIO(content))
                        header = next(reader)  # Save header unchanged

                        processed_rows = []
                        for row in reader:
                            if len(row) < 3:
                                processed_rows.append(row)
                                continue

                            col2, col3 = row[1], row[2]

                            # Fill missing value without overwriting existing one
                            if col2 and not col3:
                                row[2] = col2
                            elif col3 and not col2:
                                row[1] = col3

                            # Drop rows where both col2 and col3 are empty
                            if not row[1] and not row[2]:
                                continue

                            # Swap col2 and col3 (header is untouched, so column names stay correct)
                            row[1], row[2] = row[2], row[1]

                            processed_rows.append(row)

                        # Serialize processed CSV back to bytes
                        output = StringIO()
                        writer = csv.writer(output, lineterminator="\n")
                        writer.writerow(header)
                        writer.writerows(processed_rows)
                        encoded = output.getvalue().encode("utf-8")

                        # Write into the new archive under the same internal path
                        info = tarfile.TarInfo(name=member.name)
                        info.size = len(encoded)
                        tar_out.addfile(info, BytesIO(encoded))

                        write_log(log_type="system", message=_("GeoIP v5: packed %(name)s into archive", name=filename))

            if not os.path.exists(temp_tar_path) or os.path.getsize(temp_tar_path) == 0:
                raise FileNotFoundError(
                    _("File %(output_tar_path)s was not created or is empty", output_tar_path=output_tar_path)
                )

            os.replace(temp_tar_path, output_tar_path)  # Atomic replace only after success

            write_log(
                log_type="system",
                message=_("GeoIP v5: archive created successfully: %(path)s (%(size)s bytes)",
                          path=output_tar_path, size=os.path.getsize(output_tar_path)),
            )
            write_log(log_type="updates", message=_("IDSv5: file has been modified"))
            return output_tar_path

        except Exception as e:
            # Clean up failed temp file before next attempt
            if os.path.exists(temp_tar_path):
                os.remove(temp_tar_path)

            write_log(
                log_type="system",
                message=_(
                    "Attempt %(attempt)s/%(max_attempts)s: error during file processing and compression: %(err)s",
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    err=str(e),
                ),
            )

            if attempt == max_attempts - 1:  # If this is the last attempt
                write_log(log_type=["system", "updates"], message=_("IDSv5: error during modification"))
                return None

            write_log(
                log_type="system", message=_("Pausing for %(delay)s seconds before the next attempt...", delay=delay)
            )
            time.sleep(delay)

    return None


def _write_csv_rows_from_file(input_path: str, writer: csv.writer) -> None:
    """
    Reads a CSV file skipping the header and writes the first two columns of each row to the given CSV writer.

    Args:
        input_path: Path to the input CSV file.
        writer: CSV writer object to write the processed rows.
    """
    if os.path.exists(input_path):
        with open(input_path, "r", newline="") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                if len(row) >= 2:
                    writer.writerow(row[:2])
    else:
        write_log(
            log_type="system", message=_("File %(input_path)s not found", input_path=os.path.basename(input_path))
        )

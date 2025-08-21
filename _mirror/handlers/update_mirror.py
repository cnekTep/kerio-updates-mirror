import datetime
import logging
import threading
from pathlib import Path

from flask import redirect, current_app
from flask_babel import gettext as _

from config.config_env import config
from db.database import (
    get_ids,
    get_all_ids_file_names,
    clear_webfilter_table,
    clear_ids_table,
    cleanup_bitdefender_cache,
    get_all_bitdefender_cache_file_names,
    update_cache_last_usage_batch,
    add_stat_mirror_update,
)
from handlers.geo import download_and_process_geo, combine_and_compress_geo_files
from handlers.ids import download_ids_update_files, download_snort_template
from handlers.webfilter import update_web_filter_key
from utils.file_utils import clean_directory, delete_oldest_files_until
from utils.internet_utils import make_request_with_retries
from utils.logging import write_log


def handler_update_mirror(forced=False):
    """
    Flask route handler for mirror update process.
    Launches the update process in a background thread and redirects user to the log page.

    Args:
        forced: True if update is forced, False if not

    Returns:
        Flask redirect to the log page
    """
    app = current_app._get_current_object()  # Get current Flask application

    # Clear database tables if forced
    if forced:
        clear_webfilter_table()
        clear_ids_table()

    # Start update in a separate thread
    thread = threading.Thread(target=background_update_mirror, args=(app,))
    thread.daemon = True  # Thread will automatically terminate when main application closes
    thread.start()

    return redirect("/#updates_log")  # Immediately redirect user to the updates log page


def update_mirror(scheduler=False) -> None:
    """
    Function to directly perform mirror update, suitable for calling from scheduler.
    This function does not require Flask context or return anything.

    Args:
        scheduler: True if function is called from scheduler. Defaults to False.
    """
    write_log(log_type="updates", message="", date=False)
    write_log(log_type="updates", message="----------------------------------------------------------------")
    write_log(
        log_type=["system", "updates"],
        message=(
            _("Scheduled mirror update process started") if scheduler else _("Manual mirror update process started")
        ),
    )
    write_log(
        log_type="updates", message=_("Using license key: %(license_number)s", license_number=config.license_number)
    )
    write_log(log_type="updates", message="----------------------------------------------------------------")

    if config.update_web_filter_key and not config.forced_web_filter_key:  # Update Web Filter key
        update_web_filter_key()

    if config.update_ids_1:  # IPS/IDS Snort (Windows versions)
        download_ids_update_files(version="1")

    if config.update_ids_2:  # Compromised address lists for blocking
        download_ids_update_files(version="2")

    if config.update_ids_3:  # IPS/IDS Snort (Linux versions up to 9.5)
        download_ids_update_files(version="3")

    if config.update_ids_4:  # Update GeoIP database files
        if config.geoip_github:
            actual_version = get_ids(name="ids4")
            current_version = "0"
            if actual_version is not None and "version" in actual_version:
                current_version = actual_version["version"]
            if int(current_version) < int(datetime.datetime.now().strftime("%Y%m%d")):
                write_log(
                    log_type="system",
                    message=_(
                        "Downloading new version: 4.%(version)s", version=datetime.datetime.now().strftime("%Y%m%d")
                    ),
                )

                # Download and process all necessary geo files
                geo_files = [
                    (config.geoip4_url, "v4.csv", True),
                    (config.geoip6_url, "v6.csv", True),
                    (config.geoloc_url, "locations.csv", False),
                ]

                total_size = 0
                for url, filename, modify in geo_files:
                    file_size = download_and_process_geo(url=url, output_filename=filename, modify=modify)
                    total_size += file_size

                add_stat_mirror_update(update_type="ids_v4_github", bytes_downloaded=total_size)

                combine_and_compress_geo_files(
                    v4_filename="v4.csv",
                    v6_filename="v6.csv",
                )
            else:
                write_log(
                    log_type="updates",
                    message=_(
                        "IDSv4: no new version available, current version: 4.%(actual_version)s",
                        actual_version=current_version,
                    ),
                )
        else:
            download_ids_update_files(version="4")

    if config.update_ids_5:  # IPS/IDS Snort (Linux versions from 9.5)
        download_ids_update_files(version="5")

    if config.update_snort_template:  # Download Snort template files
        download_snort_template()

    # Create a list of files to keep in update_files directory
    all_ids_file_names = get_all_ids_file_names()
    update_files_to_keep = [".gitkeep", "locations.csv", "v4.csv", "v6.csv", "snort.tpl", "snort.tpl.md5"]
    for file_name in all_ids_file_names:
        update_files_to_keep.append(file_name)
        update_files_to_keep.append(f"{file_name}.sig")

    # Clean update_files directory
    clean_directory(dir_path=Path("update_files"), files_to_keep=update_files_to_keep)

    if config.bitdefender_update_mode == "via_mirror_cache":
        # Upload actual files versions and update their last usage in database.
        update_bitdefender_cache_last_usage()
        # Delete old bitdefender cache files from database
        cleanup_bitdefender_cache(int(config.bitdefender_cache_max_days))
        # Create a list of files to keep in bitdefender_cache directory
        cache_files_to_keep = get_all_bitdefender_cache_file_names()
        cache_files_to_keep.append(".gitkeep")

        # Clean bitdefender_cache directory
        bitdefender_cache_dir = Path("update_files/bitdefender_cache")
        clean_directory(dir_path=bitdefender_cache_dir, files_to_keep=cache_files_to_keep)  # Del by max time
        if config.bitdefender_cache_max_size:  # Del by max size
            logging.error(f"Bitdefender cache max size: {config.bitdefender_cache_max_size}")
            delete_oldest_files_until(
                dir_path=bitdefender_cache_dir, max_folder_bytes=int(config.bitdefender_cache_max_size)
            )

        write_log(log_type=["system", "updates"], message=_("Bitdefender old cache files removed"))

    write_log(
        log_type=["system", "updates"],
        message=(
            _("Scheduled mirror update process completed") if scheduler else _("Manual mirror update process completed")
        ),
    )
    write_log(log_type="updates", message="----------------------------------------------------------------")


def update_bitdefender_cache_last_usage():
    """Updates last usage date for actual bitdefender cache files in database"""
    if config.antivirus_update_url == "https://bdupdate.kerio.com":
        url = f"{config.kerio_cdn_url}/av64bit/versions.dat"
    else:
        url = f"{config.antivirus_update_url}/av64bit/versions.dat"

    try:
        response = make_request_with_retries(url=url, context=f"downloading bitdefender versions.dat file: {url}")

        if not response:
            write_log(log_type="system", message=_("Error downloading bitdefender versions.dat file"))
            return
        write_log(log_type="system", message=_("Successfully downloaded bitdefender versions.dat file"))

        # Parse each line and extract hash
        lines = response.text.strip().split("\n")

        valid_hashes = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse line format: [+|-|0] <hash> <filename> <size>
            parts = line.split()
            if len(parts) < 4:
                continue

            # Extract hash (second column)
            hash_value = parts[1]

            # Basic hash validation - alphanumeric, reasonable length
            if len(hash_value) >= 32 and hash_value.isalnum():
                valid_hashes.append(hash_value)

        if valid_hashes:
            # Update last_usage for all valid hashes in database
            update_cache_last_usage_batch(file_hashes=valid_hashes)
    except Exception as e:
        write_log(
            log_type="system", message=_("Error downloading bitdefender versions.dat file: %(error)s", error=str(e))
        )
        return


def background_update_mirror(app):
    """
    Perform the mirror update process in the background.

    Args:
        app: Flask application object for creating application context
    """
    with app.app_context():  # Create application context for background thread
        update_mirror()  # Reuse the same update logic

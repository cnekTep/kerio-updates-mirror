import datetime
import threading

from flask import redirect, current_app

from config.config_env import config
from db.database import get_ids, get_all_ids_file_names
from handlers.geo import download_and_process_geo, combine_and_compress_geo_files
from handlers.ids import download_ids_update_files
from handlers.webfilter import update_web_filter_key
from utils.file_utils import clean_update_files
from utils.logging import write_log


def handler_update_mirror():
    """
    Flask route handler for mirror update process.
    Launches the update process in a background thread and redirects user to the log page.

    Returns:
        Flask redirect to the log page
    """
    app = current_app._get_current_object()  # Get current Flask application

    # Start update in a separate thread
    thread = threading.Thread(target=background_update_mirror, args=(app,))
    thread.daemon = True  # Thread will automatically terminate when main application closes
    thread.start()

    return redirect("/#updates_log")  # Immediately redirect user to the updates log page


def update_mirror():
    """
    Function to directly perform mirror update, suitable for calling from scheduler.
    This function does not require Flask context or return anything.
    """
    write_log(log_type="system", message="Scheduled mirror update process started")
    write_log(log_type="updates", message="", date=False)
    write_log(log_type="updates", message="----------------------------------------------------------------")
    write_log(log_type="updates", message="Starting scheduled mirror update...")
    write_log(log_type="updates", message=f"Using license key: {config.license_number}")
    write_log(log_type="updates", message="----------------------------------------------------------------")

    if config.update_web_filter_key:  # Update Web Filter key
        update_web_filter_key()

    if config.update_ids_1:  # IPS/IDS Snort (Windows versions)
        download_ids_update_files(version="1")

    if config.update_ids_2:  # Compromised address lists for blocking
        download_ids_update_files(version="2")

    if config.update_ids_3:  # IPS/IDS Snort (Linux versions up to 9.5)
        download_ids_update_files(version="3")

    if config.update_ids_4:  # Update GeoIP database files
        if not config.geoip_github:
            download_ids_update_files(version="4")
            return

        actual_version = get_ids(name=f"ids4")
        if int(actual_version["version"]) < int(datetime.datetime.now().strftime("%Y%m%d")):
            write_log(
                log_type="system",
                message=f"Downloading new version: 4.{datetime.datetime.now().strftime('%Y%m%d')}",
            )

            # Download and process all necessary geo files
            download_and_process_geo(url=config.geoip4_url, output_filename=f"v4.csv", modify=True)
            download_and_process_geo(url=config.geoip6_url, output_filename=f"v6.csv", modify=True)
            download_and_process_geo(url=config.geoloc_url, output_filename=f"locations.csv", modify=False)

            combine_and_compress_geo_files(
                v4_filename="v4.csv",
                v6_filename="v6.csv",
            )
        else:
            write_log(
                log_type="updates",
                message=f"IDSv4: no new version available, current version: 4.{actual_version['version']}",
            )

    if config.update_ids_5:  # IPS/IDS Snort (Linux versions from 9.5)
        download_ids_update_files(version="5")

    all_ids_file_names = get_all_ids_file_names()
    files_to_keep = ["locations.csv", "v4.csv", "v6.csv"]
    for file_name in all_ids_file_names:
        files_to_keep.append(file_name)
        files_to_keep.append(f"{file_name}.sig")

    clean_update_files(files_to_keep=files_to_keep)

    write_log(log_type="updates", message=f"Update completed")
    write_log(log_type="updates", message="----------------------------------------------------------------")
    write_log(log_type="system", message="Scheduled mirror update process completed")


def background_update_mirror(app):
    """
    Perform the mirror update process in the background.

    Args:
        app: Flask application object for creating application context
    """
    with app.app_context():  # Create application context for background thread
        update_mirror()  # Reuse the same update logic

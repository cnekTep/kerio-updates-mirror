import logging
import os

from flask import request, Response, send_file
from flask_babel import gettext as _

from config.config_env import config
from db.database import get_ids, update_ids
from utils.internet_utils import make_request_with_retries, download_file_with_retries
from utils.logging import write_log


def handler_ids_update(update_type: str):
    """Handler for providing IDS or Snort update files"""
    write_log(
        log_type="system",
        message=_(
            "Received request for %(update_type)s update: %(request_path)s",
            update_type=update_type,
            request_path=request.path,
        ),
        ip=request.remote_addr if config.ip_logging else None,
    )

    current_directory = os.getcwd()  # Get the current directory
    target_directory = os.path.join(current_directory, "update_files")  # Construct the target directory

    if update_type == "IDS":  # Check if the update type is "IDS"
        request_path = request.path.replace("/control-update", target_directory)
    else:  # Otherwise, it's "Snort"
        filename = request.path.split("/")[-1]
        request_path = os.path.join(target_directory, filename)

    return send_file(path_or_file=request_path, as_attachment=True)


def handler_checknew():
    """Handler for checking for new versions"""
    response_text = "--INFO--\nReminderId='1'\nReminderAuth='1'\nVersion='0'"
    return Response(response=response_text, status=200, mimetype="text/plain")


def handle_update():
    """Handler for update.php request"""
    local_ip = request.headers.get("Host")
    version = request.args.get("version")

    if not version:
        write_log(
            log_type="system",
            message=_("Error processing URL %(request_url)s in update request", request_url=request.url),
            ip=request.remote_addr if config.ip_logging else None,
        )
        return Response(response="", status=400)

    write_log(
        log_type="system",
        message=_("Received update request for version: %(version)s", version=version),
        ip=request.remote_addr if config.ip_logging else None,
    )

    # Parse major version number
    try:
        major_version = int(version.split(".")[0])
    except (ValueError, IndexError):
        write_log(
            log_type="system",
            message=_("Invalid version format: %(version)s", version=version),
            ip=request.remote_addr if config.ip_logging else None,
        )
        return Response(response="400 Bad Request", status=400, mimetype="text/plain")

    # Special cases handling
    if major_version == 0:
        return Response(response="0:0.0", status=200)
    elif major_version in [9, 10]:
        write_log(
            log_type="connections",
            message=_("Received update request for antivirus"),
            ip=request.remote_addr if config.ip_logging else None,
        )

        response_text = "THDdir=https://bdupdate.kerio.com/../"  # Default value

        # Check if alternative mode is enabled
        if config.alternative_mode:
            update_url = config.antivirus_update_url.strip().rstrip("/")
            is_kerio_host = "bdupdate.kerio.com" in update_url

            # Set default response for alternative mode without mirror
            if config.bitdefender_update_mode == "no_mirror":
                response_text = f"THDdir={update_url}/../"

            # Make request to Kerio if needed
            if is_kerio_host:
                url = f"https://bdupdate.kerio.com/update.php?id={config.license_number}&version={version}&tag="
                headers = {"Host": "bdupdate.kerio.com"}

                response = make_request_with_retries(
                    url=url, headers=headers, context="receiving antivirus update link"
                )

                if response:
                    if config.bitdefender_update_mode == "via_mirror":
                        config.kerio_cdn_url = response.text.replace("THDdir=", "").strip()
                    else:
                        response_text = response.text
                else:
                    write_log(
                        log_type="system",
                        message=_("Error occurred while receiving a link to an antivirus update"),
                    )
                    return Response(response="400 Bad Request", status=400, mimetype="text/plain")

        write_log(
            log_type="system",
            message=_("Update link sent: %(url)s", url=response_text.replace("THDdir=", "").strip()),
            ip=request.remote_addr if config.ip_logging else None,
        )
        return Response(
            response=response_text,
            mimetype="text/plain",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # Regular versions (1-5)
    if 1 <= major_version <= 5:
        write_log(
            log_type="connections",
            message=_("Received update request for IDSv%(version)s", version=major_version),
            ip=request.remote_addr if config.ip_logging else None,
        )
        try:
            result = get_ids(f"ids{major_version}")
            response_text = (
                f"0:{major_version}.{str(result['version'])}\n"
                f"full:http://{local_ip}/control-update/{result['file_name']}"
            )
            return Response(response=response_text, status=200)
        except Exception as err:
            write_log(
                log_type="system",
                message=_("Error occurred while processing IDS update: %(err)s", err=str(err)),
            )
            return Response(response="500 Internal Server Error", status=500, mimetype="text/plain")

    # Unknown version
    write_log(
        log_type="system",
        message=_("Received unknown download request: %(version)s", version=version),
        ip=request.remote_addr if config.ip_logging else None,
    )
    return Response(response="404 Not found", status=404, mimetype="text/plain")


def download_ids_update_files(version: str) -> None:
    """
    Downloads IDS update files from Kerio server

    Args:
        version: IDS version
    """
    # Get current version number and download link
    url = f"https://ids-update.kerio.com/update.php?id={config.license_number}&version={version}.0&tag="
    headers = {"Host": "ids-update.kerio.com"}

    if not config.license_number:
        log_message = _("IDSv%(version)s: passing because license key is not configured", version=version)
        write_log(log_type=["system", "updates"], message=log_message)
        return

    response = make_request_with_retries(url=url, headers=headers, context=f"IDSv{version}")

    if not response:
        log_message = _("IDSv%(version)s: error downloading update", version=version)
        write_log(log_type=["system", "updates"], message=log_message)
        return

    # Parse response text into lines and initialize result dictionary
    lines = response.text.strip().splitlines()
    result = {}

    # Parse each line
    for line in lines:
        key, value = line.split(sep=":", maxsplit=1)
        if key == "0":
            result["version"] = int(value.split(".")[1])
        elif key == "full":
            result["download_link"] = value
        else:
            log_message = _("IDSv%(version)s error: %(err)s", version=version, err=response.text.strip())
            write_log(log_type=["system", "updates"], message=log_message)
            config.license_number = None
            return

    # Get current version from database
    actual_version = get_ids(name=f"ids{version}")
    current_version = 0

    if actual_version is not None and "version" in actual_version:
        current_version = actual_version["version"]

    if current_version >= result["version"]:
        log_message = _(
            "IDSv%(version)s: no new version, current version: %(version)s.%(result_version)s",
            version=version,
            result_version=result["version"],
        )
        write_log(log_type=["system", "updates"], message=log_message)
        return

    # Download new version
    write_log(
        log_type="system",
        message=_(
            "IDSv%(version)s: downloading new version: %(version)s.%(result_version)s",
            version=version,
            result_version=result["version"],
        ),
    )

    # Create directory for saving files
    save_directory = "update_files"
    os.makedirs(name=save_directory, exist_ok=True)

    # Get filename from URL
    filename = result["download_link"].split("/")[-1]
    save_path = os.path.join(save_directory, filename)

    # Download main file using existing function
    if not download_file_with_retries(
        url=result["download_link"], save_path=save_path, context=f"IDSv{version} main file"
    ):
        write_log(log_type="system", message=_("Failed to download main file for IDSv%(version)s", version=version))
        return

    # Download signature file for certain versions
    if version in ["1", "2", "3", "5"]:
        sig_save_path = os.path.join(save_directory, f"{filename}.sig")
        if not download_file_with_retries(
            url=f"{result['download_link']}.sig", save_path=sig_save_path, context=f"IDSv{version} signature file"
        ):
            write_log(
                log_type="system",
                message=_("Failed to download signature file for IDSv%(version)s", version=version),
            )
            return

    # Update version information in database
    update_ids(name=f"ids{version}", version=int(result["version"]), file_name=filename)
    log_message = _(
        "IDSv%(version)s: downloaded new version - %(version)s.%(result_version)s",
        version=version,
        result_version=result["version"],
    )
    write_log(log_type=["system", "updates"], message=log_message)


def download_snort_template() -> None:
    snort_template_url = "http://download.kerio.com/control-update/config/v1/snort.tpl"
    snort_template_md5_url = "http://download.kerio.com/control-update/config/v1/snort.tpl.md5"

    download_urls = [snort_template_url, snort_template_md5_url]

    # Create directory for saving files
    save_directory = "update_files"
    os.makedirs(name=save_directory, exist_ok=True)

    for url in download_urls:
        # Get filename from URL
        filename = url.split("/")[-1]
        save_path = os.path.join(save_directory, filename)

        # Download file using existing function
        if download_file_with_retries(url=url, save_path=save_path, context="Snort template"):
            write_log(
                log_type="system",
                message=_("Successfully downloaded Snort template: %(url)s", url=url),
            )
        else:
            write_log(
                log_type="system",
                message=_("Failed to download Snort template: %(url)s", url=url),
            )

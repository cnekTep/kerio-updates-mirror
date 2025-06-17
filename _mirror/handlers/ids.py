import os

import requests
from flask import request, Response, send_file
from flask_babel import gettext as _

from config.config_env import config
from db.database import get_ids, update_ids
from utils.internet_utils import add_proxy_to_params, prepare_request_params
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
                try:
                    target_host = "bdupdate.kerio.com"
                    url = f"https://bdupdate.kerio.com/update.php?id={config.license_number}&version={version}&tag="
                    headers = {"Host": target_host}
                    request_params = prepare_request_params(url=url, headers=headers)

                    # Setup proxy if configured
                    if config.tor:
                        request_params = add_proxy_to_params(proxy_type="tor", params=request_params)
                    elif config.proxy:
                        request_params = add_proxy_to_params(proxy_type="proxy", params=request_params)

                    response = requests.get(**request_params)
                    response.raise_for_status()

                    # Handle response based on mode
                    if config.bitdefender_update_mode == "via_mirror":
                        config.kerio_cdn_url = response.text.replace("THDdir=", "").strip()
                    else:
                        response_text = response.text

                except Exception as err:
                    write_log(
                        log_type="system",
                        message=_(
                            "Error occurred while receiving a link to an antivirus update: %(err)s", err=str(err)
                        ),
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
    target_host = "ids-update.kerio.com"
    url = f"https://ids-update.kerio.com/update.php?id={config.license_number}&version={version}.0&tag="
    headers = {"Host": target_host}

    if not config.license_number:
        log_message = _("IDSv%(version)s: passing because license key is not configured", version=version)
        write_log(log_type=["system", "updates"], message=log_message)
        return

    # Attempt order: direct, TOR (if enabled), proxy (if enabled)
    connection_attempts = [{"type": "direct"}]

    if config.tor:
        connection_attempts.append({"type": "tor"})

    if config.proxy:
        connection_attempts.append({"type": "proxy"})

    for attempt in connection_attempts:
        try:
            proxy_type = None
            request_params = prepare_request_params(url=url, headers=headers)

            # Apply proxy settings for TOR or regular proxy
            if attempt["type"] in ("tor", "proxy"):
                proxy_type = attempt["type"]
                request_params = add_proxy_to_params(proxy_type=proxy_type, params=request_params)

            # Send HTTP request
            response = requests.get(**request_params)

            if not response.ok:
                continue

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

            # Download main file
            if not download_file(url=result["download_link"], save_path=save_path, proxy_type=proxy_type):
                write_log(
                    log_type="system", message=_("Failed to download main file for IDSv%(version)s", version=version)
                )
                continue

            # Download signature file for certain versions
            if version in ["1", "2", "3", "5"]:
                sig_save_path = os.path.join(save_directory, f"{filename}.sig")
                if not download_file(
                    url=f"{result['download_link']}.sig", save_path=sig_save_path, proxy_type=proxy_type
                ):
                    write_log(
                        log_type="system",
                        message=_("Failed to download signature file for IDSv%(version)s", version=version),
                    )
                    continue

            # Update version information in database
            update_ids(name=f"ids{version}", version=int(result["version"]), file_name=filename)
            log_message = _(
                "IDSv%(version)s: downloaded new version - %(version)s.%(result_version)s",
                version=version,
                result_version=result["version"],
            )
            write_log(log_type=["system", "updates"], message=log_message)
            return

        except requests.RequestException as err:
            attempt_desc = {
                "direct": "without proxy",
                "tor": "via TOR",
                "proxy": "with proxy",
            }[attempt["type"]]

            write_log(
                log_type="system",
                message=_(
                    "Error downloading IDSv%(version)s %(proxy_status)s: %(err)s",
                    version=version,
                    proxy_status=attempt_desc,
                    err=str(err),
                ),
            )

    # If we get here, all attempts failed
    log_message = _("IDSv%(version)s: error downloading update", version=version)
    write_log(log_type=["system", "updates"], message=log_message)


def download_snort_template() -> None:
    snort_template_url = "http://download.kerio.com/control-update/config/v1/snort.tpl"
    snort_template_md5_url = "http://download.kerio.com/control-update/config/v1/snort.tpl.md5"

    download_urls = [snort_template_url, snort_template_md5_url]

    for url in download_urls:
        # Attempt order: direct, TOR (if enabled), proxy (if enabled)
        connection_attempts = [{"type": "direct"}]

        if config.tor:
            connection_attempts.append({"type": "tor"})

        if config.proxy:
            connection_attempts.append({"type": "proxy"})

        for attempt in connection_attempts:
            attempt_desc = {
                "direct": "without proxy",
                "tor": "via TOR",
                "proxy": "with proxy",
            }[attempt["type"]]

            proxy_type = None

            # Apply proxy settings for TOR or regular proxy
            if attempt["type"] in ("tor", "proxy"):
                proxy_type = attempt["type"]

            # Create directory for saving files
            save_directory = "update_files"
            os.makedirs(name=save_directory, exist_ok=True)

            # Get filename from URL
            filename = url.split("/")[-1]
            save_path = os.path.join(save_directory, filename)

            # Download file
            if not download_file(url=url, save_path=save_path, proxy_type=proxy_type):
                write_log(
                    log_type="system",
                    message=_(
                        "[%(proxy_status)s] Failed to download Snort template: %(url)s",
                        proxy_status=attempt_desc,
                        url=url,
                    ),
                )
                continue
            else:
                write_log(
                    log_type="system",
                    message=_(
                        "[%(proxy_status)s] Successfully downloaded Snort template: %(url)s",
                        proxy_status=attempt_desc,
                        url=url,
                    ),
                )
                break


def download_file(url: str, save_path: str, proxy_type: str = None):
    """
    Downloads a file from the specified URL and saves it to the given path.

    Args:
        url: URL to download from
        save_path: Path to save the file to
        proxy_type: Type of proxy to use

    Returns:
        bool: True if download successful, False otherwise
    """
    try:
        params = prepare_request_params(url=url, stream=True)

        if proxy_type:
            params = add_proxy_to_params(proxy_type=proxy_type, params=params)

        response = requests.get(**params)
        response.raise_for_status()

        # Save the file
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        return True
    except requests.RequestException:
        return False

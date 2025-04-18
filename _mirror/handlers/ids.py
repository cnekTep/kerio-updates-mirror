import base64
import os

import requests
from flask import request, Response, send_file

from config.config_env import config
from db.database import get_ids, update_ids
from utils.logging import write_log


def handler_control_update():
    """Handler for providing IDS update files"""
    write_log(log_type="system", message=f"Received request for IDS update: {request.path}")
    request_path = request.path.replace("/control-update", "update_files")

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
        write_log(log_type="system", message=f"Error processing URL {request.url} in update request")
        return Response(response="", status=400)

    write_log(log_type="system", message=f"Received update request for version: {version}")

    # Parse major version number
    try:
        major_version = int(version.split(".")[0])
    except (ValueError, IndexError):
        write_log(log_type="system", message=f"Invalid version format: {version}")
        return Response(response="400 Bad Request", status=400, mimetype="text/plain")

    # Special cases handling
    if major_version == 0:
        return Response(response="0:0.0", status=200)
    elif major_version == 9:
        return Response(
            response="THDdir=https://bdupdate.kerio.com/../",
            mimetype="text/plain",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # Regular versions (1-5)
    if 1 <= major_version <= 5:
        result = get_ids(f"ids{major_version}")
        response_text = (
            f"0:{major_version}.{str(result['version'])}\n"
            f"full:http://{local_ip}/control-update/{result['file_name']}"
        )
        return Response(response=response_text, status=200)

    # Unknown version
    write_log(log_type="system", message=f"Received unknown download request: {version}")
    return Response(response="404 Not found", status=404, mimetype="text/plain")


def download_ids_update_files(version: str):
    """Downloads IDS update files from Kerio server"""
    # Get current version number and download link
    target_host = "ids-update.kerio.com"
    url = f"https://ids-update.kerio.com/update.php?id={config.license_number}&version={version}.0&tag="
    headers = {"Host": target_host}

    # Try direct connection first, then proxy if available
    for use_proxy in [False, True]:
        # Skip proxy attempt if proxy is not configured
        if use_proxy and not config.proxy:
            break

        try:
            params = prepare_request_params(url=url, headers=headers)

            if use_proxy:
                params = add_proxy_to_params(params)

            response = requests.get(**params)

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

            # Get current version from database
            actual_version = get_ids(name=f"ids{version}")

            if actual_version["version"] >= result["version"]:
                write_log(
                    log_type="updates",
                    message=f"IDSv{version}: no new version, current version: {version}.{result['version']}",
                )
                write_log(
                    log_type="system",
                    message=f"IDSv{version}: no new version, current version: {version}.{result['version']}",
                )
                return

            # Download new version
            write_log(
                log_type="system", message=f"IDSv{version}: downloading new version: {version}.{result['version']}"
            )

            # Create directory for saving files
            save_directory = "update_files"
            os.makedirs(name=save_directory, exist_ok=True)

            # Get filename from URL
            filename = result["download_link"].split("/")[-1]
            save_path = os.path.join(save_directory, filename)

            # Download main file
            if not download_file(url=result["download_link"], save_path=save_path, use_proxy=use_proxy):
                write_log(log_type="system", message=f"Failed to download main file for IDSv{version}")
                continue

            # Download signature file for certain versions
            if version in ["1", "2", "3", "5"]:
                sig_save_path = os.path.join(save_directory, f"{filename}.sig")
                if not download_file(
                    url=f"{result['download_link']}.sig", save_path=sig_save_path, use_proxy=use_proxy
                ):
                    write_log(log_type="system", message=f"Failed to download signature file for IDSv{version}")
                    continue

            # Update version information in database
            update_ids(name=f"ids{version}", version=int(result["version"]), file_name=filename)
            write_log(
                log_type="updates", message=f"IDSv{version}: downloaded new version - {version}.{result['version']}"
            )
            write_log(
                log_type="system", message=f"IDSv{version}: downloaded new version - {version}.{result['version']}"
            )
            return

        except requests.RequestException as err:
            proxy_status = "with proxy" if use_proxy else "without proxy"
            write_log(log_type="system", message=f"Error downloading IDSv{version} {proxy_status}: {str(err)}")

    # If we get here, all attempts failed
    write_log(log_type="updates", message=f"IDSv{version}: error downloading update")
    write_log(log_type="system", message=f"IDSv{version}: error downloading update")


def prepare_request_params(url: str, headers: dict = None, stream: bool = False) -> dict:
    """
    Prepares request parameters with optional proxy configuration.

    Args:
        url: URL for the request
        headers: Headers for the request
        stream: Whether to stream the response

    Returns:
        dict: Dictionary with request parameters
    """
    params = {
        "url": url,
        "timeout": 30,
        "stream": stream,
    }

    if headers:
        params["headers"] = headers

    return params


def add_proxy_to_params(params: dict) -> dict:
    """
    Adds proxy configuration to request parameters if proxy is configured.

    Args:
        params: Request parameters to modify

    Returns:
        dict: Modified request parameters with proxy settings
    """
    if not config.proxy:
        return params

    params["proxies"] = {
        "http": f"http://{config.proxy_host}:{config.proxy_port}",
        "https": f"http://{config.proxy_host}:{config.proxy_port}",
    }

    if config.proxy_login:
        headers = params.get("headers", {})
        auth_str = f"{config.proxy_login}:{config.proxy_password}"
        headers["Proxy-Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
        params["headers"] = headers

    return params


def download_file(url: str, save_path: str, use_proxy: bool = False):
    """
    Downloads a file from the specified URL and saves it to the given path.

    Args:
        url: URL to download from
        save_path: Path to save the file to
        use_proxy: Whether to use proxy for download

    Returns:
        bool: True if download successful, False otherwise
    """
    try:
        params = prepare_request_params(url=url, stream=True)

        if use_proxy:
            params = add_proxy_to_params(params)

        response = requests.get(**params)
        response.raise_for_status()

        # Save the file
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        return True
    except requests.RequestException:
        return False

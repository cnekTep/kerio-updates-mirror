import json
import os
import re

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from flask import jsonify, request
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from config.config_env import config
from utils.logging import write_log


def handle_distro_upload():
    """
    Handle distribution file upload with digital signature.

    This function processes uploaded distribution files, validates them,
    saves them to the appropriate directory, and creates a digital signature
    for security verification.

    Returns:
        tuple: Flask response tuple containing:
            - JSON response with success status and data
            - HTTP status code

    Raises:
        Exception: Internal server error for unexpected failures

    Note:
        Expected file format: kerio-control-upgrade-{version}.img
        Creates corresponding .sig file for each uploaded distribution
    """
    try:
        # Check if file is present in the request
        if "distro_file" not in request.files:
            return jsonify({"success": False, "error": _("No file selected")}), 400

        file = request.files["distro_file"]

        # Check if file is selected
        if file.filename == "":
            return jsonify({"success": False, "error": _("No file selected")}), 400

        # Create directory if it doesn't exist
        distro_dir = "./update_files/distros"
        os.makedirs(name=distro_dir, exist_ok=True)

        # Secure filename
        filename = secure_filename(file.filename)

        # Validate filename format and extract version
        kerio_version = get_kerio_version_from_filename(filename)
        if not kerio_version:
            return jsonify({"success": False, "error": _("Invalid filename format")}), 400

        # Save file
        filepath = os.path.join(distro_dir, filename)
        file.save(filepath)
        write_log(log_type="system", message=_("Kerio Control Upgrade file uploaded: %(filename)s", filename=filename))

        # Sign the file
        _create_file_signature(filepath)
        write_log(
            log_type="system", message=_("Kerio Control Upgrade file signed: %(filename)s", filename=f"{filename}.sig")
        )

        # Update distributions list
        distros = get_distributes_list()

        return jsonify(
            {
                "success": True,
                "message": _('File "%(filename)s" uploaded successfully', filename=filename),
                "filename": filename,
                "distros": distros,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": _("Internal server error")}), 500


def _create_file_signature(filepath: str) -> None:
    """
    Create a digital signature for the given file.

    Args:
        filepath (str): Path to the file to be signed
    """
    private_key_path = "./certs/distro_pkey.key"

    # Load private key
    with open(private_key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(data=key_file.read(), password=None, backend=default_backend())

    # Read file data
    with open(filepath, "rb") as f:
        data = f.read()

    # Calculate signature
    signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    # Save detached signature
    signature_path = filepath + ".sig"
    with open(signature_path, "wb") as f:
        f.write(signature)


def get_distributes_list():
    """
    Get list of available distribution files.

    Returns only .img files that have corresponding .sig signature files,
    ensuring that all distributions are properly signed.

    Returns:
        List[str]: Sorted list of distribution filenames

    Note:
        Only returns files with both .img and .sig extensions
    """
    distro_dir = "./update_files/distros"

    try:
        files = os.listdir(distro_dir)

        # Get only .img files
        img_files = [f for f in files if f.endswith(".img")]

        # Filter .img files that have corresponding .sig files
        distros = [f for f in img_files if f + ".sig" in files]

        return sorted(distros)
    except OSError:
        return []


def get_kerio_version_from_filename(filename) -> str | None:
    """
    Extract Kerio Control version from filename.

    Args:
        filename (str): Distribution filename

    Returns:
        Optional[str]: Version string if found, None otherwise
    """
    pattern = r"^kerio-control-upgrade-(\d+\.\d+\.\d+-\d+).*"
    match = re.match(pattern=pattern, string=filename)

    if match:
        return match.group(1)

    return None


def is_update_available(request_data: dict) -> str:
    """
    Check if an update is available for the requested version.

    Compares the client's current version with the configured update version
    to determine if an update is available.

    Args:
        request_data (Dict[str, str]): Client request data containing version info
            Expected keys: prod_major, prod_minor, prod_build, prod_build_number

    Returns:
        str: Formatted response text for the client

    Note:
        Uses version mapping from ./data/kerio_control_versions.json
        Falls back to parsing version string if not found in mapping
    """
    mapping_file = "./data/kerio_control_versions.json"

    # Load version mapping
    with open(mapping_file, encoding="utf-8") as f:
        mapping = json.load(f)

    # Get update info from mapping or parse from version string
    update_version = config.kerio_control_update_version

    if update_version in mapping:
        update_info = mapping[update_version]
    else:
        # Parse version string like "9.5.0-8778"
        try:
            version_part, build_part = update_version.split("-")
            major, minor, build = version_part.split(".")
            update_info = {
                "prod_major": major,
                "prod_minor": minor,
                "prod_build": build,
                "prod_build_number": "9999",  # Default when parsing from string
                "description": f"Kerio Control {version_part} ({build_part})",
            }
        except ValueError:
            raise RuntimeError(f"Failed to parse version {update_version!r} and no mapping data available")

    # Compare versions directly as tuples
    current_version = (
        int(request_data["prod_major"]),
        int(request_data["prod_minor"]),
        int(request_data["prod_build"]),
        int(request_data["prod_build_number"]),
    )

    available_version = (
        int(update_info["prod_major"]),
        int(update_info["prod_minor"]),
        int(update_info["prod_build"]),
        int(update_info["prod_build_number"]),
    )

    # Compare tuples lexicographically
    if current_version >= available_version:
        response_text = f"--INFO--\nReminderId='1'\nReminderAuth='1'\nVersion='0'"
    else:
        response_text = (
            "--INFO--\n"
            f"ReminderId='1'\n"
            f"ReminderAuth='1'\n"
            "Version='1'\n"
            "LicenseUsageReceived='1'\n"
            "--VERSION_BEGIN--\n"
            f"PackageCode='KWF:{update_info["prod_major"].zfill(3)}.{update_info["prod_minor"].zfill(3)}.{update_info["prod_build"].zfill(5)}.T.000.000'\n"
            f"Description='{update_info["description"]}'\n"
            f"Comment='{update_info["description"]}'\n"
            f"DownloadURL='http://prod-update.kerio.com/control-update/distros/{config.kerio_control_update_file}'\n"
            "DownloadURLtext='Download from here!'\n"
            "InfoURL='https://support.keriocontrol.gfi.com'\n"
            "InfoURLtext='View more information!'\n"
            "--VERSION_END--"
        )

    return response_text

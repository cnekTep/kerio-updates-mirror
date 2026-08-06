import secrets
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from starlette.datastructures import FormData, UploadFile

from app.config import settings
from app.service.auth import AuthService
from app.service.distro import DistroService
from app.service.nginx_acl import NginxACLService, NginxACLValidationError
from app.utils.file_utils import delete_file, ensure_dir


@dataclass
class SettingsService:
    """
    Service layer for saving settings pages.

    Each method corresponds to a settings page (e.g. /settings/update)
    and is responsible for extracting, validating, and persisting form data.
    """

    nginx_acl_service: NginxACLService
    auth_service: AuthService
    distro_service: DistroService

    async def save(self, name: str, form: FormData) -> bool | None:
        """
        Dispatches form data to the appropriate save method by page name.

        Args:
            name: Settings page name (e.g. "update", "connection")
            form: Parsed form data from the request

        Returns:
            bool | None: True if auth settings were changed, and need to be redirected
        """
        handler = getattr(self, f"_save_{name}", None)
        if handler is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Settings page '{name}' not found",
            )
        return await handler(form)

    @staticmethod
    def _get(form: FormData, key: str, default: str = "") -> str:
        """
        Returns a string value from form data, ignoring UploadFile entries.
        Falls back to default if the key is missing or the value is not a plain string.

        Args:
            form: Parsed form data from the request
            key: Field name to look up
            default: Fallback value if field is absent or not a plain string
        """
        value = form.get(key)
        if isinstance(value, UploadFile) or value is None or value == "":
            return default
        return value

    @staticmethod
    def _bool(form: FormData, key: str) -> bool:
        """Returns True if checkbox field is present in form data."""
        return key in form

    @staticmethod
    def _validate_credentials(username: str, password: str, password_re: str) -> None:
        """
        Validates credentials for enabling authentication.

        Password is only required if None is set yet (i.e. on first setup);
        an empty password on subsequent saves means "keep the current one".

        Args:
            username: Username submitted in the form
            password: New password submitted in the form (may be empty)
            password_re: Password confirmation submitted in the form
        """

        if not username:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username is required"
            )
        if not password and not settings.security.password_hash:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password is required"
            )
        if password != password_re:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Passwords do not match"
            )

    async def _save_update(self, form: FormData) -> None:
        antivirus = self._get(form, "antivirus", "disabled")
        antispam = self._get(form, "antispam", "disabled")

        kerio_control_update_file = (
            self._get(form, "kerio_control_update_file") or "None"
        )
        kerio_control_update_version = (
            self.distro_service.extract_version(kerio_control_update_file)
            if kerio_control_update_file != "None"
            else "None"
        )

        data = {
            "updates.update_ids_3": self._bool(form, "update_ids_3"),
            "updates.update_ids_5": self._bool(form, "update_ids_5"),
            "updates.update_snort_template": self._bool(form, "update_snort_template"),
            "updates.update_geoip_4": self._bool(form, "update_geoip_4"),
            "updates.geoip_custom_url": self._bool(form, "geoip_custom_url"),
            "updates.update_geoip_5": self._bool(form, "update_geoip_5"),
            "updates.geoip_5_copy_geoname_id": self._bool(
                form, "geoip_5_copy_geoname_id"
            ),
            "updates.update_web_filter_key": self._bool(form, "update_web_filter_key"),
            "updates.update_shieldmatrix": self._bool(form, "update_shieldmatrix"),
            "updates.license_number": self._get(form, "license") or "None",
            "updates.license_number_last_update": (
                date.today()
                if self._get(form, "license") != settings.updates.license_number
                else settings.updates.license_number_last_update
            ),
            "updates.antivirus_url": self._get(form, "antivirus_url"),
            "updates.antispam_url": self._get(form, "antispam_url"),
            "updates.update_antivirus": antivirus != "disabled",
            "updates.antivirus_through_mirror": antivirus in {"proxy", "mirror"},
            "updates.antivirus_cache": antivirus == "mirror",
            "updates.update_antispam": antispam != "disabled",
            "updates.antispam_cache": antispam == "mirror",
            "updates.forced_web_filter_key": (
                self._get(form, "forced_web_filter_key_value")
                if self._bool(form, "forced_web_filter_key")
                else "None"
            )
            or "None",
            "updates.update_kerio_control_distro": self._bool(
                form, "update_kerio_control_distro"
            ),
            "updates.kerio_control_update_file": kerio_control_update_file,
            "updates.kerio_control_update_version": kerio_control_update_version,
        }

        # Delete version files when antivirus or antispam url changed
        files = ["versions.dat", "versions.id", "versions.sig"]
        checks = [
            ("antivirus_url", "antivirus_cache"),
            ("antispam_url", "antispam_cache"),
        ]

        for form_key, cache_dir_name in checks:
            if self._get(form, form_key) != getattr(settings.updates, form_key):
                cache_dir = ensure_dir(settings.updates.update_dir / cache_dir_name)
                for file in files:
                    delete_file(cache_dir / file)

        # Update settings
        settings.bulk_update(data)

    async def _save_connection(self, form: FormData) -> None:
        priority = form.getlist("download_priority")

        data = {
            "network.direct": self._bool(form, "direct"),
            "network.xray": self._bool(form, "xray"),
            "network.tor": self._bool(form, "tor"),
            "network.proxy": self._bool(form, "proxy"),
            "network.proxy_type": self._get(form, "proxy_type", "None"),
            "network.proxy_host": self._get(form, "proxy_host", "None"),
            "network.proxy_port": self._get(form, "proxy_port", "None"),
            "network.proxy_username": self._get(form, "proxy_username", "None"),
            "network.proxy_password": self._get(form, "proxy_password", "None"),
            "network.download_priority": ",".join(priority) if priority else "",
        }
        settings.bulk_update(data)

    async def _save_security(self, form: FormData) -> bool:
        auth = self._bool(form, "auth")
        username = self._get(form, "username")
        password = self._get(form, "password")
        password_re = self._get(form, "password_re")
        reload = False

        if auth:
            self._validate_credentials(
                username=username, password=password, password_re=password_re
            )
            data = {
                "security.auth": True,
                "security.username": username,
            }
            if password:
                data["security.password_hash"] = self.auth_service.hash_password(
                    password
                )
                reload = True
            if not settings.security.secret_key:
                data["security.secret_key"] = secrets.token_hex(32)
        else:
            data = {
                "security.auth": False,
                "security.username": None,
                "security.password_hash": None,
                "security.secret_key": None,
            }

        settings.bulk_update(data)

        try:
            self.nginx_acl_service.write(
                target="web",
                restricted="web_allowed_ips" in form,
                ip_list=self._get(form, "web_allowed_ips_list"),
            )
            self.nginx_acl_service.write(
                target="api",
                restricted="api_allowed_ips" in form,
                ip_list=self._get(form, "api_allowed_ips_list"),
            )
        except NginxACLValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid IP addresses: {', '.join(e.invalid)}",
            )

        return reload

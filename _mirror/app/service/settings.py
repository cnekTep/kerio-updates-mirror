import re
import secrets
from dataclasses import dataclass
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import HTTPException, status, BackgroundTasks
from starlette.datastructures import FormData, UploadFile

from app.config import settings
from app.service.auth import AuthService
from app.service.distro import DistroService
from app.service.license import LicenseService
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
    license_service: LicenseService

    async def save(
        self,
        name: str,
        form: FormData,
        background_tasks: BackgroundTasks,
        scheduler: AsyncIOScheduler | None = None,
    ) -> bool | None:
        """
        Dispatches form data to the appropriate save method by page name.

        Args:
            name: Settings page name (e.g. "update", "connection")
            form: Parsed form data from the request
            background_tasks: Background tasks to be executed after the request
            scheduler: AsyncIOScheduler for background tasks

        Returns:
            bool | None: True if auth settings were changed, and need to be redirected
        """
        handler = getattr(self, f"_save_{name}", None)
        if handler is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Settings page '{name}' not found",
            )
        if handler == self._save_update:
            return await handler(form, background_tasks, scheduler)
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
    def _get_list(form: FormData, key: str) -> list[str] | None:
        """
        Returns a list of string values from a comma-separated form field.
        Whitespace around each item is stripped. Ignores UploadFile entries.

        Args:
            form: Parsed form data from the request
            key: Field name to look up

        Returns:
            List of non-empty stripped strings, or None if the field is absent,
            empty, or not a plain string
        """
        value = form.get(key)
        if isinstance(value, UploadFile) or value is None or value == "":
            return None

        result = [e.strip() for e in value.split(",") if e.strip()]
        return result or None

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
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Username is required"
            )
        if not password and not settings.security.password_hash:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Password is required"
            )
        if password != password_re:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Passwords do not match"
            )

    @staticmethod
    def _parse_hhmm(value) -> tuple[int | None, int | None]:
        """
        Parses a "HH:MM" string into hours and minutes.

        Accepts one- or two-digit hours and minutes (e.g. "3:5", "03:05").
        Returns a two-tuple; on any invalid input (non-string, wrong format,
        out-of-range values) both items are None, so the result can always be
        unpacked safely: ``hour, minute = _parse_hhmm(value)``.

        Args:
            value: Raw form value to parse (any type; non-strings yield (None, None))

        Returns:
            Tuple ``(hour, minute)`` with ints in range 0..23 / 0..59,
            or ``(None, None)`` if the value is missing or invalid
        """
        m = re.fullmatch(
            r"(\d{1,2}):(\d{1,2})", value.strip() if isinstance(value, str) else ""
        )
        if not m:
            return None, None
        h, mm = int(m[1]), int(m[2])
        if h > 23 or mm > 59:
            return None, None
        return h, mm

    async def _save_update(
        self,
        form: FormData,
        background_tasks: BackgroundTasks,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        new_license = self._get(form, "license_number")
        # No license in settings (None) and an empty field are the same thing
        license_changed = new_license != (settings.updates.license_number or "")

        scheduler_full_update_hour, scheduler_full_update_minute = self._parse_hhmm(
            self._get(form, "autoupdate_time")
        )
        scheduler_changed = (
            scheduler_full_update_hour != settings.app.scheduler_full_update_hour
            or scheduler_full_update_minute != settings.app.scheduler_full_update_minute
        )

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
        kerio_connect_update_file_win = (
            self._get(form, "kerio_connect_update_file_win") or "None"
        )
        kerio_connect_update_version_win = (
            self.distro_service.extract_version(kerio_connect_update_file_win)
            if kerio_connect_update_file_win != "None"
            else "None"
        )
        kerio_connect_update_file_deb = (
            self._get(form, "kerio_connect_update_file_deb") or "None"
        )
        kerio_connect_update_version_deb = (
            self.distro_service.extract_version(kerio_connect_update_file_deb)
            if kerio_connect_update_file_deb != "None"
            else "None"
        )

        data = {
            "app.scheduler_full_update_hour": (
                scheduler_full_update_hour
                if scheduler_full_update_hour is not None
                else settings.app.scheduler_full_update_hour
            ),
            "app.scheduler_full_update_minute": (
                scheduler_full_update_minute
                if scheduler_full_update_minute is not None
                else settings.app.scheduler_full_update_minute
            ),
            "updates.update_ids_3": self._bool(form, "update_ids_3"),
            "updates.update_ids_5": self._bool(form, "update_ids_5"),
            "updates.update_geoip_4": self._bool(form, "update_geoip_4"),
            "updates.geoip_custom_url": self._bool(form, "geoip_custom_url"),
            "updates.update_geoip_5": self._bool(form, "update_geoip_5"),
            "updates.geoip_5_copy_geoname_id": self._bool(
                form, "geoip_5_copy_geoname_id"
            ),
            "updates.update_web_filter_key": self._bool(form, "update_web_filter_key"),
            "updates.update_shieldmatrix": self._bool(form, "update_shieldmatrix"),
            "updates.license_number": new_license or "None",
            "updates.license_exp_date": (
                "None"
                if license_changed
                else self._get(form, "license_exp_date") or "None"
            ),
            "updates.license_number_last_update": (
                date.today()
                if license_changed
                else settings.updates.license_number_last_update
            ),
            "updates.license_exp_date_autocheck": self._bool(
                form, "license_exp_date_autocheck"
            ),
            "updates.license_exp_date_mirror_update": self._bool(
                form, "license_exp_date_mirror_update"
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
            "updates.update_kerio_connect_distro": self._bool(
                form, "update_kerio_connect_distro"
            ),
            "updates.kerio_connect_update_file_win": kerio_connect_update_file_win,
            "updates.kerio_connect_update_version_win": kerio_connect_update_version_win,
            "updates.kerio_connect_update_file_deb": kerio_connect_update_file_deb,
            "updates.kerio_connect_update_version_deb": kerio_connect_update_version_deb,
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

        # Update license expiration date (in background)
        autocheck = settings.updates.license_exp_date_autocheck or self._bool(
            form, "license_exp_date_autocheck"
        )
        if new_license and license_changed and autocheck:
            background_tasks.add_task(
                self.license_service.update_expiration_date,
                license_number=new_license,
                notify=False,
            )
        # Update settings
        settings.bulk_update(data)

        # Update scheduler in real-time (if it changed)
        if (
            scheduler_changed
            and scheduler_full_update_hour is not None
            and scheduler_full_update_minute is not None
        ):
            if scheduler is not None:
                from app.utils.scheduler import reschedule_full_update

                reschedule_full_update(
                    scheduler, scheduler_full_update_hour, scheduler_full_update_minute
                )

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

        web_ips = self._get(form, "web_allowed_ips_list")
        api_ips = self._get(form, "api_allowed_ips_list")
        # Validate both lists before persisting anything, so invalid input
        # cannot leave settings half-saved
        invalid: list[str] = []
        for ip_list in (web_ips, api_ips):
            try:
                self.nginx_acl_service.validate(ip_list)
            except NginxACLValidationError as e:
                invalid.extend(e.invalid)
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid IP addresses: {', '.join(invalid)}",
            )

        data: dict[str, str | bool | None] = {
            "security.api_read_token": self._get(form, "api_read_token") or None,
            "security.api_write_token": self._get(form, "api_write_token") or None,
        }

        if auth:
            self._validate_credentials(
                username=username, password=password, password_re=password_re
            )
            data.update(
                {
                    "security.auth": True,
                    "security.username": username,
                }
            )
            if password:
                data["security.password_hash"] = self.auth_service.hash_password(
                    password
                )
                reload = True
            if not settings.security.secret_key:
                data["security.secret_key"] = secrets.token_hex(32)
        else:
            data.update(
                {
                    "security.auth": False,
                    "security.username": None,
                    "security.password_hash": None,
                    "security.secret_key": None,
                }
            )

        settings.bulk_update(data)

        self.nginx_acl_service.write(
            target="web", restricted="web_allowed_ips" in form, ip_list=web_ips
        )
        self.nginx_acl_service.write(
            target="api", restricted="api_allowed_ips" in form, ip_list=api_ips
        )

        return reload

    async def _save_notification(self, form: FormData) -> None:
        data = {
            "notification.email_enabled": self._bool(form, "email_enabled"),
            "notification.email_template": self._get(form, "email_template"),
            "email.email_to": self._get_list(form, "email_to"),
            "email.smtp_host": self._get(form, "smtp_host", "None"),
            "email.smtp_port": self._get(form, "smtp_port", "None"),
            "email.smtp_username": self._get(form, "smtp_username", "None"),
            "email.smtp_password": self._get(form, "smtp_password", "None"),
            "email.smtp_from": self._get(form, "smtp_from", "None"),
            "email.smtp_from_name": self._get(form, "smtp_from_name", "None"),
            "email.smtp_timeout": self._get(form, "smtp_timeout", "None"),
            "email.smtp_use_tls": self._bool(form, "smtp_use_tls"),
            "notification.telegram_enabled": self._bool(form, "telegram_enabled"),
            "telegram.bot_api_url": self._get(form, "bot_api_url", "None"),
            "telegram.bot_token": self._get(form, "bot_token", "None"),
            "telegram.chat_id": self._get(form, "chat_id", "None"),
            "notification.telegram_template": self._get(form, "telegram_template"),
            "telegram.thread_enabled": self._bool(form, "telegram_threads_enabled"),
            "telegram.thread_updates_id": self._get(form, "thread_updates_id", "None"),
            "telegram.thread_errors_id": self._get(form, "thread_errors_id", "None"),
        }
        settings.bulk_update(data)

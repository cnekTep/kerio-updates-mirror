import logging
import time
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import set_key
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class AppConfig(BaseModel):
    version: str = Field(description="Application version")
    config_reload_interval: float = Field(
        description="How often (seconds) workers poll .env mtime for changes",
    )
    scheduler_full_update_hour: int = Field(
        description="Hour (0-23) at which the full mirror update job runs daily"
    )
    scheduler_full_update_minute: int = Field(
        description="Minute (0-59) at which the full mirror update job runs daily"
    )


class RunConfig(BaseModel):
    host: str = Field(description="Host to run on")
    ports: int | list[int] = Field(description="Ports to run on")


class LoggingConfig(BaseModel):
    log_dir: Path = Field(description="Directory for logs")
    log_rotation_size_bytes: int = Field(
        description="Maximum log file size in bytes before archiving (default: 10MB)"
    )
    log_level: Literal["debug", "info", "warning", "error", "critical"] = Field(
        description="Log level"
    )
    log_format: str = Field(description="Log format")
    date_format: str = Field(description="Date format")
    log_ip: bool = Field(description="Log IP address in logs")
    debug: bool = Field(description="Enable debug mode")
    log_requests_body: bool = Field(description="Log requests body in debug mode")
    log_responses_body: bool = Field(description="Log responses body in debug mode")
    log_body_limit: int = Field(description="Log body limit in bytes")

    @property
    def log_level_value(self) -> int:
        return logging.getLevelNamesMapping()[self.log_level.upper()]

    def model_post_init(self, __context) -> None:
        """Called after model initialization to configure logging"""
        # Creating a directory for logs if it does not exist
        self.log_dir.mkdir(exist_ok=True)

        # Force configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level_value)

        # Remove existing handlers to avoid duplicates
        root_logger.handlers.clear()

        # Create console handler with formatting
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level_value)
        formatter = logging.Formatter(self.log_format, self.date_format)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)


class DatabaseConfig(BaseModel):
    url: str = Field(description="Database URL")
    echo: bool = Field(description="Enable log output for db requests")
    echo_pool: bool = Field(description="Enable log output for db pool")
    pool_size: int = Field(description="SQLAlchemy connection pool size")
    max_overflow: int = Field(
        description="Max extra connections allowed beyond pool_size"
    )

    # Alembic naming conventions
    naming_convention: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


class UpdatesConfig(BaseModel):
    update_dir: Path = Field(description="Directory for updates and cache files")
    license_number: str | None = Field(
        description="Kerio Control product license number for updates"
    )
    license_number_last_update: date | None = Field(
        description="Last update date of license number"
    )

    # Web Filter
    update_web_filter_key: bool = Field(description="Update web filter key")
    web_filter_key: str | None = Field(description="License key for web filter")
    web_filter_key_last_update: date | None = Field(
        description="Last update date of web filter key"
    )
    forced_web_filter_key: str | None = Field(
        description="Use this key instead web_filter_key (key from Kerio servers)"
    )

    # IDS/IPS Snort
    update_ids_3: bool = Field(
        description="Update IPS/IDS Snort system (Kerio Control < 9.5)"
    )
    ids_3_version: int | None = Field(description="Current version of IDS/IPS v3")
    ids_3_last_update: date | None = Field(description="Last update date of IDS/IPS v3")
    update_ids_5: bool = Field(
        description="Update IPS/IDS Snort system (Kerio Control >= 9.5)"
    )
    ids_5_version: int | None = Field(description="Current version of IDS/IPS v5")
    ids_5_last_update: date | None = Field(description="Last update date of IDS/IPS v5")
    ids_2_version: int | None = Field(description="Current version of IDS/IPS v2")
    ids_2_last_update: date | None = Field(description="Last update date of IDS/IPS v2")
    update_snort_template: bool = Field(description="Update Snort template")

    # GeoIP
    update_geoip_4: bool = Field(
        description="Update GeoIP database files (Kerio Control < 9.4.5)"
    )
    geoip_4_version: int | None = Field(description="Current version of GeoIP v4")
    geoip_4_last_update: date | None = Field(description="Last update date of GeoIP v4")
    update_geoip_5: bool = Field(
        description="Update GeoIP database files (Kerio Control >= 9.6.0)"
    )
    geoip_5_copy_geoname_id: bool = Field(
        description="Modify GeoIP database, copy geoname_id to registered_country_geoname_id"
    )
    geoip_5_version: int | None = Field(description="Current version of GeoIP v5")
    geoip_5_last_update: date | None = Field(description="Last update date of GeoIP v5")
    geoip_custom_url: bool = Field(description="Use custom GeoIP URL")
    geoip4_url: str = Field(description="GeoIP v4 URL")
    geoip6_url: str = Field(description="GeoIP v6 URL")
    geoloc_url: str = Field(description="GeoIP locations URL")

    # ShieldMatrix
    update_shieldmatrix: bool = Field(description="Update ShieldMatrix")
    shieldmatrix_link: str = Field(description="ShieldMatrix link to get updates URL")
    shieldmatrix_url: str = Field(description="ShieldMatrix update check URL")
    shieldmatrix_version_ttl: int = Field(
        description="How long (seconds) the shieldmatrix version is cached before re-downloading"
    )

    # Registration
    update_registration: bool = Field(description="Update Kerio registration")

    # Kerio Control distributive
    update_kerio_control_distro: bool = Field(
        description="Update Kerio Control distributive"
    )
    kerio_control_distro_versions_file: Path = Field(
        description="Kerio Control distributive versions mapping file"
    )
    kerio_control_update_file: str | None = Field(
        description="Kerio Control update filename"
    )
    kerio_control_update_version: str | None = Field(
        description="Kerio Control update version"
    )

    # Antivirus
    update_antivirus: bool = Field(description="Update antivirus")
    antivirus_url: str = Field(description="Kerio antivirus update check URL")
    antivirus_through_mirror: bool = Field(description="Use antivirus through mirror")
    antivirus_cache: bool = Field(description="Use cache to update antivirus")
    kerio_cdn_url: str | None = Field(
        description="Cached CDN base URL for antivirus updates, fetched from bdupdate.kerio.com"
    )
    kerio_cdn_url_cache_ttl: int = Field(
        description="Kerio CDN URL cache TTL (seconds)"
    )
    antivirus_version_ttl: int = Field(
        description="How long (seconds) the antivirus versions.* files are cached before re-downloading"
    )

    # Antispam
    update_antispam: bool = Field(description="Update antispam")
    antispam_url: str = Field(description="Kerio antispam update check URL")
    antispam_cache: bool = Field(description="Use cache to update antispam")
    antispam_version_ttl: int = Field(
        description="How long (seconds) the antispam versions.* files are cached before re-downloading"
    )


class NetworkConfig(BaseModel):
    direct: bool = Field(description="Use direct connection")

    # TOR settings
    tor: bool = Field(description="Use TOR")
    tor_host: str = Field(description="TOR host")
    tor_port: int = Field(description="TOR port")

    # Proxy settings
    proxy: bool = Field(description="Use proxy")
    proxy_type: str | None = Field(description="Proxy type: 'http' or 'socks5'")
    proxy_host: str | None = Field(description="Proxy host")
    proxy_port: int | None = Field(description="Proxy port")
    proxy_username: str | None = Field(description="Proxy username")
    proxy_password: str | None = Field(description="Proxy password")

    download_priority: str = Field(
        description="Preferred connection order for downloads (e.g. 'direct,tor,proxy')"
    )


class UserConfig(BaseModel):
    log_lines: int = Field(description="Number of log lines to display")


class SecurityConfig(BaseModel):
    nginx_acl_dir: Path = Field(description="Directory for nginx ACL files")
    auth: bool = Field(description="Enable basic auth")
    username: str | None = Field(description="Username for basic auth")
    password_hash: str | None = Field(description="Password hash for basic auth")
    secret_key: str | None = Field(description="Secret key for basic auth")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.default", ".env"),
        case_sensitive=False,
        env_prefix="APP_CONFIG__",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        env_parse_none_str="None",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    run: RunConfig = Field(default_factory=RunConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    updates: UpdatesConfig = Field(default_factory=UpdatesConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    user: UserConfig = Field(default_factory=UserConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    # Private attrs are not loaded from env and survive reassignment
    _env_mtime: float = PrivateAttr(default=0.0)
    _last_check: float = PrivateAttr(default=0.0)

    def model_post_init(self, __context: object) -> None:
        """Record mtime and check timestamp right after every (re)load."""
        self._env_mtime = self._read_env_mtime()
        self._last_check = time.monotonic()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_env_mtime(self) -> float:
        """Return mtime of the writable .env file, or 0.0 if it doesn't exist."""
        path = Path(self.model_config["env_file"][1])
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reinitialize settings from env files (all fields re-read)."""
        self.__init__()  # triggers model_post_init → _env_mtime / _last_check reset

    def reload_if_stale(self) -> None:
        """
        Reload settings if the .env file has been modified since last load.
        Throttled by config_reload_interval to avoid excessive stat() calls.
        """
        now = time.monotonic()
        # Fast path: check interval has not elapsed yet
        if now - self._last_check < self.app.config_reload_interval:
            return

        # Throttle window expired - do a real mtime check
        self._last_check = now
        current_mtime = self._read_env_mtime()
        if current_mtime != self._env_mtime:
            self.reload()

    def update(self, key_path: str, value: str | int | bool) -> None:
        """
        Update value in .env file and reinitialize settings

        Args:
            key_path: Dot-separated path to the setting (e.g., "updates.license_number")
            value: New value to set
        """
        env_key = self.model_config["env_prefix"] + key_path.upper().replace(".", "__")
        set_key(
            dotenv_path=Path(self.model_config["env_file"][1]),
            key_to_set=env_key,
            value_to_set=str(value),
            quote_mode="auto",
        )
        self.reload()

    def bulk_update(self, data: dict[str, str | int | bool]) -> None:
        """
        Update multiple values in .env file and reinitialize settings once.

        Args:
            data: Dict of dot-separated key paths to new values,
                  e.g. {"updates.license_number": "ABC", "updates.update_ids_5": True}
        """
        env_path = Path(self.model_config["env_file"][1])
        for key_path, value in data.items():
            env_key = self.model_config["env_prefix"] + key_path.upper().replace(
                ".", "__"
            )
            set_key(
                dotenv_path=env_path,
                key_to_set=env_key,
                value_to_set=str(value),
                quote_mode="auto",
            )
        self.reload()

    def get_auth_setting(self) -> bool:
        """Return the current auth setting."""
        return self.security.auth


settings = Settings()


def theme_context(request: Request) -> dict:
    """Injected into every template context: resolves theme from cookie,
    falling back to dark if the cookie is missing or has an invalid value."""
    theme = request.cookies.get("theme", "dark")
    return {"theme": theme if theme in ("dark", "light") else "dark"}


# Make templates accessible from anywhere via import
templates = Jinja2Templates(
    directory=BASE_DIR / "templates",
    context_processors=[theme_context],
)
# Add version to templates
templates.env.globals["version"] = settings.app.version
templates.env.globals["get_auth"] = settings.get_auth_setting

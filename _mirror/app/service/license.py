import re
from dataclasses import dataclass
from random import randint

from app.config import settings
from app.service.kerio_update import KerioUpdateService
from app.utils.app_logging import log_event
from app.utils.service_types import UpdateResult

# Format: NNNNN-XXXXX-XXXXX (first block digits, other blocks alphanumeric).
LICENSE_KEY_PATTERN = re.compile(
    r"^\d{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$",
    flags=re.IGNORECASE,
)


class LicenseError(Exception):
    """Base class for license-related errors."""


class InvalidLicenseKeyError(LicenseError):
    """Raised when the license key has an invalid format."""


class LicenseLookupError(LicenseError):
    """Raised when the license expiration date cannot be obtained from Kerio."""


@dataclass
class LicenseService:
    """
    Service layer for license key information.

    Validates the license key and fetches its expiration date from Kerio
    registration endpoints.
    """

    kerio_update_service: KerioUpdateService

    async def update_expiration_date(self, license_number: str, notify: bool):
        """
        Updates the license expiration date in the settings.

        Args:
            license_number: License key in format NNNNN-XXXXX-XXXXX.
            notify: Whether to notify the user of the update.

        Returns:
            UpdateResult: Result of the update operation.
        """
        log_event(
            log_type=["system"],
            message="License Key | Fetching license expiration date from Kerio server",
            notify=notify,
        )

        try:
            expiration_date = await self.get_expiration_date(license_number)
        except LicenseLookupError as exc:
            return self._fail(str(exc), notify=True)
        except Exception as exc:
            return self._fail(str(exc), notify=True)

        settings.update("updates.license_exp_date", expiration_date)
        return UpdateResult(
            success=True, message=f"License expiration date: {expiration_date}"
        )

    async def get_expiration_date(self, license_number: str) -> str:
        """
        Fetch license expiration date from Kerio.

        Args:
            license_number: License key in format NNNNN-XXXXX-XXXXX.

        Returns:
            Expiration date exactly as returned by Kerio.

        Raises:
            InvalidLicenseKeyError: If the license key format is invalid.
            LicenseLookupError: If Kerio did not return a token or an expiration date.
        """
        self.validate_license_key(license_number)

        # Random host id is used only to open a temporary registration session
        host_id = self._generate_host_id()

        connect_info = await self.kerio_update_service.get_registration_connect_info(
            client_ip=None,
            host_id=host_id,
            force_update=True,
        )
        kerio_token = connect_info.headers.get("x-kerio-token")
        if not kerio_token:
            raise LicenseLookupError("No Kerio token received")

        lookup_info = await self.kerio_update_service.get_registration_lookup_info(
            token=kerio_token,
            base_id=license_number,
            host_id=host_id,
        )
        expires = lookup_info.get("expires")
        if not expires:
            raise LicenseLookupError("No expiration date received")

        return expires

    @staticmethod
    def validate_license_key(license_key: str) -> None:
        """
        Validate license key format: NNNNN-XXXXX-XXXXX.
        (first block digits, other blocks alphanumeric, case-insensitive).

        Args:
                license_key: License key to validate.

        Raises:
            InvalidLicenseKeyError: If the format is invalid.
        """
        if not LICENSE_KEY_PATTERN.match(license_key):
            raise InvalidLicenseKeyError(
                "Invalid license key format. Expected format: NNNNN-XXXXX-XXXXX"
            )

    @staticmethod
    def _generate_host_id() -> str:
        """Generate a random MAC-like host id, e.g. 'A1:0F:3C:22:9B:E4'."""
        return ":".join(f"{randint(0, 255):02X}" for _ in range(6))

    @staticmethod
    def _fail(message: str, notify: bool) -> UpdateResult:
        """Log a failure and return it."""
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="License",
        )
        return UpdateResult(success=False, message=message)

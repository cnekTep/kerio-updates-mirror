import re
from datetime import date

from app.config import settings
from app.utils.app_logging import log_event
from app.utils.internet_utils import make_request_with_retries
from app.utils.service_types import UpdateResult

# Substrings in the Kerio response body that mean "the license is no longer
# usable" -> key must be reset. Each marker doubles as the error label used
# in the log/error message.
_LICENSE_ERRORS: tuple[str, ...] = (
    "Invalid product license",
    "Product Software Maintenance expired",
    "Unknown product license",
)


class WebFilterService:
    """
    Service layer for web filter operations.

    Handles business logic related to web filter key management,
    acting as an intermediary between the API layer and data repository.
    """

    async def update_web_filter_key(self, notify: bool = True) -> UpdateResult:
        """
        Updates Web Filter key by fetching it from Kerio server

        Args:
            notify (bool, optional): Whether to notify on failure.

        Returns:
            UpdateResult: success flag and a message describing the result
            (e.g. "Web Filter Key Update | Received key: x:xx:xxxxxx:xxxxxxxxxx:xxxxx").
        """
        if not settings.updates.license_number:
            return self._fail_and_clear_license(
                message=(
                    "Web Filter Key Update | Error: "
                    "License key is not configured, web filter key removed"
                ),
                notify=notify,
                clear_key=False,
            )

        log_event(
            log_type=["system"],
            message="Web Filter Key Update | Fetching Web Filter key from Kerio server",
        )

        url = f"https://wf-activation.kerio.com/getkey.php"
        params = {
            "id": settings.updates.license_number,
        }
        headers = {
            "accept": "*/*",
            "host": "wf-activation.kerio.com",
        }

        response = await make_request_with_retries(
            url=url,
            params=params,
            headers=headers,
            context="Web Filter Key Update",
        )

        if not response:
            return self._fail(
                message=(
                    "Web Filter Key Update | Error: "
                    "Failed to fetch Web Filter key from Kerio server"
                ),
                notify=notify,
            )

        # Any of the known license errors -> reset stored license/key
        license_error = self._match_license_error(response.text)
        if license_error is not None:
            return self._fail_and_clear_license(
                message=(
                    f"Web Filter Key Update | Error: {license_error}: "
                    f"{settings.updates.license_number}, web filter key removed"
                ),
                notify=notify,
                clear_key=True,
            )

        wfkey = response.text.strip()

        if not self._is_valid_web_filter_key(wfkey):
            return self._fail(
                message=(
                    "Web Filter Key Update | Error: "
                    f"Received key has invalid format, skipping update: {wfkey}"
                ),
                notify=notify,
            )

        message = f"Web Filter Key Update | Received key: {wfkey}"
        log_event(
            log_type=["system", "updates"],
            message=message,
        )
        settings.bulk_update(
            {
                "updates.web_filter_key": wfkey,
                "updates.web_filter_key_last_update": date.today(),
            }
        )
        return UpdateResult(success=True, message=message)

    @staticmethod
    def _match_license_error(response_text: str) -> str | None:
        """Return the first known license error marker present in the response."""
        for marker in _LICENSE_ERRORS:
            if marker in response_text:
                return marker
        return None

    @staticmethod
    def _fail(message: str, notify: bool) -> UpdateResult:
        """Log a failure and return it, without touching stored settings."""
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="Web Filter Update",
        )
        return UpdateResult(success=False, message=message)

    @staticmethod
    def _fail_and_clear_license(
        message: str,
        notify: bool,
        clear_key: bool,
    ) -> UpdateResult:
        """Log a failure and reset the stored license number (and key, if requested)."""
        log_event(
            log_type=["system", "updates", "errors"],
            message=message,
            notify=notify,
            action_name="Web Filter Update",
        )

        update = {
            "updates.license_number": None,
            "updates.web_filter_key_last_update": date.today() if clear_key else None,
        }
        if clear_key:
            update["updates.web_filter_key"] = None
        settings.bulk_update(update)

        if clear_key:
            # Reload settings to apply changes
            settings.reload()

        return UpdateResult(success=False, message=message)

    @staticmethod
    def _is_valid_web_filter_key(key: str) -> bool:
        """Validate Kerio Web Filter key format"""
        pattern = re.compile(
            pattern=r"0:[a-z]{2}:[a-f0-9]{4,6}:[0-9]{1,15}:[0-9]{5,6}",
            flags=re.IGNORECASE,
        )
        return bool(pattern.fullmatch(key))

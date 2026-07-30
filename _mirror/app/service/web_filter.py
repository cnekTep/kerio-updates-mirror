import re
from datetime import date

from app.config import settings
from app.utils.app_logging import write_log
from app.utils.internet_utils import make_request_with_retries


class WebFilterService:
    """
    Service layer for web filter operations.

    Handles business logic related to web filter key management,
    acting as an intermediary between the API layer and data repository.
    """

    async def update_web_filter_key(self) -> None:
        """Updates Web Filter key by fetching it from Kerio server"""
        if not settings.updates.license_number:
            write_log(
                log_type=["system", "updates"],
                message=(
                    "Web Filter Key Update | "
                    "License key is not configured, web filter key removed"
                ),
            )
            settings.bulk_update(
                {
                    "updates.license_number": None,
                    "updates.web_filter_key_last_update": None,
                }
            )
            return

        write_log(
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
            write_log(
                log_type=["system", "updates"],
                message=(
                    "Web Filter Key Update | "
                    "Failed to fetch Web Filter key from Kerio server"
                ),
            )
            return

        if "Invalid product license" in response.text:
            write_log(
                log_type=["system", "updates"],
                message=(
                    f"Web Filter Key Update | "
                    f"Invalid product license: "
                    f"{settings.updates.license_number}, web filter key removed"
                ),
            )
            settings.bulk_update(
                {
                    "updates.license_number": None,
                    "updates.web_filter_key": None,
                    "updates.web_filter_key_last_update": date.today(),
                }
            )
            return

        if "Product Software Maintenance expired" in response.text:
            write_log(
                log_type=["system", "updates"],
                message=(
                    f"Web Filter Key Update | License key expired: "
                    f"{settings.updates.license_number}, web filter key removed"
                ),
            )
            settings.bulk_update(
                {
                    "updates.license_number": None,
                    "updates.web_filter_key": None,
                    "updates.web_filter_key_last_update": date.today(),
                }
            )
            return

        wfkey = response.text.strip()

        if not self._is_valid_web_filter_key(wfkey):
            write_log(
                log_type=["system", "updates", "errors"],
                message=(
                    "Web Filter Key Update | "
                    f"Received key has invalid format, skipping update: {wfkey}"
                ),
            )
            return

        write_log(
            log_type=["system", "updates"],
            message=f"Web Filter Key Update | Received key: {wfkey}",
        )
        settings.bulk_update(
            {
                "updates.web_filter_key": wfkey,
                "updates.web_filter_key_last_update": date.today(),
            }
        )

    @staticmethod
    def _is_valid_web_filter_key(key: str) -> bool:
        """Validate Kerio Web Filter key format"""
        pattern = re.compile(
            pattern=r"0:[a-z]{2}:[a-f0-9]{4,6}:[0-9]{1,15}:[0-9]{5,6}",
            flags=re.IGNORECASE,
        )
        return bool(pattern.fullmatch(key))

import os
from typing import Any, Dict

from dotenv import load_dotenv, set_key


class Config:
    """
    Configuration class that automatically loads and saves
    values to .env file when attributes are changed.
    """

    def __init__(self, env_path: str = ".env"):
        """
        Initialize configuration.

        Args:
            env_path: Path to .env file
        """
        self.env_path = env_path
        self._data: Dict[str, Any] = {}

        # Default values
        self._defaults = {
            "LOCALE": "en",  # Locale
            "DB": "mirror.db",  # Database path
            "LICENSE_NUMBER": None,  # License number
            "PROXY": True,  # Use proxy or not
            "PROXY_HOST": "172.222.0.5",  # Proxy host
            "PROXY_PORT": "8118",  # Proxy port
            "PROXY_LOGIN": None,  # Proxy login (if required)
            "PROXY_PASSWORD": None,  # Proxy password (if required)
            "UPDATE_WEB_FILTER_KEY": False,  # Whether to update Web Filter key
            "UPDATE_IDS_1": False,  # Update IPS/IDS Snort system (Windows version)
            "UPDATE_IDS_2": False,  # Update compromised address lists for blocking
            "UPDATE_IDS_3": False,  # Update IPS/IDS Snort system (Linux version up to 9.5)
            "UPDATE_IDS_4": False,  # Update GeoIP databases for geolocation/visitor blocking
            "UPDATE_IDS_5": False,  # Update IPS/IDS Snort system (Linux version 9.5+)
            "GEOIP_GITHUB": False,  # Use GitHub as a source for GeoIP database updates
            "GEOIP4_URL": "https://raw.githubusercontent.com/wyot1/GeoLite2-Unwalled/downloads/COUNTRY/CSV/GeoLite2-Country-Blocks-IPv4.csv",
            "GEOIP6_URL": "https://raw.githubusercontent.com/wyot1/GeoLite2-Unwalled/downloads/COUNTRY/CSV/GeoLite2-Country-Blocks-IPv6.csv",
            "GEOLOC_URL": "https://raw.githubusercontent.com/wyot1/GeoLite2-Unwalled/downloads/COUNTRY/CSV/GeoLite2-Country-Locations-en.csv",
            "ALLOWED_IPS": "",  # Comma-separated list of allowed IP addresses, e.g. "1.1.1.1.1, 8.8.8.8.8"
            "IP_LOGGING": True,  # Enable IP logging
        }

        # Create .env file if it doesn't exist
        if not os.path.exists(env_path):
            with open(env_path, "a"):
                pass

        # Load environment variables from .env file
        load_dotenv(env_path)

        # Initialize configuration
        self._load_config()

    def _load_config(self) -> None:
        """
        Load configuration from .env file and set default values for missing entries.
        """
        missing_vars = {}

        # Apply values from file or use default values
        for key, default_value in self._defaults.items():
            env_value = os.environ.get(key)

            if env_value is not None:
                # Converting values from .env
                if env_value.lower() == "true":
                    self._data[key.lower()] = True
                elif env_value.lower() == "false":
                    self._data[key.lower()] = False
                elif env_value.lower() == "none":
                    self._data[key.lower()] = None
                else:
                    self._data[key.lower()] = env_value
            else:
                self._data[key.lower()] = default_value  # Setting the default value
                missing_vars[key] = self._format_value(default_value)  # Mark it for saving in .env

        # Write missing variables to .env file
        for key, value in missing_vars.items():
            set_key(dotenv_path=self.env_path, key_to_set=key, value_to_set=value)

    def __getattr__(self, name: str) -> Any:
        """
        Intercept access to non-existent attributes.

        Args:
            name: Attribute name

        Returns:
            Value from configuration

        Raises:
            AttributeError: If attribute doesn't exist in configuration
        """
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'Config' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Intercept attribute setting and update .env file.

        Args:
            name: Attribute name
            value: New value
        """
        # Skip special attributes and class attributes
        if name.startswith("_") or name == "env_path":
            super().__setattr__(name, value)
            return

        # For regular attributes update _data and .env file
        self._data[name] = value

        # Update .env file
        env_key = name.upper()
        set_key(dotenv_path=self.env_path, key_to_set=env_key, value_to_set=self._format_value(value))

    @staticmethod
    def _format_value(value: Any) -> str:
        """
        Format value for writing to .env file.

        Args:
            value: Any Python value

        Returns:
            String representation suitable for .env file
        """
        if value is None:
            return "None"
        return str(value)


# Single configuration instance that will be imported by other modules
config = Config()

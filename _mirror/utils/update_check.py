import json
import os
from datetime import datetime

from flask_babel import gettext as _

from utils.app_logging import write_log
from utils.internet_utils import make_request_with_retries


class UpdateChecker:
    def __init__(
        self,
        github_user: str = "cnekTep",
        github_repo: str = "kerio-updates-mirror",
        version_file: str = "data/versions.json",
        results_file: str = "data/update_check_results.json",
    ):
        """
        Initialize the UpdateChecker class.

        Args:
            github_user: GitHub username
            github_repo: GitHub repository
            version_file: Name of the version file
            results_file: File to store update check results
        """
        self.github_user = github_user
        self.github_repo = github_repo
        self.version_file = version_file
        self.results_file = results_file

    def get_current_version(self) -> str | None:
        """Get the current app version from the version file"""
        try:
            with open(self.version_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data[0]["version"]
        except Exception as err:
            write_log(log_type="system", message=f"Error fetching current version: {err}")
            return None

    def get_remote_versions(self) -> dict | None:
        """
        Get the remote versions from the GitHub repository.

        Returns:
            Dictionary of remote versions or None if an error occurs
        """
        url = (
            f"https://raw.githubusercontent.com/{self.github_user}/{self.github_repo}/main/_mirror/{self.version_file}"
        )

        try:
            response = make_request_with_retries(url=url, context="check for mirror updates")
            return response.json()
        except Exception as err:
            write_log(log_type="system", message=f"Error fetching remote versions: {err}")
            return None

    def check_for_updates(self, save_results=True) -> list | bool:
        remote_versions = self.get_remote_versions()
        current_version = self.get_current_version()

        result = {
            "timestamp": datetime.now().isoformat(),
            "current_version": current_version,
            "has_updates": False,
            "latest_version": None,
            "changes": [],
        }

        if remote_versions and current_version:
            latest_version = remote_versions[0]["version"]
            result["latest_version"] = latest_version

            if latest_version > current_version:
                result["has_updates"] = True
                changes = []
                for entry in remote_versions:
                    if entry["version"] > current_version:
                        changes.append({"version": entry["version"], "description": entry["description"]})
                result["changes"] = changes

        # Save results to file
        if save_results:
            self._save_results(result)

        return result["changes"] if result["has_updates"] else False

    def _save_results(self, results) -> None:
        """Save update check results to file"""
        try:
            with open(self.results_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        except Exception as err:
            write_log(log_type="system", message=f"Error saving update results: {err}")

    def get_latest_results(self) -> dict | None:
        """Get the latest update check results"""
        try:
            if os.path.exists(self.results_file):
                with open(self.results_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # If the latest version is not available, return that update is not available
                    if not data["latest_version"]:
                        write_log(
                            log_type="system",
                            message=_("Error reading update results: can't get latest version from GitHub"),
                        )
                        data["has_updates"] = False
                        return data
                    #  If the latest version is greater than the current version, return that update is available
                    data["has_updates"] = data["latest_version"] > self.get_current_version()
                    return data
            return {
                "timestamp": None,
                "current_version": self.get_current_version(),
                "has_updates": False,
                "latest_version": None,
                "changes": [],
            }
        except Exception as err:
            write_log(log_type="system", message=f"Error reading update results: {err}")
            return None

    def manual_update_check(self) -> dict | None:
        self.check_for_updates()
        return self.get_latest_results()


checker = UpdateChecker()

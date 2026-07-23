import ipaddress

from app.config import settings
from app.utils.file_utils import ensure_dir


class NginxACLValidationError(ValueError):
    """Raised when the IP list contains invalid entries."""

    def __init__(self, invalid: list[str]) -> None:
        self.invalid = invalid
        super().__init__(f"Invalid IP entries: {', '.join(invalid)}")


class NginxACLService:
    """
    Service layer for reading and writing nginx ACL (allow/deny) configuration files.

    File format:
        allow all;            - all IPs are allowed
        allow 172.16.0.1;     - specific IP allowed
        allow 172.16.0.0/24;  - CIDR network allowed

    Sorting order on write: networks (CIDR) first, then hosts - both groups sorted numerically.
    """

    def read(self, target: str) -> tuple[bool, str]:
        """
        Reads an ACL file and returns the restriction state and IP list.

        Args:
            target: "web" or "api"

        Returns:
            Tuple of (restricted, ip_list_string) where:
                restricted - False if "allow all;" is the first directive,
                             True otherwise
                ip_list_string - comma-separated IPs/CIDRs, excluding "allow all;"
        """
        path = settings.security.nginx_acl_dir / f"allowed_ips_{target}.conf"
        if not path.exists():
            return False, ""

        lines = path.read_text(encoding="utf-8").splitlines()

        # Filter out empty lines and comments
        relevant_lines = [
            line for line in lines if line.strip() and not line.strip().startswith("#")
        ]

        # Extract IP values from directives, skipping non-matching lines
        entries = [ip for line in relevant_lines if (ip := self._parse_directive(line))]

        if entries and entries[0] == "all":
            return False, ", ".join(entries[1:])

        return True, ", ".join(entries)

    def write(self, target: str, restricted: bool, ip_list: str) -> None:
        """
        Validates, sorts, and writes an ACL file.

        If restricted is False - prepends "allow all;" but keeps the IP list
        intact so it's preserved for when restriction is re-enabled.

        Args:
            target: "web" or "api"
            restricted: True to restrict to listed IPs, False to allow all
            ip_list: Raw user input - IPs/CIDRs separated by commas, spaces, or newlines

        Raises:
            NginxACLValidationError: if any token is not a valid IP or CIDR
        """
        path = (
            ensure_dir(settings.security.nginx_acl_dir) / f"allowed_ips_{target}.conf"
        )

        tokens = self._tokenize(ip_list)
        valid, invalid = self._validate(tokens)

        if invalid:
            raise NginxACLValidationError(invalid)

        lines: list[str] = []

        if not restricted:
            lines.append("allow all;")

        lines.extend(f"allow {entry};" for entry in self._sort(valid))

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _parse_directive(line: str) -> str:
        """
        Extracts the value from a single nginx allow directive.
        Returns empty string if the line doesn't match.

        Args:
            line: Raw line, e.g. "allow 10.0.0.1;"
        """
        line = line.strip()
        if line.startswith("allow ") and line.endswith(";"):
            return line[len("allow ") : -1].strip()
        return ""

    @staticmethod
    def _tokenize(raw: str) -> list[str]:
        """
        Splits raw user input into deduplicated tokens.
        Accepts comma, semicolon, newline, or whitespace as delimiters.

        Args:
            raw: Raw user input string
        """
        normalized = raw.replace(",", " ").replace(";", " ")
        tokens = normalized.split()
        return list(dict.fromkeys(tokens))

    @staticmethod
    def _validate(tokens: list[str]) -> tuple[list[str], list[str]]:
        """
        Validates each token as an IPv4/IPv6 address or CIDR network.
        Returns (valid, invalid) lists.

        Args:
            tokens: List of raw IP/CIDR strings
        """
        valid, invalid = [], []
        for token in tokens:
            try:
                ipaddress.ip_network(token, strict=False)
                valid.append(token)
            except ValueError:
                invalid.append(token)
        return valid, invalid

    @staticmethod
    def _sort(entries: list[str]) -> list[str]:
        """
        Sorts entries: CIDR networks first, then host IPs - both groups sorted numerically.

        Args:
            entries: List of validated IP/CIDR strings
        """
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        hosts: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []

        for entry in entries:
            net = ipaddress.ip_network(entry, strict=False)
            if net.num_addresses == 1:
                hosts.append(net.network_address)
            else:
                networks.append(net)

        networks.sort()
        hosts.sort()

        return [n.compressed for n in networks] + [h.compressed for h in hosts]

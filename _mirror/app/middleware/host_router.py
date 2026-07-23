from starlette.types import ASGIApp, Receive, Scope, Send


class HostRoutingMiddleware:
    """
    Middleware for routing specific URL paths to internal API endpoints.

    Routes:
      - bda-update.kerio.com                     -> /api/kerio/updates/antispam/files/*
      - bdupdate.kerio.com/...?product...        -> /api/kerio/updates/antivirus/link
      - .../v2/repository/...                    -> /api/kerio/updates/antivirus/files/*
      - wf-activation.kerio.com                  -> /api/kerio/updates/webfilter/key
      - ids-update.kerio.com                     -> /api/kerio/updates/ids/link | /api/kerio/updates/geoip/link
      - download.kerio.com                       -> /api/kerio/updates/ids/files/*
      - shieldmatrix-updates.gfikeriocontrol.com -> /api/kerio/updates/shieldmatrix/link
      - register.kerio.com                       -> /api/kerio/updates/registration
      - prod-update.kerio.com/checknew.php       -> /api/kerio/updates/distributive/check
    """

    # Base path for all Kerio API routes
    ANTISPAM_API_BASE = "/api/kerio/updates/antispam"
    ANTIVIRUS_API_BASE = "/api/kerio/updates/antivirus"
    GEOIP_API_BASE = "/api/kerio/updates/geoip"
    IDS_API_BASE = "/api/kerio/updates/ids"
    WEBFILTER_API_BASE = "/api/kerio/updates/webfilter"
    SHIELDMATRIX_API_BASE = "/api/kerio/updates/shieldmatrix"
    DISTRIBUTIVE_API_BASE = "/api/kerio/updates/distro"
    REGISTRATION_API_BASE = "/api/kerio/updates/registration"

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            self._rewrite_path(scope)

        await self.app(scope, receive, send)

    def _rewrite_path(self, scope: Scope) -> None:
        """Rewrite scope['path'] based on hostname and path routing rules."""

        # examples:
        #   antispam:       bda-update.kerio.com/as-thin-sdk-win-x86_64/versions.id
        #                   bda-update.kerio.com/v2/repository/4/1/C/9/ace.am.41c9d20c61c98415feb47ad9641ef08a.gzip
        #
        #   antivirus:      bdupdate.kerio.com/update.php?id=12345-ABCDE&product=KWF&version=9.5.0-T3-9017
        #                   bdupdate.kerio.com/v2/repository/4/1/C/9/ace.am.41c9d20c61c98415feb47ad9641ef08a.gzip
        #
        #   geoip:          ids-update.kerio.com/update.php?id=12345-ABCDE-FGHIJ&version=4.0&tag=
        #                   ids-update.kerio.com/geoip/update.php?id=12345-ABCDE-FGHIJ&version=5.0&tag=
        #
        #   ids v2:         ids-update.kerio.com/update.php?id=12345-ABCDE-FGHIJ&version=2.0&tag=
        #   ids v3:         ids-update.kerio.com/update.php?id=12345-ABCDE-FGHIJ&version=3.0&tag=
        #   ids v5:         ids-update.kerio.com/update.php?id=12345-ABCDE-FGHIJ&version=5.0&tag=
        #
        #   snort template: download.kerio.com/control-update/config/v1/snort.tpl.md5
        #
        #   shieldmatrix:   shieldmatrix-updates.gfikeriocontrol.com/check_update/?client-id=control&version=9.5.0&last-update=0
        #
        #   web filter:     wf-activation.kerio.com/getkey.php?id=78688-GTIKA
        #
        #   distributive:   prod-update.kerio.com/checknew.php {form-data}
        #
        #   registration:   register.kerio.com/registration/LD.php

        url_path: str = scope["path"]
        url_hostname = self._get_hostname(scope)
        query_params = self._get_query_params(scope)

        match url_hostname:
            case "bda-update.kerio.com":  # Antispam
                scope["path"] = f"{self.ANTISPAM_API_BASE}/files{url_path}"

            case "bdupdate.kerio.com":  # Antivirus
                # Route antivirus get update link requests
                if query_params.get("product"):
                    scope["path"] = f"{self.ANTIVIRUS_API_BASE}/link"

            # Route antivirus file download requests
            case _ if url_path.startswith("/v2/repository/"):
                scope["path"] = f"{self.ANTIVIRUS_API_BASE}/files{url_path}"

            case "ids-update.kerio.com":  # IDS/IPS and GeoIP
                # Route GeoIP get update link requests
                if url_path.startswith("/geoip/") or query_params.get(
                    "version", ""
                ).startswith("4."):
                    scope["path"] = f"{self.GEOIP_API_BASE}/link"
                else:
                    # Route IDS/IPS get update link requests
                    scope["path"] = f"{self.IDS_API_BASE}/link"

            case "download.kerio.com":  # IDS/IPS Snort template
                file_name = url_path.split("/")[-1]
                scope["path"] = f"{self.IDS_API_BASE}/files/{file_name}"

            case "shieldmatrix-updates.gfikeriocontrol.com":  # ShieldMatrix
                scope["path"] = f"{self.SHIELDMATRIX_API_BASE}/link"

            case "wf-activation.kerio.com":  # Web filter
                scope["path"] = f"{self.WEBFILTER_API_BASE}/key"

            case "prod-update.kerio.com":  # Distributive
                scope["path"] = f"{self.DISTRIBUTIVE_API_BASE}/check"

            case "register.kerio.com":  # Registration
                scope["path"] = f"{self.REGISTRATION_API_BASE}"

    @staticmethod
    def _get_hostname(scope: Scope) -> str:
        """Extract hostname from Host header, stripping port if present."""
        host_header = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == b"host"),
            "",
        )
        return host_header.split(":")[0]

    @staticmethod
    def _get_query_params(scope: Scope) -> dict[str, str]:
        """Parse query string into a key-value dict. Duplicate keys: first value wins."""
        raw_query: bytes = scope.get("query_string", b"")
        if not raw_query:
            return {}
        params: dict[str, str] = {}
        for pair in raw_query.decode("latin-1").split("&"):
            if "=" in pair:
                k, _, v = pair.partition("=")
                params[k] = v
        return params

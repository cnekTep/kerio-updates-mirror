FROM alpine:3.24.1

# ── Dependencies ──────────────────────────────────────────────────────────────
#   curl            - ETag-based conditional geodata download
#   jq              - JSON processing for merge-routing.sh
#   su-exec         - privilege drop before starting xray
#   tzdata          - timezone support
#   ca-certificates - TLS root certs for xray outbound connections
RUN apk add --no-cache curl jq su-exec tzdata ca-certificates

# ── User ──────────────────────────────────────────────────────────────────────
# Dedicated non-root user (uid 65532 matches official XTLS image)
RUN addgroup -g 65532 -S xray && adduser -u 65532 -S -G xray xray

# ── Binaries ──────────────────────────────────────────────────────────────────
# Place the xray binary next to this Dockerfile before building
COPY xray /usr/local/bin/xray
RUN chmod +x /usr/local/bin/xray

# ── Scripts ───────────────────────────────────────────────────────────────────
# Copy scripts and set executable bit
COPY update-geodata.sh  /usr/local/bin/update-geodata.sh
COPY merge-routing.sh   /usr/local/bin/merge-routing.sh
COPY entrypoint.sh      /entrypoint.sh
RUN chmod +x /usr/local/bin/update-geodata.sh \
             /usr/local/bin/merge-routing.sh \
             /entrypoint.sh

# ── Directories ───────────────────────────────────────────────────────────────
# Create directories with correct ownership
# geodata and logs - xray-owned (xray process reads/writes them after privilege drop)
# confs            - root-owned (entrypoint writes routing.json, then drops privs)
RUN mkdir -p /usr/local/share/xray /usr/local/etc/xray /var/log/xray \
    && chown xray:xray /usr/local/share/xray /var/log/xray

VOLUME /usr/local/share/xray
VOLUME /usr/local/etc/xray
VOLUME /var/log/xray

# ── Environment ───────────────────────────────────────────────────────────────
ENV CONFS_DIR=/usr/local/etc/xray
ENV GEODATA_DIR=/usr/local/share/xray
ENV DOMAIN_STRATEGY=AsIs
ENV GEOIP_URL=https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/geoip.dat
ENV GEOSITE_URL=https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/geosite.dat

ENTRYPOINT ["/entrypoint.sh"]

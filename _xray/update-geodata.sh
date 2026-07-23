#!/bin/sh
# update-geodata.sh
# Downloads geoip.dat and geosite.dat only if they have changed (ETag-based).
# Stores ETags in sidecar .etag files next to the dat files.
# On download failure keeps the existing file and exits cleanly.

set -e

# ── Config ────────────────────────────────────────────────────────────────────
GEODATA_DIR="${GEODATA_DIR:-/usr/local/share/xray}"
GEOIP_URL="${GEOIP_URL:-https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/geoip.dat}"
GEOSITE_URL="${GEOSITE_URL:-https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/geosite.dat}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { printf "${GREEN}[geodata]${NC} %s\n" "$1"; }
log_warn()  { printf "${YELLOW}[geodata] WARN:${NC} %s\n" "$1"; }
log_error() { printf "${RED}[geodata] ERROR:${NC} %s\n" "$1" >&2; }

# ── Functions ─────────────────────────────────────────────────────────────────
download_if_changed() {
  NAME="$1"
  URL="$2"
  DEST="$GEODATA_DIR/$NAME"
  ETAG_FILE="$GEODATA_DIR/$NAME.etag"

  # Fetch remote ETag via HEAD request only (no data transfer)
  REMOTE_ETAG=$(curl -sI --connect-timeout 5 --max-time 10 "$URL" \
    | grep -i "^etag:" | tr -d '\r\n' | awk '{print $2}')

  if [ -z "$REMOTE_ETAG" ]; then
    log_warn "$NAME: could not get ETag from server, skipping update"
    return 0
  fi

  # Compare with locally saved ETag
  LOCAL_ETAG=""
  [ -f "$ETAG_FILE" ] && LOCAL_ETAG=$(cat "$ETAG_FILE")

  if [ "$REMOTE_ETAG" = "$LOCAL_ETAG" ] && [ -f "$DEST" ]; then
    log_info "$NAME: up to date, skipping download"
    return 0
  fi

  # Download to a temp file, then atomically replace
  log_info "$NAME: downloading from $URL ..."
  TMP="$DEST.tmp"
  if curl -fsSL --connect-timeout 10 --max-time 120 "$URL" -o "$TMP"; then
    mv "$TMP" "$DEST"
    echo "$REMOTE_ETAG" > "$ETAG_FILE"
    log_info "$NAME: updated successfully"
  else
    rm -f "$TMP"
    if [ -f "$DEST" ]; then
      log_warn "$NAME: download failed, keeping existing file"
    else
      log_error "$NAME: download failed and no existing file found"
      return 1
    fi
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
mkdir -p "$GEODATA_DIR"

download_if_changed "geoip.dat"   "$GEOIP_URL"
download_if_changed "geosite.dat" "$GEOSITE_URL"

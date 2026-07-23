#!/bin/sh
# entrypoint.sh
# Runs as root:
#   1. Downloads/updates geodata (ETag-based, skips if unchanged, keeps old on failure)
#   2. Verifies geodata files exist before starting xray
#   3. Merges routing rules if confs/rules/ directory exists
#   4. Drops privileges to xray:xray and starts xray

set -e

# ── Config ────────────────────────────────────────────────────────────────────
GEODATA_DIR="${GEODATA_DIR:-/usr/local/share/xray}"
CONFS_DIR="${CONFS_DIR:-/usr/local/etc/xray}"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
log_info()  { printf "${GREEN}[entrypoint]${NC} %s\n" "$1"; }
log_error() { printf "${RED}[entrypoint] ERROR:${NC} %s\n" "$1" >&2; }

# ── Step 1: update geodata ────────────────────────────────────────────────────
# Non-fatal - on download failure keeps existing files and continues
/usr/local/bin/update-geodata.sh

# ── Step 2: verify geodata ────────────────────────────────────────────────────
# Ensures files exist either from download or placed manually
for f in geoip.dat geosite.dat; do
  if [ ! -f "$GEODATA_DIR/$f" ]; then
    log_error "$f not found in $GEODATA_DIR"
    log_error "Place the file manually or check network connectivity."
    exit 1
  fi
done

# ── Step 3: merge routing rules ───────────────────────────────────────────────
# Runs only if rules directory exists
if [ -d "$CONFS_DIR/rules" ]; then
  /usr/local/bin/merge-routing.sh
fi

# ── Step 4: drop privileges and start xray ────────────────────────────────────
# exec replaces this shell - no root process remains after this point
log_info "Starting xray (user: xray, confdir: $CONFS_DIR)"
exec su-exec xray:xray /usr/local/bin/xray run -confdir "$CONFS_DIR"

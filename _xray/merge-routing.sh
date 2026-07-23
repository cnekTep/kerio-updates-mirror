#!/bin/sh
# merge-routing.sh
# Merges all JSON rule files from confs/rules/ into a single routing.json.
# Each rule file must contain a JSON array of Xray routing rule objects: [{...}, ...]
# Files are merged in alphabetical order (use numeric prefixes to control priority).

set -e

# ── Config ────────────────────────────────────────────────────────────────────
CONFS_DIR="${CONFS_DIR:-/etc/xray/confs}"
RULES_DIR="${CONFS_DIR}/rules"
OUTPUT="${CONFS_DIR}/routing.json"
DOMAIN_STRATEGY="${DOMAIN_STRATEGY:-AsIs}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { printf "${GREEN}[merge-routing]${NC} %s\n" "$1"; }
log_warn()  { printf "${YELLOW}[merge-routing] WARN:${NC} %s\n" "$1"; }
log_error() { printf "${RED}[merge-routing] ERROR:${NC} %s\n" "$1" >&2; }

# ─── Checks ───────────────────────────────────────────────────────────────────
# Check jq is available
if ! command -v jq > /dev/null 2>&1; then
  log_error "jq is not installed"
  exit 1
fi

# Check rules directory exists
if [ ! -d "$RULES_DIR" ]; then
  log_error "Rules directory not found: $RULES_DIR"
  exit 1
fi

# ─── Collect rule files ───────────────────────────────────────────────────────
RULE_FILES=""
FILE_COUNT=0

for f in "$RULES_DIR"/*.json; do
  # Handle empty directory (glob returns literal string if no match)
  [ -e "$f" ] || continue

  # Validate: each file must be a JSON array
  if ! jq -e 'type == "array"' "$f" > /dev/null 2>&1; then
    log_error "$f is not a JSON array - expected format: [{\"type\":\"field\", ...}, ...]"
    exit 1
  fi

  RULE_FILES="$RULE_FILES $f"
  FILE_COUNT=$((FILE_COUNT + 1))
  log_info "  + $(basename "$f")"
done

# ─── Handle empty rules dir ───────────────────────────────────────────────────
if [ "$FILE_COUNT" -eq 0 ]; then
  log_warn "No .json files found in $RULES_DIR - writing empty routing.json"
  printf '{"routing":{"domainStrategy":"%s","rules":[]}}\n' "$DOMAIN_STRATEGY" > "$OUTPUT"
  exit 0
fi

# ─── Merge ────────────────────────────────────────────────────────────────────
log_info "Merging $FILE_COUNT file(s) -> $OUTPUT (domainStrategy: $DOMAIN_STRATEGY)"

# shellcheck disable=SC2086
jq -s --arg ds "$DOMAIN_STRATEGY" \
  '{routing:{domainStrategy:$ds, rules:(reduce .[] as $arr ([];. + $arr))}}' \
  $RULE_FILES > "$OUTPUT"

# Count resulting rules
RULE_COUNT=$(jq '.routing.rules | length' "$OUTPUT")
log_info "Done - $RULE_COUNT rule(s) written to $OUTPUT"

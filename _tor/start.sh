#!/bin/sh
set -e

# ─── Constants ───────────────────────────────────────────────────────────────

USER_BRIDGES_FILE="/tor/bridges/user_bridges.config"
BRIDGES_FILE="/tor/bridges/bridges.config"

DEFAULT_BRIDGE="Bridge 82.165.230.191:8151 07895E6DE9B3CBCB74B6CCF1ABB14BF112FF36F7"

# ─── Functions ────────────────────────────────────────────────────────────────

create_user_bridges_file() {
    if [ ! -f "$USER_BRIDGES_FILE" ]; then
        cat > "$USER_BRIDGES_FILE" << 'EOF'
# ============================================================
#  USER BRIDGES CONFIGURATION
# ============================================================
#
#  Add your personal Tor bridges below.
#  Get bridges at:
#    - Website: https://bridges.torproject.org
#    - Telegram: https://t.me/GetBridgesBot
#    - Email: bridges@torproject.org
#
#  RULES:
#    1. Each bridge MUST start with the word "Bridge"
#    2. One bridge per line
#    3. Lines starting with "#" are comments (ignored)
#
#  FORMAT:
#    Bridge <transport> <ip>:<port> <fingerprint> [options]
#
#  EXAMPLES:
#
#  obfs4:
#    Bridge obfs4 157.90.18.58:9999 4747D5EB038771935A8BEEF1938959953B562634 cert=E9kqqm5BMViPCNAPUfo/0Kx2SF96bv58nAYml8HofiUqhwlqz82C9eI3fpbnqR0HB+FXfw iat-mode=0
#
#  webtunnel:
#    Bridge webtunnel [2001:db8:f1c4:ca39:40a2:2e3f:f66b:2308]:443 93557BF013203581B6B7C3BF016425F1758F7CD6 url=https://diffusesystems.net/UvVD4kzlcS8HLlpxDdRWXidiDTDt0EiZ ver=0.0.3
#
# ============================================================
#  ADD YOUR BRIDGES BELOW THIS LINE:
# ============================================================

EOF
        echo "[create] user_bridges file created: $USER_BRIDGES_FILE"
    fi
}

create_bridges_file() {
    if [ ! -f "$BRIDGES_FILE" ]; then
        echo "$DEFAULT_BRIDGE" > "$BRIDGES_FILE"
        echo "[create] bridges file created with default bridge: $BRIDGES_FILE"
    fi
}

# ─── Init ─────────────────────────────────────────────────────────────────────

create_user_bridges_file
create_bridges_file

# Start Tor in daemon mode
tor &

# Run connectivity check
python3 /tor/check_tor/main.py

wait
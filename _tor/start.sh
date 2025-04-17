#!/bin/sh

# Start Tor and Privoxy in parallel
tor & privoxy --no-daemon /etc/privoxy/config &

# Conditional check USE_CHECK_TOR
if [ "$USE_CHECK_TOR" = "true" ]; then
    python3 /usr/local/bin/check_tor/main.py
else
    sleep infinity
fi
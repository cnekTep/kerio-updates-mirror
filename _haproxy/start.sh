#!/bin/sh
set -e

CFG=/etc/haproxy/haproxy.cfg
PIDFILE=/var/run/haproxy.pid
TRIGGER=/etc/haproxy/watch/reload.trigger
ALLOWED_IPS_ACL=/etc/haproxy/watch/allowed_ips.acl

start_haproxy() {
  echo "Starting haproxy..."

  # Check if allowed_ips.acl exists, create if not
  if [ ! -f "$ALLOWED_IPS_ACL" ]; then
    echo "Creating default allowed_ips.acl file..."
    echo "0.0.0.0/0" > "$ALLOWED_IPS_ACL"
  fi

  # Validate config before starting
  if ! haproxy -f "$CFG" -c; then
    echo "ERROR: HAProxy configuration is invalid!"
    exit 1
  fi

  haproxy -f "$CFG" -p "$PIDFILE" &  # Backgrounded, without -Ds for console logs
}

# Simple signal handling - just restart docker container
trap 'echo "Stopping..."; kill $(jobs -p) 2>/dev/null || true; exit 0' SIGINT SIGTERM

start_haproxy

DIR=$(dirname "$TRIGGER")
FILE=$(basename "$TRIGGER")

echo "Watching $DIR for $FILE..."

# Add timeout to inotifywait to make it more robust
while inotifywait -t 86400 -e create,close_write,move "$DIR" 2>/dev/null; do
  if [ -f "$TRIGGER" ]; then
    echo "Trigger file detected → restarting container..."
    rm -f "$TRIGGER"
    exit 0  # Exit cleanly to trigger Docker restart
  fi
done

# If inotifywait exits (timeout or error), restart anyway for robustness
echo "inotifywait exited, restarting container for safety..."
exit 0
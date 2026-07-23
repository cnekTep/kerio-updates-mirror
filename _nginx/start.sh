#!/bin/bash
set -Eeuo pipefail

WATCH_DIR=/etc/nginx/watch
NGINX_PID=""
WATCHER_PID=""
INOTIFY_PID=""
CLEANUP_DONE=0
SHUTDOWN_REQUESTED=0

# -----------------------------------------------------------------------------
# Create default allow-all stubs if files don't exist yet.
# Edit these files to restrict access - nginx reloads automatically via inotify.
#
#   allowed_ips_web.conf - controls access to /
#   allowed_ips_api.conf - controls access to /api
# -----------------------------------------------------------------------------
init_allowed_ips() {
    mkdir -p "$WATCH_DIR"
    # allow group write so the mirror container's appuser (gid 999) can also write here
    chmod 775 "$WATCH_DIR"

    for f in \
        "$WATCH_DIR/allowed_ips_web.conf" \
        "$WATCH_DIR/allowed_ips_api.conf"
    do
        if [ ! -f "$f" ]; then
            {
                echo "# allow all - replace with specific IPs to restrict"
                echo "allow all;"
            } > "$f"
            # match group of appuser in the mirror container (gid 999)
            # so it can write to this file without world-write permissions
            chgrp 999 "$f" 2>/dev/null || true
            chmod 664 "$f"
            echo "[watch]111 created default $f"
        fi
    done
}

# -----------------------------------------------------------------------------
# Reload nginx after validating config.
# Called by the inotify watch loop on every change in WATCH_DIR.
# -----------------------------------------------------------------------------
reload_nginx() {
    local changed_file="$1"
    echo "[reload] change detected: $changed_file - testing config..."

    if nginx -t 2>&1; then
        if nginx -s reload 2>&1; then
            echo "[reload] nginx reloaded successfully"
        else
            echo "[reload] ERROR: reload command failed"
        fi
    else
        echo "[reload] ERROR: config test failed - keeping current config"
    fi
}

# -----------------------------------------------------------------------------
# Cleanup - called by EXIT trap on any exit.
# Idempotent: guard flag prevents double-execution.
# No exit here - EXIT trap handles termination automatically.
# -----------------------------------------------------------------------------
cleanup() {
    [ "$CLEANUP_DONE" -eq 1 ] && return 0
    CLEANUP_DONE=1

    echo "[shutdown] stopping services..."

    # stop watcher loop and inotifywait, close their file descriptor
    [ -n "$WATCHER_PID" ]  && kill "$WATCHER_PID"  2>/dev/null || true
    [ -n "$INOTIFY_PID" ]  && kill "$INOTIFY_PID"  2>/dev/null || true
    exec 3<&- 2>/dev/null || true

    # gracefully stop nginx and wait for in-flight requests to finish
    [ -n "$NGINX_PID" ] && nginx -s quit 2>/dev/null || true
    [ -n "$NGINX_PID" ] && wait "$NGINX_PID"   2>/dev/null || true
    [ -n "$WATCHER_PID" ] && wait "$WATCHER_PID" 2>/dev/null || true

    echo "[shutdown] done"
}

# -----------------------------------------------------------------------------
# on_term - called on SIGINT/SIGTERM (docker stop).
# Sets flag so the monitor loop knows it's a clean shutdown, then exits.
# Separate from cleanup so that exit 0 doesn't interfere with EXIT trap logic.
# -----------------------------------------------------------------------------
on_term() {
    SHUTDOWN_REQUESTED=1
    cleanup
    exit 0
}

trap cleanup EXIT
trap on_term INT TERM

# --- boot sequence -----------------------------------------------------------

init_allowed_ips

echo "[start] testing nginx configuration..."
nginx -t

echo "[start] starting nginx..."
nginx -g "daemon off;" &
NGINX_PID=$!

# -----------------------------------------------------------------------------
# Run inotifywait in background, expose its stdout via FD 3.
# Main shell stays free to receive signals at any time.
# -----------------------------------------------------------------------------
echo "[watch] monitoring $WATCH_DIR for changes..."

exec 3< <(inotifywait -m -q -e close_write,create,moved_to \
    --format '%f' "$WATCH_DIR" 2>/dev/null)
INOTIFY_PID=$!

# watcher loop runs in background - PID tracked for health monitoring below
while read -r -u 3 changed_file; do
    reload_nginx "$changed_file"
done &
WATCHER_PID=$!

# -----------------------------------------------------------------------------
# Monitor loop: wait for any child to exit, then check who died.
#
# wait -n: blocks until any tracked child exits - no polling, no CPU waste.
# || true: prevents set -e from firing before we print diagnostics.
#
# SHUTDOWN_REQUESTED: set by on_term - distinguishes clean stop from crash.
# -----------------------------------------------------------------------------
while true; do
    # temporarily disable errexit so wait -n's non-zero return code
    # doesn't trigger set -e before we can inspect what actually happened.
    # Note: wait_rc is a useful diagnostic hint but not a guaranteed indicator
    # of which process died - if both exit simultaneously, the code is ambiguous.
    set +e
    wait -n "$NGINX_PID" "$WATCHER_PID"
    wait_rc=$?
    set -e

    # clean shutdown via SIGTERM/SIGINT - on_term already called cleanup
    if [ "$SHUTDOWN_REQUESTED" -eq 1 ]; then
        exit 0
    fi

    if ! kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "[monitor] nginx exited unexpectedly (exit code: $wait_rc) - stopping container"
        exit 1
    fi

    if ! kill -0 "$WATCHER_PID" 2>/dev/null; then
        echo "[monitor] watcher exited unexpectedly (exit code: $wait_rc) - stopping container"
        exit 1
    fi
done
#!/bin/sh
set -e

# Fix ownership of the bind-mounted bridges directory so the "tor" user
# can write config files into it. Only needs CAP_CHOWN, granted below.
chown -R tor:tor /tor/bridges

# Drop privileges and hand off to the actual entrypoint command (start.sh).
# exec replaces this shell process so the target command becomes PID 1
# and receives signals (SIGINT/SIGTERM) directly.
exec su-exec tor "$@"
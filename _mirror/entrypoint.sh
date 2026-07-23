#!/bin/bash
set -Eeuo pipefail

# Grant group 999 (appuser) read/write access to everything in /mirror,
# without changing actual ownership of host-owned files.
# -R  : apply recursively to existing files/dirs
# -d  : set as default ACL too, so new files/dirs created later
#       (by host user or by the app itself) inherit these permissions
setfacl -R  -m g:999:rwX /mirror
setfacl -R  -d -m g:999:rwX /mirror

exec gosu appuser "$@"
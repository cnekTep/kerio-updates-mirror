#!/bin/bash
set -euo pipefail

# Run from the script's own directory regardless of where it's called from
cd "$(dirname "$(readlink -f "$0")")"

echo "==> Updating the source code..."
git pull

echo "==> Stopping Docker containers..."
docker compose down

echo "==> Deleting old volume..."
docker volume rm -f kerio-updates-mirror_mirror-venv-data

echo "==> Launching Docker containers..."
docker compose up -d

echo "==> Done!"
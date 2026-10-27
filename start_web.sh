#!/usr/bin/env bash
# Start the local Seerah contact file web app.
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec python3 webapp.py "$@"

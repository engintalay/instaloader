#!/usr/bin/env bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[!] Önce kurulum yapın: ./install.sh"
    exit 1
fi

"$VENV_DIR/bin/python" "$(dirname "$0")/download_profile.py" "$@"

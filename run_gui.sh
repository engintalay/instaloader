#!/usr/bin/env bash
set -e

BASE_DIR="$(dirname "$0")"
VENV_DIR="$BASE_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[!] Önce kurulum yapın: ./install.sh"
    exit 1
fi

"$VENV_DIR/bin/python" "$BASE_DIR/gui_app.py"

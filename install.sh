#!/usr/bin/env bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

echo "[*] Sanal ortam oluşturuluyor..."
python -m venv "$VENV_DIR"

echo "[*] Bağımlılıklar kuruluyor..."
"$VENV_DIR/bin/pip" install --quiet instaloader browser_cookie3 pycookiecheat pillow

echo "[+] Kurulum tamamlandı."
echo "    Kullanım: ./run.sh <profil_adı> [tarayıcı]"
echo "    GUI: ./run_gui.sh"

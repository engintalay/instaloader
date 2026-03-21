#!/usr/bin/env bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

echo "[*] Sanal ortam oluşturuluyor..."
python3.10 -m venv "$VENV_DIR"

echo "[*] Bağımlılıklar kuruluyor..."
"$VENV_DIR/bin/pip" install --quiet instaloader browser_cookie3 pycookiecheat

echo "[+] Kurulum tamamlandı."
echo "    Kullanım: ./run.sh <profil_adı> [tarayıcı]"

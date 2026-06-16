#!/usr/bin/env bash
# Build a standalone ChatSorter binary on Linux/macOS (output: dist/ChatSorter).
# Uses a throwaway venv so it never touches your system Python. Needs the Tk
# binding present (Linux: sudo apt install python3-tk).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

VENV="${VENV:-/tmp/chatsorter-build-venv}"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip pyinstaller
"$VENV/bin/pyinstaller" --noconfirm --onefile --name ChatSorter \
  --hidden-import auto_sort --hidden-import watch_vault \
  --hidden-import classify_vault --hidden-import sort_vault \
  gui.py

echo
echo "Done -> $DIR/dist/ChatSorter"

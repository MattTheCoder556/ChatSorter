#!/usr/bin/env bash
# Launch the ChatSorter desktop UI (Linux/macOS).
# Needs the Tk binding: on Debian/Ubuntu  ->  sudo apt install python3-tk
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python)"
exec "$PY" "$DIR/gui.py" "$@"

#!/usr/bin/env bash
# Linux/macOS equivalent of watch.cmd — START the vault watcher in the background.
#
#   ./watch.sh                       # watch the default vault below
#   ./watch.sh ~/my-vault/wiki       # watch a specific vault
#   ./watch.sh ~/my-vault --no-llm   # sort by existing type only (no API key needed)
#
# Any extra args after the vault path are passed straight to watch_vault.py.
# The LLM pass needs MINIMAX_API_KEY exported (or pass --no-llm).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# >>> EDIT THIS default to your vault root, or pass a path as the first arg <<<
VAULT="${1:-$HOME/knowledge-vault/wiki}"
[[ $# -gt 0 ]] && shift   # remaining args ("$@") forwarded to the watcher

LOG="$DIR/vaultwatch.log"

if pgrep -f "watch_vault.py" >/dev/null 2>&1; then
    echo "  VaultWatch is already running (PID $(pgrep -f watch_vault.py | tr '\n' ' '))."
    echo "  Run ./stop.sh first if you want to restart it."
    exit 0
fi

if [[ ! -d "$VAULT" ]]; then
    echo "  error: not a directory: $VAULT" >&2
    echo "  edit the VAULT default in watch.sh, or pass a path: ./watch.sh <vault>" >&2
    exit 1
fi

PY="$(command -v python3 || command -v python)"
# --log off: the watcher writes nothing itself; nohup captures stdout+stderr into
# one log (so even a startup error like a missing API key lands in vaultwatch.log).
nohup "$PY" "$DIR/watch_vault.py" "$VAULT" --interval 5 --notify --log off "$@" >> "$LOG" 2>&1 &
disown
sleep 1
echo
echo "  VaultWatch is now ON  (watching: $VAULT)"
echo "  Drop any .md into the vault root and it sorts itself within ~5 seconds."
echo "  A desktop notification (notify-send) fires each time a note is filed."
echo
echo "  ./stop.sh to turn it off  •  ./status.sh to check it"
echo

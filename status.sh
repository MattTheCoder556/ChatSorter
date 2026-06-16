#!/usr/bin/env bash
# Linux/macOS equivalent of status.cmd — is the watcher running? + recent activity.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/vaultwatch.log"

PIDS="$(pgrep -f watch_vault.py 2>/dev/null || true)"
echo
if [[ -n "$PIDS" ]]; then
    echo "  VaultWatch: RUNNING (PID $(echo "$PIDS" | tr '\n' ' '))"
else
    echo "  VaultWatch: STOPPED  (run ./watch.sh to start it)"
fi

if [[ -f "$LOG" ]]; then
    echo
    echo "  --- recent activity ---"
    tail -n 15 "$LOG" | sed 's/^/  /'
else
    echo "  (no activity yet)"
fi
echo

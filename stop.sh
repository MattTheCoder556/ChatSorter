#!/usr/bin/env bash
# Linux/macOS equivalent of stop.cmd — STOP the vault watcher.
if pkill -f "watch_vault.py" 2>/dev/null; then
    echo
    echo "  VaultWatch is now OFF. New notes will no longer be sorted automatically."
    echo
else
    echo
    echo "  VaultWatch was not running."
    echo
fi

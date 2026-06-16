#!/usr/bin/env bash
# Register a systemd *user* timer that classifies (MiniMax M3) + sorts a vault on
# an interval. The Linux equivalent of register_task.ps1. No root needed.
#
# Examples:
#   ./register_task.sh ~/knowledge-vault/wiki
#   ./register_task.sh ~/knowledge-vault/wiki --minutes 5 --name myvaultsort
#   ./register_task.sh ~/knowledge-vault/wiki --no-llm        # sort only
#
# Requirements:
#   * python3 on PATH; auto_sort.py / classify_vault.py / sort_vault.py beside this script.
#   * For the LLM pass, MINIMAX_API_KEY (and optionally MINIMAX_MODEL / MINIMAX_BASE_URL)
#     exported in the unit's environment. By default this script copies them from your
#     current shell into the unit. Make sure they're set before running, e.g.:
#         export MINIMAX_API_KEY="your-key-here"
#         export MINIMAX_MODEL="MiniMax-M2"     # or your exact M3 id
#
# Remove later with:
#   systemctl --user disable --now <name>.timer
#   rm ~/.config/systemd/user/<name>.{service,timer} && systemctl --user daemon-reload
set -euo pipefail

VAULT=""
MINUTES=10
NAME="vaultsort"
NO_LLM=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --minutes) MINUTES="$2"; shift 2 ;;
        --name)    NAME="$2";    shift 2 ;;
        --no-llm)  NO_LLM=1;     shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *)  VAULT="$1"; shift ;;
    esac
done

[[ -n "$VAULT" ]] || { echo "usage: $0 <vault> [--minutes N] [--name X] [--no-llm]" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_SORT="$SCRIPT_DIR/auto_sort.py"
[[ -f "$AUTO_SORT" ]] || { echo "auto_sort.py not found at $AUTO_SORT" >&2; exit 1; }

PY="$(command -v python3 || command -v python)" \
    || { echo "python3 not found on PATH" >&2; exit 1; }

# absolute vault path (expand ~ and relative)
VAULT="$(cd "$(eval echo "$VAULT")" 2>/dev/null && pwd)" \
    || { echo "not a directory: $VAULT" >&2; exit 1; }

ARGS=("$AUTO_SORT" "$VAULT")
[[ "$NO_LLM" -eq 1 ]] && ARGS+=("--no-llm")

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

# Pull credentials from the current shell into the unit (only the LLM pass needs them).
ENV_LINES=""
for var in MINIMAX_API_KEY MINIMAX_MODEL MINIMAX_BASE_URL; do
    if [[ -n "${!var:-}" ]]; then
        ENV_LINES+="Environment=$var=${!var}"$'\n'
    fi
done
if [[ "$NO_LLM" -eq 0 && -z "${MINIMAX_API_KEY:-}" ]]; then
    echo "warning: MINIMAX_API_KEY is not set in this shell; the LLM pass will fail." >&2
    echo "         export it and re-run, or pass --no-llm for deterministic sorting only." >&2
fi

cat > "$UNIT_DIR/$NAME.service" <<EOF
[Unit]
Description=Classify (MiniMax M3) + sort vault $VAULT

[Service]
Type=oneshot
${ENV_LINES}ExecStart=$PY ${ARGS[*]}
EOF

cat > "$UNIT_DIR/$NAME.timer" <<EOF
[Unit]
Description=Run $NAME every $MINUTES minute(s)

[Timer]
OnBootSec=2min
OnUnitActiveSec=${MINUTES}min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$NAME.timer"

echo "Registered timer '$NAME.timer': classify+sort '$VAULT' every $MINUTES minute(s)."
echo "Run now to test:  systemctl --user start $NAME.service"
echo "Follow logs:      journalctl --user -u $NAME.service -f"
echo "Next runs:        systemctl --user list-timers $NAME.timer"
echo "Remove:           systemctl --user disable --now $NAME.timer && rm $UNIT_DIR/$NAME.{service,timer} && systemctl --user daemon-reload"

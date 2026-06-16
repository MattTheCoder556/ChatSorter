# Obsidian Vault Chat Sorter (MiniMax M3)

An "always sort" pipeline for an Obsidian vault. Obsidian's Smart Composer plugin
is a *reactive* chat assistant — it only acts when you message it, so it can't
continuously sort notes (even with MiniMax M3 behind it). This fills that gap with
a scheduler + an LLM classification pass.

Two passes, run back to back:

1. **classify** (`classify_vault.py`) — for every loose root-level `.md` that has
   no recognized `type:`, send it to **MiniMax M3** and write the inferred type
   into the note's frontmatter.
2. **sort** (`sort_vault.py`) — move every typed note into its folder
   (`concept → concepts/`, `entity → entities/`, …). Deterministic, no network.

`auto_sort.py` runs both. A Windows Scheduled Task runs `auto_sort.py` on an interval.

## Safety
- Never deletes; only moves.
- Never overwrites an existing `type:` — only adds one when missing.
- Never clobbers a destination file that already exists.
- Low-confidence classifications are left untouched in the root (it never guesses).
- Root-only: never recurses into already-sorted folders.
- Idempotent: safe to run on any schedule.

## Setup (Windows)
```powershell
# 1. Python on PATH (python --version should work)

# 2. Credentials as USER env vars, so the Scheduled Task can read them:
setx MINIMAX_API_KEY "your-key-here"
setx MINIMAX_MODEL   "MiniMax-M2"      # set to your exact M3 model id
#   optional, only if your endpoint differs from the default:
# setx MINIMAX_BASE_URL "https://api.minimax.io/v1"
#   -> open a NEW terminal after setx so the values load.
```

## Try it before scheduling
```powershell
# preview only — calls the LLM but writes/moves nothing
python auto_sort.py "C:\Users\Matt\knowledge-vault\wiki" --dry-run

# cap LLM calls while testing cost/behavior
python auto_sort.py "C:\Users\Matt\knowledge-vault\wiki" --limit 5 --dry-run

# real run, once
python auto_sort.py "C:\Users\Matt\knowledge-vault\wiki"

# sort only, no LLM (deterministic — only files notes that already have type:)
python auto_sort.py "C:\Users\Matt\knowledge-vault\wiki" --no-llm
```

## "Always sort" — two ways

### A. Watcher (instant — sorts the moment a file lands) — recommended
`watch_vault.py` runs continuously and sorts any new/changed note in the root as
soon as it stops being written. Only newly-arrived notes are sent to MiniMax, so
leftover untyped notes aren't re-charged on every tick.

```powershell
# run it in the foreground to watch (Ctrl+C to stop)
python watch_vault.py "C:\Users\Matt\knowledge-vault\wiki"

# make it always-on: starts at logon, restarts if it ever exits, no console window
.\register_watcher.ps1 -Vault "C:\Users\Matt\knowledge-vault\wiki"
Start-ScheduledTask      -TaskName "VaultWatch"                    # start now
Stop-ScheduledTask       -TaskName "VaultWatch"                    # stop
Unregister-ScheduledTask -TaskName "VaultWatch" -Confirm:$false    # remove
```
Tuning: `--interval` (poll seconds, default 5), `--settle` (seconds a file must be
unchanged before processing, default 2), `--no-llm` (sort by existing type only).

### B. Interval task (sweeps every N minutes)
Simpler, not instant. Good if you'd rather not keep a process running.
```powershell
.\register_task.ps1 -Vault "C:\Users\Matt\knowledge-vault\wiki" -Minutes 10
Start-ScheduledTask -TaskName "VaultSort"                          # test now
Get-ScheduledTaskInfo -TaskName "VaultSort"                        # last result
Unregister-ScheduledTask -TaskName "VaultSort" -Confirm:$false     # remove
```

## Tuning
- `--threshold 0.6` — minimum model confidence before a type is written. Raise it
  to be more conservative (more notes left in root), lower to classify more.
- `--map note=notes,ref=references` — use a different type→folder convention. The
  map keys double as the allowed classification labels.
- `--keep index.md,README.md` — filenames the pipeline never touches.
- `--max-chars 6000` — how much of each note is sent to the model.
- Edit `TYPE_HINTS` in `classify_vault.py` to refine how each type is described to
  the model — this is the main lever for "intuitive" classification.

## Files
| file | role |
|------|------|
| `watch_vault.py`   | **watcher: auto-sorts files the instant they land** |
| `auto_sort.py`     | one-shot entry point: classify → sort (interval task runs this) |
| `classify_vault.py`| MiniMax M3 pass: writes `type:` onto untyped notes |
| `sort_vault.py`    | deterministic mover: files notes by `type:` |
| `register_watcher.ps1`| registers the always-on watcher task (at logon) |
| `register_task.ps1`| registers the interval Scheduled Task |

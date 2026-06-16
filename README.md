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

### Documents, not just notes
The sort pass also files **documents by extension** (no LLM, no text extraction —
works on any file):

| extension | → folder |
|---|---|
| `.pdf .doc .docx .odt .rtf .txt` | `Documents/` |
| `.ppt .pptx .odp` | `Presentations/` |
| `.xls .xlsx .csv .ods` | `Spreadsheets/` |

Images are **deliberately not** moved (relocating them on disk breaks Obsidian
embeds), nor is anything else. Turn document sorting off with `--no-docs`, or
remap it with `--doc-map pdf=Docs,xlsx=Sheets`.

## Get the app (standalone, no Python needed)
A single double-click executable — no Python install required for end users.

- **Windows `.exe`:** built automatically by GitHub Actions on every push to `main`.
  Download it from the latest run under the repo's **Actions → build-exe → Artifacts
  → `ChatSorter-windows`**, or grab it from a tagged **Release**. Then just
  double-click `ChatSorter.exe`.
- **Build it yourself:**
  - Windows: double-click `build.cmd` → `dist\ChatSorter.exe`
  - Linux/macOS: `./build.sh` → `dist/ChatSorter` (needs `python3-tk` on Linux)

Both bundle the GUI and all sub-tools into one file; the watcher runs by the exe
re-invoking itself, so there are no loose `.py` files to ship.

## Desktop UI (Windows + Linux + macOS)
Prefer buttons over the command line? `gui.py` is a single cross-platform window
(pure-stdlib Tkinter — no pip installs) that does everything: pick the vault, see a
**legend of exactly what gets sorted where**, **Sort now** / **Preview (dry run)**,
**Start/Stop watcher**, toggle **Include documents** and **Use AI**, with a live
activity log.
```bash
# Windows: double-click gui.cmd   (or:  python gui.py)
# Linux:   ./gui.sh               (needs the Tk binding once: sudo apt install python3-tk)
# macOS:   python3 gui.py
```
The vault, model, toggles, **and the API key you type** persist to `config.json`
next to the script — the single place every run reads its defaults from, so you
only enter the key once. (It's stored in plaintext locally; `config.json` is
gitignored so it is never committed.) Leave the field blank to fall back to the
`MINIMAX_API_KEY` env var. Untick **Use AI** to sort by existing `type:` /
extension only, with no key at all.

By default the watcher stops when you close the window. Tick **Keep watcher
running after closing** to leave it running in the background as a detached
process (tracked by `watcher.pid`); the next time you open the UI it re-attaches to
that watcher so you can see and stop it. (For a watcher with no UI at all, use
`watch.sh` / the systemd timer.)

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

## Setup (Linux / macOS)
The Python is cross-platform (stdlib only — no pip installs). Only the credentials
and the scheduler differ from Windows.
```bash
# 1. python3 on PATH (python3 --version should work)

# 2. Credentials as env vars (add to ~/.bashrc / ~/.zshrc to persist):
export MINIMAX_API_KEY="your-key-here"
export MINIMAX_MODEL="MiniMax-M2"      # set to your exact M3 model id
# optional, only if your endpoint differs from the default:
# export MINIMAX_BASE_URL="https://api.minimax.io/v1"
```

## Try it before scheduling
On Linux/macOS use `python3` and a POSIX path, e.g.
`python3 auto_sort.py ~/knowledge-vault/wiki --dry-run`. The flags below are identical.
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

### Linux: interval timer (systemd user timer)
`register_task.sh` is the Linux equivalent of `register_task.ps1`. It installs a
**user** timer (no root) that runs `auto_sort.py` on an interval, copying your
current shell's `MINIMAX_*` env vars into the unit.
```bash
chmod +x register_task.sh
./register_task.sh ~/knowledge-vault/wiki --minutes 10            # classify + sort
./register_task.sh ~/knowledge-vault/wiki --minutes 10 --no-llm   # sort only

systemctl --user start vaultsort.service                          # test now
systemctl --user list-timers vaultsort.timer                       # next runs
journalctl --user -u vaultsort.service -f                          # follow logs
systemctl --user disable --now vaultsort.timer                     # remove (then rm the unit files)
```
For the always-on watcher on Linux, the `watch.sh` / `stop.sh` / `status.sh`
helpers mirror the Windows `.cmd` files:
```bash
chmod +x watch.sh stop.sh status.sh
./watch.sh ~/knowledge-vault/wiki            # start in background (uses MINIMAX_API_KEY)
./watch.sh ~/knowledge-vault/wiki --no-llm   # start, sort by existing type only
./status.sh                                  # RUNNING/STOPPED + last 15 log lines
./stop.sh                                    # stop it
```
Edit the `VAULT` default at the top of `watch.sh` so you can launch with no args.
The watcher uses `notify-send` for desktop notifications; to survive logout, wrap
it in a `[Service]` unit with `Restart=always` instead.

## Tuning
- `--threshold 0.6` — minimum model confidence before a type is written. Raise it
  to be more conservative (more notes left in root), lower to classify more.
- `--map note=notes,ref=references` — use a different type→folder convention. The
  map keys double as the allowed classification labels.
- `--doc-map pdf=Docs,xlsx=Sheets` — change where documents go by extension.
  `--no-docs` turns document sorting off entirely (Markdown only).
- `--keep index.md,README.md` — filenames the pipeline never touches.
- `--max-chars 6000` — how much of each note is sent to the model.
- Edit `TYPE_HINTS` in `classify_vault.py` to refine how each type is described to
  the model — this is the main lever for "intuitive" classification.

## Files
| file | role |
|------|------|
| `gui.py`           | **cross-platform desktop UI (Tkinter): sort / watch / log** |
| `gui.cmd` / `gui.sh` | double-click launchers for the UI (Windows / Linux) |
| `build.cmd` / `build.sh` | build a standalone ChatSorter.exe / binary (PyInstaller) |
| `.github/workflows/build-exe.yml` | CI that builds the Windows .exe on every push |
| `watch_vault.py`   | **watcher: auto-sorts files the instant they land** |
| `auto_sort.py`     | one-shot entry point: classify → sort (interval task runs this) |
| `classify_vault.py`| MiniMax M3 pass: writes `type:` onto untyped notes |
| `sort_vault.py`    | deterministic mover: files notes by `type:` |
| `register_watcher.ps1`| registers the always-on watcher task (at logon) |
| `register_task.ps1`| registers the interval Scheduled Task (Windows) |
| `register_task.sh` | registers the interval systemd **user** timer (Linux) |
| `watch.cmd` / `stop.cmd` / `status.cmd` | start / stop / check the watcher (Windows) |
| `watch.sh` / `stop.sh` / `status.sh` | start / stop / check the watcher (Linux/macOS) |

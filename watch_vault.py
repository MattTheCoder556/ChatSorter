#!/usr/bin/env python3
r"""Watch a vault root and auto-sort any .md file the moment it lands.

A long-running, zero-dependency poller. When a new or changed root-level note
appears AND stops changing (it has "settled"), it runs the pipeline:
  1. classify the NEW notes with MiniMax M3 -> writes `type:` frontmatter
  2. sort the whole root by type -> moves notes into their folders

Only newly-arrived/changed notes are sent to the LLM, so leftover untyped notes
(ones the model already declined) are not re-charged on every tick.

    python watch_vault.py "C:\Users\me\knowledge-vault\wiki"
    python watch_vault.py "C:\Users\me\knowledge-vault\wiki" --interval 3 --settle 2
    python watch_vault.py "C:\Users\me\knowledge-vault\wiki" --no-llm

Stop with Ctrl+C. To run it always (at logon), use register_watcher.ps1.
Config (MINIMAX_API_KEY / MINIMAX_MODEL / MINIMAX_BASE_URL) is read from the
environment, same as the other scripts.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import classify_vault as cl
import sort_vault as sv

CREATE_NO_WINDOW = 0x08000000  # keep the notification helper windowless


def log_line(logfile, msg):
    """Print and (best-effort) append a timestamped line to the activity log."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    if logfile:
        try:
            with open(logfile, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def notify(title, msg):
    """Fire a desktop notification; never let it disrupt the watcher.

    Uses `notify-send` on Linux, `osascript` on macOS, and a PowerShell balloon
    tip on Windows. Any failure (tool missing, no desktop session) is swallowed.
    """
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["notify-send", str(title), str(msg)])
        elif sys.platform == "darwin":
            t = str(title).replace('"', '\\"')
            m = str(msg).replace('"', '\\"')
            subprocess.Popen(
                ["osascript", "-e", f'display notification "{m}" with title "{t}"'])
        else:  # Windows
            t = str(title).replace("'", "''")
            m = str(msg).replace("'", "''")
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                f"$n.ShowBalloonTip(4000,'{t}','{m}','Info');"
                "Start-Sleep -Milliseconds 4500;$n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=CREATE_NO_WINDOW,
            )
    except OSError:
        pass


def resolve_credentials(args):
    """Return (api_key, base_url). Prefer env vars; fall back to a Smart Composer
    config (the MiniMax provider) so the watcher needs no env setup to run."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    base_url = args.base_url
    if not api_key and args.sc_config:
        try:
            data = json.loads(Path(args.sc_config).read_text(encoding="utf-8"))
            mm = next((p for p in data.get("providers", []) if p.get("id") == "minimax"), None)
            if mm:
                api_key = mm.get("apiKey") or api_key
                base_url = mm.get("baseUrl") or base_url
        except (OSError, ValueError, KeyError) as e:
            print(f"could not read --sc-config ({e!r})")
    return api_key, base_url


def signatures(root: Path, keep: set, doc_map: dict | None = None) -> dict:
    """Map name -> (size, mtime_int) for sortable root-level files (excl. keep-list).

    Always watches *.md; also watches document extensions in `doc_map` when set.
    """
    sigs = {}
    for f in root.iterdir():
        if not f.is_file() or f.name in keep:
            continue
        suffix = f.suffix.lower()
        if suffix != ".md" and not (doc_map and suffix in doc_map):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        sigs[f.name] = (st.st_size, int(st.st_mtime))
    return sigs


def main():
    ap = argparse.ArgumentParser(description="Watch a vault root and auto classify+sort.")
    ap.add_argument("vault", help="folder to watch (root-level .md files)")
    ap.add_argument("--map", type=sv.parse_map, default=sv.DEFAULT_MAP, help="comma list type=folder")
    ap.add_argument("--keep", default=None, help="comma list of filenames to never touch")
    ap.add_argument("--model", default=cl.DEFAULT_MODEL, help="MiniMax model id")
    ap.add_argument("--base-url", default=cl.DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    ap.add_argument("--threshold", type=float, default=0.6, help="min confidence to write")
    ap.add_argument("--interval", type=float, default=5.0, help="poll seconds")
    ap.add_argument("--settle", type=float, default=2.0,
                    help="a file must be unchanged this many seconds before processing")
    ap.add_argument("--no-llm", action="store_true", help="skip LLM, sort by existing type only")
    ap.add_argument("--no-new", action="store_true",
                    help="don't invent new folders; leave unmatched notes in the root")
    ap.add_argument("--doc-map", type=sv.parse_doc_map, default=sv.DEFAULT_DOC_MAP,
                    help="comma list ext=folder for documents, e.g. pdf=Docs,xlsx=Sheets")
    ap.add_argument("--no-docs", action="store_true",
                    help="watch Markdown only; leave pdf/docx/etc. in place")
    ap.add_argument("--ignore-existing", action="store_true",
                    help="treat files already in the root at startup as handled; "
                         "only act on notes that arrive or change after launch")
    ap.add_argument("--sc-config", default=None,
                    help="path to Smart Composer's data.json; used to read the MiniMax "
                         "key/base URL when MINIMAX_API_KEY is not in the environment")
    ap.add_argument("--log", default=None,
                    help="activity log file (default: vaultwatch.log next to this script; "
                         "pass 'off' to disable)")
    ap.add_argument("--notify", action="store_true",
                    help="show a desktop notification each time a note is filed")
    args = ap.parse_args()

    if args.log is None:
        logfile = str(Path(__file__).with_name("vaultwatch.log"))
    elif args.log.lower() == "off":
        logfile = None
    else:
        logfile = args.log

    root = Path(args.vault).expanduser()
    if not root.is_dir():
        sys.exit(f"error: not a directory: {root}")

    keep = {x.strip() for x in args.keep.split(",")} if args.keep else sv.DEFAULT_KEEP
    doc_map = None if args.no_docs else args.doc_map

    api_key = None
    base_url = args.base_url
    if not args.no_llm:
        api_key, base_url = resolve_credentials(args)
        if not api_key:
            sys.exit("error: no MiniMax key (set MINIMAX_API_KEY or pass --sc-config), "
                     "or use --no-llm to sort by existing type only.")

    log_line(logfile, f"VaultWatch started - watching {root} "
                      f"(every {args.interval}s, llm={'off' if args.no_llm else args.model})")

    # Files we've already handed to the pipeline (name -> signature). Seeded empty
    # so anything already sitting in the root gets processed on the first tick —
    # unless --ignore-existing, which pre-seeds the current root as "handled".
    seen: dict = {}
    if args.ignore_existing:
        seen = signatures(root, keep, doc_map)
        log_line(logfile, f"ignoring {len(seen)} pre-existing root file(s); "
                          "only new/changed notes will be sorted")

    while True:
        try:
            now = time.time()
            cur = signatures(root, keep, doc_map)
            new_files = []
            for name, sig in cur.items():
                if seen.get(name) == sig:
                    continue  # unchanged since we last handled it
                size, mtime = sig
                if now - mtime < args.settle:
                    continue  # still being written; wait for it to settle (don't mark seen)
                new_files.append(name)

            if new_files:
                log_line(logfile, f"detected {len(new_files)} new/changed: {', '.join(new_files)}")
                targets = [root / n for n in new_files]
                sort_map = args.map
                # only Markdown gets the LLM type-classification pass; documents
                # are filed by extension and never sent to the model.
                md_targets = [t for t in targets if t.suffix.lower() == ".md"]
                if not args.no_llm and md_targets:
                    _, used = cl.classify_root(root, args.map, keep, api_key=api_key,
                                               model=args.model, base_url=base_url,
                                               threshold=args.threshold, files=md_targets,
                                               allow_new=not args.no_new)
                    for lbl, folder in used.items():
                        if lbl not in args.map and not (root / folder).exists():
                            log_line(logfile, f"  created new folder: {folder}/")
                    sort_map = {**args.map, **used}  # honour new folders when sorting

                def on_move(name, folder):
                    log_line(logfile, f"  sorted: {name}  ->  {folder}/")
                    if args.notify:
                        notify("Note filed", f"{name}  ->  {folder}")

                # only sort the files we just detected, never the whole backlog
                moved = sv.sort_root(root, sort_map, keep, files=targets,
                                     on_move=on_move, doc_map=doc_map)
                if moved == 0:
                    log_line(logfile, "  (left in root — unclear type, low confidence)")
                # Mark only the files we actually handled, using their pre-move
                # signature. Moved files won't reappear; leftovers won't re-trigger
                # until they change again.
                for n in new_files:
                    seen[n] = cur[n]

            # Forget files that have left the root, so seen can't grow unbounded.
            seen = {n: s for n, s in seen.items() if n in cur}
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped.")
            return
        except Exception as e:  # noqa: BLE001 - long-running daemon must not die on a transient error
            log_line(logfile, f"tick error (continuing): {e!r}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()

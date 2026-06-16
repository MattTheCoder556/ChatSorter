#!/usr/bin/env python3
r"""Orchestrator: classify untyped notes with MiniMax M3, then file everything.

This is the single entry point a Scheduled Task should run. It does two passes:
  1. classify_vault.classify_root  -> writes `type:` onto untyped notes via the LLM
  2. sort_vault.sort_root          -> moves every typed note into its folder

Both passes are safe and idempotent: nothing is deleted, existing types are never
overwritten, destinations are never clobbered, low-confidence notes stay put.

    python auto_sort.py "C:\Users\me\knowledge-vault\wiki"
    python auto_sort.py "C:\Users\me\knowledge-vault\wiki" --dry-run
    python auto_sort.py "C:\Users\me\knowledge-vault\wiki" --no-llm   # sort only
"""
import argparse
import os
import sys
from pathlib import Path

import classify_vault as cl
import sort_vault as sv


def main():
    ap = argparse.ArgumentParser(description="Classify (MiniMax M3) then sort a vault.")
    ap.add_argument("vault", help="folder whose root-level .md files should be processed")
    ap.add_argument("--map", type=sv.parse_map, default=sv.DEFAULT_MAP,
                    help="comma list type=folder")
    ap.add_argument("--keep", default=None, help="comma list of filenames to never touch")
    ap.add_argument("--model", default=cl.DEFAULT_MODEL, help="MiniMax model id")
    ap.add_argument("--base-url", default=cl.DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    ap.add_argument("--threshold", type=float, default=0.6, help="min confidence to write")
    ap.add_argument("--limit", type=int, default=None, help="max LLM calls this run")
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM pass, sort only")
    ap.add_argument("--no-new", action="store_true",
                    help="don't invent new folders; leave unmatched notes in place")
    ap.add_argument("--doc-map", type=sv.parse_doc_map, default=sv.DEFAULT_DOC_MAP,
                    help="comma list ext=folder for documents, e.g. pdf=Docs,xlsx=Sheets")
    ap.add_argument("--no-docs", action="store_true",
                    help="sort Markdown only; leave pdf/docx/etc. in place")
    ap.add_argument("--dry-run", action="store_true", help="preview both passes, change nothing")
    args = ap.parse_args()

    root = Path(args.vault).expanduser()
    if not root.is_dir():
        sys.exit(f"error: not a directory: {root}")

    keep = {x.strip() for x in args.keep.split(",")} if args.keep else sv.DEFAULT_KEEP

    if not args.no_llm:
        api_key = os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            sys.exit("error: set MINIMAX_API_KEY, or pass --no-llm to sort only.")
        print("== pass 1: classify untyped notes ==")
        _, used = cl.classify_root(root, args.map, keep, api_key=api_key, model=args.model,
                                   base_url=args.base_url, dry_run=args.dry_run,
                                   threshold=args.threshold, limit=args.limit,
                                   allow_new=not args.no_new)
        args.map = {**args.map, **used}  # honour any new folders in the sort pass
    else:
        print("== pass 1: skipped (--no-llm) ==")

    print("== pass 2: sort notes by type + documents by extension ==")
    doc_map = None if args.no_docs else args.doc_map
    moved = sv.sort_root(root, args.map, keep, args.dry_run, doc_map=doc_map)
    verb = "would sort" if args.dry_run else "sorted"
    print(f"done: {verb} {moved} file(s)")


if __name__ == "__main__":
    main()

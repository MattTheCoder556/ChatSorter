#!/usr/bin/env python3
r"""LLM pass: classify loose .md notes that LACK a recognized `type:` and write it.

This is the "Option B" semantic path. For every root-level note whose type the
deterministic sorter can't read, we send the note to MiniMax M3, get back one of
the known type labels (or "unknown"), and write `type:` into the note's
frontmatter. sort_vault.py then files it. We only ever ADD a type line; we never
overwrite an existing type, never move files, never delete.

Config via environment variables (so a Scheduled Task can run unattended):

    MINIMAX_API_KEY     required. Your MiniMax API key.
    MINIMAX_MODEL       model id. Defaults to "MiniMax-M2"; set to your M3 id.
    MINIMAX_BASE_URL    OpenAI-compatible base. Default "https://api.minimax.io/v1".

Usage:
    python classify_vault.py "C:\Users\me\knowledge-vault\wiki" --dry-run
    python classify_vault.py "C:\Users\me\knowledge-vault\wiki" --limit 20
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from sort_vault import DEFAULT_KEEP, DEFAULT_MAP, parse_map, read_type

DEFAULT_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2")
DEFAULT_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")

# Short, stable definitions handed to the model so classification is intuitive
# and consistent. Keys MUST match the keys in the type->folder map.
TYPE_HINTS = {
    "agent": "a profile of a single person, persona, or social-media account "
             "(name/handle, bio, posting style, voice)",
    "company": "a profile of an organization, business, brand, or product company",
    "knowledge": "general reference, research, or factual notes on a subject "
                 "(explainers, how-tos, background)",
    "topic": "a note centered on a recurring theme or subject area to track over time",
    "strategy": "planning, strategy, roadmap, positioning, or decision notes",
    "seo": "website scans, SEO audits, site-alignment checks, or competitor-trend reports",
}


def has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return bool(lines) and lines[0].lstrip("﻿").strip() == "---"  # tolerate a BOM


def insert_type(text: str, type_value: str) -> str:
    """Return `text` with `type: <value>` added to frontmatter (creating it if absent)."""
    if has_frontmatter(text):
        lines = text.splitlines(keepends=True)
        # insert right after the opening fence
        head = lines[0]
        rest = lines[1:]
        return head + f"type: {type_value}\n" + "".join(rest)
    # no frontmatter at all -> prepend a fresh block
    return f"---\ntype: {type_value}\n---\n\n{text}"


_BAD_FOLDER_CHARS = re.compile(r'[\\/:*?"<>|]+')


def sanitize_folder(name: str) -> str | None:
    """Turn a model-proposed category into a safe single folder name, or None."""
    name = _BAD_FOLDER_CHARS.sub(" ", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name or name.startswith((".", "_")):
        return None
    return name[:40].strip()


def existing_categories(root: Path, type_map: dict) -> dict:
    """label(lowercased) -> folder name. Curated map plus the vault's own
    top-level folders, so notes reuse existing folders (incl. ones made earlier)
    instead of spawning near-duplicates."""
    cats = dict(type_map)  # curated label -> folder (e.g. seo -> SEO)
    seen = {v.lower() for v in cats.values()}
    try:
        children = sorted(root.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.is_dir() and not child.name.startswith((".", "_")):
            if child.name.lower() not in seen:
                cats[child.name.lower()] = child.name
                seen.add(child.name.lower())
    return cats


def build_prompt(cat_map: dict, body: str, allow_new: bool = True) -> list[dict]:
    menu = "\n".join(
        f"- {folder}" + (f": {TYPE_HINTS[label]}" if label in TYPE_HINTS else "")
        for label, folder in cat_map.items()
    )
    system = (
        "You are a precise note classifier for an Obsidian vault. You file each note "
        "into one folder. Strongly prefer an existing folder when one reasonably fits. "
        "Respond with ONLY a compact JSON object, no prose, no code fences."
    )
    if allow_new:
        rule = ("Pick the existing folder that best fits (use its EXACT name). If none "
                "reasonably fits, invent a short new folder name (1-2 words, Title Case, "
                "no punctuation) describing the note's category.")
        new_field = '"is_new": <true if you invented the name, else false>, '
    else:
        rule = ("Pick the existing folder that best fits (use its EXACT name), or use "
                '"unknown" if none fit.')
        new_field = ""
    user = (
        "Existing folders:\n"
        f"{menu}\n\n"
        f"{rule}\n"
        f'Reply as JSON: {{"folder": "<folder name>", {new_field}"confidence": <0.0-1.0>}}\n\n'
        "--- NOTE START ---\n"
        f"{body}\n"
        "--- NOTE END ---"
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def call_minimax(messages: list[dict], *, api_key: str, model: str,
                 base_url: str, timeout: int = 60) -> str:
    """Call the OpenAI-compatible chat completions endpoint. Returns content text."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        # M3 is a reasoning model: it spends tokens thinking before the answer,
        # so this budget must cover reasoning + the small JSON reply.
        "max_tokens": 2048,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_decision(content: str) -> tuple[str | None, bool, float]:
    """Parse the model reply -> (folder or None, is_new, confidence).

    Robust to reasoning models that wrap the answer in <think> blocks, prose, or
    code fences: we pull the LAST flat JSON object that carries a `folder`.
    """
    content = (content or "").strip()
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if content.startswith("```"):
        content = content.strip("`")
        if "\n" in content:
            content = content.split("\n", 1)[1]

    for chunk in reversed(re.findall(r"\{[^{}]*\}", content)):
        try:
            obj = json.loads(chunk)
        except ValueError:
            continue
        if "folder" in obj:
            folder = str(obj.get("folder", "")).strip()
            is_new = bool(obj.get("is_new", False))
            try:
                conf = float(obj.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            return (folder or None), is_new, conf
    return None, False, 0.0


def classify_root(root: Path, type_map: dict, keep: set, *, api_key: str,
                  model: str, base_url: str, dry_run: bool = False,
                  threshold: float = 0.6, max_chars: int = 6000,
                  limit: int | None = None, files=None,
                  allow_new: bool = True) -> tuple[int, dict]:
    """Classify untyped notes and write frontmatter.

    Returns (count_written, used_map) where used_map is label(lower) -> folder for
    every category applied this run, including any NEW folders the model proposed.
    The caller merges used_map into the type map before the sort pass so the new
    folders are honoured. If `files` is given, only those notes are considered.
    """
    cat_map = existing_categories(root, type_map)        # label(lower) -> folder
    folder_lookup = {f.lower(): f for f in cat_map.values()}  # match model replies
    used: dict = {}
    written = 0
    calls = 0
    targets = sorted(files) if files is not None else sorted(root.glob("*.md"))
    for md in targets:  # root only, not recursive
        if md.name in keep:
            continue
        if read_type(md) in cat_map:  # already typed -> sorter handles it
            continue
        if limit is not None and calls >= limit:
            print(f"reached --limit {limit}; stopping")
            break

        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            print(f"skip {md.name} (read error: {e})")
            continue
        if not text.strip():  # empty note: nothing to classify
            print(f"skip {md.name} (empty)")
            continue

        prompt = build_prompt(cat_map, text[:max_chars], allow_new=allow_new)
        calls += 1
        try:
            content = call_minimax(prompt, api_key=api_key, model=model, base_url=base_url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"skip {md.name} (API error: {e}); retrying once...")
            time.sleep(2)
            try:
                content = call_minimax(prompt, api_key=api_key, model=model, base_url=base_url)
            except Exception as e2:  # noqa: BLE001 - unattended run, keep going
                print(f"skip {md.name} (API error after retry: {e2})")
                continue

        folder, is_new, conf = parse_decision(content)
        if not folder or folder.lower() == "unknown" or conf < threshold:
            print(f"skip {md.name} (folder={folder!r} conf={conf:.2f} < {threshold})")
            continue

        if folder.lower() in folder_lookup:        # reuse existing folder
            dest = folder_lookup[folder.lower()]
            new_tag = ""
        elif allow_new:                             # create a new folder
            dest = sanitize_folder(folder)
            if not dest:
                print(f"skip {md.name} (unusable folder name {folder!r})")
                continue
            new_tag = " [NEW folder]"
        else:
            print(f"skip {md.name} (no existing folder fit; --no-new)")
            continue

        label = dest.lower()
        used[label] = dest
        folder_lookup[dest.lower()] = dest  # so the next file reuses it this run
        if dry_run:
            print(f"WOULD file {md.name} -> {dest}/{new_tag} (conf={conf:.2f})")
        else:
            md.write_text(insert_type(text, label), encoding="utf-8")
            print(f"set type: {label} on {md.name} -> {dest}/{new_tag} (conf={conf:.2f})")
        written += 1
    return written, used


def main():
    ap = argparse.ArgumentParser(description="LLM classify untyped vault notes (MiniMax M3).")
    ap.add_argument("vault", help="folder whose untyped root-level .md files should be classified")
    ap.add_argument("--map", type=parse_map, default=DEFAULT_MAP,
                    help="comma list type=folder; the type keys are the allowed labels")
    ap.add_argument("--keep", default=None, help="comma list of filenames to never touch")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="MiniMax model id")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    ap.add_argument("--threshold", type=float, default=0.6, help="min confidence to write")
    ap.add_argument("--max-chars", type=int, default=6000, help="note chars sent to the model")
    ap.add_argument("--limit", type=int, default=None, help="max LLM calls this run (cost cap)")
    ap.add_argument("--no-new", action="store_true",
                    help="do not invent new folders; leave unmatched notes in place")
    ap.add_argument("--dry-run", action="store_true", help="show classifications without writing")
    args = ap.parse_args()

    root = Path(args.vault).expanduser()
    if not root.is_dir():
        sys.exit(f"error: not a directory: {root}")

    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        sys.exit("error: set MINIMAX_API_KEY (your MiniMax API key) in the environment.")

    keep = {x.strip() for x in args.keep.split(",")} if args.keep else DEFAULT_KEEP
    print(f"classifying with model={args.model} via {args.base_url}")
    written, used = classify_root(root, args.map, keep, api_key=api_key, model=args.model,
                                  base_url=args.base_url, dry_run=args.dry_run,
                                  threshold=args.threshold, max_chars=args.max_chars,
                                  limit=args.limit, allow_new=not args.no_new)
    new_folders = sorted(f for lbl, f in used.items() if lbl not in args.map)
    verb = "would write" if args.dry_run else "wrote"
    print(f"done: {verb} type on {written} file(s)")
    if new_folders:
        print(f"new folders proposed: {', '.join(new_folders)}")


if __name__ == "__main__":
    main()

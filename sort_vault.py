#!/usr/bin/env python3
"""Sort loose .md files in a vault/wiki folder into subfolders by `type:` frontmatter.

Deterministic. No network, no LLM. Idempotent. Cross-platform.

    python sort_vault.py "C:\\Users\\me\\knowledge-vault\\wiki"
    python sort_vault.py ~/other-vault --map note=notes,ref=references --dry-run

This is the deterministic mover. The LLM classification pass lives in
classify_vault.py; auto_sort.py runs both in sequence.
"""
import argparse
import shutil
import sys
from pathlib import Path

# default convention (override with --map / --keep)
# tuned for the bluesky-agent vault: label -> existing folder name (case-sensitive)
DEFAULT_MAP = {
    "agent": "Agents",
    "company": "Companies",
    "knowledge": "Knowledge",
    "topic": "Topics",
    "strategy": "Strategy",
    "seo": "SEO",
}
DEFAULT_KEEP = {
    "Welcome.md", "USAGE.md", "SYNTHESIS_REPORT.md", "README.md", "index.md",
}


def read_type(md: Path) -> str | None:
    """Pull the `type:` value from YAML frontmatter, if present."""
    try:
        lines = md.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    if not lines or lines[0].lstrip("﻿").strip() != "---":  # tolerate a BOM
        return None
    for line in lines[1:]:
        if line.strip() == "---":  # end of frontmatter
            break
        if line.startswith("type:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'").lower()
    return None


def parse_map(s: str) -> dict:
    out = {}
    for pair in s.split(","):
        pair = pair.strip()
        if not pair:
            continue
        k, _, v = pair.partition("=")
        out[k.strip().lower()] = v.strip()
    return out


def sort_root(root: Path, type_map: dict, keep: set, dry_run: bool = False,
              files=None, on_move=None) -> int:
    """Move root-level .md files into folders by type. Returns count moved.

    If `files` is given (an iterable of Paths), only those are considered;
    otherwise every root-level *.md is scanned. `on_move(name, folder)` is called
    for each file actually moved (not in dry-run).
    """
    moved = 0
    targets = sorted(files) if files is not None else sorted(root.glob("*.md"))
    for md in targets:  # root only, not recursive
        if md.name in keep:
            continue
        t = read_type(md)
        folder = type_map.get(t)
        if not folder:  # unknown/missing type -> leave it
            print(f"skip {md.name} (type={t!r})")
            continue
        dest_dir = root / folder
        dest = dest_dir / md.name
        if dest.exists():  # don't clobber
            print(f"skip {md.name} (already in {folder}/)")
            continue
        if dry_run:
            print(f"WOULD move {md.name} -> {folder}/")
        else:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(md), str(dest))
            print(f"move {md.name} -> {folder}/")
            if on_move:
                on_move(md.name, folder)
        moved += 1
    return moved


def main():
    ap = argparse.ArgumentParser(description="Sort loose .md files by `type:` frontmatter.")
    ap.add_argument("vault", help="folder whose root-level .md files should be sorted")
    ap.add_argument("--map", type=parse_map, default=DEFAULT_MAP,
                    help="comma list type=folder, e.g. concept=concepts,entity=entities")
    ap.add_argument("--keep", default=None,
                    help="comma list of filenames to never move (overrides default)")
    ap.add_argument("--dry-run", action="store_true", help="show moves without doing them")
    args = ap.parse_args()

    root = Path(args.vault).expanduser()
    if not root.is_dir():
        sys.exit(f"error: not a directory: {root}")

    keep = {x.strip() for x in args.keep.split(",")} if args.keep else DEFAULT_KEEP
    moved = sort_root(root, args.map, keep, args.dry_run)

    verb = "would sort" if args.dry_run else "sorted"
    print(f"done: {verb} {moved} file(s)")


if __name__ == "__main__":
    main()

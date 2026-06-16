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

# Documents are filed by extension (they can't carry a `type:`). Deterministic,
# no LLM, no text extraction -> works for any file regardless of contents.
# Images are intentionally NOT here: moving them on disk breaks Obsidian embeds.
DEFAULT_DOC_MAP = {
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".odt": "Documents", ".rtf": "Documents", ".txt": "Documents",
    ".ppt": "Presentations", ".pptx": "Presentations", ".odp": "Presentations",
    ".xls": "Spreadsheets", ".xlsx": "Spreadsheets", ".csv": "Spreadsheets",
    ".ods": "Spreadsheets",
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


def parse_doc_map(s: str) -> dict:
    """Parse 'pdf=Documents,xlsx=Spreadsheets' -> {'.pdf': 'Documents', ...}."""
    out = {}
    for k, v in parse_map(s).items():
        ext = k if k.startswith(".") else "." + k
        out[ext.lower()] = v
    return out


def _root_targets(root: Path, doc_map: dict | None):
    """Every root-level file we might sort: all *.md, plus doc extensions if on."""
    names = {p for p in root.glob("*.md") if p.is_file()}
    if doc_map:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in doc_map:
                names.add(p)
    return sorted(names)


def sort_root(root: Path, type_map: dict, keep: set, dry_run: bool = False,
              files=None, on_move=None, doc_map: dict | None = None) -> int:
    """Move root-level files into folders. Returns count moved.

    Markdown is filed by its `type:` frontmatter (via `type_map`); documents are
    filed by extension (via `doc_map`, e.g. .pdf -> Documents). If `files` is given
    only those are considered; otherwise every root-level *.md (plus doc extensions
    when `doc_map` is set) is scanned. `on_move(name, folder)` fires per move.
    """
    moved = 0
    targets = sorted(files) if files is not None else _root_targets(root, doc_map)
    for item in targets:  # root only, not recursive
        if item.name in keep:
            continue
        suffix = item.suffix.lower()
        if suffix == ".md":                       # note -> file by frontmatter type
            t = read_type(item)
            folder = type_map.get(t)
            miss = f"type={t!r}"
        elif doc_map and suffix in doc_map:        # document -> file by extension
            folder = doc_map[suffix]
            miss = f"ext={suffix}"
        else:
            continue                               # not a sortable file -> leave it
        if not folder:  # unknown/missing type -> leave it
            print(f"skip {item.name} ({miss})")
            continue
        dest_dir = root / folder
        dest = dest_dir / item.name
        if dest.exists():  # don't clobber
            print(f"skip {item.name} (already in {folder}/)")
            continue
        if dry_run:
            print(f"WOULD move {item.name} -> {folder}/")
        else:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(dest))
            print(f"move {item.name} -> {folder}/")
            if on_move:
                on_move(item.name, folder)
        moved += 1
    return moved


def main():
    ap = argparse.ArgumentParser(description="Sort loose .md files by `type:` frontmatter.")
    ap.add_argument("vault", help="folder whose root-level .md files should be sorted")
    ap.add_argument("--map", type=parse_map, default=DEFAULT_MAP,
                    help="comma list type=folder, e.g. concept=concepts,entity=entities")
    ap.add_argument("--keep", default=None,
                    help="comma list of filenames to never move (overrides default)")
    ap.add_argument("--doc-map", type=parse_doc_map, default=DEFAULT_DOC_MAP,
                    help="comma list ext=folder for documents, e.g. pdf=Docs,xlsx=Sheets")
    ap.add_argument("--no-docs", action="store_true",
                    help="sort Markdown only; leave pdf/docx/etc. in place")
    ap.add_argument("--dry-run", action="store_true", help="show moves without doing them")
    args = ap.parse_args()

    root = Path(args.vault).expanduser()
    if not root.is_dir():
        sys.exit(f"error: not a directory: {root}")

    keep = {x.strip() for x in args.keep.split(",")} if args.keep else DEFAULT_KEEP
    doc_map = None if args.no_docs else args.doc_map
    moved = sort_root(root, args.map, keep, args.dry_run, doc_map=doc_map)

    verb = "would sort" if args.dry_run else "sorted"
    print(f"done: {verb} {moved} file(s)")


if __name__ == "__main__":
    main()

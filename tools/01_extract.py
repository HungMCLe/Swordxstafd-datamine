#!/usr/bin/env python3
"""Stage 1 - Unpack an Android game package into out/extracted/.

Handles .apk, .apks, .xapk, .aab and plain .zip. Split/bundle formats
(.xapk / .apks) are ZIP containers holding one or more inner .apk files
plus (for .xapk) OBB expansion data; every inner archive is unzipped in
turn so the final tree contains all DEX, native libs, and assets.

Usage:
    python3 tools/01_extract.py path/to/game.xapk
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import EXTRACTED, banner, dim, ensure_dirs, green, human, red, yellow

INNER_ARCHIVE_SUFFIXES = {".apk", ".zip"}


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> int:
    """Extract a zip, guarding against path traversal (zip-slip)."""
    dest = dest.resolve()
    count = 0
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not str(target).startswith(str(dest)):
            print(red(f"  ! skipping unsafe path: {member.filename}"))
            continue
        zf.extract(member, dest)
        count += 1
    return count


def _unpack(archive: Path, dest: Path, depth: int = 0) -> None:
    indent = "  " * (depth + 1)
    if not zipfile.is_zipfile(archive):
        print(yellow(f"{indent}{archive.name} is not a zip; leaving as-is"))
        return
    print(f"{indent}unpacking {archive.name} ({human(archive.stat().st_size)})")
    with zipfile.ZipFile(archive) as zf:
        n = _safe_extract(zf, dest)
    print(dim(f"{indent}  -> {n} entries"))

    # Recurse into inner apk/zip archives (split apks, bundled obb apks).
    for inner in sorted(dest.rglob("*")):
        if inner.is_file() and inner.suffix.lower() in INNER_ARCHIVE_SUFFIXES:
            if inner.resolve() == archive.resolve():
                continue
            sub = inner.with_suffix(inner.suffix + ".contents")
            sub.mkdir(exist_ok=True)
            _unpack(inner, sub, depth + 1)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1]).expanduser()
    if not src.exists():
        print(red(f"File not found: {src}"))
        return 1

    banner("Stage 1 - Extract package")
    ensure_dirs()
    if EXTRACTED.exists() and any(EXTRACTED.iterdir()):
        print(yellow(f"Clearing previous extraction at {EXTRACTED}"))
        shutil.rmtree(EXTRACTED)
    EXTRACTED.mkdir(parents=True, exist_ok=True)

    _unpack(src, EXTRACTED)

    files = list(EXTRACTED.rglob("*"))
    n_files = sum(1 for f in files if f.is_file())
    print(green(f"\nExtracted {n_files} files to {EXTRACTED}"))
    # Quick landmark inventory to orient the next stages.
    for landmark in ("base.apk.contents", "AndroidManifest.xml", "classes.dex",
                     "lib", "assets", "assets/bin/Data"):
        hit = list(EXTRACTED.rglob(landmark))
        if hit:
            print(dim(f"  found: {landmark}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

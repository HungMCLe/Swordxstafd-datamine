#!/usr/bin/env python3
"""Stage 3 - Collect the game's data/config files into out/configs/.

Mobile RPGs keep their balance data (hero stats, skill coefficients, drop
rates, level curves) in bundled data files. This stage copies every
plausible data file out of the extracted tree, preserving relative paths,
so the numbers are in one browsable place. JSON is pretty-printed when it
parses. Binary blobs (protobuf, Unity .assets) are copied verbatim for the
engine-specific stages to crack open.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (CONFIGS, EXTRACTED, banner, dim, ensure_dirs, green, human,
                 red, yellow)

# Extensions worth collecting as data.
DATA_EXTS = {
    ".json", ".csv", ".tsv", ".xml", ".yaml", ".yml", ".txt", ".ini",
    ".lua", ".luac", ".js", ".dat", ".bytes", ".bin", ".pb", ".proto",
    ".conf", ".cfg", ".plist", ".table", ".tab",
}
# Filename keywords that flag a data file even with an odd extension.
NAME_KEYWORDS = (
    "config", "data", "table", "formula", "skill", "hero", "char", "unit",
    "stat", "attr", "battle", "combat", "damage", "level", "exp", "growth",
    "balance", "monster", "enemy", "item", "equip", "drop", "reward", "buff",
)
# Noise to skip (Android resources, images, fonts, audio, shaders).
SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ktx", ".astc", ".pkm",
    ".ttf", ".otf", ".mp3", ".ogg", ".wav", ".mp4", ".fsb", ".bank",
    ".so", ".dex", ".arsc", ".version", ".properties",
}
MAX_JSON_PRETTY = 25 * 1024 * 1024  # don't try to reflow >25MB json


def interesting(p: Path) -> bool:
    ext = p.suffix.lower()
    if ext in SKIP_EXTS:
        return False
    name = p.name.lower()
    if ext in DATA_EXTS:
        return True
    if any(k in name for k in NAME_KEYWORDS):
        return True
    return False


def main() -> int:
    banner("Stage 3 - Dump config / data files")
    if not EXTRACTED.exists():
        print(red("out/extracted missing - run Stage 1 first."))
        return 1
    ensure_dirs()

    copied = 0
    pretty = 0
    total_bytes = 0
    by_ext: dict[str, int] = {}

    for src in EXTRACTED.rglob("*"):
        if not src.is_file() or not interesting(src):
            continue
        rel = src.relative_to(EXTRACTED)
        dest = CONFIGS / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.suffix.lower() == ".json" and src.stat().st_size <= MAX_JSON_PRETTY:
            try:
                obj = json.loads(src.read_text(encoding="utf-8", errors="replace"))
                dest.write_text(json.dumps(obj, indent=2, ensure_ascii=False),
                                encoding="utf-8")
                pretty += 1
            except (json.JSONDecodeError, UnicodeError, OSError):
                shutil.copy2(src, dest)
        else:
            shutil.copy2(src, dest)

        copied += 1
        sz = src.stat().st_size
        total_bytes += sz
        by_ext[src.suffix.lower() or "(none)"] = by_ext.get(src.suffix.lower() or "(none)", 0) + 1

    print(green(f"Copied {copied} data files ({human(total_bytes)}) to {CONFIGS}"))
    print(dim(f"  pretty-printed {pretty} JSON files"))
    print(yellow("\nBy extension:"))
    for ext, n in sorted(by_ext.items(), key=lambda kv: -kv[1]):
        print(dim(f"  {ext:10s} {n}"))

    # Surface the biggest data files - balance tables tend to be large.
    big = sorted((p for p in CONFIGS.rglob("*") if p.is_file()),
                 key=lambda p: -p.stat().st_size)[:20]
    if big:
        print(yellow("\nLargest data files (likely balance tables):"))
        for p in big:
            print(dim(f"  {human(p.stat().st_size):>9s}  {p.relative_to(CONFIGS)}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

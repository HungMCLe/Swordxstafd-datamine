"""Shared helpers for the Sword x Staff datamining toolkit."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root = parent of the tools/ directory this file lives in.
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
EXTRACTED = OUT / "extracted"
CONFIGS = OUT / "configs"
JADX = OUT / "jadx"
IL2CPP = OUT / "il2cpp"
UNITY = OUT / "unity_assets"
TOOLS = ROOT / "_tools"

# ANSI colors (disabled when not a tty).
_TTY = sys.stdout.isatty()
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s
def bold(s): return _c("1", s)
def green(s): return _c("32", s)
def yellow(s): return _c("33", s)
def red(s): return _c("31", s)
def cyan(s): return _c("36", s)
def dim(s): return _c("2", s)


def banner(title: str) -> None:
    line = "=" * max(8, len(title) + 4)
    print()
    print(cyan(line))
    print(cyan(f"  {title}"))
    print(cyan(line))


def human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.1f}{unit}" if unit != "B" else f"{int(f)}B"
        f /= 1024
    return f"{f:.1f}TB"


def iter_files(root: Path):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            yield Path(dirpath) / name


def ensure_dirs() -> None:
    for d in (OUT, EXTRACTED, CONFIGS, JADX, IL2CPP, UNITY, TOOLS):
        d.mkdir(parents=True, exist_ok=True)

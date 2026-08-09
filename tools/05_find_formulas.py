#!/usr/bin/env python3
"""Stage 5 - Hunt for damage/stat/economy formulas across everything dumped.

Scans the decompiled code (out/jadx, out/il2cpp), the collected data files
(out/configs), and Unity asset dumps (out/unity_assets). It scores each file
by how much combat/stat math it contains, then writes a ranked Markdown
report (out/REPORT_formulas.md) with the actual formula lines and context so
you can read the calculations directly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (CONFIGS, IL2CPP, JADX, OUT, UNITY, banner, dim, green, human,
                 red, yellow)

SCAN_DIRS = [
    ("code:il2cpp", IL2CPP),
    ("code:java", JADX),
    ("data:configs", CONFIGS),
    ("data:unity", UNITY),
]

TEXT_EXTS = {".cs", ".java", ".json", ".txt", ".lua", ".js", ".csv", ".tsv",
             ".xml", ".yaml", ".yml", ".h", ".ini", ".cfg", ".table"}
MAX_BYTES = 60 * 1024 * 1024  # skip files larger than this

# High-value method / symbol names (strong formula signal).
METHOD_RE = re.compile(
    r"\b(calc(?:ulate)?|compute|formula|damage|takedamage|dealdamage|"
    r"applydamage|onhit|gethit|attackpower|defense|mitigation|critical|"
    r"critrate|critdamage|hitchance|dodge|evasion|penetration|resist|"
    r"healamount|levelup|expcurve|growth|scaling)\w*",
    re.IGNORECASE)

# Stat vocabulary - common RPG attribute tokens. Boundaries treat letters as
# the only "inside" chars, so underscores/quotes/digits delimit: this matches
# base_atk, atk_growth, crit_rate as well as bare atk/crit.
STAT_RE = re.compile(
    r"(?<![a-zA-Z])(atk|attack|def|defen[cs]e|hp|mp|health|mana|dmg|damage|"
    r"crit|critical|speed|spd|dodge|evasion|accuracy|hit|penetrat|armor|"
    r"resist|block|parry|lifesteal|vampir|haste|coeff|coefficient|ratio|"
    r"multiplier|scaling|growth|bonus|reduc|mitigat|level|lvl|exp|power)"
    r"(?![a-zA-Z])",
    re.IGNORECASE)

# Arithmetic operators / math calls that indicate an actual computation.
MATH_RE = re.compile(
    r"[*/]|(?<![<>=!+\-*/])[+\-](?![+\-])|"
    r"\b(Math|Mathf)\.\w+|\b(pow|sqrt|floor|ceil|round|min|max|clamp|log|exp)\s*\(")


def score_line(line: str) -> tuple[int, bool]:
    """Return (weight, is_formula_snippet) for one line."""
    has_stat = bool(STAT_RE.search(line))
    has_math = bool(MATH_RE.search(line))
    has_method = bool(METHOD_RE.search(line))
    w = 0
    if has_method:
        w += 3
    if has_stat and has_math:
        w += 4  # stat token combined with arithmetic = likely a formula
    elif has_stat:
        w += 1
    elif has_math and has_method:
        w += 2
    is_formula = (has_stat and has_math) or (has_method and has_math)
    return w, is_formula


def scan_file(path: Path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    total = 0
    snippets = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or len(s) > 400:
            continue
        w, is_formula = score_line(s)
        if w:
            total += w
        if is_formula and len(snippets) < 60:
            snippets.append((i, s[:300]))
    if total == 0:
        return None
    return total, snippets


def main() -> int:
    banner("Stage 5 - Find formulas")
    results = []  # (score, source_label, path, snippets)
    scanned = 0
    for label, root in SCAN_DIRS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in TEXT_EXTS:
                continue
            scanned += 1
            r = scan_file(p)
            if r:
                score, snippets = r
                results.append((score, label, p, snippets))

    if not results:
        print(red("Nothing scanned. Run Stages 1-4 first (need out/jadx, out/configs, ...)."))
        return 1

    results.sort(key=lambda x: -x[0])
    print(green(f"Scanned {scanned} text files; {len(results)} contain stat/formula math."))
    print(yellow("\nTop files by formula score:"))
    for score, label, p, _ in results[:25]:
        rel = _rel(p)
        print(dim(f"  {score:5d}  [{label:12s}] {rel}"))

    _write_report(results)
    print(green(f"\nFull report: {OUT/'REPORT_formulas.md'}"))
    return 0


def _rel(p: Path) -> str:
    for base in (JADX, IL2CPP, CONFIGS, UNITY):
        try:
            return str(p.relative_to(base.parent))
        except ValueError:
            continue
    return str(p)


def _write_report(results) -> None:
    lines = ["# Sword x Staff - formula report", "",
             "Files ranked by density of combat/stat math. Each snippet is a line",
             "that pairs a stat token (atk, def, crit, hp, exp, ...) with arithmetic",
             "or lives in a damage/calc method. Read the top code files first for the",
             "logic, then the data files for the coefficients that feed it.", "",
             f"Total files with formula signal: **{len(results)}**", "",
             "## Ranked files", ""]
    lines.append("| # | score | source | file |")
    lines.append("|--:|------:|--------|------|")
    for i, (score, label, p, _) in enumerate(results[:60], 1):
        lines.append(f"| {i} | {score} | {label} | `{_rel(p)}` |")
    lines += ["", "## Formula snippets (top 40 files)", ""]
    for score, label, p, snippets in results[:40]:
        if not snippets:
            continue
        lines.append(f"### `{_rel(p)}`  \n_score {score} · {label}_\n")
        lines.append("```")
        for ln, text in snippets[:40]:
            lines.append(f"{ln:>6}: {text}")
        lines.append("```")
        lines.append("")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "REPORT_formulas.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract Unity data assets (MonoBehaviour, TextAsset, ScriptableObject)
into out/unity_assets/ as JSON/text using UnityPy.

In Unity RPGs the balance data - hero base stats, skill coefficients, level
curves - is authored as ScriptableObjects and serialized into AssetBundles
or resources.assets as MonoBehaviour type-trees. UnityPy reads those trees
without needing the game running, so the numbers come out as plain JSON.
TextAssets often hold raw JSON/CSV/Lua config too.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import EXTRACTED, UNITY, dim, green, red, yellow

try:
    import UnityPy
except ImportError:
    print(red("UnityPy not installed - run tools/00_setup.sh"))
    raise SystemExit(1)

# Unity serialized-asset containers to scan.
ASSET_GLOBS = ("*.assets", "*.bundle", "*.unity3d", "*.resource", "*.dat")


def _safe_name(s: str, fallback: str) -> str:
    s = "".join(c if c.isalnum() or c in "._- " else "_" for c in (s or "")).strip()
    return s or fallback


def main() -> int:
    UNITY.mkdir(parents=True, exist_ok=True)
    candidates: list[Path] = []
    for g in ASSET_GLOBS:
        candidates += [p for p in EXTRACTED.rglob(g) if p.is_file()]
    # also the common Unity data dir even with no extension
    candidates += [p for p in EXTRACTED.rglob("*")
                   if p.is_file() and "bin/Data" in str(p) and p.suffix == ""]
    candidates = sorted(set(candidates))

    if not candidates:
        print(yellow("No Unity asset containers found."))
        return 0

    print(dim(f"Scanning {len(candidates)} candidate asset files..."))
    n_text = n_mono = n_err = 0

    for path in candidates:
        try:
            env = UnityPy.load(str(path))
        except Exception:
            continue
        for obj in env.objects:
            try:
                if obj.type.name == "TextAsset":
                    data = obj.read()
                    name = _safe_name(getattr(data, "m_Name", "") or getattr(data, "name", ""),
                                      f"text_{obj.path_id}")
                    script = getattr(data, "m_Script", None) or getattr(data, "script", None)
                    raw = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else (script or b"")
                    (UNITY / f"{name}.txt").write_bytes(raw)
                    n_text += 1
                elif obj.type.name in ("MonoBehaviour", "ScriptableObject"):
                    if not obj.serialized_type or not obj.serialized_type.node:
                        continue  # no type-tree -> can't read fields generically
                    tree = obj.read_typetree()
                    name = _safe_name(tree.get("m_Name", ""), f"mono_{obj.path_id}")
                    (UNITY / f"{name}.json").write_text(
                        json.dumps(tree, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
                    n_mono += 1
            except Exception:
                n_err += 1
                continue

    print(green(f"Dumped {n_mono} MonoBehaviour/ScriptableObject + {n_text} TextAsset files "
                f"to {UNITY}"))
    if n_err:
        print(dim(f"  ({n_err} objects skipped - no type-tree or read error)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage 2 - Identify the game engine and print where formulas likely live.

The engine dictates the whole extraction strategy:
  * Unity IL2CPP  -> code compiled to native libil2cpp.so; reverse with
                     Il2CppDumper (needs global-metadata.dat). Data lives in
                     AssetBundles / resources.assets as MonoBehaviours & TextAssets.
  * Unity Mono    -> C# in Managed/*.dll; decompile directly (dnSpy/ILSpy).
  * Cocos2d-x     -> gameplay in Lua/JS scripts (often bytecode-compiled or
                     XXTEA-encrypted) under assets/.
  * Unreal        -> content in .pak files; blueprints in native libUE*.so.
The result is written to out/ENGINE.md and echoed to the console.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import EXTRACTED, OUT, banner, bold, cyan, dim, green, human, red, yellow


def find(patterns):
    hits = []
    for pat in patterns:
        hits += [p for p in EXTRACTED.rglob(pat) if p.is_file()]
    return hits


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(EXTRACTED))
    except ValueError:
        return str(p)


def main() -> int:
    banner("Stage 2 - Detect engine")
    if not EXTRACTED.exists() or not any(EXTRACTED.iterdir()):
        print(red("out/extracted is empty - run Stage 1 first."))
        return 1

    so_files = find(["*.so"])
    so_names = {p.name for p in so_files}

    signals = {
        "unity": bool(so_names & {"libunity.so", "libil2cpp.so", "libmono.so",
                                  "libmonobdwgc-2.0.so"})
                 or bool(find(["assets/bin/Data/*", "**/global-metadata.dat"])),
        "il2cpp": "libil2cpp.so" in so_names or bool(find(["**/global-metadata.dat"])),
        "mono": bool(so_names & {"libmono.so", "libmonobdwgc-2.0.so"})
                or bool(find(["**/Managed/*.dll"])),
        "cocos": bool(so_names & {"libcocos2djs.so", "libcocos2dlua.so", "libcocos.so"})
                 or bool(find(["**/*.luac", "src/*.lua", "**/main.lua"])),
        "unreal": any(n.startswith("libUE") for n in so_names)
                  or bool(find(["**/*.pak"])),
        "godot": bool(find(["**/*.pck"])) or "libgodot_android.so" in so_names,
        "flutter": "libflutter.so" in so_names,
    }

    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out(bold("Native libraries (.so):"))
    if so_files:
        for p in sorted(so_files, key=lambda x: x.name)[:40]:
            out(dim(f"  {p.name:32s} {human(p.stat().st_size):>9s}  {rel(p)}"))
    else:
        out(dim("  (none found)"))

    engine = "unknown"
    if signals["unity"]:
        engine = "Unity (IL2CPP)" if signals["il2cpp"] else (
                 "Unity (Mono)" if signals["mono"] else "Unity")
    elif signals["cocos"]:
        engine = "Cocos2d-x"
    elif signals["unreal"]:
        engine = "Unreal Engine"
    elif signals["godot"]:
        engine = "Godot"
    elif signals["flutter"]:
        engine = "Flutter"

    out()
    out(bold(f"Detected engine: ") + cyan(engine))

    # Landmark files that matter for extraction.
    landmarks = {
        "global-metadata.dat": find(["**/global-metadata.dat"]),
        "libil2cpp.so": [p for p in so_files if p.name == "libil2cpp.so"],
        "Managed/*.dll (Mono)": find(["**/Managed/*.dll"]),
        "AssetBundles/resources.assets": find(["**/*.assets", "**/*.bundle", "**/*.unity3d"]),
        "Lua scripts": find(["**/*.lua", "**/*.luac"]),
        "JSON/CSV data": find(["**/*.json"]) + find(["**/*.csv"]),
        "protobuf (.proto/.pb)": find(["**/*.proto", "**/*.pb"]),
    }
    out()
    out(bold("Key landmarks:"))
    for label, hits in landmarks.items():
        if hits:
            out(green(f"  [x] {label}: {len(hits)} file(s)"))
            for p in hits[:3]:
                out(dim(f"        {rel(p)}"))
        else:
            out(dim(f"  [ ] {label}: none"))

    # Engine-specific guidance for the next stages.
    tips = {
        "Unity (IL2CPP)": [
            "Run Stage 4: Il2CppDumper on global-metadata.dat + libil2cpp.so",
            "  -> produces dump.cs with every class/method + field names.",
            "Formulas: search dump.cs for Damage/Attack/Calc* methods (Stage 5),",
            "  and dump MonoBehaviour/TextAsset data from AssetBundles (Stage 4 Unity).",
        ],
        "Unity (Mono)": [
            "Decompile Managed/*.dll with ILSpy/dnSpy (readable C#).",
            "Formulas are directly readable in the Assembly-CSharp.dll classes.",
        ],
        "Unity": [
            "Confirm IL2CPP vs Mono (presence of libil2cpp.so vs Managed/*.dll).",
        ],
        "Cocos2d-x": [
            "Lua/JS is the gameplay layer. If .luac (bytecode) or encrypted,",
            "  identify the XXTEA key (often in libcocos*.so strings) to decrypt.",
            "Formulas live in the .lua config/logic files - Stage 5 will grep them.",
        ],
        "Unreal Engine": [
            "Unpack .pak files with UnrealPak / repak; logic is in native libUE*.so.",
        ],
        "unknown": [
            "Fall back to jadx on the DEX (Stage 4) and grep everything (Stage 5).",
        ],
    }
    out()
    out(bold("Recommended next steps:"))
    for t in tips.get(engine, tips["unknown"]):
        out(yellow(f"  - {t}"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ENGINE.md").write_text(
        "# Engine detection\n\n```\n" + "\n".join(lines) + "\n```\n", encoding="utf-8")
    (OUT / "engine.txt").write_text(engine, encoding="utf-8")
    print(dim(f"\nWrote {OUT/'ENGINE.md'}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

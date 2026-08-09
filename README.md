# Sword x Staff — datamining toolkit

A one-command pipeline to pull the **formulas and calculations** out of
*Sword x Staff* (Boltray Games, package `com.zjcs.android.us`) — damage
math, stat growth curves, crit/defense mitigation, level/EXP curves, drop
rates, and the balance tables that feed them.

> **Goal:** read the game's math, not modify or redistribute the game.
> This repo contains *tools only* — no game assets are committed (see
> `.gitignore`). You supply the `.apk`/`.xapk`; the scripts do the rest.

---

## Quick start

```bash
# 1. Get the game package onto a machine that can reach an app store / mirror.
#    (Google Play via an emulator, or an .xapk from a mirror — see docs/GET_THE_APK.md)

# 2. Point the pipeline at it:
./datamine.sh ~/Downloads/SwordxStaff.xapk

# 3. Read the results:
open out/REPORT_formulas.md      # ranked list of every file with combat/stat math
```

That's the whole thing. `datamine.sh` runs all six stages and drops
everything into `./out/`.

---

## What it produces (`./out/`)

| Output | What's in it |
|--------|--------------|
| `REPORT_formulas.md` | **Start here.** Files ranked by how much stat/damage math they contain, with the actual formula lines quoted. |
| `ENGINE.md` | Which engine the game uses and where its data lives. |
| `il2cpp/dump.cs` | Every C# class/method/field name recovered from the compiled code (Unity IL2CPP games). This is where the damage logic lives. |
| `jadx/` | The Android app decompiled to readable Java (launcher/SDK layer). |
| `configs/` | Every bundled data file (JSON/CSV/Lua/…): hero stats, skill tables, curves. |
| `unity_assets/` | Unity `ScriptableObject`/`MonoBehaviour`/`TextAsset` data dumped to JSON — the balance tables. |

---

## The stages

Run individually if you want, or let `datamine.sh` chain them:

| Stage | Script | Does |
|------:|--------|------|
| 0 | `tools/00_setup.sh` | Downloads apktool, jadx, Il2CppDumper (from GitHub) + installs UnityPy. |
| 1 | `tools/01_extract.py` | Unpacks the `.apk`/`.xapk`/`.apks` (recursively unzips split/bundled apks). |
| 2 | `tools/02_detect_engine.py` | Detects Unity IL2CPP / Unity Mono / Cocos2d-x / Unreal / … and prints where formulas live. |
| 3 | `tools/03_dump_configs.py` | Collects every data/config file into `out/configs/`, pretty-printing JSON. |
| 4 | `tools/04_decompile.sh` | jadx (Java) + apktool (resources) + Il2CppDumper (`dump.cs`) + UnityPy (asset data). |
| 5 | `tools/05_find_formulas.py` | Scores every text/code file for stat+math, writes `REPORT_formulas.md`. |

---

## Requirements on your machine

- **Python 3.8+** (stages 1/2/3/5, UnityPy) — required.
- **Java 8+** (`java`) — for jadx + apktool.
- **.NET 6+** (`dotnet`) — for Il2CppDumper (Unity IL2CPP symbol recovery).
  Without it you still get everything else; the script tells you exactly
  which two files to run Il2CppDumper against on a Windows box.
- **~10 GB free disk** — a 2.4 GB package expands a lot when decompiled.

`tools/00_setup.sh` fetches the RE tools; you only need the runtimes above.

---

## How this works, in one paragraph

Sword x Staff is (almost certainly) a **Unity IL2CPP** game: the C# gameplay
code is ahead-of-time compiled into `libil2cpp.so`, with all the names
stripped into `global-metadata.dat`. `Il2CppDumper` marries those two back
together to produce `dump.cs` — a full class/method/field listing where you
can read `CalcDamage(...)`, `GetFinalAttack(...)`, mitigation curves, and so
on. The *numbers* those methods use (base stats, growth per level, skill
coefficients) are authored as Unity `ScriptableObject`s and shipped in
AssetBundles / `resources.assets`, which `UnityPy` dumps to JSON. Stage 5
then greps across both to rank where the real math is. See
[`docs/DATAMINING_GUIDE.md`](docs/DATAMINING_GUIDE.md) for the full picture
and [`docs/FORMULA_HUNTING.md`](docs/FORMULA_HUNTING.md) for exactly where to
look once the dump is ready.

---

## Legal / ethical note

This toolkit is for **understanding** the game's mechanics — the kind of
analysis wikis and theorycrafters do. It reads files you already have from a
package you legitimately obtained. Don't commit or redistribute the game's
copyrighted assets, and respect Boltray's terms of service. Nothing here
modifies, repacks, or cheats the game.

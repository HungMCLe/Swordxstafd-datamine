# Datamining guide — how to read a mobile RPG's formulas

This is the mental model behind the toolkit. Read it once and the output of
`./datamine.sh` will make sense.

## 1. A mobile game package is just a zip

- `.apk` — a ZIP. Inside: `classes*.dex` (compiled app code), `lib/<abi>/*.so`
  (native libraries), `assets/` and `res/` (data), `AndroidManifest.xml`.
- `.xapk` / `.apks` — a ZIP **of** apks: a `base.apk` plus split apks
  (per-language, per-density, per-ABI) and, for `.xapk`, OBB expansion data.
  Stage 1 unzips all of it recursively.

The gameplay code and data are **not** in the Java/DEX for most commercial
games — the DEX is a thin launcher around a game engine. So the first real
question is: *which engine?*

## 2. Identify the engine (Stage 2)

Look at `lib/<abi>/*.so`:

| You see… | Engine | Where the code is | Where the data is |
|----------|--------|-------------------|-------------------|
| `libil2cpp.so` + `global-metadata.dat` | **Unity (IL2CPP)** | native, names in metadata → `dump.cs` | AssetBundles / `resources.assets` (ScriptableObjects) |
| `libmono*.so` + `Managed/*.dll` | **Unity (Mono)** | plain .NET DLLs (very readable) | same as above |
| `libcocos2d*.so`, `*.lua`/`*.luac` | **Cocos2d-x** | Lua/JS scripts (maybe bytecode/encrypted) | Lua tables / JSON |
| `libUE*.so`, `*.pak` | **Unreal** | native + blueprints | `.pak` archives |

Sword x Staff's package layout points to **Unity IL2CPP**, the most common
choice for this genre.

## 3. Recover the code names — IL2CPP (Stage 4)

IL2CPP compiles C# to C++/native, then strips symbol names into a single
file, `global-metadata.dat`. `Il2CppDumper` reads that file plus
`libil2cpp.so` and reconstructs:

- `dump.cs` — every class, method signature, field, and enum. You can't see
  method *bodies* here, but the **names and structure** tell you exactly what
  computes what: `BattleUnit.CalcDamage`, `Attribute.GetFinalAtk`,
  `DamageHelper.Mitigation`, etc.
- `il2cpp.h`, `script.json` — for loading into Ghidra/IDA to read actual
  method bodies (the arithmetic) when the name isn't enough.

**Reading the real arithmetic:** open `libil2cpp.so` in Ghidra, run the
`Il2CppDumper` Ghidra script (`script.json` + `ghidra_with_struct.py`, shipped
in the tool zip) to apply the recovered names, then jump to the address of
`CalcDamage` and read the decompiled C. That's where `atk * (1 - def/(def+k))`
lives.

## 4. Recover the numbers — Unity assets (Stage 4)

Balance data is authored as **ScriptableObjects** and serialized into
AssetBundles or `resources.assets` as `MonoBehaviour` type-trees. `UnityPy`
walks those trees without running the game and writes each one as JSON:
hero base stats, per-level growth, skill coefficients, drop weights. It also
extracts `TextAsset`s, which frequently hold raw JSON/CSV/Lua config directly.

## 5. Cross-reference (Stage 5)

`05_find_formulas.py` scans `dump.cs`, the Java, the config files, and the
Unity JSON, scoring each file by how much it pairs **stat words** (atk, def,
crit, hp, exp…) with **arithmetic** (`* / + -`, `Mathf.*`, `pow/floor/min…`)
or sits inside a **calc/damage method**. The ranked `REPORT_formulas.md` is
your index into the whole dump — top code files give the logic, top data
files give the coefficients.

## 6. Putting a formula together

A worked example of the loop you'll run:

1. `REPORT_formulas.md` points at `BattleUnit.CalcDamage` in `dump.cs`.
2. Its signature: `int CalcDamage(BattleUnit target, SkillData skill)`.
3. Open the body in Ghidra → you read
   `dmg = (atk * skillRatio - def * 0.5) * critMult * elementMult`.
4. `skillRatio`, `critMult`, `elementMult` are fields → find their values in
   the Unity `SkillData` JSON under `out/unity_assets/`.
5. You now have the full formula **and** its constants. Write it up.

## Common obstacles

- **No `dotnet` locally** → run Il2CppDumper on Windows, or install .NET 6+.
  Stage 4 prints the exact two file paths to feed it.
- **Encrypted `global-metadata.dat`** (some games XOR/obfuscate the header) →
  you may need a Frida dump of the metadata from a running app, or a header
  fix. Symptom: Il2CppDumper errors on "metadata magic".
- **Encrypted Cocos Lua** (`.luac` won't decompile) → find the XXTEA key in
  `libcocos*.so` strings and decrypt first. (Not expected here — Unity game.)
- **AssetBundle encryption** → rarer; UnityPy handles standard bundles.

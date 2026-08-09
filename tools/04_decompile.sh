#!/usr/bin/env bash
# Stage 4 - Decompile code and dump engine-specific data.
#   * jadx        : every base.apk DEX -> readable Java  (out/jadx)
#   * apktool     : decoded resources + AndroidManifest  (out/apktool)
#   * Il2CppDumper: IL2CPP symbol recovery -> dump.cs     (out/il2cpp)
#   * UnityPy     : MonoBehaviour/TextAsset data as JSON  (out/unity_assets)
# Each step is skipped gracefully if its tool or input is absent.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/_tools"
EXTRACTED="$ROOT/out/extracted"
say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!  %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

[[ -d "$EXTRACTED" ]] || { warn "out/extracted missing - run Stage 1 first"; exit 1; }

# Pick the primary code APK (base.apk holds the app's DEX; split apks hold
# language/density resources and rarely contain gameplay code).
BASE_APK="$(find "$EXTRACTED" -name 'base.apk' -not -path '*/.contents/*' 2>/dev/null | head -1)"
[[ -z "$BASE_APK" ]] && BASE_APK="$(find "$EXTRACTED" -name '*.apk' 2>/dev/null | head -1)"

# --- jadx : DEX -> Java ---------------------------------------------------
if have java && [[ -x "$TOOLS/jadx/bin/jadx" ]]; then
  if [[ -n "$BASE_APK" ]]; then
    say "jadx decompiling $(basename "$BASE_APK") -> out/jadx"
    "$TOOLS/jadx/bin/jadx" --no-res -d "$ROOT/out/jadx" "$BASE_APK" \
      >"$ROOT/out/jadx.log" 2>&1 || warn "jadx finished with warnings (see out/jadx.log)"
  else
    warn "no .apk found to decompile"
  fi
else
  warn "skipping jadx (need java + Stage 0 setup)"
fi

# --- apktool : resources + manifest --------------------------------------
if have java && [[ -f "$TOOLS/apktool.jar" && -n "$BASE_APK" ]]; then
  say "apktool decoding resources -> out/apktool"
  java -jar "$TOOLS/apktool.jar" d -f -o "$ROOT/out/apktool" "$BASE_APK" \
    >"$ROOT/out/apktool.log" 2>&1 || warn "apktool warnings (see out/apktool.log)"
else
  warn "skipping apktool (need java + Stage 0 setup)"
fi

# --- Il2CppDumper : recover IL2CPP symbols -------------------------------
META="$(find "$EXTRACTED" -name 'global-metadata.dat' 2>/dev/null | head -1)"
LIBIL2CPP="$(find "$EXTRACTED" -name 'libil2cpp.so' 2>/dev/null | sort | head -1)"
if [[ -n "$META" && -n "$LIBIL2CPP" ]]; then
  if have dotnet && [[ -f "$TOOLS/il2cppdumper/Il2CppDumper.dll" ]]; then
    say "Il2CppDumper on libil2cpp.so + global-metadata.dat -> out/il2cpp"
    mkdir -p "$ROOT/out/il2cpp"
    dotnet "$TOOLS/il2cppdumper/Il2CppDumper.dll" "$LIBIL2CPP" "$META" "$ROOT/out/il2cpp" \
      >"$ROOT/out/il2cpp.log" 2>&1 \
      && say "  -> out/il2cpp/dump.cs (all classes/methods/fields)" \
      || warn "Il2CppDumper failed (see out/il2cpp.log). If arch mismatch, pass the arm64 libil2cpp.so."
  elif [[ -f "$TOOLS/il2cppdumper/Il2CppDumper.exe" ]] && have wine; then
    say "Il2CppDumper via wine -> out/il2cpp"
    mkdir -p "$ROOT/out/il2cpp"
    wine "$TOOLS/il2cppdumper/Il2CppDumper.exe" "$LIBIL2CPP" "$META" "$ROOT/out/il2cpp" \
      >"$ROOT/out/il2cpp.log" 2>&1 || warn "Il2CppDumper failed (see out/il2cpp.log)"
  else
    warn "IL2CPP game detected but no runtime for Il2CppDumper."
    warn "  Install .NET 6+ ('dotnet') then re-run this stage, OR run"
    warn "  _tools/il2cppdumper on Windows against:"
    warn "    lib: $LIBIL2CPP"
    warn "    meta: $META"
  fi
else
  say "no IL2CPP metadata (not an IL2CPP build, or already Mono/other)"
fi

# --- UnityPy : dump Unity data assets ------------------------------------
if python3 -c "import UnityPy" 2>/dev/null; then
  say "UnityPy dumping MonoBehaviour/TextAsset data -> out/unity_assets"
  python3 "$ROOT/tools/unity_extract.py" || warn "UnityPy extraction had issues"
else
  say "UnityPy not installed - skipping Unity asset dump (run Stage 0)"
fi

say "Stage 4 done."

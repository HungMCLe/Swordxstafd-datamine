#!/usr/bin/env bash
# Stage 0 - Fetch reverse-engineering tools into ./_tools and install
# Python helpers. Tools are pulled from GitHub release assets (universally
# reachable). Safe to re-run: existing downloads are skipped.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/_tools"
mkdir -p "$TOOLS"
cd "$TOOLS"

# Pinned, verified-reachable versions (bump as needed).
APKTOOL_VER="2.9.3"
JADX_VER="1.5.0"
IL2CPP_VER="6.7.46"

say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

fetch() { # url dest
  local url="$1" dest="$2"
  if [[ -s "$dest" ]]; then
    say "already have $(basename "$dest")"
    return 0
  fi
  say "downloading $(basename "$dest")"
  curl -fL --retry 4 --retry-delay 2 --max-time 900 -o "$dest.part" "$url"
  mv "$dest.part" "$dest"
}

# --- apktool (jar) : decodes resources + AndroidManifest ------------------
fetch "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VER}/apktool_${APKTOOL_VER}.jar" \
      "$TOOLS/apktool.jar"

# --- jadx : DEX -> Java decompiler ---------------------------------------
if [[ ! -x "$TOOLS/jadx/bin/jadx" ]]; then
  fetch "https://github.com/skylot/jadx/releases/download/v${JADX_VER}/jadx-${JADX_VER}.zip" \
        "$TOOLS/jadx.zip"
  say "unpacking jadx"
  rm -rf "$TOOLS/jadx" && mkdir -p "$TOOLS/jadx"
  ( cd "$TOOLS/jadx" && unzip -q "$TOOLS/jadx.zip" )
  chmod +x "$TOOLS/jadx/bin/jadx" || true
fi

# --- Il2CppDumper : recovers class/method/field names from IL2CPP --------
# Requires the .NET runtime to actually run (dotnet). We download it either
# way so it is ready if you have .NET; the decompile stage checks for dotnet.
if [[ ! -f "$TOOLS/il2cppdumper/Il2CppDumper.dll" && ! -f "$TOOLS/il2cppdumper/Il2CppDumper.exe" ]]; then
  fetch "https://github.com/Perfare/Il2CppDumper/releases/download/v${IL2CPP_VER}/Il2CppDumper-net6-v${IL2CPP_VER}.zip" \
        "$TOOLS/il2cppdumper.zip"
  say "unpacking Il2CppDumper"
  rm -rf "$TOOLS/il2cppdumper" && mkdir -p "$TOOLS/il2cppdumper"
  ( cd "$TOOLS/il2cppdumper" && unzip -q "$TOOLS/il2cppdumper.zip" )
fi

# --- Python libs : Unity asset extraction (UnityPy) ----------------------
say "installing Python helpers (UnityPy)"
if have pip3; then
  pip3 install --quiet --disable-pip-version-check UnityPy 2>/dev/null \
    || say "UnityPy install failed (Unity asset extraction will be skipped)"
fi

# --- Report what is usable ------------------------------------------------
echo
say "tool status:"
have java    && echo "  [x] java   $(java -version 2>&1 | head -1)" || echo "  [ ] java   MISSING (needed for apktool/jadx)"
have dotnet  && echo "  [x] dotnet $(dotnet --version 2>/dev/null)" || echo "  [ ] dotnet MISSING (needed for Il2CppDumper - install .NET 6+)"
python3 -c "import UnityPy" 2>/dev/null && echo "  [x] UnityPy installed" || echo "  [ ] UnityPy missing"
echo "  tools dir: $TOOLS"

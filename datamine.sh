#!/usr/bin/env bash
# Sword x Staff datamining pipeline - one command, all stages.
#
#   ./datamine.sh path/to/SwordxStaff.xapk
#
# Runs: setup tools -> extract -> detect engine -> dump configs ->
# decompile/dump assets -> find formulas. Outputs land in ./out/, with the
# headline result at ./out/REPORT_formulas.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  cat <<EOF
Usage: ./datamine.sh <path-to-apk-or-xapk> [--skip-setup]

  <path>        The game package: .apk / .xapk / .apks / .aab / .zip
  --skip-setup  Reuse already-downloaded tools in ./_tools

Get the package on a machine that can reach the store (this repo's docs/
explain how), point this script at it, and read ./out/REPORT_formulas.md.
EOF
  exit 2
fi

PKG="$1"; shift || true
SKIP_SETUP=0
for a in "$@"; do [[ "$a" == "--skip-setup" ]] && SKIP_SETUP=1; done

[[ -f "$PKG" ]] || { echo "Package not found: $PKG" >&2; exit 1; }

hr() { printf '\n\033[1;35m######## %s ########\033[0m\n' "$*"; }

if [[ "$SKIP_SETUP" -eq 0 ]]; then
  hr "Stage 0: setup tools"
  bash tools/00_setup.sh
fi

hr "Stage 1: extract"
python3 tools/01_extract.py "$PKG"

hr "Stage 2: detect engine"
python3 tools/02_detect_engine.py

hr "Stage 3: dump config/data"
python3 tools/03_dump_configs.py

hr "Stage 4: decompile + dump assets"
bash tools/04_decompile.sh

hr "Stage 5: find formulas"
python3 tools/05_find_formulas.py

hr "DONE"
echo "Headline result : out/REPORT_formulas.md"
echo "Engine report   : out/ENGINE.md"
echo "Decompiled code : out/jadx/  out/il2cpp/dump.cs"
echo "Balance data    : out/configs/  out/unity_assets/"

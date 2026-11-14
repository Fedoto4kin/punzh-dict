#!/usr/bin/env bash
# Publish release APK for direct download from the site.
#
# Local:
#   scripts/publish_apk.sh
#   scripts/publish_apk.sh /path/to/punzh-dict-1.0.0-19-release.apk
#   scripts/publish_apk.sh /path/to/app.apk ./downloads
#
# Prod (karielan-hub):
#   scripts/publish_apk.sh ~/punzh-dict-mobile/.../punzh-dict-1.0.0-19-release.apk \
#       ~/punzh-dict/downloads
#
# Nginx serves ~/punzh-dict/downloads/ at /downloads/ (host config).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIBLING_APK_DIR="$ROOT/../punzh-dict-mobile/build/app/outputs/flutter-apk"

pick_latest_apk() {
  local newest=""
  local f
  shopt -s nullglob
  for f in "$SIBLING_APK_DIR"/punzh-dict-*-release.apk; do
    if [[ -z "$newest" || "$f" -nt "$newest" ]]; then
      newest="$f"
    fi
  done
  shopt -u nullglob
  if [[ -z "$newest" ]]; then
    echo "No punzh-dict-*-release.apk under $SIBLING_APK_DIR" >&2
    exit 1
  fi
  echo "$newest"
}

SRC="${1:-}"
OUT="${2:-$ROOT/app/downloads}"

if [[ -z "$SRC" ]]; then
  SRC="$(pick_latest_apk)"
fi
if [[ ! -f "$SRC" ]]; then
  echo "APK not found: $SRC" >&2
  exit 1
fi

need() { command -v "$1" >/dev/null || { echo "Missing: $1" >&2; exit 1; }; }
need sha256sum
need python3

mkdir -p "$OUT"
ABS_OUT="$(cd "$OUT" && pwd)"
BASE="$(basename "$SRC")"
# punzh-dict-1.0.0-19-release.apk → version / code
VERSION=""
VERSION_CODE=""
if [[ "$BASE" =~ ^punzh-dict-([0-9]+\.[0-9]+\.[0-9]+)-([0-9]+)- ]]; then
  VERSION="${BASH_REMATCH[1]}"
  VERSION_CODE="${BASH_REMATCH[2]}"
fi

STABLE="$ABS_OUT/punzh-dict.apk"
TMP="$ABS_OUT/.punzh-dict.apk.tmp"
cp -f "$SRC" "$TMP"
mv -f "$TMP" "$STABLE"
# Keep versioned copy for history (same dir; not linked from the site).
if [[ -n "$VERSION" && -n "$VERSION_CODE" ]]; then
  cp -f "$STABLE" "$ABS_OUT/punzh-dict-${VERSION}-${VERSION_CODE}.apk"
fi

SHA="$(sha256sum "$STABLE" | awk '{print $1}')"
SIZE="$(wc -c <"$STABLE" | tr -d ' ')"
BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$ABS_OUT/manifest.json" <<PY
import json, sys
path = sys.argv[1]
data = {
    "version": "${VERSION}" or None,
    "version_code": int("${VERSION_CODE}") if "${VERSION_CODE}" else None,
    "filename": "punzh-dict.apk",
    "sha256": "${SHA}",
    "size": int("${SIZE}"),
    "built_at": "${BUILT_AT}",
    "source": "${BASE}",
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY

echo "Published → $ABS_OUT"
ls -lh "$STABLE" "$ABS_OUT/manifest.json"
echo
cat "$ABS_OUT/manifest.json"
echo
echo "URL: https://punzhina.krc.karelia.ru/downloads/punzh-dict.apk"

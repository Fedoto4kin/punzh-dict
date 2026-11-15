#!/usr/bin/env bash
# Export dict.sqlite + manifest.json for the offline app update URL.
#
# Local:
#   scripts/publish_mobile_pack.sh /tmp/mobile-pack
#   python -m http.server -d /tmp/mobile-pack 8765
#
# Prod (karielan-hub), weekly cron example:
#   0 4 * * 1 /home/krl/punzh-dict/scripts/publish_mobile_pack.sh \
#       /home/krl/punzh-dict/mobile-pack >>/home/krl/punzh-dict/mobile-pack/cron.log 2>&1
#
# Skips overwrite when live data_version matches the new export (no content change).
# Force: scripts/publish_mobile_pack.sh /path --force
#
# Nginx serves ~/punzh-dict/mobile-pack/ at /mobile-pack/ (host config; not this script).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT="${1:-}"
FORCE=0
if [[ "${2:-}" == "--force" ]] || [[ "${FORCE_PUBLISH:-}" == "1" ]]; then
  FORCE=1
fi

if [[ -z "$OUT" ]]; then
  echo "Usage: $0 <output-dir> [--force]" >&2
  echo "Example: $0 /tmp/mobile-pack" >&2
  echo "Prod:    $0 ~/punzh-dict/mobile-pack" >&2
  exit 1
fi

CONTAINER="${PUNZH_DJANGO_CONTAINER:-}"

detect_container() {
  if [[ -n "$CONTAINER" ]]; then
    echo "$CONTAINER"
    return
  fi
  local names
  names="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
  if echo "$names" | grep -qx 'punzh_web'; then
    echo punzh_web
  elif echo "$names" | grep -qx 'punzh_django'; then
    echo punzh_django
  else
    echo "No punzh_web/punzh_django. Set PUNZH_DJANGO_CONTAINER." >&2
    exit 1
  fi
}

read_data_version() {
  local path="$1"
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data_version"])' "$path"
}

need() { command -v "$1" >/dev/null || { echo "Missing: $1" >&2; exit 1; }; }
need docker
need python3

CONTAINER="$(detect_container)"
mkdir -p "$OUT"
ABS_OUT="$(cd "$OUT" && pwd)"
REMOTE_TMP="/tmp/punzh-mobile-pack-$$"
STAGE="$(mktemp -d /tmp/punzh-mobile-pack-stage.XXXXXX)"
cleanup() {
  rm -rf "$STAGE"
  docker exec "$CONTAINER" rm -rf "$REMOTE_TMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Exporting via $CONTAINER → $REMOTE_TMP …"
docker exec -w /app "$CONTAINER" \
  python manage.py export_mobile_db --out "$REMOTE_TMP"

docker cp "$CONTAINER:$REMOTE_TMP/manifest.json" "$STAGE/manifest.json"
docker cp "$CONTAINER:$REMOTE_TMP/dict.sqlite" "$STAGE/dict.sqlite"

NEW_VER="$(read_data_version "$STAGE/manifest.json")"
LIVE_MANIFEST="$ABS_OUT/manifest.json"
if [[ "$FORCE" -eq 0 && -f "$LIVE_MANIFEST" ]]; then
  LIVE_VER="$(read_data_version "$LIVE_MANIFEST" || true)"
  if [[ -n "${LIVE_VER:-}" && "$LIVE_VER" == "$NEW_VER" ]]; then
    echo "Unchanged data_version=$NEW_VER — skip publish (use --force to overwrite)."
    cat "$STAGE/manifest.json"
    exit 0
  fi
fi

cp -f "$STAGE/dict.sqlite" "$ABS_OUT/dict.sqlite"
cp -f "$STAGE/manifest.json" "$ABS_OUT/manifest.json"

echo "Published → $ABS_OUT (data_version=$NEW_VER)"
ls -lh "$ABS_OUT/manifest.json" "$ABS_OUT/dict.sqlite"
echo
cat "$ABS_OUT/manifest.json"
echo
echo "URL: https://punzhina.krc.karelia.ru/mobile-pack/manifest.json"

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
# Nginx serves ~/punzh-dict/mobile-pack/ at /mobile-pack/ (host config; not this script).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT="${1:-}"
if [[ -z "$OUT" ]]; then
  echo "Usage: $0 <output-dir>" >&2
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

need() { command -v "$1" >/dev/null || { echo "Missing: $1" >&2; exit 1; }; }
need docker

CONTAINER="$(detect_container)"
mkdir -p "$OUT"
ABS_OUT="$(cd "$OUT" && pwd)"
REMOTE_TMP="/tmp/punzh-mobile-pack-$$"

echo "Exporting via $CONTAINER → $REMOTE_TMP …"
docker exec -w /app "$CONTAINER" \
  python manage.py export_mobile_db --out "$REMOTE_TMP"

docker cp "$CONTAINER:$REMOTE_TMP/dict.sqlite" "$ABS_OUT/dict.sqlite"
docker cp "$CONTAINER:$REMOTE_TMP/manifest.json" "$ABS_OUT/manifest.json"
docker exec "$CONTAINER" rm -rf "$REMOTE_TMP"

echo "Published → $ABS_OUT"
ls -lh "$ABS_OUT/manifest.json" "$ABS_OUT/dict.sqlite"
echo
cat "$ABS_OUT/manifest.json"
echo
echo "URL: https://punzhina.krc.karelia.ru/mobile-pack/manifest.json"

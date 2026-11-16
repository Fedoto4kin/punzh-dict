#!/usr/bin/env bash
# Count historical APK downloads from host nginx access logs.
# On karielan-hub (krl in docker group), reads /var/log/nginx via a throwaway
# container (logs are www-data:adm, not world-readable).
#
#   scripts/count_apk_nginx_hits.sh
#
# Then seed Django on prod:
#   docker exec -w /app punzh_web python manage.py set_apk_download_count N
set -euo pipefail

docker run --rm -v /var/log/nginx:/logs:ro alpine:3.20 sh -c '
  apk add --no-cache gzip >/dev/null
  total=0
  for f in /logs/access.log /logs/access.log.*; do
    [ -e "$f" ] || continue
    case "$f" in
      *.gz) n=$(gzip -dc "$f" | grep -E "GET /mobile-pack/punzh-dict-latest\\.apk" | grep -cE "\" (200|206) " || true) ;;
      *)    n=$(grep -E "GET /mobile-pack/punzh-dict-latest\\.apk" "$f" | grep -cE "\" (200|206) " || true) ;;
    esac
    n=${n:-0}
    [ "$n" -gt 0 ] && echo "$f: $n"
    total=$((total + n))
  done
  echo "TOTAL: $total"
'

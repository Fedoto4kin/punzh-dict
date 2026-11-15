#!/usr/bin/env bash
# Prod/dev deploy: migrate + collectstatic into STATIC_ROOT (app/staticfiles).
# Do not use --clear: that briefly wipes all /static/ files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PULL=1
RELOAD_NGINX=0
CONTAINER="${PUNZH_DJANGO_CONTAINER:-}"

usage() {
  cat <<'EOF'
Usage: ./deploy.sh [--no-pull] [--no-restart] [--reload-nginx] [--container NAME]

  --no-pull         skip git pull
  --no-restart      skip docker restart (uwsgi/runserver keep old code)
  --reload-nginx    nginx -t && systemctl reload nginx (needs sudo)
  --container NAME  docker exec target (default: punzh_web or punzh_django)

Env: PUNZH_DJANGO_CONTAINER
EOF
}

RESTART=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) PULL=0 ;;
    --no-restart) RESTART=0 ;;
    --reload-nginx) RELOAD_NGINX=1 ;;
    --container)
      CONTAINER="${2:?}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

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
    echo "No punzh_web/punzh_django container. Set --container or PUNZH_DJANGO_CONTAINER." >&2
    exit 1
  fi
}

# Public GitHub LFS works anonymously, but a failed auth attempt can stick
# lfs.<url>.access=basic in .git/config and then every pull asks for credentials.
clear_sticky_lfs_basic_auth() {
  local key
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    git config --unset-all "$key" || true
  done < <(git config --get-regexp '^lfs\..*\.access$' 2>/dev/null | awk '$2 == "basic" { print $1 }')
}

if [[ "$PULL" -eq 1 ]]; then
  clear_sticky_lfs_basic_auth
  # Fail fast if credentials are somehow still required (no TTY on deploy).
  GIT_TERMINAL_PROMPT=0 git pull --ff-only
fi

CONTAINER="$(detect_container)"
echo "Using container: $CONTAINER"

docker exec --user 1000:1000 -w /app "$CONTAINER" python manage.py migrate --noinput
docker exec --user 1000:1000 -w /app "$CONTAINER" python manage.py collectstatic --noinput

if [[ "$RESTART" -eq 1 ]]; then
  echo "Restarting $CONTAINER (uwsgi/runserver pick up code)…"
  docker restart "$CONTAINER"
fi

if [[ "$RELOAD_NGINX" -eq 1 ]]; then
  sudo nginx -t
  sudo systemctl reload nginx
fi

echo "Done. Confirm /static/admin/js/article_html_editor.js is 200 after nginx points at app/staticfiles/."

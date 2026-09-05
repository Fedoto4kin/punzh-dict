#!/usr/bin/env bash
# Dry-run LLM cleanup for pilot v2. See data/cleanup_pilot_v2_manifest.json
# Dual LLM pass; json results: word / before / after (+ report).
# Add --debug to the python line for after_llm* / pos / diffs.
set -euo pipefail
cd "$(dirname "$0")"
CONTAINER="${PUNZH_AGENTS_CONTAINER:-punzh_django}"
OUT="${1:-cleanup_pilot_v2.json}"
MANIFEST="data/cleanup_pilot_v2_manifest.json"
IDS=$(python3 -c "import json; print(' '.join('--id '+str(i) for i in json.load(open('$MANIFEST'))['ids']))")
echo "Pilot v2 → $OUT ($(echo $IDS | wc -w) id flags), review on, slim json"
docker exec --user 1000:1000 -w /app/agents "$CONTAINER" \
  python -u clean_translations.py --out "$OUT" --force --review $IDS

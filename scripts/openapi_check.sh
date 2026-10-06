#!/usr/bin/env bash
# Staleness check for the generated API documents (docs/dev-guide.md §1.3; DG-MK-lint).
# Regenerates both files into .run/openapi-check/ exactly as make openapi does and compares bytes.
#   scripts/openapi_check.sh [<openapi.json to compare> [<schema.d.ts to compare>]]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCUMENT="${1:-$ROOT/docs/api/openapi.json}"
SCHEMA="${2:-$ROOT/frontend/src/lib/api/schema.d.ts}"
OUT="$ROOT/.run/openapi-check"
NODE_BIN="$ROOT/frontend/node_modules/.bin"

mkdir -p "$OUT"
"$ROOT/backend/.venv/bin/erev" openapi --out "$OUT/openapi.json" >/dev/null || {
  echo "openapi check: erev openapi failed"
  exit 1
}
"$NODE_BIN/openapi-typescript" "$OUT/openapi.json" -o "$OUT/schema.raw.d.ts" >/dev/null 2>&1 || {
  echo "openapi check: openapi-typescript failed"
  exit 1
}
# Prettier 3 skips files matched by .gitignore (.run/), so format through stdin as the committed path.
"$NODE_BIN/prettier" --config "$ROOT/frontend/.prettierrc" --stdin-filepath "$ROOT/frontend/src/lib/api/schema.d.ts" \
  <"$OUT/schema.raw.d.ts" >"$OUT/schema.d.ts" || {
  echo "openapi check: prettier failed"
  exit 1
}

status=0
for pair in "$OUT/openapi.json:$DOCUMENT" "$OUT/schema.d.ts:$SCHEMA"; do
  generated="${pair%%:*}"
  committed="${pair#*:}"
  if ! cmp -s "$generated" "$committed"; then
    echo "openapi check: ${committed#"$ROOT"/} is stale; run make openapi"
    status=1
  fi
done
exit "$status"

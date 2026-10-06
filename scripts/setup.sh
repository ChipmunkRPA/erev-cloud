#!/usr/bin/env bash
# make setup (docs/dev-guide.md §4.2 DG-MK-setup). Idempotent.
# This is the only loop command that downloads packages or updates lock files (DG-ENV-08; DG-MK-00f).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
export TMPDIR="$PWD/.run/tmp"

fail() {
  echo "FAIL setup: $1"
  exit 1
}

# (1) toolchain, before the project environment exists
uv run --no-project --python 3.12 scripts/check_env.py --tools || fail "toolchain check"

# (2) local directories
mkdir -p .run/tmp .run/reports .run/locks .data/files || fail "local directories"

# (3) lock files with LOCK=1 only, then the backend environment
if [[ "${LOCK:-}" == "1" ]]; then
  uv lock --project backend || fail "uv lock"
  npm --prefix frontend install --package-lock-only --ignore-scripts || fail "npm lock"
fi
# Every extra is installed locally (the `gcp` hosted providers, 05 SAR-21) so that licence-check
# reads their metadata from backend/.venv; tests still exercise the hosted adapters with fakes only.
if [[ -f backend/uv.lock ]]; then
  uv sync --project backend --frozen --all-extras || fail "uv sync"
else
  uv sync --project backend --all-extras || fail "uv sync"
fi

# (4) frontend packages from the lock file
[[ -f frontend/package-lock.json ]] || fail "frontend/package-lock.json missing; run make setup LOCK=1"
npm --prefix frontend ci || fail "npm ci"

# (5) Playwright browser
frontend/node_modules/.bin/playwright install chromium || fail "playwright install chromium"

# (6) to (8) keys, required names, database roles and privileges
backend/.venv/bin/python scripts/check_env.py --ensure-keys || fail "ensure keys"
backend/.venv/bin/python scripts/check_env.py --names || fail "required variables"
backend/.venv/bin/python scripts/check_env.py --db || fail "database checks"

# (9) migrate the dev database
make --no-print-directory migrate DB=dev || fail "migrate"

echo "OK setup"

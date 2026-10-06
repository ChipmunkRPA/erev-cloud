#!/usr/bin/env bash
# Build the harness venv and a byte-identical copy of the legacy repo. Never writes to ~/dev/erev-legacy.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY="${EREV_LEGACY:-$HOME/dev/erev-legacy}"
cd "$HERE"
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
rsync -a --delete --exclude .git "$LEGACY/" erev_copy/
mkdir -p fixtures
cp "$LEGACY/ops/libnew/libwarm/db/ASC606.db" fixtures/ASC606.shipped.db
shasum -a 256 "$LEGACY/eRev.py" erev_copy/eRev.py fixtures/ASC606.shipped.db

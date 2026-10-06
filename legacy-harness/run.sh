#!/usr/bin/env bash
# Replay the full UAT scenario headless, run the defect probes, and rebuild the analysis tables.
# Flags (--golden-dir, --out-dir, --allow-modified-copy) are passed to all three scripts.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
export QT_QPA_PLATFORM=offscreen QT_LOGGING_RULES="qt.qpa.*=false"
.venv/bin/python replay.py "$@"
.venv/bin/python probes.py "$@"
.venv/bin/python analyze.py "$@"

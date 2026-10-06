#!/usr/bin/env bash
# scripts/gate_context.sh <gate> -- <command…>   (GATE-BIND-1; docs/dev-guide.md §4.1 DG-MK-00i;
# 05 §7.8 REL-02)
#
# The entry the Makefile gate targets use: the command (an inner `make <gate>-gate`) runs in an
# immutable execution context through `scripts/gate_report.py <gate> --exec -- <command…>`, which
# clones the repository at the captured HEAD into .run/gates/ctx-<gate>-<sha12>-<pid>/, runs the
# command there with the context's packages ahead of the editable install, verifies the source did
# not change, copies the report the command wrote back to .run/reports/<gate>/ and stamps it with
# `source_binding`. A dirty worktree runs in place, labelled "worktree-dirty (development; not
# release evidence)". The interpreter is the worktree venv's python (EREV_GATE_PY overrides;
# python3 from PATH when neither exists).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${EREV_GATE_PY:-$ROOT/backend/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3 || true)"; fi
[[ -n "$PY" ]] || { echo "gate-context: no python interpreter (set EREV_GATE_PY)" >&2; exit 2; }
GATE="${1:-}"
[[ -n "$GATE" ]] || { echo "usage: scripts/gate_context.sh <gate> -- <command…>" >&2; exit 2; }
shift
[[ "${1:-}" == "--" ]] && shift
[[ $# -gt 0 ]] || { echo "usage: scripts/gate_context.sh <gate> -- <command…>" >&2; exit 2; }
exec "$PY" "$ROOT/scripts/gate_report.py" "$GATE" --exec -- "$@"

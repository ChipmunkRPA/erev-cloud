"""DG-MK-00g usable-evidence predicate of the gate wrapper (GATE-BIND-1), ported read-only from
lane P1's candidate 8 (``sprint/l2`` 5e29be6, ``scripts/gate_report.py`` REPORT_KEYS, ``_figure``,
``has_population``, ``usable_evidence``) so wrapped writers such as ``scripts/tf_validate.sh`` are
tested against the same rule. Keep in step with ``scripts/gate_report.py`` once P1 merges.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REPORT_KEYS = (
    "target",
    "command",
    "build_sha",
    "worktree_dirty",
    "started_at",
    "finished_at",
    "exit_code",
    "counts",
    "failures",
)


def _figure(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def has_population(counts: Mapping[str, Any]) -> bool:
    """DG-MK-00g evidence population: at least one figure in ``counts`` (top level or one level
    down), or a non-empty ``stages`` map whose stages all passed."""
    for key, value in counts.items():
        if key == "stages":
            if isinstance(value, dict) and value and all(v == "pass" for v in value.values()):
                return True
            continue
        if _figure(value):
            return True
        if isinstance(value, dict) and any(_figure(v) for v in value.values()):
            return True
    return False


def usable_evidence(report: Mapping[str, Any], target: str, captured_sha: str) -> str | None:
    """Why an inner DG-MK-00g report is not usable gate evidence (None when it is): the nine keys
    with their types, the target and the captured build (identity), a populated ``counts``."""
    missing = [key for key in REPORT_KEYS if key not in report]
    if missing:
        return "schema: missing " + ", ".join(missing)
    if not _figure(report["exit_code"]):
        return "schema: exit_code is not an integer"
    if not isinstance(report["counts"], dict):
        return "schema: counts is not an object"
    if not isinstance(report["failures"], list):
        return "schema: failures is not a list"
    if report["target"] != target:
        return f"identity: target {report['target']!r} is not {target!r}"
    build = report["build_sha"]
    if build != captured_sha:
        shown = build[:12] if isinstance(build, str) else repr(build)
        return f"identity: build_sha {shown} is not the captured {captured_sha[:12]}"
    if not has_population(report["counts"]):
        return "population: counts carries no figure"
    return None

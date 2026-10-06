"""Golden parity cases and integrity preconditions (docs/dev-guide.md §9.6 DG-PAR-01, DG-PAR-03;
docs/legacy/DEVIATIONS.md §2; BUILD_SPEC GPA-1).

``cases`` yields one :class:`GoldenCase` per id of ``docs/legacy/golden/golden-tests.json``, in file
order. Ids, kinds, ``steps_through``, ``window``, ``contract``, ``pob`` and legacy values come from
that file; expected values, ``tolerance``, ``classification``, ``dev_id`` and ``related_dev_ids``
come from ``deviations.json`` ``tests[<id>]`` (DG-PAR-01). A stale ``deviations.json`` still yields
every case, and each case then fails with :data:`STALE`.

``check`` evaluates the DG-PAR-03 preconditions. ``session_integrity`` checks them once per session
against ``deviations.json``, or against the copy named by ``EREV_PARITY_DEVIATIONS``. Only the
DG-PAR-03 regression test sets that variable, to a copy under ``.run/tmp/``. Both documents are
read-only inputs, and nothing here writes a file.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final

__all__ = [
    "CASE_COUNT",
    "DEVIATIONS",
    "DEVIATIONS_ENV",
    "GOLDEN_TESTS",
    "POSTING_RULE_ID",
    "PROBE_STATUS_KEYS",
    "STALE",
    "GoldenCase",
    "Integrity",
    "cases",
    "check",
    "deviations_file",
    "session_integrity",
]

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
GOLDEN_DIR: Final = REPO_ROOT / "docs" / "legacy" / "golden"
GOLDEN_TESTS: Final = GOLDEN_DIR / "golden-tests.json"
DEVIATIONS: Final = GOLDEN_DIR / "deviations.json"
DEVIATIONS_ENV: Final = "EREV_PARITY_DEVIATIONS"
STALE: Final = (
    "deviations.json is stale; the supervisor must rerun "
    "research-harness/deviations/build_deviations.py"
)
CASE_COUNT: Final = 122
POSTING_RULE_ID: Final = "EXACT-CUM"  # DG-KRN-MONEY-03 erev_engine.money.cumulative_posted
PROBE_STATUS_KEYS: Final = frozenset(
    {"authority", "COMMITTED", "COMMITTED_WITH_FINDINGS", "REJECTED", "error_code"}
)
# golden-tests.json members that identify a case rather than carry legacy values.
_IDENTITY: Final = frozenset(
    {"id", "kind", "steps_through", "window", "contract", "pob", "sku", "inputs", "source"}
)


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One golden test joined with its ``deviations.json`` entry (DG-PAR-01)."""

    id: str
    kind: str
    steps_through: str | None
    contract: str | None
    pob: str | None
    window: tuple[str, str] | None
    legacy: Mapping[str, Any]
    expected: Mapping[str, Any]
    tolerance: str | None
    classification: str | None
    dev_id: str | None
    related_dev_ids: tuple[str, ...]

    @property
    def case_id(self) -> str:
        """The pytest id ``<kind>::<test id>``, so ``make parity K=<kind>`` selects a kind."""
        return f"{self.kind}::{self.id}"


@dataclass(frozen=True, slots=True)
class Integrity:
    """The DG-PAR-03 outcome: the SHA-256 of ``golden-tests.json`` and each failed precondition."""

    golden_tests_sha256: str
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def deviations_file() -> Path:
    """``deviations.json``, or the copy that ``EREV_PARITY_DEVIATIONS`` names."""
    override = os.environ.get(DEVIATIONS_ENV)
    return Path(override) if override else DEVIATIONS


def _document(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} does not hold a JSON object")
    return loaded


def check(golden_path: Path = GOLDEN_TESTS, deviations_path: Path = DEVIATIONS) -> Integrity:
    """The DG-PAR-03 preconditions over the two documents."""
    raw = golden_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    golden = json.loads(raw)
    deviations = _document(deviations_path)
    found: list[str] = []
    inputs = deviations.get("inputs")
    recorded = inputs.get("golden_tests_sha256") if isinstance(inputs, dict) else None
    if recorded != digest:
        found.append(
            f"inputs.golden_tests_sha256 {recorded!r} differs from sha256(golden-tests.json) "
            f"{digest}"
        )
    golden_ids = [str(item["id"]) for item in golden["tests"]]
    tests = deviations.get("tests")
    deviation_ids = list(tests) if isinstance(tests, dict) else []
    if len(golden_ids) != CASE_COUNT or len(set(golden_ids)) != CASE_COUNT:
        found.append(f"golden-tests.json holds {len(set(golden_ids))} ids, not {CASE_COUNT}")
    if set(golden_ids) != set(deviation_ids):
        found.append("golden-tests.json and deviations.json hold different test ids")
    if deviations.get("self_check_failures") != []:
        found.append("deviations.json self_check_failures is not empty")
    if deviations.get("posting_rule_id") != POSTING_RULE_ID:
        found.append(f"posting_rule_id is not {POSTING_RULE_ID}")
    mapping = deviations.get("probe_status_mapping")
    if not isinstance(mapping, dict) or frozenset(mapping) != PROBE_STATUS_KEYS:
        found.append("probe_status_mapping keys differ from the DG-PAR-10 key set")
    return Integrity(golden_tests_sha256=digest, problems=tuple(found))


@cache
def session_integrity() -> Integrity:
    """DG-PAR-03, checked once per session against :func:`deviations_file`."""
    return check(GOLDEN_TESTS, deviations_file())


def _window(value: object) -> tuple[str, str] | None:
    if isinstance(value, Sequence) and not isinstance(value, str) and len(value) == 2:
        return str(value[0]), str(value[1])
    return None


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def cases(
    golden_path: Path = GOLDEN_TESTS, deviations_path: Path | None = None
) -> tuple[GoldenCase, ...]:
    """DG-PAR-01: every golden test in ``golden-tests.json`` order."""
    golden = _document(golden_path)
    deviations = _document(deviations_file() if deviations_path is None else deviations_path)
    entries = deviations.get("tests")
    by_id: Mapping[str, Any] = entries if isinstance(entries, dict) else {}
    found: list[GoldenCase] = []
    for item in golden["tests"]:
        entry = by_id.get(str(item["id"]))
        entry = entry if isinstance(entry, dict) else {}
        legacy = item.get("expected")
        found.append(
            GoldenCase(
                id=str(item["id"]),
                kind=str(item["kind"]),
                steps_through=_text(item.get("steps_through")),
                contract=_text(item.get("contract")),
                pob=_text(item.get("pob")),
                window=_window(item.get("window")),
                legacy=legacy
                if isinstance(legacy, dict)
                else {key: value for key, value in item.items() if key not in _IDENTITY},
                expected=entry.get("expected") or {},
                tolerance=_text(entry.get("tolerance")),
                classification=_text(entry.get("classification")),
                dev_id=_text(entry.get("dev_id")),
                related_dev_ids=tuple(str(dev) for dev in entry.get("related_dev_ids") or ()),
            )
        )
    return tuple(found)

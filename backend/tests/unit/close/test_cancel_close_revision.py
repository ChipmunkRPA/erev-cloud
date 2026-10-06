"""CLO-CANCEL-CLOSE-REOPENED-1 — revision 0107 admits the pair ``closing → reopened`` (04 rev 1.170
T-REF-07; PRD rev 1.99 SM-07; DG-MIG-04 / DG-MIG-12 literals). CPU-only: the literals are compared
with the installing revision 0029; the database proof is
``tests/pg/test_db_invariants.py::test_db_07_end_of_a_soft_close_returns_to_reopened`` and
``tests/domain/close/test_reopen.py::test_cancel_close_returns_a_reopened_period_to_reopened``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final

from erev_api.domain.reference import periods
from erev_api.enums import PeriodState

VERSIONS: Final = Path(__file__).resolve().parents[4] / "backend/erev_api/db/migrations/versions"
PAIR: Final = "'closing>reopened'"


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pairs(body: str) -> set[str]:
    listed = body.split("ARRAY[", 1)[1].split("])", 1)[0]
    return {item.strip().strip("'") for item in listed.replace("\n", " ").split(",")}


def test_0107_restores_the_0029_literals() -> None:
    revision, installed = (
        _load("0107_cancel_close_returns_reopened"),
        _load("0029_entities_books_period_states"),
    )
    # the number is the register's; the parent is not pinned here — the chain follows merge
    # order and a revision's parent moves at every merge (supervisor rulings R-68 (e), R-117 (h))
    assert revision.revision == "0107"
    # the downgrade restores both bodies verbatim (DG-MIG-04)
    assert revision.PREVIOUS_UPDATE_BODY == installed.PERIOD_STATE_UPDATE_BODY
    assert revision.PREVIOUS_PAIR_BODY == installed.TRANSITION_PAIR_BODY
    for body in (revision.UPDATE_BODY, revision.PAIR_BODY):
        assert "$fn$" not in body


def test_0107_adds_exactly_the_one_pair_to_both_guards() -> None:
    revision = _load("0107_cancel_close_returns_reopened")
    for new, old in (
        (revision.UPDATE_BODY, revision.PREVIOUS_UPDATE_BODY),
        (revision.PAIR_BODY, revision.PREVIOUS_PAIR_BODY),
    ):
        assert _pairs(new) - _pairs(old) == {"closing>reopened"}
        assert _pairs(old) - _pairs(new) == set()
        # nothing but the pair list differs
        assert new.split("ARRAY[", 1)[0] == old.split("ARRAY[", 1)[0]
        assert new.split("])", 1)[1] == old.split("])", 1)[1]
    # the pairs of the transition guard are the allowed transitions of the domain, creation
    # included ("" → future)
    expected = {f"{'' if a is None else a.value}>{b.value}" for a, b in periods.ALLOWED_TRANSITIONS}
    assert _pairs(revision.PAIR_BODY) == expected
    assert (PeriodState.CLOSING, PeriodState.REOPENED) in periods.ALLOWED_TRANSITIONS


def test_0107_checks_ask_a_cancel_reason_and_no_reference_of_the_pair() -> None:
    revision = _load("0107_cancel_close_returns_reopened")
    cancel = "'CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER'"
    reopen = "'ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', 'OTHER'"
    # the two terms of 0029, unchanged, around the term of the new pair — which refuses a NULL
    # reason as well (a bare ``IN`` is NULL for a NULL reason, and a CHECK passes NULL)
    assert revision.REASON_SQL == (
        f"(NOT (from_state = 'closing' AND to_state = 'open') OR reason_code IN ({cancel})) "
        "AND (NOT (from_state = 'closing' AND to_state = 'reopened') "
        f"OR coalesce(reason_code IN ({cancel}), false)) "
        f"AND (NOT (from_state = 'closed' AND to_state = 'reopened') OR reason_code IN ({reopen}))"
    )
    assert revision.PREVIOUS_REASON_SQL == (
        f"(NOT (from_state = 'closing' AND to_state = 'open') OR reason_code IN ({cancel})) "
        f"AND (NOT (from_state = 'closed' AND to_state = 'reopened') OR reason_code IN ({reopen}))"
    )
    returned = "(from_state IS NOT DISTINCT FROM 'closing' AND to_state = 'reopened')"
    for sql, column in (
        (revision.APPROVAL_SQL, "approval_request_id"),
        (revision.LOCK_SQL, "period_lock_id"),
    ):
        assert sql.startswith(f"({returned} AND {column} IS NULL) OR (NOT {returned} AND ")
        approved = "'closed', 'reopened', 'permanently_locked'"
        assert sql.endswith(f"(to_state NOT IN ({approved}) OR {column} IS NOT NULL))")

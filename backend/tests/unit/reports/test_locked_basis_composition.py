"""F-RPS-CUTOFF-R1 × F-CLO CLO-8 composition (record §43 addendum; Codex 1913): the stored read
basis ``known_at_basis`` is ADMITTED on an as-locked run. CLO-8 normalises a locked run's
selectors and refuses every parameter outside ``locked.ADMITTED_KEYS`` — at creation
(``reconcile_selectors``), in the list predicate (``framework._consistent_with_lock``) and on every
addressed read (``run_mismatch`` through ``assert_run_matches``: detail, rows, output, rerun). The
basis is a stored run parameter, not a selector: it never widens or changes the frozen dataset's
scope, so a locked run created with it keeps its basis, stays visible, readable and rerunnable,
and every other non-selector key still refuses by name. ``_resolve`` stores the basis AFTER the
lock normalisation, so ``parameters = normalized`` cannot drop it. The database reads
(``lock_scope``, the entity scope) stand in; the SQL twin is compiled, not executed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.domain.reports import framework, locked
from erev_api.domain.reports.catalogue import (
    DEFINITIONS_BY_CODE,
    HISTORICAL_BASIS,
    KNOWN_AT_BASIS_KEY,
    RECORD_BASIS,
)
from erev_api.enums import SnapshotKind
from sqlalchemy.dialects import postgresql

LOCK: Final = UUID("00000000-0000-4000-8000-000000000c10")
ENTITY_A: Final = UUID("00000000-0000-4000-8000-00000000000a")
PERIOD: Final = UUID("00000000-0000-4000-8000-000000000909")
CODE: Final = "contract_balances"
KIND: Final = SnapshotKind.CONTRACT_BALANCES.value
SCOPE: Final = locked.LockScope(
    lock_id=LOCK,
    entity_id=ENTITY_A,
    entity_code="AVM-US",
    book_code="ASC606",
    period_id=PERIOD,
    period_key="FY2026-P09",
)
SCHEMA: Final = DEFINITIONS_BY_CODE[CODE].parameters_schema
NOW: Final = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
STAMP: Final = "2026-09-20T11:00:00Z"
LOCKED_HISTORICAL: Final = {
    "period_lock_id": str(LOCK),
    "known_at": STAMP,
    KNOWN_AT_BASIS_KEY: HISTORICAL_BASIS,
}
DERIVED: Final = {"entity_codes": ["AVM-US"], "book": "ASC606", "period_key": "FY2026-P09"}


def _resolve(monkeypatch: pytest.MonkeyPatch, given: dict[str, Any]) -> Any:
    """``framework._resolve`` with the two database reads standing in: the caller's entity scope
    and the lock's scope (T-CLS-04)."""
    monkeypatch.setattr(
        framework, "_in_scope_entities", lambda session, principal, permission: {"AVM-US": ENTITY_A}
    )
    monkeypatch.setattr(
        framework.locked, "lock_scope", lambda session, lock_id: SCOPE if lock_id == LOCK else None
    )
    uow = SimpleNamespace(session=None, principal=None, now=NOW)
    return framework._resolve(uow, SCHEMA, given, code=CODE)


def _findings(errors: list[Any]) -> dict[str, str]:
    return {str(error.field): str(error.message) for error in errors}


def _persisted(resolved: Any) -> dict[str, Any]:
    """The ``report_run`` row ``_insert_run`` persists, as ``run_row`` / ``run_report`` /
    ``rerun`` / ``explain_cell`` read it back."""
    return {
        "report_code": CODE,
        "report_version": 1,
        "parameters": dict(resolved.parameters),
        "entity_ids": [str(value) for value in resolved.entity_ids],
        "known_at": resolved.known_at,
        "book_code": resolved.book_code,
        "as_of_date": resolved.as_of_date,
        "period_lock_id": resolved.period_lock_id,
        "output_format": "json",
    }


def test_the_basis_is_admitted_and_the_admitted_set_is_otherwise_unchanged() -> None:
    assert KNOWN_AT_BASIS_KEY in locked.ADMITTED_KEYS
    assert locked.ADMITTED_KEYS == frozenset(
        {"period_lock_id", "known_at", KNOWN_AT_BASIS_KEY, *locked.SELECTOR_KEYS}
    )
    assert KNOWN_AT_BASIS_KEY not in locked.SELECTOR_KEYS  # a stored basis, never a selector


def test_a_locked_run_created_with_the_basis_keeps_it_after_the_lock_normalisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved, errors = _resolve(monkeypatch, LOCKED_HISTORICAL)
    assert errors == []
    assert resolved.parameters == {**LOCKED_HISTORICAL, **DERIVED}
    assert (resolved.historical, resolved.period_lock_id) == (True, LOCK)
    assert resolved.entity_ids == (ENTITY_A,)
    assert framework.utc_text(resolved.known_at) == STAMP


def test_the_basis_is_derived_and_stored_on_a_locked_run_whether_or_not_it_was_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supplied_cutoff, errors = _resolve(
        monkeypatch, {"period_lock_id": str(LOCK), "known_at": STAMP}
    )
    assert errors == [] and supplied_cutoff.parameters[KNOWN_AT_BASIS_KEY] == HISTORICAL_BASIS
    assert supplied_cutoff.historical is True
    defaulted, errors = _resolve(monkeypatch, {"period_lock_id": str(LOCK)})
    assert errors == [] and defaulted.parameters[KNOWN_AT_BASIS_KEY] == RECORD_BASIS
    assert defaulted.historical is False
    assert defaulted.parameters["known_at"] == framework.utc_text(NOW)


def test_the_persisted_locked_run_stays_visible_readable_and_rerunnable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved, errors = _resolve(monkeypatch, LOCKED_HISTORICAL)
    assert errors == []
    run = _persisted(resolved)
    # Every addressed read (detail, rows, output, rerun) reconciles the run with its lock.
    assert locked.run_mismatch(run, SCOPE) is None
    # The rerun / explain path derives the basis from the stored row.
    assert framework.report_params(run).historical is True
    # The list predicate — the SQL twin — admits the same keys.
    compiled = framework._consistent_with_lock().compile(dialect=postgresql.dialect())
    assert set(sorted(locked.ADMITTED_KEYS)) <= set(compiled.params.values())
    assert KNOWN_AT_BASIS_KEY in compiled.params.values()


def test_a_foreign_key_still_refuses_by_name_under_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, errors = _resolve(monkeypatch, {**LOCKED_HISTORICAL, "include_zero": True})
    assert _findings(errors) == {
        "parameters.include_zero": locked.NOT_A_LOCK_SELECTOR.format(
            key="include_zero", kind=KIND, lock=LOCK
        )
    }
    resolved, errors = _resolve(monkeypatch, LOCKED_HISTORICAL)
    assert errors == []
    tampered = _persisted(resolved)
    tampered["parameters"]["include_zero"] = True
    assert locked.run_mismatch(tampered, SCOPE) == "parameters.include_zero"


def test_the_basis_rule_composes_with_the_lock_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """``historical`` without ``known_at`` is refused on a locked run too — by the basis rule, not
    by the lock's (the key is admitted)."""
    _, errors = _resolve(
        monkeypatch, {"period_lock_id": str(LOCK), KNOWN_AT_BASIS_KEY: HISTORICAL_BASIS}
    )
    assert _findings(errors) == {f"parameters.{KNOWN_AT_BASIS_KEY}": framework.BASIS_NEEDS_KNOWN_AT}

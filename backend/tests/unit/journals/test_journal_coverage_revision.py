"""Security finding SC-7 — revision 0085 replaces the DB-16 coverage function without the mode
(04 rev 1.106; supervisor ruling R-32; DG-MIG-04 / DG-MIG-12 literals). CPU-only: the literals are
compared with the installing revision's body; the database proof is
``tests/pg/test_db_invariants.py::test_db_16_journal_run_coverage_contiguous`` and
``tests/domain/journals/test_summarise.py::test_sc_7_delta_run_never_journalises_seals_a_gross_run_covered``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final

VERSIONS: Final = Path(__file__).resolve().parents[4] / "backend/erev_api/db/migrations/versions"


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0085_replaces_the_coverage_function_and_restores_the_0046_literal() -> None:
    revision = _load("0085_journal_run_coverage_without_mode")
    assert revision.revision == "0085"
    assert revision.FUNCTION == "tg_journal_run__coverage"
    installed = _load("0046_journal_tables").RUN_COVERAGE_BODY
    assert revision.PREVIOUS == installed  # the downgrade restores it verbatim (DG-MIG-04)
    assert revision.BODY != revision.PREVIOUS
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS


def test_0085_keys_lock_and_coverage_on_entity_book_and_period_only() -> None:
    """The defect was the mode in three places of the 0046 body: the advisory-lock key, the covered
    maximum's WHERE clause and the message. None of them names the mode any more."""
    revision = _load("0085_journal_run_coverage_without_mode")
    old, new = revision.PREVIOUS, revision.BODY
    assert "|| ':' || NEW.mode::text, 0));" in old and "AND r.mode = NEW.mode" in old
    assert "mode" not in new
    assert "|| NEW.book_code::text || ':' || NEW.period_id::text, 0));" in new
    # everything else of the guard is kept: the scope early-return, the cancelled exclusion, the
    # run's own row and the error code.
    for kept in (
        "IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()",
        "OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN",
        "AND r.state <> 'cancelled' AND r.id <> NEW.id;",
        "IF NEW.from_chain_seq IS DISTINCT FROM covered THEN",
        "EREV-JR-001: run %s starts at chain sequence %s, but the runs of ",
    ):
        assert kept in old and kept in new, kept


def test_0085_holds_the_legacy_range_to_the_same_rule() -> None:
    """A ``DELTA`` run covers a second book; its LEGACY range starts at the maximum
    ``delta_to_chain_seq`` of the key's non-cancelled runs, or 0. A run that states no LEGACY range
    (every ``GROSS`` run) is not checked."""
    new = _load("0085_journal_run_coverage_without_mode").BODY
    assert "coalesce(max(r.delta_to_chain_seq), 0)" in new
    assert "IF NEW.delta_from_chain_seq IS NOT NULL" in new
    assert "AND NEW.delta_from_chain_seq IS DISTINCT FROM legacy_covered THEN" in new
    assert new.count("EREV-JR-001") == 2
    assert new.index("INTO covered, legacy_covered") < new.index("IF NEW.from_chain_seq")

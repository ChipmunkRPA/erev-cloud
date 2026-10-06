"""REOPEN-CLOSING-FLAG-1 — revision 0113 reads ``is_post_reopen`` from the period's lock record and
refuses a missing reason (supervisor ruling R-117 (c); 04 rev 1.184 T-SL-04, T-REF-07, §14.1 DB-07;
DG-MIG-04 / DG-MIG-12 literals). CPU-only: the literals are compared with the revisions that
installed what the downgrade restores (0105 for the guard, 0107 for the check); the database
proofs are
``tests/pg/test_db_invariants.py::test_ctl_015_subledger_insert_into_closed_period`` and
``::test_db_07_invalid_pair_rejected``, ``tests/pg/test_period_guard_row_lock.py``,
``tests/pg/test_period_guard_legacy.py`` and
``tests/domain/close/test_reopen.py::test_a_line_posted_in_the_soft_close_after_a_reopen_is_a_post_reopen_line``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final

VERSIONS: Final = Path(__file__).resolve().parents[4] / "backend/erev_api/db/migrations/versions"
# what revision 0105 stored: the state literal of the line's own row or of the primary book's
STATE_LITERALS: Final = (
    "  NEW.is_post_reopen := (period_state_now = 'reopened'",
    "                         OR coalesce(primary_state_now, '') = 'reopened');",
)
STATE_READS: Final = (
    "    SELECT s.state::text INTO primary_state_now",
    "  SELECT s.state::text INTO period_state_now",
)
CANCEL: Final = "'CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER'"
REOPEN: Final = "'ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', 'OTHER'"


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0113_restores_the_0105_body_and_the_0107_check() -> None:
    revision = _load("0113_post_reopen_from_lock_record")
    guard = _load("0105_legacy_follows_primary")
    pair = _load("0107_cancel_close_returns_reopened")
    # the number is the register's; the parent is not pinned here — it follows the head the
    # revision finds at each merge (supervisor rulings R-68 (e) and R-117 (h))
    assert revision.revision == "0113"
    # the downgrade restores the body and the check verbatim (DG-MIG-04): the latest revisions
    # that installed them
    assert revision.SUBLEDGER_GUARD_BODY_0105 == guard.SUBLEDGER_GUARD_BODY
    assert revision.REASON_SQL_0107 == pair.REASON_SQL
    assert revision.SUBLEDGER_GUARD == guard.SUBLEDGER_GUARD
    assert revision.REASON_CHECK == pair.REASON_CHECK
    assert "$fn$" not in revision.SUBLEDGER_GUARD_BODY


def test_0113_reads_the_flag_from_the_lock_records_and_changes_nothing_else() -> None:
    revision = _load("0113_post_reopen_from_lock_record")
    new = revision.SUBLEDGER_GUARD_BODY.split("\n")
    old = revision.SUBLEDGER_GUARD_BODY_0105.split("\n")
    # no state literal decides the flag any more, and each state row gives its lock id as well
    assert [line for line in old if line not in new] == [
        STATE_READS[0],
        STATE_READS[1],
        *STATE_LITERALS,
    ]
    record = [
        "      FROM erev.period_lock l",
        "     WHERE l.tenant_id = NEW.tenant_id AND l.id = {lock};",
        "  END IF;",
    ]
    assert [line for line in new if line not in old] == [
        "  lock_now uuid;",
        "  lock_kind_now text;",
        "  primary_lock_now uuid;",
        "  primary_lock_kind_now text;",
        "    SELECT s.state::text, s.current_lock_id INTO primary_state_now, primary_lock_now",
        "  SELECT s.state::text, s.current_lock_id INTO period_state_now, lock_now",
        "  IF lock_now IS NOT NULL THEN",
        "    SELECT l.kind::text INTO lock_kind_now",
        record[0],
        record[1].format(lock="lock_now"),
        "  IF primary_lock_now IS NOT NULL THEN",
        "    SELECT l.kind::text INTO primary_lock_kind_now",
        record[0],
        record[1].format(lock="primary_lock_now"),
        "  NEW.is_post_reopen := (coalesce(lock_kind_now = 'REOPEN', false)",
        "                         OR coalesce(primary_lock_kind_now = 'REOPEN', false));",
    ]
    body = revision.SUBLEDGER_GUARD_BODY
    assert "'reopened');" not in body and body.count("NEW.is_post_reopen :=") == 1
    # both state rows are locked first — the primary book's for a LEGACY line, then the line's
    # own; each record is read afterwards in a statement of its own, never joined to a row the
    # guard may have waited for, and without a lock
    assert body.count("FOR SHARE;") == 2 and "JOIN" not in body.upper()
    assert body.rindex("FOR SHARE;") < body.index("FROM erev.period_lock l")
    assert body.rindex("FROM erev.period_lock l") < body.index("NEW.is_post_reopen :=")
    # the refusals of a period that is not postable still come before the flag
    assert body.rindex("EREV-LED-003: period %s of entity") < body.index("IF lock_now IS NOT NULL")
    assert body.index("whose close the '") < body.index("IF lock_now IS NOT NULL")


def test_0113_refuses_a_missing_reason_for_each_pair_that_asks_one() -> None:
    revision = _load("0113_post_reopen_from_lock_record")
    # ``NULL IN (…)`` is NULL, which a CHECK lets pass: every term is strict now
    assert revision.REASON_SQL == (
        "(NOT (from_state = 'closing' AND to_state = 'open') "
        f"OR coalesce(reason_code IN ({CANCEL}), false)) "
        "AND (NOT (from_state = 'closing' AND to_state = 'reopened') "
        f"OR coalesce(reason_code IN ({CANCEL}), false)) "
        "AND (NOT (from_state = 'closed' AND to_state = 'reopened') "
        f"OR coalesce(reason_code IN ({REOPEN}), false))"
    )
    assert revision.REASON_SQL.count("coalesce(") == 3
    assert revision.REASON_SQL_0107.count("coalesce(") == 1

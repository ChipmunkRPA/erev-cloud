"""SCH-06 CPU pins (record §4.31; Codex production-20260922-0349 §2, 0644 §1, 0708 §2): the
deferred-origin gap, and the shape of the candidate populations — the performing entity's channels
resolve the group through the CURRENT membership and never touch the contracting entity's rows."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from erev_api.domain.reference.period_redirty import (
    PeriodStateRow,
    candidate_selects,
    deferred_gap,
)
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

# ``erev.contract`` as a table reference: not ``erev.contract_event``, ``…contract_id`` etc.
CONTRACT_TABLE = re.compile(r"erev\.contract(?![_a-z])")
CURRENT_MEMBER = "combination_group_member.valid_to_known_at IS NULL"


def _row(month: int, state: str) -> PeriodStateRow:
    start = date(2026, month, 1)
    end = date(2026, month + 1, 1) - date.resolution if month < 12 else date(2026, 12, 31)
    return PeriodStateRow(uuid4(), start, end, state)


def _ids(rows: list[PeriodStateRow], *months: int) -> tuple[UUID, ...]:
    return tuple(rows[m - 1].period_id for m in months)


def test_the_gap_is_every_closed_period_after_the_latest_postable_one() -> None:
    rows = [
        _row(1, "closed"),
        _row(2, "closed"),
        _row(3, "open"),
        _row(4, "closed"),
        _row(5, "permanently_locked"),
        _row(6, "future"),
        _row(7, "future"),
    ]
    assert deferred_gap(rows, opened_start=date(2026, 7, 1)) == _ids(rows, 4, 5)
    # Opening March itself: January and February are the gap (no postable period before March).
    assert deferred_gap(rows, opened_start=date(2026, 3, 1)) == _ids(rows, 1, 2)


def test_future_in_span_is_no_origin_and_closing_or_reopened_bound_it() -> None:
    rows = [
        _row(1, "closed"),
        _row(2, "reopened"),
        _row(3, "closed"),
        _row(4, "future"),
        _row(5, "closed"),
        _row(6, "future"),
    ]
    assert deferred_gap(rows, opened_start=date(2026, 6, 1)) == _ids(rows, 3, 5)
    rows[1] = PeriodStateRow(rows[1].period_id, rows[1].start_date, rows[1].end_date, "closing")
    assert deferred_gap(rows, opened_start=date(2026, 6, 1)) == _ids(rows, 3, 5)


def test_no_gap_when_the_previous_period_is_postable_or_nothing_is_closed() -> None:
    rows = [_row(1, "closed"), _row(2, "open"), _row(3, "future")]
    assert deferred_gap(rows, opened_start=date(2026, 3, 1)) == ()
    assert deferred_gap([_row(1, "future"), _row(2, "future")], opened_start=date(2026, 2, 1)) == ()


# --- the candidate populations (SCH06-PERFORMING-ENTITY-1) ---------------------------------------


def _sql(statement: Select[Any]) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def _candidates(gap: tuple[UUID, ...]) -> dict[str, Select[Any]]:
    return candidate_selects(
        tenant_id=uuid4(),
        entity_id=uuid4(),
        book_code="ASC606",
        period_id=uuid4(),
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 31),
        gap_period_ids=gap,
    )


def test_the_performing_entitys_channels_resolve_the_group_through_current_membership() -> None:
    named = _candidates((uuid4(), uuid4()))
    assert set(named) == {
        "events_in_period",
        "scheduled_in_period",
        "performing_groups",
        "events_in_gap",
        "posted_in_gap_current",
        "posted_in_gap_historical",
        "scheduled_in_gap",
    }
    for name in (
        "scheduled_in_period",
        "scheduled_in_gap",
        "performing_groups",
        "posted_in_gap_current",
    ):
        sql = _sql(named[name])
        assert "JOIN erev.combination_group_member" in sql and CURRENT_MEMBER in sql, name
        assert "combination_group_member.combination_group_id AS group_id" in sql, name
        # never the contracting entity's rows, which RLS-TE hides from a B-scoped caller
        assert CONTRACT_TABLE.search(sql) is None and "contract_event" not in sql, name
    # The event channels are the contracting entity's own rows, through the contract.
    for name in ("events_in_period", "events_in_gap"):
        sql = _sql(named[name])
        assert "erev.contract_event JOIN erev.contract ON" in sql, name
        assert "contract.combination_group_id AS group_id" in sql, name


def test_rule_c_is_bounded_by_the_performing_entity_and_the_book_only() -> None:
    sql = _sql(_candidates(())["performing_groups"])
    assert "obligation_version.performing_entity_id = " in sql
    assert "obligation_version.book_code = " in sql
    # No date window: retrospective modifications and closed-origin catch-ups concern obligations
    # whose window may have ended (supervisor ruling 2026-09-22).
    assert "start_date" not in sql and "end_date" not in sql
    # The version's own historical group is never the candidate.
    assert "obligation_version.combination_group_id" not in sql


def test_a_posted_line_in_the_gap_names_its_current_and_its_historical_group() -> None:
    named = _candidates((uuid4(),))
    current = _sql(named["posted_in_gap_current"])
    historical = _sql(named["posted_in_gap_historical"])
    for sql in (current, historical):
        assert "subledger_line.origin_period_id IN" in sql and "subledger_line.period_id IN" in sql
        assert "subledger_line.entity_id = " in sql and "subledger_line.book_code = " in sql
    assert "subledger_posting.combination_group_id AS group_id" in historical
    assert "erev.subledger_posting" not in current


def test_without_a_gap_only_the_opened_period_channels_are_candidates() -> None:
    assert set(_candidates(())) == {"events_in_period", "scheduled_in_period", "performing_groups"}

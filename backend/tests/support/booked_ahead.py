"""Bundles of a contract booked ahead of the open periods (ENGINE_SPEC_B C-05 rev 1.100; item
ENG-S10-FUTURE-INCEPTION-1, supervisor ruling R-107 (a)).

The platform hands the engine, per entity, the calendar from the period containing the group's
inception on, preceded by the earlier periods that carry a state (05 RCP-15 "Period range"). For
a contract whose inception lies after the entity's last open period every period from the
inception period on is ``future`` and the evaluation horizon (ENGINE_SPEC CV-13) ends before it.
``booked_ahead`` puts a frozen answer-key bundle into that shape in memory: nothing of the stream,
the rates or the products changes, and the key files are never edited. No database, clock or
network (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection
from datetime import date, timedelta
from typing import Final

from erev_engine.bundle import BookInput, EntityInput, InputBundle, PeriodInput

__all__ = ["OPEN_MONTHS", "booked_ahead", "horizon_end"]

OPEN_MONTHS: Final = 12  # earlier periods added per entity, all open
_FUTURE: Final = "future"
_OPEN: Final = "open"
_EVALUATED: Final = frozenset({"open", "closing", "reopened"})  # CV-13


def _month_before(first: date) -> tuple[date, date]:
    end = first - timedelta(days=1)
    return end.replace(day=1), end


def _earlier(entity: EntityInput) -> tuple[PeriodInput, ...]:
    """``OPEN_MONTHS`` calendar months before the entity's first period, open in every book."""
    first = min(entity.periods, key=lambda period: period.start_date)
    if first.start_date.day != 1:
        raise ValueError(f"{entity.code}: the calendar does not start on the first of a month")
    books = tuple(book for book, _ in first.states)
    found: list[PeriodInput] = []
    start, fiscal_year, period_no = first.start_date, first.fiscal_year, first.period_no
    for _ in range(OPEN_MONTHS):
        begin, end = _month_before(start)
        fiscal_year, period_no = (
            (fiscal_year, period_no - 1) if period_no > 1 else (fiscal_year - 1, 12)
        )
        found.append(
            PeriodInput(
                period_key=f"FY{fiscal_year}-P{period_no:02d}",
                fiscal_year=fiscal_year,
                period_no=period_no,
                start_date=begin,
                end_date=end,
                states=tuple((book, _OPEN) for book in books),
            )
        )
        start = begin
    taken = {period.period_key for period in entity.periods}
    if taken & {period.period_key for period in found}:
        raise ValueError(f"{entity.code}: an added period key is already in the calendar")
    return tuple(reversed(found))


def _policies(
    book: BookInput, first_keys: dict[str, str], added: dict[str, list[str]]
) -> BookInput:
    """The pin-P rows follow the loaded periods (05 RCP-15): every PERIOD-scope row of an entity's
    first carried period is repeated for each period added before it."""
    rows = list(book.policies)
    for row in book.policies:
        if row.scope != "PERIOD":
            continue
        entity_code, _, period_key = row.subject_key.partition("@")
        if first_keys.get(entity_code) != period_key:
            continue
        rows.extend(
            dataclasses.replace(row, subject_key=f"{entity_code}@{key}")
            for key in added[entity_code]
        )
    rows.sort(key=lambda row: (row.code, row.scope, row.subject_key))
    return dataclasses.replace(book, policies=tuple(rows))


def booked_ahead(bundle: InputBundle, *, entities: Collection[str] | None = None) -> InputBundle:
    """``bundle`` as the platform builds it for a contract booked ahead of the open periods of
    ``entities`` (every entity by default): each of them gains ``OPEN_MONTHS`` earlier open
    periods, and every period the bundle carried for it becomes ``future`` in every book — its
    horizon ends the day before the calendar the bundle carried, so before the group's inception
    period. An entity not named keeps its calendar as it is."""
    chosen = {entity.code for entity in bundle.entities} if entities is None else set(entities)
    unknown = chosen - {entity.code for entity in bundle.entities}
    if unknown:
        raise KeyError(sorted(unknown))
    calendars: list[EntityInput] = []
    first_keys: dict[str, str] = {}
    added: dict[str, list[str]] = {}
    for entity in bundle.entities:
        if entity.code not in chosen:
            calendars.append(entity)
            continue
        carried = sorted(entity.periods, key=lambda period: period.start_date)
        earlier = _earlier(entity)
        first_keys[entity.code] = carried[0].period_key
        added[entity.code] = [period.period_key for period in earlier]
        future = tuple(
            dataclasses.replace(period, states=tuple((book, _FUTURE) for book, _ in period.states))
            for period in carried
        )
        calendars.append(dataclasses.replace(entity, periods=(*earlier, *future)))
    books = tuple(_policies(book, first_keys, added) for book in bundle.books)
    return dataclasses.replace(bundle, entities=tuple(calendars), books=books)


def horizon_end(bundle: InputBundle, entity_code: str, book_code: str) -> date:
    """The end of the evaluation horizon of (entity, book): its last period whose state is open,
    closing or reopened (ENGINE_SPEC CV-13)."""
    (entity,) = [item for item in bundle.entities if item.code == entity_code]
    return max(
        period.end_date
        for period in entity.periods
        if dict(period.states).get(book_code) in _EVALUATED
    )

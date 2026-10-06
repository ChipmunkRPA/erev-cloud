"""Fiscal calendars and period generation (04 T-REF-04, T-REF-05, E-50, DB-05, AUD-CMD; 03
REQ-REF-002, REQ-REF-003; PRD WLD-P-05; DESIGN_SYSTEM DS-FMT-19; BUILD_SPEC RFD-1, BS3-D-16).

The commands run in a unit of work of the tenant's SYSTEM principal holding ``masterdata.maintain``
(API-R-18); the API tests cover the permission itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, period
from erev_api.domain.reference import calendars, commands
from erev_api.enums import CalendarPattern, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.schemas.calendars import CalendarIn, GenerateYearIn, GenerateYearOut
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of

NEAREST = calendars.NEAREST_WEEKDAY_TO_MONTH_END
LAST = calendars.LAST_WEEKDAY_OF_MONTH
# BS3-D-16 example: weeks end on Saturday, and the year ends on the Saturday nearest 31 January.
RETAIL: dict[str, Any] = {
    "pattern": CalendarPattern.P445,
    "fiscal_year_start_month": 2,
    "week_end_day": 6,
    "year_end_anchor": NEAREST,
}
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_DAYS_2026 = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True, slots=True)
class Calendars:
    tenant_id: UUID
    clock: FrozenClock
    keyring: KeyRing
    settings: Settings

    @contextmanager
    def uow(self) -> Iterator[UnitOfWork]:
        principal = replace(
            system_principal(self.tenant_id), permissions=frozenset({"masterdata.maintain"})
        )
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-calendars",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=self.clock.now(),
            format_locale="en-US",
        )
        files = LocalFileStore(self.settings.file_root)
        with unit_of_work(ctx, clock=self.clock, keyring=self.keyring, files=files) as uow:
            yield uow

    def create(self, code: str, **rule: Any) -> UUID:
        with self.uow() as uow:
            out = commands.create_calendar(uow, body=CalendarIn(code=code, name=code, **rule))
            uow.commit()
        return out.id

    def generate(self, calendar_id: UUID, fiscal_year: int) -> GenerateYearOut:
        with self.uow() as uow:
            out = commands.generate_year(
                uow, calendar_id=calendar_id, body=GenerateYearIn(fiscal_year=fiscal_year)
            )
            uow.commit()
        return out

    def count(self, statement: Any) -> int:
        ctx = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(ctx, read_only=True) as session:
            return int(session.execute(statement).scalar_one())

    def periods(self, calendar_id: UUID) -> int:
        where = period.c.calendar_id == calendar_id
        return self.count(select(func.count()).select_from(period).where(where))

    def audited(self, action: str) -> int:
        where = audit_event.c.action == action
        return self.count(select(func.count()).select_from(audit_event).where(where))


@pytest.fixture
def world(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Calendars:
    return Calendars(tenant_id_of(tenant_factory(keyring=keyring)), clock, keyring, app_settings)


def _weeks(out: GenerateYearOut) -> list[int]:
    return [((p.end_date - p.start_date).days + 1) // 7 for p in out.periods]


def _rule(pattern: CalendarPattern, anchor: str = NEAREST) -> calendars.CalendarRule:
    return calendars.CalendarRule(
        pattern=pattern, fiscal_year_start_month=2, week_end_day=6, year_end_anchor=anchor
    )


def test_monthly_calendar_generates_twelve_periods(world: Calendars) -> None:
    calendar_id = world.create("GREGORIAN")
    out = world.generate(calendar_id, 2026)
    assert (out.calendar_id, out.fiscal_year, out.inserted_count) == (calendar_id, 2026, 12)
    assert [(p.period_key, p.name, p.start_date, p.end_date) for p in out.periods] == [
        (
            f"FY2026-P{month:02d}",
            f"{MONTH_NAMES[month - 1]} 2026",
            date(2026, month, 1),
            date(2026, month, MONTH_DAYS_2026[month - 1]),
        )
        for month in range(1, 13)
    ]
    assert [p.quarter_no for p in out.periods] == [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]
    assert {(p.fiscal_year, p.period_no) for p in out.periods} == {(2026, n) for n in range(1, 13)}
    assert world.periods(calendar_id) == 12
    # AUD-CMD: one event for the calendar and one per inserted period.
    assert (world.audited("fiscal_calendar.create"), world.audited("period.generate")) == (1, 12)


def test_april_start_fiscal_year_named_by_end_year(world: Calendars) -> None:
    calendar_id = world.create("JP-APRIL", fiscal_year_start_month=4)
    out = world.generate(calendar_id, 2027)
    by_key = {p.period_key: p for p in out.periods}
    first, sixth, last = by_key["FY2027-P01"], by_key["FY2027-P06"], by_key["FY2027-P12"]
    assert (first.start_date, first.end_date, first.name) == (
        date(2026, 4, 1),
        date(2026, 4, 30),
        "Apr 2026",
    )
    assert (sixth.start_date, sixth.end_date, sixth.name, sixth.quarter_no) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
        "Sep 2026",
        2,
    )
    assert (last.start_date, last.end_date, last.name) == (
        date(2027, 3, 1),
        date(2027, 3, 31),
        "Mar 2027",
    )


def test_p445_retail_calendar_periods(world: Calendars) -> None:
    calendar_id = world.create("RETAIL-445", **RETAIL)
    out = world.generate(calendar_id, 2026)
    by_key = {p.period_key: p for p in out.periods}
    assert (by_key["FY2026-P01"].start_date, by_key["FY2026-P01"].end_date) == (
        date(2025, 2, 2),
        date(2025, 3, 1),
    )
    assert (by_key["FY2026-P03"].start_date, by_key["FY2026-P03"].end_date) == (
        date(2025, 3, 30),
        date(2025, 5, 3),
    )
    assert (by_key["FY2026-P12"].start_date, by_key["FY2026-P12"].end_date) == (
        date(2025, 12, 28),
        date(2026, 1, 31),
    )
    assert sum((p.end_date - p.start_date).days + 1 for p in out.periods) == 364
    assert [p.end_date.isoweekday() for p in out.periods] == [6] * 12
    assert _weeks(out) == [4, 4, 5] * 4
    # DS-FMT-19 names the periods of a week-based calendar FY<YYYY> P<NN>.
    assert [p.name for p in out.periods[:2]] == ["FY2026 P01", "FY2026 P02"]


def test_53_week_year_adds_week_to_last_period(world: Calendars) -> None:
    calendar_id = world.create("RETAIL-445", **RETAIL)
    out = world.generate(calendar_id, 2029)
    first, last = out.periods[0], out.periods[-1]
    assert (first.start_date, last.end_date) == (date(2028, 1, 30), date(2029, 2, 3))
    assert (last.end_date - first.start_date).days + 1 == 371
    assert (last.period_key, (last.end_date - last.start_date).days + 1) == ("FY2029-P12", 42)
    assert _weeks(out) == [4, 4, 5] * 3 + [4, 4, 6]


def test_week_patterns_layouts() -> None:
    def weeks(pattern: CalendarPattern) -> list[int]:
        return [spec.days // 7 for spec in calendars.generate_periods(_rule(pattern), 2026)]

    assert weeks(CalendarPattern.P454) == [4, 5, 4] * 4
    assert weeks(CalendarPattern.P544) == [5, 4, 4] * 4

    p13 = calendars.generate_periods(_rule(CalendarPattern.P13), 2026)
    assert [spec.days for spec in p13] == [28] * 13
    assert sum(spec.days for spec in p13) == 364
    assert [spec.quarter_no for spec in p13] == [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 4]
    assert (p13[-1].period_key, p13[-1].quarter_no) == ("FY2026-P13", 4)
    # The 53-week FY2029 adds its extra week to period 13.
    assert calendars.generate_periods(_rule(CalendarPattern.P13), 2029)[-1].days == 35

    for anchor in (NEAREST, LAST):
        for fiscal_year in (2026, 2029):
            w5253 = calendars.generate_periods(_rule(CalendarPattern.W5253, anchor), fiscal_year)
            p445 = calendars.generate_periods(_rule(CalendarPattern.P445, anchor), fiscal_year)
            assert (w5253[0].start_date, w5253[-1].end_date) == (
                p445[0].start_date,
                p445[-1].end_date,
            )

    # LAST_WEEKDAY_OF_MONTH ends FY2029 on the last Saturday of January 2029, a 52-week year.
    last_saturday = calendars.generate_periods(_rule(CalendarPattern.P445, LAST), 2029)
    assert (last_saturday[0].start_date, last_saturday[-1].end_date) == (
        date(2028, 1, 30),
        date(2029, 1, 27),
    )
    assert sum(spec.days for spec in last_saturday) == 364


def test_generate_year_twice_is_idempotent(world: Calendars) -> None:
    calendar_id = world.create("GREGORIAN")
    first = world.generate(calendar_id, 2026)
    second = world.generate(calendar_id, 2026)
    assert second.inserted_count == 0
    assert [p.id for p in second.periods] == [p.id for p in first.periods]
    assert len(second.periods) == 12
    assert world.periods(calendar_id) == 12
    # No period was affected, so no event was written (AUD-CMD).
    assert world.audited("period.generate") == 12


def test_generate_year_keeps_calendar_contiguous(world: Calendars) -> None:
    calendar_id = world.create("GREGORIAN")
    world.generate(calendar_id, 2026)
    with world.uow() as uow, pytest.raises(Problem) as refused:
        commands.generate_year(uow, calendar_id=calendar_id, body=GenerateYearIn(fiscal_year=2028))
    assert refused.value.slug == "validation-failed"
    assert [(error.field, error.rule_id) for error in refused.value.errors] == [
        ("fiscal_year", "DB-05")
    ]
    assert refused.value.errors[0].message == (
        "Generate FY2027 first: the periods of a calendar are contiguous."
    )
    # A year before the first grows the calendar backwards; the DB-05 trigger accepts each row.
    earlier = world.generate(calendar_id, 2025)
    assert (earlier.inserted_count, earlier.periods[-1].end_date) == (12, date(2025, 12, 31))
    world.generate(calendar_id, 2027)
    assert world.periods(calendar_id) == 36


def test_create_calendar_findings(world: Calendars) -> None:
    world.create("GREGORIAN")
    body = CalendarIn(code="GREGORIAN", name="  ", week_end_day=6)
    with world.uow() as uow, pytest.raises(Problem) as refused:
        commands.create_calendar(uow, body=body)
    assert [(error.field, error.rule_id) for error in refused.value.errors] == [
        ("code", "T-REF-04"),
        ("name", "T-REF-04"),
        ("week_end_day", "T-REF-04"),
    ]
    with world.uow() as uow, pytest.raises(Problem) as malformed:
        commands.create_calendar(uow, body=CalendarIn(code="-retail", name="Retail", **RETAIL))
    assert [error.field for error in malformed.value.errors] == ["code"]

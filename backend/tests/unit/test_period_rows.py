"""The PERIOD rows of a period-pinned parameter (item PINP-PERIOD-VALUE-1; 05 RCP-15; dev-guide
DG-KRN-REG-03; POLICIES §0.5 rule 3; 04 T-CON-07).

The finding. The bundle builder resolved every period-pinned parameter ONCE — at the bundle's
``known_at``, for the entity of the earliest member — and stamped that value on every period of
every entity. A version that took effect on a later date therefore reached the periods that had
ended before it (measured on SF-ORD-30201: POL-004 ``ENGINE`` from 1 November put a billing intent
of 12,000.00 into March at the next computation), and one entity's own version answered for the
other entities of the bundle.

The rule. A period's row carries the value in force for ITS entity at the earlier of ``known_at``
and the period's last instant in the entity's time zone, among the versions published at or
before ``known_at``. A version nobody dated: a first version of its scope answers for every
earlier period, a successor from the instant its predecessor was closed at. ``_period_rows`` is
pure over the rows of ``registry.known_versions``. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from erev_api.domain.contracts import bundles
from erev_engine.bundle import EntityInput
from support import bundles as support

BILLING = "billing.posting"  # POL-004: TENANT; framework default ERP
JE_MODE = "je.posting_mode"  # POL-005: ENTITY, TENANT; framework default GROSS
INVOICE_BASIS = "balance.position_invoice_basis"  # POL-123: TENANT; no framework default
US = support.entity("AVM-US", start=date(2026, 1, 1), months=12)  # America/New_York
UK = dataclasses.replace(US, code="AVM-UK", functional_currency="GBP", time_zone="Europe/London")
IDS = {"AVM-US": uuid4(), "AVM-UK": uuid4()}
DECEMBER = datetime(2026, 12, 1, 12, tzinfo=UTC)
PROVISIONED = datetime(2025, 12, 1, tzinfo=UTC)  # before every period of the entities here


def version(
    values: dict[str, Any],
    *,
    scope: str = "TENANT",
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    published_at: datetime = PROVISIONED,
    entity_id: UUID | None = None,
) -> dict[str, Any]:
    """One row of ``registry.known_versions``."""
    return {
        "id": uuid4(),
        "category": "ACCOUNTING_POLICY",
        "scope": scope,
        "book_code": None,
        "entity_id": entity_id,
        "values": values,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "published_at": published_at,
    }


def rows(
    code: str,
    versions: list[dict[str, Any]],
    *,
    entities: tuple[EntityInput, ...] = (US,),
    known_at: datetime = DECEMBER,
) -> dict[str, tuple[Any, str, str]]:
    """``<entity>@<period>`` -> (value, level, source) of the parameter's PERIOD rows."""
    found = bundles._period_rows(
        code,
        book_code="ASC606",
        entities=entities,
        entity_ids=IDS,
        versions=versions,
        known_at=known_at,
    )
    assert all((item.code, item.scope, item.pin) == (code, "PERIOD", "P") for item in found)
    return {item.subject_key: (item.value, item.level, item.source_ref) for item in found}


def periods(
    found: dict[str, tuple[Any, str, str]], source: str, entity: str = "AVM-US"
) -> list[str]:
    """The period keys of ``entity`` whose row came from ``source``, in order."""
    return sorted(
        key.split("@")[1]
        for key, (_, _, row_source) in found.items()
        if key.startswith(f"{entity}@") and row_source == source
    )


def months(first: int, last: int) -> list[str]:
    return [f"FY2026-P{month:02d}" for month in range(first, last + 1)]


def test_the_last_instant_of_a_period_is_the_entitys() -> None:
    end = bundles.period_end_instant
    # New York: UTC-4 under daylight time, UTC-5 from 1 November 2026, 02:00 local
    assert end(date(2026, 3, 31), "America/New_York") == datetime(
        2026, 4, 1, 3, 59, 59, 999999, tzinfo=UTC
    )
    assert end(date(2026, 10, 31), "America/New_York") == datetime(
        2026, 11, 1, 3, 59, 59, 999999, tzinfo=UTC
    )
    assert end(date(2026, 11, 30), "America/New_York") == datetime(
        2026, 12, 1, 4, 59, 59, 999999, tzinfo=UTC
    )
    assert end(date(2026, 6, 30), "Europe/London") == datetime(
        2026, 6, 30, 22, 59, 59, 999999, tzinfo=UTC
    )


def test_a_chain_of_undated_versions_is_read_at_each_periods_last_instant() -> None:
    """Three versions nobody dated: the first; one published on 15 June, inside FY2026-P06; one
    published on 10 August. May keeps the first — it ended before the second was published —
    June and July take the second, August and the periods after it the third. Before the repair
    every period carried the third."""
    second_published = datetime(2026, 6, 15, 13, tzinfo=UTC)
    third_published = datetime(2026, 8, 10, 13, tzinfo=UTC)
    third = version({BILLING: "ENGINE"}, published_at=third_published)
    second = version({BILLING: "ERP"}, published_at=second_published, effective_to=third_published)
    first = version({BILLING: "ENGINE"}, effective_to=second_published)
    found = rows(BILLING, [third, second, first])  # the latest published first
    assert len(found) == 12
    assert periods(found, str(first["id"])) == months(1, 5)
    assert periods(found, str(second["id"])) == months(6, 7)
    assert periods(found, str(third["id"])) == months(8, 12)
    assert found["AVM-US@FY2026-P05"][:2] == ("ENGINE", "T")
    assert found["AVM-US@FY2026-P06"][:2] == ("ERP", "T")
    assert found["AVM-US@FY2026-P08"][:2] == ("ENGINE", "T")


def test_an_undated_successor_of_a_dated_first_version_begins_at_its_publication() -> None:
    """The scope's first version is dated at 1 June; its successor, published on 15 August, has
    no date. January to May are held by neither and take the framework default — the successor
    begins at its publication, whatever its row's open lower bound says — June and July keep
    the first, August and the periods after it take the successor. (This item's first build
    handed January to May the successor's value.)"""
    june = datetime(2026, 6, 1, 4, tzinfo=UTC)  # 1 June, 00:00 in New York
    published = datetime(2026, 8, 15, 13, tzinfo=UTC)
    second = version({BILLING: "ENGINE"}, published_at=published)
    first = version({BILLING: "ENGINE"}, effective_from=june, effective_to=published)
    found = rows(BILLING, [second, first])  # the latest published first
    assert periods(found, "POL-004") == months(1, 5)
    assert {found[f"AVM-US@{key}"][:2] for key in months(1, 5)} == {("ERP", "DEFAULT")}
    assert periods(found, str(first["id"])) == months(6, 7)
    assert periods(found, str(second["id"])) == months(8, 12)


def test_a_first_version_answers_for_every_period_unless_it_is_dated() -> None:
    """A tenant's first version without a date states the policy it has applied: every period
    carries it, the ones that ended before its publication too. Dated at 1 June, it leaves the
    earlier periods to the framework default."""
    undated = version({BILLING: "ENGINE"})
    assert periods(rows(BILLING, [undated]), str(undated["id"])) == months(1, 12)
    june = datetime(2026, 6, 1, 4, tzinfo=UTC)  # 1 June, 00:00 in New York
    dated = version({BILLING: "ENGINE"}, effective_from=june)
    found = rows(BILLING, [dated])
    assert periods(found, "POL-004") == months(1, 5)
    assert {found[f"AVM-US@{key}"][:2] for key in months(1, 5)} == {("ERP", "DEFAULT")}
    assert periods(found, str(dated["id"])) == months(6, 12)


def test_a_version_that_takes_effect_later_never_reaches_an_earlier_period() -> None:
    """The measured case: a successor effective from 1 November. Read on 12 September it answers
    for no period; read in December it answers for November and December, and March keeps the
    predecessor."""
    november = datetime(2026, 11, 1, 4, tzinfo=UTC)
    second = version({BILLING: "ENGINE"}, effective_from=november)
    first = version({BILLING: "ERP"}, effective_to=november)
    known = [second, first]
    september = datetime(2026, 9, 12, 16, tzinfo=UTC)
    assert periods(rows(BILLING, known, known_at=september), str(first["id"])) == months(1, 12)
    found = rows(BILLING, known)
    assert periods(found, str(first["id"])) == months(1, 10)
    assert periods(found, str(second["id"])) == months(11, 12)


def test_a_period_that_has_not_ended_takes_the_value_in_force_at_known_at() -> None:
    """Read on 12 September: a successor effective from 20 September is not in force yet, so
    September and the later periods carry the predecessor; read on 21 September they carry the
    successor, and August keeps the predecessor."""
    boundary = datetime(2026, 9, 20, 4, tzinfo=UTC)
    second = version({BILLING: "ENGINE"}, effective_from=boundary)
    first = version({BILLING: "ERP"}, effective_to=boundary)
    known = [second, first]
    before = rows(BILLING, known, known_at=datetime(2026, 9, 12, 16, tzinfo=UTC))
    assert periods(before, str(first["id"])) == months(1, 12)
    after = rows(BILLING, known, known_at=datetime(2026, 9, 21, 16, tzinfo=UTC))
    assert periods(after, str(first["id"])) == months(1, 8)
    assert periods(after, str(second["id"])) == months(9, 12)


def test_a_period_ends_in_its_entitys_time_zone() -> None:
    """A successor effective from 1 July, 00:00 UTC. June ends at 22:59 UTC in London and at 03:59
    UTC of 1 July in New York: London's June keeps the predecessor, New York's June takes the
    successor."""
    boundary = datetime(2026, 7, 1, 0, tzinfo=UTC)
    second = version({BILLING: "ENGINE"}, effective_from=boundary)
    first = version({BILLING: "ERP"}, effective_to=boundary)
    found = rows(BILLING, [second, first], entities=(UK, US))
    assert periods(found, str(first["id"]), "AVM-UK") == months(1, 6)
    assert periods(found, str(first["id"]), "AVM-US") == months(1, 5)
    assert periods(found, str(second["id"]), "AVM-US") == months(6, 12)


def test_an_entitys_version_answers_for_that_entitys_periods_only() -> None:
    """Before the repair the value of the earliest member's entity was stamped on every entity
    of the bundle."""
    tenant = version({JE_MODE: "GROSS"})
    entity = version({JE_MODE: "DELTA"}, scope="ENTITY", entity_id=IDS["AVM-UK"])
    found = rows(JE_MODE, [entity, tenant], entities=(UK, US))
    assert periods(found, str(entity["id"]), "AVM-UK") == months(1, 12)
    assert periods(found, str(tenant["id"]), "AVM-US") == months(1, 12)
    assert found["AVM-UK@FY2026-P03"][:2] == ("DELTA", "E")
    assert found["AVM-US@FY2026-P03"][:2] == ("GROSS", "T")


def test_a_parameter_without_a_default_has_rows_only_where_a_version_holds_it() -> None:
    """POL-123 has no framework default: no version, no row; a first version dated at 1 June
    gives rows from June on (the engine reads POL-004 for the earlier periods, ENGINE_SPEC_B
    S10-R-06)."""
    assert rows(INVOICE_BASIS, []) == {}
    june = datetime(2026, 6, 1, 4, tzinfo=UTC)
    dated = version({INVOICE_BASIS: "ERP_POSTED_INVOICES"}, effective_from=june)
    found = rows(INVOICE_BASIS, [dated])
    assert sorted(key.split("@")[1] for key in found) == months(6, 12)
    assert set(found.values()) == {("ERP_POSTED_INVOICES", "T", str(dated["id"]))}

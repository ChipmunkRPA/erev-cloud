"""``registry.resolve_among``: the version levels for an instant other than the one the versions
were read at (item PINP-PERIOD-VALUE-1; 05 RCP-15; dev-guide DG-KRN-REG-03; POLICIES §0.5 rule 3).

The bundle builder reads the registry versions known at its ``known_at`` once and asks, per entity
and period, for the value in force at the period's last instant. The rows here are the columns
``known_versions`` selects, the latest published first. No database (DG-TST-18).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.enums import BookCode
from erev_api.registry.resolve import ResolvedValue, resolve_among

BILLING = "billing.posting"  # POL-004: TENANT; framework default ERP; pin P
JE_MODE = "je.posting_mode"  # POL-005: ENTITY, TENANT; framework default GROSS; pin P
LOSS_SCOPE = "loss.scope"  # BOOK; FORCED under IFRS 15; framework default SCOPED_605_35_ONLY
INVOICE_BASIS = "balance.position_invoice_basis"  # POL-123: TENANT; no framework default; pin P
ROUNDING = "rounding.posting_mode"  # FORCED in both books
US = BookCode.ASC606
AVM_US, AVM_UK = uuid4(), uuid4()


PROVISIONED = datetime(2025, 12, 1, tzinfo=UTC)  # before every instant asked about here


def at(month: int, day: int = 1, hour: int = 0) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def version(
    values: dict[str, Any],
    *,
    scope: str = "TENANT",
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    published_at: datetime = PROVISIONED,
    book_code: str | None = None,
    entity_id: UUID | None = None,
    category: str = "ACCOUNTING_POLICY",
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "category": category,
        "scope": scope,
        "book_code": book_code,
        "entity_id": entity_id,
        "values": values,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "published_at": published_at,
    }


def answer(found: ResolvedValue) -> tuple[Any, str]:
    return found.value, found.level


def test_a_first_version_without_a_date_answers_for_every_instant() -> None:
    """A tenant's first version of a scope has no lower bound: it answers for the periods that
    ended before it was published, as it did when one instant served every period."""
    first = version({BILLING: "ENGINE"})
    for instant in (at(1), at(6), at(12)):
        found = resolve_among([first], BILLING, book_code=US, at=instant)
        assert (answer(found), found.source_id) == (("ENGINE", "T"), first["id"])


def test_a_dated_first_version_answers_from_its_date() -> None:
    first = version({BILLING: "ENGINE"}, effective_from=at(11, 1, 4))
    assert answer(resolve_among([first], BILLING, book_code=US, at=at(10, 31, 23))) == (
        "ERP",
        "DEFAULT",
    )
    assert answer(resolve_among([first], BILLING, book_code=US, at=at(11, 1, 4))) == ("ENGINE", "T")


def test_a_dated_successor_answers_from_its_date_and_the_predecessor_before() -> None:
    """Ranges are half-open: the predecessor's ``effective_to`` is the successor's
    ``effective_from`` (``lifecycle.publish``)."""
    boundary = at(11, 1, 4)
    second = version({BILLING: "ENGINE"}, effective_from=boundary)
    first = version({BILLING: "ERP"}, effective_to=boundary)
    known = [second, first]  # the latest published first
    before = resolve_among(known, BILLING, book_code=US, at=at(10, 31, 23))
    assert (answer(before), before.source_id) == (("ERP", "T"), first["id"])
    after = resolve_among(known, BILLING, book_code=US, at=boundary)
    assert (answer(after), after.source_id) == (("ENGINE", "T"), second["id"])


def test_a_successor_without_a_date_answers_from_its_publication() -> None:
    """``publish`` leaves the successor's ``effective_from`` NULL and closes the predecessor at
    the publication instant. The successor's row has no lower bound; it begins at its
    publication, so the predecessor answers for an earlier instant. Three versions in a row
    read the same way."""
    second_published, third_published = at(6, 15, 9), at(9, 12, 16)
    third = version({BILLING: "ENGINE"}, published_at=third_published)
    second = version({BILLING: "ERP"}, published_at=second_published, effective_to=third_published)
    first = version({BILLING: "ENGINE"}, effective_to=second_published)
    known = [third, second, first]
    sources = [
        resolve_among(known, BILLING, book_code=US, at=instant).source_id
        for instant in (at(3, 31, 23), second_published, at(8, 31, 23), third_published, at(12))
    ]
    assert sources == [first["id"], second["id"], second["id"], third["id"], third["id"]]


def test_a_successor_without_a_date_never_answers_before_its_publication() -> None:
    """The scope's first version is DATED, at 1 June, and its successor has no date: published on
    15 August, it closes the first there. No version holds an instant in May — the successor
    begins at its publication, whatever its row's open lower bound says — so the framework
    default answers. (This item's first build let the successor answer for May: where the
    first version does not hold the instant, nothing ended before the successor did.)"""
    june, published = at(6, 1, 4), at(8, 15, 9)
    second = version({BILLING: "ENGINE"}, published_at=published)
    first = version(
        {BILLING: "ENGINE"}, effective_from=june, effective_to=published, published_at=at(5, 20)
    )
    known = [second, first]
    may = resolve_among(known, BILLING, book_code=US, at=at(5, 31, 23))
    assert (answer(may), may.source_id) == (("ERP", "DEFAULT"), None)
    july = resolve_among(known, BILLING, book_code=US, at=at(7, 31, 23))
    assert (answer(july), july.source_id) == (("ENGINE", "T"), first["id"])
    for instant in (published, at(12)):
        found = resolve_among(known, BILLING, book_code=US, at=instant)
        assert (answer(found), found.source_id) == (("ENGINE", "T"), second["id"])
    # the scope's FIRST version without a date keeps its open lower bound, however late it was
    # published
    only = version({BILLING: "ENGINE"}, published_at=published)
    assert answer(resolve_among([only], BILLING, book_code=US, at=at(5, 31, 23))) == ("ENGINE", "T")
    # and a version of another scope is no predecessor: an entity's first undated version too
    entity = version({JE_MODE: "DELTA"}, scope="ENTITY", entity_id=AVM_UK, published_at=published)
    tenant = version({JE_MODE: "GROSS"})
    early = resolve_among([entity, tenant], JE_MODE, book_code=US, entity_id=AVM_UK, at=at(5))
    assert (answer(early), early.source_id) == (("DELTA", "E"), entity["id"])


def test_of_two_versions_that_still_hold_an_instant_the_one_that_ends_first_answers() -> None:
    """``lifecycle.publish`` writes no such rows — a successor's date is after its predecessor's
    and the predecessor is closed there — but the reading of rows it did not write is stated:
    the version whose range ends first answers, and between equal ends the latest published."""
    later = version({BILLING: "ERP"}, effective_from=at(6), published_at=at(5, 20))
    earlier = version({BILLING: "ENGINE"}, effective_from=at(3), effective_to=at(9))
    july = resolve_among([later, earlier], BILLING, book_code=US, at=at(7))
    assert (answer(july), july.source_id) == (("ENGINE", "T"), earlier["id"])
    october = resolve_among([later, earlier], BILLING, book_code=US, at=at(10))
    assert (answer(october), october.source_id) == (("ERP", "T"), later["id"])
    twin = version(
        {BILLING: "ERP"}, effective_from=at(4), effective_to=at(9), published_at=at(3, 20)
    )
    same_end = resolve_among([twin, earlier], BILLING, book_code=US, at=at(7))
    assert same_end.source_id == twin["id"]


def test_an_entity_version_answers_for_its_entity_only() -> None:
    tenant = version({JE_MODE: "GROSS"})
    entity = version({JE_MODE: "DELTA"}, scope="ENTITY", entity_id=AVM_UK)
    known = [entity, tenant]
    uk = resolve_among(known, JE_MODE, book_code=US, entity_id=AVM_UK, at=at(9))
    assert (answer(uk), uk.source_id) == (("DELTA", "E"), entity["id"])
    us = resolve_among(known, JE_MODE, book_code=US, entity_id=AVM_US, at=at(9))
    assert (answer(us), us.source_id) == (("GROSS", "T"), tenant["id"])
    # without an entity the ENTITY level is not consulted
    assert answer(resolve_among(known, JE_MODE, book_code=US, at=at(9))) == ("GROSS", "T")


def test_an_entity_version_that_takes_effect_later_leaves_the_earlier_instants_to_the_tenant() -> (
    None
):
    tenant = version({JE_MODE: "GROSS"})
    entity = version({JE_MODE: "DELTA"}, scope="ENTITY", entity_id=AVM_UK, effective_from=at(7))
    known = [entity, tenant]
    levels = [
        resolve_among(known, JE_MODE, book_code=US, entity_id=AVM_UK, at=instant).level
        for instant in (at(6, 30, 23), at(7))
    ]
    assert levels == ["T", "E"]


def test_a_book_version_answers_for_its_book() -> None:
    asc = version({LOSS_SCOPE: "ALL_CONTRACTS_WITH_EAC"}, scope="BOOK", book_code="ASC606")
    found = resolve_among([asc], LOSS_SCOPE, book_code=US, at=at(9))
    assert answer(found) == ("ALL_CONTRACTS_WITH_EAC", "B")
    # FORCED under IFRS 15: the framework value, whatever a version says
    ifrs = version({LOSS_SCOPE: "SCOPED_605_35_ONLY"}, scope="BOOK", book_code="IFRS15")
    forced = resolve_among([ifrs, asc], LOSS_SCOPE, book_code=BookCode.IFRS15, at=at(9))
    assert answer(forced) == ("ALL_CONTRACTS_WITH_EAC", "DEFAULT")


def test_a_version_that_does_not_hold_the_parameter_passes_to_the_next_level() -> None:
    tenant = version({JE_MODE: "GROSS", BILLING: "ENGINE"})
    entity = version({BILLING: "ERP"}, scope="ENTITY", entity_id=AVM_UK)  # not allowed there
    found = resolve_among([entity, tenant], JE_MODE, book_code=US, entity_id=AVM_UK, at=at(9))
    assert (answer(found), found.source_id) == (("GROSS", "T"), tenant["id"])
    # another category's version is never read for the parameter
    other = version({JE_MODE: "DELTA"}, category="DISCLOSURE_ELECTION")
    assert answer(resolve_among([other], JE_MODE, book_code=US, at=at(9))) == ("GROSS", "DEFAULT")


def test_a_forced_parameter_keeps_the_framework_value() -> None:
    tenant = version({ROUNDING: "HALF_EVEN"})
    assert answer(resolve_among([tenant], ROUNDING, book_code=US, at=at(9))) == (
        "HALF_UP",
        "DEFAULT",
    )


def test_a_parameter_without_a_default_has_no_value_before_its_first_version() -> None:
    first = version({INVOICE_BASIS: "ERP_POSTED_INVOICES"}, effective_from=at(6))
    assert answer(resolve_among([first], INVOICE_BASIS, book_code=US, at=at(5, 31, 23))) == (
        None,
        "DEFAULT",
    )
    assert answer(resolve_among([first], INVOICE_BASIS, book_code=US, at=at(6))) == (
        "ERP_POSTED_INVOICES",
        "T",
    )


def test_an_unknown_parameter_is_refused_by_name() -> None:
    with pytest.raises(LookupError, match="no.such.parameter"):
        resolve_among([], "no.such.parameter", book_code=US, at=at(9))

"""The order of effective instants of the versions of one registry scope key, at its boundary
(04 §16.5 "Order of effective instants" rev 1.183; PRD ERR-80, ERR-81; supervisor ruling R-117 (b)
rule 4 and the supervisor's ruling of 2026-10-01 on the tie — way (i) of the report of items
REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1).

``registry_versions.order_errors`` is pure: the version being submitted, the PUBLISHED version of
its key and the instant of the check. A version never takes effect before the effective instant of
the PUBLISHED version, and takes effect together with it only when that version names no date:

* such a version is in effect from its own publication instant, so a successor published at that
  same instant supersedes it there, and its interval is empty. A world built on one frozen instant
  — every seed world — meets this tie at its first settings version
  (``tests/domain/demo/test_seed_avenmoor_reference.py::test_tenant_policy_version``);
* a tie with a DATED version stays refused, as ``lifecycle.publish`` refuses it;
* one microsecond before the instant of an undated version is refused like any earlier instant.

The refusals through the product are in ``tests/domain/policies/test_registry_whole_set.py``
(``test_err_80_…``, ``test_err_81_…``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from erev_api.domain.policies import registry_versions

PUBLISHED_AT = datetime(2026, 9, 12, 12, tzinfo=UTC)
EFFECTIVE = datetime(2026, 11, 1, 4, tzinfo=UTC)
TICK = timedelta(microseconds=1)
DATED = "Version 3 takes effect on {day}. Choose an effective date after it."
UNDATED = (
    "Version 3 takes effect on {day}. Choose an effective date after it, or submit this version "
    "once version 3 is in effect."
)


def _published(effective_from: datetime | None) -> dict[str, Any]:
    return {"version_no": 3, "effective_from": effective_from, "published_at": PUBLISHED_AT}


def _refusals(
    effective_from: datetime | None, predecessor: dict[str, Any], *, now: datetime
) -> list[tuple[str | None, str | None, str]]:
    found = registry_versions.order_errors({"effective_from": effective_from}, predecessor, now=now)
    return [(error.field, error.rule_id, error.message) for error in found]


def test_the_first_version_of_a_key_has_no_order_to_keep() -> None:
    assert _refusals(None, None, now=PUBLISHED_AT) == []  # type: ignore[arg-type]
    assert registry_versions.order_errors({"effective_from": EFFECTIVE}, None, now=EFFECTIVE) == []


@pytest.mark.parametrize("dated", [False, True], ids=["without a date", "dated at that instant"])
def test_a_tie_with_a_published_version_that_names_no_date_is_admitted(dated: bool) -> None:
    """The published version took effect at its publication; a successor starts at that very
    instant — submitted there without a date, or dated at it — and supersedes it there."""
    undated = _published(None)
    mine = PUBLISHED_AT if dated else None
    assert _refusals(mine, undated, now=PUBLISHED_AT) == []
    # and any later instant, as before
    assert _refusals(mine if dated else None, undated, now=PUBLISHED_AT + TICK) == []
    assert _refusals(PUBLISHED_AT + TICK, undated, now=PUBLISHED_AT) == []


def test_one_microsecond_before_an_undated_versions_instant_is_refused() -> None:
    """Admitting the tie admits nothing earlier: a successor never takes effect before the
    version it stands on."""
    undated = _published(None)
    day = "12 Sep 2026"
    assert _refusals(PUBLISHED_AT - TICK, undated, now=PUBLISHED_AT) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", DATED.format(day=day))
    ]
    assert _refusals(None, undated, now=PUBLISHED_AT - TICK) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", UNDATED.format(day=day))
    ]


def test_a_tie_with_a_dated_published_version_stays_refused() -> None:
    """A dated version is superseded only after its date (``lifecycle.publish`` refuses the tie
    too): dated at that instant, or submitted without a date at it, the successor is refused —
    and admitted one microsecond later."""
    dated = _published(EFFECTIVE)
    day = "01 Nov 2026"
    assert _refusals(EFFECTIVE, dated, now=PUBLISHED_AT) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", DATED.format(day=day))
    ]
    assert _refusals(None, dated, now=EFFECTIVE) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", UNDATED.format(day=day))
    ]
    assert _refusals(EFFECTIVE - TICK, dated, now=PUBLISHED_AT) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", DATED.format(day=day))
    ]
    assert _refusals(EFFECTIVE + TICK, dated, now=PUBLISHED_AT) == []
    assert _refusals(None, dated, now=EFFECTIVE + TICK) == []


# --- before the first legal entity (PRD ERR-80 rev 1.178; 04 §16.5 rev 1.227; item
# PINP-PERIOD-VALUE-1, the supervisor's ruling of 2026-10-02) ------------------------------------

HISTORY = datetime(2023, 1, 1, tzinfo=UTC)  # the first day of a migrated history


def _before_entities(
    effective_from: datetime | None, predecessor: dict[str, Any], *, now: datetime
) -> list[tuple[str | None, str | None, str]]:
    """``_refusals`` for an accounting-category version in a workspace without a legal entity."""
    found = registry_versions.order_errors(
        {"effective_from": effective_from}, predecessor, now=now, before_first_entity=True
    )
    return [(error.field, error.rule_id, error.message) for error in found]


def test_before_the_first_legal_entity_the_order_yields_to_a_published_version_without_a_date() -> (
    None
):
    """A version without a date is in effect from its publication for the ORDER of versions, and
    answers for every earlier period for the VALUE of a period when it is the first of its scope
    (04 T-PLT-32). Before the first legal entity the order yields where the two meet: a dated
    version may start before the publication of a published version that names no date — a
    migrating tenant's policies, dated at the first day of its history. The caller says that the
    workspace has no legal entity and the category is an accounting one; unsaid, the refusal
    stands."""
    undated = _published(None)
    refused = [("effective_from", "REGISTRY_EFFECTIVE_ORDER", DATED.format(day="12 Sep 2026"))]
    for mine in (HISTORY, PUBLISHED_AT - TICK):
        assert _refusals(mine, undated, now=PUBLISHED_AT) == refused
        assert _before_entities(mine, undated, now=PUBLISHED_AT) == []
    # at the published version's instant and after it, as without the yield
    assert _before_entities(PUBLISHED_AT, undated, now=PUBLISHED_AT) == []
    assert _before_entities(None, undated, now=PUBLISHED_AT) == []


def test_before_the_first_legal_entity_the_order_stands_against_a_dated_published_version() -> None:
    """Publication closes the predecessor at the successor's instant, so a successor dated before
    a DATED predecessor would leave it an interval that ends before it begins: refused, with the
    tie, as from the first legal entity on. PRD ERR-81 — a version without a date while the
    published one is not in effect yet — is untouched."""
    dated = _published(EFFECTIVE)
    day = "01 Nov 2026"
    for mine in (HISTORY, EFFECTIVE - TICK, EFFECTIVE):
        assert _before_entities(mine, dated, now=PUBLISHED_AT) == [
            ("effective_from", "REGISTRY_EFFECTIVE_ORDER", DATED.format(day=day))
        ]
    assert _before_entities(EFFECTIVE + TICK, dated, now=PUBLISHED_AT) == []
    assert _before_entities(None, dated, now=PUBLISHED_AT) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", UNDATED.format(day=day))
    ]
    assert _before_entities(None, _published(None), now=PUBLISHED_AT - TICK) == [
        ("effective_from", "REGISTRY_EFFECTIVE_ORDER", UNDATED.format(day="12 Sep 2026"))
    ]

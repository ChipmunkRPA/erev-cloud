"""D-98 candidate 127 — Codex production-20260921-0533 F1
(``PRODUCTION-B4-EXACT-OPENING-7916266a.md``): the intact application pipeline of an
``OPENING_BALANCE_ESTABLISHED`` event — ``payload_json`` → ``engine_payload`` → stage 07 parse and
apply — with the stored body UNMODIFIED. The stored form of
a payload whose optional ``fair_value_contract_liability`` is unset carries ``null`` (04 §16.3: `O`,
only with reason ``BUSINESS_COMBINATION``); stage 07 reads that specific null as the absent member —
never as 0 — and establishes the opening state. Retained: the IFRS15 business-combination
requirement (ENGINE_SPEC S07-R-08: a missing or null fair value is the ``fair_value`` finding), the
``member`` finding for a malformed non-null value, the payload boundary's non-negative Money and
reason rules, API-S-Money for the fair value itself, and an explicit zero as the value 0.

CPU only (no database). Fail-first on 7916266a: the present null was a ``member`` finding
(opening.py 254-258) and stage 07 returned without establishing the opening state.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest
from erev_api.domain.contracts.bundles import engine_payload
from erev_api.enums import ContractEventType
from erev_api.events import payloads
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput
from erev_engine.stages import s07_onboarding
from erev_engine.stages.s07_onboarding import opening
from erev_engine.stages.state import EventView, ObligationState, SegmentCause
from erev_engine.trace import TraceBuilder
from pydantic import ValidationError
from support.bundles import entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    contract_view,
    event_view,
    obligation,
    segment,
    usd,
)

OPENING = ContractEventType.OPENING_BALANCE_ESTABLISHED
INCEPTION = date(2025, 1, 1)
CUTOVER = date(2025, 12, 31)
OVERRIDES = [("onboarding.method", "CONTRACT", CONTRACT_KEY, "OPENING_BALANCES_AT_CUTOVER")]
# Version 2 carries exact 18-place values whose sum is the 240,000.00 transaction price exactly.
REVENUE_EXACT = "119999.876543210987654321"
REMAINING_EXACT = "120000.123456789012345679"


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _body(reason: str = "LEGACY_MIGRATION", *, version: int, **members: Any) -> dict[str, Any]:
    exact = version == 2
    row = {
        "obligation_key": "SUB-01",
        "delivered_quantity_cum": "0",
        "ssp_delivered_cum": "0",
        "remaining_quantity": "1",
        "remaining_ssp": "240000",
        "revenue_cum": _usd(REVENUE_EXACT if exact else "120000.00"),
        "billed_cum": _usd("240000.00"),
        "catch_up_cum": _usd("0.00"),
        "pre_standard_revenue_cum": _usd("0.00"),
        "remaining_allocation": _usd(REMAINING_EXACT if exact else "120000.00"),
        "remaining_billing": _usd("0.00"),
        "position_obligation": _usd("0.00"),
        "netting_reclass_amount": _usd("0.00"),
    }
    return {"reason": reason, "cutover_date": CUTOVER.isoformat(), "obligations": [row], **members}


def _stored(version: int, body: Mapping[str, Any]) -> dict[str, Any]:
    """The stored JSON body of the admitted payload, exactly as ``payload_json`` writes it."""
    model = (
        payloads.OpeningBalanceEstablishedV1.model_validate(body)
        if version == 1
        else payloads.parse_payload(OPENING, version, body)
    )
    return payloads.payload_json(model)


def _event(stored: Mapping[str, Any]) -> EventView:
    """The engine's view of the stored body through the bundle boundary — nothing dropped, nothing
    added."""
    return event_view(CONTRACT_KEY, 3, OPENING.value, CUTOVER, engine_payload(stored))


def _calendar() -> EntityInput:
    return entity(start=INCEPTION, months=24, books=("ASC606", "IFRS15"))


def _obligation() -> ObligationState:
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=INCEPTION, end=date(2026, 12, 31)
    )
    return obligation("SUB-01", [subscription], convention="MONTHLY_EVEN")


@pytest.mark.parametrize("version", [1, 2])
def test_unmodified_stored_body_with_null_fair_value_establishes_the_opening(version: int) -> None:
    """Both a stored version-1 body and a new version-2 body: the unset optional member is stored as
    ``null``; parse reads it as absent (no finding, ``fair_value`` None) and apply establishes the
    opening segment. Posted amounts still round to the minor unit (S07-R-04) — only admission and
    transport are exact."""
    stored = _stored(version, _body(version=version))
    assert "fair_value_contract_liability" in stored
    assert stored["fair_value_contract_liability"] is None
    assert stored["migration_batch_id"] is None
    ev = _event(stored)
    assert ev.payload["fair_value_contract_liability"] is None  # present null, handed over as is
    parsed = opening.parse(ev)
    assert (parsed.findings, parsed.fair_value) == ((), None)
    revenue = Decimal(REVENUE_EXACT if version == 2 else "120000.00")
    assert parsed.rows["SUB-01"].value("revenue_cum") == Fraction(revenue)
    assert parsed.rows["SUB-01"].x_exact == Fraction(240000)

    ctx = book_context(_calendar(), overrides=OVERRIDES)
    st = allocated_state([_obligation()], events=[ev], inception=INCEPTION)
    after = s07_onboarding.apply(ctx, st, ev, TraceBuilder(engine_version=ENGINE_VERSION))
    assert after.findings == ()
    seg = after.obligations[0].segments[-1]
    assert (seg.cause, seg.effective_date, seg.event_key) == (
        SegmentCause.OPENING_BALANCE,
        CUTOVER,
        ev.event_key,
    )
    assert seg.x_exact == Fraction(240000)
    baseline = s07_onboarding.baseline_of(after.obligations[0])
    assert baseline is not None
    assert baseline.revenue_cum == usd("119999.88" if version == 2 else "120000.00")


def test_business_combination_null_fair_value_is_still_refused_under_ifrs15() -> None:
    """S07-R-08 retained: with reason BUSINESS_COMBINATION the IFRS15 book needs the
    acquisition-date fair value; a stored null is absence, and absence is the ``fair_value``
    finding — stage 07 returns without establishing the opening state."""
    stored = _stored(2, _body("BUSINESS_COMBINATION", version=2))
    assert stored["fair_value_contract_liability"] is None
    ev = _event(stored)
    parsed = opening.parse(ev)
    assert (parsed.findings, parsed.fair_value) == ((), None)
    ifrs = book_context(_calendar(), book_code="IFRS15", overrides=OVERRIDES)
    contracts = [contract_view(CONTRACT_KEY, statuses=((INCEPTION, "ACTIVE"),), book_code="IFRS15")]
    st = allocated_state([_obligation()], contracts=contracts, events=[ev], inception=INCEPTION)
    after = s07_onboarding.apply(ifrs, st, ev, TraceBuilder(engine_version=ENGINE_VERSION))
    assert after.obligations == st.obligations
    (finding,) = after.findings
    assert (finding.code, finding.detail["check"], finding.subject_key) == (
        "OPENING_BALANCE_INCONSISTENT",
        "fair_value",
        CONTRACT_KEY,
    )


def test_malformed_non_null_fair_value_is_still_a_member_finding() -> None:
    """Only the specific null is absence: a present non-null value that is not a number stays the
    ``member`` finding (never a value, never dropped)."""
    base = engine_payload(_stored(2, _body("BUSINESS_COMBINATION", version=2)))
    for malformed in ("abc", "", True, [1], {"currency": "USD"}):
        ev = event_view(
            CONTRACT_KEY,
            3,
            OPENING.value,
            CUTOVER,
            {**base, "fair_value_contract_liability": malformed},
        )
        parsed = opening.parse(ev)
        assert parsed.fair_value is None, repr(malformed)
        assert [(f.detail["check"], f.detail["member"]) for f in parsed.findings] == [
            ("member", "fair_value_contract_liability")
        ], repr(malformed)


def test_explicit_zero_fair_value_is_the_value_zero_not_absence() -> None:
    """An explicit ``0.00`` is the value 0: stored as the Money object, parsed as ``Fraction(0)``,
    and the IFRS15 requirement is met (no ``fair_value`` finding)."""
    body = _body("BUSINESS_COMBINATION", version=2, fair_value_contract_liability=_usd("0.00"))
    stored = _stored(2, body)
    assert stored["fair_value_contract_liability"] == _usd("0.00")
    ev = _event(stored)
    parsed = opening.parse(ev)
    assert (parsed.findings, parsed.fair_value) == ((), Fraction(0))
    ifrs = book_context(_calendar(), book_code="IFRS15", overrides=OVERRIDES)
    contracts = [contract_view(CONTRACT_KEY, statuses=((INCEPTION, "ACTIVE"),), book_code="IFRS15")]
    st = allocated_state([_obligation()], contracts=contracts, events=[ev], inception=INCEPTION)
    assert [f.detail["check"] for f in opening.consistency(ifrs, st, ev, parsed)] == []


def test_payload_boundary_refusals_are_unchanged() -> None:
    """The fair value stays API-S-Money and non-negative, and needs reason BUSINESS_COMBINATION —
    nothing widened, no zero fallback."""
    with pytest.raises(ValidationError):
        payloads.parse_payload(
            OPENING,
            2,
            _body("BUSINESS_COMBINATION", version=2, fair_value_contract_liability=_usd("-1.00")),
        )
    with pytest.raises(ValidationError):
        payloads.parse_payload(
            OPENING,
            2,
            _body("BUSINESS_COMBINATION", version=2, fair_value_contract_liability=_usd("1.00001")),
        )
    with pytest.raises(ValidationError, match="BUSINESS_COMBINATION"):
        payloads.parse_payload(
            OPENING, 2, _body(version=2, fair_value_contract_liability=_usd("1.00"))
        )

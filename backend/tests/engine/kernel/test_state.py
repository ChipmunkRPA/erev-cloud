"""Shared stage state (ENGINE_SPEC CV-17, CV-43, S01-R-16, S01-R-18; ENGINE_SPEC_B §0.5; EKC-6)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine.bundle import EstimateVersionInput, ResolvedPolicyInput
from erev_engine.stages.state import (
    EstimatePin,
    EstimatePins,
    EventView,
    Finding,
    LedgerPoint,
    LedgerStep,
    PolicyResolver,
    ProgressBase,
    QuantityLedger,
)
from erev_engine.trace import SourceRef


def _policy(
    code: str, scope: str, subject_key: str, value: str, *, pin: str = "K", level: str = "T"
) -> ResolvedPolicyInput:
    return ResolvedPolicyInput(code, scope, subject_key, value, level, "REG@v1", pin)


def _sorted(*policies: ResolvedPolicyInput) -> tuple[ResolvedPolicyInput, ...]:
    return tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key)))


def _event(key: str, on: date, seq: int) -> EventView:
    return EventView(
        event_key=key,
        contract_key="K-01",
        event_type="DELIVERY_RECORDED",
        effective_date=on,
        record_seq=seq,
        recorded_at=datetime(2026, 3, 1, tzinfo=UTC),
        obligation_subject_keys=("K-01/POB-01",),
        payload={},
        is_new=True,
        source=SourceRef("contract_event", key),
    )


def test_policy_resolver_scopes() -> None:
    policies = _sorted(
        _policy("mod.ssp_basis", "GROUP", "", "GROUP-VALUE"),
        _policy("mod.ssp_basis", "ENTITY", "US01", "ENTITY-VALUE", level="E"),
        _policy("mod.ssp_basis", "CONTRACT", "K-01", "CONTRACT-VALUE", level="C"),
        _policy("mod.ssp_basis", "OBLIGATION", "K-01/POB-02", "OBLIGATION-VALUE", level="O"),
        _policy("late_events.posting", "PERIOD", "US01@FY2026-P02", "P02-VALUE", pin="P"),
        _policy("late_events.posting", "PERIOD", "US01@FY2026-P03", "P03-VALUE", pin="P"),
    )
    resolver = PolicyResolver(policies)
    code = "mod.ssp_basis"
    assert resolver.value(code, contract="K-01", obligation="K-01/POB-02") == "OBLIGATION-VALUE"
    assert resolver.value(code, contract="K-01", obligation="K-01/POB-01") == "CONTRACT-VALUE"
    assert resolver.value(code, contract="K-02", obligation="K-02/POB-01", entity="US01") == (
        "ENTITY-VALUE"
    )
    assert resolver.value(code, contract="K-02", obligation="K-02/POB-01") == "GROUP-VALUE"
    assert resolver.value(code) == "GROUP-VALUE"
    assert resolver.resolved(code, contract="K-01").level == "C"
    assert resolver.value("late_events.posting", entity="US01", period="FY2026-P03") == "P03-VALUE"
    with pytest.raises(ValueError, match="no value"):
        resolver.value("late_events.posting", entity="US01", period="FY2026-P04")
    with pytest.raises(ValueError, match="period-scoped"):
        resolver.value("late_events.posting", contract="K-01", entity="US01")
    with pytest.raises(ValueError, match="absent"):
        resolver.value("rounding.schedule")
    with pytest.raises(ValueError, match="rounding.schedule"):
        resolver.require(["mod.ssp_basis", "rounding.schedule"])
    resolver.require(["mod.ssp_basis", "late_events.posting"])
    assert resolver.all() == policies


@pytest.mark.parametrize(
    "policies",
    [
        (  # unsorted
            _policy("b.key", "GROUP", "", "X"),
            _policy("a.key", "GROUP", "", "X"),
        ),
        (_policy("a.key", "PERIOD", "US01@FY2026-P01", "X"),),  # PERIOD scope with pin K
        (_policy("a.key", "GROUP", "", "X", pin="P"),),  # pin P outside the PERIOD scope
        (_policy("a.key", "GROUP", "K-01", "X"),),  # GROUP with a subject key
        (_policy("a.key", "CONTRACT", "", "X"),),  # empty subject key outside GROUP
        (_policy("a.key", "PRODUCT", "SKU-1", "X"),),  # unknown scope
        (
            _policy("a.key", "GROUP", "", "X"),
            _policy("a.key", "PERIOD", "US01@FY2026-P01", "Y", pin="P"),
        ),  # mixed pins
    ],
)
def test_policy_resolver_rejects_malformed_values(
    policies: tuple[ResolvedPolicyInput, ...],
) -> None:
    with pytest.raises(ValueError):
        PolicyResolver(policies)


def _point(delivered: int, key: str) -> LedgerPoint:
    zero = LedgerPoint.zero()
    return LedgerPoint(Fraction(delivered), *(zero.returned_cum,) * 9, last_event_key=key)


def test_quantity_ledger_at() -> None:
    first = _event("K-01/EV-000002", date(2026, 1, 10), 1)
    second = _event("K-01/EV-000003", date(2026, 2, 10), 3)
    ledger = QuantityLedger(
        {
            "K-01/POB-01": (
                LedgerStep(first.order_key, _point(2, first.event_key)),
                LedgerStep(second.order_key, _point(5, second.event_key)),
            )
        }
    )
    subject = "K-01/POB-01"
    assert ledger.at(subject).delivered_cum == 5
    assert ledger.at(subject, before=second).delivered_cum == 2
    assert ledger.at(subject, before=first) == LedgerPoint.zero()
    assert ledger.at(subject, on=date(2026, 1, 9)) == LedgerPoint.zero()
    assert ledger.at(subject, on=date(2026, 1, 31)).last_event_key == "K-01/EV-000002"
    assert ledger.at(subject, on=date(2026, 2, 10)).delivered_cum == 5
    assert ledger.at("K-01/POB-99") == LedgerPoint.zero()
    with pytest.raises(ValueError):
        ledger.at(subject, before=first, on=date(2026, 1, 31))
    with pytest.raises(ValueError):
        QuantityLedger({subject: tuple(reversed(ledger.steps[subject]))})
    assert ProgressBase.zero() == ProgressBase(Fraction(0), Fraction(0), Fraction(0), None)


def _version(no: int, effective: date) -> EstimateVersionInput:
    return EstimateVersionInput(
        estimate_key="K-01/VC-1",
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code="VC-1",
        method="MOST_LIKELY_AMOUNT",
        vc_element_type=None,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=None,
        version_key=f"K-01/VC-1@v{no}",
        version_no=no,
        status="APPROVED",
        effective_date=effective,
        scenarios=(),
        parameters={},
        unconstrained_amount=Decimal("1000.00"),
        most_conservative_amount=None,
        constrained_amount=Decimal("800.00"),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None if no == 1 else f"K-01/VC-1@v{no - 1}",
        judgement_key=None,
        content_sha256="0" * 64,
    )


def test_estimate_pins_pin() -> None:
    applied_v1 = _event("K-01/EV-000004", date(2026, 1, 5), 4)
    applied_v2 = _event("K-01/EV-000007", date(2026, 3, 5), 7)
    v1, v2 = _version(1, date(2026, 1, 1)), _version(2, date(2026, 3, 1))
    pins = EstimatePins(
        {
            "K-01/VC-1": (
                EstimatePin(v1, applied_v1.order_key),
                EstimatePin(v2, applied_v2.order_key),
            )
        }
    )
    assert pins.pin("K-01/VC-1", date(2026, 2, 1)) == v1
    assert pins.pin("K-01/VC-1", date(2026, 3, 31)) == v2
    assert pins.pin("K-01/VC-1", date(2026, 3, 31), before=applied_v2) == v1
    assert pins.pin("K-01/VC-1", date(2025, 12, 31)) is None
    assert pins.pin("K-01/VC-9", date(2026, 3, 31)) is None
    # Equal effective dates: the greater version number wins.
    v3 = _version(3, date(2026, 3, 1))
    later = _event("K-01/EV-000009", date(2026, 3, 20), 9)
    tied = EstimatePins(
        {"K-01/VC-1": (EstimatePin(v2, applied_v2.order_key), EstimatePin(v3, later.order_key))}
    )
    assert tied.pin("K-01/VC-1", date(2026, 3, 31)) == v3


def test_finding_order_cv_43() -> None:
    findings = [
        Finding("SSP_KEY_NOT_FOUND", "ERROR", "K-01/POB-02", {"sku": "B"}, 5, None),
        Finding("SSP_KEY_NOT_FOUND", "ERROR", "K-01/POB-02", {"sku": "A"}, 5, None),
        Finding("PRODUCT_UNMAPPED", "ERROR", "K-01/POB-03", {}, 3, None),
        Finding("EVENT_BEFORE_INCEPTION", "ERROR", None, {}, 1, "K-01/EV-000002"),
        Finding("EVENT_BEFORE_INCEPTION", "ERROR", None, {}, 1, "K-01/EV-000001"),
    ]
    ordered = sorted(findings, key=Finding.sort_key)
    assert [(f.stage, f.code, f.event_key, dict(f.detail)) for f in ordered] == [
        (1, "EVENT_BEFORE_INCEPTION", "K-01/EV-000001", {}),
        (1, "EVENT_BEFORE_INCEPTION", "K-01/EV-000002", {}),
        (3, "PRODUCT_UNMAPPED", None, {}),
        (5, "SSP_KEY_NOT_FOUND", None, {"sku": "A"}),
        (5, "SSP_KEY_NOT_FOUND", None, {"sku": "B"}),
    ]


def test_contract_period_exception_is_isolated_and_falls_back_to_entity() -> None:
    from erev_engine.bundle import contract_period_key

    code = "fx.cl_historical_layering"
    resolver = PolicyResolver(
        _sorted(
            _policy(code, "PERIOD", "US@SEP", "ENABLED", pin="P"),
            _policy(code, "PERIOD", "US@OCT", "ENABLED", pin="P"),
            _policy(code, "PERIOD", "UK@SEP", "ENABLED", pin="P"),
            _policy(
                code,
                "CONTRACT_PERIOD",
                contract_period_key("A", "US", "SEP"),
                "DISABLED_REMEASURE_AS_MONETARY",
                pin="P",
                level="C",
            ),
        )
    )
    assert (
        resolver.value(code, contract="A", entity="US", period="SEP")
        == "DISABLED_REMEASURE_AS_MONETARY"
    )
    for contract, entity, period in [("B", "US", "SEP"), ("A", "UK", "SEP"), ("A", "US", "OCT")]:
        assert resolver.value(code, contract=contract, entity=entity, period=period) == "ENABLED"
    assert resolver.value(code, entity="US", period="SEP") == "ENABLED"
    with pytest.raises(ValueError, match="period-scoped"):
        resolver.value(code, contract="A")
    assert contract_period_key("A@B", "C", "D") != contract_period_key("A", "B@C", "D")
    assert contract_period_key('A", "B', "C", "D") != contract_period_key("A", 'B", "C', "D")


@pytest.mark.parametrize("pin,level", [("K", "C"), ("P", "E")])
def test_contract_period_scope_rejects_wrong_pin_or_authority(pin: str, level: str) -> None:
    with pytest.raises(ValueError):
        PolicyResolver(
            (
                _policy(
                    "fx.cl_historical_layering",
                    "CONTRACT_PERIOD",
                    "scope",
                    "ENABLED",
                    pin=pin,
                    level=level,
                ),
            )
        )

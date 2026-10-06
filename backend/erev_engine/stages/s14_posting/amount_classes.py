"""Stage 14 amount classes (05 RCP-07; ENGINE_SPEC_B Table 14-A; BUILD_SPEC END-4).

Private to stage 14 (DG-ENG-07); the package exports the constant. Every amount the engine produces
is classified once: **event-driven** (``EVENT``) amounts change only when an event is appended and
post at compute; **time-driven** (``TIME``) amounts change with the passage of periods and post in
the named close-run pass (05 RCP-07, RCP-08). ``AMOUNT_CLASSES`` maps each part of ``JET_PARTS``
that produces amounts to its drivers: the table 2.3-B triggers of the part, plus the drivers Table
14-A names in the class column (proportional amortisation over event-driven revenue, the
recognition of a monetary liability, the POL-163 settlement at relief). ``amount_class`` also
consults the parts that post through a target (S14-R-02, S14-R-03). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s14_posting.templates import (
    CLOSE_RUN_PASSES,
    JET_02_TRIGGERS,
    JET_PARTS,
    NOT_A_CONTRACT_EVENT,
)

__all__ = ["AMOUNT_CLASSES", "EVENT", "TIME", "AmountClass", "amount_class"]

EVENT: Final = "EVENT"
TIME: Final = "TIME"


@dataclass(frozen=True, slots=True)
class AmountClass:
    """The class of an amount and, for a ``TIME`` amount, the close-run pass that posts it."""

    amount_class: str  # EVENT | TIME (RCP-07)
    posting_pass: str | None  # E-31 CLOSE_RELEASE | FX_REMEASUREMENT | NETTING_RECLASS

    def __post_init__(self) -> None:
        if self.amount_class == EVENT and self.posting_pass is not None:
            raise ValueError("an EVENT amount posts at compute, in no close-run pass")
        if self.amount_class == TIME and self.posting_pass not in CLOSE_RUN_PASSES:
            raise ValueError("a TIME amount names its close-run pass (RCP-08)")
        if self.amount_class not in (EVENT, TIME):
            raise ValueError(f"unknown amount class {self.amount_class!r}")


_EVENT: Final = AmountClass(EVENT, None)
_JET_02_EVENTS: Final = tuple(trigger for trigger in JET_02_TRIGGERS if trigger != "CLOSE_RELEASE")


def _classes(
    events: Iterable[str] = (), times: Mapping[str, str] | None = None
) -> Mapping[str, AmountClass]:
    drivers: dict[str, AmountClass] = dict.fromkeys(events, _EVENT)
    for driver, posting_pass in (times or {}).items():
        if driver in drivers:
            raise ValueError(f"driver {driver} is both EVENT and TIME")
        drivers[driver] = AmountClass(TIME, posting_pass)
    return MappingProxyType(dict(sorted(drivers.items())))


def _release(*drivers: str) -> Mapping[str, str]:
    return dict.fromkeys(drivers, "CLOSE_RELEASE")


_REVENUE: Final = _classes(_JET_02_EVENTS, _release("CLOSE_RELEASE"))
_AMENDMENT: Final = _classes(("CONTRACT_AMENDED", "CONTRACT_TERMINATED"))
_PROMISE: Final = _classes(("CONTRACT_ACTIVATED", "CONTRACT_AMENDED"))
# 05 RCP-07 rev 1.3: JET-10d differences at the recognition of a monetary liability are EVENT.
_RECOGNITION: Final = (
    "ESTIMATE_CHANGED",
    "USAGE_REPORTED",
    "BILLING_RECORDED",
    "DELIVERY_RECORDED",
    "PAYMENT_RECEIVED",
    "CONTRACT_ACTIVATED",
)
_SETTLEMENT: Final = (
    "CREDIT_MEMO_RECORDED",
    "RETURN_RECORDED",
    "CONTRACT_CRITERIA_MET",
    "CONTRACT_TERMINATED",
    NOT_A_CONTRACT_EVENT,
)
_FX_PERIOD_END: Final = MappingProxyType({"FX_REMEASUREMENT": "FX_REMEASUREMENT"})

AMOUNT_CLASSES: Final[Mapping[str, Mapping[str, AmountClass]]] = MappingProxyType(
    {
        "JET-01b receipt": _classes(("PAYMENT_RECEIVED", "BILLING_RECORDED")),
        "JET-01b criteria met": _classes(("CONTRACT_CRITERIA_MET",)),
        "JET-01b 25-7 revenue": _classes((NOT_A_CONTRACT_EVENT,), _release("CLOSE_RELEASE")),
        "JET-01b refund": _classes(("CONTRACT_TERMINATED",)),
        # NORMAL amounts of deterministic components post in CLOSE_RELEASE; events at compute.
        "JET-02 principal": _REVENUE,
        "JET-02 agent": _REVENUE,
        "JET-03 invoice": _classes(("BILLING_RECORDED",)),
        "JET-03 credit memo": _classes(("CREDIT_MEMO_RECORDED",)),
        # Return-window expiry is time-driven (L1-3-Q-22 EXPIRY_AMOUNT_CLASS).
        "JET-04a": _classes(("ESTIMATE_CHANGED", "USAGE_REPORTED"), _release("CLOSE_RELEASE")),
        "JET-04b": _classes(
            ("ESTIMATE_CHANGED", "USAGE_REPORTED", "BILLING_RECORDED", "CREDIT_MEMO_RECORDED"),
            _release("CLOSE_RELEASE"),
        ),
        "JET-04c": _classes(("ESTIMATE_CHANGED", "BILLING_RECORDED", "CREDIT_MEMO_RECORDED")),
        "JET-05a": _AMENDMENT,
        "JET-05b": _AMENDMENT,
        "JET-05c": _AMENDMENT,
        "JET-06 reclass": _classes((), {"NETTING_RECLASS": "NETTING_RECLASS"}),
        "JET-06 reversal": _classes((), {"NETTING_RECLASS": "NETTING_RECLASS"}),
        "JET-07a": _classes(("DELIVERY_RECORDED",)),
        "JET-07b": _classes(("DELIVERY_RECORDED", "RETURN_RECORDED")),
        # EVENT at transfer and return; TIME at period end and expiry.
        "JET-07c": _classes(
            ("DELIVERY_RECORDED", "ESTIMATE_CHANGED", "RETURN_RECORDED"),
            _release("CLOSE_RELEASE"),
        ),
        "JET-07d": _classes(("RETURN_RECORDED",)),
        "JET-08 expiry": _classes(("MATERIAL_RIGHT_EXPIRED",)),
        "JET-09a": _classes(("COST_INCURRED",)),
        "JET-09a′": _classes(("COST_INCURRED",)),
        # TIME for STRAIGHT_LINE; EVENT for proportional amortisation over event-driven revenue.
        "JET-09b": _classes(_JET_02_EVENTS, _release("CLOSE_RELEASE")),
        "JET-09c": _classes((), _release("CLOSE_RELEASE")),
        "JET-09d": _classes((), _release("CLOSE_RELEASE")),
        "JET-09e": _classes(("CONTRACT_TERMINATED",)),
        "JET-09f": _classes(("COST_INCURRED",)),
        # TIME at period end; EVENT for the settlement at billing or payment.
        "JET-10a": _classes(("BILLING_RECORDED", "PAYMENT_RECEIVED"), _FX_PERIOD_END),
        "JET-10a′": _classes((), _FX_PERIOD_END),
        # POL-163 override: the relief that empties a layer settles it (L2-5-Q-16).
        "JET-10b": _classes(_JET_02_EVENTS, {**_FX_PERIOD_END, **_release("CLOSE_RELEASE")}),
        "JET-10c": _classes(("CREDIT_MEMO_RECORDED",)),
        "JET-10d": _classes(
            (*_SETTLEMENT, *_RECOGNITION, "CONTRACT_AMENDED"),
            {**_FX_PERIOD_END, **_release("CLOSE_RELEASE")},
        ),
        # Financing interest and loss provisions are time-driven whatever marks the group dirty.
        "JET-11a": _classes((), _release(*JET_02_TRIGGERS)),
        "JET-11b": _classes((), _release(*JET_02_TRIGGERS)),
        "JET-12": _classes((), _release("ESTIMATE_CHANGED", "COST_INCURRED", "CLOSE_RELEASE")),
        "JET-13 contracting": _REVENUE,
        "JET-13 performing": _REVENUE,
        "JET-14 promised": _PROMISE,
        "JET-14 after revenue": _PROMISE,
        "JET-14 release": _classes(("BILLING_RECORDED", *JET_02_TRIGGERS)),
        "JET-14 share-based": _classes(("ESTIMATE_CHANGED",)),
        "JET-15": _classes(("PRE_STANDARD_REVENUE_RECORDED",)),
        "JET-16 accrual": _classes(("DELIVERY_RECORDED",)),
        "JET-16 claim release": _classes(("COST_INCURRED",)),
        "JET-17 unconditional": _classes(JET_02_TRIGGERS),
        "JET-17 receipt": _classes(("PAYMENT_RECEIVED",)),
    }
)


def amount_class(part: str, driver: str) -> AmountClass:
    """The class of an amount of ``part`` driven by ``driver``; parts posting through it count."""
    found: set[AmountClass] = set()
    own = AMOUNT_CLASSES.get(part, {})
    if driver in own:
        found.add(own[driver])
    for name, spec in JET_PARTS.items():
        if spec.through == part and driver in AMOUNT_CLASSES.get(name, {}):
            found.add(AMOUNT_CLASSES[name][driver])
    if len(found) != 1:
        raise ValueError(f"part {part} has no single amount class for driver {driver} (RCP-07)")
    return found.pop()

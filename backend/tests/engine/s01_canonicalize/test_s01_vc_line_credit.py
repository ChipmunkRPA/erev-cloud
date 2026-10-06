"""Stage 01 re-check of ``REFUND_EXCEEDS_BILLED`` over a parity VC line (ENGINE_SPEC S01-R-16,
CV-44, S03-R-18; 04 table 15.4-A #25 "a credit would make non-VC cumulative billing negative";
DEVIATIONS §5 #25, DEV-021, DEV-022 "VC lines excluded from billing checks"; BUILD_SPEC GPA-2).

Golden step 06 credits Contract 4 ``VC #1`` (stratification ``VC``, booked price −200.00) with
100.00 while nothing was billed on that line. The import accepts the row, because the code covers
non-VC billing only, and stage 01 re-checks the same code over the stream (CV-44). Before the fix
the group was quarantined with ``REFUND_EXCEEDS_BILLED`` on ``Contract 4/VC %231``, so no version
of step 06 existed and ``contract_position::rollforward-06-Contract4`` read the step 05 figures.

Bundles come from ``support.bundles`` (DG-ENG-11); no database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EventInput, InputBundle
from erev_engine.stages import s01_canonicalize
from erev_engine.stages.state import CanonicalBundle
from erev_engine.trace import TraceBuilder
from support import bundles

CONTRACT = "Contract 4"
INCEPTION = date(2023, 1, 1)
LINE_END = date(2023, 12, 31)
MARCH_END = date(2023, 3, 31)
PARITY = "LEGACY_PARITY"
# Contract 4 of the golden contract setup (step 03): key, product, quantity, price, stratification.
LINES = (
    ("POB #1", "Hardware 1", "8", "600.00", "Hardware 1"),
    ("POB #2", "Software 1", "4", "400.00", "Software 1"),
    ("POB #3", "Consulting 1", "1", "150.00", "Consulting 1"),
    ("VC #1", "Variable Consideration", "1", "-200.00", "VC"),
)
POB_2 = "Contract 4/POB %232"
VC_1 = "Contract 4/VC %231"


def booking() -> EventInput:
    lines = [
        {
            **bundles.booking_line(
                key,
                product_code=product,
                quantity=quantity,
                total_price=price,
                start=INCEPTION,
                end=LINE_END,
            ),
            "stratification": stratification,
        }
        for key, product, quantity, price, stratification in LINES
    ]
    return bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=[key for key, *_ in LINES],
    )


def billing(stream: int, obligation: str, amount: str) -> EventInput:
    payload = {
        "invoice_number": f"INV-{stream}",
        "line_external_id": f"INV-{stream}",
        "obligation_key": obligation,
        "amount": Decimal(amount),
        "issue_date": MARCH_END,
    }
    return bundles.event(
        CONTRACT, stream, "BILLING_RECORDED", MARCH_END, payload, obligation_keys=[obligation]
    )


def credit(stream: int, obligation: str | None, amount: str) -> EventInput:
    payload: dict[str, object] = {
        "credit_memo_number": f"CM-{stream}",
        "amount": Decimal(amount),
        "issue_date": MARCH_END,
    }
    if obligation is not None:
        payload["obligation_key"] = obligation
    keys = [] if obligation is None else [obligation]
    return bundles.event(
        CONTRACT, stream, "CREDIT_MEMO_RECORDED", MARCH_END, payload, obligation_keys=keys
    )


def delivery(stream: int, obligation: str, quantity: str) -> EventInput:
    payload = {"obligation_key": obligation, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return bundles.event(
        CONTRACT, stream, "DELIVERY_RECORDED", MARCH_END, payload, obligation_keys=[obligation]
    )


def bundle(*events: EventInput, preset: str = PARITY) -> InputBundle:
    calendar = bundles.entity(start=date(2023, 1, 1), months=24)
    headers = (bundles.contract(CONTRACT, inception=INCEPTION),)
    products = [bundles.product(product) for _, product, *_ in LINES]
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2024, 12, 31, 23, tzinfo=UTC),
        tenant_preset=preset,
        currencies=bundles.currencies("USD"),
        books=(bundles.book(entity=calendar),),
        entities=(calendar,),
        group=dataclasses.replace(
            bundles.group(headers, products=products), transaction_currency="USD"
        ),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def run(value: InputBundle) -> CanonicalBundle:
    return s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))


def _findings(cb: CanonicalBundle) -> list[tuple[str, str, str | None]]:
    return [(f.code, f.subject_key, f.event_key) for f in cb.findings]


def test_s01_r16_credit_on_a_parity_vc_line_raises_no_refund_finding() -> None:
    # Golden step 06, Contract 4: POB #2 delivered 1 and billed 200.00; VC #1 delivered 0.5 and
    # credited 100.00 with nothing billed on it.
    events = (
        booking(),
        delivery(2, "POB #2", "1"),
        billing(3, "POB #2", "200.00"),
        delivery(4, "VC #1", "0.5"),
        credit(5, "VC #1", "100.00"),
    )
    cb = run(bundle(*events))
    assert _findings(cb) == []
    vc = cb.ledger.at(VC_1)
    assert (vc.delivered_cum, vc.billed_cum, vc.credited_cum) == (Fraction(1, 2), 0, 100)
    # An unreferenced credit draws on non-VC billing only: 200.00 billed on POB #2, so a credit of
    # 200.00 is covered although VC #1 was credited 100.00.
    covered = run(bundle(*events, credit(6, None, "200.00")))
    assert _findings(covered) == []
    exceeding = run(bundle(*events, credit(6, None, "200.01")))
    assert _findings(exceeding) == [("REFUND_EXCEEDS_BILLED", CONTRACT, "Contract 4/EV-000006")]


def test_s01_r16_non_vc_credit_still_raises_under_the_parity_preset() -> None:
    events = (booking(), billing(2, "POB #2", "100.00"), credit(3, "POB #2", "150.00"))
    cb = run(bundle(*events))
    assert _findings(cb) == [("REFUND_EXCEEDS_BILLED", POB_2, "Contract 4/EV-000003")]
    assert cb.findings[0].detail == {
        "billed": "100",
        "credited": "150",
        "event_key": "Contract 4/EV-000003",
    }


def test_s01_r16_vc_stratification_outside_the_parity_preset_is_checked() -> None:
    # S03-R-18 gives stratification VC the LEGACY-VC template under the parity preset only.
    cb = run(bundle(booking(), credit(2, "VC #1", "100.00"), preset="DEFAULT"))
    assert _findings(cb) == [("REFUND_EXCEEDS_BILLED", VC_1, "Contract 4/EV-000002")]

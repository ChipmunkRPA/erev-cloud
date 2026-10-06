"""EX-01-A: the ledger after a legacy progress upload (ENGINE_SPEC §1.8; S01-INV-03; ENA-1).

The nine events of the worked example, effective on the upload date 2023-01-31, follow the
booking of Contract 1 from the golden contract setup. The recognised figures are EX-08-A.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EventInput, InputBundle
from erev_engine.stages import s01_canonicalize
from erev_engine.trace import TraceBuilder
from support import bundles

CONTRACT = "Contract 1"
INCEPTION = date(2023, 1, 1)
UPLOAD = date(2023, 1, 31)
LINES = (
    ("POB #1", "Hardware 1", "5", "500.00"),
    ("POB #2", "Software 1", "2", "400.00"),
    ("POB #3", "Consulting 1", "1", "400.00"),
)


def _event(stream: int, event_type: str, payload: dict[str, object]) -> EventInput:
    obligation = payload["obligation_key"]
    assert isinstance(obligation, str)
    return bundles.event(
        CONTRACT, stream, event_type, UPLOAD, payload, obligation_keys=[obligation]
    )


def _progress(
    stream: int,
    obligation: str,
    delivery: str,
    *,
    billing: str | None = None,
    pre_standard: str | None = None,
    memo: str,
) -> list[EventInput]:
    events = [
        _event(
            stream,
            "DELIVERY_RECORDED",
            {"obligation_key": obligation, "quantity": Decimal(delivery), "trigger": "DELIVERY"},
        )
    ]
    reference = f"UPL-1:{CONTRACT}:{obligation}"
    if billing is not None:
        events.append(
            _event(
                stream + 1,
                "BILLING_RECORDED",
                {
                    "obligation_key": obligation,
                    "amount": Decimal(billing),
                    "invoice_number": reference,
                    "line_external_id": reference,
                    "issue_date": UPLOAD,
                },
            )
        )
    if pre_standard is not None:
        events.append(
            _event(
                stream + 1,
                "PRE_STANDARD_REVENUE_RECORDED",
                {"obligation_key": obligation, "amount": Decimal(pre_standard)},
            )
        )
    events.append(
        _event(stream + 2, "MEMO_UPDATED", {"obligation_key": obligation, "memo_1": memo})
    )
    return events


def _bundle() -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    lines = [
        bundles.booking_line(
            key,
            product_code=product,
            quantity=qty,
            total_price=price,
            start=INCEPTION,
            end=date(2023, 12, 31),
        )
        for key, product, qty, price in LINES
    ]
    booked = bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=[key for key, *_ in LINES],
    )
    activated = bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})
    progress = [
        *_progress(3, "POB #1", "2", billing="300.00", memo="Jan batch"),
        *_progress(6, "POB #2", "1", pre_standard="66.00", memo="Go-live"),
        *_progress(9, "POB #3", "0.5", pre_standard="88.00", memo="Phase 1"),
    ]
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2023, 2, 1, tzinfo=UTC),
        tenant_preset="LEGACY_PARITY",
        currencies=bundles.currencies("USD"),
        books=(bundles.book(preset="LEGACY_PARITY", entity=calendar),),
        entities=(calendar,),
        group=bundles.group((header,), products=[bundles.product(p) for _, p, *_ in LINES]),
        contracts=(header,),
        events=(booked, activated, *progress),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_ex_01_a_ledger() -> None:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(_bundle(), tb)
    progress = [view for view in cb.events if view.effective_date == UPLOAD]
    assert [(view.event_type, view.payload["obligation_key"]) for view in progress] == [
        ("DELIVERY_RECORDED", "POB #1"),
        ("BILLING_RECORDED", "POB #1"),
        ("MEMO_UPDATED", "POB #1"),
        ("DELIVERY_RECORDED", "POB #2"),
        ("PRE_STANDARD_REVENUE_RECORDED", "POB #2"),
        ("MEMO_UPDATED", "POB #2"),
        ("DELIVERY_RECORDED", "POB #3"),
        ("PRE_STANDARD_REVENUE_RECORDED", "POB #3"),
        ("MEMO_UPDATED", "POB #3"),
    ]
    assert cb.findings == () and cb.boundary_events == ()
    assert len(cb.measure_events) == 10  # activation and the nine progress events

    pob_1 = cb.ledger.at("Contract 1/POB %231")
    assert (pob_1.delivered_cum, pob_1.billed_cum) == (2, 300)
    assert cb.ledger.at("Contract 1/POB %232").delivered_cum == 1
    assert cb.ledger.at("Contract 1/POB %233").delivered_cum == Fraction(1, 2)
    # Memo and pre-standard revenue events do not move the ledger (S01-R-16).
    assert len(cb.ledger.steps["Contract 1/POB %231"]) == 2
    assert len(cb.ledger.steps["Contract 1/POB %232"]) == 1
    for steps in cb.ledger.steps.values():
        for step in steps:
            point = step.point
            assert point.delivered_cum >= point.returned_cum >= 0  # S01-INV-03
            assert point.billed_cum >= point.credited_cum >= 0

    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    assert nodes["delivered_quantity_cum:Contract 1/POB %233:-"].value == "0.5"
    assert nodes["delivered_quantity_cum:Contract 1/POB %231:-"].value == "2"

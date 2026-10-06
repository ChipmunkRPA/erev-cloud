"""Stage 05 SSP points under the parity preset (BUILD_SPEC ENA-10).

Legacy 01 §7.3 TC-setup-03 to 06 and CHK-035 run stages 01 to 05 over the golden SKU SSP book of
step 01 with a replaced booking; legacy 03 §3.1 TC-06 calls ``resolve_ssp`` on lines that stage 03
would refuse (negative and zero quantities). No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import InputBundle
from erev_engine.enums import BookCode
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import AllocatedState, BookContext, Finding, PolicyResolver
from erev_engine.trace import SourceRef, TraceBuilder, TraceNode
from support import bundles, golden_streams

LABEL = "2023-01-01"
INCEPTION = date(2023, 1, 1)
CONTRACT = "Contract 1"


def line(key: str, product: str, quantity: str, price: str) -> dict[str, object]:
    return {
        "obligation_key": key,
        "product_code": product,
        "stratification": product,
        "quantity": Decimal(quantity),
        "total_price": Decimal(price),
        "start_date": INCEPTION,
        "end_date": date(2023, 12, 31),
        "ssp_version_label": LABEL,
    }


def parity_bundle(*lines: dict[str, object]) -> InputBundle:
    """Golden Contract 1 with its booking replaced by ``lines`` (golden SSP book, parity)."""
    golden = golden_streams.stream(CONTRACT, "02")
    header = dataclasses.replace(golden.contracts[0], material_rights=())
    keys = [str(item["obligation_key"]) for item in lines]
    booked = bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": list(lines)}, obligation_keys=keys
    )
    replay = dataclasses.replace(
        golden, contracts=(header,), events=(booked,), estimate_versions=()
    )
    return replay.input_bundle(preset="LEGACY_PARITY")


def context(value: InputBundle) -> BookContext:
    book = value.books[0]
    return BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in value.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def fold(
    value: InputBundle,
) -> tuple[BookContext, PricedState, AllocatedState, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3)."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb)
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def selected_node(traced: dict[str, TraceNode], key: str) -> TraceNode:
    return traced[f"original_ssp_selected:{CONTRACT}/{key}:-"]


def test_tc_setup_03_hardware_in_range() -> None:
    ctx, priced, allocated, _ = fold(parity_bundle(line("POB-01", "Hardware 1", "5", "500")))
    (draft,) = priced.pob.obligations
    findings: list[Finding] = []
    ssp = s05_allocation.resolve_ssp(
        ctx,
        draft,
        draft.pricing_date,
        draft.stated_price,
        findings=findings,
        identified=priced.pob.identified,
    )
    assert findings == []
    assert ssp is not None
    assert (ssp.low, ssp.mid, ssp.high) == (Fraction("382.5"), 450, Fraction("517.5"))
    assert (ssp.selected, ssp.in_range, ssp.point_policy) == (500, True, "CONTRACT_PRICE")
    assert (ssp.book_code, ssp.version_label, ssp.method) == (
        "LEGACY-SKU-SSP",
        LABEL,
        "legacy_range",
    )
    assert allocated.obligations[0].ssp == ssp


def test_tc_setup_04_software_clamped_high() -> None:
    _, _, allocated, _ = fold(parity_bundle(line("POB-01", "Software 1", "2", "400")))
    ssp = allocated.obligations[0].ssp
    assert ssp is not None
    assert (ssp.low, ssp.high) == (272, 368)
    assert (ssp.selected, ssp.in_range, ssp.point_policy) == (368, False, "NEAREST_BOUND")


def test_tc_setup_05_hardware_clamped_low() -> None:
    _, _, allocated, _ = fold(parity_bundle(line("POB-01", "Hardware 1", "8", "600")))
    ssp = allocated.obligations[0].ssp
    assert ssp is not None
    assert (ssp.low, ssp.mid, ssp.high) == (612, 720, 828)
    assert (ssp.selected, ssp.in_range) == (612, False)


def test_tc_setup_06_prices_on_bounds_kept() -> None:
    value = parity_bundle(
        line("POB-01", "Hardware 1", "5", "517.5"), line("POB-02", "Software 1", "2", "272")
    )
    _, priced, allocated, traced = fold(value)
    assert allocated.findings == ()
    assert [ob.ssp.selected for ob in allocated.obligations if ob.ssp is not None] == [
        Fraction("517.5"),
        272,
    ]
    assert all(ob.ssp is not None and ob.ssp.in_range for ob in allocated.obligations)
    assert priced.tp.total.posted == 78_950
    assert traced[f"total_ssp:CG-{CONTRACT}:-"].value == "789.5"
    # A = P when TP = TSSP.
    assert [ob.original_allocation.a_posted for ob in allocated.obligations] == [51_750, 27_200]


def test_chk_035_legacy_range_points() -> None:
    cases = (
        (("Hardware 1", "5", "500"),),
        (("Software 1", "2", "400"),),
        (("Hardware 1", "8", "600"),),
        (("Hardware 1", "5", "517.5"), ("Software 1", "2", "272")),
    )
    values = []
    for case in cases:
        lines = [line(f"POB-{n:02d}", *row) for n, row in enumerate(case, start=1)]
        _, _, allocated, traced = fold(parity_bundle(*lines))
        assert allocated.findings == ()
        values.append(
            tuple(selected_node(traced, f"POB-{n:02d}").value for n in range(1, len(case) + 1))
        )
        node = selected_node(traced, "POB-01")
        assert node.formula_id == "ssp.point.v1"
        assert node.params["version_key"] == "LEGACY-SKU-SSP@v1"
        assert node.params["policy"] in ("CONTRACT_PRICE", "NEAREST_BOUND")
        (source,) = node.inputs
        assert isinstance(source, SourceRef) and source.ref_type == "ssp_entry"
    assert values == [("500",), ("368",), ("612",), ("517.5", "272")]


def test_tc_prospective_06_ssp_clamp_unit_cases() -> None:
    ctx, priced, _, _ = fold(parity_bundle(line("POB-01", "Hardware 1", "5", "500")))
    base = priced.pob.obligations[0].line
    rows = (
        ("Hardware 1", "-5", "-500", ("-517.5", "-382.5"), "-500"),
        ("Hardware 1", "2", "500", ("153", "207"), "207"),
        ("Consulting 1", "2", "300", ("300", "300"), "300"),
        ("Material Right - Services", "-1000", "0", ("-1000", "-1000"), "-1000"),
        ("Consulting 1", "5", "1000", ("750", "750"), "750"),
        ("Hardware 1", "0", "50", ("0", "0"), "0"),
    )
    for product, quantity, price, band, expected in rows:
        raw = dataclasses.replace(
            base,
            product_code=product,
            stratification=product,
            quantity=Fraction(quantity),
            stated_price=Fraction(price),
        )
        findings: list[Finding] = []
        ssp = s05_allocation.resolve_ssp(
            ctx,
            raw,
            raw.pricing_date,
            raw.stated_price,
            findings=findings,
            identified=priced.pob.identified,
        )
        assert findings == [], product
        assert ssp is not None
        assert (ssp.low, ssp.high) == (Fraction(band[0]), Fraction(band[1])), (product, quantity)
        assert ssp.selected == Fraction(expected), (product, quantity)

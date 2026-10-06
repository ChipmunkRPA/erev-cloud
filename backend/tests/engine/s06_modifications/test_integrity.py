"""Stage 06 modification integrity: S06-R-07 and 04 table 15.4-A codes (ENB-13; REQ-MOD-019).

``validate_modification`` returns ``CONTRACT_NOT_FOUND``, ``POB_NOT_FOUND``, ``MOD_DUPLICATE_KEY``,
``MOD_SIGN_MISMATCH`` and ``IMPORT_NO_DATA_ROWS`` (legacy 03 §7.3 TC-06, TC-10 to TC-12, TC-17 and
TC-20; legacy 04 §7.3 TC-RM-09, TC-RM-10 and TC-RM-14, fixed column). ``apply`` refuses a boundary
event naming an unknown contract or obligation, or a modification already applied, with
``EngineError("ENGINE_INVARIANT_VIOLATED")`` naming S06-R-07 (CV-44, CV-45; L3-2-Q-1).

The native tests fold with the stage 06 test helpers under ``DEFAULT`` and bind the §4.2 fake price
function; the template tests fold golden streams through 04.30 (golden step 07) with the real
stages 01 to 05. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import InputBundle, ModificationInput
from erev_engine.errors import EngineError
from erev_engine.stages import s06_modifications
from erev_engine.stages.s06_modifications import ModificationView
from erev_engine.stages.state import AllocatedState, BookContext, Finding
from erev_engine.trace import TraceBuilder
from support import bundles, golden_streams
from support.fold import book_context, fold_book, fold_inception
from test_s06_prospective import (
    END,
    INCEPTION,
    MOD_DATE,
    amended,
    booked,
    bundle,
    checked,
    chk_028,
    fold,
    mod_line,
    modification_input,
    obligation,
    point_entry,
    price_function,
    product,
    ssp_version,
    usd,
)
from test_tc_rm import amended as template_amended
from test_tc_rm import fold as template_fold
from test_tc_rm import template_line

MOD_08_15 = date(2023, 5, 15)


def codes(findings: Sequence[Finding]) -> list[tuple[str, str, int, str | None]]:
    return [(item.code, item.severity, item.stage, item.subject_key) for item in findings]


def template_modification(
    key: str, mode: str, lines: Sequence[Mapping[str, object]]
) -> ModificationInput:
    """A legacy template modification of ``mode`` on 2023-05-15 (LM-TPL-MOD-01 to 15)."""
    native = modification_input(key, MOD_08_15, lines, kind="QUANTITY_CHANGE")
    return dataclasses.replace(native, template_mode=mode, currency="USD")


def golden(
    contract: str, preset: str = "LEGACY_PARITY"
) -> tuple[BookContext, AllocatedState, InputBundle]:
    """Golden ``contract`` through 04.30 folded by stages 01 to 05. Under ``DEFAULT`` the golden
    products map to the seeded parity templates, as TC-RM-15 (L2-3-Q-11)."""
    value = golden_streams.stream(contract, "07").input_bundle(preset=preset)
    if preset == "DEFAULT":
        products = tuple(
            dataclasses.replace(
                item,
                default_template_code="LEGACY-DISTINCT"
                if item.distinctness_default == "distinct"
                else "LEGACY-NONDISTINCT",
            )
            if item.default_template_code is None
            else item
            for item in value.group.products
        )
        value = dataclasses.replace(
            value, group=dataclasses.replace(value.group, products=products)
        )
    return book_context(value, "ASC606"), fold_inception(value, "ASC606"), value


def validate(
    ctx: BookContext, st: AllocatedState, contract: str, modification: ModificationInput
) -> tuple[Finding, ...]:
    view = ModificationView.of(contract, modification)
    return s06_modifications.validate_modification(ctx, st, view)


# --- Native probes (legacy 03 §7.3 probe state; ``DEFAULT``) --------------------------------------

TREATMENTS_10 = {"POB-01": "PROSPECTIVE", "POB-02": "PROSPECTIVE", "POB-03": "PROSPECTIVE"}


def tc_10(*, applied_twice: bool = False) -> InputBundle:
    """K-01: two DAILY obligations over 2026 and 2027 (240,000.00 and 60,000.00); on 16 Sep 2026
    modification MOD-10 adds only POB-03 for 60,000.00 (legacy 03 probe P-01). With
    ``applied_twice`` a second ``CONTRACT_AMENDED`` carries MOD-10 again (probe P-19 re-upload)."""
    lines = [
        bundles.booking_line(
            "POB-01", product_code="SKU-SAAS", quantity="1", total_price="240000.00", end=END
        ),
        bundles.booking_line(
            "POB-02", product_code="SKU-SUPPORT", quantity="1", total_price="60000.00", end=END
        ),
    ]
    addon = mod_line("POB-03", "ADD", "SKU-SEATS", "1", "60000.00", start=MOD_DATE, end=END)
    modification = modification_input("MOD-10", MOD_DATE, [addon], kind="ADD_OBLIGATION")
    events = [booked(INCEPTION, *lines), amended(4, modification, TREATMENTS_10)]
    if applied_twice:
        events.append(amended(5, modification, TREATMENTS_10))
    return bundle(
        *events,
        products=[
            product("SKU-SAAS", "TPL-SAAS"),
            product("SKU-SEATS", "TPL-SAAS"),
            product("SKU-SUPPORT", "TPL-SAAS"),
        ],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "SKU-SAAS", "240000.00"),
                    point_entry("SSP-US@v1", "SKU-SUPPORT", "60000.00"),
                ],
                date(2025, 1, 1),
                date(2026, 8, 31),
            ),
            ssp_version(
                2,
                [
                    point_entry("SSP-US@v2", "SKU-SAAS", "155000.00"),
                    point_entry("SSP-US@v2", "SKU-SEATS", "77500.00"),
                    point_entry("SSP-US@v2", "SKU-SUPPORT", "38750.00"),
                ],
                date(2026, 9, 1),
            ),
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
    )


def test_tc_prospective_10_new_pob_versions_every_obligation() -> None:
    folded = fold(tc_10())
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("300000.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    # Legacy appended one row and did not re-version the existing obligations; the fixed engine
    # gives three obligation versions (S06-R-16).
    assert [ob.obligation_key for ob in after.obligations] == ["POB-01", "POB-02", "POB-03"]
    for ob in after.obligations:
        assert ob.last_modification_key == "MOD-10", ob.obligation_key
        assert ob.segments[-1].event_key == ev.event_key, ob.obligation_key
        assert ob.lineage_pre_modification == ("K-01/POB-01", "K-01/POB-02"), ob.obligation_key
    # Equal contract-level inputs: every share cites the one pool node with the same weights.
    pool = f"mod_pool@{ev.event_key}:K-01:-"
    shares = [nodes[f"mod_share@{ev.event_key}:{ob.subject_key}:-"] for ob in after.obligations]
    assert {share.inputs for share in shares} == {(pool,)}
    common = {
        tuple(sorted((name, value) for name, value in share.params.items() if name != "key"))
        for share in shares
    }
    assert len(common) == 1
    assert sum(ob.segments[-1].a_posted for ob in after.obligations) == usd("360000.00")
    assert after.tp_history[-1].allocation_basis.posted == usd("360000.00")


def test_tc_prospective_11_unknown_contract_rejected() -> None:
    folded = fold(tc_10())
    header = folded.state.contracts[0].header
    (finding,) = validate(folded.ctx, folded.state, "Contract Z", header.modifications[0])
    assert codes([finding]) == [("CONTRACT_NOT_FOUND", "ERROR", 6, "Contract Z")]
    assert (finding.detail["rule"], finding.detail["contract_key"]) == ("S06-R-07", "Contract Z")
    # Legacy created an orphan contract; the engine refuses such an event (TC-11 fixed).
    orphan = dataclasses.replace(
        folded.amended, contract_key="Contract Z", event_key="Contract Z/EV-000004"
    )
    with pytest.raises(EngineError) as raised:
        s06_modifications.apply(
            folded.ctx,
            folded.state,
            orphan,
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=folded.identified,
            price_at=price_function("300000.00"),
        )
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert (raised.value.detail["rule"], raised.value.detail["code"]) == (
        "S06-R-07",
        "CONTRACT_NOT_FOUND",
    )


def test_tc_rm_14_unknown_contract_rejected() -> None:
    ctx, st, value = golden("Contract 2")
    row = template_line(value, "POB #1", "2", "180")  # the Contract 2 row, named for Contract 9
    modification = template_modification("MOD-RM14", "retrospective", [row])
    assert codes(validate(ctx, st, "Contract 9", modification)) == [
        ("CONTRACT_NOT_FOUND", "ERROR", 6, "Contract 9")
    ]
    assert validate(ctx, st, "Contract 2", modification) == ()  # the same row on Contract 2


def test_tc_prospective_12_duplicate_lines_rejected() -> None:
    folded = fold(chk_028(mod_line("POB-01", "CHANGE", "SKU-P", "10", "950.00")))
    line = mod_line("POB-01", "CHANGE", "SKU-P", "10", "950.00")
    modification = modification_input(
        "MOD-12", date(2026, 6, 15), [line, line], kind="QUANTITY_CHANGE"
    )
    (finding,) = validate(folded.ctx, folded.state, "K-01", modification)
    assert codes([finding]) == [("MOD_DUPLICATE_KEY", "ERROR", 6, "K-01/POB-01")]
    assert (finding.detail["line_index"], finding.detail["first_line_index"]) == ("1", "0")
    assert finding.detail["product_code"] == "SKU-P"

    # A second CONTRACT_AMENDED carrying the applied MOD-10 (P-19 re-upload): legacy appended
    # duplicate rows. The engine refuses it when the event repeats or the stream carries it twice.
    folded = fold(tc_10())
    once = s06_modifications.apply(
        folded.ctx,
        folded.state,
        folded.amended,
        TraceBuilder(engine_version=ENGINE_VERSION),
        identified=folded.identified,
        price_at=price_function("300000.00"),
    )
    with pytest.raises(EngineError) as raised:
        s06_modifications.apply(
            folded.ctx,
            once,
            folded.amended,
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=folded.identified,
            price_at=price_function("300000.00"),
        )
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["rule"] == "S06-R-07"
    assert (raised.value.detail["code"], raised.value.detail["modification_key"]) == (
        "MOD_DUPLICATE_KEY",
        "MOD-10",
    )
    with pytest.raises(EngineError) as twice:
        fold_book(tc_10(applied_twice=True), "ASC606")
    assert (twice.value.detail["rule"], twice.value.detail["code"]) == (
        "S06-R-07",
        "MOD_DUPLICATE_KEY",
    )
    assert twice.value.detail["event_key"] == "K-01/EV-000005"


def test_tc_rm_10_duplicate_rows_rejected() -> None:
    ctx, st, value = golden("Contract 2")
    row = template_line(value, "POB #1", "1", "200")
    modification = template_modification("MOD-RM10", "retrospective", [row, row])
    assert codes(validate(ctx, st, "Contract 2", modification)) == [
        ("MOD_DUPLICATE_KEY", "ERROR", 6, obligation(st, "POB #1").subject_key)
    ]


@pytest.mark.parametrize("preset", ["DEFAULT", "LEGACY_PARITY"])
def test_tc_prospective_17_sign_mismatch_rejected(preset: str) -> None:
    ctx, st, value = golden("Contract 1", preset)
    row = template_line(value, "POB #1", "-1", "90")
    modification = template_modification("MOD-17", "prospective", [row])
    (finding,) = validate(ctx, st, "Contract 1", modification)
    assert codes([finding]) == [
        ("MOD_SIGN_MISMATCH", "ERROR", 6, obligation(st, "POB #1").subject_key)
    ]
    assert (finding.detail["quantity_delta"], finding.detail["consideration_delta"]) == ("-1", "90")
    assert finding.detail["rule"] == "S06-R-07"


def test_tc_prospective_06_ssp_clamp_unit_cases_sign_mismatch_rejected() -> None:
    """Legacy 03 §3.1: Hardware 1 (P 100, d 0.10, r 0.15) qty −1 with billing +90 clamped to −76.5
    in legacy (P-15); the fixed engine rejects the row. Rows of one sign, and a price-only row
    (qty 0 with billing 50), are not sign mismatches."""
    ctx, st, value = golden("Contract 1")
    mismatch = template_modification(
        "MOD-06", "prospective", [template_line(value, "POB #1", "-1", "90")]
    )
    assert codes(validate(ctx, st, "Contract 1", mismatch)) == [
        ("MOD_SIGN_MISMATCH", "ERROR", 6, obligation(st, "POB #1").subject_key)
    ]
    for quantity, billing in (("-5", "-500"), ("2", "500"), ("0", "50")):
        row = template_line(value, "POB #1", quantity, billing)
        assert (
            validate(ctx, st, "Contract 1", template_modification("MOD-06", "prospective", [row]))
            == ()
        )


def test_tc_prospective_20_header_only_rejected() -> None:
    ctx, st, _ = golden("Contract 1")
    header_only = template_modification("MOD-20", "prospective", [])
    (finding,) = validate(ctx, st, "Contract 1", header_only)
    assert codes([finding]) == [("IMPORT_NO_DATA_ROWS", "ERROR", 6, "Contract 1")]
    assert (finding.detail["template_mode"], finding.detail["rule"]) == ("prospective", "S06-R-07")
    # A native modification may carry no lines: a price change on satisfied performance (S06-R-09).
    native = dataclasses.replace(header_only, template_mode=None, price_change_amount=None)
    assert validate(ctx, st, "Contract 1", native) == ()


def test_tc_rm_09_header_only_rejected() -> None:
    ctx, st, _ = golden("Contract 2")
    header_only = template_modification("MOD-RM09", "retrospective", [])
    assert codes(validate(ctx, st, "Contract 2", header_only)) == [
        ("IMPORT_NO_DATA_ROWS", "ERROR", 6, "Contract 2")
    ]


def test_pob_not_found() -> None:
    ctx, st, value = golden("Contract 2")
    unknown = {**template_line(value, "POB #1", "2", "180"), "obligation_key": "POB #9"}
    modification = template_modification("MOD-PNF", "retrospective", [unknown])
    (finding,) = validate(ctx, st, "Contract 2", modification)
    assert (finding.code, finding.severity, finding.stage) == ("POB_NOT_FOUND", "ERROR", 6)
    assert (finding.subject_key, finding.detail["obligation_key"]) == (
        "Contract 2/POB %239",
        "POB #9",
    )
    added = template_modification("MOD-PNF", "retrospective", [{**unknown, "action": "ADD"}])
    assert all(item.code != "POB_NOT_FOUND" for item in validate(ctx, st, "Contract 2", added))

    # The boundary handler refuses the event (CV-44, CV-45).
    folded = template_fold(
        template_amended(
            value, "MOD-PNF", MOD_08_15, "retrospective", [unknown], "LEGACY_RETROSPECTIVE"
        )
    )
    (ev,) = [item for item in folded.state.events if item.event_type == "CONTRACT_AMENDED"]
    with pytest.raises(EngineError) as raised:
        s06_modifications.apply(
            folded.ctx,
            folded.state,
            ev,
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=folded.identified,
            price_at=price_function("900.00"),
        )
    assert (raised.value.detail["rule"], raised.value.detail["code"]) == (
        "S06-R-07",
        "POB_NOT_FOUND",
    )
    assert raised.value.detail["obligation_key"] == "POB #9"

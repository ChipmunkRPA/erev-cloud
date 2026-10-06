"""Refund liability of a refund-settled VC element without a target (D-87 L5-3-Q-7 = L6-5-Q-11).

Stage 10 published the version's ``refund_liability_target``, else 0 (ENGINE_SPEC_B §10.2.4), so a
rebate, refund or price-protection element whose versions hold no target left the billed excess in
the contract liability (VC-S3-EX24, JE-CHK-025, RET-WM-04, VC-BR-02, VC-RB-04, RET-BR-03). By the
ruling, when the pinned version has no target and ``vc_element_type`` is REBATE, PRICE_PROTECTION,
REFUND or VOLUME_TIER, RL(t) = max(0, min(K_t, B_t − R_t − O_t)): K_t the pin's constrained
reduction (magnitude), B_t billing net of credit memos on the element's target obligations through
t, R_t their ``revenue_cum`` and O_t their RETURN, TERMINATION and CONCESSION components. An
explicit target keeps §10.2.4; DISCOUNT and SLA_CREDIT, and the LEGACY book, keep 0 without it.
These tests run the answer-key worlds without a database.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import cast

import erev_engine
import pytest
from erev_engine.bundle import (
    BookOutput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    OutputBundle,
)
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.stages.s10_billing_balances import refund_liability
from erev_engine.trace import SourceRef, reevaluate
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.runners import _build_checkpoint_bundles
from support.recognition import allocated_state, obligation, segment, usd


def _period_key(as_of: date) -> str:
    return f"FY{as_of.year}-P{as_of.month:02d}"  # monthly calendars from January


def _checkpoints(
    family: str, key_id: str, contract: str
) -> list[tuple[str, str, str, InputBundle]]:
    """(checkpoint name, book, period key, the bundle holding ``contract``) in key order."""
    return _loaded_checkpoints(load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml"), contract)


def _loaded_checkpoints(
    loaded: LoadedKey, contract: str
) -> list[tuple[str, str, str, InputBundle]]:
    out: list[tuple[str, str, str, InputBundle]] = []
    for checkpoint in _build_checkpoint_bundles(loaded):
        (bundle,) = [
            cast(InputBundle, item)
            for item in checkpoint.bundles
            if any(header.external_id == contract for header in item.contracts)
        ]
        out.append((checkpoint.name, checkpoint.book, _period_key(checkpoint.as_of), bundle))
    return out


def _refund(bundle: InputBundle, book: str, contract: str, period_key: str) -> int:
    """T-CON-09 ``refund_liability_txn`` of ``contract`` at ``period_key``."""
    output = cast(OutputBundle, erev_engine.compute(bundle))
    (found,) = [item for item in output.books if item.book_code == book]
    (row,) = [
        item
        for item in found.balances
        if item.subject_key.startswith(f"{contract}@") and item.period_key == period_key
    ]
    return cast(int, row.columns["refund_liability_txn"])


def _figures(family: str, key_id: str, contract: str) -> dict[str, int]:
    return {
        name: _refund(bundle, book, contract, period_key)
        for name, book, period_key, bundle in _checkpoints(family, key_id, contract)
    }


def _with_versions(bundle: InputBundle, **changes: object) -> InputBundle:
    versions = tuple(dataclasses.replace(item, **changes) for item in bundle.estimate_versions)
    return dataclasses.replace(bundle, estimate_versions=versions)


def test_l7_6_volume_tier_without_target_takes_the_billed_excess() -> None:
    """VC-S3-EX24: K 5,750.00, B 57,500.00, R 51,750.00 at 30 June: RL 5,750.00; 0 in March."""
    assert _figures("vc", "VC-S3-EX24", "C-EX24") == {"end-of-q1": 0, "end-of-q2": 575_000}


def test_l7_6_refund_element_is_capped_by_the_billing_net_of_credit_memos() -> None:
    """RET-WM-04: 20,000.00, then min(17,500.00, 488,000.00 − 482,500.00) = 5,500.00, then 0."""
    assert _figures("ret", "RET-WM-04-REFUNDS-AND-CHARGEBACKS", "WM-04") == {
        "orders-delivered": 2_000_000,
        "re-estimate": 550_000,
        "window-closed": 0,
    }


def test_l7_6_rebate_follows_the_constrained_reduction_and_the_settlement_memo() -> None:
    """VC-BR-02: 9,000.00 / 32,500.00 / 45,000.00 / 30,000.00 / 0 (credit memo 31 January 2027)."""
    assert _figures("vc", "VC-BR-02-DISTRIBUTOR-RETRO-REBATE", "BR-02") == {
        "q1": 900_000,
        "q2-higher-tier": 3_250_000,
        "q3": 4_500_000,
        "q4-actual": 3_000_000,
        "rebate-settled": 0,
    }


def test_l7_6_engine_billing_refund_element() -> None:
    """VC-RB-04 (ENGINE billing): 60,000.00 / 45,000.00 / 0."""
    assert _figures("vc", "VC-RB-04-COST-REPORT-SETTLEMENT", "RB-04") == {
        "interim-billed": 6_000_000,
        "cost-report-filed": 4_500_000,
        "final-settlement": 0,
    }


def test_l7_6_explicit_target_keeps_section_10_2_4() -> None:
    """A REBATE version with ``refund_liability_target`` 1,000.00 publishes 1,000.00, not the
    excess (5,750.00). The control uses a T-CON-13 explicit-target type; VOLUME_TIER carries no
    explicit target (VC-R09; ENC-VC-direction ruling)."""
    ((_, book, period_key, bundle),) = [
        item for item in _checkpoints("vc", "VC-S3-EX24", "C-EX24") if item[0] == "end-of-q2"
    ]
    targeted = _with_versions(
        bundle, vc_element_type="REBATE", parameters={"refund_liability_target": "1000.00"}
    )
    assert _refund(targeted, book, "C-EX24", period_key) == 100_000


def test_l7_6_discount_and_sla_credit_keep_zero_without_a_target() -> None:
    """DISCOUNT and SLA_CREDIT keep "0 without it" (606-10-32-10, 55-23)."""
    ((_, book, period_key, bundle),) = [
        item for item in _checkpoints("vc", "VC-S3-EX24", "C-EX24") if item[0] == "end-of-q2"
    ]
    for element_type in ("DISCOUNT", "SLA_CREDIT"):
        changed = _with_versions(bundle, vc_element_type=element_type)
        assert _refund(changed, book, "C-EX24", period_key) == 0


def test_l7_6_derived_form_gate() -> None:
    """The derived form applies to REBATE, PRICE_PROTECTION, REFUND and VOLUME_TIER outside the
    LEGACY book."""
    for element_type in ("REBATE", "PRICE_PROTECTION", "REFUND", "VOLUME_TIER"):
        assert refund_liability.derives("ASC606", element_type)
        assert refund_liability.derives("IFRS15", element_type)
        assert not refund_liability.derives("LEGACY", element_type)
    for element_type in ("DISCOUNT", "SLA_CREDIT", None):
        assert not refund_liability.derives("ASC606", element_type)


def test_l8_e_k_is_the_stage_04_constrained_reduction_without_constrained_amount() -> None:
    """D-88 L7-6-Q-5: K_t is |the posted amount of the pinned version's ``VcElementView``| in the
    latest ``tp_history`` build-up on or before t (S04-R-07), not ``constrained_amount``. A REBATE
    version 2 with MOST_LIKELY_AMOUNT scenarios {5,750.00 at 0.6; 0.00 at 0.4} and no
    ``constrained_amount`` gives K 5,750.00 in ASC606, so RL(30 June) = min(5,750.00, 57,500.00 −
    51,750.00) = 5,750.00; input 0 of the excess node cites member ``vc_constrained``."""
    ((_, book, period_key, bundle),) = [
        item for item in _checkpoints("vc", "VC-S3-EX24", "C-EX24") if item[0] == "end-of-q2"
    ]
    scenarios = (
        {"outcome": "threshold met", "amount": Decimal("5750.00"), "probability": Decimal("0.6")},
        {"outcome": "threshold missed", "amount": Decimal("0.00"), "probability": Decimal("0.4")},
    )
    versions = tuple(
        dataclasses.replace(
            item,
            vc_element_type="REBATE",
            scenarios=scenarios,
            constrained_amount=None,
        )
        if item.version_no == 2
        else dataclasses.replace(item, vc_element_type="REBATE")
        for item in bundle.estimate_versions
    )
    changed = dataclasses.replace(bundle, estimate_versions=versions)
    assert book == "ASC606"
    assert _refund(changed, book, "C-EX24", period_key) == 575_000
    output = cast(OutputBundle, erev_engine.compute(changed))
    (found,) = [item for item in output.books if item.book_code == book]
    (node,) = [
        item
        for item in found.trace.nodes
        if item.id.startswith("refund_liability:")
        and "/VARIABLE_CONSIDERATION/" in item.id
        and item.id.endswith(f":{period_key}")
    ]
    source = node.inputs[0]
    assert isinstance(source, SourceRef)
    assert (source.ref_type, dict(source.detail)) == (
        "estimate_version",
        {"member": "vc_constrained", "value": "5750.00"},
    )
    assert (node.params["mode"], node.value) == ("excess", "5750.00")


def test_l7_6_several_elements_take_the_excess_in_element_key_order() -> None:
    """Two elements on the same obligation share one excess: the first by element key takes
    min(K_1, excess), the next min(K_2, excess − RL_1)."""
    assert refund_liability.excess_share(575_000, 5_750_000, 5_175_000, 0, 0) == 575_000
    assert refund_liability.excess_share(575_000, 5_750_000, 5_175_000, 0, 575_000) == 0
    assert refund_liability.excess_share(300_000, 5_750_000, 5_175_000, 0, 400_000) == 175_000
    assert refund_liability.excess_share(575_000, 5_000_000, 5_175_000, 0, 0) == 0  # max(0, ·)
    assert refund_liability.excess_share(575_000, 5_750_000, 5_175_000, 200_000, 0) == 375_000


# --- D-90d L9-RUN-Q-3 and Q-8: CV-21 encoded component keys and balance subjects ------------------

RET_BR_03 = "RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION"
# (plain id, id with a CV-21 delimiter, its encoded form).
DELIMITER_IDS = (
    ("BR-03-ARMS", "BR-03/ARMS", "BR-03%2FARMS"),
    ("BR-03-SPARES", "BR-03/SPARES", "BR-03%2FSPARES"),
)
_LINE_DIMENSIONS = ("contract", "contract_key", "obligation_key", "product")


def test_l9_run_q3_component_key_encodes_group_and_entity() -> None:
    """``refund_liability._key`` percent-encodes the group code and the entity as stages 05 and 07
    encode them (CV-21); a key without a delimiter is byte-identical to the former raw form."""
    seg = segment(Fraction(100), usd("100.00"), start=date(2026, 1, 1), end=date(2026, 3, 31))
    plain = allocated_state([obligation("POB-001", [seg], contract_key="C-1")])
    assert (
        refund_liability._key(plain, "US01", refund_liability.RETURN, "C-1/POB-001")
        == "CG-1@US01/RETURN/C-1/POB-001"
    )
    delimited = dataclasses.replace(
        allocated_state([obligation("POB-001", [seg], contract_key="C/1")]), group_code="CG-C/1"
    )
    assert (
        refund_liability._key(delimited, "US@01", refund_liability.RETURN, "C%2F1/POB-001")
        == "CG-C%2F1@US%4001/RETURN/C%2F1/POB-001"
    )


def _delimiter_variant(tmp_path: Path) -> Path:
    """A copy of RET-BR-03 whose contract ids carry a CV-21 delimiter (``BR-03/ARMS``,
    ``BR-03/SPARES``), under ``<tmp>/ret/<id>.yaml`` as the loader expects."""
    text = (ANSWER_KEY_ROOT / "ret" / f"{RET_BR_03}.yaml").read_text(encoding="utf-8")
    for plain, delimited, _ in DELIMITER_IDS:
        assert plain in text
        text = text.replace(plain, delimited)
    path = tmp_path / "ret" / f"{RET_BR_03}.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def _plain_ids(value: str) -> str:
    """The variant's subjects and dimensions read with the plain contract ids."""
    for plain, delimited, encoded in DELIMITER_IDS:
        value = value.replace(encoded, plain).replace(delimited, plain)
    return value


def _figures_of(book: BookOutput) -> tuple[set[tuple[object, ...]], set[tuple[object, ...]]]:
    """Balance rows and posting intents of ``book`` as comparable figures (ids read plain)."""
    balances = {
        (_plain_ids(row.subject_key), row.period_key, tuple(sorted(row.columns.items())))
        for row in book.balances
    }
    intents = {
        (
            _plain_ids(intent.subject_key),
            intent.entity,
            intent.posting_period_key,
            intent.origin_period_key,
            intent.entry_kind,
            intent.posting_class,
            intent.reason_code,
            tuple(
                (
                    line.side,
                    line.account_role,
                    line.amount_txn,
                    line.amount_functional,
                    tuple(
                        (name, _plain_ids(line.dimensions[name]))
                        for name in _LINE_DIMENSIONS
                        if name in line.dimensions
                    ),
                )
                for line in intent.lines
            ),
        )
        for intent in book.posting_intents
    }
    return balances, intents


def _book(bundle: InputBundle, book: str) -> BookOutput:
    output = cast(OutputBundle, erev_engine.compute(bundle))
    (found,) = [item for item in output.books if item.book_code == book]
    return found


def test_l9_run_q3_q8_delimiter_contract_ids_keep_their_figures(tmp_path: Path) -> None:
    """RET-BR-03 with the contract ids ``BR-03/ARMS`` and ``BR-03/SPARES`` computes every
    checkpoint with the figures of the plain key and CV-21 encoded subjects: the balance rows
    ``BR-03%2FARMS@BR-DE`` and ``BR-03%2FSPARES@BR-DE``, the component keys
    ``CG-BR-03%2FARMS@BR-DE/VARIABLE_CONSIDERATION/BR-03%2FARMS/PP-BR03-ARMS`` and
    ``CG-BR-03%2FSPARES@BR-DE/RETURN/BR-03%2FSPARES/L1-SPARES``. Before D-90d the routed
    PRICE_PROTECTION element raised ``ENGINE_INVARIANT_VIOLATED`` "no obligation receives the
    transaction price change" at stage 08 (its estimate key head is the encoded id) and the
    RETURN component and balance rows carried raw ``BR-03/SPARES`` heads."""
    variant = load(_delimiter_variant(tmp_path))
    plain = load(ANSWER_KEY_ROOT / "ret" / f"{RET_BR_03}.yaml")
    seen: set[str] = set()
    for (_, delimited, encoded), plain_id in zip(
        DELIMITER_IDS, ("BR-03-ARMS", "BR-03-SPARES"), strict=True
    ):
        expected = _loaded_checkpoints(plain, plain_id)
        actual = _loaded_checkpoints(variant, delimited)
        assert [item[:3] for item in actual] == [item[:3] for item in expected]
        for (name, book, period_key, bundle), (_, _, _, plain_bundle) in zip(
            actual, expected, strict=True
        ):
            found = _book(bundle, book)
            assert _figures_of(found) == _figures_of(_book(plain_bundle, book))
            subjects = {row.subject_key for row in found.balances} | {
                intent.subject_key for intent in found.posting_intents
            }
            assert not any(delimited in subject for subject in subjects), (name, subjects)
            seen |= subjects
            (row,) = [
                item
                for item in found.balances
                if item.subject_key == f"{encoded}@BR-DE" and item.period_key == period_key
            ]
            if (delimited, name) == ("BR-03/ARMS", "price-protection"):
                assert row.columns["refund_liability_txn"] == 1_200_000
                (jet_04b,) = [
                    intent
                    for intent in found.posting_intents
                    if intent.subject_key
                    == f"CG-{encoded}@BR-DE/VARIABLE_CONSIDERATION/{encoded}/PP-BR03-ARMS"
                    and intent.posting_period_key == "FY2026-P05"
                ]
                assert [
                    (line.side, line.account_role, line.amount_txn, line.dimensions["contract_key"])
                    for line in jet_04b.lines
                    if line.account_role == "REFUND_LIABILITY"
                ] == [("C", "REFUND_LIABILITY", 1_200_000, "BR-03/ARMS")]
            if (delimited, name) == ("BR-03/SPARES", "shipment-month"):
                assert row.columns["refund_liability_txn"] == 200_000
                assert f"CG-{encoded}@BR-DE/RETURN/{encoded}/L1-SPARES" in {
                    intent.subject_key for intent in found.posting_intents
                }
    assert {"BR-03%2FARMS@BR-DE", "BR-03%2FSPARES@BR-DE"} <= seen


# --- ENC-VC-direction: a refundable reduction (DECREASE) versus a positive overage (INCREASE) -----

VC_FS_02 = "VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE"
# VC-FS-02 expected transaction prices by checkpoint (the key's oracle, unchanged).
VC_FS_02_PRICES = {
    "q1": 22_000_000,
    "q2-reestimate": 28_000_000,
    "october-contract-asset": 28_000_000,
    "year-end-actual": 29_500_000,
}


def _book(bundle: InputBundle, book: str) -> BookOutput:
    output = cast(OutputBundle, erev_engine.compute(bundle))
    (found,) = [item for item in output.books if item.book_code == book]
    return found


def test_enc_vc_direction_increase_volume_tier_creates_no_refund_component() -> None:
    """VC-FS-02 (supervisor-ruled input: the tiered overage is an INCREASE). With the direction the
    element adds to the price (220,000.00 / 280,000.00 / 280,000.00 / 295,000.00), stage 10 creates
    no VARIABLE_CONSIDERATION component, publishes no refund liability, needs no REFUND_LIABILITY
    account (the world maps none) and every node re-evaluates. With the member absent the B3-DG-17
    default (DECREASE) stands and the historical failure returns: a 20,000.00 refund component whose
    JET-04b part finds no account (ACCOUNT_MAPPING_MISSING; the state before this lane)."""
    checkpoints = [
        (name, book, period_key, _with_versions(bundle, direction="INCREASE"))
        for name, book, period_key, bundle in _checkpoints("vc", VC_FS_02, "FS-02")
    ]  # the ruled direction, forced here so the test does not depend on the fixture text
    assert [name for name, *_ in checkpoints] == list(VC_FS_02_PRICES)
    for name, book, period_key, bundle in checkpoints:
        found = _book(bundle, book)
        assert found.contract_version is not None
        assert found.contract_version.columns["transaction_price"] == VC_FS_02_PRICES[name]
        # No refund component node; the zero member-balance nodes of member_sums.py (role
        # ``member_sum``; DG-KRN-EXP-01, D-97 (8)) link the T-CON-09 columns, not components.
        assert not [
            node
            for node in found.trace.nodes
            if node.id.startswith("refund_liability:") and node.params.get("role") != "member_sum"
        ]
        assert not [
            intent
            for intent in found.posting_intents
            if any(line.account_role == "REFUND_LIABILITY" for line in intent.lines)
        ]
        (row,) = [
            item
            for item in found.balances
            if item.subject_key.startswith("FS-02@") and item.period_key == period_key
        ]
        assert row.columns["refund_liability_txn"] == 0
        assert reevaluate(found.trace) == {node.id: node.value for node in found.trace.nodes}
    (_, book, _, q1) = checkpoints[0]
    absent = _with_versions(q1, direction=None)
    with pytest.raises(EngineError) as failed:
        erev_engine.compute(absent)
    assert failed.value.code == "ACCOUNT_MAPPING_MISSING"
    (finding,) = json.loads(failed.value.detail["findings"])  # CV-15: canonical JSON
    assert finding["detail"]["role"] == "REFUND_LIABILITY"
    explicit_decrease = _with_versions(q1, direction="DECREASE")
    with pytest.raises(EngineError) as failed:
        erev_engine.compute(explicit_decrease)
    assert failed.value.code == "ACCOUNT_MAPPING_MISSING"


# --- ENC-VC-direction ruling: explicit refund targets versus the derived reduction --------------
# Supervisor model-scope ruling of 2026-09-19 (the 32-10 basis is the supervisor's reading): an
# explicit non-negative target on one of the five refund-settled types drives the component for
# either direction; a positive overage without a target derives nothing; an explicit target on any
# other type fails closed naming the supported route; targets are never silently discarded.

SUPPORTED = tuple(sorted(refund_liability.REFUND_SETTLED_TYPES))
UNSUPPORTED = ("BONUS", "VOLUME_TIER")
EX24 = ("vc", "VC-S3-EX24", "C-EX24")
EX24_ESTIMATE = "C-EX24/VC-VOLUME"
TARGET = "refund_liability_target"


def _ex24_q2() -> tuple[str, str, InputBundle]:
    ((_, book, period_key, bundle),) = [
        item for item in _checkpoints(*EX24) if item[0] == "end-of-q2"
    ]
    return book, period_key, bundle


def _retyped(
    bundle: InputBundle, vc_type: str, direction: str | None, target: str | None
) -> InputBundle:
    parameters = {} if target is None else {TARGET: target}
    return _with_versions(
        bundle, vc_element_type=vc_type, direction=direction, parameters=parameters
    )


def _vc_refund_nodes(book: BookOutput) -> dict[str, tuple[str, str | None]]:
    """period key -> (value, cited estimate version key) of the VC refund component's nodes."""
    out: dict[str, tuple[str, str | None]] = {}
    for node in book.trace.nodes:
        if node.id.startswith("refund_liability:") and "/VARIABLE_CONSIDERATION/" in node.id:
            refs = [item for item in node.inputs if isinstance(item, SourceRef)]
            out[node.id.rsplit(":", 1)[1]] = (node.value, refs[0].ref_id if refs else None)
    return out


def _refund_postings(book: BookOutput) -> dict[str, int]:
    """period key -> net credit posted to REFUND_LIABILITY (minor units), non-zero periods."""
    out: dict[str, int] = {}
    for intent in book.posting_intents:
        for line in intent.lines:
            if line.account_role == "REFUND_LIABILITY":
                signed = line.amount_txn if line.side == "C" else -line.amount_txn
                out[intent.posting_period_key] = out.get(intent.posting_period_key, 0) + signed
    return {key: value for key, value in sorted(out.items()) if value}


def _price(book: BookOutput) -> int:
    assert book.contract_version is not None
    return cast(int, book.contract_version.columns["transaction_price"])


def _replays(book: BookOutput) -> None:
    assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}


def test_enc_vc_direction_refund_candidate_follows_the_ruling() -> None:
    """R02/R05/R09/R10 predicate: an explicit target makes a supported type a candidate for either
    direction; without a target only a DECREASE refund-settled or derived type is; a target on an
    unsupported type is not a candidate (it is refused before the predicate is consulted)."""
    _, _, bundle = _ex24_q2()
    (template,) = [item for item in bundle.estimate_versions if item.version_no == 1]
    for vc_type in SUPPORTED:
        for direction in (None, "INCREASE", "DECREASE"):
            for target in ("0.00", "25.01"):
                version = dataclasses.replace(
                    template,
                    vc_element_type=vc_type,
                    direction=direction,
                    parameters={TARGET: target},
                )
                assert refund_liability.refund_candidate(version)
                assert refund_liability.explicit_target(version) == target
        untargeted = dataclasses.replace(template, vc_element_type=vc_type, parameters={})
        assert refund_liability.refund_candidate(
            dataclasses.replace(untargeted, direction="DECREASE")
        )
        assert not refund_liability.refund_candidate(
            dataclasses.replace(untargeted, direction="INCREASE")
        )
        nulled = dataclasses.replace(untargeted, direction="DECREASE", parameters={TARGET: None})
        assert refund_liability.explicit_target(nulled) is None  # explicit null = absent (T-CON-13)
    volume = dataclasses.replace(template, vc_element_type="VOLUME_TIER", parameters={})
    assert refund_liability.refund_candidate(dataclasses.replace(volume, direction=None))  # derived
    assert not refund_liability.refund_candidate(dataclasses.replace(volume, direction="INCREASE"))
    for vc_type in UNSUPPORTED:
        for direction in ("INCREASE", "DECREASE"):
            targeted = dataclasses.replace(
                template, vc_element_type=vc_type, direction=direction, parameters={TARGET: "0.00"}
            )
            assert not refund_liability.refund_candidate(targeted)
            with pytest.raises(EngineError):
                refund_liability.refuse_unsupported_target(targeted, EX24_ESTIMATE)
    bonus = dataclasses.replace(template, vc_element_type="BONUS", parameters={})
    for direction in (None, "INCREASE", "DECREASE"):
        assert not refund_liability.refund_candidate(
            dataclasses.replace(bonus, direction=direction)
        )


@pytest.mark.parametrize("vc_type", SUPPORTED)
def test_enc_vc_direction_r02_increase_without_target_derives_nothing(vc_type: str) -> None:
    """VC-R02: a supported type, INCREASE, no target: the element adds 5,750.00 to the price
    (63,250.00) and no VC refund component exists; no refund evidence is manufactured."""
    book_code, period_key, bundle = _ex24_q2()
    book = _book(_retyped(bundle, vc_type, "INCREASE", None), book_code)
    assert _price(book) == 6_325_000
    assert _vc_refund_nodes(book) == {}
    assert _refund_postings(book) == {}
    assert (
        _refund(_retyped(bundle, vc_type, "INCREASE", None), book_code, "C-EX24", period_key) == 0
    )
    _replays(book)


@pytest.mark.parametrize("vc_type", SUPPORTED)
@pytest.mark.parametrize("direction", ["INCREASE", "DECREASE"])
def test_enc_vc_direction_r03_r05_explicit_zero_target_is_zero_not_absent(
    vc_type: str, direction: str
) -> None:
    """VC-R03 and VC-R05 (zero): an explicit ``"0.00"`` target on a supported type is accepted for
    either direction: the component exists, its node cites the target member with value 0, the
    balance is 0 and nothing non-zero posts to REFUND_LIABILITY. For DECREASE the zero overrides
    the derived excess (5,750.00 without a target on REBATE, PRICE_PROTECTION and REFUND)."""
    book_code, period_key, bundle = _ex24_q2()
    zeroed = _retyped(bundle, vc_type, direction, "0.00")
    book = _book(zeroed, book_code)
    nodes = _vc_refund_nodes(book)
    assert nodes[period_key] == ("0.00", f"{EX24_ESTIMATE}@v2")
    (node,) = [
        n
        for n in book.trace.nodes
        if n.id.startswith("refund_liability:")
        and n.id.endswith(f":{period_key}")
        and "/VARIABLE_CONSIDERATION/" in n.id
    ]
    (ref,) = [item for item in node.inputs if isinstance(item, SourceRef)]
    assert dict(ref.detail) == {"member": TARGET, "value": "0"}
    assert _refund(zeroed, book_code, "C-EX24", period_key) == 0
    assert _refund_postings(book) == {}
    _replays(book)


@pytest.mark.parametrize("vc_type", SUPPORTED)
@pytest.mark.parametrize("direction", ["INCREASE", "DECREASE"])
def test_enc_vc_direction_r04_r05_explicit_target_is_the_liability(
    vc_type: str, direction: str
) -> None:
    """VC-R04 and VC-R05 (25.01): an explicit ``"25.01"`` target on a supported type gives a VC
    liability of exactly 2,501 minor units for either direction, sourced from the approved version
    and the target member, posted once to REFUND_LIABILITY in the version's period (JET-04b)."""
    book_code, period_key, bundle = _ex24_q2()
    targeted = _retyped(bundle, vc_type, direction, "25.01")
    book = _book(targeted, book_code)
    assert _vc_refund_nodes(book)[period_key] == ("25.01", f"{EX24_ESTIMATE}@v2")
    assert _refund(targeted, book_code, "C-EX24", period_key) == 2_501
    # Both versions carry the target, so the liability posts once, in version 1's period (P01),
    # and is remeasured to the same 25.01 by version 2 (no second posting).
    assert _refund_postings(book) == {"FY2026-P01": 2_501}
    assert _price(book) == (6_325_000 if direction == "INCREASE" else 5_175_000)
    _replays(book)


@pytest.mark.parametrize("vc_type", ("REBATE", "PRICE_PROTECTION", "REFUND"))
def test_enc_vc_direction_r06_derived_form_and_explicit_zero(vc_type: str) -> None:
    """VC-R06: DECREASE, no target, non-LEGACY: D-87 stands. (a) EX24's attained balances K
    5,750.00, B 57,500.00, R 51,750.00 give 5,750.00; (b) the R06 figures on the same world: K
    100.00 (version 2 constrained 100.00) and one more 50.00 invoice, so B 57,550.00, R 57,400.00,
    excess 150.00, RL = min(100.00, 150.00) = 100.00; the O term of the rule is the RETURN,
    TERMINATION and CONCESSION components (``excess_share`` with O 25.00: min(100, 125) = 100).
    An explicit zero on the same element gives 0 instead."""
    book_code, period_key, bundle = _ex24_q2()
    derived = _retyped(bundle, vc_type, "DECREASE", None)
    assert _refund(derived, book_code, "C-EX24", period_key) == 575_000
    assert (
        _refund(_retyped(bundle, vc_type, "DECREASE", "0.00"), book_code, "C-EX24", period_key) == 0
    )
    versions = tuple(
        dataclasses.replace(
            item,
            vc_element_type=vc_type,
            direction="DECREASE",
            parameters={},
            unconstrained_amount=Decimal("100.00"),
            most_conservative_amount=Decimal("100.00"),
            constrained_amount=Decimal("100.00"),
        )
        if item.version_no == 2
        else dataclasses.replace(item, vc_element_type=vc_type, direction="DECREASE", parameters={})
        for item in bundle.estimate_versions
    )
    q2_bill = next(
        e
        for e in bundle.events
        if e.event_type == "BILLING_RECORDED" and e.effective_date == date(2026, 6, 30)
    )
    payload = {
        **q2_bill.payload,
        "invoice_number": "INV-EX24-Q2B",
        "line_external_id": "INV-EX24-Q2B-1",
        "amount": Decimal("50.00"),
    }
    extra = dataclasses.replace(
        q2_bill,
        event_key="C-EX24/EV-000009",
        stream_version=9,
        record_seq=9,
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )
    events = tuple(
        sorted((*bundle.events, extra), key=lambda e: (e.effective_date, e.record_seq, e.event_key))
    )
    figures = dataclasses.replace(bundle, estimate_versions=versions, events=events)
    book = _book(figures, book_code)
    assert _price(book) == 5_740_000
    (node,) = [
        n
        for n in book.trace.nodes
        if n.id.startswith("refund_liability:")
        and n.id.endswith(f":{period_key}")
        and "/VARIABLE_CONSIDERATION/" in n.id
    ]
    assert (
        node.params["mode"],
        node.params["billed"],
        node.params["revenue"],
        node.params["other"],
    ) == ("excess", "5755000", "5740000", "0")
    assert (node.value, _refund(figures, book_code, "C-EX24", period_key)) == ("100.00", 10_000)
    assert refund_liability.excess_share(10_000, 100_000, 85_000, 2_500, 0) == 10_000
    _replays(book)


def test_enc_vc_direction_r07_r08_untargeted_controls_unchanged() -> None:
    """VC-R07: VC-S3-EX24 as keyed (VOLUME_TIER, no direction, no target) keeps 0 / 5,750.00.
    VC-R08: DISCOUNT and SLA_CREDIT without a target keep 0; the LEGACY book derives nothing."""
    assert _figures(*EX24) == {"end-of-q1": 0, "end-of-q2": 575_000}
    book_code, period_key, bundle = _ex24_q2()
    for vc_type in ("DISCOUNT", "SLA_CREDIT"):
        assert (
            _refund(_retyped(bundle, vc_type, "DECREASE", None), book_code, "C-EX24", period_key)
            == 0
        )
    for vc_type in sorted(refund_liability.DERIVED_TYPES):
        assert not refund_liability.derives("LEGACY", vc_type)


@pytest.mark.parametrize("vc_type", UNSUPPORTED)
@pytest.mark.parametrize("direction", ["INCREASE", "DECREASE"])
@pytest.mark.parametrize("target", ["0.00", "25.01"])
def test_enc_vc_direction_r09_unsupported_target_type_fails_closed(
    vc_type: str, direction: str, target: str
) -> None:
    """VC-R09: an explicit target (including zero) on BONUS or VOLUME_TIER, either direction, is
    outside the T-CON-13 model: ENGINE_INVARIANT_VIOLATED naming the type, the version and the
    supported route; no partial output (compute raises before returning anything)."""
    book_code, _, bundle = _ex24_q2()
    with pytest.raises(EngineError) as failed:
        erev_engine.compute(_retyped(bundle, vc_type, direction, target))
    error = failed.value
    assert error.code == "ENGINE_INVARIANT_VIOLATED"
    assert error.subject_key == EX24_ESTIMATE
    detail = dict(error.detail)
    assert (detail["rule"], detail["reason"], detail["vc_element_type"], detail["direction"]) == (
        "CV-45",
        "REFUND_TARGET_TYPE_UNSUPPORTED",
        vc_type,
        direction,
    )
    assert detail["estimate_version_key"].startswith(f"{EX24_ESTIMATE}@v")
    assert detail["supported_types"] == "DISCOUNT|PRICE_PROTECTION|REBATE|REFUND|SLA_CREDIT"
    assert (
        "refund_liability_target" in error.message and "DISCOUNT|PRICE_PROTECTION" in error.message
    )
    assert "D-87" in detail["route"]


@pytest.mark.parametrize("direction", ["INCREASE", "DECREASE"])
def test_enc_vc_direction_r10_bonus_without_target_keeps_its_price_behaviour(
    direction: str,
) -> None:
    """VC-R10: BONUS without a target is not refused for lacking explicit-target support: the
    price moves by its direction (63,250.00 / 51,750.00) and no refund component exists."""
    book_code, period_key, bundle = _ex24_q2()
    plain = _retyped(bundle, "BONUS", direction, None)
    book = _book(plain, book_code)
    assert _price(book) == (6_325_000 if direction == "INCREASE" else 5_175_000)
    assert _vc_refund_nodes(book) == {}
    assert _refund(plain, book_code, "C-EX24", period_key) == 0
    _replays(book)


def _targets_world(
    bundle: InputBundle,
    steps: Sequence[tuple[date, str | None]],
    *,
    vc_type: str = "REBATE",
    direction: str = "DECREASE",
    memo: tuple[date, str] | None = None,
) -> InputBundle:
    """EX24's q2 world re-keyed as ``vc_type`` with ``direction`` (constrained 0.00) whose versions
    carry the explicit targets of ``steps`` (effective date, target), applied by ESTIMATE_CHANGED
    events in order; optionally one CREDIT_MEMO_RECORDED (date, amount) against INV-EX24-Q1."""
    (template,) = [item for item in bundle.estimate_versions if item.version_no == 1]
    changed = next(e for e in bundle.events if e.event_type == "ESTIMATE_CHANGED")
    kept = [e for e in bundle.events if e.event_type != "ESTIMATE_CHANGED"]
    versions: list[EstimateVersionInput] = []
    events: list[EventInput] = list(kept)
    stream = max(e.stream_version for e in kept)
    for index, (effective, target) in enumerate(steps, start=1):
        key = f"{EX24_ESTIMATE}@v{index}"
        versions.append(
            dataclasses.replace(
                template,
                vc_element_type=vc_type,
                direction=direction,
                version_key=key,
                version_no=index,
                effective_date=effective,
                parameters={} if target is None else {TARGET: target},
                unconstrained_amount=Decimal("0.00"),
                most_conservative_amount=Decimal("0.00"),
                constrained_amount=Decimal("0.00"),
                supersedes_version_key=None if index == 1 else f"{EX24_ESTIMATE}@v{index - 1}",
            )
        )
        stream += 1
        payload = {"estimate_version_id": key}
        events.append(
            dataclasses.replace(
                changed,
                event_key=f"C-EX24/EV-{stream:06d}",
                stream_version=stream,
                record_seq=stream,
                effective_date=effective,
                recorded_at=datetime(
                    effective.year, effective.month, effective.day, 12, tzinfo=UTC
                ),
                payload=payload,
                payload_sha256=sha256_hex(payload),
                estimate_version_key=key,
            )
        )
    if memo is not None:
        bill = next(e for e in kept if e.event_type == "BILLING_RECORDED")
        stream += 1
        payload = {
            "credit_memo_number": "CM-EX24-1",
            "credited_invoice_number": "INV-EX24-Q1",
            "obligation_key": "L1-A",
            "amount": Decimal(memo[1]),
            "issue_date": memo[0],
        }
        events.append(
            dataclasses.replace(
                bill,
                event_key=f"C-EX24/EV-{stream:06d}",
                stream_version=stream,
                record_seq=stream,
                event_type="CREDIT_MEMO_RECORDED",
                effective_date=memo[0],
                recorded_at=datetime(memo[0].year, memo[0].month, memo[0].day, 12, tzinfo=UTC),
                payload=payload,
                payload_sha256=sha256_hex(payload),
            )
        )
    ordered = tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key)))
    return dataclasses.replace(bundle, estimate_versions=tuple(versions), events=ordered)


@pytest.mark.parametrize("vc_type", ["REBATE", "REFUND"])
@pytest.mark.parametrize("direction", ["INCREASE", "DECREASE"])
def test_enc_vc_direction_r11_target_sequence_releases_and_rebuilds(
    vc_type: str, direction: str
) -> None:
    """VC-R11: approved targets 25.01 (31 Mar) → 0.00 (30 Apr) → 10.00 (30 Jun) on a supported
    element, for either direction: component balances 2,501 → 0 → 1,000 minor units, each
    period's node citing the version pinned at its end (latest approved on or before the date),
    JET-04b changes +2,501 (P03), −2,501 (P04), +1,000 (P06); the zero releases the balance and
    keeps the history. The INCREASE sequence passes identically to the DECREASE one."""
    book_code, _, bundle = _ex24_q2()
    steps = (
        (date(2026, 3, 31), "25.01"),
        (date(2026, 4, 30), "0.00"),
        (date(2026, 6, 30), "10.00"),
    )
    world = _targets_world(bundle, steps, vc_type=vc_type, direction=direction)
    book = _book(world, book_code)
    nodes = _vc_refund_nodes(book)
    assert {
        key: nodes[key] for key in ("FY2026-P03", "FY2026-P04", "FY2026-P05", "FY2026-P06")
    } == {
        "FY2026-P03": ("25.01", f"{EX24_ESTIMATE}@v1"),
        "FY2026-P04": ("0.00", f"{EX24_ESTIMATE}@v2"),
        "FY2026-P05": ("0.00", f"{EX24_ESTIMATE}@v2"),
        "FY2026-P06": ("10.00", f"{EX24_ESTIMATE}@v3"),
    }
    assert {
        key: _refund(world, book_code, "C-EX24", key)
        for key in ("FY2026-P03", "FY2026-P04", "FY2026-P06")
    } == {
        "FY2026-P03": 2_501,
        "FY2026-P04": 0,
        "FY2026-P06": 1_000,
    }
    assert _refund_postings(book) == {
        "FY2026-P03": 2_501,
        "FY2026-P04": -2_501,
        "FY2026-P06": 1_000,
    }
    _replays(book)


def test_enc_vc_direction_r12_reduced_target_net_of_a_credit_memo_counts_once() -> None:
    """VC-R12: target 25.01 (31 Mar); a 10.00 credit memo on 30 Apr and a re-estimate the same day
    to 15.01 (the preparer's target is net of memos issued by its effective date, T-CON-13): the
    component is exactly 15.01, the memo consumes nothing of the VC component (S10-R-14), the
    node cites version 2, and the postings are +2,501 then −1,000."""
    book_code, _, bundle = _ex24_q2()
    steps = ((date(2026, 3, 31), "25.01"), (date(2026, 4, 30), "15.01"))
    world = _targets_world(bundle, steps, memo=(date(2026, 4, 30), "10.00"))
    book = _book(world, book_code)
    nodes = _vc_refund_nodes(book)
    assert (nodes["FY2026-P03"], nodes["FY2026-P04"], nodes["FY2026-P06"]) == (
        ("25.01", f"{EX24_ESTIMATE}@v1"),
        ("15.01", f"{EX24_ESTIMATE}@v2"),
        ("15.01", f"{EX24_ESTIMATE}@v2"),
    )
    assert not [
        node.id
        for node in book.trace.nodes
        if node.id.startswith("refund_liability_consumed@")
        and "/VARIABLE_CONSIDERATION/" in node.id
    ]
    assert _refund(world, book_code, "C-EX24", "FY2026-P04") == 1_501
    assert _refund_postings(book) == {"FY2026-P03": 2_501, "FY2026-P04": -1_000}
    nodes_by_id = {node.id: node.value for node in book.trace.nodes}
    assert nodes_by_id["billed_cum:C-EX24/L1-A:FY2026-P04"] == "7490.00"  # 7,500.00 − 10.00
    _replays(book)


def test_enc_vc_direction_r13_explicit_null_target_is_absent() -> None:
    """VC-R13 (null): ``{"refund_liability_target": null}`` is the T-CON-13 "absent = 0" case, so
    a DECREASE REBATE derives the excess as without the member (5,750.00) while ``"0.00"`` gives 0;
    recorded as current behaviour, not an approved extension of the decimal-string member."""
    book_code, period_key, bundle = _ex24_q2()
    nulled = _with_versions(
        bundle, vc_element_type="REBATE", direction="DECREASE", parameters={TARGET: None}
    )
    assert _refund(nulled, book_code, "C-EX24", period_key) == 575_000
    assert (
        _refund(_retyped(bundle, "REBATE", "DECREASE", "0.00"), book_code, "C-EX24", period_key)
        == 0
    )

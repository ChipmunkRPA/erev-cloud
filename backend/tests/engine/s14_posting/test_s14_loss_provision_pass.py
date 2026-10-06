"""JET-12 loss provisions: the T-CON-09 column, the ``CLOSE_RELEASE`` pass and the POL-151 scope
(ENGINE_SPEC_B §11.2.7 S11-R-14, S11-R-15, Table 14-A row JET-12, S14-R-05; 05 RCP-07, RCP-08(a);
POLICIES JET-12, POL-150 to POL-153; D-92 (3); lane ENG-C7).

Stage 11 computed the EX-11-B / CHK-132 provisions (0.00 / 30,000.00 / 0.00), but no T-CON-09
``loss_provision_txn`` column was produced and no JET-12 ``LOSS_EXPENSE`` / ``LOSS_PROVISION``
intent was derived, so the four LOSS keys stopped at ``loss_provision: actual <absent>``. The
part is ``TIME``: compute posts nothing for an open period and the ``CLOSE_RELEASE`` pass posts the
movement required(t) − required(t − 1); a closed period carries at compute (RCP-08). The worlds
are the keys' worlds with the cost-to-cost template replaced by a ``UNITS_DELIVERED`` stand-in
that delivers the same progress at the same dates (as ``test_s11_loss.py`` does: stage 09's
cost-to-cost measure is lane ENC-5, unmerged), written as scratch keys and built by the answer-key
assembler (DG-AK-40). Every checkpoint figure asserted is the key's. No database.
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import erev_engine
import pytest
import yaml
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import BookOutput, InputBundle, OutputBundle
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.money import DECIMAL_CONTEXT
from erev_engine.stages.s12_fx_entities import FxState, FxTarget, RateRef
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.s14_posting.targets import part_targets, role_targets
from erev_engine.stages.state import Target
from erev_engine.trace import TraceBuilder
from support import bundles, intent_totals
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load, parse_yaml
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

RELEASE = "CLOSE_RELEASE"
LOSS_PROVISION = "LOSS_PROVISION"  # E-29 entry kind of JET-12
EXPENSE, PROVISION = "LOSS_EXPENSE", "LOSS_PROVISION"
COLUMN = "loss_provision_txn"
ENTITY = bundles.ENTITY_CODE

LOSS_S7 = ANSWER_KEY_ROOT / "loss" / "LOSS-S7-LOSS-OWN.yaml"
GE_03 = ANSWER_KEY_ROOT / "loss" / "LOSS-GE-03-LOSS-CONTRACT-PROVISION.yaml"
IFRS_SW11 = ANSWER_KEY_ROOT / "ifrs" / "IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY.yaml"
# Scratch ids (DG-AK-04: the prefix is families[0]; no CHK is claimed).
S7_ID = "LOSS-ENG-C7-S7-LOSS-OWN-UNITS-STAND-IN"
GE_03_ID = "LOSS-ENG-C7-GE-03-UNITS-STAND-IN"
SW11_ID = "IFRS-ENG-C7-SW11-UNITS-STAND-IN"
# Units delivered at each PROGRESS_INPUT cost, giving the key's progress: 450 / 900 = 50%,
# 770 / 1,100 = 70%, 100% (S7); 800 / 2,000 = 40%, 1,300 / 2,600 = 50%, 75%, 100% (GE-03);
# 440 / 1,100 = 40% (SW11).
S7_UNITS = ("50", "20", "30")
GE_03_UNITS = ("40", "10", "25", "25")
SW11_UNITS = ("40",)

Line = tuple[str, str, str | None, str | None, str, int]  # period, class, origin, reason, role, txn


def _stand_in(source: Path, scratch_id: str, units: Sequence[str], tmp_path: Path) -> Path:
    """The key's world with its cost-to-cost template replaced by a ``UNITS_DELIVERED`` stand-in
    (100 units on the line; a delivery of ``units[i]`` right after the i-th ``PROGRESS_INPUT``
    cost, at its date), re-sequenced with the checkpoints following their items. Obligation rows
    are dropped (``progress_ratio`` is the cost-to-cost figure); every other checkpoint value is
    the key's."""
    data = cast(dict[str, object], parse_yaml(source.read_text(encoding="utf-8"), path=source))
    data["id"] = scratch_id
    data["title"] = f"ENG-C7 units stand-in of {source.stem} (test scratch key)"
    data["summary"] = "Test scratch world for test_s14_loss_provision_pass (D-92 (3); ENG-C7)."
    data["derived_from"] = {"research04": [], "research05": [], "chk": [], "golden": [], "dev": []}
    data.pop("tags", None)
    world = cast(dict[str, object], data["world"])
    for template in cast(list[dict[str, object]], world["pob_templates"]):
        if template["recognition_method"] == "COST_TO_COST":
            template["satisfaction_pattern"] = "POINT_IN_TIME"
            template["over_time_criterion"] = "NOT_APPLICABLE"
            template["recognition_method"] = "UNITS_DELIVERED"
    for contract in cast(list[dict[str, object]], data["contracts"]):
        for line in cast(list[dict[str, object]], contract["lines"]):
            line["quantity"] = "100"
    timeline: list[dict[str, object]] = []
    new_seq: dict[str, int] = {}
    delivered = iter(units)
    for item in cast(list[dict[str, object]], data["timeline"]):
        old = str(item["seq"])
        timeline.append({**item, "seq": len(timeline) + 1})
        new_seq[old] = len(timeline)
        payload = cast(dict[str, object], item.get("payload") or {})
        if item["event_type"] == "COST_INCURRED" and payload.get("purpose") == "PROGRESS_INPUT":
            timeline.append(
                {
                    "seq": len(timeline) + 1,
                    "kind": "event",
                    "contract": item["contract"],
                    "event_type": "DELIVERY_RECORDED",
                    "effective_date": item["effective_date"],
                    "payload": {
                        "obligation_key": payload["obligation_key"],
                        "quantity": next(delivered),
                        "trigger": "DELIVERY",
                    },
                }
            )
            new_seq[old] = len(timeline)
    assert next(delivered, None) is None, "every stand-in delivery follows a cost"
    data["timeline"] = timeline
    for checkpoint in cast(list[dict[str, object]], data["checkpoints"]):
        checkpoint["after_seq"] = new_seq[str(checkpoint["after_seq"])]
        for block in cast(list[dict[str, object]], checkpoint.get("contracts") or ()):
            block.pop("obligations", None)
    path = tmp_path / source.parent.name / f"{scratch_id}.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _checkpoint(path: Path, name: str) -> tuple[InputBundle, str]:
    loaded = load(path)
    checkpoint = next(c for c in runners._build_checkpoint_bundles(loaded) if c.name == name)
    (bundle,) = checkpoint.bundles
    return cast(InputBundle, bundle), checkpoint.book


def _runs(path: Path, name: str) -> tuple[OutputBundle, OutputBundle, str]:
    """``compute`` and the ``CLOSE_RELEASE`` pass over its intents for checkpoint ``name``."""
    bundle, book = _checkpoint(path, name)
    command = cast(OutputBundle, erev_engine.compute(bundle))
    with decimal.localcontext(DECIMAL_CONTEXT):
        released = intent_totals.close_pass(bundle, [command], RELEASE)
    return command, released, book


def _book(output: OutputBundle, book_code: str) -> BookOutput:
    (book,) = [item for item in output.books if item.book_code == book_code]
    return book


def _loss_lines(output: OutputBundle, book_code: str) -> list[Line]:
    """Signed amounts (debit positive) of the book's ``LOSS_PROVISION`` intents."""
    return sorted(
        (
            intent.posting_period_key,
            intent.posting_class,
            intent.origin_period_key,
            intent.reason_code,
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
        )
        for intent in _book(output, book_code).posting_intents
        if intent.entry_kind == LOSS_PROVISION
        for line in intent.lines
    )


def _column(output: OutputBundle, book_code: str, subject: str, period: str) -> object:
    (row,) = [
        b
        for b in _book(output, book_code).balances
        if b.subject_key == subject and b.period_key == period
    ]
    return row.columns.get(COLUMN, "<absent>")


# --- Stage 14 part target -----------------------------------------------------------------------


def _fx_state(*functional: FxTarget) -> FxState:
    return FxState(
        allocated=allocated_state([]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=(),
        functional_targets=functional,
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def _fx_target(period: str, txn: str, functional: str) -> FxTarget:
    """A stage 12 functional amount of the loss unit's required provision (EUR → USD)."""
    return FxTarget(
        book_code=BookCode.ASC606,
        entity=ENTITY,
        subject_key=CONTRACT_KEY,
        measure="loss_provision_required",
        part=None,
        balance_role=None,
        period_key=period,
        txn_currency="EUR",
        amount_txn=usd(txn),
        functional_currency="USD",
        amount_functional=usd(functional),
        rates=(RateRef("SPOT-EURUSD/EUR/USD/2026-02-28/", "SPOT-EURUSD@v1"),),
        node_id=f"fx_functional:{CONTRACT_KEY}:{period}",
    )


def _required(period: str, amount: str, measure: str = "loss_provision_required") -> Target:
    node = f"{measure}:{CONTRACT_KEY}:{period}"
    return Target(
        BookCode.ASC606, ENTITY, CONTRACT_KEY, measure, period, None, usd(amount), None, node
    )


def test_jet_12_part_target_is_a_time_amount_of_the_close_release_pass() -> None:
    """Table 14-A JET-12: the cumulative target is the required provision (S11-R-14), the whole of
    it ``TIME`` of the ``CLOSE_RELEASE`` pass (RCP-07 rev 1.2; S14-R-05); the role lines debit
    ``LOSS_EXPENSE`` and credit ``LOSS_PROVISION`` for an increase (POLICIES JET-12)."""
    ctx = book_context(bundles.entity(months=3), book_code="ASC606", currency="USD")
    inputs = PartInputs(
        loss_provisions=(_required("FY2026-P01", "0.00"), _required("FY2026-P02", "30000.00"))
    )
    parts = part_targets(ctx, _fx_state(), inputs)
    assert [(p.part, p.subject_key, p.period_key, p.amount_txn, p.time_txn) for p in parts] == [
        ("JET-12", CONTRACT_KEY, "FY2026-P01", 0, 0),
        ("JET-12", CONTRACT_KEY, "FY2026-P02", usd("30000.00"), usd("30000.00")),
    ]
    roles = role_targets(ctx, parts, TraceBuilder(engine_version=ENGINE_VERSION))
    assert sorted(
        (r.key.entry_kind, r.key.account_role, r.period_key, r.amount_txn, r.time_txn, r.passes)
        for r in roles
    ) == [
        (LOSS_PROVISION, EXPENSE, "FY2026-P01", 0, 0, (RELEASE,)),
        (LOSS_PROVISION, EXPENSE, "FY2026-P02", usd("30000.00"), usd("30000.00"), (RELEASE,)),
        (LOSS_PROVISION, EXPENSE, "FY2026-P03", usd("30000.00"), usd("30000.00"), (RELEASE,)),
        (LOSS_PROVISION, PROVISION, "FY2026-P01", 0, 0, (RELEASE,)),
        (LOSS_PROVISION, PROVISION, "FY2026-P02", -usd("30000.00"), -usd("30000.00"), (RELEASE,)),
        (LOSS_PROVISION, PROVISION, "FY2026-P03", -usd("30000.00"), -usd("30000.00"), (RELEASE,)),
    ]


def test_a_loss_target_of_another_measure_is_refused() -> None:
    ctx = book_context(bundles.entity(months=3), book_code="ASC606", currency="USD")
    inputs = PartInputs(loss_provisions=(_required("FY2026-P01", "1.00", "provision_movement"),))
    with pytest.raises(ValueError, match="CV-45"):
        part_targets(ctx, _fx_state(), inputs)


def test_jet_12_takes_the_stage_12_functional_amount_when_supplied() -> None:
    """S14-R-01: a foreign-currency JET-12 part carries the stage 12 functional amount of its
    measure, as every other part does (Codex's native control on aa902ac: a EUR 30,000.00 target
    with a matching USD 33,000.00 at 1.10 failed closed). The part and the role targets carry
    33,000.00 functional, all of it ``TIME``, with the pinned rate; the same-currency control
    converts at rate 1."""
    calendar = bundles.entity(months=3, functional_currency="USD")
    ctx = book_context(calendar, book_code="ASC606", currency="EUR")
    inputs = PartInputs(loss_provisions=(_required("FY2026-P02", "30000.00"),))
    fx = _fx_target("FY2026-P02", "30000.00", "33000.00")
    (part,) = part_targets(ctx, _fx_state(fx), inputs)
    assert (
        part.part,
        part.amount_txn,
        part.amount_functional,
        part.time_txn,
        part.time_functional,
        part.txn_currency,
        part.functional_currency,
        part.rates,
        part.node_ids,
    ) == (
        "JET-12",
        usd("30000.00"),
        usd("33000.00"),
        usd("30000.00"),
        usd("33000.00"),
        "EUR",
        "USD",
        fx.rates,
        (f"loss_provision_required:{CONTRACT_KEY}:FY2026-P02", fx.node_id),
    )
    roles = role_targets(ctx, (part,), TraceBuilder(engine_version=ENGINE_VERSION))
    assert sorted(
        (r.key.account_role, r.period_key, r.amount_txn, r.amount_functional, r.time_functional)
        for r in roles
    ) == [
        (EXPENSE, "FY2026-P02", usd("30000.00"), usd("33000.00"), usd("33000.00")),
        (EXPENSE, "FY2026-P03", usd("30000.00"), usd("33000.00"), usd("33000.00")),
        (PROVISION, "FY2026-P02", -usd("30000.00"), -usd("33000.00"), -usd("33000.00")),
        (PROVISION, "FY2026-P03", -usd("30000.00"), -usd("33000.00"), -usd("33000.00")),
    ]
    same = book_context(bundles.entity(months=3), book_code="ASC606", currency="USD")
    (control,) = part_targets(same, _fx_state(), inputs)
    assert (control.amount_functional, control.rates) == (usd("30000.00"), ())


def test_a_stage_12_amount_of_another_transaction_amount_is_refused() -> None:
    """S14-R-01: the stage 12 target must convert the part's own transaction amount."""
    calendar = bundles.entity(months=3, functional_currency="USD")
    ctx = book_context(calendar, book_code="ASC606", currency="EUR")
    inputs = PartInputs(loss_provisions=(_required("FY2026-P02", "30000.00"),))
    fx = _fx_target("FY2026-P02", "29000.00", "31900.00")
    with pytest.raises(EngineError, match="another transaction amount"):
        part_targets(ctx, _fx_state(fx), inputs)


def test_a_foreign_currency_loss_unit_fails_closed_without_a_stage_12_amount() -> None:
    """S14-R-01 / L3-2-Q-14: stage 12 publishes no functional amount for a loss provision (§12
    names no loss-provision flow), so a non-zero JET-12 target of a contracting entity whose
    functional currency differs from the transaction currency fails closed instead of posting at
    rate 1; a zero target passes. Residual limit recorded by lane ENG-C7 (no corpus key holds a
    loss unit in a foreign-currency entity)."""
    calendar = bundles.entity(months=3, functional_currency="EUR")
    ctx = book_context(calendar, book_code="ASC606", currency="USD")
    zero = PartInputs(loss_provisions=(_required("FY2026-P01", "0.00"),))
    assert [p.amount_functional for p in part_targets(ctx, _fx_state(), zero)] == [0]
    inputs = PartInputs(loss_provisions=(_required("FY2026-P01", "30000.00"),))
    with pytest.raises(EngineError, match="no functional amount"):
        part_targets(ctx, _fx_state(), inputs)


# --- EX-11-B / CHK-132 through compute and the CLOSE_RELEASE pass --------------------------------


def test_ex_11_b_provision_and_release_post_in_the_close_release_pass(tmp_path: Path) -> None:
    """LOSS-S7-LOSS-OWN: FY2027-P12 required 30,000.00 (total loss 100,000.00 less the 70,000.00
    through margin), FY2028-P12 released to nil (S11-R-14; CHK-132). Compute posts no JET-12 line
    of an open period (RCP-08(a)); the pass posts Dr LOSS_EXPENSE / Cr LOSS_PROVISION 30,000.00 in
    FY2027-P12 and the reverse in FY2028-P12, ``TIME``; T-CON-09 ``loss_provision_txn`` reads 0.00 /
    30,000.00 / 0.00."""
    path = _stand_in(LOSS_S7, S7_ID, S7_UNITS, tmp_path)
    subject = "C-LOSS@US01"
    command, released, book = _runs(path, "end-2026")
    assert (_loss_lines(command, book), _loss_lines(released, book)) == ([], [])
    assert _column(released, book, subject, "FY2026-P12") == 0
    command, released, book = _runs(path, "end-2027")
    assert _loss_lines(command, book) == []
    assert _loss_lines(released, book) == [
        ("FY2027-P12", "TIME", None, None, EXPENSE, usd("30000.00")),
        ("FY2027-P12", "TIME", None, None, PROVISION, -usd("30000.00")),
    ]
    assert _column(released, book, subject, "FY2027-P12") == usd("30000.00")
    assert _column(command, book, subject, "FY2027-P12") == usd(
        "30000.00"
    )  # the balance is compute's
    command, released, book = _runs(path, "end-2028")
    assert _loss_lines(command, book) == []
    assert _loss_lines(released, book) == [
        ("FY2027-P12", "TIME", None, None, EXPENSE, usd("30000.00")),
        ("FY2027-P12", "TIME", None, None, PROVISION, -usd("30000.00")),
        ("FY2028-P12", "TIME", None, None, EXPENSE, -usd("30000.00")),
        ("FY2028-P12", "TIME", None, None, PROVISION, usd("30000.00")),
    ]
    assert _column(released, book, subject, "FY2028-P12") == 0
    (intent,) = [
        i
        for i in _book(released, book).posting_intents
        if i.entry_kind == LOSS_PROVISION and i.posting_period_key == "FY2028-P12"
    ]
    assert (intent.subject_key, intent.posting_class) == ("C-LOSS", "TIME")  # the loss unit
    assert {line.dimensions["contract_key"] for line in intent.lines} == {"C-LOSS"}


def test_the_close_release_pass_is_idempotent_over_its_own_intents(tmp_path: Path) -> None:
    """RCP-06: every path posts "cumulative target minus posted", so a second CLOSE_RELEASE pass
    over the first pass's intents posts no JET-12 line."""
    path = _stand_in(LOSS_S7, S7_ID, S7_UNITS, tmp_path)
    bundle, book = _checkpoint(path, "end-2027")
    command = cast(OutputBundle, erev_engine.compute(bundle))
    with decimal.localcontext(DECIMAL_CONTEXT):
        first = intent_totals.close_pass(bundle, [command], RELEASE)
        second = intent_totals.close_pass(bundle, [command, first], RELEASE)
    assert len(_loss_lines(first, book)) == 2
    assert _loss_lines(second, book) == []


def test_ge_03_monthly_provision_release_as_loss_making_work_is_performed(tmp_path: Path) -> None:
    """LOSS-GE-03: required 100,000.00 at the September overrun, 50,000.00 at year end, 0.00 at
    completion (S11-R-14; POL-153): JET-12 posts +100,000.00 in FY2026-P09, then releases
    50,000.00 in FY2026-P12 and 50,000.00 in FY2027-P03 (CAD)."""
    path = _stand_in(GE_03, GE_03_ID, GE_03_UNITS, tmp_path)
    command, released, book = _runs(path, "complete")
    assert _loss_lines(command, book) == []
    assert _loss_lines(released, book) == [
        ("FY2026-P09", "TIME", None, None, EXPENSE, usd("100000.00")),
        ("FY2026-P09", "TIME", None, None, PROVISION, -usd("100000.00")),
        ("FY2026-P12", "TIME", None, None, EXPENSE, -usd("50000.00")),
        ("FY2026-P12", "TIME", None, None, PROVISION, usd("50000.00")),
        ("FY2027-P03", "TIME", None, None, EXPENSE, -usd("50000.00")),
        ("FY2027-P03", "TIME", None, None, PROVISION, usd("50000.00")),
    ]
    subject = "GE-03@GE-CA"
    assert [
        _column(released, book, subject, period)
        for period in ("FY2026-P06", "FY2026-P09", "FY2026-P12", "FY2027-P03")
    ] == [0, usd("100000.00"), usd("50000.00"), 0]


# --- POL-151 scope: the IFRS15 book only ----------------------------------------------------------


def test_pol_151_scope_provides_in_the_ifrs15_book_only(tmp_path: Path) -> None:
    """IFRS-SW11: the contract is not a Subtopic 605-35 contract, so the ASC606 book (POL-151
    ``SCOPED_605_35_ONLY``) measures no loss unit, reads ``loss_provision_txn`` 0 and posts no
    JET-12 line in compute or in the pass. The IFRS15 book (``ALL_CONTRACTS_WITH_EAC`` FORCED;
    IAS 37.66, 37.68A) provides 100,000.00 at the January period end (EAC 1,100,000.00 against
    1,000,000.00, nothing through margin yet) and releases 40,000.00 in June, when costs 440,000.00
    against revenue 400,000.00 carry 40,000.00 through margin: balance 60,000.00 (S11-R-14,
    S11-R-15; POLICIES §6.2 row 11)."""
    path = _stand_in(IFRS_SW11, SW11_ID, SW11_UNITS, tmp_path)
    subject = "C-IFRS-SW11@US01"
    command, released, _ = _runs(path, "ifrs15-june-close")
    assert (_loss_lines(command, "ASC606"), _loss_lines(released, "ASC606")) == ([], [])
    assert _column(released, "ASC606", subject, "FY2026-P06") == 0
    assert _book(command, "ASC606").loss_provision_versions == ()
    assert _loss_lines(command, "IFRS15") == []
    assert _loss_lines(released, "IFRS15") == [
        ("FY2026-P01", "TIME", None, None, EXPENSE, usd("100000.00")),
        ("FY2026-P01", "TIME", None, None, PROVISION, -usd("100000.00")),
        ("FY2026-P06", "TIME", None, None, EXPENSE, -usd("40000.00")),
        ("FY2026-P06", "TIME", None, None, PROVISION, usd("40000.00")),
    ]
    assert [_column(released, "IFRS15", subject, f"FY2026-P0{m}") for m in range(1, 7)] == [
        usd("100000.00"),
        usd("100000.00"),
        usd("100000.00"),
        usd("100000.00"),
        usd("100000.00"),
        usd("60000.00"),
    ]
    versions = _book(command, "IFRS15").loss_provision_versions
    assert {(v.columns["measurement_basis"], v.columns["unit"]) for v in versions} == {
        ("IAS_37", "CONTRACT")
    }


# --- Q-4 / AD-31: a foreign-currency contracting entity fails closed on a non-zero provision ------


def _foreign_currency(path: Path, books: Sequence[str]) -> Path:
    """The scratch world with entity US01 functional EUR against USD contracts, one USD→EUR rate
    set per E-51 type (spot 1 January; closing and average at every 2026 month end, all 0.9000)
    and the checkpoints of ``books`` only."""
    data = cast(dict[str, object], parse_yaml(path.read_text(encoding="utf-8"), path=path))
    data["books"] = list(books)
    world = cast(dict[str, object], data["world"])
    world["currencies"] = ["EUR", "USD"]
    (entity,) = cast(list[dict[str, object]], world["entities"])
    entity["functional_currency"] = "EUR"
    entity["books"] = list(books)
    ends = [f"2026-0{m}-{d}" for m, d in ((1, 31), (2, 28), (3, 31), (4, 30), (5, 31), (6, 30))]
    per_period = [
        {
            "base_currency": "USD",
            "quote_currency": "EUR",
            "effective_date": end,
            "period_key": f"FY2026-P0{index + 1}",
            "rate": "0.9000",
        }
        for index, end in enumerate(ends)
    ]
    world["fx_rate_sets"] = [
        {
            "code": "SPOT-USDEUR",
            "rate_type": "spot",
            "rates": [
                {
                    "base_currency": "USD",
                    "quote_currency": "EUR",
                    "effective_date": "2026-01-01",
                    "rate": "0.9000",
                }
            ],
        },
        {"code": "CLOSE-USDEUR", "rate_type": "closing", "rates": per_period},
        {"code": "AVG-USDEUR", "rate_type": "average", "rates": per_period},
    ]
    data["checkpoints"] = [
        checkpoint
        for checkpoint in cast(list[dict[str, object]], data["checkpoints"])
        if checkpoint["book"] in books
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def test_a_foreign_currency_contract_with_a_provision_fails_closed_at_compute(
    tmp_path: Path,
) -> None:
    """Supervisor ruling on ENG-C7 Q-4 (G12 AD-31): the fail-closed behaviour stands. The SW11
    world in a EUR-functional entity: the ASC606 book (no loss unit, POL-151) computes and reads
    ``loss_provision_txn`` 0 with every other flow converted, so the FX world itself is sound; the
    IFRS15 book, whose January provision is 100,000.00 USD, stops at stage 14 with
    ``ENGINE_INVARIANT_VIOLATED`` "stage 12 publishes no functional amount for a foreign-currency
    part target" naming the loss unit and ``loss_provision_required`` (S14-R-01; L3-2-Q-14), so no
    JET-12 line posts at rate 1 pending the AD-31 ruling on the remeasurement of the provision."""
    control = _foreign_currency(_stand_in(IFRS_SW11, SW11_ID, SW11_UNITS, tmp_path), ["ASC606"])
    bundle, book = _checkpoint(control, "asc606-june-close")
    output = cast(OutputBundle, erev_engine.compute(bundle))
    assert _column(output, book, "C-IFRS-SW11@US01", "FY2026-P06") == 0
    assert _book(output, book).loss_provision_versions == ()
    (row,) = [
        b
        for b in _book(output, book).balances
        if b.subject_key == "C-IFRS-SW11@US01" and b.period_key == "FY2026-P06"
    ]
    assert row.columns["functional_currency"] == "EUR"
    provided = _foreign_currency(_stand_in(IFRS_SW11, SW11_ID, SW11_UNITS, tmp_path), ["IFRS15"])
    bundle, book = _checkpoint(provided, "ifrs15-june-close")
    with pytest.raises(EngineError) as error:
        erev_engine.compute(bundle)
    assert error.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert "no functional amount for a foreign-currency part target" in str(error.value)
    assert error.value.subject_key == "C-IFRS-SW11"
    assert error.value.detail["measure"] == "loss_provision_required"
    assert error.value.detail["period_key"] == "FY2026-P01"


# --- RCP-08: a closed period carries at compute ---------------------------------------------------


def _with_closed(bundle: InputBundle, period_key: str, book_code: str) -> InputBundle:
    entities = []
    for entity in bundle.entities:
        periods = tuple(
            dataclasses.replace(
                period,
                states=tuple(
                    (book, "closed" if book == book_code else state)
                    for book, state in period.states
                ),
            )
            if period.period_key == period_key
            else period
            for period in entity.periods
        )
        entities.append(dataclasses.replace(entity, periods=periods))
    return dataclasses.replace(bundle, entities=tuple(entities))


def test_a_closed_period_carries_jet_12_at_compute_and_the_pass_skips_it(tmp_path: Path) -> None:
    """RCP-08: a computation posts JET-12 only as a closed-period carry. With FY2027-P12 closed,
    compute posts the 30,000.00 movement into FY2028-P01 with origin FY2027-P12 and reason
    LATE_EVENT as an EVENT amount (S14-R-04, S14-R-06); the CLOSE_RELEASE pass then posts nothing
    for it (the closed period is skipped, S14-R-05, and the carry counts as posted)."""
    path = _stand_in(LOSS_S7, S7_ID, S7_UNITS, tmp_path)
    bundle, book = _checkpoint(path, "end-2027")
    closed = _with_closed(bundle, "FY2027-P12", book)
    command = cast(OutputBundle, erev_engine.compute(closed))
    assert _loss_lines(command, book) == [
        ("FY2028-P01", "EVENT", "FY2027-P12", "LATE_EVENT", EXPENSE, usd("30000.00")),
        ("FY2028-P01", "EVENT", "FY2027-P12", "LATE_EVENT", PROVISION, -usd("30000.00")),
    ]
    with decimal.localcontext(DECIMAL_CONTEXT):
        released = intent_totals.close_pass(closed, [command], RELEASE)
    assert _loss_lines(released, book) == []


# --- The answer-key runner: compute, then the three close passes ---------------------------------


@pytest.mark.parametrize(
    ("source", "scratch_id", "units", "absent"),
    [
        (
            LOSS_S7,
            S7_ID,
            S7_UNITS,
            [
                "end-2027 subledger FY2027-P12 US01 LOSS_EXPENSE/5300 dr: expected 30000.00, "
                "actual <absent>",
                "end-2027 subledger FY2027-P12 US01 LOSS_PROVISION/2300 cr: expected 30000.00, "
                "actual <absent>",
                "end-2028 subledger FY2028-P12 US01 LOSS_EXPENSE/5300 cr: expected 30000.00, "
                "actual <absent>",
                "end-2028 subledger FY2028-P12 US01 LOSS_PROVISION/2300 dr: expected 30000.00, "
                "actual <absent>",
            ],
        ),
        (
            IFRS_SW11,
            SW11_ID,
            SW11_UNITS,
            [
                "ifrs15-june-close subledger FY2026-P06 US01 LOSS_EXPENSE/5300 cr: expected "
                "40000.00, actual <absent>",
                "ifrs15-june-close subledger FY2026-P06 US01 LOSS_PROVISION/2300 dr: expected "
                "40000.00, actual <absent>",
            ],
        ),
    ],
    ids=["LOSS-S7-LOSS-OWN", "IFRS-SW11"],
)
def test_runner_checkpoints_hold_through_the_close_release_pass(
    source: Path, scratch_id: str, units: Sequence[str], absent: Sequence[str], tmp_path: Path
) -> None:
    """The runner runs FX_REMEASUREMENT, CLOSE_RELEASE and NETTING_RECLASS over each checkpoint's
    compute intents (RCP-08; D-91 gaps (iii), ENG-D1), so the keys' JET-12 subledger lines and the
    ``loss_provision`` balances hold; with the CLOSE_RELEASE output dropped from every checkpoint
    the JET-12 lines are the only mismatches (the balance is compute's, the posting the pass's;
    JET-06 stays with the NETTING_RECLASS output)."""
    assert runners.CLOSE_PASSES == ("FX_REMEASUREMENT", RELEASE, "NETTING_RECLASS")
    loaded = load(_stand_in(source, scratch_id, units, tmp_path))
    result = runners.run_engine(loaded)
    runners.assert_checkpoints(loaded, result)
    without = dataclasses.replace(
        result,
        checkpoints=tuple(
            dataclasses.replace(
                run, passes=tuple((fx, reclass) for fx, _release, reclass in run.passes)
            )
            for run in result.checkpoints
        ),
    )
    with pytest.raises(runners.CheckpointMismatchError) as error:
        runners.assert_checkpoints(loaded, without)
    assert sorted(item.render() for item in error.value.mismatches) == [
        f"{scratch_id} {text}" for text in absent
    ]

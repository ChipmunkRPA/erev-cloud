"""Checkpoint assertions and the answer-key report (docs/dev-guide.md §9.5.6; §9.5.7 DG-AK-50 to
DG-AK-57; §9.5.8 DG-AK-43; BUILD_SPEC EKC-12).

The outputs are synthetic ``OutputBundle``s over the bundles EKC-11 assembles, because
``erev_engine.compute`` is built in END-9. Posted amounts are integer minor units (XR-03).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BalanceOut,
    BookOutput,
    ContractVersionOut,
    Diagnostic,
    IntentLine,
    ObligationVersionOut,
    OutputBundle,
    PostingIntent,
    ProposalOut,
)
from erev_engine.enums import ScheduleKind, ScheduleLineType
from erev_engine.stages.state import ScheduleLineOut
from erev_engine.trace import SourceRef, Trace, TraceNode
from support.answer_keys import report as answer_key_report
from support.answer_keys.loader import ANSWER_KEY_ROOT, AnswerKeyError, LoadedKey, load
from support.answer_keys.models import ContractBlock, ExceptionRow, SubledgerBlock
from support.answer_keys.report import KeyOutcome, build_report
from support.answer_keys.runners import (
    CheckpointMismatchError,
    CheckpointRun,
    Mismatch,
    RunResult,
    _build_checkpoint_bundles,
    _CheckpointComparison,
    _intent_contract,
    _render_grain,
    assert_checkpoints,
)

ASC606 = "ASC606"
RND = "RND-CHK-001"
ENT = "ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP"
RET = "RET-CHK-029-S3-EX22"
ONB = "ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION"
WITHDRAWN = "POS-S9-PRESENTATION-EX38-CASEA"


def _load(key_id: str) -> LoadedKey:
    return load(ANSWER_KEY_ROOT / key_id.split("-", 1)[0].lower() / f"{key_id}.yaml")


def _variant(tmp_path: Path, key_id: str, *replacements: tuple[str, str]) -> Path:
    """A copy of a corpus key under ``<tmp>/<family>/<id>.yaml`` with text replacements."""
    family = key_id.split("-", 1)[0].lower()
    text = (ANSWER_KEY_ROOT / family / f"{key_id}.yaml").read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new)
    path = tmp_path / family / f"{key_id}.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def _with_checkpoints(loaded: LoadedKey, *checkpoints: Any) -> LoadedKey:
    key = loaded.key.model_copy(update={"checkpoints": checkpoints})
    return LoadedKey(key, loaded.path, loaded.sha256)


def _group(loaded: LoadedKey) -> str:
    return _build_checkpoint_bundles(loaded)[0].bundles[0].group.group_key


def _node(subject_key: str, value: str, inputs: tuple[str, str]) -> TraceNode:
    """A posted ``tp_allocation_basis`` node over two source values (inputs[0] − inputs[1])."""
    return TraceNode(
        id=f"tp_allocation_basis:{subject_key}:-",
        measure="tp_allocation_basis",
        value=value,
        currency="USD",
        formula_id="sched.period_difference.v1",
        inputs=tuple(
            SourceRef("source_record", f"SRC-{index}", {"value": item})
            for index, item in enumerate(inputs)
        ),
        params={"minor_unit": "2"},
        rounding_residue="0",
        narrative_key="sched.period_difference",
    )


def _trace(*nodes: TraceNode) -> Trace:
    return Trace(format_version=1, engine_version=ENGINE_VERSION, nodes=nodes, root_measures={})


def _obligation(
    key: str, allocated: int, *, awaiting: int | None = None, exact: Fraction = Fraction(100, 3)
) -> ObligationVersionOut:
    columns = {
        "allocated_amount": allocated,
        "allocated_exact": exact,
        "revenue_cum": 0,
        "scheduled_amount": 0,
        "awaiting_trigger_amount": allocated if awaiting is None else awaiting,
    }
    return ObligationVersionOut(f"C-RND-1/{key}", columns, {})


def _version(group: str, **columns: object) -> ContractVersionOut:
    base = {
        "transaction_price": 10000,
        "consideration_payable_amount": 0,
        "expected_returns_amount": 0,
        "total_ssp": Fraction(300),
    }
    return ContractVersionOut(group, {**base, **columns}, {})


def _book(group: str, **changes: Any) -> BookOutput:
    """The RND-CHK-001 book that meets every expectation and DG-AK-54 identity."""
    book = BookOutput(
        book_code=ASC606,
        contract_version=_version(group),
        status_in_book=(("C-RND-1", "ACTIVE"),),
        obligation_versions=(
            _obligation("POB-001", 3334),
            _obligation("POB-002", 3333),
            _obligation("POB-003", 3333),
        ),
        balances=(),
        schedules=(),
        cost_asset_versions=(),
        loss_provision_versions=(),
        fx_layer_movements=(),
        posting_intents=(),
        proposals=(),
        time_triggers=(),
        trace=_trace(_node(group, "100.00", ("100.00", "0"))),
    )
    return dataclasses.replace(book, **changes)


def _empty_book(**changes: Any) -> BookOutput:
    book = BookOutput(ASC606, None, (), (), (), (), (), (), (), (), (), (), _trace())
    return dataclasses.replace(book, **changes)


def _run(
    loaded: LoadedKey, *books: BookOutput, diagnostics: tuple[Diagnostic, ...] = ()
) -> RunResult:
    """One output per checkpoint, each holding one book over the checkpoint's single bundle."""
    runs = []
    for checkpoint, book in zip(_build_checkpoint_bundles(loaded), books, strict=True):
        (bundle,) = checkpoint.bundles
        output = OutputBundle(ENGINE_VERSION, "0" * 64, (book,), diagnostics)
        runs.append(CheckpointRun(checkpoint, (output,)))
    return RunResult(loaded.key.id, loaded.key.runner, tuple(runs))


def _run_output(loaded: LoadedKey, output: OutputBundle) -> RunResult:
    """The first checkpoint only, with ``output`` for each of its bundles."""
    checkpoint = _build_checkpoint_bundles(loaded)[0]
    run = CheckpointRun(checkpoint, (output,) * len(checkpoint.bundles))
    return RunResult(loaded.key.id, loaded.key.runner, (run,))


def _mismatches(loaded: LoadedKey, result: RunResult) -> list[Mismatch]:
    try:
        assert_checkpoints(loaded, result)
    except CheckpointMismatchError as error:
        return list(error.mismatches)
    return []


def _line(
    role: str,
    side: str,
    txn: int,
    functional: int | None = None,
    *,
    contract_key: str | None = None,
) -> IntentLine:
    return IntentLine(
        line_key=f"{role}-{side}",
        side=side,
        account_role=role,
        clearing_purpose=None,
        counterparty_entity=None,
        account_code="",
        amount_txn=txn,
        amount_functional=txn if functional is None else functional,
        txn_currency="USD",
        functional_currency="USD",
        dimensions={} if contract_key is None else {"contract_key": contract_key},
        source_event_key=None,
        trace_node_id="-",
    )


def _intent(
    entry_key: str,
    *lines: IntentLine,
    subject_key: str = "C-RND-1/POB-001",
    entry_kind: str = "RECOGNITION",
) -> PostingIntent:
    return PostingIntent(
        entry_key=entry_key,
        book_code=ASC606,
        entity="US01",
        posting_period_key="FY2026-P01",
        origin_period_key=None,
        entry_kind=entry_kind,
        posting_class="TIME",
        subject_key=subject_key,
        reason_code=None,
        lines=lines,
    )


def test_money_places(tmp_path: Path) -> None:
    rnd = _load(RND)
    group = _group(rnd)
    assert _mismatches(rnd, _run(rnd, _book(group))) == []

    billed = 'total_ssp: "300"}'
    loaded = load(
        _variant(tmp_path / "a", RND, (billed, 'total_ssp: "300", billed_cum: "322.10"}'))
    )
    ok = _book(group, contract_version=_version(group, billed_cum=32210))
    assert _mismatches(loaded, _run(loaded, ok)) == []
    off = _book(group, contract_version=_version(group, billed_cum=32211))
    assert [
        (m.subject, m.field, m.expected, m.actual) for m in _mismatches(loaded, _run(loaded, off))
    ] == [("contract C-RND-1", "billed_cum", "322.10", "322.11")]
    with pytest.raises(
        AnswerKeyError, match=r"322\.1 has 1 decimal places; USD has 2 \(DG-AK-51\)"
    ):
        load(_variant(tmp_path / "b", RND, (billed, 'total_ssp: "300", billed_cum: "322.1"}')))

    # Inside `functional` the places are those of the entity functional currency (JPY: 0).
    def balances(functional: str) -> tuple[tuple[str, str], ...]:
        return (
            ('functional_currency: "USD"', 'functional_currency: "JPY"'),
            ('currencies: ["USD"]', 'currencies: ["JPY", "USD"]'),
            (
                billed,
                billed + "\n        balances:\n          - {entity: US01, contract_liability: "
                f'"322.10", functional: {{contract_liability: "{functional}"}}}}',
            ),
        )

    jpy = load(_variant(tmp_path / "c", RND, *balances("322")))
    row = BalanceOut(
        "C-RND-1@US01",
        "FY2026-P01",
        {"contract_liability_txn": 32210, "contract_liability_functional": 322},
        {},
    )
    assert _mismatches(jpy, _run(jpy, _book(group, balances=(row,)))) == []
    with pytest.raises(AnswerKeyError, match=r"322\.10 has 2 decimal places; JPY has 0"):
        load(_variant(tmp_path / "d", RND, *balances("322.10")))


def test_exact_values_rounded_to_expected_places(tmp_path: Path) -> None:
    exact = ('allocated_exact: "33.333333", awaiting', 'allocated_exact: "0.4", awaiting')
    loaded = load(_variant(tmp_path / "a", RND, exact))
    group = _group(loaded)

    def book(value: str) -> BookOutput:
        ratio = Fraction(Decimal(value))
        obligations = (
            _obligation("POB-001", 3334, exact=ratio),
            _obligation("POB-002", 3333, exact=ratio),
            _obligation("POB-003", 3333, exact=ratio),
        )
        return _book(group, obligation_versions=obligations)

    assert _mismatches(loaded, _run(loaded, book("0.40000001"))) == []
    assert _mismatches(loaded, _run(loaded, book("0.44999999"))) == []
    fields = [(m.subject, m.field) for m in _mismatches(loaded, _run(loaded, book("0.45")))]
    assert fields == [(f"obligation C-RND-1/POB-00{n}", "allocated_exact") for n in (1, 2, 3)]

    def rate_key(tmp: Path, rate: str) -> Path:
        rates = (
            "fx_rate_sets:\n    - {code: FX-1, rate_type: spot, rates: [{base_currency: EUR, "
            f'quote_currency: USD, effective_date: "2026-01-01", rate: "{rate}"}}]}}'
        )
        return _variant(
            tmp,
            RND,
            ("fx_rate_sets: []", rates),
            ('currencies: ["USD"]', 'currencies: ["EUR", "USD"]'),
        )

    load(rate_key(tmp_path / "b", "1.084500000001"))
    with pytest.raises(
        AnswerKeyError, match=r"13 decimal places; a rate has at most 12 \(DG-AK-52\)"
    ):
        load(rate_key(tmp_path / "c", "1.0845000000001"))


def _identity_fields(loaded: LoadedKey, book: BookOutput) -> list[str]:
    fields = {m.field for m in _mismatches(loaded, _run(loaded, book))}
    return sorted(field for field in fields if field.startswith("DG-AK-54"))


def test_implicit_assertions() -> None:
    rnd = _load(RND)
    group = _group(rnd)
    assert _identity_fields(rnd, _book(group)) == []

    low_basis = _book(group, trace=_trace(_node(group, "99.99", ("99.99", "0"))))
    assert _identity_fields(rnd, low_basis) == [
        "DG-AK-54 sum allocated_amount - expected_returns_amount = tp_allocation_basis"
    ]

    payable = _book(group, contract_version=_version(group, consideration_payable_amount=-100))
    assert _identity_fields(rnd, payable) == [
        "DG-AK-54 sum allocated_amount = transaction_price - consideration_payable_amount"
    ]

    obligations = (
        _obligation("POB-001", 3334),
        _obligation("POB-002", 3333, awaiting=3332),
        _obligation("POB-003", 3333),
    )
    assert _identity_fields(rnd, _book(group, obligation_versions=obligations)) == [
        "DG-AK-54 allocated_amount = revenue_cum + scheduled_amount + awaiting_trigger_amount"
    ]

    unbalanced = _intent("E-1", _line("CONTRACT_LIABILITY", "D", 100), _line("REVENUE", "C", 99))
    (mismatch,) = [
        m
        for m in _mismatches(rnd, _run(rnd, _book(group, posting_intents=(unbalanced,))))
        if m.field == "DG-AK-54 debits = credits (transaction)"
    ]
    assert (mismatch.subject, mismatch.expected, mismatch.actual) == (
        "journal US01 ASC606 USD FY2026-P01",
        "1.00",
        "0.99",
    )
    assert _identity_fields(rnd, _book(group, posting_intents=(unbalanced,))) == [
        "DG-AK-54 debits = credits (functional)",
        "DG-AK-54 debits = credits (transaction)",
    ]

    stale = _book(group, trace=_trace(_node(group, "100.00", ("100.00", "1.00"))))
    assert _identity_fields(rnd, stale) == ["DG-AK-54 reevaluate(trace)"]

    # D-79: the basis is Σ allocated_amount − expected_returns_amount (Σ a_posted; S04-R-02).
    february = next(c for c in _load(RET).key.checkpoints if c.name == "end-of-february")
    ret = _with_checkpoints(
        _load(RET), february.model_copy(update={"contracts": None, "subledger": None})
    )
    ret_group = _group(ret)

    def returns_book(node_value: str) -> BookOutput:
        version = ContractVersionOut(
            ret_group,
            {
                "transaction_price": 970000,
                "expected_returns_amount": -30000,
                "consideration_payable_amount": 0,
            },
            {},
        )
        obligation = ObligationVersionOut(
            "C-RET/L1-PROD",
            {
                "allocated_amount": 970000,
                "revenue_cum": 970000,
                "scheduled_amount": 0,
                "awaiting_trigger_amount": 0,
            },
            {},
        )
        return _book(
            ret_group,
            contract_version=version,
            status_in_book=(("C-RET", "ACTIVE"),),
            obligation_versions=(obligation,),
            trace=_trace(_node(ret_group, node_value, (node_value, "0"))),
        )

    assert _identity_fields(ret, returns_book("10000.00")) == []
    found = _mismatches(ret, _run(ret, returns_book("9999.99")))
    assert [(m.subject, m.field, m.expected, m.actual) for m in found] == [
        (
            f"group {ret_group} book ASC606",
            "DG-AK-54 sum allocated_amount - expected_returns_amount = tp_allocation_basis",
            "9999.99",
            "10000.00",
        )
    ]


def test_mismatches_collected_before_failing(tmp_path: Path) -> None:
    billed = ('total_ssp: "300"}', 'total_ssp: "300", billed_cum: "5.00"}')
    loaded = load(_variant(tmp_path, RND, billed))
    first = loaded.key.checkpoints[0]
    second = first.model_copy(update={"name": "second-look", "as_of": "2026-01-02"})
    variant = _with_checkpoints(loaded, first, second)
    group = _group(variant)

    with pytest.raises(CheckpointMismatchError) as caught:
        assert_checkpoints(variant, _run(variant, _book(group), _book(group)))
    found = [
        (m.key_id, m.checkpoint, m.subject, m.field, m.expected, m.actual)
        for m in caught.value.mismatches
    ]
    assert found == [
        (RND, "after-activation", "contract C-RND-1", "billed_cum", "5.00", "<absent>"),
        (RND, "second-look", "contract C-RND-1", "billed_cum", "5.00", "<absent>"),
    ]
    message = str(caught.value)
    for name in ("after-activation", "second-look"):
        assert (
            f"{RND} {name} contract C-RND-1 billed_cum: expected 5.00, actual <absent>" in message
        )


def test_subledger_aggregation() -> None:
    rnd = _load(RND)
    group = _group(rnd)

    def keyed(*blocks: dict[str, Any]) -> LoadedKey:
        checkpoint = rnd.key.checkpoints[0].model_copy(
            update={
                "as_of": "2026-01-31",
                "subledger": tuple(SubledgerBlock.model_validate(block) for block in blocks),
            }
        )
        return _with_checkpoints(rnd, checkpoint)

    def block(match: str, *lines: dict[str, str]) -> dict[str, Any]:
        return {
            "period_key": "FY2026-P01",
            "entity": "US01",
            "match": match,
            "grain": "role",
            "lines": list(lines),
        }

    fx = (
        _intent("E-1", _line("FX_GAIN_LOSS", "C", 0, 1500), _line("CONTRACT_ASSET", "D", 0, 1500)),
        _intent("E-2", _line("FX_GAIN_LOSS", "D", 0, 500), _line("CONTRACT_ASSET", "C", 0, 500)),
    )
    netting = (
        _intent("E-3", _line("REVENUE", "D", 1000), _line("CONTRACT_LIABILITY", "C", 1000)),
        _intent("E-4", _line("REVENUE", "C", 1000), _line("CONTRACT_LIABILITY", "D", 1000)),
    )
    gain = {"account_role": "FX_GAIN_LOSS", "cr": "0.00", "functional_cr": "10.00"}
    asset = {"account_role": "CONTRACT_ASSET", "dr": "0.00", "functional_dr": "10.00"}
    book = _book(group, posting_intents=fx + netting)

    # A functional-only line matches the net functional amount; zero-net keys are omitted.
    assert _mismatches(keyed(block("subset", gain)), _run(rnd, book)) == []
    assert _mismatches(keyed(block("exact", gain, asset)), _run(rnd, book)) == []
    wrong = dict(gain, functional_cr="12.00")
    assert [
        (m.field, m.expected, m.actual)
        for m in _mismatches(keyed(block("subset", wrong)), _run(rnd, book))
    ] == [("functional_cr", "12.00", "cr 10.00")]
    only_gain = _mismatches(keyed(block("exact", gain)), _run(rnd, book))
    assert [(m.subject, m.field, m.expected) for m in only_gain] == [
        ("subledger FY2026-P01 US01 CONTRACT_ASSET", "line", "<absent>")
    ]

    # `match: exact` with `lines: []` asserts that nothing posted.
    nothing = keyed(block("exact"))
    assert _mismatches(nothing, _run(rnd, _book(group, posting_intents=netting))) == []
    posted = _mismatches(nothing, _run(rnd, book))
    assert sorted(m.subject for m in posted) == [
        "subledger FY2026-P01 US01 CONTRACT_ASSET",
        "subledger FY2026-P01 US01 FX_GAIN_LOSS",
    ]


# D-90 (RET-BR-03): the subledger block `contract` filter under `runner: engine` (§9.5.6).


def _block(contract: str | None, *lines: dict[str, str], grain: str = "role") -> SubledgerBlock:
    return SubledgerBlock.model_validate(
        {
            "period_key": "FY2026-P01",
            "entity": "US01",
            "match": "exact",
            **({} if contract is None else {"contract": contract}),
            "grain": grain,
            "lines": list(lines),
        }
    )


def _keyed(loaded: LoadedKey, *blocks: SubledgerBlock) -> LoadedKey:
    """The first checkpoint, as of 2026-01-31, holding only ``blocks``."""
    checkpoint = loaded.key.checkpoints[0].model_copy(
        update={
            "as_of": "2026-01-31",
            "contracts": None,
            "subledger": blocks,
            "exceptions": None,
            "groups": None,
        }
    )
    return _with_checkpoints(loaded, checkpoint)


def _refund(entry_key: str, subject_key: str, amount: int, *owners: str | None) -> PostingIntent:
    """A JET-04b entry (Dr CONTRACT_LIABILITY, Cr REFUND_LIABILITY); ``owners`` are the line
    ``contract_key`` values: one for both lines, or the debit's and the credit's."""
    debit, credit = owners if len(owners) == 2 else owners * 2
    return _intent(
        entry_key,
        _line("CONTRACT_LIABILITY", "D", amount, contract_key=debit),
        _line("REFUND_LIABILITY", "C", amount, contract_key=credit),
        subject_key=subject_key,
        entry_kind="REFUND_LIABILITY",
    )


def _refund_lines(amount: str) -> tuple[dict[str, str], dict[str, str]]:
    return (
        {"account_role": "CONTRACT_LIABILITY", "dr": amount},
        {"account_role": "REFUND_LIABILITY", "cr": amount},
    )


def _group_book(group: str, *intents: PostingIntent) -> BookOutput:
    """A combined-group book: a zero basis meets DG-AK-54 (D-79)."""
    return _empty_book(
        contract_version=_version(group, transaction_price=0),
        trace=_trace(_node(group, "0.00", ("0.00", "0"))),
        posting_intents=intents,
    )


def _found(loaded: LoadedKey, result: RunResult) -> list[tuple[str, str, str, str]]:
    return [(m.subject, m.field, m.expected, m.actual) for m in _mismatches(loaded, result)]


def _unattributed(contract: str, intent: PostingIntent) -> tuple[str, str, str, str]:
    subject = f"subledger FY2026-P01 US01 {contract} entry {intent.entry_key} {intent.subject_key}"
    return (subject, "contract", contract, "<unattributed>")


@pytest.mark.parametrize(
    "source",
    [
        "RETURN/C-RND-1/POB-001",
        "VARIABLE_CONSIDERATION/C-RND-1/VC-001",
        "TERMINATION/C-RND-1/EV-000009",
        "CONCESSION/C-RND-1/EV-000009/C-RND-1/POB-001",
    ],
)
def test_subledger_contract_filter_keeps_refund_component_entries(source: str) -> None:
    """Stage 14 posts JET-04b per refund component on the key `<group>@<entity>/<KIND>/<source>`
    (L2-4-Q-15) with lines carrying `contract_key`: the member's block keeps the entry. The
    head-only attribution read `CG-C-RND-1@US01` and dropped it (dr and cr <absent>)."""
    rnd = _load(RND)
    group = _group(rnd)
    loaded = _keyed(rnd, _block("C-RND-1", *_refund_lines("20.00")))
    intent = _refund("E-1", f"{group}@US01/{source}", 2000, "C-RND-1")
    assert _found(loaded, _run(loaded, _book(group, posting_intents=(intent,)))) == []


def test_subledger_contract_filter_combined_group() -> None:
    """In combination group G-ENT-01 an entry belongs to the member its lines' `contract_key`
    names. The engine sets no `contract_key` on a component key of a multi-member group
    (s14 assign.subject_contracts returns every member), so that entry fails closed: one
    `contract` mismatch in each member's block, never a silent drop."""
    ent = _load(ENT)
    group = _group(ent)
    a_block = _block("C-ENT-A", *_refund_lines("10.00"))
    b_block = _block("C-ENT-B", *_refund_lines("5.00"))
    loaded = _keyed(ent, a_block, b_block)
    (bundle,) = _build_checkpoint_bundles(loaded)[0].bundles
    assert (group, bundle.group.member_contract_keys) == ("G-ENT-01", ("C-ENT-A", "C-ENT-B"))
    a = _refund("E-A", f"{group}@US01/RETURN/C-ENT-A/POB-A", 1000, "C-ENT-A")
    b = _refund("E-B", f"{group}@US01/VARIABLE_CONSIDERATION/C-ENT-B/VC-B", 500, "C-ENT-B")
    assert _found(loaded, _run(loaded, _group_book(group, a, b))) == []
    undimensioned = _refund("E-U", f"{group}@US01/RETURN/C-ENT-A/POB-A", 300, None)
    assert _found(loaded, _run(loaded, _group_book(group, a, b, undimensioned))) == [
        _unattributed("C-ENT-A", undimensioned),
        _unattributed("C-ENT-B", undimensioned),
    ]


def test_subledger_contract_filter_group_code_equal_to_member_id(tmp_path: Path) -> None:
    """With `combination_group: C-ENT-A`, engine assign.subject_contracts matches the component key
    `C-ENT-A@US01/…` as contract C-ENT-A whatever its source. A source naming C-ENT-B contradicts
    that `contract_key`, so the entry fails closed; a component head equal to the group code names
    no contract, so B's own entry belongs to B."""
    variant = load(_variant(tmp_path, ENT, ("G-ENT-01", "C-ENT-A")))
    group = _group(variant)
    loaded = _keyed(
        variant,
        _block("C-ENT-A", *_refund_lines("10.00")),
        _block("C-ENT-B", *_refund_lines("5.00")),
    )
    (bundle,) = _build_checkpoint_bundles(loaded)[0].bundles
    assert (group, bundle.group.member_contract_keys) == ("C-ENT-A", ("C-ENT-A", "C-ENT-B"))
    a = _refund("E-A", "C-ENT-A@US01/RETURN/C-ENT-A/POB-A", 1000, "C-ENT-A")
    b = _refund("E-B", "C-ENT-A@US01/VARIABLE_CONSIDERATION/C-ENT-B/VC-B", 500, "C-ENT-B")
    wrong = _refund("E-W", "C-ENT-A@US01/RETURN/C-ENT-B/POB-B", 300, "C-ENT-A")
    assert _found(loaded, _run(loaded, _group_book(group, a, b, wrong))) == [
        _unattributed("C-ENT-A", wrong),
        _unattributed("C-ENT-B", wrong),
    ]


@pytest.mark.parametrize(
    "subject",
    [
        "C-OTHER/POB-001",
        "C-OTHER@US01",
        "{group}@US01/RETURN/C-OTHER/POB-001",
        "CG-C-OTHER@US01/RETURN/C-RND-1/POB-001",
    ],
)
def test_subledger_contract_filter_non_member_head_in_singleton_group(subject: str) -> None:
    """In singleton group CG-C-RND-1 the engine names the sole member as `contract_key` for every
    subject (assign.py every-member fallback). A subject or component source naming another
    contract, or a component head other than the group code, contradicts it: the entry fails
    closed. The head-only attribution dropped these entries silently."""
    rnd = _load(RND)
    group = _group(rnd)
    loaded = _keyed(rnd, _block("C-RND-1"))
    intent = _refund("E-1", subject.format(group=group), 2000, "C-RND-1")
    assert _found(loaded, _run(loaded, _book(group, posting_intents=(intent,)))) == [
        _unattributed("C-RND-1", intent)
    ]


def test_subledger_contract_filter_group_at_entity_fx_remeasurement() -> None:
    """An FX_REMEASUREMENT entry on the group and entity subject `<group>@<entity>` (CV-21) names
    no contract. In a singleton group its lines carry the sole member and the member's block keeps
    the functional-only lines; in a multi-member group they carry no `contract_key` and the entry
    fails closed. The head-only attribution dropped both."""

    def remeasurement(subject: str, owner: str | None) -> PostingIntent:
        return _intent(
            "E-FX",
            _line("FX_GAIN_LOSS", "C", 0, 1500, contract_key=owner),
            _line("CONTRACT_ASSET", "D", 0, 1500, contract_key=owner),
            subject_key=subject,
            entry_kind="FX_REMEASUREMENT",
        )

    rnd = _load(RND)
    group = _group(rnd)
    gain = {"account_role": "FX_GAIN_LOSS", "cr": "0.00", "functional_cr": "15.00"}
    asset = {"account_role": "CONTRACT_ASSET", "dr": "0.00", "functional_dr": "15.00"}
    singleton = _keyed(rnd, _block("C-RND-1", gain, asset))
    intent = remeasurement(f"{group}@US01", "C-RND-1")
    assert _found(singleton, _run(singleton, _book(group, posting_intents=(intent,)))) == []

    ent = _load(ENT)
    ent_group = _group(ent)
    combined = _keyed(ent, _block("C-ENT-A"))
    intent = remeasurement(f"{ent_group}@US01", None)
    assert _found(combined, _run(combined, _group_book(ent_group, intent))) == [
        _unattributed("C-ENT-A", intent)
    ]


def test_subledger_contract_filter_mixed_and_missing_dimensions_fail_closed() -> None:
    """An entry whose lines carry different `contract_key` values, or carry it on some lines or on
    none, cannot be attributed. subledger() reports it once per period, entity and contract however
    many blocks name that contract; aggregate() records nothing, so calling it before mismatches()
    adds no duplicate."""
    rnd = _load(RND)
    group = _group(rnd)
    blocks = (_block("C-RND-1"), _block("C-RND-1", grain="role_account"))
    loaded = _keyed(rnd, *blocks)
    intents = (
        _refund("E-MIXED", "C-RND-1/POB-001", 1000, "C-RND-1", "C-OTHER"),
        _refund("E-PARTIAL", "C-RND-1/POB-001", 1000, "C-RND-1", None),
        _refund("E-NONE", "C-RND-1/POB-001", 1000, None),
    )
    run = _run(loaded, _book(group, posting_intents=intents)).checkpoints[0]
    comparison = _CheckpointComparison(loaded.key, loaded.key.checkpoints[0], run)
    assert comparison.aggregate(blocks[0], False) == {}
    assert comparison.found == []
    found = [(m.subject, m.field, m.expected, m.actual) for m in comparison.mismatches()]
    assert found == [_unattributed("C-RND-1", intent) for intent in intents]


def test_intent_contract_decodes_cv21_delimiters() -> None:
    """`contract_key` and member ids are raw external ids; subject keys are CV-21 encoded (`%2F`,
    `%40`, `%23`, `%3A`, `%25`) and split on their delimiters before decoding."""
    raw, encoded = "C/1@A#B:%", "C%2F1%40A%23B%3A%25"
    members = (raw, "C-2")

    def owner(subject: str, contract_key: str = raw) -> str | None:
        return _intent_contract(_refund("E-1", subject, 1, contract_key), "G/1", members)

    for subject in (
        f"{encoded}/POB %231",
        f"{encoded}/POB %231#FIXED",
        f"{encoded}@US01",
        f"{encoded}/COST/EV-000003",
        f"G%2F1@US01/RETURN/{encoded}/POB %231",
        f"G%2F1@US01/CONCESSION/{encoded}/EV-000009/{encoded}/POB %231",
        "G%2F1@US01",
    ):
        assert owner(subject) == raw, subject
    assert owner("C%2F1@US01") is None  # names contract "C/1", not a member
    assert owner("G%2F1@US01/RETURN/C-2/POB-1") is None  # the source names another member
    assert owner(f"{encoded}/POB %231", "C/1") is None  # a raw prefix is not a member
    assert owner(f"{encoded}/POB %231", encoded) is None  # the encoded form is not the raw id


def test_subledger_unfiltered_totals_unchanged() -> None:
    """A block without `contract` sums every entry of its period and entity, attributable or not,
    and records no mismatch. The member's block of a singleton group sums the attributable entries;
    the head-only attribution kept only `C-RND-1/…` and `C-RND-1@…` subjects."""
    rnd = _load(RND)
    group = _group(rnd)
    subjects = (
        f"{group}@US01/RETURN/C-RND-1/POB-001",
        f"{group}@US01/VARIABLE_CONSIDERATION/C-RND-1/VC-001",
        f"{group}@US01/TERMINATION/C-RND-1/EV-000009",
        f"{group}@US01/CONCESSION/C-RND-1/EV-000009/C-RND-1/POB-001",
        "C-RND-1/POB-001",
        "C-RND-1@US01",
        f"{group}@US01",
    )
    intents = [_refund(f"E-{n}", s, 1000 + n, "C-RND-1") for n, s in enumerate(subjects)]
    intents += [
        _refund("E-OTHER", "C-RND-1/POB-001", 2000, "C-OTHER"),
        _refund("E-NONE", f"{group}@US01", 3000, None),
    ]
    unfiltered, filtered = _block(None), _block("C-RND-1")
    loaded = _keyed(rnd, unfiltered, filtered)
    run = _run(loaded, _book(group, posting_intents=tuple(intents))).checkpoints[0]
    comparison = _CheckpointComparison(loaded.key, loaded.key.checkpoints[0], run)

    def totals(block: SubledgerBlock) -> dict[str, tuple[Fraction, Fraction]]:
        found = comparison.aggregate(block, False)
        return {_render_grain(grain): (net.txn, net.functional) for grain, net in found.items()}

    every, member = Fraction(12021, 100), Fraction(7021, 100)
    assert totals(unfiltered) == {
        "CONTRACT_LIABILITY": (every, every),
        "REFUND_LIABILITY": (-every, -every),
    }
    assert totals(filtered) == {
        "CONTRACT_LIABILITY": (member, member),
        "REFUND_LIABILITY": (-member, -member),
    }
    assert comparison.found == []


def test_subledger_contract_filter_concession_conflicting_subject_fails_closed() -> None:
    """A CONCESSION component source is `<event key>/<subject key>` (refund_liability.py
    `_concessions`): the global event key `<contract>/EV-<n>`, then the obligation subject key
    `<contract>/<obligation>`. Both name a contract. Lines carrying C-ENT-A on the source
    `C-ENT-A/EV-000009/C-ENT-B/POB-B` contradict the subject contract C-ENT-B, so the entry fails
    closed and is reported once per contract, however many blocks name it. faf425a read only the
    event key contract and counted the entry in C-ENT-A's blocks."""
    ent = _load(ENT)
    group = _group(ent)
    blocks = (_block("C-ENT-A"), _block("C-ENT-A", grain="role_account"), _block("C-ENT-B"))
    loaded = _keyed(ent, *blocks)
    subject = f"{group}@US01/CONCESSION/C-ENT-A/EV-000009/C-ENT-B/POB-B"
    conflicting = _refund("E-C", subject, 700, "C-ENT-A")
    assert _found(loaded, _run(loaded, _group_book(group, conflicting))) == [
        _unattributed("C-ENT-A", conflicting),
        _unattributed("C-ENT-B", conflicting),
    ]


def test_subledger_contract_filter_same_contract_concession_attributed() -> None:
    """A CONCESSION entry whose event key and obligation subject both name the contract its lines
    carry belongs to that member's block and to no other member's block."""
    ent = _load(ENT)
    group = _group(ent)
    loaded = _keyed(ent, _block("C-ENT-A", *_refund_lines("7.00")), _block("C-ENT-B"))
    subject = f"{group}@US01/CONCESSION/C-ENT-A/EV-000009/C-ENT-A/POB-A"
    concession = _refund("E-C", subject, 700, "C-ENT-A")
    assert _found(loaded, _run(loaded, _group_book(group, concession))) == []


def test_intent_contract_concession_encoded_contracts_split_before_decoding() -> None:
    """Contract external ids holding `/`, `@`, `#` and `%` are CV-21 encoded in the event key and in
    the obligation subject of a CONCESSION source. The key splits on its delimiters before any
    component is decoded, so a decoded `/` or `@` never opens another component."""
    raw, encoded = "C/1@A#B:%", "C%2F1%40A%23B%3A%25"
    nested, nested_encoded = "C-2/EV-000009/C-2", "C-2%2FEV-000009%2FC-2"
    members = (raw, "C-2", nested)

    def owner(source: str, contract_key: str = raw) -> str | None:
        subject = f"G%2F1@US01/CONCESSION/{source}"
        return _intent_contract(_refund("E-1", subject, 1, contract_key), "G/1", members)

    assert owner(f"{encoded}/EV-000009/{encoded}/POB %231") == raw
    assert owner(f"{encoded}/EV-000009/{encoded}@US01") == raw
    assert owner(f"{encoded}/EV-000009/C-2/POB-1") is None  # the subject names C-2
    assert owner(f"{encoded}/EV-000009/C-2@US01") is None
    assert owner(f"C-2/EV-000009/{encoded}/POB-1") is None  # the event key names C-2
    assert owner(f"{encoded}/EV-000009/C%2F1/POB-1") is None  # names contract "C/1"
    assert owner(f"{nested_encoded}/EV-000001/{nested_encoded}/POB-1", nested) == nested
    # Decoded before splitting, this source would read `C-2/EV-000009/C-2/POB-1`, a concession
    # naming C-2 twice; split first it is one contract component and an obligation, no event key.
    assert owner(f"{nested_encoded}/POB-1", "C-2") is None
    assert owner(f"{nested_encoded}/POB-1", nested) is None


def test_intent_contract_refund_component_grammar_names_its_contracts() -> None:
    """Every refund component kind with a producer names the contracts of its source grammar
    (refund_liability.py `_key`): RETURN and VARIABLE_CONSIDERATION `<contract>/<obligation or
    element>`, TERMINATION `<contract>/EV-<n>`, CONCESSION
    `<contract>/EV-<n>/<contract>/<obligation>` or `<contract>/EV-<n>/<contract>@<entity>`."""
    members = ("C-A", "C-B")

    def owner(subject: str, contract_key: str) -> str | None:
        return _intent_contract(_refund("E-1", subject, 1, contract_key), "G", members)

    for source in (
        "RETURN/C-A/POB-001",
        "VARIABLE_CONSIDERATION/C-A/VC-001",
        "TERMINATION/C-A/EV-000009",
        "TERMINATION/C-A/EV-1000000",
        "CONCESSION/C-A/EV-000009/C-A/POB-001",
        "CONCESSION/C-A/EV-000009/C-A@US01",
    ):
        assert owner(f"G@US01/{source}", "C-A") == "C-A", source
        assert owner(f"G@US01/{source}", "C-B") is None, source


@pytest.mark.parametrize(
    "subject",
    [
        "G@US01/RETURN/C-A/POB-001/C-B",
        "G@US01/RETURN/C-A",
        "G@US01/RETURN/C-A#FIXED/POB-001",
        "G@US01/RETURN/C-A/POB:001",
        "G@US01/RETURN/C-A/POB%2G",
        "G@US01/VARIABLE_CONSIDERATION/C-A/VC-001/C-B/VC-002",
        "G@US01/VARIABLE_CONSIDERATION/C-A",
        "G@US01/TERMINATION/C-A/EV-000009/C-B/POB-001",
        "G@US01/TERMINATION/C-A/POB-001",
        "G@US01/TERMINATION/C-A/EV-9",
        "G@US01/CONCESSION/C-A/EV-000009/C-B/POB-001",
        "G@US01/CONCESSION/C-A/EV-000009/C-B@US01",
        "G@US01/CONCESSION/C-A/EV-000009/C-A",
        "G@US01/CONCESSION/C-A/POB-001/C-A/POB-001",
        "G@US01/CONCESSION/C-A/EV-000009/C-A/POB-001/C-B",
        "G@US01/CONCESSION/C-A/EV-000009/C-A@US01@C-B",
        "G@US01/UNCLAIMED_PROPERTY/C-A/POB-001",
        "G@US01/OTHER/C-A/POB-001",
        "G@US01/RETURN",
        "G@US01#X/RETURN/C-A/POB-001",
        "G@US01@C-B/RETURN/C-A/POB-001",
        "G@/RETURN/C-A/POB-001",
    ],
)
def test_intent_contract_refund_component_outside_its_grammar_fails_closed(subject: str) -> None:
    """A refund component key whose head or source does not match the grammar of its kind names
    nothing attributable, so the entry fails closed even though its lines carry a member and the
    leading source component names that member. faf425a accepted each of these subjects."""
    members = ("C-A", "C-B")
    assert _intent_contract(_refund("E-1", subject, 1, "C-A"), "G", members) is None


def test_group_balances_sum_members() -> None:
    ent = _load(ENT)
    only_groups = ent.key.checkpoints[0].model_copy(
        update={"contracts": None, "subledger": None, "exceptions": None}
    )
    loaded = _with_checkpoints(ent, only_groups)
    (checkpoint,) = _build_checkpoint_bundles(loaded)
    (bundle,) = checkpoint.bundles
    assert bundle.group.member_contract_keys == ("C-ENT-A", "C-ENT-B")

    def rows(b_liability: int) -> tuple[BalanceOut, ...]:
        def row(contract: str, entity: str, liability: int, asset: int) -> BalanceOut:
            columns = {
                "contract_liability_txn": liability,
                "contract_asset_txn": asset,
                "unbilled_receivable_txn": 0,
            }
            return BalanceOut(f"{contract}@{entity}", "FY2026-P01", columns, {})

        return (
            row("C-ENT-A", "US01", 600000, 0),
            row("C-ENT-B", "US01", b_liability, 0),
            row("C-ENT-A", "US02", 0, 333333),
            row("C-ENT-B", "US02", 0, 400000),
        )

    def book(b_liability: int) -> BookOutput:
        # D-79: an ASC606 book needs a contract version; a zero basis meets DG-AK-54.
        group = bundle.group.group_key
        return _empty_book(
            contract_version=_version(group, transaction_price=0),
            trace=_trace(_node(group, "0.00", ("0.00", "0"))),
            balances=rows(b_liability),
        )

    assert _mismatches(loaded, _run(loaded, book(477778))) == []
    found = _mismatches(loaded, _run(loaded, book(477777)))
    assert [(m.subject, m.field, m.expected, m.actual) for m in found] == [
        ("group G-ENT-01@US01 FY2026-P01", "contract_liability", "10777.78", "10777.77")
    ]


def _schedule_line(
    amount: int, cumulative: int, quantity: Fraction | None = Fraction(1)
) -> ScheduleLineOut:
    return ScheduleLineOut(
        schedule_kind=ScheduleKind.REVENUE,
        subject_type="obligation",
        subject_key="C-RND-1/POB-001",
        entity="US01",
        period_key="FY2026-P01",
        line_type=ScheduleLineType.NORMAL,
        amount=amount,
        cumulative_amount=cumulative,
        cumulative_exact=Fraction(cumulative),
        quantity=quantity,
        is_released_at_close=False,
        trace_node_id="-",
    )


def _only(loaded: LoadedKey, **blocks: object) -> LoadedKey:
    """The first checkpoint holding only the given blocks."""
    checkpoint = loaded.key.checkpoints[0].model_copy(
        update={"contracts": None, "subledger": None, "exceptions": None, **blocks}
    )
    return _with_checkpoints(loaded, checkpoint)


def _contract_only(loaded: LoadedKey, **members: object) -> LoadedKey:
    block = ContractBlock.model_validate({"contract": "C-RND-1", **members})
    return _only(loaded, contracts=(block,))


def test_optional_blocks_compared() -> None:
    # ER-G-02: every optional comparison block can fail, with one mismatch per violation.
    rnd = _load(RND)
    group = _group(rnd)

    def fields(
        loaded: LoadedKey, book: BookOutput, diagnostics: tuple[Diagnostic, ...] = ()
    ) -> list[str]:
        return [m.field for m in _mismatches(loaded, _run(loaded, book, diagnostics=diagnostics))]

    # Schedule rows: `amounts` form, then period form.
    row = {"obligation_key": "POB-001", "schedule_kind": "REVENUE"}
    amounts = _contract_only(rnd, schedule=[{**row, "amounts": {"FY2026-P01": "33.34"}}])
    assert fields(amounts, _book(group, schedules=(_schedule_line(3334, 3334),))) == []
    assert fields(amounts, _book(group, schedules=(_schedule_line(3333, 3334),))) == ["amount"]
    period = _contract_only(
        rnd,
        schedule=[
            {
                **row,
                "period_key": "FY2026-P01",
                "amount": "33.34",
                "cumulative_amount": "33.34",
                "quantity": "1",
            }
        ],
    )
    assert fields(period, _book(group, schedules=(_schedule_line(3334, 3334),))) == []
    for line, field in (
        (_schedule_line(3333, 3334), "amount"),
        (_schedule_line(3334, 3333), "cumulative_amount"),
        (_schedule_line(3334, 3334, Fraction(2)), "quantity"),
    ):
        assert fields(period, _book(group, schedules=(line,))) == [field]

    # Trace assertions: wrong value, wrong formula id, absent node.
    node = {"measure": "tp_allocation_basis", "subject_key": group}
    exact = {**node, "value": "100.00", "formula_id": "sched.period_difference.v1"}
    assert fields(_contract_only(rnd, trace=[exact]), _book(group)) == []
    for assertion, field in (
        ({**node, "value": "99.99"}, "value"),
        ({**node, "value": "100.00", "formula_id": "sched.other.v1"}, "formula_id"),
        ({"measure": "revenue_cum", "subject_key": "POB-001", "value": "0.00"}, "value"),
    ):
        assert fields(_contract_only(rnd, trace=[assertion]), _book(group)) == [field]

    # Modification proposals.
    wanted = {"reference": "MOD-1", "proposed_treatments": {"POB-001": "PROSPECTIVE"}}
    modification = _contract_only(rnd, modifications=[wanted])

    def proposal(treatments: dict[str, str], reference: str = "MOD-1") -> ProposalOut:
        # CV-16: the engine keys a proposal by the contract subject, with detail.modification_key.
        detail = {"modification_key": reference}
        return ProposalOut("MODIFICATION_TREATMENT", "C-RND-1", None, treatments, detail)

    prospective = proposal({"POB-001": "PROSPECTIVE"})
    assert fields(modification, _book(group, proposals=(prospective,))) == []
    catch_up = proposal({"POB-001": "CUMULATIVE_CATCH_UP"})
    assert fields(modification, _book(group, proposals=(catch_up,))) == ["proposed_treatments"]
    # An obligation the key does not list is not asserted (DG-AK-53; L5-3-Q-18).
    wider = proposal({"POB-001": "PROSPECTIVE", "POB-002": "PROSPECTIVE"})
    assert fields(modification, _book(group, proposals=(wider,))) == []
    other = proposal({"POB-001": "PROSPECTIVE"}, reference="MOD-2")
    assert fields(modification, _book(group, proposals=(other,))) == ["proposed_treatments"]

    # Exceptions: an exact set per listed code, on the checkpoint book only.
    listed = _only(
        rnd, exceptions=(ExceptionRow(code="LATE_EVENT", severity="WARNING", contract="C-RND-1"),)
    )

    def warning(book_code: str) -> Diagnostic:
        return Diagnostic("LATE_EVENT", "WARNING", book_code, "C-RND-1", None, {})

    assert fields(listed, _book(group), (warning("ASC606"),)) == []
    assert fields(listed, _book(group), (warning("ASC606"), warning("ASC606"))) == ["finding"]
    assert fields(listed, _book(group), (warning("ASC606"), warning("IFRS15"))) == []

    # A result without the checkpoint's run.
    found = _mismatches(_only(rnd), RunResult(rnd.key.id, rnd.key.runner, ()))
    assert [(m.subject, m.field) for m in found] == [("checkpoint", "run")]

    # Two books: only the checkpoint book's figures are compared.
    billed = _contract_only(rnd, version={"billed_cum": "5.00"})
    asc606 = _book(group, contract_version=_version(group, billed_cum=500))
    ifrs15 = dataclasses.replace(
        asc606, book_code="IFRS15", contract_version=_version(group, billed_cum=700)
    )

    def two_books(first: BookOutput, second: BookOutput) -> RunResult:
        return _run_output(billed, OutputBundle(ENGINE_VERSION, "0" * 64, (first, second), ()))

    assert _mismatches(billed, two_books(asc606, ifrs15)) == []
    swapped = two_books(
        dataclasses.replace(asc606, contract_version=ifrs15.contract_version),
        dataclasses.replace(ifrs15, contract_version=asc606.contract_version),
    )
    assert _mismatches(billed, swapped)


def test_books_and_contract_version_required() -> None:
    # ER-C-05 (D-79; 05 RCP-11; ENGINE_SPEC §0.5): every BookInput needs a BookOutput.
    onb = _load(ONB)
    cutover = next(c for c in onb.key.checkpoints if c.name == "cutover-no-postings")
    only_cutover = _with_checkpoints(onb, cutover)
    found = _mismatches(
        only_cutover, _run_output(only_cutover, OutputBundle(ENGINE_VERSION, "0" * 64, (), ()))
    )
    assert ("book ASC606", "computed", "<absent>") in [
        (m.subject, m.field, m.actual) for m in found
    ]

    rnd = _load(RND)
    group = _group(rnd)
    unversioned = _mismatches(rnd, _run(rnd, _book(group, contract_version=None)))
    assert [(m.subject, m.actual) for m in unversioned if m.field == "contract_version"] == [
        (f"group {group} book ASC606", "<absent>")
    ]

    # The LEGACY book carries no contract version.
    (checkpoint,) = _build_checkpoint_bundles(rnd)
    (bundle,) = checkpoint.bundles
    legacy_input = dataclasses.replace(bundle.books[0], book_code="LEGACY", is_primary=False)
    with_legacy = dataclasses.replace(bundle, books=(*bundle.books, legacy_input))
    output = OutputBundle(
        ENGINE_VERSION, "0" * 64, (_book(group), _empty_book(book_code="LEGACY")), ()
    )
    run = CheckpointRun(dataclasses.replace(checkpoint, bundles=(with_legacy,)), (output,))
    assert _mismatches(rnd, RunResult(rnd.key.id, rnd.key.runner, (run,))) == []
    without_legacy = OutputBundle(ENGINE_VERSION, "0" * 64, (_book(group),), ())
    run = CheckpointRun(dataclasses.replace(checkpoint, bundles=(with_legacy,)), (without_legacy,))
    assert [
        (m.subject, m.field)
        for m in _mismatches(rnd, RunResult(rnd.key.id, rnd.key.runner, (run,)))
    ] == [("book LEGACY", "computed")]


def test_rel_cov_1_direct_invocation_stamps_the_wrapper_run_id_it_inherits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The propagation witness (Codex production-20260921-0734 §1 (4)): under a gate wrapper the
    writer stamps the run id it inherits from EREV_GATE_RUN_ID — the run binding the manifest
    checks (REL-COV-1) — here with a controlled non-empty value, test-locally set and restored."""
    monkeypatch.setenv("ID", WITHDRAWN)
    for variable in ("FAMILY", "REQ", answer_key_report.SCOPE_ENV, answer_key_report.CLEARED_ENV):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(answer_key_report.RUN_ID_ENV, "p1witness00000000000000000000001")
    exit_code = answer_key_report.main(
        [
            "--command",
            "probe",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--basetemp",
            str(tmp_path / "basetemp"),
        ]
    )
    assert exit_code == 1  # the selection still holds no active key (DG-AK-13)
    document = json.loads(
        (tmp_path / "reports" / "answer-keys-filtered" / "report.json").read_text(encoding="utf-8")
    )
    assert document["run_id"] == "p1witness00000000000000000000001"


def test_dg_ak_13_selection_without_active_key_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ID", WITHDRAWN)
    # A direct invocation outside any gate wrapper: the ci stage's own wrapper exports
    # EREV_GATE_RUN_ID (and a canonical run its selection variables) to every process under it,
    # and the writer stamps what it inherits (REL-COV-1 run binding) — so this test isolates them.
    for variable in (
        "FAMILY",
        "REQ",
        answer_key_report.RUN_ID_ENV,
        answer_key_report.SCOPE_ENV,
        answer_key_report.CLEARED_ENV,
        answer_key_report.PLATFORM_ENV,
    ):
        monkeypatch.delenv(variable, raising=False)
    exit_code = answer_key_report.main(
        [
            "--command",
            "probe",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--basetemp",
            str(tmp_path / "basetemp"),
        ]
    )
    assert exit_code == 1
    lines = capsys.readouterr().out.splitlines()
    # A filtered run is the named diagnostic `answer-keys-filtered` (DG-AK-42 rev 1.43): its own
    # report directory and target name; the canonical answer-keys report is never written by it.
    assert lines[-1] == (
        "FAIL answer-keys-filtered: the selection holds no active answer key (DG-AK-13)"
    )
    assert not (tmp_path / "reports" / "answer-keys").exists()
    document = json.loads(
        (tmp_path / "reports" / "answer-keys-filtered" / "report.json").read_text(encoding="utf-8")
    )
    assert document["target"] == "answer-keys-filtered"
    assert document["scope"] == {
        "kind": "filtered",
        "mode": "filtered",
        "platform": "in-memory",
        "cleared": [],
        "selection": {"families": [], "ids": [WITHDRAWN], "requirements": []},
    }
    assert document["run_id"] is None  # no wrapper run around this direct invocation
    assert "coverage" not in document
    assert document["corpus"]["ids"] and WITHDRAWN in document["corpus"]["ids"]
    assert len(document["corpus"]["sha256"]) == 64
    assert document["exit_code"] == 1
    assert document["failures"][0]["stage"] == "select"
    assert document["counts"]["withdrawn"] == 1
    assert not (tmp_path / "basetemp").exists()  # pytest never started


def test_rel_cov_1_scope_from_env() -> None:
    # Codex 1510: the canonical mode clears inherited filters explicitly and records what it
    # cleared, the platform and the mode; the other modes are named.
    from support.answer_keys.report import scope_from_env

    canonical = scope_from_env(
        {"EREV_AK_SCOPE": "full", "EREV_AK_CLEARED": "ID REQ", "EREV_AK_PLATFORM": "db",
         "FAMILY": "", "ID": "", "REQ": ""}
    )  # fmt: skip
    assert canonical.selection == {"families": (), "ids": (), "requirements": ()}
    assert canonical.scope == {
        "kind": "full",
        "mode": "canonical",
        "platform": "db",
        "cleared": ["ID", "REQ"],
        "selection": {"families": [], "ids": [], "requirements": []},
    }
    # A canonical run whose selection variables were NOT cleared is refused (the recipe clears).
    with pytest.raises(ValueError, match="AK_SCOPE=full"):
        scope_from_env({"EREV_AK_SCOPE": "full", "ID": WITHDRAWN})
    with pytest.raises(ValueError, match="EREV_AK_SCOPE"):
        scope_from_env({"EREV_AK_SCOPE": "fool"})
    implicit = scope_from_env({})
    assert implicit.scope["mode"] == "unfiltered-implicit" and implicit.scope["kind"] == "full"
    assert implicit.scope["platform"] == "in-memory" and implicit.scope["cleared"] == []
    filtered = scope_from_env({"ID": WITHDRAWN, "EREV_AK_PLATFORM": "db"})
    assert filtered.scope["mode"] == "filtered" and filtered.scope["kind"] == "filtered"
    assert filtered.scope["platform"] == "db" and filtered.selection["ids"] == (WITHDRAWN,)


def test_report_shape() -> None:
    rnd, ent = _load(RND), _load(ENT)
    mismatch = Mismatch(
        RND, "after-activation", "contract C-RND-1", "billed_cum", "5.00", "<absent>"
    )
    report = build_report(
        command=f"make answer-keys ID={RND},{ENT}",
        selected=[rnd, ent],
        outcomes={RND: KeyOutcome("failed", (mismatch,), "1 mismatch")},
        started_at="2026-09-12T00:00:00.000000Z",
        finished_at="2026-09-12T00:00:01.000000Z",
        exit_code=1,
        failures=[{"stage": "keys", "exit_code": 1, "keys": [RND]}],
        build_sha="nogit",
        worktree_dirty=False,
    )
    json.dumps(report)
    assert set(report) == {
        "target", "command", "build_sha", "worktree_dirty", "started_at", "finished_at",
        "exit_code", "counts", "failures", "keys", "scope", "run_id",
    }  # fmt: skip
    assert report["target"] == "answer-keys"
    assert report["scope"] == {
        "kind": "full", "mode": "unfiltered-implicit", "platform": "in-memory", "cleared": [],
        "selection": {"families": [], "ids": [], "requirements": []},
    }  # fmt: skip
    assert report["run_id"] is None
    bound = build_report(
        command="make answer-keys AK_SCOPE=full",
        selected=[rnd, ent],
        outcomes={},
        started_at="2026-09-12T00:00:00.000000Z",
        finished_at="2026-09-12T00:00:01.000000Z",
        exit_code=0,
        failures=[],
        build_sha="nogit",
        worktree_dirty=False,
        scope={"kind": "full", "mode": "canonical", "platform": "db", "cleared": ["ID"],
               "selection": {"families": [], "ids": [], "requirements": []}},
        run_id="run-abc",
    )  # fmt: skip
    assert bound["scope"]["mode"] == "canonical" and bound["run_id"] == "run-abc"
    filtered = build_report(
        command=f"make answer-keys ID={RND}",
        selected=[rnd],
        outcomes={RND: KeyOutcome("passed")},
        started_at="2026-09-12T00:00:00.000000Z",
        finished_at="2026-09-12T00:00:01.000000Z",
        exit_code=0,
        failures=[],
        build_sha="nogit",
        worktree_dirty=False,
        selection={"families": (), "ids": (RND,), "requirements": ()},
        corpus=[rnd, ent],
    )
    assert filtered["target"] == "answer-keys-filtered"
    assert filtered["scope"] == {
        "kind": "filtered", "mode": "filtered", "platform": "in-memory", "cleared": [],
        "selection": {"families": [], "ids": [RND], "requirements": []},
    }  # fmt: skip
    assert filtered["corpus"]["ids"] == sorted([RND, ENT])
    assert (
        filtered["corpus"]["sha256"]
        == hashlib.sha256(
            "\n".join(
                f"{k.key.id}:{k.sha256}" for k in sorted([rnd, ent], key=lambda k: k.key.id)
            ).encode()
        ).hexdigest()
    )
    assert filtered["corpus"]["active"] + filtered["corpus"]["withdrawn"] == 2
    first, second = report["keys"]
    assert first == {
        "id": RND,
        "path": f"docs/accounting/answer-keys/rnd/{RND}.yaml",
        "sha256": rnd.sha256,
        "runner": "engine",
        "result": "failed",
        "mismatches": [
            {
                "checkpoint": "after-activation",
                "object": "contract C-RND-1",
                "field": "billed_cum",
                "expected": "5.00",
                "actual": "<absent>",
            }
        ],
        "message": "1 mismatch",
        "notes": [],
        "review_status": rnd.key.review.status,
    }
    assert (second["id"], second["result"], second["mismatches"]) == (ENT, "not_run", [])
    not_approved = sum(1 for item in (rnd, ent) if item.key.review.status != "approved")
    assert report["counts"] == {
        "selected": 2,
        "passed": 0,
        "failed": 1,
        "not_run": 1,
        "withdrawn": 0,
        "not_approved": not_approved,
    }

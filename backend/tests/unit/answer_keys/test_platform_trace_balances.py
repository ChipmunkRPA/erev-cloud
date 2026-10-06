"""Record §24 (D-98 72): the trace-balances reader mirrors ``erev_engine._balances``.

Fail-first (`.run/f-rps-e1/fail-first-balances-d98-72.log`, head 9550d6e3): RET-JS-03's engine
trace through the reader gave refund_liability_txn 0 and return_asset_txn 0 (engine 500000 and
280000) and emitted the group subject ``CG-JS-03@JS-US`` as a member row.

The proof is a corpus property: for every checkpoint bundle of balance-carrying keys, the engine
computes the bundle, its trace is serialized and read back hash-verified, and the reader's rows
over inert entity rows equal the engine's own ``book.balances`` — every ``_txn`` column, the
same-currency ``_functional`` columns and the cited trace nodes, row for row. No key changes.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import erev_engine
import pytest
from erev_api.db.tables import legal_entity
from erev_api.explain.store import trace_document, trace_from_row
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.trace import Trace, TraceNode
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.models import AnswerKey, BalanceRow, Checkpoint, ContractBlock
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.runners import CheckpointRun, _Assembler
from support.answer_keys.workspace_adapter import missing_balances
from support.answer_keys.workspace_reads import PersistedReads

POS_012, _DLT, _EX21, _EX42, POS_117 = PLATFORM_KEY_IDS
RET_JS_03 = "RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET"
CORPUS = (
    RET_JS_03,
    POS_012,
    POS_117,
    "ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP",
    "ENT-CROSS-CURRENCY-PAIR-GBP-CONTRACT-USD-PERFORMER",
    "CPC-CHK-120-MIXED-ORDINARY",
    "COST-S8-CONTRACT-COSTS-EX2",
    "BRK-JS-02-GIFT-CARDS-BREAKAGE-ESCHEAT",
    "LOSS-GE-03-LOSS-CONTRACT-PROVISION",
)


class _Entities:
    """A ``TableSource`` holding only the tenant's entities (all the reader reads for balances)."""

    tenant_id = uuid5(NAMESPACE_URL, "erev://trace-balances/tenant")

    def __init__(self, bundle: InputBundle) -> None:
        self.rows = [
            {
                "id": uuid5(self.tenant_id, e.code),
                "code": e.code,
                "functional_currency": e.functional_currency,
            }
            for e in bundle.entities
        ]

    def table_rows(self, table: Any, **equals: object) -> list[dict[str, Any]]:
        assert table is legal_entity, table
        return [dict(r) for r in self.rows if all(r.get(k) == v for k, v in equals.items())]

    def aggregate(self, table: Any, column: str) -> tuple[int, object]:
        raise AssertionError("not read")

    def file_bytes(self, file_id: Any) -> bytes:
        raise AssertionError("not read")


def _load(key_id: str) -> LoadedKey:
    return load(next(ANSWER_KEY_ROOT.rglob(f"{key_id}.yaml")))


def _round_trip(trace: Trace) -> Trace:
    row = {
        "id": uuid5(NAMESPACE_URL, "trace"),
        "format_version": trace.format_version,
        "engine_version": trace.engine_version,
        "trace": trace_document(trace),
        "root_measures": dict(trace.root_measures),
        "trace_sha256": trace.sha256(),
    }
    return trace_from_row(row)  # hash-verified


def _rebuilt(bundle: InputBundle, book: BookOutput, where: str):  # noqa: ANN202
    reads = PersistedReads(_Entities(bundle))  # type: ignore[arg-type]
    obligation_entities = {
        ov.subject_key: str(ov.columns["contracting_entity_code"])
        for ov in book.obligation_versions
    }
    return reads.trace_balances(
        _round_trip(book.trace),
        currency=bundle.group.transaction_currency,
        members=bundle.group.member_contract_keys,
        group_key=bundle.group.group_key,
        obligation_entities=obligation_entities,
        where=where,
    )


@pytest.mark.parametrize("key_id", CORPUS)
def test_reader_rows_equal_the_engines_balances_row_for_row(key_id: str) -> None:
    loaded = _load(key_id)
    compared = 0
    for checkpoint in _Assembler(loaded).checkpoints():
        for bundle in checkpoint.bundles:
            output = erev_engine.compute(bundle)
            book = next(b for b in output.books if b.book_code == checkpoint.book)
            currency = bundle.group.transaction_currency
            functional = {e.code: e.functional_currency for e in bundle.entities}
            engine = {(b.subject_key, b.period_key): b for b in book.balances}
            mine = {
                (b.subject_key, b.period_key): b for b in _rebuilt(bundle, book, checkpoint.name)
            }
            assert set(mine) == set(engine), (
                key_id,
                checkpoint.name,
                sorted(set(mine) ^ set(engine)),
            )
            for key, expected in engine.items():
                actual = mine[key]
                same = functional[str(expected.columns["entity"])] == currency
                for name, value in expected.columns.items():
                    if name.endswith("_txn") or (same and name.endswith("_functional")):
                        assert actual.columns.get(name) == value, (
                            key_id,
                            checkpoint.name,
                            key,
                            name,
                        )
                        compared += 1
                for name in actual.columns:
                    if name.endswith("_txn"):
                        assert name in expected.columns, (key_id, key, name)  # nothing invented
                if same:
                    assert dict(actual.trace_nodes) == dict(expected.trace_nodes), (key_id, key)
                assert actual.columns["entity"] == expected.columns["entity"]
            assert not any(k[0].startswith(bundle.group.group_key + "@") for k in mine) or (
                bundle.group.group_key in bundle.group.member_contract_keys
            )
    assert compared > 0


def test_ret_js_03_refund_liability_and_return_asset_come_from_their_producer_nodes() -> None:
    """Codex's exact case: 5,000.00 refund liability (component grain) and 2,800.00 return asset
    (obligation grain) at FY2026-P03; the group subject is never a member row. Since D-97 (8) the
    member row links the stage 10 member-sum node of each measure, whose inputs are the producer
    nodes (the refund component, the obligation-grain return asset); the reader mirrors that."""
    loaded = _load(RET_JS_03)
    checkpoint = _Assembler(loaded).checkpoints()[0]
    assert checkpoint.name == "shipment"
    (bundle,) = checkpoint.bundles
    book = next(b for b in erev_engine.compute(bundle).books if b.book_code == checkpoint.book)
    rows = {(b.subject_key, b.period_key): b for b in _rebuilt(bundle, book, "shipment")}
    p03 = rows[("JS-03@JS-US", "FY2026-P03")]
    assert (p03.columns["refund_liability_txn"], p03.columns["return_asset_txn"]) == (
        500000,
        280000,
    )
    engine_p03 = next(
        b for b in book.balances if (b.subject_key, b.period_key) == ("JS-03@JS-US", "FY2026-P03")
    )
    nodes = {node.id: node for node in book.trace.nodes}
    for measure, producer in (
        ("refund_liability", "refund_liability:CG-JS-03@JS-US/RETURN/"),
        ("return_asset", "return_asset:JS-03/L1-MACHINES:FY2026-P03"),
    ):
        link = p03.trace_nodes[measure]
        assert link == engine_p03.trace_nodes[measure] == f"{measure}:JS-03@JS-US:FY2026-P03"
        rollup = nodes[link]
        assert rollup.params.get("role") == "member_sum"
        (producer_id,) = rollup.inputs
        assert str(producer_id).startswith(producer)
    assert not any(subject.startswith("CG-JS-03@") for subject, _ in rows)
    # Without the persisted obligation entities the obligation-grain node still attributes through
    # the refund component that names it; a bare obligation node with neither refuses by name.
    reads = PersistedReads(_Entities(bundle))  # type: ignore[arg-type]
    again = reads.trace_balances(
        _round_trip(book.trace),
        currency="USD",
        members=bundle.group.member_contract_keys,
        group_key=bundle.group.group_key,
        where="shipment",
    )
    assert (
        next(b for b in again if b.period_key == "FY2026-P03").columns["return_asset_txn"] == 280000
    )
    bare = Trace(
        format_version=1,
        engine_version="x",
        nodes=(
            _node("contract_liability", "JS-03@JS-US", "FY2026-P03", "0.00"),
            _node("return_asset", "JS-03/L1-MACHINES", "FY2026-P03", "1.00"),
        ),
        root_measures={},
    )
    with pytest.raises(NotProvisioned, match="obligation grain and no persisted obligation row"):
        reads.trace_balances(
            bare, currency="USD", members=("JS-03",), group_key="CG-JS-03", where="t"
        )


def _node(measure: str, subject: str, period: str, value: str) -> TraceNode:
    return TraceNode(
        id=f"{measure}:{subject}:{period}",
        measure=measure,
        value=value,
        currency="USD",
        formula_id="bal.member.v1",
        inputs=(),
        params={"minor_unit": "2"},
        rounding_residue="0",
        narrative_key="bal.member",
    )


def test_grain_checks_and_zero_fill_follow_the_engine() -> None:
    loaded = _load(RET_JS_03)
    (bundle,) = _Assembler(loaded).checkpoints()[0].bundles
    reads = PersistedReads(_Entities(bundle))  # type: ignore[arg-type]
    member = _node("contract_liability", "JS-03@JS-US", "FY2026-P03", "10.00")
    group_row = _node("contract_liability", "CG-JS-03@JS-US", "FY2026-P03", "10.00")
    stranger = _node("contract_liability", "ZZ-9@JS-US", "FY2026-P03", "10.00")
    trace = Trace(format_version=1, engine_version="x", nodes=(member, group_row), root_measures={})
    (row,) = reads.trace_balances(
        trace, currency="USD", members=("JS-03",), group_key="CG-JS-03", where="t"
    )
    assert row.subject_key == "JS-03@JS-US" and row.columns["contract_liability_txn"] == 1000
    # The engine's own zero-fills and nothing else: the five stage-10 measures and the two
    # stage-11 columns read 0; a measure the engine did not produce here stays absent.
    assert row.columns["refund_liability_txn"] == 0 and row.columns["cost_asset_carrying_txn"] == 0
    assert row.columns["loss_provision_txn"] == 0
    assert "contract_liability_current_txn" not in row.columns
    with pytest.raises(NotProvisioned, match="neither a member of the group nor the group"):
        reads.trace_balances(
            Trace(format_version=1, engine_version="x", nodes=(stranger,), root_measures={}),
            currency="USD",
            members=("JS-03",),
            group_key="CG-JS-03",
            where="t",
        )
    # A component key outside the D-90 grammar cannot be attributed.
    odd = _node("refund_liability", "CG-JS-03@JS-US/UNKNOWN/what", "FY2026-P03", "1.00")
    with pytest.raises(NotProvisioned, match="outside the D-90 grammar"):
        reads.trace_balances(
            Trace(format_version=1, engine_version="x", nodes=(member, odd), root_measures={}),
            currency="USD",
            members=("JS-03",),
            group_key="CG-JS-03",
            where="t",
        )
    # An asserted amount the rebuilt row does not carry is named, never zero.
    checkpoint = Checkpoint(
        name="t",
        after_seq=1,
        as_of="2026-03-31",
        book="ASC606",
        contracts=(
            ContractBlock(
                contract="JS-03",
                balances=(BalanceRow(entity="JS-US", contract_liability_current="1.00"),),
            ),
        ),
    )
    bundles = _Assembler(loaded).checkpoints()[0]
    from erev_engine.bundle import OutputBundle

    output = OutputBundle(
        engine_version="x",
        input_sha256="0" * 64,
        books=(
            BookOutput(
                book_code="ASC606",
                contract_version=None,
                status_in_book=(),
                obligation_versions=(),
                balances=(row,),
                schedules=(),
                cost_asset_versions=(),
                loss_provision_versions=(),
                fx_layer_movements=(),
                posting_intents=(),
                proposals=(),
                time_triggers=(),
                trace=trace,
            ),
        ),
        diagnostics=(),
    )
    run = CheckpointRun(bundles, (output,))
    assert missing_balances(checkpoint, run, {"JS-US": "FY2026-P03"}) == [
        "JS-03@JS-US FY2026-P03 contract_liability_current"
    ]
    assert missing_balances(checkpoint, run, {"JS-US": "FY2026-P04"}) == ["JS-03@JS-US FY2026-P04"]


def test_the_six_original_outputs_hold_twelve_member_rows_and_no_group_row() -> None:
    """READ2-R2's numbers: POS-CHK-012 end-of-p1 / end-of-p2 (both groups), POS-CHK-117
    march-close and RET-JS-03 shipment — 12 native rows; the reader emits exactly those 12, none
    at group level (fail-first at 9550d6e3: 24, twelve of them the groups' own subjects)."""
    outputs = ((POS_012, None), (POS_117, "march-close"), (RET_JS_03, "shipment"))
    native = reader = 0
    for key_id, only in outputs:
        loaded = _load(key_id)
        for checkpoint in _Assembler(loaded).checkpoints():
            if only is not None and checkpoint.name != only:
                continue
            for bundle in checkpoint.bundles:
                book = next(
                    b for b in erev_engine.compute(bundle).books if b.book_code == checkpoint.book
                )
                rows = _rebuilt(bundle, book, checkpoint.name)
                assert {(b.subject_key, b.period_key) for b in rows} == {
                    (b.subject_key, b.period_key) for b in book.balances
                }
                heads = {b.subject_key.rpartition("@")[0] for b in rows}
                assert heads <= set(bundle.group.member_contract_keys)
                native += len(book.balances)
                reader += len(rows)
    assert (native, reader) == (12, 12)


def _relabelled_cost_world() -> LoadedKey:
    """Record §26: the COST-S8-CONTRACT-COSTS-EX2 world re-validated in memory with its contract
    relabelled ``C-COST/2`` (encoded component ``C-COST%2F2``) and a second entity ``US02`` (same
    currency and calendar) as the line's performing entity — a separately labelled world; the
    original key file and its financial inputs are untouched."""
    loaded = _load("COST-S8-CONTRACT-COSTS-EX2")
    text = json.dumps(loaded.key.model_dump(mode="json", by_alias=True))
    data = json.loads(text.replace("C-COST-2", "C-COST/2"))
    us01 = next(e for e in data["world"]["entities"] if e["code"] == "US01")
    data["world"]["entities"].append({**us01, "code": "US02", "name": "US02 (relabelled world)"})
    for contract in data["contracts"]:
        for line in contract["lines"]:
            line["performing_entity_code"] = "US02"
    return dataclasses.replace(loaded, key=AnswerKey.model_validate(data))


def test_stage_11_attribution_uses_the_encoded_persisted_mapping_on_a_producer_world() -> None:
    """Record §26: an actual-producer regression — the engine computes the relabelled world (an
    encoded contract id, two entity rows); the reader attributes stage 11's carrying amounts
    through the persisted obligation mapping keyed by the ENCODED head and equals the engine; a
    supplied mapping that names no obligation of the contract refuses by name (the mapping is
    authoritative when supplied); without a mapping the single-member-row fallback answers."""
    relabelled = _relabelled_cost_world()
    assert [c.external_id for c in relabelled.key.contracts] == ["C-COST/2"]
    checkpoint = _Assembler(relabelled).checkpoints()[0]
    (bundle,) = checkpoint.bundles
    assert sorted(e.code for e in bundle.entities) == ["US01", "US02"]
    book = next(b for b in erev_engine.compute(bundle).books if b.book_code == checkpoint.book)
    engine = {(b.subject_key, b.period_key): b for b in book.balances}
    assert all(subject == "C-COST%2F2@US01" for subject, _ in engine)  # the encoded head
    reads = PersistedReads(_Entities(bundle))  # type: ignore[arg-type]
    mapping = {
        ov.subject_key: str(ov.columns["contracting_entity_code"])
        for ov in book.obligation_versions
    }
    assert set(mapping) == {"C-COST%2F2/L1-OUTSOURCE"} and set(mapping.values()) == {"US01"}
    common = {
        "currency": bundle.group.transaction_currency,
        "members": bundle.group.member_contract_keys,
        "group_key": bundle.group.group_key,
        "where": "relabelled",
    }
    trace = _round_trip(book.trace)
    mine = {
        (b.subject_key, b.period_key): b
        for b in reads.trace_balances(trace, obligation_entities=mapping, **common)
    }
    assert set(mine) == set(engine)
    for key, expected in engine.items():
        assert (
            mine[key].columns["cost_asset_carrying_txn"]
            == expected.columns["cost_asset_carrying_txn"]
        )
    assert engine[("C-COST%2F2@US01", "FY2026-P01")].columns["cost_asset_carrying_txn"] > 0
    with pytest.raises(NotProvisioned, match="name no obligation of that contract"):
        reads.trace_balances(trace, obligation_entities={}, **common)  # supplied, so authoritative
    # F-RPS-ST11-R1 (Codex's US02 world): a mapping to an input entity for which the contract
    # opens no member row refuses by name — the native amount is never dropped or zero-filled.
    with pytest.raises(
        NotProvisioned, match="mapped to entity 'US02', for which the contract opens no"
    ):
        reads.trace_balances(
            trace, obligation_entities={"C-COST%2F2/L1-OUTSOURCE": "US02"}, **common
        )
    fallback = {
        (b.subject_key, b.period_key): b
        for b in reads.trace_balances(trace, obligation_entities=None, **common)
    }
    assert (
        fallback[("C-COST%2F2@US01", "FY2026-P01")].columns["cost_asset_carrying_txn"]
        == (engine[("C-COST%2F2@US01", "FY2026-P01")].columns["cost_asset_carrying_txn"])
    )


def test_encoded_head_lookup_disambiguates_two_member_rows_where_the_fallback_cannot() -> None:
    """Two member rows of one encoded contract (``C%2F1`` in US01 and US02): the persisted mapping
    places the carrying amount on the contracting entity's row; without a mapping the reader
    refuses by name instead of guessing."""
    loaded = _load(RET_JS_03)
    (bundle,) = _Assembler(loaded).checkpoints()[0].bundles
    tables = _Entities(bundle)
    tables.rows = [
        {"id": uuid5(NAMESPACE_URL, code), "code": code, "functional_currency": "USD"}
        for code in ("US01", "US02")
    ]
    reads = PersistedReads(tables)  # type: ignore[arg-type]
    trace = Trace(
        format_version=1,
        engine_version="x",
        nodes=(
            _node("contract_liability", "C%2F1@US01", "FY2026-P01", "10.00"),
            _node("contract_liability", "C%2F1@US02", "FY2026-P01", "5.00"),
            TraceNode(
                id="carrying_amount:C%2F1/EV-000001:FY2026-P01",
                measure="carrying_amount",
                value="123.45",
                currency="USD",
                formula_id="cost.carrying.v1",
                inputs=(),
                params={"minor_unit": "2"},
                rounding_residue="0",
                narrative_key="cost.carrying",
            ),
        ),
        root_measures={},
    )
    common = {"currency": "USD", "members": ("C/1",), "group_key": "CG-C/1", "where": "t"}
    rows = {
        b.subject_key: b
        for b in reads.trace_balances(trace, obligation_entities={"C%2F1/L1": "US01"}, **common)
    }
    assert rows["C%2F1@US01"].columns["cost_asset_carrying_txn"] == 12345
    assert rows["C%2F1@US02"].columns["cost_asset_carrying_txn"] == 0
    with pytest.raises(NotProvisioned, match="no single member row"):
        reads.trace_balances(trace, obligation_entities=None, **common)
    tables.rows.append(
        {"id": uuid5(NAMESPACE_URL, "US03"), "code": "US03", "functional_currency": "USD"}
    )
    with pytest.raises(NotProvisioned, match="mapped to entity 'US03'"):  # F-RPS-ST11-R1
        reads.trace_balances(trace, obligation_entities={"C%2F1/L1": "US03"}, **common)

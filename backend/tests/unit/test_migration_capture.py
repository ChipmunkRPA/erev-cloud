"""``domain.migration.capture`` — the opening-balance import's savepoint dry run and its durable
capture (BUILD_SPEC LMG-2 ``MIGRATION_IMPORT``; 04 T-MIG-04 / T-MIG-05 rev 1.60; D-98 candidates
122 and 126; lane record §24). Fakes only: the applier and the session are ports; the in-savepoint
reader is exercised over queued fake rows that mirror the engine tables; the platform applier's
payload builders run over the shipped WLD-F-15 staging. No database.

These tests were written AFTER the module (disclosed in the record): the module's shape followed the
§24 design note and the code was written first; there is no fail-first log for this file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.migration import capture, legacy_db, opening_balances
from erev_api.domain.migration.opening_balances import ContractOpening
from erev_api.enums import MigrationMode, PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from erev_engine.errors import EngineError
from erev_engine.trace import Trace, TraceNode
from sqlalchemy.dialects import postgresql
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
BATCH = UUID(int=31)
CUTOVER = date(2023, 1, 31)
KNOWN_AT = datetime(2026, 9, 20, 19, 0, tzinfo=UTC)
CURRENCY = "USD"


OPERATION = UUID(int=32)  # the import job's id, written as capture_operation_id with IMPORTING


def _batch(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": BATCH,
        "migration_no": "MIG-000001",
        "mode": MigrationMode.OPENING_BALANCES.value,
        "status": "IMPORTING",
        "cutover_date": CUTOVER,
        "capture_operation_id": OPERATION,
    }
    row.update(over)
    return row


def _staging() -> opening_balances.Staging:
    return opening_balances.stage(legacy_db.rows(FIXTURE), CUTOVER)


def _rounded(contract: ContractOpening, places: int = 2) -> ContractOpening:
    """The contract with every opening value quantised to ``places`` — a payload-representable
    shape for the applier's builders (the fixture itself carries up to 15 places)."""
    quantum = Decimal(1).scaleb(-places)
    rows = tuple(
        dataclasses.replace(row, values={k: v.quantize(quantum) for k, v in row.values.items()})
        for row in contract.rows
    )
    return dataclasses.replace(
        contract,
        obligations=tuple(r for r in rows if not r.is_vc),
        vc_elements=tuple(r for r in rows if r.is_vc),
    )


# --- payload builders -----------------------------------------------------------------------------


def test_booking_body_is_the_platform_payload_of_the_staged_terms() -> None:
    contract = _staging().contracts[0]
    body = capture.booking_body(
        contract, batch=_batch(), currency=CURRENCY, customer_id=UUID(int=5)
    )
    assert body.external_id == "Contract 1" and body.customer_id == UUID(int=5)
    assert body.document_ref == "migration:MIG-000001"  # BS3-D-26
    assert body.transaction_currency == CURRENCY and body.inception_date == contract.inception_date
    staged = opening_balances.booking_payload(contract)["lines"]
    assert [line.obligation_key for line in body.lines] == [
        item["obligation_key"] for item in staged
    ]
    # pob_template_code is not a booking member (the product's default template carries it)
    assert all("pob_template_code" not in line.model_dump() for line in body.lines)
    assert body.lines[0].total_price.currency == CURRENCY
    assert body.lines[0].performing_entity_code == staged[0]["performing_entity_code"]


def test_vc_elements_writes_the_s01_r_06_element_of_every_staged_vc_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FLMG-VC-ELEMENT-1 (lane FIX-E; ENGINE_SPEC S07-R-11 "VC rows become VC lines with their VC
    element (POL-213)", S01-R-06): for every staged ``VC`` row the applier writes the contract-level
    element ``VC-<obligation key>`` — ``ENTERED_AMOUNT``, version 1, the stated price as a
    magnitude, a negative price a ``DECREASE`` element, effective on the inception date,
    ``allocation_target = CONTRACT`` — with origin MIGRATION and no approval request (the rows
    live in the dry run's savepoint), and answers how many ``ESTIMATE_CHANGED`` events it appended
    (the stream head the activation and the opening balance follow). WLD-F-15: Contract 2's
    ``VC #1`` is -100 and Contract 4's -200; Contracts 1 and 3 carry no VC row and write nothing.
    The pre-fix applier wrote no element at all (the pg witness measures the consequence)."""
    written: list[tuple[Any, dict[str, Any]]] = []

    def fake_writer(uow: Any, element: Any, **kwargs: Any) -> UUID:
        written.append((element, {"uow": uow, **kwargs}))
        return UUID(int=900 + len(written))

    monkeypatch.setattr(capture, "write_vc_element", fake_writer)
    contracts = {contract.external_id: contract for contract in _staging().contracts}
    unit = object()
    counts = {
        name: capture.vc_elements(
            cast(UnitOfWork, unit), contract, contract_id=UUID(int=40 + index), currency=CURRENCY
        )
        for index, (name, contract) in enumerate(sorted(contracts.items()))
    }
    assert counts == {"Contract 1": 0, "Contract 2": 1, "Contract 3": 0, "Contract 4": 1}
    assert [kwargs for _, kwargs in written] == [{"uow": unit, "origin": "MIGRATION"}] * 2
    second, fourth = (element for element, _ in written)
    assert dataclasses.asdict(second) == {
        "contract_id": UUID(int=41),
        "contract_external_id": "Contract 2",
        "element_code": "VC-VC #1",
        "obligation_key": "VC #1",
        "direction": "DECREASE",
        "constrained_amount": Decimal(100),
        "currency": CURRENCY,
        "effective_date": contracts["Contract 2"].inception_date,
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "method": "ENTERED_AMOUNT",
        "allocation_target": "CONTRACT",
        "version_no": 1,
        "rationale": second.rationale,
    }
    assert second.estimate_key == "Contract 2/VC-VC #1"
    assert second.effective_date == date(2023, 1, 1)
    assert (fourth.contract_external_id, fourth.direction, fourth.constrained_amount) == (
        "Contract 4",
        "DECREASE",
        Decimal(200),
    )
    # a positive stated price is an INCREASE element of the same magnitude (04 B3-D16)
    written.clear()
    vc_row = contracts["Contract 2"].vc_elements[0]
    bonus = dataclasses.replace(
        contracts["Contract 2"],
        vc_elements=(
            dataclasses.replace(
                vc_row, mapped=dataclasses.replace(vc_row.mapped, stated_price=Decimal("75.5"))
            ),
        ),
    )
    assert (
        capture.vc_elements(
            cast(UnitOfWork, unit), bonus, contract_id=UUID(int=41), currency=CURRENCY
        )
        == 1
    )
    assert (written[0][0].direction, written[0][0].constrained_amount) == (
        "INCREASE",
        Decimal("75.5"),
    )


def test_the_opening_event_is_effective_on_the_cutover_or_on_a_later_inception() -> None:
    """Ruling R-5a (variant E; ENGINE_SPEC S07-R-01, S07-R-02, S07-R-11): a contract whose legacy
    minimum ``Current Period`` is after the cutover keeps that inception and carries its one
    opening event on it, the payload still naming the batch's cutover. WLD-F-15: Contracts 1 and
    2 were set up on 1 Jan 2023 and open on the 31 Jan 2023 cutover; Contracts 3 and 4 were set up
    on 1 Feb 2023 and open on 1 Feb 2023 with rows that hold nothing at the cutover."""
    contracts = {contract.external_id: contract for contract in _staging().contracts}
    assert {name: contract.inception_date for name, contract in contracts.items()} == {
        "Contract 1": date(2023, 1, 1),
        "Contract 2": date(2023, 1, 1),
        "Contract 3": date(2023, 2, 1),
        "Contract 4": date(2023, 2, 1),
    }
    assert {
        name: capture.opening_effective_date(contract, CUTOVER)
        for name, contract in contracts.items()
    } == {
        "Contract 1": CUTOVER,
        "Contract 2": CUTOVER,
        "Contract 3": date(2023, 2, 1),
        "Contract 4": date(2023, 2, 1),
    }
    # the inception is never moved onto the cutover; a contract set up ON the cutover opens on it
    late = contracts["Contract 3"]
    assert capture.opening_effective_date(late, date(2023, 2, 1)) == date(2023, 2, 1)
    assert capture.opening_effective_date(late, date(2023, 2, 28)) == date(2023, 2, 28)
    assert late.inception_date == date(2023, 2, 1)
    # "nil rows": the staged rows of the two late contracts carry no history, and their remaining
    # allocation is the whole transaction price (PRD WLD-X-27: 1,300.00 and 950.00)
    history = (
        "revenue_cum",
        "billed_cum",
        "catch_up_cum",
        "pre_standard_revenue_cum",
        "delivered_quantity_cum",
        "ssp_delivered_cum",
        "position_obligation",
        "netting_reclass_amount",
    )
    for name, price in (("Contract 3", Decimal("1300.00")), ("Contract 4", Decimal("950.00"))):
        staged = contracts[name]
        assert {member: staged.total(member) for member in history} == dict.fromkeys(
            history, Decimal(0)
        )
        assert staged.total("remaining_allocation").quantize(Decimal("0.01")) == price
        payload = opening_balances.opening_payload(staged, CUTOVER)
        assert (payload["reason"], payload["cutover_date"]) == ("LEGACY_MIGRATION", "2023-01-31")
    # the two contracts that existed at the cutover do carry history (295.69 and 58.85 recognised)
    assert contracts["Contract 1"].total("revenue_cum").quantize(Decimal("0.01")) == Decimal(
        "295.69"
    )
    assert contracts["Contract 2"].total("revenue_cum").quantize(Decimal("0.01")) == Decimal(
        "58.85"
    )


def test_opening_body_v1_boundary_refuses_unrepresentable_money_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The explicit V1-BOUNDARY witness (Codex 0605 §3 / 0634 / B4): under payload version 1
    # (``MoneyIn``, four places) the shipped fixture's 14-place revenue_cum cannot be carried —
    # refused by name, never rounded (D-98 127 interim). Version 1 is pinned explicitly here; the
    # registered latest is version 2 since B4's 04 rev 1.61 landed (main fe8e85df).
    from erev_api.events import payloads

    contract = _staging().contracts[0]
    monkeypatch.setattr(
        capture, "opening_payload_model", lambda: (1, payloads.OpeningBalanceEstablishedV1)
    )
    with pytest.raises(Problem) as refused:
        capture.opening_body(contract, batch=_batch(), currency=CURRENCY)
    detail = refused.value.detail or ""
    assert detail.startswith("Contract 1 ") and "decimal places" in detail
    assert "S07-R-11" in detail and "MoneyStr" in detail and "does not round" in detail
    assert refused.value.errors[0].rule_id == capture.RULE
    # and the V1 model itself refuses the exact text (MoneyStr four places): the boundary is real
    with pytest.raises(ValueError, match="decimal"):
        payloads.OpeningObligationV1.model_validate(
            {
                "obligation_key": "POB #1",
                **{member: "1" for member in capture.OPENING_QUANTITY_MEMBERS},
                **{
                    member: {"amount": "295.69000000000005", "currency": CURRENCY}
                    for member in capture.OPENING_MONEY_MEMBERS
                },
            }
        )
    # a four-place contract passes version 1: every member present, quantities as decimal strings,
    # money in the reporting currency, migration_batch_id = the batch
    body = capture.opening_body(_rounded(contract), batch=_batch(), currency=CURRENCY)
    assert body.reason == "LEGACY_MIGRATION" and body.cutover_date == CUTOVER
    assert body.migration_batch_id == BATCH and len(body.obligations) == len(contract.rows)


def test_opening_body_accepts_the_original_unrounded_fixture_under_v2() -> None:
    # D-98 candidate 127 (B4's V2 on main: ``OpeningBalanceEstablishedV2`` / ``ExactMoneyIn``,
    # 04 rev 1.61): the ORIGINAL UNROUNDED WLD-F-15 values are carried exactly — all eight money
    # members, the four quantities, the batch and cutover — and the payload is the registered
    # latest version, intact (round-trips through the registry model); nothing quantised.
    from erev_api import money
    from erev_api.events import payloads

    version, model = capture.opening_payload_model()
    # the registered latest is version 2 and IS B4's model (04 rev 1.61)
    assert version == 2 and model is payloads.OpeningBalanceEstablishedV2
    staging = _staging()
    contract = staging.contracts[0]
    # the staged rows are the payload's source (the same call opening_body makes)
    staged_rows = opening_balances.opening_payload(contract, CUTOVER)["rows"]
    unrounded = [
        row[member]
        for row in staged_rows
        for member in capture.OPENING_MONEY_MEMBERS
        if capture._places(Decimal(str(row[member]))) > capture.MONEY_PLACES
    ]
    assert unrounded, "the shipped fixture must carry a value beyond four places"
    body = capture.opening_body(contract, batch=_batch(), currency=CURRENCY)
    assert isinstance(body, model)
    assert body.reason == "LEGACY_MIGRATION" and body.cutover_date == CUTOVER
    assert body.migration_batch_id == BATCH and body.fair_value_contract_liability is None
    assert len(body.obligations) == len(staged_rows)
    for staged, carried in zip(staged_rows, body.obligations, strict=True):
        assert carried.obligation_key == staged["obligation_key"]
        for member in capture.OPENING_QUANTITY_MEMBERS:
            assert Decimal(getattr(carried, member)) == Decimal(str(staged[member]))
            assert getattr(carried, member) == money.exact_plain_decimal(str(staged[member]))
        for member in capture.OPENING_MONEY_MEMBERS:
            carried_money = getattr(carried, member)
            assert carried_money.currency == CURRENCY
            assert Decimal(carried_money.amount) == Decimal(str(staged[member]))
            assert carried_money.amount == money.exact_plain_decimal(str(staged[member]))
    # every contract of the fixture is carried, not only the first
    for other in staging.contracts[1:]:
        capture.opening_body(other, batch=_batch(), currency=CURRENCY)
    # intact: the registry's version-2 model re-validates the dumped payload byte for byte
    dumped = body.model_dump(mode="json")
    again = payloads.OpeningBalanceEstablishedV2.model_validate(dumped)
    assert again.model_dump(mode="json") == dumped
    # true invalid values are still refused by name under V2: an amount beyond the API-C-06 bound
    # (19 fractional digits) fails the registered model, never rounded
    too_fine = dict(staged_rows[0], revenue_cum=Decimal("295.6900000000000000001"))
    widened = {**opening_balances.opening_payload(contract, CUTOVER), "rows": [too_fine]}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(capture, "opening_payload", lambda _contract, _cutover: widened)
        with pytest.raises(Problem) as refused:
            capture.opening_body(contract, batch=_batch(), currency=CURRENCY)
    assert "refused the staged values" in (refused.value.detail or "")


def test_opening_body_refuses_a_v2_unrepresentable_amount_by_name(tmp_path: Path) -> None:
    # Codex 1101 §2: the negative input of the CURRENT contract (V2 / ExactMoneyIn) — a copy of the
    # shipped fixture whose Contract 1 / POB #1 catch-up REAL is 1e-19: exact text
    # 0.0000000000000000001, 19 fractional digits, beyond the API-C-06 bound — refused by name at
    # the
    # exact-value boundary; nothing rounded; the shipped fixture untouched (the pg case runs the
    # same
    # input through the import job end to end — NOT RUN on the lane)
    from support.parity.sqlite_fixtures import sqlite_copy_with_cell

    target_row = next(
        row
        for row in legacy_db.latest_rows(legacy_db.rows(FIXTURE))  # the staged (latest) version
        if row.values.get("Contract Unique Name") == "Contract 1"
        and row.values.get("POB Unique ID") == "POB #1"
    )
    negative = sqlite_copy_with_cell(
        FIXTURE,
        tmp_path / "unrepresentable-v2.db",
        table="Contract_Live",
        column="Current Cumulative Catchup - Cumulative - Disclosure Only",
        rowid=target_row.source_rowid,
        value=1e-19,
    )
    staging = opening_balances.stage(legacy_db.rows(negative), CUTOVER)
    contract = next(c for c in staging.contracts if c.external_id == "Contract 1")
    version, _model = capture.opening_payload_model()
    assert version == 2
    with pytest.raises(Problem) as refused:
        capture.opening_body(contract, batch=_batch(), currency=CURRENCY)
    detail = refused.value.detail or ""
    assert detail.startswith("Contract 1") and "catch_up_cum" in detail
    assert (
        "0.0000000000000000001" in detail
        and "API-C-06" in detail
        and "refused, not rounded" in detail
    )
    assert refused.value.errors[0].rule_id == capture.RULE
    # the untouched shipped fixture still passes under V2 (the acceptance witness above)
    original = next(c for c in _staging().contracts if c.external_id == "Contract 1")
    capture.opening_body(original, batch=_batch(), currency=CURRENCY)


def test_prerequisites_check_requires_the_confirmed_target_not_the_legacy_text() -> None:
    # Codex 1227 F1: after the confirmed mapping Mock Entity 1 → AVM-US the dry run's prerequisite
    # check asks the tenant for AVM-US and never for the legacy text; present → passes, absent →
    # refused by the TARGET's name. A by-table session records the codes each SELECT asked for.
    staging = opening_balances.stage(
        legacy_db.rows(FIXTURE), CUTOVER, entity_codes={"Mock Entity 1": "AVM-US"}
    )
    contract = next(c for c in staging.contracts if c.entity_code == "AVM-US")
    templates = {
        code: UUID(int=0x700 + i)
        for i, code in enumerate(sorted({row.mapped.template_code for row in contract.rows}))
    }

    class _ByTable:
        def __init__(self, entities: tuple[str, ...]) -> None:
            self.entities = entities
            self.asked: list[str] = []

        def execute(self, statement: Any, params: Any = None) -> _Result:
            compiled = statement.compile(dialect=postgresql.dialect())
            sql = str(compiled)
            if "FROM erev.legal_entity" in sql:
                wanted = [
                    str(item)
                    for value in compiled.params.values()
                    for item in (value if isinstance(value, list) else [value])
                ]
                self.asked.extend(wanted)
                return _Result(rows=tuple((e,) for e in self.entities if e in wanted))
            if "FROM erev.product" in sql:
                return _Result(
                    rows=tuple(
                        {
                            "code": row.mapped.product_code,
                            "default_pob_template_id": templates[row.mapped.template_code],
                        }
                        for row in contract.rows
                    )
                )
            if "FROM erev.pob_template" in sql:
                return _Result(rows=tuple((i, code) for code, i in templates.items()))
            if "FROM erev.ssp_entry" in sql:
                # 04 rev 1.72: the APPROVED LEGACY-SKU-SSP entry of every staged line
                # (label, SKU, stratification)
                return _Result(
                    rows=tuple(
                        (
                            row.mapped.ssp_version_label,
                            row.mapped.product_code,
                            row.mapped.stratification or "",
                            "10",
                            "0",
                        )
                        for row in contract.rows
                    )
                )
            if "FROM erev.tenant_currency" in sql:
                return _Result(rows=((CURRENCY,),))
            return _Result()

    session = _ByTable(entities=("AVM-US", "Mock Entity 2"))  # the legacy text is ABSENT
    capture.PlatformApplier._check_prerequisites(session, contract, CURRENCY)  # AVM-US present
    assert "AVM-US" in session.asked and "Mock Entity 1" not in session.asked
    absent = _ByTable(entities=("Mock Entity 2",))
    with pytest.raises(Problem) as refused:
        capture.PlatformApplier._check_prerequisites(absent, contract, CURRENCY)
    detail = refused.value.detail or ""
    assert "entity 'AVM-US'" in detail and "Mock Entity 1" not in detail


def test_canonical_row_is_the_stored_representation_hashed() -> None:
    row = {
        "id": UUID(int=7),
        "revenue_cum": Decimal("295.69"),
        "original_allocated_exact": Decimal("1300.000000000000000000"),
        "start_date": date(2023, 1, 1),
        "known_at": KNOWN_AT,
        "trace_nodes": {"revenue_cum": "n1"},
        "hold_types": ["A", "B"],
        "memo_1": None,
        "obligation_kind": SimpleNamespace(value="STANDARD"),
    }
    document, digest = capture.canonical_row(row)
    assert document["id"] == str(UUID(int=7))
    assert document["revenue_cum"] == "295.69"
    assert document["original_allocated_exact"] == "1300.000000000000000000"  # as stored
    assert document["start_date"] == "2023-01-01" and document["memo_1"] is None
    assert document["obligation_kind"] == "STANDARD"
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert digest == hashlib.sha256(encoded.encode()).hexdigest()


# --- the dry run over fakes -----------------------------------------------------------------------


class _Result:
    def __init__(self, *, rows: tuple[Any, ...] = (), scalar: Any = None) -> None:
        self._rows, self._scalar = rows, scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalars(self) -> list[Any]:
        return [row[0] if isinstance(row, tuple) else row for row in self._rows]

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar

    def __iter__(self) -> Any:
        return iter(self._rows)


class _Savepoint:
    def __init__(self) -> None:
        self.rolled_back = 0
        self.committed = 0

    def rollback(self) -> None:
        self.rolled_back += 1

    def commit(self) -> None:
        self.committed += 1


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[str] = []
        self.savepoints: list[_Savepoint] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self.calls.append(str(statement.compile(dialect=postgresql.dialect())))
        return self.results.pop(0) if self.results else _Result()

    def begin_nested(self) -> _Savepoint:
        savepoint = _Savepoint()
        self.savepoints.append(savepoint)
        return savepoint


class _Uow:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.now = KNOWN_AT
        self.principal = SimpleNamespace(
            id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=UUID(int=1)
        )
        self.buffered: list[Any] = [{"kept": True}]

    def drain_audit_events(self) -> list[Any]:
        drained, self.buffered = self.buffered, []
        return drained

    def buffer_audit_event(self, event: Any) -> None:
        self.buffered.append(event)


def _trace() -> tuple[Trace, dict[str, Any]]:
    node = TraceNode(
        id="revenue_cum:POB #1",
        measure="revenue_cum",
        value="295.69",
        currency="USD",
        formula_id="f",
        inputs=(),
        params={},
        rounding_residue="0.001234567800000000",
        narrative_key="k",
    )
    trace = Trace(format_version=1, engine_version="test", nodes=(node,), root_measures={})
    from erev_api.explain.store import trace_document

    return trace, trace_document(trace)


VERSION_ID, GROUP_ID, COMPUTATION_ID, TRACE_ID = (
    UUID(int=100),
    UUID(int=200),
    UUID(int=300),
    UUID(int=400),
)
CONTRACT_ID, OBLIGATION_VERSION_ID, OPENING_EVENT_ID = UUID(int=500), UUID(int=600), UUID(int=700)
INPUT_SHA = "a" * 64
OPENING_PAYLOAD_SHA = "e" * 64  # the bundle's opening event payload_sha256 (the hash-bound side)
# canonical evidence bytes the reader stores and digests (decoding is the reconcile's step)
EVIDENCE = b'{"bundle":{},"evidence_format":1}'


def _applied(offset: int = 0, *, contract: str = "Contract 1") -> capture.Applied:
    """What the applier hands the reader: the bundle facts of one dry-run contract."""
    return capture.Applied(
        contract_id=UUID(int=CONTRACT_ID.int + offset),
        combination_group_id=UUID(int=GROUP_ID.int + offset),
        bundle_known_at=KNOWN_AT,
        bundle_member_keys=frozenset({contract}),
        opening_event_key=f"{contract}/EV-000003",
        opening_payload_sha256=OPENING_PAYLOAD_SHA,
        input_sha256=INPUT_SHA,
        input_evidence=EVIDENCE,
    )


def _engine_rows(
    *,
    versions: int = 1,
    with_trace: bool = True,
    obligations: int = 1,
    payload_batch: UUID | None = BATCH,
    offset: int = 0,
    member_key: str = "Contract 1",
) -> list[_Result]:
    """The queued reads of ``read_version`` in call order: contract versions, the computation, the
    calc trace, the obligation versions, the members, the event stream. ``offset`` distinguishes
    the identities of several dry-run contracts (each has its own group and version)."""
    trace, document = _trace()
    version = {
        "id": UUID(int=VERSION_ID.int + offset),
        "combination_group_id": UUID(int=GROUP_ID.int + offset),
        "contract_computation_id": COMPUTATION_ID,
        "book_code": "ASC606",
        "version_no": 1,
        "status_in_book": "ACTIVE",
        "output_sha256": "b" * 64,
        "calc_trace_id": TRACE_ID,
        "known_at": KNOWN_AT,
    }
    computation = {
        "id": COMPUTATION_ID,
        "input_sha256": INPUT_SHA,
        "engine_version": "test",
        "engine_release_id": None,
    }
    trace_row = {
        "id": TRACE_ID,
        "contract_version_id": VERSION_ID,
        "book_code": "ASC606",
        "format_version": 1,
        "engine_version": "test",
        "trace_sha256": trace.sha256(),
        "node_count": 1,
        "root_measures": {},
        "trace": document,
    }
    obligation = {
        "id": OBLIGATION_VERSION_ID,
        "contract_version_id": VERSION_ID,
        "contract_id": CONTRACT_ID,
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": Decimal("1300"),
        "remaining_quantity": Decimal("0"),
        "billed_cum": Decimal("300.00"),
        "revenue_cum": Decimal("295.69"),
        "remaining_allocation": Decimal("1004.31"),
        "position_obligation": Decimal("4.31"),
        "netting_reclass_amount": Decimal("0.00"),
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
        "contract_external_id": "Contract 1",
    }
    payload = {
        "reason": "LEGACY_MIGRATION",
        "cutover_date": CUTOVER.isoformat(),
        "migration_batch_id": None if payload_batch is None else str(payload_batch),
    }
    event = {
        "id": UUID(int=OPENING_EVENT_ID.int + offset),
        "event_type": "OPENING_BALANCE_ESTABLISHED",
        "stream_version": 3,
        "payload": payload,
    }
    return [
        _Result(rows=tuple(dict(version) for _ in range(versions))),
        _Result(rows=(computation,)),
        _Result(rows=(trace_row,) if with_trace else ()),
        _Result(rows=tuple(obligation for _ in range(obligations))),
        _Result(rows=((UUID(int=CONTRACT_ID.int + offset), member_key),)),
        _Result(rows=(event,)),
    ]


class _FakeApplier:
    def __init__(self) -> None:
        self.applied: list[str] = []

    def apply(self, uow: UnitOfWork, *, batch: Any, contract: ContractOpening) -> capture.Applied:
        offset = len(self.applied)
        self.applied.append(contract.external_id)
        return _applied(offset, contract=contract.external_id)


def test_read_version_captures_identities_provenance_members_output_and_the_trace_mirror() -> None:
    session = _Session(*_engine_rows())
    applied = _applied()
    version, obligations = capture.read_version(
        session, applied=applied, capture_operation_id=OPERATION
    )
    assert version.contract_version_id == VERSION_ID and version.calc_trace_id == TRACE_ID
    assert version.contract_computation_id == COMPUTATION_ID
    assert (version.input_sha256, version.output_sha256) == ("a" * 64, "b" * 64)
    assert version.cutover_date == CUTOVER and version.payload_migration_batch_id == BATCH
    assert version.members == (capture.Member(CONTRACT_ID, "Contract 1"),)
    assert version.obligation_version_ids == (OBLIGATION_VERSION_ID,)
    # the folded provenance (Codex 0422): the bundle's own cutoff, the event it consumed, the
    # operation, and that the output WAS read (an empty tuple is observed, never omitted)
    assert version.bundle_known_at == KNOWN_AT and version.opening_event_id == OPENING_EVENT_ID
    # Codex 0605 R1: the declared event UUID is bound to the bundle's logical opening event at
    # capture — the retained key is the bundle's and the binding digest recomputes from all three
    assert version.opening_event_key == "Contract 1/EV-000003"
    assert version.opening_event_binding_sha256 == capture.opening_event_binding(
        OPENING_EVENT_ID, "Contract 1/EV-000003", OPENING_PAYLOAD_SHA
    )
    assert version.opening_event_binding_sha256 != capture.opening_event_binding(
        UUID(int=OPENING_EVENT_ID.int + 1), "Contract 1/EV-000003", OPENING_PAYLOAD_SHA
    )
    assert version.capture_operation_id == OPERATION and version.expected_output_captured is True
    assert version.input_sha256 == INPUT_SHA
    # Codex 0515 R1: the producing input's evidence is retained with its raw digest
    from erev_engine.upgrade import raw_digest

    assert version.input_evidence == {"bundle": {}, "evidence_format": 1}
    assert version.input_evidence_sha256 == raw_digest(EVIDENCE)
    trace, document = _trace()
    assert version.trace_sha256 == trace.sha256() and version.trace == document
    (item,) = obligations
    assert item.obligation_version_id == OBLIGATION_VERSION_ID and item.contract_id == CONTRACT_ID
    assert item.revenue_cum == Decimal("295.69") and item.trace_nodes == {
        "revenue_cum": "revenue_cum:POB #1"
    }
    assert item.row["revenue_cum"] == "295.69" and "contract_external_id" not in item.row
    assert len(item.row_sha256) == 64
    # the ref binds membership, expected output and provenance for the reconcile
    ref = version.ref()
    assert ref.contract_ids == {CONTRACT_ID} and ref.obligation_version_ids == {
        OBLIGATION_VERSION_ID
    }
    assert (ref.cutover_date, ref.payload_migration_batch_id) == (CUTOVER, BATCH)
    # the group's rows were read from the engine tables inside the savepoint
    assert any("FROM erev.contract_version" in call for call in session.calls)
    assert any("FROM erev.calc_trace" in call for call in session.calls)


def test_read_version_admits_an_empty_output_and_refuses_missing_or_ambiguous_evidence() -> None:
    applied = _applied()
    # D-98-78: a version with no obligation rows is a legitimate, captured-empty result
    version, obligations = capture.read_version(
        _Session(*_engine_rows(obligations=0)), applied=applied, capture_operation_id=OPERATION
    )
    assert obligations == () and version.obligation_version_ids == ()
    assert version.expected_output_captured is True  # observed empty, not omitted
    for what, rows in (
        ("computes exactly one", _engine_rows(versions=2)),
        ("computes exactly one", _engine_rows(versions=0)),
        ("no calc trace", _engine_rows(with_trace=False)),
        ("names no migration", _engine_rows(payload_batch=None)),
        ("not the members the producing bundle selected", _engine_rows(member_key="Contract 9")),
    ):
        with pytest.raises(capture.CaptureError, match=what):
            capture.read_version(_Session(*rows), applied=applied, capture_operation_id=OPERATION)
    # another bundle's computation, or another event than the bundle consumed — refused
    with pytest.raises(capture.CaptureError, match="computed from another bundle"):
        capture.read_version(
            _Session(*_engine_rows()),
            applied=dataclasses.replace(applied, input_sha256="f" * 64),
            capture_operation_id=OPERATION,
        )
    with pytest.raises(capture.CaptureError, match="not the event the producing bundle consumed"):
        capture.read_version(
            _Session(*_engine_rows()),
            applied=dataclasses.replace(applied, opening_event_key="Contract 1/EV-000009"),
            capture_operation_id=OPERATION,
        )


def test_dry_run_applies_reads_and_rolls_the_savepoint_back() -> None:
    staging = _staging()
    session = _Session(
        *[
            result
            for index, contract in enumerate(staging.contracts)
            for result in _engine_rows(offset=index, member_key=contract.external_id)
        ]
    )
    uow = _Uow(session)
    applier = _FakeApplier()
    children: list[_Uow] = []

    def child(outer: Any) -> Any:
        unit = _Uow(outer.session)
        unit.buffered = []
        children.append(unit)
        return unit

    captured = capture.dry_run(
        cast(UnitOfWork, uow), _batch(), staging, applier=applier, unit_factory=child
    )
    assert applier.applied == [c.external_id for c in staging.contracts]
    assert len(captured.versions) == 4 and len(captured.obligations) == 4
    assert captured.batch_id == BATCH and captured.cutover_date == CUTOVER
    assert captured.capture_operation_id == OPERATION
    (savepoint,) = session.savepoints
    assert savepoint.rolled_back == 1 and savepoint.committed == 0  # nothing survives
    assert uow.buffered == [{"kept": True}]  # the caller's audit events untouched
    (unit,) = children
    assert unit.buffered == []  # the child's events drained with it; nothing handed over
    population = captured.population(_batch())
    assert population.batch_id == BATCH and len(population.versions) == 4
    population.check_batch(_batch())


def test_dry_run_refuses_by_name_and_still_rolls_back_on_a_capture_error() -> None:
    staging = _staging()
    # a non-OPENING_BALANCES batch, pending rows and option records are refused before any apply
    with pytest.raises(Problem, match="captures OPENING_BALANCES"):
        capture.dry_run(
            cast(UnitOfWork, _Uow(_Session())),
            _batch(mode="REPLAY"),
            staging,
            applier=_FakeApplier(),
        )
    pending_row = dataclasses.replace(
        staging.contracts[0].rows[0],
        mapped=dataclasses.replace(
            staging.contracts[0].rows[0].mapped,
            pending=SimpleNamespace(policy="POL-211", choice="SERIES", detail="pending"),
        ),
    )
    pending = dataclasses.replace(
        staging.contracts[0], obligations=(pending_row, *staging.contracts[0].obligations[1:])
    )
    with_pending = dataclasses.replace(staging, contracts=(pending, *staging.contracts[1:]))
    with pytest.raises(Problem, match="POL-211"):
        capture.dry_run(
            cast(UnitOfWork, _Uow(_Session())), _batch(), with_pending, applier=_FakeApplier()
        )
    # an ambiguous computed result mid-run: refused by name, the savepoint rolled back
    session = _Session(*_engine_rows(versions=2))
    uow = _Uow(session)
    with pytest.raises(Problem, match="computes exactly one") as refused:
        capture.dry_run(
            cast(UnitOfWork, uow),
            _batch(),
            staging,
            applier=_FakeApplier(),
            unit_factory=lambda outer: outer,
        )
    assert refused.value.errors[0].rule_id == capture.RULE
    assert session.savepoints[0].rolled_back == 1  # nothing survives the refusal either


def test_computation_refusal_carries_the_engine_finding_json() -> None:
    # integrated batch #9 (S07-R-03 diagnostic): a blocking finding stops the dry run with
    # EngineError(code, "a stage collected a blocking finding (CV-15)", detail={"findings": …});
    # the refusal keeps its detail text and adds the finding JSON as a second error, so the job
    # problem names the rule, the sub-check, the reason and the figures — without it batch #9
    # showed only the code
    findings = json.dumps(
        [
            {
                "book_code": "ASC606",
                "code": "OPENING_BALANCE_INCONSISTENT",
                "detail": {"rule": "S07-R-03", "reason": "transaction_price"},
                "severity": "ERROR",
                "stage": 7,
            }
        ]
    )
    error = EngineError(
        "OPENING_BALANCE_INCONSISTENT",
        "a stage collected a blocking finding (CV-15)",
        subject_key="Contract 1",
        detail={"findings": findings},
    )
    refused = capture.computation_refusal("Contract 1", error)
    assert refused.detail == (
        "The dry-run computation of Contract 1 ended refused: OPENING_BALANCE_INCONSISTENT: "
        "a stage collected a blocking finding (CV-15); the import captures nothing for it."
    )
    assert [e.rule_id for e in refused.errors] == [capture.RULE, capture.RULE]
    assert refused.errors[0].message == refused.detail and refused.errors[1].message == findings
    # an engine error without findings keeps the single error (nothing invented)
    bare = capture.computation_refusal("Contract 1", EngineError("X", "stopped"))
    assert len(bare.errors) == 1
    assert bare.detail.endswith("refused: X: stopped; the import captures nothing for it.")


def test_platform_applier_refuses_missing_prerequisites_by_name() -> None:
    # entities absent, products absent, currency not enabled — named, nothing created or invented
    contract = _staging().contracts[0]
    session = _Session(
        _Result(rows=()),  # entities
        _Result(rows=()),  # products
        _Result(rows=()),  # templates
        _Result(rows=()),  # currency
    )
    with pytest.raises(Problem) as refused:
        capture.PlatformApplier._check_prerequisites(session, contract, CURRENCY)
    detail = refused.value.detail or ""
    assert detail.startswith("The tenant lacks a booking prerequisite of Contract 1")
    assert "entity 'Mock Entity 1'" in detail and "product 'Software 1'" in detail
    assert "reporting currency 'USD' not enabled" in detail
    assert "nothing is invented" in detail


def test_opening_payload_is_the_registered_latest_version_and_exponent_text_is_not_guessed() -> (
    None
):
    # D-98 127 consumer switch: the applier builds the registered LATEST payload model (version 1
    # today — MoneyIn, four places — version 2 when B4's 04 rev 1.61 lands); exponent text needs
    # the payload owner's exact_plain_decimal and is refused by name while it is absent.
    from erev_api import money
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import LATEST_SCHEMA_VERSION

    version, model = capture.opening_payload_model()
    assert version == LATEST_SCHEMA_VERSION[ContractEventType.OPENING_BALANCE_ESTABLISHED]
    assert model.__name__.startswith("OpeningBalanceEstablishedV")
    assert capture.exact_text(Decimal("295.6912345"), what="x") == "295.6912345"
    assert capture.exact_text("300", what="x") == "300"
    if getattr(money, "exact_plain_decimal", None) is None:
        with pytest.raises(Problem, match="exact_plain_decimal"):
            capture.exact_text("1e-05", what="Contract 1 POB #1 revenue_cum")

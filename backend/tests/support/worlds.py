"""Test worlds built through commands (BUILD_SPEC CLO-8; CLO-9 adds the legacy UAT ledger; RPS-3
adds the PRD §2.7 worlds).

``journal_world`` is the CLO-8 world of the January 2023 journals (POLICIES CHK-020, CHK-022;
WLD-X-26). Golden steps 01 to 03 are replayed under ``LEGACY_PARITY`` (``support.legacy_replay``),
so the contracts, obligations, entities, calendar and accounts are real. The revenue accounts 5001
to 5003 are added, and both entities keep the LEGACY book from FY2023-P01 with P01 and P02 open.

[J] L6-3-Q-1 (D-82 V-C): the platform replay of step 04 does not yet post the engine's CHK-022
lines. It posts revenue at the mapping's 4000 instead of the SKU Revenue Account, posts no JET-06
reclass without the close-release pass, and posts no LEGACY book. So ``post_chk_022`` and
``post_pre_standard`` write the engine intents that ``backend/tests/engine/s14_posting/
test_chk_delta.py`` pins, as sealed postings through ``subledger.post``. The JET-06 reclass joins
Contract 2's ``ENGINE_COMPUTE`` posting as entry 2, because ``CLOSE_RELEASE`` postings need a close
run (T-SL-01), and the S14 summariser reads entry kinds, not posting kinds.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_computation,
    gl_account,
    job,
    legal_entity,
    obligation,
    period,
)
from erev_api.domain.contracts.commands import BookedContract
from erev_api.domain.journals import subledger
from erev_api.enums import ContractEventType, SubledgerPostingKind
from erev_api.events.payloads import BillingRecordedV1, ProgressRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.money import MoneyIn
from erev_engine.bundle import InputBundle
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.money import minor_to_decimal
from fastapi import FastAPI
from sqlalchemy import select, text
from support import golden_streams, intent_totals
from support.factories import (
    K02_EXTERNAL_ID,
    SEAT_MONTH,
    TPL_SUB_DAILY,
    TPL_SVC_PCT,
    Workspace,
    appended,
    approved_ssp_version,
    booked_contract,
    computed,
    customer_id,
    k02_seat_month_body,
    point_entry,
    product_with_template,
    published_mapping,
    published_template,
    range_entry,
    set_default_template,
    ssp_book,
    stamp_test_release,
    step1_criteria,
    workspace,
    world_calendar,
)
from support.legacy_replay import LegacyWorld, legacy_world, replayed
from support.modifications import confirm_answers
from support.parity import scenario as parity_scenario
from support.principals import Actor, colleague, enrolled, member, sign_in
from support.principals import workspace as signed_workspace
from support.reference import PERIODS, approve, assign, get, holding, periods, post, put
from support.reference import gl_account as new_gl_account

JOURNAL_RUNS: Final = "/api/v1/journal-runs"
RUN_ID_HEADER: Final = "X-Erev-Journal-Run-Id"
ENTITY_1: Final = "Mock Entity 1"
ENTITY_2: Final = "Mock Entity 2"
JANUARY: Final = "FY2023-P01"
FEBRUARY: Final = "FY2023-P02"
REVENUE_ROLES: Final = frozenset({"REVENUE", "PRE_STANDARD_REVENUE"})
SKU_REVENUE_ACCOUNTS: Final = (
    ("5001", "Revenue - Hardware 1"),
    ("5002", "Revenue - Software 1"),
    ("5003", "Revenue - Consulting 1"),
)


@dataclass(frozen=True, slots=True)
class ContractRef:
    id: UUID
    external_id: str
    entity_id: UUID
    group_id: UUID
    computation_id: UUID
    obligations: Mapping[str, tuple[UUID, str]]  # obligation key → (id, legacy record key)


@dataclass(frozen=True, slots=True)
class JournalWorld:
    legacy: LegacyWorld
    entities: Mapping[str, UUID]
    accounts: Mapping[str, UUID]
    periods: Mapping[str, tuple[UUID, date]]
    contracts: Mapping[str, ContractRef]

    @property
    def app(self) -> FastAPI:
        return self.legacy.app


def _keep_legacy_book(world: LegacyWorld) -> None:
    for code, entity_id in world.entity_ids.items():
        kept = put(
            world.app,
            f"/api/v1/entities/{entity_id}/books/LEGACY",
            world.marcus,
            {"is_enabled": True, "first_period_key": JANUARY},
        )
        assert kept.status_code in (200, 201), kept.text
        states = {
            item["period"]["period_key"]: item
            for item in periods(world.app, world.maya, entity=code, book="LEGACY")
        }
        for key in (JANUARY, FEBRUARY):
            state = states[key]
            if state["state"] == "open":
                continue
            opened = post(
                world.app,
                f"{PERIODS}/{state['id']}/open",
                world.maya,
                {"comment": "LEGACY book of the parity world"},
                if_match=f'"r{state["row_version"]}"',
            )
            assert opened.status_code == 200, opened.text


def journal_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> JournalWorld:
    """The CLO-8 world (module docstring)."""
    legacy = legacy_world(app, keyring, clock, files)
    replayed(legacy, "03")
    _add_sku_revenue_accounts(legacy)
    _keep_legacy_book(legacy)
    return _references(legacy)


def _add_sku_revenue_accounts(legacy: LegacyWorld) -> None:
    """The SKU Revenue Accounts 5001 to 5003 of the SSP upload (POLICIES §6.3 mapping preset)."""
    existing = {str(row["code"]) for row in legacy.imports.rows(select(gl_account.c.code))}
    for code, name in SKU_REVENUE_ACCOUNTS:
        if code not in existing:
            new_gl_account(
                legacy.app,
                legacy.maya,
                code=code,
                name=name,
                account_type="REVENUE",
                normal_balance="C",
            )


def _references(legacy: LegacyWorld) -> JournalWorld:
    """The entities, accounts, periods, contracts and obligations of a replayed legacy world."""
    rows = legacy.imports.rows
    accounts = {
        str(row["code"]): row["id"] for row in rows(select(gl_account.c.code, gl_account.c.id))
    }
    entities = {
        str(row["code"]): row["id"] for row in rows(select(legal_entity.c.code, legal_entity.c.id))
    }
    months = {
        str(row["period_key"]): (row["id"], row["end_date"])
        for row in rows(select(period.c.period_key, period.c.id, period.c.end_date))
    }
    obligations: dict[UUID, dict[str, tuple[UUID, str]]] = {}
    for row in rows(
        select(
            obligation.c.contract_id,
            obligation.c.id,
            obligation.c.obligation_key,
            obligation.c.legacy_record_key,
        )
    ):
        obligations.setdefault(row["contract_id"], {})[str(row["obligation_key"])] = (
            row["id"],
            str(row["legacy_record_key"]),
        )
    computations: dict[UUID, UUID] = {}
    for row in rows(
        select(contract_computation.c.combination_group_id, contract_computation.c.id).order_by(
            contract_computation.c.id
        )
    ):
        computations[row["combination_group_id"]] = row["id"]
    contracts = {
        str(row["external_id"]): ContractRef(
            id=row["id"],
            external_id=str(row["external_id"]),
            entity_id=row["contracting_entity_id"],
            group_id=row["combination_group_id"],
            computation_id=computations[row["combination_group_id"]],
            obligations=obligations.get(row["id"], {}),
        )
        for row in rows(
            select(
                contract.c.id,
                contract.c.external_id,
                contract.c.contracting_entity_id,
                contract.c.combination_group_id,
            )
        )
    }
    return JournalWorld(
        legacy=legacy, entities=entities, accounts=accounts, periods=months, contracts=contracts
    )


Line = tuple[
    str, str, str, str | None
]  # (account role, GL account code, signed amount, obligation)


def post_lines(
    world: JournalWorld,
    *,
    key: str,
    contract_key: str,
    entries: Sequence[tuple[str, Sequence[Line]]],
    book: str = "ASC606",
    period_key: str = JANUARY,
    origin_key: str | None = None,
) -> int:
    """One sealed ``ENGINE_COMPUTE`` posting of ``entries`` (entry kind, lines) for a contract;
    the posting's chain sequence. A revenue line carries the obligation's legacy record key, any
    other line the contract's external id (L3-1-Q-30)."""
    found = world.contracts[contract_key]
    period_id, period_end = world.periods[period_key]
    origin_id = None if origin_key is None else world.periods[origin_key][0]
    lines: list[dict[str, Any]] = []
    for entry_no, (entry_kind, members) in enumerate(entries, start=1):
        for role, account, amount, obligation_key in members:
            obligation_id, legacy_key = found.obligations.get(obligation_key or "", (None, None))
            dimensions = {"contract_key": contract_key, "obligation_key": obligation_key or ""}
            lines.append(
                {
                    "period_end_date": period_end,
                    "entity_id": found.entity_id,
                    "period_id": period_id,
                    "origin_period_id": origin_id,
                    "reason_code": None if origin_id is None else "LATE_EVENT",
                    "effective_date": period_end,
                    "entry_no": entry_no,
                    "entry_kind": entry_kind,
                    "account_role": role,
                    "clearing_purpose": None,
                    "gl_account_id": world.accounts[account],
                    "dimensions": dimensions,
                    "dimension_set_sha256": subledger.dimension_set_sha256(dimensions),
                    "txn_currency": "USD",
                    "amount_txn": Decimal(amount),
                    "functional_currency": "USD",
                    "amount_functional": Decimal(amount),
                    "contract_id": found.id,
                    "obligation_id": obligation_id,
                    "legacy_key": legacy_key if role in REVENUE_ROLES else contract_key,
                }
            )
    with world.legacy.place().uow() as uow:
        posted = subledger.post(
            uow,
            book_code=book,
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"clo-8:{key}",
            description=f"CLO-8 probe {key}",
            lines=lines,
            combination_group_id=found.group_id,
            contract_computation_id=found.computation_id,
        )
        uow.commit()
    return posted.chain_seq


def post_chk_022(world: JournalWorld) -> None:
    """The January 2023 ASC606 intents of CHK-022 (test_chk_delta.test_chk_022_january_gross)."""
    post_lines(
        world,
        key="chk-022-contract-1",
        contract_key="Contract 1",
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "128.84", "POB #1"),
                    ("REVENUE", "5001", "-128.84", "POB #1"),
                ],
            ),
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "118.53", "POB #2"),
                    ("REVENUE", "5002", "-118.53", "POB #2"),
                ],
            ),
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "48.32", "POB #3"),
                    ("REVENUE", "5003", "-48.32", "POB #3"),
                ],
            ),
        ],
    )
    post_lines(
        world,
        key="chk-022-contract-2",
        contract_key="Contract 2",
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21002", "58.85", "POB #1"),
                    ("REVENUE", "5001", "-58.85", "POB #1"),
                ],
            ),
            (
                "NETTING_RECLASS",
                [
                    ("CONTRACT_ASSET", "15002", "58.85", "POB #1"),
                    ("CONTRACT_LIABILITY", "21002", "-58.85", "POB #1"),
                ],
            ),
        ],
    )


def post_pre_standard(world: JournalWorld) -> None:
    """The January 2023 LEGACY intents of CHK-020: Contract 1 pre-standard revenue POB #2 66.00 and
    POB #3 88.00 (test_chk_delta.test_chk_020_january_delta)."""
    post_lines(
        world,
        key="chk-020-legacy-contract-1",
        contract_key="Contract 1",
        book="LEGACY",
        entries=[
            (
                "PRE_STANDARD_REVENUE",
                [
                    # D-89 L7-6-Q-8: Dr PRE_STANDARD_REVENUE / Cr CONTRACT_LIABILITY.
                    ("CONTRACT_LIABILITY", "21001", "-66.00", "POB #2"),
                    ("PRE_STANDARD_REVENUE", "5002", "66.00", "POB #2"),
                ],
            ),
            (
                "PRE_STANDARD_REVENUE",
                [
                    ("CONTRACT_LIABILITY", "21001", "-88.00", "POB #3"),
                    ("PRE_STANDARD_REVENUE", "5003", "88.00", "POB #3"),
                ],
            ),
        ],
    )


def requested_run(world: JournalWorld, body: Mapping[str, Any]) -> tuple[UUID, UUID]:
    """``POST /journal-runs`` as Maya; (job id, run id)."""
    created = post(world.app, JOURNAL_RUNS, world.legacy.maya, dict(body))
    assert created.status_code == 202, created.text
    return UUID(str(created.json()["id"])), UUID(created.headers[RUN_ID_HEADER])


def calculated_run(
    world: JournalWorld,
    *,
    entity: str,
    grain: str = "LEGACY_CONTRACT_POB",
    mode: str = "GROSS",
    period_key: str = JANUARY,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Request a run, run its job as the worker does, then read API-S-JournalRun and its lines."""
    from support.factories import run_import_job

    job_id, run_id = requested_run(
        world,
        {"entity_code": entity, "period_key": period_key, "grain": grain, "mode": mode},
    )
    run_import_job(world.legacy.imports, job_id)
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    listed = get(world.app, f"{JOURNAL_RUNS}/{run_id}/lines", world.legacy.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    return dict(shown.json()), list(listed.json()["items"])


def by_account(lines: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    """(account code, debit, credit) of each line, in account order."""
    return sorted(
        (item["account"]["code"], item["debit_txn"]["amount"], item["credit_txn"]["amount"])
        for item in lines
    )


# --- The legacy UAT ledger of the legacy journal views (BUILD_SPEC CLO-9) -------------------------
#
# [J] L6-3-Q-37 (D-82 V-C). ``uat_ledger_world`` builds the DG-PAR-04 world through
# ``support.parity.scenario`` and replays golden steps 01 to 03 through the legacy v1 import
# pipeline, so the tenant, preset, entities, calendar, LEGACY book, accounts, contracts and
# obligations are real. The subledger then holds the engine's posting intents of the legacy UAT
# through step 14, sealed through ``subledger.post`` as ``computation._post_book`` seals a
# computation: ``intent_totals.computations`` of each contract's activated golden stream under
# ``LEGACY_PARITY`` with the books ASC606 and LEGACY, that is ``compute`` and the JET-06
# ``NETTING_RECLASS`` close pass (RCP-08(b)). The platform replay of steps 04 to 14 does not yet
# post these lines at this lane head (probe of 2026-09-15): revenue goes to the mapping's 4000 and
# pre-standard revenue to 4900 instead of the SKU Revenue Account, no JET-06 reclass is posted
# without the close-release pass (CLO-20, post-rc), stage 01 refuses the VC-line credit memos of
# Contracts 2 and 4 (fixed on sprint/l2 by 499fb57), and the step 14 upload is INVALID (fixed on
# sprint/l2 by 94dafb7).

UAT_CONTRACTS: Final = ("Contract 1", "Contract 2", "Contract 3", "Contract 4")
UAT_FINAL_STEP: Final = "14"
LEGACY_PRESET: Final = "LEGACY_PARITY"
REFUND_EXCEEDS_BILLED: Final = "REFUND_EXCEEDS_BILLED"
# The periods the parity world keeps open in both books (support.parity.scenario OPEN_KEYS).
UAT_HORIZON: Final = frozenset(f"FY2023-P{month:02d}" for month in range(1, 13))


def uat_bundle(contract_key: str, through_step: str = UAT_FINAL_STEP) -> InputBundle:
    """The activated golden stream of a legacy contract as ``support.intent_totals.golden`` builds
    it: the ``LEGACY_PARITY`` preset with the books ASC606 and LEGACY."""
    stream = golden_streams.stream(contract_key, through_step)
    return intent_totals.activated(
        stream.input_bundle(preset=LEGACY_PRESET, books=intent_totals.BOOKS)
    )


def without_vc_credit_memos(value: InputBundle) -> InputBundle:
    """``value`` less the credit memos on parity VC lines (S03-R-18 stratification ``VC``)."""
    kept = tuple(
        event
        for event in value.events
        if not (
            event.event_type == "CREDIT_MEMO_RECORDED"
            and any(key.startswith("VC #") for key in event.obligation_keys)
        )
    )
    return dataclasses.replace(value, events=kept)


def uat_computations(value: InputBundle) -> tuple[intent_totals.Computed, ...]:
    """``compute`` and the ``NETTING_RECLASS`` pass over ``value``.

    [J] L6-3-Q-37: when stage 01 refuses a VC-line credit memo with ``REFUND_EXCEEDS_BILLED``
    (golden Contract 4 from step 06, Contract 2 at step 14), the computation runs without the
    VC-line credit memos. Under POL-004 ``ERP`` a credit memo posts no subledger line. Contract 4's
    contract asset is 0.00 at every month end with or without them, and Contract 2's is 0.00 at
    every month end from 31 October 2023, the date of its credit memo; so no journal line of the
    views changes. Once 499fb57 merges, the first computation succeeds and the fallback no longer
    runs."""
    try:
        return intent_totals.computations(value)
    except EngineError as error:
        subject = error.subject_key or ""
        if error.code != REFUND_EXCEEDS_BILLED or not subject.partition("/")[2].startswith("VC "):
            raise
    return intent_totals.computations(without_vc_credit_memos(value))


def _effective_dates(value: InputBundle) -> Callable[[str, str], date]:
    """``computation._effective_date`` (L3-1-Q-30): the latest effective date of the bundle's
    events inside a period of an entity, else that period's end date."""
    periods = {
        (entity_input.code, item.period_key): item
        for entity_input in value.entities
        for item in entity_input.periods
    }

    def of(entity_code: str, period_key: str) -> date:
        found = periods[(entity_code, period_key)]
        inside = [
            event.effective_date
            for event in value.events
            if found.start_date <= event.effective_date <= found.end_date
        ]
        return max(inside, default=found.end_date)

    return of


def post_engine_intents(
    world: JournalWorld,
    *,
    key: str,
    computed: Sequence[intent_totals.Computed],
    horizon: frozenset[str] = UAT_HORIZON,
) -> int:
    """Seal the posting intents of ``computed`` as the platform seals a computation: one
    ``ENGINE_COMPUTE`` posting per book of each output, entries in ``entry_key`` order, amounts
    signed debit positive (L6-3-Q-37). A revenue line carries its obligation's legacy record key;
    an obligation that a later golden step adds (Contract 1 POB #4, Contract 3 POB #5) has no row in
    the step 03 world, so the line names no obligation and carries the LM-CL-70 key
    ``<contract> <obligation> <product>``. Intents of periods outside ``horizon`` are not posted:
    they are the calendar's FY2024 netting pairs, which no view window reaches. Returns the number
    of lines posted."""
    posted_lines = 0
    for index, item in enumerate(computed, start=1):
        effective = _effective_dates(item.bundle)
        for book_output in item.output.books:
            intents = sorted(
                (
                    intent
                    for intent in book_output.posting_intents
                    if intent.posting_period_key in horizon
                ),
                key=lambda intent: intent.entry_key,
            )
            if not intents:
                continue
            lines: list[dict[str, Any]] = []
            found: ContractRef | None = None
            for entry_no, intent in enumerate(intents, start=1):
                period_id, period_end = world.periods[intent.posting_period_key]
                origin_id = (
                    None
                    if intent.origin_period_key is None
                    else world.periods[intent.origin_period_key][0]
                )
                effective_date = effective(
                    intent.entity, intent.origin_period_key or intent.posting_period_key
                )
                for line in intent.lines:
                    contract_key = str(line.dimensions["contract_key"])
                    found = world.contracts[contract_key]
                    obligation_key = str(line.dimensions.get("obligation_key", ""))
                    known = found.obligations.get(obligation_key)
                    obligation_id: UUID | None = None if known is None else known[0]
                    record_key = (
                        f"{contract_key} {obligation_key} {line.dimensions.get('product', '')}"
                        if known is None
                        else known[1]
                    )
                    sign = 1 if line.side == "D" else -1
                    txn_unit = ISO_4217[line.txn_currency].minor_unit
                    functional_unit = ISO_4217[line.functional_currency].minor_unit
                    amount = sign * minor_to_decimal(line.amount_txn, txn_unit)
                    lines.append(
                        {
                            "period_end_date": period_end,
                            "entity_id": world.entities[intent.entity],
                            "period_id": period_id,
                            "origin_period_id": origin_id,
                            "reason_code": intent.reason_code,
                            "effective_date": effective_date,
                            "entry_no": entry_no,
                            "entry_kind": intent.entry_kind,
                            "account_role": line.account_role,
                            "clearing_purpose": line.clearing_purpose,
                            "gl_account_id": world.accounts[line.account_code],
                            "dimensions": dict(sorted(line.dimensions.items())),
                            "dimension_set_sha256": subledger.dimension_set_sha256(line.dimensions),
                            "txn_currency": line.txn_currency,
                            "amount_txn": amount,
                            "functional_currency": line.functional_currency,
                            "amount_functional": sign
                            * minor_to_decimal(line.amount_functional, functional_unit),
                            "contract_id": found.id,
                            "obligation_id": obligation_id,
                            "legacy_key": record_key
                            if line.account_role == "REVENUE"
                            else contract_key,
                            "trace_node_id": line.trace_node_id,
                        }
                    )
            assert found is not None
            with world.legacy.place().uow() as uow:
                subledger.post(
                    uow,
                    book_code=book_output.book_code,
                    posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
                    idempotency_key=f"clo-9:{key}:{index}:{book_output.book_code}",
                    description=f"CLO-9 engine intents {key} ({index}, {book_output.book_code})",
                    lines=lines,
                    combination_group_id=found.group_id,
                    contract_computation_id=found.computation_id,
                )
                uow.commit()
            posted_lines += len(lines)
    return posted_lines


def uat_ledger_world(
    settings: Settings, keyring: KeyRing, *, tenant_code: str = parity_scenario.TENANT_CODE
) -> JournalWorld:
    """The legacy UAT ledger through golden step 14 (section comment); a second world in one
    session passes its own ``tenant_code`` (L6-3-Q-38; BUILD_SPEC RPS-5)."""
    built = parity_scenario.build(settings, keyring, tenant_code=tenant_code)
    built.through("03")
    legacy = built.world
    _add_sku_revenue_accounts(legacy)
    world = _references(legacy)
    for contract_key in UAT_CONTRACTS:
        post_engine_intents(
            world, key=f"uat:{contract_key}", computed=uat_computations(uat_bundle(contract_key))
        )
    return world


# --- PRD §2.7 worlds of the disclosure reports (BUILD_SPEC RPS-3, RPS-4) --------------------------

REPORT_RUNS: Final = "/api/v1/report-runs"
JOBS: Final = "/api/v1/jobs"
REPORT_RUN_ID_HEADER: Final = "x-erev-report-run-id"
AVM_US: Final = "AVM-US"
PLATFORM: Final = "AVM-PLAT-ENT"
IMPLEMENTATION: Final = "AVM-IMPL-STD"
K01: Final = "SF-ORD-10001"
K02: Final = K02_EXTERNAL_ID
K08: Final = "SF-ORD-10003"
API_CALL: Final = "AVM-API-CALL"
AUGUST_2026: Final = "FY2026-P08"
SEPTEMBER_2026: Final = "FY2026-P09"
THROUGH_SEPTEMBER: Final = date(2026, 9, 30)
_TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
PLATFORM_CASE: Final = {
    "obligation_key": "POB-01",
    "product_code": PLATFORM,
    "quantity": "1",
    "total_price": "120000.00",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
}
IMPLEMENTATION_CASE: Final = {
    "obligation_key": "POB-01",
    "product_code": IMPLEMENTATION,
    "quantity": "1",
    "total_price": "15000.00",
}
# PRD §2.6 TPL-USAGE: a series of usage transactions, satisfied over time, measured by usage.
TPL_USAGE: Final = MappingProxyType(
    {
        "distinctness": "series",
        "series_increment_unit": "transaction",
        "satisfaction_pattern": "OVER_TIME",
        "over_time_criterion": "OT_A",
        "recognition_method": "USAGE",
    }
)
API_CALL_CASE: Final = {
    "obligation_key": "POB-01",
    "product_code": API_CALL,
    "quantity": "250000",
    "total_price": "25000.00",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
}


@dataclass(frozen=True, slots=True)
class ReportWorld:
    """AVM-US with the key contracts of PRD §2.7 booked, activated, billed and computed."""

    place: Workspace
    priya: Actor
    marcus: Actor
    runtime: JobRuntime
    entity_id: UUID
    contracts: Mapping[str, BookedContract]

    @property
    def app(self) -> FastAPI:
        return self.place.app

    @property
    def maya(self) -> Actor:
        return self.place.author

    @property
    def tenant_id(self) -> UUID:
        return self.place.tenant_id


def _usd(amount: str) -> MoneyIn:
    return MoneyIn(amount=amount, currency="USD")


def _billing(invoice: str, amount: str, day: date, key: str) -> EventIn:
    payload = BillingRecordedV1(
        invoice_number=invoice,
        line_external_id=f"{invoice}-1",
        obligation_key=key,
        amount=_usd(amount),
        issue_date=day,
    )
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED, effective_date=day, payload=payload
    )


def _progress(key: str, ratio: str, day: date) -> EventIn:
    payload = ProgressRecordedV1(
        obligation_key=key, cumulative_progress_ratio=ratio, measure="OUTPUT_PERCENT"
    )
    return EventIn(
        event_type=ContractEventType.PROGRESS_RECORDED, effective_date=day, payload=payload
    )


def k01_body(customer: UUID) -> dict[str, Any]:
    """PRD WLD-K-01 ``SF-ORD-10001``: O1 AVM-PLAT-ENT 120,000.00 USD over 2026; O2 AVM-IMPL-STD
    15,000.00 USD; inception 2026-01-01."""
    return {
        "external_id": K01,
        "customer_id": str(customer),
        "contracting_entity_code": AVM_US,
        "transaction_currency": "USD",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PLATFORM,
                "quantity": "1",
                "total_price": {"amount": "120000.00", "currency": "USD"},
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
            {
                "obligation_key": "O2",
                "product_code": IMPLEMENTATION,
                "quantity": "1",
                "total_price": {"amount": "15000.00", "currency": "USD"},
            },
        ],
    }


def k08_body(customer: UUID) -> dict[str, Any]:
    """PRD WLD-K-08 ``SF-ORD-10003``: O1 AVM-API-CALL over 2026, booked as the demonstration
    tenant books it — the four quarterly minimums, 800,000 calls at 0.10, as its stated
    consideration of 80,000.00 USD ([J] L5-4-Q-5); inception 2026-01-01."""
    return {
        "external_id": K08,
        "customer_id": str(customer),
        "contracting_entity_code": AVM_US,
        "transaction_currency": "USD",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": API_CALL,
                "quantity": "800000",
                "total_price": {"amount": "80000.00", "currency": "USD"},
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            }
        ],
    }


def _seeded_events(external_id: str) -> tuple[EventIn, ...]:
    """The PRD §2.7 seeded billing and measure events. R-RC-1: K-02 carries no billing plan and no
    commission (CTR-14 post-rc) and no modification CR-MARROWBY-2026-09 (CTR-17 post-rc). K-08
    carries none: no usage is reported and nothing is invoiced, so time alone recognises its
    stated consideration (item CTR-TODATE-AWAITING-1)."""
    if external_id == K08:
        return ()
    if external_id == K01:
        return (
            _billing("INV-US-1001", "120000.00", date(2026, 1, 1), "O1"),
            _progress("O2", "0.40", date(2026, 1, 31)),
            _progress("O2", "1", date(2026, 2, 27)),
            _billing("INV-US-1044", "15000.00", date(2026, 2, 27), "O2"),
        )
    return (_billing("INV-US-1002", "120000.00", date(2026, 1, 1), "O1"),)


def report_world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    *,
    contracts: Sequence[str] = (K01,),
    through: date = THROUGH_SEPTEMBER,
) -> ReportWorld:
    """PRD §2.6 for AVM-US: Maya (Revenue Accountant, SSP Analyst) prepares; Priya (SSP Approver)
    approves US-LIST 2026-H1; Marcus (Controller, SSP Approver, Tenant Admin; MFA) enables USD and
    approves the templates and AVM-MAP-2026-01. FY2026-P01 to P09 are open. TPL-SUB-DAILY is the
    default of AVM-PLAT-ENT and AVM-SEAT-MO, TPL-SVC-PCT of AVM-IMPL-STD. Each named key contract
    is booked, activated, given its seeded events effective on or before ``through`` and computed
    once at the frozen clock. Only a world asked for K-08 holds AVM-API-CALL with TPL-USAGE, its
    observable point of 0.10 USD per call and customer C-08."""
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("ssp_approver",)),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    marcus = approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    _, entity_id = world_calendar(app, maya)
    usage = K08 in contracts
    customers = {
        K01: customer_id(app, maya, code="C-01", name="Pellworth Logistics Inc. (Demo)"),
        K02: customer_id(app, maya, code="C-02", name="Marrowby Health Partners LLC (Demo)"),
    }
    if usage:
        customers[K08] = customer_id(app, maya, code="C-08", name="Ulvane Telematics Inc. (Demo)")
    products = {
        PLATFORM: product_with_template(
            app,
            maya,
            code=PLATFORM,
            name="Platform, enterprise tier",
            revenue_category="SUBSCRIPTION",
        ),
        IMPLEMENTATION: product_with_template(
            app, maya, code=IMPLEMENTATION, name="Implementation", revenue_category="SERVICES"
        ),
        SEAT_MONTH: product_with_template(
            app,
            maya,
            code=SEAT_MONTH,
            name="Platform seat, per seat per month",
            revenue_category="SUBSCRIPTION",
        ),
    }
    daily = published_template(
        app, maya, marcus, code="TPL-SUB-DAILY", outputs=TPL_SUB_DAILY, case_line=PLATFORM_CASE
    )
    percent = published_template(
        app, maya, marcus, code="TPL-SVC-PCT", outputs=TPL_SVC_PCT, case_line=IMPLEMENTATION_CASE
    )
    for code in (PLATFORM, SEAT_MONTH):
        set_default_template(app, maya, products[code], daily["template_id"])
    set_default_template(app, maya, products[IMPLEMENTATION], percent["template_id"])
    if usage:
        calls = product_with_template(
            app, maya, code=API_CALL, name="API calls (usage)", revenue_category="SERVICES"
        )
        metered = published_template(
            app, maya, marcus, code="TPL-USAGE", outputs=TPL_USAGE, case_line=API_CALL_CASE
        )
        set_default_template(app, maya, calls, metered["template_id"])
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        ssp_book(app, maya),
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[
            # PLATFORM and SEAT_MONTH carry the series template TPL-SUB-DAILY, so D-97 (3a) wants
            # their entries' basis stated (AMOUNT, as the corpus keys); IMPLEMENTATION is distinct.
            point_entry(PLATFORM, "132000.00", value_basis="AMOUNT"),
            point_entry(IMPLEMENTATION, "18000.00", "cost_plus_margin"),
            range_entry(SEAT_MONTH, "90.00", "100.00", "110.00", value_basis="AMOUNT"),
            # AVM-API-CALL carries the series template TPL-USAGE: its basis is stated as well.
            *([point_entry(API_CALL, "0.10", value_basis="AMOUNT")] if usage else []),
        ],
    )
    published_mapping(app, maya, marcus)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    bodies = {K01: k01_body, K02: k02_seat_month_body, K08: k08_body}
    booked: dict[str, BookedContract] = {}
    for external_id in contracts:
        body = bodies[external_id](customers[external_id])
        found = booked_contract(place, body, activate=True)
        events = [item for item in _seeded_events(external_id) if item.effective_date <= through]
        if events:
            appended(place, UUID(str(found.contract["id"])), 2, events)
        computed(place, UUID(str(found.combination_group["id"])))
        booked[external_id] = found
    return ReportWorld(
        place=place,
        priya=approvers["priya"],
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=entity_id,
        contracts=MappingProxyType(booked),
    )


def k01_pellworth(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    *,
    through: date = THROUGH_SEPTEMBER,
) -> ReportWorld:
    """WLD-K-01 ``SF-ORD-10001`` through ``through``: INV-US-1001 120,000.00 (2026-01-01), O2
    progress 40% (2026-01-31) and 100% (2026-02-27), INV-US-1044 15,000.00 (2026-02-27).

    [J] L6-3-Q-17 (R-RC-1, CLO-6 post-rc): the world is built with the commands of the product
    rather than through ``k01_pellworth(uow, through=date)`` of CLO-6, which also locks periods."""
    return report_world(app, keyring, clock, files, contracts=(K01,), through=through)


def k01_events(*, after: date, through: date = THROUGH_SEPTEMBER) -> tuple[EventIn, ...]:
    """The WLD-K-01 seeded events effective after ``after`` and on or before ``through`` — what a
    world built with ``k01_pellworth(through=after)`` has not appended yet."""
    return tuple(item for item in _seeded_events(K01) if after < item.effective_date <= through)


def k08_ulvane(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """WLD-K-08 ``SF-ORD-10003`` activated at its inception, 1 January 2026, and computed at the
    frozen clock with FY2026-P01 to P09 open: a usage obligation whose version date lies nine open
    periods back (browser-QA finding Q-55; item CTR-TODATE-AWAITING-1)."""
    return report_world(app, keyring, clock, files, contracts=(K08,))


def k02_marrowby(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """WLD-K-02 ``SF-ORD-10002``: INV-US-1002 120,000.00 (2026-01-01). R-RC-1 (L6-3-Q-18): without
    modification CR-MARROWBY-2026-09 (CTR-17 post-rc)."""
    return report_world(app, keyring, clock, files, contracts=(K02,))


def resigned(world: ReportWorld) -> ReportWorld:
    """The same world with FRESH sessions for Maya, Priya and Marcus (their TOTP secrets kept): a
    test that moves the frozen clock to the record-time server stamp (+ days) would otherwise hit
    the 12-hour absolute session limit (`sessions.ABSOLUTE_EXPIRED`) on its next request."""

    def again(actor: Actor) -> Actor:
        signed = sign_in(world.app, actor.member.email)
        return signed_workspace(world.app, actor.member, signed, actor.secret)

    return dataclasses.replace(
        world,
        place=dataclasses.replace(world.place, author=again(world.place.author)),
        priya=again(world.priya),
        marcus=again(world.marcus),
    )


def run_now(world: ReportWorld, job_id: UUID) -> dict[str, Any]:
    """The worker fetches the job's current task and runs it; returns API-S-Job."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=1, runtime=world.runtime)
    shown = get(world.app, f"{JOBS}/{job_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def report_run(
    world: ReportWorld,
    code: str,
    parameters: Mapping[str, Any],
    *,
    output_format: str = "JSON",
    actor: Actor | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``POST /report-runs``, the job run as the worker does, then API-S-ReportRun and, for a JSON
    run, its data rows."""
    who = world.maya if actor is None else actor
    started = post(
        world.app,
        REPORT_RUNS,
        who,
        {"report_code": code, "parameters": dict(parameters), "output_format": output_format},
    )
    assert started.status_code == 202, started.text
    run_id = started.headers[REPORT_RUN_ID_HEADER]
    finished = run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", who)
    assert shown.status_code == 200, shown.text
    rows: list[dict[str, Any]] = []
    if output_format == "JSON":
        listed = get(world.app, f"{REPORT_RUNS}/{run_id}/data", who, {"limit": "200"})
        assert listed.status_code == 200, listed.text
        rows = list(listed.json()["items"])
    return dict(shown.json()), rows


def journal_run(
    world: ReportWorld, *, period_key: str = SEPTEMBER_2026, entity_code: str = AVM_US
) -> dict[str, Any]:
    """``POST /journal-runs`` as Maya with the POL-005 and POL-006 defaults, calculated by the
    worker; returns API-S-JournalRun."""
    started = post(
        world.app, JOURNAL_RUNS, world.maya, {"entity_code": entity_code, "period_key": period_key}
    )
    assert started.status_code == 202, started.text
    finished = run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(world.app, f"{JOURNAL_RUNS}/{started.headers[RUN_ID_HEADER]}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def recalculated_journal(world: ReportWorld, run: Mapping[str, Any]) -> dict[str, Any]:
    """Cancel a draft run (``reason``), then calculate the period again from the first seal."""
    cancelled = post(
        world.app,
        f"{JOURNAL_RUNS}/{run['id']}/cancel",
        world.maya,
        {"reason": "Recalculate after the revenue journal."},
    )
    assert cancelled.status_code == 200, cancelled.text
    return journal_run(world, period_key=str(run["period"]["period_key"]))


def revenue_without_contributors(world: ReportWorld, amount: str) -> None:
    """A journal to 4010 that no schedule line explains: Dr contract liability / Cr revenue of K-01
    in Sep 2026 with no obligation. [J] L6-3-Q-25: manual adjustments (T-SL-01
    ``manual_adjustment_id``) have no command in the rc, so the probe is an ``ENGINE_COMPUTE``
    posting of the group's computation, as ``post_lines`` writes for CLO-8."""
    rows = world.place.rows
    (found,) = rows(
        select(contract.c.id, contract.c.combination_group_id).where(contract.c.external_id == K01)
    )
    (computation,) = rows(
        select(contract_computation.c.id).where(
            contract_computation.c.combination_group_id == found["combination_group_id"]
        )
    )
    (month,) = rows(
        select(period.c.id, period.c.end_date)
        .select_from(period.join(legal_entity, legal_entity.c.calendar_id == period.c.calendar_id))
        .where(legal_entity.c.code == AVM_US, period.c.period_key == SEPTEMBER_2026)
    )
    accounts = {
        str(row["code"]): row["id"]
        for row in rows(
            select(gl_account.c.code, gl_account.c.id).where(
                gl_account.c.code.in_(("2100", "4010"))
            )
        )
    }
    lines = [
        {
            "period_end_date": month["end_date"],
            "entity_id": world.entity_id,
            "period_id": month["id"],
            "effective_date": month["end_date"],
            "entry_no": 1,
            "entry_kind": "REVENUE_RECOGNITION",
            "account_role": role,
            "clearing_purpose": None,
            "gl_account_id": accounts[account],
            "dimensions": {},
            "dimension_set_sha256": subledger.dimension_set_sha256({}),
            "txn_currency": "USD",
            "amount_txn": Decimal(signed),
            "functional_currency": "USD",
            "amount_functional": Decimal(signed),
            "contract_id": found["id"],
            "obligation_id": None,
            "legacy_key": K01,
        }
        for role, account, signed in (
            ("CONTRACT_LIABILITY", "2100", amount),
            ("REVENUE", "4010", f"-{amount}"),
        )
    ]
    with world.place.uow() as uow:
        subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"rps:revenue-without-contributors:{amount}",
            description="Revenue journal without schedule contributors",
            lines=lines,
            combination_group_id=found["combination_group_id"],
            contract_computation_id=computation["id"],
        )
        uow.commit()


# --- PRD J-02 and J-03 worlds of the SSP reports (BUILD_SPEC RPS-9) -------------------------------

US_LIST: Final = "US-LIST"
SF_ORD_20417_KEY: Final = "SF-ORD-20417"
PLATFORM_100_KEY: Final = "AVM-PLAT-100"
H1_LABEL: Final = "2026-H1"
H2_LABEL: Final = "2026-H2"
H1_METHODOLOGY: Final = "List-price study"
H2_METHODOLOGY: Final = "Observable standalone sales, Jan-Aug 2026"
H2_SUBMIT_COMMENT: Final = "Supported by the standalone sales study."
H2_PRIYA_COMMENT: Final = "Supported by H1 standalone sales."


def _usd_entry(product_code: str, method: str, **band: str) -> dict[str, Any]:
    return {
        "product_code": product_code,
        "currency": "USD",
        "method": method,
        "distinctness": "distinct",
        "ranges": [dict(band)],
    }


# PRD §2.6 "Products, revenue policy templates and SSP entries": the US-LIST 2026-H1 entries.
US_LIST_H1_ENTRIES: Final = (
    _usd_entry("AVM-PLAT-ENT", "observable", point_value="132000.00"),
    _usd_entry(
        "AVM-SEAT-MO", "observable", low_value="90.00", mid_value="100.00", high_value="110.00"
    ),
    _usd_entry(
        PLATFORM_100_KEY,
        "observable",
        low_value="85000.00",
        mid_value="100000.00",
        high_value="115000.00",
    ),
    _usd_entry("AVM-IMPL-STD", "cost_plus_margin", point_value="18000.00"),
    _usd_entry(
        "AVM-IMPL-PLUS",
        "cost_plus_margin",
        low_value="18000.00",
        mid_value="20000.00",
        high_value="22000.00",
    ),
    _usd_entry("AVM-API-CALL", "observable", point_value="0.10"),
    {
        **_usd_entry("AVM-ENG-BUILD", "cost_plus_margin", point_value="1"),
        "value_basis": "PERCENT_OF_LIST",
    },
)
# PRD J-02.4: AVM-PLAT-100 at mid 112,000.00 with the range ±15%.
PLATFORM_100_H2: Final = _usd_entry(
    PLATFORM_100_KEY,
    "observable",
    low_value="95200.00",
    mid_value="112000.00",
    high_value="128800.00",
)


@dataclass(frozen=True, slots=True)
class SspPublicationWorld:
    """US-LIST with 2026-H1 and 2026-H2 published through the SSP commands (PRD J-02)."""

    report: ReportWorld
    book_id: str
    h1: Mapping[str, Any]  # API-S-SspBookVersion after the supersession
    h2: Mapping[str, Any]
    h2_request_id: str

    @property
    def app(self) -> FastAPI:
        return self.report.app


def _study_attached(app: FastAPI, author: Actor, version_id: str) -> None:
    """Upload a study (the WLD-F-19 stand-in) and attach it to the version (REQ-SSP-008)."""
    from support import upload_fixtures
    from support.http import call
    from support.principals import cookie_headers

    uploaded = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": "SSP_STUDY"},
        files={"file": ("ssp-study-2026.pdf", upload_fixtures.PDF, "application/pdf")},
        headers=cookie_headers(author.token, author.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        app,
        "/api/v1/attachments",
        author,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "ssp_book_version",
            "subject_id": version_id,
        },
    )
    assert attached.status_code == 201, attached.text


def _ssp_version_submitted(app: FastAPI, author: Actor, version_id: str, comment: str) -> str:
    """Attach the study and submit the version; the approval request id."""
    _study_attached(app, author, version_id)
    current = get(app, f"/api/v1/ssp-book-versions/{version_id}", author)
    sent = post(
        app,
        f"/api/v1/ssp-book-versions/{version_id}/submit",
        author,
        {"comment": comment},
        if_match=current.headers["ETag"],
    )
    assert sent.status_code == 200, sent.text
    return str(sent.json()["approval_request_id"])


def _decided(app: FastAPI, request_id: str, approver: Actor, comment: str) -> dict[str, Any]:
    """``POST /approvals/{id}/approve`` with the subject hash the request shows and ``comment``."""
    shown = get(app, f"/api/v1/approvals/{request_id}", approver)
    assert shown.status_code == 200, shown.text
    body = {
        "subject_content_sha256": shown.json()["subject"]["content_sha256"],
        "comment": comment,
    }
    decided = post(app, f"/api/v1/approvals/{request_id}/approve", approver, body)
    assert decided.status_code == 200, decided.text
    return dict(decided.json())


def ssp_h2_publication(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> SspPublicationWorld:
    """PRD J-02 through the SSP commands. Maya (Revenue Accountant, SSP Analyst) prepares the
    tenant-wide book US-LIST (USD): ``2026-H1`` with the PRD §2.6 entries, effective 2026-01-01,
    approved by Priya (SSP Approver; MFA); then ``2026-H2``, effective 2026-10-01, a copy of every
    H1 entry with AVM-PLAT-100 at 95,200.00 / 112,000.00 / 128,800.00 (J-02.3, J-02.4), the
    methodology label of J-02.5 and its study, approved in two steps — Priya, then Marcus (SSP
    Approver; MFA) — because the mid value moves by 12.0%; the approval ends H1 on 30 Sep 2026
    (BR-SSP-02). The clock advances one minute between the steps; AVM-US exists (no contract)."""
    from datetime import timedelta

    from support.principals import member as new_member
    from support.reference import calendar, entity, new_product

    step = timedelta(minutes=1)
    maya_member = new_member(keyring, clock, name="maya")
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name in ("priya", "marcus"):
        someone = colleague(maya_member.tenant_id, name)
        assign(someone, "ssp_approver")
        approvers[name] = enrolled(app, clock, someone)
    calendar_id = calendar(app, maya, years=(2026,))
    created_entity = entity(app, maya, code=AVM_US, calendar_id=calendar_id)
    for item in US_LIST_H1_ENTRIES:
        code = str(item["product_code"])
        new_product(app, maya, code=code, name=code)
    book_id = ssp_book(app, maya, code=US_LIST)
    versions = f"/api/v1/ssp-books/{book_id}/versions"

    first = post(
        app,
        versions,
        maya,
        {
            "legacy_version_label": H1_LABEL,
            "effective_from_date": "2026-01-01",
            "methodology_label": H1_METHODOLOGY,
        },
    )
    assert first.status_code == 201, first.text
    h1_id = str(first.json()["id"])
    stored = post(
        app,
        f"/api/v1/ssp-book-versions/{h1_id}/entries",
        maya,
        {"entries": [dict(item) for item in US_LIST_H1_ENTRIES]},
    )
    assert stored.status_code == 200, stored.text
    h1_request = _ssp_version_submitted(app, maya, h1_id, "Supported by the study.")
    clock.advance(step)
    assert _decided(app, h1_request, approvers["priya"], "OK")["status"] == "APPROVED"

    clock.advance(step)
    second = post(
        app,
        versions,
        maya,
        {
            "copy_from_version_id": h1_id,
            "legacy_version_label": H2_LABEL,
            "effective_from_date": "2026-10-01",
            "methodology_label": H2_METHODOLOGY,
        },
    )
    assert second.status_code == 201, second.text
    h2_id = str(second.json()["id"])
    edited = post(
        app,
        f"/api/v1/ssp-book-versions/{h2_id}/entries",
        maya,
        {"entries": [dict(PLATFORM_100_H2)]},
    )
    assert edited.status_code == 200, edited.text
    clock.advance(step)
    h2_request = _ssp_version_submitted(app, maya, h2_id, H2_SUBMIT_COMMENT)
    clock.advance(step)
    step_one = _decided(app, h2_request, approvers["priya"], H2_PRIYA_COMMENT)
    assert (step_one["status"], step_one["current_step_no"]) == ("PENDING", 2), step_one
    clock.advance(step)
    assert _decided(app, h2_request, approvers["marcus"], "OK")["status"] == "APPROVED"

    def shown(version_id: str) -> dict[str, Any]:
        found = get(app, f"/api/v1/ssp-book-versions/{version_id}", maya)
        assert found.status_code == 200, found.text
        return dict(found.json())

    stamp_test_release()
    report = ReportWorld(
        place=workspace(app, clock, keyring, files, maya),
        priya=approvers["priya"],
        marcus=approvers["marcus"],
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=UUID(str(created_entity["id"])),
        contracts=MappingProxyType({}),
    )
    return SspPublicationWorld(
        report=report,
        book_id=book_id,
        h1=MappingProxyType(shown(h1_id)),
        h2=MappingProxyType(shown(h2_id)),
        h2_request_id=h2_request,
    )


@dataclass(frozen=True, slots=True)
class SfOrderWorld:
    """``SF-ORD-20417`` booked, activated and computed in the J-03 world (PRD WLD-F-20)."""

    report: ReportWorld
    book_id: str
    h1_version_id: str  # US-LIST 2026-H1
    contract_id: UUID
    group_id: UUID

    @property
    def app(self) -> FastAPI:
        return self.report.app


def k_sf_ord_20417(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> SfOrderWorld:
    """PRD WLD-F-20 ``SF-ORD-20417`` activated (WLD-X-23): ``support.factories.j03_world`` — AVM-US
    and AVM-UK, customer C-12, AVM-PLAT-100 (TPL-SUB-DAILY; 85,000.00 / 100,000.00 / 115,000.00
    USD) and AVM-IMPL-PLUS (TPL-SVC-HOURS; 18,000.00 / 20,000.00 / 22,000.00 USD) under US-LIST
    2026-H1 — with the order booked (O1 96,000.00 from 01 Sep 2026 to 31 Aug 2027; O2 24,000.00
    performed by AVM-UK), activated as the SYSTEM principal (BS3-D-19) and computed by that
    activation."""
    from support.factories import activated_contract, j03_world, sf_ord_20417_body

    j03 = j03_world(app, keyring, clock, files)
    booked = booked_contract(j03.place, sf_ord_20417_body(j03.customer_id), activate=False)
    booked = activated_contract(j03.place, booked)
    report = ReportWorld(
        place=j03.place,
        priya=j03.priya,
        marcus=j03.marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=j03.entity_id,
        contracts=MappingProxyType({SF_ORD_20417_KEY: booked}),
    )
    return SfOrderWorld(
        report=report,
        book_id=j03.book_id,
        h1_version_id=j03.version_id,
        contract_id=UUID(str(booked.contract["id"])),
        group_id=UUID(str(booked.combination_group["id"])),
    )


# --- PRD WLD-K-03 ``PRJ-CB-2026-01`` (BUILD_SPEC RPS-10, RPS-11) ----------------------------------

K03_EXTERNAL_ID: Final = "PRJ-CB-2026-01"
ENG_BUILD: Final = "AVM-ENG-BUILD"
BONUS_CB_01: Final = "BONUS-CB-01"
# PRD §2.6 TPL-ENG-C2C: one distinct obligation satisfied over time, measured cost to cost.
TPL_ENG_C2C: Final = MappingProxyType(
    {
        "distinctness": "distinct",
        "satisfaction_pattern": "OVER_TIME",
        "over_time_criterion": "OT_B",
        "recognition_method": "COST_TO_COST",
    }
)
# PRD §2.6 accounts of the roles a cost-to-cost computation reaches, the loss provision included.
K03_CHART: Final = (
    ("1100", "Accounts receivable", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1200", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("2300", "Provision for anticipated losses", "LIABILITY", "C", "LOSS_PROVISION"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C", "REVENUE"),
    ("5300", "Anticipated loss expense", "EXPENSE", "D", "LOSS_EXPENSE"),
)
# PRD WLD-K-03: costs incurred February to August 2026, 420,000.00 in total.
K03_COSTS: Final = (
    (date(2026, 2, 28), "30000.00"),
    (date(2026, 3, 31), "50000.00"),
    (date(2026, 4, 30), "60000.00"),
    (date(2026, 5, 31), "70000.00"),
    (date(2026, 6, 30), "70000.00"),
    (date(2026, 7, 31), "70000.00"),
    (date(2026, 8, 31), "70000.00"),
)
# PRD WLD-K-03: INV-US-2001 to INV-US-2006, 550,000.00 in total through 2026-08-31. [J] The PRD
# states the total, not the split: 50,000.00, then five invoices of 100,000.00 at month ends.
K03_INVOICES: Final = (
    ("INV-US-2001", date(2026, 2, 28), "50000.00"),
    ("INV-US-2002", date(2026, 3, 31), "100000.00"),
    ("INV-US-2003", date(2026, 4, 30), "100000.00"),
    ("INV-US-2004", date(2026, 5, 31), "100000.00"),
    ("INV-US-2005", date(2026, 6, 30), "100000.00"),
    ("INV-US-2006", date(2026, 7, 31), "100000.00"),
)
K03_EAC_V1_RATIONALE: Final = "Estimate at completion from the project plan."
K03_BONUS_V1_RATIONALE: Final = "Completion within the window is not yet highly probable."


@dataclass(frozen=True, slots=True)
class K03World:
    """``PRJ-CB-2026-01`` active with its August 2026 position (PRD WLD-K-03, WLD-X-09)."""

    report: ReportWorld
    contract_id: UUID
    group_id: UUID
    eac_id: str  # estimate element EAC (cost build-up)
    eac_v1_id: str
    bonus_id: str  # estimate element BONUS-CB-01 (most likely amount)
    bonus_v1_id: str

    @property
    def app(self) -> FastAPI:
        return self.report.app


def estimate_version_ready(
    app: FastAPI,
    author: Actor,
    version_id: str,
    *,
    constraint_of: str | None = None,
    reviewer: Actor | None = None,
) -> None:
    """What the submission of an estimate version asks beyond its values (04 §16.14 rev 1.241;
    items EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement record): its evidence — one
    file ``author`` uploads and attaches to the version — and, for a version of a
    variable-consideration element (``constraint_of``: the element's code), a ``CONSTRAINT``
    record of that element which ``author`` sends for review and ``reviewer`` reviews, named on
    the version. The record's subject is the version itself — what SCREENS §8.4 sends — so it
    places no hold and its review appends nothing to the contract (04 §16.10 rev 1.233, point
    3); the version's request, which pins the contract's head, is made after it."""
    from support.reference import patch

    attached = post(
        app,
        "/api/v1/attachments",
        author,
        {
            "file_object_id": evidence_file(app, author),
            "subject_type": "estimate_version",
            "subject_id": version_id,
        },
    )
    assert attached.status_code == 201, attached.text
    if constraint_of is None:
        return
    assert reviewer is not None, "a CONSTRAINT record is reviewed by a second person"
    record = judgement_submitted(
        app,
        author,
        {
            "topic": "CONSTRAINT",
            "subject_type": "estimate_version",
            "subject_id": version_id,
            "conclusion": f"The constraint of {constraint_of} as this version states it.",
            "rationale": "The factors of ASC 606-10-32-12 were considered for this estimate.",
            "codification_refs": ["606-10-32-11", "606-10-32-12"],
            "questionnaire": {"estimate_key": constraint_of, "remote": False},
        },
    )
    reviewed = approve(app, str(record["approval_request_id"]), reviewer)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    named = patch(
        app,
        f"/api/v1/estimate-versions/{version_id}",
        author,
        {"judgement_record_id": record["id"]},
        if_match=None,
    )
    assert named.status_code == 200, named.text


def estimate_version_approved(
    app: FastAPI,
    author: Actor,
    approver: Actor,
    estimate_id: str,
    body: Mapping[str, Any],
    *,
    comment: str = "Review",
    controller: Actor | None = None,
    constraint_of: str | None = None,
) -> dict[str, Any]:
    """``POST /estimates/{id}/versions``, its submission by ``author`` and the approval by
    ``approver``; API-S-EstimateVersion of the APPROVED version. ``controller`` names the
    Controller who decides the second step of a version whose P&L impact is USD 50,000.00 or more
    (PRD §2.5 ``ESTIMATE_VERSION``; 04 T-PLT-17 ``flags`` ``PL_IMPACT_GE_50K``, rev 1.104): such a
    request is PENDING after ``approver`` and APPROVED after the Controller, at the same instant.
    Before the submission the version is given what it asks (``estimate_version_ready``): its
    evidence and, with ``constraint_of`` — the code of a variable-consideration element — a
    ``CONSTRAINT`` record that ``approver`` reviews."""
    from support.reference import approve

    created = post(app, f"/api/v1/estimates/{estimate_id}/versions", author, dict(body))
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    estimate_version_ready(app, author, version_id, constraint_of=constraint_of, reviewer=approver)
    sent = post(app, f"/api/v1/estimate-versions/{version_id}/submit", author, {"comment": comment})
    assert sent.status_code == 200, sent.text
    decided = approve(app, str(sent.json()["approval_request_id"]), approver)
    if controller is not None:
        assert (decided.status_code, decided.json()["status"]) == (200, "PENDING"), decided.text
        decided = approve(app, str(sent.json()["approval_request_id"]), controller)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    shown = get(app, f"/api/v1/estimate-versions/{version_id}", author)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def k03_revenue(place: Workspace, group_id: UUID) -> Decimal:
    """Cumulative revenue of the group's latest ASC606 contract version."""
    from erev_api.db.tables import contract_version

    (latest,) = place.rows(
        select(contract_version.c.revenue_cum)
        .where(
            contract_version.c.combination_group_id == group_id,
            contract_version.c.book_code == "ASC606",
        )
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    return Decimal(latest["revenue_cum"])


def k03_castellan(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> K03World:
    """PRD WLD-K-03 through the product's commands. Maya (Revenue Accountant, SSP Analyst)
    prepares; Priya (Revenue Reviewer, SSP Approver; MFA) approves US-LIST 2026-H1 and the estimate
    versions; Marcus (Controller, SSP Approver, Tenant Admin; MFA) enables USD and approves the
    template and the mapping. AVM-US (USD) has FY2026-P01 to P09 open; customer C-03; AVM-ENG-BUILD
    (TPL-ENG-C2C; cost plus margin, 100% of list). ``PRJ-CB-2026-01`` books O1 for 1,000,000.00 USD
    from 2026-02-01 with EAC version 1 of 700,000.00 and the completion bonus ``BONUS-CB-01`` of
    200,000.00 constrained to 0.00 (both effective 2026-02-01, approved by Priya), is activated as
    the SYSTEM principal (BS3-D-19), takes the February to August costs (420,000.00) and the
    invoices INV-US-2001 to INV-US-2006 (550,000.00) and is computed: cumulative revenue
    600,000.00 at 31 Aug 2026 (WLD-X-09). The booking carries ``scope_605_35``: the contract is in
    the loss-test scope of POL-151."""
    from erev_api.events.payloads import CostIncurredV1
    from support.factories import activated_contract

    maya_member = member(keyring, clock, name="maya")
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    priya, marcus = approvers["priya"], approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    _, entity_id = world_calendar(app, maya)
    buyer = customer_id(app, maya, code="C-03", name="Castellan Build Group Inc. (Demo)")
    build = product_with_template(
        app, maya, code=ENG_BUILD, name="Engineered facility build", revenue_category="SERVICES"
    )
    template = published_template(
        app,
        maya,
        marcus,
        code="TPL-ENG-C2C",
        outputs=TPL_ENG_C2C,
        case_line={
            "obligation_key": "POB-01",
            "product_code": ENG_BUILD,
            "quantity": "1",
            "total_price": "1000000.00",
        },
    )
    set_default_template(app, maya, build, template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya),
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[
            {
                "product_code": ENG_BUILD,
                "currency": "USD",
                "method": "cost_plus_margin",
                "distinctness": "distinct",
                "value_basis": "PERCENT_OF_LIST",
                "unit_list_price": "1000000.00",
                "ranges": [{"point_value": "1"}],
            }
        ],
    )
    published_mapping(app, maya, marcus, chart=K03_CHART)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": K03_EXTERNAL_ID,
            "customer_id": str(buyer),
            "contracting_entity_code": AVM_US,
            "transaction_currency": "USD",
            "inception_date": "2026-02-01",
            # a construction-type contract in the loss-test scope (POL-151 SCOPED_605_35_ONLY)
            "scope_605_35": True,
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": ENG_BUILD,
                    "quantity": "1",
                    "total_price": {"amount": "1000000.00", "currency": "USD"},
                }
            ],
        },
        activate=False,
    )
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    estimates = f"/api/v1/contracts/{contract_id}/estimates"
    eac = post(
        app,
        estimates,
        maya,
        {
            "estimate_kind": "EAC",
            "element_code": "EAC",
            "obligation_key": "O1",
            "method": "COST_BUILDUP",
        },
    )
    assert eac.status_code == 201, eac.text
    eac_v1 = estimate_version_approved(
        app,
        maya,
        priya,
        str(eac.json()["id"]),
        {
            "effective_date": "2026-02-01",
            "expected_total_amount": "700000.00",
            "rationale": K03_EAC_V1_RATIONALE,
        },
    )
    bonus = post(
        app,
        estimates,
        maya,
        {
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "element_code": BONUS_CB_01,
            "vc_element_type": "BONUS",
            "method": "MOST_LIKELY_AMOUNT",
        },
    )
    assert bonus.status_code == 201, bonus.text
    bonus_v1 = estimate_version_approved(
        app,
        maya,
        priya,
        str(bonus.json()["id"]),
        {
            "effective_date": "2026-02-01",
            "scenarios": [
                {"outcome": "Completion bonus earned", "amount": "200000.00"},
                {"outcome": "Not earned", "amount": "0.00"},
            ],
            "unconstrained_amount": "200000.00",
            "most_conservative_amount": "0.00",
            "constrained_amount": "0.00",
            "rationale": K03_BONUS_V1_RATIONALE,
        },
        constraint_of=BONUS_CB_01,
    )
    booked = activated_contract(place, booked)
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    events = [
        EventIn(
            event_type=ContractEventType.COST_INCURRED,
            effective_date=day,
            payload=CostIncurredV1(
                purpose="PROGRESS_INPUT",
                obligation_key="O1",
                amount=MoneyIn(amount=amount, currency="USD"),
            ),
        )
        for day, amount in K03_COSTS
    ]
    events += [_billing(invoice, amount, day, "O1") for invoice, day, amount in K03_INVOICES]
    appended(place, contract_id, int(head), events)
    computed(place, group_id)
    assert k03_revenue(place, group_id) == Decimal("600000.00")  # WLD-X-09
    report = ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=entity_id,
        contracts=MappingProxyType({K03_EXTERNAL_ID: booked}),
    )
    return K03World(
        report=report,
        contract_id=contract_id,
        group_id=group_id,
        eac_id=str(eac.json()["id"]),
        eac_v1_id=str(eac_v1["id"]),
        bonus_id=str(bonus.json()["id"]),
        bonus_v1_id=str(bonus_v1["id"]),
    )


def ssp_version_submitted(app: FastAPI, author: Actor, version_id: str, comment: str) -> str:
    """An SSP book version with its study attached, submitted by ``author`` (the J-02 step
    ``ssp_h2_publication`` takes); the approval request id."""
    return _ssp_version_submitted(app, author, version_id, comment)


# --- PRD J-06 and J-10 on ``PRJ-CB-2026-01`` (BUILD_SPEC RPS-11) ----------------------------------

K03_CHANGE_ORDER: Final = "CR-CASTELLAN-2026-09"
K03_EAC_V2_RATIONALE: Final = "Change order CO-07 adds 120,000.00 of cost"
K03_EAC_V3_RATIONALE: Final = "Steel price escalation (supplier notice 24 Sep 2026)"
K03_CONSTRAINT_CONCLUSION: Final = (
    "Completion within the extended 30-month window is highly likely; no significant reversal "
    "expected."
)
# The steps of J-06 and J-10 are 20 seconds apart, so they stay inside the five-minute window of
# the approvers' MFA verification at enrolment (BR-PLT-06) and no step needs a fresh TOTP.
K03_STEP_SECONDS: Final = 20


@dataclass(frozen=True, slots=True)
class K03ChangeOrder:
    """The objects of PRD J-06 on ``PRJ-CB-2026-01``."""

    eac_v2_id: str
    bonus_v2_id: str
    judgement: Mapping[str, Any]  # API-S of the CONSTRAINT record, reviewed by Priya
    modification_id: str
    modification_request_id: str


def judgement_submitted(app: FastAPI, author: Actor, body: Mapping[str, Any]) -> dict[str, Any]:
    """``POST /judgements`` and its submission by ``author``; the SUBMITTED record."""
    created = post(app, "/api/v1/judgements", author, dict(body))
    assert created.status_code == 201, created.text
    sent = post(
        app, f"/api/v1/judgements/{created.json()['id']}/submit", author, {"comment": "Review"}
    )
    assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
    return dict(sent.json())


def k03_change_order(world: K03World, clock: FrozenClock) -> K03ChangeOrder:
    """PRD J-06 through the product's commands, in the order its approvals take effect: Priya
    approves EAC version 2 (820,000.00, effective 10 Sep 2026), reviews the ``CONSTRAINT``
    judgement and approves bonus version 2 (200,000.00, most likely amount, no longer
    constrained); the change order ``CR-CASTELLAN-2026-09`` (+150,000.00 on O1, effective 10 Sep
    2026) classifies as a cumulative catch-up and is approved by Priya (step 1) and Marcus (step
    2). The result is WLD-X-10: transaction price 1,350,000.00 and cumulative revenue 691,463.41.

    The product approves estimate versions and a modification as separate requests, the
    versions first (04 §16.14 rev 1.210; PRD J-06 rev 1.158), so each estimate version applies
    with its own computation before the modification does. This helper keeps its versions
    outside the modification and its ``CONSTRAINT`` record on the contract; the journey with the
    versions created inside the draft modification is
    ``tests/domain/contracts/test_modifications.py::test_j_06_…``."""
    from datetime import timedelta

    from support.reference import approve, patch

    step = timedelta(seconds=K03_STEP_SECONDS)
    app, report = world.app, world.report
    maya, priya, marcus = report.maya, report.priya, report.marcus
    clock.advance(step)
    # EAC 700,000.00 → 820,000.00 lowers progress from 60.0% to 51.2%: a catch-up of 87,804.88,
    # so the version takes the Controller's second step (PRD §2.5; R-41 (7)).
    eac_v2 = estimate_version_approved(
        app,
        maya,
        priya,
        world.eac_id,
        {
            "effective_date": "2026-09-10",
            "expected_total_amount": "820000.00",
            "rationale": K03_EAC_V2_RATIONALE,
        },
        controller=marcus,
    )
    clock.advance(step)
    # B1-5: the record reviews the actual draft's figures, which must exist first.
    bonus = post(
        app,
        f"/api/v1/estimates/{world.bonus_id}/versions",
        maya,
        {
            "effective_date": "2026-09-10",
            "scenarios": [
                {"outcome": "Completion bonus earned", "amount": "200000.00"},
                {"outcome": "Not earned", "amount": "0.00"},
            ],
            "unconstrained_amount": "200000.00",
            "most_conservative_amount": "0.00",
            "constrained_amount": "200000.00",
            "rationale": "Completion within the extended window is highly likely.",
        },
    )
    assert bonus.status_code == 201, bonus.text
    bonus_v2_id = str(bonus.json()["id"])
    judgement = judgement_submitted(
        app,
        maya,
        {
            "topic": "CONSTRAINT",
            "subject_type": "contract",
            "subject_id": str(world.contract_id),
            "conclusion": K03_CONSTRAINT_CONCLUSION,
            "rationale": "Schedule review of change order CO-07.",
            "codification_refs": ["606-10-32-11", "606-10-32-12"],
            "questionnaire": {"estimate_key": BONUS_CB_01, "remote": True},
        },
    )
    # Item EST-PREVIEW-HEAD-PIN-1 (04 §16.10 rev 1.233): the record is on the contract, so its
    # submission holds the contract and its review releases the hold — two events that move the
    # head. It is reviewed BEFORE the version is submitted: a version's request pins the head,
    # and a review that came after the submission (this helper's order before the item) left
    # the request stale at its first decision.
    clock.advance(step)
    reviewed = approve(app, str(judgement["approval_request_id"]), priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    linked = patch(
        app,
        f"/api/v1/estimate-versions/{bonus_v2_id}",
        maya,
        {"judgement_record_id": judgement["id"]},
        if_match=None,
    )
    assert linked.status_code == 200, linked.text
    estimate_version_ready(app, maya, bonus_v2_id)  # its evidence; the record is named above
    sent = post(app, f"/api/v1/estimate-versions/{bonus_v2_id}/submit", maya, {"comment": "Review"})
    assert sent.status_code == 200, sent.text
    clock.advance(step)
    # The bonus of 200,000.00 at 51.2% progress is a catch-up of 102,439.02: Priya decides step 1
    # and Marcus, the Controller, step 2 (PRD §2.5; R-41 (7)).
    first = approve(app, str(sent.json()["approval_request_id"]), priya)
    assert (first.status_code, first.json()["status"]) == (200, "PENDING"), first.text
    decided = approve(app, str(sent.json()["approval_request_id"]), marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text

    clock.advance(step)
    created = post(
        app,
        f"/api/v1/contracts/{world.contract_id}/modifications",
        maya,
        {
            "effective_date": "2026-09-10",
            "kind": "PRICE_CHANGE",
            "reference": K03_CHANGE_ORDER,
            "lines": [
                {
                    "obligation_key": "O1",
                    "action": "CHANGE",
                    "consideration_delta": {"amount": "150000.00", "currency": "USD"},
                }
            ],
            "rationale": "Floor plan change (change order CO-07)",
        },
    )
    assert created.status_code == 201, created.text
    modification_id = str(created.json()["id"])
    classified = post(app, f"/api/v1/modifications/{modification_id}/classify", maya, {})
    assert classified.status_code == 200, classified.text
    assert classified.json()["treatment_summary"] == "CUMULATIVE_CATCH_UP", classified.text
    confirm_answers(app, modification_id, maya)
    queued = post(app, f"/api/v1/modifications/{modification_id}/preview", maya, {})
    assert queued.status_code == 202, queued.text
    assert run_now(report, UUID(str(queued.json()["id"])))["state"] == "SUCCEEDED"
    submitted = post(
        app,
        f"/api/v1/modifications/{modification_id}/submit",
        maya,
        {"comment": "Approve change order CO-07."},
    )
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    clock.advance(step)
    first = approve(app, request_id, priya)  # J-06.5
    assert (first.status_code, first.json()["current_step_no"]) == (200, 2), first.text
    clock.advance(step)
    second = approve(app, request_id, marcus)  # J-06.6
    assert (second.status_code, second.json()["status"]) == (200, "APPROVED"), second.text
    assert k03_revenue(report.place, world.group_id) == Decimal("691463.41")  # WLD-X-10
    shown = get(app, f"/api/v1/judgements/{judgement['id']}", maya)
    assert (shown.status_code, shown.json()["status"]) == (200, "REVIEWED"), shown.text
    return K03ChangeOrder(
        eac_v2_id=str(eac_v2["id"]),
        bonus_v2_id=bonus_v2_id,
        judgement=MappingProxyType(dict(shown.json())),
        modification_id=modification_id,
        modification_request_id=request_id,
    )


def k03_september(world: K03World, clock: FrozenClock) -> str:
    """PRD J-10 through the product's commands: costs of 82,000.00 effective 25 Sep 2026 bring
    cumulative revenue to 826,463.41 (WLD-X-11); EAC version 3 of 850,000.00, effective 30 Sep
    2026 and approved by Priya, takes it to 797,294.12 (WLD-X-12). Returns the id of version 3."""
    from datetime import timedelta

    from erev_api.events.payloads import CostIncurredV1

    step = timedelta(seconds=K03_STEP_SECONDS)
    report = world.report
    place = report.place
    clock.advance(step)
    head = place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == world.contract_id)
    )
    appended(
        place,
        world.contract_id,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.COST_INCURRED,
                effective_date=date(2026, 9, 25),
                payload=CostIncurredV1(
                    purpose="PROGRESS_INPUT",
                    obligation_key="O1",
                    amount=MoneyIn(amount="82000.00", currency="USD"),
                ),
            )
        ],
    )
    computed(place, world.group_id)
    assert k03_revenue(place, world.group_id) == Decimal("826463.41")  # WLD-X-11
    clock.advance(step)
    eac_v3 = estimate_version_approved(
        world.app,
        report.maya,
        report.priya,
        world.eac_id,
        {
            "effective_date": "2026-09-30",
            "expected_total_amount": "850000.00",
            "rationale": K03_EAC_V3_RATIONALE,
        },
    )
    assert k03_revenue(place, world.group_id) == Decimal("797294.12")  # WLD-X-12
    return str(eac_v3["id"])


# --- PRD §2.10 BR-06: an embedded lease routed out of Topic 606 (BUILD_SPEC RPS-11) ---------------

BR06_EXTERNAL_ID: Final = "BR-06"
ROBOT_LEASE: Final = "ROBOT-LEASE-36M"
DAAS_SERVICE: Final = "DAAS-SVC-36M"
# The templates of answer key ALC-BR-06: a point-in-time lease component and a monthly series.
TPL_LEASE_COMPONENT: Final = MappingProxyType(
    {
        "distinctness": "distinct",
        "satisfaction_pattern": "POINT_IN_TIME",
        "over_time_criterion": "NOT_APPLICABLE",
        "recognition_method": "UNITS_DELIVERED",
    }
)
TPL_DAAS_SERVICE: Final = MappingProxyType(
    {
        "distinctness": "series",
        "series_increment_unit": "month",
        "satisfaction_pattern": "OVER_TIME",
        "over_time_criterion": "OT_A",
        "recognition_method": "TIME_ELAPSED",
        "ratable_convention": "MONTHLY_EVEN",
    }
)


@dataclass(frozen=True, slots=True)
class Br06World:
    """``BR-06`` active: a robot lease component routed to ASC 842 beside a service."""

    report: ReportWorld
    contract_id: UUID
    lease_obligation_id: UUID

    @property
    def app(self) -> FastAPI:
        return self.report.app


def br06_lease(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> Br06World:
    """The facts of answer key ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT through the product's
    commands (PRD §2.10 BR-06): Maya, Priya and Marcus as in ``k03_castellan``; AVM-US (USD) with
    the calendar years 2026 to 2028; ROBOT-LEASE-36M (SSP 90,000.00) and DAAS-SVC-36M (SSP
    30,000.00, a monthly series). ``BR-06`` books L1-LEASE for 72,000.00 with scope flag
    ``LEASE_842`` and the out-of-scope amount 81,000.00, and L2-SERVICE for 36,000.00, both from
    01 Jan 2026 to 31 Dec 2028, and is activated: the lease allocation of 81,000.00 is out of
    scope and the transaction price is 27,000.00. [J] The key's lease template recognises
    ``MANUAL``; this world uses units delivered, which no test reads (the line earns nothing)."""
    from erev_api.db.tables import contract_version
    from support.factories import activated_contract, open_periods
    from support.reference import calendar, entity

    maya_member = member(keyring, clock, name="maya")
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    priya, marcus = approvers["priya"], approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    created = entity(
        app, maya, code=AVM_US, calendar_id=calendar(app, maya, years=(2026, 2027, 2028))
    )
    open_periods(
        app, maya, entity_code=AVM_US, keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    buyer = customer_id(app, maya, code="C-BR06", name="Pellworth Logistics Inc. (Demo)")
    term = {"start_date": "2026-01-01", "end_date": "2028-12-31"}
    for code, name, category, template_code, outputs, price in (
        (
            ROBOT_LEASE,
            "Robot equipment lease component, 36 months",
            "LEASE",
            "TPL-LEASE-COMPONENT",
            TPL_LEASE_COMPONENT,
            "72000.00",
        ),
        (
            DAAS_SERVICE,
            "Fleet software and maintenance, 36 months",
            "SERVICES",
            "TPL-DAAS-SVC",
            TPL_DAAS_SERVICE,
            "36000.00",
        ),
    ):
        item = product_with_template(app, maya, code=code, name=name, revenue_category=category)
        template = published_template(
            app,
            maya,
            marcus,
            code=template_code,
            outputs=outputs,
            case_line={
                "obligation_key": "POB-01",
                "product_code": code,
                "quantity": "1",
                "total_price": price,
                **term,
            },
        )
        set_default_template(app, maya, item, template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya),
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[
            point_entry(ROBOT_LEASE, "90000.00"),
            point_entry(DAAS_SERVICE, "30000.00", value_basis="AMOUNT"),
        ],
    )
    published_mapping(app, maya, marcus)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": BR06_EXTERNAL_ID,
            "customer_id": str(buyer),
            "contracting_entity_code": AVM_US,
            "transaction_currency": "USD",
            "inception_date": "2026-01-01",
            "lines": [
                {
                    "obligation_key": "L1-LEASE",
                    "product_code": ROBOT_LEASE,
                    "quantity": "1",
                    "total_price": {"amount": "72000.00", "currency": "USD"},
                    "scope_flag": "LEASE_842",
                    "out_of_scope_amount": {"amount": "81000.00", "currency": "USD"},
                    **term,
                },
                {
                    "obligation_key": "L2-SERVICE",
                    "product_code": DAAS_SERVICE,
                    "quantity": "1",
                    "total_price": {"amount": "36000.00", "currency": "USD"},
                    **term,
                },
            ],
        },
        activate=False,
    )
    booked = activated_contract(place, booked)
    contract_id = UUID(str(booked.contract["id"]))
    (version,) = place.rows(
        select(contract_version.c.transaction_price, contract_version.c.out_of_scope_amount).where(
            contract_version.c.combination_group_id == UUID(str(booked.combination_group["id"]))
        )
    )
    # answer key ALC-BR-06: transaction price 27,000.00 net of the lease allocation 81,000.00
    assert (Decimal(version["transaction_price"]), Decimal(version["out_of_scope_amount"])) == (
        Decimal("27000.00"),
        Decimal("81000.00"),
    )
    lease_obligation_id = place.scalar(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "L1-LEASE"
        )
    )
    report = ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=UUID(str(created["id"])),
        contracts=MappingProxyType({BR06_EXTERNAL_ID: booked}),
    )
    return Br06World(
        report=report, contract_id=contract_id, lease_obligation_id=UUID(str(lease_obligation_id))
    )


# --- the worlds of the analysis reports (BUILD_SPEC RPS-12): PRD WLD-K-02 and WLD-K-09 with their
# commissions, WLD-K-04, and the facts of ONB-S11-MODRETRO-OWN, IFRS-SW01 and POLICIES CHK-010 -----

K09: Final = "SF-ORD-10417"
K02_COMMISSION: Final = "COM-2026-0002"  # PRD WLD-K-02: 12,000.00 capitalised in Jan 2026
K09_COMMISSION: Final = "COM-K09"  # PRD WLD-F-27: 6,480.00 incurred 2026-09-05
COMMISSION_PLAN: Final = "SALES-2026"
# PRD §2.6 accounts of the roles a subscription with a capitalised commission reaches.
COMMISSION_CHART: Final = (
    ("1100", "Accounts receivable", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1400", "Capitalised costs to obtain a contract", "ASSET", "D", "COST_TO_OBTAIN_ASSET"),
    (
        "2020",
        "Commissions payable (contract cost clearing)",
        "LIABILITY",
        "C",
        "CONTRACT_COST_CLEARING",
    ),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C", "REVENUE"),
    ("5100", "Amortisation of contract costs", "EXPENSE", "D", "CONTRACT_COST_AMORTIZATION"),
    ("6000", "Impairment of contract cost assets", "EXPENSE", "D", "CONTRACT_COST_IMPAIRMENT"),
)


def commission(reference: str, amount: str, day: date) -> EventIn:
    """``COST_INCURRED`` of an incremental cost of obtaining the contract under plan
    ``SALES-2026`` (PRD WLD-F-27), keyed by the commission's reference."""
    from erev_api.events.payloads import CostIncurredV1

    return EventIn(
        event_type=ContractEventType.COST_INCURRED,
        effective_date=day,
        payload=CostIncurredV1(
            purpose="COST_TO_OBTAIN",
            amount=_usd(amount),
            plan_code=COMMISSION_PLAN,
            is_incremental=True,
            has_clawback=False,
        ),
        idempotency_key=reference,
    )


def k02_marrowby_commission(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """WLD-K-02 ``SF-ORD-10002`` with its commission, through the product's commands:
    ``support.factories.seat_world`` (AVM-US, USD, calendar 2026 to 2029, FY2026-P01 to P09 open;
    AVM-SEAT-MO under TPL-SUB-DAILY) over ``COMMISSION_CHART``; O1 100 seats for 240,000.00 from
    01 Jan 2026 to 31 Dec 2027, INV-US-1002 120,000.00 and ``COM-2026-0002`` 12,000.00, both on
    01 Jan 2026; computed once. [J] ``k02_marrowby`` keeps its R-RC-1 content (no commission):
    the reports that read it pin its journal and balance populations, and its mapping carries no
    contract-cost role. The billing plan of WLD-K-02 (120,000.00 due 2027-01-01) and the
    modification CR-MARROWBY-2026-09 are not part of this world (CTR-14, CTR-17); neither moves
    the commission asset in September 2026 (WLD-X-08)."""
    from support.factories import k02_body, seat_world

    seats = seat_world(app, keyring, clock, files, chart=COMMISSION_CHART)
    booked = booked_contract(seats.place, k02_body(seats.customers["C-02"]), activate=True)
    appended(
        seats.place,
        UUID(str(booked.contract["id"])),
        2,
        [
            _billing("INV-US-1002", "120000.00", date(2026, 1, 1), "O1"),
            commission(K02_COMMISSION, "12000.00", date(2026, 1, 1)),
        ],
    )
    computed(seats.place, UUID(str(booked.combination_group["id"])))
    return ReportWorld(
        place=seats.place,
        priya=seats.priya,
        marcus=seats.marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=seats.entity_id,
        contracts=MappingProxyType({K02: booked}),
    )


def k09_orrin_vale(world: ReportWorld) -> ReportWorld:
    """WLD-K-09 ``SF-ORD-10417`` booked in a ``k02_marrowby_commission`` world, through the
    product's commands: customer C-09, O1 30 seats for 108,000.00 from 01 Sep 2026 to 31 Aug 2029,
    INV-US-3101 36,000.00 (01 Sep 2026) and the commission ``COM-K09`` 6,480.00 incurred
    2026-09-05 (PRD WLD-F-27); computed once. The world then holds both contracts. The billing
    plan of WLD-K-09 (36,000.00 on 2027-09-01 and 2028-09-01) is not part of it (CTR-14)."""
    from erev_api.db.tables import customer
    from support.factories import k09_body

    place = world.place
    buyer = place.scalar(select(customer.c.id).where(customer.c.code == "C-09"))
    booked = booked_contract(place, k09_body(UUID(str(buyer))), activate=True)
    appended(
        place,
        UUID(str(booked.contract["id"])),
        2,
        [
            _billing("INV-US-3101", "36000.00", date(2026, 9, 1), "O1"),
            commission(K09_COMMISSION, "6480.00", date(2026, 9, 5)),
        ],
    )
    computed(place, UUID(str(booked.combination_group["id"])))
    return dataclasses.replace(world, contracts=MappingProxyType({**world.contracts, K09: booked}))


def _analysis_people(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> tuple[Actor, Actor, Actor]:
    """Maya (Revenue Accountant, SSP Analyst), Priya (Revenue Reviewer, SSP Approver; MFA) and
    Marcus (Controller, SSP Approver, Tenant Admin; MFA), as in ``k03_castellan``."""
    maya_member = member(keyring, clock, name="maya")
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    found: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        found[name] = enrolled(app, clock, someone)
    return maya, found["priya"], found["marcus"]


def _book_kept(
    app: FastAPI,
    author: Actor,
    approver: Actor,
    *,
    entity_code: str,
    entity_id: UUID,
    book: str,
    keys: Sequence[str],
    first_period_key: str | None = None,
) -> None:
    """``book`` enabled for the workspace (``PATCH /books/{code}``), kept by the entity (``PUT
    /entities/{id}/books/{code}``, by ``approver`` as ``_keep_legacy_book`` does) and its periods
    ``keys`` opened."""
    from support.reference import patch

    listed = get(app, "/api/v1/books", author, {"limit": 50})
    assert listed.status_code == 200, listed.text
    found = next(item for item in listed.json()["items"] if item["code"] == book)
    if not found["is_enabled"]:
        enabled = patch(
            app,
            f"/api/v1/books/{book}",
            author,
            {"is_enabled": True},
            if_match=f'"r{found["row_version"]}"',
        )
        assert enabled.status_code == 200, enabled.text
    body: dict[str, Any] = {"is_enabled": True}
    if first_period_key is not None:
        body["first_period_key"] = first_period_key
    kept = put(app, f"/api/v1/entities/{entity_id}/books/{book}", approver, body)
    assert kept.status_code in (200, 201), kept.text
    _periods_opened(app, author, entity_code=entity_code, book=book, keys=keys)


def _periods_opened(
    app: FastAPI, author: Actor, *, entity_code: str, book: str, keys: Sequence[str]
) -> None:
    """The named periods of one entity and book opened through ``POST /periods/{id}/open``."""
    states = {
        item["period"]["period_key"]: item
        for item in periods(app, author, entity=entity_code, book=book)
    }
    for key in keys:
        state = states[key]
        if state["state"] == "open":
            continue
        opened = post(
            app,
            f"{PERIODS}/{state['id']}/open",
            author,
            {"comment": f"{book} book of {entity_code}"},
            if_match=f'"r{state["row_version"]}"',
        )
        assert opened.status_code == 200, opened.text


def _appended_through_api(
    place: Workspace, contract_id: UUID, *items: Mapping[str, Any]
) -> dict[str, Any]:
    """``POST /contracts/{id}/events`` after the contract's head: the API-S-EventAppend route,
    which checks Step 1 records, moves the status and computes (CTR-7)."""
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    sent = post(
        place.app,
        f"/api/v1/contracts/{contract_id}/events",
        place.author,
        {"events": [dict(item) for item in items]},
        if_match=f'"s{int(head)}"',
    )
    assert sent.status_code == 201, sent.text
    return dict(sent.json())


EVIDENCE_NAME: Final = "evidence.pdf"


def evidence_file(app: FastAPI, actor: Actor, name: str = EVIDENCE_NAME) -> str:
    """``POST /files`` with purpose ``ATTACHMENT``: a stored file ``actor`` may name as the
    evidence of a manual event (04 §16.3 ``evidence_file_ids``); its id."""
    from support import upload_fixtures
    from support.http import call
    from support.principals import cookie_headers

    stored = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": "ATTACHMENT"},
        files={"file": (name, upload_fixtures.PDF, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert stored.status_code == 201, stored.text
    return str(stored.json()["id"])


def submitted_manual_events(
    place: Workspace,
    contract_id: UUID,
    *items: Mapping[str, Any],
    evidence_file_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """``POST /contracts/{id}/events`` by the author for a batch that holds a manual event
    (BUILD_SPEC CTR-6; 04 §16.3 "Manual events"): nothing is appended and the answer names the
    event submission and its approval request. Evidence: ``evidence_file_ids``, or one file the
    author uploads here."""
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    if evidence_file_ids is None:
        evidence_file_ids = [evidence_file(place.app, place.author)]
    sent = post(
        place.app,
        f"/api/v1/contracts/{contract_id}/events",
        place.author,
        {
            "events": [dict(item) for item in items],
            "evidence_file_ids": list(evidence_file_ids),
        },
        if_match=f'"s{int(head)}"',
    )
    assert sent.status_code == 201, sent.text
    created = dict(sent.json())
    assert set(created) == {"event_submission_id", "approval_request_id"}, created
    return created


def approved_manual_events(
    place: Workspace,
    approver: Actor,
    contract_id: UUID,
    *items: Mapping[str, Any],
    evidence_file_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The product's path of a manual event, and nothing below it (BUILD_SPEC CTR-6; PRD
    BR-REC-01): the author submits the batch with its evidence (``submitted_manual_events``),
    ``approver`` — another person, holding ``event.approve`` — approves the request, and the
    approval appends the events as SYSTEM for the author and computes the group. Returns what
    a direct append answers — ``contract``, ``events`` (API-S-Event, in stream order) and
    ``computation`` (``{id, status}`` of the computation that first included them) — with the
    ``event_submission_id`` and the ``approval_request_id``."""
    created = submitted_manual_events(
        place, contract_id, *items, evidence_file_ids=evidence_file_ids
    )
    decided = approve(place.app, created["approval_request_id"], approver)
    assert decided.status_code == 200, decided.text
    submission = get(
        place.app, f"/api/v1/event-submissions/{created['event_submission_id']}", place.author
    )
    assert submission.status_code == 200, submission.text
    assert submission.json()["status"] == "APPLIED", submission.json()
    events = []
    for event_id in submission.json()["applied_event_ids"]:
        shown = get(place.app, f"/api/v1/events/{event_id}", place.author)
        assert shown.status_code == 200, shown.text
        events.append(shown.json())
    header = get(place.app, f"/api/v1/contracts/{contract_id}", place.author)
    assert header.status_code == 200, header.text
    return {
        **created,
        "contract": header.json(),
        "events": events,
        "computation": events[-1]["computation"],
    }


# PRD WLD-K-04 ``SF-ORD-UK-2001`` (J-13-AC-7; WLD-X-14).
K04: Final = "SF-ORD-UK-2001"
AVM_UK: Final = "AVM-UK"
PLATFORM_UK: Final = "AVM-PLAT-UK"
IMPLEMENTATION_UK: Final = "AVM-IMPL-UK"
# PRD §2.6 accounts of the roles a contract performed across two entities reaches (JET-13).
K04_CHART: Final = (
    ("1100", "Accounts receivable", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1200", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("1800", "Intercompany due from", "ASSET", "D", "INTERCOMPANY_DUE_FROM"),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("2800", "Intercompany due to", "LIABILITY", "C", "INTERCOMPANY_DUE_TO"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C", "REVENUE"),
    ("7200", "Foreign exchange gain or loss", "EXPENSE", "D", "FX_GAIN_LOSS"),
)
# PRD §2.5 AVM-RATES, GBP to USD (average, closing): Aug 2026, Sep 2026; Jan to Jul 2026 every
# rate equals the Aug 2026 average; the daily spot rate equals the month average.
K04_GBP_AUGUST: Final = ("1.270000", "1.275000")
K04_GBP_SEPTEMBER: Final = ("1.280000", "1.290000")


@dataclass(frozen=True, slots=True)
class K04World:
    """``SF-ORD-UK-2001`` active with its events through 31 May 2026 (PRD WLD-K-04)."""

    report: ReportWorld  # ``entity_id`` is AVM-UK, the contracting entity
    us_entity_id: UUID
    uk_entity_id: UUID
    contract_id: UUID
    group_id: UUID

    @property
    def app(self) -> FastAPI:
        return self.report.app


def _gbp_rates(rate_type: str) -> list[dict[str, str]]:
    """The PRD §2.5 GBP to USD rates of one AVM-RATES set for Jan to Sep 2026."""
    from datetime import timedelta

    def of_month(number: int) -> tuple[str, str]:
        if number == 9:
            return K04_GBP_SEPTEMBER
        if number == 8:
            return K04_GBP_AUGUST
        return K04_GBP_AUGUST[0], K04_GBP_AUGUST[0]

    pair = {"base_currency": "GBP", "quote_currency": "USD"}
    if rate_type == "spot":
        rows: list[dict[str, str]] = []
        day = date(2026, 1, 1)
        while day <= THROUGH_SEPTEMBER:
            rows.append({**pair, "rate": of_month(day.month)[0], "effective_date": day.isoformat()})
            day += timedelta(days=1)
        return rows
    return [
        {
            **pair,
            "rate": of_month(number)[0 if rate_type == "average" else 1],
            "period_key": f"FY2026-P{number:02d}",
        }
        for number in range(1, 10)
    ]


def k04_saltmarsh(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> K04World:
    """PRD WLD-K-04 through the product's commands. Maya, Priya and Marcus as in
    ``k03_castellan``; USD and GBP enabled; AVM-US (USD, America/New_York) and AVM-UK (GBP,
    Europe/London) share a January calendar for 2026 and 2027 with FY2026-P01 to P09 open; the
    three AVM-RATES sets (spot, closing, average) carry the PRD §2.5 GBP to USD rates, approved by
    Marcus; customer C-04; AVM-PLAT-UK (TPL-SUB-DAILY; observable 60,000.00 GBP) and AVM-IMPL-UK
    (TPL-SVC-PCT; cost plus margin 10,000.00 GBP) under UK-LIST 2026; AVM-MAP-2026-01 over
    ``K04_CHART``. ``SF-ORD-UK-2001`` books O1 for 60,000.00 GBP from 01 Apr 2026 to 31 Mar 2027,
    performed by AVM-US, and O2 for 8,000.00 GBP, performed by AVM-UK; it is activated, takes
    INV-UK-0501 68,000.00 (2026-04-01) and the O2 progress of 50% (2026-04-30) and 100%
    (2026-05-31), and is computed: allocation 58,285.71 / 9,714.29 (WLD-X-14). [J] AVM-UK keeps
    the ``ASC606`` book only (PRD §2.5 adds ``IFRS15``, which no intercompany figure reads)."""
    from datetime import timedelta

    from erev_api.db.tables import obligation_version
    from support.factories import open_periods
    from support.reference import approve, calendar, entity

    maya, priya, marcus = _analysis_people(app, keyring, clock)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "GBP"]})
    assert enabled.status_code == 200, enabled.text
    calendar_id = calendar(app, maya, years=(2026, 2027))
    keys = [f"FY2026-P{month:02d}" for month in range(1, 10)]
    us = entity(app, maya, code=AVM_US, calendar_id=calendar_id)
    uk = entity(
        app,
        maya,
        code=AVM_UK,
        calendar_id=calendar_id,
        functional_currency="GBP",
        time_zone="Europe/London",
    )
    for code in (AVM_US, AVM_UK):
        open_periods(app, maya, entity_code=code, keys=keys)
    for rate_type in ("spot", "closing", "average"):
        rate_set = post(
            app,
            "/api/v1/fx-rate-sets",
            maya,
            {
                "code": f"AVM-RATES-{rate_type.upper()}",
                "name": f"AVM-RATES {rate_type}",
                "rate_type": rate_type,
            },
        )
        assert rate_set.status_code == 201, rate_set.text
        draft = post(
            app,
            f"/api/v1/fx-rate-sets/{rate_set.json()['id']}/versions",
            maya,
            {
                "coverage_from": "2026-01-01",
                "coverage_to": THROUGH_SEPTEMBER.isoformat(),
                "rates": _gbp_rates(rate_type),
            },
        )
        assert draft.status_code == 201, draft.text
        submitted = post(
            app,
            f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
            maya,
            {"comment": "AVM-RATES, PRD §2.5"},
            if_match=f'"r{draft.json()["row_version"]}"',
        )
        assert submitted.status_code == 200, submitted.text
        clock.advance(timedelta(minutes=1))
        decided = approve(app, submitted.json()["pending_approval_request_id"], marcus)
        assert decided.status_code == 200, decided.text
    buyer = customer_id(app, maya, code="C-04", name="Saltmarsh Freight Ltd (Demo)")
    term = {"start_date": "2026-04-01", "end_date": "2027-03-31"}
    platform = product_with_template(
        app,
        maya,
        code=PLATFORM_UK,
        name="Platform, enterprise tier, 12 months (UK)",
        revenue_category="SUBSCRIPTION",
    )
    implementation = product_with_template(
        app,
        maya,
        code=IMPLEMENTATION_UK,
        name="Implementation, UK standard",
        revenue_category="SERVICES",
    )
    daily = published_template(
        app,
        maya,
        marcus,
        code="TPL-SUB-DAILY",
        outputs=TPL_SUB_DAILY,
        case_line={
            "obligation_key": "POB-01",
            "product_code": PLATFORM_UK,
            "quantity": "1",
            "total_price": "60000.00",
            **term,
        },
    )
    percent = published_template(
        app,
        maya,
        marcus,
        code="TPL-SVC-PCT",
        outputs=TPL_SVC_PCT,
        case_line={
            "obligation_key": "POB-01",
            "product_code": IMPLEMENTATION_UK,
            "quantity": "1",
            "total_price": "8000.00",
        },
    )
    set_default_template(app, maya, platform, daily["template_id"])
    set_default_template(app, maya, implementation, percent["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="UK-LIST", currency="GBP"),
        label="2026",
        effective_from="2026-01-01",
        entries=[
            point_entry(PLATFORM_UK, "60000.00", currency="GBP", value_basis="AMOUNT"),
            point_entry(IMPLEMENTATION_UK, "10000.00", "cost_plus_margin", currency="GBP"),
        ],
    )
    published_mapping(app, maya, marcus, chart=K04_CHART)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": K04,
            "customer_id": str(buyer),
            "contracting_entity_code": AVM_UK,
            "transaction_currency": "GBP",
            "inception_date": "2026-04-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM_UK,
                    "quantity": "1",
                    "total_price": {"amount": "60000.00", "currency": "GBP"},
                    "performing_entity_code": AVM_US,
                    **term,
                },
                {
                    "obligation_key": "O2",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity": "1",
                    "total_price": {"amount": "8000.00", "currency": "GBP"},
                    "performing_entity_code": AVM_UK,
                },
            ],
        },
        activate=True,
    )
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    invoice = BillingRecordedV1(
        invoice_number="INV-UK-0501",
        line_external_id="INV-UK-0501-1",
        amount=MoneyIn(amount="68000.00", currency="GBP"),
        issue_date=date(2026, 4, 1),
    )
    appended(
        place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 4, 1),
                payload=invoice,
            ),
            _progress("O2", "0.50", date(2026, 4, 30)),
            _progress("O2", "1", date(2026, 5, 31)),
        ],
    )
    computed(place, group_id)
    lines = select(obligation_version.c.obligation_key, obligation_version.c.allocated_amount)
    allocated = {
        str(row["obligation_key"]): Decimal(row["allocated_amount"])
        for row in place.rows(lines.where(obligation_version.c.combination_group_id == group_id))
    }
    # WLD-X-14: 68,000 × 60,000 ÷ 70,000 with the largest remainder
    assert allocated == {"O1": Decimal("58285.71"), "O2": Decimal("9714.29")}
    report = ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=UUID(str(uk["id"])),
        contracts=MappingProxyType({K04: booked}),
    )
    return K04World(
        report=report,
        us_entity_id=UUID(str(us["id"])),
        uk_entity_id=UUID(str(uk["id"])),
        contract_id=contract_id,
        group_id=group_id,
    )


def _template_published_from(
    app: FastAPI,
    author: Actor,
    approver: Actor,
    *,
    code: str,
    outputs: Mapping[str, Any],
    case_line: Mapping[str, Any],
    effective_from: str,
) -> dict[str, str]:
    """``support.factories.published_template`` for a version effective from ``effective_from``
    (an instant), whose example case books on that day: a contract with an inception before 2026
    needs templates in force then."""
    from support.factories import CONFIG_TEST_CASES, POB_TEMPLATE_VERSIONS, POB_TEMPLATES
    from support.reference import approve

    created = post(app, POB_TEMPLATES, author, {"code": code, "name": f"Template {code}"})
    assert created.status_code == 201, created.text
    template_id = str(created.json()["id"])
    version = post(
        app,
        f"{POB_TEMPLATES}/{template_id}/versions",
        author,
        {**outputs, "effective_from": effective_from},
    )
    assert version.status_code == 201, version.text
    version_id = str(version.json()["id"])
    case = post(
        app,
        CONFIG_TEST_CASES,
        author,
        {
            "subject_type": "pob_template_version",
            "subject_id": version_id,
            "name": f"{case_line['product_code']} booking",
            "input": {"booking_date": effective_from[:10], "lines": [dict(case_line)]},
            "expected_output": {"drafts": [{"obligation_key": case_line["obligation_key"]}]},
        },
    )
    assert case.status_code == 201, case.text
    tested = post(app, f"{POB_TEMPLATE_VERSIONS}/{version_id}/test", author, {})
    assert (tested.status_code, tested.json()["status"]) == (200, "TESTED"), tested.text
    sent = post(
        app, f"{POB_TEMPLATE_VERSIONS}/{version_id}/submit", author, {"comment": "Ready for review"}
    )
    assert sent.status_code == 200, sent.text
    decided = approve(app, str(sent.json()["pending_approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    return {"template_id": template_id, "version_id": version_id}


# Answer key ONB-S11-MODRETRO-OWN (research 04 S11-MODRETRO-OWN).
C_ADOPT: Final = "C-ADOPT"
US01: Final = "US01"
ADOPTION_DATE: Final = date(2026, 1, 1)  # the date of initial application
# The key's accounts of the roles the contract reaches, with the LEGACY book's revenue role.
ADOPTION_CHART: Final = (
    ("1100", "Accounts receivable (billed)", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1200", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("4000", "Revenue - products", "REVENUE", "C", "REVENUE"),
    ("4900", "Pre-standard revenue", "REVENUE", "C", "PRE_STANDARD_REVENUE"),
)
# Legacy GAAP recognised 100,000.00 a year, half on each line (150,000.00 each over three years):
# the year 2025 at its end, and the first half of 2026, which lies after the adoption date.
ADOPTION_LEGACY_REVENUE: Final = (
    (date(2025, 12, 31), "50000.00"),
    (date(2026, 6, 30), "25000.00"),
)


def onb_s11_modretro_own(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """The facts of answer key ONB-S11-MODRETRO-OWN through the product's commands, with the
    ``LEGACY`` book the adoption bridge compares against. Maya, Priya and Marcus as in
    ``k03_castellan``; US01 (USD) on a January calendar for 2025 to 2027 keeps ``ASC606`` and
    ``LEGACY`` from FY2025-P01, with FY2025-P01 to FY2026-P09 open in both; LIC-PERP (TPL-LIC, a
    functional licence recognised at a point in time; observable 180,000.00) and PCS-36
    (TPL-RATABLE, time elapsed by whole months; observable 120,000.00), templates, SSP book
    version and mapping in force from 01 Jan 2025. ``C-ADOPT`` books L1-LIC and L2-PCS (01 Jan
    2025 to 31 Dec 2027) for 150,000.00 each on 01 Jan 2025, is activated, invoiced 300,000.00
    (INV-ADOPT) and delivers the licence that day; legacy GAAP recognised 100,000.00 a year
    (``PRE_STANDARD_REVENUE_RECORDED``, ``ADOPTION_LEGACY_REVENUE``); Priya approves the batch,
    which holds a manual delivery (BUILD_SPEC CTR-6), and the approval appends and computes. [J]
    The key states the world for ``ASC606`` alone ("the LEGACY book comparison belongs to the
    delta-posting keys"); its tenant value ``recognition.time_convention = MONTHLY_EVEN`` reaches
    the support line through the template's ratable convention, and the entity's
    ``transition.first_time_application`` is the registry default ``MODIFIED_RETROSPECTIVE``."""
    from support.reference import calendar, entity, mapping_published

    maya, priya, marcus = _analysis_people(app, keyring, clock)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    created = entity(
        app, maya, code=US01, calendar_id=calendar(app, maya, years=(2025, 2026, 2027))
    )
    entity_id = UUID(str(created["id"]))
    keys = [f"FY2025-P{month:02d}" for month in range(1, 13)]
    keys += [f"FY2026-P{month:02d}" for month in range(1, 10)]
    _periods_opened(app, maya, entity_code=US01, book="ASC606", keys=keys)
    _book_kept(
        app,
        maya,
        marcus,
        entity_code=US01,
        entity_id=entity_id,
        book="LEGACY",
        keys=keys,
        first_period_key="FY2025-P01",
    )
    buyer = customer_id(app, maya, code="CUST-1", name="Example Customer (Demo)")
    start = "2025-01-01T00:00:00Z"
    term = {"start_date": "2025-01-01", "end_date": "2027-12-31"}
    for code, name, category, template_code, outputs, line in (
        (
            "LIC-PERP",
            "Software licence (Demo)",
            "LICENCE",
            "TPL-LIC",
            {
                "obligation_kind": "LICENCE",
                "distinctness": "distinct",
                "satisfaction_pattern": "POINT_IN_TIME",
                "over_time_criterion": "NOT_APPLICABLE",
                "recognition_method": "POINT_IN_TIME",
                "licence_nature": "FUNCTIONAL",
            },
            {},
        ),
        (
            "PCS-36",
            "Post-contract support 36 months (Demo)",
            "SERVICES",
            "TPL-RATABLE",
            {
                "distinctness": "distinct",
                "satisfaction_pattern": "OVER_TIME",
                "over_time_criterion": "OT_A",
                "recognition_method": "TIME_ELAPSED",
                "ratable_convention": "MONTHLY_EVEN",
            },
            term,
        ),
    ):
        item = product_with_template(app, maya, code=code, name=name, revenue_category=category)
        template = _template_published_from(
            app,
            maya,
            marcus,
            code=template_code,
            outputs=outputs,
            case_line={
                "obligation_key": "POB-01",
                "product_code": code,
                "quantity": "1",
                "total_price": "150000.00",
                **line,
            },
            effective_from=start,
        )
        set_default_template(app, maya, item, template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="SSP-MAIN"),
        label="2025",
        effective_from="2025-01-01",
        entries=[point_entry("LIC-PERP", "180000.00"), point_entry("PCS-36", "120000.00")],
    )
    mapping_published(
        app,
        maya,
        marcus,
        name="MAP-2025-01",
        effective_from=start,
        rules=[
            {
                "account_role": role,
                "gl_account_id": new_gl_account(
                    app, maya, code=code, name=name, account_type=kind, normal_balance=normal
                ),
            }
            for code, name, kind, normal, role in ADOPTION_CHART
        ],
    )
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    price = {"amount": "150000.00", "currency": "USD"}
    booked = booked_contract(
        place,
        {
            "external_id": C_ADOPT,
            "customer_id": str(buyer),
            "contracting_entity_code": US01,
            "transaction_currency": "USD",
            "inception_date": "2025-01-01",
            "lines": [
                {
                    "obligation_key": "L1-LIC",
                    "product_code": "LIC-PERP",
                    "quantity": "1",
                    "total_price": price,
                },
                {
                    "obligation_key": "L2-PCS",
                    "product_code": "PCS-36",
                    "quantity": "1",
                    "total_price": price,
                    **term,
                },
            ],
        },
        activate=True,
    )
    usd = {"currency": "USD"}
    # BUILD_SPEC CTR-6: the delivery is a person's, so Maya's request waits whole and Priya
    # approves it; the approval appends the batch and computes (no evidence is asked of a
    # delivery on control transfer, 04 §16.3).
    approved_manual_events(
        place,
        priya,
        UUID(str(booked.contract["id"])),
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2025-01-01",
            "payload": {
                "invoice_number": "INV-ADOPT",
                "line_external_id": "INV-ADOPT-1",
                "amount": {"amount": "300000.00", **usd},
                "issue_date": "2025-01-01",
            },
        },
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2025-01-01",
            "payload": {"obligation_key": "L1-LIC", "quantity": "1", "trigger": "CONTROL_TRANSFER"},
        },
        *(
            {
                "event_type": "PRE_STANDARD_REVENUE_RECORDED",
                "effective_date": day.isoformat(),
                "payload": {"obligation_key": key, "amount": {"amount": amount, **usd}},
            }
            for day, amount in ADOPTION_LEGACY_REVENUE
            for key in ("L1-LIC", "L2-PCS")
        ),
        evidence_file_ids=[],
    )
    return ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=entity_id,
        contracts=MappingProxyType({C_ADOPT: booked}),
    )


# Answer key IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK (research 04 §13 #1; POL-011).
C_IFRS_SW01: Final = "C-IFRS-SW01"
# The key's accounts of the roles the contract reaches in its two books.
IFRS_SW01_CHART: Final = (
    ("1100", "Accounts receivable", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1200", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("2090", "Subledger clearing", "LIABILITY", "C", "BILLING_CLEARING:UNAPPLIED_CASH"),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("2105", "Deposit liability", "LIABILITY", "C", "DEPOSIT_LIABILITY"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C", "REVENUE"),
)
IFRS_SW01_NOT_PROBABLE: Final = (
    "Not probable (likely to occur) in the ASC606 book; weak payment history"
)
IFRS_SW01_PROBABLE: Final = "Probable (more likely than not) in the IFRS15 book"


def ifrs_sw01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """The facts of answer key IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK through the product's
    commands. Maya, Priya and Marcus as in ``k03_castellan``; US01 (USD) keeps ``ASC606`` and
    ``IFRS15`` with FY2026-P01 to P09 open in both; SVC-12M (TPL-RAT-ME, time elapsed by whole
    months; observable 12,000.00); AVM-MAP-2026-01 over ``IFRS_SW01_CHART``. ``C-IFRS-SW01`` books
    L1-SERVICE for 12,000.00 over 2026. Collectibility is assessed per book on 01 Jan 2026, each
    assessment on a judgement record Marcus reviewed: not probable in ``ASC606`` and probable in
    ``IFRS15``. The contract is then invoiced and paid 1,000.00 on the first day of January,
    February and March 2026; every append computes (CTR-7). ``ASC606`` holds no contract (a
    deposit liability of 3,000.00); ``IFRS15`` recognises 1,000.00 a month. [J] The key names two
    ``COLLECTIBILITY`` records; the product takes a not-probable assessment only on a
    ``NOT_A_CONTRACT`` record (PRD SM-02 guard), so the ``ASC606`` record has that topic."""
    from erev_api.db.tables import contract_version
    from support.factories import open_periods
    from support.reference import approve, calendar, entity

    maya, priya, marcus = _analysis_people(app, keyring, clock)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    created = entity(app, maya, code=US01, calendar_id=calendar(app, maya, years=(2026, 2027)))
    entity_id = UUID(str(created["id"]))
    keys = [f"FY2026-P{month:02d}" for month in range(1, 10)]
    open_periods(app, maya, entity_code=US01, keys=keys)
    _book_kept(app, maya, maya, entity_code=US01, entity_id=entity_id, book="IFRS15", keys=keys)
    buyer = customer_id(app, maya, code="CUST-1", name="Pellworth Logistics Inc. (Demo)")
    service = product_with_template(
        app, maya, code="SVC-12M", name="Managed service, 12 months", revenue_category="SERVICES"
    )
    term = {"start_date": "2026-01-01", "end_date": "2026-12-31"}
    template = published_template(
        app,
        maya,
        marcus,
        code="TPL-RAT-ME",
        outputs={
            "distinctness": "distinct",
            "satisfaction_pattern": "OVER_TIME",
            "over_time_criterion": "OT_A",
            "recognition_method": "TIME_ELAPSED",
            "ratable_convention": "MONTHLY_EVEN",
        },
        case_line={
            "obligation_key": "POB-01",
            "product_code": "SVC-12M",
            "quantity": "1",
            "total_price": "12000.00",
            **term,
        },
    )
    set_default_template(app, maya, service, template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="SSP-US-2026"),
        label="2026",
        effective_from="2026-01-01",
        entries=[point_entry("SVC-12M", "12000.00")],
    )
    published_mapping(app, maya, marcus, chart=IFRS_SW01_CHART)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": C_IFRS_SW01,
            "customer_id": str(buyer),
            "contracting_entity_code": US01,
            "transaction_currency": "USD",
            "inception_date": "2026-01-01",
            "document_ref": C_IFRS_SW01,  # table 15.4-I SOURCE_REFERENCE: the approved activation
            "lines": [
                {
                    "obligation_key": "L1-SERVICE",
                    "product_code": "SVC-12M",
                    "quantity": "1",
                    "total_price": {"amount": "12000.00", "currency": "USD"},
                    **term,
                }
            ],
        },
        activate=False,
    )
    contract_id = UUID(str(booked.contract["id"]))
    records: dict[str, str] = {}
    refundable = {"consideration_nonrefundable": False}  # 606-10-25-7: a liability, not revenue
    for book, topic, conclusion, questionnaire in (
        ("ASC606", "NOT_A_CONTRACT", IFRS_SW01_NOT_PROBABLE, refundable),
        ("IFRS15", "COLLECTIBILITY", IFRS_SW01_PROBABLE, None),
    ):
        body: dict[str, Any] = {
            "topic": topic,
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "book": book,
            "conclusion": conclusion,
            "rationale": "Credit review of the customer's payment history and the contract terms.",
            # the five criteria of a Step 1 review (supervisor rulings R-113 (f), R-115 (f))
            "questionnaire": {"criteria": step1_criteria(topic), **(questionnaire or {})},
        }
        record = judgement_submitted(app, maya, body)
        reviewed = approve(app, str(record["approval_request_id"]), marcus)
        assert reviewed.status_code == 200, reviewed.text
        records[book] = str(record["id"])
    for book, probable in (("ASC606", False), ("IFRS15", True)):
        _appended_through_api(
            place,
            contract_id,
            {
                "event_type": "COLLECTIBILITY_ASSESSED",
                "effective_date": "2026-01-01",
                "payload": {
                    "book": book,
                    "is_probable": probable,
                    "judgement_record_id": records[book],
                },
            },
        )
    # Supervisor ruling R-20 (b) (04 §16.3 rev 1.105): books that differ get no not-a-contract
    # gate on the recorder's authority — the contract stays DRAFT until its activation is approved,
    # where the engine decides per book (S02-R-01): not a contract in ASC606, active in IFRS15.
    # Maya submits; Priya, the Revenue Reviewer, approves; the key's invoices follow.
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    submitted = post(
        app,
        f"/api/v1/contracts/{contract_id}/submit-activation",
        maya,
        {},
        if_match=f'"s{int(head)}"',
    )
    assert submitted.status_code == 200, submitted.text
    activated = approve(app, submitted.headers["x-erev-approval-request"], priya)
    assert activated.status_code == 200, activated.text
    for month in (1, 2, 3):
        day = f"2026-{month:02d}-01"
        amount = {"amount": "1000.00", "currency": "USD"}
        _appended_through_api(
            place,
            contract_id,
            {
                "event_type": "BILLING_RECORDED",
                "effective_date": day,
                "payload": {
                    "invoice_number": f"INV-SW01-{month}",
                    "line_external_id": f"INV-SW01-{month}-1",
                    "amount": amount,
                    "issue_date": day,
                },
            },
            {
                "event_type": "PAYMENT_RECEIVED",
                "effective_date": day,
                "payload": {
                    "receipt_reference": f"RCPT-SW01-{month}",
                    "amount": amount,
                    "receipt_date": day,
                    "applied_invoice_numbers": [f"INV-SW01-{month}"],
                },
            },
        )
    statuses = {
        str(row["book_code"]): str(row["status_in_book"])
        for row in place.rows(
            select(contract_version.c.book_code, contract_version.c.status_in_book)
            .where(
                contract_version.c.combination_group_id == UUID(str(booked.combination_group["id"]))
            )
            .order_by(contract_version.c.version_no)
        )
    }
    # the key's checkpoints: not a contract in ASC606, active in IFRS15
    assert statuses == {"ASC606": "NOT_A_CONTRACT", "IFRS15": "ACTIVE"}, statuses
    return ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=entity_id,
        contracts=MappingProxyType({C_IFRS_SW01: booked}),
    )


# POLICIES CHK-010 (answer key POS-CHK-010).
C_POS: Final = "C-POS"
CHK_010_CHART: Final = (
    ("1100", "Accounts receivable (billed)", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1200", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("4010", "Revenue - services / subscriptions", "REVENUE", "C", "REVENUE"),
)
CHK_010_DAY: Final = date(2026, 1, 31)


def chk_010_position(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """The contract of POLICIES CHK-010 (answer key POS-CHK-010) through the product's commands.
    Maya, Priya and Marcus as in ``k03_castellan``; US01 (USD) with FY2026-P01 to P09 open;
    TM-HOURS (TPL-RTI, right to invoice; an unconditional right, POL-122), PHASE-1 (TPL-MILESTONE;
    conditional) and PHASE-2 (TPL-OUTPUT, output percent; conditional) under SSP-MAIN 2026 (0,
    10,000 and 2,000). ``C-POS`` books P1-TM at 25.00 an hour, P2-MILESTONE for 10,000.00 and
    P3-BUILD for 2,000.00 on 01 Jan 2026 and is activated; on 31 Jan 2026 it delivers 120 hours,
    achieves the milestone, reports 50% of the build and is invoiced 4,000.00 on P2 (INV-POS-1)
    and 5,000.00 on P3 (INV-POS-2); the append computes. Revenue 14,000.00, billed 9,000.00:
    unbilled receivable 3,000.00 (P1) and contract asset 2,000.00 (P2). [J] The key books P1-TM
    with quantity 1 and delivers 120 hours; the product refuses a delivery beyond the booked
    quantity (``PROGRESS_OVER_DELIVERY``), so the line books the 120 hours."""
    from erev_api.db.tables import contract_version_balance
    from support.factories import open_periods
    from support.reference import calendar, entity

    maya, priya, marcus = _analysis_people(app, keyring, clock)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    created = entity(app, maya, code=US01, calendar_id=calendar(app, maya, years=(2026,)))
    open_periods(
        app, maya, entity_code=US01, keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    buyer = customer_id(app, maya, code="CUST-1", name="Example Customer (Demo)")
    conditional = {
        "distinctness": "distinct",
        "satisfaction_pattern": "OVER_TIME",
        "over_time_criterion": "OT_C",
        "policy_values": {"balance.right_to_consideration": "CONDITIONAL"},
    }
    for code, name, template_code, outputs, line in (
        (
            "TM-HOURS",
            "Time and materials hours (Demo)",
            "TPL-RTI",
            {
                "distinctness": "distinct",
                "satisfaction_pattern": "OVER_TIME",
                "over_time_criterion": "OT_A",
                "recognition_method": "RIGHT_TO_INVOICE",
                "policy_values": {"balance.right_to_consideration": "UNCONDITIONAL"},
            },
            {
                "quantity": "120",
                "total_price": "0.00",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        ),
        (
            "PHASE-1",
            "Design phase with milestone billing (Demo)",
            "TPL-MILESTONE",
            {**conditional, "recognition_method": "MILESTONE"},
            {"quantity": "1", "total_price": "10000.00"},
        ),
        (
            "PHASE-2",
            "Build phase (Demo)",
            "TPL-OUTPUT",
            {**conditional, "recognition_method": "OUTPUT_PERCENT"},
            {"quantity": "1", "total_price": "2000.00"},
        ),
    ):
        item = product_with_template(app, maya, code=code, name=name, revenue_category="SERVICES")
        template = published_template(
            app,
            maya,
            marcus,
            code=template_code,
            outputs=outputs,
            case_line={"obligation_key": "POB-01", "product_code": code, **line},
        )
        set_default_template(app, maya, item, template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="SSP-MAIN"),
        label="2026",
        effective_from="2026-01-01",
        entries=[
            point_entry("TM-HOURS", "0"),
            point_entry("PHASE-1", "10000"),
            point_entry("PHASE-2", "2000"),
        ],
    )
    published_mapping(app, maya, marcus, chart=CHK_010_CHART)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": C_POS,
            "customer_id": str(buyer),
            "contracting_entity_code": US01,
            "transaction_currency": "USD",
            "inception_date": "2026-01-01",
            "lines": [
                {
                    "obligation_key": "P1-TM",
                    "product_code": "TM-HOURS",
                    "quantity": "120",
                    "total_price": {"amount": "0.00", "currency": "USD"},
                    "unit_price": "25.00",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                },
                {
                    "obligation_key": "P2-MILESTONE",
                    "product_code": "PHASE-1",
                    "quantity": "1",
                    "total_price": {"amount": "10000.00", "currency": "USD"},
                },
                {
                    "obligation_key": "P3-BUILD",
                    "product_code": "PHASE-2",
                    "quantity": "1",
                    "total_price": {"amount": "2000.00", "currency": "USD"},
                },
            ],
        },
        activate=True,
    )
    contract_id = UUID(str(booked.contract["id"]))
    # POL-122 is an obligation override; product-level pins do not authorize this treatment.
    override = post(
        app,
        "/api/v1/policy-overrides",
        maya,
        {
            "contract_id": str(contract_id),
            "obligation_key": "P1-TM",
            "policy_key": "balance.right_to_consideration",
            "value": "UNCONDITIONAL",
            "rationale": "CHK-010: the right to consideration for P1-TM is unconditional.",
        },
    )
    assert override.status_code == 201, override.text
    submitted = post(app, f"/api/v1/policy-overrides/{override.json()['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    decision = approve(app, str(submitted.json()["approval_request_id"]), marcus)
    assert decision.status_code == 200, decision.text
    day = CHK_010_DAY.isoformat()
    # BUILD_SPEC CTR-6: a delivery, a milestone and a progress event of a person wait for
    # another user; Maya submits the batch with one evidence file and Priya approves it.
    approved_manual_events(
        place,
        priya,
        contract_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": day,
            "payload": {"obligation_key": "P1-TM", "quantity": "120", "trigger": "DELIVERY"},
        },
        {
            "event_type": "MILESTONE_ACHIEVED",
            "effective_date": day,
            "payload": {
                "obligation_key": "P2-MILESTONE",
                "milestone_code": "DESIGN-SIGNOFF",
                "cumulative_weight": "1",
            },
        },
        {
            "event_type": "PROGRESS_RECORDED",
            "effective_date": day,
            "payload": {
                "obligation_key": "P3-BUILD",
                "cumulative_progress_ratio": "0.5",
                "measure": "OUTPUT_PERCENT",
            },
        },
        *(
            {
                "event_type": "BILLING_RECORDED",
                "effective_date": day,
                "payload": {
                    "invoice_number": invoice,
                    "line_external_id": f"{invoice}-1",
                    "obligation_key": key,
                    "amount": {"amount": amount, "currency": "USD"},
                    "issue_date": day,
                },
            }
            for invoice, key, amount in (
                ("INV-POS-1", "P2-MILESTONE", "4000.00"),
                ("INV-POS-2", "P3-BUILD", "5000.00"),
            )
        ),
    )
    (balance,) = place.rows(
        select(
            contract_version_balance.c.contract_liability_txn,
            contract_version_balance.c.contract_asset_txn,
            contract_version_balance.c.unbilled_receivable_txn,
        ).where(contract_version_balance.c.contract_id == contract_id)
    )
    # CHK-010: net position −5,000.00 = unbilled receivable 3,000.00 + contract asset 2,000.00
    assert [Decimal(value) for value in balance.values()] == [
        Decimal("0.00"),
        Decimal("2000.00"),
        Decimal("3000.00"),
    ]
    return ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=UUID(str(created["id"])),
        contracts=MappingProxyType({C_POS: booked}),
    )


# --- BUILD_SPEC RPS-8: a close through the product, WLD-K-07 and the late invoice INV-DE-4390 -----

K07: Final = "NS-SO-DE-5003"
AVM_DE: Final = "AVM-DE"
FLEET: Final = "AVM-FLEET"
EXPANSION_CREDIT: Final = "AVM-EXP-CREDIT"
LATE_INVOICE: Final = "INV-DE-4390"
LATE_INVOICE_FILE: Final = "avm-de-invoices-2026-09.csv"  # PRD WLD-F-22
FEBRUARY_2026: Final = "FY2026-P02"
# PRD §2.6 TPL-PROD-PIT (point in time on delivery) and TPL-OPTION (a customer option that is a
# material right).
TPL_PROD_PIT: Final = MappingProxyType(
    {
        "distinctness": "distinct",
        "satisfaction_pattern": "POINT_IN_TIME",
        "over_time_criterion": "NOT_APPLICABLE",
        "recognition_method": "POINT_IN_TIME",
    }
)
TPL_OPTION: Final = MappingProxyType({"obligation_kind": "MATERIAL_RIGHT", **TPL_PROD_PIT})
# The CSV v2 ``invoices`` columns a document line without tax lines fills (04 T-IMP-01, NC-19).
INVOICE_COLUMNS: Final = (
    "contract",
    "document_kind",
    "invoice_number",
    "issue_date",
    "lines.line_external_id",
    "lines.product_code",
    "lines.quantity",
    "lines.amount.amount",
    "lines.amount.currency",
)
_TOTP_STEPS: Final[dict[UUID, int]] = {}  # the TOTP step each persona last verified at


class ErpLedger:
    """An ERP-like general ledger behind a journal export (05 ADP-10 to ADP-12): it answers each
    chunk once with ``POSTED`` and a document id that names the batch, and a repeated external id
    with the first answer. The product's export, relay and acknowledgement run against it; a
    ``CSV`` export waits for a confirmation command that is not built (05 ADP-33; CLO-14)."""

    def __init__(self) -> None:
        self.posted: dict[str, Any] = {}

    def factory(self, context: Any) -> Any:
        return _ErpGl(self, context)


class _ErpGl:
    def __init__(self, ledger: ErpLedger, context: Any) -> None:
        from erev_api.adapters.gl.csv import CsvGl

        self._ledger = ledger
        self._csv = CsvGl(context)

    @property
    def code(self) -> str:
        return "NETSUITE"

    def validate_accounts(self, accounts: Any, dimensions: Any) -> Any:
        return self._csv.validate_accounts(accounts, dimensions)

    def post_chunk(self, chunk: Any) -> Any:
        import hashlib

        from erev_api.domain.journals import ports

        posted = self._ledger.posted
        found = posted.get(chunk.external_id)
        if found is None:
            found = ports.PostingResult(
                external_id=chunk.external_id,
                status="POSTED",
                gl_document_id="GL-" + str(chunk.external_id).split(":", 2)[-1],
                gl_posted_date=chunk.period_end_date,
                response_sha256=hashlib.sha256(chunk.external_id.encode("utf-8")).hexdigest(),
            )
            posted[chunk.external_id] = found
        return found

    def get_posting(self, external_id: str) -> Any:
        return self._ledger.posted.get(external_id)

    def pull_chart_of_accounts(self) -> Any:
        return self._csv.pull_chart_of_accounts()

    def pull_trial_balance(self, entity: Any, period: Any, accounts: Any) -> Any:
        return self._csv.pull_trial_balance(entity, period, accounts)


def _exported_to_erp(world: ReportWorld, run_id: str) -> dict[str, Any]:
    """``POST /journal-runs/{id}/export`` and its job with an ``ErpLedger`` in the ``CSV`` slot of
    the composition root for that export only; returns API-S-JournalRun."""
    from erev_api.domain.journals import ports
    from erev_api.enums import GlAdapter

    slot = GlAdapter.CSV
    kept = ports.GL_ADAPTERS.get(slot)
    ports.GL_ADAPTERS[slot] = ErpLedger().factory
    try:
        exported = post(
            world.app, f"{JOURNAL_RUNS}/{run_id}/export", world.maya, {"adapter": slot.value}
        )
        assert exported.status_code == 202, exported.text
        finished = run_now(world, UUID(str(exported.json()["id"])))
    finally:
        if kept is None:
            ports.GL_ADAPTERS.pop(slot, None)
        else:
            ports.GL_ADAPTERS[slot] = kept
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def on_record_clock(world: ReportWorld, clock: FrozenClock) -> ReportWorld:
    """The frozen clock set one second after the server's present, and the personas signed in
    again (``resigned``). A close runs on the record-time clock: T-CON-05 ``recorded_at`` is the
    server's (DB-08), and a lock stamps its record with the application clock and freezes its
    datasets at a cutoff that has to cover them (ENGINE_SPEC_B S15-R-18c)."""
    from datetime import timedelta

    from sqlalchemy import func

    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp + timedelta(seconds=1))
    return resigned(world)


def verified(world: ReportWorld, clock: FrozenClock, name: str) -> ReportWorld:
    """The world with persona ``name`` (``priya``, ``marcus``) freshly verified by TOTP
    (BR-PLT-06). The clock moves on thirty seconds only when the persona already verified at the
    present step — a spent code is refused (T-PLT-04 ``last_used_step``)."""
    from datetime import timedelta

    from erev_api.auth import totp
    from support.principals import step_up

    actor: Actor = getattr(world, name)
    user_id = actor.member.user_id
    if _TOTP_STEPS.get(user_id) == totp.time_step(clock.now()):
        clock.advance(timedelta(seconds=30))
    _TOTP_STEPS[user_id] = totp.time_step(clock.now())
    return dataclasses.replace(world, **{name: step_up(world.app, clock, actor)})


def period_state(world: ReportWorld, entity_code: str, period_key: str) -> dict[str, Any]:
    """API-S-Period of one period of an entity in its primary book."""
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity=entity_code)
        if item["period"]["period_key"] == period_key
    ]
    return dict(found)


def posted_journal(
    world: ReportWorld, clock: FrozenClock, *, entity_code: str, period_key: str
) -> tuple[dict[str, Any], ReportWorld]:
    """One journal run through its life (PRD SM-08): Maya calculates and submits it, Priya
    (Revenue Reviewer, fresh TOTP) approves it, Maya exports it and the ERP ledger acknowledges
    it. Returns API-S-JournalRun (``acknowledged``) and the world with Priya's verified session."""
    from support.reference import approve

    run = journal_run(world, period_key=period_key, entity_code=entity_code)
    submitted = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    world = verified(world, clock, "priya")
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    shown = _exported_to_erp(world, str(run["id"]))
    assert shown["state"] == "acknowledged", shown
    return shown, world


def period_locked(
    world: ReportWorld, clock: FrozenClock, *, entity_code: str, period_key: str
) -> tuple[dict[str, Any], ReportWorld]:
    """One period closed through the product (PRD SM-07 ``open → closing → closed``): Maya starts
    the close; the period's journal run is calculated, approved, exported and acknowledged
    (``posted_journal``); Maya requests the lock and Marcus (Controller, fresh TOTP) approves it,
    which certifies the gates and freezes the twelve datasets. Every earlier period of the entity is
    closed first as fixture state (``close_world.periods_closed_before``; PRD BR-CLS-08, supervisor
    ruling R-6: the lock is chronological). Two stand-ins: the two required
    reconciliations are rows reviewed through the SM-09 transitions
    (``close_world.reviewed_reconciliations_for``) — no command generates a reconciliation before
    CLO-15 — and the period's close run is a ``SUCCEEDED`` row
    (``close_world.close_run_succeeded_for``; supervisor ruling R-114 (b)), written right before
    the request: fixture state for the gate ``CLOSE_RUN_COMPLETED``, which posts no period end. A
    world that needs its period end posted runs the run (``support.close_runs.closed``). Returns
    the period's journal run and the world with the verified sessions."""
    from support.close_world import (
        close_run_succeeded_for,
        periods_closed_before,
        reviewed_reconciliations_for,
    )
    from support.reference import approve

    app = world.app
    state = period_state(world, entity_code, period_key)
    # PRD BR-CLS-08 (supervisor ruling R-6): a period is submitted for lock, and locked, only when
    # every earlier period of its entity and book is closed. The earlier periods are closed as
    # fixture state of that order rule — their lines stay as posted; a caller that closed them
    # itself loses nothing, since a period already ``closed`` is left as it is.
    periods_closed_before(
        world.place,
        app,
        world.maya,
        entity_id=UUID(str(state["entity"]["id"])),
        before=period_key,
        entity_code=entity_code,
    )
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": f"{state['period']['name']} close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    run, world = posted_journal(world, clock, entity_code=entity_code, period_key=period_key)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
        close_run_succeeded_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
    state = period_state(world, entity_code, period_key)
    requested = post(
        app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": f"{state['period']['name']} close complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    world = verified(world, clock, "marcus")
    decided = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert period_state(world, entity_code, period_key)["state"] == "closed"
    return run, world


def period_reopened(
    world: ReportWorld, clock: FrozenClock, *, entity_code: str, period_key: str, comment: str
) -> ReportWorld:
    """A closed period reopened for an error correction (PRD J-14.1 to J-14.3; BR-CLS-02): Priya
    requests it, Marcus approves (1 of 2) and Elena, a second Controller, approves (2 of 2)."""
    from support.close_world import actor_with_role
    from support.reference import approve

    app = world.app
    elena = actor_with_role(app, clock, world.tenant_id, "controller", name="elena")
    state = period_state(world, entity_code, period_key)
    world = verified(world, clock, "priya")
    requested = post(
        app,
        f"{PERIODS}/{state['id']}/request-reopen",
        world.priya,
        {"reason_code": "ERROR_CORRECTION", "comment": comment},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    world = verified(world, clock, "marcus")
    first = approve(app, request_id, world.marcus)
    assert (first.status_code, first.json()["status"]) == (200, "PENDING"), first.text
    decided = approve(app, request_id, elena)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert period_state(world, entity_code, period_key)["state"] == "reopened"
    return world


@dataclass(frozen=True, slots=True)
class K07World:
    """``NS-SO-DE-5003`` in AVM-DE (PRD WLD-K-07) at one of its stages: delivered; with Aug 2026
    locked (``august_run``); with the late invoice committed (``late_invoice``)."""

    report: ReportWorld  # ``entity_id`` is AVM-DE
    contract_id: UUID
    group_id: UUID
    august_run: Mapping[str, Any] | None = None  # API-S-JournalRun of the Aug 2026 close
    late_invoice: Mapping[str, Any] | None = None  # API-S-Import, with ``approval_request_no``

    @property
    def app(self) -> FastAPI:
        return self.report.app


def k07_delivered(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> K07World:
    """PRD WLD-K-07 through the product's commands. Maya, Priya and Marcus as in
    ``k03_castellan``; USD and EUR enabled; AVM-DE (EUR, Europe/Berlin) on a January calendar
    with FY2026-P01 to P09 open; customer C-07; AVM-FLEET (TPL-PROD-PIT; observable 100,000.00
    EUR) and AVM-EXP-CREDIT (TPL-OPTION; 12,000.00 EUR, the option's standalone selling price)
    under DE-LIST 2026; AVM-MAP-2026-01 over ``K11_CHART``; ``billing.posting`` stays ``ERP``
    (PRD §2.5). ``NS-SO-DE-5003`` books O1 for 100,000.00 EUR and the option O2 at no price, is
    activated, takes the delivery of O1 on 14 Aug 2026 and is computed: allocation 89,285.71 /
    10,714.29 (WLD-X-17). No invoice is recorded (WLD-K-07). [J] The option's terms (40% off one
    further order by 13 Oct 2026; redemption 80%) are T-CON-14 facts no command stores before
    CTR-14; the booking carries what allocates it, its standalone selling price."""
    from erev_api.db.tables import obligation_version
    from erev_api.events.payloads import DeliveryRecordedV1
    from support.factories import K11_CHART

    maya, priya, marcus = _analysis_people(app, keyring, clock)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "EUR"]})
    assert enabled.status_code == 200, enabled.text
    _, entity_id = world_calendar(
        app, maya, entity_code=AVM_DE, functional_currency="EUR", time_zone="Europe/Berlin"
    )
    buyer = customer_id(app, maya, code="C-07", name="Fenwright Logistik AG (Demo)")
    products = {
        FLEET: product_with_template(
            app, maya, code=FLEET, name="Gateway fleet package", revenue_category="PRODUCT"
        ),
        EXPANSION_CREDIT: product_with_template(
            app,
            maya,
            code=EXPANSION_CREDIT,
            name="Expansion credit (customer option)",
            revenue_category="MATERIAL_RIGHT",
        ),
    }
    for code, template, outputs, price in (
        (FLEET, "TPL-PROD-PIT", TPL_PROD_PIT, "100000.00"),
        (EXPANSION_CREDIT, "TPL-OPTION", TPL_OPTION, "12000.00"),
    ):
        published = published_template(
            app,
            maya,
            marcus,
            code=template,
            outputs=outputs,
            case_line={
                "obligation_key": "POB-01",
                "product_code": code,
                "quantity": "1",
                "total_price": price,
            },
        )
        set_default_template(app, maya, products[code], published["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="DE-LIST", currency="EUR"),
        label="2026",
        effective_from="2026-01-01",
        entries=[
            point_entry(FLEET, "100000.00", currency="EUR"),
            point_entry(EXPANSION_CREDIT, "12000.00", currency="EUR"),
        ],
    )
    published_mapping(app, maya, marcus, chart=K11_CHART)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": K07,
            "customer_id": str(buyer),
            "contracting_entity_code": AVM_DE,
            "transaction_currency": "EUR",
            "inception_date": "2026-08-14",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": FLEET,
                    "quantity": "1",
                    "total_price": {"amount": "100000.00", "currency": "EUR"},
                },
                {
                    "obligation_key": "O2",
                    "product_code": EXPANSION_CREDIT,
                    "quantity": "1",
                    "total_price": {"amount": "0.00", "currency": "EUR"},
                },
            ],
        },
        activate=True,
    )
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    appended(
        place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.DELIVERY_RECORDED,
                effective_date=date(2026, 8, 14),
                payload=DeliveryRecordedV1(obligation_key="O1", quantity="1", trigger="DELIVERY"),
            )
        ],
    )
    computed(place, group_id)
    lines = select(obligation_version.c.obligation_key, obligation_version.c.allocated_amount)
    allocated = {
        str(row["obligation_key"]): Decimal(row["allocated_amount"])
        for row in place.rows(lines.where(obligation_version.c.combination_group_id == group_id))
    }
    # WLD-X-17: 100,000 × 100,000 ÷ 112,000 with the largest remainder
    assert allocated == {"O1": Decimal("89285.71"), "O2": Decimal("10714.29")}
    report = ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=entity_id,
        contracts=MappingProxyType({K07: booked}),
    )
    return K07World(report=report, contract_id=contract_id, group_id=group_id)


def k07_august_locked(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> K07World:
    """``k07_delivered`` with Aug 2026 of AVM-DE locked through the product (``period_locked``)
    on the record-time clock: the PRD J-04 precondition "K-07 delivered with no invoice; Aug 2026
    locked"."""
    world = k07_delivered(app, keyring, clock, files)
    report = on_record_clock(world.report, clock)
    run, report = period_locked(report, clock, entity_code=AVM_DE, period_key=AUGUST_2026)
    return dataclasses.replace(world, report=report, august_run=MappingProxyType(run))


def k07_late_invoice(world: K07World, clock: FrozenClock) -> K07World:
    """PRD J-04.2 and J-04.3 for K-07: Maya uploads ``avm-de-invoices-2026-09.csv`` with the
    template ``invoices`` — INV-DE-4390, 100,000.00 EUR, dated 2026-08-31 — and submits it; Priya
    approves it and the commit job appends the ``BILLING_RECORDED``. [J] The file holds the K-07
    row of WLD-F-22 only (K-11 is not in this world), with the members the PRD states: no due
    date, no tax line, no obligation."""
    import csv
    import io
    from datetime import timedelta

    from support.factories import ImportWorld, run_import_job
    from support.legacy_replay import diffed, job_of, shown, submit
    from support.reference import APPROVALS, approve

    report = world.report
    clock.advance(timedelta(minutes=5))
    imports = ImportWorld(app=report.app, actor=report.maya, runtime=report.runtime, clock=clock)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(INVOICE_COLUMNS)
    writer.writerow(
        (K07, "INVOICE", LATE_INVOICE, "2026-08-31", "1", FLEET, "1", "100000.00", "EUR")
    )
    import_id = diffed(imports, LATE_INVOICE_FILE, buffer.getvalue().encode("utf-8"), "invoices")
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    report = verified(report, clock, "priya")
    decided = approve(report.app, request_id, report.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == "COMMITTED", done
    request = get(report.app, f"{APPROVALS}/{request_id}", report.maya)
    assert request.status_code == 200, request.text
    late_invoice = {**done, "approval_request_no": str(request.json()["request_no"])}
    return dataclasses.replace(world, report=report, late_invoice=MappingProxyType(late_invoice))


def k07_fenwright(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> K07World:
    """BUILD_SPEC RPS-8: WLD-K-07 with Aug 2026 locked and the late invoice INV-DE-4390 —
    ``k07_august_locked``, then ``k07_late_invoice`` (PRD J-04.2, J-04.3; WLD-X-18)."""
    return k07_late_invoice(k07_august_locked(app, keyring, clock, files), clock)


# --- a late event that reaches a contract through an import (supervisor ruling R-63 (c)) ----------

JANUARY_2026: Final = "FY2026-P01"
LATE_PROGRESS_FILE: Final = "avm-us-progress-2026-02.csv"
# The ``progress_events`` members a PROGRESS_RECORDED row states; a blank cell is absent (DIN-9).
PROGRESS_COLUMNS: Final = (
    "contract",
    "event_type",
    "effective_date",
    "obligation_key",
    "cumulative_progress_ratio",
    "measure",
)


def committed_import(
    report: ReportWorld,
    clock: FrozenClock,
    *,
    name: str,
    template: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> tuple[ReportWorld, dict[str, Any]]:
    """PRD J-04.2 and J-04.3 through the product: Maya uploads the CSV v2 file ``name`` of
    ``template`` and submits it; Priya (``import.approve``, fresh TOTP) approves it and the commit
    job appends its events as the SYSTEM principal. Returns the world with Priya's verified
    session and API-S-Import of the committed upload with ``approval_request_no`` added. An import
    commit starts no computation (05 IPL-11 is not built): the group waits for the next command."""
    import csv
    import io
    from datetime import timedelta

    from support.factories import ImportWorld, run_import_job
    from support.legacy_replay import diffed, job_of, shown, submit
    from support.reference import APPROVALS, approve

    clock.advance(timedelta(minutes=5))
    imports = ImportWorld(app=report.app, actor=report.maya, runtime=report.runtime, clock=clock)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    import_id = diffed(imports, name, buffer.getvalue().encode("utf-8"), template)
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    report = verified(report, clock, "priya")
    decided = approve(report.app, request_id, report.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == "COMMITTED", done
    request = get(report.app, f"{APPROVALS}/{request_id}", report.maya)
    assert request.status_code == 200, request.text
    return report, {**done, "approval_request_no": str(request.json()["request_no"])}


def k01_late_progress(
    world: ReportWorld, clock: FrozenClock
) -> tuple[ReportWorld, dict[str, Any], dict[str, Any]]:
    """K-01 with a locked January 2026: the O2 progress of 40% at 31 Jan 2026 (PRD WLD-K-01)
    arrives late through the ``progress_events`` import, and Maya's note of 10 Feb 2026 is the
    next command on the contract, whose computation posts the late revenue — 16,200.00 × 0.40 =
    6,480.00 — in the first open period with origin FY2026-P01. Returns the world, the committed
    upload (``committed_import``) and the response of the note's append."""
    world, upload = committed_import(
        world,
        clock,
        name=LATE_PROGRESS_FILE,
        template="progress_events",
        columns=PROGRESS_COLUMNS,
        rows=[(K01, "PROGRESS_RECORDED", "2026-01-31", "O2", "0.40", "OUTPUT_PERCENT")],
    )
    noted = _appended_through_api(
        world.place,
        UUID(str(world.contracts[K01].contract["id"])),
        {
            "event_type": "MEMO_UPDATED",
            "effective_date": "2026-02-10",
            "payload": {"memo_1": "January progress confirmed by the project lead"},
        },
    )
    return world, upload, noted


# --- a deposit transferred when the criteria are met (RPT-ROLLFWD-KINDS-1; ruling R-72) -----------

K09_RECEIPT: Final = "RCPT-US-4410"


def k09_deposit_transfer(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """WLD-K-09 ``SF-ORD-10417`` as an arrangement that is not a contract at first (PRD SM-02 rev
    1.34; POLICIES JET-01b; ENGINE_SPEC S02-R-04, S02-R-08), through the product's commands:
    ``support.factories.seat_world`` over ``STEP1_CHART`` (receipts post to the deposit
    liability). Maya books the contract; a reviewed ``NOT_A_CONTRACT`` record and the
    not-probable assessment of 01 Sep 2026 bring it to ``NOT_A_CONTRACT``; 36,000.00 is received
    on 05 Sep 2026; a reviewed ``COLLECTIBILITY`` record and the probable re-assessment of 10 Sep
    2026 precede the criteria-met activation, which Maya submits and Priya (Revenue Reviewer)
    approves. The approval appends ``CONTRACT_CRITERIA_MET`` and ``CONTRACT_ACTIVATED``, and its
    computation posts, in FY2026-P09: the receipt (Dr clearing / Cr deposit liability 36,000.00),
    the transfer (Dr deposit liability / Cr contract liability 36,000.00) and the revenue of
    September with its catch-up, 2,956.20 = 108,000.00 × 30 / 1,096."""
    from datetime import timedelta

    from support.factories import STEP1_CHART, k09_body, seat_world
    from support.reference import approve

    seats = seat_world(app, keyring, clock, files, chart=STEP1_CHART)
    assign(seats.priya.member, "revenue_reviewer")  # PRD §2.5: activations are hers to approve
    maya = seats.place.author
    drafted = post(app, "/api/v1/contracts", maya, k09_body(seats.customers["C-09"]))
    assert drafted.status_code == 201, drafted.text
    contract_id = UUID(str(drafted.json()["id"]))

    def reviewed(topic: str, questionnaire: Mapping[str, Any] | None = None) -> str:
        body: dict[str, Any] = {
            "topic": topic,
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "book": "ASC606",
            "conclusion": f"{topic} assessed for {K09}.",
            "rationale": "Credit review of Orrin Vale Architects LLP and the contract terms.",
            # the five criteria of a Step 1 review (04 T-CON-19 rev 1.150; supervisor rulings
            # R-113 (f), R-115 (f)), as the story has them: (a) to (d) met throughout; (e),
            # collectibility, not met on 01 Sep 2026 and met at the re-assessment of 10 Sep 2026
            "questionnaire": {"criteria": step1_criteria(topic), **(questionnaire or {})},
        }
        record = judgement_submitted(app, maya, body)
        decided = approve(app, str(record["approval_request_id"]), seats.marcus)
        assert decided.status_code == 200, decided.text
        return str(record["id"])

    def assessed(record_id: str, *, probable: bool, day: str) -> dict[str, Any]:
        return {
            "event_type": "COLLECTIBILITY_ASSESSED",
            "effective_date": day,
            "payload": {
                "book": "ASC606",
                "is_probable": probable,
                "judgement_record_id": record_id,
            },
        }

    refused = reviewed("NOT_A_CONTRACT", {"consideration_nonrefundable": False})
    gated = _appended_through_api(
        seats.place, contract_id, assessed(refused, probable=False, day="2026-09-01")
    )
    assert gated["contract"]["status"] == "NOT_A_CONTRACT", gated["contract"]
    _appended_through_api(
        seats.place,
        contract_id,
        {
            "event_type": "PAYMENT_RECEIVED",
            "effective_date": "2026-09-05",
            "payload": {
                "receipt_reference": K09_RECEIPT,
                "amount": {"amount": "36000.00", "currency": "USD"},
                "receipt_date": "2026-09-05",
            },
        },
    )
    # Time passes: the criteria-met record is reviewed AFTER the gate was written (supervisor
    # rulings R-77 (3), R-102 (a)), and the clock of this world stands still unless moved.
    clock.advance(timedelta(minutes=1))
    met = reviewed("COLLECTIBILITY")
    _appended_through_api(seats.place, contract_id, assessed(met, probable=True, day="2026-09-10"))
    head = seats.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    submitted = post(
        app,
        f"/api/v1/contracts/{contract_id}/submit-activation",
        maya,
        {"comment": "Collection is now probable."},
        if_match=f'"s{int(head)}"',
    )
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.headers["x-erev-approval-request"], seats.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    shown = get(app, f"/api/v1/contracts/{contract_id}", maya)
    assert (shown.status_code, shown.json()["status"]) == (200, "ACTIVE"), shown.text
    return ReportWorld(
        place=seats.place,
        priya=seats.priya,
        marcus=seats.marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=seats.entity_id,
        contracts=MappingProxyType({}),
    )

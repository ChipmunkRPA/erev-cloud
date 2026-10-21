"""Authorized book-policy counterfactuals, executed outside SQL transactions.

Original engine outputs and both report endpoints must reproduce before attribution.
Each phase replaces one family of ASC606 resolved policies with IFRS15 policies;
interactions belong to the later phase. Unreproduced framework behavior stays OTHER.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import BalanceOut, InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s01_canonicalize.convert import contract_key_from_subject
from sqlalchemy import select

from erev_api.db.tables import contract_version
from erev_api.domain.reports import computation_sources, tie_outs
from erev_api.domain.reports.builders import ReportParams, SourceCollector
from erev_api.domain.reports.builders import book_bridge as bridge
from erev_api.domain.reports.builders.contract_balance_rollforward import ranges
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

EVIDENCE = "book_bridge_policy_replay_v1"
type Metrics = dict[tuple[str, str], Decimal]
type Engine = Callable[[InputBundle], OutputBundle]


@dataclass(frozen=True)
class Prepared:
    collector: SourceCollector
    sources: tuple[computation_sources.VerifiedComputation, ...]
    entity_code: str
    entity_id: UUID
    period_keys: tuple[str, ...]
    tenant_id: UUID
    entity_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class Calculated:
    prepared: Prepared
    retained: Mapping[str, Any]
    executions: tuple[Mapping[str, Any], ...]


def reader(uow: UnitOfWork, params: ReportParams) -> UnitOfWork:
    return (
        uow
        if params.requester is None
        else UnitOfWork(
            ctx=params.requester,
            session=uow.session,
            clock=uow.clock,
            keyring=uow.keyring,
            files=uow.files,
        )
    )


def prepare(uow: UnitOfWork, params: ReportParams) -> Prepared:
    collector = SourceCollector()
    bridge.build(uow, replace(params, sources=collector, execution_result=None))
    entities, periods, _ = ranges(uow.session, params)
    entity = entities[0]
    versions = set().union(*collector.versions.values()) if collector.versions else set()
    latest: dict[tuple[UUID, str], UUID] = {}
    for group, book_code, computation in uow.session.execute(
        select(
            contract_version.c.combination_group_id,
            contract_version.c.book_code,
            contract_version.c.contract_computation_id,
        )
        .where(contract_version.c.id.in_(versions))
        .order_by(contract_version.c.version_no.desc())
    ):
        latest.setdefault((group, str(book_code)), computation)
    groups: dict[UUID, set[UUID]] = {}
    for (group, _), computation in latest.items():
        groups.setdefault(group, set()).add(computation)
    sources = []
    authorized = reader(uow, params)
    unavailable: list[str] = []
    for ids in groups.values():
        if len(ids) != 1:
            continue  # no common original computation for both book endpoints
        try:
            sources.append(computation_sources.read_for_report(authorized, next(iter(ids))))
        except Problem as error:
            if error.slug not in {"forbidden", "not-found", "validation-failed"}:
                raise
            unavailable.append(
                error.slug + ":" + ",".join(item.rule_id or "" for item in error.errors)
            )
            # Ordinary report scope can be narrower than complete-group replay scope.
            # No source metadata or money outside that scope is exposed.
    collector.record_evidence(
        "book_bridge_replay_selection_v1",
        {
            "version_count": len(versions),
            "group_count": len(groups),
            "selected_count": len(sources),
            "unavailable": unavailable,
        },
    )
    return Prepared(
        collector,
        tuple(sources),
        entity.code,
        entity.id,
        tuple(item.key for item in periods[entity.id]),
        uow.principal.tenant_id,
        params.entity_ids,
    )


def policy_driver(code: str) -> str:
    if code in {"step1.collectibility_threshold", "step1.event_c_enabled"}:
        return bridge.COLLECTIBILITY
    if code == "costs.impairment_reversal":
        return bridge.COST_IMPAIRMENT_REVERSAL
    if code == "licence.renewal_start":
        return "LICENCE_RENEWALS"
    if code.startswith("loss."):
        return bridge.ONEROUS_CONTRACTS
    if code in {"fx.cl_layer_date", "fx.cl_layer_consumption", "fx.cl_historical_layering"}:
        return "ADVANCE_CONSIDERATION_FX"
    return "FRAMEWORK_ELECTIONS"


def project(
    prepared: Prepared, basis: InputBundle, output: OutputBundle, book_code: str
) -> Metrics:
    retained = prepared.collector.evidence[bridge.EVIDENCE]
    view = retained["currency_view"]
    functional = view != "transaction"
    entity = next(item for item in basis.entities if item.code == prepared.entity_code)
    book = next(item for item in output.books if item.book_code == book_code)
    contracts = {c.external_id: c for c in basis.contracts}
    subjects = {contract_entity_subject_key(key, entity.code): key for key in contracts}
    amounts: Metrics = {}

    def convert(name: str, value: int, *, period_key: str, revenue: bool) -> Decimal:
        currency = (
            entity.functional_currency if functional else contracts[name].transaction_currency
        )
        amount = Decimal(value).scaleb(-basis.currencies[currency].minor_unit)
        if view == "reporting":
            key = (
                f"book_bridge_average_rate_v1:{period_key}"
                if revenue
                else "book_bridge_closing_rate_v1"
            )
            rate = prepared.collector.evidence[key]["rates"][str(prepared.entity_id)]["rate"]
            amount = tie_outs.quantized(amount * Decimal(rate), retained["display_currency"])
        return amount

    suffix = "functional" if functional else "txn"
    balances: dict[str, BalanceOut] = {}
    for row in book.balances:
        if row.subject_key not in subjects or row.period_key > prepared.period_keys[-1]:
            continue
        previous = balances.get(row.subject_key)
        if previous is None or row.period_key > previous.period_key:
            balances[row.subject_key] = row
    for subject, row in balances.items():
        name = subjects[subject]
        for measure, column in bridge.BALANCE_OF.items():
            value = row.columns.get(f"{column}_{suffix}")
            if value is None:
                txn = row.columns.get(f"{column}_txn", 0)
                if (
                    functional
                    and contracts[name].transaction_currency != entity.functional_currency
                    and txn
                ):
                    raise ValueError("No functional projection for nonzero balance")
                value = txn
            if type(value) is not int:
                raise ValueError("Non-integer engine money")
            amounts[(name, measure)] = convert(
                name, value, period_key=row.period_key, revenue=False
            )
    revenues: dict[tuple[str, str], int] = {}

    def revenue(subject: str, period_key: str, value: int) -> None:
        name = contract_key_from_subject(subject)
        if name not in contracts or type(value) is not int:
            raise ValueError("Invalid revenue source")
        key = (name, period_key)
        revenues[key] = revenues.get(key, 0) + value

    for line in basis.posted:
        if (
            line.book_code == book_code
            and line.entity_code == entity.code
            and line.period_key in prepared.period_keys
            and line.account_role == "REVENUE"
        ):
            revenue(
                line.subject_key,
                line.period_key,
                -(line.amount_functional if functional else line.amount_txn),
            )
    for intent in book.posting_intents:
        if intent.entity != entity.code or intent.posting_period_key not in prepared.period_keys:
            continue
        for intent_line in intent.lines:
            if intent_line.account_role == "REVENUE":
                value = intent_line.amount_functional if functional else intent_line.amount_txn
                revenue(
                    intent.subject_key,
                    intent.posting_period_key,
                    value if intent_line.side == "C" else -value,
                )
    for (name, period_key), value in revenues.items():
        key = (name, bridge.REVENUE)
        amounts[key] = amounts.get(key, Decimal(0)) + convert(
            name, value, period_key=period_key, revenue=True
        )
    return amounts


def collectibility_basis(basis: InputBundle) -> tuple[InputBundle, tuple[str, ...]]:
    """Exchange book-specific Step 1 facts in memory; original events remain immutable."""
    swapped = {bridge.ASC606: bridge.IFRS15, bridge.IFRS15: bridge.ASC606}
    events = []
    changed = []
    for event in basis.events:
        if (
            event.event_type in {"COLLECTIBILITY_ASSESSED", "CONTRACT_CRITERIA_MET"}
            and event.payload.get("book") in swapped
        ):
            payload = {**event.payload, "book": swapped[str(event.payload["book"])]}
            events.append(replace(event, payload=payload, payload_sha256=sha256_hex(payload)))
            changed.append(event.event_key)
        else:
            events.append(event)
    contracts = tuple(
        replace(
            contract,
            judgements=tuple(
                replace(judgement, book_code=swapped[judgement.book_code])
                if judgement.topic in {"COLLECTIBILITY", "NOT_A_CONTRACT"}
                and judgement.book_code in swapped
                else judgement
                for judgement in contract.judgements
            ),
        )
        for contract in basis.contracts
    )
    return replace(basis, events=tuple(events), contracts=contracts), tuple(changed)


def calculate(prepared: Prepared, *, engine: Engine) -> Calculated:
    retained = copy.deepcopy(prepared.collector.evidence[bridge.EVIDENCE])
    records = {row["contract_external_id"]: row for row in retained["sources"]}
    executions: list[Mapping[str, Any]] = []
    for source in prepared.sources:
        basis = source.bundle
        names = {c.external_id for c in basis.contracts} & records.keys()
        if not names or basis.engine_version != ENGINE_VERSION or not prepared.period_keys:
            continue
        original = engine(basis)
        if original.input_sha256 != basis.sha256() or original.sha256() != source.output_sha256:
            continue
        books = {b.book_code: b for b in basis.books}
        if not set(bridge.BOOKS) <= books.keys():
            continue
        try:
            endpoints = {code: project(prepared, basis, original, code) for code in bridge.BOOKS}
        except (ValueError, StopIteration):
            continue
        if any(
            endpoints[code].get((name, measure), Decimal(0))
            != Decimal(records[name][field].get(measure, "0"))
            for code, field in ((bridge.ASC606, "asc606"), (bridge.IFRS15, "ifrs15"))
            for name in names
            for measure in bridge.MEASURES
        ):
            continue
        current, previous = basis, endpoints[bridge.ASC606]
        effects: dict[str, dict[str, dict[str, str]]] = {
            name: {measure: {} for measure in bridge.MEASURES} for name in names
        }
        steps: list[dict[str, Any]] = []
        for driver in bridge.DRIVERS[:-1]:
            asc = next(b for b in current.books if b.book_code == bridge.ASC606)
            target = books[bridge.IFRS15]
            old = {
                (p.code, p.scope, p.subject_key): p
                for p in asc.policies
                if policy_driver(p.code) == driver
            }
            new = {
                (p.code, p.scope, p.subject_key): p
                for p in target.policies
                if policy_driver(p.code) == driver
            }
            phase_basis, event_keys = (
                collectibility_basis(current) if driver == bridge.COLLECTIBILITY else (current, ())
            )
            if {k: p.value for k, p in old.items()} == {
                k: p.value for k, p in new.items()
            } and phase_basis == current:
                continue
            policies = tuple(
                sorted(
                    [p for p in asc.policies if policy_driver(p.code) != driver]
                    + list(new.values()),
                    key=lambda p: (p.code, p.scope, p.subject_key),
                )
            )
            current = replace(
                phase_basis,
                trigger="DRY_RUN",
                books=tuple(
                    replace(b, policies=policies) if b.book_code == bridge.ASC606 else b
                    for b in current.books
                ),
            )
            try:
                computed = engine(current)
                after = project(prepared, current, computed, bridge.ASC606)
            except (EngineError, ValueError) as error:
                steps.append(
                    {
                        "driver": driver,
                        "status": "UNAVAILABLE",
                        "reason": error.code
                        if isinstance(error, EngineError)
                        else "PROJECTION_UNAVAILABLE",
                    }
                )
                break  # retain prior proven effects; the entire remainder belongs to OTHER

            for name in names:
                for measure in bridge.MEASURES:
                    key = (name, measure)
                    effects[name][measure][driver] = str(
                        previous.get(key, Decimal(0)) - after.get(key, Decimal(0))
                    )
            steps.append(
                {
                    "driver": driver,
                    "event_keys": list(event_keys),
                    "input_sha256": current.sha256(),
                    "output_sha256": computed.sha256(),
                    "policy_codes": sorted({p.code for p in (*old.values(), *new.values())}),
                }
            )
            previous = after
        for name in names:
            for measure in bridge.MEASURES:
                key = (name, measure)
                effects[name][measure][bridge.OTHER] = str(
                    previous.get(key, Decimal(0)) - endpoints[bridge.IFRS15].get(key, Decimal(0))
                )
            records[name]["driver_effects"] = effects[name]
        executions.append(
            {
                "computation_id": str(source.computation_id),
                "input_sha256": basis.sha256(),
                "output_sha256": source.output_sha256,
                "steps": steps,
            }
        )
    return Calculated(prepared, retained, tuple(executions))


def consume(uow: UnitOfWork, params: ReportParams, result: Calculated) -> Mapping[str, Any]:
    prepared = result.prepared
    if prepared.tenant_id != uow.principal.tenant_id or prepared.entity_ids != params.entity_ids:
        raise Problem("forbidden")
    authorized = reader(uow, params)
    for source in prepared.sources:
        computation_sources.read_for_report(authorized, source.computation_id)
    collector = params.sources
    if collector is not None:
        frozen = prepared.collector
        collector.cutoff = frozen.cutoff
        collector.versions.update(frozen.versions)
        collector.labels.update(frozen.labels)
        collector.members.update(frozen.members)
        collector.evidence.update(frozen.evidence)
        collector.record_evidence(bridge.EVIDENCE, result.retained)
        collector.record_evidence(EVIDENCE, list(result.executions))
    return result.retained

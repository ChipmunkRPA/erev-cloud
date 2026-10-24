"""Authorized worker preparation and retained presentation of modification causal analysis."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date
from fractions import Fraction
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_event,
    contract_version,
    modification,
    obligation_version,
)
from erev_api.domain.migration.reconciliation import exact_decimal_text
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.stages.s01_canonicalize import contract_subject_key

from . import computation_sources, modification_causal, reporting_currency, tie_outs
from .book_bridge_replay import reader
from .builders import ReportParams, SourceCollector
from .builders import modification_register as register
from .outputs import Column, ReportData
from .variance_replay import Engine
from .variance_reporting import Basis

EVIDENCE = "modification_causal_report_v1"
BASIS = "causal_analysis"
LABEL = "Causal analysis: sequential event differences; not original journal allocation"


def selection(params: ReportParams) -> dict[str, Any]:
    return {
        key: params.parameters.get(key)
        for key in (
            "book",
            "from_date",
            "to_date",
            "status",
            "contract_external_id",
            "currency_view",
            "currency_basis",
        )
    }


@dataclass(frozen=True)
class Task:
    source: computation_sources.VerifiedComputation
    entity_code: str
    period_key: str
    event_keys: tuple[str, ...]
    reporting: Basis | None


@dataclass(frozen=True)
class Prepared:
    collector: SourceCollector
    tasks: tuple[Task, ...]
    identity: Mapping[str, Any]
    modifications: Mapping[str, Mapping[str, str]]
    unavailable: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class Calculated:
    prepared: Prepared
    evidence: Mapping[str, Any]


def prepare(uow: UnitOfWork, params: ReportParams) -> Prepared:
    collector = SourceCollector()
    # The register resolves its exact application versions and event identities once.
    register.build(
        uow,
        replace(
            params,
            sources=collector,
            execution_result=None,
            parameters={
                **params.parameters,
                "currency_basis": "source",
                "currency_view": "transaction",
            },
        ),
    )
    original = collector.evidence[register.EVIDENCE]
    records = original["sources"]
    applications = collector.evidence.get("modification_application_versions_v1", {})
    versions = {}
    if applications:
        for row in uow.session.execute(
            select(
                contract_version.c.id,
                contract_version.c.combination_group_id,
                contract_version.c.contract_computation_id,
                contract_version.c.version_no,
            ).where(contract_version.c.id.in_([UUID(v["id"]) for v in applications.values()]))
        ).mappings():
            versions[str(row["id"])] = row
    latest: dict[UUID, Any] = {}
    for row in versions.values():
        group = row["combination_group_id"]
        if group not in latest or row["version_no"] > latest[group]["version_no"]:
            latest[group] = row
    event_keys = {}
    ids = [UUID(r["modification_id"]) for r in records if r.get("modification_id")]
    if ids:
        for identity, external, sequence in uow.session.execute(
            select(modification.c.id, contract.c.external_id, contract_event.c.stream_version)
            .join(contract_event, contract_event.c.id == modification.c.applied_event_id)
            .join(contract, contract.c.id == contract_event.c.contract_id)
            .where(modification.c.id.in_(ids))
        ):
            event_keys[str(identity)] = f"{contract_subject_key(str(external))}/EV-{sequence:06d}"
    entities = tie_outs.entities(uow.session, params.entity_ids, params=params)
    by_code = {e.code: e for e in entities}
    calendars = tie_outs.calendars(uow.session, entities, params=params)
    selected: dict[tuple[UUID, str, str], list[str]] = {}
    modifications = {}
    unavailable = []
    for record in records:
        identity = record.get("modification_id")
        version = applications.get(identity)
        if record["status"] != "APPLIED":
            unavailable.append(
                {
                    "modification_no": record["modification_no"],
                    "contract_external_id": record["contract_external_id"],
                    "reason": "Not applied; no original event to replay",
                }
            )
            continue
        if version is None or identity not in event_keys:
            raise Problem(
                "validation-failed", "Applied modification lacks retained computation evidence."
            )
        entity = by_code[record["entity_code"]]

        period = calendars[entity.id].holding(date.fromisoformat(record["effective_date"]))
        if period is None:
            raise Problem("validation-failed", "Modification date has no fiscal period.")
        group = UUID(version["combination_group_id"])
        key = event_keys[identity]
        selected.setdefault((group, entity.code, period.key), []).append(key)
        modifications[key] = {
            k: record[k]
            for k in (
                "modification_id",
                "modification_no",
                "contract_id",
                "contract_external_id",
                "effective_date",
            )
        }
        for field in ("proposed_treatments", "chosen_treatments"):
            treatments = record.get(field)
            modifications[key][field] = (
                canonical_bytes(treatments).decode("utf-8") if treatments else None
            )
        assessment = record["questionnaire"].get("combined_reassessment")
        if assessment:
            modifications[key]["combined_reassessment"] = canonical_bytes(assessment).decode(
                "utf-8"
            )
    sources = {}
    tasks = []
    for (group, entity_code, period_key), keys in sorted(selected.items(), key=lambda x: str(x[0])):
        if group not in sources:
            sources[group] = computation_sources.read_for_report(
                reader(uow, params), latest[group]["contract_computation_id"]
            )
        source = sources[group]
        if not {e.code for e in source.bundle.entities} <= by_code.keys():
            raise Problem(
                "validation-failed",
                "Select all entities in the retained computation group for causal analysis.",
            )
        entity = by_code[entity_code]
        selected_period = calendars[entity.id].named(period_key, "currency_view")
        original_periods = [
            period
            for original_entity in source.bundle.entities
            if original_entity.code == entity_code
            for period in original_entity.periods
            if period.period_key == period_key
        ]
        if len(original_periods) != 1 or (
            original_periods[0].start_date,
            original_periods[0].end_date,
        ) != (selected_period.start, selected_period.end):
            raise Problem(
                "validation-failed", "Original and selected fiscal period boundaries differ."
            )
        reporting = None
        if params.parameters.get("currency_view") == "reporting":
            period = calendars[entity.id].named(period_key, "currency_view")
            rates = {}
            for kind in ("average",):
                rates[kind] = reporting_currency.rates_for_period(
                    uow.session,
                    replace(params, sources=collector),
                    tenant_id=uow.principal.tenant_id,
                    entities=(entity,),
                    periods={entity.id: period},
                    rate_type=kind,
                    evidence_key=f"modification_causal_rate_v1:{entity.id}:{period.key}:{kind}",
                )
            reporting = Basis(
                entity.functional_currency,
                rates["average"].currency,
                period.key,
                period.end,
                # Only revenue is projected; the closing slot is unused.
                Fraction(str(rates["average"].rates[entity.id]["rate"])),
                Fraction(str(rates["average"].rates[entity.id]["rate"])),
                sha256_hex(
                    {
                        k: {
                            "currency": v.currency,
                            "rates": {str(i): fact for i, fact in v.rates.items()},
                        }
                        for k, v in rates.items()
                    }
                ),
            )
        tasks.append(Task(source, entity_code, period_key, tuple(keys), reporting))
    identity = {
        "tenant_id": str(uow.principal.tenant_id),
        "entity_ids": sorted(str(e) for e in params.entity_ids),
        "selection": selection(params),
        "book": original["book"],
        "modification_context_columns": True,
        "modification_treatment_maps": True,
        "currency_view": params.parameters.get("currency_view") or "transaction",
    }
    return Prepared(collector, tuple(tasks), identity, modifications, tuple(unavailable))


def calculate(prepared: Prepared, *, engine: Engine) -> Calculated:
    analyses = []
    # Identical original/prefix inputs across period projections execute only once.
    cache: dict[str, OutputBundle] = {}

    def cached(bundle: InputBundle) -> OutputBundle:
        key = bundle.sha256()
        if key not in cache:
            cache[key] = engine(bundle)
        return cache[key]

    for task in prepared.tasks:
        analysis = modification_causal.calculate(
            task.source.bundle,
            source_output_sha256=task.source.output_sha256,
            selected_event_keys=task.event_keys,
            entity_code=task.entity_code,
            book_code=prepared.identity["book"],
            period_key=task.period_key,
            currency_view=cast(Any, prepared.identity["currency_view"]),
            reporting_basis=task.reporting,
            engine=cached,
        )
        metrics = []
        for key, result in analysis.replay.measures.items():
            metrics.append(
                {
                    "contract_external_id": key.contract_external_id,
                    "currency": key.currency,
                    "baseline": exact_decimal_text(result.metric_before),
                    "final": exact_decimal_text(result.metric_after),
                    "effects": [
                        {
                            "event_key": e.event_keys[0],
                            "driver": e.driver,
                            "amount": exact_decimal_text(e.amount),
                        }
                        for e in result.effects
                    ],
                }
            )
        analyses.append(
            {
                "computation_id": str(task.source.computation_id),
                "group_id": str(task.source.group_id),
                "entity_code": task.entity_code,
                "period_key": task.period_key,
                "selected_event_keys": list(task.event_keys),
                "source_input_sha256": analysis.source_input_sha256,
                "source_output_sha256": analysis.source_output_sha256,
                "executions": [asdict(e) for e in analysis.replay.executions],
                "reporting_basis": None
                if task.reporting is None
                else {
                    "currency": task.reporting.currency,
                    "average": str(task.reporting.average),
                    "evidence_sha256": task.reporting.evidence_sha256,
                },
                "metrics": metrics,
            }
        )
    evidence = json.loads(
        canonical_bytes(
            {
                **prepared.identity,
                "analyses": analyses,
                "modifications": prepared.modifications,
                "unavailable": prepared.unavailable,
            }
        )
    )
    return Calculated(prepared, evidence)


def consume(uow: UnitOfWork, params: ReportParams, result: Calculated) -> Mapping[str, Any]:
    validate(params, result.evidence, str(uow.principal.tenant_id))
    for source in {t.source.computation_id: t.source for t in result.prepared.tasks}.values():
        computation_sources.read_for_report(reader(uow, params), source.computation_id)
    if params.sources is not None:
        frozen, target = result.prepared.collector, params.sources
        target.cutoff = frozen.cutoff
        target.versions.update(frozen.versions)
        target.labels.update(frozen.labels)
        target.members.update(frozen.members)
        target.evidence.update(frozen.evidence)
        target.record_evidence(EVIDENCE, result.evidence)
    return result.evidence


def validate(
    params: ReportParams, evidence: Mapping[str, Any], tenant_id: str | None = None
) -> None:
    if evidence["entity_ids"] != sorted(str(e) for e in params.entity_ids) or (
        tenant_id is not None and evidence["tenant_id"] != tenant_id
    ):
        raise Problem("forbidden")
    if evidence["selection"] != selection(params):
        raise Problem(
            "validation-failed", "Saved causal analysis uses another parameter selection."
        )


def dataset(evidence: Mapping[str, Any]) -> ReportData:
    rows = []
    for analysis in evidence["analyses"]:
        for metric in analysis["metrics"]:
            prefix = sha256_hex(
                [
                    analysis["computation_id"],
                    analysis["entity_code"],
                    analysis["period_key"],
                    metric["contract_external_id"],
                    metric["currency"],
                ]
            )
            if Fraction(metric["baseline"]) + sum(
                (Fraction(e["amount"]) for e in metric["effects"]), Fraction(0)
            ) != Fraction(metric["final"]):
                raise Problem("validation-failed", "Saved causal effects do not reconcile.")
            entries = [
                (
                    "baseline",
                    "Fixed-basis baseline, including retained posted history",
                    "",
                    metric["baseline"],
                )
            ]
            for index, effect in enumerate(metric["effects"]):
                selected = effect["event_key"] in analysis["selected_event_keys"]
                entries.append(
                    (
                        str(index),
                        "Selected modification" if selected else "Other event",
                        effect["event_key"],
                        effect["amount"],
                    )
                )
            entries.append(("final", "Final period revenue", "", metric["final"]))
            for suffix, kind, key, amount in entries:
                mod = evidence["modifications"].get(key, {})
                rows.append(
                    {
                        "row_key": f"causal:{prefix}:{suffix}",
                        "contract_external_id": metric["contract_external_id"],
                        "entity_code": analysis["entity_code"],
                        "period_key": analysis["period_key"],
                        "modification_no": mod.get("modification_no"),
                        "event_key": key,
                        "contribution": kind,
                        "basis": LABEL,
                        "currency": metric["currency"],
                        "causal_amount": {"amount": amount, "currency": metric["currency"]},
                    }
                )
    for index, item in enumerate(evidence["unavailable"]):
        rows.append(
            {
                "row_key": f"causal:unavailable:{index}",
                "contract_external_id": item["contract_external_id"],
                "modification_no": item["modification_no"],
                "contribution": item["reason"],
                "basis": LABEL,
                "entity_code": None,
                "period_key": None,
                "event_key": "",
                "currency": None,
                "causal_amount": None,
            }
        )
    context_columns: tuple[Column, ...] = ()
    if evidence.get("modification_context_columns"):
        context_columns = (
            Column("modification_contract", "Modification owner contract", "text"),
            Column("modification_effective_date", "Modification effective date", "date"),
            Column("combined_reassessment", "Combination reassessment (authored JSON)", "text"),
        )
        for row in rows:
            modification = evidence["modifications"].get(row["event_key"], {})
            row["modification_contract"] = modification.get("contract_external_id")
            effective = modification.get("effective_date")
            row["modification_effective_date"] = (
                date.fromisoformat(effective) if effective is not None else None
            )
            row["combined_reassessment"] = modification.get("combined_reassessment")
    if evidence.get("modification_treatment_maps"):
        context_columns += (
            Column(
                "modification_proposed_treatments",
                "Modification proposed treatments (by obligation, JSON)",
                "text",
            ),
            Column(
                "modification_chosen_treatments",
                "Modification chosen treatments (by obligation, JSON)",
                "text",
            ),
        )
        for row in rows:
            modification = evidence["modifications"].get(row["event_key"], {})
            for field in ("proposed_treatments", "chosen_treatments"):
                row[f"modification_{field}"] = modification.get(field)
    return ReportData(
        columns=(
            Column("contract_external_id", "Affected contract", "text"),
            Column("entity_code", "Entity", "code"),
            Column("period_key", "Period", "code"),
            Column("modification_no", "Modification", "code"),
            Column("event_key", "Event", "code"),
            Column("contribution", "Contribution", "text"),
            Column("basis", "Amount basis", "text"),
            Column("currency", "Currency", "code"),
            Column("causal_amount", "Causal analysis amount", "money"),
        )
        + context_columns,
        rows=tuple(rows),
        control_totals={
            "basis": LABEL,
            "period_reconciliations": len(evidence["analyses"]),
            "unavailable_modifications": evidence["unavailable"],
        },
    )


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.binding is not None:
        evidence = tie_outs.bound_evidence(params, EVIDENCE)
        validate(params, evidence, str(uow.principal.tenant_id))
    elif isinstance(params.execution_result, Calculated):
        evidence = consume(uow, params, params.execution_result)
    else:
        raise Problem(
            "validation-failed", "Causal analysis requires the report worker calculation."
        )
    return dataset(evidence)


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[Mapping[str, str], list[dict[str, Any]]]:
    if (
        params.binding is None
        or params.report_code != register.CODE
        or params.report_version != 1
        or params.binding.report_version != 1
        or column_key != "causal_amount"
    ):
        raise Problem("validation-failed", "Choose a saved causal analysis amount.")
    evidence = tie_outs.bound_evidence(params, EVIDENCE)
    validate(params, evidence)
    row = next((r for r in dataset(evidence).rows if r["row_key"] == row_key), None)
    if row is None or row["causal_amount"] is None:
        raise Problem("not-found", "The saved causal analysis has no such row.")
    analysis = next(
        (
            a
            for a in evidence["analyses"]
            if any(
                row_key.startswith(
                    "causal:"
                    + sha256_hex(
                        [
                            a["computation_id"],
                            a["entity_code"],
                            a["period_key"],
                            m["contract_external_id"],
                            m["currency"],
                        ]
                    )
                    + ":"
                )
                for m in a["metrics"]
            )
        ),
        None,
    )
    if analysis is None:
        raise Problem("validation-failed", "The saved computation identity is missing.")
    identity = session.execute(
        select(contract.c.id)
        .join(
            obligation_version,
            (obligation_version.c.contract_id == contract.c.id)
            & (obligation_version.c.tenant_id == contract.c.tenant_id),
        )
        .join(
            contract_version,
            (contract_version.c.id == obligation_version.c.contract_version_id)
            & (contract_version.c.tenant_id == obligation_version.c.tenant_id),
        )
        .where(
            contract.c.external_id == row["contract_external_id"],
            contract_version.c.contract_computation_id == UUID(analysis["computation_id"]),
            contract_version.c.book_code == evidence["book"],
        )
        .distinct()
    ).scalar_one_or_none()
    if identity is None:
        raise Problem("not-found", "The original affected contract is unavailable.")
    details = [
        LABEL,
        f"Period: {row['period_key']}",
        f"Contribution: {row['contribution']}",
        f"Original input: {analysis['source_input_sha256']}",
        f"Original output: {analysis['source_output_sha256']}",
    ]
    for execution in analysis["executions"]:
        if not row["event_key"] or row["event_key"] in execution["event_keys"]:
            details.extend(
                [
                    f"Executed input: {execution['input_sha256']}",
                    f"Executed output: {execution['output_sha256']}",
                ]
            )
    if analysis["reporting_basis"]:
        details.append(
            "Pinned reporting basis: " + json.dumps(analysis["reporting_basis"], sort_keys=True)
        )
    return row[column_key], [
        {
            "object_type": "contract",
            "id": str(identity),
            "measure": column_key,
            "value": row[column_key],
            "href": f"/contracts/{identity}",
            "details": details,
        }
    ]

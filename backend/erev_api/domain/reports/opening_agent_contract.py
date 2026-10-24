"""Contract FIFO net disclosure from original sources, with one group cap."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from . import (
    opening_agent_sources,
    opening_relief_periods,
    opening_relief_availability as availability,
    revenue_attribution,
    tie_outs,
)
from .builders import ReportParams
from .builders.contract_balance_rollforward import Entry
from erev_api.uow import UnitOfWork

KEY = "agent_contract_opening_v1"
ZERO = Decimal(0)


@dataclass
class Result:
    recognized: Decimal
    relief: Decimal
    evidence: dict[str, Any]
    entries: list[Entry]
    eligible_entries: list[Entry]
    paid: set[UUID]


def enabled(params: ReportParams) -> bool:
    return params.binding is None or KEY in params.binding.evidence


def calculate(
    uow: UnitOfWork,
    rows: Sequence[tie_outs.BalanceRow],
    posted: Mapping[tuple[UUID, UUID], Sequence[Entry]],
    net: Mapping[tuple[UUID, UUID], list[Entry]],
    *,
    start: date,
    opening: Decimal,
    consumed: Decimal,
    view: str,
    allow_zero_consumption: bool = True,
    allow_unresolved: bool = False,
) -> Result | None:
    owners = {row.contract_id for row in rows}
    agents = {}
    for row in rows:
        key = (row.contract_id, row.entity_id)
        found = opening_agent_sources.read(
            uow,
            row,
            list(posted.get(key, ())),
            start,
            opening,
            view=view,
            net_entries=net.get(key, []),
            allowed_source_contracts=owners,
            classify_opening=not (allow_zero_consumption and consumed <= 0),
            allow_unresolved=allow_unresolved,
        )
        if found is not None:
            agents[key] = found
    if not agents:
        return None
    entries: list[Entry] = []
    eligible_entries: list[Entry] = []
    paid: set[UUID] = set()
    members = {}
    for row in rows:
        key = (row.contract_id, row.entity_id)
        found = agents.get(key)
        current = list(found.entries if found is not None else posted.get(key, ()))
        entries.extend(e for e in current if e.flow.is_revenue)
        obligations = {}
        if found is not None:
            paid.update(found.paid_lines)
            eligible_entries.extend(found.opening_entries)
            obligations = {
                subject: {"agent_net_sources": evidence}
                for subject, evidence in found.evidence.items()
            }
        principal = {}
        for entry in current:
            if not entry.flow.is_revenue or (
                found is not None and entry.subject_key in found.eligible
            ):
                continue
            if entry.line_id is None:
                raise tie_outs.invalid(
                    "currency_view", "Contract FIFO lacks its original net line."
                )
            try:
                identity, proof = revenue_attribution.for_control(uow, entry.line_id, view=view)
                if proof.components or proof.delta.amount != -entry.flow.amount:
                    raise ValueError(
                        "Contract FIFO principal amount differs from original sources."
                    )
                dates = {(owner, layer): when for owner, layer, when in proof.layer_dates}
                eligible = ZERO
                for part in proof.delta.movements:
                    if part.contract_id not in owners:
                        raise ValueError("Contract FIFO source belongs to another group.")
                    if part.movement_kind != "LIABILITY_LAYER_CONSUMED":
                        continue
                    created = dates.get((part.contract_id, part.layer_key))
                    if created is None:
                        raise ValueError("Contract FIFO source lacks its original creation date.")
                    if created < start:
                        eligible -= Decimal(part.amount.numerator) / Decimal(
                            part.amount.denominator
                        )
                eligible_entries.append(replace(entry, flow=replace(entry.flow, amount=eligible)))
                paid.update((entry.line_id, identity, *proof.paid_line_ids))
                principal[str(entry.line_id)] = {
                    "net_line": str(identity),
                    "net_income": str(entry.flow.amount),
                    "opening_income": str(eligible),
                    "sources": list(map(str, proof.delta.source_ids)),
                    "evidence": [[str(i), digest] for i, digest in proof.evidence],
                }
            except ValueError as error:
                raise tie_outs.invalid("currency_view", str(error)) from error
        for entry in current:
            if entry.flow.is_revenue:
                if entry.subject_key is None:
                    raise tie_outs.invalid("currency_view", "Contract net income lacks a subject.")
                detail = obligations.setdefault(entry.subject_key, {})
                detail["posted_revenue"] = str(
                    Decimal(detail.get("posted_revenue", "0")) + entry.flow.amount
                )
        members[str(row.contract_id)] = {
            "version": str(row.version_id),
            "obligations": obligations,
            "posted_lines": sorted(str(e.line_id) for e in current if e.flow.is_revenue),
            "principal_sources": principal,
        }
    uncertain = sorted({subject for found in agents.values() for subject in found.unresolved})
    recognized = sum((e.flow.amount for e in entries), ZERO)
    eligible = sum((e.flow.amount for e in eligible_entries), ZERO)
    relief = min(
        max(ZERO, opening), max(ZERO, consumed), max(ZERO, recognized), max(ZERO, eligible)
    )
    return Result(
        recognized,
        relief,
        {
            "basis": "CONTRACT_FIFO_ORIGINAL_NET_SOURCES",
            "members": members,
            "opening_cap": str(opening),
            "consumption_cap": str(consumed),
            "recognized": str(recognized),
            "eligible": None if uncertain else str(eligible),
            "relief": None if uncertain else str(relief),
            **({"unresolved_subjects": uncertain} if uncertain else {}),
        },
        entries,
        eligible_entries,
        paid,
    )


def row(
    members: Sequence[tie_outs.BalanceRow],
    group: str,
    currency: str,
    opening: Decimal,
    result: Result,
) -> dict[str, Any]:
    first = members[0]
    combined = len(members) > 1
    return {
        **(
            {"_opening_unavailable": availability.unresolved(result.evidence)}
            if availability.unresolved(result.evidence)
            else {}
        ),
        "_opening_source": {
            "entity_id": str(first.entity_id),
            "contracts": sorted(str(member.contract_id) for member in members),
            "group_key": group,
        },
        "row_key": f"combined:{group}"
        if combined
        else f"contract:{first.external_id}:{first.entity_code}",
        "section": 2,
        "summary": "Combined contracts (group total): "
        + "; ".join(sorted(member.external_id for member in members))
        + ". Member relief is not allocated."
        if combined
        else None,
        "contract_external_id": None if combined else first.external_id,
        "customer_name": None if combined else first.customer_name,
        "entity_code": first.entity_code,
        "currency": currency,
        "opening_contract_liability": tie_outs.money(opening, currency),
        "revenue_recognized": tie_outs.money(result.recognized, currency),
        "revenue_from_opening": tie_outs.money(result.relief, currency),
    }


def period_slices(
    result: Result,
    *,
    periods: Sequence[tie_outs.PeriodRef],
    opening: Decimal,
    consumption: Mapping[UUID, Decimal],
) -> tuple[dict[UUID, Decimal], dict[UUID, Decimal]]:
    def group(entries: Sequence[Entry]) -> list[Entry]:
        return [replace(entry, subject_key="group") for entry in entries]

    uncertain = availability.unresolved(result.evidence)
    relief = (
        {p.id: ZERO for p in periods}
        if uncertain
        else opening_relief_periods.deltas(
            periods=[p.id for p in periods],
            opening=opening,
            obligations={"group": opening},
            entries=group(result.entries),
            source_eligibility={"group": group(result.eligible_entries)},
            consumption=consumption,
            expected=result.relief,
        )
    )
    net = {
        p.id: sum((e.flow.amount for e in result.entries if e.period_id == p.id), ZERO)
        for p in periods
    }
    result.evidence["period_relief"] = {
        p.key: None if uncertain else str(relief[p.id]) for p in periods
    }
    result.evidence["period_net_revenue"] = {p.key: str(net[p.id]) for p in periods}
    return relief, net


def retain(params: ReportParams, evidence: dict[str, Any], paid: set[UUID]) -> None:
    if params.binding is not None and params.binding.evidence[KEY] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Contract FIFO net sources differ from retained evidence."
        )
    tie_outs.record_evidence(params, KEY, evidence)
    tie_outs.require_members(params, "agent_contract_paid_line", paid)
    tie_outs.record_members(params, "agent_contract_paid_line", paid)

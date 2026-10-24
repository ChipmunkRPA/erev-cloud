"""Net agent opening income only where the complete original source set proves its bucket."""

from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import obligation_version
from erev_api.domain.reports import revenue_attribution, tie_outs
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import obligation_subject_key

KEY = "agent_opening_source_sets_v1"
ZERO = Decimal(0)


def bucket(proof: revenue_attribution.AmountProof, start: date) -> str:
    """Classify a whole verified net amount, never assign a fraction to an individual source."""
    if proof.amount == 0:
        return "ZERO_NET"
    dates = {(owner, layer): created for owner, layer, created in proof.layer_dates}
    if not proof.sources or any((s.contract_id, s.layer_key) not in dates for s in proof.sources):
        raise ValueError("Agent net income lacks original source-layer creation dates.")
    kinds = {
        "OPENING"
        if s.movement_kind == "LIABILITY_LAYER_CONSUMED"
        and dates[s.contract_id, s.layer_key] < start
        else "NON_OPENING"
        for s in proof.sources
    }
    if len(kinds) != 1:
        raise ValueError(
            "Agent net income mixes opening and non-opening sources; "
            "no per-source net allocation is retained."
        )
    return next(iter(kinds))


@dataclass(frozen=True)
class Result:
    entries: tuple[Entry, ...]
    eligible: dict[str, Decimal]
    evidence: dict[str, Any]
    paid_lines: set[UUID]


def read(
    uow: UnitOfWork, row: tie_outs.BalanceRow, entries: list[Entry], start: date, opening: Decimal
) -> Result | None:
    agents = set(
        uow.session.scalars(
            select(obligation_version.c.obligation_key).where(
                obligation_version.c.contract_version_id == row.version_id,
                obligation_version.c.contract_id == row.contract_id,
                obligation_version.c.contracting_entity_id == row.entity_id,
                obligation_version.c.performing_entity_id == row.entity_id,
                obligation_version.c.principal_agent == "AGENT",
            )
        )
    )
    if not agents:
        return None
    subjects = {obligation_subject_key(row.external_id, key) for key in agents}
    eligible = dict.fromkeys(subjects, ZERO)
    facts: dict[str, Any] = {
        subject: {"basis": "UNIFORM_NET_SOURCE_SET", "lines": []} for subject in subjects
    }
    converted = []
    paid: set[UUID] = set()
    for entry in entries:
        if not entry.flow.is_revenue or entry.subject_key not in subjects:
            converted.append(entry)
            continue
        if entry.line_id is None:
            raise tie_outs.invalid("currency_view", "Agent income lacks an original control line.")
        try:
            _, gross = revenue_attribution.for_control(uow, entry.line_id, view="transaction")
            if not gross.components or gross.delta.amount != -Fraction(entry.flow.amount):
                raise ValueError(
                    "Original agent gross relief does not reconcile to the posted flow."
                )
            net = ZERO
            lines = []
            paid.update((entry.line_id, *gross.paid_line_ids))
            for identity, role, txn, _functional in gross.components:
                paid.add(identity)
                if role != "REVENUE":
                    continue
                proof = revenue_attribution.verify_component(uow, identity, view="transaction")
                if proof.amount != Fraction(txn):
                    raise ValueError("Agent net amount differs from its original posting.")
                if any(source.contract_id != row.contract_id for source in proof.sources):
                    raise ValueError(
                        "Agent opening attribution across original member owners "
                        "remains unsupported."
                    )
                category = "NO_OPENING" if opening <= 0 else bucket(proof, start)
                amount = -Decimal(txn)
                net += amount
                if category == "OPENING":
                    eligible[entry.subject_key] += amount
                paid.update(proof.paid_line_ids)
                lines.append(
                    {
                        "net_line": str(identity),
                        "bucket": category,
                        "net_income": str(amount),
                        "sources": [
                            {
                                k: (
                                    v.isoformat()
                                    if isinstance(v, date)
                                    else str(v)
                                    if isinstance(v, UUID)
                                    else v
                                )
                                for k, v in asdict(s).items()
                            }
                            for s in proof.sources
                        ],
                        "layer_dates": [
                            [str(c), k, d.isoformat()] for c, k, d in proof.layer_dates
                        ],
                        "evidence": [[str(c), digest] for c, digest in proof.evidence],
                    }
                )
            facts[entry.subject_key]["lines"].append(
                {
                    "control_line": str(entry.line_id),
                    "gross_relief": str(entry.flow.amount),
                    "net_income": str(net),
                    "components": [[str(i), r, t, f] for i, r, t, f in gross.components],
                    "source_sets": lines,
                }
            )
            converted.append(replace(entry, flow=replace(entry.flow, amount=net)))
        except ValueError as error:
            raise tie_outs.invalid("currency_view", str(error)) from error
    return Result(tuple(converted), eligible, facts, paid)

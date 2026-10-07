"""Approved contract-pinned policy exceptions for calculation bundles.

Read once per combination group, under its tenant scope. Product inputs are installed first;
these rows replace them in O > C > P order. Period-pinned exceptions require a separate
effective-period representation and are deliberately not admitted here.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_engine.bundle import ResolvedPolicyInput
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import policy_override
from erev_api.domain.policies.templates import engine_policy_value
from erev_api.enums import BookCode, RegistryScope
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS


def approved_rows(
    session: Session, contract_ids: Sequence[UUID], known_at: datetime
) -> Sequence[Mapping[str, Any]]:
    """Latest-known approval first, retaining superseded rows for historical cutoffs."""
    table = policy_override
    found = (
        session.execute(
            select(table)
            .where(
                table.c.contract_id.in_(contract_ids),
                table.c.status.in_(("APPROVED", "SUPERSEDED")),
                table.c.approved_at <= known_at,
            )
            .order_by(
                table.c.approved_at.desc(),
                (table.c.status == "APPROVED").desc(),
                table.c.id.desc(),
            )
        )
        .mappings()
        .all()
    )

    return [dict(row) for row in found]


def scoped_inputs(
    rows: Sequence[Mapping[str, Any]],
    *,
    book_code: str,
    contracts: Mapping[UUID, str],
    obligations: Sequence[Mapping[str, Any]],
    lines: Sequence[tuple[str, Mapping[str, Any]]],
) -> tuple[ResolvedPolicyInput, ...]:
    """Resolve explicit exceptions without letting one member affect another member.

    C values also appear at each line's obligation scope: the engine chooses by scope,
    while product defaults already occupy that scope. Explicit O values replace those
    projected C values. An override never changes a framework-forced policy.
    """
    obligation_keys = {
        (UUID(str(row["contract_id"])), UUID(str(row["id"]))): str(row["obligation_key"])
        for row in obligations
    }
    line_subjects: dict[str, set[str]] = {}
    for contract_key, line in lines:
        line_subjects.setdefault(contract_key, set()).add(
            obligation_subject_key(contract_key, str(line["obligation_key"]))
        )
    selected: dict[tuple[str, UUID, UUID | None], Mapping[str, Any]] = {}
    for row in rows:
        code = str(row["policy_key"])
        spec = POLICY_PARAMETERS.get(code)
        if spec is None or spec.pin != "K" or registry.is_forced(spec, BookCode(book_code)):
            continue
        contract_id = UUID(str(row["contract_id"]))
        obligation_id = None if row["obligation_id"] is None else UUID(str(row["obligation_id"]))
        scope = RegistryScope.CONTRACT if obligation_id is None else RegistryScope.OBLIGATION
        if scope not in spec.allowed_levels or row["level"] != scope.value:
            continue
        if contract_id not in contracts:
            continue
        if obligation_id is not None and (contract_id, obligation_id) not in obligation_keys:
            continue
        selected.setdefault((code, contract_id, obligation_id), row)

    resolved: dict[tuple[str, str, str], ResolvedPolicyInput] = {}

    def add(row: Mapping[str, Any], scope: str, subject: str, level: str) -> None:
        code = str(row["policy_key"])
        resolved[(code, scope, subject)] = ResolvedPolicyInput(
            code, scope, subject, engine_policy_value(row["value"]), level, str(row["id"]), "K"
        )

    for (_, contract_id, obligation_id), row in selected.items():
        if obligation_id is not None:
            continue
        contract_key = contracts[contract_id]
        add(row, "CONTRACT", contract_key, "C")
        for subject in sorted(line_subjects.get(contract_key, ())):
            add(row, "OBLIGATION", subject, "C")
    for (_, contract_id, obligation_id), row in selected.items():
        if obligation_id is not None:
            subject = obligation_subject_key(
                contracts[contract_id], obligation_keys[(contract_id, obligation_id)]
            )
            add(row, "OBLIGATION", subject, "O")
    return tuple(resolved[key] for key in sorted(resolved))

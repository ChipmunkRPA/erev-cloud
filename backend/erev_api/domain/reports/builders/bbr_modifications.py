"""RPT-37 applied modification values from their original application version and predecessor.

A group-level price delta is counted once per application, never once per obligation. Missing
or ambiguous evidence refuses; the latest group version is not a substitute for application.
"""

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import or_, select

from erev_api.db.tables import (
    combination_group_member,
    contract_event,
    contract_version,
    modification,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

EVIDENCE: Final = "bbr_modification_values_v1"
# A conservative allowlist: unfamiliar causes cannot silently be treated as price-neutral.
NON_VALUATION_CAUSES: Final = frozenset({"MEMO_UPDATED"})


def read(uow: UnitOfWork, params: ReportParams, *, start: date, end: date) -> dict[str, Any]:
    if params.book_code is None:
        raise tie_outs.invalid("book", "Choose a book.")
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "BBR modification values have no lock dataset.")
    cutoff = params.binding.cutoff if params.binding is not None else params.known_at
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
    if params.binding is not None:
        result = tie_outs.bound_evidence(params, EVIDENCE)
    else:
        tenant = uow.principal.tenant_id
        rows = [
            dict(r)
            for r in uow.session.execute(
                select(
                    modification.c.id,
                    modification.c.modification_no,
                    modification.c.contract_id,
                    modification.c.contracting_entity_id,
                    modification.c.effective_date,
                    modification.c.status,
                    modification.c.applied_event_id,
                    modification.c.created_at,
                    modification.c.updated_at,
                ).where(
                    modification.c.tenant_id == tenant,
                    modification.c.contracting_entity_id.in_(params.entity_ids),
                    modification.c.created_at <= cutoff,
                )
            ).mappings()
        ]
        # A mutable date/status cannot exclude a row before its history is checked.
        if any(r["updated_at"] > cutoff for r in rows):
            raise Problem(
                "invalid-transition", "Modification history does not cover the source time."
            )
        rows = [
            r for r in rows if str(r["status"]) == "APPLIED" and start <= r["effective_date"] <= end
        ]
        event_ids = [r["applied_event_id"] for r in rows if r["applied_event_id"] is not None]
        member = combination_group_member
        applications = [
            dict(r)
            for r in uow.session.execute(
                select(
                    contract_event.c.id,
                    contract_event.c.contract_id,
                    contract_event.c.event_type,
                    contract_event.c.recorded_at,
                    member.c.combination_group_id,
                )
                .select_from(contract_event)
                .join(
                    member,
                    (member.c.tenant_id == contract_event.c.tenant_id)
                    & (member.c.contract_id == contract_event.c.contract_id)
                    & (member.c.valid_from_known_at <= contract_event.c.recorded_at)
                    & or_(
                        member.c.valid_to_known_at.is_(None),
                        member.c.valid_to_known_at > contract_event.c.recorded_at,
                    ),
                )
                .where(
                    contract_event.c.tenant_id == tenant,
                    contract_event.c.id.in_(event_ids),
                    contract_event.c.recorded_at <= cutoff,
                    contract_event.c.created_at <= cutoff,
                )
            ).mappings()
        ]
        columns = (
            contract_version.c.id,
            contract_version.c.combination_group_id,
            contract_version.c.book_code,
            contract_version.c.previous_version_id,
            contract_version.c.cause_event_ids,
            contract_version.c.transaction_currency,
            contract_version.c.transaction_price,
            contract_version.c.known_at,
            contract_version.c.created_at,
        )
        base = select(*columns).where(
            contract_version.c.tenant_id == tenant,
            contract_version.c.book_code == params.book_code,
            contract_version.c.known_at <= cutoff,
            contract_version.c.created_at <= cutoff,
        )
        versions = [
            dict(r)
            for r in uow.session.execute(
                base.where(contract_version.c.cause_event_ids.overlap(event_ids))
            ).mappings()
        ]
        previous_ids = [
            r["previous_version_id"] for r in versions if r["previous_version_id"] is not None
        ]
        predecessors = [
            dict(r)
            for r in uow.session.execute(
                base.where(contract_version.c.id.in_(previous_ids))
            ).mappings()
        ]
        cause_ids = {event for r in versions for event in r["cause_event_ids"]}
        types = {
            str(r.id): str(r.event_type)
            for r in uow.session.execute(
                select(
                    contract_event.c.id,
                    contract_event.c.event_type,
                ).where(contract_event.c.tenant_id == tenant, contract_event.c.id.in_(cause_ids))
            )
        }
        result = json.loads(
            canonical_bytes(
                {
                    "book_code": params.book_code,
                    "start": start,
                    "end": end,
                    "modifications": rows,
                    "applications": applications,
                    "versions": versions,
                    "predecessors": predecessors,
                    "cause_types": types,
                }
            )
        )
        tie_outs.record_evidence(params, EVIDENCE, result)
    if (
        result["book_code"] != params.book_code
        or result["start"] != start.isoformat()
        or result["end"] != end.isoformat()
    ):
        raise Problem(
            "invalid-transition", "Retained modification values belong to another book or range."
        )
    scope = {str(e) for e in params.entity_ids}
    for row in result["modifications"]:
        if row["contracting_entity_id"] not in scope:
            raise Problem("forbidden", "Retained modifications exceed the report entity scope.")
        if any(datetime.fromisoformat(row[k]) > cutoff for k in ("created_at", "updated_at")):
            raise Problem("invalid-transition", "Retained modification exceeds the source cutoff.")
    return dict(result)


def values(source: Mapping[str, Any]) -> tuple[Contribution, ...]:
    previous = {r["id"]: r for r in source["predecessors"]}
    result = []
    counted: set[str] = set()
    for row in source["modifications"]:
        event_id = row["applied_event_id"]
        applications = [a for a in source["applications"] if a["id"] == event_id]
        if len(applications) != 1:
            raise Problem(
                "invalid-transition", "Modification has no unique historical application group."
            )
        group_id = applications[0]["combination_group_id"]
        candidates = [
            v
            for v in source["versions"]
            if event_id in v["cause_event_ids"] and v["combination_group_id"] == group_id
        ]
        if len(candidates) != 1:
            raise Problem("invalid-transition", "Modification has no unique application version.")
        version = candidates[0]
        for cause in version["cause_event_ids"]:
            kind = source["cause_types"].get(cause)
            if kind is None or (cause != event_id and kind not in NON_VALUATION_CAUSES):
                raise Problem(
                    "invalid-transition",
                    "Application price change has shared or unknown valuation causes.",
                )
        if version["id"] in counted:
            raise Problem("invalid-transition", "An application version cannot be counted twice.")
        counted.add(version["id"])
        before = Decimal(0)
        basis = [UUID(event_id), UUID(version["id"])]
        if version["previous_version_id"] is not None:
            predecessor = previous.get(version["previous_version_id"])
            if predecessor is None:
                raise Problem(
                    "invalid-transition", "Modification price predecessor is unavailable."
                )
            if (
                predecessor["combination_group_id"] != group_id
                or predecessor["transaction_currency"] != version["transaction_currency"]
                or predecessor["book_code"] != version["book_code"]
            ):
                raise Problem(
                    "invalid-transition",
                    "Modification predecessor has a different valuation basis.",
                )
            before = Decimal(predecessor["transaction_price"])
            basis.append(UUID(predecessor["id"]))
        with localcontext() as context:
            context.prec = 80
            amount = Decimal(version["transaction_price"]) - before
        result.append(
            Contribution(
                "modification",
                UUID(row["id"]),
                UUID(row["contract_id"]),
                UUID(row["contracting_entity_id"]),
                date.fromisoformat(row["effective_date"]),
                version["transaction_currency"],
                amount,
                basis_ids=tuple(basis),
            )
        )
    return tuple(sorted(result, key=lambda r: (r.effective_date, str(r.source_id))))

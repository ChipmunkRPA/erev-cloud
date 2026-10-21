"""Compare report closing balances with retained GL role totals, without netting failures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import report_source_revision
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef

if TYPE_CHECKING:
    from erev_api.domain.reports.builders.contract_balance_rollforward import ContractRollforward

EVIDENCE = "rollforward_gl_inputs_v6"
REVISION_EVIDENCE = "rollforward_gl_inputs_v5"
HISTORICAL_EVIDENCE = "rollforward_gl_inputs_v4"
REVIEW_EVIDENCE = "rollforward_gl_inputs_v3"
BRIDGE_EVIDENCE = "rollforward_gl_inputs_v2"
REVIEWED = frozenset({"REVIEWED", "AUTO_CERTIFIED", "CERTIFIED"})
LEGACY_EVIDENCE = "rollforward_gl_inputs_v1"
ROLES = {
    "CONTRACT_LIABILITY": "contract_liability",
    "CONTRACT_ASSET": "contract_asset",
    "UNBILLED_RECEIVABLE": "unbilled_receivable",
}


def compare(
    entities: Sequence[EntityRef],
    items: Sequence[ContractRollforward],
    sources: Mapping[str, Any],
    *,
    bridge: bool = True,
    require_review: bool = True,
) -> dict[str, Any]:
    """GL debit-positive balances are compared to the report's positive captions per role."""
    details: list[dict[str, Any]] = []
    expected: dict[str, Decimal] = {}
    actual: dict[str, Decimal] = {}
    incomplete = False
    failed = False
    for entity in entities:
        source = sources.get(str(entity.id))
        if source is None:
            incomplete = True
            details.append(
                {"entity": entity.code, "reason": "No trial balance at the report cutoff."}
            )
            continue
        reference = {
            "reconciliation_id": source["id"],
            **{
                key: source[key]
                for key in ("book_code", "period_key", "source_revision_id", "source_recorded_at")
                if source.get(key)
            },
            **({"source_status": source["status"]} if "status" in source else {}),
        }
        if source.get("unavailable_reason"):
            incomplete = True
            details.append(
                {
                    "entity": entity.code,
                    **reference,
                    "result": tie_outs.NOT_APPLICABLE,
                    "reason": source["unavailable_reason"],
                }
            )
            continue
        if require_review and source.get("status") not in REVIEWED:
            incomplete = True
            details.append(
                {
                    "entity": entity.code,
                    **reference,
                    "result": tie_outs.NOT_APPLICABLE,
                    "reason": "The GL reconciliation has not been reviewed or certified.",
                }
            )
            continue
        rows: dict[str, Any] = {}
        for row in source["totals"]:
            role = row.get("account_role")
            if role not in ROLES:
                continue
            if role in rows:
                raise tie_outs.invalid("currency_view", "The GL source repeats a balance role.")
            rows[role] = row
        selected = [item for item in items if item.entity_id == entity.id]
        if any(item.currency != entity.functional_currency for item in selected):
            incomplete = True
            details.append(
                {
                    "entity": entity.code,
                    **reference,
                    "reason": "GL comparison requires functional balances.",
                }
            )
            continue
        for role, caption in ROLES.items():
            report = sum((item.lines["CLOSING"][caption] for item in selected), Decimal(0))
            row = rows.get(role)
            # The GL reconciliation omits a role only when it has neither mapped
            # accounts nor a subledger balance. Such an omitted role can agree
            # only with a zero report caption; never use it for a nonzero balance.
            if row is None and report == 0:
                details.append(
                    {
                        "entity": entity.code,
                        "role": role,
                        **reference,
                        "currency": entity.functional_currency,
                        "gl": "0",
                        "rollforward": "0",
                        "difference": "0",
                        "result": tie_outs.PASS,
                        **(
                            {
                                "source_subledger": "0",
                                "subledger_gl_difference": "0",
                                "report_subledger_difference": "0",
                                "bridge_result": tie_outs.PASS,
                            }
                            if bridge
                            else {}
                        ),
                    }
                )
                continue
            if (
                row is None
                or row.get("not_stated") is not None
                or row.get("source_amount") is None
                or row["currency"] != entity.functional_currency
            ):
                incomplete = True
                reason = (
                    "The GL source has no total for this role."
                    if row is None
                    else "The GL source marks this role as not stated."
                    if row.get("not_stated") is not None
                    else "The GL source has no amount for this role."
                    if row.get("source_amount") is None
                    else "The GL source currency differs from the entity functional currency."
                )
                details.append(
                    {
                        "entity": entity.code,
                        "role": role,
                        **reference,
                        "currency": entity.functional_currency,
                        "rollforward": str(report),
                        "result": tie_outs.NOT_APPLICABLE,
                        "reason": reason,
                    }
                )
                continue
            gl = Decimal(row["source_amount"]) * (-1 if role == "CONTRACT_LIABILITY" else 1)
            if not gl.is_finite():
                raise tie_outs.invalid("currency_view", "The GL source amount is not finite.")
            role_failed = report != gl
            bridge_values: dict[str, str] = {}
            bridge_missing = False
            if bridge:
                retained = row.get("subledger_amount")
                if retained is None:
                    incomplete = bridge_missing = True
                    bridge_values = {
                        "bridge_result": tie_outs.NOT_APPLICABLE,
                        "bridge_reason": "The GL source has no retained subledger amount.",
                    }
                else:
                    subledger = Decimal(retained) * (-1 if role == "CONTRACT_LIABILITY" else 1)
                    if not subledger.is_finite():
                        raise tie_outs.invalid(
                            "currency_view", "The retained subledger amount is not finite."
                        )
                    subledger_gl, report_subledger = subledger - gl, report - subledger
                    bridge_failed = subledger_gl != 0 or report_subledger != 0
                    role_failed |= bridge_failed
                    bridge_values = {
                        "source_subledger": str(subledger),
                        "subledger_gl_difference": str(subledger_gl),
                        "report_subledger_difference": str(report_subledger),
                        "bridge_result": tie_outs.FAIL if bridge_failed else tie_outs.PASS,
                    }
            failed |= role_failed
            tie_outs.add(expected, entity.functional_currency, gl)
            tie_outs.add(actual, entity.functional_currency, report)
            details.append(
                {
                    "entity": entity.code,
                    "role": role,
                    **reference,
                    "currency": entity.functional_currency,
                    "gl": str(gl),
                    "rollforward": str(report),
                    "difference": str(report - gl),
                    "result": tie_outs.FAIL
                    if role_failed
                    else tie_outs.NOT_APPLICABLE
                    if bridge_missing
                    else tie_outs.PASS,
                    **bridge_values,
                }
            )
    result = tie_outs.compared(tie_outs.TO_ROLLFORWARD_EQ_GL, expected, actual)
    result["result"] = (
        tie_outs.FAIL if failed else tie_outs.NOT_APPLICABLE if incomplete else tie_outs.PASS
    )
    result["details"] = details
    return result


def _captured_sources(
    session: Session,
    cutoff: datetime,
    entities: Sequence[EntityRef],
    periods: Mapping[UUID, Sequence[PeriodRef]],
    book_code: str,
) -> dict[str, Any]:
    """Resolve all GL identities and states in one MVCC statement from immutable revisions."""
    targets = {entity.id: periods[entity.id][-1] for entity in entities if periods.get(entity.id)}
    if not targets:
        return {}
    table = report_source_revision
    attached = or_(
        table.c.document["source_file_id"].astext.is_not(None),
        table.c.document["sync_run_id"].astext.is_not(None),
    )
    history = (
        select(
            table,
            func.row_number()
            .over(partition_by=table.c.source_id, order_by=table.c.revision_no.desc())
            .label("latest"),
            func.bool_or(attached).over(partition_by=table.c.source_id).label("had_source"),
        )
        .where(
            table.c.source_kind == "gl_reconciliation",
            table.c.recorded_at <= cutoff,
            table.c.document["book_code"].astext == book_code,
            or_(
                *(
                    and_(
                        table.c.entity_id == entity_id,
                        table.c.document["period_id"].astext == str(period.id),
                    )
                    for entity_id, period in targets.items()
                )
            ),
        )
        .subquery()
    )
    rows = (
        session.execute(select(history).where(history.c.latest == 1, history.c.had_source))
        .mappings()
        .all()
    )
    chosen: dict[UUID, tuple[tuple[datetime, datetime, str], Mapping[str, Any]]] = {}
    for revision in rows:
        original = revision["document"]
        as_of = datetime.fromisoformat(str(original["as_of_known_at"]))
        created = datetime.fromisoformat(str(original["created_at"]))
        if as_of > cutoff or created > cutoff:
            continue
        entity_id = revision["entity_id"]
        rank = (as_of, created, str(revision["source_id"]))
        if entity_id not in chosen or rank > chosen[entity_id][0]:
            chosen[entity_id] = (rank, dict(revision))
    sources = {}
    for entity_id, (_, held) in chosen.items():
        original = held["document"]
        source = {
            "id": str(held["source_id"]),
            "period_key": targets[entity_id].key,
            "book_code": book_code,
            "source_revision_id": str(held["id"]),
            "source_recorded_at": held["recorded_at"].isoformat(),
            **{
                key: original[key]
                for key in (
                    "status",
                    "period_id",
                    "as_of_known_at",
                    "source_file_id",
                    "sync_run_id",
                    "totals",
                )
            },
        }
        if not original["source_file_id"] and not original["sync_run_id"]:
            source["unavailable_reason"] = (
                "The GL trial balance was not attached at the report cutoff."
            )
        sources[str(entity_id)] = source
    return sources


def build(
    session: Session,
    params: ReportParams,
    *,
    entities: Sequence[EntityRef],
    periods: Mapping[UUID, Sequence[PeriodRef]],
    items: Sequence[ContractRollforward],
    book_code: str,
    contract_id: UUID | None,
) -> dict[str, Any]:
    if contract_id is not None:
        result = tie_outs.not_applicable(tie_outs.TO_ROLLFORWARD_EQ_GL)
        result["details"] = [
            {"reason": "An entity GL balance cannot be compared with one contract."}
        ]
        return result
    evidence_key = EVIDENCE
    if params.binding is not None:
        # Preserve each retained control version without reading current review state.
        evidence_key = next(
            (
                key
                for key in (
                    EVIDENCE,
                    REVISION_EVIDENCE,
                    HISTORICAL_EVIDENCE,
                    REVIEW_EVIDENCE,
                    BRIDGE_EVIDENCE,
                    LEGACY_EVIDENCE,
                )
                if key in params.binding.evidence
            ),
            LEGACY_EVIDENCE,
        )
        sources = params.binding.evidence.get(evidence_key, {})
    else:
        cutoff = tie_outs.cutoff_for(session, params)
        sources = _captured_sources(session, cutoff, entities, periods, book_code)
    if params.sources is not None:
        params.sources.record_evidence(evidence_key, sources)
    return compare(
        entities,
        items,
        sources,
        bridge=evidence_key != LEGACY_EVIDENCE,
        require_review=evidence_key
        in {EVIDENCE, REVISION_EVIDENCE, HISTORICAL_EVIDENCE, REVIEW_EVIDENCE},
    )

"""Compare report closing balances with retained GL role totals, without netting failures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import reconciliation
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef

if TYPE_CHECKING:
    from erev_api.domain.reports.builders.contract_balance_rollforward import ContractRollforward

EVIDENCE = "rollforward_gl_inputs_v4"
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
            **{key: source[key] for key in ("book_code", "period_key") if source.get(key)},
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
                for key in (EVIDENCE, REVIEW_EVIDENCE, BRIDGE_EVIDENCE, LEGACY_EVIDENCE)
                if key in params.binding.evidence
            ),
            LEGACY_EVIDENCE,
        )
        sources = params.binding.evidence.get(evidence_key, {})
    else:
        sources = {}
        cutoff = tie_outs.cutoff_for(session, params)
        for entity in entities:
            selected = periods.get(entity.id, ())
            if not selected:
                continue
            row = (
                session.execute(
                    select(reconciliation)
                    .where(
                        reconciliation.c.entity_id == entity.id,
                        reconciliation.c.book_code == book_code,
                        reconciliation.c.period_id == selected[-1].id,
                        reconciliation.c.kind == "SUBLEDGER_TO_GL",
                        reconciliation.c.created_at <= cutoff,
                        reconciliation.c.as_of_known_at <= cutoff,
                        or_(
                            reconciliation.c.source_file_id.is_not(None),
                            reconciliation.c.sync_run_id.is_not(None),
                        ),
                    )
                    .order_by(
                        reconciliation.c.as_of_known_at.desc(),
                        reconciliation.c.created_at.desc(),
                        reconciliation.c.id.desc(),
                    )
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if row is not None and row["updated_at"] > cutoff:
                # The identity existed at the cutoff but its current review/totals did not.
                # Never skip it and fall back to a superseded older reviewed source.
                sources[str(entity.id)] = {
                    "id": str(row["id"]),
                    "period_key": selected[-1].key,
                    "book_code": book_code,
                    "unavailable_reason": (
                        "The latest GL reconciliation changed after the report cutoff; "
                        "its historical review state and totals are unavailable."
                    ),
                }
            elif row is not None:
                sources[str(entity.id)] = {
                    "id": str(row["id"]),
                    "status": str(getattr(row["status"], "value", row["status"])),
                    "period_id": str(row["period_id"]),
                    "period_key": selected[-1].key,
                    "book_code": book_code,
                    "as_of_known_at": row["as_of_known_at"].isoformat(),
                    "source_file_id": str(row["source_file_id"]) if row["source_file_id"] else None,
                    "sync_run_id": str(row["sync_run_id"]) if row["sync_run_id"] else None,
                    "totals": row["totals"],
                }
    if params.sources is not None:
        params.sources.record_evidence(evidence_key, sources)
    return compare(
        entities,
        items,
        sources,
        bridge=evidence_key != LEGACY_EVIDENCE,
        require_review=evidence_key in {EVIDENCE, REVIEW_EVIDENCE},
    )

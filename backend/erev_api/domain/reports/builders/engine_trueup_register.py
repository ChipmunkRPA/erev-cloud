"""Upgrade processing portions and attributed sealed lines, at an exact record cutoff.

Amounts are signed ledger amounts, never a hypothetical upgrade delta. Retained
input facts supply reruns; current report/export permission is checked by the worker.
"""

from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import and_, select

from erev_api.db.tables import (
    legal_entity,
    period,
    posting_attribution,
    release_group_processing,
    release_validation_group,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.reports.builders import RETAINED, ReportParams
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import money
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE: Final = "engine_trueup_register"
BINDING: Final = "upgrade_processing_inputs"
COLUMNS: Final = (
    Column("record_type", "Record type", "code"),
    Column("group_id", "Combination group", "code"),
    Column("entity_code", "Entity", "code"),
    Column("book_code", "Book", "code"),
    Column("upgrade_state", "Processing state", "code"),
    Column("group_terminal", "Whole group terminal", "boolean"),
    Column("sampled", "Sampled group", "boolean"),
    Column("unresolved_origins", "Unresolved origin periods", "text"),
    Column("reason", "Reason", "text"),
    Column("posting_id", "Posting", "code"),
    Column("period_key", "Posting period", "code"),
    Column("account_role", "Account role", "code"),
    Column("cause", "Attribution cause", "code"),
    Column("amount_txn", "Signed transaction amount", "money"),
    Column("amount_functional", "Signed functional amount", "money"),
)


def require_access(uow: UnitOfWork, params: ReportParams) -> None:
    actor = uow.principal if params.requester is None else params.requester.principal
    scope = actor.permission_scopes.get("report.run")
    if (
        actor.tenant_id != uow.principal.tenant_id
        or "report.run" not in actor.permissions
        or not scope
        or (scope != "*" and not set(params.entity_ids) <= scope)
    ):
        raise Problem("forbidden")


def _read(uow: UnitOfWork, params: ReportParams, validation_id: UUID) -> dict[str, Any]:
    # All portions are needed only to establish whether the WHOLE group is terminal.
    # Hidden portion identities/states are never retained or returned to a partial reader.
    p = release_group_processing.c
    events = (
        uow.session.execute(
            select(release_group_processing)
            .where(
                p.tenant_id == uow.principal.tenant_id,
                p.release_validation_id == validation_id,
                p.created_at <= params.known_at,
            )
            .distinct(p.combination_group_id, p.entity_id, p.book_code)
            .order_by(p.combination_group_id, p.entity_id, p.book_code, p.seq.desc())
        )
        .mappings()
        .all()
    )
    entities = dict(
        uow.session.execute(
            select(legal_entity.c.id, legal_entity.c.code).where(
                legal_entity.c.id.in_(params.entity_ids)
            )
        )
        .tuples()
        .all()
    )
    groups: dict[UUID, list[Mapping[str, Any]]] = {}
    for event in events:
        groups.setdefault(event["combination_group_id"], []).append(dict(event))
    g = release_validation_group.c
    sampled = set(
        uow.session.execute(
            select(g.combination_group_id).where(
                g.release_validation_attempt_id.in_(
                    {e["release_validation_attempt_id"] for e in events}
                ),
                g.created_at <= params.known_at,
                g.selection == "SAMPLED",
            )
        ).scalars()
    )
    portions = []
    for event in events:
        if event["entity_id"] not in params.entity_ids:
            continue
        group = groups[event["combination_group_id"]]
        complete = all(e["entity_id"] in params.entity_ids for e in group)
        portions.append(
            {
                "id": str(event["id"]),
                "group_id": str(event["combination_group_id"]),
                "entity_id": str(event["entity_id"]),
                "entity_code": entities[event["entity_id"]],
                "book_code": str(event["book_code"]),
                "upgrade_state": str(event["upgrade_state"]),
                "attempt_id": str(event["release_validation_attempt_id"]),
                "group_terminal": all(
                    e["upgrade_state"] in {"POSTED", "SETTLED_NO_POSTING"} for e in group
                )
                if complete
                else None,
                "sampled": event["combination_group_id"] in sampled,
                "unresolved_origins": list(event["unresolved_origin_period_keys"]),
                "posting_ids": [str(v) for v in event["subledger_posting_ids"]],
                "reason": event["reason"],
            }
        )
    ids = {UUID(v) for portion in portions for v in portion["posting_ids"]}
    line_columns, a, h, seal = (
        subledger_line.c,
        posting_attribution.c,
        subledger_posting.c,
        subledger_posting_seal.c,
    )
    statement = (
        select(
            line_columns.id,
            line_columns.entity_id,
            line_columns.book_code,
            line_columns.subledger_posting_id,
            line_columns.account_role,
            line_columns.txn_currency,
            line_columns.amount_txn,
            line_columns.functional_currency,
            line_columns.amount_functional,
            period.c.period_key,
            a.release_validation_attempt_id,
            a.combination_group_id,
            a.cause,
            a.sampled,
            seal.seal_sha256,
        )
        .select_from(subledger_line)
        .join(
            posting_attribution,
            and_(
                a.tenant_id == line_columns.tenant_id,
                a.subledger_posting_id == line_columns.subledger_posting_id,
            ),
        )
        .join(
            subledger_posting,
            and_(
                h.tenant_id == line_columns.tenant_id,
                h.id == line_columns.subledger_posting_id,
            ),
        )
        .join(
            subledger_posting_seal,
            and_(
                seal.tenant_id == line_columns.tenant_id,
                seal.subledger_posting_id == line_columns.subledger_posting_id,
            ),
        )
        .join(
            period,
            and_(
                period.c.tenant_id == line_columns.tenant_id, period.c.id == line_columns.period_id
            ),
        )
        .where(
            line_columns.tenant_id == uow.principal.tenant_id,
            line_columns.entity_id.in_(params.entity_ids),
            line_columns.subledger_posting_id.in_(ids),
            line_columns.recorded_at <= params.known_at,
            line_columns.created_at <= params.known_at,
            a.created_at <= params.known_at,
            h.created_at <= params.known_at,
            seal.created_at <= params.known_at,
            seal.sealed_at <= params.known_at,
        )
        .order_by(line_columns.id)
    )
    lines = []
    for row in uow.session.execute(statement).mappings():
        lines.append({k: (v if isinstance(v, bool) else str(v)) for k, v in row.items()})
    return {
        "version": 1,
        "validation_id": str(validation_id),
        "entity_ids": sorted(str(v) for v in params.entity_ids),
        "portions": portions,
        "lines": lines,
    }


def dataset(facts: Mapping[str, Any]) -> ReportData:
    rows: list[dict[str, Any]] = []
    totals: dict[str, Decimal] = {}
    states: Counter[str] = Counter()
    for portion in facts["portions"]:
        states[portion["upgrade_state"]] += 1
        base = {
            key: portion[key]
            for key in (
                "group_id",
                "entity_code",
                "book_code",
                "upgrade_state",
                "group_terminal",
                "sampled",
                "reason",
            )
        }
        base["unresolved_origins"] = ", ".join(portion["unresolved_origins"])
        rows.append({"row_key": f"portion:{portion['id']}", "record_type": "PORTION", **base})
        matched_postings = set()
        for line in facts["lines"]:
            if (
                line["entity_id"] != portion["entity_id"]
                or line["book_code"] != portion["book_code"]
                or line["subledger_posting_id"] not in portion["posting_ids"]
            ):
                continue
            if (
                line["release_validation_attempt_id"] != portion["attempt_id"]
                or line["combination_group_id"] != portion["group_id"]
            ):
                raise Problem(
                    "validation-failed", "Upgrade posting attribution does not match its portion."
                )
            matched_postings.add(line["subledger_posting_id"])
            row = {
                "row_key": f"line:{line['id']}",
                "record_type": "POSTING_LINE",
                **base,
                "posting_id": line["subledger_posting_id"],
                "period_key": line["period_key"],
                "account_role": line["account_role"],
                "cause": line["cause"],
                "sampled": line["sampled"],
            }
            for basis, currency in (("txn", "txn_currency"), ("functional", "functional_currency")):
                amount = Decimal(line[f"amount_{basis}"])
                if not amount.is_finite():
                    raise Problem("validation-failed", "Upgrade posting amount is invalid.")
                row[f"amount_{basis}"] = money(amount, line[currency])
                key = ":".join(
                    (
                        portion["entity_code"],
                        portion["book_code"],
                        line["period_key"],
                        basis,
                        line[currency],
                        line["account_role"],
                    )
                )
                totals[key] = totals.get(key, Decimal(0)) + amount
            rows.append(row)
        if matched_postings != set(portion["posting_ids"]):
            raise Problem(
                "validation-failed", "An attributed sealed posting is unavailable at this cutoff."
            )
    rows.sort(
        key=lambda row: (
            row["group_id"],
            row["entity_code"],
            row["book_code"],
            row["record_type"] != "PORTION",
            row["row_key"],
        )
    )
    # Uniform keys let every format render the same columns, including pending portions.
    for row in rows:
        for column in COLUMNS:
            row.setdefault(column.key, None)
    return ReportData(
        COLUMNS,
        tuple(rows),
        {
            "portions": len(facts["portions"]),
            "states": dict(sorted(states.items())),
            "signed_amounts": {key: str(value) for key, value in sorted(totals.items())},
        },
    )


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    require_access(uow, params)
    if (
        params.report_code != CODE
        or params.report_version != 1
        or params.period_lock_id is not None
        or params.filters
    ):
        raise Problem("validation-failed", "Invalid upgrade register parameters.")
    try:
        identity = UUID(str(params.parameters["release_validation_id"]))
        if params.binding is None:
            facts = _read(uow, params, identity)
        else:
            binding = params.binding
            facts = binding.evidence[BINDING]
            if (
                binding.strategy != RETAINED
                or binding.report_version != 1
                or binding.cutoff != params.known_at
                or sha256_hex(facts) != binding.evidence[BINDING + "_sha256"]
            ):
                raise ValueError("source binding")
        if (
            facts["version"] != 1
            or facts["validation_id"] != str(identity)
            or facts["entity_ids"] != sorted(str(v) for v in params.entity_ids)
        ):
            raise ValueError("source scope")
        data = dataset(facts)
    except (KeyError, ValueError, TypeError) as error:
        raise Problem(
            "validation-failed", "The upgrade register source evidence is invalid."
        ) from error
    if params.sources is not None:
        params.sources.record_cutoff(params.known_at)
        params.sources.record_evidence(BINDING, facts)
        params.sources.record_evidence(BINDING + "_sha256", sha256_hex(facts))
    return data

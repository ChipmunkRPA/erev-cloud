"""Attach live disclosure children once; retries reuse their immutable run selectors.

The caller supplies the authorized initiating context and owns the outer transaction.
Parent publication and locked disclosure snapshots are handled separately.
"""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select, update

from erev_api.db.tables import period_state_transition, report_run
from erev_api.domain.reports import disclosure_plan, framework, tie_outs
from erev_api.domain.reports.disclosure_plan import ChildSource
from erev_api.domain.reports.requester import require_export
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Disclosure child runs: {detail}")


def _read(uow: UnitOfWork, parent: Mapping[str, Any]) -> tuple[ChildSource, ...]:
    ids = tuple(parent["child_report_run_ids"])
    expected = tuple(
        (code, sections, basis)
        for code, sections in disclosure_plan.SECTIONS.items()
        for basis in (
            ("PERIOD", "QUARTER_TO_DATE") if parent["parameters"].get("quarter") else ("PERIOD",)
        )
        if basis == "PERIOD" or code not in disclosure_plan.POINT_IN_TIME
    )
    if len(ids) != len(expected) or len(set(ids)) != len(ids):
        raise _refuse("the attached child population is incomplete or duplicated.")
    rows = {
        row["id"]: row
        for row in uow.session.execute(
            select(report_run).where(
                report_run.c.tenant_id == uow.principal.tenant_id, report_run.c.id.in_(ids)
            )
        ).mappings()
    }
    sources = []
    period_keys: set[str] = set()
    quarter_starts: set[str] = set()
    for identity, (code, sections, basis) in zip(ids, expected, strict=True):
        row = rows.get(identity)
        if row is None:
            raise _refuse("an attached child is unavailable.")
        p = row["parameters"]
        if (
            row["report_code"] != code
            or row["report_version"] != 1
            or row["output_format"] != "JSON"
            or row["period_lock_id"] is not None
            or row["entity_ids"] != parent["entity_ids"]
            or row["book_code"] != parent["book_code"]
            or row["known_at"] != parent["known_at"]
            or (row["created_by"], row["created_by_kind"])
            != (parent["created_by"], parent["created_by_kind"])
            or p.get("known_at_basis") != "historical"
            or p.get("currency_view") != parent["parameters"].get("currency_view", "transaction")
            or row["job_id"] is None
        ):
            raise _refuse("an attached child differs from its parent scope or initiator.")
        key = (
            p.get("period_key") if code in disclosure_plan.POINT_IN_TIME else p.get("to_period_key")
        )
        if not isinstance(key, str):
            raise _refuse("an attached child has no period selector.")
        period_keys.add(key)
        if code not in disclosure_plan.POINT_IN_TIME:
            first = p.get("from_period_key")
            if not isinstance(first, str) or (basis == "PERIOD" and first != key):
                raise _refuse("an attached child has the wrong interval.")
            if basis == "QUARTER_TO_DATE":
                quarter_starts.add(first)
        sources.append(
            ChildSource(f"{code}:{basis}", sections, basis, identity, row["job_id"], sha256_hex(p))
        )
    selected = parent["parameters"].get("period_key")
    if (
        len(period_keys) != 1
        or len(quarter_starts) > 1
        or (selected is not None and period_keys != {selected})
    ):
        raise _refuse("child periods disagree with the selected disclosure interval.")
    return tuple(sources)


def ensure(uow: UnitOfWork, parent_id: UUID) -> tuple[ChildSource, ...]:
    """Serialize attachment with a parent row lock; never replace existing child IDs."""
    found = (
        uow.session.execute(
            select(report_run)
            .where(report_run.c.tenant_id == uow.principal.tenant_id, report_run.c.id == parent_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if found is None or found["report_code"] != "disclosure_pack":
        raise _refuse("the parent disclosure run is unavailable.")
    parent = dict(found)
    principal = uow.principal
    scope = principal.permission_scopes.get("report.run")
    if (
        len(parent["entity_ids"]) != 1
        or "report.run" not in principal.permissions
        or not scope
        or (scope != "*" and not set(parent["entity_ids"]) <= scope)
        or (parent["created_by"], parent["created_by_kind"]) != (principal.id, principal.kind.value)
    ):
        raise Problem("forbidden")
    require_export(principal, parent["output_format"], parent["entity_ids"])
    if parent["period_lock_id"] is not None:
        raise _refuse("a locked pack requires frozen disclosure sources, not live child reports.")
    if parent["child_report_run_ids"]:
        # Immutable child parameters preserve the chosen quarter even if calendars later change.
        return _read(uow, parent)
    if parent["status"] not in {"QUEUED", "RUNNING"}:
        raise _refuse("a terminal parent cannot acquire new sources.")
    with uow.savepoint():
        params = framework.report_params(parent)
        entities = tie_outs.entities(uow.session, params.entity_ids)
        if len(entities) != 1:
            raise _refuse("the selected entity is unavailable.")
        entity = entities[0]
        calendar = tie_outs.calendars(uow.session, entities)[entity.id]
        period = tie_outs.period_of(params, calendar, entity)
        transitions = period_state_transition.c
        states = uow.session.execute(
            select(transitions.to_state, transitions.created_at, transitions.created_txid)
            .where(
                transitions.tenant_id == principal.tenant_id,
                transitions.entity_id == entity.id,
                transitions.period_id == period.id,
                transitions.book_code == parent["book_code"],
                transitions.created_at <= params.known_at,
            )
            .order_by(
                transitions.created_at.desc(),
                transitions.created_txid.desc(),
                transitions.id.desc(),
            )
            .limit(2)
        ).all()
        ambiguous = (
            len(states) == 2
            and states[0][1:] == states[1][1:]
            and states[0].to_state != states[1].to_state
        )
        if not states or states[0].to_state != "open" or ambiguous:
            raise _refuse(
                "live draft packs require an open period at the source cutoff; "
                "frozen disclosure sources are not yet available."
            )
        planned = disclosure_plan.requests(
            entity_code=entity.code,
            book=str(parent["book_code"]),
            calendar=calendar,
            period_key=period.key,
            known_at=params.known_at,
            quarter=bool(params.parameters.get("quarter")),
            currency_view=str(params.parameters.get("currency_view", "transaction")),
        )
        children = disclosure_plan.queue(uow, planned)
        ids = [child.run_id for child in children]
        uow.session.execute(
            update(report_run)
            .where(report_run.c.tenant_id == principal.tenant_id, report_run.c.id == parent_id)
            .values(
                child_report_run_ids=ids,
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
        return _read(uow, {**parent, "child_report_run_ids": ids})

"""Shared return approval and atomic member application through the existing approval kernel."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.approvals import engine as approvals, subjects
from erev_api.db import transitions
from erev_api.db.locking import hold_fx_publication
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import approval_request, contract, legal_entity
from erev_api.domain.contracts import (
    bundles,
    computation,
    estimates,
    portfolio_estimate_versions,
    portfolio_impact,
    portfolio_binding,
    portfolios,
    repo,
)
from erev_api.domain.contracts.activation import engine_problem
from erev_api.events.stream import append_events
from erev_api.enums import ApprovalSubjectType, ComputationTrigger
from erev_api.problems import Problem
from erev_api.schemas.portfolios import PortfolioImpactOut
from erev_api.schemas.estimates import EstimateVersionOut
from erev_api.uow import UnitOfWork
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError


def _lock(
    uow: UnitOfWork, version_id: UUID, *, prepare: bool
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    session = uow.session
    hold_fx_publication(session, uow.principal.tenant_id)
    first = estimates._version_row(session, version_id)
    element = estimates._estimate_row(session, first["estimate_id"])
    portfolio_id = element["portfolio_id"]
    if portfolio_id is None or str(element["estimate_kind"]) != "RETURN_RATE":
        raise Problem("validation-failed", "Only shared return estimates can use this workflow.")
    portfolios.get(session, portfolio_id, lock=True)
    portfolios.require_estimate_scope(session, uow.ctx, portfolio_id, "contract.read")
    if prepare:
        portfolios.require_estimate_scope(session, uow.ctx, portfolio_id, "estimate.create")
    row = estimates._version_row(session, version_id, lock=True)
    basis = row.get("portfolio_application_basis")
    if not basis or not portfolio_binding.recipients(basis):
        raise Problem("validation-failed", "Save explicit member targets before submission.")
    ids = portfolio_binding.recipients(basis)
    heads = session.execute(
        select(contract.c.id, contract.c.combination_group_id).where(contract.c.id.in_(ids))
    ).all()
    if len(heads) != len(ids):
        raise Problem("not-found")
    currents = []
    for head in sorted(heads, key=lambda h: (str(h.combination_group_id), str(h.id))):
        _, current = repo.lock_group_then_contract(session, head.id)
        currents.append(dict(current))
    return dict(row), dict(element), currents


def _routing(
    uow: UnitOfWork, row: dict[str, Any], impact: PortfolioImpactOut
) -> tuple[tuple[Decimal, str] | None, frozenset[str]]:
    currencies = {group.currency for group in impact.groups}
    rates = bundles.fx_rate_inputs(uow.session, currencies | {"USD"}, None)
    total = Decimal(0)
    unknown = False
    for group in impact.groups:
        impact_amount = abs(Decimal(group.catch_up_amount))
        rate = estimates._spot_rate(
            rates, base=group.currency, quote="USD", on=row["effective_date"]
        )
        if impact_amount and rate is None:
            unknown = True
        elif rate is not None:
            total += estimates._converted(impact_amount, rate, "USD")
    flags = (
        frozenset({estimates.ESTIMATE_PL_IMPACT_FLAG})
        if unknown or total >= estimates.PL_IMPACT_THRESHOLD
        else frozenset()
    )
    # A multi-entity request has no single functional currency. Only state a functional
    # amount when every affected entity shares the transaction currency.
    entities = subjects.estimate_version_entities(uow.session, row["id"])
    functional = set(
        uow.session.scalars(
            select(legal_entity.c.functional_currency).where(legal_entity.c.id.in_(entities.ids))
        )
    )
    amount = None
    if len(currencies) == 1 and {str(c).strip() for c in functional} == currencies:
        amount = (
            sum((abs(Decimal(g.catch_up_amount)) for g in impact.groups), Decimal(0)),
            next(iter(currencies)),
        )
    return amount, flags


def _audit(
    uow: UnitOfWork,
    row: dict[str, Any],
    element: dict[str, Any],
    before: str,
    after: str,
    **extra: Any,
) -> None:
    uow.audit(
        action=f"estimate_version.{after.lower()}",
        object_type="estimate_version",
        object_id=row["id"],
        before={"status": before},
        after={"status": after, **extra},
        contract_ids=portfolios.audit_contract_ids(uow.session, element["portfolio_id"]),
    )


def submit(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    comment: str | None,
    check_version: Callable[[int], None],
) -> EstimateVersionOut:
    row, element, currents = _lock(uow, version_id, prepare=True)
    check_version(int(row["row_version"]))
    if str(row["status"]) != "DRAFT":
        raise Problem("invalid-transition", "Only a draft can be submitted.")
    errors = estimates._submission_errors(uow.session, element, currents[0], row)
    if errors:
        raise estimates._failed(errors)
    impact = portfolio_impact.preview(
        uow.session, uow.ctx, element["portfolio_id"], element["id"], version_id, uow.now
    )
    amount, flags = _routing(uow, row, impact)
    with system_entity_scope(uow.session):
        digest = sha256_hex(subjects.estimate_version_content(uow.session, version_id))
    transitions.apply(
        uow.session,
        "estimate_version",
        version_id,
        to_status="SUBMITTED",
        expected_status="DRAFT",
        set_values={"content_sha256": digest, **estimates._stamps(uow)},
    )
    _audit(uow, row, element, "DRAFT", "SUBMITTED", content_sha256=digest)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.ESTIMATE_VERSION,
        subject_id=version_id,
        summary=f"Approve shared {element['element_code']} version {row['version_no']}",
        comment=comment,
        impact_preview=approvals.ImpactPreview(
            before={
                "groups": [
                    {
                        "group_id": str(g.combination_group_id),
                        "currency": g.currency,
                        "members": [
                            {
                                "contract_id": str(m.contract_id),
                                "balances": [b.model_dump(mode="json") for b in m.balances_before],
                            }
                            for m in g.members
                        ],
                    }
                    for g in impact.groups
                ]
            },
            after=impact.model_dump(mode="json"),
        ),
        routing_decision=approvals.route_submission(
            uow, ApprovalSubjectType.ESTIMATE_VERSION, version_id, amount=amount, flags=flags
        ),
    )
    stored = estimates._version_row(uow.session, version_id)
    if str(request["status"]) == "PENDING" and str(stored["status"]) == "SUBMITTED":
        transitions.apply(
            uow.session,
            "estimate_version",
            version_id,
            to_status=None,
            expected_status="SUBMITTED",
            set_values={"approval_request_id": request["id"], **estimates._stamps(uow)},
        )
    return portfolio_estimate_versions.get(
        uow.session, uow.ctx, element["portfolio_id"], element["id"], version_id
    )


def approve(uow: UnitOfWork, version_id: UUID, request_id: UUID) -> None:
    row, element, currents = _lock(uow, version_id, prepare=False)
    if str(row["status"]) != "SUBMITTED":
        raise Problem("invalid-transition", "The shared version is not submitted.")
    approvals.assert_fresh_basis(uow, request_id)
    refusal = estimates._approval_refusal(uow.session, element, currents[0], row)
    if refusal:
        raise Problem("invalid-transition", refusal)
    impact = portfolio_impact.preview(
        uow.session, uow.ctx, element["portfolio_id"], element["id"], version_id, uow.now
    )
    amount, flags = _routing(uow, row, impact)
    requested = uow.session.execute(
        select(
            approval_request.c.amount_functional,
            approval_request.c.amount_currency,
            approval_request.c.flags,
        ).where(approval_request.c.id == request_id)
    ).one()
    prior_amount = (
        None
        if requested.amount_functional is None
        else (Decimal(requested.amount_functional), str(requested.amount_currency).strip())
    )
    if amount != prior_amount or flags != frozenset(requested.flags):
        raise approvals.StaleBasis()
    previous = estimates._approved_versions(uow.session, element["id"], lock=True)
    for old in previous:
        transitions.apply(
            uow.session,
            "estimate_version",
            old["id"],
            to_status="SUPERSEDED",
            expected_status="APPROVED",
            set_values=estimates._stamps(uow),
        )
        _audit(uow, dict(old), element, "APPROVED", "SUPERSEDED", superseded_by=str(version_id))
    transitions.apply(
        uow.session,
        "estimate_version",
        version_id,
        to_status="APPROVED",
        expected_status="SUBMITTED",
        set_values={"approval_request_id": request_id, **estimates._stamps(uow)},
    )
    system = estimates._system_unit(uow)
    event_ids = []
    previous_id = None if not previous else previous[0]["id"]
    for current in currents:
        (event,) = append_events(
            system,
            contract_id=current["id"],
            expected_stream_version=int(current["head_stream_version"]),
            events=[estimates._changed_event(row, previous_id, request_id)],
            origin="SYSTEM",
        )
        event_ids.append(event["id"])
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    transitions.apply(
        uow.session,
        "estimate_version",
        version_id,
        to_status=None,
        expected_status="APPROVED",
        set_values={"applied_event_ids": event_ids, **estimates._stamps(uow)},
    )
    _audit(
        uow,
        row,
        element,
        "SUBMITTED",
        "APPROVED",
        approval_request_id=str(request_id),
        applied_event_ids=[str(e) for e in event_ids],
    )
    try:
        for group_id in sorted({c["combination_group_id"] for c in currents}):
            computation.recompute(uow, group_id, trigger=ComputationTrigger.COMMAND)
    except EngineError as error:
        raise engine_problem(error) from error


def withdraw(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    comment: str | None,
    check_version: Callable[[int], None],
) -> EstimateVersionOut:
    row, element, _ = _lock(uow, version_id, prepare=True)
    check_version(int(row["row_version"]))
    if str(row["status"]) != "SUBMITTED" or row["approval_request_id"] is None:
        raise Problem("invalid-transition", "Only a pending version can be withdrawn.")
    approvals.withdraw(
        uow, approval_request_id=row["approval_request_id"], comment=comment, through_subject=True
    )
    return portfolio_estimate_versions.get(
        uow.session, uow.ctx, element["portfolio_id"], element["id"], version_id
    )

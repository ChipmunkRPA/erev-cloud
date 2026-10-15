"""Native immutable option-term entry before activation review (T-CON-14)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from sqlalchemy import insert, or_, select

from erev_api.audit.writer import record_facts
from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id
from erev_api.db.tables import approval_request, estimate, material_right, obligation
from erev_api.domain.contracts import computation, compute_job, obligations, queries, repo
from erev_api.enums import ComputationStatus
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.obligations import MaterialRightCreateIn, MaterialRightOut
from erev_api.uow import UnitOfWork


def _invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed",
        message,
        errors=[ProblemError(field=field, rule_id="MATERIAL_RIGHT_TERMS", message=message)],
    )


def create(
    uow: UnitOfWork,
    obligation_id: UUID,
    body: MaterialRightCreateIn,
    *,
    expected_stream_version: int | None,
) -> MaterialRightOut:
    session = uow.session
    line = (
        session.execute(select(obligation).where(obligation.c.id == obligation_id))
        .mappings()
        .one_or_none()
    )
    if line is None:
        raise Problem("not-found")
    contract_id = UUID(str(line["contract_id"]))
    group_id, current = repo.lock_group_then_contract(session, contract_id)
    require_for_entity(uow.ctx, "contract.create", current["contracting_entity_id"])
    if expected_stream_version != int(current["head_stream_version"]):
        raise Problem(
            "precondition-failed", "The contract changed. Reload it before entering option terms."
        )
    pending = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.subject_type == "CONTRACT_ACTIVATION",
            approval_request.c.subject_id == contract_id,
            approval_request.c.status == "PENDING",
        )
    ).first()
    if str(current["status"]) != "DRAFT" or pending is not None:
        raise Problem(
            "invalid-transition",
            "Enter option terms on a draft before submitting activation for review.",
        )
    if session.execute(
        select(material_right.c.id).where(material_right.c.obligation_id == obligation_id)
    ).first():
        raise Problem("invalid-transition", "This obligation already has immutable option terms.")
    discount = body.ssp_method == "DISCOUNT_X_LIKELIHOOD"
    for field in (
        "incremental_discount_ratio",
        "expected_purchase_amount",
        "likelihood_estimate_id",
    ):
        present = getattr(body, field) is not None
        if discount and not present:
            raise _invalid(
                field,
                "Discount-times-likelihood requires a discount, expected purchase amount "
                "and likelihood estimate.",
            )
        if not discount and present:
            raise _invalid(field, "This field applies only to Discount times likelihood.")
    if body.ssp_method == "RENEWAL_ALTERNATIVE" and body.option_type != "RENEWAL_OPTION":
        raise _invalid("option_type", "The renewal alternative requires a renewal option.")
    currency = str(current["transaction_currency"]).strip()
    if (
        body.expected_purchase_amount is not None
        and body.expected_purchase_amount.currency != currency
    ):
        raise _invalid(
            "expected_purchase_amount.currency", "Use the contract's transaction currency."
        )
    if body.likelihood_estimate_id is not None:
        found = session.execute(
            select(estimate.c.id).where(
                estimate.c.id == body.likelihood_estimate_id,
                estimate.c.contract_id == contract_id,
                estimate.c.estimate_kind == "EXERCISE_LIKELIHOOD",
                or_(estimate.c.obligation_id.is_(None), estimate.c.obligation_id == obligation_id),
            )
        ).first()
        if found is None:
            raise _invalid(
                "likelihood_estimate_id",
                "Choose an exercise-likelihood estimate of this contract and obligation.",
            )
    right_id = new_id()
    session.execute(
        insert(material_right).values(
            tenant_id=uow.principal.tenant_id,
            id=right_id,
            contract_id=contract_id,
            obligation_id=obligation_id,
            option_type=body.option_type.value,
            ssp_method=body.ssp_method,
            incremental_discount_ratio=None
            if body.incremental_discount_ratio is None
            else Decimal(body.incremental_discount_ratio),
            is_discount_available_without_contract=body.is_discount_available_without_contract,
            expected_purchase_amount=None
            if body.expected_purchase_amount is None
            else Decimal(body.expected_purchase_amount.amount),
            currency=currency,
            expiry_date=body.expiry_date,
            likelihood_estimate_id=body.likelihood_estimate_id,
            is_legacy_quantity_ssp_dollars=False,
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
        )
    )
    target = obligation_subject_key(str(current["external_id"]), str(line["obligation_key"]))
    engine = computation.default_engine()

    def checked(bundle: InputBundle) -> OutputBundle:
        output = engine(bundle)
        kinds = [
            str(item.columns.get("obligation_kind"))
            for book in output.books
            for item in book.obligation_versions
            if item.subject_key == target
        ]
        if not kinds or any(kind != "MATERIAL_RIGHT" for kind in kinds):
            raise _invalid(
                "obligation_id",
                "Option terms require a current material-right obligation in every book.",
            )
        return output

    computed = compute_job.compute_group(uow, group_id, engine=checked)
    if computed.status is not ComputationStatus.SUCCEEDED:
        raise _invalid(
            "ssp_method",
            "These option terms could not be computed. Check the template, SSP "
            "and approved likelihood estimate.",
        )
    record_facts(
        uow,
        action="material_right.create",
        object_type="material_right",
        ids=[right_id],
        contract_id=contract_id,
    )
    return obligations.material_right_out(
        session, obligation_id, params=queries.ReadParams(), now=uow.now
    )

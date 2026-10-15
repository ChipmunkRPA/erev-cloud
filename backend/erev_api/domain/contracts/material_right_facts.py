"""Validated immutable option facts shared by native entry and migration capture.

Callers own authorization, lifecycle locks, computation and audit. A failure must roll back
these facts with the calling command; this helper does not commit or activate a contract.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import insert, or_, select

from erev_api.db import new_id
from erev_api.db.tables import estimate, material_right, obligation
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.obligations import MaterialRightCreateIn
from erev_api.uow import UnitOfWork


def invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed",
        message,
        errors=[ProblemError(field=field, rule_id="MATERIAL_RIGHT_TERMS", message=message)],
    )


def insert_terms(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    obligation_id: UUID,
    currency: str,
    body: MaterialRightCreateIn,
) -> UUID:
    """Insert validated terms for an obligation belonging to this contract and tenant."""
    session = uow.session
    if (
        session.execute(
            select(obligation.c.id).where(
                obligation.c.id == obligation_id,
                obligation.c.contract_id == contract_id,
            )
        ).first()
        is None
    ):
        raise invalid("obligation_id", "Choose an obligation of this contract.")
    discount = body.ssp_method == "DISCOUNT_X_LIKELIHOOD"
    for field in (
        "incremental_discount_ratio",
        "expected_purchase_amount",
        "likelihood_estimate_id",
    ):
        present = getattr(body, field) is not None
        if discount and not present:
            raise invalid(
                field,
                "Discount-times-likelihood requires a discount, expected purchase amount "
                "and likelihood estimate.",
            )
        if not discount and present:
            raise invalid(field, "This field applies only to Discount times likelihood.")
    if body.ssp_method == "RENEWAL_ALTERNATIVE" and body.option_type != "RENEWAL_OPTION":
        raise invalid("option_type", "The renewal alternative requires a renewal option.")
    if (
        body.expected_purchase_amount is not None
        and body.expected_purchase_amount.currency != currency
    ):
        raise invalid(
            "expected_purchase_amount.currency", "Use the contract's transaction currency."
        )
    if body.entered_ssp_amount is not None:
        if body.ssp_method != "ENTERED_AMOUNT":
            raise invalid("entered_ssp_amount", "This field applies only to Entered amount.")
        if body.entered_ssp_amount.currency != currency:
            raise invalid("entered_ssp_amount.currency", "Use the contract's transaction currency.")
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
            raise invalid(
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
            entered_ssp_amount=None
            if body.entered_ssp_amount is None
            else Decimal(body.entered_ssp_amount.amount),
            currency=currency,
            expiry_date=body.expiry_date,
            likelihood_estimate_id=body.likelihood_estimate_id,
            is_legacy_quantity_ssp_dollars=False,
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
        )
    )
    return right_id

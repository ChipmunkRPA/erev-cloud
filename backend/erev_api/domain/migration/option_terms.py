"""Persist POL-212 converted option terms through the native immutable-fact writer."""

from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select

from erev_api.db.tables import obligation
from erev_api.domain.contracts.material_right_facts import insert_terms, invalid
from erev_api.domain.migration.opening_balances import ContractOpening
from erev_api.schemas.obligations import MaterialRightCreateIn
from erev_api.uow import UnitOfWork


def persist(
    uow: UnitOfWork, *, opening: ContractOpening, contract_id: UUID, currency: str
) -> list[UUID]:
    """Write converted totals after booking, before activation/computation, in the caller's UOW.

    Legacy rows do not identify the commercial option subtype, so OTHER preserves that
    absence. They never imply a renewal, likelihood estimate or expiry date. KEEP rows have
    no option record and create no terms. The caller audits only after computation succeeds.
    """
    rows = [row for row in opening.rows if row.mapped.option is not None]
    if not rows:
        return []
    ids = {
        str(row.obligation_key): row.id
        for row in uow.session.execute(
            select(obligation.c.id, obligation.c.obligation_key).where(
                obligation.c.contract_id == contract_id
            )
        )
    }
    written: list[UUID] = []
    for row in rows:
        option = row.mapped.option
        assert option is not None
        if (
            option.ssp_method != "ENTERED_AMOUNT"
            or option.quantity != 1
            or option.is_legacy_quantity_ssp_dollars
        ):
            raise invalid(
                "option_record", "Converted options require quantity one and entered SSP."
            )
        obligation_id = ids.get(row.mapped.obligation_key)
        if obligation_id is None:
            raise invalid("obligation_key", "The converted option has no booked obligation.")
        amount = format(option.option_ssp, "f")
        if "." in amount:
            amount = amount.rstrip("0").rstrip(".")
        try:
            body = MaterialRightCreateIn.model_validate(
                {
                    "option_type": "OTHER",
                    "ssp_method": "ENTERED_AMOUNT",
                    "entered_ssp_amount": {
                        "amount": amount,
                        "currency": currency,
                    },
                }
            )
        except ValidationError as error:
            raise invalid(
                "option_ssp",
                "The converted option SSP cannot be represented as native option terms.",
            ) from error
        written.append(
            insert_terms(
                uow,
                contract_id=contract_id,
                obligation_id=obligation_id,
                currency=currency,
                body=body,
            )
        )
    return written

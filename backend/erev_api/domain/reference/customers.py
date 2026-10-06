"""Customers and related-party groups (04 T-REF-18, T-REF-19, API-R-22; 03 REQ-REF-010,
REQ-REF-011, REQ-CON-010; PRD §2.7; SCREENS §9; BUILD_SPEC RFD-8).

Pure rules and copy, and the membership read that combination detection uses (REQ-CON-010); the
reference commands create and change customers and groups. A customer holds business identity only
(T-REF-19, M-ARCH-01), belongs to at most one related-party group (REQ-REF-011), and its external id
is unique per source system (REQ-REF-010). Customers are deactivated, never deleted (IM-M).
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import customer
from erev_api.domain.reference import entities
from erev_api.problems import ProblemError

RULE_CUSTOMER: Final = "T-REF-19"
RULE_GROUP: Final = "T-REF-18"
# SCREENS §9.5 "Duplicate code".
CODE_TAKEN: Final = "Customer code {code} is already used."
GROUP_CODE_TAKEN: Final = "Another related-party group already uses this code."
EXTERNAL_ID_TAKEN: Final = (
    "Another customer from {source_system} already uses external id {external_id}."
)
EXTERNAL_ID_BLANK: Final = "Enter the external id, or leave it out."
GROUP_UNKNOWN: Final = "Choose an existing related-party group."
PARENT_UNKNOWN: Final = "Choose an existing customer as the parent."
PARENT_CYCLE: Final = "A customer cannot be its own parent or sit below itself."


def country_code_errors(value: str | None) -> list[ProblemError]:
    """ISO 3166-1 alpha-2 in capitals, or no country (SCREENS §9.5 "Country")."""
    if value is None or entities.COUNTRY_CODE.fullmatch(value):
        return []
    return [
        ProblemError(field="country_code", rule_id=RULE_CUSTOMER, message=entities.COUNTRY_FORMAT)
    ]


def related_customer_ids(session: Session, customer_id: UUID) -> list[UUID]:
    """The other customers of ``customer_id``'s related-party group, in code order; empty for a
    customer without a group or unknown to ``session`` (REQ-REF-011; REQ-CON-010 combination
    detection; SCREENS §9.3 "Related customers")."""
    own = select(customer.c.related_party_group_id).where(customer.c.id == customer_id)
    group_id = session.execute(own).scalar_one_or_none()
    if group_id is None:
        return []
    statement = (
        select(customer.c.id)
        .where(customer.c.related_party_group_id == group_id, customer.c.id != customer_id)
        .order_by(customer.c.code)
    )
    return [UUID(str(value)) for value in session.execute(statement).scalars()]

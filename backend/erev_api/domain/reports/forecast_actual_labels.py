"""Freeze actual-line labels at capture; unavailable historical categories stay explicit."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, obligation_version, product


def attach(
    session: Session, rows: Sequence[dict[str, Any]], *, known_at: datetime, book_code: str
) -> list[dict[str, Any]]:
    if not rows:
        return []
    contract_ids = {UUID(row["contract_id"]) for row in rows if row["contract_id"] is not None}
    obligation_ids = {
        UUID(row["obligation_id"]) for row in rows if row["obligation_id"] is not None
    }
    # External contract IDs are fixed by contract admission/replacement (EXTERNAL_ID_FIXED).
    contracts = {
        item.id: item.external_id
        for item in session.execute(
            select(contract.c.id, contract.c.external_id).where(
                contract.c.id.in_(contract_ids),
                contract.c.created_at <= known_at,
            )
        )
    }

    candidates: dict[UUID, set[tuple[UUID, UUID]]] = {}
    for version in session.execute(
        select(
            obligation_version.c.obligation_id,
            obligation_version.c.contract_id,
            obligation_version.c.product_id,
        ).where(
            obligation_version.c.obligation_id.in_(obligation_ids),
            obligation_version.c.book_code == book_code,
            obligation_version.c.created_at <= known_at,
        )
    ):
        candidates.setdefault(version.obligation_id, set()).add(
            (version.contract_id, version.product_id)
        )
    products = {
        row.id: row
        for row in session.execute(
            select(
                product.c.id,
                product.c.revenue_category,
            ).where(
                product.c.id.in_({p for pairs in candidates.values() for _, p in pairs}),
                product.c.created_at <= known_at,
                product.c.updated_at <= known_at,
            )
        )
    }
    result = []
    for row in rows:
        contract_id = None if row["contract_id"] is None else UUID(row["contract_id"])
        obligation_id = None if row["obligation_id"] is None else UUID(row["obligation_id"])
        pairs = candidates.get(obligation_id, set()) if obligation_id else set()
        category_known, category = False, None
        if len(pairs) == 1:
            owner, product_id = next(iter(pairs))
            if owner == contract_id and product_id in products:
                category_known = True
                category = products[product_id].revenue_category
        result.append(
            dict(row)
            | {
                "contract_label_known": contract_id in contracts,
                "contract_external_id": contracts.get(contract_id),
                "revenue_category_known": category_known,
                "revenue_category": category,
            }
        )
    return result

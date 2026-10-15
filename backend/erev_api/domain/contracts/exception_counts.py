"""Current operational exception counts shared by contract headers and list filters.

Count distinct queue items, not repeated occurrences. Subject precedence follows the queue's
contract attribution: a combination suggestion names its payload contracts, an explicit contract
names only that contract, and an otherwise group-bound item names current group members.
An obligation-only item belongs to its owning contract. Tenant/entity RLS remains in force.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, Text, and_, case, cast, exists, func, select

from erev_api.db.tables import combination_group_member, contract, exception_item, obligation


def open_items() -> Select[Any]:
    """A correlated set of open queue items related to the outer contract row."""
    item = exception_item.c
    raw = item.source_payload["contract_ids"]
    suggested_ids = case((func.jsonb_typeof(raw) == "array", raw), else_=func.jsonb_build_array())
    suggested = and_(
        item.code == "COMBINATION_SUGGESTED", func.jsonb_array_length(suggested_ids) > 0
    )
    member = combination_group_member.c
    group_member = exists(
        select(member.contract_id)
        .where(
            member.tenant_id == item.tenant_id,
            member.combination_group_id == item.combination_group_id,
            member.contract_id == contract.c.id,
            member.valid_to_known_at.is_(None),
        )
        .correlate(exception_item, contract)
    )
    owns_obligation = exists(
        select(obligation.c.id)
        .where(
            obligation.c.tenant_id == item.tenant_id,
            obligation.c.id == item.obligation_id,
            obligation.c.contract_id == contract.c.id,
        )
        .correlate(exception_item, contract)
    )
    related = case(
        (suggested, suggested_ids.contains(func.jsonb_build_array(cast(contract.c.id, Text)))),
        (item.contract_id.is_not(None), item.contract_id == contract.c.id),
        (item.obligation_id.is_not(None), owns_obligation),
        else_=group_member,
    )
    return (
        select(item.id)
        .select_from(exception_item)
        .where(
            item.tenant_id == contract.c.tenant_id,
            item.status.in_(("OPEN", "IN_PROGRESS")),
            related,
        )
        .correlate(contract)
    )


def count() -> Any:
    return open_items().with_only_columns(func.count()).scalar_subquery()

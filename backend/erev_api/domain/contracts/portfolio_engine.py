"""Validate retained shared-return inputs before mapping them into native portfolio pins."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from erev_engine.bundle import PortfolioInput
from erev_engine.errors import EngineError


def shared_return_contract(
    version: Mapping[str, Any],
    element: Mapping[str, Any],
    *,
    contracts: Mapping[UUID, Mapping[str, Any]],
    portfolios: Sequence[PortfolioInput],
    obligation_keys: Mapping[UUID, str],
    obligation_owners: Mapping[UUID, UUID],
) -> str:
    """Return a deterministic member identity only when the shared pin is representable.

    Native shared return rates have common obligation keys across their population. Refuse
    asymmetric targets instead of applying one member's selected key to another member.
    Total quantities and breakage need their frozen per-member application, not duplication.
    """

    def refuse(detail: str) -> None:
        raise EngineError("ENGINE_INVARIANT_VIOLATED", detail)

    if str(element["estimate_kind"]) != "RETURN_RATE":
        refuse("Shared breakage requires frozen member allocations before calculation")
    if version["rate"] is None or version["expected_quantity"] is not None:
        refuse("Shared return input requires a rate; total quantities need member allocation")
    selected = next((p for p in portfolios if p.code == str(element.get("portfolio_id"))), None)
    if selected is None or not selected.member_contract_keys:
        refuse("The applied shared estimate has no retained member population")
    assert selected is not None
    members = {
        cid: row
        for cid, row in contracts.items()
        if str(row["external_id"]) in selected.member_contract_keys
    }
    if len(members) != len(selected.member_contract_keys):
        refuse("The applied shared estimate population is incomplete")
    if any(
        str(row["transaction_currency"]).strip() != str(version["currency"]).strip()
        for row in members.values()
    ):
        refuse("Shared return costs require member-currency conversion before calculation")
    targets = {UUID(str(value)) for value in element["target_obligation_ids"] or ()}
    if element["obligation_id"] is not None:
        targets.add(UUID(str(element["obligation_id"])))
    grouped: dict[UUID, set[str]] = {cid: set() for cid in members}
    for target in targets:
        owner = obligation_owners.get(target)
        if owner in contracts and owner not in grouped:
            refuse("A shared estimate target belongs to a nonmember contract")
        if owner in grouped:
            if target not in obligation_keys:
                refuse("A shared estimate target has no retained obligation key")
            grouped[owner].add(obligation_keys[target])
    sets = {frozenset(keys) for keys in grouped.values()}
    if len(sets) != 1 or not next(iter(sets), frozenset()):
        refuse("Shared return estimates require explicit matching targets for every member")
    return min(selected.member_contract_keys)

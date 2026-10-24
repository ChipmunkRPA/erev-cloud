"""Reconstruct the source transfer basis under the caller's group/contract locks."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from typing import Any
from uuid import UUID

from erev_api.domain.contracts import bundles, repo
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from erev_engine.boundary_basis import FixedBoundaryBasis, fixed_boundary_basis
from erev_engine.bundle import InputBundle
from erev_engine.canonical import canonical_bytes


def snapshot(measured: Sequence[FixedBoundaryBasis]) -> dict[str, Any]:
    if not measured:
        raise ValueError("A transfer snapshot requires a measured population")
    first = measured[0]
    return {
        "input_sha256": first.input_sha256,
        "effective_date": first.effective_date.isoformat(),
        "position": first.boundary_position,
        "source_contract": first.contract_key,
        "obligations": {
            item.obligation_key: {
                "allocation_exact": str(item.allocation_exact),
                "recognized_exact": str(item.recognized_exact),
                "remaining_exact": str(item.remaining_exact),
                "allocation_minor": item.allocation_minor,
                "recognized_minor": item.recognized_minor,
                "remaining_minor": item.remaining_minor,
                "remaining_quantity": str(item.remaining_quantity),
                "service_start_date": None
                if item.service_start_date is None
                else item.service_start_date.isoformat(),
                "service_end_date": None
                if item.service_end_date is None
                else item.service_end_date.isoformat(),
            }
            for item in measured
        },
    }


def without_pending_pair(original: InputBundle, pending_pair: frozenset[str]) -> InputBundle:
    # Preparing/submitting this very pair adds draft headers, not source performance.
    # Remove only these unapplied headers; retain every other original input.
    if any(
        event.modification_key in pending_pair
        or str(event.payload.get("modification_id")) in pending_pair
        for event in original.events
    ):
        raise Problem("invalid-transition", "The regroup pair already has an applied source event.")
    return replace(
        original,
        contracts=tuple(
            replace(
                contract,
                modifications=tuple(
                    mod
                    for mod in contract.modifications
                    if mod.modification_key not in pending_pair
                ),
            )
            for contract in original.contracts
        ),
    )


def source_basis(
    original: InputBundle,
    *,
    contract_key: str,
    effective_date: date,
    obligation_keys: tuple[str, ...],
    pending_pair: frozenset[str],
) -> dict[str, Any]:
    value = without_pending_pair(original, pending_pair)
    header = next(c for c in value.contracts if c.external_id == contract_key)
    result = {}
    for book in value.books:
        if header.contracting_entity_code not in book.entity_codes:
            continue
        if book.book_code == "LEGACY":
            raise Problem("invalid-transition", "Legacy transfer basis is unavailable.")
        result[book.book_code] = snapshot(
            fixed_boundary_basis(
                value,
                book_code=book.book_code,
                effective_date=effective_date,
                contract_key=contract_key,
                obligation_keys=obligation_keys,
            )
        )
    return result


def require_fresh(uow: UnitOfWork, rows: Sequence[Mapping[str, Any]]) -> None:
    """Called after pair consistency, while submission/approval holds both groups' locks."""
    if not any((row.get("questionnaire") or {}).get("regroup_source_basis") for row in rows):
        return
    source = next(row for row in rows if str(row["kind"]) == "REMOVE_OBLIGATION")
    target = next(row for row in rows if str(row["kind"]) == "ADD_OBLIGATION")
    current = repo.get_contract(uow.session, UUID(str(source["contract_id"])))
    original = bundles.build(uow.session, UUID(str(current["combination_group_id"])), uow.now)
    actual = source_basis(
        original,
        contract_key=str(current["external_id"]),
        effective_date=source["effective_date"],
        obligation_keys=tuple(str(line["obligation_key"]) for line in source["lines"]),
        pending_pair=frozenset(str(row["id"]) for row in rows),
    )
    if canonical_bytes(actual) != canonical_bytes(source["questionnaire"]["regroup_source_basis"]):
        raise Problem(
            "invalid-transition", "Regroup source inputs changed; rebuild and review both sides."
        )
    receiving = repo.get_contract(uow.session, UUID(str(target["contract_id"])))
    target_input = bundles.build(uow.session, UUID(str(receiving["combination_group_id"])), uow.now)
    expected_target = (source.get("questionnaire") or {}).get("regroup_target_input_sha256")
    if (
        expected_target is not None
        and without_pending_pair(target_input, frozenset(str(row["id"]) for row in rows)).sha256()
        != expected_target
    ):
        raise Problem(
            "invalid-transition", "Regroup target inputs changed; rebuild and review both sides."
        )
    header = next(c for c in target_input.contracts if c.external_id == receiving["external_id"])
    target_books = {
        book.book_code
        for book in target_input.books
        if header.contracting_entity_code in book.entity_codes
    }
    if (
        target_books != set(actual)
        or header.transaction_currency != current["transaction_currency"].strip()
    ):
        raise Problem(
            "invalid-transition", "The target books or currency differ from the transfer basis."
        )

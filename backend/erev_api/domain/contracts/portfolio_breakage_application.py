"""Frozen member/book breakage pins and source freshness at financial application."""

from collections.abc import Mapping
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import obligation_subject_key

from . import portfolio_breakage_basis


def native(
    version: Mapping[str, Any], contracts: Mapping[UUID, Mapping[str, Any]]
) -> dict[str, Any]:
    basis = version.get("portfolio_application_basis") or {}
    snapshots = basis.get("breakage_allocations") or {}
    if not snapshots:
        raise Problem(
            "validation-failed", "Save the shared breakage allocation for every affected book."
        )
    expected_targets = {
        obligation_subject_key(member["contract_key"], key)
        for member in basis.get("members", [])
        if UUID(str(member["contract_id"])) in contracts
        for key in member["obligation_keys"]
    }
    output = {}
    for book, snapshot in sorted(snapshots.items()):
        preview = portfolio_breakage_basis.read(snapshot)
        if (
            str(preview.portfolio_id) != str(basis.get("portfolio_id"))
            or preview.book_code != book
            or str(preview.version_id) != str(version["id"])
            or str(preview.effective_date) != str(version["effective_date"])
            or Fraction(preview.total_breakage_quantity)
            != Fraction(
                str((version.get("parameters") or {}).get("portfolio_total_breakage_quantity"))
            )
        ):
            raise Problem(
                "validation-failed", "Saved breakage allocation differs from the version."
            )
        members = {}
        for share in preview.shares:
            key = obligation_subject_key(share.contract_external_id, share.obligation_key)
            if key not in expected_targets:
                continue
            quantity, forfeited = (
                Fraction(share.entitlement_quantity),
                Fraction(share.breakage_quantity),
            )
            members[key] = {
                "entitlement_quantity": str(quantity),
                "breakage_quantity": str(forfeited),
                "expected_quantity": str(quantity - forfeited),
            }
        if set(members) != expected_targets:
            raise Problem("validation-failed", "Saved breakage allocation omits a member target.")
        output[book] = members
    return {**version, "native_breakage_allocations": output}


def require_fresh(uow: UnitOfWork, element: Mapping[str, Any], version: Mapping[str, Any]) -> None:
    from . import portfolio_preview

    snapshots = (version.get("portfolio_application_basis") or {}).get("breakage_allocations") or {}
    if not snapshots:
        raise Problem(
            "validation-failed", "Save shared breakage allocations before impact or submission."
        )
    for book, snapshot in sorted(snapshots.items()):
        preview = portfolio_preview.preview(
            uow.session,
            uow.ctx,
            element["portfolio_id"],
            element["id"],
            version["id"],
            book,
            uow=uow,
        )
        portfolio_breakage_basis.require_fresh(snapshot, preview)

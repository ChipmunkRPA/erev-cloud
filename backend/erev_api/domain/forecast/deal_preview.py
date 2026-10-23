"""Immutable retained deal previews, idempotent under the worker's reserved preview identity."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, text

from erev_api.controls.release import current_release
from erev_api.db.tables import deal_preview
from erev_api.domain.contracts import bundles
from erev_api.domain.forecast import deal_bundle, deal_compute
from erev_api.problems import Problem
from erev_api.schemas.deal_previews import DealInputIn
from erev_api.uow import UnitOfWork
from erev_engine.canonical import canonical_bytes, sha256_hex


def retain(uow: UnitOfWork, proposal: DealInputIn, identity: UUID) -> dict[str, Any]:
    """Authorize every attempt; reuse only verified evidence for the exact requested proposal.

    The caller owns commit/fencing. A failed computation leaves no preview or scratch contract.
    Canonical engine evidence is retained so future readers need not rerun current configuration.
    """
    deal_bundle.authorize(uow, proposal)
    uow.session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"deal-preview:{uow.principal.tenant_id}:{identity}"},
    )
    existing = (
        uow.session.execute(
            select(deal_preview).where(
                deal_preview.c.tenant_id == uow.principal.tenant_id, deal_preview.c.id == identity
            )
        )
        .mappings()
        .one_or_none()
    )
    proposed = proposal.model_dump(mode="json")
    if existing is not None:
        row = dict(existing)
        if (
            row["input"].get("proposal") != proposed
            or sha256_hex(row["input"]) != row["input_sha256"]
            or sha256_hex(row["result"]) != row["result_sha256"]
        ):
            raise Problem(
                "precondition-failed", "The retained preview does not match its evidence."
            )
        return row
    release = current_release()
    if release is None:
        raise Problem("invalid-transition", "An engine release must be registered before preview.")
    bundle, found = deal_bundle.resolve(uow, proposal, identity)
    computed = deal_compute.compute(bundle)
    if release.engine_version != computed.output.engine_version:
        raise Problem(
            "precondition-failed", "The preview engine differs from its registered release."
        )
    inputs = json.loads(canonical_bytes({"proposal": proposed, "engine_bundle": computed.input}))
    result = json.loads(canonical_bytes(computed.output))
    pins = bundles.pinned_refs(uow.session, computed.input, found, computed.output)
    row = {
        "tenant_id": uow.principal.tenant_id,
        "id": identity,
        "input": inputs,
        "input_sha256": sha256_hex(inputs),
        "result": result,
        "result_sha256": sha256_hex(result),
        "engine_release_id": release.id,
        "pinned_refs": pins,
        "saved_contract_id": None,
        "created_at": uow.now,
        "created_by": uow.principal.id,
        "created_by_kind": uow.principal.kind.value,
    }
    uow.session.execute(insert(deal_preview).values(**row))
    uow.audit(
        contract_id=None,  # A hypothetical deal has no saved contract yet.
        action="deal_preview.run",
        object_type="deal_preview",
        object_id=identity,
        after={
            "proposal": proposed,
            "input_sha256": row["input_sha256"],
            "result_sha256": row["result_sha256"],
            "engine_release_id": str(release.id),
            "pinned_refs": pins,
        },
    )
    return row

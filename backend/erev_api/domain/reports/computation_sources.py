"""Verify retained computation inputs for internal report replay.

This returns engine inputs, never a downloadable artifact. The complete contract group must
remain readable. No missing source is reconstructed from current configuration or live events.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID

from erev_engine import upgrade
from erev_engine.bundle import InputBundle
from sqlalchemy import select

from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    combination_group,
    computation_evidence,
    contract,
    contract_computation,
    contract_version,
    legal_entity,
    obligation_version,
)
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class VerifiedComputation:
    computation_id: UUID
    group_id: UUID
    engine_release_id: UUID
    bundle: InputBundle
    output: Mapping[str, Any]
    output_sha256: str
    ledger_cutoff: Mapping[str, int]
    previous_computation_id: UUID | None


def _refuse(reason: str) -> Problem:
    return Problem(
        "validation-failed",
        "The retained computation cannot be used for report replay.",
        errors=[
            ProblemError(
                rule_id=reason, message="Retained computation evidence failed verification."
            )
        ],
    )


def _read_file(uow: UnitOfWork, row: Mapping[Any, Any], name: str) -> bytes:
    expected = FilePurpose.COMPUTATION_INPUT if name == "input" else FilePurpose.COMPUTATION_OUTPUT
    try:
        meta, stream = open_file(
            uow.session, row[f"{name}_file_id"], files=uow.files, keyring=uow.keyring
        )
    except FileNotFoundError as error:
        raise _refuse(f"{name.upper()}_EVIDENCE_MISSING") from error
    except Problem as error:
        if error.slug != "not-found":
            raise
        raise _refuse(f"{name.upper()}_EVIDENCE_MISSING") from error
    with stream:
        content = stream.read()
    digest = hashlib.sha256(content).hexdigest()
    if (
        meta["purpose"] != expected
        or meta["media_type"] != "application/json"
        or meta["size_bytes"] != len(content)
        or meta["sha256"] != digest
        or row[f"{name}_file_sha256"] != digest
    ):
        raise _refuse(f"{name.upper()}_EVIDENCE_HASH_MISMATCH")
    return content


def read_for_report(uow: UnitOfWork, computation_id: UUID) -> VerifiedComputation:
    """Read a complete, currently authorized group, verifying both stored source copies.

    Report workers must supply their authorized human principal. SYSTEM has no implicit
    reader grant. Source identities are checked before file access; the decoded bundle's
    entity and contract population is checked again before returning it to internal replay.
    """
    principal = uow.principal
    scopes = []
    for permission in ("report.run",):
        scope = principal.permission_scopes.get(permission)
        if permission not in principal.permissions or scope is None or scope == frozenset():
            raise Problem("forbidden")
        if scope != "*":
            scopes.append(scope)
    visible_entities = {
        row.id: row.code
        for row in uow.session.execute(
            select(legal_entity.c.id, legal_entity.c.code).where(
                legal_entity.c.tenant_id == principal.tenant_id
            )
        )
        if all(row.id in scope for scope in scopes)
    }
    source = (
        uow.session.execute(
            select(contract_computation).where(
                contract_computation.c.tenant_id == principal.tenant_id,
                contract_computation.c.id == computation_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        raise Problem("not-found")
    try:
        members = {UUID(key): int(value) for key, value in source["stream_heads"].items()}
    except (ValueError, TypeError, AttributeError) as error:
        raise Problem("not-found") from error
    # Read complete identities under tenant scope, then require every identity to be in the
    # caller's original visible scope. Partial RLS results must never look like a complete group.
    with system_entity_scope(uow.session):
        contracts = uow.session.execute(
            select(contract.c.id, contract.c.external_id, contract.c.contracting_entity_id).where(
                contract.c.tenant_id == principal.tenant_id, contract.c.id.in_(members)
            )
        ).all()
        versions = uow.session.execute(
            select(
                contract_version.c.id,
                contract_version.c.book_code,
                contract_version.c.output_sha256,
            ).where(
                contract_version.c.tenant_id == principal.tenant_id,
                contract_version.c.contract_computation_id == computation_id,
            )
        ).all()
        entities = set(
            uow.session.execute(
                select(obligation_version.c.performing_entity_id).where(
                    obligation_version.c.tenant_id == principal.tenant_id,
                    obligation_version.c.contract_version_id.in_([row.id for row in versions]),
                )
            ).scalars()
        )
    entities.update(row.contracting_entity_id for row in contracts)
    if (
        not members
        or {row.id for row in contracts} != set(members)
        or not entities <= visible_entities.keys()
    ):
        raise Problem("not-found")
    if source["status"] != "SUCCEEDED":
        raise _refuse("COMPUTATION_NOT_SUCCEEDED")
    evidence = (
        uow.session.execute(
            select(computation_evidence).where(
                computation_evidence.c.tenant_id == principal.tenant_id,
                computation_evidence.c.contract_computation_id == computation_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if evidence is None:
        raise _refuse("INPUT_EVIDENCE_MISSING")
    input_bytes = _read_file(uow, evidence, "input")
    output_bytes = _read_file(uow, evidence, "output")
    try:
        bundle = upgrade.decode_input(input_bytes)
        output = upgrade.output_mapping(output_bytes)
    except (ValueError, TypeError, KeyError) as error:
        raise _refuse("COMPUTATION_EVIDENCE_CODEC_INVALID") from error
    if (
        bundle.sha256() != source["input_sha256"]
        or evidence["input_sha256"] != source["input_sha256"]
    ):
        raise _refuse("LOGICAL_HASH_MISMATCH")
    if (
        evidence["codec"]
        != {"format_version": bundle.format_version, "engine_version": bundle.engine_version}
        or bundle.engine_version != source["engine_version"]
        or bundle.known_at != source["cutoff_at"]
        or output.get("engine_version") != source["engine_version"]
        or output.get("input_sha256") != source["input_sha256"]
    ):
        raise _refuse("COMPUTATION_SOURCE_IDENTITY_MISMATCH")
    expected_heads = {row.external_id: members[row.id] for row in contracts}
    actual_heads: dict[str, int] = {}
    for event in bundle.events:
        actual_heads[event.contract_key] = max(
            actual_heads.get(event.contract_key, 0), event.stream_version
        )
    group_code = uow.session.execute(
        select(combination_group.c.code).where(
            combination_group.c.tenant_id == principal.tenant_id,
            combination_group.c.id == source["combination_group_id"],
        )
    ).scalar_one_or_none()
    if (
        actual_heads != expected_heads
        or set(bundle.group.member_contract_keys) != set(expected_heads)
        or {member.external_id for member in bundle.contracts} != set(expected_heads)
        or bundle.group.group_key != group_code
    ):
        raise _refuse("COMPUTATION_SOURCE_IDENTITY_MISMATCH")
    if not {entity.code for entity in bundle.entities} <= set(visible_entities.values()):
        raise Problem("not-found")
    hashes = {row.output_sha256 for row in versions}
    books = {row.book_code for row in versions}
    if (
        hashes != {evidence["output_sha256"]}
        or evidence["output_file_sha256"] != evidence["output_sha256"]
        or set(evidence["book_codes"]) != books
        or len(evidence["book_codes"]) != len(books)
    ):
        raise _refuse("EXPECTED_HASH_DISAGREEMENT")
    cutoffs = evidence["ledger_cutoff"]
    if (
        not isinstance(cutoffs, dict)
        or set(cutoffs) != {book.book_code for book in bundle.books}
        or any(type(value) is not int or value < 0 for value in cutoffs.values())
    ):
        raise _refuse("COMPUTATION_LEDGER_CUTOFF_INVALID")
    predecessor = evidence["previous_computation_id"]
    previous_heads: dict[str, int] = {}
    if predecessor is not None:
        previous = (
            uow.session.execute(
                select(contract_computation).where(
                    contract_computation.c.tenant_id == principal.tenant_id,
                    contract_computation.c.id == predecessor,
                    contract_computation.c.combination_group_id == source["combination_group_id"],
                    contract_computation.c.status == "SUCCEEDED",
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous is None or predecessor == computation_id:
            raise _refuse("COMPUTATION_PREDECESSOR_MISMATCH")
        by_id = {str(row.id): row.external_id for row in contracts}
        previous_heads = {
            by_id[key]: int(value)
            for key, value in previous["stream_heads"].items()
            if key in by_id
        }
    if tuple(sorted(previous_heads.items())) != bundle.group.previous_stream_heads:
        raise _refuse("COMPUTATION_PREDECESSOR_MISMATCH")
    return VerifiedComputation(
        computation_id=computation_id,
        group_id=source["combination_group_id"],
        engine_release_id=source["engine_release_id"],
        bundle=bundle,
        output=MappingProxyType(output),
        output_sha256=evidence["output_sha256"],
        ledger_cutoff=MappingProxyType(dict(cutoffs)),
        previous_computation_id=evidence["previous_computation_id"],
    )

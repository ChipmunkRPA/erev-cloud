"""The destructive commands on a file are bound to the legal entities of the records that
reference it (item FILE-SHRED-SCOPE-1, parts B3 and B5; the supervisor's ruling of 2026-10-01 on
the independent review of the ``EVIDENCE_SHRED`` merge 58eba434; 04 T-PLT-29 "Shred scope" and
API-R-12 rev 1.225; 05 §6.17 PRV-07 rev 1.164; 03 REQ-PLT-012; ruling R-28).

``file.shred`` asked for ``settings.manage`` at any scope and looked at holds only, so Una —
Tenant Admin for one entity — destroyed a document that only records of another entity
referenced and none held (B3); and where a record of the other entity did hold the file, the 409
told her which — "the source of import IMP-…" — and wrote it into a ``DENIED`` event, on the
direct path and on ``request-shred`` (B5).

The world is rows where the product has no light command for them — two legal entities with a
contract each, attachments and imports — and the stored files are real objects with a wrapped
key. Four people through the product: Tess, Tenant Admin for every entity; Una, Tenant Admin
for North alone; Carla, Controller of every entity, who reads the documents; Carl, Controller
for North alone, who decides what is asked of North.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import engine as approvals_engine
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    file_attachment,
    file_object,
)
from erev_api.domain.platform import evidence_shred, file_evidence, privacy
from erev_api.enums import FilePurpose
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, get, post, reject, slug
from support.rows import insert_contract_rows, insert_import_upload
from support.stored_files import Stored, store

FILES = "/api/v1/files"
REASON = "DSR-2026-0917: erase the person's data in this document"
SCOPE_RULE = "T-PLT-10"
# What Una is refused, by part. B3: no record holds the file, and before the rule she shredded it.
BEYOND_HER_SCOPE = (
    "south-letter",  # attached to a contract of South
    "shared-letter",  # attached to a contract of each entity
    "voided-letter",  # attached to North, and to South by an attachment since voided
    "loose-upload",  # no record references it
    "south-upload",  # the source of an import that names South
    "open-upload",  # the source of an import whose entities are not resolved
)
# B5: a record of South holds the file, and before the rule the refusal named it.
HELD_BY_SOUTH = ("south-submitted", "south-committed")
WITHIN_HER_SCOPE = ("north-letter", "north-upload")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@dataclass(frozen=True, slots=True)
class World:
    """A workspace of two legal entities, its four people and its stored files by name."""

    tenant_id: UUID
    south_id: UUID
    tess: Actor
    una: Actor
    carla: Actor
    carl: Actor
    stored: Mapping[str, Stored]
    import_no: Mapping[str, str]  # the number of the import that owns a source, by file name


def _attach(
    session: Any, tenant_id: UUID, stored: Stored, contract_id: UUID, **values: Any
) -> None:
    session.execute(
        insert(file_attachment).values(
            tenant_id=tenant_id,
            id=uuid4(),
            file_object_id=stored.id,
            subject_type="contract",
            subject_id=contract_id,
            created_by_kind="SYSTEM",
            **values,
        )
    )


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> World:
    root = member(keyring, clock, name="tess")
    assign(root, "tenant_admin")
    tenant_id = root.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id)
        south = insert_contract_rows(session, tenant_id)
    una_member = colleague(tenant_id, "una")
    assign(una_member, "tenant_admin", entity_ids=[north.entity_id])
    carla_member = colleague(tenant_id, "carla")
    assign(carla_member, "controller")
    carl_member = colleague(tenant_id, "carl")
    assign(carl_member, "controller", entity_ids=[north.entity_id])

    def keep(purpose: FilePurpose, *names: str) -> dict[str, Stored]:
        return {
            name: store(tenant_id, purpose, name, clock=clock, keyring=keyring, files=files)
            for name in names
        }

    stored = {
        **keep(
            FilePurpose.ATTACHMENT,
            "north-letter",
            "south-letter",
            "shared-letter",
            "voided-letter",
            "loose-upload",
        ),
        **keep(
            FilePurpose.IMPORT_SOURCE,
            "north-upload",
            "south-upload",
            "open-upload",
            "south-submitted",
            "south-committed",
            "north-committed",
        ),
    }
    # (status, the entities the upload names: None = not resolved, which is every entity)
    imports: dict[str, tuple[str, list[UUID] | None]] = {
        "north-upload": ("UPLOADED", [north.entity_id]),
        "south-upload": ("UPLOADED", [south.entity_id]),
        "open-upload": ("UPLOADED", None),
        "south-submitted": ("SUBMITTED", [south.entity_id]),
        "south-committed": ("COMMITTED", [south.entity_id]),
        "north-committed": ("COMMITTED", [north.entity_id]),
    }
    import_no = {name: f"IMP-9{index:05d}" for index, name in enumerate(imports, start=1)}
    with tenant_session(_context(tenant_id)) as session:
        _attach(session, tenant_id, stored["north-letter"], north.contract_id)
        _attach(session, tenant_id, stored["south-letter"], south.contract_id)
        _attach(session, tenant_id, stored["shared-letter"], north.contract_id)
        _attach(session, tenant_id, stored["shared-letter"], south.contract_id)
        _attach(session, tenant_id, stored["voided-letter"], north.contract_id)
        _attach(
            session,
            tenant_id,
            stored["voided-letter"],
            south.contract_id,
            voided_at=clock.now(),
            voided_by_kind="SYSTEM",
            void_reason="Attached to the wrong contract.",
        )
        for name, (status, named) in imports.items():
            insert_import_upload(
                session,
                tenant_id=tenant_id,
                file_object_id=stored[name].id,
                status=status,
                named_entity_ids=named,
                import_no=import_no[name],
            )
    return World(
        tenant_id=tenant_id,
        south_id=south.entity_id,
        tess=enrolled(app, clock, root),
        una=enrolled(app, clock, una_member),
        carla=enrolled(app, clock, carla_member),
        carl=enrolled(app, clock, carl_member),
        stored=stored,
        import_no=import_no,
    )


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _file(world: World, name: str) -> dict[str, Any]:
    (row,) = _rows(
        world.tenant_id,
        select(file_object.c.sha256, file_object.c.purpose, file_object.c.shredded_at).where(
            file_object.c.id == world.stored[name].id
        ),
    )
    return row


def _denied(world: World, *names: str) -> list[tuple[str, str, dict[str, Any]]]:
    """(file name, action, detail) of the ``DENIED`` events on the named files, in chain order."""
    name_of = {world.stored[name].id: name for name in names}
    return [
        (name_of[row["object_id"]], str(row["action"]), dict(row["detail"]))
        for row in _rows(
            world.tenant_id,
            select(audit_event.c.object_id, audit_event.c.action, audit_event.c.detail)
            .where(audit_event.c.outcome == "DENIED", audit_event.c.object_id.in_(list(name_of)))
            .order_by(audit_event.c.chain_seq),
        )
    ]


def _shred(app: FastAPI, actor: Actor, world: World, name: str) -> HttpResponse:
    return post(app, f"{FILES}/{world.stored[name].id}/shred", actor, {"reason": REASON})


def _request(app: FastAPI, actor: Actor, world: World, name: str) -> HttpResponse:
    return post(app, f"{FILES}/{world.stored[name].id}/request-shred", actor, {"reason": REASON})


def _answer(response: HttpResponse) -> tuple[int, str | None]:
    """(status, problem) — no problem for an answer that is none, so that a command that did
    what it was asked shows as that in a comparison."""
    return (response.status_code, slug(response) if response.status_code >= 400 else None)


def _scope_detail(world: World, name: str) -> dict[str, Any]:
    """The detail of the ``DENIED`` event of a scope refusal: the rule, the file's own facts and
    the reason given — no record and no entity."""
    row = _file(world, name)
    return {
        "rule_id": SCOPE_RULE,
        "sha256": str(row["sha256"]),
        "purpose": str(getattr(row["purpose"], "value", row["purpose"])),
        "reason": REASON,
        "permission": privacy.SHRED_PERMISSION,
    }


def _held(response: HttpResponse, rule: str, record: str) -> None:
    """409 by reference: the refusal names the record that holds the file."""
    assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
    (error,) = response.json()["errors"]
    assert error["rule_id"] == rule, error
    assert f"This file is {record}." in str(error["message"]), error


def test_file_shred_scope_1_the_direct_shred_is_bound_to_the_entities_of_the_files_records(
    app: FastAPI, world: World
) -> None:
    """B3. Una holds ``settings.manage`` for North alone. She shreds a file that only records of
    North reference; every other file is refused 403 ``forbidden`` by the scope rule, with a
    ``DENIED`` event that names no record, and stays as it was: a file a record of South
    references — alone, beside a record of North, or by an attachment since voided — a file no
    record references, and the source of an import that names South or whose entities are not
    resolved. Tess, who holds it for every entity, shreds each of them."""
    una, tess = world.una, world.tess
    answers = {name: _shred(app, una, world, name) for name in BEYOND_HER_SCOPE}
    assert {name: _answer(answer) for name, answer in answers.items()} == {
        name: (403, "forbidden") for name in BEYOND_HER_SCOPE
    }
    for name, answer in answers.items():
        body = answer.json()
        assert body["detail"] == privacy.SHRED_BEYOND_SCOPE, name
        assert [(error["rule_id"], error["message"]) for error in body["errors"]] == [
            (SCOPE_RULE, privacy.SHRED_BEYOND_SCOPE)
        ], name
        assert _file(world, name)["shredded_at"] is None, name
    # The documents are still read by the people who read their records.
    for name in ("south-letter", "shared-letter", "voided-letter", "south-upload", "open-upload"):
        served = get(app, f"{FILES}/{world.stored[name].id}/content", world.carla)
        assert served.status_code == 200, (name, served.text)
        assert served.content == world.stored[name].content, name
    # Each attempt is on the audit log as the command refused, by the rule and nothing more.
    assert _denied(world, *BEYOND_HER_SCOPE) == [
        (name, privacy.SHRED_ACTION, _scope_detail(world, name)) for name in BEYOND_HER_SCOPE
    ]

    # Positive controls: what only records of North reference is hers to shred ...
    for name in WITHIN_HER_SCOPE:
        done = _shred(app, una, world, name)
        assert done.status_code == 200, (name, done.text)
        assert _file(world, name)["shredded_at"] is not None, name
    # ... and the administrator of every entity shreds each file Una was refused.
    for name in BEYOND_HER_SCOPE:
        done = _shred(app, tess, world, name)
        assert done.status_code == 200, (name, done.text)
        assert _file(world, name)["shredded_at"] is not None, name


def test_file_shred_scope_1_a_refusal_names_no_record_outside_the_callers_scope(
    app: FastAPI, world: World
) -> None:
    """B5. A record of South holds the file: the source of an import that is submitted (no
    override) or committed (lifted by an approval). Una, who administers North alone, is
    answered the scope refusal on both commands — the direct shred and the request — and neither
    the answer nor its ``DENIED`` event carries the import's number. The refusal by reference
    stays for a caller whose scope covers the record: Tess is told the record on both commands,
    and Una is told the record of North that holds a file of hers."""
    una, tess = world.una, world.tess
    asked = {
        (command.__name__, name): command(app, una, world, name)
        for name in HELD_BY_SOUTH
        for command in (_shred, _request)
    }
    assert {
        key: (*_answer(answer), world.import_no[key[1]] in answer.text)
        for key, answer in asked.items()
    } == {key: (403, "forbidden", False) for key in asked}
    for (command, name), answer in asked.items():
        line = (
            privacy.SHRED_BEYOND_SCOPE
            if command == _shred.__name__
            else approvals_engine.OUTSIDE_SCOPE_DETAIL
        )
        assert answer.json()["detail"] == line, (command, name)
    # One DENIED event per attempt, under the command's own action, by the scope rule: the file
    # and the reason, never the record that holds it.
    denied = _denied(world, *HELD_BY_SOUTH)
    assert denied == [
        (name, action, _scope_detail(world, name))
        for name in HELD_BY_SOUTH
        for action in (privacy.SHRED_ACTION, "file_object.request_shred")
    ]
    for name, _action, detail in denied:
        assert world.import_no[name] not in json.dumps(detail), detail

    # Positive controls. Tess's scope covers the records, and she is told which hold the file.
    submitted = (
        f"the source of import {world.import_no['south-submitted']}, which is submitted for "
        "approval or being committed"
    )
    committed = f"the source of committed import {world.import_no['south-committed']}"
    _held(_shred(app, tess, world, "south-submitted"), file_evidence.RULE_EVIDENCE_HELD, submitted)
    _held(
        _request(app, tess, world, "south-submitted"), file_evidence.RULE_EVIDENCE_HELD, submitted
    )
    _held(
        _shred(app, tess, world, "south-committed"), file_evidence.RULE_APPROVAL_REQUIRED, committed
    )
    opened = _request(app, tess, world, "south-committed")
    assert opened.status_code == 200, opened.text
    # Una's scope covers North: the record that holds her file is named to her, and she asks.
    own = f"the source of committed import {world.import_no['north-committed']}"
    _held(_shred(app, una, world, "north-committed"), file_evidence.RULE_APPROVAL_REQUIRED, own)
    asked_for = _request(app, una, world, "north-committed")
    assert asked_for.status_code == 200, asked_for.text
    for name in (*HELD_BY_SOUTH, "north-committed"):
        assert _file(world, name)["shredded_at"] is None, name


def test_file_shred_scope_1_the_decision_names_no_record_that_came_to_hold_the_file(
    app: FastAPI, world: World
) -> None:
    """B5, at the decision. A request names the records that hold the file, and its decider's
    scope covers their entities — not those of a record that comes to hold the file afterwards.
    Una asks for the source of a committed import of North; then the same file becomes the
    source of an import of South that is submitted, which holds it without override. Carl,
    Controller for North alone, is refused because the holds are no longer the request's
    (``PRV-07``), and the answer does not carry the number of South's import; the request stays
    PENDING, undecided, and nothing is shredded. Positive controls: Carl rejects the request, a
    new request is refused to Tess by reference — her scope covers South — and a request whose
    holds stand is approved and shreds."""
    una, tess, carl = world.una, world.tess, world.carl
    asked = _request(app, una, world, "north-committed")
    assert asked.status_code == 200, asked.text
    request_id = str(asked.json()["approval_request_id"])
    came_later = "IMP-900077"
    with tenant_session(_context(world.tenant_id)) as session:
        insert_import_upload(
            session,
            tenant_id=world.tenant_id,
            file_object_id=world.stored["north-committed"].id,
            status="SUBMITTED",
            named_entity_ids=[world.south_id],
            import_no=came_later,
        )

    decided = approve(app, request_id, carl)
    assert (*_answer(decided), came_later in decided.text) == (409, "invalid-transition", False)
    assert [(error["rule_id"], error["message"]) for error in decided.json()["errors"]] == [
        ("PRV-07", evidence_shred.HOLDS_CHANGED)
    ]
    (request,) = _rows(
        world.tenant_id,
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id)),
    )
    assert request["status"] == "PENDING"
    assert (
        _rows(
            world.tenant_id,
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == UUID(request_id)
            ),
        )
        == []
    )
    assert _file(world, "north-committed")["shredded_at"] is None

    # Positive controls. The request is closed by rejecting it ...
    assert reject(app, request_id, carl, "Another import rests on the file.").status_code == 200
    # ... a new one is refused by reference to a requester whose scope covers the record ...
    _held(
        _request(app, tess, world, "north-committed"),
        file_evidence.RULE_EVIDENCE_HELD,
        f"the source of import {came_later}, which is submitted for approval or being committed",
    )
    # ... and a request whose holds stand is approved by a Controller of its entity, and shreds.
    standing = _request(app, tess, world, "south-committed")
    assert standing.status_code == 200, standing.text
    done = approve(app, str(standing.json()["approval_request_id"]), world.carla)
    assert done.status_code == 200, done.text
    assert _file(world, "south-committed")["shredded_at"] is not None

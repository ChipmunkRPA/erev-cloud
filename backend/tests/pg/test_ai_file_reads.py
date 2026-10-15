"""Derived AI text rechecks source access instead of granting access through a proposal."""

from __future__ import annotations

from dataclasses import replace

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_proposal, file_attachment, file_object, tenant
from erev_api.domain.platform import file_access
from erev_api.enums import FilePurpose, PrincipalKind, TenantKind
from sqlalchemy import insert, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    RowContext,
    ai_proposal_row,
    file_attachment_row,
    file_object_values,
    insert_contract_rows,
)

pytestmark = pytest.mark.pg


def test_ai_text_requires_current_source_and_ai_permission(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    other = tenant_id_of(tenant_factory(keyring=keyring))
    user_id = new_id()
    principal = replace(
        system_principal(tenant_id),
        kind=PrincipalKind.USER,
        id=user_id,
        permissions=frozenset({"ai.use"}),
        permission_scopes={"ai.use": "*"},
    )
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="ai-file-read",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with tenant_session(DbContext(tenant_id, user_id, "*")) as session:
        source = file_object_values(tenant_id, created_by=user_id, created_by_kind="USER")
        session.execute(insert(file_object).values(**source))
        texts = []
        for kind, source_id in (
            ("CONTRACT_EXTRACTION", source["id"]),
            ("QA_ANSWER", source["id"]),
            ("CONTRACT_EXTRACTION", None),
        ):
            derived = file_object_values(tenant_id, purpose=FilePurpose.AI_DOCUMENT_TEXT)
            session.execute(insert(file_object).values(**derived))
            row = ai_proposal_row(RowContext(tenant_id, user_id), session) | {
                "kind": kind,
                "file_object_id": source_id,
                "document_text_file_id": derived["id"],
            }
            session.execute(insert(ai_proposal).values(**row))
            texts.append(derived)
        assert file_access.bound(session, ctx, source["id"]) is not None
        assert file_access.bound(session, ctx, texts[0]["id"]) is not None
        for derived in texts[1:]:
            assert file_access.bound(session, ctx, derived["id"]) is None
        # A non-uploader holding ai.use receives no new source or derived-file grant.
        stranger = replace(ctx, principal=replace(principal, id=new_id()))
        assert file_access.bound(session, stranger, source["id"]) is None
        assert file_access.bound(session, stranger, texts[0]["id"]) is None
        contract = insert_contract_rows(session, tenant_id)
        attachment = file_attachment_row(RowContext(tenant_id, user_id), session) | {
            "subject_type": "contract",
            "subject_id": contract.contract_id,
            "file_object_id": source["id"],
        }
        session.execute(insert(file_attachment).values(**attachment))
        reader = replace(
            stranger,
            principal=replace(
                stranger.principal,
                permissions=frozenset({"ai.use", "contract.read"}),
                permission_scopes={"ai.use": "*", "contract.read": frozenset({contract.entity_id})},
            ),
        )
        assert file_access.bound(session, reader, texts[0]["id"]) is not None
        wrong_entity = replace(
            reader,
            principal=replace(
                reader.principal,
                permission_scopes={"ai.use": "*", "contract.read": frozenset({new_id()})},
            ),
        )
        assert file_access.bound(session, wrong_entity, texts[0]["id"]) is None
        session.execute(
            update(file_attachment)
            .where(file_attachment.c.id == attachment["id"])
            .values(
                voided_at=clock.now(),
                voided_by=user_id,
                voided_by_kind="USER",
                void_reason="Removed access",
            )
        )
        assert file_access.bound(session, reader, texts[0]["id"]) is None
        no_ai = replace(
            ctx, principal=replace(principal, permissions=frozenset(), permission_scopes={})
        )
        assert file_access.bound(session, no_ai, source["id"]) is not None
        assert file_access.bound(session, no_ai, texts[0]["id"]) is None
        operator = replace(ctx, principal=replace(principal, kind=PrincipalKind.OPERATOR))
        assert file_access.bound(session, operator, texts[0]["id"]) is None
        # Malformed derived-to-derived links cannot recurse or expose text.
        loop = ai_proposal_row(RowContext(tenant_id, user_id), session) | {
            "kind": "CONTRACT_EXTRACTION",
            "file_object_id": texts[2]["id"],
            "document_text_file_id": texts[2]["id"],
        }
        session.execute(insert(ai_proposal).values(**loop))
        assert file_access.bound(session, ctx, texts[2]["id"]) is None
        session.execute(
            update(tenant)
            .where(tenant.c.id == tenant_id)
            .values(ai_disabled_at=clock.now(), ai_disabled_by_kind="SYSTEM")
        )
        assert file_access.bound(session, ctx, texts[0]["id"]) is not None
        session.execute(
            update(file_object)
            .where(file_object.c.id == source["id"])
            .values(
                shredded_at=clock.now(),
                shredded_by=user_id,
                shredded_by_kind="USER",
                shred_reason="Synthetic approved erasure test",
            )
        )
        assert file_access.bound(session, ctx, texts[0]["id"]) is None
    with tenant_session(DbContext(other, user_id, "*")) as session:
        foreign_ctx = replace(ctx, principal=replace(principal, tenant_id=other))
        assert file_access.bound(session, foreign_ctx, texts[0]["id"]) is None
    assert file_access.referencing_scopes(tenant_id, texts[0]["id"]) == [file_access.EVERY_ENTITY]

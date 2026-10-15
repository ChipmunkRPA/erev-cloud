"""The proposal timestamp bounds an application index scan under tenant RLS."""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_proposal
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.plans import bound_by, plan, scan
from support.rows import RowContext, ai_proposal_row

pytestmark = pytest.mark.pg


def test_proposal_date_bounds_index_before_enum_filters(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant, None, "*")) as session:
        row = ai_proposal_row(RowContext(tenant, new_id()), session)
        session.execute(insert(ai_proposal).values(**row))
        statement = (
            select(ai_proposal.c.id)
            .where(
                ai_proposal.c.created_at >= row["created_at"],
                ai_proposal.c.kind == "QA_ANSWER",
                ai_proposal.c.status == "proposed",
            )
            .order_by(ai_proposal.c.created_at)
        )
        assert session.scalars(statement).all() == [row["id"]]
    node = scan(plan(tenant, statement), "ai_proposal")
    bound_by(node, "ix_ai_proposal__status", "created_at")
    assert "kind" in node["Filter"] and "status" in node["Filter"]


def test_proposal_expiry_bounds_index_under_rls(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant, None, "*")) as session:
        row = ai_proposal_row(RowContext(tenant, new_id()), session)
        session.execute(insert(ai_proposal).values(**row))
        statement = (
            select(ai_proposal.c.id, ai_proposal.c.row_version)
            .where(
                ai_proposal.c.tenant_id == tenant,
                ai_proposal.c.expires_at <= row["expires_at"],
                ai_proposal.c.status == "proposed",
            )
            .order_by(ai_proposal.c.expires_at, ai_proposal.c.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        assert session.scalars(statement).all() == [row["id"]]
    node = scan(plan(tenant, statement), "ai_proposal")
    bound_by(node, "ix_ai_proposal__expiry", "expires_at")

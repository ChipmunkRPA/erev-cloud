"""D-98 140-A3 R2 composed with CTR-17 Q-3 (MAIN DEFECT 2, 2026-09-21; 04 rev 1.80): the T-CON-05
``contract_event.modification_id`` column keeps ``fk_contract_event__modification`` (0068) — an id
that names no T-CON-06 row is refused by name at the database layer, NULL is admitted. The
legacy-template ``CONTRACT_AMENDED`` stores NULL and carries its synthetic id in the payload (the
legacy_v1 witnesses); a native event stores its row id (tests/domain/contracts,
test_modifications.py)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract_event
from sqlalchemy import exc, insert
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import contract_event_values, insert_contract_rows

pytestmark = pytest.mark.pg  # DG-TST-07: every module under tests/pg carries the pg marker

FK: str = "fk_contract_event__modification"


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def test_fk_contract_event__modification_refuses_an_unlinked_id_and_admits_null(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(_context(tenant_id)) as session:
        rows = insert_contract_rows(session, tenant_id, head_stream_version=1)
        values = dict(
            contract_id=rows.contract_id, contracting_entity_id=rows.entity_id, stream_version=1
        )
        with pytest.raises(exc.IntegrityError) as info:
            with session.begin_nested():
                session.execute(
                    insert(contract_event).values(
                        **contract_event_values(tenant_id, modification_id=uuid4(), **values)
                    )
                )
        assert getattr(info.value.orig, "sqlstate", None) == "23503"  # foreign_key_violation
        assert FK in str(info.value.orig)
        # NULL — the legacy-template event's stored form — is admitted.
        session.execute(
            insert(contract_event).values(
                **contract_event_values(tenant_id, modification_id=None, **values)
            )
        )

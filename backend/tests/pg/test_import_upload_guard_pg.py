"""DB-03 on ``import_upload``: the two columns that scope an upload are written once (04 T-IMP-02
rev 1.107 ``named_entity_ids``, rev 1.147 ``uploader_scopes``; revisions 0087 and 0102; supervisor
rulings R-29, R-98 and R-109 (a)). PostgreSQL-bound: the ``erev_app`` role against the installed
trigger ``tg_import_upload__transition``.

The independent review of merge 4ac6c1d1 listed the set-once trigger of revision 0087 among the
rule branches without a test at database level: a second write refused, and a first write in a
late status, which the trigger admits — the validation job, not the database, ties the first
write to VALIDATING. ``uploader_scopes`` is stricter: it is outside the updatable column list
and without a column grant, so it is what the INSERT wrote, for ever.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import file_object, import_upload
from erev_api.enums import FilePurpose
from sqlalchemy import exc, insert, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import file_object_values, import_upload_values

pytestmark = pytest.mark.pg


def _upload(context: DbContext, **values: Any) -> UUID:
    """An UPLOADED upload of a stored file, inserted as the application role inserts it."""
    with tenant_session(context) as session:
        stored = file_object_values(context.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
        session.execute(insert(file_object).values(**stored))
        row = import_upload_values(context.tenant_id, file_object_id=stored["id"], **values)
        session.execute(insert(import_upload).values(**row))
    return UUID(str(row["id"]))


def _stored(context: DbContext, upload_id: UUID, column: str) -> Any:
    with tenant_session(context, read_only=True) as session:
        return session.execute(
            select(import_upload.c[column]).where(import_upload.c.id == upload_id)
        ).scalar_one()


def _refused(context: DbContext, upload_id: UUID, **values: Any) -> str:
    """The database's refusal of an UPDATE of the upload by the application role."""
    with pytest.raises(exc.DBAPIError) as refused, tenant_session(context) as session:
        session.execute(
            update(import_upload).where(import_upload.c.id == upload_id).values(**values)
        )
    return str(refused.value.orig)


def test_named_entity_ids_is_written_once(committed_db: TestDatabase, keyring: KeyRing) -> None:
    """Revision 0087: NULL until the validation result names the entities; then final — an
    emptied or widened set is refused, and so is a second write of the same kind (``'{}'``, the
    tenant-level set, is as final as a named one). The trigger does not tie the first write to
    a status: an upload already DIFF_READY may still receive it, which is why an upload that was
    in flight when the column arrived stays NULL — unresolved, every entity — unless the
    validation job writes it."""
    del committed_db
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    first, second = new_id(), new_id()

    upload_id = _upload(context)
    assert _stored(context, upload_id, "named_entity_ids") is None
    with tenant_session(context) as session:
        session.execute(
            update(import_upload)
            .where(import_upload.c.id == upload_id)
            .values(named_entity_ids=[first])
        )
    assert _stored(context, upload_id, "named_entity_ids") == [first]
    for again in ([first, second], [], None):
        message = _refused(context, upload_id, named_entity_ids=again)
        assert "EREV-TRN-001" in message and "named_entity_ids" in message, message
    assert _stored(context, upload_id, "named_entity_ids") == [first]

    # The empty set is final too.
    level_id = _upload(context)
    with tenant_session(context) as session:
        session.execute(
            update(import_upload).where(import_upload.c.id == level_id).values(named_entity_ids=[])
        )
    message = _refused(context, level_id, named_entity_ids=[first])
    assert "EREV-TRN-001" in message and "named_entity_ids" in message, message
    assert _stored(context, level_id, "named_entity_ids") == []

    # A first write in a late status is admitted by the database.
    late_id = _upload(context, status="DIFF_READY")
    with tenant_session(context) as session:
        session.execute(
            update(import_upload)
            .where(import_upload.c.id == late_id)
            .values(named_entity_ids=[second])
        )
    assert _stored(context, late_id, "status") == "DIFF_READY"
    assert _stored(context, late_id, "named_entity_ids") == [second]


def test_uploader_scopes_is_what_the_insert_wrote(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """Revision 0102: the codes the creating token carried are written with the row and never
    change — not widened, not narrowed, not cleared, and not given to an upload that has none.
    The application role is refused by the transition guard (the column is outside its updatable
    list) or, where the statement touches nothing else, by the missing column grant."""
    del committed_db
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    carried = ["contract.read", "import.upload"]

    upload_id = _upload(context, uploader_scopes=carried)
    assert _stored(context, upload_id, "uploader_scopes") == carried
    for changed in ([*carried, "contract.create"], ["import.upload"], None):
        message = _refused(context, upload_id, uploader_scopes=changed)
        assert "uploader_scopes" in message or "permission denied" in message, message
    assert _stored(context, upload_id, "uploader_scopes") == carried

    person_id = _upload(context)
    assert _stored(context, person_id, "uploader_scopes") is None
    message = _refused(context, person_id, uploader_scopes=carried)
    assert "uploader_scopes" in message or "permission denied" in message, message
    assert _stored(context, person_id, "uploader_scopes") is None

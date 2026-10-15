"""Only an approved database request may confer authority on a composed child action."""

from pathlib import Path
from typing import Any

import pytest
from erev_api.approvals import engine
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_approval_request
from tests.pg.test_migration_capture_pg import _ctx

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("status", list(ApprovalRequestStatus))
def test_composition_requires_an_approved_stored_request(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: ApprovalRequestStatus,
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    hashed: list[str] = []

    def matching_content(*args: Any, **kwargs: Any) -> str:
        hashed.append("content")
        return "a" * 64

    monkeypatch.setattr(engine, "current_content_sha256", matching_content)
    with unit_of_work(
        _ctx(tenant_id, clock), clock=clock, keyring=keyring, files=LocalFileStore(tmp_path)
    ) as uow:
        subject_id = new_id()
        request_id = insert_approval_request(
            uow.session,
            tenant_id=tenant_id,
            status=status,
            subject_id=subject_id,
            subject_type=ApprovalSubjectType.IMPORT_COMMIT.value,
            subject_content_sha256="a" * 64,
        )
        before = tuple(uow.audit_events)
        if status is ApprovalRequestStatus.APPROVED:
            consumed = engine.consume_fresh_basis(
                uow,
                request_id,
                subject_type=ApprovalSubjectType.IMPORT_COMMIT,
                subject_id=subject_id,
                keys=["NEW-CONTRACT"],
                bases={"NEW-CONTRACT": None},
            )
            assert consumed.covers(uow, key="NEW-CONTRACT", approval_request_id=request_id)
            assert hashed == ["content"]
        else:
            with pytest.raises(Problem) as refused:
                engine.consume_fresh_basis(
                    uow,
                    request_id,
                    subject_type=ApprovalSubjectType.IMPORT_COMMIT,
                    subject_id=subject_id,
                    keys=["NEW-CONTRACT"],
                )
            assert refused.value.slug == "invalid-transition"
            assert status.value in str(refused.value)
            assert hashed == []
        assert tuple(uow.audit_events) == before

"""SCH-13 / SCH-14 database-bound witnesses (record §4.25; D-98 138-A2 — authored here, NOT RUN on
the lane: the integrated batch measures them). The CPU witnesses of both tasks live in
``tests/unit/test_partition_window_check.py`` and ``tests/unit/test_file_orphan_sweep.py``; these
exercise the parts that need the database — the partition catalogue read, the key-lock reference
guard under the tenant's RLS, the tenant directory and the composed ``run``."""

from __future__ import annotations

import io
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.controls import partition_window as sch13
from erev_api.controls.doctor import PARTITION_COLUMNS
from erev_api.domain.platform.provisioning import TenantProvisionResult
from erev_api.enums import FilePurpose, TenantKind
from erev_api.files import sweep as sch14
from erev_api.files.store import LocalFileStore, storage_key_lock_id, store_file
from erev_api.jobs.context import JobRuntime
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase

NOW = datetime(2026, 9, 21, 3, 40, tzinfo=UTC)


def _csv_body() -> bytes:
    """Content for one upload through the real ``store_file``.

    D-98 138-A3: it must be admitted by the upload policy (ATTACHMENT admits text/csv; a `.txt`
    name has no extension mapping and is refused `upload-type-not-allowed` before the key lock,
    row insert and commit). And it must be content no other test of the session stored (ruling
    R-60 (e)): ``store_file`` answers a second upload of the same bytes — same tenant, same
    purpose — with the retained row of the first, whose object lives under the file root of the
    test that stored it. The ``acme`` tenant is session-scoped and the ``tmp_path`` roots are
    not, so with one shared body the second test of the session looked for its "referenced"
    object in a root that never held it."""
    return f"code,name\nA,Alpha\nB,{secrets.token_hex(8)}\n".encode("ascii")


def _tenant_id(acme: TenantProvisionResult) -> UUID:
    return UUID(str(acme.tenant["id"]))


@contextmanager
def _uow(
    tenant_id: UUID, clock: FrozenClock, keyring: KeyRing, files: LocalFileStore
) -> Iterator[UnitOfWork]:
    context = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="sch-periodics-witness",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(context, clock=clock, keyring=keyring, files=files) as uow:
        yield uow


def test_sch_13_reads_the_partition_catalogue_and_is_clean_to_2032(
    test_database: TestDatabase,
) -> None:
    """The real catalogue: 04 §1.6 rule 1 creates the PT-MPE / PT-MOC partitions through 2032-12,
    so at FROZEN_AT the 24-month horizon holds for every parent and the check logs INFO."""
    checked = sch13.check(now=FROZEN_AT)
    assert checked.level == "info" and checked.result.ok, checked.result.failures
    assert checked.result.summary.startswith("every partition window ends after")
    # The observation names every partitioned parent (the doctor's PARTITION_COLUMNS).
    assert not [f for f in checked.result.failures if "no partition window observation" in f]
    assert len(PARTITION_COLUMNS) == 3


def test_sch_14_reference_guard_holds_the_key_lock_and_answers_from_the_tenant_rows(
    acme: TenantProvisionResult, keyring: KeyRing, tmp_path: Path
) -> None:
    """The guard re-reads the tenant's ``file_object`` rows under ``lock_storage_key``: a stored
    file is referenced, an unknown key is not, and while the guard is open another session cannot
    take the key's advisory lock (``pg_try_advisory_xact_lock`` false)."""
    tenant_id = _tenant_id(acme)
    clock = frozen_clock(FROZEN_AT)
    files = LocalFileStore(tmp_path / "files")
    with _uow(tenant_id, clock, keyring, files) as uow:
        row = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(_csv_body()),  # admitted content with a matching extension (UPL)
            original_filename="referenced.csv",
            media_type="text/csv",
        )
        uow.commit()
    key = str(row["storage_key"])
    with sch14.reference_guard(tenant_id, key) as has_row:
        assert has_row is True
        with _uow(tenant_id, clock, keyring, files) as other:
            taken = other.session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": storage_key_lock_id(key)},
            ).scalar_one()
            assert taken is False  # the guard holds the key's lock
    with sch14.reference_guard(tenant_id, f"{tenant_id}/ATTACHMENT/{'f' * 64}") as has_row:
        assert has_row is False


def test_sch_14_tenant_directory_names_the_provisioned_tenant(acme: TenantProvisionResult) -> None:
    assert _tenant_id(acme) in sch14.tenant_directory()


def test_sch_14_run_deletes_an_aged_orphan_and_keeps_a_referenced_object(
    acme: TenantProvisionResult, keyring: KeyRing, tmp_path: Path
) -> None:
    """The composed task over a local store and the real tenant rows: a 25-hour-old object with
    no ``file_object`` row goes (object then sidecar), a referenced object of the same age stays,
    and the report says so."""
    tenant_id = _tenant_id(acme)
    clock = frozen_clock(NOW)
    files = LocalFileStore(tmp_path / "files")
    with _uow(tenant_id, clock, keyring, files) as uow:
        row = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(_csv_body()),
            original_filename="kept.csv",
            media_type="text/csv",
        )
        uow.commit()
    referenced = str(row["storage_key"])
    orphan = f"{tenant_id}/ATTACHMENT/{'a' * 64}"
    files.put_object(orphan, io.BytesIO(b"orphan"))
    files.put_object(orphan + ".dek", io.BytesIO(b"dek"))
    old = (NOW - timedelta(hours=25)).timestamp()
    for key in (referenced, orphan, orphan + ".dek"):
        os.utime(files._path(key), (old, old))  # noqa: SLF001 — the store's own path resolution
    report = sch14.run(JobRuntime(clock=clock, keyring=keyring, files=files))
    assert report.deleted == (orphan,) and report.sidecars_deleted == (orphan + ".dek",)
    assert report.kept_referenced == (referenced,)
    assert not files.exists(orphan) and not files.exists(orphan + ".dek")
    assert files.exists(referenced)

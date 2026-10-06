"""A stored file for a test world: the object, its wrapped key and its ``file_object`` row, written
by the store's own function as the SYSTEM principal (04 T-PLT-29; 05 PRV-06, UPL-02).

The worlds that are about the stored object itself — what a shred destroys, what a copy shares —
need real bytes under a real key, and no route of their own to bring them in. The content is of a
type the purpose admits and unique, as a content identity is.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from uuid import UUID, uuid4

from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.enums import FilePurpose, TenantKind
from erev_api.files.store import LocalFileStore, store_file
from erev_api.uow import unit_of_work

PDF = b"%PDF-1.4\n"


@dataclass(frozen=True, slots=True)
class Stored:
    """A stored file and the bytes it was stored with."""

    id: UUID
    content: bytes


def store(
    tenant_id: UUID,
    purpose: FilePurpose,
    name: str,
    *,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    kind: TenantKind = TenantKind.PRODUCTION,
    content: bytes | None = None,
) -> Stored:
    """Store a file of ``purpose`` in ``tenant_id`` and commit: a CSV for an import source, a
    PDF otherwise, each with a mark of its own — or ``content``, for a world that stores bytes
    a second time (the store then answers the row those bytes already have)."""
    mark = f"{name} {uuid4()}".encode()
    fresh, filename, media_type = (
        (b"account,amount\n" + mark + b",1.00\n", f"{name}.csv", "text/csv")
        if purpose is FilePurpose.IMPORT_SOURCE
        else (PDF + b"% " + mark + b"\n", f"{name}.pdf", "application/pdf")
    )
    content = fresh if content is None else content
    ctx = RequestContext(
        principal=system_principal(tenant_id, on_behalf_of_id=None),
        tenant_kind=kind,
        request_id="tests-stored-file",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        row = store_file(
            uow,
            purpose=purpose,
            stream=io.BytesIO(content),
            original_filename=filename,
            media_type=media_type,
        )
        uow.commit()
    return Stored(UUID(str(row["id"])), content)

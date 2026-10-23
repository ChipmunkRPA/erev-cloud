"""Typed input/output evidence written before a computation's own ledger postings.

Existing computations are never backfilled from current data. New files retain the complete
input, including its cutoff and typed payload values; raw and logical hashes remain distinct.
"""

from __future__ import annotations

import hashlib
import io
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import insert, select

from erev_api.db.tables import computation_evidence, ledger_chain_head
from erev_api.domain.contracts import fx_input_freshness
from erev_api.enums import FilePurpose
from erev_api.files.store import store_file
from erev_engine import upgrade
from erev_engine.bundle import InputBundle, OutputBundle

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork


def retain(
    uow: UnitOfWork,
    bundle: InputBundle,
    output: OutputBundle,
    *,
    computation_id: UUID,
    previous_computation_id: UUID | None,
) -> None:
    """Persist original digests and files in the caller's transaction, before posting."""
    input_bytes = upgrade.encode_input(bundle)
    output_bytes = upgrade.encode_output(output)
    input_sha256 = bundle.sha256()
    output_sha256 = output.sha256()
    if output.input_sha256 != input_sha256 or output.engine_version != bundle.engine_version:
        raise ValueError("Computation evidence does not match its input bundle")
    input_digest = hashlib.sha256(input_bytes).hexdigest()
    output_digest = hashlib.sha256(output_bytes).hexdigest()
    if output_digest != output_sha256:
        raise ValueError("Computation output evidence differs from its logical hash")
    books = [book.book_code for book in output.books if book.contract_version is not None]
    cutoffs = {
        str(row.book_code): int(row.last_chain_seq)
        for row in uow.session.execute(
            select(ledger_chain_head.c.book_code, ledger_chain_head.c.last_chain_seq).where(
                ledger_chain_head.c.tenant_id == uow.principal.tenant_id,
                ledger_chain_head.c.book_code.in_([book.book_code for book in bundle.books]),
            )
        )
    }
    if set(cutoffs) != {book.book_code for book in bundle.books}:
        raise ValueError("Computation evidence requires every book's ledger cutoff")
    files = []
    for purpose, content, digest in (
        (FilePurpose.COMPUTATION_INPUT, input_bytes, input_digest),
        (FilePurpose.COMPUTATION_OUTPUT, output_bytes, output_digest),
    ):
        row = store_file(
            uow,
            purpose=purpose,
            stream=io.BytesIO(content),
            original_filename=f"{computation_id}-{purpose.value.lower()}.json",
            media_type="application/json",
        )
        if row["sha256"] != digest or row["size_bytes"] != len(content):
            raise ValueError("Stored computation evidence metadata differs from original bytes")
        files.append(row["id"])
    uow.session.execute(
        insert(computation_evidence).values(
            tenant_id=uow.principal.tenant_id,
            contract_computation_id=computation_id,
            input_file_id=files[0],
            input_file_sha256=input_digest,
            input_sha256=input_sha256,
            output_file_id=files[1],
            output_file_sha256=output_digest,
            output_sha256=output_sha256,
            book_codes=books,
            codec={
                "format_version": bundle.format_version,
                "engine_version": bundle.engine_version,
            },
            fx_inputs=fx_input_freshness.capture(bundle),
            ledger_cutoff=cutoffs,
            previous_computation_id=previous_computation_id,
            captured="AT_COMPUTATION",
            backfill_verification_id=None,
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
        )
    )

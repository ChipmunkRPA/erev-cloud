"""A balanced, correctly sealed ledger fixture written against schema 0150.

Migration refusal tests need historical rows, not the current writer against an old schema.
The 0150 seal contains every physical line column except generated dr_cr, with no server stamp.
"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from erev_api.db.tables import subledger_line, subledger_posting, subledger_posting_seal
from erev_api.domain.journals import subledger
from erev_engine.canonical import canonical_bytes
from sqlalchemy import insert, text
from sqlalchemy.orm import Session
from support.rows import (
    PROBE_RECORDED_AT,
    LedgerRows,
    insert_ledger_parts,
    subledger_line_values,
    subledger_posting_values,
)


def insert_legacy_ledger(session: Session, tenant_id: UUID) -> LedgerRows:
    parts = insert_ledger_parts(session, tenant_id)
    posting = subledger_posting_values(tenant_id, parts=parts)
    session.execute(insert(subledger_posting).values(**posting))
    lines = [
        subledger_line_values(
            tenant_id, posting=posting, parts=parts, amount=amount, subject_key="legacy-fixture"
        )
        for amount in (Decimal("10.00"), Decimal("-10.00"))
    ]
    session.execute(insert(subledger_line), lines)
    stored = tuple(
        dict(row)
        for row in session.execute(
            text(
                "SELECT * FROM erev.subledger_line WHERE tenant_id=:tenant "
                "AND subledger_posting_id=:posting"
            ),
            {"tenant": tenant_id, "posting": posting["id"]},
        ).mappings()
    )
    assert len(stored) == 2 and all("recorded_server_at" not in row for row in stored)
    totals = subledger.control_totals(stored)
    document = {
        "posting": subledger._document(posting, subledger.HEADER_MEMBERS),
        "control_totals": [subledger._plain(dict(item)) for item in totals],
        "lines": [
            subledger._document(row, tuple(name for name in row if name != "dr_cr"))
            for row in sorted(stored, key=lambda item: str(item["id"]))
        ],
    }
    digest = sha256(canonical_bytes(document)).hexdigest()
    session.execute(
        insert(subledger_posting_seal).values(
            tenant_id=tenant_id,
            subledger_posting_id=posting["id"],
            book_code=posting["book_code"],
            line_count=2,
            control_totals=totals,
            prev_seal_sha256=None,
            seal_sha256=digest,
            sealed_at=PROBE_RECORDED_AT,
            **{key: posting[key] for key in ("created_at", "created_by", "created_by_kind")},
        )
    )
    return LedgerRows(parts=parts, posting=posting, lines=stored, seal_sha256=digest)

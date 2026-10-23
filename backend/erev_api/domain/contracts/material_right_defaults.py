"""Option-entry defaults from the same pinned policy inputs used by computation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from erev_api.domain.contracts import bundles, obligations
from erev_api.schemas.obligations import MaterialRightDefaultsOut, MaterialRightMethodDefault
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.state import PolicyResolver


def read(session: Session, obligation_id: UUID, *, known_at: datetime) -> MaterialRightDefaultsOut:
    line = obligations.obligation_row(session, obligation_id)
    header = line["contract"]
    bundle = bundles.build(session, header["combination_group_id"], known_at)
    contract_key = str(header["external_id"])
    subject = obligation_subject_key(contract_key, str(line["obligation_key"]))
    books = []
    for book in bundle.books:
        if book.book_code == "LEGACY":
            continue
        policy = PolicyResolver(book.policies).resolved(
            "material_right.ssp_method", contract=contract_key, obligation=subject
        )
        books.append(
            MaterialRightMethodDefault.model_validate(
                dict(
                    book=book.book_code,
                    method=policy.value,
                    level=policy.level,
                    source=policy.source_ref,
                )
            )
        )
    methods = {book.method for book in books}
    return MaterialRightDefaultsOut(
        method=books[0].method if len(methods) == 1 else None, books=books
    )

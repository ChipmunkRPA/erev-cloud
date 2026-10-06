"""The detail subledger: postings, lines, seals and ledger chains (04 T-SL-01 to T-SL-04, §14.1
DB-06, DB-07, §14.3, §15.3 API-R-36; dev-guide DG-CMD-10, DG-TST-22; 05 RCP-05, RCP-21;
ENGINE_SPEC_B §14.2 S14-R-12, S14-R-15; 03 REQ-JE-006; BUILD_SPEC CTR-3).

``post`` writes one posting in the caller's unit of work: the ``subledger_posting`` row, its lines
and its seal. A posting whose ``(book_code, idempotency_key)`` exists is not written again
(``ux_subledger_posting__idempotency``; research 06 P9), so a retried persist cannot double post.
The application computes ``seal_sha256`` over ``prev_seal_sha256 ‖ canonical(posting header,
control totals, lines sorted by id)`` (T-SL-02) — the lines as they are STORED: the DB-07 guard
decides ``is_post_reopen`` from the period's state row it reads ``FOR SHARE``, so ``post`` takes
that value back from the insert and reads no period state of its own (04 §14.1, the DB-06 note,
rev 1.140; supervisor ruling R-97 (1)). The DB-06 seal trigger checks the balance per entry,
overwrites the control totals with the same figures, and extends the book's chain under the
``ledger_chain_head`` row lock. ``verify_ledger_chain`` recomputes every seal of a book in chain
order and names the first sequence that fails (DG-TST-22).

[J] L3-1-Q-29: the hashed documents hold every stored column except the generated ``dr_cr``;
decimals are written without trailing zeros, so a value read back at the column scale hashes as
the value written. The control totals group by entity, period and transaction currency, ordered by
the text of their ids and the currency, with amounts as ``erev.money`` text.

The subject key (supervisor ruling R-11 as amended; 04 T-SL-04 rev 1.282). A line stores the
subject of the entry it belongs to, as the engine keys it (``PostingIntent.subject_key``;
ENGINE_SPEC_B S14-R-12), inside its sealed document, and the read-back of posted amounts answers
it (``contracts.bundles._posted``; 05 RCP-05). ``post`` is the one door to the table: every
caller inside ``erev_api`` passes ``require_subject_key=True``. The column is nullable for the
lines a test builder writes; such a line reads back in the spelling of decision L3-1-Q-32.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.currencies import ISO_4217
from sqlalchemy import Select, and_, insert, or_, select
from sqlalchemy.orm import Session

from erev_api.audit.writer import record_facts
from erev_api.auth.principal import RequestContext
from erev_api.controls.ledger_chain_registry import register_ledger_chain_verifier
from erev_api.db import locking, new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    book,
    contract,
    gl_account,
    ledger_chain_head,
    legal_entity,
    obligation,
    period,
    subledger_line,
    subledger_line_event,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.journals import completeness
from erev_api.enums import BookCode, ControlResult, SubledgerPostingKind
from erev_api.money import money_out
from erev_api.problems import Problem
from erev_api.schemas.subledger import (
    ControlTotalOut,
    SubledgerFxRateOut,
    SubledgerLineLinksOut,
    SubledgerLineOut,
    SubledgerPostingOut,
    SubledgerSealOut,
)

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

__all__ = [
    "EVENT",
    "POSTING_CLASSES",
    "TIME",
    "LedgerChainVerification",
    "LineFilters",
    "Posted",
    "adjustment_key",
    "compute_key",
    "control_totals",
    "dimension_set_sha256",
    "get_posting",
    "ledger_chain_head_rows",
    "line_outs",
    "list_lines",
    "post",
    "release_key",
    "seal_sha256",
    "verify_ledger_chain",
]

EVENT: Final = "EVENT"
TIME: Final = "TIME"
# 05 RCP-05, ENGINE_SPEC_B S14-R-04: the posting class of each E-31 posting kind.
POSTING_CLASSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        SubledgerPostingKind.ENGINE_COMPUTE.value: EVENT,
        SubledgerPostingKind.MANUAL_ADJUSTMENT.value: EVENT,
        SubledgerPostingKind.VOID_REVERSAL.value: EVENT,
        SubledgerPostingKind.CLOSE_RELEASE.value: TIME,
        SubledgerPostingKind.FX_REMEASUREMENT.value: TIME,
        SubledgerPostingKind.NETTING_RECLASS.value: TIME,
    }
)
POSTING_OBJECT: Final = "subledger_posting"
LINE_OBJECT: Final = "subledger_line"
SEAL_OBJECT: Final = "subledger_posting_seal"
# T-SL-01 header members in the seal hash; ``created_txid`` names a transaction, not content.
HEADER_MEMBERS: Final = (
    "id",
    "tenant_id",
    "book_code",
    "posting_kind",
    "combination_group_id",
    "contract_computation_id",
    "close_run_id",
    "manual_adjustment_id",
    "reverses_posting_id",
    "idempotency_key",
    "description",
    "created_at",
    "created_by",
    "created_by_kind",
)
# T-SL-04 members in the seal hash: every stored column but the generated ``dr_cr``.
LINE_MEMBERS: Final = tuple(
    column.name for column in subledger_line.columns if column.name != "dr_cr"
)
_LINE_DEFAULTS: Final[Mapping[str, Any]] = MappingProxyType(
    {"dimensions": {}, "is_post_reopen": False}
)
# T-SL-12: a line mapping may carry the ordered ids of the first-included events of its cumulative
# delta (S14-R-13a); not a T-SL-04 member, so the seal document is unchanged.
LINE_EVENTS_KEY: Final = "contract_event_ids"
SUBJECT_KEY: Final = "subject_key"  # T-SL-04: the subject of the line's entry (ruling R-11)
TOTAL_QUANTUM: Final = Decimal("0.0001")  # erev.money scale (TY-01)
POSTABLE_STATES: Final = frozenset({"open", "closing", "reopened"})


def compute_key(computation_id: uuid.UUID) -> str:
    """T-SL-01 idempotency key of an engine computation's posting."""
    return f"compute:{computation_id}"


def release_key(close_run_id: uuid.UUID, group_id: uuid.UUID) -> str:
    """T-SL-01 idempotency key of a close-release computation's posting."""
    return f"release:{close_run_id}:{group_id}"


def adjustment_key(manual_adjustment_id: uuid.UUID) -> str:
    """T-SL-01 idempotency key of the ``MANUAL_ADJUSTMENT`` posting of an approved manual journal
    or reclassification (04 T-SL-05 ``subledger_posting_id``; BUILD_SPEC CLO-12): approving the
    same adjustment twice posts once."""
    return f"adjustment:{manual_adjustment_id}"


def void_key(contract_event_id: uuid.UUID) -> str:
    """T-SL-01 idempotency key of the ``VOID_REVERSAL`` posting of a ``CONTRACT_VOIDED`` event
    (REQ-CON-015; BUILD_SPEC CTR-11): a retry of the same void is a no-op."""
    return f"void:{contract_event_id}"


def ledger_chain_head_rows(tenant_id: uuid.UUID, *, now: datetime) -> list[dict[str, Any]]:
    """04 §14.3: one ``ledger_chain_head`` per book, before any seal (BS-D-12)."""
    return [
        {
            "tenant_id": tenant_id,
            "book_code": code.value,
            "last_chain_seq": 0,
            "last_seal_sha256": None,
            "updated_at": now,
        }
        for code in (BookCode.ASC606, BookCode.IFRS15, BookCode.LEGACY)
    ]


def dimension_set_sha256(dimensions: Mapping[str, str]) -> str:
    """T-SL-04: the SHA-256 of the sorted dimension object."""
    return sha256_hex({str(key): str(value) for key, value in dimensions.items()})


def _money_text(value: Decimal) -> str:
    return format(value.quantize(TOTAL_QUANTUM), "f")


def control_totals(lines: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """T-SL-02 ``control_totals`` of ``lines``, in the order and form the seal trigger stores."""
    groups: dict[tuple[str, str, str], list[Decimal]] = {}
    for line in lines:
        key = (str(line["entity_id"]), str(line["period_id"]), str(line["txn_currency"]).strip())
        totals = groups.setdefault(key, [Decimal(0), Decimal(0), Decimal(0), Decimal(0)])
        txn = Decimal(line["amount_txn"])
        functional = Decimal(line["amount_functional"])
        if txn > 0:
            totals[0] += txn
        elif txn < 0:
            totals[1] -= txn
        if functional > 0:
            totals[2] += functional
        elif functional < 0:
            totals[3] -= functional
    return [
        {
            "entity_id": entity_id,
            "period_id": period_id,
            "currency": currency,
            "debit_txn": _money_text(totals[0]),
            "credit_txn": _money_text(totals[1]),
            "debit_functional": _money_text(totals[2]),
            "credit_functional": _money_text(totals[3]),
        }
        for (entity_id, period_id, currency), totals in sorted(groups.items())
    ]


def _plain(value: object) -> object:
    """A hashable document value: decimals without trailing zeros, enum literals, trimmed codes."""
    if isinstance(value, Enum):
        return _plain(value.value)
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, str):
        return value.rstrip()
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _document(row: Mapping[str, Any], members: Sequence[str]) -> dict[str, object]:
    return {name: _plain(row.get(name, _LINE_DEFAULTS.get(name))) for name in members}


def line_event_rows(
    tenant_id: uuid.UUID,
    lines: Sequence[Mapping[str, Any]],
    line_rows: Sequence[Mapping[str, Any]],
    stamps: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """The T-SL-12 rows of ``lines``: one per (line, first-included event) in set order, stamped
    like the lines (S14-R-13a; 04 rev 1.37). A line without ``contract_event_ids`` (a single-event
    or manual line) contributes none; a repeated id is a bundle-assembly defect."""
    rows: list[dict[str, Any]] = []
    for line, row in zip(lines, line_rows, strict=True):
        seen: set[uuid.UUID] = set()
        for ordinal, event_id in enumerate(line.get(LINE_EVENTS_KEY) or (), start=1):
            event_uuid = uuid.UUID(str(event_id))
            if event_uuid in seen:
                raise ValueError(f"line {row['id']} names event {event_uuid} twice (S14-R-13a)")
            seen.add(event_uuid)
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "subledger_line_id": row["id"],
                    "subledger_line_period_end_date": row["period_end_date"],
                    "contract_event_id": event_uuid,
                    "ordinal": ordinal,
                    **stamps,
                }
            )
    return rows


def seal_sha256(
    prev_seal_sha256: str | None,
    posting: Mapping[str, Any],
    totals: Sequence[Mapping[str, Any]],
    lines: Sequence[Mapping[str, Any]],
) -> str:
    """T-SL-02: SHA-256 over ``prev_seal_sha256 ‖ canonical(posting header, control totals, lines
    sorted by id)``; the first seal of a book hashes the empty previous seal."""
    document = {
        "posting": _document(posting, HEADER_MEMBERS),
        "control_totals": [_plain(dict(item)) for item in totals],
        "lines": [
            _document(line, LINE_MEMBERS) for line in sorted(lines, key=lambda row: str(row["id"]))
        ],
    }
    digest = hashlib.sha256()
    digest.update((prev_seal_sha256 or "").strip().encode("ascii"))
    digest.update(canonical_bytes(document))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Posted:
    """The posting ``post`` wrote, or the stored one of the same key (``replayed``)."""

    posting_id: uuid.UUID
    book_code: str
    chain_seq: int
    seal_sha256: str
    line_ids: tuple[uuid.UUID, ...]
    replayed: bool


def _stored_posting(session: Session, *, book_code: str, idempotency_key: str) -> Posted | None:
    found = (
        session.execute(
            select(
                subledger_posting.c.id,
                subledger_posting_seal.c.chain_seq,
                subledger_posting_seal.c.seal_sha256,
            )
            .select_from(
                subledger_posting.join(
                    subledger_posting_seal,
                    and_(
                        subledger_posting_seal.c.tenant_id == subledger_posting.c.tenant_id,
                        subledger_posting_seal.c.subledger_posting_id == subledger_posting.c.id,
                    ),
                )
            )
            .where(
                subledger_posting.c.book_code == book_code,
                subledger_posting.c.idempotency_key == idempotency_key,
            )
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        return None
    posting_id = uuid.UUID(str(found["id"]))
    line_ids = tuple(
        uuid.UUID(str(value))
        for value in session.scalars(
            select(subledger_line.c.id)
            .where(subledger_line.c.subledger_posting_id == posting_id)
            .order_by(subledger_line.c.entry_no, subledger_line.c.id)
        )
    )
    return Posted(
        posting_id=posting_id,
        book_code=book_code,
        chain_seq=int(found["chain_seq"]),
        seal_sha256=str(found["seal_sha256"]),
        line_ids=line_ids,
        replayed=True,
    )


def _store_lines(session: Session, line_rows: Sequence[dict[str, Any]]) -> None:
    """Insert ``line_rows`` and put into each the ``is_post_reopen`` the insert stored.

    The DB-07 guard decides that member from the period's state row, read ``FOR SHARE`` — after a
    wait, the state the holder committed (04 §14.1 DB-07 rev 1.113). The seal is computed over
    these rows, so it hashes the stored value: a change of the state in flight at the insert
    (start-close on a ``reopened`` period, a reopen approval) cannot part the seal from the
    stored posting (04 §14.1, the DB-06 note, rev 1.140; supervisor ruling R-97 (1))."""
    stored = {
        str(row.id): bool(row.is_post_reopen)
        for row in session.execute(
            insert(subledger_line).returning(subledger_line.c.id, subledger_line.c.is_post_reopen),
            line_rows,
        )
    }
    if len(stored) != len(line_rows):
        raise RuntimeError(
            f"the insert of {len(line_rows)} subledger lines returned {len(stored)} rows"
        )
    for row in line_rows:
        row["is_post_reopen"] = stored[str(row["id"])]


def post(
    uow: UnitOfWork,
    *,
    book_code: str,
    posting_kind: SubledgerPostingKind,
    idempotency_key: str,
    description: str,
    lines: Sequence[Mapping[str, Any]],
    combination_group_id: uuid.UUID | None = None,
    contract_computation_id: uuid.UUID | None = None,
    close_run_id: uuid.UUID | None = None,
    manual_adjustment_id: uuid.UUID | None = None,
    reverses_posting_id: uuid.UUID | None = None,
    require_subject_key: bool = False,
) -> Posted:
    """Write a sealed posting of ``lines`` (T-SL-04 values without the posting's members), or
    return the stored posting of ``(book_code, idempotency_key)`` (RCP-21).

    ``require_subject_key`` (supervisor ruling R-11 as amended; 04 T-SL-04 rev 1.282): every
    caller inside ``erev_api`` passes True, and a line without ``subject_key`` is then refused
    before anything is written — the read-back of posted amounts answers the stored key (05
    RCP-05), so a product line without one would be read under a subject it was not posted
    under. ``tests/architecture/test_subledger_door.py`` pins the callers."""
    session = uow.session
    stored = _stored_posting(session, book_code=book_code, idempotency_key=idempotency_key)
    if stored is not None:
        return stored
    if len(lines) < 2:
        raise ValueError("a posting holds at least two lines (T-SL-02 line_count >= 2)")
    if require_subject_key:
        unnamed = [
            number for number, line in enumerate(lines, start=1) if not line.get(SUBJECT_KEY)
        ]
        if unnamed:
            raise ValueError(
                f"line {unnamed[0]} of a {posting_kind.value} posting names no subject key "
                "(04 T-SL-04): a product posting stores the subject of every line"
            )
    principal = uow.principal
    stamps = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    posting_id = new_id()
    posting_row: dict[str, Any] = {
        "tenant_id": principal.tenant_id,
        "id": posting_id,
        "book_code": book_code,
        "posting_kind": posting_kind.value,
        "combination_group_id": combination_group_id,
        "contract_computation_id": contract_computation_id,
        "close_run_id": close_run_id,
        "manual_adjustment_id": manual_adjustment_id,
        "reverses_posting_id": reverses_posting_id,
        "idempotency_key": idempotency_key,
        "description": description,
        **stamps,
    }
    session.execute(insert(subledger_posting).values(**posting_row))
    line_rows: list[dict[str, Any]] = []
    for line in lines:
        row = {name: line.get(name, _LINE_DEFAULTS.get(name)) for name in LINE_MEMBERS}
        row.update(
            tenant_id=principal.tenant_id,
            id=line.get("id") or new_id(),
            subledger_posting_id=posting_id,
            book_code=book_code,
            recorded_at=uow.now,
            is_post_reopen=False,  # the DB-07 guard decides it; ``_store_lines`` takes it back
            **stamps,
        )
        line_rows.append(row)
    _store_lines(session, line_rows)
    event_rows = line_event_rows(principal.tenant_id, lines, line_rows, stamps)
    if event_rows:
        session.execute(insert(subledger_line_event), event_rows)
    head = session.execute(
        select(ledger_chain_head.c.last_seal_sha256)
        .where(ledger_chain_head.c.book_code == book_code)
        .with_for_update()
    ).one_or_none()
    if head is None:
        raise RuntimeError(f"book {book_code} has no ledger chain head (04 §14.3)")
    locking.mark_chain_head(session)  # DG-KRN-DB-08 (1c) rev 1.218: no state row is waited for now
    previous = None if head.last_seal_sha256 is None else str(head.last_seal_sha256)
    totals = control_totals(line_rows)
    seal = seal_sha256(previous, posting_row, totals, line_rows)
    session.execute(
        insert(subledger_posting_seal).values(
            tenant_id=principal.tenant_id,
            subledger_posting_id=posting_id,
            book_code=book_code,
            line_count=len(line_rows),
            control_totals=totals,
            prev_seal_sha256=previous,
            seal_sha256=seal,
            sealed_at=uow.now,
            **stamps,
        )
    )
    chain_seq = int(
        session.execute(
            select(subledger_posting_seal.c.chain_seq).where(
                subledger_posting_seal.c.subledger_posting_id == posting_id
            )
        ).scalar_one()
    )
    line_ids = tuple(uuid.UUID(str(row["id"])) for row in line_rows)
    # The posting's events name the contracts of its lines (04 T-PLT-19 ``detail.contract_id``).
    contracts = sorted({uuid.UUID(str(row["contract_id"])) for row in line_rows})
    record_facts(
        uow,
        action=f"{POSTING_OBJECT}.create",
        object_type=POSTING_OBJECT,
        ids=[posting_id],
        detail={
            "book_code": book_code,
            "posting_kind": posting_kind.value,
            "idempotency_key": idempotency_key,
            "chain_seq": chain_seq,
            "line_count": len(line_rows),
        },
        contract_ids=contracts,
    )
    record_facts(
        uow,
        action=f"{LINE_OBJECT}.create",
        object_type=LINE_OBJECT,
        ids=line_ids,
        contract_ids=contracts,
    )
    record_facts(
        uow,
        action=f"{SEAL_OBJECT}.create",
        object_type=SEAL_OBJECT,
        ids=[posting_id],
        contract_ids=contracts,
    )
    return Posted(
        posting_id=posting_id,
        book_code=book_code,
        chain_seq=chain_seq,
        seal_sha256=seal,
        line_ids=line_ids,
        replayed=False,
    )


# --- verification (DG-TST-22) --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LedgerChainVerification:
    book_code: str
    result: ControlResult
    seals_checked: int
    first_failure_seq: int | None
    failure_detail: Mapping[str, str] | None
    last_seal_sha256: str | None


@register_ledger_chain_verifier
def verify_ledger_chain(session: Session, *, book_code: str) -> LedgerChainVerification:
    """Recompute every seal of ``book_code`` visible to ``session`` in chain order; FAIL names the
    first sequence whose position, previous seal, line count, control totals or hash departs."""
    seals = (
        session.execute(
            select(subledger_posting_seal)
            .where(subledger_posting_seal.c.book_code == book_code)
            .order_by(subledger_posting_seal.c.chain_seq)
        )
        .mappings()
        .all()
    )
    previous: str | None = None
    checked = 0

    def failed(seq: int, reason: str) -> LedgerChainVerification:
        return LedgerChainVerification(
            book_code=book_code,
            result=ControlResult.FAIL,
            seals_checked=checked,
            first_failure_seq=seq,
            failure_detail=MappingProxyType({"reason": reason}),
            last_seal_sha256=previous,
        )

    for expected, seal in enumerate(seals, start=1):
        checked = expected
        seq = int(seal["chain_seq"])
        if seq != expected:
            return failed(seq, "chain_seq does not follow the previous seal")
        stored_previous = (
            None if seal["prev_seal_sha256"] is None else str(seal["prev_seal_sha256"])
        )
        if stored_previous != previous:
            return failed(seq, "prev_seal_sha256 does not name the previous seal")
        posting_id = seal["subledger_posting_id"]
        posting = (
            session.execute(select(subledger_posting).where(subledger_posting.c.id == posting_id))
            .mappings()
            .one()
        )
        lines = [
            dict(row)
            for row in session.execute(
                select(subledger_line).where(subledger_line.c.subledger_posting_id == posting_id)
            ).mappings()
        ]
        if len(lines) != int(seal["line_count"]):
            return failed(seq, "line_count does not count the posting's lines")
        totals = control_totals(lines)
        if [dict(item) for item in seal["control_totals"]] != totals:
            return failed(seq, "control_totals do not match the posting's lines")
        if seal_sha256(previous, dict(posting), totals, lines) != str(seal["seal_sha256"]):
            return failed(seq, "seal_sha256 does not match the posting content")
        previous = str(seal["seal_sha256"])
    head = session.execute(
        select(ledger_chain_head.c.last_chain_seq, ledger_chain_head.c.last_seal_sha256).where(
            ledger_chain_head.c.book_code == book_code
        )
    ).one_or_none()
    head_sha = None if head is None or head.last_seal_sha256 is None else str(head.last_seal_sha256)
    if head is None or int(head.last_chain_seq) != len(seals) or head_sha != previous:
        return failed(len(seals) + 1, "the ledger chain head does not name the last seal")
    return LedgerChainVerification(
        book_code=book_code,
        result=ControlResult.PASS,
        seals_checked=len(seals),
        first_failure_seq=None,
        failure_detail=None,
        last_seal_sha256=previous,
    )


# --- API-R-36 reads -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LineFilters:
    """API-R-36 filters the resource applies itself (API-C-10, API-C-11)."""

    entity: tuple[str, ...] = ()
    book: str | None = None
    period: str | None = None
    origin_period: str | None = None
    contract: uuid.UUID | None = None
    known_at: datetime | None = None


ORIGIN_PERIOD: Final = period.alias("origin_period")
LINE_COLUMNS: Final = (
    subledger_line.c.id,
    subledger_line.c.subledger_posting_id,
    subledger_posting.c.posting_kind,
    subledger_line.c.entity_id,
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.name.label("entity_name"),
    subledger_line.c.book_code,
    # 04 API-S-SubledgerLine ``journal_run_id`` rev 1.288: the line's own period, the key by which
    # ``journal_runs_of`` finds the runs that may journalise it
    subledger_line.c.period_id,
    period.c.period_key,
    ORIGIN_PERIOD.c.period_key.label("origin_period_key"),
    subledger_line.c.is_post_reopen,
    subledger_line.c.effective_date,
    subledger_line.c.recorded_at,
    subledger_line.c.entry_no,
    subledger_line.c.entry_kind,
    subledger_line.c.account_role,
    subledger_line.c.gl_account_id,
    gl_account.c.code.label("account_code"),
    gl_account.c.name.label("account_name"),
    subledger_line.c.dr_cr,
    subledger_line.c.txn_currency,
    subledger_line.c.amount_txn,
    subledger_line.c.functional_currency,
    subledger_line.c.amount_functional,
    subledger_line.c.fx_rate_id,
    subledger_line.c.fx_rate,
    subledger_line.c.fx_rate_set_version_id,
    subledger_line.c.contract_id,
    # 04 API-S-SubledgerLine rev 1.159: the contract's external id rides on the row, so a reader
    # names the contract of every line without one read per contract (``contract_join``).
    contract.c.external_id.label("contract_external_id"),
    subledger_line.c.obligation_id,
    # 04 API-S-SubledgerLine rev 1.245: the obligation's key rides on the row as the contract's
    # external id does, joined through the contract's row (``OBLIGATION_JOIN``).
    obligation.c.obligation_key,
    subledger_line.c.contract_version_id,
    subledger_line.c.contract_event_id,
    subledger_line.c.schedule_line_id,
    subledger_line.c.reason_code,
)
# The outer join every statement of ``LINE_COLUMNS`` ends with: the line's contract by its key —
# at most one row, so no line is added, dropped or reordered. Every line has a contract (T-SL-04
# ``contract_id`` is not null); the name is null only when the contract is outside the caller's
# entity scope (T-CON-01 is RLS-TE), hence the outer join.
CONTRACT_JOIN: Final = and_(
    contract.c.tenant_id == subledger_line.c.tenant_id,
    contract.c.id == subledger_line.c.contract_id,
)
# The outer join that follows it (rev 1.245): the line's obligation by its key AND by the joined
# contract's id. T-CON-10 is RLS-T while the contract is RLS-TE, so a join by the obligation's id
# alone would name the obligation of a contract whose name the caller is not told; through the
# contract's row the key is null wherever ``contract_external_id`` is, and where the line has no
# obligation. At most one row, so no line is added, dropped or reordered.
OBLIGATION_JOIN: Final = and_(
    obligation.c.tenant_id == subledger_line.c.tenant_id,
    obligation.c.id == subledger_line.c.obligation_id,
    obligation.c.contract_id == contract.c.id,
)


def _key_or_id(column_key: Any, column_id: Any, value: str) -> Any:
    try:
        return column_id == uuid.UUID(value)
    except ValueError:
        return column_key == value


def _primary_book(session: Session) -> str:
    found = session.execute(select(book.c.code).where(book.c.is_primary.is_(True))).scalar()
    return BookCode.ASC606.value if found is None else str(found)


def line_statement(session: Session, filters: LineFilters) -> Select[Any]:
    """The lines visible in ``session`` under ``filters``; the book defaults to the primary book
    (API-C-11) and ``known_at`` keeps lines recorded by then (API-C-10)."""
    tenant = subledger_line.c.tenant_id
    statement = (
        select(*LINE_COLUMNS)
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == tenant,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == tenant,
                    legal_entity.c.id == subledger_line.c.entity_id,
                ),
            )
            .join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == tenant,
                    gl_account.c.id == subledger_line.c.gl_account_id,
                ),
            )
            .join(
                period,
                and_(period.c.tenant_id == tenant, period.c.id == subledger_line.c.period_id),
            )
            .outerjoin(
                ORIGIN_PERIOD,
                and_(
                    ORIGIN_PERIOD.c.tenant_id == tenant,
                    ORIGIN_PERIOD.c.id == subledger_line.c.origin_period_id,
                ),
            )
            .outerjoin(contract, CONTRACT_JOIN)
            .outerjoin(obligation, OBLIGATION_JOIN)
        )
        .where(subledger_line.c.book_code == (filters.book or _primary_book(session)))
    )
    if filters.entity:
        statement = statement.where(
            or_(
                *(
                    _key_or_id(legal_entity.c.code, legal_entity.c.id, item)
                    for item in filters.entity
                )
            )
        )
    if filters.period is not None:
        statement = statement.where(_key_or_id(period.c.period_key, period.c.id, filters.period))
    if filters.origin_period is not None:
        statement = statement.where(
            _key_or_id(ORIGIN_PERIOD.c.period_key, ORIGIN_PERIOD.c.id, filters.origin_period)
        )
    if filters.contract is not None:
        statement = statement.where(subledger_line.c.contract_id == filters.contract)
    if filters.known_at is not None:
        statement = statement.where(subledger_line.c.recorded_at <= filters.known_at)
    return statement


def list_lines[T](
    ctx: RequestContext, filters: LineFilters, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the tenant's subledger lines; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, line_statement(session, filters))


def journal_runs_of(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    files: FileStore | None,
    keyring: KeyRing | None,
) -> dict[uuid.UUID, uuid.UUID]:
    """API-S-SubledgerLine ``journal_run_id`` (04 rev 1.288; item SUBLEDGER-LINE-JOURNAL-RUN-1)
    for the rows of one page of ``LINE_COLUMNS``: line id → the run that journalises it, by the
    rule the completeness assertion reads (``completeness.journalising_runs``) — three
    statements a page whatever its number of lines, and none of them the page's own. A line that
    is absent names no run. ``files`` and ``keyring`` go to the reader of a run's record, as the
    gate hands them: every read of the schema hands both."""
    lines = [
        completeness.SealedLine(
            id=uuid.UUID(str(row["id"])),
            entity_id=uuid.UUID(str(row["entity_id"])),
            period_id=uuid.UUID(str(row["period_id"])),
            book_code=str(getattr(row["book_code"], "value", row["book_code"])),
            subledger_posting_id=uuid.UUID(str(row["subledger_posting_id"])),
        )
        for row in rows
    ]
    return completeness.journalising_runs(session, lines, files=files, keyring=keyring)


def line_outs(
    rows: Sequence[Mapping[str, Any]], journal_runs: Mapping[uuid.UUID, uuid.UUID]
) -> list[SubledgerLineOut]:
    """API-S-SubledgerLine of each row of ``line_statement``; ``journal_runs`` is the page's
    ``journal_runs_of``: a line it does not name is journalised by no run."""
    items: list[SubledgerLineOut] = []
    for row in rows:
        line_id = row["id"]
        event_id = row["contract_event_id"]
        rate = None
        if row["fx_rate_id"] is not None:
            rate = SubledgerFxRateOut(
                id=row["fx_rate_id"],
                rate=format(Decimal(row["fx_rate"]).normalize(), "f"),
                rate_set_version_id=row["fx_rate_set_version_id"],
            )
        items.append(
            SubledgerLineOut(
                id=line_id,
                posting_id=row["subledger_posting_id"],
                posting_kind=row["posting_kind"],
                entity={
                    "id": row["entity_id"],
                    "code": row["entity_code"],
                    "name": row["entity_name"],
                },
                book=row["book_code"],
                period_key=row["period_key"],
                origin_period_key=row["origin_period_key"],
                is_post_reopen=row["is_post_reopen"],
                effective_date=row["effective_date"],
                recorded_at=row["recorded_at"],
                entry_no=row["entry_no"],
                entry_kind=row["entry_kind"],
                account_role=row["account_role"],
                account={
                    "id": row["gl_account_id"],
                    "code": row["account_code"],
                    "name": row["account_name"],
                },
                dr_cr=str(row["dr_cr"]),
                amount_txn=money_out(
                    Decimal(row["amount_txn"]), str(row["txn_currency"]).strip(), ISO_4217
                ),
                amount_functional=money_out(
                    Decimal(row["amount_functional"]),
                    str(row["functional_currency"]).strip(),
                    ISO_4217,
                ),
                fx_rate=rate,
                contract_id=row["contract_id"],
                contract_external_id=row["contract_external_id"],
                obligation_id=row["obligation_id"],
                obligation_key=row["obligation_key"],
                contract_version_id=row["contract_version_id"],
                contract_event_id=event_id,
                schedule_line_id=row["schedule_line_id"],
                journal_run_id=journal_runs.get(uuid.UUID(str(line_id))),
                reason_code=row["reason_code"],
                links=SubledgerLineLinksOut(
                    explain=f"/api/v1/explain/subledger_line/{line_id}/amount",
                    event=None if event_id is None else f"/api/v1/events/{event_id}",
                    schedule_line=None,
                    source_row=None,
                ),
            )
        )
    return items


def get_posting(ctx: RequestContext, posting_id: uuid.UUID) -> SubledgerPostingOut:
    """``GET /subledger-postings/{id}``: the posting and its seal; 404 when invisible.

    T-SL-01 and its seal (T-SL-02) carry no entity; the lines do (T-SL-04). A posting is the
    session's to read when one of its lines is, and its control totals are those of the entities
    whose lines the session reads (03 REQ-PLT-012; supervisor ruling R-28; head R28-READS): until
    then any holder of the permission read a posting of another entity by id, with every total.
    The seal's own members — chain sequence, hashes, line count — are of the whole posting. A
    session of all entities reads a posting that has no line as before."""
    context = ctx.principal.db_context
    with tenant_session(context, read_only=True) as session:
        entities = {
            str(value)
            for value in session.execute(
                select(subledger_line.c.entity_id)
                .where(subledger_line.c.subledger_posting_id == posting_id)
                .distinct()
            ).scalars()
        }
        row = (
            session.execute(
                select(
                    subledger_posting,
                    subledger_posting_seal.c.chain_seq,
                    subledger_posting_seal.c.line_count,
                    subledger_posting_seal.c.control_totals,
                    subledger_posting_seal.c.prev_seal_sha256,
                    subledger_posting_seal.c.seal_sha256,
                    subledger_posting_seal.c.sealed_at,
                )
                .select_from(
                    subledger_posting.join(
                        subledger_posting_seal,
                        and_(
                            subledger_posting_seal.c.tenant_id == subledger_posting.c.tenant_id,
                            subledger_posting_seal.c.subledger_posting_id == subledger_posting.c.id,
                        ),
                    )
                )
                .where(subledger_posting.c.id == posting_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None or (not entities and context.entity_scope != "*"):
        raise Problem("not-found")
    return SubledgerPostingOut(
        id=row["id"],
        book=row["book_code"],
        posting_kind=row["posting_kind"],
        combination_group_id=row["combination_group_id"],
        contract_computation_id=row["contract_computation_id"],
        close_run_id=row["close_run_id"],
        manual_adjustment_id=row["manual_adjustment_id"],
        reverses_posting_id=row["reverses_posting_id"],
        idempotency_key=row["idempotency_key"],
        description=row["description"],
        created_at=row["created_at"],
        seal=SubledgerSealOut(
            chain_seq=row["chain_seq"],
            line_count=row["line_count"],
            control_totals=[
                ControlTotalOut.model_validate(item)
                for item in row["control_totals"]
                if context.entity_scope == "*" or str(item["entity_id"]) in entities
            ],
            prev_seal_sha256=None
            if row["prev_seal_sha256"] is None
            else str(row["prev_seal_sha256"]),
            seal_sha256=str(row["seal_sha256"]),
            sealed_at=row["sealed_at"],
        ),
    )

"""SSP area queries (dev-guide DG-LAY-04, DG-CMD-13): SSP books, versions, entries and the version
diff (04 API-R-26, T-REF-28 to T-REF-31, §16.4; SCREENS §11.4; BUILD_SPEC RFD-12).

Every read runs in the principal's context, so row-level security limits the rows to the tenant and
an id of another tenant reads as 404 (API-C-03). The tables are RLS-T, so the book's entity is
asked here: a book of an entity, its versions and their entries are read only where the caller's
``ssp.read`` covers that entity, and are absent — left out of the list, 404 by id — for anyone
else (``scope``; item SSP-ENTITY-SCOPE-1). Decimals are returned as API-C-06 text.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, and_, case, select
from sqlalchemy.orm import Session

from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    file_attachment,
    file_object,
    gl_account,
    legal_entity,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
)
from erev_api.domain.platform.approval_queries import actor, display_names
from erev_api.domain.reference.products import exact_text
from erev_api.domain.reference.queries import Page
from erev_api.domain.ssp import books, scope
from erev_api.enums import ConfigStatus, FilePurpose
from erev_api.files.store import lock_readable
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext

BOOK_COLUMNS: Final = (
    ssp_book.c.id,
    ssp_book.c.code,
    ssp_book.c.name,
    ssp_book.c.description,
    legal_entity.c.code.label("entity_code"),
    ssp_book.c.currency,
    ssp_book.c.channel,
    ssp_book.c.segment,
    ssp_book.c.resolution_mode,
    ssp_book.c.row_version,
    ssp_book.c.created_at,
    ssp_book.c.updated_at,
)
VERSION_COLUMNS: Final = (
    ssp_book_version.c.id,
    ssp_book_version.c.ssp_book_id,
    ssp_book_version.c.version_no,
    ssp_book_version.c.status,
    ssp_book_version.c.legacy_version_label,
    ssp_book_version.c.effective_from_date,
    ssp_book_version.c.effective_to_date,
    ssp_book_version.c.methodology_label,
    ssp_book_version.c.is_methodology_change,
    ssp_book_version.c.entry_count,
    ssp_book_version.c.diff_summary,
    ssp_book_version.c.ssp_calculator_run_id,
    ssp_book_version.c.approval_request_id,
    ssp_book_version.c.content_sha256,
    ssp_book_version.c.published_at,
    ssp_book_version.c.created_by,
    ssp_book_version.c.created_by_kind,
    ssp_book_version.c.created_at,
    ssp_book_version.c.updated_at,
    ssp_book_version.c.row_version,
)
_REVENUE_ACCOUNT_CODE: Final = "revenue_account_code"
ENTRY_COLUMNS: Final = (
    ssp_entry.c.id,
    product.c.code,
    ssp_entry.c.stratification,
    ssp_entry.c.region,
    ssp_entry.c.channel,
    ssp_entry.c.segment,
    ssp_entry.c.deal_size_band,
    ssp_entry.c.term_band,
    ssp_entry.c.currency,
    ssp_entry.c.method,
    ssp_entry.c.value_basis,
    ssp_entry.c.quantity_unit,
    ssp_entry.c.unit_list_price,
    ssp_entry.c.midpoint_discount_ratio,
    ssp_entry.c.range_ratio,
    ssp_entry.c.cost_basis,
    ssp_entry.c.margin_ratio,
    ssp_entry.c.observable_point,
    gl_account.c.code.label(_REVENUE_ACCOUNT_CODE),
    ssp_entry.c.distinctness,
)
STUDY_SUBJECT: Final = "ssp_book_version"


# --- books ---------------------------------------------------------------------------------------


def book_select() -> Select[Any]:
    """T-REF-28 rows with the code of their scope entity."""
    joined = ssp_book.outerjoin(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == ssp_book.c.tenant_id,
            legal_entity.c.id == ssp_book.c.entity_id,
        ),
    )
    return select(*BOOK_COLUMNS).select_from(joined)


def _version_pointers(
    session: Session, book_ids: Iterable[Any]
) -> tuple[dict[UUID, dict[str, Any]], dict[UUID, UUID]]:
    """The latest APPROVED version and the highest-numbered DRAFT version of each book."""
    ids = sorted({UUID(str(book_id)) for book_id in book_ids})
    current: dict[UUID, dict[str, Any]] = {}
    drafts: dict[UUID, UUID] = {}
    if not ids:
        return current, drafts
    statement = (
        select(
            ssp_book_version.c.ssp_book_id,
            ssp_book_version.c.id,
            ssp_book_version.c.version_no,
            ssp_book_version.c.status,
            ssp_book_version.c.legacy_version_label,
            ssp_book_version.c.effective_from_date,
            ssp_book_version.c.effective_to_date,
        )
        .where(
            ssp_book_version.c.ssp_book_id.in_(ids),
            ssp_book_version.c.status.in_([ConfigStatus.APPROVED.value, ConfigStatus.DRAFT.value]),
        )
        .order_by(ssp_book_version.c.version_no)
    )
    for row in session.execute(statement).mappings():
        book_id = UUID(str(row["ssp_book_id"]))
        if row["status"] == ConfigStatus.APPROVED.value:
            current[book_id] = {
                name: row[name]
                for name in (
                    "id",
                    "version_no",
                    "legacy_version_label",
                    "effective_from_date",
                    "effective_to_date",
                )
            }
        else:
            drafts[book_id] = UUID(str(row["id"]))
    return current, drafts


def books_out(session: Session, rows: Sequence[Mapping[Any, Any]]) -> list[dict[str, Any]]:
    """API-S-SspBook items with ``current_version`` and ``draft_version_id``."""
    current, drafts = _version_pointers(session, [row["id"] for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {str(key): value for key, value in row.items()}
        book_id = UUID(str(item["id"]))
        item["current_version"] = current.get(book_id)
        item["draft_version_id"] = drafts.get(book_id)
        items.append(item)
    return items


def list_ssp_books[T: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the SSP books the caller reaches: the books of all entities and the books of
    the entities its ``ssp.read`` covers (``scope.in_reach``)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, book_select().where(scope.in_reach(ctx.principal, scope.READ)))
        return result, books_out(session, result.items)


def ssp_book_row(session: Session, book_id: UUID) -> dict[str, Any] | None:
    """The API-S-SspBook visible to ``session``, or None."""
    row = session.execute(book_select().where(ssp_book.c.id == book_id)).mappings().first()
    return None if row is None else books_out(session, [row])[0]


def get_ssp_book(ctx: RequestContext, book_id: UUID) -> dict[str, Any]:
    """``GET /ssp-books/{id}``; 404 ``not-found`` for an unknown book and for a book out of the
    caller's reach."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope.require_book(session, ctx.principal, scope.READ, book_id)
        row = ssp_book_row(session, book_id)
    if row is None:
        raise Problem("not-found")
    return row


# --- versions ------------------------------------------------------------------------------------


def version_select() -> Select[Any]:
    """T-REF-29 rows."""
    return select(*VERSION_COLUMNS)


def _study_rows(
    session: Session, version_ids: Iterable[Any]
) -> list[tuple[UUID, UUID, UUID, bool]]:
    """(version, attachment, file, whether the file is shredded) of the live attachments of
    purpose ``SSP_STUDY`` of the versions, in attachment order."""
    ids = sorted({UUID(str(version_id)) for version_id in version_ids})
    if not ids:
        return []
    statement = (
        select(
            file_attachment.c.subject_id,
            file_attachment.c.id,
            file_object.c.id,
            file_object.c.shredded_at.is_not(None),
        )
        .join(
            file_object,
            and_(
                file_object.c.tenant_id == file_attachment.c.tenant_id,
                file_object.c.id == file_attachment.c.file_object_id,
            ),
        )
        .where(
            file_attachment.c.subject_type == STUDY_SUBJECT,
            file_attachment.c.subject_id.in_(ids),
            file_attachment.c.voided_at.is_(None),
            file_object.c.purpose == FilePurpose.SSP_STUDY.value,
        )
        .order_by(file_attachment.c.created_at, file_attachment.c.id)
    )
    return [
        (UUID(str(version_id)), UUID(str(attachment_id)), UUID(str(file_id)), bool(shredded))
        for version_id, attachment_id, file_id, shredded in session.execute(statement).tuples()
    ]


def _study_attachments(session: Session, version_ids: Iterable[Any]) -> dict[UUID, list[UUID]]:
    """The studies of each version, in attachment order (REQ-SSP-008): its live attachments of
    purpose ``SSP_STUDY`` whose file can still be read. An attachment row outlives the shred of
    its file and is no study then (04 T-PLT-29 "A document a rule asks for"; rulings R-119 (g),
    R-120 (g))."""
    found: dict[UUID, list[UUID]] = {}
    for version_id, attachment_id, _file_id, shredded in _study_rows(session, version_ids):
        if not shredded:
            found.setdefault(version_id, []).append(attachment_id)
    return found


def study_attachment_ids(session: Session, version_id: UUID) -> list[UUID]:
    """The studies of one version (REQ-SSP-008; BUILD_SPEC RFD-13), as the API shows them."""
    return _study_attachments(session, [version_id]).get(version_id, [])


def counted_study_ids(session: Session, version_id: UUID) -> list[UUID]:
    """The studies of one version for the rule that asks for one — at its submission and at its
    approval: read with their files' rows locked to the end of the transaction, so that the
    command and a shred of a study see each other (``files.store.lock_readable``)."""
    rows = _study_rows(session, [version_id])
    readable = lock_readable(session, [file_id for _version, _attachment, file_id, _gone in rows])
    return [
        attachment_id for _version, attachment_id, file_id, _gone in rows if file_id in readable
    ]


def versions_out(session: Session, rows: Sequence[Mapping[Any, Any]]) -> list[dict[str, Any]]:
    """API-S-SspBookVersion items with ``created_by`` as API-S-Actor and their
    ``study_attachment_ids``."""
    names = display_names(session, [row["created_by"] for row in rows])
    studies = _study_attachments(session, [row["id"] for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {str(key): value for key, value in row.items()}
        user_id, kind = item.pop("created_by"), item.pop("created_by_kind")
        item["created_by"] = actor(user_id, str(kind), names)
        item["study_attachment_ids"] = studies.get(UUID(str(item["id"])), [])
        items.append(item)
    return items


def list_ssp_book_versions[T: Page](
    ctx: RequestContext, book_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the versions of a book; 404 ``not-found`` for an unknown book and for a book
    out of the caller's reach."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope.require_book(session, ctx.principal, scope.READ, book_id)
        statement = version_select().where(ssp_book_version.c.ssp_book_id == book_id)
        result = page(session, statement)
        return result, versions_out(session, result.items)


def ssp_book_version_row(session: Session, version_id: UUID) -> dict[str, Any] | None:
    """The API-S-SspBookVersion visible to ``session``, or None."""
    statement = version_select().where(ssp_book_version.c.id == version_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else versions_out(session, [row])[0]


def get_ssp_book_version(ctx: RequestContext, version_id: UUID) -> dict[str, Any]:
    """``GET /ssp-book-versions/{id}``; 404 ``not-found`` for an unknown version and for a
    version of a book out of the caller's reach."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope.require_version_book(session, ctx.principal, scope.READ, version_id)
        row = ssp_book_version_row(session, version_id)
    if row is None:
        raise Problem("not-found")
    return row


# --- entries -------------------------------------------------------------------------------------


def entry_select() -> Select[Any]:
    """T-REF-30 rows with their product code and revenue account code."""
    joined = ssp_entry.join(
        product,
        and_(product.c.tenant_id == ssp_entry.c.tenant_id, product.c.id == ssp_entry.c.product_id),
    ).outerjoin(
        gl_account,
        and_(
            gl_account.c.tenant_id == ssp_entry.c.tenant_id,
            gl_account.c.id == ssp_entry.c.revenue_gl_account_id,
        ),
    )
    return select(*ENTRY_COLUMNS).select_from(joined)


def _bands(session: Session, entry_ids: Iterable[Any]) -> dict[UUID, list[dict[str, Any]]]:
    """The T-REF-31 bands per entry: ``NONE`` first, then by dimension and start."""
    ids = sorted({UUID(str(entry_id)) for entry_id in entry_ids})
    found: dict[UUID, list[dict[str, Any]]] = {}
    if not ids:
        return found
    statement = (
        select(
            ssp_range.c.ssp_entry_id,
            ssp_range.c.band_dimension,
            *(ssp_range.c[name] for name in books.BAND_VALUES),
        )
        .where(ssp_range.c.ssp_entry_id.in_(ids))
        .order_by(
            ssp_range.c.ssp_entry_id,
            case((ssp_range.c.band_dimension == books.BAND_NONE, 0), else_=1),
            ssp_range.c.band_dimension,
            ssp_range.c.band_from.nulls_first(),
            ssp_range.c.id,
        )
    )
    for row in session.execute(statement).mappings():
        band: dict[str, Any] = {"band_dimension": str(row["band_dimension"])}
        band.update({name: exact_text(row[name]) for name in books.BAND_VALUES})
        found.setdefault(UUID(str(row["ssp_entry_id"])), []).append(band)
    return found


def entries_out(session: Session, rows: Sequence[Mapping[Any, Any]]) -> list[dict[str, Any]]:
    """API-S-SspEntry items with API-C-06 decimal text and their bands."""
    bands = _bands(session, [row["id"] for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {str(key): value for key, value in row.items()}
        item["product_code"] = item.pop("code")
        for name in books.ATTRIBUTES:
            item[name] = exact_text(item[name])
        item["ranges"] = bands.get(UUID(str(item["id"])), [])
        items.append(item)
    return items


def entries_of(session: Session, version_id: UUID) -> list[dict[str, Any]]:
    """Every entry of a version in key order."""
    statement = (
        entry_select()
        .where(ssp_entry.c.ssp_book_version_id == version_id)
        .order_by(
            product.c.code,
            ssp_entry.c.stratification,
            *(ssp_entry.c[name].nulls_first() for name in books.DIMENSION_KEYS),
            ssp_entry.c.currency,
        )
    )
    return entries_out(session, session.execute(statement).mappings().all())


def entries_by_id(session: Session, entry_ids: Sequence[UUID]) -> list[dict[str, Any]]:
    """The entries ``entry_ids`` in that order."""
    rows = session.execute(entry_select().where(ssp_entry.c.id.in_(entry_ids))).mappings().all()
    by_id = {UUID(str(item["id"])): item for item in entries_out(session, rows)}
    return [by_id[entry_id] for entry_id in entry_ids]


def list_ssp_entries[T: Page](
    ctx: RequestContext, version_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the entries of a version; 404 ``not-found`` for an unknown version and for a
    version of a book out of the caller's reach."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope.require_version_book(session, ctx.principal, scope.READ, version_id)
        statement = entry_select().where(ssp_entry.c.ssp_book_version_id == version_id)
        result = page(session, statement)
        return result, entries_out(session, result.items)


def ssp_version_diff(ctx: RequestContext, version_id: UUID, against: UUID) -> dict[str, Any]:
    """``GET /ssp-book-versions/{id}/diff?against=<version id>``: 404 for an unknown version and
    for a version of a book out of the caller's reach; 422 ``validation-failed`` on ``against``
    unless it names a version of the same book (RPT-20)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope.require_version_book(session, ctx.principal, scope.READ, version_id)
        books_of = {
            UUID(str(row_id)): UUID(str(book_id))
            for row_id, book_id in session.execute(
                select(ssp_book_version.c.id, ssp_book_version.c.ssp_book_id).where(
                    ssp_book_version.c.id.in_([version_id, against])
                )
            ).tuples()
        }
        if version_id not in books_of:
            raise Problem("not-found")
        if books_of.get(against) != books_of[version_id]:
            error = ProblemError(
                field="against", rule_id=books.RULE_VERSION, message=books.AGAINST_OTHER_BOOK
            )
            raise Problem("validation-failed", errors=[error])
        return books.diff(entries_of(session, version_id), entries_of(session, against))

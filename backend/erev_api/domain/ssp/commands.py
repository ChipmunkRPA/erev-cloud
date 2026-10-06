"""SSP area commands (dev-guide DG-LAY-04, DG-CMD-11): SSP books, versions and entries (04 API-R-26,
T-REF-28 to T-REF-31, §16.4, DB-04; PRD SM-04; BUILD_SPEC RFD-12).

The routes guard every command with ``ssp.create``, and every command asks it FOR THE BOOK'S
ENTITY (``scope``; supervisor ruling R-28; item SSP-ENTITY-SCOPE-1): a book of an entity is
changed only by a member whose ``ssp.create`` covers that entity, and answers 404 to anyone
else; a new book is made for an entity the permission covers.

Inserting or updating a book or a version writes
one AUD-CMD event with field-level ``before`` and ``after`` of the changed members; entry and band
writes are AUD-FACT summaries (04 §1.7). A version and its entries change only while the version is
DRAFT (DB-04; SM-04), otherwise 409 ``configuration-frozen``. Several versions of one book may be
DRAFT at once (L2-1-Q-25). ``POST /ssp-book-versions/{id}/entries`` upserts by key, and an unchanged
entry writes nothing (L2-1-Q-26).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Table, and_, delete, func, insert, select, update

from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import (
    gl_account,
    legal_entity,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
)
from erev_api.domain.platform import provisioning, users
from erev_api.domain.reference import fx
from erev_api.domain.reference.commands import CODE_FORMAT, CODE_PATTERN, VALUE_REQUIRED
from erev_api.domain.reference.products import exact_text, series_product_ids
from erev_api.domain.ssp import books, scope
from erev_api.enums import ConfigStatus, SspValueBasis
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.ssp_books import SspBookIn, SspBookVersionIn, SspEntriesIn, SspEntryIn

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

VersionCheck = Callable[[int], None]
BOOK_CREATE: Final = "ssp_book.create"
BOOK_UPDATE: Final = "ssp_book.update"
VERSION_CREATE: Final = "ssp_book_version.create"
VERSION_UPDATE: Final = "ssp_book_version.update"
ENTRY_CREATE: Final = "ssp_entry.create"
ENTRY_UPDATE: Final = "ssp_entry.update"
ENTRY_DELETE: Final = "ssp_entry.delete"
RANGE_CREATE: Final = "ssp_range.create"
RANGE_DELETE: Final = "ssp_range.delete"
RULE_FROZEN: Final = "DB-04"
BOOK_NOT_NULL: Final = ("code", "name", "resolution_mode")
VERSION_NOT_NULL: Final = ("methodology_label", "is_methodology_change")
# The T-REF-30 columns an entry command writes, and the stored key (``ux_ssp_entry__key``).
ENTRY_COLUMNS: Final = (
    "product_id",
    "stratification",
    *books.DIMENSION_KEYS,
    "currency",
    "method",
    "value_basis",
    "quantity_unit",
    *books.ATTRIBUTES,
    "revenue_gl_account_id",
    "distinctness",
)
STORED_KEY: Final = ("product_id", "stratification", *books.DIMENSION_KEYS, "currency")
BandRow = tuple[Any, ...]


# --- helpers -------------------------------------------------------------------------------------


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        **_created(uow),
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _modified(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {"updated_by": principal.id, "updated_by_kind": principal.kind.value}


def _jsonable(value: Any) -> Any:
    """An audit member: ids and decimals as text, enumerations as literals, dates as ISO text."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return exact_text(value)
    return value


def _audit_members(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in values.items()}


def _problem(errors: Sequence[ProblemError]) -> Problem:
    return Problem("validation-failed", errors=errors)


def _label(value: Any, *, field: str, rule_id: str, errors: list[ProblemError]) -> str:
    """A TY-07 label with surrounding spaces removed; appends the finding when it is invalid."""
    label = "" if value is None else str(value).strip()
    if len(label) not in provisioning.LABEL_LENGTH:
        errors.append(ProblemError(field=field, rule_id=rule_id, message=users.NAME_LENGTH))
    return label


def _code_errors(session: Session, code: str, *, book_id: UUID | None) -> list[ProblemError]:
    """TY-06, unique in the workspace (``ux_ssp_book__code``)."""
    if not CODE_PATTERN.fullmatch(code):
        return [ProblemError(field="code", rule_id=books.RULE_BOOK, message=CODE_FORMAT)]
    statement = select(ssp_book.c.id).where(ssp_book.c.code == code)
    if book_id is not None:
        statement = statement.where(ssp_book.c.id != book_id)
    if session.execute(statement).first() is None:
        return []
    message = books.CODE_TAKEN.format(code=code)
    return [ProblemError(field="code", rule_id=books.RULE_BOOK, message=message)]


def _entity_id(uow: UnitOfWork, code: Any, errors: list[ProblemError]) -> UUID | None:
    """The id of the entity ``code`` that the caller's ``ssp.create`` covers; none for an
    absent scope. An entity the session reads through another role, where the permission is
    held for other entities only, answers as a code that names none (supervisor ruling R-28:
    the permission is asked for that entity)."""
    stripped = books.text_key(None if code is None else str(code))
    if stripped is None:
        return None
    found = uow.session.execute(
        select(legal_entity.c.id).where(legal_entity.c.code == stripped)
    ).scalar_one_or_none()
    if found is None or not scope.reaches(uow.principal, scope.CREATE, found):
        errors.append(
            ProblemError(field="entity_code", rule_id=books.RULE_BOOK, message=books.ENTITY_UNKNOWN)
        )
        return None
    return UUID(str(found))


def _currency(session: Session, code: Any, errors: list[ProblemError]) -> str | None:
    """An active ISO 4217 currency as the book scope; none for an absent scope."""
    if code is None:
        return None
    if str(code) not in fx.active_currencies(session, [str(code)]):
        errors.append(
            ProblemError(field="currency", rule_id=books.RULE_BOOK, message=books.CURRENCY_UNKNOWN)
        )
        return None
    return str(code)


def _ids_by_code(
    session: Session, table: Table, codes: Collection[str], *, active_only: bool = False
) -> dict[str, UUID]:
    """The ids of the visible rows of ``table`` among ``codes``, keyed by code."""
    if not codes:
        return {}
    statement = select(table.c.code, table.c.id).where(table.c.code.in_(sorted(codes)))
    if active_only:
        statement = statement.where(table.c.is_active.is_(True))
    return {str(code): UUID(str(row_id)) for code, row_id in session.execute(statement).tuples()}


def _series_products(session: Session, product_ids: Mapping[str, UUID]) -> set[str]:
    """D-97 (3a) / SSP-ADMISSION-R1: the product codes among ``product_ids`` whose default POB
    template has a version of ``series`` distinctness — ``products.series_product_ids``, the one
    predicate ``ProductOut.requires_explicit_ssp_basis`` also exposes; their SSP entries declare an
    explicit E-49 basis."""
    series = series_product_ids(session, list(product_ids.values()))
    return {code for code, product_id in product_ids.items() if product_id in series}


def _book_quantity_units(
    session: Session, book_id: UUID, version_id: UUID, replaced: Collection[tuple[Any, ...]]
) -> dict[str, set[str]]:
    """D-97 (3) agreement scope: every E-125 ``quantity_unit`` the book's retained stored entries
    declare per product code, over every version of the book; the current version's entries whose
    stored key the request replaces are left out (they are being rewritten). A product with more
    than one unit is a contradiction among the stored rows themselves, which ``books.
    quantity_unit_errors`` refuses before anything is written (Codex 8/9 supplemental: the first
    stored row is never silently authoritative)."""
    statement = (
        select(
            product.c.code,
            ssp_entry.c.ssp_book_version_id,
            ssp_entry.c.quantity_unit,
            *(ssp_entry.c[name] for name in STORED_KEY),
        )
        .select_from(
            ssp_entry.join(
                ssp_book_version,
                and_(
                    ssp_book_version.c.tenant_id == ssp_entry.c.tenant_id,
                    ssp_book_version.c.id == ssp_entry.c.ssp_book_version_id,
                ),
            ).join(
                product,
                and_(
                    product.c.tenant_id == ssp_entry.c.tenant_id,
                    product.c.id == ssp_entry.c.product_id,
                ),
            )
        )
        .where(
            ssp_book_version.c.ssp_book_id == book_id,
            ssp_entry.c.quantity_unit.is_not(None),
        )
        .order_by(ssp_book_version.c.version_no, ssp_entry.c.id)
    )
    units: dict[str, set[str]] = {}
    for row in session.execute(statement).mappings():
        key = tuple(row[name] for name in STORED_KEY)
        if UUID(str(row["ssp_book_version_id"])) == version_id and key in replaced:
            continue
        units.setdefault(str(row["code"]), set()).add(str(row["quantity_unit"]))
    return units


def _lock_version(session: Session, version_id: UUID) -> Mapping[str, Any]:
    """The version under ``FOR UPDATE``; 404 when it is not visible."""
    row = (
        session.execute(
            select(ssp_book_version).where(ssp_book_version.c.id == version_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _require_draft(version: Mapping[str, Any]) -> None:
    """409 ``configuration-frozen`` unless the version is DRAFT (DB-04; PRD ERR-09)."""
    if version["status"] != ConfigStatus.DRAFT.value:
        error = ProblemError(field="status", rule_id=RULE_FROZEN, message=books.NOT_DRAFT)
        raise Problem("configuration-frozen", errors=[error])


def _label_errors(
    session: Session, book_id: UUID, label: str | None, *, version_id: UUID | None
) -> list[ProblemError]:
    """``ux_ssp_book_version__label``: a label names one version of the book."""
    if label is None:
        return []
    statement = select(ssp_book_version.c.id).where(
        ssp_book_version.c.ssp_book_id == book_id,
        ssp_book_version.c.legacy_version_label == label,
    )
    if version_id is not None:
        statement = statement.where(ssp_book_version.c.id != version_id)
    if session.execute(statement).first() is None:
        return []
    message = books.LABEL_TAKEN.format(label=label)
    return [ProblemError(field="legacy_version_label", rule_id=books.RULE_VERSION, message=message)]


def _effective_errors(effective_from: date | None, effective_to: date | None) -> list[ProblemError]:
    """T-REF-29: ``effective_to_date`` is null or on or after ``effective_from_date``."""
    if effective_to is None or effective_from is None or effective_to >= effective_from:
        return []
    return [
        ProblemError(
            field="effective_to_date", rule_id=books.RULE_VERSION, message=books.EFFECTIVE_ORDER
        )
    ]


# --- books ---------------------------------------------------------------------------------------


def create_ssp_book(uow: UnitOfWork, *, body: SspBookIn) -> UUID:
    """``POST /ssp-books``: 422 collects the findings on code, name, entity and currency."""
    session = uow.session
    errors: list[ProblemError] = []
    code = body.code.strip()
    errors += _code_errors(session, code, book_id=None)
    name = _label(body.name, field="name", rule_id=books.RULE_BOOK, errors=errors)
    entity_id = _entity_id(uow, body.entity_code, errors)
    currency = _currency(session, body.currency, errors)
    if errors:
        raise _problem(errors)
    values = {
        "code": code,
        "name": name,
        "description": books.text_key(body.description),
        "entity_id": entity_id,
        "currency": currency,
        "channel": books.text_key(body.channel),
        "segment": books.text_key(body.segment),
        "resolution_mode": body.resolution_mode,
    }
    book_id = new_id()
    session.execute(
        insert(ssp_book).values(
            tenant_id=uow.principal.tenant_id, id=book_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=BOOK_CREATE,
        object_type=books.OBJECT_BOOK,
        object_id=book_id,
        after=_audit_members(values),
    )
    return book_id


def _entries_in_other_currency(session: Session, book_id: UUID, currency: str) -> bool:
    statement = (
        select(ssp_entry.c.id)
        .join(
            ssp_book_version,
            (ssp_book_version.c.tenant_id == ssp_entry.c.tenant_id)
            & (ssp_book_version.c.id == ssp_entry.c.ssp_book_version_id),
        )
        .where(ssp_book_version.c.ssp_book_id == book_id, ssp_entry.c.currency != currency)
        .limit(1)
    )
    return session.execute(statement).first() is not None


def _has_approved_version(session: Session, book_id: UUID) -> bool:
    """DB-05: a book with an APPROVED version keeps its scope (BUILD_SPEC RFD-13)."""
    statement = (
        select(ssp_book_version.c.id)
        .where(
            ssp_book_version.c.ssp_book_id == book_id,
            ssp_book_version.c.status.in_(
                [ConfigStatus.APPROVED.value, ConfigStatus.SUPERSEDED.value]
            ),
        )
        .limit(1)
    )
    return session.execute(statement).first() is not None


def _has_submitted_version(session: Session, book_id: UUID) -> bool:
    """A version of the book is under approval: its content, the book's scope included, is what
    the approver certifies (04 §16.10 rev 1.110; REQ-PLT-014; security ruling R-27)."""
    statement = (
        select(ssp_book_version.c.id)
        .where(
            ssp_book_version.c.ssp_book_id == book_id,
            ssp_book_version.c.status == ConfigStatus.SUBMITTED.value,
        )
        .limit(1)
    )
    return session.execute(statement).first() is not None


def update_ssp_book(
    uow: UnitOfWork, book_id: UUID, *, changes: Mapping[str, Any], check_version: VersionCheck
) -> None:
    """``PATCH /ssp-books/{id}``: 404; 428 or 412 for ``If-Match``; 422 collects the findings, among
    them a currency scope that stored entries contradict (L2-1-Q-27), then refuses a change of the
    scope or resolution mode once a version is APPROVED (DB-05); 409 ``configuration-frozen`` for
    such a change while a version is SUBMITTED (04 API-S-SspBook rev 1.110; the book row is locked
    here and by ``publication.submit_ssp_book_version``, so a submission and a scope change never
    cross)."""
    session = uow.session
    current = scope.require_book(session, uow.principal, scope.CREATE, book_id, lock=True)
    check_version(int(current["row_version"]))
    errors = [
        ProblemError(field=member, rule_id=books.RULE_BOOK, message=VALUE_REQUIRED)
        for member in BOOK_NOT_NULL
        if member in changes and changes[member] is None
    ]
    values: dict[str, Any] = {}
    if changes.get("code") is not None:
        values["code"] = str(changes["code"]).strip()
        errors += _code_errors(session, values["code"], book_id=book_id)
    if changes.get("name") is not None:
        values["name"] = _label(
            changes["name"], field="name", rule_id=books.RULE_BOOK, errors=errors
        )
    for member in ("description", "channel", "segment"):
        if member in changes:
            values[member] = books.text_key(changes[member])
    if "entity_code" in changes:
        values["entity_id"] = _entity_id(uow, changes["entity_code"], errors)
    if "currency" in changes:
        values["currency"] = _currency(session, changes["currency"], errors)
        if (
            values["currency"] is not None
            and values["currency"] != current["currency"]
            and _entries_in_other_currency(session, book_id, values["currency"])
        ):
            errors.append(
                ProblemError(
                    field="currency", rule_id=books.RULE_BOOK, message=books.CURRENCY_IN_USE
                )
            )
    if changes.get("resolution_mode") is not None:
        values["resolution_mode"] = str(changes["resolution_mode"])
    if errors:
        raise _problem(errors)
    changed = {name: value for name, value in values.items() if current[name] != value}
    if not changed:
        return
    frozen = [name for name in books.SCOPE_MEMBERS if name in changed]
    if frozen and _has_approved_version(session, book_id):
        raise _problem(
            [
                ProblemError(
                    field=books.SCOPE_MEMBERS[name],
                    rule_id=books.RULE_SCOPE,
                    message=books.SCOPE_FROZEN,
                )
                for name in frozen
            ]
        )
    if frozen and _has_submitted_version(session, book_id):
        raise Problem(
            "configuration-frozen",
            errors=[
                ProblemError(
                    field=books.SCOPE_MEMBERS[name],
                    rule_id=books.RULE_SCOPE_UNDER_APPROVAL,
                    message=books.SCOPE_UNDER_APPROVAL,
                )
                for name in frozen
            ],
        )
    session.execute(
        update(ssp_book).where(ssp_book.c.id == book_id).values(**changed, **_modified(uow))
    )
    uow.audit(
        action=BOOK_UPDATE,
        object_type=books.OBJECT_BOOK,
        object_id=book_id,
        before=_audit_members({name: current[name] for name in changed}),
        after=_audit_members(changed),
    )


# --- versions ------------------------------------------------------------------------------------


def _insert_bands(uow: UnitOfWork, entry_id: UUID, bands: Sequence[books.BandDraft]) -> list[UUID]:
    rows = [
        {
            "tenant_id": uow.principal.tenant_id,
            "id": new_id(),
            "ssp_entry_id": entry_id,
            "band_dimension": band.band_dimension,
            **{name: getattr(band, name) for name in books.BAND_VALUES},
            **_created(uow),
        }
        for band in bands
    ]
    if rows:
        uow.session.execute(insert(ssp_range), rows)
    return [row["id"] for row in rows]


def _copy_entries(
    uow: UnitOfWork, *, source_id: UUID, version_id: UUID
) -> tuple[list[UUID], list[UUID]]:
    """Copy the entries and bands of ``source_id`` into the new DRAFT version."""
    session = uow.session
    rows = (
        session.execute(
            select(ssp_entry)
            .where(ssp_entry.c.ssp_book_version_id == source_id)
            .order_by(ssp_entry.c.id)
        )
        .mappings()
        .all()
    )
    if not rows:
        return [], []
    tenant_id = uow.principal.tenant_id
    created = _created(uow)
    new_ids = {UUID(str(row["id"])): new_id() for row in rows}
    entry_rows = [
        {
            "tenant_id": tenant_id,
            "id": new_ids[UUID(str(row["id"]))],
            "ssp_book_version_id": version_id,
            **{name: row[name] for name in ENTRY_COLUMNS},
            **created,
        }
        for row in rows
    ]
    session.execute(insert(ssp_entry), entry_rows)
    bands = (
        session.execute(
            select(ssp_range)
            .where(ssp_range.c.ssp_entry_id.in_(sorted(new_ids)))
            .order_by(ssp_range.c.id)
        )
        .mappings()
        .all()
    )
    band_rows = [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "ssp_entry_id": new_ids[UUID(str(band["ssp_entry_id"]))],
            "band_dimension": band["band_dimension"],
            **{name: band[name] for name in books.BAND_VALUES},
            **created,
        }
        for band in bands
    ]
    if band_rows:
        session.execute(insert(ssp_range), band_rows)
    return [row["id"] for row in entry_rows], [row["id"] for row in band_rows]


def _record_entry_facts(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    created: Sequence[UUID] = (),
    updated: Sequence[UUID] = (),
    deleted: Sequence[UUID] = (),
    bands_deleted: Sequence[UUID] = (),
    bands_created: Sequence[UUID] = (),
) -> None:
    detail = {"ssp_book_version_id": str(version_id)}
    for action, object_type, ids in (
        (ENTRY_CREATE, books.OBJECT_ENTRY, created),
        (ENTRY_UPDATE, books.OBJECT_ENTRY, updated),
        (ENTRY_DELETE, books.OBJECT_ENTRY, deleted),
        (RANGE_DELETE, books.OBJECT_RANGE, bands_deleted),
        (RANGE_CREATE, books.OBJECT_RANGE, bands_created),
    ):
        if ids:
            audit_writer.record_facts(
                uow, action=action, object_type=object_type, ids=ids, detail=detail
            )


def create_ssp_book_version(uow: UnitOfWork, book_id: UUID, *, body: SspBookVersionIn) -> UUID:
    """``POST /ssp-books/{id}/versions``: the next version as DRAFT, optionally copying the entries
    of ``copy_from_version_id``.

    404 for an unknown book; 422 collects the findings on ``copy_from_version_id`` (a version of
    this book), ``legacy_version_label`` (unique in the book), ``effective_to_date`` and
    ``methodology_label``. The version names the latest APPROVED version of the book as the one it
    supersedes (L2-1-Q-25).
    """
    session = uow.session
    scope.require_book(session, uow.principal, scope.CREATE, book_id, lock=True)
    versions = (
        session.execute(
            select(
                ssp_book_version.c.id, ssp_book_version.c.version_no, ssp_book_version.c.status
            ).where(ssp_book_version.c.ssp_book_id == book_id)
        )
        .mappings()
        .all()
    )
    errors: list[ProblemError] = []
    source_id = body.copy_from_version_id
    if source_id is not None and all(row["id"] != source_id for row in versions):
        errors.append(
            ProblemError(
                field="copy_from_version_id", rule_id=books.RULE_VERSION, message=books.COPY_UNKNOWN
            )
        )
    label = books.text_key(body.legacy_version_label)
    errors += _label_errors(session, book_id, label, version_id=None)
    errors += _effective_errors(body.effective_from_date, body.effective_to_date)
    methodology = _label(
        body.methodology_label, field="methodology_label", rule_id=books.RULE_VERSION, errors=errors
    )
    if errors:
        raise _problem(errors)
    approved = [row for row in versions if row["status"] == ConfigStatus.APPROVED.value]
    supersedes = max(approved, key=lambda row: int(row["version_no"]))["id"] if approved else None
    version_no = max((int(row["version_no"]) for row in versions), default=0) + 1
    copied_count = 0
    if source_id is not None:
        copied_count = int(
            session.execute(
                select(func.count())
                .select_from(ssp_entry)
                .where(ssp_entry.c.ssp_book_version_id == source_id)
            ).scalar_one()
        )
    values = {
        "legacy_version_label": label,
        "effective_from_date": body.effective_from_date,
        "effective_to_date": body.effective_to_date,
        "methodology_label": methodology,
        "is_methodology_change": body.is_methodology_change,
    }
    version_id = new_id()
    session.execute(
        insert(ssp_book_version).values(
            tenant_id=uow.principal.tenant_id,
            id=version_id,
            ssp_book_id=book_id,
            **values,
            entry_count=copied_count,
            **_stamps(uow),
            version_no=version_no,
            status=ConfigStatus.DRAFT.value,
            supersedes_version_id=supersedes,
        )
    )
    copied, bands = (
        ([], [])
        if source_id is None
        else _copy_entries(uow, source_id=source_id, version_id=version_id)
    )
    uow.audit(
        action=VERSION_CREATE,
        object_type=books.OBJECT_VERSION,
        object_id=version_id,
        after=_audit_members(
            {
                "ssp_book_id": book_id,
                **values,
                "version_no": version_no,
                "status": ConfigStatus.DRAFT.value,
                "supersedes_version_id": supersedes,
            }
        ),
        detail={
            "copy_from_version_id": None if source_id is None else str(source_id),
            "entries_copied": len(copied),
        },
    )
    _record_entry_facts(uow, version_id, created=copied, bands_created=bands)
    return version_id


def update_ssp_book_version(
    uow: UnitOfWork, version_id: UUID, *, changes: Mapping[str, Any], check_version: VersionCheck
) -> None:
    """``PATCH /ssp-book-versions/{id}``: 404; 428 or 412 for ``If-Match``; 409
    ``configuration-frozen`` unless DRAFT; 422 collects the findings."""
    session = uow.session
    scope.require_version_book(session, uow.principal, scope.CREATE, version_id)
    current = _lock_version(session, version_id)
    check_version(int(current["row_version"]))
    _require_draft(current)
    errors = [
        ProblemError(field=member, rule_id=books.RULE_VERSION, message=VALUE_REQUIRED)
        for member in VERSION_NOT_NULL
        if member in changes and changes[member] is None
    ]
    values: dict[str, Any] = {}
    if "legacy_version_label" in changes:
        values["legacy_version_label"] = books.text_key(changes["legacy_version_label"])
        errors += _label_errors(
            session,
            UUID(str(current["ssp_book_id"])),
            values["legacy_version_label"],
            version_id=version_id,
        )
    for member in ("effective_from_date", "effective_to_date"):
        if member in changes:
            values[member] = changes[member]
    if "effective_from_date" in values or "effective_to_date" in values:
        errors += _effective_errors(
            values.get("effective_from_date", current["effective_from_date"]),
            values.get("effective_to_date", current["effective_to_date"]),
        )
    if changes.get("methodology_label") is not None:
        values["methodology_label"] = _label(
            changes["methodology_label"],
            field="methodology_label",
            rule_id=books.RULE_VERSION,
            errors=errors,
        )
    if changes.get("is_methodology_change") is not None:
        values["is_methodology_change"] = bool(changes["is_methodology_change"])
    if errors:
        raise _problem(errors)
    changed = {name: value for name, value in values.items() if current[name] != value}
    if not changed:
        return
    session.execute(
        update(ssp_book_version)
        .where(ssp_book_version.c.id == version_id)
        .values(**changed, **_modified(uow))
    )
    uow.audit(
        action=VERSION_UPDATE,
        object_type=books.OBJECT_VERSION,
        object_id=version_id,
        before=_audit_members({name: current[name] for name in changed}),
        after=_audit_members(changed),
    )


# --- entries -------------------------------------------------------------------------------------


def _band_draft(band: Any) -> books.BandDraft:
    return books.BandDraft(
        band_dimension=str(band.band_dimension),
        **{name: books.decimal_or_none(getattr(band, name)) for name in books.BAND_VALUES},
    )


def _draft(entry: SspEntryIn) -> books.EntryDraft:
    """The entry with trimmed keys and parsed decimals (L2-1-Q-26)."""
    return books.EntryDraft(
        product_code=entry.product_code.strip(),
        stratification=entry.stratification.strip(),
        region=books.text_key(entry.region),
        channel=books.text_key(entry.channel),
        segment=books.text_key(entry.segment),
        deal_size_band=books.text_key(entry.deal_size_band),
        term_band=books.text_key(entry.term_band),
        currency=entry.currency,
        method=entry.method.value,
        value_basis=None if entry.value_basis is None else entry.value_basis.value,
        quantity_unit=None if entry.quantity_unit is None else entry.quantity_unit.value,
        unit_list_price=books.decimal_or_none(entry.unit_list_price),
        midpoint_discount_ratio=books.decimal_or_none(entry.midpoint_discount_ratio),
        range_ratio=books.decimal_or_none(entry.range_ratio),
        cost_basis=books.decimal_or_none(entry.cost_basis),
        margin_ratio=books.decimal_or_none(entry.margin_ratio),
        observable_point=books.decimal_or_none(entry.observable_point),
        revenue_account_code=books.text_key(entry.revenue_account_code),
        distinctness=entry.distinctness.value,
        ranges=None if entry.ranges is None else tuple(_band_draft(band) for band in entry.ranges),
    )


def _band_order(band: BandRow) -> tuple[str, bool, Decimal]:
    start = band[1]
    return (str(band[0]), start is not None, Decimal(0) if start is None else Decimal(start))


def _band_rows(bands: Sequence[books.BandDraft]) -> list[BandRow]:
    rows = [
        (band.band_dimension, *(getattr(band, name) for name in books.BAND_VALUES))
        for band in bands
    ]
    return sorted(rows, key=_band_order)


def _stored_entries(
    session: Session, version_id: UUID
) -> dict[tuple[Any, ...], tuple[UUID, dict[str, Any], list[BandRow]]]:
    """The version's entries by stored key: id, written columns and bands."""
    rows = (
        session.execute(select(ssp_entry).where(ssp_entry.c.ssp_book_version_id == version_id))
        .mappings()
        .all()
    )
    bands: dict[UUID, list[BandRow]] = {}
    if rows:
        statement = select(ssp_range).where(
            ssp_range.c.ssp_entry_id.in_(sorted(UUID(str(row["id"])) for row in rows))
        )
        for band in session.execute(statement).mappings():
            bands.setdefault(UUID(str(band["ssp_entry_id"])), []).append(
                (band["band_dimension"], *(band[name] for name in books.BAND_VALUES))
            )
    return {
        tuple(row[name] for name in STORED_KEY): (
            UUID(str(row["id"])),
            {name: row[name] for name in ENTRY_COLUMNS},
            sorted(bands.get(UUID(str(row["id"])), []), key=_band_order),
        )
        for row in rows
    }


def _refresh_entry_count(uow: UnitOfWork, version_id: UUID) -> None:
    session = uow.session
    count = session.execute(
        select(func.count())
        .select_from(ssp_entry)
        .where(ssp_entry.c.ssp_book_version_id == version_id)
    ).scalar_one()
    session.execute(
        update(ssp_book_version)
        .where(ssp_book_version.c.id == version_id)
        .values(entry_count=int(count), **_modified(uow))
    )


def upsert_ssp_entries(uow: UnitOfWork, version_id: UUID, *, body: SspEntriesIn) -> list[UUID]:
    """``POST /ssp-book-versions/{id}/entries``: the ids of the stored entries in request order.

    404 for an unknown version; 409 ``configuration-frozen`` unless DRAFT; 422 collects the findings
    of every entry (``books.entry_errors``), then ``SSP_DUPLICATE_KEY`` for each key the request
    repeats. An entry whose key the version holds replaces that entry and all its bands
    (L2-1-Q-26).
    """
    session = uow.session
    scope.require_version_book(session, uow.principal, scope.CREATE, version_id)
    current = _lock_version(session, version_id)
    _require_draft(current)
    book_currency = session.execute(
        select(ssp_book.c.currency).where(ssp_book.c.id == current["ssp_book_id"])
    ).scalar_one()
    drafts = [_draft(entry) for entry in body.entries]
    product_ids = _ids_by_code(session, product, {draft.product_code for draft in drafts})
    account_ids = _ids_by_code(
        session,
        gl_account,
        {draft.revenue_account_code for draft in drafts if draft.revenue_account_code is not None},
        active_only=True,
    )
    currencies = fx.active_currencies(session, sorted({draft.currency for draft in drafts}))
    series_products = _series_products(session, product_ids)
    errors: list[ProblemError] = []
    for index, draft in enumerate(drafts):
        errors += books.entry_errors(
            index,
            draft,
            products=product_ids.keys(),
            accounts=account_ids.keys(),
            currencies=currencies,
            book_currency=None if book_currency is None else str(book_currency),
            series_products=series_products,
        )
    replaced = {
        (
            product_ids.get(draft.product_code),
            draft.stratification,
            *(getattr(draft, name) for name in books.DIMENSION_KEYS),
            draft.currency,
        )
        for draft in drafts
    }
    errors += books.quantity_unit_errors(
        drafts,
        _book_quantity_units(session, UUID(str(current["ssp_book_id"])), version_id, replaced),
    )
    errors += books.duplicate_key_errors(drafts)
    if errors:
        raise _problem(errors)
    stored = _stored_entries(session, version_id)
    tenant_id = uow.principal.tenant_id
    created: list[UUID] = []
    updated: list[UUID] = []
    bands_created: list[UUID] = []
    bands_deleted: list[UUID] = []
    ids: list[UUID] = []
    for draft in drafts:
        account = draft.revenue_account_code
        values = {
            "product_id": product_ids[draft.product_code],
            "stratification": draft.stratification,
            **{name: getattr(draft, name) for name in books.DIMENSION_KEYS},
            "currency": draft.currency,
            "method": draft.method,
            # D-97 (3a): the T-REF-30 default applies to a non-series product's omitted basis
            # only; a series product's omission was refused above.
            "value_basis": draft.value_basis or SspValueBasis.AMOUNT.value,
            "quantity_unit": draft.quantity_unit,
            **{name: getattr(draft, name) for name in books.ATTRIBUTES},
            "revenue_gl_account_id": None if account is None else account_ids[account],
            "distinctness": draft.distinctness,
        }
        bands = books.derived_bands(draft)
        found = stored.get(tuple(values[name] for name in STORED_KEY))
        if found is None:
            entry_id = new_id()
            session.execute(
                insert(ssp_entry).values(
                    tenant_id=tenant_id,
                    id=entry_id,
                    ssp_book_version_id=version_id,
                    **values,
                    **_created(uow),
                )
            )
            created.append(entry_id)
        else:
            entry_id, stored_values, stored_bands = found
            if stored_values == values and stored_bands == _band_rows(bands):
                ids.append(entry_id)
                continue
            session.execute(update(ssp_entry).where(ssp_entry.c.id == entry_id).values(**values))
            removed = session.execute(
                delete(ssp_range)
                .where(ssp_range.c.ssp_entry_id == entry_id)
                .returning(ssp_range.c.id)
            ).scalars()
            bands_deleted += [UUID(str(value)) for value in removed]
            updated.append(entry_id)
        bands_created += _insert_bands(uow, entry_id, bands)
        ids.append(entry_id)
    if created or updated:
        _refresh_entry_count(uow, version_id)
    _record_entry_facts(
        uow,
        version_id,
        created=created,
        updated=updated,
        bands_deleted=bands_deleted,
        bands_created=bands_created,
    )
    return ids


def delete_ssp_entry(uow: UnitOfWork, version_id: UUID, entry_id: UUID) -> None:
    """``DELETE /ssp-book-versions/{id}/entries/{entry_id}``: 404 for an entry outside the version;
    409 ``configuration-frozen`` unless DRAFT. The bands go first: DB-04 reads their entry."""
    session = uow.session
    scope.require_version_book(session, uow.principal, scope.CREATE, version_id)
    current = _lock_version(session, version_id)
    found = session.execute(
        select(ssp_entry.c.id).where(
            ssp_entry.c.id == entry_id, ssp_entry.c.ssp_book_version_id == version_id
        )
    ).first()
    if found is None:
        raise Problem("not-found")
    _require_draft(current)
    removed = session.execute(
        delete(ssp_range).where(ssp_range.c.ssp_entry_id == entry_id).returning(ssp_range.c.id)
    ).scalars()
    bands_deleted = [UUID(str(value)) for value in removed]
    session.execute(delete(ssp_entry).where(ssp_entry.c.id == entry_id))
    _refresh_entry_count(uow, version_id)
    _record_entry_facts(uow, version_id, deleted=[entry_id], bands_deleted=bands_deleted)

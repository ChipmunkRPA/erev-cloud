"""Avenmoor SSP books (PRD §2.6 products and SSP entries; BUILD_SPEC RFD-16).

``maya`` (SSP Analyst) creates each book and its first version with the §2.6 entries, uploads the
list-price study and submits the version; ``priya`` (SSP Approver) approves it. ``US-LIST 2026-H1``,
``UK-LIST 2026`` and ``DE-LIST 2026`` are effective 2026-01-01 and ``JP-LIST FY2027`` 2026-04-01.

[J] L4-5-Q-4: the documents name no study document, so the study is a CSV of the version's entries
generated here (deterministic bytes, PRD WLD-R-01; SSP submission needs a study, SCREENS §11.3).

Item DEMO-SSP-BASIS-1 (supervisor's ruling on MOD-K02-SPLIT-1, 2026-10-01): the entry of a
``series`` product measured by time elapsed declares its pricing basis (04 E-49; D-93 (4),
D-97 (3); ENGINE_SPEC S06-R-11 series row), as PRD §2.6 words it. AVM-SEAT-MO is priced "per
seat-month" and its lines count seat-months: ``PER_INCREMENT`` with quantity unit
``INCREMENTS``. AVM-PLAT-ENT, AVM-PLAT-100, AVM-PLAT-UK and AVM-SUP-12 are priced for their
booked term of 12 months: ``PER_BOOKED_TERM``. Seeded as ``AMOUNT`` — which on a series entry
is the remaining-increments reading, taken as is — the K-02 change of PRD WLD-X-06 weighed O1
at 2,400 x 100.00 = 240,000.00 instead of its remaining increments at the modification date
(155,178.08) and previewed 166,723.94 / 48,454.14 where the PRD and CTR-17's acceptance have
148,451.55 / 66,726.53. An inception allocation does not read the series bases (stage 05).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import ssp_book_version
from erev_api.domain.demo.avenmoor import ACCOUNTANT, SSP_APPROVER, expect_version
from erev_api.domain.platform import attachments
from erev_api.domain.ssp import commands, publication
from erev_api.enums import (
    ApprovalSubjectType,
    Distinctness,
    FilePurpose,
    SspMethod,
    SspQuantityUnit,
    SspValueBasis,
)
from erev_api.schemas.ssp_books import (
    SspBookIn,
    SspBookVersionIn,
    SspEntriesIn,
    SspEntryIn,
    SspRangeIn,
)

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

SSP_CREATE: Final = "ssp.create"
METHODOLOGY: Final = "List-price study"
STUDY_COLUMNS: Final = ("product_code", "currency", "method", "value_basis", "low", "mid", "high")
STUDY_MEDIA_TYPE: Final = "text/csv"
SUBMIT_COMMENT: Final = "Supported by the list-price study."


@dataclass(frozen=True, slots=True)
class EntrySpec:
    product_code: str
    method: SspMethod
    point: str | None = None
    low: str | None = None
    mid: str | None = None
    high: str | None = None
    value_basis: SspValueBasis = SspValueBasis.AMOUNT
    unit_list_price: str | None = None  # the list price a PERCENT_OF_LIST ratio applies to
    # What a line's quantity counts under a PER_INCREMENT entry (04 T-REF-30; D-97 (3)): every
    # dated entry of one product in one book states the same unit (the engine fails closed).
    quantity_unit: SspQuantityUnit | None = None


@dataclass(frozen=True, slots=True)
class BookSpec:
    code: str
    name: str
    currency: str
    version_label: str
    effective_from: date
    entries: tuple[EntrySpec, ...]


_OBS, _CPM = SspMethod.OBSERVABLE, SspMethod.COST_PLUS_MARGIN
# The bases a series entry declares (module docstring, item DEMO-SSP-BASIS-1).
_TERM: Final = SspValueBasis.PER_BOOKED_TERM
BOOKS: Final[tuple[BookSpec, ...]] = (
    BookSpec(
        "US-LIST",
        "US list prices",
        "USD",
        "2026-H1",
        date(2026, 1, 1),
        (
            EntrySpec("AVM-PLAT-ENT", _OBS, point="132000.00", value_basis=_TERM),
            EntrySpec(
                "AVM-SEAT-MO",
                _OBS,
                low="90.00",
                mid="100.00",
                high="110.00",
                value_basis=SspValueBasis.PER_INCREMENT,
                quantity_unit=SspQuantityUnit.INCREMENTS,
            ),
            EntrySpec(
                "AVM-PLAT-100",
                _OBS,
                low="85000.00",
                mid="100000.00",
                high="115000.00",
                value_basis=_TERM,
            ),
            EntrySpec("AVM-IMPL-STD", _CPM, point="18000.00"),
            EntrySpec("AVM-IMPL-PLUS", _CPM, low="18000.00", mid="20000.00", high="22000.00"),
            EntrySpec("AVM-API-CALL", _OBS, point="0.10"),
            # PERCENT_OF_LIST (E-49): a ratio of list price, point 100%. [J] L5-4-Q-3 (CTR-20): the
            # engine prices the ratio with the entry's unit list price, which PRD §2.6 does not
            # state; the list price is K-03's fixed price 1,000,000.00.
            EntrySpec(
                "AVM-ENG-BUILD",
                _CPM,
                point="1",
                value_basis=SspValueBasis.PERCENT_OF_LIST,
                unit_list_price="1000000.00",
            ),
        ),
    ),
    BookSpec(
        "UK-LIST",
        "UK list prices",
        "GBP",
        "2026",
        date(2026, 1, 1),
        (
            EntrySpec("AVM-PLAT-UK", _OBS, point="60000.00", value_basis=_TERM),
            EntrySpec("AVM-IMPL-UK", _CPM, point="10000.00"),
        ),
    ),
    BookSpec(
        "DE-LIST",
        "DE list prices",
        "EUR",
        "2026",
        date(2026, 1, 1),
        (
            EntrySpec("AVM-KIT", _OBS, point="100.00"),
            EntrySpec("AVM-PART", _OBS, point="100.00"),
            EntrySpec("AVM-GW", _OBS, low="405.00", mid="450.00", high="495.00"),
            EntrySpec("AVM-FLEET", _OBS, point="100000.00"),
            EntrySpec(
                "AVM-SUP-12",
                _CPM,
                low="19000.00",
                mid="20000.00",
                high="21000.00",
                value_basis=_TERM,
            ),
        ),
    ),
    BookSpec(
        "JP-LIST",
        "JP list prices",
        "JPY",
        "FY2027",
        date(2026, 4, 1),
        (EntrySpec("AVM-LIB-LIC", _OBS, point="50000000"),),
    ),
)


def entry_in(spec: EntrySpec, currency: str) -> SspEntryIn:
    band = (
        SspRangeIn(point_value=spec.point)
        if spec.point is not None
        else SspRangeIn(low_value=spec.low, mid_value=spec.mid, high_value=spec.high)
    )
    return SspEntryIn(
        product_code=spec.product_code,
        currency=currency,
        method=spec.method,
        value_basis=spec.value_basis,
        quantity_unit=spec.quantity_unit,
        distinctness=Distinctness.DISTINCT,
        unit_list_price=spec.unit_list_price,
        ranges=[band],
    )


def study_document(book: BookSpec) -> bytes:
    """The list-price study of a book version as CSV (UTF-8, LF line ends); the same bytes on every
    call."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(STUDY_COLUMNS)
    for spec in book.entries:
        writer.writerow(
            (
                spec.product_code,
                book.currency,
                spec.method.value,
                spec.value_basis.value,
                spec.low or "",
                spec.mid or spec.point or "",
                spec.high or "",
            )
        )
    return buffer.getvalue().encode("utf-8")


def study_filename(book: BookSpec) -> str:
    return f"{book.code.lower()}-{book.version_label.lower()}-study.csv"


def _book(ctx: BuildContext, book: BookSpec) -> UUID:
    with ctx.command(ACCOUNTANT, SSP_CREATE) as uow:
        book_id = commands.create_ssp_book(
            uow, body=SspBookIn(code=book.code, name=book.name, currency=book.currency)
        )
    with ctx.command(ACCOUNTANT, SSP_CREATE) as uow:
        version_id = commands.create_ssp_book_version(
            uow,
            book_id,
            body=SspBookVersionIn(
                legacy_version_label=book.version_label,
                effective_from_date=book.effective_from,
                methodology_label=METHODOLOGY,
            ),
        )
    with ctx.command(ACCOUNTANT, SSP_CREATE) as uow:
        commands.upsert_ssp_entries(
            uow,
            version_id,
            body=SspEntriesIn(entries=[entry_in(spec, book.currency) for spec in book.entries]),
        )
    with ctx.command(ACCOUNTANT) as uow:
        stored = attachments.upload_file(
            uow,
            purpose=FilePurpose.SSP_STUDY.value,
            stream=io.BytesIO(study_document(book)),
            original_filename=study_filename(book),
            media_type=STUDY_MEDIA_TYPE,
        )
    with ctx.command(ACCOUNTANT) as uow:
        attachments.attach(
            uow,
            file_object_id=UUID(str(stored["id"])),
            subject_type="ssp_book_version",
            subject_id=version_id,
            description=f"{book.code} {book.version_label} list-price study",
        )
    with ctx.read() as session:
        row_version = session.execute(
            select(ssp_book_version.c.row_version).where(ssp_book_version.c.id == version_id)
        ).scalar_one()
    with ctx.command(ACCOUNTANT, SSP_CREATE) as uow:
        publication.submit_ssp_book_version(
            uow,
            version_id,
            comment=SUBMIT_COMMENT,
            check_version=expect_version(int(row_version)),
        )
    ctx.approve(ApprovalSubjectType.SSP_BOOK_VERSION, version_id, [SSP_APPROVER])
    return version_id


def build(ctx: BuildContext) -> None:
    """The four SSP books of PRD §2.6 with their approved first versions."""
    for book in BOOKS:
        _book(ctx, book)

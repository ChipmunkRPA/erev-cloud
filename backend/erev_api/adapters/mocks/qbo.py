"""QuickBooks Online mock server (05 ADP-20 to ADP-23; PRD J-01.16; 03 REQ-JE-015, REQ-INT-009;
BUILD_SPEC CLO-15).

State is in memory per api process, one company per realm, and restored by ``POST
/__admin/reset``. Routes, under ``/api/v1/__mocks__/qbo`` (the v3 accounting API shapes,
minimally):

- ``POST /v3/company/<realm>/journalentry?requestid=<uuid>`` creates one journal entry and answers
  ``{"JournalEntry": {...}}``; a repeated ``requestid`` returns the stored first response and
  books nothing (ADP-23). An entry whose debits and credits differ, without a line, without a
  ``requestid`` or with a ``DocNumber`` longer than 21 characters answers 400 with a
  ``ValidationFault``;
- ``GET /v3/company/<realm>/query?query=select * from JournalEntry where DocNumber = '<n>'`` finds
  entries by document number (the adapter's ``get_posting``);
- ``GET /v3/company/<realm>/reports/TrialBalance?end_date=&accounts=`` — per account the closing
  balance at ``end_date`` as debit and credit columns: every document dated through it, an income
  statement account (account types Income, Other Income, Expense, Other Expense, Cost of Goods
  Sold — stated by a line's ``AccountRef.type``) within the calendar year of ``end_date``, the
  mock company's fiscal year;
- ``GET /v3/company/<realm>/reports/TransactionList?start_date=&end_date=&accounts=`` — one row
  per document and account dated inside the range: date, document number, account, amount (debit
  positive) and the private note, which is the ADP-10 external id of a chunk this subledger posted
  and empty for a document made in QuickBooks;
- ``POST /__erp/documents``: mock administration for a test or a seed that states a document the
  company itself booked (``account`` names the realm), as the NetSuite mock's.

A company keeps its ledger in one currency, its home currency: that of the first document booked
to it, which both reports state. This subledger states a journal in the entity's functional
currency with the functional amounts (05 ADP-10 rev 1.92; supervisor ruling R-110), so its
journals arrive in that currency whatever the contracts' currencies. The mock holds no exchange
rates and converts nothing: a document in another currency than the company's is refused (400,
``ValidationFault``). A line with amount 0.00 books nothing.

Faults (ADP-21) on the journal route: ``RATE_LIMIT``, ``SERVER_ERROR`` and ``PERMANENT_ERROR``
answer before anything is stored; ``TIMEOUT`` stores the entry and answers 504 — the answer was
lost, the adapter's ``get_posting`` finds the document (ADP-15); ``DUPLICATE``, for a document
number the company holds, answers 400 with fault code 6140 naming its transaction id (ADP-12
``Duplicate``).
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from erev_api.adapters.mocks.admin import FaultKind, error_response, fault_response, world_of

__all__ = ["CODE", "PREFIX", "QboMock", "router"]

CODE: Final = "qbo"
PREFIX: Final = f"/{CODE}"
JOURNAL_ROUTE: Final = f"{PREFIX}/v3/company/journalentry"
QUERY_ROUTE: Final = f"{PREFIX}/v3/company/query"
REPORT_ROUTE: Final = f"{PREFIX}/v3/company/reports"
DOC_NUMBER_LENGTH: Final = 21
FIRST_ID: Final = 145
DUPLICATE_DOCUMENT: Final = "6140"
OTHER_CURRENCY: Final = (
    "The mock company keeps its ledger in {home} and holds no exchange rates: a document in "
    "{currency} is refused."
)
INCOME_STATEMENT_TYPES: Final = frozenset(
    {"Income", "Other Income", "Expense", "Other Expense", "Cost of Goods Sold"}
)
_BY_DOC_NUMBER: Final = re.compile(
    r"^\s*select\s+\*\s+from\s+JournalEntry\s+where\s+DocNumber\s*=\s*'([^']*)'\s*$", re.I
)
ZERO: Final = Decimal(0)


@dataclass(frozen=True, slots=True)
class CompanyDocument:
    """One document of a company's ledger; ``lines`` are (account, amount), debit positive."""

    reference: str
    private_note: str  # the ADP-10 external id of an eRev chunk; empty for a company's own
    posted: date
    currency: str
    lines: tuple[tuple[str, Decimal], ...]


class EntryRefused(Exception):
    """A journal entry the company does not accept (400 ``ValidationFault``)."""


class QboMock:
    """ADP-22 state: per realm, the journal entries by request id and the ledger documents."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._responses: dict[tuple[str, str], dict[str, Any]] = {}  # (realm, requestid)
        self._entries: dict[str, list[dict[str, Any]]] = {}  # realm → JournalEntry objects
        self._documents: dict[str, list[CompanyDocument]] = {}
        self._types: dict[tuple[str, str], str] = {}  # (realm, account) → account type
        self.served: list[str] = []

    def reset(self) -> None:
        with self._lock:
            self._responses = {}
            self._entries = {}
            self._documents = {}
            self._types = {}
            self.served = []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "realms": sorted(self._documents),
                "journal_entries": sum(len(found) for found in self._entries.values()),
                "documents": sum(len(found) for found in self._documents.values()),
                "served": len(self.served),
            }

    def posting_count(self, realm: str) -> int:
        """The journal entries the company holds: a repeated request id adds none (ADP-23)."""
        with self._lock:
            return len(self._entries.get(realm, ()))

    def held(self, realm: str, number: str) -> dict[str, Any] | None:
        with self._lock:
            return next((e for e in self._entries.get(realm, ()) if e["DocNumber"] == number), None)

    def by_doc_number(self, realm: str, number: str) -> list[dict[str, Any]]:
        with self._lock:
            self.served.append(f"query:{realm}:{number}")
            return [dict(e) for e in self._entries.get(realm, ()) if e["DocNumber"] == number]

    def create(self, realm: str, request_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """The response of the entry created for ``request_id``: the stored one when the request
        id repeats. ``EntryRefused`` for a body the company does not accept."""
        with self._lock:
            stored = self._responses.get((realm, request_id))
            if stored is not None:
                self.served.append(f"journalentry:replay:{realm}:{request_id}")
                return dict(stored)
            document = self._document_of(realm, body)
            entries = self._entries.setdefault(realm, [])
            entry = {
                "Id": str(FIRST_ID + sum(len(found) for found in self._entries.values())),
                "SyncToken": "0",
                "DocNumber": document.reference,
                "PrivateNote": document.private_note,
                "TxnDate": document.posted.isoformat(),
                "CurrencyRef": {"value": document.currency},
            }
            entries.append(entry)
            self._documents.setdefault(realm, []).append(document)
            response = {"JournalEntry": entry, "time": f"{document.posted.isoformat()}T00:00:00Z"}
            self._responses[(realm, request_id)] = response
            self.served.append(f"journalentry:{realm}:{document.reference}")
            return dict(response)

    def _document_of(self, realm: str, body: dict[str, Any]) -> CompanyDocument:
        try:
            number = str(body["DocNumber"])
            posted = date.fromisoformat(str(body["TxnDate"]))
            currency = str(body["CurrencyRef"]["value"])
            lines = list(body["Line"])
        except (KeyError, TypeError, ValueError) as error:
            raise EntryRefused("Required parameter is missing in the request.") from error
        if len(number) > DOC_NUMBER_LENGTH:
            raise EntryRefused(f"DocNumber is longer than {DOC_NUMBER_LENGTH} characters.")
        self._require_home(realm, currency)
        if not lines:
            raise EntryRefused("A journal entry needs at least one line.")
        amounts: dict[str, Decimal] = {}
        debits = credits = ZERO
        for line in lines:
            try:
                detail = dict(line["JournalEntryLineDetail"])
                account = dict(detail["AccountRef"])
                code = str(account["value"])
                amount = Decimal(str(line["Amount"]))
                posting = str(detail["PostingType"])
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                raise EntryRefused("A journal line lacks its account or amount.") from error
            if amount < 0 or posting not in ("Debit", "Credit"):
                raise EntryRefused("A journal line needs a posting type and a positive amount.")
            if account.get("type") is not None:
                self._types.setdefault((realm, code), str(account["type"]))
            if posting == "Debit":
                debits += amount
            else:
                credits += amount
            if amount:
                signed = amount if posting == "Debit" else -amount
                amounts[code] = amounts.get(code, ZERO) + signed
        if debits != credits:
            raise EntryRefused("Debits must equal credits.")
        return CompanyDocument(
            reference=number,
            private_note=str(body.get("PrivateNote") or ""),
            posted=posted,
            currency=currency,
            lines=tuple(sorted(amounts.items())),
        )

    def add_document(self, realm: str, document: CompanyDocument) -> None:
        """Book a document the company itself made; ``EntryRefused`` in another currency than
        the company's."""
        with self._lock:
            self._require_home(realm, document.currency)
            self._documents.setdefault(realm, []).append(document)
            self.served.append(f"erp-document:{realm}:{document.reference}")

    def _currency(self, realm: str) -> str:
        """The company's home currency: that of its first document; empty before any."""
        found = self._documents.get(realm) or ()
        return found[0].currency if found else ""

    def _require_home(self, realm: str, currency: str) -> None:
        home = self._currency(realm)
        if home and currency != home:
            raise EntryRefused(OTHER_CURRENCY.format(home=home, currency=currency))

    def trial_balance(self, realm: str, *, end: date, accounts: frozenset[str]) -> dict[str, Any]:
        with self._lock:
            self.served.append(f"report:TrialBalance:{realm}")
            totals: dict[str, Decimal] = {}
            for doc in self._documents.get(realm, ()):
                if doc.posted > end:
                    continue
                for code, amount in doc.lines:
                    if accounts and code not in accounts:
                        continue
                    yearly = self._types.get((realm, code)) in INCOME_STATEMENT_TYPES
                    if yearly and doc.posted.year != end.year:
                        continue
                    totals[code] = totals.get(code, ZERO) + amount
            rows = [
                {
                    "ColData": [
                        {"value": code},
                        {"value": format(max(amount, ZERO), "f")},
                        {"value": format(max(-amount, ZERO), "f")},
                    ]
                }
                for code, amount in sorted(totals.items())
            ]
            return {
                "Header": {
                    "ReportName": "TrialBalance",
                    "EndPeriod": end.isoformat(),
                    "Currency": self._currency(realm),
                },
                "Columns": {
                    "Column": [{"ColTitle": ""}, {"ColTitle": "Debit"}, {"ColTitle": "Credit"}]
                },
                "Rows": {"Row": rows},
            }

    def transaction_list(
        self, realm: str, *, start: date, end: date, accounts: frozenset[str]
    ) -> dict[str, Any]:
        with self._lock:
            self.served.append(f"report:TransactionList:{realm}")
            rows = [
                {
                    "ColData": [
                        {"value": doc.posted.isoformat()},
                        {"value": doc.reference},
                        {"value": code},
                        {"value": format(amount, "f")},
                        {"value": doc.private_note},
                    ]
                }
                for doc in sorted(
                    self._documents.get(realm, ()), key=lambda d: (d.posted, d.reference)
                )
                if start <= doc.posted <= end
                for code, amount in doc.lines
                if not accounts or code in accounts
            ]
            return {
                "Header": {
                    "ReportName": "TransactionList",
                    "StartPeriod": start.isoformat(),
                    "EndPeriod": end.isoformat(),
                    "Currency": self._currency(realm),
                },
                "Rows": {"Row": rows},
            }


def mock_of(request: Request) -> QboMock:
    adapter = world_of(request).adapters[CODE]
    assert isinstance(adapter, QboMock)
    return adapter


def _fault(message: str, detail: str, code: str = "2010") -> Response:
    """The v3 ``ValidationFault`` shape (400)."""
    return JSONResponse(
        {
            "Fault": {
                "Error": [{"Message": message, "Detail": detail, "code": code}],
                "type": "ValidationFault",
            }
        },
        status_code=400,
    )


def _accounts(value: str) -> frozenset[str]:
    return frozenset(code for code in value.split(",") if code)


router = APIRouter(prefix=PREFIX)


@router.post("/v3/company/{realm}/journalentry")
async def create_journal_entry(realm: str, request: Request, requestid: str = "") -> Response:
    """ADP-10 / ADP-23: one entry per request id; the faults of the module docstring."""
    kind = world_of(request).faults.take(JOURNAL_ROUTE)
    if kind not in (FaultKind.TIMEOUT, FaultKind.DUPLICATE):
        refused = error_response(kind)
        if refused is not None:
            return refused
    if not requestid:
        return _fault("Required parameter is missing", "requestid is required by this integration.")
    mock = mock_of(request)
    try:
        body = dict(json.loads(await request.body()))
    except (ValueError, TypeError):
        return _fault("Request has invalid or unsupported property", "The body is not JSON.")
    if kind is FaultKind.DUPLICATE:
        held = mock.held(realm, str(body.get("DocNumber")))
        if held is not None:
            return _fault(
                "Duplicate Document Number Error",
                "Duplicate Document Number Error : You must specify a different number. This "
                f"number has already been used. DocNumber={held['DocNumber']} is assigned to "
                f"TxnType=Journal Entry with TxnId={held['Id']}",
                DUPLICATE_DOCUMENT,
            )
    try:
        response = mock.create(realm, requestid, body)
    except EntryRefused as refused_entry:
        return _fault("A business validation error has occurred", str(refused_entry), "6000")
    if kind is FaultKind.TIMEOUT:
        return error_response(kind) or Response(status_code=504)
    return JSONResponse(response)


@router.get("/v3/company/{realm}/query")
def query(realm: str, request: Request, query: str = "") -> Response:
    fault = fault_response(request, QUERY_ROUTE)
    if fault is not None:
        return fault
    matched = _BY_DOC_NUMBER.match(query)
    if matched is None:
        return _fault(
            "Error parsing query", "The mock answers JournalEntry by DocNumber only.", "4000"
        )
    found = mock_of(request).by_doc_number(realm, matched.group(1))
    return JSONResponse({"QueryResponse": {"JournalEntry": found, "maxResults": len(found)}})


@router.get("/v3/company/{realm}/reports/TrialBalance")
def trial_balance(realm: str, request: Request, end_date: date, accounts: str = "") -> Response:
    fault = fault_response(request, REPORT_ROUTE)
    if fault is not None:
        return fault
    report = mock_of(request).trial_balance(realm, end=end_date, accounts=_accounts(accounts))
    return JSONResponse(report)


@router.get("/v3/company/{realm}/reports/TransactionList")
def transaction_list(
    realm: str, request: Request, start_date: date, end_date: date, accounts: str = ""
) -> Response:
    fault = fault_response(request, REPORT_ROUTE)
    if fault is not None:
        return fault
    report = mock_of(request).transaction_list(
        realm, start=start_date, end=end_date, accounts=_accounts(accounts)
    )
    return JSONResponse(report)


# --- mock administration: what the company itself booked (ADP-22) -------------------------------


class ErpLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str = Field(min_length=1, max_length=64)
    amount: Decimal  # debit positive, credit negative


class ErpDocumentIn(BaseModel):
    """A document the company itself booked; ``account`` names the realm."""

    model_config = ConfigDict(extra="forbid")

    account: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=200)
    date: date
    currency: str = Field(min_length=3, max_length=3)
    lines: list[ErpLineIn] = Field(min_length=1, max_length=1000)


@router.post("/__erp/documents", status_code=201)
def add_erp_document(body: ErpDocumentIn, request: Request) -> Any:
    mock = mock_of(request)
    try:
        mock.add_document(
            body.account,
            CompanyDocument(
                reference=body.reference,
                private_note="",
                posted=body.date,
                currency=body.currency,
                lines=tuple((line.account, line.amount) for line in body.lines),
            ),
        )
    except EntryRefused as refused:
        return _fault("A business validation error has occurred", str(refused), "6000")
    return mock.snapshot()

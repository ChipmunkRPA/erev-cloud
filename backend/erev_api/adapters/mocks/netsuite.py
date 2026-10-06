"""NetSuite mock server (05 ADP-20 to ADP-23; PRD J-13, J-23.7, WLD-B-07, WLD-F-32; 03 REQ-JE-014,
REQ-INT-008, REQ-INT-009; BUILD_SPEC DIN-14, CLO-15).

State is in memory per api process and restored by ``POST /__admin/reset``. Routes, under
``/api/v1/__mocks__/netsuite`` (the SuiteTalk REST record shapes, minimally):

- chart (DIN-14; seeded from ``fixtures/quayside/quayside-netsuite-chart.json``): ``GET
  /record/v1/account`` (list, ``items``), ``GET /record/v1/account/{id}``, ``GET
  /record/v1/department`` and ``GET /record/v1/subsidiary``;
- journals (CLO-15): ``PUT /record/v1/journalEntry/eid:<external id>`` upserts one journal entry
  and answers 204 with its ``Location``; a repeated external id keeps the first document and
  answers the same (ADP-23: the posting count does not change, ADP-13: nothing posted is changed).
  ``GET /record/v1/journalEntry/eid:<external id>`` reads it (``id``, ``tranId``, ``tranDate``,
  ``externalId``). A journal whose debits and credits differ, or without a line, answers 400;
- trial balance (CLO-15): ``GET /restlet/v1/trialBalance`` (below).

The ledger. Every journal received is one GL document of a ledger kept per NetSuite account — the
workspace code, read from the external id ``erev:<workspace code>:…`` — and subsidiary (the
entity code): document number (``tranId``, ``JE-NS-88001`` upwards), external id, posting period,
GL date, currency and one amount per account, debit positive. The ledger opens an account it does
not know, with the type the line states: refusing an unknown account is the adapter's
``validate_accounts`` against the chart. A line without an amount books nothing. This subledger
states a journal in the entity's functional currency with the functional amounts (05 ADP-10 rev
1.92; supervisor ruling R-110), so the journals of a subsidiary arrive in one currency whatever
the contracts' currencies; the informational members of a foreign-currency batch
(``custbody_erev_txn_currency``, ``custcol_erev_txn_debit``, ``custcol_erev_txn_credit``) are
accepted and not booked.

Documents made in the ERP carry no external id. They come from the packaged fixtures
``fixtures/<workspace code>/netsuite-tb-*.json`` (WLD-F-32: ``JE-NS-88121``, 250.00 on account
2100 of subsidiary AVM-US in Sep 2026 — a document of that subsidiary for whoever asks) and from
``POST /__erp/documents``, mock administration for a test or a seed that states what the ERP
itself booked: a manual journal, or an invoice or credit memo in ERP billing mode (Dr receivable /
Cr contract liability, net of tax, at the issue date; supervisor ruling R-74 (e)). ``POST
/__erp/accounts`` adds accounts to the chart the same way.

Trial balance: ``GET /restlet/v1/trialBalance?account=&subsidiary=&period=&startDate=&endDate=
&accounts=`` answers ``lines`` — per account and currency the closing balance at ``endDate``: every
document dated through it, a balance sheet account cumulative, an income statement account (chart
types Income, OthIncome, COGS, Expense, OthExpense) within the fiscal year of ``period`` — and
``details`` — one row per document and account dated inside the period, with ``tranId`` and
``externalId`` (null for a document made in the ERP). Amounts are those posted, in the posting
currency: the mock holds no exchange rates and converts nothing. A real ledger answers a
subsidiary's trial balance in its base currency alone, so a document made in the ERP is stated
here in that currency — an invoice of another currency at the amount the ledger booked it at; a
second currency in the answer means a document was stated otherwise, and the comparison of
BUILD_SPEC CLO-17 refuses such a trial balance by name. A fixture of the asking workspace that
states ``balances`` for the subsidiary and period fixes the ``lines`` (``mode`` ``FIXED``);
otherwise they are computed (``COMPUTED``).

Faults (ADP-21). Every route passes the queued fault of its route first. On the journal upsert
``RATE_LIMIT``, ``SERVER_ERROR`` and ``PERMANENT_ERROR`` answer before anything is stored;
``TIMEOUT`` stores the journal and answers 504 — the ledger accepted and the answer was lost, so
the adapter's ``get_posting`` finds the document (ADP-15); ``DUPLICATE``, for an external id the
ledger holds, answers 409 naming the document (ADP-12 ``Duplicate``). ``READ_LAG`` (rev 1.175;
item JRN-EXIT-SETTLE-1) is the ledger that accepts now and shows later: the upsert stores the
journal and answers 204, and the reads — the journal by its external id, the trial balance —
leave it out until ``POST /__erp/journals/release`` shows every journal the mock holds. The
adapter's read-back then finds nothing and it raises ``Accepted`` (ADP-12). A repeated upsert of
such a journal is accepted again and shows nothing more.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from erev_engine.currencies import ISO_4217
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from erev_api.adapters.mocks.admin import FaultKind, error_response, fault_response, world_of

__all__ = [
    "CODE",
    "DOCUMENT_SERIES",
    "PREFIX",
    "SCENARIO_FIXTURE",
    "TRIAL_BALANCE_FIXTURES",
    "LedgerDocument",
    "NetSuiteMock",
    "load_scenario",
    "router",
]

CODE: Final = "netsuite"
PREFIX: Final = f"/{CODE}"
FIXTURES: Final = Path(__file__).with_name("fixtures")
SCENARIO_FIXTURE: Final = FIXTURES / "quayside" / "quayside-netsuite-chart.json"
TRIAL_BALANCE_FIXTURES: Final = "netsuite-tb-*.json"
JOURNAL_ROUTE: Final = f"{PREFIX}/record/v1/journalEntry"
TRIAL_BALANCE_ROUTE: Final = f"{PREFIX}/restlet/v1/trialBalance"
EID: Final = "eid:"
DOCUMENT_SERIES: Final = ("JE-NS-", 88001)  # the document number of the first journal received
# NetSuite account types whose balance a trial balance states for the fiscal year to date.
INCOME_STATEMENT_TYPES: Final = frozenset({"Income", "OthIncome", "COGS", "Expense", "OthExpense"})
ZERO: Final = Decimal(0)


@dataclass(frozen=True, slots=True)
class Scenario:
    accounts: tuple[dict[str, Any], ...]
    departments: tuple[dict[str, Any], ...]
    subsidiaries: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class LedgerDocument:
    """One GL document of the mock ledger. ``account`` is the NetSuite account (the workspace
    code); None for a packaged document of its subsidiary, which every asking workspace sees.
    ``lines`` are (account number, amount), debit positive."""

    account: str | None
    subsidiary: str
    reference: str
    external_id: str | None
    period: str
    posted: date
    currency: str
    lines: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True, slots=True)
class FixedBalances:
    """The ``balances`` a trial-balance fixture states for its workspace, subsidiary and period."""

    account: str
    subsidiary: str
    period: str
    lines: tuple[tuple[str, str, Decimal], ...]  # (account number, currency, amount)


def load_scenario(path: Path = SCENARIO_FIXTURE) -> Scenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(
        accounts=tuple(dict(a) for a in raw["accounts"]),
        departments=tuple(dict(d) for d in raw["departments"]),
        subsidiaries=tuple(dict(s) for s in raw["subsidiaries"]),
    )


def load_trial_balance_fixtures(
    root: Path = FIXTURES,
) -> tuple[tuple[LedgerDocument, ...], tuple[FixedBalances, ...]]:
    """The ERP-made documents and the fixed balances of every packaged
    ``<workspace code>/netsuite-tb-*.json`` (ADP-22), in file order."""
    documents: list[LedgerDocument] = []
    fixed: list[FixedBalances] = []
    for path in sorted(root.glob(f"*/{TRIAL_BALANCE_FIXTURES}")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        subsidiary, currency = str(raw["subsidiary"]), str(raw["currency"])
        for item in raw.get("documents", ()):
            documents.append(
                LedgerDocument(
                    account=None,
                    subsidiary=subsidiary,
                    reference=str(item["reference"]),
                    external_id=None,
                    period=str(item["period"]),
                    posted=date.fromisoformat(str(item["date"])),
                    currency=str(item.get("currency", currency)),
                    lines=tuple(
                        (str(line["account"]), Decimal(str(line["amount"])))
                        for line in item["lines"]
                    ),
                )
            )
        if raw.get("balances"):
            fixed.append(
                FixedBalances(
                    account=str(raw["tenant_code"]),
                    subsidiary=subsidiary,
                    period=str(raw["period"]),
                    lines=tuple(
                        (
                            str(line["account"]),
                            str(line.get("currency", currency)),
                            Decimal(str(line["amount"])),
                        )
                        for line in raw["balances"]
                    ),
                )
            )
    return tuple(documents), tuple(fixed)


def _fiscal_year(period: str) -> str:
    """``FY2026`` of ``FY2026-P09``; the whole key when it has another form."""
    return period.split("-", 1)[0]


def _amount(value: Decimal, currency: str) -> str:
    found = ISO_4217.get(currency)
    exponent = Decimal(1).scaleb(-(2 if found is None else found.minor_unit))
    return format(value.quantize(exponent), "f")


class JournalRefused(Exception):
    """A journal the ledger does not accept (400 with the SuiteTalk error shape)."""


class NetSuiteMock:
    """ADP-22 state: the chart, departments and subsidiaries, the ledger and the requests
    served."""

    def __init__(self, scenario_path: Path = SCENARIO_FIXTURE, fixtures: Path = FIXTURES) -> None:
        self._path = scenario_path
        self._fixtures = fixtures
        self._lock = threading.Lock()
        self.scenario = load_scenario(scenario_path)
        self.served: list[str] = []
        self._packaged, self._fixed = load_trial_balance_fixtures(fixtures)
        self._journals: dict[str, dict[str, Any]] = {}
        self._documents: list[LedgerDocument] = []
        self._opened: dict[str, str | None] = {}

    def reset(self) -> None:
        with self._lock:
            self.scenario = load_scenario(self._path)
            self.served = []
            self._packaged, self._fixed = load_trial_balance_fixtures(self._fixtures)
            self._journals = {}
            self._documents = []
            self._opened = {}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "accounts": [a["acctNumber"] for a in self.scenario.accounts],
                "departments": len(self.scenario.departments),
                "served": len(self.served),
                "journals": len(self._journals),
                "unreleased_journals": sum(1 for item in self._journals.values() if item["hidden"]),
                "erp_documents": len(self._documents) + len(self._packaged),
            }

    def _note(self, what: str) -> None:
        with self._lock:
            self.served.append(what)

    # --- chart (DIN-14) ---------------------------------------------------------------------------

    def accounts(self) -> list[dict[str, Any]]:
        self._note("account:list")
        return list(self.scenario.accounts)

    def account(self, record_id: str) -> dict[str, Any] | None:
        found = next((a for a in self.scenario.accounts if str(a["id"]) == record_id), None)
        if found is not None:
            self._note(f"account:{record_id}")
        return found

    def departments(self) -> list[dict[str, Any]]:
        self._note("department:list")
        return list(self.scenario.departments)

    def subsidiaries(self) -> list[dict[str, Any]]:
        self._note("subsidiary:list")
        return list(self.scenario.subsidiaries)

    def add_accounts(self, accounts: list[dict[str, Any]]) -> int:
        """Add accounts to the chart (``__erp/accounts``); an account number the chart holds is
        left as it is. The number of accounts added."""
        added = 0
        with self._lock:
            held = {str(a["acctNumber"]) for a in self.scenario.accounts}
            records = list(self.scenario.accounts)
            for item in accounts:
                number = str(item["acctNumber"])
                if number in held:
                    continue
                held.add(number)
                records.append(
                    {
                        "id": str(9000 + len(records)),
                        "acctNumber": number,
                        "acctName": str(item.get("acctName") or number),
                        "acctType": str(item.get("acctType") or "OthCurrAsset"),
                        "isInactive": False,
                    }
                )
                added += 1
            self.scenario = Scenario(
                accounts=tuple(records),
                departments=self.scenario.departments,
                subsidiaries=self.scenario.subsidiaries,
            )
        return added

    # --- journals (CLO-15) ------------------------------------------------------------------------

    @property
    def posting_count(self) -> int:
        """The journals the ledger holds: a repeated external id adds none (ADP-23)."""
        with self._lock:
            return len(self._journals)

    def journal(self, external_id: str) -> dict[str, Any] | None:
        """The journal the ledger shows for ``external_id``: none while it holds one it has not
        released (``READ_LAG``)."""
        with self._lock:
            found = self._journals.get(external_id)
            return None if found is None or found["hidden"] else dict(found["record"])

    def release_journals(self) -> int:
        """The ledger shows every journal it holds (``POST /__erp/journals/release``): the number
        it had not shown."""
        with self._lock:
            waiting = [item for item in self._journals.values() if item["hidden"]]
            for item in waiting:
                item["hidden"] = False
            return len(waiting)

    def upsert_journal(
        self, external_id: str, body: dict[str, Any], *, hidden: bool = False
    ) -> dict[str, Any]:
        """The record of the journal with ``external_id``: the stored one, or a new document of
        ``body``. ``JournalRefused`` for a body the ledger does not accept. ``hidden`` stores a
        new journal that the ledger's reads leave out until ``release_journals`` (``READ_LAG``);
        a journal the ledger holds stays as it is, shown or not."""
        with self._lock:
            held = self._journals.get(external_id)
            if held is not None:
                self.served.append(f"journalEntry:repeat:{external_id}")
                return dict(held["record"])
            document = self._document_of(external_id, body)
            record = {
                "id": str(5000 + len(self._journals) + 1),
                "tranId": document.reference,
                "tranDate": document.posted.isoformat(),
                "externalId": external_id,
                "subsidiary": {"refName": document.subsidiary},
                "currency": {"refName": document.currency},
                "postingPeriod": {"refName": document.period},
            }
            self._journals[external_id] = {"record": record, "document": document, "hidden": hidden}
            self.served.append(f"journalEntry:{external_id}")
            return dict(record)

    def _next_reference(self) -> str:
        prefix, first = DOCUMENT_SERIES
        taken = {doc.reference for doc in (*self._packaged, *self._documents)}
        taken |= {str(item["record"]["tranId"]) for item in self._journals.values()}
        number = first
        while f"{prefix}{number}" in taken:
            number += 1
        return f"{prefix}{number}"

    def _document_of(self, external_id: str, body: dict[str, Any]) -> LedgerDocument:
        if str(body.get("externalId")) != external_id:
            raise JournalRefused("The externalId of the body differs from the key of the request.")
        try:
            subsidiary = str(body["subsidiary"]["refName"])
            currency = str(body["currency"]["refName"])
            posted = date.fromisoformat(str(body["tranDate"]))
            period = str(body["postingPeriod"]["refName"])
            items = list(body["line"]["items"])
        except (KeyError, TypeError, ValueError) as error:
            raise JournalRefused("The journal entry lacks a required field.") from error
        if not items:
            raise JournalRefused("A journal entry needs at least one line.")
        amounts: dict[str, Decimal] = {}
        debits = credits = ZERO
        for item in items:
            try:
                account = dict(item["account"])
                number = str(account["acctNumber"])
                debit = Decimal(str(item.get("debit") or "0"))
                credit = Decimal(str(item.get("credit") or "0"))
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                raise JournalRefused("A journal line lacks its account or amount.") from error
            if debit < 0 or credit < 0:
                raise JournalRefused("A journal line amount cannot be negative.")
            debits, credits = debits + debit, credits + credit
            self._open(number, account.get("acctType"))
            if debit or credit:
                amounts[number] = amounts.get(number, ZERO) + debit - credit
        if debits != credits:
            raise JournalRefused("The amounts in a journal entry must balance.")
        parts = external_id.split(":")
        account_id = parts[1] if len(parts) >= 3 and parts[0] == "erev" else ""
        return LedgerDocument(
            account=account_id,
            subsidiary=subsidiary,
            reference=self._next_reference(),
            external_id=external_id,
            period=period,
            posted=posted,
            currency=currency,
            lines=tuple(sorted(amounts.items())),
        )

    def _open(self, number: str, account_type: Any) -> None:
        if any(str(a["acctNumber"]) == number for a in self.scenario.accounts):
            return
        if self._opened.get(number) is None:
            self._opened[number] = None if account_type is None else str(account_type)

    # --- documents made in the ERP (WLD-F-32; ruling R-74 (e)) ------------------------------------

    def add_document(self, document: LedgerDocument) -> None:
        with self._lock:
            for number, _ in document.lines:
                self._open(number, None)
            self._documents.append(document)
            self.served.append(f"erp-document:{document.reference}")

    # --- trial balance (REQ-INT-009) --------------------------------------------------------------

    def _income_statement(self, number: str) -> bool:
        for record in self.scenario.accounts:
            if str(record["acctNumber"]) == number:
                return str(record.get("acctType")) in INCOME_STATEMENT_TYPES
        return self._opened.get(number) in INCOME_STATEMENT_TYPES

    def trial_balance(
        self,
        *,
        account: str,
        subsidiary: str,
        period: str,
        start: date,
        end: date,
        accounts: frozenset[str],
    ) -> dict[str, Any]:
        with self._lock:
            self.served.append(f"trialBalance:{subsidiary}:{period}")
            documents = [
                doc
                for doc in (
                    # a journal the ledger has not released is in none of its reads (READ_LAG)
                    *(item["document"] for item in self._journals.values() if not item["hidden"]),
                    *self._documents,
                    *self._packaged,
                )
                if doc.subsidiary == subsidiary and doc.account in (None, account)
            ]
            year = _fiscal_year(period)
            totals: dict[tuple[str, str], Decimal] = {}
            details: list[dict[str, Any]] = []
            for doc in sorted(documents, key=lambda item: (item.posted, item.reference)):
                if doc.posted > end:
                    continue
                for number, amount in doc.lines:
                    if accounts and number not in accounts:
                        continue
                    if not self._income_statement(number) or _fiscal_year(doc.period) == year:
                        key = (number, doc.currency)
                        totals[key] = totals.get(key, ZERO) + amount
                    if doc.posted >= start:
                        details.append(
                            {
                                "account": number,
                                "currency": doc.currency,
                                "amount": _amount(amount, doc.currency),
                                "tranId": doc.reference,
                                "externalId": doc.external_id,
                                "tranDate": doc.posted.isoformat(),
                            }
                        )
            fixed = next(
                (
                    item
                    for item in self._fixed
                    if (item.account, item.subsidiary, item.period) == (account, subsidiary, period)
                ),
                None,
            )
            if fixed is not None:
                stated = [
                    (number, currency, amount)
                    for number, currency, amount in fixed.lines
                    if not accounts or number in accounts
                ]
            else:
                stated = [
                    (number, currency, amount) for (number, currency), amount in totals.items()
                ]
            return {
                "account": account,
                "subsidiary": subsidiary,
                "period": period,
                "endDate": end.isoformat(),
                "mode": "COMPUTED" if fixed is None else "FIXED",
                "lines": [
                    {"account": number, "currency": currency, "amount": _amount(amount, currency)}
                    for number, currency, amount in sorted(stated)
                ],
                "details": details,
            }


def mock_of(request: Request) -> NetSuiteMock:
    adapter = world_of(request).adapters[CODE]
    assert isinstance(adapter, NetSuiteMock)
    return adapter


def _list(items: list[dict[str, Any]]) -> Response:
    return JSONResponse(
        {"count": len(items), "hasMore": False, "items": items, "totalResults": len(items)}
    )


def _problem(status: int, title: str, detail: str, **members: Any) -> Response:
    """The SuiteTalk REST error shape: ``o:errorDetails`` carries the message."""
    return JSONResponse(
        {
            "type": f"https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.{status - 399}",
            "title": title,
            "status": status,
            "o:errorDetails": [{"detail": detail, **members}],
        },
        status_code=status,
    )


def _external_id(key: str) -> str | None:
    return key[len(EID) :] if key.startswith(EID) and len(key) > len(EID) else None


router = APIRouter(prefix=PREFIX)


@router.get("/record/v1/account")
def list_accounts(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/record/v1/account")
    return fault or _list(mock_of(request).accounts())


@router.get("/record/v1/account/{record_id}")
def get_account(record_id: str, request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/record/v1/account")
    if fault is not None:
        return fault
    body = mock_of(request).account(record_id)
    if body is None:
        detail = {
            "type": "https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.5",
            "title": "Not Found",
            "status": 404,
        }
        return JSONResponse(detail, status_code=404)
    return JSONResponse(body)


@router.get("/record/v1/department")
def list_departments(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/record/v1/department")
    return fault or _list(mock_of(request).departments())


@router.get("/record/v1/subsidiary")
def list_subsidiaries(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/record/v1/subsidiary")
    return fault or _list(mock_of(request).subsidiaries())


@router.put("/record/v1/journalEntry/{key}")
async def upsert_journal(key: str, request: Request) -> Response:
    """ADP-10 / ADP-23: upsert by external id; the faults of the module docstring."""
    kind = world_of(request).faults.take(JOURNAL_ROUTE)
    if kind not in (FaultKind.TIMEOUT, FaultKind.DUPLICATE):
        refused = error_response(kind)
        if refused is not None:
            return refused
    external_id = _external_id(key)
    if external_id is None:
        return _problem(400, "Bad Request", "Upsert a journal entry by its key eid:<external id>.")
    mock = mock_of(request)
    held = mock.journal(external_id)
    if kind is FaultKind.DUPLICATE and held is not None:
        return _problem(
            409,
            "Conflict",
            f"A journal entry with external id {external_id} already exists.",
            **{"o:errorCode": "DUP_RCRD", "tranId": held["tranId"]},
        )
    try:
        body = json.loads(await request.body())
        record = mock.upsert_journal(external_id, dict(body), hidden=kind is FaultKind.READ_LAG)
    except (ValueError, TypeError):
        return _problem(400, "Bad Request", "The request body is not a journal entry.")
    except JournalRefused as refused_journal:
        return _problem(400, "Bad Request", str(refused_journal), **{"o:errorCode": "USER_ERROR"})
    if kind is FaultKind.TIMEOUT:
        return error_response(kind) or Response(status_code=504)
    location = f"{request.url.path.rsplit('/', 1)[0]}/{record['id']}"
    return Response(status_code=204, headers={"Location": location})


@router.get("/record/v1/journalEntry/{key}")
def get_journal(key: str, request: Request) -> Response:
    fault = fault_response(request, JOURNAL_ROUTE)
    if fault is not None:
        return fault
    external_id = _external_id(key)
    record = None if external_id is None else mock_of(request).journal(external_id)
    if record is None:
        return _problem(404, "Not Found", "The journal entry does not exist.")
    return JSONResponse(record)


@router.get("/restlet/v1/trialBalance")
def trial_balance(
    request: Request,
    account: str,
    subsidiary: str,
    period: str,
    startDate: date,  # noqa: N803 - the ERP's parameter name
    endDate: date,  # noqa: N803
    accounts: str = "",
) -> Response:
    fault = fault_response(request, TRIAL_BALANCE_ROUTE)
    if fault is not None:
        return fault
    wanted = frozenset(code for code in accounts.split(",") if code)
    return JSONResponse(
        mock_of(request).trial_balance(
            account=account,
            subsidiary=subsidiary,
            period=period,
            start=startDate,
            end=endDate,
            accounts=wanted,
        )
    )


# --- mock administration: what the ERP itself holds (ADP-22; supervisor ruling R-74 (e)) ---------


class ErpLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str = Field(min_length=1, max_length=64)
    amount: Decimal  # debit positive, credit negative


class ErpDocumentIn(BaseModel):
    """A document the ERP itself booked: a manual journal, or an invoice or credit memo in ERP
    billing mode. ``account`` is the NetSuite account — the workspace code."""

    model_config = ConfigDict(extra="forbid")

    account: str = Field(min_length=1, max_length=64)
    subsidiary: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=200)
    date: date
    period: str = Field(min_length=1, max_length=16)
    currency: str = Field(min_length=3, max_length=3)
    lines: list[ErpLineIn] = Field(min_length=1, max_length=1000)


class ErpAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acctNumber: str = Field(min_length=1, max_length=64)  # noqa: N815 - the ERP's member name
    acctName: str | None = Field(default=None, max_length=200)  # noqa: N815
    acctType: str | None = Field(default=None, max_length=32)  # noqa: N815


class ErpAccountsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounts: list[ErpAccountIn] = Field(min_length=1, max_length=1000)


@router.post("/__erp/documents", status_code=201)
def add_erp_document(body: ErpDocumentIn, request: Request) -> dict[str, Any]:
    """State a document made in the ERP; it carries no external id."""
    mock = mock_of(request)
    mock.add_document(
        LedgerDocument(
            account=body.account,
            subsidiary=body.subsidiary,
            reference=body.reference,
            external_id=None,
            period=body.period,
            posted=body.date,
            currency=body.currency,
            lines=tuple((line.account, line.amount) for line in body.lines),
        )
    )
    return mock.snapshot()


@router.post("/__erp/accounts", status_code=201)
def add_erp_accounts(body: ErpAccountsIn, request: Request) -> dict[str, Any]:
    """Add accounts to the ERP's chart of accounts."""
    mock = mock_of(request)
    added = mock.add_accounts([item.model_dump() for item in body.accounts])
    return {"added": added, **mock.snapshot()}


@router.post("/__erp/journals/release")
def release_erp_journals(request: Request) -> dict[str, Any]:
    """The ledger shows every journal it accepted and had not shown (the end of ``READ_LAG``)."""
    mock = mock_of(request)
    released = mock.release_journals()
    return {"released": released, **mock.snapshot()}

"""``QUICKBOOKS_ONLINE`` general ledger adapter (05 §5.2 ``GLAdapter``, ADP-10 to ADP-14, ADP-20;
03 REQ-JE-015, REQ-INT-009; BUILD_SPEC CLO-15). Exercised only against the in-process mock.

Journals. ``post_chunk`` creates one journal entry with ``POST /v3/company/<realm>/journalentry
?requestid=<uuid>``. The request id is ``uuid5(NAMESPACE_EREV, external_id)`` with
``NAMESPACE_EREV = uuid5(NAMESPACE_URL, "https://erev.dev/ns/journal")`` — bounded, URL-safe and
derived from the chunk's identity alone — so a repeated request returns the stored first response
(ADP-10, ADP-23). ``DocNumber`` is the run number with ``-<batch no>-<chunk no>``, at most 21
characters, and ``PrivateNote`` holds the full external id. ``get_posting`` finds the entry by its
``DocNumber`` and ``PrivateNote`` (ADP-12 recovery). Each call is ONE attempt — the export relay
owns the ADP-12 schedule: a timeout, a connection error, 408, 429 or 5xx raises ``Transient``
(with the ``Retry-After`` the service states); a duplicate document number (fault code 6140)
raises ``Duplicate`` with the transaction id QuickBooks names; any other 4xx is ``Permanent`` with
the fault's detail.

What the journal states (05 ADP-10 rev 1.92; 04 T-SL-07 "The currencies of an exported batch";
supervisor ruling R-110, pending the independent accountant as candidate AD-55). The entry is in
the entity's FUNCTIONAL currency (``CurrencyRef``) and the ``Amount`` of a line is its functional
debit or credit. For a batch of another transaction currency a line's transaction amount goes
along in its ``Description``, after the memo, as ``[USD debit 54000.00]`` — whatever the side of
its functional amount, which can be the opposite one for a netted line: information only. So
both lines of a foreign-currency remeasurement — which have no transaction amount — reach the
ledger, and nothing is converted at the ledger's own rate. A line whose functional amount is nil
is stated with ``Amount`` 0.00 and books nothing. The journal API's limits behind this form (one
currency and one exchange rate per entry, one amount per line) are read from its documentation
and not verified against a live company.

QuickBooks Online serves no chart of accounts in 1.0 (03 REQ-INT-008 names NetSuite):
``validate_accounts`` and ``pull_chart_of_accounts`` read the workspace's chart of the context,
as ``CSV_GL`` does.

Trial balance (REQ-INT-009). ``pull_trial_balance`` reads the ``TrialBalance`` report at the
period end (the closing balances) and the ``TransactionList`` report of the period (the
documents), on the ADP-12 schedule. A QuickBooks company is one legal entity: the connection's
``config.realm_id`` names it, and the adapter asks that company whatever entity code it is given.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Final, Literal
from urllib.parse import quote, urlencode
from uuid import NAMESPACE_URL, UUID, uuid5

from erev_engine.currencies import ISO_4217

from erev_api.domain.integrations.ports import transient_status
from erev_api.domain.journals import ports

__all__ = [
    "CODE",
    "DOC_NUMBER_LENGTH",
    "NAMESPACE_EREV",
    "REALM_KEY",
    "QuickBooksGl",
    "connection_factory",
    "doc_number",
    "journal_body",
    "quickbooks_factory",
    "request_id",
]

CODE: Final = "QUICKBOOKS_ONLINE"
NAMESPACE_EREV: Final = uuid5(NAMESPACE_URL, "https://erev.dev/ns/journal")  # ADP-10
DOC_NUMBER_LENGTH: Final = 21
REALM_KEY: Final = "realm_id"
RETRY_BACKOFF_SECONDS: Final = (30, 60, 120, 240, 480, 900, 900, 900)
MAX_ATTEMPTS: Final = 8
DUPLICATE_DOCUMENT: Final = "6140"  # "Duplicate Document Number Error"
UNKNOWN_ACCOUNT: Final = "Account {code} is not in the chart of accounts."
NO_CONNECTION: Final = (
    "No QuickBooks Online connection with a base URL is named: nothing can be reached."
)
# 05 ADP-10 rev 1.92: a line's transaction amount in a batch of another transaction currency,
# after the memo in the line's ``Description``.
TXN_NOTE: Final = "[{currency} {side} {amount}]"
NO_REALM: Final = "The QuickBooks Online connection names no realm_id (its company)."
_TXN_ID: Final = re.compile(r"TxnId=([A-Za-z0-9-]+)")
_DOC_NUMBER: Final = re.compile(r"[A-Za-z0-9._-]+")
DOC_NUMBER_SLOT: Final = "<doc number>"
# The QuickBooks query language, not SQL of this system: the document number is checked against
# ``_DOC_NUMBER`` before it takes the slot.
DOCUMENT_QUERY: Final = "select * from JournalEntry where DocNumber = '<doc number>'"
# E-52 account types → the QuickBooks account type a line's AccountRef states.
ERP_ACCOUNT_TYPES: Final[Mapping[str, str]] = {
    "ASSET": "Other Current Asset",
    "LIABILITY": "Other Current Liability",
    "EQUITY": "Equity",
    "REVENUE": "Income",
    "EXPENSE": "Expense",
}


def request_id(external_id: str) -> UUID:
    """ADP-10: the ``requestid`` of a chunk."""
    return uuid5(NAMESPACE_EREV, external_id)


def doc_number(run_no: str, batch_no: int | str, chunk_no: int | str) -> str:
    """ADP-10: the run number with ``-<batch no>-<chunk no>``, at most 21 characters."""
    return f"{run_no}-{batch_no}-{chunk_no}"[:DOC_NUMBER_LENGTH]


def _amount(value: Decimal, currency: str) -> str:
    exponent = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    return format(Decimal(value).quantize(exponent), "f")


def _txn_notes(line: ports.ChunkLine, currency: str, sides: Sequence[str]) -> list[str]:
    """``[USD debit 54000.00]`` for each of ``sides`` on which the line has a transaction
    amount."""
    amounts = {"Debit": line.debit, "Credit": line.credit}
    return [
        TXN_NOTE.format(
            currency=currency, side=side.lower(), amount=_amount(amounts[side], currency)
        )
        for side in sides
        if amounts[side]
    ]


def journal_body(
    chunk: ports.JournalChunk, account_types: Mapping[str, str | None] | None = None
) -> dict[str, Any]:
    """The JournalEntry of a chunk (QuickBooks Online v3 shape, minimally) in the entity's
    functional currency (module docstring; ruling R-110): one ``Line`` per functional debit or
    credit of a journal line; only a batch of another transaction currency states the
    transaction amounts, in the ``Description``."""
    types = account_types or {}
    currency, txn_currency = chunk.functional_currency, chunk.txn_currency
    foreign = txn_currency != currency
    lines: list[dict[str, Any]] = []
    for line in chunk.lines:
        postings = [
            (kind, value)
            for kind, value in (
                ("Debit", line.debit_functional),
                ("Credit", line.credit_functional),
            )
            if value
        ]
        # a line whose functional amount is nil is stated with 0.00 on its transaction side and
        # books nothing; it keeps the note of whatever transaction amount it has
        nil_side = "Credit" if line.credit and not line.debit else "Debit"
        for posting_type, value in postings or [(nil_side, Decimal(0))]:
            account: dict[str, Any] = {"value": line.account_code, "name": line.account_name}
            erp_type = ERP_ACCOUNT_TYPES.get(types.get(line.account_code) or "")
            if erp_type is not None:
                account["type"] = erp_type
            # A journal line is one QuickBooks line and carries its transaction amount whatever
            # the side: a netted line can be a transaction debit and a functional credit. Only a
            # line stated as two QuickBooks lines gives each its own side's amount.
            sides = (posting_type,) if len(postings) == 2 else ("Debit", "Credit")
            notes = _txn_notes(line, txn_currency, sides) if foreign else []
            lines.append(
                {
                    "Id": str(len(lines) + 1),
                    "DetailType": "JournalEntryLineDetail",
                    "Amount": _amount(value, currency),
                    "Description": " ".join(part for part in (line.memo, *notes) if part) or None,
                    "JournalEntryLineDetail": {"PostingType": posting_type, "AccountRef": account},
                }
            )
    return {
        "DocNumber": doc_number(chunk.run_no, chunk.batch_no, chunk.chunk_no),
        "PrivateNote": chunk.external_id,
        "TxnDate": chunk.period_end_date.isoformat(),
        "CurrencyRef": {"value": currency},
        "Line": lines,
    }


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


class QuickBooksGl:
    """One adapter per dispatch, over the client the root supplies and one company (realm)."""

    def __init__(
        self,
        context: ports.GLContext,
        *,
        client: Any,
        base_url: str,
        realm_id: str,
        sleep: Callable[[float], None] | None = None,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._context = context
        self._client = client
        self._company = f"{base_url.rstrip('/')}/v3/company/{quote(realm_id, safe='')}"
        self._sleep = sleep if sleep is not None else _default_sleep
        self._max_attempts = max_attempts
        self._chart = {account.code: account for account in context.accounts}
        self._types = {account.code: account.account_type for account in context.accounts}
        self.attempts: list[tuple[str, int]] = []

    @property
    def code(self) -> Literal["QUICKBOOKS_ONLINE"]:
        return "QUICKBOOKS_ONLINE"

    def validate_accounts(
        self, accounts: Sequence[ports.AccountRef], dimensions: Sequence[ports.DimensionRef]
    ) -> ports.ValidationResult:
        unknown = sorted({account.code for account in accounts} - self._chart.keys())
        return ports.ValidationResult(
            errors=tuple(UNKNOWN_ACCOUNT.format(code=code) for code in unknown)
        )

    def pull_chart_of_accounts(self) -> Sequence[ports.AccountRef]:
        return tuple(self._chart[code] for code in sorted(self._chart))

    # --- REQ-JE-015: journals ---------------------------------------------------------------------

    def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
        path = f"/journalentry?requestid={request_id(chunk.external_id)}"
        response = self._send("POST", path, journal_body(chunk, self._types), chunk.external_id)
        return _posting(chunk.external_id, response.json()["JournalEntry"], response.content)

    def get_posting(self, external_id: str) -> ports.PostingResult | None:
        parts = external_id.split(":")
        if len(parts) < 5:
            return None
        number = doc_number(parts[-3], parts[-2], parts[-1])
        if _DOC_NUMBER.fullmatch(number) is None:
            return None  # never a value the query language could read as more than a literal
        query = urlencode({"query": DOCUMENT_QUERY.replace(DOC_NUMBER_SLOT, number)})
        response = self._send("GET", f"/query?{query}", None, external_id)
        found = [
            entry
            for entry in response.json().get("QueryResponse", {}).get("JournalEntry", ())
            if entry.get("PrivateNote") == external_id
        ]
        return None if not found else _posting(external_id, found[0], response.content)

    # --- REQ-INT-009: trial balance ---------------------------------------------------------------

    def pull_trial_balance(
        self, entity: ports.EntityRef, period: ports.PeriodRef, accounts: Sequence[str]
    ) -> ports.TrialBalance:
        wanted = ",".join(sorted(set(accounts)))
        closing = self._get(
            "/reports/TrialBalance?"
            + urlencode({"end_date": period.end_date.isoformat(), "accounts": wanted})
        )
        currency = str(closing.get("Header", {}).get("Currency", ""))
        lines = tuple(
            ports.TrialBalanceLine(
                account_code=str(cells[0]["value"]),
                currency=currency,
                amount=Decimal(str(cells[1]["value"] or "0"))
                - Decimal(str(cells[2]["value"] or "0")),
            )
            for cells in _rows(closing)
        )
        listed = self._get(
            "/reports/TransactionList?"
            + urlencode(
                {
                    "start_date": period.start_date.isoformat(),
                    "end_date": period.end_date.isoformat(),
                    "accounts": wanted,
                }
            )
        )
        details = tuple(
            ports.TrialBalanceDetail(
                account_code=str(cells[2]["value"]),
                currency=currency,
                amount=Decimal(str(cells[3]["value"])),
                document_reference=str(cells[1]["value"]),
                external_id=cells[4]["value"] or None,
                posted_date=date.fromisoformat(str(cells[0]["value"])),
            )
            for cells in _rows(listed)
        )
        return ports.TrialBalance(
            entity_code=entity.code,
            period_key=period.period_key,
            balances={line.account_code: line.amount for line in lines},
            lines=lines,
            details=details,
        )

    # --- transport --------------------------------------------------------------------------------

    def _request(self, method: str, path: str, body: Mapping[str, Any] | None) -> Any:
        try:
            response = self._client.request(method, f"{self._company}{path}", json=body)
        except Exception as error:  # noqa: BLE001 - driver errors are transient (ADP-12)
            self.attempts.append((path.split("?", 1)[0], 0))
            raise ports.Transient(f"connection error: {type(error).__name__}") from error
        self.attempts.append((path.split("?", 1)[0], int(response.status_code)))
        return response

    def _send(
        self, method: str, path: str, body: Mapping[str, Any] | None, external_id: str
    ) -> Any:
        """One request (the relay owns the schedule); the response of a 2xx."""
        response = self._request(method, path, body)
        status = int(response.status_code)
        if status < 300:
            return response
        if transient_status(status):
            header = response.headers.get("Retry-After")
            raise ports.Transient(
                f"QuickBooks Online answered HTTP {status}.",
                retry_after=None if header is None else float(header),
            )
        fault = _fault_of(response)
        held = _TXN_ID.search(str(fault.get("Detail") or ""))
        if str(fault.get("code")) == DUPLICATE_DOCUMENT and held is not None:
            raise ports.Duplicate(external_id, held.group(1))
        message = fault.get("Detail") or fault.get("Message")
        raise ports.Permanent(str(message or f"QuickBooks Online answered HTTP {status}."))

    def _get(self, path: str) -> dict[str, Any]:
        """A read on the ADP-12 schedule (the trial balance is pulled inside a job)."""
        last: ports.Transient | None = None
        for attempt in range(self._max_attempts):
            try:
                body = self._send("GET", path, None, "").json()
                return dict(body) if isinstance(body, Mapping) else {}
            except ports.Transient as error:
                last = error
            if attempt + 1 < self._max_attempts:
                delay: float = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                if last.retry_after is not None:
                    delay = max(delay, last.retry_after)
                self._sleep(float(delay))
        assert last is not None
        raise last


def _rows(report: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
    return [list(row["ColData"]) for row in report.get("Rows", {}).get("Row", ())]


def _fault_of(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    errors = body.get("Fault", {}).get("Error", ()) if isinstance(body, Mapping) else ()
    return dict(errors[0]) if errors and isinstance(errors[0], Mapping) else {}


def _posting(external_id: str, entry: Mapping[str, Any], content: bytes) -> ports.PostingResult:
    posted = entry.get("TxnDate")
    return ports.PostingResult(
        external_id=external_id,
        status="POSTED",
        gl_document_id=str(entry["Id"]),
        gl_posted_date=None if posted is None else date.fromisoformat(str(posted)),
        response_sha256=hashlib.sha256(content).hexdigest(),
    )


def quickbooks_factory(client: Any, base_url: str, realm_id: str) -> ports.GLAdapterFactory:
    """A factory bound to one client, base URL and company (tests and single-company roots)."""

    def build(context: ports.GLContext) -> ports.GLAdapter:
        return QuickBooksGl(context, client=client, base_url=base_url, realm_id=realm_id)

    return build


def connection_factory(build_client: Callable[[str], Any]) -> ports.GLAdapterFactory:
    """The ``GLAdapterFactory`` of a root that reaches each connection over its own ``base_url``
    (the worker; DG-LAY-03): the client is built per dispatch from the context's ``base_url``,
    the company is the connection's ``config.realm_id``. A context without either names no
    usable connection: ``Permanent``."""

    def build(context: ports.GLContext) -> ports.GLAdapter:
        if not context.base_url:
            raise ports.Permanent(NO_CONNECTION)
        realm = context.config.get(REALM_KEY)
        if not realm:
            raise ports.Permanent(NO_REALM)
        return QuickBooksGl(
            context,
            client=build_client(context.base_url),
            base_url=context.base_url,
            realm_id=str(realm),
            max_attempts=max(1, int(context.config.get("max_attempts", MAX_ATTEMPTS))),
        )

    return build

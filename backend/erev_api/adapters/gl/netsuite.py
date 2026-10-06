"""``NETSUITE`` general ledger adapter (05 §5.2 ``GLAdapter``, ADP-10 to ADP-14, ADP-20; 03
REQ-JE-014, REQ-INT-008, REQ-INT-009; BUILD_SPEC DIN-14, CLO-15).

Chart (DIN-14). ``pull_chart_of_accounts`` reads ``/record/v1/account`` from the client the
composition root supplies (the in-process mock in dev / test / e2e) on the ADP-12 schedule and
answers ``AccountRef`` rows in account-number order; ``pull_dimension_values`` reads a dimension's
records (``department``) the same way. ``validate_accounts`` checks a chunk's accounts against the
pulled chart.

Journals (CLO-15). ``post_chunk`` upserts the chunk as one journal entry with ``PUT
/record/v1/journalEntry/eid:<external id>`` (ADP-10) and reads the entry back for its document
number (``tranId``), which becomes the batch's ``gl_document_id``; a repeated external id answers
the same document (ADP-23). ``get_posting`` reads the entry by the same external id (ADP-12: the
recovery after a timeout). Each call is ONE attempt: the export relay owns the ADP-12 schedule, so
a timeout, a connection error, 408, 429 or 5xx raises ``Transient`` (with the ``Retry-After`` the
ERP states), "the external id exists" raises ``Duplicate`` with the document the ERP holds, and any
other 4xx is ``Permanent`` with the ERP's message.

What the journal states (05 ADP-10 rev 1.92; 04 T-SL-07 "The currencies of an exported batch";
supervisor ruling R-110, pending the independent accountant as candidate AD-55). The entry is the
batch's entity and posting period in the entity's FUNCTIONAL currency, and one line per journal
line with its functional debit or credit, memo, dimensions and source references. For a batch of
another transaction currency that currency (``custbody_erev_txn_currency``) and each line's
transaction debit or credit (``custcol_erev_txn_debit``, ``custcol_erev_txn_credit``) go along as
information: the ledger books the functional amounts, so both lines of a foreign-currency
remeasurement — which have no transaction amount — reach it, and nothing is converted at the
ledger's own rate. A line whose functional amount is nil states no amount and books nothing. The
journal API's limits behind this form (one currency and one exchange rate per entry, one amount
per line) are read from its documentation and not verified against a live account.

Trial balance (CLO-15; REQ-INT-009). ``pull_trial_balance`` reads the closing balances of the
accounts asked for at the period end, and the GL documents of the period on them, on the ADP-12
schedule: ``TrialBalance.lines`` — debit positive, a balance sheet account cumulative, an income
statement account fiscal year to date — and ``details`` with the ADP-10 external id of a document
this subledger posted and None for a document made in the ERP.

The adapter holds no credential (ADP-14: a connection to the in-process mock carries none).
``chart_source`` builds the adapter from a connection's context for a ``COA_SYNC`` run — it is the
``ChartSource`` of ``erev_api.domain.integrations.ports`` — and ``register`` wires it for the code
``NETSUITE``; ``netsuite_factory`` binds a client and base URL (tests), ``connection_factory``
builds the client for the ``base_url`` each dispatch's context names (the worker; DG-LAY-03).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final
from urllib.parse import quote, urlencode

from erev_engine.currencies import ISO_4217

from erev_api.domain.integrations import ports as integration_ports
from erev_api.domain.integrations.ports import transient_status
from erev_api.domain.journals import ports

__all__ = [
    "ACCOUNT_TYPE_MAP",
    "CODE",
    "ErpAccount",
    "ErpDimensionValue",
    "NetSuiteGl",
    "RETRY_BACKOFF_SECONDS",
    "TXN_CREDIT_FIELD",
    "TXN_CURRENCY_FIELD",
    "TXN_DEBIT_FIELD",
    "chart_source",
    "connection_factory",
    "journal_body",
    "netsuite_factory",
    "register",
]

CODE: Final = "NETSUITE"

RETRY_BACKOFF_SECONDS: Final = (30, 60, 120, 240, 480, 900, 900, 900)
MAX_ATTEMPTS: Final = 8
NO_CONNECTION: Final = "No NetSuite connection with a base URL is named: nothing can be reached."
JOURNAL_PATH: Final = "/record/v1/journalEntry/eid:{external_id}"
# 05 ADP-10 rev 1.92: the informational members of a batch whose transaction currency is not the
# entity's functional currency — the entry's transaction currency, a line's transaction amount.
TXN_CURRENCY_FIELD: Final = "custbody_erev_txn_currency"
TXN_DEBIT_FIELD: Final = "custcol_erev_txn_debit"
TXN_CREDIT_FIELD: Final = "custcol_erev_txn_credit"
TRIAL_BALANCE_PATH: Final = "/restlet/v1/trialBalance"
# E-52 account types → the NetSuite account type a journal line states for its account.
ERP_ACCOUNT_TYPES: Final[Mapping[str, str]] = {
    "ASSET": "OthCurrAsset",
    "LIABILITY": "OthCurrLiab",
    "EQUITY": "Equity",
    "REVENUE": "Income",
    "EXPENSE": "Expense",
}
# NetSuite account types → the E-3x account_type / normal_balance of T-REF-15 (research 06 §14.4).
ACCOUNT_TYPE_MAP: Final[Mapping[str, tuple[str, str]]] = {
    "Bank": ("ASSET", "D"),
    "AcctRec": ("ASSET", "D"),
    "OthCurrAsset": ("ASSET", "D"),
    "FixedAsset": ("ASSET", "D"),
    "OthAsset": ("ASSET", "D"),
    "AcctPay": ("LIABILITY", "C"),
    "OthCurrLiab": ("LIABILITY", "C"),
    "DeferRevenue": ("LIABILITY", "C"),
    "LongTermLiab": ("LIABILITY", "C"),
    "Equity": ("EQUITY", "C"),
    "Income": ("REVENUE", "C"),
    "OthIncome": ("REVENUE", "C"),
    "COGS": ("EXPENSE", "D"),
    "Expense": ("EXPENSE", "D"),
    "OthExpense": ("EXPENSE", "D"),
}


@dataclass(frozen=True, slots=True)
class ErpAccount:
    """One chart-of-accounts record as the ERP states it (T-INT-04 ``external_id`` = its record
    id)."""

    external_id: str
    code: str
    name: str
    account_type: str
    normal_balance: str
    is_active: bool

    @property
    def ref(self) -> ports.AccountRef:
        return ports.AccountRef(code=self.code, name=self.name)


@dataclass(frozen=True, slots=True)
class ErpDimensionValue:
    external_id: str
    dimension_code: str
    code: str
    name: str
    is_active: bool


def account_of(record: Mapping[str, Any]) -> ErpAccount:
    kind = str(record.get("acctType", ""))
    account_type, normal_balance = ACCOUNT_TYPE_MAP.get(kind, ("ASSET", "D"))
    return ErpAccount(
        external_id=str(record["id"]),
        code=str(record["acctNumber"]),
        name=str(record.get("acctName") or record["acctNumber"]),
        account_type=account_type,
        normal_balance=normal_balance,
        is_active=not bool(record.get("isInactive", False)),
    )


def dimension_value_of(dimension_code: str, record: Mapping[str, Any]) -> ErpDimensionValue:
    name = str(record.get("name") or record["id"])
    return ErpDimensionValue(
        external_id=str(record["id"]),
        dimension_code=dimension_code,
        code=str(record.get("code") or name),
        name=name,
        is_active=not bool(record.get("isInactive", False)),
    )


class NetSuiteGl:
    """One adapter per dispatch, over the client the root supplies; the chart is pulled on
    demand."""

    code: Final = CODE

    def __init__(
        self,
        context: ports.GLContext,
        *,
        client: Any,
        base_url: str,
        sleep: Callable[[float], None] | None = None,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._context = context
        self._client = client
        self._base = base_url.rstrip("/")
        self._sleep = sleep if sleep is not None else _default_sleep
        self._max_attempts = max_attempts
        self._chart: dict[str, ErpAccount] | None = None
        self._types = {account.code: account.account_type for account in context.accounts}
        self.attempts: list[tuple[str, int]] = []

    # --- REQ-INT-008 ------------------------------------------------------------------------------

    def pull_erp_accounts(self) -> tuple[ErpAccount, ...]:
        body = self._get("/record/v1/account")
        found = tuple(sorted((account_of(r) for r in body.get("items", ())), key=lambda a: a.code))
        self._chart = {account.code: account for account in found}
        return found

    def pull_chart_of_accounts(self) -> Sequence[ports.AccountRef]:
        return tuple(account.ref for account in self.pull_erp_accounts() if account.is_active)

    def pull_dimension_values(self, dimension_code: str) -> tuple[ErpDimensionValue, ...]:
        body = self._get(f"/record/v1/{quote(dimension_code)}")
        return tuple(
            sorted(
                (dimension_value_of(dimension_code, r) for r in body.get("items", ())),
                key=lambda v: v.code,
            )
        )

    def validate_accounts(
        self, accounts: Sequence[ports.AccountRef], dimensions: Sequence[ports.DimensionRef]
    ) -> ports.ValidationResult:
        chart = (
            self._chart
            if self._chart is not None
            else {a.code: a for a in self.pull_erp_accounts()}
        )
        unknown = sorted({account.code for account in accounts} - chart.keys())
        return ports.ValidationResult(
            errors=tuple(
                f"Account {code} is not in the NetSuite chart of accounts." for code in unknown
            )
        )

    # --- REQ-JE-014: journals (CLO-15) -----------------------------------------------------------

    def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
        path = JOURNAL_PATH.format(external_id=quote(chunk.external_id, safe=":"))
        self._send("PUT", path, journal_body(chunk, self._types), external_id=chunk.external_id)
        posted = self.get_posting(chunk.external_id)
        if posted is None:
            # ADP-12 rev 1.175: the ledger answered the upsert and does not show the journal —
            # an acceptance, which the exits of a failed batch must not read as "holds nothing".
            raise ports.Accepted(f"{chunk.external_id} was accepted and cannot be read back yet")
        return posted

    def get_posting(self, external_id: str) -> ports.PostingResult | None:
        path = JOURNAL_PATH.format(external_id=quote(external_id, safe=":"))
        response = self._send("GET", path, None, external_id=external_id, missing_ok=True)
        if response is None:
            return None
        body = response.json()
        posted = body.get("tranDate")
        return ports.PostingResult(
            external_id=external_id,
            status="POSTED",
            gl_document_id=str(body["tranId"]),
            gl_posted_date=None if posted is None else date.fromisoformat(str(posted)),
            response_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    # --- REQ-INT-009: trial balance (CLO-15) ------------------------------------------------------

    def pull_trial_balance(
        self, entity: ports.EntityRef, period: ports.PeriodRef, accounts: Sequence[str]
    ) -> ports.TrialBalance:
        query = urlencode(
            {
                "account": self._context.tenant_code,
                "subsidiary": entity.code,
                "period": period.period_key,
                "startDate": period.start_date.isoformat(),
                "endDate": period.end_date.isoformat(),
                "accounts": ",".join(sorted(set(accounts))),
            }
        )
        body = self._get(f"{TRIAL_BALANCE_PATH}?{query}")
        lines = tuple(
            ports.TrialBalanceLine(
                account_code=str(item["account"]),
                currency=str(item["currency"]),
                amount=Decimal(str(item["amount"])),
            )
            for item in body.get("lines", ())
        )
        details = tuple(
            ports.TrialBalanceDetail(
                account_code=str(item["account"]),
                currency=str(item["currency"]),
                amount=Decimal(str(item["amount"])),
                document_reference=str(item["tranId"]),
                external_id=None if item.get("externalId") is None else str(item["externalId"]),
                posted_date=None
                if item.get("tranDate") is None
                else date.fromisoformat(str(item["tranDate"])),
            )
            for item in body.get("details", ())
        )
        balances: dict[str, Decimal] = {}
        for line in lines:
            balances[line.account_code] = balances.get(line.account_code, Decimal(0)) + line.amount
        return ports.TrialBalance(
            entity_code=entity.code,
            period_key=period.period_key,
            balances=balances,
            lines=lines,
            details=details,
        )

    # --- one attempt: the export relay owns the schedule (ADP-12, ADP-31) -------------------------

    def _send(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None,
        *,
        external_id: str,
        missing_ok: bool = False,
    ) -> Any | None:
        """One request; the response of a 2xx, None for a 404 that ``missing_ok`` admits."""
        try:
            response = self._client.request(method, f"{self._base}{path}", json=body)
        except Exception as error:  # noqa: BLE001 - driver errors are transient (ADP-12)
            self.attempts.append((path, 0))
            raise ports.Transient(f"connection error: {type(error).__name__}") from error
        status = int(response.status_code)
        self.attempts.append((path, status))
        if status < 300:
            return response
        if status == 404 and missing_ok:
            return None
        if transient_status(status):
            header = response.headers.get("Retry-After")
            raise ports.Transient(
                f"NetSuite answered HTTP {status}.",
                retry_after=None if header is None else float(header),
            )
        detail = _error_of(response)
        existing = detail.get("existing")
        if status == 409 and existing is not None:
            raise ports.Duplicate(external_id, str(existing))
        raise ports.Permanent(str(detail.get("message") or f"NetSuite answered HTTP {status}."))

    # --- transport with the ADP-12 schedule -------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        last: ports.Transient | None = None
        for attempt in range(self._max_attempts):
            retry_after: float | None = None
            try:
                response = self._client.get(f"{self._base}{path}")
            except Exception as error:  # noqa: BLE001 - driver errors are transient (ADP-12)
                last = ports.Transient(f"connection error: {type(error).__name__}")
                self.attempts.append((path, 0))
            else:
                status = int(response.status_code)
                self.attempts.append((path, status))
                if status < 300:
                    body = response.json()
                    return dict(body) if isinstance(body, Mapping) else {"items": body}
                if transient_status(status):  # ADP-12: every 5xx (05 rev 1.12)
                    last = ports.Transient(f"HTTP {status}")
                    header = response.headers.get("Retry-After")
                    retry_after = None if header is None else float(header)
                else:
                    raise ports.Permanent(f"HTTP {status}")
            if attempt + 1 < self._max_attempts:
                delay: float = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                if retry_after is not None:
                    delay = max(delay, retry_after)
                self._sleep(float(delay))
        assert last is not None
        raise last


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _error_of(response: Any) -> dict[str, Any]:
    """The message of a SuiteTalk error body (``o:errorDetails[0].detail``) and, for "the external
    id exists", the document the ERP holds."""
    try:
        body = response.json()
    except ValueError:
        return {}
    if not isinstance(body, Mapping):
        return {}
    details = body.get("o:errorDetails") or ()
    first = details[0] if details and isinstance(details[0], Mapping) else {}
    return {"message": first.get("detail") or body.get("title"), "existing": first.get("tranId")}


def _amount(value: Decimal, currency: str) -> str:
    exponent = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    return format(Decimal(value).quantize(exponent), "f")


def journal_body(
    chunk: ports.JournalChunk, account_types: Mapping[str, str | None] | None = None
) -> dict[str, Any]:
    """The journal entry of a chunk (SuiteTalk REST record shape, minimally): the REQ-JE-011
    document in the entity's functional currency (module docstring; ruling R-110). A line states
    its functional debit or credit; a line whose functional amount is nil states neither. Only a
    batch of another transaction currency carries the informational members."""
    types = account_types or {}
    currency, txn_currency = chunk.functional_currency, chunk.txn_currency
    foreign = txn_currency != currency
    items: list[dict[str, Any]] = []
    for line in chunk.lines:
        account: dict[str, Any] = {"acctNumber": line.account_code, "acctName": line.account_name}
        erp_type = ERP_ACCOUNT_TYPES.get(types.get(line.account_code) or "")
        if erp_type is not None:
            account["acctType"] = erp_type
        item: dict[str, Any] = {
            "line": line.line_no,
            "account": account,
            "memo": line.memo,
            "custcol_erev_je_no": line.je_no,
            "custcol_erev_dimensions": json.dumps(
                dict(line.dimensions), sort_keys=True, separators=(",", ":")
            ),
            "custcol_erev_source": line.source_references,
        }
        if line.debit_functional:
            item["debit"] = _amount(line.debit_functional, currency)
        if line.credit_functional:
            item["credit"] = _amount(line.credit_functional, currency)
        if foreign and line.debit:
            item[TXN_DEBIT_FIELD] = _amount(line.debit, txn_currency)
        if foreign and line.credit:
            item[TXN_CREDIT_FIELD] = _amount(line.credit, txn_currency)
        items.append(item)
    body: dict[str, Any] = {
        "externalId": chunk.external_id,
        "subsidiary": {"refName": chunk.entity_code},
        "currency": {"refName": currency},
        "tranDate": chunk.period_end_date.isoformat(),
        "postingPeriod": {"refName": chunk.posting_period},
        "memo": f"eRev journal run {chunk.run_no}, batch {chunk.batch_no}, chunk {chunk.chunk_no}",
        "line": {"items": items},
    }
    if foreign:
        body[TXN_CURRENCY_FIELD] = txn_currency
    return body


def chart_source(
    context: integration_ports.InboundContext, *, sleep: Callable[[float], None] | None = None
) -> NetSuiteGl:
    """The ``COA_SYNC`` source of one connection (REQ-INT-008): the connection's base URL, the
    client the root supplies and its non-secret ``config.max_attempts`` (else the ADP-12 default).
    The chart is the ERP's, so the ``GLContext`` carries the workspace code and no accounts."""
    return NetSuiteGl(
        ports.GLContext(tenant_code=context.tenant_code, accounts=()),
        client=context.client,
        base_url=context.base_url,
        sleep=sleep,
        max_attempts=max(1, int(context.config.get("max_attempts", MAX_ATTEMPTS))),
    )


def register() -> None:
    """Composition-root wiring (DG-LAY-03): the ``NETSUITE`` chart source over the context's
    client. The journal factory is registered by the root that owns the HTTP client
    (``connection_factory``)."""
    integration_ports.register_chart_source(CODE, chart_source)


def netsuite_factory(client: Any, base_url: str) -> ports.GLAdapterFactory:
    """The ``GLAdapterFactory`` a composition root registers with ``register_gl_adapter``
    (DG-LAY-03): the client and base URL are bound here, the workspace context arrives per
    dispatch."""

    def build(context: ports.GLContext) -> ports.GLAdapter:
        return NetSuiteGl(context, client=client, base_url=base_url)

    return build


def connection_factory(build_client: Callable[[str], Any]) -> ports.GLAdapterFactory:
    """The ``GLAdapterFactory`` of a root that reaches each connection over its own ``base_url``
    (the worker; DG-LAY-03): the client is built per dispatch from the context's ``base_url``
    through ``build_client`` (the SAR-15 client factory), and ``config.max_attempts`` bounds the
    trial-balance schedule. A context without a ``base_url`` names no connection: ``Permanent``."""

    def build(context: ports.GLContext) -> ports.GLAdapter:
        if not context.base_url:
            raise ports.Permanent(NO_CONNECTION)
        return NetSuiteGl(
            context,
            client=build_client(context.base_url),
            base_url=context.base_url,
            max_attempts=max(1, int(context.config.get("max_attempts", MAX_ATTEMPTS))),
        )

    return build

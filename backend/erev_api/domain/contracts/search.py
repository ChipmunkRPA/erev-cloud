"""API-R-55 search over the five E-120 scopes (04 §15.3 API-R-55, §16.13 API-S-SearchResult rev
1.195; dev-guide DG-LST-11; SCREENS R-01, §1.4; BUILD_SPEC CTR-28; supervisor ruling R-116 (f)).

**The word rule.** An item matches when every term of ``q`` begins a word of its ``primary`` or of
its ``secondary``; a word is a maximal run of letters or digits, compared case-folded. The rule
has ONE implementation, the database's: ``TERMS`` splits ``q`` and ``_begins_word`` reads a text,
both with the character class ``[[:alnum:]]`` over ``lower()``. Python defines no word.

**The scan.** A scope is one statement over the scope's rows, read under the caller's row policy
and the request's statement timeout: the rows every term matches, an exact ``primary`` first, then
the rows whose ``primary`` alone matches, then the rest; within each the row written last, then
``id`` descending; ``limit + 1`` rows. The cost is linear in the rows the caller can read. A
substring is never matched: no index answers one, and what a search finds must not change when a
table of search keys replaces the scan (item SEARCH-KEYS-1).

**What is answered.** Contracts and journal runs are bound by their entity (row-level security).
``obligation`` and ``source_invoice`` are tenant-level in the policy and are read THROUGH the
contract: an obligation's own contract, an invoice's contract by the ``contract_ref`` of its
lines — so a record the caller could not open is not answered, and nothing counts it. An invoice
is answered once, in its newest stored version. Customers are tenant master data. ``status`` is
what the scope's single read answers without parameters (``queries.shown_statuses``,
``queries.satisfaction_at``), read for the page at once (DG-LST-10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, case, exists, func, literal, or_, select, text
from sqlalchemy import true as sql_true
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    contract,
    customer,
    journal_run,
    legal_entity,
    obligation,
    period,
    product,
    source_invoice,
    source_invoice_line,
    source_record,
)
from erev_api.domain.contracts import queries
from erev_api.domain.platform.audit_labels import BETWEEN
from erev_api.enums import SearchScope
from erev_api.problems import Problem, ProblemError

READ_PERMISSION: Final = "contract.read"
RULE_ID: Final = "API-R-55"
DEFAULT_LIMIT: Final = 8
MAX_LIMIT: Final = 50
MIN_LENGTH: Final = 2
MAX_LENGTH: Final = 200
API: Final = "/api/v1"
# 04 §16.13 "Matching and order": the terms of ``q``, as the database splits it.
TERMS: Final = text(
    "SELECT array_remove(regexp_split_to_array(lower(:q), '[^[:alnum:]]+'), '') AS terms"
)
# ... and what stands in front of a term where it begins a word of a text.
WORD_START: Final = "(^|[^[:alnum:]])"
TOO_SHORT: Final = "Type at least 2 characters to search."
TOO_LONG: Final = "Search for at most 200 characters."
NO_TERM: Final = "Type a letter or a digit to search."
# The order of a scope: the tier, then the instant the row was written, then its id.
EXACT: Final = 0
BY_PRIMARY: Final = 1
type After = tuple[int, datetime, UUID]
type Statuses = Callable[[Session, Sequence[Mapping[str, Any]], datetime], Mapping[UUID, str]]


def invalid(field: str, message: str) -> Problem:
    """422 ``validation-failed`` on one parameter of the search."""
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field=field, rule_id=RULE_ID, message=message)],
    )


@dataclass(frozen=True, slots=True)
class Found:
    """One page of a scope: its items in order and, when a further row of the caller's exists,
    the position of the last item — what the next request of the scope continues after."""

    scope: SearchScope
    items: list[dict[str, Any]]
    last: After | None


@dataclass(frozen=True, slots=True)
class _Scope:
    """A scope's rows before the terms: a statement that selects ``id``, ``primary``,
    ``secondary`` and ``updated`` (and whatever ``href`` and ``statuses`` read), the API link of
    a row, and the scope's status literals for a page of rows."""

    rows: Select[Any]
    href: Callable[[Mapping[str, Any]], str]
    statuses: Statuses


def _no_status(
    _session: Session, _rows: Sequence[Mapping[str, Any]], _now: datetime
) -> Mapping[UUID, str]:
    return {}


def _same_tenant(left: Any, right: Any, *on: ColumnElement[bool]) -> ColumnElement[bool]:
    return and_(left.c.tenant_id == right.c.tenant_id, *on)


def _contracts() -> _Scope:
    rows = select(
        contract.c.id,
        contract.c.external_id.label("primary"),
        customer.c.name.label("secondary"),
        contract.c.updated_at.label("updated"),
        contract.c.status.label("stored"),
    ).select_from(
        contract.join(
            customer, _same_tenant(customer, contract, customer.c.id == contract.c.customer_id)
        )
    )

    def statuses(
        session: Session, found: Sequence[Mapping[str, Any]], _now: datetime
    ) -> Mapping[UUID, str]:
        return queries.shown_statuses(session, {row["id"]: row["stored"] for row in found})

    return _Scope(rows, lambda row: f"{API}/contracts/{row['id']}", statuses)


def _customers() -> _Scope:
    rows = select(
        customer.c.id,
        customer.c.code.label("primary"),
        customer.c.name.label("secondary"),
        customer.c.updated_at.label("updated"),
    )
    return _Scope(rows, lambda row: f"{API}/customers/{row['id']}", _no_status)


def _invoices() -> _Scope:
    """The newest stored version of each invoice whose lines name a contract the session reads;
    that contract — the first by external id where the lines name several — is ``secondary`` and
    the link. The join to ``contract`` is what binds the invoice to the caller's entities."""
    billed = (
        select(contract.c.id, contract.c.external_id)
        .select_from(
            source_invoice_line.join(
                contract,
                _same_tenant(
                    contract,
                    source_invoice_line,
                    contract.c.external_id == source_invoice_line.c.contract_ref,
                ),
            )
        )
        .where(
            source_invoice_line.c.tenant_id == source_invoice.c.tenant_id,
            source_invoice_line.c.source_invoice_id == source_invoice.c.id,
        )
        .order_by(contract.c.external_id)
        .limit(1)
        .correlate(source_invoice)
        .lateral("billed_contract")
    )
    later, later_record = source_invoice.alias("later_invoice"), source_record.alias("later_record")
    superseded = exists().where(
        later.c.tenant_id == source_invoice.c.tenant_id,
        later.c.source_system == source_invoice.c.source_system,
        later.c.external_invoice_id == source_invoice.c.external_invoice_id,
        later_record.c.tenant_id == later.c.tenant_id,
        later_record.c.id == later.c.source_record_id,
        later_record.c.version_order > source_record.c.version_order,
    )
    rows = (
        select(
            source_invoice.c.id,
            source_invoice.c.invoice_number.label("primary"),
            billed.c.external_id.label("secondary"),
            source_invoice.c.created_at.label("updated"),
            billed.c.id.label("contract_id"),
        )
        .select_from(
            source_invoice.join(
                source_record,
                _same_tenant(
                    source_record,
                    source_invoice,
                    source_record.c.id == source_invoice.c.source_record_id,
                ),
            ).join(billed, sql_true())
        )
        .where(~superseded)
    )
    return _Scope(rows, lambda row: f"{API}/contracts/{row['contract_id']}", _no_status)


def _obligations() -> _Scope:
    rows = select(
        obligation.c.id,
        (contract.c.external_id + BETWEEN + obligation.c.obligation_key).label("primary"),
        product.c.name.label("secondary"),
        obligation.c.created_at.label("updated"),
    ).select_from(
        obligation.join(
            contract, _same_tenant(contract, obligation, contract.c.id == obligation.c.contract_id)
        ).join(product, _same_tenant(product, obligation, product.c.id == obligation.c.product_id))
    )

    def statuses(
        session: Session, found: Sequence[Mapping[str, Any]], now: datetime
    ) -> Mapping[UUID, str]:
        return queries.satisfaction_at(session, [row["id"] for row in found], now=now)

    return _Scope(rows, lambda row: f"{API}/obligations/{row['id']}", statuses)


def _journals() -> _Scope:
    rows = select(
        journal_run.c.id,
        journal_run.c.run_no.label("primary"),
        (period.c.period_key + BETWEEN + legal_entity.c.code).label("secondary"),
        journal_run.c.updated_at.label("updated"),
        journal_run.c.state.label("stored"),
    ).select_from(
        journal_run.join(
            period, _same_tenant(period, journal_run, period.c.id == journal_run.c.period_id)
        ).join(
            legal_entity,
            _same_tenant(legal_entity, journal_run, legal_entity.c.id == journal_run.c.entity_id),
        )
    )

    def statuses(
        _session: Session, found: Sequence[Mapping[str, Any]], _now: datetime
    ) -> Mapping[UUID, str]:
        return {row["id"]: str(getattr(row["stored"], "value", row["stored"])) for row in found}

    return _Scope(rows, lambda row: f"{API}/journal-runs/{row['id']}", statuses)


SCOPES: Final[Mapping[SearchScope, Callable[[], _Scope]]] = {
    SearchScope.CONTRACTS: _contracts,
    SearchScope.CUSTOMERS: _customers,
    SearchScope.INVOICES: _invoices,
    SearchScope.OBLIGATIONS: _obligations,
    SearchScope.JOURNALS: _journals,
}


def checked(q: str) -> str:
    """``q`` trimmed; 422 ``validation-failed`` outside 2 to 200 characters (04 API-R-55)."""
    trimmed = q.strip()
    if len(trimmed) < MIN_LENGTH:
        raise invalid("q", TOO_SHORT)
    if len(trimmed) > MAX_LENGTH:
        raise invalid("q", TOO_LONG)
    return trimmed


def _begins_word(value: ColumnElement[Any], term: str) -> ColumnElement[bool]:
    """``lower(value) ~ ('(^|[^[:alnum:]])' || term)``: ``term`` begins a word of ``value``.
    ``term`` is one of the database's own terms — letters and digits alone — bound as a value."""
    return func.lower(value).regexp_match(literal(WORD_START + term))


def statement(
    scope: _Scope, *, q: str, terms: Sequence[str], limit: int, after: After | None
) -> Select[Any]:
    """The scope's page: the rows every term matches, in the order of 04 §16.13, ``limit + 1`` of
    them from ``after`` on. ``tier`` is 0 for an exact ``primary``, 1 where ``primary`` alone
    matches every term and 2 otherwise."""
    found = scope.rows.subquery("found")
    by_primary = and_(*(_begins_word(found.c.primary, term) for term in terms))
    matched = and_(
        *(
            or_(_begins_word(found.c.primary, term), _begins_word(found.c.secondary, term))
            for term in terms
        )
    )
    tier = case(
        (func.lower(found.c.primary) == func.lower(literal(q)), EXACT),
        (by_primary, BY_PRIMARY),
        else_=BY_PRIMARY + 1,
    )
    page = select(found, tier.label("tier")).where(matched)
    if after is not None:
        tier_after, updated_after, id_after = after
        page = page.where(
            or_(
                tier > tier_after,
                and_(
                    tier == tier_after,
                    or_(
                        found.c.updated < updated_after,
                        and_(found.c.updated == updated_after, found.c.id < id_after),
                    ),
                ),
            )
        )
    return page.order_by(tier, found.c.updated.desc(), found.c.id.desc()).limit(limit + 1)


def _terms(session: Session, q: str) -> list[str]:
    terms = [str(term) for term in session.execute(TERMS, {"q": q}).scalar_one()]
    if not terms:
        raise invalid("q", NO_TERM)
    return terms


def _read(
    session: Session,
    name: SearchScope,
    *,
    q: str,
    terms: Sequence[str],
    limit: int,
    after: After | None,
    now: datetime,
) -> Found:
    scope = SCOPES[name]()
    rows = [
        dict(row)
        for row in session.execute(
            statement(scope, q=q, terms=terms, limit=limit, after=after)
        ).mappings()
    ]
    shown = rows[:limit]
    statuses = scope.statuses(session, shown, now) if shown else {}
    items = [
        {
            "id": row["id"],
            "primary": row["primary"],
            "secondary": row["secondary"],
            "status": statuses.get(row["id"]),
            "href": scope.href(row),
        }
        for row in shown
    ]
    last: After | None = None
    if len(rows) > limit:
        final = shown[-1]
        last = (int(final["tier"]), final["updated"], final["id"])
    return Found(scope=name, items=items, last=last)


def search(
    ctx: RequestContext,
    *,
    q: str,
    scope: SearchScope | None,
    limit: int,
    after: After | None,
    now: datetime,
) -> list[Found]:
    """``GET /search``: the page of ``scope`` from ``after`` on, or the first page of every E-120
    scope in E-120 order. ``q`` is the trimmed query (``checked``); 422 when it holds no term."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        terms = _terms(session, q)
        names = list(SearchScope) if scope is None else [scope]
        return [
            _read(session, name, q=q, terms=terms, limit=limit, after=after, now=now)
            for name in names
        ]

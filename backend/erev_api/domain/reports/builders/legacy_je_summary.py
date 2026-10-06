"""RPT-13 ``legacy_je_summary`` Legacy journal summary (SCREENS_B §5.6.3 RPT-13; ENGINE_SPEC_B
S14-R-23; DEVIATIONS §3 PJR-2 to PJR-5; legacy 06 §7.3 TC-JE-01, TC-JE-02; POLICIES CHK-020,
CHK-022; PRD WLD-X-26; dev-guide §9.6 kind ``journal_entry_totals``; 03 REQ-JE-007, REQ-JE-008;
BUILD_SPEC RPS-5).

The report wraps ``journals.views.legacy_view`` (CLO-9) over the run's entities, the ``ASC606``
book, the inclusive window ``from_date`` to ``to_date`` and ``mode`` (``GROSS``, else ``DELTA``
against the ``LEGACY`` book), reading the subledger lines recorded by the run's ``known_at``.

Rows, one list in section order:

- section ``by_account``, ``account:<code>``: ``account``, ``currency``, ``debit``, ``credit`` and
  ``net`` (debit − credit);
- section ``by_entity``, ``entity:<code>``: ``entity_code``, ``debit``, ``credit``, ``balanced`` and
  ``difference`` (CTL-022);
- section ``line_items``, ``item:<legacy key>:<account>``: ``key``, ``account``, ``entity_code`` and
  the signed ``amount`` (debit positive).

A row key takes ``:<ISO>`` when the window holds several currencies, and a line item also
``:<entity code>`` when one key and account appear in several entities. Control totals: ``mode``,
``book``, ``from_date``, ``to_date``, ``lines`` and, per currency, ``total_debit``,
``total_credit`` and ``net``. No tie-out.

[J] Defaults: ``mode`` ``GROSS`` (stored by the framework), ``book`` ``ASC606``, and the window the
period holding the run's as-of date (SCREENS_B RPT-13). The view's refusals (``DELTA`` without an
enabled Legacy book) end the run FAILED with the view's problem (RV-14).
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Final

from erev_api.domain.journals import views
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_history as history
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import BookCode, JournalRunMode
from erev_api.uow import UnitOfWork

CODE: Final = "legacy_je_summary"
BY_ACCOUNT: Final = "by_account"
BY_ENTITY: Final = "by_entity"
LINE_ITEMS: Final = "line_items"
COLUMNS: Final = (
    Column("section", "Section", "code"),
    Column("account", "Account", "code"),
    Column("entity_code", "Entity", "code"),
    Column("key", "Key", "text"),
    Column("currency", "Currency", "code"),
    Column("debit", "Debit", "money"),
    Column("credit", "Credit", "money"),
    Column("net", "Net", "money"),
    Column("balanced", "Balanced", "boolean"),
    Column("difference", "Difference", "money"),
    Column("amount", "Amount", "money"),
)


def _row(section: str, row_key: str, **values: Any) -> dict[str, Any]:
    return {"row_key": row_key, "section": section, **values}


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = str(params.book_code or params.parameters.get("book") or BookCode.ASC606.value)
    mode = str(params.parameters.get("mode") or JournalRunMode.GROSS.value)
    from_date, to_date = history.date_range(session, params, year=False)
    codes = [entity.code for entity in tie_outs.entities(session, params.entity_ids)]
    view = views.legacy_view(
        uow, codes, book_code, from_date, to_date, mode, known_at=params.known_at
    )
    several = len(view.totals) > 1
    rows: list[dict[str, Any]] = []
    for account in view.by_account:
        suffix = f":{account.currency}" if several else ""
        rows.append(
            _row(
                BY_ACCOUNT,
                f"account:{account.account}{suffix}",
                account=account.account,
                currency=account.currency,
                debit=tie_outs.money(account.debit, account.currency),
                credit=tie_outs.money(account.credit, account.currency),
                net=tie_outs.money(account.net, account.currency),
            )
        )
    for entity in view.by_entity:
        suffix = f":{entity.currency}" if several else ""
        rows.append(
            _row(
                BY_ENTITY,
                f"entity:{entity.entity_code}{suffix}",
                entity_code=entity.entity_code,
                currency=entity.currency,
                debit=tie_outs.money(entity.debit, entity.currency),
                credit=tie_outs.money(entity.credit, entity.currency),
                balanced=entity.balanced,
                difference=tie_outs.money(entity.difference, entity.currency),
            )
        )
    shared = Counter((item.key, item.account, item.currency) for item in view.line_items)
    for item in view.line_items:
        suffix = f":{item.currency}" if several else ""
        if shared[(item.key, item.account, item.currency)] > 1:
            suffix += f":{item.entity_code}"
        rows.append(
            _row(
                LINE_ITEMS,
                f"item:{item.key}:{item.account}{suffix}",
                key=item.key,
                account=item.account,
                entity_code=item.entity_code,
                currency=item.currency,
                amount=tie_outs.money(item.amount, item.currency),
            )
        )
    control: dict[str, Any] = {
        "mode": view.mode,
        "book": view.book_code,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "lines": sum(total.lines for total in view.totals),
        "total_debit": tie_outs.by_currency(
            {total.currency: Decimal(total.total_debit) for total in view.totals}
        ),
        "total_credit": tie_outs.by_currency(
            {total.currency: Decimal(total.total_credit) for total in view.totals}
        ),
        "net": tie_outs.by_currency({total.currency: Decimal(total.net) for total in view.totals}),
    }
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=control)

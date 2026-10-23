"""Read separate closing balances and period GL documents from one optional extended sheet."""

from __future__ import annotations

from datetime import date

from erev_api.domain.close import trial_balance as tb
from erev_api.domain.imports.parse import SheetRows, cell_text
from erev_api.domain.journals.ports import TrialBalanceDetail, TrialBalanceLine

HEADERS = (*tb.HEADERS, "row_type", "document_reference", "external_id", "posted_date")


def read(
    sheet: SheetRows, *, functional_currency: str, start_date: date, end_date: date
) -> tuple[tuple[TrialBalanceLine, ...], tuple[TrialBalanceDetail, ...]]:
    """Legacy three-column balances or explicit BALANCE/DOCUMENT rows; never sum documents
    into closing balances. Document dates must belong to the reconciliation period."""
    headers = tuple((cell_text(value) or "").strip().lower() for value in sheet.headers)
    while headers and headers[-1] == "":
        headers = headers[:-1]
    if "row_type" not in headers:
        return tb.lines_of_sheet(sheet, functional_currency=functional_currency), ()
    if sorted(headers) != sorted(HEADERS):
        raise tb.SheetError(
            [
                (
                    1,
                    "file_id",
                    "Use account, currency, amount; or add row_type, "
                    "document_reference, external_id and posted_date for GL detail.",
                )
            ]
        )
    columns = {name: headers.index(name) for name in HEADERS}
    findings: list[tuple[int | None, str, str]] = []
    balance_rows = []
    documents: list[tuple[int, TrialBalanceDetail]] = []
    for number, cells in sheet.rows:
        values = {
            name: (cell_text(cells[index]) or "").strip() if index < len(cells) else ""
            for name, index in columns.items()
        }
        formulas = [
            name for name, index in columns.items() if (number, index) in sheet.formula_cells
        ]
        if formulas:
            findings.extend((number, name, tb.FORMULA_CELL) for name in formulas)
            continue
        if not any(values.values()):
            continue
        kind = values["row_type"].upper()
        monetary = tuple(values[key] for key in tb.HEADERS)
        if kind == "BALANCE":
            balance_rows.append((number, monetary))
            for name in ("document_reference", "external_id", "posted_date"):
                if values[name]:
                    findings.append((number, name, "Leave document fields empty on BALANCE rows."))
            continue
        if kind != "DOCUMENT":
            findings.append((number, "row_type", "Choose BALANCE or DOCUMENT."))
            continue
        try:
            (line,) = tb.lines_of_sheet(
                SheetRows(sheet.sheet_name, tb.HEADERS, ((number, monetary),), frozenset()),
                functional_currency=functional_currency,
            )
        except tb.SheetError as error:
            findings.extend(error.findings)
            continue
        if not values["document_reference"]:
            findings.append((number, "document_reference", "Enter the GL document reference."))
            continue
        try:
            posted = date.fromisoformat(values["posted_date"])
            if posted.isoformat() != values["posted_date"] or not start_date <= posted <= end_date:
                raise ValueError("outside period")
        except ValueError:
            findings.append(
                (
                    number,
                    "posted_date",
                    "Enter a YYYY-MM-DD posting date inside the reconciliation period.",
                )
            )
            continue
        documents.append(
            (
                number,
                TrialBalanceDetail(
                    account_code=line.account_code,
                    currency=line.currency,
                    amount=line.amount,
                    document_reference=values["document_reference"],
                    external_id=values["external_id"] or None,
                    posted_date=posted,
                ),
            )
        )
    balances: tuple[TrialBalanceLine, ...] = ()
    try:
        balances = tb.lines_of_sheet(
            SheetRows(sheet.sheet_name, tb.HEADERS, tuple(balance_rows), frozenset()),
            functional_currency=functional_currency,
        )
    except tb.SheetError as error:
        findings.extend(error.findings)
    accounts = {line.account_code for line in balances}
    for number, document in documents:
        if document.account_code not in accounts:
            findings.append(
                (number, "account", "Include a BALANCE row for this document's account.")
            )
    if findings:
        raise tb.SheetError(findings)
    return balances, tuple(document for _, document in documents)

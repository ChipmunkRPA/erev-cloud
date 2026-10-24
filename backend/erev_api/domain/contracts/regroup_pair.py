"""Consistency of a retained, book-specific regroup pair before submission/application."""

from collections.abc import Mapping, Sequence
from datetime import date
from fractions import Fraction
from typing import Any, Never

from erev_api.problems import Problem
from erev_engine.canonical import canonical_bytes
from erev_engine.currencies import ISO_4217


def _refuse() -> Never:
    raise Problem(
        "invalid-transition",
        "The regroup pair differs from its retained transfer basis; rebuild both sides.",
    )


def _lines(
    rows: object, currency: str, action: str
) -> dict[str, tuple[Fraction, Fraction, str, str, str]]:
    if not isinstance(rows, (list, tuple)) or not rows:
        _refuse()
    result = {}
    assert isinstance(rows, (list, tuple))
    for row in rows:
        if not isinstance(row, Mapping) or row.get("action") != action:
            _refuse()
        assert isinstance(row, Mapping)
        key = str(row.get("obligation_key") or "")
        amount = row.get("consideration_delta")
        if (
            not key
            or key in result
            or not isinstance(amount, Mapping)
            or amount.get("currency") != currency
        ):
            _refuse()
        assert isinstance(amount, Mapping)
        try:
            quantity, price = Fraction(str(row["quantity_delta"])), Fraction(str(amount["amount"]))
        except (KeyError, ValueError, ZeroDivisionError):
            _refuse()
        sign = -1 if action == "REMOVE" else 1
        if quantity * sign <= 0 or price * sign < 0:
            _refuse()
        result[key] = (
            quantity * sign,
            price * sign,
            str(row.get("start_date") or ""),
            str(row.get("end_date") or ""),
            str(row.get("product_code") or ""),
        )
    return result


def require_consistent(rows: Sequence[Mapping[str, Any]], *, primary_book: str) -> None:
    """Validate new retained pairs; do not reinterpret legacy pairs lacking these fields."""
    if not any(row.get("regroup_id") is not None for row in rows):
        return
    if (
        len(rows) != 2
        or len({str(row.get("regroup_id")) for row in rows}) != 1
        or any(row.get("regroup_id") is None for row in rows)
    ):
        _refuse()
    by_kind = {str(row["kind"]): row for row in rows}
    if set(by_kind) != {"REMOVE_OBLIGATION", "ADD_OBLIGATION"}:
        _refuse()
    source, target = by_kind["REMOVE_OBLIGATION"], by_kind["ADD_OBLIGATION"]
    if (
        source["contract_id"] == target["contract_id"]
        or source["effective_date"] != target["effective_date"]
        or source["currency"] != target["currency"]
    ):
        _refuse()
    questionnaires = [row.get("questionnaire") or {} for row in (source, target)]
    if not any("regroup_book_lines" in q or "regroup_source_basis" in q for q in questionnaires):
        return
    if any("SEPARATE_CONTRACT" in (row.get("chosen_treatments") or {}).values() for row in rows):
        _refuse()
    out, incoming = [q.get("regroup_book_lines") for q in questionnaires]
    evidence = questionnaires[0].get("regroup_source_basis")
    if (
        not isinstance(out, Mapping)
        or not isinstance(incoming, Mapping)
        or not isinstance(evidence, Mapping)
    ):
        _refuse()
    assert (
        isinstance(out, Mapping) and isinstance(incoming, Mapping) and isinstance(evidence, Mapping)
    )
    if not out or set(out) != set(incoming) or set(out) != set(evidence) or primary_book not in out:
        _refuse()
    if canonical_bytes(evidence) != canonical_bytes(questionnaires[1].get("regroup_source_basis")):
        _refuse()
    currency = str(source["currency"]).strip()
    scale = 10 ** ISO_4217[currency].minor_unit
    source_lines = _lines(source["lines"], currency, "REMOVE")
    target_lines = _lines(target["lines"], currency, "ADD")
    for book in out:
        removed = _lines(out[book], currency, "REMOVE")
        added = _lines(incoming[book], currency, "ADD")
        if removed != added or set(removed) != set(source_lines) or set(added) != set(target_lines):
            _refuse()
        if book == primary_book and (removed != source_lines or added != target_lines):
            _refuse()
        basis = evidence[book]
        if not isinstance(basis, Mapping) or basis.get("effective_date") != str(
            source["effective_date"]
        ):
            _refuse()
        obligations = basis.get("obligations")
        if not isinstance(obligations, Mapping) or set(obligations) != set(removed):
            _refuse()
        for key, (quantity, amount, start, end, _product) in removed.items():
            item = obligations[key]
            try:
                if quantity != Fraction(
                    str(item["remaining_quantity"])
                ) or amount * scale != Fraction(str(item["remaining_minor"])):
                    _refuse()
                minor = [
                    Fraction(str(item[field]))
                    for field in ("allocation_minor", "recognized_minor", "remaining_minor")
                ]
                if (
                    any(value.denominator != 1 for value in minor)
                    or minor[0] - minor[1] != minor[2]
                ):
                    _refuse()
                effective = date.fromisoformat(str(source["effective_date"]))
                original_start = item["service_start_date"]
                expected_start = (
                    max(effective, date.fromisoformat(str(original_start)))
                    if original_start
                    else effective
                )
                if start != expected_start.isoformat() or end != (item["service_end_date"] or ""):
                    _refuse()
            except (KeyError, ValueError, TypeError, ZeroDivisionError):
                _refuse()

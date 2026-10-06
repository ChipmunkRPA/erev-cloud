"""CLO-5 monitor input queries as compiled SQL (F-CLO fix-forward after the integrated batch on
main 0cb36c14, ci stage: 17 monitor failures and 7 cockpit / gates 500s traced to one statement).

PostgreSQL has no ``min(uuid)``: ``monitors._fx`` picked "the first contract per transaction
currency" with ``min(contract.id)``, and every ``run_monitors`` — hence every cockpit refresh —
failed with ``UndefinedFunction``. The query now takes the minimum of the id's text form, which is a
deterministic representative and needs no new aggregate. CPU-only: the statement is compiled, not
executed."""

from __future__ import annotations

from uuid import UUID

from erev_api.domain.close import monitors
from sqlalchemy.dialects import postgresql

ENTITY = UUID("00000000-0000-4000-8000-0000000000e1")


def _sql() -> str:
    statement = monitors.fx_requirement_query(ENTITY, "USD")
    return str(statement.compile(dialect=postgresql.dialect()))


def test_fx_requirement_query_never_aggregates_a_uuid_directly() -> None:
    sql = _sql()
    assert "min(erev.contract.id)" not in sql
    assert "min(CAST(erev.contract.id AS TEXT))" in sql


def test_fx_requirement_query_keeps_its_scope_and_grouping() -> None:
    sql = _sql()
    assert "erev.contract.contracting_entity_id = " in sql
    assert "erev.contract.status = " in sql
    assert "erev.contract.transaction_currency != " in sql
    assert "GROUP BY erev.contract.transaction_currency" in sql
    assert "ORDER BY erev.contract.transaction_currency" in sql


# --- batch #4 (main c9110467): the duplicate-invoice identity amount is canonical money text ------


def test_canonical_amount_quantizes_to_the_currency_minor_unit() -> None:
    """T-SRC-04 ``total_amount`` is NUMERIC(24, 4); the Q-8 identity tuple and the T-IMP-05 dedupe
    key carry the amount as canonical money text in the currency's minor unit, so the key does not
    change with the column's scale (``1200.0000`` and ``1200.00`` are one amount)."""
    from decimal import Decimal

    assert monitors.canonical_amount(Decimal("1200.0000"), "USD") == Decimal("1200.00")
    assert str(monitors.canonical_amount(Decimal("1200.0000"), "USD")) == "1200.00"
    # Half-up, as erev_engine.money rounds (Codex 0829: money.py uses HALF_UP; stage 10 billing
    # admission requires exact minor units, so an off-minor source amount is only named here):
    # JPY has no minor unit — 1200.5 → 1201, 1201.5 → 1202.
    assert str(monitors.canonical_amount(Decimal("1200.5000"), "JPY")) == "1201"
    assert str(monitors.canonical_amount(Decimal("1201.5000"), "JPY")) == "1202"
    assert str(monitors.canonical_amount(Decimal("12.345000"), "KWD")) == "12.345"
    assert monitors.canonical_amount(None, "USD") is None
    # An unknown currency keeps two places rather than inventing a scale.
    assert str(monitors.canonical_amount(Decimal("7.1000"), "XXX")) == "7.10"

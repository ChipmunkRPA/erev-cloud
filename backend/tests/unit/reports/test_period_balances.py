"""Period balances read from a contract version's trace (ENGINE_SPEC_B S15-R-07a; supervisor
ruling R-16, 2026-09-29; ``erev_api.domain.reports.tie_outs.period_balances``; ENGINE_SPEC CV-21,
CV-50; dev-guide DG-KRN-EXP-01, DG-KRN-EXP-02). No database.

The engine keys a member contract's balance nodes ``<measure>:<contract>@<entity>:<period key>``
with BOTH components CV-21-encoded (``contract_entity_subject_key``). The reader built its lookup
prefix from the raw external id and the raw entity code, found no node for an id holding ``%``
``/`` ``@`` ``#`` or ``:``, and answered the stored ``contract_version_balance`` column — the
version's LATEST period — for every period asked. These witnesses pin the corrected read: the
engine's own key, and a named refusal wherever the trace cannot answer the period.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.domain.reports import tie_outs
from erev_api.problems import Problem
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key, encode_key

VERSION = uuid5(NAMESPACE_URL, "erev://tests/version/period-balances")
CONTRACT = uuid5(NAMESPACE_URL, "erev://tests/contract/period-balances")
ENTITY = uuid5(NAMESPACE_URL, "erev://tests/entity/period-balances")
PERIODS = tuple(f"FY2026-P{month:02d}" for month in range(1, 10))
# 120,000.00 ratable over 2026, no billing: the contract asset at each month end (days / 365)
DAYS = (31, 59, 90, 120, 151, 181, 212, 243, 273)
ASSET = {
    key: f"{Decimal(120000) * days / 365:.2f}" for key, days in zip(PERIODS, DAYS, strict=True)
}
AUGUST, SEPTEMBER = "FY2026-P08", "FY2026-P09"
# one external id per CV-21 delimiter, the formula-trigger pair, and a plain one
EXTERNAL_IDS = ("A", "=A", "'=A", "A:B", "A/B", "A@B", "A#B", "A%B")
# TY-06 admits `:`, `/` and `#` in an entity code
ENTITY_CODES = ("AVM-US", "AVM:US", "AVM/US", "AVM#US")


def _node_values(external_id: str, entity_code: str) -> list[tuple[str, str]]:
    """The contract-asset nodes stage 10 publishes for a member, under the engine's own subject
    key: one per period end."""
    subject = contract_entity_subject_key(external_id, entity_code)
    return [(f"contract_asset:{subject}:{key}", ASSET[key]) for key in PERIODS]


def _stored(**columns: str) -> dict[str, Any]:
    """The version's ``contract_version_balance`` row: the balances at its latest period."""
    row: dict[str, Any] = {f"{measure}_txn": Decimal(0) for measure in tie_outs.BALANCE_MEASURES}
    row["txn_currency"] = "USD"
    row.update({f"{measure}_txn": Decimal(value) for measure, value in columns.items()})
    return row


def _read(
    traced: tie_outs.TracedBalances,
    external_id: str,
    entity_code: str,
    period_key: str,
    stored: dict[str, Any] | None = None,
) -> dict[str, Decimal]:
    return tie_outs.period_balances(
        traced,
        external_id=external_id,
        entity_code=entity_code,
        period_key=period_key,
        stored=_stored(contract_asset=ASSET[SEPTEMBER]) if stored is None else stored,
        version_id=VERSION,
    )


@pytest.mark.parametrize("entity_code", ENTITY_CODES)
@pytest.mark.parametrize("external_id", EXTERNAL_IDS)
def test_an_earlier_period_is_read_from_its_own_node_whatever_the_identifiers_hold(
    external_id: str, entity_code: str
) -> None:
    """Eight ids and four entity codes, identical contracts: August is 79,890.41 and September
    89,753.42 for every one. Fail-first: the raw prefix missed every id or code holding a CV-21
    delimiter and answered the stored September figure for August."""
    traced = tie_outs.traced_balances(_node_values(external_id, entity_code))
    august = _read(traced, external_id, entity_code, AUGUST)
    september = _read(traced, external_id, entity_code, SEPTEMBER)
    assert august["contract_asset"] == Decimal("79890.41")
    assert september["contract_asset"] == Decimal("89753.42")
    assert set(august) == set(tie_outs.BALANCE_MEASURES)
    # a period before the first node: nothing measured yet; after the last: the last node's value
    assert _read(traced, external_id, entity_code, "FY2025-P12")["contract_asset"] == 0
    assert _read(traced, external_id, entity_code, "FY2026-P11")["contract_asset"] == Decimal(
        "89753.42"
    )


def test_the_subject_key_is_the_engines_both_components_encoded() -> None:
    """The reader resolves under ``contract_entity_subject_key`` — the one CV-21 table
    (``KEY_ESCAPES``: ``%`` first, then ``/`` ``@`` ``#`` ``:``) — and under nothing else: nodes
    keyed by the RAW spelling, by an encoded contract with a raw entity code, or by a raw contract
    with an encoded entity code are not this member's."""
    external_id, entity_code = "A%:B/C@D#E", "AVM:US/1#2"
    assert contract_entity_subject_key(external_id, entity_code) == (
        "A%25%3AB%2FC%40D%23E@AVM%3AUS%2F1%232"
    )
    traced = tie_outs.traced_balances(_node_values(external_id, entity_code))
    assert _read(traced, external_id, entity_code, AUGUST)["contract_asset"] == Decimal("79890.41")
    for spelling in (
        f"{external_id}@{entity_code}",
        f"{encode_key(external_id)}@{entity_code}",
        f"{external_id}@{encode_key(entity_code)}",
    ):
        misspelt = tie_outs.traced_balances(
            (f"contract_asset:{spelling}:{key}", ASSET[key]) for key in PERIODS
        )
        with pytest.raises(tie_outs.BalanceUnreadable) as refused:
            _read(misspelt, external_id, entity_code, AUGUST)
        assert refused.value.errors[0].rule_id == tie_outs.RULE_PERIOD_BALANCE, spelling


def test_a_member_whose_subject_carries_no_balance_node_is_refused_by_name() -> None:
    """Fail closed (R-16): the trace holds balance nodes, none under this member's subject key —
    the read names the contract, the entity, the version and the period, and answers nothing from
    the stored latest figure (not even where that figure is 0)."""
    other = tie_outs.traced_balances(_node_values("SF-ORD-10001", "AVM-US"))
    for stored in (_stored(contract_asset="89753.42"), _stored()):
        with pytest.raises(tie_outs.BalanceUnreadable) as refused:
            _read(other, "A:B", "AVM-US", AUGUST, stored)
        problem = refused.value
        assert isinstance(problem, Problem)
        assert (problem.slug, problem.status) == ("validation-failed", 422)
        assert problem.detail == "1 field needs attention."
        (error,) = problem.errors
        assert error.rule_id == "S15-R-07a"
        assert error.field == "balances[A:B@AVM-US]"
        for named in ("Contract A:B", "entity AVM-US", str(VERSION), AUGUST, "A%3AB@AVM-US"):
            assert named in error.message, named
        assert "89753.42" not in error.message  # no figure is offered in place of the balance
    empty = tie_outs.traced_balances(())  # a version without a stored trace
    with pytest.raises(tie_outs.BalanceUnreadable):
        _read(empty, "SF-ORD-10001", "AVM-US", SEPTEMBER)


def test_a_stored_figure_without_period_nodes_answers_its_latest_period_only() -> None:
    """The column fallback, as the documents leave it: a measure the engine does not publish per
    member contract (the current parts; ``accounts_receivable`` outside ENGINE mode) has no period
    node and its stored column is the T-CON-09 default 0 — 0 at every period. A NON-ZERO stored
    figure without period nodes is the version's latest period and answers that period (and later
    ones) only; asked for an earlier period it is refused by name, never answered."""
    traced = tie_outs.traced_balances(_node_values("K-01", "AVM-US"))
    unpublished = ("contract_liability_current", "contract_asset_current", "accounts_receivable")
    august = _read(traced, "K-01", "AVM-US", AUGUST)
    assert [august[measure] for measure in unpublished] == [0, 0, 0]
    # the column as stored: ``erev.money`` at four places; the refusal states the currency's two
    held = _stored(contract_asset=ASSET[SEPTEMBER], refund_liability="250.0000")
    assert _read(traced, "K-01", "AVM-US", SEPTEMBER, held)["refund_liability"] == Decimal("250.00")
    assert _read(traced, "K-01", "AVM-US", "FY2026-P10", held)["refund_liability"] == Decimal(
        "250.00"
    )
    with pytest.raises(tie_outs.BalanceUnreadable) as refused:
        _read(traced, "K-01", "AVM-US", AUGUST, held)
    (error,) = refused.value.errors
    assert error.rule_id == tie_outs.RULE_PERIOD_BALANCE
    for named in (
        "Contract K-01",
        "entity AVM-US",
        "refund_liability 250.00 USD",
        f"latest period {SEPTEMBER}",
        f"earlier period {AUGUST}",
        str(VERSION),
    ):
        assert named in error.message, named
    # with its own period nodes the measure is read like every other
    published = tie_outs.traced_balances(
        [
            *_node_values("K-01", "AVM-US"),
            ("refund_liability:K-01@AVM-US:FY2026-P08", "100.00"),
            ("refund_liability:K-01@AVM-US:FY2026-P09", "250.00"),
        ]
    )
    assert _read(published, "K-01", "AVM-US", AUGUST, held)["refund_liability"] == Decimal("100.00")


def test_group_level_nodes_are_not_a_members_balance() -> None:
    """The presented balances of the unit of account sit under ``<group code>@<entity>`` beside
    the members' (``contract_asset:CG-CON-000004@AVM-US:<period>``; the current parts only there):
    another subject, never read as the member contract's."""
    traced = tie_outs.traced_balances(
        [
            *_node_values("A:B", "AVM-US"),
            *(
                (f"contract_asset_current:CG-CON-000004@AVM-US:{key}", ASSET[key])
                for key in PERIODS
            ),
        ]
    )
    assert set(traced.latest) == {"A%3AB@AVM-US", "CG-CON-000004@AVM-US"}
    assert _read(traced, "A:B", "AVM-US", AUGUST)["contract_asset_current"] == 0


class _Rows:
    """A session stub for ``balances_at``: one statement, the given joined rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def execute(self, statement: Any) -> _Rows:
        return self

    def mappings(self) -> list[dict[str, Any]]:
        return self.rows

    def scalars(self) -> list[Any]:
        return []


def _joined_row(external_id: str, entity_code: str) -> dict[str, Any]:
    """One joined ``contract_version_balance`` row as ``balances_at`` selects it."""
    return {
        **_stored(contract_asset=ASSET[SEPTEMBER]),
        "contract_version_id": VERSION,
        "contract_id": uuid5(NAMESPACE_URL, f"erev://tests/contract/{external_id}"),
        "entity_id": ENTITY,
        "external_id": external_id,
        "customer_id": None,
        "customer_name": None,
        "entity_code": entity_code,
    }


def _balances_at(rows: list[dict[str, Any]], period_key: str) -> tuple[tie_outs.BalanceRow, ...]:
    at = tie_outs.PeriodRef(
        id=uuid5(NAMESPACE_URL, f"erev://tests/period/{period_key}"),
        key=period_key,
        name="Aug 2026",
        fiscal_year=2026,
        period_no=8,
        quarter_no=3,
        start=date(2026, 8, 1),
        end=date(2026, 8, 31),
    )
    return tie_outs.balances_at(
        _Rows(rows),  # type: ignore[arg-type]
        entity_ids=(ENTITY,),
        book_code="ASC606",
        period_keys={ENTITY: at},
        cutoff=datetime(2026, 9, 30, tzinfo=UTC),
    )


def test_balances_at_reads_the_member_under_the_engines_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wiring of ``balances_at``: the joined row's external id and entity code reach the
    engine's subject key, the requested period its node — and a trace keyed otherwise refuses."""
    row = _joined_row("A:B", "AVM/US")
    good = tie_outs.traced_balances(_node_values("A:B", "AVM/US"))
    monkeypatch.setattr(tie_outs, "_balance_nodes", lambda session, version: good)
    (found,) = _balances_at([row], AUGUST)
    assert (found.external_id, found.entity_code, found.version_id) == ("A:B", "AVM/US", VERSION)
    assert found.value("contract_asset") == Decimal("79890.41")
    raw = tie_outs.traced_balances(
        (f"contract_asset:A:B@AVM/US:{key}", ASSET[key]) for key in PERIODS
    )
    monkeypatch.setattr(tie_outs, "_balance_nodes", lambda session, version: raw)
    with pytest.raises(tie_outs.BalanceUnreadable) as refused:
        _balances_at([row], AUGUST)
    assert refused.value.errors[0].rule_id == tie_outs.RULE_PERIOD_BALANCE


def test_balances_at_names_every_unreadable_member_and_serves_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One refusal for the whole read: every member the trace cannot answer is named — contract,
    entity, version, period — beside members that read cleanly, and no row is returned."""
    traced = tie_outs.traced_balances(
        [
            *_node_values("A", "AVM-US"),
            *((f"contract_asset:A:B@AVM-US:{key}", ASSET[key]) for key in PERIODS),  # raw
            *((f"contract_asset:A/B@AVM-US:{key}", ASSET[key]) for key in PERIODS),  # raw
        ]
    )
    monkeypatch.setattr(tie_outs, "_balance_nodes", lambda session, version: traced)
    rows = [_joined_row(external_id, "AVM-US") for external_id in ("A", "A/B", "A:B")]
    with pytest.raises(tie_outs.BalanceUnreadable) as refused:
        _balances_at(rows, AUGUST)
    problem = refused.value
    assert (problem.slug, problem.status) == ("validation-failed", 422)
    assert problem.detail == "2 fields need attention."
    assert [error.field for error in problem.errors] == [
        "balances[A/B@AVM-US]",
        "balances[A:B@AVM-US]",
    ]
    for error, (external_id, subject) in zip(
        problem.errors, (("A/B", "A%2FB@AVM-US"), ("A:B", "A%3AB@AVM-US")), strict=True
    ):
        assert error.rule_id == "S15-R-07a"
        for named in (f"Contract {external_id}", "entity AVM-US", str(VERSION), AUGUST, subject):
            assert named in error.message, named
    (clean,) = _balances_at(rows[:1], AUGUST)  # the readable member alone is served
    assert clean.value("contract_asset") == Decimal("79890.41")

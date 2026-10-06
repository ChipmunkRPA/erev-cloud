"""Who is named the contracts of a not-stated role (04 T-CLS-06 "Role basis" and §16.8 rev 1.253;
the supervisor's ruling of 2026-10-01 21:23, point 4), without a database.

``totals`` is stored once for every reader and names each contract a not-stated role concerns, and
``contract`` is RLS-TE on the contracting entity. The read names the contracts its reader reads and
counts all of them; the one statement that decides "reads" runs under the reader's own session and
asks the ``contract`` table for the named ids — row-level security is the filter, not a list the
application keeps. As the engine stands every contract named is its reader's (a contract's balances
are held with its own contracting entity; 04 T-CLS-06 "Role basis", the correction of rev 1.259):
the pins state what the read does where the table's key allows the other case.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_api.domain.close import reconciliations
from sqlalchemy.dialects import postgresql

FIRST = "01a0fa9d-ea4d-73d2-ac24-26b28d4f7001"
SECOND = "01a0fa9d-ea4d-73d2-ac24-26b28d4f7002"
REASON = "2 contract(s) in another currency than USD hold no USD balance at FY2026-P08."
# The statement that decides which named contracts a reader reads, as PostgreSQL receives it.
SELECTED = "SELECT erev.contract.id FROM erev.contract WHERE erev.contract.id IN ({ids})"


def _row(not_stated: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "account_code": "1105",
        "account_role": "UNBILLED_RECEIVABLE",
        "account_codes": ["1105"],
        "currency": "USD",
        "subledger_amount": None if not_stated else "11200.00",
        "source_amount": "11050.00",
        "difference": None if not_stated else "-150.00",
        "not_stated": not_stated,
    }


NAMED = [
    {"id": FIRST, "external_id": "SF-ORD-EU-3001"},
    {"id": SECOND, "external_id": "SF-ORD-DE-0007"},
]


def test_a_not_stated_row_names_the_contracts_its_reader_reads_and_counts_all_of_them() -> None:
    stored = _row({"reason": REASON, "contracts": NAMED})

    def shown(readable: frozenset[str]) -> Any:
        return reconciliations._total_out(stored, readable)["not_stated"]

    # a reader of every entity is named both
    assert shown(frozenset({FIRST, SECOND})) == {
        "reason": REASON,
        "contracts": NAMED,
        "contract_count": 2,
    }
    # a reader of the reconciliation's entity alone: one is hers to read, two are counted
    assert shown(frozenset({FIRST})) == {
        "reason": REASON,
        "contracts": NAMED[:1],
        "contract_count": 2,
    }
    # a reader who reads neither is still told how many there are
    assert shown(frozenset()) == {"reason": REASON, "contracts": [], "contract_count": 2}
    # the stored row is not changed by a read
    assert stored["not_stated"] == {"reason": REASON, "contracts": NAMED}


def test_a_reason_without_contracts_counts_none_and_a_stated_row_has_no_member() -> None:
    shared = _row({"reason": "Account(s) 1105 carry CONTRACT_ASSET and UNBILLED_RECEIVABLE."})
    assert reconciliations._total_out(shared, frozenset())["not_stated"] == {
        "reason": "Account(s) 1105 carry CONTRACT_ASSET and UNBILLED_RECEIVABLE.",
        "contracts": [],
        "contract_count": 0,
    }
    stated = reconciliations._total_out(_row(None), frozenset({FIRST}))
    assert stated["not_stated"] is None
    assert stated["difference"].model_dump() == {"amount": "-150.00", "currency": "USD"}
    # a billing row stores no role members at all
    billing = {"account_code": None, "currency": "USD", "difference": "0.00"}
    assert reconciliations._total_out(billing, frozenset())["not_stated"] is None


def test_the_reader_reads_a_contract_when_her_own_session_returns_it() -> None:
    """``_readable_contracts``: one statement over ``contract`` by the named ids, executed on the
    session it is given — the reader's — so row-level security decides; no statement when no row
    names a contract."""
    statements: list[Any] = []

    class _Session:
        def execute(self, statement: Any) -> Any:
            statements.append(statement)

            class _Found:
                def scalars(self) -> list[UUID]:
                    return [UUID(FIRST)]

            return _Found()

    session: Any = _Session()
    rows = [
        {"totals": [_row({"reason": REASON, "contracts": NAMED}), _row(None)]},
        {"totals": {}},  # the column's default before a comparison
        {"totals": [_row({"reason": REASON, "contracts": NAMED[:1]})]},
    ]
    assert reconciliations._readable_contracts(session, rows) == frozenset({FIRST})
    (statement,) = statements
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    listed = ", ".join(f"'{value}'" for value in (FIRST, SECOND))
    assert " ".join(str(compiled).split()) == SELECTED.format(ids=listed)
    assert reconciliations._readable_contracts(session, [{"totals": [_row(None)]}]) == frozenset()
    assert len(statements) == 1

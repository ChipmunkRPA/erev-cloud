"""The order of the contract history along a contract's chain (item RPT-FORMER-GROUP-READERS-1;
supervisor ruling R-117 (a); ``contract_history.in_chain_order``; 04 T-CON-04, §17.1 rule 1;
SCREENS_B RPT-09, RPT-10).

``version_no`` counts the versions of one combination group. Two orders of one customer, each
computed in its own group and then combined (PRD WLD-K-09 ``SF-ORD-10417`` and ``SF-ORD-10418``),
each hold a version 1 twice: the history's statement, ordered by the stored number, lists the
version of the own group and the version of the combined group side by side, line by line. The
rows carry the number along the chain and are ordered by it.
"""

from __future__ import annotations

from typing import Any

from erev_api.domain.reports.builders.contract_history import in_chain_order

FIRST, SECOND, NEVER_COMBINED = "SF-ORD-10417", "SF-ORD-10418", "SF-ORD-10300"


def row(contract: str, *, stored: int, chain: int, line: int, key: str) -> dict[str, Any]:
    return {
        "contract_external_id": contract,
        "version_no": stored,
        "chain_version_no": chain,
        "line_sequence": line,
        "obligation_key": key,
    }


def placed(rows: list[dict[str, Any]]) -> list[tuple[str, int, str]]:
    return [
        (item["contract_external_id"], item["chain_version_no"], item["obligation_key"])
        for item in in_chain_order(rows)
    ]


def test_the_versions_of_two_groups_follow_the_chain() -> None:
    """The statement's order for a contract of two lines — own group versions 1 and 2, then the
    combined group's version 1 — is by the stored number: 1 (own), 1 (combined), 2 (own), each
    pair line by line. Along the chain the combined group's version is the third."""
    statement_order = [
        row(FIRST, stored=1, chain=1, line=1, key="O1"),
        row(FIRST, stored=1, chain=3, line=1, key="O1"),
        row(FIRST, stored=1, chain=1, line=2, key="O2"),
        row(FIRST, stored=1, chain=3, line=2, key="O2"),
        row(FIRST, stored=2, chain=2, line=1, key="O1"),
        row(FIRST, stored=2, chain=2, line=2, key="O2"),
    ]
    assert placed(statement_order) == [
        (FIRST, 1, "O1"),
        (FIRST, 1, "O2"),
        (FIRST, 2, "O1"),
        (FIRST, 2, "O2"),
        (FIRST, 3, "O1"),
        (FIRST, 3, "O2"),
    ]


def test_a_contract_that_never_changed_its_group_keeps_its_rows_in_place() -> None:
    """The number along the chain is the stored number, and the order is the statement's — the
    obligations that share a line included (the database's collation orders their keys)."""
    statement_order = [
        row(NEVER_COMBINED, stored=1, chain=1, line=1, key="O1"),
        row(NEVER_COMBINED, stored=1, chain=1, line=2, key="o2-b"),
        row(NEVER_COMBINED, stored=1, chain=1, line=2, key="O2-A"),
        row(NEVER_COMBINED, stored=2, chain=2, line=1, key="O1"),
    ]
    assert in_chain_order(list(statement_order)) == statement_order


def test_the_contracts_stay_in_the_statements_order() -> None:
    """The statement orders the contracts by the database's collation; the rows of a contract are
    re-ordered among themselves only."""
    statement_order = [
        row(SECOND, stored=1, chain=1, line=1, key="O1"),
        row(SECOND, stored=1, chain=2, line=1, key="O1"),
        row(NEVER_COMBINED, stored=1, chain=1, line=1, key="O1"),
        row(FIRST, stored=1, chain=2, line=1, key="O1"),
        row(FIRST, stored=1, chain=1, line=1, key="O1"),
    ]
    assert placed(statement_order) == [
        (SECOND, 1, "O1"),
        (SECOND, 2, "O1"),
        (NEVER_COMBINED, 1, "O1"),
        (FIRST, 1, "O1"),
        (FIRST, 2, "O1"),
    ]

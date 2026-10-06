"""04 NC-20 and §1.4 "Index conditions under a policy" (rev 1.181; dev-guide DG-KRN-DB-10;
supervisor ruling R-116; item PERF-RLS-INDEX-1): no index of a table with a row-level-security
policy has a key the policy cannot use, unless ``erev_api.db.index_conditions.ALLOWED`` names it
with its reason.

The check reads the catalogue of the migrated schema, so it fails on the revision that adds such
an index — for a status, a kind, an amount, a member of a ``jsonb`` column — and not at volume,
where the index would have been entered by its tenant alone. The probe test builds each kind of
key in an owner transaction that is rolled back.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from erev_api.db import index_conditions
from erev_api.db.index_conditions import ALLOWED, IndexFinding, findings, reason
from erev_api.db.lint import catalogue_connection
from sqlalchemy import Connection
from support.db import TestDatabase

pytestmark = pytest.mark.pg

PROBE = "index_conditions_probe"


@pytest.fixture
def owner_transaction(test_database: TestDatabase) -> Iterator[Connection]:
    """An owner transaction that always rolls back, so probe objects never persist."""
    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            yield connection
        finally:
            connection.rollback()


def test_nc_20_every_index_of_a_table_with_a_policy_can_be_used_under_it(
    test_database: TestDatabase,
) -> None:
    """The migrated schema, read as ``erev_app``: every index key is one the policy can use or
    is listed with its reason, and no entry of the list has lost its index or its finding."""
    with catalogue_connection(request_id="tests-index-conditions") as connection:
        assert [str(finding) for finding in findings(connection)] == []
    assert all(reason.strip() for reason in ALLOWED.values())


def test_nc_20_the_check_names_each_kind_of_key(owner_transaction: Connection) -> None:
    """A table with a policy and one index of each kind: the check names the four the policy
    cannot use and passes the three it can."""
    before = findings(owner_transaction)
    for statement in (
        f"CREATE TABLE erev.{PROBE} (tenant_id uuid NOT NULL, id uuid NOT NULL, "
        "state erev.job_state NOT NULL, created_at timestamptz NOT NULL, amount numeric, "
        "detail jsonb, note text, PRIMARY KEY (tenant_id, id))",
        f"ALTER TABLE erev.{PROBE} ENABLE ROW LEVEL SECURITY",
        # the enumeration directly behind the tenant: entered by the tenant alone
        f"CREATE INDEX ix_{PROBE}__state ON erev.{PROBE} (tenant_id, state)",
        # a column the policy could use, behind one it cannot
        f"CREATE INDEX ix_{PROBE}__state_created ON erev.{PROBE} "
        "(tenant_id, id, state, created_at)",
        f"CREATE INDEX ix_{PROBE}__note ON erev.{PROBE} (tenant_id, lower(note))",
        f"CREATE INDEX ix_{PROBE}__detail ON erev.{PROBE} USING gin (detail)",
        # the three the policy can use: the enumeration and the amount last, behind a selective
        # column; and the status as the predicate of a partial index
        f"CREATE INDEX ix_{PROBE}__created_state ON erev.{PROBE} (tenant_id, created_at, state)",
        f"CREATE INDEX ix_{PROBE}__id_amount ON erev.{PROBE} (tenant_id, id, amount)",
        f"CREATE INDEX ix_{PROBE}__queued ON erev.{PROBE} (tenant_id, created_at) "
        "WHERE state = 'QUEUED'",
    ):
        owner_transaction.exec_driver_sql(statement)
    found = {
        finding.index: finding.message
        for finding in findings(owner_transaction)
        if finding not in before
    }
    assert sorted(found) == [
        f"ix_{PROBE}__detail",
        f"ix_{PROBE}__note",
        f"ix_{PROBE}__state",
        f"ix_{PROBE}__state_created",
    ]
    assert found[f"ix_{PROBE}__detail"].startswith("access method gin")
    assert found[f"ix_{PROBE}__note"].startswith("an expression in the key")
    assert found[f"ix_{PROBE}__state"].startswith("nothing but the tenant stands in front of state")
    assert found[f"ix_{PROBE}__state_created"].startswith("created_at stands behind state")


def test_nc_20_a_listed_index_without_a_finding_is_a_finding(
    owner_transaction: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list cannot outlive its reasons: an entry whose index was dropped, or whose key was
    put right, fails by name."""
    monkeypatch.setattr(
        index_conditions, "ALLOWED", {**ALLOWED, "ix_no_such_index__status": "left behind"}
    )
    assert findings(owner_transaction) == [
        IndexFinding(
            "-",
            "ix_no_such_index__status",
            "listed in ALLOWED, but its key has no finding: remove the entry",
        )
    ]


@pytest.mark.parametrize(
    ("columns", "leakproof", "expected"),
    [
        (["tenant_id", "idempotency_key", "book_code"], [True, True, False], None),
        (
            ["tenant_id", "external_id", "source_system", "object_type"],
            [True, True, False, False],
            None,
        ),
        (["tenant_id", "created_at"], [True, True], None),
        (
            ["tenant_id", "book_code", "idempotency_key"],
            [True, False, True],
            "idempotency_key stands",
        ),
        (["tenant_id", "status"], [True, False], "nothing but the tenant"),
        (["status", "created_at"], [False, True], "created_at stands behind status"),
        (["tenant_id", None], [True, False], "an expression in the key"),
    ],
)
def test_nc_20_the_reason_of_a_key(
    columns: list[str | None], leakproof: list[bool], expected: str | None
) -> None:
    found = reason("btree", columns, leakproof)
    assert (found is None) if expected is None else (found or "").startswith(expected), found
    assert (reason("gin", columns, leakproof) or "").startswith("access method gin")

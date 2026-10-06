"""05 §2.7 index conditions under the policy as ``erev doctor`` reads them on a deployment (SAR-40
``index-conditions``, rev 1.156; 04 NC-20; dev-guide DG-KRN-DB-10).

``test_index_conditions.py`` holds the migrated schema to the catalogue check. This module holds
the doctor's collector and predicate to a real catalogue: read as ``erev_app`` on the doctor's own
connection, the schema the revisions build has no finding; an index built by hand on a table with
a policy and an index of the list that the schema no longer has are each named as a warning, and
the check stays ok. The probes run in an owner transaction that is rolled back.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from erev_api.controls.doctor import (
    INDEX_CONDITIONS,
    IndexConditionsObservation,
    index_conditions,
    observe_index_conditions,
)
from erev_api.db.index_conditions import ALLOWED
from erev_api.db.lint import catalogue_connection
from sqlalchemy import Connection
from support.db import TestDatabase

pytestmark = pytest.mark.pg

# An index no revision builds: an enumeration directly behind the tenant (04 NC-20).
BY_HAND = "ix_tenant_membership__doctor_probe"
# An index the list names with its reason; a schema without it is not the tested one.
LISTED = "ix_contract__status"


@pytest.fixture
def owner_transaction(test_database: TestDatabase) -> Iterator[Connection]:
    """An owner transaction that always rolls back, so the probes never persist."""
    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            yield connection
        finally:
            connection.rollback()


def test_sar_40_the_doctor_reads_no_index_finding_on_the_migrated_schema(
    test_database: TestDatabase,
) -> None:
    """The doctor's own path: the catalogue connection as ``erev_app`` (no tenant context). The
    schema the revisions build passes, and the line counts the list as it stands."""
    with catalogue_connection(request_id="tests-doctor-index-conditions") as connection:
        observed = observe_index_conditions(connection)
    assert observed == IndexConditionsObservation(findings=(), listed=len(ALLOWED))
    assert index_conditions(observed).lines() == [
        f"OK {INDEX_CONDITIONS}: every index of a table with a row-level-security policy has a "
        f"key the policy can use, or is one of the {len(ALLOWED)} listed with a reason (05 §2.7)"
    ]


def test_sar_40_the_doctor_warns_of_an_index_built_or_dropped_by_hand(
    owner_transaction: Connection,
) -> None:
    """A schema that is not the tested one: one index more, whose key the policy cannot use, and
    one index of the list less. The doctor names both in the catalogue check's words, as
    warnings: the check stays ok and the command's exit code 0."""
    assert LISTED in ALLOWED and BY_HAND not in ALLOWED
    owner_transaction.exec_driver_sql(
        f"CREATE INDEX {BY_HAND} ON erev.tenant_membership (tenant_id, status)"
    )
    owner_transaction.exec_driver_sql(f"DROP INDEX erev.{LISTED}")
    result = index_conditions(observe_index_conditions(owner_transaction))
    assert result.ok and result.failures == ()
    assert result.lines() == [
        f"WARN {INDEX_CONDITIONS}: -.{LISTED}: listed in ALLOWED, but its key has no finding: "
        "remove the entry",
        f"WARN {INDEX_CONDITIONS}: tenant_membership.{BY_HAND}: nothing but the tenant stands in "
        "front of status, whose comparison is not leakproof: the index is entered by the tenant "
        "alone",
    ]

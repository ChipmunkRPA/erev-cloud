"""Data-model drift DG-ARC-09, pg part: ``pg_enum`` labels in both directions (dev-guide §6.8;
04 §3; FND-7). Slice 1b: a database-candidate mirror without a type is a finding unless
``RECONCILED_ENUM_TYPES`` names it (D-98 66)."""

from __future__ import annotations

import enum
from collections.abc import Mapping

import pytest
from erev_api.db import migration_ops as ops
from erev_api.db.session import identity_session
from sqlalchemy import Connection, text
from support.db import TestDatabase
from support.enum_mirrors import RECONCILED_ENUM_TYPES, database_enums

pytestmark = pytest.mark.pg

_ENUM_TYPES = text(
    "SELECT t.typname, array_agg(e.enumlabel::text ORDER BY e.enumsortorder) "
    "FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
    "JOIN pg_enum e ON e.enumtypid = t.oid "
    "WHERE n.nspname = 'erev' AND t.typtype = 'e' GROUP BY t.typname ORDER BY t.typname"
)


def enum_drift(
    connection: Connection, classes: Mapping[str, type[enum.StrEnum]] | None = None
) -> list[str]:
    """Both directions of DG-ARC-09 (slice 1b, Codex 0515): every ``erev.*`` enum type needs a
    StrEnum mirror with the same labels, and every database-candidate StrEnum needs a PostgreSQL
    type unless ``RECONCILED_ENUM_TYPES`` names it (D-98 66: pending, text + CHECK or
    value-only)."""
    mirrors = database_enums() if classes is None else classes
    findings: list[str] = []
    present: set[str] = set()
    for type_name, labels in connection.execute(_ENUM_TYPES):
        present.add(str(type_name))
        mirror = mirrors.get(type_name)
        if mirror is None:
            findings.append(f"erev.{type_name}: no StrEnum mirror")
        elif list(labels) != [member.value for member in mirror]:
            findings.append(f"erev.{type_name}: labels differ from {mirror.__name__}")
    for type_name, mirror in sorted(mirrors.items()):
        if type_name not in present and type_name not in RECONCILED_ENUM_TYPES:
            findings.append(f"erev.{type_name}: no PostgreSQL enum type for {mirror.__name__}")
    return findings


class ProbeKind(enum.StrEnum):
    ALPHA = "ALPHA"
    BETA = "BETA"


def test_dg_arc_09_pg_enum_labels_equal_python(test_database: TestDatabase) -> None:
    # E-01 to E-131 less withdrawn and API-only (E-131 `ssp_quantity_unit`, ENG-C1b)
    assert len(database_enums()) == 131 - 2 - 14
    with identity_session(request_id="tests-enum-drift") as session:
        assert enum_drift(session.connection()) == []

    # The comparison reports a missing mirror and an appended label (rolled back).
    with test_database.owner_engine.connect() as connection, ops.bound_to(connection):
        connection.begin()
        try:
            ops.create_enum("probe_kind", [member.value for member in ProbeKind])
            probes = {**database_enums(), "probe_kind": ProbeKind}
            assert enum_drift(connection, probes) == []
            assert enum_drift(connection) == ["erev.probe_kind: no StrEnum mirror"]
            ops.add_enum_value("probe_kind", "GAMMA")
            assert enum_drift(connection, probes) == [
                "erev.probe_kind: labels differ from ProbeKind"
            ]
            # The reverse direction (slice 1b): a database-candidate mirror without a type is a
            # finding unless RECONCILED_ENUM_TYPES names it; the reconciled names are not types.
            assert enum_drift(connection, {**probes, "missing_probe": ProbeKind}) == [
                "erev.probe_kind: labels differ from ProbeKind",
                "erev.missing_probe: no PostgreSQL enum type for ProbeKind",
            ]
            assert not set(RECONCILED_ENUM_TYPES) & {
                row[0] for row in connection.execute(_ENUM_TYPES)
            }
        finally:
            connection.rollback()

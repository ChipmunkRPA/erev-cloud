"""Item FILE-SHRED-DURABLE-ORDER-1 — revision 0120 gives ``file_object`` the instant its shred
was completed (04 rev 1.237 T-PLT-29; 05 PRV-07 b rev 1.171; DG-ARC-07; DG-MIG-04 / DG-MIG-12
literals). CPU-only: the revision's two literals are compared with the renderer and with the
installing revision 0011, and its statements with what the document names; the database proofs
are ``tests/pg/test_transitions_drift.py``, ``tests/pg/test_immutability_and_grants.py``,
``tests/pg/test_index_conditions.py`` and the walk of ``tests/pg/test_migrations.py``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final

from erev_api.db import migration_ops
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql

VERSIONS: Final = Path(__file__).resolve().parents[3] / "backend/erev_api/db/migrations/versions"
COLUMN: Final = "shred_completed_at"


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0120_re_renders_the_file_object_transition() -> None:
    """The function the revision installs is the fresh rendering (DG-ARC-07) and the one it
    restores on the way down is the 0011 literal, verbatim (DG-MIG-04). Between the two nothing
    differs but the new column: one member more in the allow-list and its write-once block."""
    revision = _load("0120_file_shred_completed")
    # the number is the register's; the parent is not pinned here — the chain follows merge
    # order and a revision's parent moves at every merge (supervisor rulings R-68 (e), R-117 (h))
    assert revision.revision == "0120"
    assert revision.BODY == transition_trigger_sql("file_object")
    assert revision.PREVIOUS == _load("0011_files").FILE_OBJECT_TRANSITION_BODY
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS

    old, new = revision.PREVIOUS.splitlines(), revision.BODY.splitlines()
    added = [line for line in new if line not in old]
    removed = [line for line in old if line not in new]
    # The allow-list line is replaced by one that names the column too ...
    [was] = removed
    assert f"'{COLUMN}', " not in was and "ARRAY['legal_hold', 'retention_until'" in was
    listed = [line for line in added if "ARRAY[" in line]
    assert [line.replace(f"'{COLUMN}', ", "") for line in listed] == [was]
    # ... and the column's own block refuses a second value, as each shred column's block does.
    block = [line for line in added if "ARRAY[" not in line]
    assert block == [
        f"  IF OLD.{COLUMN} IS NOT NULL AND NEW.{COLUMN} IS DISTINCT FROM OLD.{COLUMN} THEN",
        f"      MESSAGE = format('EREV-TRN-001: {COLUMN} of %I.%I is already set',",
    ]
    assert len(new) - len(old) == 5  # the IF, the two lines of RAISE, the format's second, END IF

    spec = TRANSITIONS["file_object"]
    assert spec.status_column is None and spec.pairs == frozenset()
    assert spec.updatable_columns - spec.set_once == {"legal_hold", "retention_until"}
    assert spec.set_once == {
        COLUMN,
        "shred_reason",
        "shredded_at",
        "shredded_by",
        "shredded_by_kind",
    }


def test_0120_names_what_04_names() -> None:
    """T-PLT-29 rev 1.237: the column, its check — only a marked row carries a completion — the
    partial index the sweep reads, entered by the tenant and the instant of the decision (04
    NC-20: both keys bound a scan under the policy), and the application role's column grant."""
    revision = _load("0120_file_shred_completed")
    assert (revision.TABLE, revision.COLUMN) == ("file_object", COLUMN)
    assert revision.CHECK == "ck_file_object__shred_completed"
    assert revision.INDEX == "ix_file_object__shred_incomplete"
    assert revision.INDEX_COLUMNS == ("tenant_id", "shredded_at")
    assert revision.INCOMPLETE == f"shredded_at IS NOT NULL AND {COLUMN} IS NULL"
    assert revision.APP_ROLE == "erev_app"
    document = (VERSIONS.parents[4] / "docs" / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    assert f"`{revision.CHECK} CHECK ({COLUMN} IS NULL OR shredded_at IS NOT NULL)`" in document
    assert (
        f"`{revision.INDEX} ({', '.join(revision.INDEX_COLUMNS)}) WHERE {revision.INCOMPLETE}`"
        in document
    )


def test_0120_downgrade_removes_what_upgrade_created_in_reverse_order() -> None:
    """DG-MIG-04 on CPU (``migration_ops.recording``, the helper's sink without a database): the
    five statements of ``upgrade()`` — the column, its check, the column grant, the partial
    index, the function — and the five of ``downgrade()``, which undo them one by one in reverse
    order and restore the 0011 function. The database walk is
    ``tests/pg/test_migrations.py::test_upgrade_downgrade_upgrade``."""
    revision = _load("0120_file_shred_completed")
    with migration_ops.recording() as up:
        revision.upgrade()
    with migration_ops.recording() as down:
        revision.downgrade()
    function = (
        "CREATE OR REPLACE FUNCTION erev.tg_file_object__transition() RETURNS trigger "
        "LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn$"
    )
    assert up == [
        f"ALTER TABLE erev.file_object ADD COLUMN {COLUMN} timestamptz NULL",
        "ALTER TABLE erev.file_object ADD CONSTRAINT ck_file_object__shred_completed "
        f"CHECK ({COLUMN} IS NULL OR shredded_at IS NOT NULL)",
        f"GRANT UPDATE ({COLUMN}) ON TABLE erev.file_object TO erev_app",
        "CREATE INDEX ix_file_object__shred_incomplete ON erev.file_object "
        f"(tenant_id, shredded_at) WHERE shredded_at IS NOT NULL AND {COLUMN} IS NULL",
        f"{function}{revision.BODY}$fn$",
    ]
    assert down == [
        f"{function}{revision.PREVIOUS}$fn$",
        "DROP INDEX erev.ix_file_object__shred_incomplete",
        f"REVOKE UPDATE ({COLUMN}) ON TABLE erev.file_object FROM erev_app",
        "ALTER TABLE erev.file_object DROP CONSTRAINT ck_file_object__shred_completed",
        f"ALTER TABLE erev.file_object DROP COLUMN {COLUMN}",
    ]

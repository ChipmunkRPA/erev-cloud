"""Global catalogue T-PLT-31 ``registry_parameter`` (04 §14.2; DG-MIG-07; BUILD_SPEC FND-8)."""

from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest
from alembic import command
from erev_api.db.session import identity_session
from erev_api.db.tables.platform import registry_parameter_correction
from erev_api.enums import RegistryScope
from erev_api.registry import platform as platform_catalogue
from erev_api.registry.effective import EFFECTIVE_REGISTRY_PARAMETER
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import POLICY_PARAMETERS
from sqlalchemy import Connection, exc, insert, select, text
from support.db import TestDatabase, alembic_config, fresh_head

pytestmark = pytest.mark.pg

SELECT_ROWS = (
    "SELECT code, pol_id, category::text AS category, value_schema, default_asc606, "
    "default_ifrs15, is_forced_asc606, is_forced_ifrs15, legacy_parity_value, "
    "allowed_levels::text[] AS allowed_levels, pin, approval_code, description, source_ref, "
    "section FROM erev.registry_parameter ORDER BY code"
)


def _sqlstate(connection: Connection, statement: str) -> str | None:
    savepoint = connection.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        connection.exec_driver_sql(statement)
    savepoint.rollback()
    return getattr(excinfo.value.orig, "sqlstate", None)


def test_registry_parameter_seeded(test_database: TestDatabase) -> None:
    specs = {**POLICY_PARAMETERS, **PLATFORM_PARAMETERS}
    with identity_session(request_id="tests-registry-parameter") as session:
        connection = session.connection()
        rows = [dict(row) for row in connection.execute(text(SELECT_ROWS)).mappings()]
        assert len(rows) == len(POLICY_PARAMETERS) + len(PLATFORM_PARAMETERS)
        # 131 POL rows of POLICIES §1 and §5.0 + 24 platform parameters (T-PLT-31; the 24th is
        # platform.snapshot_retention_families, F-SNP 0063 / 0003).
        assert len(rows) == 155
        pol_ids = [row["pol_id"] for row in rows if row["pol_id"] is not None]
        assert len(pol_ids) == len(set(pol_ids)) == len(POLICY_PARAMETERS)
        for row in rows:
            spec = specs[row["code"]]
            assert row == {
                "code": spec.code,
                "pol_id": spec.pol_id,
                "category": spec.category.value,
                "value_schema": spec.value_schema,
                "default_asc606": spec.default_asc606,
                "default_ifrs15": spec.default_ifrs15,
                "is_forced_asc606": spec.is_forced_asc606,
                "is_forced_ifrs15": spec.is_forced_ifrs15,
                "legacy_parity_value": spec.legacy_parity_value,
                "allowed_levels": [s.value for s in RegistryScope if s in spec.allowed_levels],
                "pin": spec.pin,
                "approval_code": spec.approval_code,
                "description": spec.description,
                "source_ref": spec.source_ref,
                "section": spec.section,
            }, spec.code
        batch = connection.execute(
            text(
                "SELECT count(*) FROM erev.registry_parameter "
                "WHERE pol_id BETWEEN 'POL-210' AND 'POL-214' AND allowed_levels = '{}'"
            )
        ).scalar_one()
        assert batch == 5
        index = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'erev' "
                "AND indexname = 'ux_registry_parameter__pol_id'"
            )
        ).scalar_one()
        assert index.startswith("CREATE UNIQUE INDEX") and "WHERE (pol_id IS NOT NULL)" in index
        privileges = {
            privilege: connection.execute(
                text("SELECT has_table_privilege('erev_app', 'erev.registry_parameter', :p)"),
                {"p": privilege},
            ).scalar_one()
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
        }
        assert privileges == {
            "SELECT": True,
            "INSERT": False,
            "UPDATE": False,
            "DELETE": False,
            "TRUNCATE": False,
        }
        update = "UPDATE erev.registry_parameter SET pin = 'K' WHERE code = 'billing.posting'"
        assert _sqlstate(connection, update) == "42501"


RETENTION = "platform.snapshot_retention_families"
UPDATE_CORRECTION = (
    "UPDATE erev.registry_parameter_correction SET section = 'x' WHERE correction_no = 1"
)
DELETE_CORRECTION = "DELETE FROM erev.registry_parameter_correction WHERE correction_no = 1"
SELECT_CORRECTIONS = (
    "SELECT code, correction_no, value_schema, description, source_ref, section, "
    "applied_by_revision, created_by_kind FROM erev.registry_parameter_correction "
    "ORDER BY code, correction_no"
)


def _effective(connection: Connection) -> dict[str, dict[str, object]]:
    rows = connection.execute(select(EFFECTIVE_REGISTRY_PARAMETER)).mappings().all()
    by_code = {str(row["code"]): dict(row) for row in rows}
    assert len(rows) == len(by_code), "one effective row per code"
    return by_code


def test_effective_relation_agrees_with_the_catalogue_and_the_seed_is_intact(
    test_database: TestDatabase,
) -> None:
    """04 rev 1.59 T-PLT-31 rule 3 on a fresh database (written in lane F-SNP; NOT RUN on the lane —
    databases Ray-side): 0066 appended exactly one correction (the retention parameter's schema that
    admits {}), the effective relation advertises the Python catalogue for every code, and the
    seeded rows are untouched (storage assertions kept apart from effective-view agreement)."""
    specs = {**POLICY_PARAMETERS, **PLATFORM_PARAMETERS}
    with identity_session(request_id="tests-registry-parameter-effective") as session:
        connection = session.connection()
        corrections = [dict(r) for r in connection.execute(text(SELECT_CORRECTIONS)).mappings()]
        assert [(c["code"], c["correction_no"], c["applied_by_revision"]) for c in corrections] == [
            (RETENTION, 1, "0066")
        ]
        assert corrections[0]["value_schema"] == PLATFORM_PARAMETERS[RETENTION].value_schema
        assert corrections[0]["created_by_kind"] == "SYSTEM"
        effective = _effective(connection)
        assert set(effective) == set(specs) and len(effective) == 155
        for code, row in effective.items():
            spec = specs[code]
            assert row["value_schema"] == spec.value_schema, code
            assert row["description"] == spec.description, code
            assert row["source_ref"] == spec.source_ref, code
            assert row["section"] == spec.section, code
            assert row["pin"] == spec.pin and row["approval_code"] == spec.approval_code, code
        # storage: the seeded rows are the fresh rendering too (0003 / 0063 seed from the catalogue)
        seeded = {r["code"]: dict(r) for r in connection.execute(text(SELECT_ROWS)).mappings()}
        assert len(seeded) == 155
        assert seeded[RETENTION]["value_schema"] == PLATFORM_PARAMETERS[RETENTION].value_schema
        # erev_app holds SELECT only on the global-reference table (04 §14.2): permission denial
        # (42501) precedes any trigger, as for the seed table above (Codex 0515)
        assert _sqlstate(connection, UPDATE_CORRECTION) == "42501"
        assert _sqlstate(connection, DELETE_CORRECTION) == "42501"
    # DB-01: the append-only trigger refuses the privileged owner too (P0001), in a savepoint that
    # rolls back — the seeded catalogue and correction 1 are unchanged afterwards
    with test_database.owner_engine.begin() as owner:
        assert _sqlstate(owner, UPDATE_CORRECTION) == "P0001"
        assert _sqlstate(owner, DELETE_CORRECTION) == "P0001"
        assert (
            owner.execute(
                text("SELECT count(*) FROM erev.registry_parameter_correction")
            ).scalar_one()
            == 1
        )


def _downgrade_to_base_or_skip() -> None:
    """The old-seed walk's first leg. 0067's downgrade is REFUSED BY NAME over OPENING_BALANCES
    batches without a cutover (``EREV-MIG-0067``; D-98 128 and its amendment 1) — a legitimate
    state of a populated shared database, so the walk needs an unpopulated one and skips by that
    name (option (i) of the amendment). Alembic commits one transaction per revision: the refused
    revision's own DDL is rolled back, but any DESCENDANT of 0067 already downgraded stays
    downgraded (Codex production-20260921-1727 §4 bound), so the database is brought back to head
    — the upgrade direction is safe by construction — before the skip; a skip is not an old-seed
    success. Any other failure of the downgrade propagates — a raw CheckViolation included: that is
    the RLS-blind guard's defect (F-LMG), never tolerated here."""
    fresh_head()  # FLMG-WALK-RESET-1: the walk descends from a data-free head (DG-MIG-05 / -06)
    try:
        command.downgrade(alembic_config(), "base")
    except exc.DBAPIError as error:
        message = str(error.orig).splitlines()[0] if error.orig is not None else str(error)
        if "EREV-MIG-0067" in message:
            command.upgrade(alembic_config(), "head")  # descendants of 0067 back in place
            pytest.skip(f"0067's downgrade refused by name: {message}")
        raise


def test_old_seed_forward_upgrade_appends_a_correction(
    test_database: TestDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The true old-seed case through supported boundaries (Codex 0408; written NOT RUN on the
    lane):
    0003 renders the seed from the Python catalogue at run time, so the catalogue is pointed at the
    pre-1.56 schema (all five families required) while the database is upgraded to 0065; the real
    catalogue is restored and 0066 runs. The seeded row keeps the OLD schema (append-only, never
    updated), the correction row and the effective relation carry the NEW one, and a later owner-
    appended correction 2 moves the effective section / description the API filters and searches."""
    spec = PLATFORM_PARAMETERS[RETENTION]
    old_schema = spec.value_schema["anyOf"][1]  # the object branch alone: {} invalid
    old_catalogue = MappingProxyType(
        {**PLATFORM_PARAMETERS, RETENTION: dataclasses.replace(spec, value_schema=old_schema)}
    )
    _downgrade_to_base_or_skip()  # the walk's first leg; skips by name when 0067 refuses
    try:
        try:
            # the catalogue patch never outlives its one step (Codex 0533): if the upgrade to
            # 0065 raises, the patch is undone BEFORE the final base → head rebuild below, so
            # 0003 can never seed the old schema into the shared database a second time
            monkeypatch.setattr(platform_catalogue, "PLATFORM_PARAMETERS", old_catalogue)
            command.upgrade(alembic_config(), "0065")
        finally:
            monkeypatch.undo()
        assert platform_catalogue.PLATFORM_PARAMETERS[RETENTION].value_schema == spec.value_schema
        with test_database.owner_engine.begin() as owner:
            seeded = owner.execute(
                text("SELECT value_schema FROM erev.registry_parameter WHERE code = :c"),
                {"c": RETENTION},
            ).scalar_one()
            assert seeded == old_schema  # the old seed really is persisted
            assert (
                owner.execute(text("SELECT count(*) FROM erev.registry_parameter")).scalar_one()
                == 155
            )
        command.upgrade(alembic_config(), "0066")
        with test_database.owner_engine.begin() as owner:
            seeded_after = owner.execute(
                text("SELECT value_schema FROM erev.registry_parameter WHERE code = :c"),
                {"c": RETENTION},
            ).scalar_one()
            assert seeded_after == old_schema  # never updated (IM-A)
            corrections = [dict(r) for r in owner.execute(text(SELECT_CORRECTIONS)).mappings()]
            assert [(c["code"], c["correction_no"]) for c in corrections] == [(RETENTION, 1)]
            assert corrections[0]["value_schema"] == spec.value_schema
            effective = _effective(owner)
            assert (
                effective[RETENTION]["value_schema"] == spec.value_schema
            )  # advertised: corrected
            assert effective[RETENTION]["section"] == spec.section
            assert (
                len(effective) == 155
                and effective["ai.enabled"]["value_schema"]
                == PLATFORM_PARAMETERS["ai.enabled"].value_schema
            )  # fallback: a code without corrections keeps its seed
            # a later correction (a governed revision would append it; the owner stands in here)
            owner.execute(
                insert(registry_parameter_correction).values(
                    code=RETENTION,
                    correction_no=2,
                    value_schema=spec.value_schema,
                    description="Corrected description: retention families per copied family.",
                    source_ref=spec.source_ref,
                    section="Corrected",
                    applied_by_revision="tests",
                    created_by_kind="SYSTEM",
                )
            )
            effective = _effective(owner)
            assert effective[RETENTION]["section"] == "Corrected"
            assert effective[RETENTION]["description"].startswith("Corrected description")
            by_section = (
                owner.execute(
                    select(EFFECTIVE_REGISTRY_PARAMETER.c.code).where(
                        EFFECTIVE_REGISTRY_PARAMETER.c.section == "Corrected"
                    )
                )
                .scalars()
                .all()
            )
            assert by_section == [RETENTION]  # the section filter follows the correction
            searched = (
                owner.execute(
                    select(EFFECTIVE_REGISTRY_PARAMETER.c.code).where(
                        EFFECTIVE_REGISTRY_PARAMETER.c.description.ilike("%corrected description%")
                    )
                )
                .scalars()
                .all()
            )
            assert searched == [RETENTION]  # the q search follows the correction
            assert (
                owner.execute(
                    text("SELECT count(*) FROM erev.registry_parameter_correction")
                ).scalar_one()
                == 2
            )
    finally:
        # the migration boundary restores the shared database with the REAL catalogue, pass or
        # fail (Codex 0515 / 0533): the patch above is already undone when this runs
        assert platform_catalogue.PLATFORM_PARAMETERS[RETENTION].value_schema == spec.value_schema
        command.downgrade(alembic_config(), "base")
        command.upgrade(alembic_config(), "head")

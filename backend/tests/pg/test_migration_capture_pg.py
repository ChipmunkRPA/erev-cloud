"""T-MIG-04 / T-MIG-05 and ``MIGRATION_IMPORT`` over a database (BUILD_SPEC LMG-2; 04 rev 1.60;
revision 0067; D-98 candidates 122 and 126). WRITTEN, NOT RUN on the lane (the databases
``erev_rv_l24_*`` are Ray-side) — lane record docs/reviews/loop/prod/F-LMG.md §24.5.

Measured here: (1) the capture tables' database invariants — IM-A immutability, the CHECKs (book
ASC606, the payload's batch = the batch, ≥ 1 member), the one-version-per-batch and
one-obligation-per-batch unique keys, the FK from T-MIG-05 to T-MIG-04 — and that the
``VersionRef`` bound from a stored row round-trips through the repository reader; (2) the import
job's CURRENT contract over the shipped WLD-F-15 copy with the booking prerequisites provisioned
(entities, products with the parity templates, the reporting currency): the job FAILS BY NAME with
the payload-precision refusal (S07-R-11 "values as stored" vs ``money.MoneyStr`` four places — the
specification conflict raised to the supervisor), no ``contract`` row exists, no T-MIG-04 row
exists; the import's own transaction rolls back (the batch is PROFILED again at that instant, its
IMPORTING claim undone) and the job's terminal hook then SETTLES the batch FAILED in its own
transaction — so the observed end state is job FAILED and batch FAILED, never a lingering
PROFILED or IMPORTING (Codex 0629 wording). The negative input is the V2 / ExactMoneyIn one (Codex
1101; the four-place V1 refusal is the labelled V1 witness in tests/unit). (2b) The positive
end-to-end case (Codex 1106 C1; authored in this module, NOT RUN on the lane):
``test_import_job_creates_the_confirmed_prerequisites_over_wld_f_15`` — no provisioned entity or
product, the registered worker path, the confirmed writers create them, IMPORTED with 24 T-MIG-02,
4 T-MIG-04 and 16 T-MIG-05 rows and no ``contract`` row; ``MIGRATION_RECONCILE`` → RECONCILED with
136 lines is the reconcile module's case.
(3) The lifecycle witnesses (Codex 0422; 04 T-MIG-01 note rev 1.60) over a seeded durable capture:
same-operation recovery returns the stored result without writing; a foreign operation's capture is
refused by name; the terminal hook leaves a verified capture untouched and fails a PROFILED batch.

Lane FIX-E (2026-09-29) — the module's first runs on a lane database (``erev_rv_l7_test``):
(1) and (3) pass as written. (2) passes after FLMG-PG-REPLAY-REQUEST-1 — the witness now carries
the ``MIGRATION_SSP_REPLAY`` request 04 rev 1.72 requires, so the job reaches the exact-value
boundary it witnesses. (2c) is new:
``test_import_prices_a_vc_row_with_its_vc_element_and_stores_the_capture_under_the_tenant`` — the
registered worker path over the contracts in flight at the cutover, the witness of the two product
defects these runs exposed (FLMG-VC-ELEMENT-1: the dry run wrote no VC element for a legacy ``VC``
row; FLMG-CAPTURE-TENANT-1: the capture rows carried no tenant). (2b) and
``test_import_keeps_an_existing_ssp_only_product_over_a_second_label`` still FAIL, at the engine's
``EVENT_BEFORE_INCEPTION`` on Contract 3: WLD-F-15's Contracts 3 and 4 were set up on 1 Feb 2023,
after the 31 Jan 2023 cutover — ENGINE_SPEC S07-R-02 (inception = the legacy minimum ``Current
Period``) against S07-R-01 and S01-R-15. Ruled 2026-09-30: such a contract is booked at its legacy
inception and receives no opening balance; T-MIG-04 requires an opening event per captured version
(five NOT NULL columns), so its capture shape is with the supervisor. All three witnesses and (2c)
assert the captured balances PRD WLD-X-27 / ENGINE_SPEC EX-07-A state for Contracts 1 and 2
(FLMG-ONBOARDING-METHOD-PIN-1: POL-210's mode (a) method at contract level).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    contract,
    estimate,
    estimate_version,
    file_object,
    fiscal_calendar,
    job,
    legal_entity,
    migrated_legacy_row,
    migration_batch,
    migration_population_obligation,
    migration_population_version,
    period,
    pob_template,
    product,
    rule,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    tenant,
)
from erev_api.domain.imports.legacy_v1.sku_ssp import product_parity_values
from erev_api.domain.migration import capture, jobs, legacy_db, repository
from erev_api.domain.migration import commands as migration_commands
from erev_api.domain.reference.commands import create_product
from erev_api.enums import (
    ApprovalSubjectType,
    Distinctness,
    FilePurpose,
    JobKind,
    PrincipalAgent,
    PrincipalKind,
    TenantKind,
)
from erev_api.files.store import LocalFileStore, store_file
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.problems import Problem
from erev_api.schemas.products import ProductIn
from erev_api.uow import unit_of_work
from erev_engine.canonical import canonical_bytes
from erev_engine.upgrade import decode_input
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from support.architecture import ROOT
from support.db import TestDatabase
from support.factories import maya_principal, stamp_test_release
from support.legacy_replay import PARITY_TEMPLATES, _publish_parity_templates
from support.principals import member
from support.rows import (
    file_object_values,
    fiscal_calendar_values,
    legal_entity_values,
    migration_batch_values,
    migration_population_obligation_values,
    migration_population_version_values,
    period_values,
    product_values,
)

pytestmark = pytest.mark.pg

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
# WLD-F-15: the SKUs and the parity template each row maps to (field_mapping; POL-211 SINGLE_POB).
SKU_TEMPLATES = {
    "Software 1": "LEGACY-DISTINCT",
    "Hardware 1": "LEGACY-DISTINCT",
    "Consulting 1": "LEGACY-NONDISTINCT",
    "Material Right - Hardware": "LEGACY-MATERIAL-RIGHT",
    "Material Right - Services": "LEGACY-MATERIAL-RIGHT",
    "Variable Consideration": "LEGACY-VC",
}
ENTITIES = ("Mock Entity 1", "Mock Entity 2")
# The captured cumulative amounts of the contracts in flight at the cutover, QUOTED FROM THE
# DOCUMENTS (never from a run): PRD WLD-X-27 (the WLD-T-21 database import at cutover 31 Jan 2023)
# — "cumulative revenue C1 / C2 … 295.69 / 58.85; cumulative billing C1 / C2 … 300.00 / 0.00; C1
# contract liability … 4.31; C2 debit net position … 58.85"; ENGINE_SPEC EX-07-A — Contract 1
# "C_0 = 128.84 / 118.53 / 48.32 / 0.00 … baseline revenue 295.69; net position 300.00 − 295.69 =
# 4.31 (contract liability)"; legacy 07 GT-05 — Contract 2 "position -58.8462 -> unbilled A/R
# reclass 58.8462 on POB #1". Per contract: (Σ revenue_cum, Σ billed_cum, Σ position — a liability
# positive, Σ netting reclass).
WLD_X_27_CUMULATIVE = {
    "Contract 1": (Decimal("295.69"), Decimal("300.00"), Decimal("4.31"), Decimal("0.00")),
    "Contract 2": (Decimal("58.85"), Decimal("0.00"), Decimal("-58.85"), Decimal("58.85")),
}
EX_07_A_REVENUE = {  # ENGINE_SPEC EX-07-A: Contract 1's baseline revenue C_0 per obligation
    "POB #1": Decimal("128.84"),
    "POB #2": Decimal("118.53"),
    "POB #3": Decimal("48.32"),
    "POB #4": Decimal("0.00"),
}


def _captured_cumulative(session: Any, batch_id: UUID) -> dict[str, tuple[Decimal, ...]]:
    """Per contract of the batch's T-MIG-05 rows: (Σ ``revenue_cum``, Σ ``billed_cum``, Σ
    ``position_obligation``, Σ ``netting_reclass_amount``) — the typed measure columns the
    reconcile extracts from."""
    totals: dict[str, list[Decimal]] = {}
    for row in session.execute(
        select(migration_population_obligation).where(
            migration_population_obligation.c.migration_batch_id == batch_id
        )
    ).mappings():
        found = totals.setdefault(str(row["contract_external_id"]), [Decimal(0)] * 4)
        found[0] += Decimal(str(row["revenue_cum"]))
        found[1] += Decimal(str(row["billed_cum"]))
        found[2] += Decimal(str(row["position_obligation"]))
        found[3] += Decimal(str(row["netting_reclass_amount"]))
    return {name: tuple(values) for name, values in sorted(totals.items())}


def _assert_the_capture_holds_the_imported_balances(session: Any, batch_id: UUID) -> None:
    """FLMG-ONBOARDING-METHOD-PIN-1 (05 RCP-15 rev 1.36; POL-210 mode (a); ENGINE_SPEC §7.1): the
    contracts the migration opened are computed under ``OPENING_BALANCES_AT_CUTOVER`` at contract
    level, so the durable capture holds the imported cumulative amounts — WLD-X-27 / EX-07-A, not
    the zero revenue a recompute from inception gives a stream without history (the pre-fix
    capture: Contract 1 revenue 0.00, net position 300.00) — and the retained input of each of
    those versions shows the pin with the contract's own opening event as its source."""
    captured = _captured_cumulative(session, batch_id)
    assert {name: captured[name] for name in WLD_X_27_CUMULATIVE} == WLD_X_27_CUMULATIVE
    revenue = {
        str(row["obligation_key"]): Decimal(str(row["revenue_cum"]))
        for row in session.execute(
            select(migration_population_obligation).where(
                migration_population_obligation.c.migration_batch_id == batch_id,
                migration_population_obligation.c.contract_external_id == "Contract 1",
            )
        ).mappings()
    }
    assert revenue == EX_07_A_REVENUE
    for version in (
        session.execute(
            select(migration_population_version).where(
                migration_population_version.c.migration_batch_id == batch_id
            )
        )
        .mappings()
        .all()
    ):
        name = str(version["members"][0]["contract_external_id"])
        if name not in WLD_X_27_CUMULATIVE:
            continue
        evidence = decode_input(canonical_bytes(version["input_evidence"]))
        pins = [
            policy
            for policy in evidence.books[0].policies
            if policy.code == "onboarding.method" and policy.scope == "CONTRACT"
        ]
        assert [(pin.subject_key, pin.value, pin.level, pin.pin) for pin in pins] == [
            (name, "OPENING_BALANCES_AT_CUTOVER", "C", "K")
        ]
        assert pins[0].source_ref == version["opening_event_key"]  # the immutable fact


def _problem_text(problem: Any) -> str:
    """The job problem as FULL text for an assertion message: a str is printed whole by pytest
    (batch #9 truncated the dict repr before the finding's detail — S07-R-03 diagnostic)."""
    return json.dumps(problem, indent=1, sort_keys=True, default=str)


def _ctx(tenant_id: UUID, clock: FrozenClock) -> RequestContext:
    """The import job's request context (batch #5 return (2) / (3)): ``unit_of_work`` needs the
    principal-bearing ``RequestContext`` — here the job's SYSTEM principal with
    ``MIGRATION_PERMISSIONS`` (``capture.migration_principal``), not a bare ``DbContext``."""
    return RequestContext(
        principal=capture.migration_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-migration-capture-pg",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


UNREPRESENTABLE_COLUMN = "Current Cumulative Catchup - Cumulative - Disclosure Only"


def unrepresentable_copy(target: Path) -> Path:
    """WLD-F-15 with Contract 1 / POB #1's catch-up REAL set to 1e-19 — exact text
    ``0.0000000000000000001`` (19 fractional digits), beyond the API-C-06 bound of ``ExactMoneyIn``
    (the V2 negative input; Codex 1101 §2). Built through the parity support (the only test
    location that may import sqlite3, DG-ARC-05); the shipped fixture is untouched."""
    from support.parity.sqlite_fixtures import sqlite_copy_with_cell

    target_row = next(
        row
        for row in legacy_db.latest_rows(legacy_db.rows(FIXTURE))  # the staged (latest) version
        if row.values.get("Contract Unique Name") == "Contract 1"
        and row.values.get("POB Unique ID") == "POB #1"
    )
    return sqlite_copy_with_cell(
        FIXTURE,
        target,
        table="Contract_Live",
        column=UNREPRESENTABLE_COLUMN,
        rowid=target_row.source_rowid,
        value=1e-19,
    )


def _fails(session: Any, statement: Any) -> tuple[str, str]:
    """SQLSTATE and PRIMARY message of a statement that must fail; only its savepoint rolls back
    (the pattern of ``test_t_mig_tables._refused``). Integrated batch #6 test-pg return (1): the
    earlier form caught the error INSIDE ``with session.begin_nested()``, so the context manager
    issued RELEASE SAVEPOINT on the aborted subtransaction (``InFailedSqlTransaction``)."""
    savepoint = session.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        session.execute(statement)
    savepoint.rollback()
    origin = excinfo.value.orig
    diag = getattr(origin, "diag", None)
    primary = str(getattr(diag, "message_primary", "") or "") or str(origin)
    return str(getattr(origin, "sqlstate", "") or ""), primary


def test_t_mig_04_and_05_checks_keys_and_immutability(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        session.execute(insert(file_object).values(**file_row))
        batch = migration_batch_values(tenant_id, source_file_id=file_row["id"], status="IMPORTED")
        session.execute(insert(migration_batch).values(**batch))
        version = migration_population_version_values(tenant_id, migration_batch_id=batch["id"])
        session.execute(insert(migration_population_version).values(**version))
        # the child row shares its parent's identities (batch #8 test-pg return: the reader selects
        # T-MIG-05 rows by the parent's contract_version_id and binds capture_operation_id — the
        # helper's fresh defaults left the parent childless; the wld_f_15 witness's shape)
        captured = migration_population_obligation_values(
            tenant_id,
            migration_batch_id=batch["id"],
            population_version_id=version["id"],
            capture_operation_id=version["capture_operation_id"],
            contract_version_id=version["contract_version_id"],
            obligation_version_id=version["obligation_version_ids"][0],
            contract_id=UUID(version["members"][0]["contract_id"]),
        )
        session.execute(insert(migration_population_obligation).values(**captured))
        # CHECKs (04 T-MIG-04): the book, the payload's batch, at least one member
        other_book = migration_population_version_values(
            tenant_id, migration_batch_id=batch["id"], book_code="LEGACY"
        )
        assert (
            "ck_migration_population_version__book"
            in _fails(session, insert(migration_population_version).values(**other_book))[1]
        )
        foreign = migration_population_version_values(
            tenant_id, migration_batch_id=batch["id"], payload_migration_batch_id=UUID(int=99)
        )
        assert (
            "ck_migration_population_version__payload_batch"
            in _fails(session, insert(migration_population_version).values(**foreign))[1]
        )
        unbound = migration_population_version_values(
            tenant_id, migration_batch_id=batch["id"], members=[]
        )
        assert (
            "ck_migration_population_version__members"
            in _fails(session, insert(migration_population_version).values(**unbound))[1]
        )
        # one capture per batch and version; one row per captured obligation version
        twice = migration_population_version_values(
            tenant_id,
            migration_batch_id=batch["id"],
            contract_version_id=version["contract_version_id"],
        )
        assert _fails(session, insert(migration_population_version).values(**twice))[0] == "23505"
        again = migration_population_obligation_values(
            tenant_id,
            migration_batch_id=batch["id"],
            population_version_id=version["id"],
            obligation_version_id=captured["obligation_version_id"],
        )
        assert _fails(session, insert(migration_population_obligation).values(**again))[0] == (
            "23505"
        )
        # T-MIG-05 → T-MIG-04 (tenant FK); IM-A: erev_app holds SELECT + INSERT only, so its
        # UPDATE / DELETE are refused by privilege (42501) BEFORE the DB-01 trigger can answer —
        # batch #7 test-pg return (D-98 133 AMENDMENT 2, B7-LMG-PG-1); the trigger is witnessed
        # below through the owner connection (the test_immutability_and_grants precedent)
        orphan = migration_population_obligation_values(
            tenant_id, migration_batch_id=batch["id"], population_version_id=UUID(int=4242)
        )
        assert _fails(session, insert(migration_population_obligation).values(**orphan))[0] == (
            "23503"
        )
        tamper_version = (
            update(migration_population_version)
            .where(migration_population_version.c.id == version["id"])
            .values(node_count=2)
        )
        drop_obligation = migration_population_obligation.delete().where(
            migration_population_obligation.c.id == captured["id"]
        )
        assert _fails(session, tamper_version)[0] == "42501"
        assert _fails(session, drop_obligation)[0] == "42501"
        # the repository reader binds the stored row: membership, expected output, provenance
        stamp = type("Uow", (), {})()
        stamp.session = session
        stamp.principal = type(
            "P", (), {"id": None, "kind": PrincipalKind.SYSTEM, "tenant_id": tenant_id}
        )()
        stamp.now = clock.now()
        bound = repository.comparison_population(stamp, batch)  # type: ignore[arg-type]
        assert bound is not None
        (ref,) = bound.versions
        assert ref.contract_version_id == version["contract_version_id"]
        assert ref.obligation_version_ids == set(version["obligation_version_ids"])
        assert ref.payload_migration_batch_id == batch["id"]
        bound.check_batch(batch)
        rows = repository.population_obligation_versions(stamp, bound)  # type: ignore[arg-type]
        assert [row["id"] for row in rows] == [captured["obligation_version_id"]]
        lookup = repository.trace_nodes(stamp, ref)  # type: ignore[arg-type]
        assert lookup("revenue_cum:POB #1") is not None  # the mirrored trace, hash-checked
    # DB-01 for any role that holds the privilege: erev_owner meets the row triggers (EREV-IMM-001);
    # FORCE RLS names no owner policy, hence NO FORCE inside the rolled-back transaction
    # (SPEC-Q-129; the test_immutability_and_grants.py pattern)
    messages: list[str] = []
    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            for name in ("migration_population_version", "migration_population_obligation"):
                connection.exec_driver_sql(f"ALTER TABLE erev.{name} NO FORCE ROW LEVEL SECURITY")
            for statement in (
                update(migration_population_version)
                .where(migration_population_version.c.id == version["id"])
                .values(node_count=2),
                migration_population_obligation.delete().where(
                    migration_population_obligation.c.id == captured["id"]
                ),
            ):
                savepoint = connection.begin_nested()
                with pytest.raises(DBAPIError) as excinfo:
                    connection.execute(statement)
                savepoint.rollback()
                diag = getattr(excinfo.value.orig, "diag", None)
                messages.append(str(getattr(diag, "message_primary", "") or ""))
        finally:
            connection.rollback()
    assert messages == [
        "EREV-IMM-001: UPDATE on erev.migration_population_version is not permitted; the table is "
        "append-only",
        "EREV-IMM-001: DELETE on erev.migration_population_obligation is not permitted; the table "
        "is append-only",
    ]


def _provision(session: Any, tenant_id: UUID) -> None:
    """The booking prerequisites of WLD-F-15 that the import-phase follow-up will create: the two
    selling entities on the tenant's calendar and the six SKUs as products carrying their parity
    template (the templates published through the established seam)."""
    calendar = fiscal_calendar_values(tenant_id)
    session.execute(insert(fiscal_calendar).values(**calendar))
    for code in ENTITIES:
        session.execute(
            insert(legal_entity).values(
                **legal_entity_values(tenant_id, calendar_id=calendar["id"], code=code)
            )
        )
    templates = {
        str(row.code): UUID(str(row.id))
        for row in session.execute(
            select(pob_template.c.code, pob_template.c.id).where(
                pob_template.c.code.in_([code for code, _, _ in PARITY_TEMPLATES])
            )
        )
    }
    for sku, template_code in SKU_TEMPLATES.items():
        session.execute(
            insert(product).values(
                **product_values(
                    tenant_id, code=sku, default_pob_template_id=templates[template_code]
                )
            )
        )


def test_import_job_refuses_by_name_the_unrepresentable_opening_values_and_writes_nothing(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
) -> None:
    files = LocalFileStore(app_settings.file_root)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    stamp_test_release()
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    _publish_parity_templates(tenant_id)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        # Codex 1101 §2: the negative input is authored against the CURRENT registered payload
        # contract (V2 / ExactMoneyIn, 04 rev 1.61) — a copy of WLD-F-15 whose Contract 1 / POB #1
        # catch-up REAL is 1e-19: its exact plain text 0.0000000000000000001 has 19 fractional
        # digits, beyond the API-C-06 bound; the shipped fixture is never modified (REQ-MIG-004)
        negative = unrepresentable_copy(tmp_path / "unrepresentable-v2.db")
        with negative.open("rb") as stream:
            stored = store_file(
                uow,
                purpose=FilePurpose.LEGACY_DATABASE,
                stream=stream,
                original_filename=FIXTURE.name,
                media_type="application/vnd.sqlite3",
            )
        _provision(uow.session, tenant_id)
        # FLMG-PG-DIGEST-STUB-1 (batch #9): the batch carries the negative copy's PROFILE — its
        # SKU_SSP table is the shipped one (only a Contract_Live cell differs), so the bound digest
        # equals the spooled one and the import reaches the unrepresentable-value boundary instead
        # of the SKU_SSP_UNBOUND refusal that precedes staging (04 rev 1.72)
        batch = migration_batch_values(
            tenant_id,
            source_file_id=stored["id"],
            status="PROFILED",
            profile=legacy_db.profile(negative).as_json(),
        )
        uow.session.execute(insert(migration_batch).values(**batch))
        uow.commit()
    # FLMG-PG-REPLAY-REQUEST-1 (lane FIX-E; 04 T-MIG-01 note rev 1.72): the import phase approves
    # the LEGACY-SKU-SSP replay under the APPROVED MIGRATION_SSP_REPLAY request the /import
    # confirmation submitted — without it the job stops at the prerequisite writer ("no APPROVED
    # approval request") and never reaches the dry run's exact-value boundary this witness is for
    replay = _replay_request_as_user(someone, tenant_id, clock, keyring, files, batch["id"])
    assert str(replay["status"]) == "APPROVED", replay
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        row = registry.insert_job(
            uow.session,
            JobKind.MIGRATION_IMPORT,
            {
                "migration_id": str(batch["id"]),
                "batch_parameters": {},
                "ssp_replay_request_id": str(replay["id"]),
                "sku_ssp_sha256": batch["profile"]["sku_ssp_sha256"],
            },
            tenant_id=tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            uow.session,
            job_id=row["id"],
            tenant_id=tenant_id,
            queue=str(row["queue"]),
            now=clock.now(),
        )
        uow.commit()
    job_id = UUID(str(row["id"]))
    # MIGRATION_IMPORT inherits the default retry policy (max_attempts = 1): the first named
    # refusal is terminal, so ONE run settles the job FAILED and runs the registered terminal hook
    # (jobs.import_failed) — no two-attempt lifecycle is claimed (Codex 0533 L1)
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(context) as session:
        state: Any = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == job_id)
        ).one()
        status, batch_problem = session.execute(
            select(migration_batch.c.status, migration_batch.c.problem).where(
                migration_batch.c.id == batch["id"]
            )
        ).one()
        contracts = session.execute(select(func.count()).select_from(contract)).scalar_one()
        captured = session.execute(
            select(func.count())
            .select_from(migration_population_version)
            .where(migration_population_version.c.migration_batch_id == batch["id"])
        ).scalar_one()
    assert state[0] == "FAILED"
    detail = str(state[1]["detail"])
    # the CURRENT contract (V2 / ExactMoneyIn): refused by name at the exact-value boundary —
    # the 19-fractional-digit amount is outside the API-C-06 bound; nothing is rounded (the
    # historical four-place refusal is the V1-boundary witness in
    # tests/unit/test_migration_capture.py)
    assert detail.startswith("Contract 1") and "0.0000000000000000001" in detail
    assert "API-C-06" in detail and "refused, not rounded" in detail
    assert state[1]["errors"][0]["rule_id"] == capture.RULE
    # terminal truth: the import's transaction rolled back (IMPORTING never persisted, no capture,
    # no contract) and the registered hook then moved the PROFILED batch to FAILED with the same
    # problem in the settlement transaction — job and batch FAILED together
    assert status == "FAILED" and batch_problem["detail"] == detail
    assert contracts == 0  # BS3-D-26: no contract row before promotion — dry run or refusal
    assert captured == 0


def _replay_request_as_user(
    someone: Any,
    tenant_id: UUID,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    batch_id: UUID,
) -> Any:
    """The /import confirmation's MIGRATION_SSP_REPLAY request as the CONFIRMING USER submits it —
    its own unit of work under a USER principal, so the engine's ``source.channel`` fact is USER and
    the provisioned AUTO-MIG-01 rule (``source.channel eq USER``) can match; the job's SYSTEM
    authority stays separate (FLMG-PG-REPLAY-ACTOR-1, Codex 0644 §2). The batch row must be
    committed first. Submitted through the module that owns the confirmation
    (``migration.commands.submit_request`` — the import of that module registers the
    MIGRATION_SSP_REPLAY lifecycle, as in the API process; a bare ``approvals.submit`` made this
    module pass only after another module had imported the route, FLMG-PG-LIFECYCLE-IMPORT-1)."""
    user_context = RequestContext(
        principal=maya_principal(someone),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-migration-capture-pg-user",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(user_context, clock=clock, keyring=keyring, files=files) as uow:
        replay = migration_commands.submit_request(
            uow,
            subject_type=ApprovalSubjectType.MIGRATION_SSP_REPLAY,
            subject_id=batch_id,
            summary="Legacy SSP replay (witness)",
        )
        uow.commit()
    return replay


@pytest.mark.parametrize(
    "target", ["Mock Entity 1", "AVM-US"], ids=["identity-mapping", "non-identity-target"]
)
def test_import_job_creates_the_confirmed_prerequisites_over_wld_f_15(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    target: str,
) -> None:
    """LM-CL-09 / LM-CL-03 (04 §17.2 rev 1.64; D-98 candidate 133; Codex 1106 R1 / C1): the import
    over the shipped WLD-F-15 with NO provisioned selling entity and NO product — only a fiscal
    calendar with a period and the published parity templates — through the REGISTERED worker path
    (``registry.run_job``, the plain SYSTEM job principal): the import phase's outer unit of work
    carries the limited migration writer authority, the confirmed writers create the two entities
    (tenant reporting currency, the confirmed calendar / time zone) and the six products (their
    parity templates), ONE ``migration_batch.prerequisites`` audit event lists them, the dry run
    then passes and the batch is IMPORTED with its durable capture; no ``contract`` row exists.
    Codex 1227 F1 (``non-identity-target``): with the confirmed mapping Mock Entity 1 → AVM-US the
    created entities are exactly {AVM-US, Mock Entity 2} — no ``Mock Entity 1`` row — and the dry
    run passes against the TARGET code (on the pre-fold source it demanded the legacy text and the
    import failed)."""
    expected = tuple(sorted({target, "Mock Entity 2"}))
    files = LocalFileStore(app_settings.file_root)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    stamp_test_release()
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    _publish_parity_templates(tenant_id)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        with FIXTURE.open("rb") as stream:
            stored = store_file(
                uow,
                purpose=FilePurpose.LEGACY_DATABASE,
                stream=stream,
                original_filename=FIXTURE.name,
                media_type="application/vnd.sqlite3",
            )
        # the ONLY provisioning: a calendar with one period (the entity writer keeps the primary
        # book from the calendar's earliest period); no entity, no product
        calendar = fiscal_calendar_values(tenant_id)
        uow.session.execute(insert(fiscal_calendar).values(**calendar))
        uow.session.execute(
            insert(period).values(
                **period_values(
                    tenant_id,
                    calendar_id=calendar["id"],
                    fiscal_year=2023,
                    period_no=1,
                    start_date=date(2023, 1, 1),
                    end_date=date(2023, 1, 31),
                )
            )
        )
        currency = str(
            uow.session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == tenant_id)
            ).scalar_one()
        ).strip()
        # 04 rev 1.72: the PROFILE as the profiling phase writes it — the SKU_SSP digest, findings
        # and keys
        batch = migration_batch_values(
            tenant_id,
            source_file_id=stored["id"],
            status="PROFILED",
            profile=legacy_db.profile(FIXTURE).as_json(),
        )
        uow.session.execute(insert(migration_batch).values(**batch))
        uow.commit()
    # the /import confirmation's part (D-98 133 AMENDMENT 4 option A2): the MIGRATION_SSP_REPLAY
    # request is submitted by the CONFIRMING USER in its own unit of work — the engine's
    # source.channel fact is USER, the provisioned AUTO-MIG-01 rule matches and approves it — while
    # the job keeps the SYSTEM migration authority (FLMG-PG-REPLAY-ACTOR-1, Codex 0644 §2)
    replay = _replay_request_as_user(someone, tenant_id, clock, keyring, files, batch["id"])
    assert str(replay["status"]) == "APPROVED", replay
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        params = {
            "migration_id": str(batch["id"]),
            "phase": "IMPORT",
            "batch_parameters": {},
            "entity_mapping": [
                {"legacy_name": name, "entity_code": code, "calendar_id": None, "time_zone": None}
                for name, code in zip(ENTITIES, (target, "Mock Entity 2"), strict=True)
            ],
            "resolved_entities": [
                {
                    "legacy_name": name,
                    "entity_code": code,
                    "functional_currency": currency,
                    "calendar_id": str(calendar["id"]),
                    "time_zone": "UTC",
                }
                for name, code in zip(ENTITIES, (target, "Mock Entity 2"), strict=True)
            ],
            "create_missing_entities": True,
            "create_missing_products": True,
            "ssp_replay_request_id": str(replay["id"]),
            "sku_ssp_sha256": batch["profile"]["sku_ssp_sha256"],
        }
        row = registry.insert_job(
            uow.session,
            JobKind.MIGRATION_IMPORT,
            params,
            tenant_id=tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            uow.session,
            job_id=row["id"],
            tenant_id=tenant_id,
            queue=str(row["queue"]),
            now=clock.now(),
        )
        uow.commit()
    job_id = UUID(str(row["id"]))
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(context) as session:
        state, problem = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == job_id)
        ).one()
        assert state == "SUCCEEDED", _problem_text(problem)
        status, profile = session.execute(
            select(migration_batch.c.status, migration_batch.c.profile).where(
                migration_batch.c.id == batch["id"]
            )
        ).one()
        assert status == "IMPORTED"
        assert profile["created_entities"] == list(expected)
        # + the SKU present only in SKU_SSP (LM-SSP-02; 04 rev 1.72)
        assert profile["created_products"] == sorted([*SKU_TEMPLATES, "Material Right - Software"])
        entities = session.execute(
            select(
                legal_entity.c.code, legal_entity.c.functional_currency, legal_entity.c.time_zone
            ).order_by(legal_entity.c.code)
        ).all()
        # the TARGET codes only: no row for a legacy text the confirmation mapped elsewhere (F1)
        assert [(e[0], e[1], e[2]) for e in entities] == [
            (code, currency, "UTC") for code in expected
        ]
        templates = {
            str(row.id): str(row.code)
            for row in session.execute(select(pob_template.c.id, pob_template.c.code))
        }
        products = session.execute(
            select(product.c.code, product.c.name, product.c.default_pob_template_id).order_by(
                product.c.code
            )
        ).all()
        assert {p[0]: (p[1], templates[str(p[2])]) for p in products} == {
            sku: (sku, template_code)
            for sku, template_code in {
                **SKU_TEMPLATES,
                "Material Right - Software": "LEGACY-DISTINCT",
            }.items()
        }
        # 04 rev 1.72: ONE APPROVED LEGACY-SKU-SSP version per label, approved under the replay
        # request
        # (EREV-CFG-002 satisfied by the control itself), 7 entries, named in the profile
        versions = session.execute(
            select(
                ssp_book_version.c.id,
                ssp_book_version.c.legacy_version_label,
                ssp_book_version.c.status,
                ssp_book_version.c.approval_request_id,
                ssp_book_version.c.published_by,
            )
            .select_from(
                ssp_book_version.join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
            )
            .where(ssp_book.c.code == "LEGACY-SKU-SSP")
        ).all()
        assert [(v[1], v[2], v[3], v[4]) for v in versions] == [
            ("2023-01-01", "APPROVED", replay["id"], None)
        ]
        entries = session.execute(
            select(func.count())
            .select_from(ssp_entry)
            .where(ssp_entry.c.ssp_book_version_id == versions[0][0])
        ).scalar_one()
        assert entries == 7
        assert profile["replayed_ssp_versions"] == [
            {
                "legacy_version_label": "2023-01-01",
                "ssp_book_version_id": str(versions[0][0]),
                "entry_count": 7,
                "source_sha256": batch["profile"]["sku_ssp_sha256"],
                "reused": False,
            }
        ]
        request_status, subject_type = session.execute(
            select(approval_request.c.status, approval_request.c.subject_type).where(
                approval_request.c.id == replay["id"]
            )
        ).one()
        assert (request_status, subject_type) == (
            "APPROVED",
            ApprovalSubjectType.MIGRATION_SSP_REPLAY.value,
        )
        # the ACTUAL rule / request linkage: one AUTO_APPROVE decision by SYSTEM on the request,
        # naming the tenant's provisioned AUTO-MIG-01 rule and its rule set version; the audit row
        rule_id, rule_set_version_id = session.execute(
            select(rule.c.id, rule.c.rule_set_version_id).where(rule.c.rule_key == "AUTO-MIG-01")
        ).one()
        decisions = session.execute(
            select(
                approval_decision.c.decision,
                approval_decision.c.approver_kind,
                approval_decision.c.auto_rule_id,
                approval_decision.c.auto_rule_set_version_id,
            ).where(approval_decision.c.approval_request_id == replay["id"])
        ).all()
        assert [(d[0], d[1], d[2], d[3]) for d in decisions] == [
            ("AUTO_APPROVE", "SYSTEM", rule_id, rule_set_version_id)
        ]
        auto_audit = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == "approval_request.auto_approve",
                audit_event.c.object_id == replay["id"],
            )
        ).all()
        assert len(auto_audit) == 1  # the auto-approve audit row of this request
        events = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == "migration_batch.prerequisites",
                audit_event.c.object_id == batch["id"],
            )
        ).all()
        assert len(events) == 1
        assert sorted(e["code"] for e in events[0][0]["entities"]) == list(expected)
        assert sorted(p["code"] for p in events[0][0]["products"]) == sorted(
            [*SKU_TEMPLATES, "Material Right - Software"]
        )
        assert [v["legacy_version_label"] for v in events[0][0]["ssp_versions"]] == ["2023-01-01"]
        assert session.execute(select(func.count()).select_from(contract)).scalar_one() == 0
        assert (
            session.execute(
                select(func.count())
                .select_from(migrated_legacy_row)
                .where(migrated_legacy_row.c.migration_batch_id == batch["id"])
            ).scalar_one()
            == 24
        )
        assert (
            session.execute(
                select(func.count())
                .select_from(migration_population_version)
                .where(migration_population_version.c.migration_batch_id == batch["id"])
            ).scalar_one()
            == 4
        )
        assert (
            session.execute(
                select(func.count())
                .select_from(migration_population_obligation)
                .where(migration_population_obligation.c.migration_batch_id == batch["id"])
            ).scalar_one()
            == 16
        )
        # IMPORTED for the right reason: the capture holds the imported balances (WLD-X-27)
        _assert_the_capture_holds_the_imported_balances(session, batch["id"])
    # FLMG-SSP-REUSE-SCALE-1 (Codex 0644 §2): a SECOND batch over the same SKU_SSP file reuses the
    # persisted APPROVED version — its NUMERIC(38,18) entries compare EXACTLY equal to the source
    # cells (scale-insensitive), so no conflict, no new version, entries unchanged; the request is
    # the confirming USER's (FLMG-PG-REPLAY-ACTOR-1). Green only with FLMG-SSP-EXISTING-PRODUCT-1 in
    # the same head: the second batch meets the SSP-only product the first one created.
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        with FIXTURE.open("rb") as stream:
            stored_again = store_file(
                uow,
                purpose=FilePurpose.LEGACY_DATABASE,
                stream=stream,
                original_filename=FIXTURE.name,
                media_type="application/vnd.sqlite3",
            )
        batch_again = migration_batch_values(
            tenant_id,
            source_file_id=stored_again["id"],
            status="PROFILED",
            profile=legacy_db.profile(FIXTURE).as_json(),
        )
        uow.session.execute(insert(migration_batch).values(**batch_again))
        uow.commit()
    replay_again = _replay_request_as_user(
        someone, tenant_id, clock, keyring, files, batch_again["id"]
    )
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        params_again = {
            **params,
            "migration_id": str(batch_again["id"]),
            "ssp_replay_request_id": str(replay_again["id"]),
            "sku_ssp_sha256": batch_again["profile"]["sku_ssp_sha256"],
        }
        row_again = registry.insert_job(
            uow.session,
            JobKind.MIGRATION_IMPORT,
            params_again,
            tenant_id=tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            uow.session,
            job_id=row_again["id"],
            tenant_id=tenant_id,
            queue=str(row_again["queue"]),
            now=clock.now(),
        )
        uow.commit()
    job_again = UUID(str(row_again["id"]))
    with tenant_session(context) as session:
        task_again = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_again)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_again})
    registry.run_job(job_again, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(context) as session:
        state_again, problem_again = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == job_again)
        ).one()
        assert state_again == "SUCCEEDED", _problem_text(problem_again)
        profile_again = session.execute(
            select(migration_batch.c.profile).where(migration_batch.c.id == batch_again["id"])
        ).scalar_one()
        # reused: the SAME version id, nothing created, the request approved
        assert profile_again["replayed_ssp_versions"] == [
            {
                "legacy_version_label": "2023-01-01",
                "ssp_book_version_id": str(versions[0][0]),
                "entry_count": 7,
                "source_sha256": batch_again["profile"]["sku_ssp_sha256"],
                "reused": True,
            }
        ]
        assert profile_again["created_products"] == [] and profile_again["created_entities"] == []
        still = session.execute(
            select(func.count())
            .select_from(
                ssp_book_version.join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
            )
            .where(ssp_book.c.code == "LEGACY-SKU-SSP")
        ).scalar_one()
        assert still == 1
        assert (
            session.execute(
                select(func.count())
                .select_from(ssp_entry)
                .where(ssp_entry.c.ssp_book_version_id == versions[0][0])
            ).scalar_one()
            == 7
        )


def test_import_keeps_an_existing_ssp_only_product_over_a_second_label(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """FLMG-SSP-EXISTING-PRODUCT-1 (Codex 0644 §2): a product found only in ``SKU_SSP`` that ALREADY
    exists in the tenant is kept — identity and facts unchanged, never recreated — and the import
    succeeds: ``created_products`` lists the six staged SKUs only, ONE product row with the
    pre-created id, and the replayed version's entry references it. Isolated by its own tenant
    (approved versions, products and batches are tenant-scoped rows) on the shipped WLD-F-15 fixture
    labelled 2023-01-01 — DG-ARC-05 allows SQLite only to READ a legacy .db, so no relabelled copy
    is written (supervisor's ruling; the first attempt's relabelling helper was removed)."""
    files = LocalFileStore(app_settings.file_root)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    stamp_test_release()
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    _publish_parity_templates(tenant_id)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    existing_only = "Material Right - Software"
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        template_id = uow.session.execute(
            select(pob_template.c.id).where(pob_template.c.code == "LEGACY-DISTINCT")
        ).scalar_one()
        pre_existing = create_product(
            uow,
            body=ProductIn(
                code=existing_only,
                name=existing_only,
                default_pob_template_id=template_id,
                distinctness_default=Distinctness("distinct"),
                principal_agent=PrincipalAgent.PRINCIPAL,
                policy_values=dict(product_parity_values()),
            ),
        )
        with FIXTURE.open("rb") as stream:
            stored = store_file(
                uow,
                purpose=FilePurpose.LEGACY_DATABASE,
                stream=stream,
                original_filename=FIXTURE.name,
                media_type="application/vnd.sqlite3",
            )
        calendar = fiscal_calendar_values(tenant_id)
        uow.session.execute(insert(fiscal_calendar).values(**calendar))
        uow.session.execute(
            insert(period).values(
                **period_values(
                    tenant_id,
                    calendar_id=calendar["id"],
                    fiscal_year=2023,
                    period_no=1,
                    start_date=date(2023, 1, 1),
                    end_date=date(2023, 1, 31),
                )
            )
        )
        currency = str(
            uow.session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == tenant_id)
            ).scalar_one()
        ).strip()
        batch = migration_batch_values(
            tenant_id,
            source_file_id=stored["id"],
            status="PROFILED",
            profile=legacy_db.profile(FIXTURE).as_json(),
        )
        uow.session.execute(insert(migration_batch).values(**batch))
        uow.commit()
    replay = _replay_request_as_user(someone, tenant_id, clock, keyring, files, batch["id"])
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        params = {
            "migration_id": str(batch["id"]),
            "phase": "IMPORT",
            "batch_parameters": {},
            "entity_mapping": [
                {"legacy_name": name, "entity_code": name, "calendar_id": None, "time_zone": None}
                for name in ENTITIES
            ],
            "resolved_entities": [
                {
                    "legacy_name": name,
                    "entity_code": name,
                    "functional_currency": currency,
                    "calendar_id": str(calendar["id"]),
                    "time_zone": "UTC",
                }
                for name in ENTITIES
            ],
            "create_missing_entities": True,
            "create_missing_products": True,
            "ssp_replay_request_id": str(replay["id"]),
            "sku_ssp_sha256": batch["profile"]["sku_ssp_sha256"],
        }
        row = registry.insert_job(
            uow.session,
            JobKind.MIGRATION_IMPORT,
            params,
            tenant_id=tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            uow.session,
            job_id=row["id"],
            tenant_id=tenant_id,
            queue=str(row["queue"]),
            now=clock.now(),
        )
        uow.commit()
    job_id = UUID(str(row["id"]))
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(context) as session:
        state, problem = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == job_id)
        ).one()
        assert state == "SUCCEEDED", _problem_text(problem)
        profile = session.execute(
            select(migration_batch.c.profile).where(migration_batch.c.id == batch["id"])
        ).scalar_one()
        # the pre-existing SSP-only product is NOT recreated: only the six staged SKUs are created
        assert profile["created_products"] == sorted(SKU_TEMPLATES)
        # IMPORTED for the right reason: the capture holds the imported balances (WLD-X-27)
        _assert_the_capture_holds_the_imported_balances(session, batch["id"])
        rows = session.execute(
            select(product.c.id, product.c.name, product.c.default_pob_template_id).where(
                product.c.code == existing_only
            )
        ).all()
        assert [(str(r[0]), r[1], str(r[2])) for r in rows] == [
            (str(pre_existing.id), existing_only, str(template_id))
        ]  # ONE row, the pre-created identity and facts
        versions = session.execute(
            select(ssp_book_version.c.id, ssp_book_version.c.legacy_version_label)
            .select_from(
                ssp_book_version.join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
            )
            .where(ssp_book.c.code == "LEGACY-SKU-SSP")
        ).all()
        assert [v[1] for v in versions] == ["2023-01-01"]  # this tenant's only version
        bound = session.execute(
            select(ssp_entry.c.product_id)
            .select_from(ssp_entry.join(product, product.c.id == ssp_entry.c.product_id))
            .where(
                ssp_entry.c.ssp_book_version_id == versions[0][0],
                product.c.code == existing_only,
            )
        ).all()
        # the entry binds to the kept product
        assert [str(b[0]) for b in bound] == [str(pre_existing.id)]
        assert profile["replayed_ssp_versions"][0]["legacy_version_label"] == "2023-01-01"


IN_FLIGHT = ("Contract 1", "Contract 2")  # set up 1 Jan 2023 — on or before the 31 Jan cutover


def test_import_prices_a_vc_row_with_its_vc_element_and_stores_the_capture_under_the_tenant(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FLMG-VC-ELEMENT-1 and FLMG-CAPTURE-TENANT-1 (lane FIX-E) through the REGISTERED worker path
    over the contracts of WLD-F-15 that are in flight at the cutover: the legacy-source port hands
    the 16 rows of Contract 1 and Contract 2 (both set up on 1 Jan 2023). Contracts 3 and 4 were
    set up on 1 Feb 2023, AFTER the 31 Jan 2023 cutover — ENGINE_SPEC S07-R-02 books them at that
    date while S07-R-01 dates the opening balance on the cutover and S01-R-15 refuses an event
    before the inception: ruled 2026-09-30 (no opening balance for such a contract), its capture
    shape open — not exercised here. The shipped file is read, never rewritten (DG-ARC-05).

    (1) ENGINE_SPEC S07-R-11 / POL-213 (S01-R-06): Contract 2's ``VC #1`` row (stated price -100)
    is a VC line of the booking AND the contract-level element ``Contract 2/VC-VC #1`` — version 1,
    ``ENTERED_AMOUNT``, ``DECREASE`` 100, ``allocation_target = CONTRACT``, effective at the
    inception, its ``ESTIMATE_CHANGED`` (origin MIGRATION) between the booking and the activation —
    so the engine prices the contract at 900.00 (PRD WLD-X-27 "TP C2"; the legacy allocation
    470.77 / 313.85 / 115.38 / 0.00) and S07-R-03 accepts Σ X_i = 900. On the pre-fix source the
    element was never written: the price was 1,000.00 and the job FAILED with
    OPENING_BALANCE_INCONSISTENT (check ``transaction_price``). Contract 1 has no VC row and keeps
    the three-event stream at 1,300.00. (2) 04 T-MIG-04 / T-MIG-05 are RLS-T: every capture row
    carries the tenant; on the pre-fix source the insert omitted ``tenant_id`` and PostgreSQL
    refused it ("new row violates row-level security policy"), the job ending in its sanitized
    500. (3) BS3-D-26: nothing of the dry run survives — no ``contract``, ``estimate`` or
    ``estimate_version`` row. (4) FLMG-ONBOARDING-METHOD-PIN-1 (05 RCP-15 rev 1.36): the two
    contracts are computed under POL-210's mode (a) method at contract level, so the capture holds
    the imported cumulative amounts PRD WLD-X-27 and ENGINE_SPEC EX-07-A state (Contract 1 revenue
    295.69, net 4.31; Contract 2 58.85, -58.85, reclass 58.85); on the pre-fix source the registry
    default ``RECOMPUTE_FROM_INCEPTION`` applied and the capture held revenue 0.00."""
    files = LocalFileStore(app_settings.file_root)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    stamp_test_release()
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    _publish_parity_templates(tenant_id)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    in_flight = tuple(
        row for row in legacy_db.rows(FIXTURE) if row.contract_external_id in IN_FLIGHT
    )
    assert len(in_flight) == 16
    ssp_rows = legacy_db.sku_ssp_rows(FIXTURE)
    monkeypatch.setattr(
        jobs, "legacy_source_with_ssp", lambda jc, uow, batch: (in_flight, ssp_rows)
    )
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        with FIXTURE.open("rb") as stream:
            stored = store_file(
                uow,
                purpose=FilePurpose.LEGACY_DATABASE,
                stream=stream,
                original_filename=FIXTURE.name,
                media_type="application/vnd.sqlite3",
            )
        calendar = fiscal_calendar_values(tenant_id)
        uow.session.execute(insert(fiscal_calendar).values(**calendar))
        uow.session.execute(
            insert(period).values(
                **period_values(
                    tenant_id,
                    calendar_id=calendar["id"],
                    fiscal_year=2023,
                    period_no=1,
                    start_date=date(2023, 1, 1),
                    end_date=date(2023, 1, 31),
                )
            )
        )
        currency = str(
            uow.session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == tenant_id)
            ).scalar_one()
        ).strip()
        batch = migration_batch_values(
            tenant_id,
            source_file_id=stored["id"],
            status="PROFILED",
            profile=legacy_db.profile(FIXTURE).as_json(),
        )
        uow.session.execute(insert(migration_batch).values(**batch))
        uow.commit()
    replay = _replay_request_as_user(someone, tenant_id, clock, keyring, files, batch["id"])
    assert str(replay["status"]) == "APPROVED", replay
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        row = registry.insert_job(
            uow.session,
            JobKind.MIGRATION_IMPORT,
            {
                "migration_id": str(batch["id"]),
                "phase": "IMPORT",
                "batch_parameters": {},
                "entity_mapping": [
                    {
                        "legacy_name": name,
                        "entity_code": name,
                        "calendar_id": None,
                        "time_zone": None,
                    }
                    for name in ENTITIES
                ],
                "resolved_entities": [
                    {
                        "legacy_name": name,
                        "entity_code": name,
                        "functional_currency": currency,
                        "calendar_id": str(calendar["id"]),
                        "time_zone": "UTC",
                    }
                    for name in ENTITIES
                ],
                "create_missing_entities": True,
                "create_missing_products": True,
                "ssp_replay_request_id": str(replay["id"]),
                "sku_ssp_sha256": batch["profile"]["sku_ssp_sha256"],
            },
            tenant_id=tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            uow.session,
            job_id=row["id"],
            tenant_id=tenant_id,
            queue=str(row["queue"]),
            now=clock.now(),
        )
        uow.commit()
    job_id = UUID(str(row["id"]))
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(context) as session:
        state, problem = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == job_id)
        ).one()
        assert state == "SUCCEEDED", _problem_text(problem)
        status, profile = session.execute(
            select(migration_batch.c.status, migration_batch.c.profile).where(
                migration_batch.c.id == batch["id"]
            )
        ).one()
        assert status == "IMPORTED"
        assert (profile["contracts"], profile["obligations"], profile["vc_elements"]) == (2, 7, 1)
        assert (profile["captured_versions"], profile["captured_obligation_versions"]) == (2, 8)
        # (2) the capture rows are the tenant's — every row of both tables
        versions = (
            session.execute(
                select(migration_population_version).where(
                    migration_population_version.c.migration_batch_id == batch["id"]
                )
            )
            .mappings()
            .all()
        )
        captured = (
            session.execute(
                select(migration_population_obligation).where(
                    migration_population_obligation.c.migration_batch_id == batch["id"]
                )
            )
            .mappings()
            .all()
        )
        assert [v["tenant_id"] for v in versions] == [tenant_id] * 2
        assert [c["tenant_id"] for c in captured] == [tenant_id] * 8
        by_contract = {str(v["members"][0]["contract_external_id"]): v for v in versions}
        assert sorted(by_contract) == list(IN_FLIGHT)
        # (1) the retained producing input of each version (T-CON-25 evidence, verified as the
        # reconcile verifies it): Contract 2's stream carries the element's ESTIMATE_CHANGED
        # between the booking and the activation; Contract 1's stream has three events
        streams: dict[str, Any] = {}
        for name, version in by_contract.items():
            repository.verify_input_evidence(version)
            streams[name] = decode_input(canonical_bytes(version["input_evidence"]))
        assert [(e.event_type, e.origin) for e in streams["Contract 2"].events] == [
            ("CONTRACT_BOOKED", "MIGRATION"),
            ("ESTIMATE_CHANGED", "MIGRATION"),
            ("CONTRACT_ACTIVATED", "MIGRATION"),
            ("OPENING_BALANCE_ESTABLISHED", "MIGRATION"),
        ]
        assert by_contract["Contract 2"]["opening_event_key"] == "Contract 2/EV-000004"
        (element,) = streams["Contract 2"].estimate_versions
        assert (element.estimate_key, element.version_no) == ("Contract 2/VC-VC %231", 1)
        assert (element.estimate_kind, element.method) == (
            "VARIABLE_CONSIDERATION",
            "ENTERED_AMOUNT",
        )
        assert (element.direction, element.constrained_amount) == ("DECREASE", Decimal(100))
        assert (element.allocation_target, element.status) == ("CONTRACT", "APPROVED")
        assert element.effective_date == date(2023, 1, 1) and element.currency == currency
        assert streams["Contract 2"].events[1].estimate_version_key == element.version_key
        assert [e.event_type for e in streams["Contract 1"].events] == [
            "CONTRACT_BOOKED",
            "CONTRACT_ACTIVATED",
            "OPENING_BALANCE_ESTABLISHED",
        ]
        assert by_contract["Contract 1"]["opening_event_key"] == "Contract 1/EV-000003"
        assert streams["Contract 1"].estimate_versions == ()
        # the engine's allocation of each contract sums to the legacy transaction price (PRD
        # WLD-X-27: TP C1 1,300.00, C2 900.00); the VC line is an obligation of kind VC_LINE at 0
        allocated = {
            (str(c["contract_external_id"]), str(c["obligation_key"])): (
                str(c["obligation_kind"]),
                Decimal(str(c["row"]["allocated_amount"])),
            )
            for c in captured
        }
        assert allocated == {
            ("Contract 1", "POB #1"): ("STANDARD", Decimal("322.10")),
            ("Contract 1", "POB #2"): ("STANDARD", Decimal("237.07")),
            ("Contract 1", "POB #3"): ("STANDARD", Decimal("96.63")),
            ("Contract 1", "POB #4"): ("MATERIAL_RIGHT", Decimal("644.20")),
            ("Contract 2", "POB #1"): ("STANDARD", Decimal("470.77")),
            ("Contract 2", "POB #2"): ("STANDARD", Decimal("313.85")),
            ("Contract 2", "POB #3"): ("STANDARD", Decimal("115.38")),
            ("Contract 2", "VC #1"): ("VC_LINE", Decimal(0)),
        }
        assert sum(a for (name, _), (_, a) in allocated.items() if name == "Contract 2") == 900
        assert sum(a for (name, _), (_, a) in allocated.items() if name == "Contract 1") == 1300
        # (4) POL-210 mode (a) at contract level: the imported balances are the opening state
        _assert_the_capture_holds_the_imported_balances(session, batch["id"])
        # (3) the dry run's rows rolled back with its savepoint
        for table in (contract, estimate, estimate_version):
            assert session.execute(select(func.count()).select_from(table)).scalar_one() == 0


def test_same_operation_recovery_and_terminal_hook_over_a_durable_capture(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    files = LocalFileStore(app_settings.file_root)
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    operation = UUID(int=4242)
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        uow.session.execute(insert(file_object).values(**file_row))
        # an IMPORTED batch whose durable capture was written by ``operation`` (one version, one
        # obligation version; the builders' hashes are consistent)
        batch = migration_batch_values(
            tenant_id,
            source_file_id=file_row["id"],
            status="IMPORTED",
            capture_operation_id=operation,
            profile={"contracts": 1, "legacy_pob_rows": 1},
        )
        uow.session.execute(insert(migration_batch).values(**batch))
        version = migration_population_version_values(
            tenant_id, migration_batch_id=batch["id"], capture_operation_id=operation
        )
        uow.session.execute(insert(migration_population_version).values(**version))
        captured = migration_population_obligation_values(
            tenant_id,
            migration_batch_id=batch["id"],
            population_version_id=version["id"],
            capture_operation_id=operation,
            contract_version_id=version["contract_version_id"],
            obligation_version_id=version["obligation_version_ids"][0],
            contract_id=UUID(version["members"][0]["contract_id"]),
        )
        uow.session.execute(insert(migration_population_obligation).values(**captured))
        uow.commit()
    # same operation → recovered from the stored capture: reads only, the batch unchanged
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        profile = jobs.import_batch(uow, batch["id"], job_id=operation, rows=())
        assert profile["recovered"] is True and profile["captured_versions"] == 1
    with tenant_session(context) as session:
        row = session.execute(
            select(migration_batch.c.status, migration_batch.c.row_version).where(
                migration_batch.c.id == batch["id"]
            )
        ).one()
        assert row[0] == "IMPORTED" and row[1] == batch.get("row_version", row[1])
    # another job (operation) finds the batch IMPORTED under a foreign capture → refused by name
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        with pytest.raises(Problem) as refused:
            jobs.import_batch(uow, batch["id"], job_id=UUID(int=4243), rows=())
        assert (refused.value.detail or "").startswith(
            repository.FOREIGN_CAPTURE_COPY.split("{")[0]
        )
    # the terminal hook of the same operation leaves the verified capture untouched
    problem = {"instance": f"/api/v1/jobs/{operation}", "detail": "worker lost", "status": 500}
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        jobs.import_failed(uow, {"migration_id": str(batch["id"])}, problem)
        uow.commit()
    with tenant_session(context) as session:
        status = session.execute(
            select(migration_batch.c.status).where(migration_batch.c.id == batch["id"])
        ).scalar_one()
        assert status == "IMPORTED"
    # a PROFILED batch whose import failed terminally ends FAILED with the problem (E-76)
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        profiled = migration_batch_values(
            tenant_id, source_file_id=file_row["id"], status="PROFILED"
        )
        uow.session.execute(insert(migration_batch).values(**profiled))
        uow.commit()
    with unit_of_work(_ctx(tenant_id, clock), clock=clock, keyring=keyring, files=files) as uow:
        jobs.import_failed(uow, {"migration_id": str(profiled["id"])}, problem)
        uow.commit()
    with tenant_session(context) as session:
        row = session.execute(
            select(migration_batch.c.status, migration_batch.c.problem).where(
                migration_batch.c.id == profiled["id"]
            )
        ).one()
        assert row[0] == "FAILED" and row[1]["detail"] == "worker lost"

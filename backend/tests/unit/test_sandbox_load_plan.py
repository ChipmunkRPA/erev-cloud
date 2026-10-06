"""SNP-2 sandbox load — the pure part (BUILD_SPEC SNP-2; 04 rev 1.67 API-R-04 / T-PLT-34 / §15.4-B /
§16.14; 05 SBX-04 to SBX-06 rev 1.20; D-98 candidate 137 with amendments 1 and 2). CPU-only: the
load params and the derived API-S-Job ``mode``, the sandbox code, the manifest verification against
the running registry, the typed decoding of JSONL rows with ``tenant_id`` re-stamping and deferred
references, the load plan, the refusal rule ids on existing slugs, and the load report."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from erev_api.db.tables import metadata
from erev_api.domain.platform import jobs as platform_jobs
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.problems import Problem
from erev_api.schemas.common import JOB_MODE_EXPORT, JOB_MODE_RESTORE, job_mode

SANDBOX = UUID("01a0c1a2-0000-7000-8000-000000000001")
USER = UUID("01a0c1a2-0000-7000-8000-000000000002")
SOURCE = UUID("01a0c1a2-0000-7000-8000-000000000003")


def test_load_params_round_trip_and_mode() -> None:
    restore = sb.load_params_of(
        sandbox_tenant_id=SANDBOX, name="Q3 review", requested_by=USER, restore=True
    )
    copy = sb.load_params_of(
        sandbox_tenant_id=SANDBOX, name="Q3 review", requested_by=USER, restore=False
    )
    assert set(restore) == {"load"} and set(copy) == {"sandbox"}
    parsed = sb.parse_load({"tenant_snapshot_id": "x", **restore})
    assert parsed is not None and parsed.restore and parsed.sandbox_tenant_id == SANDBOX
    assert parsed.requested_by == USER and parsed.name == "Q3 review"
    parsed_copy = sb.parse_load({**copy})
    assert parsed_copy is not None and not parsed_copy.restore
    assert sb.parse_load({"tenant_snapshot_id": "x"}) is None  # an export-only job
    # API-S-Job mode (04 rev 1.67; D-98 137 (1)): derived from params, never stored
    assert job_mode("TENANT_SNAPSHOT", restore) == JOB_MODE_RESTORE == sb.MODE_RESTORE
    assert job_mode("TENANT_SNAPSHOT", copy) == JOB_MODE_EXPORT == sb.MODE_EXPORT
    assert job_mode("TENANT_SNAPSHOT", None) == JOB_MODE_EXPORT
    assert job_mode("CLOSE_RUN", {"load": {}}) is None
    assert sb.job_mode("TENANT_SNAPSHOT", restore) == JOB_MODE_RESTORE
    # ... so every job read selects them: without `params` each answer said `export`
    assert "params" in {column.name for column in platform_jobs.JOB_COLUMNS}
    # a SYSTEM request carries no user: parse keeps None, the loader refuses by name before writing
    system = sb.parse_load(
        sb.load_params_of(sandbox_tenant_id=SANDBOX, name="n", requested_by=None, restore=True)
    )
    assert system is not None and system.requested_by is None
    with pytest.raises(Problem) as info:
        sb.parse_load({"load": {"sandbox_tenant_id": "not-a-uuid", "name": "n"}})
    assert info.value.slug == "validation-failed"
    with pytest.raises(Problem):
        sb.parse_load({"load": {"sandbox_tenant_id": str(SANDBOX), "name": "  "}})


def test_sandbox_code_is_a_t_plt_01_code() -> None:
    from erev_api.domain.platform.provisioning import TENANT_CODE, TENANT_CODE_LENGTH

    for name in ("Q3 review", "My Sandbox! 2026", "  ", "ÄÖÜ", "x" * 200, "a-b-c"):
        code = sb.sandbox_code(name)
        assert TENANT_CODE.fullmatch(code), (name, code)
        assert len(code) in TENANT_CODE_LENGTH, (name, code)
        assert code.startswith("sbx-")
    assert sb.sandbox_code("Q3 review") == "sbx-q3-review"


def test_refusals_ride_existing_slugs_with_rule_ids() -> None:
    # D-98 candidate 137 amendment 1: no new §15.2 slug; the SNP-1 precedent
    cases = (
        (sb.not_loadable("x"), "precondition-failed", sb.RULE_NOT_LOADABLE),
        (sb.registry_mismatch("x"), "precondition-failed", sb.RULE_REGISTRY),
        (sb.digest_mismatch("x"), "precondition-failed", sb.RULE_DIGEST),
        (sb.budget_exceeded([SANDBOX]), "precondition-failed", sb.RULE_BUDGET),
        (sb.actor_required(), "forbidden", sb.RULE_ACTOR),
        (sb.sandbox_name_taken("sbx-x"), "validation-failed", sb.RULE_NAME_TAKEN),
    )
    for problem, slug, rule_id in cases:
        assert problem.slug == slug and [e.rule_id for e in problem.errors] == [rule_id], slug
    assert sb.sandbox_name_taken("sbx-x").errors[0].field == "name"
    assert str(SANDBOX) in sb.budget_exceeded([SANDBOX]).errors[0].message


def _manifest_document(**overrides: object) -> dict[str, object]:
    inv = sd.inventory()
    document: dict[str, object] = {
        "format_version": sd.MANIFEST_FORMAT_VERSION,
        "source_tenant_id": str(SOURCE),
        "known_at": "2026-09-12T12:00:00+00:00",
        "purpose": "STORED_BACKUP",
        "datasets": [
            {"name": d.name, "sha256": sd.EMPTY_SHA256, "row_count": 0} for d in inv.datasets
        ],
    }
    document.update(overrides)
    return document


def test_manifest_verified_against_the_running_registry() -> None:
    inv = sd.inventory()
    plan = sb.verify_manifest(_manifest_document(), inv)
    assert plan.source_tenant_id == SOURCE and plan.purpose == "STORED_BACKUP"
    assert plan.known_at == datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert [d.name for d in plan.datasets] == [d.name for d in inv.datasets]
    copied = {d.name for d in inv.datasets if d.snapshot_class is sd.SnapshotClass.COPIED}
    assert {d.name for d in plan.datasets if d.load_rows} == copied
    replay = {d.name for d in plan.datasets if not d.load_rows}
    assert replay == {"period_state", "period_state_transition", "period_lock"}  # REPLAY_REFERENCE
    assert sb.plan_load(plan) == ()  # every dataset empty: nothing to insert
    # refusals, each by name (SNAPSHOT_REGISTRY_MISMATCH)
    for bad in (
        _manifest_document(format_version=sd.MANIFEST_FORMAT_VERSION + 1),
        _manifest_document(datasets=[]),
        _manifest_document(datasets=list(reversed(_manifest_document()["datasets"]))),  # type: ignore[arg-type]
        _manifest_document(purpose="OTHER"),
        _manifest_document(known_at="not a time"),
    ):
        with pytest.raises(Problem) as info:
            sb.verify_manifest(bad, inv)
        assert info.value.slug == "precondition-failed"
        assert info.value.errors[0].rule_id == sb.RULE_REGISTRY
    document = _manifest_document()
    document["datasets"][0]["sha256"] = "zz"  # type: ignore[index]
    with pytest.raises(Problem):
        sb.verify_manifest(document, inv)


def test_entry_verification_and_plan_order() -> None:
    inv = sd.inventory()
    document = _manifest_document()
    entries = document["datasets"]
    assert isinstance(entries, list)
    digest = hashlib.sha256(b'{"id": "x"}\n').hexdigest()
    for entry in entries:
        if entry["name"] in ("contract", "customer", "contract_event"):
            entry.update({"sha256": digest, "row_count": 1})
    plan = sb.verify_manifest(document, inv)
    planned = sb.plan_load(plan)
    assert [d.name for d in planned] == sorted(
        [d.name for d in planned], key=lambda n: inv.dataset(n).load_position
    )
    assert {d.name for d in planned} == {"contract", "customer", "contract_event"}
    contract = next(d for d in planned if d.name == "contract")
    sb.verify_entry(contract, stored_sha256=digest, decoded_rows=1)
    with pytest.raises(Problem) as info:
        sb.verify_entry(contract, stored_sha256="0" * 64, decoded_rows=1)
    assert info.value.errors[0].rule_id == sb.RULE_DIGEST
    with pytest.raises(Problem):
        sb.verify_entry(contract, stored_sha256=digest, decoded_rows=2)


def test_coerce_row_restamps_tenant_and_types_and_holds_deferred() -> None:
    inv = sd.inventory()
    # a nullable reference to a table that loads LATER is held back for the fixup step
    # (combination_group → judgement_record; FIX-D1: a self-reference no longer is)
    dataset = inv.dataset("combination_group")
    assert dataset.deferred == ("judgement_record_id",)
    table = metadata.tables["erev.combination_group"]
    row = {
        "tenant_id": str(SOURCE),
        "id": str(SANDBOX),
        "judgement_record_id": str(USER),
        "created_at": "2026-09-12T12:00:00+00:00",
        "inception_date": "2026-01-01",
        "code": "G1",
    }
    values, held = sb.coerce_row(table, row, tenant_id=SANDBOX, deferred=dataset.deferred)
    assert values["tenant_id"] == SANDBOX  # re-stamped, the source's id never travels
    assert values["id"] == SANDBOX and isinstance(values["id"], UUID)
    assert values["judgement_record_id"] is None and held == {"judgement_record_id": USER}
    assert values["created_at"] == datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert values["code"] == "G1" and values["inception_date"] == date(2026, 1, 1)
    assert "rationale" not in values  # absent columns are left to the database
    # a self-reference is inserted with its row: nothing is held (the rows load referenced-first)
    entity = inv.dataset("legal_entity")
    assert entity.deferred == () and entity.self_references == ("parent_entity_id",)
    values, held = sb.coerce_row(
        metadata.tables["erev.legal_entity"],
        {"id": str(SANDBOX), "parent_entity_id": str(USER), "code": "E1"},
        tenant_id=SANDBOX,
        deferred=entity.deferred,
    )
    assert values["parent_entity_id"] == USER and held == {}
    # a GENERATED column is never inserted: the database derives it and refuses a supplied value
    mapping_rule = metadata.tables["erev.account_mapping_rule"]
    assert mapping_rule.c.specificity.computed is not None
    values, held = sb.coerce_row(
        mapping_rule,
        {"id": str(SANDBOX), "priority": 3, "specificity": 8, "entity_id": str(USER)},
        tenant_id=SANDBOX,
    )
    assert "specificity" not in values and values["priority"] == 3 and values["entity_id"] == USER
    assert {
        (t.name, c.name) for t in metadata.tables.values() for c in t.columns if c.computed
    } == {
        ("account_mapping_rule", "specificity"),  # the one generated column of a COPIED table
        ("subledger_line", "dr_cr"),  # REGENERATED: never loaded
    }
    # numeric / date / array coercion on a synthetic table
    probe = sa.Table(
        "probe",
        sa.MetaData(),
        sa.Column("tenant_id", sa.Uuid()),
        sa.Column("amount", sa.Numeric(18, 6)),
        sa.Column("on_date", sa.Date()),
        sa.Column("ids", sa.ARRAY(sa.Uuid())),
        sa.Column("flag", sa.Boolean()),
        sa.Column("data", sa.JSON()),
    )
    values, held = sb.coerce_row(
        probe,
        {
            "amount": "12.500000",
            "on_date": "2026-01-31",
            "ids": [str(USER)],
            "flag": True,
            "data": {"a": 1},
        },
        tenant_id=SANDBOX,
    )
    assert values["amount"] == Decimal("12.500000") and values["on_date"] == date(2026, 1, 31)
    assert values["ids"] == [USER] and values["flag"] is True and values["data"] == {"a": 1}
    assert held == {}


def test_load_report_is_canonical_and_names_findings() -> None:
    blocked = sb.BlockedPeriod(uuid4(), uuid4(), "ASC606", uuid4(), "open → closed", "open", "gate")
    report = sb.LoadReport(
        sandbox_tenant_id=SANDBOX,
        source_tenant_id=SOURCE,
        tenant_snapshot_id=USER,
        known_at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        loaded_at=datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        row_counts={"contract": 2, "customer": 1},
        groups_recomputed=3,
        compared=3,
        mismatches=(
            {
                "combination_group_id": "g",
                "book_code": "ASC606",
                "source_sha256": "a",
                "sandbox_sha256": "b",
            },
        ),
        blocked_periods=(blocked,),
    )
    assert report.derived_mismatches == 1
    content = sb.report_bytes(report)
    assert content.endswith(b"\n")
    document = json.loads(content)
    assert list(document) == sorted(document)  # canonical: sorted keys
    assert document["derived_mismatches"] == 1 and document["groups_recomputed"] == 3
    assert document["blocked_periods"][0]["attempted"] == "open → closed"
    assert document["format_version"] == sb.LOAD_REPORT_FORMAT_VERSION
    assert sb.report_bytes(report) == content  # deterministic
    assert sb.LOAD_REPORT_PURPOSE == "AUDIT_DIGEST"  # E-68 widened in 04 rev 1.67


def test_audit_actions_and_header_names() -> None:
    assert sb.ACTION_REQUESTED == "tenant.sandbox_requested"
    assert sb.ACTION_LOADED == "tenant.snapshot_loaded"
    assert sb.ACTION_RESTORED == "tenant.sandbox_restored"
    assert sb.SANDBOX_ID_HEADER == "X-Erev-Sandbox-Tenant-Id"
    assert sb.EXCEPTION_REPLAY_BLOCKED == "SANDBOX_REPLAY_BLOCKED"
    assert sb.EXCEPTION_DETERMINISM == "SANDBOX_DETERMINISM_MISMATCH"

"""``TENANT_SNAPSHOT`` handler, the pure orchestration with fakes (BUILD_SPEC SNP-1 slice I-2; 05
SBX-02, SBX-03, SBX-06, SBX-11; T-PLT-34; lane record §13.2). No database.

The handler module registers its kind through ``jobs.registry.task`` on import. ``TENANT_SNAPSHOT``
is still listed in ``PENDING_JOB_HANDLERS`` (the worker's ``HANDLER_MODULES`` line is P2's
post-merge slice), so this module imports the handler lazily inside a fixture and removes the
registration at teardown; the DG-ARC-08 registries test runs first by collection rank and never
sees it.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, BinaryIO
from uuid import UUID

import pytest
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.enums import FilePurpose, JobKind, TenantKind
from erev_api.jobs import registry
from erev_api.problems import Problem

KNOWN_AT = datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC)
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
BEFORE = KNOWN_AT - timedelta(days=10)
AFTER = KNOWN_AT + timedelta(days=1)
TENANT = UUID(int=0x7)
SNAPSHOT = UUID(int=0x5)
CONTRACT_A, CONTRACT_B, CUSTOMER = UUID(int=0xA1), UUID(int=0xA2), UUID(int=0xC1)
FILE_1, FILE_2, ATTACHMENT = UUID(int=0xF1), UUID(int=0xF2), UUID(int=0xE1)
JUDGEMENT, REQUEST, STEP, DECISION = (
    UUID(int=0x11),
    UUID(int=0x100),
    UUID(int=0x101),
    UUID(int=0x102),
)
ROUTE = Path(__file__).resolve().parents[2] / "erev_api/api/v1/tenant.py"


@pytest.fixture(scope="module")
def job() -> Iterator[ModuleType]:
    """The handler module, registered for the test and deregistered afterwards. ``task`` refuses a
    second registration and a module imports once per process, so an already-imported module is
    re-registered by hand."""
    from erev_api.domain.platform import snapshot_job

    present = JobKind.TENANT_SNAPSHOT in registry.HANDLERS  # the worker registers it (DG-ARC-08)
    if not present:
        registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        )
    yield snapshot_job
    if not present:  # pop only what this fixture registered
        registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


def _u(n: int) -> UUID:
    return UUID(int=n)


def _row(**extra: Any) -> dict[str, Any]:
    return {
        "tenant_id": TENANT,
        "id": SNAPSHOT,
        "known_at": KNOWN_AT,
        "purpose": "STORED_BACKUP",
        "status": "QUEUED",
        "target_tenant_id": None,
        "manifest_file_id": None,
        "manifest_sha256": None,
        "row_counts": None,
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        **extra,
    }


class FakeRepo:
    def __init__(self, row: Mapping[str, Any], kind: TenantKind = TenantKind.PRODUCTION) -> None:
        self.row = dict(row)
        self.kind = kind
        self.transitions: list[tuple[str, str, dict[str, Any]]] = []
        self.audits: list[dict[str, Any]] = []
        self.locks: list[UUID] = []

    @property
    def now(self) -> datetime:
        return NOW

    def load(self, snapshot_id: UUID) -> Mapping[str, Any]:
        if snapshot_id != self.row["id"]:
            raise Problem("not-found")
        return dict(self.row)

    def source_kind(self, tenant_id: UUID) -> TenantKind:
        assert tenant_id == TENANT
        return self.kind

    def take_copy_lock(self, tenant_id: UUID) -> None:
        self.locks.append(tenant_id)

    def transition(
        self,
        snapshot_id: UUID,
        *,
        to_status: str,
        set_values: Mapping[str, Any],
        expected_status: str,
    ) -> Mapping[str, Any]:
        assert snapshot_id == self.row["id"] and self.row["status"] == expected_status
        self.row.update(set_values)
        self.row["status"] = to_status
        self.transitions.append((expected_status, to_status, dict(set_values)))
        return dict(self.row)

    def audit(self, **event: Any) -> None:
        self.audits.append(event)


def _world() -> dict[str, list[dict[str, Any]]]:
    """Two contracts (B after known_at), one customer, two files (F2 unreferenced), one attachment
    on A, one judgement record on A with an approval request, step and decision."""
    return {
        "customer": [{"id": CUSTOMER, "created_at": BEFORE}],
        "contract": [
            {"id": CONTRACT_A, "created_at": BEFORE, "customer_id": CUSTOMER},
            {"id": CONTRACT_B, "created_at": AFTER, "customer_id": CUSTOMER},
        ],
        "file_object": [
            {
                "id": f,
                "created_at": BEFORE,
                "sha256": "a" * 64,
                "purpose": "ATTACHMENT",
                "retention_until": None,
                "legal_hold": False,
            }
            for f in (FILE_1, FILE_2)
        ],
        "file_attachment": [
            {
                "id": ATTACHMENT,
                "created_at": BEFORE,
                "file_object_id": FILE_1,
                "subject_type": "contract",
                "subject_id": CONTRACT_A,
            }
        ],
        "judgement_record": [
            {
                "id": JUDGEMENT,
                "created_at": BEFORE,
                "subject_type": "contract",
                "subject_id": CONTRACT_A,
                "approval_request_id": REQUEST,
            }
        ],
        "approval_request": [
            {
                "id": REQUEST,
                "created_at": BEFORE,
                "subject_type": "JUDGEMENT_RECORD",
                "subject_id": JUDGEMENT,
                "impact_preview_file_id": None,
            }
        ],
        "approval_step": [{"id": STEP, "approval_request_id": REQUEST}],
        "approval_decision": [
            {"id": DECISION, "approval_request_id": REQUEST, "decided_at": BEFORE}
        ],
    }


class FakeReader:
    def __init__(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        counts_after: Mapping[str, int] | None = None,
    ) -> None:
        self.tables = tables
        self.calls = 0
        self.counts_after = counts_after

    def rows(self, dataset: sd.Dataset) -> Sequence[Mapping[str, Any]]:
        return list(self.tables.get(dataset.name, ()))

    def counts(self) -> Mapping[str, int]:
        self.calls += 1
        if self.calls > 1 and self.counts_after is not None:
            return dict(self.counts_after)
        return {name: len(rows) for name, rows in self.tables.items()}

    def engine_release(self) -> str | None:
        return "1.0.0"

    def retention_policy(self) -> Any:
        return CONFIRMED_RETENTION


CONFIRMED_RETENTION = sd.RetentionPolicy(
    families=sd.RETENTION_FAMILIES,
    source=(
        "registry version 00000000-0000-0000-0000-00000000abcd approved by "
        "00000000-0000-0000-0000-000000000099 at 2026-06-29T09:30:00+00:00"
    ),
)


class FakeWriter:
    """A byte-capture writer over the streaming protocol of slice I-3: reads each stream to the
    end, keeps the bytes, and answers like ``put_file`` (row with id, sha256, size_bytes)."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str, UUID]] = {}
        self.stream_kinds: dict[str, str] = {}

    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        content = stream.read()
        file_id = _u(0x1000 + len(self.files))
        self.files[name] = (content, media_type, file_id)
        self.stream_kinds[name] = type(stream).__name__
        return {
            "id": file_id,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }


def _params(job: ModuleType, **changes: Any) -> Any:
    return job.parse_params(
        {
            "tenant_snapshot_id": str(SNAPSHOT),
            "known_at": "2026-06-30T23:59:59Z",
            "purpose": "STORED_BACKUP",
            **changes,
        }
    )


# --- params ---------------------------------------------------------------------------------------


def test_parse_params_requires_every_field_and_an_offset(job: ModuleType) -> None:
    parsed = _params(job)
    assert (parsed.tenant_snapshot_id, parsed.known_at, parsed.purpose) == (
        SNAPSHOT,
        KNOWN_AT,
        "STORED_BACKUP",
    )
    assert _params(job, known_at="2026-07-01T01:59:59+02:00").known_at == KNOWN_AT
    for field, value in (
        ("tenant_snapshot_id", "not-a-uuid"),
        ("known_at", "2026-06-30 23:59:59"),  # no offset
        ("known_at", None),
        ("purpose", "PRODUCTION_RESTORE"),
    ):
        with pytest.raises(Problem) as info:
            _params(job, **{field: value})
        assert info.value.slug == "validation-failed"
        assert [e.field for e in info.value.errors] == [field]


# --- the export -----------------------------------------------------------------------------------


def test_export_writes_one_file_per_dataset_and_the_manifest(job: ModuleType) -> None:
    repo, reader, writer = FakeRepo(_row()), FakeReader(_world()), FakeWriter()
    beats: list[int] = []
    result = job.export_snapshot(
        repo, reader, writer, params=_params(job), heartbeat=lambda: beats.append(1)
    )
    inv = sd.inventory()
    assert result.status == "SUCCEEDED" and result.already_done is False
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING"), ("RUNNING", "SUCCEEDED")]
    assert repo.transitions[0][2] == {"started_at": NOW}
    assert repo.locks == [TENANT]  # the 05 §5.6 copy lock, once, before RUNNING
    assert [a["action"] for a in repo.audits] == [job.ACTION_STARTED, job.ACTION_CREATED]
    assert repo.audits[1]["detail"]["audit_history_carried"] is False
    assert len(beats) == 2 * len(inv.datasets)
    # one JSONL file per dataset with rows (I-3: an empty dataset is not stored) plus the manifest
    assert set(writer.files) == {f"{n}.jsonl" for n, c in result.row_counts.items() if c} | {
        job.MANIFEST_NAME
    }
    assert len(result.row_counts) == len(inv.datasets) and len(writer.files) < len(inv.datasets)
    assert all(
        m == job.DATASET_MEDIA_TYPE for n, (_, m, _) in writer.files.items() if n != "manifest.json"
    )
    # the known_at cutoff and the selectors: contract B, file F2 are out; the approval travels
    assert result.row_counts["contract"] == 1 and result.row_counts["file_object"] == 1
    assert (
        result.row_counts["approval_request"] == 1 and result.row_counts["approval_decision"] == 1
    )
    assert result.row_counts["file_attachment"] == 1 and result.row_counts["judgement_record"] == 1
    contract_lines = writer.files["contract.jsonl"][0].split(b"\n")[:-1]
    assert len(contract_lines) == 1 and str(CONTRACT_A).encode() in contract_lines[0]
    manifest = json.loads(writer.files[job.MANIFEST_NAME][0])
    assert manifest["format_version"] == 2 and manifest["purpose"] == "STORED_BACKUP"
    assert manifest["known_at"] == "2026-06-30T23:59:59.000000Z"
    assert len(manifest["datasets"]) == len(inv.datasets)
    assert [f["id"] for f in manifest["retention"]["files"]] == [str(FILE_1)]
    assert manifest["shared"]["engine_release"] == "1.0.0"
    assert manifest["audit_history_carried"] is False
    assert result.manifest_sha256 == hashlib.sha256(writer.files[job.MANIFEST_NAME][0]).hexdigest()
    assert repo.row["manifest_sha256"] == result.manifest_sha256
    assert (
        repo.row["manifest_file_id"] == result.manifest_file_id == writer.files["manifest.json"][2]
    )
    assert repo.row["row_counts"] == result.row_counts and repo.row["finished_at"] == NOW
    # the manifest entries tie to the files
    files = {
        n.removesuffix(".jsonl"): c for n, (c, _, _) in writer.files.items() if n != "manifest.json"
    }
    entries = {e["name"]: e for e in manifest["datasets"]}
    assert all(
        hashlib.sha256(files.get(n, b"")).hexdigest() == e["sha256"] for n, e in entries.items()
    )


def test_succeeded_row_returns_idempotently_without_touching_anything(job: ModuleType) -> None:
    done = _row(
        status="SUCCEEDED",
        manifest_file_id=_u(9),
        manifest_sha256="b" * 64,
        row_counts={"contract": 1},
    )
    repo, reader, writer = FakeRepo(done), FakeReader(_world()), FakeWriter()
    result = job.export_snapshot(repo, reader, writer, params=_params(job))
    assert result.already_done is True and result.manifest_file_id == _u(9)
    assert result.row_counts == {"contract": 1}
    assert repo.transitions == [] and repo.audits == [] and repo.locks == [] and writer.files == {}


@pytest.mark.parametrize(
    ("row", "slug", "detail"),
    [
        (_row(status="FAILED"), "invalid-transition", "failed"),
        (_row(status="RUNNING"), "invalid-transition", "already being exported"),
        (_row(purpose="SANDBOX_COPY"), "validation-failed", "purpose differs"),
        (_row(known_at=KNOWN_AT - timedelta(seconds=1)), "validation-failed", "known_at differs"),
    ],
)
def test_refusals_before_any_transition(
    job: ModuleType, row: dict[str, Any], slug: str, detail: str
) -> None:
    repo, writer = FakeRepo(row), FakeWriter()
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_world()), writer, params=_params(job))
    assert info.value.slug == slug and detail in str(info.value)
    assert repo.transitions == [] and repo.locks == [] and writer.files == {}


def test_known_at_in_the_future_and_a_sandbox_source_are_refused(job: ModuleType) -> None:
    future = _row(known_at=NOW + timedelta(minutes=1))
    with pytest.raises(Problem) as info:
        job.export_snapshot(
            FakeRepo(future),
            FakeReader(_world()),
            FakeWriter(),
            params=_params(job, known_at=(NOW + timedelta(minutes=1)).isoformat()),
        )
    assert info.value.slug == "validation-failed" and job.KNOWN_AT_FUTURE in str(info.value)
    repo = FakeRepo(_row(), kind=TenantKind.SANDBOX)
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_world()), FakeWriter(), params=_params(job))
    assert info.value.slug == "sandbox-restricted" and repo.transitions == [] and repo.locks == []
    with pytest.raises(Problem) as info:
        job.export_snapshot(
            FakeRepo(_row(id=_u(0x99))), FakeReader(_world()), FakeWriter(), params=_params(job)
        )
    assert info.value.slug == "not-found"


def test_a_source_that_changes_during_the_read_is_refused_and_the_row_stays_running(
    job: ModuleType,
) -> None:
    world = _world()
    changed = {name: len(rows) for name, rows in world.items()} | {"contract": 3}
    repo = FakeRepo(_row())
    with pytest.raises(Problem) as info:
        job.export_snapshot(
            repo, FakeReader(world, counts_after=changed), FakeWriter(), params=_params(job)
        )
    assert info.value.slug == "precondition-failed" and "contract: 2 rows before, 3 after" in str(
        info.value
    )
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]  # no SUCCEEDED
    # the failure hook then ends the row FAILED with the problem document the registry stores
    failed = job.fail_snapshot(repo, SNAPSHOT, info.value.to_json(instance="/api/v1/jobs/x"))
    assert failed is not None and failed["status"] == "FAILED" and failed["finished_at"] == NOW
    assert repo.audits[-1]["action"] == job.ACTION_FAILED
    detail = repo.audits[-1]["detail"]
    assert detail["status"] == 412 and str(detail["problem_type"]).endswith("precondition-failed")
    # D-98 cand. 84: the post-write check names the stored datasets and itself, no failed write
    assert detail["check"] == "source_count" and "failed" not in detail
    assert detail["written"] and detail["written"] == sorted(
        detail["written"], key=sd.LOAD_ORDER.index
    )

    # a SUCCEEDED or FAILED row is left alone by the hook
    assert job.fail_snapshot(repo, SNAPSHOT, {"type": "x", "status": 500}) is None
    assert job.fail_snapshot(FakeRepo(_row(status="SUCCEEDED")), SNAPSHOT, {"type": "x"}) is None


# --- registration and wiring boundaries -----------------------------------------------------------


def test_handler_registers_its_kind_and_the_route_does_not_import_it(job: ModuleType) -> None:
    spec = registry.HANDLERS[JobKind.TENANT_SNAPSHOT]
    assert spec.handler is job.tenant_snapshot_export
    assert spec.retry.max_attempts == 1  # 05 §5.6: retry none
    assert spec.on_failure is job.snapshot_failed
    assert registry.JOB_QUEUE[JobKind.TENANT_SNAPSHOT] == "maintenance"
    # the route module stays clear of the handler until P2's HANDLER_MODULES line lands
    assert "snapshot_job" not in ROUTE.read_text(encoding="utf-8")
    assert job.COPY_LOCK.format(tenant_id=TENANT) == f"tenant-copy:{TENANT}"


# --- Codex integration review of 2c87ef9b: F-SNP-I2-R1 (ruling D-98 62) ---------------------------

SSP_BOOK, VERSION_200, VERSION_201 = _u(0x200), _u(0x2000), _u(0x2001)
ENTRY_300, ENTRY_301, RANGE_400, RANGE_401 = _u(0x300), _u(0x301), _u(0x400), _u(0x401)
JUNE_1 = datetime(2026, 6, 1, tzinfo=UTC)
JUNE_29 = datetime(2026, 6, 29, tzinfo=UTC)
JULY_1 = datetime(2026, 7, 1, tzinfo=UTC)


def _ssp_world() -> dict[str, list[dict[str, Any]]]:
    """Codex's exact composition: a 29 June draft version 200 (entry 300, range 400) and a 1 July
    draft version 201 (entry 301, range 401) on one SSP book, known_at 30 June."""
    return {
        "ssp_book": [{"id": SSP_BOOK, "created_at": JUNE_1}],
        "ssp_book_version": [
            {
                "id": VERSION_200,
                "created_at": JUNE_29,
                "effective_from": None,
                "ssp_book_id": SSP_BOOK,
            },
            {
                "id": VERSION_201,
                "created_at": JULY_1,
                "effective_from": None,
                "ssp_book_id": SSP_BOOK,
            },
        ],
        "ssp_entry": [
            {"id": ENTRY_300, "ssp_book_version_id": VERSION_200},
            {"id": ENTRY_301, "ssp_book_version_id": VERSION_201},
        ],
        "ssp_range": [
            {"id": RANGE_400, "ssp_entry_id": ENTRY_300},
            {"id": RANGE_401, "ssp_entry_id": ENTRY_301},
        ],
    }


def test_r1_descendants_of_an_excluded_ssp_version_are_excluded(job: ModuleType) -> None:
    repo, writer = FakeRepo(_row()), FakeWriter()
    result = job.export_snapshot(repo, FakeReader(_ssp_world()), writer, params=_params(job))
    assert result.status == "SUCCEEDED"
    assert (
        result.row_counts["ssp_book_version"] == 1
    )  # version 201 cut by its own rule (before the fix too)
    assert result.row_counts["ssp_entry"] == 1  # entry 301 follows its excluded parent (R1)
    assert result.row_counts["ssp_range"] == 1  # range 401 follows entry 301 transitively (R1)
    entries = writer.files["ssp_entry.jsonl"][0]
    assert str(ENTRY_300).encode() in entries and str(ENTRY_301).encode() not in entries
    ranges = writer.files["ssp_range.jsonl"][0]
    assert str(RANGE_400).encode() in ranges and str(RANGE_401).encode() not in ranges
    assert repo.audits[-1]["detail"]["excluded_descendants"] == {"ssp_entry": 1, "ssp_range": 1}


@pytest.mark.parametrize(
    ("parent", "child", "column", "parent_extra"),
    [
        ("role", "role_permission", "role_id", {}),
        ("rule_set_version", "rule", "rule_set_version_id", {"effective_from": None}),
        ("rule_set_version", "rule_test_case", "subject_id", {"effective_from": None}),
        (
            "account_mapping_version",
            "account_mapping_rule",
            "account_mapping_version_id",
            {"effective_from": None},
        ),
        ("approval_request", "approval_step", "approval_request_id", {}),
        ("ssp_calculator_run", "ssp_calculator_result", "ssp_calculator_run_id", {}),
    ],
)
def test_r1_every_parent_family_follows_its_cut_parent(
    job: ModuleType, parent: str, child: str, column: str, parent_extra: dict[str, Any]
) -> None:
    kept_parent, cut_parent, kept_child, cut_child = _u(0x10), _u(0x11), _u(0x20), _u(0x21)
    # An approval is copied only with its copied subject (both readings, Q-2): the requests anchor
    # on a copied rule_set_version. A rule test case's parent IS its polymorphic subject
    # (candidate 34): the child column is subject_id under subject_type rule_set_version.
    anchor = _u(0x99)
    extra = (
        {"subject_type": "RULE_SET_VERSION", "subject_id": anchor}
        if parent == "approval_request"
        else {}
    )
    child_extra = {"subject_type": "rule_set_version"} if child == "rule_test_case" else {}
    world = {
        parent: [
            {"id": kept_parent, "created_at": JUNE_29, **parent_extra, **extra},
            {"id": cut_parent, "created_at": JULY_1, **parent_extra, **extra},
        ],
        child: [
            {"id": kept_child, column: kept_parent, **child_extra},
            {"id": cut_child, column: cut_parent, **child_extra},
        ],
    }
    if parent == "approval_request":
        world["rule_set_version"] = [{"id": anchor, "created_at": JUNE_29, "effective_from": None}]
    if child == "role_permission":
        world[child] = [
            {"role_id": kept_parent, "permission_code": "contract.read"},
            {"role_id": cut_parent, "permission_code": "contract.read"},
        ]
    result = job.export_snapshot(
        FakeRepo(_row()), FakeReader(world), FakeWriter(), params=_params(job)
    )
    assert (result.row_counts[parent], result.row_counts[child]) == (1, 1), (parent, child)


def test_r1_a_broken_required_reference_refuses_before_success(job: ModuleType) -> None:
    world = _ssp_world()
    world["ssp_entry"].append(
        {"id": _u(0x302), "ssp_book_version_id": _u(0x999)}
    )  # no such version
    repo = FakeRepo(_row())
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(world), FakeWriter(), params=_params(job))
    assert info.value.slug == "validation-failed" and "ssp_entry.ssp_book_version_id" in str(
        info.value
    )
    assert [t[:2] for t in repo.transitions] == [
        ("QUEUED", "RUNNING")
    ]  # never SUCCEEDED, never nulled


# --- Codex retest at 9e001b81: F-SNP-I2-R2 (ruling D-98 71) and the missing-stamp refusal ---------

RUN_500 = _u(0x500)


def test_r2_an_optional_reference_to_a_cut_target_excludes_the_row(job: ModuleType) -> None:
    """Codex's observation at 9e001b81: calculator run 500 predates known_at and names the late
    version 201 through the nullable draft_ssp_book_version_id. Ruling D-98 71: the row is
    excluded — never kept with the link cleared; the audit names the excluded ids and counts."""
    world = _ssp_world()
    world["ssp_calculator_run"] = [
        {"id": RUN_500, "created_at": JUNE_29, "draft_ssp_book_version_id": VERSION_201}
    ]
    repo, writer = FakeRepo(_row()), FakeWriter()
    result = job.export_snapshot(repo, FakeReader(world), writer, params=_params(job))
    assert result.status == "SUCCEEDED"
    assert result.row_counts["ssp_calculator_run"] == 0  # expected run ids: []
    assert "ssp_calculator_run.jsonl" not in writer.files  # no rows → nothing stored (I-3)
    detail = repo.audits[-1]["detail"]
    assert detail["excluded_descendants"] == {
        "ssp_entry": 1,
        "ssp_range": 1,
        "ssp_calculator_run": 1,
    }
    assert detail["excluded_descendant_ids"]["ssp_calculator_run"] == [str(RUN_500)]
    assert detail["excluded_descendant_ids"]["ssp_range"] == [str(RANGE_401)]
    assert "nulled_as_of" not in detail


def test_r3_a_composite_key_table_reports_its_primary_key_identity(job: ModuleType) -> None:
    """Codex I2-R3: role_permission has no id column; the excluded identity in the audit detail is
    the row's primary key within the tenant scope (role_id|permission_code), never "None"."""
    role_kept, role_cut = _u(0x10), _u(0x11)
    world = {
        "role": [
            {"id": role_kept, "created_at": JUNE_29},
            {"id": role_cut, "created_at": JULY_1},
        ],
        "role_permission": [
            {"role_id": role_kept, "permission_code": "contract.read"},
            {"role_id": role_cut, "permission_code": "contract.read"},
        ],
    }
    repo, writer = FakeRepo(_row()), FakeWriter()
    result = job.export_snapshot(repo, FakeReader(world), writer, params=_params(job))
    assert result.row_counts["role_permission"] == 1
    detail = repo.audits[-1]["detail"]
    assert detail["excluded_descendant_ids"]["role_permission"] == [f"{role_cut}|contract.read"]
    assert "None" not in json.dumps(detail["excluded_descendant_ids"])


# --- slice I-5: the Q-4 retention rules as configuration with a refusing default -----------------


def test_an_unset_retention_policy_refuses_before_any_read_or_write(job: ModuleType) -> None:
    """The refusing default: no PUBLISHED TENANT version confirms the families → precondition-failed
    naming the parameter, after QUEUED → RUNNING, before the count sweep, any read or any write."""

    class Unset(FakeReader):
        def retention_policy(self) -> Any:
            return None

    repo, writer, reader = FakeRepo(_row()), FakeWriter(), Unset(_ssp_world())
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, reader, writer, params=_params(job))
    assert info.value.slug == "precondition-failed"
    assert "platform.snapshot_retention_families" in str(info.value)
    assert writer.files == {} and reader.calls == 0
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]


def test_an_unconfirmed_retention_version_refuses_by_name(job: ModuleType) -> None:
    """D-98 cand. 86: an in-force version without a named human approval refuses
    RETENTION_UNCONFIRMED at the same point as RETENTION_UNSET — before any count, read or write."""

    class Unconfirmed(FakeReader):
        def retention_policy(self) -> Any:
            raise job.retention_unconfirmed("published_by is NULL")

    repo, writer, reader = FakeRepo(_row()), FakeWriter(), Unconfirmed(_ssp_world())
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, reader, writer, params=_params(job))
    assert info.value.slug == "precondition-failed"
    assert "RETENTION_UNCONFIRMED" in str(info.value) or "human approval" in str(info.value)
    assert "published_by is NULL" in str(info.value)
    assert writer.files == {} and reader.calls == 0
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]


def test_a_confirmed_retention_policy_is_written_into_the_manifest(job: ModuleType) -> None:
    repo, writer = FakeRepo(_row()), FakeWriter()
    result = job.export_snapshot(repo, FakeReader(_ssp_world()), writer, params=_params(job))
    assert result.status == "SUCCEEDED"
    manifest = json.loads(writer.files[job.MANIFEST_NAME][0])
    assert manifest["retention"]["families"] == dict(sd.RETENTION_FAMILIES)
    assert manifest["retention"]["families_status"] == "CONFIRMED: " + CONFIRMED_RETENTION.source
    assert "PROPOSED" not in json.dumps(manifest)


def test_a_missing_release_stamp_refuses_before_any_write(job: ModuleType) -> None:
    """A process without a stamped engine release (05 REL-03) cannot export: the refusal comes
    after the RUNNING transition and before any dataset read or write, so nothing is written."""

    class Unstamped(FakeReader):
        def engine_release(self) -> str | None:
            return None

    repo, writer = FakeRepo(_row()), FakeWriter()
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, Unstamped(_ssp_world()), writer, params=_params(job))
    assert info.value.slug == "precondition-failed" and "release" in str(info.value)
    assert writer.files == {}
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]


# --- slice I-3: the streaming put_file writer -----------------------------------------------------


def test_datasets_are_streamed_and_the_store_hash_is_checked(job: ModuleType) -> None:
    """Each dataset with rows reaches the writer as a JsonlStream whose bytes hash to the manifest
    entry and to the stored row's sha256; a dataset without rows is not stored (T-PLT-29 stores at
    least one byte) and its entry carries the empty digest with row count 0."""
    repo, writer = FakeRepo(_row()), FakeWriter()
    result = job.export_snapshot(repo, FakeReader(_ssp_world()), writer, params=_params(job))
    assert result.status == "SUCCEEDED"
    manifest = json.loads(writer.files[job.MANIFEST_NAME][0])
    entries = {e["name"]: e for e in manifest["datasets"]}
    stored, unstored = 0, 0
    for name, entry in entries.items():
        if entry["row_count"] == 0:
            unstored += 1
            assert f"{name}.jsonl" not in writer.files
            assert entry["sha256"] == sd.EMPTY_SHA256
        else:
            stored += 1
            content = writer.files[f"{name}.jsonl"][0]
            assert hashlib.sha256(content).hexdigest() == entry["sha256"]
            assert content.count(b"\n") == entry["row_count"]
            assert writer.stream_kinds[f"{name}.jsonl"] == "JsonlStream"
    assert stored == 4 and unstored == len(entries) - 4  # book, version, entry, range
    assert result.row_counts["ssp_range"] == 1


class MismatchWriter(FakeWriter):
    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        row = dict(super().write(name=name, stream=stream, media_type=media_type))
        row["sha256"] = "0" * 64  # the store hashed other bytes than it was handed
        return row


def test_a_store_hash_mismatch_refuses_before_success(job: ModuleType) -> None:
    repo, writer = FakeRepo(_row()), MismatchWriter()
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_ssp_world()), writer, params=_params(job))
    assert info.value.slug == "precondition-failed" and "sha256" in str(info.value)
    assert job.MANIFEST_NAME not in writer.files
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]


class FailingWriter(FakeWriter):
    def __init__(self, fail_on: str) -> None:
        super().__init__()
        self.fail_on = fail_on

    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        if name == self.fail_on:
            raise OSError("disk full: /var/erev/files/secret-path")
        return super().write(name=name, stream=stream, media_type=media_type)


def test_a_write_error_refuses_before_success_and_names_the_written_datasets(
    job: ModuleType,
) -> None:
    repo, writer = FakeRepo(_row()), FailingWriter("ssp_entry.jsonl")
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_ssp_world()), writer, params=_params(job))
    problem = info.value
    assert problem.slug == "precondition-failed"
    written = [name[: -len(".jsonl")] for name in writer.files]  # stored before the failure
    assert written == ["ssp_book", "ssp_book_version"] and job.MANIFEST_NAME not in writer.files
    by_rule = {error.rule_id: error for error in problem.errors}
    assert by_rule["SNP-1-WRITTEN"].message == "ssp_book, ssp_book_version"
    assert by_rule["SNP-1-WRITE"].field == "ssp_entry"
    assert by_rule["SNP-1-WRITE"].message == "OSError"  # the class, never the message
    assert "secret-path" not in str(problem)
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]
    # the failure hook names them in the audit event
    job.fail_snapshot(repo, repo.row["id"], problem.to_json(instance="/api/v1/jobs/x"))
    detail = repo.audits[-1]["detail"]
    assert detail["written"] == ["ssp_book", "ssp_book_version"] and detail["failed"] == "ssp_entry"
    assert repo.row["status"] == "FAILED"


# --- Codex I-3 review at fd9254ca: I3-R1 class-only, I3-R2 naming guarantee ---------------------


def _written_and_failed(problem: Problem) -> tuple[list[str], str | None, str | None]:
    by_rule = {error.rule_id: error for error in problem.errors}
    written = by_rule["SNP-1-WRITTEN"].message
    failed = by_rule["SNP-1-WRITE"]
    return (written.split(", ") if written else []), failed.field, failed.message


class ProblemWriter(FakeWriter):
    """A writer whose failure is a native Problem carrying a detail sentinel (I3-R1)."""

    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        if name == "ssp_entry.jsonl":
            raise Problem("precondition-failed", "SENTINEL-DETAIL-MUST-NOT-LEAK")
        return super().write(name=name, stream=stream, media_type=media_type)


def test_r1_a_native_problem_is_reported_by_class_only(job: ModuleType) -> None:
    repo = FakeRepo(_row())
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_ssp_world()), ProblemWriter(), params=_params(job))
    written, failed, message = _written_and_failed(info.value)
    assert (written, failed, message) == (["ssp_book", "ssp_book_version"], "ssp_entry", "Problem")
    assert "SENTINEL" not in str(info.value)
    job.fail_snapshot(repo, repo.row["id"], info.value.to_json(instance="/api/v1/jobs/x"))
    assert "SENTINEL" not in json.dumps(repo.audits[-1]["detail"])
    assert repo.audits[-1]["detail"]["failed"] == "ssp_entry"


def test_d98_82_a_wrapped_catalogue_problem_carries_class_and_slug(job: ModuleType) -> None:
    """Ruling D-98 cand. 82: the slug travels in a separate ProblemError (field problem_slug),
    validated against the catalogue; the SNP-1-WRITE message stays the class; a non-catalogue
    exception yields the class only."""
    repo = FakeRepo(_row())
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_ssp_world()), ProblemWriter(), params=_params(job))
    slugs = [e for e in info.value.errors if e.field == "problem_slug"]
    assert [(e.rule_id, e.message) for e in slugs] == [("SNP-1-WRITE-SLUG", "precondition-failed")]
    assert {e.rule_id: e.message for e in info.value.errors}["SNP-1-WRITE"] == "Problem"
    job.fail_snapshot(repo, repo.row["id"], info.value.to_json(instance="/api/v1/jobs/x"))
    detail = repo.audits[-1]["detail"]
    assert detail["problem_slug"] == "precondition-failed" and detail["failed"] == "ssp_entry"
    with pytest.raises(Problem) as plain:
        job.export_snapshot(
            FakeRepo(_row()),
            FakeReader(_ssp_world()),
            FailingWriter("ssp_entry.jsonl"),
            params=_params(job),
        )
    assert [e for e in plain.value.errors if e.field == "problem_slug"] == []
    with pytest.raises(ValueError, match="catalogue"):
        job._write_failure("detail", [], "x", "Problem", problem_slug="not-a-catalogue-slug")


class PartialWriter(FakeWriter):
    """A writer that stops reading a dataset stream early (I3-R2: a corrupt protocol return)."""

    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        if name == "ssp_entry.jsonl":
            content = stream.read(4)  # partly consumed; the rest never reaches the store
            return {
                "id": _u(0x1234),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": 4,
            }
        return super().write(name=name, stream=stream, media_type=media_type)


class ManifestMismatchWriter(FakeWriter):
    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        row = dict(super().write(name=name, stream=stream, media_type=media_type))
        if name == job_module_manifest_name():
            row["sha256"] = "0" * 64
        return row


def job_module_manifest_name() -> str:
    from erev_api.domain.platform import snapshot_job

    return snapshot_job.MANIFEST_NAME


@pytest.mark.parametrize(
    ("writer_class", "expected_written", "expected_failed"),
    [
        (MismatchWriter, [], "ssp_book"),  # the first dataset's digest already differs
        (PartialWriter, ["ssp_book", "ssp_book_version"], "ssp_entry"),
        (
            ManifestMismatchWriter,
            ["ssp_book", "ssp_book_version", "ssp_entry", "ssp_range"],
            "manifest",
        ),
    ],
)
def test_r2_every_refusal_after_the_first_write_names_written_and_failed(
    job: ModuleType,
    writer_class: type[FakeWriter],
    expected_written: list[str],
    expected_failed: str,
) -> None:
    repo = FakeRepo(_row())
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(_ssp_world()), writer_class(), params=_params(job))
    written, failed, message = _written_and_failed(info.value)
    assert (written, failed, message) == (expected_written, expected_failed, "STORED_MISMATCH")
    assert info.value.slug == "precondition-failed" and "sha256" in str(info.value)
    job.fail_snapshot(repo, repo.row["id"], info.value.to_json(instance="/api/v1/jobs/x"))
    detail = repo.audits[-1]["detail"]
    assert (detail["written"], detail["failed"]) == (expected_written, expected_failed)
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING"), ("RUNNING", "FAILED")]


# --- Codex F-SNP-I41-R1 (ruling D-98 candidate 84): post-write checks name the written datasets --


PRODUCT_600 = _u(0x600)


def test_i41_r1_a_source_count_change_after_the_manifest_names_the_written_datasets(
    job: ModuleType,
) -> None:
    """Codex's one case: the second counts() reports ssp_book 1 → 2 after every dataset and the
    manifest were stored. The refusal stays precondition-failed with no SUCCEEDED / manifest
    reference; it carries the datasets stored so far (SNP-1-WRITTEN) and SNP-1-CHECK =
    source_count with the class-only message — never a failed dataset (no SNP-1-WRITE)."""
    inv = sd.inventory()
    order = {c: "p600" for c in inv.dataset("product").order_by if c not in ("id", "created_at")}
    world = _ssp_world()
    world["product"] = [{"id": PRODUCT_600, "created_at": JUNE_1, **order}]
    counts_after = {name: len(rows) for name, rows in world.items()}
    counts_after["ssp_book"] = 2
    repo, writer = FakeRepo(_row()), FakeWriter()
    with pytest.raises(Problem) as info:
        job.export_snapshot(
            repo, FakeReader(world, counts_after=counts_after), writer, params=_params(job)
        )
    assert info.value.slug == "precondition-failed" and "ssp_book" in str(info.value)
    by_rule = {error.rule_id: error for error in info.value.errors}
    assert by_rule["SNP-1-WRITTEN"].message == (
        "product, ssp_book, ssp_book_version, ssp_entry, ssp_range"
    )
    assert (by_rule["SNP-1-CHECK"].field, by_rule["SNP-1-CHECK"].message) == (
        "source_count",
        "Problem",
    )
    assert "SNP-1-WRITE" not in by_rule
    # inert manifest bytes may exist at this point; no success and no reference is recorded
    assert job.MANIFEST_NAME in writer.files
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]
    assert repo.row.get("manifest_file_id") is None
    job.fail_snapshot(repo, repo.row["id"], info.value.to_json(instance="/api/v1/jobs/x"))
    detail = repo.audits[-1]["detail"]
    assert detail["written"] == [
        "product",
        "ssp_book",
        "ssp_book_version",
        "ssp_entry",
        "ssp_range",
    ]
    assert detail["check"] == "source_count" and "failed" not in detail
    assert repo.row["status"] == "FAILED"


# --- ruling D-98 candidate 106: array drops are counted in the manifest ---------------------------


def test_cut_array_elements_are_dropped_and_counted_in_the_manifest(job: ModuleType) -> None:
    up_kept, up_cut, batch = _u(0x701), _u(0x702), _u(0x900)
    world = _ssp_world()
    world["import_upload"] = [
        {"id": up_kept, "created_at": JUNE_29},
        {"id": up_cut, "created_at": JULY_1},
    ]
    world["migration_batch"] = [
        {"id": batch, "created_at": JUNE_29, "import_upload_ids": [up_cut, up_kept]}
    ]
    repo, writer = FakeRepo(_row()), FakeWriter()
    result = job.export_snapshot(repo, FakeReader(world), writer, params=_params(job))
    assert result.status == "SUCCEEDED" and result.row_counts["migration_batch"] == 1
    exported = json.loads(writer.files["migration_batch.jsonl"][0].split(b"\n")[0])
    assert exported["import_upload_ids"] == [str(up_kept)]
    manifest = json.loads(writer.files[job.MANIFEST_NAME][0])
    assert manifest["array_drops"] == {"migration_batch.import_upload_ids": 1}
    assert repo.audits[-1]["detail"]["array_drops"] == {"migration_batch.import_upload_ids": 1}


# --- ruling D-98 candidate 106a: a complete scope cut refuses by name before any write -----------


def test_a_complete_scope_cut_refuses_before_any_write(job: ModuleType) -> None:
    inv = sd.inventory()
    order = {c: "e" for c in inv.dataset("legal_entity").order_by if c not in ("id", "created_at")}
    e_kept, e_cut, account = _u(0x801), _u(0x802), _u(0x810)
    world = _ssp_world()
    world["legal_entity"] = [
        {"id": e_kept, "created_at": JUNE_1, **order},
        {"id": e_cut, "created_at": JULY_1, **order},
    ]
    world["gl_account"] = [{"id": account, "created_at": JUNE_1, "entity_ids": [e_cut]}]
    repo, writer = FakeRepo(_row()), FakeWriter()
    with pytest.raises(Problem) as info:
        job.export_snapshot(repo, FakeReader(world), writer, params=_params(job))
    assert info.value.slug == "validation-failed"
    assert "SNAPSHOT_SCOPE_UNREPRESENTABLE" in str(info.value)
    errors = {error.rule_id: error for error in info.value.errors}
    assert errors["SNAPSHOT_SCOPE_UNREPRESENTABLE"].field == "gl_account.entity_ids"
    assert str(account) in errors["SNAPSHOT_SCOPE_UNREPRESENTABLE"].message
    assert str(e_cut) in errors["SNAPSHOT_SCOPE_UNREPRESENTABLE"].message
    assert writer.files == {}  # before selection, encoding and any write
    assert [t[:2] for t in repo.transitions] == [("QUEUED", "RUNNING")]


def test_writer_for_is_the_put_file_writer_and_it_checks_the_stored_bytes(
    job: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PutFileWriter streams to files.store.put_file and reads the stored bytes back through
    open_file; the digests must agree (inert fakes for both: no storage, no database)."""
    calls: dict[str, Any] = {}

    def fake_put_file(
        uow: Any, *, purpose: Any, stream: BinaryIO, original_filename: str, media_type: str
    ) -> Any:
        content = stream.read()
        calls.update(purpose=purpose, name=original_filename, media_type=media_type)
        row = {
            "id": _u(0x77),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        return SimpleNamespace(row=row, created=True)

    def fake_open_file(session: Any, file_id: Any, *, files: Any, keyring: Any) -> Any:
        return {}, io.BytesIO(calls["readback"])

    monkeypatch.setattr(job, "put_file", fake_put_file)
    monkeypatch.setattr(job, "open_file", fake_open_file)
    writer = job.writer_for(SimpleNamespace(session=None, files=None, keyring=None))
    assert isinstance(writer, job.PutFileWriter)
    calls["readback"] = b'{"a":1}\n'
    row = writer.write(
        name="contract.jsonl", stream=io.BytesIO(b'{"a":1}\n'), media_type=job.DATASET_MEDIA_TYPE
    )
    assert row["id"] == _u(0x77) and calls["purpose"] is FilePurpose.SNAPSHOT_DATASET
    assert calls["name"] == "contract.jsonl" and calls["media_type"] == job.DATASET_MEDIA_TYPE
    calls["readback"] = b'{"a":2}\n'  # the store returns other bytes than it hashed
    with pytest.raises(Problem) as info:
        writer.write(
            name="x.jsonl", stream=io.BytesIO(b'{"a":1}\n'), media_type=job.DATASET_MEDIA_TYPE
        )
    assert info.value.slug == "precondition-failed" and "read back" in str(info.value)


def test_reader_establishes_repeatable_read_first_and_the_release_is_wired(job: ModuleType) -> None:
    from erev_api.controls import release as release_module
    from erev_api.db import session as db_session

    # tenant_session(isolation_level="REPEATABLE READ") puts SET TRANSACTION before set_config
    statements: list[str] = []

    class Recorder:
        def execute(self, statement: Any, params: Any = None) -> None:
            statements.append(str(statement))

        def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

    db_session.transaction_setup(
        Recorder(),  # type: ignore[arg-type]
        db_session.DbContext(tenant_id=TENANT, user_id=None, entity_scope="*"),
        read_only=True,
        isolation_level="REPEATABLE READ",
    )
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
    assert "set_config" in statements[1] and statements[2] == "SET TRANSACTION READ ONLY"
    assert job.DbSnapshotReader.ISOLATION_LEVEL == "REPEATABLE READ"
    # the manifest's engine release is the stamped release, <engine_version>+<build_sha>
    stamped = release_module.EngineRelease(
        id=_u(1),
        engine_version="1.2.3",
        build_sha="abc123",
        schema_revision="0054",
        deployed_at=NOW,
    )
    assert job.engine_release_of(stamped) == "1.2.3+abc123"
    assert job.engine_release_of(None) is None

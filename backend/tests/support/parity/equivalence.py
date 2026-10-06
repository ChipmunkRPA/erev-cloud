"""Kind ``point_in_time_equivalence`` reader (BUILD_SPEC GPB-3; docs/dev-guide.md §9.6 kind row;
docs/legacy/DEVIATIONS.md OQ-D7; legacy 07 §7 GT-20; ENGINE_SPEC §7.4 S07-R-11, S07-R-12; the
F-LMG record §4 and §5 — reader contracts frozen at 765d038 and 408e37e on ``sprint/l24-flmg``).

The one case, ``shipped-db-equivalence``, asserts that replaying the legacy template files of the
golden steps 01 to ``steps_through`` reproduces the 24 ``Contract_Live`` rows of the shipped legacy
database on the 69 compared columns. The reader exercises the prescribed inputs through the
committed F-LMG interfaces and never decides the outcome itself:

1. Legacy side. ``legacy_db.load_legacy_rows`` reads the fixture
   ``backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db`` read-only (DG-LAY-11) once the
   ``legacy_db.file_sha256`` digest equals the one ``backend/tests/fixtures/manifest.json`` pins;
   ``legacy_db.schema`` fixes the numeric classification (54 numeric, 15 text);
   ``legacy_db.profile`` and ``legacy_db.rows`` give ``replay.replay_plan`` the shape the
   reference database requires (SSP; setup; setup; dated 2023-01-31).
2. Prescribed replay. The golden steps (``golden_streams.steps``) form the ``replay.PlanItem``
   plan: ``replay.infer_template`` must agree with the golden handler mapping,
   ``replay.validate_plan`` and ``replay.slot_mismatches`` must return no error, and
   ``replay.upload_parameters`` of each ``replay.batches`` item, with the workbook's SHA-256, gives
   the parameters the replay must upload. The replay itself is the DG-PAR-04 v1-importer replay of
   those files into this kind's own fresh tenant under the preset (``scenario.build`` with
   ``TENANT_CODE``, then ``through(steps_through)``): the sandbox tenant of S07-R-12 without the
   API-R-48 envelope, which the rc does not have yet (F-LMG LMG-4 and F-SNP; T1 record). Every
   committed import's template code, parameters and file digest is checked against the plan's
   upload parameters, both in the scenario's own record and tenant-wide (API-R-43 ``GET /imports``:
   every import the tenant persists must be exactly one planned batch, none may be missing and none
   may be outside the plan; Codex GPB3-S2), so the rows compared are those of the planned replay
   and of nothing else.
3. eRev side. Report ``legacy_contract_history_export`` (RPT-10) through API-R-41 over both
   entities and the calendar years the legacy ``Current Period`` values span. Its rows carry the
   report row key and the 71 legacy names (``legacy_columns.legacy_row``), the eRev row shape
   F-LMG §5 names; the run's ``row_count`` must be an integer equal to the data rows read (Codex
   GPB3-S1); the reader checks that shape and hands the 71 legacy columns to the comparison.
4. Comparison. ``reconciliation.compare_point_in_time(legacy, erev, schema=schema)``: numeric
   columns within 1/10000, text exact with NULL equal to empty, ``Processing Time Log`` and ``Record
   Unique ID`` excluded, rows aligned by version rank and ``Record Unique ID without time``, rows
   one side lacks as mismatches of the synthetic ``__rows__`` column.

``mismatches`` compares the result with the ``deviations.json`` expected object exactly: the object
must carry exactly ``rows`` (an integer) and ``columns_with_mismatch`` (a list of names); a missing
member, any other member or another type is a mismatch (DG-PAR-09; Codex GPB3-S3), and one detail
entry per mismatching column follows. Every precondition the reader
cannot establish raises :class:`EquivalenceInputError`; the driver records the message and the case
fails (fail closed). The reader holds no expected value and no tolerance of its own.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.config import Settings
from erev_api.domain.migration import legacy_db, reconciliation, replay
from erev_api.domain.migration.reconciliation import EquivalenceResult
from erev_api.domain.reports.legacy_columns import NAMES
from erev_engine.guards import no_floats
from support import golden_streams
from support.factories import run_import_job
from support.legacy_replay import ENTITIES, LegacyWorld
from support.parity import scenario
from support.parity.compare import Mismatch
from support.parity.integrity import GoldenCase
from support.parity.values import DATA_PAGE_LIMIT, REPORT_RUN_ID_HEADER, REPORT_RUNS
from support.reference import get, post

__all__ = [
    "DETAIL_LIMIT",
    "EXPORT_BOOK",
    "EXPORT_REPORT",
    "FIXTURE",
    "KIND",
    "MANIFEST",
    "ROW_KEY",
    "TENANT_CODE",
    "Equivalence",
    "EquivalenceInputError",
    "LegacySide",
    "PlannedUpload",
    "check",
    "checked_row_count",
    "export_rows",
    "import_problems",
    "legacy_side",
    "manifest_sha256",
    "mismatches",
    "persisted_imports",
    "prescribed_plan",
    "project_rows",
    "replay_evidence",
    "replayed",
    "window_of",
]

KIND: Final = "point_in_time_equivalence"
EXPORT_REPORT: Final = "legacy_contract_history_export"  # RPT-10
EXPORT_BOOK: Final = "ASC606"  # the export's fixed book (04 §17.1)
# This kind's own replay tenant (the S07-R-12 sandbox; the DG-PAR-06 fresh-tenant pattern).
TENANT_CODE: Final = "legacy-parity-equivalence"
FIXTURES: Final = golden_streams.REPO_ROOT / "backend" / "tests" / "fixtures"
FIXTURE: Final = FIXTURES / "legacy_db" / "ASC606-shipped-step04.db"
MANIFEST: Final = FIXTURES / "manifest.json"
ROW_KEY: Final = "row_key"  # the report envelope key beside the 71 legacy names
IMPORTS: Final = "/api/v1/imports"  # API-R-43: every import the tenant persists
EXPECTED_MEMBERS: Final = ("rows", "columns_with_mismatch")  # the expected object, exactly
DETAIL_LIMIT: Final = 5  # mismatching cells shown per column in the parity report
_COMMITTED: Final = "COMMITTED"
_SUCCEEDED: Final = "SUCCEEDED"


class EquivalenceInputError(RuntimeError):
    """A prescribed input the reader could not establish; the case fails closed."""


@dataclass(frozen=True, slots=True)
class PlannedUpload:
    """One planned batch and the upload parameters the replay must use (F-LMG 408e37e)."""

    order: int  # 1-based, the batch order
    step: str  # golden step number "01" to "14"
    file_name: str
    parameters: replay.UploadParameters


@dataclass(frozen=True, slots=True)
class LegacySide:
    """The shipped database as the frozen contracts read it, and the plan it prescribes."""

    source_sha256: str
    schema: tuple[legacy_db.LegacyColumn, ...]
    rows: tuple[Mapping[str, str | None], ...]
    profile: legacy_db.LegacyProfile
    plan: tuple[PlannedUpload, ...]


@dataclass(frozen=True, slots=True)
class Equivalence:
    """The reader's outcome: the F-LMG result and the evidence of the inputs it compared."""

    result: EquivalenceResult
    legacy: LegacySide
    tenant_code: str
    export_run_id: str
    export_row_count: int
    window: tuple[date, date]


# --- legacy side and the prescribed plan ----------------------------------------------------------


def manifest_sha256(fixture: Path = FIXTURE, manifest: Path = MANIFEST) -> str:
    """The digest ``backend/tests/fixtures/manifest.json`` pins for ``fixture``."""
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    relative = fixture.resolve().relative_to(manifest.resolve().parent).as_posix()
    for entry in entries:
        if isinstance(entry, Mapping) and entry.get("path") == relative:
            return str(entry["sha256"]).lower()
    raise EquivalenceInputError(f"{manifest} lists no entry for {relative}")


def prescribed_plan(
    profile: legacy_db.LegacyProfile,
    legacy_rows: Sequence[legacy_db.LegacyRow],
    steps: Sequence[golden_streams.GoldenStep],
) -> tuple[PlannedUpload, ...]:
    """The golden steps as the replay plan the reference database requires (F-LMG §4), with the
    upload parameters of every batch; ``EquivalenceInputError`` when the plan does not fit."""
    shape = replay.replay_plan(profile, legacy_rows)
    items: list[replay.PlanItem] = []
    for step in steps:
        try:
            inferred = replay.infer_template(step.workbook.name)
        except ValueError as error:
            raise EquivalenceInputError(f"step {step.number}: {error}") from error
        if inferred != (step.template_code, step.mode):
            raise EquivalenceInputError(
                f"step {step.number}: infer_template({step.workbook.name!r}) gives {inferred}, "
                f"the golden handler gives {(step.template_code, step.mode)}"
            )
        items.append(
            replay.PlanItem(
                file_name=step.workbook.name,
                template_code=step.template_code,
                mode=step.mode,
                effective_date=step.date_input,
            )
        )
    required = replay.required_files(profile)
    errors = replay.validate_plan(items, required=required) + replay.slot_mismatches(items, shape)
    if errors:
        found = "; ".join(f"{error.field}: {error.message}" for error in errors)
        raise EquivalenceInputError(
            f"the golden steps do not form the plan the reference requires ({required} files, "
            f"{len(shape.slots)} slots): {found}"
        )
    planned: list[PlannedUpload] = []
    for batch, step in zip(replay.batches(items), steps, strict=True):
        digest = hashlib.sha256(step.workbook.read_bytes()).hexdigest()
        if digest != step.file_sha256.lower():
            raise EquivalenceInputError(
                f"step {step.number}: workbook {step.workbook.name!r} has SHA-256 {digest}, "
                f"step.json pins {step.file_sha256}"
            )
        planned.append(
            PlannedUpload(
                order=batch.order,
                step=step.number,
                file_name=batch.file_name,
                parameters=replay.upload_parameters(batch, file_sha256=digest),
            )
        )
    return tuple(planned)


def legacy_side(
    steps_through: str, *, fixture: Path = FIXTURE, manifest: Path = MANIFEST
) -> LegacySide:
    """The shipped database through the frozen contracts, and the plan it prescribes for the
    golden steps 01 to ``steps_through``."""
    if not fixture.is_file():
        raise EquivalenceInputError(f"shipped legacy database missing: {fixture}")
    pinned = manifest_sha256(fixture, manifest)
    digest = legacy_db.file_sha256(fixture)
    if digest != pinned:
        raise EquivalenceInputError(
            f"{fixture.name} has SHA-256 {digest}; the fixture manifest pins {pinned}"
        )
    schema = legacy_db.schema(fixture)
    rows = legacy_db.load_legacy_rows(fixture)
    profile = legacy_db.profile(fixture)
    plan = prescribed_plan(profile, legacy_db.rows(fixture), golden_streams.steps(steps_through))
    if legacy_db.file_sha256(fixture) != digest:  # J-20-AC-2: reading never writes the source
        raise EquivalenceInputError(f"{fixture.name} changed while it was read")
    return LegacySide(source_sha256=digest, schema=schema, rows=rows, profile=profile, plan=plan)


def window_of(legacy_rows: Sequence[Mapping[str, str | None]]) -> tuple[date, date]:
    """The export window: the calendar years every legacy ``Current Period`` lies in."""
    periods = [legacy_db.parse_period(row.get(legacy_db.CURRENT_PERIOD)) for row in legacy_rows]
    found = [period for period in periods if period is not None]
    if not found:
        raise EquivalenceInputError("the legacy rows carry no Current Period")
    return date(min(found).year, 1, 1), date(max(found).year, 12, 31)


# --- the replay and its evidence -----------------------------------------------------------------


def replayed(settings: Settings, keyring: KeyRing, steps_through: str) -> scenario.ParityScenario:
    """The golden steps 01 to ``steps_through`` replayed through the v1 importer into this kind's
    own fresh tenant under the preset (DG-PAR-04 steps; S07-R-12 sandbox semantics)."""
    world = scenario.build(settings, keyring, tenant_code=TENANT_CODE)
    world.through(steps_through)
    return world


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _upload_of(done: Mapping[str, Any]) -> dict[str, Any]:
    """The upload parameters an API-S-Import shows, in the vocabulary of ``UploadParameters``."""
    parameters = dict(done.get("parameters") or {})
    return {
        "status": done.get("status"),
        "template_code": (done.get("template") or {}).get("code"),
        "mode": parameters.get("mode"),
        "date_input": parameters.get("effective_date"),
        "file_sha256": str((done.get("file") or {}).get("sha256") or "").lower(),
    }


def _wanted(item: PlannedUpload) -> dict[str, Any]:
    return {
        "status": _COMMITTED,
        "template_code": item.parameters.template_code,
        "mode": item.parameters.mode,
        "date_input": _date_text(item.parameters.date_input),
        "file_sha256": item.parameters.file_sha256,
    }


def persisted_imports(world: LegacyWorld) -> list[Mapping[str, Any]]:
    """Every import the tenant persists (API-R-43 ``GET /imports``, every page), as the API shows
    it — not only the uploads the scenario remembers (Codex GPB3-S2)."""
    found: list[Mapping[str, Any]] = []
    cursor: str | None = None
    while True:
        query: dict[str, Any] = {"limit": str(DATA_PAGE_LIMIT)}
        if cursor is not None:
            query["cursor"] = cursor
        listed = get(world.app, IMPORTS, world.maya, query)
        if listed.status_code != 200:
            raise EquivalenceInputError(
                f"GET /imports answered {listed.status_code}: {listed.text}"
            )
        body = listed.json()
        found.extend(body["items"])
        cursor = body.get("next_cursor")
        if not cursor:
            return found


def import_problems(
    plan: Sequence[PlannedUpload],
    persisted: Sequence[Mapping[str, Any]],
    committed: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Every way the tenant's imports differ from the plan (pure; empty when they agree): the
    scenario committed other steps; a persisted import count other than the plan's; a planned batch
    matched by no or by several persisted imports (template code, mode, effective date, file digest,
    status COMMITTED); a persisted import outside the plan; a scenario record that differs from the
    plan's upload parameters."""
    problems: list[str] = []
    planned_steps = [item.step for item in plan]
    if sorted(committed) != sorted(planned_steps):
        problems.append(
            f"the replay committed steps {sorted(committed)}; the plan has {planned_steps}"
        )
    if len(persisted) != len(plan):
        problems.append(f"the tenant persists {len(persisted)} imports; the plan has {len(plan)}")
    remaining = [(str(done.get("id")), _upload_of(done)) for done in persisted]
    for item in plan:
        wanted = _wanted(item)
        matches = [entry for entry in remaining if entry[1] == wanted]
        if len(matches) != 1:
            problems.append(
                f"batch {item.order} (step {item.step}, {item.file_name}) matches {len(matches)} "
                f"persisted imports; exactly one committed as {wanted} is required"
            )
        else:
            remaining.remove(matches[0])
    for import_id, observed in remaining:
        problems.append(f"import {import_id} committed as {observed} is outside the plan")
    for item in plan:
        done = committed.get(item.step)
        if done is not None and _upload_of(done) != _wanted(item):
            problems.append(
                f"batch {item.order} (step {item.step}, {item.file_name}) was recorded by the "
                f"replay as "
                f"{_upload_of(done)}; the plan requires {_wanted(item)}"
            )
    return problems


def replay_evidence(world: scenario.ParityScenario, plan: Sequence[PlannedUpload]) -> None:
    """Every planned batch was committed with its upload parameters, and nothing else exists in the
    tenant: the scenario's own record and the tenant's persisted imports (API-R-43) both agree with
    the plan, else ``EquivalenceInputError`` (fail closed; Codex GPB3-S2)."""
    problems = import_problems(plan, persisted_imports(world.world), dict(world.imports))
    if problems:
        raise EquivalenceInputError("; ".join(problems))


# --- eRev side -----------------------------------------------------------------------------------


def _data_rows(world: LegacyWorld, run_id: str) -> Iterator[Mapping[str, Any]]:
    cursor: str | None = None
    while True:
        query: dict[str, Any] = {"limit": str(DATA_PAGE_LIMIT)}
        if cursor is not None:
            query["cursor"] = cursor
        listed = get(world.app, f"{REPORT_RUNS}/{run_id}/data", world.maya, query)
        if listed.status_code != 200:
            raise EquivalenceInputError(f"report run {run_id} data answered {listed.text}")
        body = listed.json()
        yield from body["items"]
        cursor = body.get("next_cursor")
        if not cursor:
            return


def export_rows(
    world: LegacyWorld, window: tuple[date, date]
) -> tuple[str, list[Mapping[str, Any]]]:
    """Report ``legacy_contract_history_export`` over ``window`` for both entities through
    API-R-41 and the job run as the worker runs it; the run id and its data rows."""
    parameters = {
        "entity_codes": list(ENTITIES),
        "book": EXPORT_BOOK,
        "from_date": window[0].isoformat(),
        "to_date": window[1].isoformat(),
    }
    started = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {"report_code": EXPORT_REPORT, "parameters": parameters, "output_format": "JSON"},
    )
    if started.status_code != 202:
        raise EquivalenceInputError(
            f"POST /report-runs answered {started.status_code}: {started.text}"
        )
    run_import_job(world.imports, UUID(str(started.json()["id"])))
    run_id = str(started.headers[REPORT_RUN_ID_HEADER])
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", world.maya)
    if shown.status_code != 200:
        raise EquivalenceInputError(f"report run {run_id} answered {shown.text}")
    run = shown.json()
    if run.get("status") != _SUCCEEDED:
        raise EquivalenceInputError(
            f"report run {run_id} ended {run.get('status')}: {run.get('problem')}"
        )
    rows = list(_data_rows(world, run_id))
    checked_row_count(run, rows, run_id)
    return run_id, rows


def checked_row_count(run: Mapping[str, Any], rows: Sequence[Any], run_id: str) -> int:
    """The run's ``row_count``: present, an integer (not a bool or text) and equal to the data rows
    read, else ``EquivalenceInputError`` (Codex GPB3-S1: a promised metadata check, never
    skipped)."""
    counted = run.get("row_count")
    if not isinstance(counted, int) or isinstance(counted, bool):
        raise EquivalenceInputError(
            f"report run {run_id} carries no integer row_count (found {counted!r})"
        )
    if counted != len(rows):
        raise EquivalenceInputError(
            f"report run {run_id} counts {counted} rows; its data pages hold {len(rows)}"
        )
    return counted


def project_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    """The 71 legacy columns of each export row (the ``legacy_columns.legacy_row`` shape F-LMG §5
    names); ``EquivalenceInputError`` unless every row carries exactly the row key and the 71
    legacy names."""
    wanted = sorted([ROW_KEY, *NAMES])
    projected: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        if sorted(row) != wanted:
            extra = sorted(set(row) - set(wanted))
            missing = sorted(set(wanted) - set(row))
            raise EquivalenceInputError(
                f"export row {index} is not the 71-column legacy shape (extra {extra}, "
                f"missing {missing})"
            )
        projected.append({name: row[name] for name in NAMES})
    return tuple(projected)


# --- the case ------------------------------------------------------------------------------------


def check(case: GoldenCase, settings: Settings, keyring: KeyRing) -> Equivalence:
    """The shipped rows against the export rows of the prescribed replay, through F-LMG's
    ``compare_point_in_time``; the result is compared with ``deviations.json`` by ``mismatches``."""
    if case.kind != KIND:
        raise EquivalenceInputError(f"case {case.id} has kind {case.kind}, not {KIND}")
    if case.steps_through is None:
        raise EquivalenceInputError(f"case {case.id} names no steps_through")
    legacy = legacy_side(case.steps_through)
    world = replayed(settings, keyring, case.steps_through)
    replay_evidence(world, legacy.plan)
    window = window_of(legacy.rows)
    run_id, exported = export_rows(world.world, window)
    erev = project_rows(exported)
    result = reconciliation.compare_point_in_time(legacy.rows, erev, schema=legacy.schema)
    no_floats(result.to_json())  # DG-ENG-03: the oracle's values are exact
    return Equivalence(
        result=result,
        legacy=legacy,
        tenant_code=TENANT_CODE,
        export_run_id=run_id,
        export_row_count=len(exported),
        window=window,
    )


def _diff_text(value: Fraction | None) -> str | None:
    if value is None:
        return None
    return f"{value.numerator}/{value.denominator}" if value.denominator != 1 else str(value)


def _member_equal(field: str, actual: Any, expected: Any) -> bool:
    if field == "rows":
        return (
            isinstance(expected, int)
            and not isinstance(expected, bool)
            and isinstance(actual, int)
            and actual == expected
        )
    if field == "columns_with_mismatch":
        return isinstance(expected, list) and list(actual) == [str(name) for name in expected]
    return False


def mismatches(expected: Mapping[str, Any], result: EquivalenceResult) -> list[Mismatch]:
    """DG-PAR-07 for this kind: the expected object carries exactly ``rows`` and
    ``columns_with_mismatch`` and each equals the result exactly; a missing member, another
    member or another type fails the case (DG-PAR-09; Codex GPB3-S3); one detail entry per
    mismatching column names its kind, count, greatest difference and first cells."""
    actual: dict[str, Any] = {
        "rows": result.rows,
        "columns_with_mismatch": list(result.columns_with_mismatch),
    }
    found: list[Mismatch] = []
    for field in EXPECTED_MEMBERS:
        if field not in expected:
            found.append(Mismatch(field, None, "missing from the expected object", None))
    for field, value in expected.items():
        if field not in actual:
            found.append(Mismatch(field, value, "not a member of the equivalence result", None))
        elif not _member_equal(field, actual[field], value):
            found.append(Mismatch(field, value, actual[field], None))
    for name in result.columns_with_mismatch:
        status = result.columns[name]
        detail = {
            "kind": status.kind,
            "mismatches": status.mismatch_count,
            "max_abs_diff": _diff_text(status.max_abs_diff),
            "first": [
                {
                    "row_key": item.row_key,
                    "legacy": item.legacy,
                    "erev": item.erev,
                    "diff": _diff_text(item.diff),
                }
                for item in status.mismatches[:DETAIL_LIMIT]
            ],
        }
        found.append(Mismatch(f"columns[{name}]", "match", detail, None))
    return found

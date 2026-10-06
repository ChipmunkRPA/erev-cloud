"""API-R-43 Imports: template registry, uploads, rows, error report, cancellation and mapping
profiles. The upload reads answer only inside the caller's ``contract.read`` scope (04 rev 1.107;
rulings R-28, R-29): an upload naming an entity outside it is 404, exactly as an unknown id.

04 §15.3 API-R-43, §16.6; T-IMP-01 to T-IMP-04, T-IMP-06; 05 §5.5 IPL-01 to IPL-06, UPL-10, UPL-20;
PRD SM-05, ACT-22; BUILD_SPEC DIN-1, DIN-10. Reads need ``contract.read``; import commands need
``import.upload`` and mapping profile commands ``config.author``. ``POST /imports`` answers 202
API-S-Job (validation) with ``Location`` of the job and ``X-Erev-Import-Id``.
``GET /imports/{id}/diff`` (API-S-ImportDiff) and ``POST /imports/{id}/submit`` are DIN-3's; the
mapping profile routes and ``header_match`` are DIN-10's.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    assert_version,
    command,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import import_mapping_profile, import_row, import_upload
from erev_api.domain.imports import (
    commands,
    commit,
    csv_v2,
    diff,
    mapping_profiles,
    queries,
    templates,
    upload,
)
from erev_api.domain.imports.csv_v2 import framework as csv_framework
from erev_api.enums import ConfigStatus, ImportRowStatus, ImportStatus
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.imports import (
    HeaderMatchOut,
    ImportCreateIn,
    ImportDiffOut,
    ImportOut,
    ImportRowOut,
    ImportSubmitIn,
    ImportTemplateOut,
    MappingProfileIn,
    MappingProfileOut,
    MappingProfileSubmitIn,
    MappingProfileUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-43 Imports"
READ: Final = "contract.read"
UPLOAD: Final = upload.UPLOAD_PERMISSION
AUTHOR: Final = "config.author"  # PRD ACT-22 (mapping profiles)
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
IMPORT_ID_HEADER: Final = "X-Erev-Import-Id"
XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV: Final = "text/csv"
# 05 UPL-10: downloads never render inline.
DOWNLOAD_CSP: Final = "sandbox"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
IMPORT_LIST: Final = ListSpec(
    resource="imports",
    sort_keys={
        "id": import_upload.c.id,
        "import_no": import_upload.c.import_no,
        "created_at": import_upload.c.created_at,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            "status",
            import_upload.c.status,
            "exact",
            choices=frozenset(status.value for status in ImportStatus),
        ),
        "template_code": FilterSpec("template_code", import_upload.c.template_code, "exact"),
        "created_from": FilterSpec("created_from", import_upload.c.created_at, "from"),
    },
)
ROW_LIST: Final = ListSpec(
    resource="import rows",
    sort_keys={
        "id": import_row.c.id,
        "row_number": import_row.c.row_number,
        "status": import_row.c.status,
        "severity": queries.ROW_SEVERITY,
    },
    default_sort="row_number",
    # D-87 L6-4-Q-14: ERROR, WARNING, VALID, AGGREGATED, BLANK, then by row number.
    directions={"severity": "asc"},
    filters={
        "row_number": FilterSpec("row_number", import_row.c.row_number, "exact"),
        "sheet_name": FilterSpec("sheet_name", import_row.c.sheet_name, "exact"),
        "status": FilterSpec(
            "status",
            import_row.c.status,
            "exact",
            choices=frozenset(status.value for status in ImportRowStatus),
        ),
    },
    custom_filters=frozenset({"code"}),
)
PROFILE_LIST: Final = ListSpec(
    resource="import mapping profiles",
    sort_keys={
        "id": import_mapping_profile.c.id,
        "code": import_mapping_profile.c.code,
        "version_no": import_mapping_profile.c.version_no,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            "status",
            import_mapping_profile.c.status,
            "exact",
            choices=frozenset(status.value for status in ConfigStatus),
        ),
        "template_code": FilterSpec(
            "template_code", import_mapping_profile.c.template_code, "exact"
        ),
        "code": FilterSpec("code", import_mapping_profile.c.code, "exact"),
    },
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


def _attachment(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        "Content-Security-Policy": DOWNLOAD_CSP,
    }


@router.get(
    "/import-templates",
    operation_id="import_templates_list",
    response_model=ListOut[ImportTemplateOut],
    responses=problem_responses(*_READ_PROBLEMS),
)
def import_templates_list(ctx: ReadContext) -> ListOut[ImportTemplateOut]:
    """The current version of every import template, legacy v1 first (REQ-DAT-016)."""

    def page(session: Session) -> list[ImportTemplateOut]:
        # A CSV v2 template with an emitter lists its flattened columns (NC-19; BUILD_SPEC DIN-9).
        return [
            templates.template_out(csv_framework.effective(found, csv_v2.TEMPLATES))
            for found in templates.current_templates(session)
        ]

    return ListOut[ImportTemplateOut](items=queries.read(ctx, page), next_cursor=None)


@router.get(
    "/import-templates/{code}/download",
    operation_id="import_templates_download",
    response_class=Response,
    responses={
        200: {"content": {XLSX: {}}, "description": "Headers, one example row and definitions"},
        **problem_responses(*_READ_PROBLEMS, "not-found"),
    },
)
def import_templates_download(code: str, ctx: ReadContext) -> Response:
    """A blank template: the exact headers with one example row, and the sheet "Definitions"."""

    def build(session: Session) -> bytes:
        found = templates.find_template(session, code)
        if found is None:
            raise Problem("not-found")
        return templates.build_download(csv_framework.effective(found, csv_v2.TEMPLATES))

    return Response(
        content=queries.read(ctx, build), media_type=XLSX, headers=_attachment(f"{code}.xlsx")
    )


@router.get(
    "/imports",
    operation_id="imports_list",
    response_model=ListOut[ImportOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def imports_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    status: Annotated[ImportStatus | None, Query(description="E-40")] = None,
    template_code: Annotated[str | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
) -> ListOut[ImportOut]:
    """Imports; sort ``id`` (default ``-id``), ``import_no`` or ``created_at``."""

    def page(session: Session) -> tuple[ListResult, list[ImportOut]]:
        result = paginate(session, queries.imports_statement(ctx.principal), IMPORT_LIST, params)
        return result, queries.import_outs(session, result.items)

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[ImportOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/imports",
    operation_id="imports_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "duplicate-import"),
)
def imports_create(
    body: ImportCreateIn,
    cmd: Annotated[CommandContext, Depends(command(UPLOAD))],
    deps: Deps,
) -> Response:
    """Create an import from an uploaded ``IMPORT_SOURCE`` file and defer its validation; a file
    already imported for the same template version is refused (CTL-001)."""
    created: dict[str, uuid.UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        result = upload.create_import(uow, body=body)
        created["import_id"] = result.import_id
        return result.job

    def headers(job: JobOut) -> dict[str, str]:
        return {
            "Location": JOB_PATH.format(job_id=job.id),
            IMPORT_ID_HEADER: str(created["import_id"]),
        }

    return run_command(cmd, deps, handle, status_code=202, extra_headers=headers)


@router.get(
    "/imports/{import_id}",
    operation_id="imports_get",
    response_model=ImportOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def imports_get(import_id: uuid.UUID, ctx: ReadContext, deps: Deps) -> ImportOut:
    """One import: status, counts, finding counts, control totals and, for a CSV v2 upload, the
    header match of its file (BUILD_SPEC DIN-10; L6-1-Q-5)."""

    def found(session: Session) -> ImportOut:
        item = queries.get_import(session, import_id, ctx.principal)
        stored = (
            session.execute(select(import_upload).where(import_upload.c.id == import_id))
            .mappings()
            .one()
        )
        matches = mapping_profiles.upload_header_match(
            session, dict(stored), files=deps.files, keyring=deps.keyring
        )
        return item.model_copy(
            update={"header_match": [HeaderMatchOut.model_validate(entry) for entry in matches]}
        )

    return queries.read(ctx, found)


@router.get(
    "/imports/{import_id}/rows",
    operation_id="imports_rows",
    response_model=ListOut[ImportRowOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def imports_rows(
    import_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    row_number: Annotated[int | None, Query(ge=1)] = None,
    sheet_name: Annotated[str | None, Query()] = None,
    code: Annotated[list[str] | None, Query(description="§15.4 code of a row message")] = None,
    status: Annotated[ImportRowStatus | None, Query(description="E-41")] = None,
) -> ListOut[ImportRowOut]:
    """The rows of an import with their messages; sort ``row_number`` (default), ``status``, ``id``
    or ``severity`` (``ERROR``, ``WARNING``, ``VALID``, ``AGGREGATED``, ``BLANK``, then by row
    number; no ``-`` prefix)."""

    def page(session: Session) -> tuple[ListResult, list[ImportRowOut]]:
        queries.readable(session, import_id, ctx.principal)
        statement = queries.rows_statement(import_id, codes=tuple(code or ()))
        result = paginate(session, statement, ROW_LIST, params)
        return result, queries.row_outs(session, result.items)

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[ImportRowOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/imports/{import_id}/error-report",
    operation_id="imports_error_report",
    response_class=Response,
    responses={
        200: {"content": {CSV: {}}, "description": "row,column,rule_id,message"},
        **problem_responses(*_READ_PROBLEMS, "not-found"),
    },
)
def imports_error_report(import_id: uuid.UUID, ctx: ReadContext) -> Response:
    """The ``ERROR`` and ``WARNING`` messages of an import as CSV, by row then column."""
    import_no, text = queries.read(
        ctx, lambda session: queries.error_report(session, import_id, ctx.principal)
    )
    return Response(
        content=text.encode("utf-8"),
        media_type=CSV,
        headers=_attachment(f"{import_no}-error-report.csv"),
    )


@router.post(
    "/imports/{import_id}/cancel",
    operation_id="imports_cancel",
    response_model=ImportOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def imports_cancel(
    import_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(UPLOAD))],
    deps: Deps,
) -> Response:
    """Cancel an import before approval; only its uploader can."""
    return run_command(cmd, deps, lambda uow: commands.cancel_import(uow, import_id))


@router.get(
    "/imports/{import_id}/diff",
    operation_id="imports_diff",
    response_model=ImportDiffOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found", "invalid-transition"),
)
def imports_diff(import_id: uuid.UUID, ctx: ReadContext, deps: Deps) -> ImportDiffOut:
    """The dry-run diff of an import from DIFF_READY: summary counts and each change
    (REQ-DAT-015)."""

    def found(session: Session) -> ImportDiffOut:
        queries.readable(session, import_id, ctx.principal)
        return diff.get_diff(session, import_id, files=deps.files, keyring=deps.keyring)

    return queries.read(ctx, found)


@router.post(
    "/imports/{import_id}/submit",
    operation_id="imports_submit",
    response_model=ImportOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def imports_submit(
    import_id: uuid.UUID,
    body: ImportSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(UPLOAD))],
    deps: Deps,
) -> Response:
    """Submit a DIFF_READY import for approval (``IMPORT_COMMIT``); approval defers the
    commit."""

    def handle(uow: UnitOfWork) -> ImportOut:
        return commit.submit_import(uow, import_id=import_id, body=body)

    return run_command(cmd, deps, handle)


# --- mapping profiles (04 T-IMP-06; BUILD_SPEC DIN-10) -------------------------------------------


def profile_etag(out: MappingProfileOut) -> str:
    """API-C-08: a mapping profile version is IM-P, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _profile_out(session: Session, version_id: uuid.UUID) -> MappingProfileOut:
    table = import_mapping_profile
    row = session.execute(select(table).where(table.c.id == version_id)).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return MappingProfileOut.model_validate(
        {**row, "mappings": mapping_profiles.normalised_mappings(row["mappings"] or {})}
    )


@router.get(
    "/import-mapping-profiles",
    operation_id="import_mapping_profiles_list",
    response_model=ListOut[MappingProfileOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def import_mapping_profiles_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    status: Annotated[ConfigStatus | None, Query(description="E-12")] = None,
    template_code: Annotated[str | None, Query()] = None,
    code: Annotated[str | None, Query()] = None,
) -> ListOut[MappingProfileOut]:
    """Mapping profile versions; sort ``code``, ``version_no`` or ``id`` (default ``-id``)."""

    def page(session: Session) -> tuple[ListResult, list[MappingProfileOut]]:
        result = paginate(session, select(import_mapping_profile), PROFILE_LIST, params)
        return result, [_profile_out(session, row["id"]) for row in result.items]

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[MappingProfileOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/import-mapping-profiles",
    operation_id="import_mapping_profiles_create",
    status_code=201,
    response_model=MappingProfileOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def import_mapping_profiles_create(
    body: MappingProfileIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Deps,
) -> Response:
    """Start the next version of a profile code as DRAFT."""

    def handle(uow: UnitOfWork) -> MappingProfileOut:
        version_id = mapping_profiles.create_profile(
            uow,
            code=body.code,
            name=body.name,
            template_code=body.template_code,
            mappings=body.mappings.model_dump(),
            effective_from=body.effective_from,
        )
        return _profile_out(uow.session, version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/import-mapping-profiles/{out.id}",
        etag=profile_etag,
    )


@router.get(
    "/import-mapping-profiles/{profile_id}",
    operation_id="import_mapping_profiles_get",
    response_model=MappingProfileOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def import_mapping_profiles_get(
    profile_id: uuid.UUID, response: Response, ctx: ReadContext
) -> MappingProfileOut:
    """One mapping profile version with its ``ETag``."""
    out = queries.read(ctx, lambda session: _profile_out(session, profile_id))
    response.headers["ETag"] = profile_etag(out)
    return out


@router.patch(
    "/import-mapping-profiles/{profile_id}",
    operation_id="import_mapping_profiles_update",
    response_model=MappingProfileOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "configuration-frozen",
        "precondition-failed",
        "precondition-required",
    ),
)
def import_mapping_profiles_update(
    profile_id: uuid.UUID,
    body: MappingProfileUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR, precondition="row"))],
    deps: Deps,
) -> Response:
    """Change the name, mappings or effective date of a DRAFT or TESTED version."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> MappingProfileOut:
        mapping_profiles.update_profile(
            uow,
            profile_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _profile_out(uow.session, profile_id)

    return run_command(cmd, deps, handle, etag=profile_etag)


@router.post(
    "/import-mapping-profiles/{profile_id}/test",
    operation_id="import_mapping_profiles_test",
    response_model=MappingProfileOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def import_mapping_profiles_test(
    profile_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Deps,
) -> Response:
    """Check the mappings against the template's columns; a DRAFT version that passes becomes
    TESTED."""

    def handle(uow: UnitOfWork) -> MappingProfileOut:
        mapping_profiles.run_tests(uow, profile_id)
        return _profile_out(uow.session, profile_id)

    return run_command(cmd, deps, handle, etag=profile_etag)


@router.post(
    "/import-mapping-profiles/{profile_id}/submit",
    operation_id="import_mapping_profiles_submit",
    response_model=MappingProfileOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def import_mapping_profiles_submit(
    profile_id: uuid.UUID,
    body: MappingProfileSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Deps,
) -> Response:
    """Submit a TESTED version for approval (``MAPPING_PROFILE_VERSION``); approval publishes it."""

    def handle(uow: UnitOfWork) -> MappingProfileOut:
        mapping_profiles.submit_profile(uow, profile_id, comment=body.comment)
        return _profile_out(uow.session, profile_id)

    return run_command(cmd, deps, handle, etag=profile_etag)


@router.post(
    "/import-mapping-profiles/{profile_id}/publish",
    operation_id="import_mapping_profiles_publish",
    response_model=MappingProfileOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def import_mapping_profiles_publish(
    profile_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Deps,
) -> Response:
    """Publish a version left APPROVED; approval publishes a version itself (04 §16.5)."""

    def handle(uow: UnitOfWork) -> MappingProfileOut:
        mapping_profiles.publish_profile(uow, profile_id)
        return _profile_out(uow.session, profile_id)

    return run_command(cmd, deps, handle, etag=profile_etag)

"""IPL-01 upload: ``POST /imports`` (05 §5.5 IPL-01; 04 T-IMP-02, §15.2 ``duplicate-import``,
§16.6 API-S-ImportCreate; PRD SM-05, BR-DAT-03, IMP-05; 03 REQ-DAT-001; control CTL-001; BUILD_SPEC
DIN-1).

The file is stored first through ``POST /files`` (purpose ``IMPORT_SOURCE``, UPL-01 to UPL-04), so
an unsupported type is refused there with 422 ``upload-type-not-allowed``. ``create_import`` checks
the template, its required parameters and the file, then refuses a second upload of the same
(tenant, template version, file SHA-256) while an earlier import is not ``INVALID``, ``REJECTED``,
``CANCELLED`` or ``FAILED`` with 409 ``duplicate-import`` (``ux_import_upload__duplicate``), before
any row is written or validated. Otherwise it creates the ``import_upload`` (series ``IMPORT``,
``is_quarantine_mode`` from ``data.quarantine_failed_rows``) and defers ``IMPORT_VALIDATE``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from erev_api import numbering
from erev_api.db import new_id
from erev_api.db.tables import import_upload
from erev_api.domain.imports import findings, mapping_profiles, templates, validate
from erev_api.domain.platform import file_access
from erev_api.domain.platform.jobs import job_out_of
from erev_api.enums import FilePurpose, ImportStatus, JobKind, PrincipalKind
from erev_api.files import policy
from erev_api.problems import Problem, ProblemError
from erev_api.registry.resolve import setting
from erev_api.schemas.common import JobOut
from erev_api.schemas.imports import ImportCreateIn

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "UPLOAD_PERMISSION",
    "CreatedImport",
    "create_import",
    "duplicate_message",
    "parameter_errors",
]

UPLOAD_PERMISSION: Final = "import.upload"
UPLOAD_ACTION: Final = "import_upload.upload"
OBJECT_TYPE: Final = "import_upload"
SERIES: Final = "IMPORT"
RULE_ID: Final = "API-R-43"
TEMPLATE_RULE: Final = "T-IMP-01"
DUPLICATE_RULE: Final = "IMPORT_FILE_DUPLICATE"
DUPLICATE_INDEX: Final = "ux_import_upload__duplicate"
QUARANTINE_KEY: Final = "data.quarantine_failed_rows"
# ``ux_import_upload__duplicate`` ignores imports in these states (REQ-DAT-001).
ENDED: Final = (
    ImportStatus.INVALID.value,
    ImportStatus.REJECTED.value,
    ImportStatus.CANCELLED.value,
    ImportStatus.FAILED.value,
)
MEDIA_TYPES: Final[Mapping[str, str]] = {"XLSX": policy.XLSX, "CSV": policy.CSV}
EXTENSIONS: Final[Mapping[str, str]] = {"XLSX": ".xlsx", "CSV": ".csv"}


@dataclass(frozen=True, slots=True)
class CreatedImport:
    job: JobOut
    import_id: UUID


def duplicate_message(import_no: str, on: date) -> str:
    """PRD IMP-05 (``findings.duplicate_file``; BUILD_SPEC DIN-8)."""
    return findings.duplicate_file(import_no, on)


def parameter_errors(
    template: templates.Template, parameters: Mapping[str, Any]
) -> list[ProblemError]:
    """The template's required parameters: present, a date when typed ``date``, one of the allowed
    values when listed (04 T-IMP-01 ``required_parameters``)."""
    errors: list[ProblemError] = []
    for parameter in template.required_parameters:
        field = f"parameters.{parameter.name}"
        value = parameters.get(parameter.name)
        if value is None or value == "":
            message = f"{parameter.name} is required for the {template.name} template."
        elif parameter.type == "date" and not _iso_date(value):
            message = f"{parameter.name} must be a date in the form YYYY-MM-DD."
        elif parameter.allowed_values is not None and value not in parameter.allowed_values:
            message = f"{parameter.name} must be one of: {', '.join(parameter.allowed_values)}."
        else:
            continue
        errors.append(ProblemError(field=field, rule_id=TEMPLATE_RULE, message=message))
    return errors


def _iso_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _existing(
    session: Session, template: templates.Template, sha256: str
) -> Mapping[str, Any] | None:
    statement = (
        select(import_upload.c.import_no, import_upload.c.created_at)
        .where(
            import_upload.c.template_code == template.code,
            import_upload.c.template_version == template.version,
            import_upload.c.file_sha256 == sha256,
            import_upload.c.status.not_in(ENDED),
        )
        .order_by(import_upload.c.created_at)
        .limit(1)
    )
    row = session.execute(statement).mappings().one_or_none()
    return None if row is None else dict(row)


def _refuse_duplicate(session: Session, template: templates.Template, sha256: str) -> None:
    existing = _existing(session, template, sha256)
    if existing is None:
        return
    message = duplicate_message(
        str(existing["import_no"]), existing["created_at"].astimezone(UTC).date()
    )
    raise Problem(
        "duplicate-import", message, errors=[ProblemError(rule_id=DUPLICATE_RULE, message=message)]
    )


def _file(
    session: Session,
    ctx: RequestContext,
    template: templates.Template,
    file_id: UUID,
    errors: list[ProblemError],
) -> Mapping[str, Any] | None:
    """The stored source the import names: an ``IMPORT_SOURCE`` file the caller may read. A file
    the caller may not read is answered as one that does not exist (04 T-PLT-29 Read access, rev
    1.151): the validation job reads the source as SYSTEM, so the caller's right to read it is
    asked here, where the caller names it — through ``file_access.bound``, before any property of
    the file is looked at (T-PLT-29 Binding)."""
    row = file_access.bound(session, ctx, file_id)
    if (
        row is None
        or str(row["purpose"]) != FilePurpose.IMPORT_SOURCE.value
        or row["shredded_at"] is not None
    ):
        errors.append(
            ProblemError(
                field="file_id",
                rule_id=RULE_ID,
                message="Upload the file with purpose IMPORT_SOURCE first.",
            )
        )
        return None
    if str(row["media_type"]) != MEDIA_TYPES[template.file_format]:
        extension = EXTENSIONS[template.file_format]
        errors.append(
            ProblemError(
                field="file_id",
                rule_id=TEMPLATE_RULE,
                message=f"The {template.name} template takes {extension} files.",
            )
        )
        return None
    return dict(row)


def _constraint(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None)
    return None if name is None else str(name)


def create_import(uow: UnitOfWork, *, body: ImportCreateIn) -> CreatedImport:
    """IPL-01: create an ``import_upload`` and defer its validation."""
    session = uow.session
    template = templates.find_template(session, body.template_code, body.template_version)
    if template is None:
        version = "" if body.template_version is None else f" version {body.template_version}"
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="template_code",
                    rule_id=TEMPLATE_RULE,
                    message=f"No import template {body.template_code}{version} exists.",
                )
            ],
        )
    errors: list[ProblemError] = []
    if template.code not in validate.ROW_MODELS:
        errors.append(
            ProblemError(
                field="template_code",
                rule_id=RULE_ID,
                message=f"The {template.name} template cannot be uploaded yet.",
            )
        )
    errors += parameter_errors(template, body.parameters)
    if body.mapping_profile_id is not None:
        # BUILD_SPEC DIN-10: a PUBLISHED profile of the upload's CSV v2 template (T-IMP-02).
        errors += mapping_profiles.upload_errors(session, template, body.mapping_profile_id)
    if body.forecast_event_set_id is not None:
        errors.append(
            ProblemError(
                field="forecast_event_set_id",
                rule_id=RULE_ID,
                message="Forecast event sets are available only in scenario workspaces.",
            )
        )
    stored = _file(session, uow.ctx, template, body.file_id, errors)
    if errors or stored is None:
        raise Problem("validation-failed", errors=errors)
    sha256 = str(stored["sha256"]).strip()
    _refuse_duplicate(session, template, sha256)
    upload_id = new_id()
    import_no = numbering.next_number(uow, SERIES)
    deferred = uow.defer(
        JobKind.IMPORT_VALIDATE,
        {"import_upload_id": str(upload_id)},
        subject_type=OBJECT_TYPE,
        subject_id=upload_id,
    )
    principal = uow.principal
    values: dict[str, Any] = {
        "tenant_id": principal.tenant_id,
        "id": upload_id,
        "import_no": import_no,
        "template_code": template.code,
        "template_version": template.version,
        "file_object_id": stored["id"],
        "file_sha256": sha256,
        "parameters": dict(body.parameters),
        "mapping_profile_id": body.mapping_profile_id,
        "status": ImportStatus.UPLOADED.value,
        "is_quarantine_mode": bool(setting(session, QUARANTINE_KEY, known_at=uow.now)),
        # 04 rev 1.147 T-IMP-02 (rulings R-98, R-109 (a)): what the creating access token carried.
        # The jobs that process the upload hold it to these codes (``scope.uploader_bounds``);
        # a person's upload is held to that person's grants and stores nothing here.
        "uploader_scopes": (
            sorted(principal.permissions) if principal.kind is PrincipalKind.API_CLIENT else None
        ),
        "job_id": deferred["id"],
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    savepoint = session.begin_nested()
    try:
        session.execute(insert(import_upload).values(**values))
    except IntegrityError as error:
        savepoint.rollback()
        if _constraint(error) == DUPLICATE_INDEX:  # a concurrent upload committed first
            _refuse_duplicate(session, template, sha256)
        raise
    savepoint.commit()
    uow.audit(
        action=UPLOAD_ACTION,
        object_type=OBJECT_TYPE,
        object_id=upload_id,
        object_version="1",
        after={
            "import_no": import_no,
            "template_code": template.code,
            "template_version": template.version,
            "file_object_id": str(stored["id"]),
            "file_sha256": sha256,
            "status": ImportStatus.UPLOADED.value,
            "job_id": str(deferred["id"]),
        },
    )
    return CreatedImport(job=job_out_of(session, UUID(str(deferred["id"]))), import_id=upload_id)

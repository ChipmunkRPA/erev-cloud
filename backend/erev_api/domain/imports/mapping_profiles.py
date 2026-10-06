"""Import mapping profiles (04 T-IMP-06, E-12, E-119, §15.3 API-R-43, §16.6 ``header_match``; PRD
SM-04, ACT-22, §2.5 routing row ``MAPPING_PROFILE_VERSION``; SCREENS §12.2 step 2, §12.4; 03
REQ-DAT-013; BUILD_SPEC DIN-10).

A profile version maps the columns of a modern CSV file onto one CSV v2 template (T-IMP-06
``mappings``):

- ``aliases`` (source column → template column): the source header is read as the template column,
  and ``header_match`` reports it as ``ALIAS`` with the profile code;
- ``constants`` (template column → value): a template column the file does not carry takes the
  value on every data row;
- ``custom_attributes`` (source columns): their cells are kept by source header under the row's
  ``custom_attributes`` member, which the ``contracts`` command carries (``ContractBookedV1``).

Versions follow the configuration lifecycle of ``policies.lifecycle`` (E-12, DB-04). ``POST`` starts
the next version of a code as DRAFT while no version of the code is open (SM-04); ``PATCH`` edits a
DRAFT or TESTED version; ``/test`` checks the mappings against the template's columns and marks the
version TESTED; ``/submit`` raises a ``MAPPING_PROFILE_VERSION`` request. Its approval by a
``config.approve`` holder other than the author publishes the version (04 §16.5 publish note), and
the author's approval returns 403 ``self-approval``; ``/publish`` publishes a version left APPROVED.
An upload names a PUBLISHED version of its own CSV v2 template (``upload_errors``).

[J] L6-1-Q-4: 04 gives no API-S schema for a profile, so the routes answer the T-IMP-06 columns
with the SC-V lifecycle members. Authoring needs ``config.author`` (PRD ACT-22); reads need
``contract.read`` (API-R-43). Custom attribute columns apply to the templates whose command carries
``custom_attributes`` (``ATTRIBUTE_TEMPLATES``).
[J] L6-1-Q-5: ``header_match`` is computed when an import is read, from the stored file and the
upload's profile: one entry per source column in file order (``EXACT``, ``ALIAS`` or
``NOT_MAPPED``), then one ``MISSING`` entry, with an empty ``source_column``, per required template
column that neither a source column nor a constant fills. A constant is not listed.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.tables import import_mapping_profile
from erev_api.domain.imports import csv_v2, parse, templates
from erev_api.domain.imports.csv_v2 import framework as csv_framework
from erev_api.domain.policies import lifecycle
from erev_api.enums import ApprovalSubjectType, ConfigStatus, HeaderMatchKind
from erev_api.files.store import FileStore, open_file
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "KIND",
    "MappedSheet",
    "Profile",
    "create_profile",
    "header_match",
    "mapped_sheet",
    "mapping_errors",
    "profile",
    "publish_profile",
    "run_tests",
    "submit_profile",
    "update_profile",
    "upload_errors",
    "upload_header_match",
]

OBJECT_TYPE: Final = "import_mapping_profile"
CREATE_ACTION: Final = "import_mapping_profile.create"
UPDATE_ACTION: Final = "import_mapping_profile.update"
RULE_ID: Final = "REQ-DAT-013"
SHREDDED_RULE: Final = "FILE_SHREDDED"  # 04 table 15.4-B: ``files.store.open_file`` after a shred
CODE_LOCK: Final = "import_mapping_profile:{tenant_id}:{code}"
SAMPLES: Final = 3  # API-S-Import ``header_match.samples``
# [J] L6-1-Q-4: the CSV v2 templates whose command carries ``custom_attributes``.
ATTRIBUTE_TEMPLATES: Final = frozenset({"contracts"})
# [J] Copy the documents leave open (PRD CPY-01, CPY-03).
TEMPLATE_UNKNOWN: Final = "Choose a CSV v2 template. {code} is not one."
COLUMN_UNKNOWN: Final = "The {template} template has no column {column}."
COLUMN_BLANK: Final = "Enter a column name."
TARGET_TWICE: Final = "Only one source column can map to {column}."
ATTRIBUTE_TAKEN: Final = "{column} is already a template column, an alias or another attribute."
ATTRIBUTES_UNSUPPORTED: Final = "The {template} template keeps no custom attributes."
VERSION_OPEN: Final = (
    "Another version of mapping profile {code} is open. Finish it or withdraw it first."
)
NOT_TESTABLE: Final = "Only a draft or tested version can run its tests."
PROFILE_UNKNOWN: Final = "No mapping profile has this id."
PROFILE_NOT_PUBLISHED: Final = (
    "Mapping profile {code} version {version_no} is not published. Choose a published version."
)
PROFILE_OTHER_TEMPLATE: Final = "Mapping profile {code} maps the {template} template, not {upload}."
PROFILE_LEGACY: Final = "Mapping profiles apply to CSV v2 templates only."


@dataclass(frozen=True, slots=True)
class Profile:
    """A profile version as an upload applies it."""

    id: UUID
    code: str
    template_code: str
    aliases: Mapping[str, str]
    constants: Mapping[str, Any]
    custom_attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MappedSheet:
    """A sheet read through a profile, with the custom attribute cells by Excel row number."""

    sheet: parse.SheetRows
    custom_attributes: Mapping[int, Mapping[str, str]]


def normalised_mappings(mappings: Mapping[str, Any]) -> dict[str, Any]:
    """T-IMP-06 ``mappings`` with its three members present."""
    return {
        "aliases": {
            str(key): str(value) for key, value in dict(mappings.get("aliases") or {}).items()
        },
        "constants": dict(mappings.get("constants") or {}),
        "custom_attributes": [str(value) for value in mappings.get("custom_attributes") or ()],
    }


def _profile(row: Mapping[str, Any]) -> Profile:
    content = normalised_mappings(row["mappings"] or {})
    return Profile(
        id=UUID(str(row["id"])),
        code=str(row["code"]),
        template_code=str(row["template_code"]),
        aliases=content["aliases"],
        constants=content["constants"],
        custom_attributes=tuple(content["custom_attributes"]),
    )


def profile(session: Session, profile_id: UUID) -> Profile | None:
    """The profile version an upload names, whatever its status now (the upload pinned it)."""
    row = (
        session.execute(
            select(import_mapping_profile).where(import_mapping_profile.c.id == profile_id)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _profile(dict(row))


# --- validation of the mappings ------------------------------------------------------------------


def _error(field: str, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=RULE_ID, message=message)


def mapping_errors(template_code: str, mappings: Mapping[str, Any]) -> list[ProblemError]:
    """The findings of a version's mappings against its CSV v2 template's columns."""
    found = csv_v2.TEMPLATES.get(template_code)
    if found is None:
        return [_error("template_code", TEMPLATE_UNKNOWN.format(code=template_code))]
    content = normalised_mappings(mappings)
    columns = {column.name for column in found.columns}
    errors: list[ProblemError] = []
    targets: set[str] = set()
    for source, target in content["aliases"].items():
        field = f"mappings.aliases.{source}"
        if not source.strip() or not target.strip():
            errors.append(_error(field, COLUMN_BLANK))
        elif target not in columns:
            errors.append(
                _error(field, COLUMN_UNKNOWN.format(template=template_code, column=target))
            )
        elif target in targets:
            errors.append(_error(field, TARGET_TWICE.format(column=target)))
        else:
            targets.add(target)
    for column in content["constants"]:
        if column not in columns:
            message = COLUMN_UNKNOWN.format(template=template_code, column=column)
            errors.append(_error(f"mappings.constants.{column}", message))
    attributes = content["custom_attributes"]
    if attributes and template_code not in ATTRIBUTE_TEMPLATES:
        errors.append(
            _error(
                "mappings.custom_attributes", ATTRIBUTES_UNSUPPORTED.format(template=template_code)
            )
        )
        return errors
    taken = columns | set(content["aliases"])
    for index, column in enumerate(attributes):
        field = f"mappings.custom_attributes[{index}]"
        if not column.strip():
            errors.append(_error(field, COLUMN_BLANK))
        elif column in taken:
            errors.append(_error(field, ATTRIBUTE_TAKEN.format(column=column)))
        taken.add(column)
    return errors


# --- the configuration lifecycle -----------------------------------------------------------------


def _snapshot(session: Session, version_id: UUID) -> Mapping[str, Any]:
    return subjects.mapping_profile_version_content(session, version_id)


def _submit_errors(_session: Session, _version: Mapping[str, Any]) -> list[ProblemError]:
    return []


def _publish_errors(_session: Session, version: Mapping[str, Any]) -> list[ProblemError]:
    return mapping_errors(str(version["template_code"]), version["mappings"] or {})


def _summary(_session: Session, version: Mapping[str, Any]) -> str:
    return f"Mapping profile {version['code']} version {version['version_no']}"


def serialise_code(uow: UnitOfWork, code: str) -> None:
    """The transaction advisory lock of one profile code: the first version of a code has no row
    to lock, so the create takes it before it looks for an open version (PRD SM-04) — and so
    does the reopening of a rejected or withdrawn version (``lifecycle.reopen``), which otherwise
    misses a create that has not committed."""
    key = CODE_LOCK.format(tenant_id=uow.principal.tenant_id, code=code)
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


def _serialise(uow: UnitOfWork, version: Mapping[str, Any]) -> None:
    serialise_code(uow, str(version["code"]))


KIND: Final = lifecycle.ConfigVersionKind(
    table=import_mapping_profile,
    subject_type=ApprovalSubjectType.MAPPING_PROFILE_VERSION,
    scope_columns=("code",),
    content=subjects.mapping_profile_version_content,
    snapshot=_snapshot,
    submit_errors=_submit_errors,
    publish_errors=_publish_errors,
    summary=_summary,
    serialise=_serialise,
)


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {"updated_by": principal.id, "updated_by_kind": principal.kind.value}


def create_profile(
    uow: UnitOfWork,
    *,
    code: str,
    name: str,
    template_code: str,
    mappings: Mapping[str, Any],
    effective_from: datetime | None,
) -> UUID:
    """``POST /import-mapping-profiles``: the next version of ``code`` as DRAFT (SM-04).

    409 ``invalid-transition`` (rule SM-04) while another version of the code is open; 422 collects
    the mapping findings. The versions of a code are serialised by an advisory lock, because the
    first version has no row to lock.
    """
    session = uow.session
    principal = uow.principal
    serialise_code(uow, code)
    table = import_mapping_profile
    versions = (
        session.execute(
            select(table.c.id, table.c.version_no, table.c.status).where(table.c.code == code)
        )
        .mappings()
        .all()
    )
    if any(str(row["status"]) in lifecycle.OPEN for row in versions):
        raise lifecycle.refused(VERSION_OPEN.format(code=code), rule_id=lifecycle.RULE_OPEN_VERSION)
    content = normalised_mappings(mappings)
    errors = mapping_errors(template_code, content)
    if errors:
        raise Problem("validation-failed", errors=errors)
    published = [row for row in versions if str(row["status"]) == ConfigStatus.PUBLISHED.value]
    supersedes = max(published, key=lambda row: int(row["version_no"]))["id"] if published else None
    version_no = max((int(row["version_no"]) for row in versions), default=0) + 1
    version_id = new_id()
    values: dict[str, Any] = {
        "code": code,
        "name": name,
        "template_code": template_code,
        "mappings": content,
        "version_no": version_no,
        "status": ConfigStatus.DRAFT.value,
        "effective_from": effective_from,
        "supersedes_version_id": supersedes,
    }
    session.execute(
        insert(table).values(
            tenant_id=principal.tenant_id,
            id=version_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_at=uow.now,
            **_stamps(uow),
            **values,
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=version_id,
        object_version="1",
        after=values,
    )
    return version_id


def update_profile(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> None:
    """``PATCH /import-mapping-profiles/{id}``: 404; 428 or 412 for ``If-Match``; 409
    ``configuration-frozen`` outside DRAFT and TESTED (a REJECTED or WITHDRAWN version reopens as
    DRAFT, E-12); 422 for mapping findings."""
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    check_version(int(version["row_version"]))
    version = lifecycle.require_editable(uow, KIND, version)
    values: dict[str, Any] = {
        name: changes[name] for name in ("name", "effective_from") if name in changes
    }
    if "mappings" in changes:
        content = normalised_mappings(changes["mappings"])
        errors = mapping_errors(str(version["template_code"]), content)
        if errors:
            raise Problem("validation-failed", errors=errors)
        values["mappings"] = content
    changed = {name: value for name, value in values.items() if version[name] != value}
    if not changed:
        return
    table = import_mapping_profile
    session.execute(update(table).where(table.c.id == version_id).values(**changed, **_stamps(uow)))
    uow.audit(
        action=UPDATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=version_id,
        before={name: version[name] for name in changed},
        after=changed,
    )


def run_tests(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /import-mapping-profiles/{id}/test``: the mappings against the template's columns.

    409 ``invalid-transition`` unless DRAFT or TESTED; 422 with the findings, and the status stays.
    When they pass, a DRAFT version becomes TESTED with its content hash, and a TESTED version
    records the hash of the new run (L1-4-Q-4).
    """
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    if version["status"] not in lifecycle.EDITABLE:
        raise lifecycle.refused(NOT_TESTABLE)
    content = normalised_mappings(version["mappings"] or {})
    errors = mapping_errors(str(version["template_code"]), content)
    if errors:
        raise Problem("validation-failed", errors=errors)
    lifecycle.mark_tested(
        uow,
        KIND,
        version,
        content_sha256=lifecycle.current_sha256(session, KIND, version_id),
        detail={
            "aliases": len(content["aliases"]),
            "constants": len(content["constants"]),
            "custom_attributes": len(content["custom_attributes"]),
        },
    )


def submit_profile(uow: UnitOfWork, version_id: UUID, *, comment: str | None) -> None:
    """``POST /import-mapping-profiles/{id}/submit``: TESTED → SUBMITTED and one
    ``MAPPING_PROFILE_VERSION`` request (REQ-POL-003)."""
    version = lifecycle.lock(uow.session, KIND, version_id)
    lifecycle.submit(uow, KIND, version, comment=comment)


def publish_profile(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /import-mapping-profiles/{id}/publish``: a PUBLISHED version answers as it is; any
    status but APPROVED returns 409 ``invalid-transition``."""
    version = lifecycle.lock(uow.session, KIND, version_id)
    lifecycle.publish(
        uow,
        KIND,
        version,
        approval_request_id=version["approval_request_id"],
        published_by=uow.principal.id,
    )


def _on_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.approve(uow, KIND, subject_id, approval_request_id)


def _on_rejected(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(uow, KIND, subject_id, approval_request_id, to_status=ConfigStatus.REJECTED)


def _on_voided(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(uow, KIND, subject_id, approval_request_id, to_status=ConfigStatus.WITHDRAWN)


subjects.register_lifecycle(
    ApprovalSubjectType.MAPPING_PROFILE_VERSION,
    subjects.SubjectLifecycle(
        on_approved=_on_approved, on_rejected=_on_rejected, on_voided=_on_voided
    ),
)


# --- uploads -------------------------------------------------------------------------------------


def upload_errors(
    session: Session, template: templates.Template, profile_id: UUID
) -> list[ProblemError]:
    """``POST /imports`` with ``mapping_profile_id``: a PUBLISHED version of the upload's CSV v2
    template (04 T-IMP-02 ``mapping_profile_id``)."""
    field = "mapping_profile_id"
    if template.family != "CSV_V2":
        return [_error(field, PROFILE_LEGACY)]
    row = (
        session.execute(
            select(import_mapping_profile).where(import_mapping_profile.c.id == profile_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return [_error(field, PROFILE_UNKNOWN)]
    if str(row["status"]) != ConfigStatus.PUBLISHED.value:
        message = PROFILE_NOT_PUBLISHED.format(code=row["code"], version_no=row["version_no"])
        return [_error(field, message)]
    if str(row["template_code"]) != template.code:
        message = PROFILE_OTHER_TEMPLATE.format(
            code=row["code"], template=row["template_code"], upload=template.code
        )
        return [_error(field, message)]
    return []


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def mapped_sheet(sheet: parse.SheetRows, found: Profile) -> MappedSheet:
    """The sheet as the template reads it: aliased headers renamed, custom attribute columns set
    aside by row, and each constant as a column the file lacks (module docstring)."""
    names = [parse.cell_text(cell) for cell in sheet.headers]
    attributes = {
        index: name for index, name in enumerate(names) if name in found.custom_attributes
    }
    keep = [index for index in range(len(names)) if index not in attributes]
    headers: list[Any] = [
        found.aliases.get(names[index] or "", sheet.headers[index]) for index in keep
    ]
    present = {parse.cell_text(cell) for cell in headers}
    constants = [
        (column, value) for column, value in found.constants.items() if column not in present
    ]
    headers += [column for column, _ in constants]
    rows: list[tuple[int, tuple[Any, ...]]] = []
    kept: dict[int, dict[str, str]] = {}
    for number, cells in sheet.rows:
        blank = all(_blank(value) for value in cells)
        values = tuple(cells[index] if index < len(cells) else None for index in keep)
        filled = tuple(None if blank else value for _, value in constants)
        rows.append((number, values + filled))
        extra = {
            name: text
            for index, name in attributes.items()
            if (text := parse.cell_text(cells[index] if index < len(cells) else None))
            not in (None, "")
        }
        if extra:
            kept[number] = extra
    formula_cells = frozenset(
        (number, keep.index(index)) for number, index in sheet.formula_cells if index in keep
    )
    mapped = dataclasses.replace(
        sheet, headers=tuple(headers), rows=tuple(rows), formula_cells=formula_cells
    )
    return MappedSheet(sheet=mapped, custom_attributes=kept)


def _samples(sheet: parse.SheetRows, index: int) -> list[str]:
    found: list[str] = []
    for _, cells in sheet.rows:
        text = parse.cell_text(cells[index] if index < len(cells) else None)
        if text is None or text.strip() == "":
            continue
        found.append(text)
        if len(found) == SAMPLES:
            break
    return found


def header_match(
    template: templates.Template, sheet: parse.SheetRows, found: Profile | None
) -> list[dict[str, Any]]:
    """API-S-Import ``header_match`` of a CSV v2 upload (E-119; module docstring)."""
    columns = {header.name for header in template.headers}
    aliases: Mapping[str, str] = {} if found is None else found.aliases
    constants: Mapping[str, Any] = {} if found is None else found.constants
    entries: list[dict[str, Any]] = []
    filled: set[str] = set()
    for index, cell in enumerate(sheet.headers):
        name = parse.cell_text(cell)
        if name is None or name.strip() == "":
            continue
        if name in columns:
            field: str | None = name
            match = HeaderMatchKind.EXACT
        elif name in aliases:
            field = aliases[name]
            match = HeaderMatchKind.ALIAS
        else:
            field = None
            match = HeaderMatchKind.NOT_MAPPED
        if field is not None:
            filled.add(field)
        entries.append(
            {
                "source_column": name,
                "samples": _samples(sheet, index),
                "template_field": field,
                "match": match,
                "alias_profile_code": found.code
                if match is HeaderMatchKind.ALIAS and found
                else None,
            }
        )
    for header in template.headers:
        if header.required and header.name not in filled and header.name not in constants:
            entries.append(
                {
                    "source_column": "",
                    "samples": [],
                    "template_field": header.name,
                    "match": HeaderMatchKind.MISSING,
                    "alias_profile_code": None,
                }
            )
    return entries


def upload_header_match(
    session: Session, upload: Mapping[str, Any], *, files: FileStore, keyring: KeyRing
) -> list[dict[str, Any]]:
    """``header_match`` of a stored upload; empty for LEGACY_V1 templates, for unreadable files
    and for an upload whose source was shredded (rulings R-30, R-49 (c): the import still answers,
    its state and rows shown, the file's content gone)."""
    template = templates.find_template(
        session, str(upload["template_code"]), int(upload["template_version"])
    )
    if template is None or template.family != "CSV_V2":
        return []
    template = csv_framework.effective(template, csv_v2.TEMPLATES)
    found = (
        None
        if upload["mapping_profile_id"] is None
        else profile(session, UUID(str(upload["mapping_profile_id"])))
    )
    try:
        _, stream = open_file(session, upload["file_object_id"], files=files, keyring=keyring)
    except Problem as problem:
        if any(error.rule_id == SHREDDED_RULE for error in problem.errors):
            return []
        raise
    try:
        with stream:
            sheet = (
                parse.read_xlsx(stream)
                if template.file_format == "XLSX"
                else parse.read_csv(stream)
            )
    except parse.ParseError:
        return []
    return header_match(template, sheet, found)


def attributed(
    normalized: Mapping[str, Any] | None, custom_attributes: Mapping[str, str] | None
) -> Mapping[str, Any] | None:
    """A normalised row with its custom attribute cells (REQ-DAT-013)."""
    if normalized is None or not custom_attributes:
        return normalized
    return {**normalized, "custom_attributes": dict(custom_attributes)}

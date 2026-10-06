"""RPT-23 ``config_change_register`` Configuration change register (SCREENS_B §5.6.5 RPT-23; 04
T-PLT-17, T-PLT-18, T-PLT-19, T-PLT-20, T-REF-27, E-08, E-12; PRD J-01.5, J-17.8, SM-04; 03
REQ-POL-003, REQ-POL-006, REQ-RPT-022; research 07 CH-01, CH-02, A-16; CTL-031; BUILD_SPEC RPS-10).

One row per decided configuration approval request — APPROVED or REJECTED by the run's record
cutoff, with its decision in ``from_date`` .. ``to_date`` (UTC days; defaults: the first day of the
context fiscal year and the run's day) — of the E-08 configuration subjects in ``subject_types``
(default: all nine, ``catalogue.CONFIGURATION_SUBJECTS``): the requests whose every entity is among
the run's and the tenant-level requests (``register_support.requests_in_scope``). Rows are ordered
by request number; ``row_key`` ``change:<request no>``.

- ``object_label`` names the subject as ``<name> v<n>``: the version's own name (account mapping),
  its parent's code (rule set, obligation template, FX rate set, mapping profile), the category and
  scope of a policy registry version, ``<book code> <version label>`` of an SSP book version, the
  role's name or ``<SoD rule code> v<n>`` of a role change, the product code of a principal or agent
  change (no version). ``effective_from`` is the version's effective date (SC-V ``effective_from``;
  ``effective_from_date`` of an SSP book version; ``coverage_from`` of an FX rate set version); a
  role or principal-or-agent change takes effect with its approval, so it carries the approval day.
- ``author`` is the author of the version (its creator; REQ-POL-003 "approver ≠ author"), else the
  request's preparer; ``approvers`` the approving deciders in decision order; ``author_differs`` is
  false when the author decided the request, in person or as the delegator of a decision — the
  control total ``author_equals_approver_count`` counts those rows (expected 0).
- ``changed_field_count`` is the field-level diff the decision recorded (REQ-POL-003): the diff
  entries of the audit events the request caused on its subject (``audit_event.approval_request_id``
  and ``object_id``), without the lifecycle stamps (status, publication and approval columns) — for
  a published version that is the diff of its content against the version it supersedes
  (``lifecycle.publish`` audits both snapshots); an SSP book version adds the entries its stored
  diff summary counts as added, removed or changed against the prior approved version. A rejected
  request changed no configuration, so it counts 0.
- ``simulation_attached`` tells whether the version holds an impact simulation report (REQ-POL-006)
  and ``test_evidence_count`` the number of its example cases (T-REF-27).

Cutoff: requests, decisions and audit events by the record cutoff (each is timestamped); the
subject's name, version number and effective date are fixed once it is submitted (DB-04).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, Table, and_, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    account_mapping_version,
    approval_request,
    audit_event,
    fx_rate_set,
    fx_rate_set_version,
    import_mapping_profile,
    legal_entity,
    pob_template,
    pob_template_version,
    product,
    registry_version,
    role,
    rule_set,
    rule_set_version,
    rule_test_case,
    sod_rule,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.reports import catalogue, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType, AuditOutcome, RegistryScope
from erev_api.uow import UnitOfWork

CODE: Final = "config_change_register"
ROW_KEY_PREFIX: Final = "change:"  # RPT-23: row_key `change:<request no>`
SUBJECT_TYPES: Final = tuple(item.value for item in catalogue.CONFIGURATION_SUBJECTS)
DECIDED: Final = (ApprovalRequestStatus.APPROVED.value, ApprovalRequestStatus.REJECTED.value)
SSP_APPROVE_ACTION: Final = "ssp_book_version.approve"  # its detail holds the stored diff summary
# Columns a decision stamps on its subject: the lifecycle, never configuration content.
LIFECYCLE_PATHS: Final = frozenset(
    {
        "status",
        "approval_request_id",
        "approved_at",
        "published_at",
        "published_by",
        "effective_to",
        "content_sha256",
    }
)
COLUMNS: Final = (
    Column("request_no", "Change", "code"),
    Column("subject_type", "Type", "code"),
    Column("object_label", "Object", "text"),
    Column("status", "Status", "code"),
    Column("effective_from", "Effective from", "date"),
    Column("author", "Author", "text"),
    Column("submitted_at", "Submitted", "timestamp"),
    Column("approvers", "Approvers", "text"),
    Column("decided_at", "Approved", "timestamp"),
    Column("author_differs", "Author differs from approver", "boolean"),
    Column("changed_field_count", "Fields changed", "integer"),
    Column("simulation_attached", "Simulation attached", "boolean"),
    Column("test_evidence_count", "Test evidence", "integer"),
)


@dataclass(frozen=True, slots=True)
class Subject:
    """What the register shows of one configuration subject."""

    label: str
    effective_from: date | None
    author: tuple[UUID | None, str] | None  # None: the request's preparer authored the change
    simulation_attached: bool = False
    takes_effect_on_approval: bool = False


@dataclass(frozen=True, slots=True)
class Source:
    """One decided request with its subject and evidence resolved — the input of
    ``dataset_rows``."""

    request: support.Request
    subject: Subject | None
    changed_field_count: int
    test_evidence_count: int


def content_changes(diff: Sequence[Mapping[str, Any]] | None) -> int:
    """The entries of an audit diff that change configuration content: every path whose first
    segment is not a lifecycle stamp. Pure."""
    return sum(
        1 for entry in diff or () if str(entry["path"]).split(".", 1)[0] not in LIFECYCLE_PATHS
    )


def diff_summary_changes(detail: Mapping[str, Any] | None) -> int:
    """Added + removed + changed of a stored SSP ``diff_summary``; 0 without one. Pure."""
    summary = (detail or {}).get("diff_summary")
    if not isinstance(summary, Mapping):
        return 0
    return sum(int(summary.get(member) or 0) for member in ("added", "removed", "changed"))


def author_differs(author: tuple[UUID | None, str], decisions: Iterable[support.Decision]) -> bool:
    """False when the author took a decision of the request, in person or as the delegator. Pure."""
    author_id = author[0]
    if author_id is None:
        return True
    return all(author_id not in (item.approver_id, item.on_behalf_of_id) for item in decisions)


def dataset_rows(
    found: Iterable[Source], names: Mapping[UUID, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in request-number order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    same = 0
    for item in sorted(found, key=lambda source: source.request.request_no):
        request, subject = item.request, item.subject
        author = request.preparer
        if subject is not None and subject.author is not None:
            author = subject.author
        differs = author_differs(author, request.decisions)
        same += 0 if differs else 1
        effective = None if subject is None else subject.effective_from
        if (
            subject is not None
            and subject.takes_effect_on_approval
            and request.approved_at is not None
        ):
            effective = request.approved_at.astimezone(UTC).date()
        rows.append(
            {
                "row_key": f"{ROW_KEY_PREFIX}{request.request_no}",
                "request_no": request.request_no,
                "subject_type": request.subject_type,
                "object_label": request.summary if subject is None else subject.label,
                "status": request.status,
                "effective_from": effective,
                "author": support.actor_names([author], names)[0],
                "submitted_at": request.submitted_at,
                "approvers": support.joined(support.actor_names(request.approvers, names)),
                "decided_at": request.decided_at,
                "author_differs": differs,
                "changed_field_count": item.changed_field_count,
                "simulation_attached": False if subject is None else subject.simulation_attached,
                "test_evidence_count": item.test_evidence_count,
            }
        )
    return rows, {"row_count": len(rows), "author_equals_approver_count": same}


# --- subjects -------------------------------------------------------------------------------------

type Reader = Callable[[Session, Sequence[UUID]], dict[UUID, Subject]]


def _rows(session: Session, statement: Select[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in session.execute(statement).mappings()]


def _day(value: Any) -> date | None:
    if value is None:
        return None
    return value.astimezone(UTC).date() if isinstance(value, datetime) else value


def _author(row: Mapping[str, Any]) -> tuple[UUID | None, str]:
    return support.uuid_of(row["created_by"]), str(support.text(row["created_by_kind"]))


def _versioned(name: str, row: Mapping[str, Any], *, effective: Any, simulated: bool) -> Subject:
    return Subject(
        label=f"{name} v{int(row['version_no'])}",
        effective_from=_day(effective),
        author=_author(row),
        simulation_attached=simulated,
    )


def _child_reader(version: Table, parent: Table, parent_key: str, *, simulated: bool) -> Reader:
    """A reader of versions named by their parent's code (rule set, template, FX rate set)."""

    def read(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
        joined = version.join(
            parent,
            and_(parent.c.tenant_id == version.c.tenant_id, parent.c.id == version.c[parent_key]),
        )
        statement = (
            select(version, parent.c.code.label("parent_code"))
            .select_from(joined)
            .where(version.c.id.in_(list(ids)))
        )
        found: dict[UUID, Subject] = {}
        for row in _rows(session, statement):
            effective = row["coverage_from"] if "coverage_from" in row else row["effective_from"]
            found[UUID(str(row["id"]))] = _versioned(
                str(row["parent_code"]),
                row,
                effective=effective,
                simulated=simulated and row["impact_simulation_file_id"] is not None,
            )
        return found

    return read


def _registry_versions(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
    joined = registry_version.outerjoin(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == registry_version.c.tenant_id,
            legal_entity.c.id == registry_version.c.entity_id,
        ),
    )
    statement = (
        select(registry_version, legal_entity.c.code.label("entity_code"))
        .select_from(joined)
        .where(registry_version.c.id.in_(list(ids)))
    )
    found: dict[UUID, Subject] = {}
    for row in _rows(session, statement):
        category = str(support.text(row["category"])).replace("_", " ").lower()
        scope = str(support.text(row["scope"]))
        if scope == RegistryScope.ENTITY.value:
            where = f"entity {row['entity_code']}"
        elif scope == RegistryScope.BOOK.value:
            where = f"book {support.text(row['book_code'])}"
        else:
            where = "the workspace"
        found[UUID(str(row["id"]))] = _versioned(
            f"{category} for {where}",
            row,
            effective=row["effective_from"],
            simulated=row["impact_simulation_file_id"] is not None,
        )
    return found


def _account_mappings(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
    statement = select(account_mapping_version).where(account_mapping_version.c.id.in_(list(ids)))
    return {
        UUID(str(row["id"])): _versioned(
            str(row["name"]),
            row,
            effective=row["effective_from"],
            simulated=row["impact_simulation_file_id"] is not None,
        )
        for row in _rows(session, statement)
    }


def _mapping_profiles(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
    statement = select(import_mapping_profile).where(import_mapping_profile.c.id.in_(list(ids)))
    return {
        UUID(str(row["id"])): _versioned(
            str(row["code"]), row, effective=row["effective_from"], simulated=False
        )
        for row in _rows(session, statement)
    }


def _ssp_book_versions(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
    joined = ssp_book_version.join(
        ssp_book,
        and_(
            ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
            ssp_book.c.id == ssp_book_version.c.ssp_book_id,
        ),
    )
    statement = (
        select(ssp_book_version, ssp_book.c.code.label("book_code"))
        .select_from(joined)
        .where(ssp_book_version.c.id.in_(list(ids)))
    )
    found: dict[UUID, Subject] = {}
    for row in _rows(session, statement):
        label = row["legacy_version_label"]
        name = str(row["book_code"]) if label is None else f"{row['book_code']} {label}"
        found[UUID(str(row["id"]))] = _versioned(
            name, row, effective=row["effective_from_date"], simulated=False
        )
    return found


def _role_changes(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
    """A ``ROLE_CHANGE`` names a role, or the SoD rule version it publishes (BS1-D-29)."""
    found: dict[UUID, Subject] = {}
    for role_id, name in session.execute(select(role.c.id, role.c.name).where(role.c.id.in_(ids))):
        found[UUID(str(role_id))] = Subject(
            label=str(name), effective_from=None, author=None, takes_effect_on_approval=True
        )
    for row in _rows(session, select(sod_rule).where(sod_rule.c.id.in_(list(ids)))):
        found[UUID(str(row["id"]))] = _versioned(
            str(row["code"]), row, effective=row["effective_from"], simulated=False
        )
    return found


def _products(session: Session, ids: Sequence[UUID]) -> dict[UUID, Subject]:
    statement = select(product.c.id, product.c.code).where(product.c.id.in_(list(ids)))
    return {
        UUID(str(product_id)): Subject(
            label=str(code), effective_from=None, author=None, takes_effect_on_approval=True
        )
        for product_id, code in session.execute(statement)
    }


READERS: Final[Mapping[str, Reader]] = {
    ApprovalSubjectType.REGISTRY_VERSION.value: _registry_versions,
    ApprovalSubjectType.RULE_SET_VERSION.value: _child_reader(
        rule_set_version, rule_set, "rule_set_id", simulated=True
    ),
    ApprovalSubjectType.POB_TEMPLATE_VERSION.value: _child_reader(
        pob_template_version, pob_template, "pob_template_id", simulated=False
    ),
    ApprovalSubjectType.ACCOUNT_MAPPING_VERSION.value: _account_mappings,
    ApprovalSubjectType.FX_RATE_SET_VERSION.value: _child_reader(
        fx_rate_set_version, fx_rate_set, "fx_rate_set_id", simulated=False
    ),
    ApprovalSubjectType.SSP_BOOK_VERSION.value: _ssp_book_versions,
    ApprovalSubjectType.MAPPING_PROFILE_VERSION.value: _mapping_profiles,
    ApprovalSubjectType.ROLE_CHANGE.value: _role_changes,
    ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE.value: _products,
}
assert set(READERS) == set(SUBJECT_TYPES), "every configuration subject of E-08 has a reader"


def _changes(
    session: Session, requests: Sequence[support.Request], *, cutoff: datetime
) -> dict[UUID, int]:
    """Per request, the content changes its decision recorded on its subject by the cutoff."""
    if not requests:
        return {}
    subjects = {item.id: item.subject_id for item in requests}
    statement = select(
        audit_event.c.approval_request_id,
        audit_event.c.object_id,
        audit_event.c.action,
        audit_event.c.diff,
        audit_event.c.detail,
    ).where(
        audit_event.c.approval_request_id.in_(sorted(subjects, key=str)),
        audit_event.c.outcome == AuditOutcome.SUCCESS.value,
        audit_event.c.occurred_at <= cutoff,
    )
    counts: dict[UUID, int] = {}
    for request_id, object_id, action, diff, detail in session.execute(statement):
        key = UUID(str(request_id))
        if object_id is None or UUID(str(object_id)) != subjects[key]:
            continue
        counts[key] = counts.get(key, 0) + content_changes(diff)
        if str(action) == SSP_APPROVE_ACTION:
            counts[key] += diff_summary_changes(detail)
    return counts


def _test_cases(session: Session, subject_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not subject_ids:
        return {}
    statement = (
        select(rule_test_case.c.subject_id, func.count())
        .where(rule_test_case.c.subject_id.in_(list(subject_ids)))
        .group_by(rule_test_case.c.subject_id)
    )
    return {UUID(str(subject_id)): int(count) for subject_id, count in session.execute(statement)}


def sources(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    subject_types: Sequence[str],
    bounds: tuple[datetime, datetime],
) -> list[Source]:
    """The decided configuration requests in scope and range, by the cutoff."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    scope = support.requests_in_scope(session, params, cutoff=cutoff)
    decided = [
        item
        for item in support.requests(
            session,
            cutoff=cutoff,
            where=[approval_request.c.subject_type.in_(list(subject_types)), scope],
        )
        if item.status in DECIDED and support.within(item.decided_at, bounds)
    ]
    subjects: dict[UUID, Subject] = {}
    for subject_type in sorted({item.subject_type for item in decided}):
        ids = sorted(
            {item.subject_id for item in decided if item.subject_type == subject_type}, key=str
        )
        subjects.update(READERS[subject_type](session, ids))
    changes = _changes(session, decided, cutoff=cutoff)
    cases = _test_cases(session, sorted({item.subject_id for item in decided}, key=str))
    return [
        Source(
            request=item,
            subject=subjects.get(item.subject_id),
            changed_field_count=changes.get(item.id, 0),
            test_evidence_count=cases.get(item.subject_id, 0),
        )
        for item in decided
    ]


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    first, last = support.date_range(session, params, today=True)
    given = params.parameters.get("subject_types")
    found = sources(
        uow,
        params,
        subject_types=SUBJECT_TYPES if not given else tuple(str(value) for value in given),
        bounds=support.instants(first, last),
    )
    names = support.names_of(
        session,
        (item.request for item in found),
        (item.subject.author[0] for item in found if item.subject and item.subject.author),
    )
    rows, totals = dataset_rows(found, names)
    totals["from_date"], totals["to_date"] = first.isoformat(), last.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "LIFECYCLE_PATHS",
    "READERS",
    "SUBJECT_TYPES",
    "Source",
    "Subject",
    "author_differs",
    "build",
    "content_changes",
    "dataset_rows",
    "diff_summary_changes",
    "sources",
]

"""Rule set and configuration test case commands (04 §15.3 API-R-25, API-R-57, T-REF-24 to
T-REF-27, §14.1 DB-04; PRD SM-04, BR-POL-01; dev-guide §6.1 DG-CMD-01 to DG-CMD-08; BUILD_SPEC
RFD-4, RFD-5).

Authoring (RFD-4): ``create_rule_set`` records a decision table and ``create_rule_set_version`` its
next version as DRAFT, optionally copying an earlier version's rules and example cases.
``upsert_rule`` creates a rule or replaces the rule with the same ``rule_key``; ``delete_rule`` and
the example case commands complete it. Every change to a version or its children needs the version
to be DRAFT or TESTED (409 ``configuration-frozen``; DB-04 enforces the same in the database); a
REJECTED or WITHDRAWN version is reopened as DRAFT first (E-12).

Lifecycle (RFD-5): ``lint_rule_set_version`` stores the lint result; ``run_rule_set_version_tests``
runs the example cases and records DRAFT → TESTED when every case and the lint pass;
``submit_rule_set_version`` attaches the simulation report and requests approval;
``publish_rule_set_version`` publishes a version left APPROVED.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Table, delete, insert, select, update

from erev_api.audit.writer import record_facts
from erev_api.db import new_id
from erev_api.db.tables import (
    pob_template,
    pob_template_version,
    rule,
    rule_set,
    rule_set_version,
    rule_test_case,
)
from erev_api.db.tables.platform import registry_version
from erev_api.domain.policies import lifecycle, rule_sets, simulation, templates
from erev_api.enums import ConfigStatus, RuleSetKind
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

CREATE_SET_ACTION: Final = "rule_set.create"
CREATE_VERSION_ACTION: Final = "rule_set_version.create"
UPDATE_VERSION_ACTION: Final = "rule_set_version.update"
LINT_ACTION: Final = "rule_set_version.lint"
TEST_ACTION: Final = "rule_set_version.test"
CREATE_RULE_ACTION: Final = "rule.create"
UPSERT_RULE_ACTION: Final = "rule.upsert"
DELETE_RULE_ACTION: Final = "rule.delete"
CREATE_CASE_ACTION: Final = "rule_test_case.create"
UPDATE_CASE_ACTION: Final = "rule_test_case.update"
DELETE_CASE_ACTION: Final = "rule_test_case.delete"
RUN_CASES_ACTION: Final = "rule_test_case.run"
VERSION_COLUMNS: Final = ("effective_from",)
CASE_COLUMNS: Final = ("name", "input", "expected_output")
KIND: Final = rule_sets.RULE_SET_VERSION_KIND
# T-REF-27 subject types whose version tables exist; the others arrive with their items (XR-12).
CONFIG_SUBJECTS: Final[Mapping[str, Table]] = MappingProxyType(
    {
        rule_sets.SUBJECT_TYPE: rule_set_version,
        templates.SUBJECT_TYPE: pob_template_version,
        "registry_version": registry_version,
    }
)
# [J] Copy the documents leave open.
NOT_TESTABLE: Final = "Only a draft or tested version can run its tests."
CASES_REQUIRED: Final = "Add at least one test case before running the tests."
SUBJECT_UNSUPPORTED: Final = "Choose a rule set, obligation template or registry version."
VALUE_REQUIRED: Final = "Enter a value."


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _updated(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _touched(uow: UnitOfWork) -> dict[str, Any]:
    """The SC-M author of an update; the DB-02 touch trigger sets ``updated_at``."""
    principal = uow.principal
    return {"updated_by": principal.id, "updated_by_kind": principal.kind.value}


def create_rule_set(
    uow: UnitOfWork, *, code: str, kind: RuleSetKind, name: str | None, description: str | None
) -> UUID:
    """``POST /rule-sets``: the new set's id; 422 when the code is taken (T-REF-24)."""
    session = uow.session
    taken = session.execute(select(rule_set.c.id).where(rule_set.c.code == code)).first()
    if taken is not None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="code", rule_id=rule_sets.RULE_SET_RULE, message=rule_sets.CODE_TAKEN
                )
            ],
        )
    label = code if name is None or not name.strip() else name.strip()
    rule_set_id = new_id()
    values = {"code": code, "name": label, "kind": kind.value, "description": description}
    session.execute(
        insert(rule_set).values(
            tenant_id=uow.principal.tenant_id,
            id=rule_set_id,
            **values,
            **_created(uow),
            **_updated(uow),
        )
    )
    uow.audit(
        action=CREATE_SET_ACTION,
        object_type=rule_sets.OBJECT_RULE_SET,
        object_id=rule_set_id,
        after=values,
    )
    return rule_set_id


def _copy_children(
    uow: UnitOfWork, *, source_version_id: UUID, version_id: UUID
) -> tuple[list[UUID], list[UUID]]:
    """Copy the rules and example cases of ``source_version_id`` into the new DRAFT version."""
    session = uow.session
    tenant_id = uow.principal.tenant_id
    rule_ids: list[UUID] = []
    for row in rule_sets.rule_rows(session, source_version_id):
        rule_id = new_id()
        session.execute(
            insert(rule).values(
                tenant_id=tenant_id,
                id=rule_id,
                rule_set_version_id=version_id,
                rule_key=row["rule_key"],
                priority=row["priority"],
                conditions=row["conditions"],
                outputs=row["outputs"],
                specificity=row["specificity"],
                description=row["description"],
            )
        )
        rule_ids.append(rule_id)
    case_ids: list[UUID] = []
    cases = session.execute(
        select(rule_test_case)
        .where(
            rule_test_case.c.subject_type == rule_sets.SUBJECT_TYPE,
            rule_test_case.c.subject_id == source_version_id,
        )
        .order_by(rule_test_case.c.id)
    ).mappings()
    for case in cases:
        case_id = new_id()
        session.execute(
            insert(rule_test_case).values(
                tenant_id=tenant_id,
                id=case_id,
                subject_type=rule_sets.SUBJECT_TYPE,
                subject_id=version_id,
                name=case["name"],
                input=case["input"],
                expected_output=case["expected_output"],
                **_created(uow),
                **_updated(uow),
            )
        )
        case_ids.append(case_id)
    return rule_ids, case_ids


def create_rule_set_version(
    uow: UnitOfWork,
    rule_set_id: UUID,
    *,
    effective_from: datetime | None,
    source_version_id: UUID | None,
) -> UUID:
    """``POST /rule-sets/{id}/versions``: the next version as DRAFT (PRD SM-04).

    404 for an unknown set; 409 ``configuration-frozen`` for a rule set provisioning seeds and the
    approvals engine reads by its code (04 §14.3 item 2); 409 ``invalid-transition`` while another
    version of the set is DRAFT, TESTED, SUBMITTED or APPROVED; 422 when ``source_version_id`` is
    not a version of the set. The version records the PUBLISHED version it will supersede.
    """
    session = uow.session
    found = (
        session.execute(
            select(rule_set.c.id, rule_set.c.kind, rule_set.c.code)
            .where(rule_set.c.id == rule_set_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    if rule_sets.is_seeded_approval_set(found["kind"], found["code"]):
        # A further version would supersede the seeded one and could not restore it: authoring
        # refuses a tenant's rule that names a seeded-only subject (R-26 (b); R-41 (7)).
        raise Problem(
            "configuration-frozen",
            rule_sets.SEEDED_SET.format(code=str(found["code"])),
            errors=[
                ProblemError(
                    rule_id=rule_sets.RULE_SET_RULE,
                    message=rule_sets.SEEDED_SET.format(code=str(found["code"])),
                )
            ],
        )
    versions = (
        session.execute(
            select(rule_set_version.c.id, rule_set_version.c.version_no, rule_set_version.c.status)
            .where(rule_set_version.c.rule_set_id == rule_set_id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if any(version["status"] in rule_sets.OPEN_STATUSES for version in versions):
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(rule_id=rule_sets.RULE_OPEN_VERSION, message=rule_sets.VERSION_OPEN)
            ],
        )
    if source_version_id is not None and all(
        version["id"] != source_version_id for version in versions
    ):
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="source_version_id",
                    rule_id=rule_sets.RULE_SET_RULE,
                    message=rule_sets.SOURCE_UNKNOWN,
                )
            ],
        )
    published = next(
        (
            version["id"]
            for version in versions
            if version["status"] == ConfigStatus.PUBLISHED.value
        ),
        None,
    )
    version_no = max((int(version["version_no"]) for version in versions), default=0) + 1
    version_id = new_id()
    session.execute(
        insert(rule_set_version).values(
            tenant_id=uow.principal.tenant_id,
            id=version_id,
            rule_set_id=rule_set_id,
            kind=found["kind"],
            **_created(uow),
            **_updated(uow),
            version_no=version_no,
            status=ConfigStatus.DRAFT.value,
            effective_from=effective_from,
            supersedes_version_id=published,
        )
    )
    rule_ids: list[UUID] = []
    case_ids: list[UUID] = []
    if source_version_id is not None:
        rule_ids, case_ids = _copy_children(
            uow, source_version_id=source_version_id, version_id=version_id
        )
    uow.audit(
        action=CREATE_VERSION_ACTION,
        object_type=rule_sets.OBJECT_VERSION,
        object_id=version_id,
        after={
            "rule_set_id": rule_set_id,
            "version_no": version_no,
            "status": ConfigStatus.DRAFT.value,
            "effective_from": effective_from,
            "supersedes_version_id": published,
        },
        detail={
            "source_version_id": source_version_id,
            "rules_copied": len(rule_ids),
            "test_cases_copied": len(case_ids),
        },
    )
    if rule_ids:
        record_facts(
            uow,
            action=CREATE_RULE_ACTION,
            object_type=rule_sets.OBJECT_RULE,
            ids=rule_ids,
            detail={"rule_set_version_id": str(version_id)},
        )
    if case_ids:
        record_facts(
            uow,
            action=CREATE_CASE_ACTION,
            object_type=rule_sets.OBJECT_TEST_CASE,
            ids=case_ids,
            detail={"subject_type": rule_sets.SUBJECT_TYPE, "subject_id": str(version_id)},
        )
    return version_id


def update_rule_set_version(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> None:
    """``PATCH /rule-set-versions/{id}``: 404; 412 or 428 for ``If-Match``; 409
    ``configuration-frozen`` outside DRAFT and TESTED."""
    session = uow.session
    version = rule_sets.lock_version(session, version_id)
    check_version(int(version["row_version"]))
    version = lifecycle.require_editable(uow, KIND, version)
    values = {name: changes[name] for name in VERSION_COLUMNS if name in changes}
    if not values:
        return
    session.execute(
        update(rule_set_version)
        .where(rule_set_version.c.id == version_id)
        .values(**values, **_touched(uow))
    )
    uow.audit(
        action=UPDATE_VERSION_ACTION,
        object_type=rule_sets.OBJECT_VERSION,
        object_id=version_id,
        before={name: version[name] for name in values},
        after=values,
    )


def upsert_rule(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    rule_key: str,
    priority: int,
    conditions: Sequence[Mapping[str, Any]],
    outputs: Mapping[str, Any],
    description: str | None,
) -> tuple[UUID, bool]:
    """``POST /rule-set-versions/{id}/rules``: the rule id and whether the rule was created.

    404; 409 ``configuration-frozen`` outside DRAFT and TESTED; 422 collecting the condition and
    output findings (T-REF-26), then the findings on an approval rule that would lower a subject's
    own approval (``rule_sets.approval_rule_errors``). The specificity is the number of distinct
    condition fields.
    """
    session = uow.session
    version = rule_sets.lock_version(session, version_id)
    version = lifecycle.require_editable(uow, KIND, version)
    kind = RuleSetKind(version["kind"])
    specificity, errors = rule_sets.condition_errors(kind, conditions)
    errors += rule_sets.output_errors(kind, outputs)
    if not errors and kind is RuleSetKind.APPROVAL_ROUTING:
        errors += rule_sets.step_role_errors(session, outputs)  # 04 T-REF-26; record §6 item 7
    if not errors:
        # R-26 (04 T-REF-26 rev 1.104): a rule that would lower a subject's own approval.
        errors += rule_sets.approval_rule_errors(kind, conditions, outputs)
    if errors:
        raise Problem("validation-failed", errors=errors)
    values = {
        "priority": priority,
        "conditions": [dict(condition) for condition in conditions],
        "outputs": dict(outputs),
        "specificity": specificity,
        "description": description,
    }
    existing = session.execute(
        select(rule.c.id)
        .where(rule.c.rule_set_version_id == version_id, rule.c.rule_key == rule_key)
        .with_for_update()
    ).scalar_one_or_none()
    if existing is None:
        rule_id = new_id()
        session.execute(
            insert(rule).values(
                tenant_id=uow.principal.tenant_id,
                id=rule_id,
                rule_set_version_id=version_id,
                rule_key=rule_key,
                **values,
            )
        )
    else:
        rule_id = UUID(str(existing))
        session.execute(update(rule).where(rule.c.id == rule_id).values(**values))
    record_facts(
        uow,
        action=UPSERT_RULE_ACTION,
        object_type=rule_sets.OBJECT_RULE,
        ids=[rule_id],
        detail={
            "rule_set_version_id": str(version_id),
            "rule_key": rule_key,
            "created": existing is None,
        },
    )
    return rule_id, existing is None


def delete_rule(uow: UnitOfWork, version_id: UUID, rule_id: UUID) -> None:
    """``DELETE /rule-set-versions/{id}/rules/{rule_id}``: 404 for a rule outside the version;
    409 ``configuration-frozen`` outside DRAFT and TESTED."""
    session = uow.session
    version = rule_sets.lock_version(session, version_id)
    rule_key = session.execute(
        select(rule.c.rule_key).where(
            rule.c.id == rule_id, rule.c.rule_set_version_id == version_id
        )
    ).scalar_one_or_none()
    if rule_key is None:
        raise Problem("not-found")
    lifecycle.require_editable(uow, KIND, version)
    session.execute(delete(rule).where(rule.c.id == rule_id))
    record_facts(
        uow,
        action=DELETE_RULE_ACTION,
        object_type=rule_sets.OBJECT_RULE,
        ids=[rule_id],
        detail={"rule_set_version_id": str(version_id), "rule_key": str(rule_key)},
    )


def _case_errors(
    subject_type: str,
    subject: Mapping[str, Any],
    *,
    name: Any,
    facts: Any,
    expected_output: Any,
) -> list[ProblemError]:
    """Findings on an example case; a rule set version's facts and expected evaluation are checked
    against its kind (T-REF-27)."""
    errors: list[ProblemError] = []
    if not isinstance(name, str) or not name.strip():
        errors.append(
            ProblemError(
                field="name", rule_id=rule_sets.RULE_TEST_CASE, message=rule_sets.NAME_EMPTY
            )
        )
    for field, value in (("input", facts), ("expected_output", expected_output)):
        if not isinstance(value, dict):
            errors.append(
                ProblemError(field=field, rule_id=rule_sets.RULE_TEST_CASE, message=VALUE_REQUIRED)
            )
    if errors:
        return errors
    if subject_type == templates.SUBJECT_TYPE:
        return templates.case_errors(facts, expected_output)
    if subject_type != rule_sets.SUBJECT_TYPE:
        return errors
    return rule_sets.case_errors(RuleSetKind(subject["kind"]), facts, expected_output)


def _lock_subject(uow: UnitOfWork, subject_type: str, subject_id: UUID) -> Mapping[str, Any]:
    """The example case's configuration version under ``FOR UPDATE``: 422 for a subject type whose
    versions do not exist yet; 404 for an unknown version."""
    table = CONFIG_SUBJECTS.get(subject_type)
    if table is None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="subject_type",
                    rule_id=rule_sets.RULE_TEST_CASE,
                    message=SUBJECT_UNSUPPORTED,
                )
            ],
        )
    row = (
        uow.session.execute(select(table).where(table.c.id == subject_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def _editable_subject(
    uow: UnitOfWork, subject_type: str, subject: Mapping[str, Any]
) -> Mapping[str, Any]:
    if subject_type == rule_sets.SUBJECT_TYPE:
        return lifecycle.require_editable(uow, KIND, subject)
    if subject_type == templates.SUBJECT_TYPE:
        return lifecycle.require_editable(uow, templates.POB_TEMPLATE_VERSION_KIND, subject)
    rule_sets.require_editable(subject)
    return subject


def create_config_test_case(
    uow: UnitOfWork,
    *,
    subject_type: str,
    subject_id: UUID,
    name: str,
    facts: Mapping[str, Any],
    expected_output: Mapping[str, Any],
) -> UUID:
    """``POST /config-test-cases`` and ``POST /rule-set-versions/{id}/test-cases``: a T-REF-27 row.

    422 for an unsupported subject type and for the name, facts and expected evaluation; 404 for an
    unknown version; 409 ``configuration-frozen`` unless the version is DRAFT or TESTED (DB-04).
    """
    session = uow.session
    subject = _lock_subject(uow, subject_type, subject_id)
    subject = _editable_subject(uow, subject_type, subject)
    errors = _case_errors(
        subject_type, subject, name=name, facts=facts, expected_output=expected_output
    )
    if errors:
        raise Problem("validation-failed", errors=errors)
    case_id = new_id()
    session.execute(
        insert(rule_test_case).values(
            tenant_id=uow.principal.tenant_id,
            id=case_id,
            subject_type=subject_type,
            subject_id=subject_id,
            name=name.strip(),
            input=dict(facts),
            expected_output=dict(expected_output),
            **_created(uow),
            **_updated(uow),
        )
    )
    record_facts(
        uow,
        action=CREATE_CASE_ACTION,
        object_type=rule_sets.OBJECT_TEST_CASE,
        ids=[case_id],
        detail={"subject_type": subject_type, "subject_id": str(subject_id)},
    )
    return case_id


def _locked_case(
    uow: UnitOfWork, case_id: UUID, check_version: Callable[[int], None]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """The example case and its version, locked version first (DG-KRN-DB-08), with ``If-Match``
    checked and the version editable."""
    session = uow.session
    found = (
        session.execute(
            select(rule_test_case.c.subject_type, rule_test_case.c.subject_id).where(
                rule_test_case.c.id == case_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    subject_type = str(found["subject_type"])
    subject = _lock_subject(uow, subject_type, UUID(str(found["subject_id"])))
    case = (
        session.execute(
            select(rule_test_case).where(rule_test_case.c.id == case_id).with_for_update()
        )
        .mappings()
        .one()
    )
    check_version(int(case["row_version"]))
    return MappingProxyType(dict(case)), _editable_subject(uow, subject_type, subject)


def update_config_test_case(
    uow: UnitOfWork,
    case_id: UUID,
    *,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> None:
    """``PATCH /config-test-cases/{id}``: 404; 412 or 428; 409 ``configuration-frozen``; 422. A
    changed case has not run, so ``last_result`` and ``last_run_at`` are cleared."""
    session = uow.session
    case, subject = _locked_case(uow, case_id, check_version)
    values = {name: changes[name] for name in CASE_COLUMNS if name in changes}
    merged = {**{name: case[name] for name in CASE_COLUMNS}, **values}
    errors = _case_errors(
        str(case["subject_type"]),
        subject,
        name=merged["name"],
        facts=merged["input"],
        expected_output=merged["expected_output"],
    )
    if errors:
        raise Problem("validation-failed", errors=errors)
    if not values:
        return
    if "name" in values:
        values["name"] = str(values["name"]).strip()
    session.execute(
        update(rule_test_case)
        .where(rule_test_case.c.id == case_id)
        .values(**values, last_result=None, last_run_at=None, **_touched(uow))
    )
    record_facts(
        uow,
        action=UPDATE_CASE_ACTION,
        object_type=rule_sets.OBJECT_TEST_CASE,
        ids=[case_id],
        detail={"subject_type": case["subject_type"], "fields": sorted(values)},
    )


def delete_config_test_case(
    uow: UnitOfWork, case_id: UUID, *, check_version: Callable[[int], None]
) -> None:
    """``DELETE /config-test-cases/{id}``: 404; 412 or 428; 409 ``configuration-frozen``."""
    case, _ = _locked_case(uow, case_id, check_version)
    uow.session.execute(delete(rule_test_case).where(rule_test_case.c.id == case_id))
    record_facts(
        uow,
        action=DELETE_CASE_ACTION,
        object_type=rule_sets.OBJECT_TEST_CASE,
        ids=[case_id],
        detail={"subject_type": case["subject_type"], "subject_id": str(case["subject_id"])},
    )


def lint_rule_set_version(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /rule-set-versions/{id}/lint``: stores ``lint_result`` (REQ-POL-002); 409
    ``configuration-frozen`` unless the version is DRAFT or TESTED."""
    session = uow.session
    version = rule_sets.lock_version(session, version_id)
    rule_sets.require_editable(version)
    result = rule_sets.lint_result(rule_sets.rule_rows(session, version_id), at=uow.now)
    session.execute(
        update(rule_set_version)
        .where(rule_set_version.c.id == version_id)
        .values(lint_result=result, **_touched(uow))
    )
    uow.audit(
        action=LINT_ACTION,
        object_type=rule_sets.OBJECT_VERSION,
        object_id=version_id,
        before={"lint_status": rule_sets.lint_status(version["lint_result"])},
        after={"lint_status": result["status"]},
        detail={"findings": result["findings"]},
    )


def run_rule_set_version_tests(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /rule-set-versions/{id}/test``: run every example case and the lint (REQ-POL-003).

    409 ``invalid-transition`` unless the version is DRAFT or TESTED; 422 without example cases.
    Each case records its result. When every case and the lint pass, a DRAFT version becomes TESTED
    with its content hash; otherwise it stays as it is and the evidence shows the failures.
    """
    session = uow.session
    version = rule_sets.lock_version(session, version_id)
    if version["status"] not in rule_sets.EDITABLE:
        raise lifecycle.refused(NOT_TESTABLE)
    kind = RuleSetKind(version["kind"])
    rules = rule_sets.rule_rows(session, version_id)
    cases = (
        session.execute(
            select(rule_test_case)
            .where(
                rule_test_case.c.subject_type == rule_sets.SUBJECT_TYPE,
                rule_test_case.c.subject_id == version_id,
            )
            .order_by(rule_test_case.c.id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if not cases:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="test_cases", rule_id=rule_sets.RULE_EVIDENCE, message=CASES_REQUIRED
                )
            ],
        )
    lint = rule_sets.lint_result(rules, at=uow.now)
    set_code = session.execute(
        select(rule_set.c.code).where(rule_set.c.id == version["rule_set_id"])
    ).scalar_one()
    results: list[dict[str, Any]] = []
    for case in cases:
        result, actual = rule_sets.run_case(kind, rules, dict(case), rule_set_code=str(set_code))
        session.execute(
            update(rule_test_case)
            .where(rule_test_case.c.id == case["id"])
            .values(last_result=result, last_run_at=uow.now, **_touched(uow))
        )
        results.append(
            {"test_case_id": case["id"], "name": case["name"], "result": result, "actual": actual}
        )
    session.execute(
        update(rule_set_version)
        .where(rule_set_version.c.id == version_id)
        .values(lint_result=lint, **_touched(uow))
    )
    passed = sum(1 for item in results if item["result"] == rule_sets.CASE_PASS)
    detail = {
        "passed": passed,
        "failed": len(results) - passed,
        "lint_status": lint["status"],
        "cases": results,
    }
    record_facts(
        uow,
        action=RUN_CASES_ACTION,
        object_type=rule_sets.OBJECT_TEST_CASE,
        ids=[UUID(str(case["id"])) for case in cases],
        detail={"subject_type": rule_sets.SUBJECT_TYPE, "subject_id": str(version_id)},
    )
    if passed == len(results) and lint["status"] == rule_sets.LINT_PASS:
        lifecycle.mark_tested(
            uow,
            KIND,
            version,
            content_sha256=lifecycle.current_sha256(session, KIND, version_id),
            detail=detail,
        )
        return
    uow.audit(
        action=TEST_ACTION,
        object_type=rule_sets.OBJECT_VERSION,
        object_id=version_id,
        after={"status": version["status"]},
        detail=detail,
    )


def submit_rule_set_version(uow: UnitOfWork, version_id: UUID, *, comment: str | None) -> None:
    """``POST /rule-set-versions/{id}/submit``: TESTED → SUBMITTED with the simulation report and
    an approval request of subject ``RULE_SET_VERSION`` (PRD BR-POL-01; BS3-D-05).

    409 ``invalid-transition`` with rule DB-03 unless TESTED, and with rule REQ-POL-003 when the
    tests no longer describe the content. A matching auto-approval rule publishes the version now.
    """
    version = rule_sets.lock_version(uow.session, version_id)

    def attach(current: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        report = simulation.simulate(
            uow,
            simulation.SimulationSubject(
                subject_type=rule_sets.SUBJECT_TYPE,
                subject_id=version_id,
                content_sha256=str(current["content_sha256"]),
            ),
        )
        return (
            {"impact_simulation_file_id": report.file_id},
            {"impact_simulation": {"file_id": report.file_id, "summary": report.summary}},
        )

    lifecycle.submit(uow, KIND, version, comment=comment, attach=attach)


def publish_rule_set_version(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /rule-set-versions/{id}/publish``: publishes a version left APPROVED; a PUBLISHED
    version answers as it is (04 §16.5 publish note). 409 ``invalid-transition`` otherwise; 422
    for lint findings (REQ-POL-002) and the effective date order."""
    version = rule_sets.lock_version(uow.session, version_id)
    lifecycle.publish(
        uow,
        KIND,
        version,
        approval_request_id=version["approval_request_id"],
        published_by=uow.principal.id,
    )


# --- obligation templates (API-R-24; BUILD_SPEC RFD-10) ----------------------------------------

TEMPLATE_KIND: Final = templates.POB_TEMPLATE_VERSION_KIND
CREATE_TEMPLATE_ACTION: Final = "pob_template.create"
CREATE_TEMPLATE_VERSION_ACTION: Final = "pob_template_version.create"
UPDATE_TEMPLATE_VERSION_ACTION: Final = "pob_template_version.update"
# T-REF-23 NOT NULL outputs a request may not set to null; ``templates.output_errors`` reports the
# two outputs without a default.
TEMPLATE_NOT_NULL: Final = frozenset(templates.OUTPUT_COLUMNS) - {
    "series_increment_unit",
    "ratable_convention",
    "term_months",
    "revenue_category",
    "stratification_label",
    *templates.REQUIRED_OUTPUTS,
}
TEMPLATE_TEXT_OUTPUTS: Final = ("revenue_category", "stratification_label")


def create_pob_template(uow: UnitOfWork, *, code: str, name: str, description: str | None) -> UUID:
    """``POST /pob-templates``: the new template's id; 422 when the code is taken or the name is
    blank (T-REF-22)."""
    session = uow.session
    errors: list[ProblemError] = []
    taken = session.execute(select(pob_template.c.id).where(pob_template.c.code == code)).first()
    if taken is not None:
        message = templates.CODE_TAKEN.format(code=code)
        errors.append(ProblemError(field="code", rule_id=templates.RULE_TEMPLATE, message=message))
    label = name.strip()
    if not label:
        errors.append(
            ProblemError(
                field="name", rule_id=templates.RULE_TEMPLATE, message=rule_sets.NAME_EMPTY
            )
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    template_id = new_id()
    memo = None if description is None or not description.strip() else description.strip()
    values = {"code": code, "name": label, "description": memo}
    session.execute(
        insert(pob_template).values(
            tenant_id=uow.principal.tenant_id,
            id=template_id,
            **values,
            **_created(uow),
            **_updated(uow),
        )
    )
    uow.audit(
        action=CREATE_TEMPLATE_ACTION,
        object_type=templates.OBJECT_TEMPLATE,
        object_id=template_id,
        after=values,
    )
    return template_id


def _text_outputs(changes: Mapping[str, Any]) -> dict[str, Any]:
    """The request's outputs with free-text members trimmed; a blank value is none."""
    normalised = dict(changes)
    for name in TEMPLATE_TEXT_OUTPUTS:
        if normalised.get(name) is not None:
            normalised[name] = str(normalised[name]).strip() or None
    return normalised


def _template_outputs(
    uow: UnitOfWork, base: Mapping[str, Any], changes: Mapping[str, Any]
) -> dict[str, Any]:
    """The outputs of ``base`` with ``changes`` applied; 422 ``validation-failed`` lists every
    finding (T-REF-23; DG-CMD-03)."""
    normalised = _text_outputs(changes)
    errors = [
        ProblemError(field=name, rule_id=templates.RULE_VERSION, message=VALUE_REQUIRED)
        for name in templates.OUTPUT_COLUMNS
        if name in TEMPLATE_NOT_NULL and name in normalised and normalised[name] is None
    ]
    applied = {
        name: value
        for name, value in normalised.items()
        if not (name in TEMPLATE_NOT_NULL and value is None)
    }
    merged = templates.merged_outputs(base, applied)
    errors += templates.output_errors(uow.session, merged)
    if errors:
        raise Problem("validation-failed", errors=errors)
    return merged


def _copy_template_cases(
    uow: UnitOfWork, *, source_version_id: UUID, version_id: UUID
) -> list[UUID]:
    """Copy the example cases of ``source_version_id`` to the new DRAFT version."""
    session = uow.session
    case_ids: list[UUID] = []
    cases = session.execute(
        select(rule_test_case)
        .where(
            rule_test_case.c.subject_type == templates.SUBJECT_TYPE,
            rule_test_case.c.subject_id == source_version_id,
        )
        .order_by(rule_test_case.c.id)
    ).mappings()
    for case in cases:
        case_id = new_id()
        session.execute(
            insert(rule_test_case).values(
                tenant_id=uow.principal.tenant_id,
                id=case_id,
                subject_type=templates.SUBJECT_TYPE,
                subject_id=version_id,
                name=case["name"],
                input=case["input"],
                expected_output=case["expected_output"],
                **_created(uow),
                **_updated(uow),
            )
        )
        case_ids.append(case_id)
    return case_ids


def create_pob_template_version(
    uow: UnitOfWork,
    template_id: UUID,
    *,
    changes: Mapping[str, Any],
    effective_from: datetime | None,
    source_version_id: UUID | None,
) -> UUID:
    """``POST /pob-templates/{id}/versions``: the next version as DRAFT (PRD SM-04).

    404 for an unknown template; 409 ``invalid-transition`` while another version of the template
    is DRAFT, TESTED, SUBMITTED or APPROVED; 422 when ``source_version_id`` is not a version of the
    template, and for the outputs (T-REF-23). The outputs start from the column defaults, or from
    the copied version, and the request's members replace them. The version records the PUBLISHED
    version it will supersede.
    """
    session = uow.session
    found = session.execute(
        select(pob_template.c.id).where(pob_template.c.id == template_id).with_for_update()
    ).scalar_one_or_none()
    if found is None:
        raise Problem("not-found")
    versions = (
        session.execute(
            select(pob_template_version)
            .where(pob_template_version.c.pob_template_id == template_id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if any(version["status"] in rule_sets.OPEN_STATUSES for version in versions):
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(rule_id=templates.RULE_OPEN_VERSION, message=templates.VERSION_OPEN)
            ],
        )
    source = next((version for version in versions if version["id"] == source_version_id), None)
    if source_version_id is not None and source is None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="source_version_id",
                    rule_id=templates.RULE_VERSION,
                    message=templates.SOURCE_UNKNOWN,
                )
            ],
        )
    outputs = _template_outputs(
        uow, templates.OUTPUT_DEFAULTS if source is None else dict(source), changes
    )
    published = next(
        (
            version["id"]
            for version in versions
            if version["status"] == ConfigStatus.PUBLISHED.value
        ),
        None,
    )
    version_no = max((int(version["version_no"]) for version in versions), default=0) + 1
    version_id = new_id()
    session.execute(
        insert(pob_template_version).values(
            tenant_id=uow.principal.tenant_id,
            id=version_id,
            pob_template_id=template_id,
            **outputs,
            **_created(uow),
            **_updated(uow),
            version_no=version_no,
            status=ConfigStatus.DRAFT.value,
            effective_from=effective_from,
            supersedes_version_id=published,
        )
    )
    case_ids: list[UUID] = []
    if source_version_id is not None:
        case_ids = _copy_template_cases(
            uow, source_version_id=source_version_id, version_id=version_id
        )
    uow.audit(
        action=CREATE_TEMPLATE_VERSION_ACTION,
        object_type=templates.OBJECT_VERSION,
        object_id=version_id,
        after={
            "pob_template_id": template_id,
            "version_no": version_no,
            "status": ConfigStatus.DRAFT.value,
            "effective_from": effective_from,
            "supersedes_version_id": published,
            **outputs,
        },
        detail={"source_version_id": source_version_id, "test_cases_copied": len(case_ids)},
    )
    if case_ids:
        record_facts(
            uow,
            action=CREATE_CASE_ACTION,
            object_type=rule_sets.OBJECT_TEST_CASE,
            ids=case_ids,
            detail={"subject_type": templates.SUBJECT_TYPE, "subject_id": str(version_id)},
        )
    return version_id


def update_pob_template_version(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> None:
    """``PATCH /pob-template-versions/{id}``: 404; 412 or 428 for ``If-Match``; 409
    ``configuration-frozen`` outside DRAFT and TESTED (a REJECTED or WITHDRAWN version reopens as
    DRAFT); 422 for the merged outputs. An unchanged request writes nothing."""
    session = uow.session
    version = templates.lock_version(session, version_id)
    check_version(int(version["row_version"]))
    version = lifecycle.require_editable(uow, TEMPLATE_KIND, version)
    output_changes = {
        name: value for name, value in changes.items() if name in templates.OUTPUT_COLUMNS
    }
    merged = _template_outputs(uow, version, output_changes)
    values = {
        name: merged[name] for name in templates.OUTPUT_COLUMNS if merged[name] != version[name]
    }
    if "effective_from" in changes and changes["effective_from"] != version["effective_from"]:
        values["effective_from"] = changes["effective_from"]
    if not values:
        return
    session.execute(
        update(pob_template_version)
        .where(pob_template_version.c.id == version_id)
        .values(**values, **_touched(uow))
    )
    uow.audit(
        action=UPDATE_TEMPLATE_VERSION_ACTION,
        object_type=templates.OBJECT_VERSION,
        object_id=version_id,
        before={name: version[name] for name in values},
        after=values,
    )


def run_pob_template_version_tests(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /pob-template-versions/{id}/test``: ``templates.run_test_cases`` (REQ-POL-003)."""
    templates.run_test_cases(uow, version_id)


def submit_pob_template_version(uow: UnitOfWork, version_id: UUID, *, comment: str | None) -> None:
    """``POST /pob-template-versions/{id}/submit``: TESTED → SUBMITTED and an approval request of
    subject ``POB_TEMPLATE_VERSION`` (PRD BR-POL-01).

    409 ``invalid-transition`` with rule DB-03 unless TESTED, and with rule REQ-POL-003 when the
    tests no longer describe the content or a case has not passed. T-REF-23 has no simulation
    column, so the report's file id travels in the submission's audit detail (L2-1-Q-49).
    """
    version = templates.lock_version(uow.session, version_id)

    def attach(current: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        report = simulation.simulate(
            uow,
            simulation.SimulationSubject(
                subject_type=templates.SUBJECT_TYPE,
                subject_id=version_id,
                content_sha256=str(current["content_sha256"]),
            ),
        )
        return {}, {"impact_simulation": {"file_id": report.file_id, "summary": report.summary}}

    lifecycle.submit(uow, TEMPLATE_KIND, version, comment=comment, attach=attach)


def publish_pob_template_version(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /pob-template-versions/{id}/publish``: publishes a version left APPROVED; a PUBLISHED
    version answers as it is (04 §16.5 publish note). 409 ``invalid-transition`` otherwise."""
    version = templates.lock_version(uow.session, version_id)
    lifecycle.publish(
        uow,
        TEMPLATE_KIND,
        version,
        approval_request_id=version["approval_request_id"],
        published_by=uow.principal.id,
    )

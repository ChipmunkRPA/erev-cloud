"""Account-role mapping versions and account resolution (04 T-REF-14, T-REF-15, E-01, E-109, §14.1
DB-04, §15.2 ``unmapped-account-role``, §15.4 ``ACCOUNT_MAPPING_MISSING``; POLICIES §0.8; PRD §2.6,
SM-04, ERR-46; SCREENS §9.6; 03 REQ-REF-008, REQ-POL-002; CTL-031; BUILD_SPEC RFD-7).

Rules. A rule maps an ``account_role`` (with a clearing purpose for ``BILLING_CLEARING``) and an
optional entity, book, and product or revenue category to a GL account. ``RETAINED_EARNINGS`` and
``FINANCING_OBLIGATION`` accept no rule; a ``BILLING_CLEARING`` rule names its purpose and no other
rule names one (D-14a). ``lint_findings`` refuses two rules with equal role, purpose, key columns
and priority, whose specificity is then equal too (REQ-POL-002).

Resolution (``resolve_account``; T-REF-15 steps 1 to 4): the obligation override for the key; the
POB template version's override; the highest-specificity, then highest-priority rule of the
PUBLISHED version effective at ``known_at`` whose role and purpose equal the key and whose key
columns are null or equal the line's; otherwise 422 ``unmapped-account-role`` with rule
``ACCOUNT_MAPPING_MISSING`` naming contract, obligation, role and purpose (fail closed). The
override key is the role literal, or ``BILLING_CLEARING:<purpose>``.

Versions (L2-1-Q-2). PUBLISHED versions are effective-dated and coexist: publication ends the
PUBLISHED version in force at the new version's ``effective_from`` there, and a PUBLISHED version
starting at the same instant becomes SUPERSEDED. Any other overlap of PUBLISHED ranges returns 409
``configuration-overlap`` (DB-04 ``EREV-CFG-001``). Approval publishes the version in the approval
transaction (04 §16.5 publish note; SCREENS §11.0), and ``/publish`` stays for a version left
APPROVED. The version's author never approves it (REQ-POL-003; CTL-031).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    approval_decision,
    gl_account,
    legal_entity,
)
from erev_api.domain.policies import lifecycle
from erev_api.enums import (
    AccountRole,
    ApprovalDecisionKind,
    ApprovalSubjectType,
    BookCode,
    ClearingPurpose,
    ConfigStatus,
)
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

OBJECT_VERSION: Final = "account_mapping_version"
OBJECT_RULE: Final = "account_mapping_rule"
SUBJECT_TYPE: Final = "account_mapping_version"  # 04 T-REF-27 subject type literal
END_ACTION: Final = "account_mapping_version.end"
RULE_VERSION: Final = "T-REF-14"
RULE_RULE: Final = "T-REF-15"
RULE_LINT: Final = "REQ-POL-002"
RULE_MISSING: Final = "ACCOUNT_MAPPING_MISSING"  # 04 Table 15.4-A
RULE_OVERLAP: Final = "DB-04"
OVERLAP_CODE: Final = "EREV-CFG-001"
CLEARING_ROLE: Final = AccountRole.BILLING_CLEARING.value
RESERVED_ROLES: Final = frozenset(
    {AccountRole.RETAINED_EARNINGS.value, AccountRole.FINANCING_OBLIGATION.value}
)
SOURCE_OBLIGATION: Final = "obligation_override"
SOURCE_TEMPLATE: Final = "template_override"
SOURCE_RULE: Final = "account_mapping_rule"

# SCREENS §9.6 catalogue ``accountRole.<literal>`` and the clearing purpose labels.
ROLE_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "REVENUE": "Revenue",
        "CONTRACT_LIABILITY": "Contract liability",
        "CONTRACT_ASSET": "Contract asset",
        "UNBILLED_RECEIVABLE": "Unbilled receivable",
        "ACCOUNTS_RECEIVABLE": "Accounts receivable",
        "BILLING_CLEARING": "Billing clearing",
        "REFUND_LIABILITY": "Refund liability",
        "RETURN_ASSET": "Return asset",
        "DEPOSIT_LIABILITY": "Deposit liability",
        "CONSIDERATION_PAYABLE": "Consideration payable to a customer",
        "CUSTOMER_INCENTIVE_ASSET": "Customer incentive asset",
        "COST_TO_OBTAIN_ASSET": "Capitalised cost to obtain",
        "COST_TO_FULFILL_ASSET": "Capitalised cost to fulfil",
        "CONTRACT_COST_AMORTIZATION": "Contract cost amortisation",
        "CONTRACT_COST_IMPAIRMENT": "Contract cost impairment",
        "LOSS_PROVISION": "Loss provision",
        "LOSS_EXPENSE": "Loss expense",
        "WARRANTY_PROVISION": "Warranty provision",
        "WARRANTY_EXPENSE": "Warranty expense",
        "INTEREST_INCOME": "Interest income",
        "INTEREST_EXPENSE": "Interest expense",
        "FX_GAIN_LOSS": "Foreign exchange gain or loss",
        "INTERCOMPANY_DUE_TO": "Intercompany due to",
        "INTERCOMPANY_DUE_FROM": "Intercompany due from",
        "NONCASH_CONSIDERATION_ASSET": "Noncash consideration asset",
        "SALES_TAX_PAYABLE": "Sales tax payable",
        "PRE_STANDARD_REVENUE": "Pre-standard revenue",
        "ROUNDING": "Rounding",
        "COST_OF_REVENUE": "Cost of revenue",
        "CONTRACT_COST_CLEARING": "Contract cost clearing",
        "RECEIVABLE_CONTRA": "Receivable contra",
        "RETAINED_EARNINGS": "Retained earnings (reserved)",
        "FINANCING_OBLIGATION": "Financing obligation (reserved)",
    }
)
PURPOSE_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "BILLING": "Billing",
        "UNAPPLIED_CASH": "Unapplied cash",
        "AP_SUPPLIER": "Supplier payables",
        "INVENTORY": "Inventory",
        "EQUITY": "Equity",
        "INVESTMENTS": "Investments",
    }
)

# Copy: SCREENS §9.6 validation copy; PRD ERR-46 with the role label and entity code.
PURPOSE_REQUIRED: Final = "Choose a clearing purpose for billing clearing."
PURPOSE_NOT_ALLOWED: Final = "A clearing purpose applies only to billing clearing."
PRODUCT_AND_CATEGORY: Final = "Set a product or a revenue category, not both."
AMBIGUOUS: Final = (
    "Rules {first} and {second} resolve the same role, clearing purpose and key with equal "
    "specificity and priority."
)
MISSING: Final = (
    "No account is mapped for role {role} for {entity}. Publish an account mapping, then retry."
)
# [J] Copy the documents leave open.
RESERVED_ROLE: Final = "{label} is reserved: no mapping rule is allowed."
ANY_ENTITY: Final = "any entity"
EFFECTIVE_REQUIRED: Final = "Choose the date from which this mapping takes effect."
OVERLAP: Final = "The effective range of this version overlaps published version {version_no}."


def override_key(role: str, clearing_purpose: str | None) -> str:
    """The T-REF-15 override key: the role literal, or ``BILLING_CLEARING:<purpose>``."""
    if role == CLEARING_ROLE and clearing_purpose is not None:
        return f"{role}:{clearing_purpose}"
    return role


def specificity(
    *,
    entity_id: UUID | None,
    book_code: str | None,
    product_id: UUID | None,
    revenue_category: str | None,
) -> int:
    """The generated T-REF-15 ``specificity``: entity 8, book 4, product or revenue category 2."""
    return (
        (8 if entity_id is not None else 0)
        + (4 if book_code is not None else 0)
        + (2 if product_id is not None or revenue_category is not None else 0)
    )


def role_errors(account_role: str, clearing_purpose: str | None) -> list[ProblemError]:
    """D-14a: reserved roles accept no rule; ``BILLING_CLEARING`` and only it names a purpose."""
    errors: list[ProblemError] = []
    if account_role in RESERVED_ROLES:
        label = ROLE_LABELS[account_role]
        errors.append(
            ProblemError(
                field="account_role", rule_id=RULE_RULE, message=RESERVED_ROLE.format(label=label)
            )
        )
    if account_role == CLEARING_ROLE and clearing_purpose is None:
        errors.append(
            ProblemError(field="clearing_purpose", rule_id=RULE_RULE, message=PURPOSE_REQUIRED)
        )
    elif account_role != CLEARING_ROLE and clearing_purpose is not None:
        errors.append(
            ProblemError(field="clearing_purpose", rule_id=RULE_RULE, message=PURPOSE_NOT_ALLOWED)
        )
    return errors


def key_errors(product_id: UUID | None, revenue_category: str | None) -> list[ProblemError]:
    """T-REF-15 ``CHECK (product_id IS NULL OR revenue_category IS NULL)``."""
    if product_id is not None and revenue_category is not None:
        return [
            ProblemError(field="revenue_category", rule_id=RULE_RULE, message=PRODUCT_AND_CATEGORY)
        ]
    return []


RULE_COLUMNS: Final = (
    account_mapping_rule.c.id,
    account_mapping_rule.c.account_mapping_version_id,
    account_mapping_rule.c.account_role,
    account_mapping_rule.c.clearing_purpose,
    account_mapping_rule.c.entity_id,
    account_mapping_rule.c.book_code,
    account_mapping_rule.c.product_id,
    account_mapping_rule.c.revenue_category,
    account_mapping_rule.c.gl_account_id,
    gl_account.c.code.label("gl_account_code"),
    gl_account.c.name.label("gl_account_name"),
    account_mapping_rule.c.default_dimensions,
    account_mapping_rule.c.priority,
    account_mapping_rule.c.specificity,
)
RULE_JOIN: Final = account_mapping_rule.join(
    gl_account,
    and_(
        gl_account.c.tenant_id == account_mapping_rule.c.tenant_id,
        gl_account.c.id == account_mapping_rule.c.gl_account_id,
    ),
)


def rule_rows(session: Session, version_id: UUID) -> list[dict[str, Any]]:
    """The rules of a version in creation order (UUIDv7 ids), with GL account code and name."""
    statement = (
        select(*RULE_COLUMNS)
        .select_from(RULE_JOIN)
        .where(account_mapping_rule.c.account_mapping_version_id == version_id)
        .order_by(account_mapping_rule.c.id)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _lint_key(rule: Mapping[str, Any]) -> tuple[str | None, ...]:
    names = ("account_role", "clearing_purpose", "entity_id", "book_code", "product_id")
    values = [None if rule[name] is None else str(rule[name]) for name in names]
    return (*values, rule["revenue_category"], str(int(rule["priority"])))


def lint_findings(rules: Sequence[Mapping[str, Any]]) -> list[ProblemError]:
    """REQ-POL-002: each pair of rules with equal role, clearing purpose, key columns and priority,
    numbered by their position in ``rules`` (creation order)."""
    keys = [_lint_key(rule) for rule in rules]
    return [
        ProblemError(
            field="rules",
            rule_id=RULE_LINT,
            message=AMBIGUOUS.format(first=first + 1, second=second + 1),
        )
        for first in range(len(rules))
        for second in range(first + 1, len(rules))
        if keys[first] == keys[second]
    ]


# --- resolution (T-REF-15 steps 1 to 4) ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MappingProblemError(ProblemError):
    """An ``ACCOUNT_MAPPING_MISSING`` error naming the line it blocks (REQ-REF-008; L2-1-Q-6)."""

    contract: str | None = None
    obligation_key: str | None = None
    role: str | None = None
    clearing_purpose: str | None = None
    entity: str | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    """The GL account of a role and the T-REF-15 step that answered."""

    gl_account_id: UUID
    gl_account_code: str
    gl_account_name: str
    source_type: str
    override_key: str
    rule_id: UUID | None = None
    account_mapping_version_id: UUID | None = None
    version_no: int | None = None
    specificity: int | None = None
    priority: int | None = None
    default_dimensions: Mapping[str, Any] = field(default_factory=dict)


def published_version_at(session: Session, known_at: datetime) -> Mapping[str, Any] | None:
    """The PUBLISHED version whose ``[effective_from, effective_to)`` contains ``known_at``;
    PUBLISHED ranges never overlap (DB-04)."""
    version = account_mapping_version
    statement = (
        select(version.c.id, version.c.version_no)
        .where(
            version.c.status == ConfigStatus.PUBLISHED.value,
            or_(version.c.effective_from.is_(None), version.c.effective_from <= known_at),
            or_(version.c.effective_to.is_(None), version.c.effective_to > known_at),
        )
        .order_by(version.c.effective_from.desc().nulls_last())
        .limit(1)
    )
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def _entity_label(session: Session, entity_id: UUID | None, entity_code: str | None) -> str:
    if entity_code is not None:
        return entity_code
    if entity_id is None:
        return ANY_ENTITY
    code = session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == entity_id)
    ).scalar_one_or_none()
    return str(entity_id) if code is None else str(code)


def missing(
    *,
    role: str,
    clearing_purpose: str | None,
    entity: str,
    contract: str | None,
    obligation_key: str | None,
) -> Problem:
    """422 ``unmapped-account-role`` with the ``ACCOUNT_MAPPING_MISSING`` error (PRD ERR-46)."""
    label = ROLE_LABELS.get(role, role)
    if clearing_purpose is not None:
        label = f"{label} ({PURPOSE_LABELS.get(clearing_purpose, clearing_purpose)})"
    message = MISSING.format(role=label, entity=entity)
    error = MappingProblemError(
        rule_id=RULE_MISSING,
        message=message,
        contract=contract,
        obligation_key=obligation_key,
        role=role,
        clearing_purpose=clearing_purpose,
        entity=entity,
    )
    return Problem("unmapped-account-role", message, errors=[error])


def resolve_account(
    session: Session,
    *,
    role: AccountRole | str,
    known_at: datetime,
    clearing_purpose: ClearingPurpose | str | None = None,
    entity_id: UUID | None = None,
    book_code: BookCode | str | None = None,
    product_id: UUID | None = None,
    revenue_category: str | None = None,
    obligation_overrides: Mapping[str, UUID | str] | None = None,
    template_overrides: Mapping[str, UUID | str] | None = None,
    contract: str | None = None,
    obligation_key: str | None = None,
    entity_code: str | None = None,
) -> Resolution:
    """The GL account of a journal line's role, in the T-REF-15 resolution order.

    ``obligation_overrides`` (``obligation_version.account_overrides``) and ``template_overrides``
    (``pob_template_version.account_role_overrides``) map an override key to a ``gl_account.id``.
    A missing account, or an override naming an account that is not visible, raises 422
    ``unmapped-account-role`` naming ``contract``, ``obligation_key``, the role and the purpose.
    """
    role_value = AccountRole(role).value
    purpose = None if clearing_purpose is None else ClearingPurpose(clearing_purpose).value
    book = None if book_code is None else BookCode(book_code).value
    key = override_key(role_value, purpose)

    def fail() -> Problem:
        return missing(
            role=role_value,
            clearing_purpose=purpose,
            entity=_entity_label(session, entity_id, entity_code),
            contract=contract,
            obligation_key=obligation_key,
        )

    for source, overrides in (
        (SOURCE_OBLIGATION, obligation_overrides),
        (SOURCE_TEMPLATE, template_overrides),
    ):
        value = None if overrides is None else overrides.get(key)
        if value is None:
            continue
        account = (
            session.execute(
                select(gl_account.c.id, gl_account.c.code, gl_account.c.name).where(
                    gl_account.c.id == UUID(str(value))
                )
            )
            .mappings()
            .first()
        )
        if account is None:
            raise fail()
        return Resolution(
            gl_account_id=UUID(str(account["id"])),
            gl_account_code=str(account["code"]),
            gl_account_name=str(account["name"]),
            source_type=source,
            override_key=key,
        )
    version = published_version_at(session, known_at)
    if version is None:
        raise fail()
    rule = account_mapping_rule
    statement = (
        select(*RULE_COLUMNS)
        .select_from(RULE_JOIN)
        .where(
            rule.c.account_mapping_version_id == version["id"],
            rule.c.account_role == role_value,
            rule.c.clearing_purpose.is_not_distinct_from(purpose),
            or_(rule.c.entity_id.is_(None), rule.c.entity_id == entity_id),
            or_(rule.c.book_code.is_(None), rule.c.book_code == book),
            or_(rule.c.product_id.is_(None), rule.c.product_id == product_id),
            or_(rule.c.revenue_category.is_(None), rule.c.revenue_category == revenue_category),
        )
        # [J] Equal specificity and priority across different keys (a product rule and a category
        # rule): the product rule, then the earliest rule (L2-1-Q-4).
        .order_by(
            rule.c.specificity.desc(),
            rule.c.priority.desc(),
            rule.c.product_id.is_(None),
            rule.c.id,
        )
        .limit(1)
    )
    found = session.execute(statement).mappings().first()
    if found is None:
        raise fail()
    return Resolution(
        gl_account_id=UUID(str(found["gl_account_id"])),
        gl_account_code=str(found["gl_account_code"]),
        gl_account_name=str(found["gl_account_name"]),
        source_type=SOURCE_RULE,
        override_key=key,
        rule_id=UUID(str(found["id"])),
        account_mapping_version_id=UUID(str(version["id"])),
        version_no=int(version["version_no"]),
        specificity=int(found["specificity"]),
        priority=int(found["priority"]),
        default_dimensions=dict(found["default_dimensions"]),
    )


# --- the configuration lifecycle of account mapping versions -----------------------------------


def _snapshot(session: Session, version_id: UUID) -> dict[str, Any]:
    """The field-level ``before`` and ``after`` of publication audits: the rules."""
    return {"rules": subjects.account_mapping_version_content(session, version_id)["rules"]}


def _submit_errors(_session: Session, _version: Mapping[str, Any]) -> list[ProblemError]:
    """Nothing beyond the content hash: ``/test`` ran the lint on that content."""
    return []


def _publish_errors(session: Session, version: Mapping[str, Any]) -> list[ProblemError]:
    return lint_findings(rule_rows(session, version["id"]))


def _summary(_session: Session, version: Mapping[str, Any]) -> str:
    return f"Publish version {version['version_no']} of account mapping {version['name']}"


VERSION_LOCK: Final = "erev.account_mapping_version:{tenant_id}"


def serialise_versions(uow: UnitOfWork, _version: Mapping[str, Any] | None = None) -> None:
    """The transaction advisory lock of the tenant's account mapping versions: the first version
    has no row to lock, so the create takes it before it looks for an open version (PRD SM-04) —
    and so does the reopening of a rejected or withdrawn version (``lifecycle.reopen``), which
    otherwise misses a create that has not committed."""
    key = VERSION_LOCK.format(tenant_id=uow.principal.tenant_id)
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


ACCOUNT_MAPPING_VERSION_KIND: Final = lifecycle.ConfigVersionKind(
    table=account_mapping_version,
    subject_type=ApprovalSubjectType.ACCOUNT_MAPPING_VERSION,
    scope_columns=(),
    content=subjects.account_mapping_version_content,
    snapshot=_snapshot,
    submit_errors=_submit_errors,
    publish_errors=_publish_errors,
    summary=_summary,
    serialise=serialise_versions,
)


def _contains(row: Mapping[str, Any], instant: datetime) -> bool:
    starts = row["effective_from"] is None or row["effective_from"] <= instant
    return bool(starts and (row["effective_to"] is None or row["effective_to"] > instant))


def publish(
    uow: UnitOfWork,
    version: Mapping[str, Any],
    *,
    approval_request_id: UUID | None,
    published_by: UUID | None,
) -> Mapping[str, Any]:
    """APPROVED → PUBLISHED; a PUBLISHED version is returned as it is (04 §16.5 publish note).

    409 ``invalid-transition`` for any other status; 422 ``validation-failed`` for lint findings
    (REQ-POL-002) or a missing ``effective_from``; 409 ``configuration-overlap`` when a PUBLISHED
    version other than the one in force at ``effective_from`` reaches past it (DB-04). The version
    in force there ends at ``effective_from``, or becomes SUPERSEDED when it starts at that instant.
    """
    kind = ACCOUNT_MAPPING_VERSION_KIND
    if version["status"] == ConfigStatus.PUBLISHED.value:
        return version
    if version["status"] != ConfigStatus.APPROVED.value:
        raise lifecycle.refused(lifecycle.NOT_APPROVED)
    session = uow.session
    errors = _publish_errors(session, version)
    effective_from: datetime | None = version["effective_from"]
    if effective_from is None:
        errors.append(
            ProblemError(field="effective_from", rule_id=RULE_VERSION, message=EFFECTIVE_REQUIRED)
        )
    if errors or effective_from is None:
        raise Problem("validation-failed", errors=errors)
    table = account_mapping_version
    published = [
        dict(row)
        for row in session.execute(
            select(table)
            .where(table.c.id != version["id"], table.c.status == ConfigStatus.PUBLISHED.value)
            .order_by(table.c.version_no)
            .with_for_update()
        ).mappings()
    ]
    prior = next((row for row in published if _contains(row, effective_from)), None)
    reaching = [
        row
        for row in published
        if row is not prior
        and (row["effective_to"] is None or row["effective_to"] > effective_from)
    ]
    if reaching:
        message = OVERLAP.format(version_no=reaching[0]["version_no"])
        raise Problem(
            "configuration-overlap",
            code=OVERLAP_CODE,
            errors=[ProblemError(field="effective_from", rule_id=RULE_OVERLAP, message=message)],
        )
    snapshot = dict(_snapshot(session, version["id"]))
    if prior is not None and prior["effective_from"] == effective_from:
        lifecycle.transition(
            uow,
            kind,
            dict(prior),
            ConfigStatus.SUPERSEDED,
            detail={"superseded_by_version_id": version["id"]},
            approval_request_id=approval_request_id,
        )
    elif prior is not None:
        principal = uow.principal
        session.execute(
            update(table)
            .where(table.c.id == prior["id"])
            .values(
                effective_to=effective_from,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
        uow.audit(
            action=END_ACTION,
            object_type=OBJECT_VERSION,
            object_id=prior["id"],
            before={"effective_to": prior["effective_to"]},
            after={"effective_to": effective_from},
            detail={"superseded_by_version_id": version["id"]},
            approval_request_id=approval_request_id,
        )
    values = {"published_at": uow.now, "published_by": published_by}
    return lifecycle.transition(
        uow,
        kind,
        version,
        ConfigStatus.PUBLISHED,
        values=values,
        before={"published_at": None, "published_by": None},
        after={**values, **snapshot},
        detail={
            "effective_from": effective_from,
            "prior_version_id": None if prior is None else prior["id"],
        },
        approval_request_id=approval_request_id,
    )


def _approvers(session: Session, approval_request_id: UUID) -> set[UUID]:
    """The people whose APPROVE decisions the request holds, delegators included."""
    rows = session.execute(
        select(approval_decision.c.approver_id, approval_decision.c.on_behalf_of_id).where(
            approval_decision.c.approval_request_id == approval_request_id,
            approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
        )
    ).all()
    return {UUID(str(value)) for row in rows for value in row if value is not None}


def approve(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> None:
    """``SubjectSpec.on_approved``: SUBMITTED → APPROVED, then publication in the same transaction.

    An approval by the version's author raises 403 ``self-approval`` (REQ-POL-003; SoD-5); a refusal
    of publication rolls the decision back.
    """
    kind = ACCOUNT_MAPPING_VERSION_KIND
    session = uow.session
    version = lifecycle.lock(session, kind, version_id)
    if version["status"] != ConfigStatus.SUBMITTED.value:
        raise lifecycle.refused(lifecycle.NOT_SUBMITTED)
    approvers = _approvers(session, approval_request_id)
    if version["created_by"] is not None and UUID(str(version["created_by"])) in approvers:
        raise Problem("self-approval", lifecycle.AUTHOR_DETAIL)
    approved = lifecycle.transition(
        uow,
        kind,
        version,
        ConfigStatus.APPROVED,
        values={"approval_request_id": approval_request_id},
        after={"approval_request_id": approval_request_id},
        approval_request_id=approval_request_id,
    )
    principal_id = uow.principal.id
    publish(
        uow,
        approved,
        approval_request_id=approval_request_id,
        published_by=principal_id if principal_id in approvers else None,
    )


def _on_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    approve(uow, subject_id, approval_request_id)


def _on_rejected(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(
        uow,
        ACCOUNT_MAPPING_VERSION_KIND,
        subject_id,
        approval_request_id,
        to_status=ConfigStatus.REJECTED,
    )


def _on_voided(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(
        uow,
        ACCOUNT_MAPPING_VERSION_KIND,
        subject_id,
        approval_request_id,
        to_status=ConfigStatus.WITHDRAWN,
    )


subjects.register_lifecycle(
    ApprovalSubjectType.ACCOUNT_MAPPING_VERSION,
    subjects.SubjectLifecycle(
        on_approved=_on_approved, on_rejected=_on_rejected, on_voided=_on_voided
    ),
)

"""Estimates and estimate versions (04 T-CON-12, T-CON-13, E-09, E-10, E-12, §15.3 API-R-32, §16.14
estimates, table 15.4-D; ENGINE_SPEC §8.3, S01-R-18; POLICIES ALG-10, POL-040; 05 §3.6.8 EMOD-24;
PRD SM-04, §2.5 routing row ``ESTIMATE_VERSION``, ERR-13, IMP-71, IMP-74, WLD-X-16; 03 REQ-TP-004,
REQ-TP-005; CTL-013; BUILD_SPEC CTR-12).

``create_estimate`` stores a T-CON-12 element of a visible contract; the preparer holds
``estimate.create`` for the contracting entity. The findings are collected (422
``validation-failed``): a variable consideration names its element type; the direction follows the
04 checks (a price concession reduces the price, other kinds increase it), and when it is not sent
it defaults to ``DECREASE`` for price concessions and the reducing element types of B3-DG-17; the
obligation and target keys name obligations of the contract (T-CON-10); a non-contract target has
606-10-32-40 evidence; the element code is unique on the contract.

``create_version`` and ``update_version`` store and edit DRAFT versions, and ``submit_version``
routes one under subject ``ESTIMATE_VERSION``. Each validates, collecting the findings: the method,
when sent, is the element's (``ESTIMATE_METHOD_LOCKED``, IMP-71; POL-040), the parameters match the
kind's schema (``schemas.db_json.EstimateParameters``), amounts are magnitudes at the currency's
minor unit, the constrained amount lies between the most conservative and the unconstrained amounts
(``ESTIMATE_CONSTRAINT_RANGE``, IMP-74; V6), expected-value probabilities sum to 1, and the
judgement record is visible. An ``EAC`` version below the costs incurred to date answers 422
``eac-below-costs-incurred`` (ERR-13). Submission computes the group in ``DRY_RUN`` with the version
applied, which is the request's impact preview (REQ-PLT-015); an engine error answers 422.

Approval (``_approve_version``) supersedes the element's APPROVED version, approves the version,
appends ``ESTIMATE_CHANGED {estimate_version_id, previous_estimate_version_id}`` as SYSTEM at the
version's effective date with the request id, records the event in ``applied_event_ids`` and
computes the group, failing closed (DG-CMD-09). Rejection gives REJECTED and a withdrawn or voided
request WITHDRAWN; a PATCH returns either to DRAFT (E-12). ``discard_version`` moves a DRAFT version
to VOIDED (item EST-DISCARD-1; 04 rev 1.210): it leaves the preparer's work, keeps its number, and
is no longer the element's latest version.

A version may be created inside a DRAFT modification of its contract (``modification_id``; item
MOD-LINKED-ESTIMATES-1, PRD BR-MOD-02): the link is written by the INSERT and never changed, the
version is approved before its modification is submitted (``modifications.submit``), and it is
not submitted once that modification is discarded (PRD ERR-88). ``constraint_checklist`` is the
five named factors of 606-10-32-12 or nothing (item EST-CONSTRAINT-KEYS-1).

``request_preview`` defers ``CONTRACT_COMPUTE`` in mode ``ESTIMATE_PREVIEW``, whose ``run_preview``
answers API-S-ImpactSummary in ``result.summary`` (SCREENS R-16). [J] L5-2-Q-6: ``balances_before``
and ``balances_after`` list contract liability and contract asset, and refund liability and return
asset where either side is not 0 (SCREENS §8.4), at the latest period of the stored and the dry-run
versions.

[J] L5-2-Q-3: T-CON-12 is IM-A, so an element's method cannot change once stored; a version whose
``method`` differs from it is refused whether or not a version is approved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.bundle import FxRateInput, InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, minor_to_decimal
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates
from pydantic import ValidationError
from sqlalchemy import ColumnElement, Select, and_, func, insert, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    ESTIMATE_PL_IMPACT_FLAG,
    THRESHOLD_CURRENCY,
    SubjectLifecycle,
    estimate_version_content,
    register_lifecycle,
)
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import system_principal
from erev_api.db import new_id, transitions
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_decision,
    contract,
    contract_event,
    contract_version_balance,
    estimate,
    estimate_version,
    file_attachment,
    job,
    judgement_record,
    legal_entity,
    modification,
    obligation,
)
from erev_api.domain.contracts import bundles, computation, queries, repo
from erev_api.domain.contracts.activation import engine_problem
from erev_api.domain.contracts.compute_job import ESTIMATE_PREVIEW_MODE
from erev_api.domain.contracts.events import impact_summary
from erev_api.domain.platform import approval_queries
from erev_api.domain.platform.jobs import JOB_COLUMNS, job_outs
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalSubjectType,
    ComputationTrigger,
    ConfigStatus,
    ContractEventType,
    EstimateKind,
    JobKind,
    JudgementStatus,
    JudgementTopic,
    ModificationStatus,
)
from erev_api.events.payloads import EstimateChangedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import lock_readable
from erev_api.jobs.registry import JobOutcome
from erev_api.money import money_out
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import ActorOut, JobOut
from erev_api.schemas.db_json import EstimateParameters
from erev_api.schemas.estimates import (
    EstimateCreateIn,
    EstimateOut,
    EstimateVersionCreateIn,
    EstimateVersionOut,
    EstimateVersionSubmitIn,
    EstimateVersionSummaryOut,
    EstimateVersionUpdateIn,
    EstimateVersionWithdrawIn,
)
from erev_api.schemas.events import ImpactBalanceOut, ImpactSummaryOut
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext

__all__ = [
    "CREATE_PERMISSION",
    "costs_incurred_to_date",
    "create_estimate",
    "create_version",
    "discard_version",
    "estimate_outs",
    "estimates_statement",
    "get_estimate",
    "get_version",
    "request_preview",
    "run_preview",
    "submit_version",
    "update_version",
    "version_outs",
    "versions_statement",
    "visible_estimate",
    "withdraw_version",
]

CREATE_PERMISSION: Final = "estimate.create"  # PRD ACT-11; 04 API-R-32
ESTIMATE_OBJECT: Final = "estimate"
VERSION_OBJECT: Final = "estimate_version"
# The audit action of a refused preview (04 §16.10 rev 1.295): a preview that is taken writes
# ``job.start``, nothing of its own.
PREVIEW_ACTION: Final = "estimate_version.preview"
RULE_ESTIMATE: Final = "T-CON-12"
RULE_VERSION: Final = "T-CON-13"
RULE_OBLIGATION: Final = "T-CON-10"
RULE_MONEY: Final = "API-C-06"
RULE_EAC: Final = "ERR-13"
METHOD_LOCKED: Final = "ESTIMATE_METHOD_LOCKED"
CONSTRAINT_RANGE: Final = "ESTIMATE_CONSTRAINT_RANGE"
DRY_RUN: Final = "DRY_RUN"
VERSION_HREF: Final = "/api/v1/estimate-versions/{version_id}"
DRAFT: Final = ConfigStatus.DRAFT.value
SUBMITTED: Final = ConfigStatus.SUBMITTED.value
APPROVED: Final = ConfigStatus.APPROVED.value
SUPERSEDED: Final = ConfigStatus.SUPERSEDED.value
REJECTED: Final = ConfigStatus.REJECTED.value
WITHDRAWN: Final = ConfigStatus.WITHDRAWN.value
VOIDED: Final = ConfigStatus.VOIDED.value
PENDING: Final = "PENDING"
EDITABLE: Final = frozenset({DRAFT, REJECTED, WITHDRAWN})
PREVIEWABLE: Final = frozenset({DRAFT, SUBMITTED, REJECTED, WITHDRAWN})
INCREASE: Final = "INCREASE"
DECREASE: Final = "DECREASE"
OBLIGATIONS_TARGET: Final = "OBLIGATIONS"
CONTRACT_TARGET: Final = "CONTRACT"
PROGRESS_INPUT: Final = "PROGRESS_INPUT"
REDUCING_KINDS: Final = frozenset(
    {EstimateKind.VARIABLE_CONSIDERATION, EstimateKind.IMPLICIT_PRICE_CONCESSION}
)
# dev-guide §9.5.4 B3-DG-17 (topics convention T-03): element types that reduce the price.
DECREASE_TYPES: Final = frozenset(
    {
        "IMPLICIT_PRICE_CONCESSION",
        "REBATE",
        "VOLUME_TIER",
        "PRICE_PROTECTION",
        "SLA_CREDIT",
        "DISCOUNT",
        "RETURN",
        "REFUND",
        "PENALTY",
    }
)
AMOUNT_COLUMNS: Final = (
    "unconstrained_amount",
    "most_conservative_amount",
    "constrained_amount",
    "expected_total_amount",
)
EXACT_COLUMNS: Final = ("rate", "expected_quantity")
VERSION_MEMBERS: Final = (
    "effective_date",
    "scenarios",
    "parameters",
    *AMOUNT_COLUMNS,
    *EXACT_COLUMNS,
    "amortization_months",
    "currency",
    "constraint_checklist",
    "rationale",
    "judgement_record_id",
)
# SCREENS §8.4 method labels (E-10).
METHOD_LABELS: Final = {
    "EXPECTED_VALUE": "Expected value",
    "MOST_LIKELY_AMOUNT": "Most likely amount",
    "ENTERED_AMOUNT": "Entered amount",
    "RATE": "Rate",
    "COST_BUILDUP": "Cost build-up",
}
BALANCE_ALWAYS: Final = ("contract_liability", "contract_asset")
BALANCE_WHEN_SET: Final = ("refund_liability", "return_asset")
# [J] Copy the documents leave open; IMP-71, IMP-74 and ERR-13 are the PRD's.
VC_TYPE_REQUIRED: Final = "Choose the element type of the variable consideration."
DIRECTION_CONCESSION: Final = "An implicit price concession reduces the transaction price."
DIRECTION_KIND: Final = "Only variable consideration and price concessions reduce the price."
OBLIGATION_UNKNOWN: Final = "Choose an obligation of the contract."
TARGETS_REQUIRED: Final = "Name the obligations the element is allocated to."
TARGETS_NOT_ALLOWED: Final = "Target obligations apply only to the OBLIGATIONS allocation target."
EVIDENCE_REQUIRED: Final = "Add the evidence that the criteria of ASC 606-10-32-40 are met."
CODE_TAKEN: Final = "The contract already has an estimated element with this code."
METHOD_LOCKED_MESSAGE: Final = (
    "The estimation method is fixed after the first version (POL-040). Use {method}."
)
RANGE_MESSAGE: Final = (
    "The constrained estimate ({amount}) is outside the allowed range {low} – {high}."
)
MAGNITUDE: Final = "Enter amounts as magnitudes of 0 or more."
PROBABILITY_REQUIRED: Final = "Give each outcome of an expected value a probability."
PROBABILITIES: Final = "The probabilities of the outcomes must sum to 1."
JUDGEMENT_UNKNOWN: Final = "Choose a judgement record."
DECIMALS: Final = "{currency} amounts have at most {places} decimal places."
CURRENCY_UNKNOWN: Final = "{currency} is not an ISO 4217 currency code."
EAC_MESSAGE: Final = (
    "Estimated total costs ({eac}) cannot be lower than costs incurred to date ({costs})."
)
NOT_EDITABLE: Final = "Only a draft, rejected or withdrawn estimate version can be edited."
NOT_SUBMITTABLE: Final = "Only a draft estimate version can be submitted."
# PRD §2.5 ``ESTIMATE_VERSION``: "If absolute P&L impact ≥ USD 50,000.00: 2: Controller".
PL_IMPACT_THRESHOLD: Final = Decimal("50000.00")
NOT_WITHDRAWABLE: Final = (
    "Only a submitted estimate version with a pending request can be withdrawn."
)
NOT_PREVIEWABLE: Final = "An approved or superseded estimate version has no preview."
NOT_DISCARDABLE: Final = "Only a draft estimate version can be discarded."
# Item MOD-LINKED-ESTIMATES-1 (04 T-CON-13 ``modification_id``, §16.14 rev 1.210; PRD BR-MOD-02).
RULE_LIFECYCLE: Final = "SM-04"
MODIFICATION_NOT_DRAFT: Final = "Choose a draft modification of this contract."
# PRD ERR-88: a convention row of ``invalid-transition`` under the rule id of SM-04.
MODIFICATION_DISCARDED: Final = (
    "Modification {modification_no} of this estimate version was discarded. The version cannot "
    "be submitted."
)
PORTFOLIO_PENDING: Final = "portfolio-scoped estimate versions are built by CTR-13"
# Item EST-ONE-OPEN-VERSION-1 (04 T-CON-13, §16.14 rev 1.241; PRD SM-04, ERR-93): at most one
# version of an element is DRAFT or SUBMITTED. A convention row of ``invalid-transition`` under
# the rule id of SM-04; ``ux_estimate_version__open`` holds the same below the commands.
OPEN_STATUSES: Final = (DRAFT, SUBMITTED)
VERSION_OPEN: Final = (
    "Estimate version {element_code} v{version_no} is open. One version of an element is "
    "prepared at a time: approve or discard it first."
)
# Item EST-EVIDENCE-AT-SUBMIT-1 (04 §16.14 rev 1.241, table 15.4-D; PRD IMP-138, IMP-139,
# IMP-141; 03 REQ-TP-004): the estimate kinds whose version is submitted with its evidence.
EVIDENCE_KINDS: Final = frozenset(
    {
        EstimateKind.VARIABLE_CONSIDERATION.value,
        EstimateKind.EAC.value,
        EstimateKind.RETURN_RATE.value,
    }
)
ATTACHMENT_SUBJECT: Final = "estimate_version"
EVIDENCE_MISSING: Final = "ESTIMATE_EVIDENCE_REQUIRED"
EVIDENCE_MISSING_MESSAGE: Final = (
    "Attach the evidence of this estimate version before it is submitted."
)
# The same finding where the approval meets it (409 ``invalid-transition`` under SM-04): the
# uploader may void the attachment of a SUBMITTED version — DB-11 protects an APPROVED subject.
EVIDENCE_WITHDRAWN: Final = (
    "The evidence of this estimate version is no longer attached. Attach it before the version "
    "is approved."
)
ATTESTATION_REASON: Final = "ESTIMATE_ATTESTATION_REASON"
ATTESTATION_REASON_LENGTH: Final = 10
ATTESTATION_REASON_MESSAGE: Final = (
    "The values equal the approved version: this is an attestation of no change. State its "
    "reason in at least 10 characters."
)
ATTESTATION_VALUES: Final = "ESTIMATE_ATTESTATION_VALUES"
ATTESTATION_VALUES_MESSAGE: Final = (
    "The values differ from the approved version: this is not an attestation of no change."
)
ATTESTATION_FLAG: Final = "no_change_attestation"
# The constraint's judgement record (04 §16.14 rev 1.241; PRD IMP-140, ERR-94; 03 REQ-POL-008,
# CTL-049): the constrained amount of a variable-consideration version IS the constraint
# conclusion, so the version names its record at the submission and is approved on a reviewed
# one.
CONSTRAINT_RECORD: Final = "ESTIMATE_CONSTRAINT_RECORD"
CONSTRAINT_RECORD_MESSAGE: Final = (
    "Name the CONSTRAINT judgement record of this element: a record of this contract for "
    "{element_code}, sent for review or reviewed."
)
RECORD_NOT_REVIEWED: Final = (
    "Judgement record {judgement_no} of this estimate version is not reviewed. It is reviewed "
    "before the version is approved."
)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _error(field: str, rule_id: str, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _failed(errors: Sequence[ProblemError]) -> Problem:
    detail = errors[0].message if len(errors) == 1 else f"{len(errors)} fields need attention."
    return Problem("validation-failed", detail, errors=errors)


def _invalid(message: str) -> Problem:
    return Problem(
        "invalid-transition", message, errors=[_error("status", transitions.RULE_ID, message)]
    )


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _minor(currency: str) -> int:
    return ISO_4217[currency].minor_unit


def _quantized(value: Decimal, currency: str) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-_minor(currency)))


def _money(value: Decimal, currency: str) -> Any:
    return money_out(_quantized(value, currency), currency, ISO_4217)


def _shown(value: Decimal, currency: str) -> str:
    """An amount as the PRD copy writes it, for example ``5,750.00``."""
    return format(_quantized(value, currency), f",.{_minor(currency)}f")


def _plain_decimal(value: Any) -> str | None:
    if value is None:
        return None
    normalized = Decimal(str(value)).normalize()
    return format(normalized, "f")


def _audit_values(values: Mapping[str, Any]) -> dict[str, Any]:
    shown: dict[str, Any] = {}
    for name, value in values.items():
        if isinstance(value, Decimal):
            shown[name] = _plain_decimal(value)
        elif isinstance(value, date | UUID):
            shown[name] = str(value)
        else:
            shown[name] = value
    return shown


# --- rows and visibility -------------------------------------------------------------------------


def _estimate_row(session: Session, estimate_id: UUID) -> dict[str, Any]:
    found = session.execute(select(estimate).where(estimate.c.id == estimate_id)).mappings()
    row = found.one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _visible_contract(
    session: Session, element: Mapping[str, Any], *, for_update: bool = False
) -> dict[str, Any]:
    """The element's contract; 404 when it is not visible. [J] Portfolio elements wait for
    CTR-13."""
    if element["contract_id"] is None:
        raise Problem("not-found")
    if for_update:  # DG-KRN-DB-08 rev 1.36: the group row first, then the contract row
        return repo.lock_group_then_contract(session, _uuid(element["contract_id"]))[1]
    return repo.get_contract(session, _uuid(element["contract_id"]))


def visible_estimate(session: Session, estimate_id: UUID) -> dict[str, Any]:
    """The T-CON-12 row of a visible contract; 404 ``not-found`` otherwise."""
    element = _estimate_row(session, estimate_id)
    _visible_contract(session, element)
    return element


def _version_row(session: Session, version_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    statement = select(estimate_version).where(estimate_version.c.id == version_id)
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _require_prepare(uow: UnitOfWork, current: Mapping[str, Any]) -> None:
    require_for_entity(uow.ctx, CREATE_PERMISSION, _uuid(current["contracting_entity_id"]))


def _obligation_ids(session: Session, contract_id: UUID, keys: Sequence[str]) -> dict[str, UUID]:
    if not keys:
        return {}
    statement = select(obligation.c.obligation_key, obligation.c.id).where(
        obligation.c.contract_id == contract_id, obligation.c.obligation_key.in_(sorted(set(keys)))
    )
    return {str(key): _uuid(value) for key, value in session.execute(statement)}


def _approved_versions(
    session: Session, estimate_id: UUID, *, lock: bool = False
) -> list[dict[str, Any]]:
    statement = (
        select(estimate_version.c.id, estimate_version.c.version_no)
        .where(estimate_version.c.estimate_id == estimate_id, estimate_version.c.status == APPROVED)
        .order_by(estimate_version.c.version_no.desc())
    )
    if lock:
        statement = statement.with_for_update()
    return [dict(row) for row in session.execute(statement).mappings()]


def _latest_approved(session: Session, estimate_id: UUID) -> UUID | None:
    found = _approved_versions(session, estimate_id)
    return None if not found else _uuid(found[0]["id"])


def _status_audit(
    uow: UnitOfWork,
    version_id: UUID,
    before: str,
    after: str,
    *,
    contract_id: UUID | None,
    **extra: Any,
) -> None:
    """A status change of a version; ``contract_id`` is the element's contract (none for an
    element of a portfolio), the key the event carries (04 T-PLT-19)."""
    uow.audit(
        action=f"{VERSION_OBJECT}.{after.lower()}",
        object_type=VERSION_OBJECT,
        object_id=version_id,
        before={"status": before},
        after={"status": after, **extra},
        contract_id=contract_id,
    )


# --- elements ------------------------------------------------------------------------------------


def _default_direction(kind: EstimateKind, vc_element_type: str | None) -> str:
    if kind is EstimateKind.IMPLICIT_PRICE_CONCESSION:
        return DECREASE
    if kind is EstimateKind.VARIABLE_CONSIDERATION and vc_element_type in DECREASE_TYPES:
        return DECREASE
    return INCREASE


def create_estimate(uow: UnitOfWork, *, contract_id: UUID, body: EstimateCreateIn) -> EstimateOut:
    """``POST /contracts/{id}/estimates``: a T-CON-12 element (findings in the module docstring)."""
    session = uow.session
    current = repo.get_contract(session, contract_id)
    _require_prepare(uow, current)
    kind = EstimateKind(body.estimate_kind)
    errors: list[ProblemError] = []
    if kind is EstimateKind.VARIABLE_CONSIDERATION and body.vc_element_type is None:
        errors.append(_error("vc_element_type", RULE_ESTIMATE, VC_TYPE_REQUIRED))
    direction = body.direction or _default_direction(kind, body.vc_element_type)
    if kind is EstimateKind.IMPLICIT_PRICE_CONCESSION and direction != DECREASE:
        errors.append(_error("direction", RULE_ESTIMATE, DIRECTION_CONCESSION))
    if kind not in REDUCING_KINDS and direction != INCREASE:
        errors.append(_error("direction", RULE_ESTIMATE, DIRECTION_KIND))
    named = [*([] if body.obligation_key is None else [body.obligation_key])]
    found = _obligation_ids(session, contract_id, [*named, *body.target_obligation_keys])
    if body.obligation_key is not None and body.obligation_key not in found:
        errors.append(_error("obligation_key", RULE_OBLIGATION, OBLIGATION_UNKNOWN))
    for index, key in enumerate(body.target_obligation_keys):
        if key not in found:
            errors.append(
                _error(f"target_obligation_keys.{index}", RULE_OBLIGATION, OBLIGATION_UNKNOWN)
            )
    if body.allocation_target == OBLIGATIONS_TARGET and not body.target_obligation_keys:
        errors.append(_error("target_obligation_keys", RULE_ESTIMATE, TARGETS_REQUIRED))
    if body.allocation_target != OBLIGATIONS_TARGET and body.target_obligation_keys:
        errors.append(_error("target_obligation_keys", RULE_ESTIMATE, TARGETS_NOT_ALLOWED))
    if body.allocation_target != CONTRACT_TARGET and body.allocation_criteria_evidence is None:
        errors.append(_error("allocation_criteria_evidence", RULE_ESTIMATE, EVIDENCE_REQUIRED))
    taken = session.execute(
        select(estimate.c.id).where(
            estimate.c.contract_id == contract_id, estimate.c.element_code == body.element_code
        )
    ).first()
    if taken is not None:
        errors.append(_error("element_code", RULE_ESTIMATE, CODE_TAKEN))
    if errors:
        raise _failed(errors)
    principal = uow.principal
    estimate_id = new_id()
    values: dict[str, Any] = {
        "contract_id": contract_id,
        "obligation_id": None if body.obligation_key is None else found[body.obligation_key],
        "estimate_kind": kind.value,
        "element_code": body.element_code,
        "vc_element_type": body.vc_element_type,
        "direction": direction,
        "method": _text(body.method),
        "allocation_target": body.allocation_target,
        "target_obligation_ids": [found[key] for key in body.target_obligation_keys],
        "allocation_criteria_evidence": body.allocation_criteria_evidence,
    }
    session.execute(
        insert(estimate).values(
            tenant_id=principal.tenant_id,
            id=estimate_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **values,
        )
    )
    uow.audit(
        action=f"{ESTIMATE_OBJECT}.create",
        object_type=ESTIMATE_OBJECT,
        object_id=estimate_id,
        object_version="1",
        after={
            **_audit_values(values),
            "target_obligation_ids": [str(value) for value in values["target_obligation_ids"]],
        },
        contract_id=contract_id,
    )
    return get_estimate(session, estimate_id)


# --- version validation --------------------------------------------------------------------------


def _values_of(
    body: EstimateVersionCreateIn | EstimateVersionUpdateIn, names: Sequence[str]
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in names:
        value = getattr(body, name)
        if name == "scenarios":
            value = [item.model_dump(mode="json", exclude_none=True) for item in value or ()]
        elif name == "parameters":
            value = dict(value or {})
        elif name == "constraint_checklist":
            # the typed body (the five keys of T-CON-13) as the stored object
            value = None if value is None else value.model_dump()
        elif name in AMOUNT_COLUMNS or name in EXACT_COLUMNS:
            value = None if value is None else Decimal(value)
        values[name] = value
    return values


def _stored_values(row: Mapping[str, Any]) -> dict[str, Any]:
    values = {name: row[name] for name in VERSION_MEMBERS}
    for name in (*AMOUNT_COLUMNS, *EXACT_COLUMNS):
        if values[name] is not None:
            values[name] = Decimal(str(values[name]))
    if values["currency"] is not None:
        values["currency"] = str(values["currency"]).strip()
    values["scenarios"] = list(values["scenarios"] or ())
    values["parameters"] = dict(values["parameters"] or {})
    return values


def _decimals(value: Decimal) -> int:
    """The significant decimal places; stored ``erev.money`` values carry four trailing zeros."""
    exponent = value.normalize().as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _parameter_errors(
    kind: EstimateKind, value: Mapping[str, Any]
) -> tuple[dict[str, Any], list[ProblemError]]:
    try:
        return EstimateParameters.validate(kind, value), []
    except ValidationError as error:
        found = []
        for item in error.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            field = "parameters" + (f".{location}" if location else "")
            found.append(_error(field, RULE_VERSION, str(item.get("msg", ""))))
        return dict(value), found


def _version_errors(
    session: Session,
    element: Mapping[str, Any],
    current: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    method: Any,
) -> tuple[dict[str, Any], list[ProblemError]]:
    """The normalised version values and every finding of the module docstring."""
    kind = EstimateKind(_text(element["estimate_kind"]))
    element_method = _text(element["method"])
    errors: list[ProblemError] = []
    if method is not None and _text(method) != element_method:
        message = METHOD_LOCKED_MESSAGE.format(method=METHOD_LABELS[element_method])
        errors.append(_error("method", METHOD_LOCKED, message))
    normalized = dict(values)
    normalized["parameters"], found = _parameter_errors(kind, values["parameters"])
    errors.extend(found)
    currency = str(values["currency"] or current["transaction_currency"]).strip()
    normalized["currency"] = currency
    known = currency in ISO_4217
    if not known:
        errors.append(_error("currency", RULE_MONEY, CURRENCY_UNKNOWN.format(currency=currency)))
    for name in AMOUNT_COLUMNS:
        value = values[name]
        if value is None:
            continue
        if value < 0:
            errors.append(_error(name, RULE_VERSION, MAGNITUDE))
        elif known and _decimals(value) > _minor(currency):
            message = DECIMALS.format(currency=currency, places=_minor(currency))
            errors.append(_error(name, RULE_MONEY, message))
    for name in EXACT_COLUMNS:
        value = values[name]
        if value is not None and value < 0:
            errors.append(_error(name, RULE_VERSION, MAGNITUDE))
    constrained = values["constrained_amount"]
    unconstrained = values["unconstrained_amount"]
    conservative = values["most_conservative_amount"]
    if constrained is not None and unconstrained is not None and conservative is not None:
        low, high = min(conservative, unconstrained), max(conservative, unconstrained)
        if not low <= constrained <= high and known:
            message = RANGE_MESSAGE.format(
                amount=_shown(constrained, currency),
                low=_shown(low, currency),
                high=_shown(high, currency),
            )
            errors.append(_error("constrained_amount", CONSTRAINT_RANGE, message))
    scenarios = list(values["scenarios"] or ())
    for index, scenario in enumerate(scenarios):
        if Decimal(str(scenario.get("amount", "0"))) < 0:
            errors.append(_error(f"scenarios.{index}.amount", RULE_VERSION, MAGNITUDE))
    if element_method == "EXPECTED_VALUE" and scenarios:
        probabilities = [scenario.get("probability") for scenario in scenarios]
        if any(value is None for value in probabilities):
            errors.append(_error("scenarios", RULE_VERSION, PROBABILITY_REQUIRED))
        elif sum((Decimal(str(value)) for value in probabilities), Decimal(0)) != 1:
            errors.append(_error("scenarios", RULE_VERSION, PROBABILITIES))
    record = values["judgement_record_id"]
    if record is not None and (
        session.execute(
            select(judgement_record.c.id).where(judgement_record.c.id == record)
        ).first()
        is None
    ):
        errors.append(_error("judgement_record_id", RULE_VERSION, JUDGEMENT_UNKNOWN))
    return normalized, errors


def costs_incurred_to_date(session: Session, element: Mapping[str, Any], through: date) -> Decimal:
    """``COST_INCURRED`` progress inputs of the element's contract through ``through``, not voided,
    and of the element's obligation when it names one (04 §16.14 estimates; ERR-13)."""
    if element["contract_id"] is None:
        return Decimal(0)
    contract_id = _uuid(element["contract_id"])
    voided = select(contract_event.c.supersedes_event_id).where(
        contract_event.c.contract_id == contract_id,
        contract_event.c.event_type == ContractEventType.EVENT_VOIDED.value,
        contract_event.c.supersedes_event_id.is_not(None),
    )
    key: str | None = None
    if element["obligation_id"] is not None:
        key = session.execute(
            select(obligation.c.obligation_key).where(obligation.c.id == element["obligation_id"])
        ).scalar_one_or_none()
    total = Decimal(0)
    for (payload,) in session.execute(
        select(contract_event.c.payload).where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == ContractEventType.COST_INCURRED.value,
            contract_event.c.effective_date <= through,
            ~contract_event.c.id.in_(voided),
        )
    ):
        if not isinstance(payload, Mapping) or payload.get("purpose") != PROGRESS_INPUT:
            continue
        if key is not None and payload.get("obligation_key") != key:
            continue
        amount = payload.get("amount")
        value = amount.get("amount") if isinstance(amount, Mapping) else amount
        if value is not None:
            total += Decimal(str(value))
    return total


def _eac_check(session: Session, element: Mapping[str, Any], values: Mapping[str, Any]) -> None:
    """ERR-13: an ``EAC`` version below the costs incurred to date."""
    total = values["expected_total_amount"]
    if _text(element["estimate_kind"]) != EstimateKind.EAC.value or total is None:
        return
    costs = costs_incurred_to_date(session, element, values["effective_date"])
    if total >= costs:
        return
    currency = str(values["currency"])
    message = EAC_MESSAGE.format(eac=_shown(total, currency), costs=_shown(costs, currency))
    raise Problem(
        "eac-below-costs-incurred",
        message,
        errors=[_error("expected_total_amount", RULE_EAC, message)],
    )


# --- what a submission and an approval ask of a version -------------------------------------------


def _refuse_open(
    session: Session, element: Mapping[str, Any], *, besides: UUID | None = None
) -> None:
    """Item EST-ONE-OPEN-VERSION-1 (PRD ERR-93): refuse while another version of the element is
    DRAFT or SUBMITTED — one version of an element is prepared at a time, so that no two requests
    of one element wait together and none is prepared on a predecessor that is about to change.
    REJECTED and WITHDRAWN are not open: such a version is revised, or stays as history beside
    a new one. The caller holds the contract's group and row locks, so two cannot interleave."""
    statement = select(estimate_version.c.version_no).where(
        estimate_version.c.estimate_id == element["id"],
        estimate_version.c.status.in_(OPEN_STATUSES),
    )
    if besides is not None:
        statement = statement.where(estimate_version.c.id != besides)
    number = session.execute(statement.order_by(estimate_version.c.version_no).limit(1)).scalar()
    if number is None:
        return
    message = VERSION_OPEN.format(element_code=element["element_code"], version_no=int(number))
    raise Problem(
        "invalid-transition", errors=[ProblemError(rule_id=RULE_LIFECYCLE, message=message)]
    )


def _has_evidence(session: Session, version_id: UUID) -> bool:
    """The version has a live attachment whose file can still be read: the document the rule
    asks for (04 T-PLT-29 "A document a rule asks for"; rulings R-119 (g), R-120 (g)). An
    attachment row outlives the shred of its file and is no evidence then. The files' rows are
    locked to the end of the transaction, so that this command and a shred of one of them see
    each other (``files.store.lock_readable``)."""
    file_ids = [
        _uuid(file_id)
        for file_id in session.scalars(
            select(file_attachment.c.file_object_id).where(
                file_attachment.c.subject_type == ATTACHMENT_SUBJECT,
                file_attachment.c.subject_id == version_id,
                file_attachment.c.voided_at.is_(None),
            )
        )
    ]
    return bool(lock_readable(session, file_ids))


def _exact(value: Any) -> Any:
    """A stored or sent number as a Decimal, so that ``5000`` equals ``5000.0000``."""
    if value is None or isinstance(value, bool):
        return value
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return value


def _figures(values: Mapping[str, Any]) -> tuple[Any, ...]:
    """What an attestation of no change repeats (04 §16.14 rev 1.241): the scenarios, the
    amounts, rate, quantity, amortisation months and currency, the parameters other than the
    caller's own flag, and the constraint checklist BY ITS MARKED FACTORS — a version stored
    before the five keys were named holds whatever object it stored, and the five booleans a
    screen repeats equal it when they mark the same factors. The effective date, the rationale
    and the judgement record are not values."""
    scenarios = sorted(
        (str(item.get("outcome", "")), _exact(item.get("amount")), _exact(item.get("probability")))
        for item in values["scenarios"] or ()
        if isinstance(item, Mapping)
    )
    parameters = sorted(
        (name, _exact(value))
        for name, value in (values["parameters"] or {}).items()
        if name != ATTESTATION_FLAG
    )
    checklist = values["constraint_checklist"]
    marked = (
        sorted(name for name, value in (checklist or {}).items() if value is True)
        if isinstance(checklist, Mapping)
        else []
    )
    return (
        scenarios,
        *(_exact(values[name]) for name in (*AMOUNT_COLUMNS, *EXACT_COLUMNS)),
        values["amortization_months"],
        None if values["currency"] is None else str(values["currency"]).strip(),
        parameters,
        marked,
    )


def _attests_no_change(
    session: Session, element: Mapping[str, Any], row: Mapping[str, Any]
) -> bool:
    """A variable-consideration version whose values equal those of the element's approved
    version: an attestation of no change (REQ-TP-005 reassessment at each reporting date). It is
    told by its VALUES, not by the flag the caller sends. Only this kind attests: an EAC or a
    return rate with unchanged figures owes its file."""
    if _text(element["estimate_kind"]) != EstimateKind.VARIABLE_CONSIDERATION.value:
        return False
    previous = _latest_approved(session, _uuid(element["id"]))
    if previous is None or previous == row["id"]:
        return False
    return _figures(_stored_values(_version_row(session, previous))) == _figures(
        _stored_values(row)
    )


def _constraint_record(
    session: Session,
    element: Mapping[str, Any],
    current: Mapping[str, Any],
    row: Mapping[str, Any],
) -> Any:
    """The judgement record the version names when it is the CONSTRAINT record of its element —
    topic CONSTRAINT, of the version's contract, its ``estimate_key`` naming the element by its
    code or by one of the engine's two keys (``erev_engine`` reads the same three: the estimate
    key and the version key) — else None. The record's subject is not asked: the version, its
    modification, the contract or an obligation, all of the version's contract."""
    if row["judgement_record_id"] is None:
        return None
    found = session.execute(
        select(
            judgement_record.c.judgement_no,
            judgement_record.c.topic,
            judgement_record.c.status,
            judgement_record.c.contract_id,
            judgement_record.c.questionnaire,
        ).where(judgement_record.c.id == row["judgement_record_id"])
    ).one_or_none()
    if found is None or _text(found.topic) != JudgementTopic.CONSTRAINT.value:
        return None
    if found.contract_id is None or _uuid(found.contract_id) != _uuid(current["id"]):
        return None
    named = (found.questionnaire or {}).get("estimate_key")
    estimate_key = obligation_subject_key(str(current["external_id"]), str(element["element_code"]))
    keys = (str(element["element_code"]), estimate_key, f"{estimate_key}@v{int(row['version_no'])}")
    return found if named in keys else None


def _submission_errors(
    session: Session,
    element: Mapping[str, Any],
    current: Mapping[str, Any],
    row: Mapping[str, Any],
) -> list[ProblemError]:
    """What a version owes when it is sent for approval, beyond its own values (04 §16.14 rev
    1.241; items EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement record):

    - a VARIABLE_CONSIDERATION, EAC or RETURN_RATE version has its evidence attached
      (``ESTIMATE_EVIDENCE_REQUIRED``) — unless it is an attestation of no change, which owes a
      reason of at least ten characters instead (``ESTIMATE_ATTESTATION_REASON``);
    - a version that sends ``no_change_attestation`` true with values that differ from the
      approved version is refused on the flag (``ESTIMATE_ATTESTATION_VALUES``): the estimate
      change listing prints the flag;
    - a VARIABLE_CONSIDERATION version names the CONSTRAINT record of its element, SUBMITTED or
      REVIEWED (``ESTIMATE_CONSTRAINT_RECORD``). An attestation names none of its own — the
      reviewed record of the version it attests stands; if it names one, the same is asked."""
    kind = _text(element["estimate_kind"])
    errors: list[ProblemError] = []
    attests = _attests_no_change(session, element, row)
    if bool((row["parameters"] or {}).get(ATTESTATION_FLAG, False)) and not attests:
        errors.append(
            _error(f"parameters.{ATTESTATION_FLAG}", ATTESTATION_VALUES, ATTESTATION_VALUES_MESSAGE)
        )
    if attests:
        if len(str(row["rationale"]).strip()) < ATTESTATION_REASON_LENGTH:
            errors.append(_error("rationale", ATTESTATION_REASON, ATTESTATION_REASON_MESSAGE))
    elif kind in EVIDENCE_KINDS and not _has_evidence(session, _uuid(row["id"])):
        errors.append(
            ProblemError(field=None, rule_id=EVIDENCE_MISSING, message=EVIDENCE_MISSING_MESSAGE)
        )
    if kind == EstimateKind.VARIABLE_CONSIDERATION.value and not (
        attests and row["judgement_record_id"] is None
    ):
        record = _constraint_record(session, element, current, row)
        if record is None or _text(record.status) not in (
            JudgementStatus.SUBMITTED.value,
            JudgementStatus.REVIEWED.value,
        ):
            message = CONSTRAINT_RECORD_MESSAGE.format(element_code=element["element_code"])
            errors.append(_error("judgement_record_id", CONSTRAINT_RECORD, message))
    return errors


def _approval_refusal(
    session: Session,
    element: Mapping[str, Any],
    current: Mapping[str, Any],
    row: Mapping[str, Any],
) -> str | None:
    """Why a SUBMITTED version is not approved yet, or None: its CONSTRAINT record is not
    REVIEWED (PRD ERR-94) — the approval posts the catch-up, and a review that then rejected the
    record would leave posted revenue on a refused judgement — or its evidence is no longer
    attached. Both were asked at the submission; the record's review and the attachment's void
    happen after it."""
    kind = _text(element["estimate_kind"])
    attests = _attests_no_change(session, element, row)
    if kind == EstimateKind.VARIABLE_CONSIDERATION.value and not (
        attests and row["judgement_record_id"] is None
    ):
        record = _constraint_record(session, element, current, row)
        if record is None:  # the record was revised into another one since the submission
            return CONSTRAINT_RECORD_MESSAGE.format(element_code=element["element_code"])
        if _text(record.status) != JudgementStatus.REVIEWED.value:
            return RECORD_NOT_REVIEWED.format(judgement_no=record.judgement_no)
    if kind in EVIDENCE_KINDS and not attests and not _has_evidence(session, _uuid(row["id"])):
        return EVIDENCE_WITHDRAWN
    return None


# --- versions ------------------------------------------------------------------------------------


def create_version(
    uow: UnitOfWork, *, estimate_id: UUID, body: EstimateVersionCreateIn
) -> EstimateVersionOut:
    """``POST /estimates/{id}/versions``: a validated DRAFT version numbered after the element's
    latest; ``supersedes_version_id`` names the APPROVED version."""
    session = uow.session
    element = _estimate_row(session, estimate_id)
    current = _visible_contract(session, element, for_update=True)
    _require_prepare(uow, current)
    values, errors = _version_errors(
        session, element, current, _values_of(body, VERSION_MEMBERS), method=body.method
    )
    if body.modification_id is not None:
        # The contract's group and row are locked (``for_update``), as they are by the
        # modification's submission and discard: the link is made while its modification is a
        # draft, or not at all.
        change = session.execute(
            select(modification.c.contract_id, modification.c.status).where(
                modification.c.id == body.modification_id
            )
        ).one_or_none()
        if (
            change is None
            or _uuid(change.contract_id) != _uuid(current["id"])
            or _text(change.status) != ModificationStatus.DRAFT.value
        ):
            errors.append(_error("modification_id", RULE_VERSION, MODIFICATION_NOT_DRAFT))
    if errors:
        raise _failed(errors)
    _eac_check(session, element, values)
    _refuse_open(session, element)  # PRD ERR-93, under the locks taken above
    number = session.execute(
        select(func.coalesce(func.max(estimate_version.c.version_no), 0)).where(
            estimate_version.c.estimate_id == estimate_id
        )
    ).scalar_one()
    principal = uow.principal
    version_id = new_id()
    session.execute(
        insert(estimate_version).values(
            tenant_id=principal.tenant_id,
            id=version_id,
            estimate_id=estimate_id,
            version_no=int(number) + 1,
            status=DRAFT,
            supersedes_version_id=_latest_approved(session, estimate_id),
            modification_id=body.modification_id,  # written here and never again (T-CON-13)
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **values,
            **_stamps(uow),
        )
    )
    uow.audit(
        action=f"{VERSION_OBJECT}.create",
        object_type=VERSION_OBJECT,
        object_id=version_id,
        object_version="1",
        after={
            "estimate_id": str(estimate_id),
            "version_no": int(number) + 1,
            "status": DRAFT,
            **_audit_values(values),
            **(
                {}
                if body.modification_id is None
                else {"modification_id": str(body.modification_id)}
            ),
        },
        comment=body.rationale,
        contract_id=element["contract_id"],
    )
    return get_version(session, version_id)


def update_version(
    uow: UnitOfWork, *, version_id: UUID, body: EstimateVersionUpdateIn
) -> EstimateVersionOut:
    """``PATCH /estimate-versions/{id}``: edit a DRAFT version; a REJECTED or WITHDRAWN version
    returns to DRAFT first; any other status answers 409 ``invalid-transition`` (DB-03). A
    version that returns to DRAFT becomes open again, so it is refused while another version of
    its element is open (PRD ERR-93; item EST-ONE-OPEN-VERSION-1) — under the contract's group
    and row locks, which this command takes for that return."""
    session = uow.session
    row = _version_row(session, version_id, lock=True)
    element = _estimate_row(session, _uuid(row["estimate_id"]))
    status = _text(row["status"])
    current = _visible_contract(session, element, for_update=status != DRAFT)
    _require_prepare(uow, current)
    if status not in EDITABLE:
        raise _invalid(NOT_EDITABLE)
    names = sorted(set(body.model_fields_set) - {"method"})
    changes = _values_of(body, names)
    merged = {**_stored_values(row), **changes}
    values, errors = _version_errors(session, element, current, merged, method=body.method)
    if errors:
        raise _failed(errors)
    _eac_check(session, element, values)
    if status != DRAFT:
        _refuse_open(session, element, besides=version_id)
        transitions.apply(
            session,
            VERSION_OBJECT,
            version_id,
            to_status=DRAFT,
            expected_status=status,
            set_values=_stamps(uow),
        )
        _status_audit(uow, version_id, status, DRAFT, contract_id=element["contract_id"])
    updated = {name: values[name] for name in names}
    transitions.apply(
        session,
        VERSION_OBJECT,
        version_id,
        to_status=None,
        expected_status=DRAFT,
        set_values={
            **updated,
            "currency": values["currency"],
            "supersedes_version_id": _latest_approved(session, _uuid(row["estimate_id"])),
            **_stamps(uow),
        },
    )
    if updated:
        uow.audit(
            action=f"{VERSION_OBJECT}.update",
            object_type=VERSION_OBJECT,
            object_id=version_id,
            after=_audit_values(updated),
            contract_id=element["contract_id"],
        )
    return get_version(session, version_id)


def _changed_event(
    row: Mapping[str, Any], previous_id: UUID | None, approval_request_id: UUID | None
) -> EventIn:
    version_id = _uuid(row["id"])
    return EventIn(
        event_type=ContractEventType.ESTIMATE_CHANGED,
        effective_date=row["effective_date"],
        payload=EstimateChangedV1(
            estimate_version_id=version_id, previous_estimate_version_id=previous_id
        ),
        estimate_version_id=version_id,
        approval_request_id=approval_request_id,
    )


def _to_amount(value: object, minor: int) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, bool):
        raise TypeError("money is not a boolean")
    if isinstance(value, int):
        return minor_to_decimal(value, minor)
    if isinstance(value, Fraction):
        return Decimal(format_exact(value))
    return Decimal(str(value))


def _latest_output_balances(
    bundle: InputBundle, output: OutputBundle, book_code: str, external_id: str
) -> dict[str, Mapping[str, object]]:
    """Per ``<contract>@<entity>`` subject of the contract, the columns of its latest period."""
    starts = {
        (entity.code, item.period_key): item.start_date
        for entity in bundle.entities
        for item in entity.periods
    }
    book = next((item for item in output.books if item.book_code == book_code), None)
    prefix = contract_subject_key(external_id) + "@"
    latest: dict[str, tuple[date, Mapping[str, object]]] = {}
    for item in () if book is None else book.balances:
        if not item.subject_key.startswith(prefix):
            continue
        entity_code = str(item.columns.get("entity") or item.subject_key.rsplit("@", 1)[-1])
        start = starts.get((entity_code, item.period_key), date.min)
        found = latest.get(item.subject_key)
        if found is None or start >= found[0]:
            latest[item.subject_key] = (start, item.columns)
    return {subject: columns for subject, (_, columns) in latest.items()}


def _balances(
    session: Session,
    current: Mapping[str, Any],
    bundle: InputBundle,
    output: OutputBundle,
) -> tuple[list[ImpactBalanceOut], list[ImpactBalanceOut]]:
    """The labelled balances of the stored and the dry-run versions (L5-2-Q-6)."""
    contract_id = _uuid(current["id"])
    currency = str(current["transaction_currency"]).strip()
    minor = _minor(currency)
    book_code = queries.primary_book(session)
    names = (*BALANCE_ALWAYS, *BALANCE_WHEN_SET)
    before = dict.fromkeys(names, Decimal(0))
    stored = bundles.previous_version(session, _uuid(current["combination_group_id"]), book_code)
    if stored is not None:
        for row in session.execute(
            select(contract_version_balance).where(
                contract_version_balance.c.contract_version_id == stored["id"],
                contract_version_balance.c.contract_id == contract_id,
            )
        ).mappings():
            for name in names:
                before[name] += Decimal(str(row[f"{name}_txn"]))
    after = dict.fromkeys(names, Decimal(0))
    external_id = str(current["external_id"])
    for columns in _latest_output_balances(bundle, output, book_code, external_id).values():
        for name in names:
            after[name] += _to_amount(columns.get(f"{name}_txn"), minor)
    shown = [
        name for name in names if name in BALANCE_ALWAYS or before[name] != 0 or after[name] != 0
    ]
    return (
        [ImpactBalanceOut(balance=name, amount=_money(before[name], currency)) for name in shown],
        [ImpactBalanceOut(balance=name, amount=_money(after[name], currency)) for name in shown],
    )


def group_catch_up(books: Sequence[Any], minor_unit: int, primary_book: str) -> Decimal | None:
    """The P&L impact of a dry run as supervisor ruling R-66 (4) measures it, in the contract
    currency: the engine's catch-up (04 T-CON-11 ``catch_up_amount``) summed over every member
    contract of the combination group, in absolute value — read in the tenant's primary book, else
    in every book the run produced, the largest amount taken. None when the run produced no book:
    no book yields a figure, and the caller fails closed. API-S-ImpactSummary ``catch_up_total``
    reads the element's own contract in the primary book only. Pure: CPU-testable."""
    totals: dict[str, Decimal] = {}
    for book in books:
        total = Decimal(0)
        for item in book.obligation_versions:
            value = item.columns.get("catch_up_amount")
            if value is None:
                continue
            total += (
                minor_to_decimal(value, minor_unit)
                if isinstance(value, int) and not isinstance(value, bool)
                else Decimal(format_exact(value))
                if isinstance(value, Fraction)
                else Decimal(str(value))
            )
        code = str(getattr(book.book_code, "value", book.book_code))
        totals[code] = abs(total)
    if not totals:
        return None
    return totals[primary_book] if primary_book in totals else max(totals.values())


def _dry_run(
    session: Session,
    now: datetime,
    current: Mapping[str, Any],
    element: Mapping[str, Any],
    row: Mapping[str, Any],
) -> tuple[ImpactSummaryOut, Decimal | None]:
    """The group computed in ``DRY_RUN`` with the version applied as if approved now: its
    API-S-ImpactSummary and the catch-up over the whole group (``group_catch_up``)."""
    contract_id = _uuid(current["id"])
    previous = _latest_approved(session, _uuid(element["id"]))
    pending = [_changed_event(row, previous, None)]
    bundle = bundles.build(
        session,
        _uuid(current["combination_group_id"]),
        now,
        pending,
        DRY_RUN,
        pending_contract_id=contract_id,
    )
    key = obligation_subject_key(str(current["external_id"]), str(element["element_code"]))
    version_key = f"{key}@v{int(row['version_no'])}"
    bundle = dataclasses.replace(
        bundle,
        estimate_versions=tuple(
            dataclasses.replace(item, status=APPROVED) if item.version_key == version_key else item
            for item in bundle.estimate_versions
        ),
    )
    output = computation.default_engine()(bundle)
    summary = impact_summary(session, current, bundle, output, pending, computed_at=now)
    before, after = _balances(session, current, bundle, output)
    currency = str(current["transaction_currency"]).strip()
    return (
        summary.model_copy(update={"balances_before": before, "balances_after": after}),
        group_catch_up(
            output.books, ISO_4217[currency].minor_unit, str(queries.primary_book(session))
        ),
    )


def _impact_preview(summary: ImpactSummaryOut) -> approvals.ImpactPreview:
    """The dry run as the request's impact preview (REQ-PLT-015)."""
    data = summary.model_dump(mode="json")
    revenue = data["revenue_by_period"]
    return approvals.ImpactPreview(
        before={
            "transaction_price": data["transaction_price_before"],
            "rpo": data["rpo_before"],
            "revenue_by_period": [
                {"period_key": item["period_key"], "amount": item["before"]} for item in revenue
            ],
            "balances": data["balances_before"],
        },
        after={
            "transaction_price": data["transaction_price_after"],
            "rpo": data["rpo_after"],
            "revenue_by_period": [
                {"period_key": item["period_key"], "amount": item["after"]} for item in revenue
            ],
            "balances": data["balances_after"],
            "catch_up_total": data["catch_up_total"],
            "journal_lines": data["journal_lines"],
        },
    )


def _spot_rate(rates: Sequence[FxRateInput], *, base: str, quote: str, on: date) -> Decimal | None:
    """The engine's ``spot`` rate from ``base`` to ``quote`` on ``on`` among the pinned rows (the
    rate rule of the modification thresholds, 04 §16.14 ``fx_basis``): 1 for equal currencies,
    None when no row qualifies."""
    if base == quote:
        return Decimal(1)
    try:
        return Decimal(Rates(rates, base, quote).spot(on).text)
    except RateMissing:
        return None


def _converted(amount: Decimal, rate: Decimal, currency: str) -> Decimal:
    """``amount × rate`` rounded half up at ``currency``'s minor unit (S12-R-02's rounding)."""
    unit = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    return (amount * rate).quantize(unit, rounding=ROUND_HALF_UP)


def routing_facts(
    catch_up: Decimal,
    *,
    functional_currency: str,
    to_functional: Decimal | None,
    to_threshold: Decimal | None,
    group_impact: Decimal | None,
) -> tuple[tuple[Decimal, str] | None, frozenset[str]]:
    """The routing facts of an ``ESTIMATE_VERSION`` request (PRD §2.5 "If absolute P&L impact ≥
    USD 50,000.00: 2: Controller"; supervisor rulings R-41 (7) and R-66 (4); 04 §16.10 rev
    1.104). The P&L impact of a version is the catch-up of its submission's dry run, in the
    contract currency: ``group_impact``, the catch-up summed over the combination group
    (``group_catch_up``). ``amount`` is the impact in the entity's functional currency at the
    ``spot`` rate on the version's effective date — not stated when that rate is missing. The
    flag ``PL_IMPACT_GE_50K`` compares the impact in USD at the ``spot`` rate to USD. Whenever the
    threshold cannot be measured the flag is set, so the Controller's step applies: no rate to USD
    for an impact that is not zero, or no ``group_impact`` (None — no book yields a figure; the
    amount then states ``catch_up``, the summary's own figure). Pure: CPU-testable."""
    impact = abs(catch_up) if group_impact is None else abs(group_impact)
    amount = (
        None
        if to_functional is None
        else (_converted(impact, to_functional, functional_currency), functional_currency)
    )
    above = group_impact is None or (
        impact != 0
        and (
            to_threshold is None
            or _converted(impact, to_threshold, THRESHOLD_CURRENCY) >= PL_IMPACT_THRESHOLD
        )
    )
    return amount, (frozenset({ESTIMATE_PL_IMPACT_FLAG}) if above else frozenset())


def _routing_facts(
    session: Session,
    known_at: datetime,
    current: Mapping[str, Any],
    row: Mapping[str, Any],
    summary: ImpactSummaryOut,
    group_impact: Decimal | None,
) -> tuple[tuple[Decimal, str] | None, frozenset[str]]:
    """``routing_facts`` of the version from its dry run and the pinned FX rows in force."""
    currency = str(summary.catch_up_total.currency).strip()
    functional = str(
        session.execute(
            select(legal_entity.c.functional_currency).where(
                legal_entity.c.id == current["contracting_entity_id"]
            )
        ).scalar_one()
    ).strip()
    rates = bundles.fx_rate_inputs(session, {currency, functional, THRESHOLD_CURRENCY}, known_at)
    on = row["effective_date"]
    return routing_facts(
        Decimal(str(summary.catch_up_total.amount)),
        functional_currency=functional,
        to_functional=_spot_rate(rates, base=currency, quote=functional, on=on),
        to_threshold=_spot_rate(rates, base=currency, quote=THRESHOLD_CURRENCY, on=on),
        group_impact=group_impact,
    )


def submit_version(
    uow: UnitOfWork, *, version_id: UUID, body: EstimateVersionSubmitIn
) -> EstimateVersionOut:
    """``POST /estimate-versions/{id}/submit``: validate, preview, hash and route the version.

    The routing reads the dry run (R-41 (7)): the request's amount is the absolute P&L impact and
    a version of USD 50,000.00 or more takes the Controller's second step (``routing_facts``).

    A version created inside a modification (T-CON-13 ``modification_id``) is not submitted
    once that modification is discarded (PRD ERR-88): no request is left to be decided for a
    voided modification. It takes the contract's group and row locks first — the locks the
    modification's discard holds while it looks for a version that is waiting — so neither
    passes the other.

    Every submission takes those locks (04 §16.10 rev 1.233, §16.14 rev 1.241): the request's
    content pins the contract's group and head (item EST-PREVIEW-HEAD-PIN-1), so the head the
    dry run read is the head the content states; and the version's evidence and its CONSTRAINT
    record are asked under them (``_submission_errors``)."""
    session = uow.session
    row = _version_row(session, version_id, lock=True)
    element = _estimate_row(session, _uuid(row["estimate_id"]))
    linked = row["modification_id"] is not None
    current = _visible_contract(session, element, for_update=True)
    _require_prepare(uow, current)
    if _text(row["status"]) != DRAFT:
        raise _invalid(NOT_SUBMITTABLE)
    if linked:
        change = session.execute(
            select(modification.c.modification_no, modification.c.status).where(
                modification.c.id == row["modification_id"]
            )
        ).one()
        if _text(change.status) == ModificationStatus.VOIDED.value:
            message = MODIFICATION_DISCARDED.format(modification_no=change.modification_no)
            raise Problem(
                "invalid-transition",
                errors=[ProblemError(rule_id=RULE_LIFECYCLE, message=message)],
            )
    values, errors = _version_errors(session, element, current, _stored_values(row), method=None)
    errors = errors or _submission_errors(session, element, current, row)
    if errors:
        raise _failed(errors)
    _eac_check(session, element, values)
    latest = _latest_approved(session, _uuid(element["id"]))
    if latest != row["supersedes_version_id"]:
        transitions.apply(
            session,
            VERSION_OBJECT,
            version_id,
            to_status=None,
            expected_status=DRAFT,
            set_values={"supersedes_version_id": latest, **_stamps(uow)},
        )
    try:
        summary, group_impact = _dry_run(session, uow.now, current, element, row)
    except EngineError as error:
        raise engine_problem(error) from error
    # The row's own digest is the content the kernel hashes for the request — the version, and
    # every member of its contract's group with its head — read as the kernel reads it: under the
    # tenant's scope (04 §16.10 rev 1.319; R-64 (1)). The command runs under the scope of
    # ``estimate.create``, which need not hold every contracting entity of the group. Nothing of
    # it is answered ahead of the kernel's question below: a refused preparer's row rolls back.
    with system_entity_scope(session):
        digest = sha256_hex(estimate_version_content(session, version_id))
    transitions.apply(
        session,
        VERSION_OBJECT,
        version_id,
        to_status=SUBMITTED,
        expected_status=DRAFT,
        set_values={"content_sha256": digest, **_stamps(uow)},
    )
    _status_audit(
        uow,
        version_id,
        DRAFT,
        SUBMITTED,
        contract_id=element["contract_id"],
        content_sha256=digest,
    )
    amount, flags = _routing_facts(session, uow.now, current, row, summary, group_impact)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.ESTIMATE_VERSION,
        subject_id=version_id,
        summary=(
            f"Approve {element['element_code']} version {int(row['version_no'])} "
            f"of {current['contract_no']}"
        ),
        impact_preview=_impact_preview(summary),
        comment=body.comment,
        routing_decision=approvals.route_submission(
            uow, ApprovalSubjectType.ESTIMATE_VERSION, version_id, amount=amount, flags=flags
        ),
    )
    stored = _version_row(session, version_id)
    if _text(request["status"]) == PENDING and _text(stored["status"]) == SUBMITTED:
        transitions.apply(
            session,
            VERSION_OBJECT,
            version_id,
            to_status=None,
            expected_status=SUBMITTED,
            set_values={"approval_request_id": _uuid(request["id"]), **_stamps(uow)},
        )
    return get_version(session, version_id)


def withdraw_version(
    uow: UnitOfWork, *, version_id: UUID, body: EstimateVersionWithdrawIn
) -> EstimateVersionOut:
    """``POST /estimate-versions/{id}/withdraw``: the preparer withdraws the pending request, and
    ``on_voided`` returns the version to WITHDRAWN (PRD SM-01, SM-04)."""
    session = uow.session
    row = _version_row(session, version_id, lock=True)
    element = _estimate_row(session, _uuid(row["estimate_id"]))
    current = _visible_contract(session, element)
    _require_prepare(uow, current)
    if _text(row["status"]) != SUBMITTED or row["approval_request_id"] is None:
        raise _invalid(NOT_WITHDRAWABLE)
    approvals.withdraw(
        uow,
        approval_request_id=_uuid(row["approval_request_id"]),
        comment=body.comment,
        through_subject=True,
    )
    return get_version(session, version_id)


def discard_version(uow: UnitOfWork, *, version_id: UUID) -> EstimateVersionOut:
    """``POST /estimate-versions/{id}/discard`` (PRD SM-04 ``DRAFT`` → ``VOIDED``; item
    EST-DISCARD-1, supervisor ruling R-119 (e)): a draft that will not be submitted leaves the
    preparer's work — SCREENS §8.4 offered "Discard draft" and no route served it. ANY draft is
    discarded, also one that was submitted before and came back as a draft (rejected or
    withdrawn, then edited): the request's history stays on the row (``approval_request_id``)
    and in the audit trail. A DRAFT version has no pending request — a version waits for a
    decision as SUBMITTED. Every holder of ``estimate.create`` for the contracting entity may
    discard: a discard writes no content. Refused, 409 ``invalid-transition``: a version in any
    other status. Nothing else is written: the version keeps its number, which is not given out
    again, and an element's ``latest_version`` no longer counts it."""
    session = uow.session
    row = _version_row(session, version_id, lock=True)
    element = _estimate_row(session, _uuid(row["estimate_id"]))
    current = _visible_contract(session, element)
    _require_prepare(uow, current)
    if _text(row["status"]) != DRAFT:
        raise _invalid(NOT_DISCARDABLE)
    transitions.apply(
        session,
        VERSION_OBJECT,
        version_id,
        to_status=VOIDED,
        expected_status=DRAFT,
        set_values=_stamps(uow),
    )
    _status_audit(uow, version_id, DRAFT, VOIDED, contract_id=element["contract_id"])
    return get_version(session, version_id)


def request_preview(uow: UnitOfWork, *, version_id: UUID) -> JobOut:
    """``POST /estimate-versions/{id}/preview``: defer the dry run; 202 API-S-Job.

    A preview is asked by who could submit the version (04 §16.10 rev 1.295 "Who may ask for a
    preview"; supervisor ruling R-103 (b) (5)): 403 by name for a caller who does not read every
    entity it is bound to (rev 1.319: ``contract.read`` for each; until then the entities of
    her roles), before the version's state is asked, and nothing is deferred."""
    session = uow.session
    row = _version_row(session, version_id)
    element = _estimate_row(session, _uuid(row["estimate_id"]))
    current = _visible_contract(session, element)
    _require_prepare(uow, current)
    approvals.require_preview_scope(
        uow,
        ApprovalSubjectType.ESTIMATE_VERSION,
        version_id,
        action=PREVIEW_ACTION,
        permission=CREATE_PERMISSION,
    )
    if _text(row["status"]) not in PREVIEWABLE:
        raise _invalid(NOT_PREVIEWABLE)
    deferred = uow.defer(
        JobKind.CONTRACT_COMPUTE,
        {"mode": ESTIMATE_PREVIEW_MODE, "estimate_version_id": str(version_id)},
        subject_type=VERSION_OBJECT,
        subject_id=version_id,
    )
    job_row = session.execute(select(*JOB_COLUMNS).where(job.c.id == deferred["id"])).mappings()
    (item,) = job_outs(session, [dict(job_row.one())])
    return item


def run_preview(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``CONTRACT_COMPUTE`` in mode ``ESTIMATE_PREVIEW``: the dry run of one version; writes
    nothing."""
    version_id = UUID(str(params["estimate_version_id"]))
    with ctx.unit_of_work() as uow:
        session = uow.session
        row = _version_row(session, version_id)
        element = _estimate_row(session, _uuid(row["estimate_id"]))
        current = _visible_contract(session, element)
        try:
            summary, _ = _dry_run(session, uow.now, current, element, row)
        except EngineError as error:
            raise engine_problem(error) from error
        uow.discard()
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": VERSION_HREF.format(version_id=version_id),
            "counts": {"events": 1},
            "summary": summary.model_dump(mode="json"),
        },
    )


# --- lifecycle -----------------------------------------------------------------------------------


def _system_unit(uow: UnitOfWork) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, stamped with the caller's instant."""
    ctx = dataclasses.replace(uow.ctx, principal=system_principal(uow.principal.tenant_id))
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _approve_version(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``ESTIMATE_VERSION`` (module docstring; DG-CMD-09)."""
    session = uow.session
    row = _version_row(session, version_id, lock=True)
    if _text(row["status"]) != SUBMITTED:
        raise LookupError(f"estimate version {version_id} is not submitted")
    element = _estimate_row(session, _uuid(row["estimate_id"]))
    if element["contract_id"] is None:
        raise LookupError(PORTFOLIO_PENDING)
    # DG-KRN-DB-08 rev 1.36 (D-98 candidate 101a): group row first, then the contract row.
    group_id, current = repo.lock_group_then_contract(session, _uuid(element["contract_id"]))
    previous = _approved_versions(session, _uuid(element["id"]), lock=True)
    # DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d, R3d-b): every protecting lock held (the version,
    # the group, the contract, the earlier approved versions), nothing written yet — the version
    # must still hash to the basis the approver reviewed.
    approvals.assert_fresh_basis(uow, approval_request_id)
    # 04 §16.14 rev 1.241 (PRD ERR-94): the CONSTRAINT record is REVIEWED and the evidence is
    # still attached — both asked at the submission, both able to change since.
    refusal = _approval_refusal(session, element, current, row)
    if refusal is not None:
        raise Problem(
            "invalid-transition", errors=[ProblemError(rule_id=RULE_LIFECYCLE, message=refusal)]
        )
    for item in previous:
        earlier = _uuid(item["id"])
        transitions.apply(
            session,
            VERSION_OBJECT,
            earlier,
            to_status=SUPERSEDED,
            expected_status=APPROVED,
            set_values=_stamps(uow),
        )
        _status_audit(
            uow,
            earlier,
            APPROVED,
            SUPERSEDED,
            contract_id=element["contract_id"],
            superseded_by=str(version_id),
        )
    previous_id = None if not previous else _uuid(previous[0]["id"])
    transitions.apply(
        session,
        VERSION_OBJECT,
        version_id,
        to_status=APPROVED,
        expected_status=SUBMITTED,
        set_values={"approval_request_id": approval_request_id, **_stamps(uow)},
    )
    system = _system_unit(uow)
    (appended,) = append_events(
        system,
        contract_id=_uuid(current["id"]),
        expected_stream_version=int(current["head_stream_version"]),
        events=[_changed_event(row, previous_id, approval_request_id)],
        origin="SYSTEM",
    )
    for audit_event in system.drain_audit_events():
        uow.buffer_audit_event(audit_event)
    event_id = _uuid(appended["id"])
    transitions.apply(
        session,
        VERSION_OBJECT,
        version_id,
        to_status=None,
        expected_status=APPROVED,
        set_values={"applied_event_ids": [event_id], **_stamps(uow)},
    )
    _status_audit(
        uow,
        version_id,
        SUBMITTED,
        APPROVED,
        contract_id=element["contract_id"],
        approval_request_id=str(approval_request_id),
        event_id=str(event_id),
    )
    try:
        computation.recompute(uow, group_id, trigger=ComputationTrigger.COMMAND)
    except EngineError as error:
        raise engine_problem(error) from error


def _closer(to_status: Literal["REJECTED", "WITHDRAWN"]) -> Any:
    """``on_rejected`` (REJECTED) or ``on_voided`` (WITHDRAWN) of a SUBMITTED version."""

    def close(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> None:
        session = uow.session
        row = _version_row(session, version_id, lock=True)
        if _text(row["status"]) != SUBMITTED:
            return
        transitions.apply(
            session,
            VERSION_OBJECT,
            version_id,
            to_status=to_status,
            expected_status=SUBMITTED,
            set_values=_stamps(uow),
        )
        element = _estimate_row(session, _uuid(row["estimate_id"]))
        _status_audit(
            uow,
            version_id,
            SUBMITTED,
            to_status,
            contract_id=element["contract_id"],
            approval_request_id=str(approval_request_id),
        )

    return close


register_lifecycle(
    ApprovalSubjectType.ESTIMATE_VERSION,
    SubjectLifecycle(
        on_approved=_approve_version, on_rejected=_closer(REJECTED), on_voided=_closer(WITHDRAWN)
    ),
)


# --- reads ---------------------------------------------------------------------------------------


def estimates_statement(
    *,
    contract_id: UUID,
    kinds: Sequence[EstimateKind] = (),
    statuses: Sequence[ConfigStatus] = (),
) -> Select[Any]:
    """``GET /contracts/{id}/estimates``; ``status`` filters on the latest version's status — the
    highest ``version_no`` that is not a discarded draft (04 §16.14 rev 1.210)."""
    conditions: list[ColumnElement[bool]] = [estimate.c.contract_id == contract_id]
    if kinds:
        conditions.append(estimate.c.estimate_kind.in_([value.value for value in kinds]))
    if statuses:
        latest = (
            select(estimate_version.c.status)
            .where(
                estimate_version.c.estimate_id == estimate.c.id,
                estimate_version.c.status != VOIDED,
            )
            .order_by(estimate_version.c.version_no.desc())
            .limit(1)
            .scalar_subquery()
        )
        conditions.append(latest.in_([value.value for value in statuses]))
    return select(estimate).where(and_(*conditions))


def versions_statement(
    *,
    estimate_id: UUID,
    statuses: Sequence[ConfigStatus] = (),
    modification_id: UUID | None = None,
) -> Select[Any]:
    """``GET /estimates/{id}/versions``; ``modification_id`` keeps the versions created inside
    that modification (04 API-R-32 rev 1.210)."""
    statement = select(estimate_version).where(estimate_version.c.estimate_id == estimate_id)
    if statuses:
        statement = statement.where(
            estimate_version.c.status.in_([value.value for value in statuses])
        )
    if modification_id is not None:
        statement = statement.where(estimate_version.c.modification_id == modification_id)
    return statement


def _approvals(
    session: Session, request_ids: Sequence[UUID]
) -> dict[UUID, tuple[UUID | None, str, datetime]]:
    """The approving decision of each request: (approver, approver kind, decided at)."""
    wanted = sorted(set(request_ids))
    if not wanted:
        return {}
    found: dict[UUID, tuple[UUID | None, str, datetime]] = {}
    statement = (
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            approval_decision.c.decided_at,
        )
        .where(
            approval_decision.c.approval_request_id.in_(wanted),
            approval_decision.c.decision.in_(
                [ApprovalDecisionKind.APPROVE.value, ApprovalDecisionKind.AUTO_APPROVE.value]
            ),
        )
        .order_by(approval_decision.c.decided_at)
    )
    for request_id, approver_id, kind, decided_at in session.execute(statement):
        found[_uuid(request_id)] = (
            None if approver_id is None else _uuid(approver_id),
            _text(kind),
            decided_at,
        )
    return found


def _approved_by(
    row: Mapping[str, Any],
    decisions: Mapping[UUID, tuple[UUID | None, str, datetime]],
    names: Mapping[UUID, str],
) -> tuple[ActorOut | None, datetime | None]:
    if _text(row["status"]) not in (APPROVED, SUPERSEDED) or row["approval_request_id"] is None:
        return None, None
    decision = decisions.get(_uuid(row["approval_request_id"]))
    if decision is None:
        return None, None
    approver_id, kind, decided_at = decision
    return ActorOut.model_validate(approval_queries.actor(approver_id, kind, names)), decided_at


def _names(session: Session, *groups: Sequence[Any]) -> dict[UUID, str]:
    ids = [_uuid(value) for group in groups for value in group if value is not None]
    return approval_queries.display_names(session, ids)


def estimate_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[EstimateOut]:
    """API-R-32 estimate list items with ``current_version`` and ``latest_version`` (§16.14)."""
    if not rows:
        return []
    ids = [_uuid(row["id"]) for row in rows]
    versions = [
        dict(item)
        for item in session.execute(
            select(
                estimate_version.c.id,
                estimate_version.c.estimate_id,
                estimate_version.c.version_no,
                estimate_version.c.status,
                estimate_version.c.effective_date,
                estimate_version.c.approval_request_id,
            ).where(estimate_version.c.estimate_id.in_(ids))
        ).mappings()
    ]
    by_estimate: dict[UUID, list[dict[str, Any]]] = {}
    for item in versions:
        by_estimate.setdefault(_uuid(item["estimate_id"]), []).append(item)
    decisions = _approvals(
        session,
        [_uuid(item["approval_request_id"]) for item in versions if item["approval_request_id"]],
    )
    names = _names(
        session,
        [row["created_by"] for row in rows],
        [decision[0] for decision in decisions.values()],
    )
    obligation_ids = {
        _uuid(value)
        for row in rows
        for value in [row["obligation_id"], *(row["target_obligation_ids"] or ())]
        if value is not None
    }
    keys = (
        {
            _uuid(found_id): str(key)
            for found_id, key in session.execute(
                select(obligation.c.id, obligation.c.obligation_key).where(
                    obligation.c.id.in_(sorted(obligation_ids))
                )
            )
        }
        if obligation_ids
        else {}
    )

    def summary(item: Mapping[str, Any] | None) -> EstimateVersionSummaryOut | None:
        if item is None:
            return None
        approver, approved_at = _approved_by(item, decisions, names)
        return EstimateVersionSummaryOut(
            id=item["id"],
            version_no=int(item["version_no"]),
            status=ConfigStatus(_text(item["status"])),
            effective_date=item["effective_date"],
            approver=approver,
            approved_at=approved_at,
        )

    found = []
    for row in rows:
        items = sorted(by_estimate.get(_uuid(row["id"]), []), key=lambda item: item["version_no"])
        # A discarded draft (VOIDED; item EST-DISCARD-1) is not the element's latest version.
        items = [item for item in items if _text(item["status"]) != VOIDED]
        approved = [item for item in items if _text(item["status"]) == APPROVED]
        targets = [_uuid(value) for value in row["target_obligation_ids"] or ()]
        found.append(
            EstimateOut.model_validate(
                {
                    "id": row["id"],
                    "contract_id": row["contract_id"],
                    "portfolio_id": row["portfolio_id"],
                    "obligation_id": row["obligation_id"],
                    "obligation_key": None
                    if row["obligation_id"] is None
                    else keys.get(_uuid(row["obligation_id"])),
                    "estimate_kind": _text(row["estimate_kind"]),
                    "element_code": row["element_code"],
                    "vc_element_type": row["vc_element_type"],
                    "direction": row["direction"],
                    "method": _text(row["method"]),
                    "allocation_target": row["allocation_target"],
                    "target_obligation_ids": targets,
                    "target_obligation_keys": [keys[value] for value in targets if value in keys],
                    "allocation_criteria_evidence": row["allocation_criteria_evidence"],
                    "current_version": summary(approved[-1] if approved else None),
                    "latest_version": summary(items[-1] if items else None),
                    "created_by": approval_queries.actor(
                        row["created_by"], _text(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                }
            )
        )
    return found


def get_estimate(session: Session, estimate_id: UUID) -> EstimateOut:
    (item,) = estimate_outs(session, [visible_estimate(session, estimate_id)])
    return item


def version_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[EstimateVersionOut]:
    """T-CON-13 versions with ``approver``, ``approved_at`` and the kind additions of §16.14."""
    if not rows:
        return []
    elements = {
        _uuid(item["id"]): dict(item)
        for item in session.execute(
            select(estimate).where(
                estimate.c.id.in_(sorted({_uuid(row["estimate_id"]) for row in rows}))
            )
        ).mappings()
    }
    contract_ids = sorted(
        {_uuid(item["contract_id"]) for item in elements.values() if item["contract_id"]}
    )
    currencies = (
        {
            _uuid(found_id): str(code).strip()
            for found_id, code in session.execute(
                select(contract.c.id, contract.c.transaction_currency).where(
                    contract.c.id.in_(contract_ids)
                )
            )
        }
        if contract_ids
        else {}
    )
    decisions = _approvals(
        session, [_uuid(row["approval_request_id"]) for row in rows if row["approval_request_id"]]
    )
    names = _names(
        session,
        [row["created_by"] for row in rows],
        [decision[0] for decision in decisions.values()],
    )
    found = []
    for row in rows:
        element = elements[_uuid(row["estimate_id"])]
        kind = _text(element["estimate_kind"])
        currency = (
            str(row["currency"]).strip()
            if row["currency"] is not None
            else currencies.get(_uuid(element["contract_id"]), "USD")
            if element["contract_id"] is not None
            else "USD"
        )
        values = _stored_values(row)
        approver, approved_at = _approved_by(row, decisions, names)
        excluded = None
        if (
            kind == EstimateKind.VARIABLE_CONSIDERATION.value
            and values["unconstrained_amount"] is not None
            and values["constrained_amount"] is not None
        ):
            gap = values["unconstrained_amount"] - values["constrained_amount"]
            excluded = _money(max(Decimal(0), gap), currency)
        costs = None
        ratio = None
        if kind == EstimateKind.EAC.value:
            incurred = costs_incurred_to_date(session, element, row["effective_date"])
            costs = _money(incurred, currency)
            total = values["expected_total_amount"]
            if total is not None and total != 0:
                ratio = _plain_decimal(incurred / total)
        found.append(
            EstimateVersionOut.model_validate(
                {
                    "id": row["id"],
                    "estimate_id": row["estimate_id"],
                    "version_no": int(row["version_no"]),
                    "status": _text(row["status"]),
                    "effective_date": row["effective_date"],
                    "scenarios": values["scenarios"],
                    "parameters": values["parameters"],
                    **{
                        name: None
                        if values[name] is None
                        else _money(values[name], currency).amount
                        for name in AMOUNT_COLUMNS
                    },
                    **{name: _plain_decimal(values[name]) for name in EXACT_COLUMNS},
                    "amortization_months": row["amortization_months"],
                    "currency": currency,
                    "constraint_checklist": row["constraint_checklist"],
                    "rationale": row["rationale"],
                    "judgement_record_id": row["judgement_record_id"],
                    "content_sha256": None
                    if row["content_sha256"] is None
                    else str(row["content_sha256"]).strip(),
                    "approval_request_id": row["approval_request_id"],
                    "applied_event_ids": list(row["applied_event_ids"] or ()),
                    "supersedes_version_id": row["supersedes_version_id"],
                    "modification_id": row["modification_id"],
                    "approver": approver,
                    "approved_at": approved_at,
                    "excluded_amount": excluded,
                    "costs_incurred_to_date": costs,
                    "progress_ratio": ratio,
                    "created_by": approval_queries.actor(
                        row["created_by"], _text(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "row_version": int(row["row_version"]),
                }
            )
        )
    return found


def get_version(session: Session, version_id: UUID) -> EstimateVersionOut:
    row = _version_row(session, version_id)
    visible_estimate(session, _uuid(row["estimate_id"]))
    (item,) = version_outs(session, [row])
    return item

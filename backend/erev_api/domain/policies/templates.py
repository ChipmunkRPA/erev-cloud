"""Obligation templates (04 T-REF-22, T-REF-23, T-REF-27, E-11, E-18 to E-21, E-89 to E-91, E-105,
§14.1 DB-04, §15.3 API-R-24, API-R-57, §16.2 API-S-VersionSummary; ENGINE_SPEC §0.2 Table 0.2-A,
§3.3 S03-R-01, S03-R-02, S03-R-17; POLICIES §0.5; PRD §2.6, SM-04; SCREENS §11.2; 03 REQ-POL-001,
REQ-POL-003, REQ-POB-005; CTL-031; BUILD_SPEC RFD-10).

Outputs. A template version (T-REF-23) holds the outputs every obligation built from it receives.
``output_errors`` reports the T-REF-23 checks in field order (series increment, over-time criterion,
point-in-time methods, ratable convention, term), then the revenue category, disaggregation, level P
policy values and account role overrides, whose keys are ``account_role`` literals or
``BILLING_CLEARING:<purpose>`` and whose values name active GL accounts (T-REF-15).

Test cases. ``case_errors`` checks the shape of an example case (T-REF-27): ``input`` books
``lines`` at ``booking_date``; ``expected_output`` names the expected ``drafts`` and ``findings``.
``run_test_cases`` builds an input bundle with one contract booking the case lines, each line's
product resolving to the version under test and the tenant's resolved policies. It runs stages 01
and 02 and calls ``erev_engine.stages.s03_pob_builder.build_lines(ctx, st, lines, at, tb)`` at the
booking date (Table 0.2-A; no engine change). Each case records its result; when every case passes,
a DRAFT version becomes TESTED, and the drafts are recorded in the detail of the run's audit event.

Resolution (CTL-031). ``template_inputs`` returns the PUBLISHED and SUPERSEDED versions published at
or before ``known_at`` as engine ``TemplateInput`` rows with their effective dates;
``resolve_template_version`` picks the greatest version whose range holds a date, as stage 03 does
(S03-R-02). A DRAFT, TESTED, SUBMITTED or APPROVED version never resolves.

Lifecycle. ``POB_TEMPLATE_VERSION_KIND`` hands template versions to the configuration lifecycle
(RFD-5): one PUBLISHED version per template, which the next publication supersedes. This module
registers the approval callbacks when it is imported.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    ContractInput,
    EntityInput,
    EventInput,
    GroupInput,
    InputBundle,
    PeriodInput,
    ProductInput,
    ResolvedPolicyInput,
    TemplateInput,
)
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.dates import add_months, month_end
from erev_engine.enums import BookCode as EngineBookCode
from erev_engine.errors import EngineError
from erev_engine.money import format_exact
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s03_pob_builder
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s03_pob_builder import PobDraft
from erev_engine.stages.state import BookContext, Finding, PolicyResolver
from erev_engine.trace import TraceBuilder
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.audit.writer import record_facts
from erev_api.db.tables import (
    approval_request,
    gl_account,
    pob_template,
    pob_template_version,
    product,
    rule_test_case,
)
from erev_api.domain.policies import lifecycle
from erev_api.domain.reference import mapping
from erev_api.domain.reference import products as product_rules
from erev_api.enums import (
    AccountRole,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ClearingPurpose,
    ConfigStatus,
)
from erev_api.problems import Problem, ProblemError
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

OBJECT_TEMPLATE: Final = "pob_template"
OBJECT_VERSION: Final = "pob_template_version"
OBJECT_TEST_CASE: Final = "rule_test_case"
SUBJECT_TYPE: Final = "pob_template_version"  # T-REF-27 `subject_type` of a template version
RULE_TEMPLATE: Final = "T-REF-22"
RULE_VERSION: Final = "T-REF-23"
RULE_TEST_CASE: Final = "T-REF-27"
RULE_EVIDENCE: Final = "REQ-POL-003"
RULE_OPEN_VERSION: Final = "SM-04"
TEST_ACTION: Final = "pob_template_version.test"
RUN_CASES_ACTION: Final = "rule_test_case.run"
CASE_PASS: Final = "PASS"
CASE_FAIL: Final = "FAIL"

# 04 T-REF-23 checks.
SERIES_INCREMENT_UNITS: Final = ("day", "month", "transaction", "unit")
START_DATE_RULES: Final = (
    "LINE_START",
    "BOOKING_DATE",
    "CONTROL_TRANSFER",
    "FIRST_USAGE",
    "LICENCE_START_OR_AVAILABLE",
)
END_DATE_RULES: Final = ("LINE_END", "START_PLUS_TERM", "NONE")
POINT_IN_TIME_METHODS: Final = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED", "MANUAL"})
OUTPUT_COLUMNS: Final = subjects.POB_TEMPLATE_OUTPUT_COLUMNS
REQUIRED_OUTPUTS: Final = ("satisfaction_pattern", "recognition_method")
# T-REF-23 column defaults; ``satisfaction_pattern`` and ``recognition_method`` have none.
OUTPUT_DEFAULTS: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "obligation_kind": "STANDARD",
        "distinctness": "distinct",
        "series_increment_unit": None,
        "satisfaction_pattern": None,
        "over_time_criterion": "NOT_APPLICABLE",
        "recognition_method": None,
        "ratable_convention": None,
        "start_date_rule": "LINE_START",
        "end_date_rule": "LINE_END",
        "term_months": None,
        "principal_agent": "PRINCIPAL",
        "warranty_type": "NONE",
        "licence_nature": "NOT_APPLICABLE",
        "sfc_assessment_required": False,
        "revenue_category": None,
        "disaggregation": {},
        "account_role_overrides": {},
        "stratification_label": None,
        "is_excluded_from_netting_attribution": False,
        "policy_values": {},
    }
)
CONVENTION_POLICY: Final = "recognition.time_convention"  # POL-090, level P (T, P)

# Example cases (T-REF-27; L2-1-Q-46).
CASE_INPUT_MEMBERS: Final = frozenset({"booking_date", "currency", "lines"})
LINE_MEMBERS: Final = frozenset(
    {"obligation_key", "product_code", "quantity", "total_price", "start_date", "end_date"}
    | {"stratification"}
)
EXPECTED_MEMBERS: Final = frozenset({"drafts", "findings"})
MAX_CASE_LINES: Final = 50
DEFAULT_CURRENCY: Final = "USD"
# [J] The natural keys of the case world; no tenant row is created.
CASE_CONTRACT: Final = "TEST-CASE"
CASE_CUSTOMER: Final = "TEST-CUSTOMER"
CASE_ENTITY: Final = "TEST-ENTITY"
CASE_GROUP: Final = "TEST-GROUP"
CASE_BOOK: Final = "ASC606"
CASE_HORIZON_MONTHS: Final = 12
ZERO_SHA256: Final = "0" * 64

_CODE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}")  # TY-06
_DECIMAL: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")  # ASCII digits only (D-78)
_ISO_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ROLES: Final = frozenset(role.value for role in AccountRole)
_PURPOSES: Final = frozenset(purpose.value for purpose in ClearingPurpose)

# [J] Copy the documents leave open, in the PRD §5.5 tone.
CODE_TAKEN: Final = "Obligation template code {code} is already used."
SATISFACTION_REQUIRED: Final = "Choose a satisfaction pattern."
METHOD_REQUIRED: Final = "Choose a recognition method."
SERIES_UNIT_REQUIRED: Final = "Choose the series increment of a series obligation."
SERIES_UNIT_NOT_ALLOWED: Final = "A series increment applies only to a series obligation."
CRITERION_REQUIRED: Final = "Choose the over-time criterion of an over-time obligation."
CRITERION_NOT_ALLOWED: Final = "An over-time criterion applies only to an over-time obligation."
POINT_IN_TIME_METHOD: Final = (
    "A point-in-time obligation uses Point in time, Units delivered or Manual."
)
CONVENTION_REQUIRED: Final = "Choose the ratable convention for time elapsed."
CONVENTION_NOT_ALLOWED: Final = "A ratable convention applies only to time elapsed."
TERM_REQUIRED: Final = "Enter the term in months for Start plus term."
TERM_POSITIVE: Final = "Enter a term of at least one month."
CATEGORY_FORMAT: Final = (
    "Enter a revenue category of letters, digits and the characters _ . : / # ( ) + -."
)
ATTRIBUTE_CODE: Final = "Name the disaggregation attribute."
ATTRIBUTE_VALUE: Final = "Enter a value for this disaggregation attribute."
OVERRIDE_KEY: Final = "Use an account role, or Billing clearing with a clearing purpose."
OVERRIDE_RESERVED: Final = "No account can be mapped to {label}."
OVERRIDE_ACCOUNT: Final = "Choose an active GL account."
SOURCE_UNKNOWN: Final = "Choose a version of this obligation template to copy."
VERSION_OPEN: Final = (
    "Another version of this obligation template is open. Finish it or withdraw it first."
)
NOT_TESTABLE: Final = "Only a draft or tested version can run its tests."
CASES_REQUIRED: Final = "Add at least one test case before running the tests."
EVIDENCE_INCOMPLETE: Final = "Run the tests again: every test case must pass."
INPUT_MEMBER: Final = "Use only booking_date, currency and lines."
BOOKING_DATE: Final = "Enter the booking date as YYYY-MM-DD."
CURRENCY: Final = "Enter an ISO 4217 currency code."
LINES_COUNT: Final = "Add between 1 and 50 lines."
LINE_SHAPE: Final = "Give each line a product_code and a total_price."
LINE_MEMBER: Final = (
    "Use only obligation_key, product_code, quantity, total_price, start_date, end_date and "
    "stratification."
)
LINE_TEXT: Final = "Enter a non-blank text value."
LINE_DECIMAL: Final = "Enter a decimal number as text, for example 120000.00."
LINE_QUANTITY: Final = "Enter a quantity other than zero, as text."
LINE_DATE: Final = "Enter the date as YYYY-MM-DD."
LINE_KEY_TWICE: Final = "Another line of this case uses this obligation key."
EXPECTED_SHAPE: Final = "Expect drafts, findings or both, and nothing else."
EXPECTED_DRAFTS: Final = "Enter the expected drafts as a list of objects."
EXPECTED_FINDINGS: Final = "Enter the expected finding codes as a list of text values."


def _error(field: str, message: str, rule_id: str = RULE_VERSION) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _plain(value: Any) -> Any:
    """A StrEnum member as its literal; other values as they are."""
    return str(value) if isinstance(value, str) else value


def merged_outputs(base: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """The outputs of ``base`` with the output members of ``changes`` applied, as literals."""
    merged = {name: _plain(base[name]) for name in OUTPUT_COLUMNS}
    for name in OUTPUT_COLUMNS:
        if name in changes:
            value = _plain(changes[name])
            if name == "account_role_overrides" and isinstance(value, Mapping):
                value = {str(key): str(account) for key, account in value.items()}
            merged[name] = value
    return merged


def _series_errors(values: Mapping[str, Any]) -> list[ProblemError]:
    """``CHECK ((distinctness = 'series') = (series_increment_unit IS NOT NULL))`` (REQ-POB-005)."""
    series = values["distinctness"] == "series"
    unit = values["series_increment_unit"]
    if series and unit is None:
        return [_error("series_increment_unit", SERIES_UNIT_REQUIRED)]
    if not series and unit is not None:
        return [_error("series_increment_unit", SERIES_UNIT_NOT_ALLOWED)]
    return []


def _measure_errors(values: Mapping[str, Any]) -> list[ProblemError]:
    """The over-time criterion, point-in-time methods and ratable convention checks of T-REF-23."""
    errors: list[ProblemError] = []
    pattern, method = values["satisfaction_pattern"], values["recognition_method"]
    criterion, convention = values["over_time_criterion"], values["ratable_convention"]
    if pattern == "OVER_TIME" and criterion == "NOT_APPLICABLE":
        errors.append(_error("over_time_criterion", CRITERION_REQUIRED))
    elif pattern == "POINT_IN_TIME" and criterion != "NOT_APPLICABLE":
        errors.append(_error("over_time_criterion", CRITERION_NOT_ALLOWED))
    if pattern == "POINT_IN_TIME" and method is not None and method not in POINT_IN_TIME_METHODS:
        errors.append(_error("recognition_method", POINT_IN_TIME_METHOD))
    if method == "TIME_ELAPSED" and convention is None:
        errors.append(_error("ratable_convention", CONVENTION_REQUIRED))
    elif method is not None and method != "TIME_ELAPSED" and convention is not None:
        errors.append(_error("ratable_convention", CONVENTION_NOT_ALLOWED))
    return errors


def _disaggregation_errors(values: Any) -> list[ProblemError]:
    """``disaggregation`` maps non-blank attribute codes to non-blank text values."""
    if not isinstance(values, Mapping):
        return [_error("disaggregation", ATTRIBUTE_VALUE)]
    errors: list[ProblemError] = []
    for code in sorted(values):
        where = f"disaggregation.{code}"
        value = values[code]
        if not str(code).strip():
            errors.append(_error(where, ATTRIBUTE_CODE))
        elif not isinstance(value, str) or not value.strip():
            errors.append(_error(where, ATTRIBUTE_VALUE))
    return errors


def _override_key_message(key: str) -> str | None:
    """The finding on an override key: an ``account_role`` literal, not reserved (D-14a), with a
    clearing purpose exactly for ``BILLING_CLEARING`` (T-REF-15 override key)."""
    role, separator, purpose = key.partition(":")
    if role not in _ROLES:
        return OVERRIDE_KEY
    if role in mapping.RESERVED_ROLES:
        return OVERRIDE_RESERVED.format(label=mapping.ROLE_LABELS[role])
    if role == AccountRole.BILLING_CLEARING.value:
        return None if separator and purpose in _PURPOSES else OVERRIDE_KEY
    return OVERRIDE_KEY if separator else None


def override_errors(session: Session, overrides: Any) -> list[ProblemError]:
    """Findings on ``account_role_overrides``, in key order: the key form and an active GL account
    the session can see."""
    if not isinstance(overrides, Mapping):
        return [_error("account_role_overrides", OVERRIDE_ACCOUNT)]
    parsed: list[tuple[str, str | None, UUID | None]] = []
    for key in sorted(overrides):
        message = _override_key_message(str(key))
        try:
            account_id: UUID | None = UUID(str(overrides[key]))
        except ValueError:
            account_id = None
        parsed.append((str(key), message, account_id))
    ids = [account_id for _, _, account_id in parsed if account_id is not None]
    active = {
        UUID(str(found))
        for found in session.execute(
            select(gl_account.c.id).where(gl_account.c.id.in_(ids), gl_account.c.is_active)
        ).scalars()
    }
    errors: list[ProblemError] = []
    for key, message, account_id in parsed:
        where = f"account_role_overrides.{key}"
        if message is not None:
            errors.append(_error(where, message))
        elif account_id is None or account_id not in active:
            errors.append(_error(where, OVERRIDE_ACCOUNT))
    return errors


def output_errors(session: Session, values: Mapping[str, Any]) -> list[ProblemError]:
    """Every finding on the merged outputs of a version, in field order (T-REF-23; DG-CMD-03)."""
    errors: list[ProblemError] = []
    if values["satisfaction_pattern"] is None:
        errors.append(_error("satisfaction_pattern", SATISFACTION_REQUIRED))
    if values["recognition_method"] is None:
        errors.append(_error("recognition_method", METHOD_REQUIRED))
    errors += _series_errors(values)
    errors += _measure_errors(values)
    term = values["term_months"]
    if values["end_date_rule"] == "START_PLUS_TERM" and term is None:
        errors.append(_error("term_months", TERM_REQUIRED))
    elif term is not None and term < 1:
        errors.append(_error("term_months", TERM_POSITIVE))
    category = values["revenue_category"]
    if category is not None and not _CODE.fullmatch(str(category)):
        errors.append(_error("revenue_category", CATEGORY_FORMAT))
    errors += _disaggregation_errors(values["disaggregation"])
    errors += product_rules.policy_values_errors(values["policy_values"] or {})
    errors += override_errors(session, values["account_role_overrides"])
    return errors


# --- example cases (T-REF-27) ----------------------------------------------------------------


def _case_error(field: str, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=RULE_TEST_CASE, message=message)


def _is_date(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_decimal(value: Any) -> bool:
    return isinstance(value, str) and _DECIMAL.fullmatch(value) is not None


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _line_errors(index: int, line: Any, keys: set[str]) -> list[ProblemError]:
    where = f"input.lines[{index}]"
    if not isinstance(line, Mapping):
        return [_case_error(where, LINE_SHAPE)]
    errors = [
        _case_error(f"{where}.{name}", LINE_MEMBER) for name in sorted(set(line) - LINE_MEMBERS)
    ]
    if not _is_text(line.get("product_code")):
        errors.append(_case_error(f"{where}.product_code", LINE_TEXT))
    if not _is_decimal(line.get("total_price")):
        errors.append(_case_error(f"{where}.total_price", LINE_DECIMAL))
    quantity = line.get("quantity")
    if quantity is not None and (not _is_decimal(quantity) or Decimal(quantity) == 0):
        errors.append(_case_error(f"{where}.quantity", LINE_QUANTITY))
    for name in ("start_date", "end_date"):
        if line.get(name) is not None and not _is_date(line[name]):
            errors.append(_case_error(f"{where}.{name}", LINE_DATE))
    stratification = line.get("stratification")
    if stratification is not None and not isinstance(stratification, str):
        errors.append(_case_error(f"{where}.stratification", LINE_TEXT))
    key = line.get("obligation_key", f"POB-{index + 1:02d}")
    if not _is_text(key):
        errors.append(_case_error(f"{where}.obligation_key", LINE_TEXT))
    elif key in keys:
        errors.append(_case_error(f"{where}.obligation_key", LINE_KEY_TWICE))
    else:
        keys.add(str(key))
    return errors


def _expected_errors(expected: Mapping[str, Any]) -> list[ProblemError]:
    if not expected or not set(expected) <= EXPECTED_MEMBERS:
        return [_case_error("expected_output", EXPECTED_SHAPE)]
    errors: list[ProblemError] = []
    drafts = expected.get("drafts", [])
    if not isinstance(drafts, list) or not all(isinstance(item, Mapping) for item in drafts):
        errors.append(_case_error("expected_output.drafts", EXPECTED_DRAFTS))
    findings = expected.get("findings", [])
    if not isinstance(findings, list) or not all(isinstance(item, str) for item in findings):
        errors.append(_case_error("expected_output.findings", EXPECTED_FINDINGS))
    return errors


def case_errors(facts: Mapping[str, Any], expected: Mapping[str, Any]) -> list[ProblemError]:
    """The findings on an example case of a template version (L2-1-Q-46).

    ``input`` is ``{booking_date, currency?, lines: [{product_code, total_price, quantity?,
    obligation_key?, start_date?, end_date?, stratification?}]}``; ``expected_output`` is
    ``{drafts?, findings?}``.
    """
    errors = [
        _case_error(f"input.{name}", INPUT_MEMBER)
        for name in sorted(set(facts) - CASE_INPUT_MEMBERS)
    ]
    if not _is_date(facts.get("booking_date")):
        errors.append(_case_error("input.booking_date", BOOKING_DATE))
    currency = facts.get("currency")
    if currency is not None and (not isinstance(currency, str) or currency not in ISO_4217):
        errors.append(_case_error("input.currency", CURRENCY))
    lines = facts.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_CASE_LINES:
        errors.append(_case_error("input.lines", LINES_COUNT))
    else:
        keys: set[str] = set()
        for index, line in enumerate(lines):
            errors += _line_errors(index, line, keys)
    return errors + _expected_errors(expected)


def _engine_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    if isinstance(value, str | int | Decimal):
        return str(value)
    if isinstance(value, list | tuple):
        return ",".join(_engine_literal(item) for item in value)
    raise TypeError(f"unsupported policy value {type(value).__qualname__}")


def engine_policy_value(value: Any) -> str | tuple[str, ...] | Mapping[str, str]:
    """A registry value as ``ResolvedPolicyInput.value``: literals and decimals as text, a list as a
    tuple and an object as text members (ENGINE_SPEC §0.4)."""
    if isinstance(value, Mapping):
        return {str(key): _engine_literal(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return tuple(_engine_literal(item) for item in value)
    return _engine_literal(value)


def _flat_values(values: Mapping[str, Any]) -> dict[str, str]:
    """Level P values as the text members of ``ProductInput`` and ``TemplateInput``."""
    flat: dict[str, str] = {}
    for code, value in sorted(values.items()):
        converted = engine_policy_value(value)
        flat[str(code)] = (
            converted
            if isinstance(converted, str)
            else ",".join(converted.values() if isinstance(converted, Mapping) else converted)
        )
    return flat


def _case_lines(facts: Mapping[str, Any]) -> list[dict[str, object]]:
    """API-S-ContractLine members of the case lines (04 §16.1), decimals and dates typed."""
    lines: list[dict[str, object]] = []
    for index, raw in enumerate(facts["lines"]):
        line: dict[str, object] = {
            "obligation_key": str(raw.get("obligation_key", f"POB-{index + 1:02d}")),
            "product_code": str(raw["product_code"]).strip(),
            "quantity": Decimal(str(raw.get("quantity", "1"))),
            "total_price": Decimal(str(raw["total_price"])),
        }
        for name in ("start_date", "end_date"):
            if raw.get(name) is not None:
                line[name] = date.fromisoformat(str(raw[name]))
        if raw.get("stratification") is not None:
            line["stratification"] = str(raw["stratification"])
        lines.append(line)
    return lines


def _calendar(first: date, last: date, currency: str) -> EntityInput:
    """Monthly open ASC606 periods ``FY<year>-P<nn>`` from ``first`` through ``last``."""
    periods: list[PeriodInput] = []
    start = date(first.year, first.month, 1)
    while start <= last:
        periods.append(
            PeriodInput(
                period_key=f"FY{start.year}-P{start.month:02d}",
                fiscal_year=start.year,
                period_no=start.month,
                start_date=start,
                end_date=month_end(start),
                states=((CASE_BOOK, "open"),),
            )
        )
        start = add_months(start, 1)
    return EntityInput(CASE_ENTITY, currency, "UTC", "MONTHLY", tuple(periods))


def _product_inputs(
    session: Session, codes: Collection[str], *, template_code: str, at: date
) -> tuple[tuple[ProductInput, ...], dict[str, Mapping[str, Any]]]:
    """The tenant products of ``codes`` and their bundle components, each resolving to
    ``template_code`` (S03-R-02 step 2), with their level P values. Unknown codes are left out, so
    stage 03 reports ``PRODUCT_UNMAPPED``."""
    found: dict[str, ProductInput] = {}
    values: dict[str, Mapping[str, Any]] = {}
    pending = set(codes)
    while pending:
        rows = session.execute(
            select(product).where(product.c.code.in_(sorted(pending)))
        ).mappings()
        pending = set()
        for row in rows:
            code = str(row["code"])
            components = product_rules.bundle_components(session, row["id"], at=at)
            found[code] = ProductInput(
                code=code,
                sku_number=row["sku_number"],
                product_family=row["product_family"],
                revenue_category=row["revenue_category"],
                default_template_code=template_code,
                principal_agent=str(row["principal_agent"]),
                distinctness_default=str(row["distinctness_default"]),
                unit_of_measure=str(row["unit_of_measure"]),
                is_bundle=bool(row["is_bundle"]),
                policy_values=_flat_values(row["policy_values"]),
                assurance_cost_per_unit=row["assurance_cost_per_unit"],
                components=components,
                is_franchisor_preopening_service=bool(row["is_franchisor_preopening_service"]),
            )
            values[code] = dict(row["policy_values"])
            pending |= {c.component_product_code for c in components} - set(found)
    return tuple(found[code] for code in sorted(found)), values


def _template_input(
    version: Mapping[str, Any], template_code: str, *, effective_from: date
) -> TemplateInput:
    """The version under test as the only version of its template, effective from the case start."""
    return TemplateInput(
        template_code=template_code,
        version_key=f"{template_code}@v{version['version_no']}",
        version_no=int(version["version_no"]),
        content_sha256=version["content_sha256"] or ZERO_SHA256,
        obligation_kind=str(version["obligation_kind"]),
        distinctness=str(version["distinctness"]),
        series_increment_unit=version["series_increment_unit"],
        satisfaction_pattern=str(version["satisfaction_pattern"]),
        over_time_criterion=str(version["over_time_criterion"]),
        recognition_method=str(version["recognition_method"]),
        ratable_convention=None
        if version["ratable_convention"] is None
        else str(version["ratable_convention"]),
        start_date_rule=str(version["start_date_rule"]),
        end_date_rule=str(version["end_date_rule"]),
        term_months=version["term_months"],
        principal_agent=str(version["principal_agent"]),
        warranty_type=str(version["warranty_type"]),
        licence_nature=str(version["licence_nature"]),
        sfc_assessment_required=bool(version["sfc_assessment_required"]),
        revenue_category=version["revenue_category"],
        disaggregation={str(k): str(v) for k, v in sorted(dict(version["disaggregation"]).items())},
        account_role_overrides={
            str(k): str(v) for k, v in sorted(dict(version["account_role_overrides"]).items())
        },
        stratification_label=version["stratification_label"],
        is_excluded_from_netting_attribution=bool(version["is_excluded_from_netting_attribution"]),
        policy_values=_flat_values(version["policy_values"]),
        effective_from=effective_from,
        effective_to=None,
    )


def _level_p(values: Mapping[str, Any]) -> dict[str, Any]:
    """Level P values whose parameter is contract-pinned; ``PolicyResolver`` keeps pin P values in
    the PERIOD scope only (CV-17)."""
    return {
        code: value
        for code, value in values.items()
        if code in POLICY_PARAMETERS and POLICY_PARAMETERS[code].pin == "K"
    }


def _policies(
    session: Session,
    *,
    calendar: EntityInput,
    known_at: datetime,
    version: Mapping[str, Any],
    version_key: str,
    lines: Sequence[Mapping[str, object]],
    product_values: Mapping[str, Mapping[str, Any]],
) -> tuple[ResolvedPolicyInput, ...]:
    """The resolved policies of the case book (DG-KRN-REG-03; POLICIES §0.5).

    Every parameter resolves through ``registry.resolve`` at the TENANT level or the framework
    default. The version's ``policy_values`` and its ``ratable_convention`` (POL-090) are level P
    values of the case contract; each line's obligation adds its product's values, which the
    template's values precede (T-REF-20 note).
    """
    resolved: list[ResolvedPolicyInput] = []
    for code, spec in sorted(POLICY_PARAMETERS.items()):
        found = registry.resolve(session, code, book_code=BookCode.ASC606, known_at=known_at)
        if found.value is None:
            continue
        value = engine_policy_value(found.value)
        source = spec.source_ref if found.source_id is None else str(found.source_id)
        if spec.pin == "P":
            resolved.extend(
                ResolvedPolicyInput(
                    code,
                    "PERIOD",
                    f"{calendar.code}@{p.period_key}",
                    value,
                    found.level,
                    source,
                    "P",
                )
                for p in calendar.periods
            )
        else:
            resolved.append(ResolvedPolicyInput(code, "GROUP", "", value, found.level, source, "K"))
    template_values = _level_p(dict(version["policy_values"]))
    if version["ratable_convention"] is not None:
        template_values.setdefault(CONVENTION_POLICY, str(version["ratable_convention"]))
    for code, value in sorted(template_values.items()):
        resolved.append(
            ResolvedPolicyInput(
                code, "CONTRACT", CASE_CONTRACT, engine_policy_value(value), "P", version_key, "K"
            )
        )
    for line in lines:
        product_code = str(line["product_code"])
        merged = {**_level_p(product_values.get(product_code, {})), **template_values}
        subject_key = obligation_subject_key(CASE_CONTRACT, str(line["obligation_key"]))
        resolved.extend(
            ResolvedPolicyInput(
                code, "OBLIGATION", subject_key, engine_policy_value(value), "P", version_key, "K"
            )
            for code, value in sorted(merged.items())
        )
    return tuple(sorted(resolved, key=lambda p: (p.code, p.scope, p.subject_key)))


def _build_drafts(
    session: Session,
    version: Mapping[str, Any],
    template_code: str,
    facts: Mapping[str, Any],
    *,
    known_at: datetime,
) -> tuple[tuple[PobDraft, ...], list[Finding]]:
    """Stages 01 and 02 over the case world, then ``build_lines`` at the booking date."""
    booking = date.fromisoformat(str(facts["booking_date"]))
    currency = str(facts.get("currency") or DEFAULT_CURRENCY)
    lines = _case_lines(facts)
    dates = [
        booking,
        *(value for line in lines for value in line.values() if isinstance(value, date)),
    ]
    first, last = min(dates), add_months(max(dates), CASE_HORIZON_MONTHS)
    calendar = _calendar(first, last, currency)
    products, product_values = _product_inputs(
        session,
        {str(line["product_code"]) for line in lines},
        template_code=template_code,
        at=booking,
    )
    template = _template_input(
        version, template_code, effective_from=calendar.periods[0].start_date
    )
    policies = _policies(
        session,
        calendar=calendar,
        known_at=known_at,
        version=version,
        version_key=template.version_key,
        lines=lines,
        product_values=product_values,
    )
    book = BookInput(
        CASE_BOOK,
        True,
        (CASE_ENTITY,),
        policies,
        AccountMappingInput(f"{CASE_CONTRACT}@v0", ZERO_SHA256, ()),
    )
    header = ContractInput(
        external_id=CASE_CONTRACT,
        customer_code=CASE_CUSTOMER,
        related_party_group=None,
        contracting_entity_code=CASE_ENTITY,
        transaction_currency=currency,
        inception_date=booking,
        signature_date=booking,
        document_ref=None,
        termination_party=None,
        termination_has_penalty=None,
        termination_notice_days=None,
        has_commercial_substance=True,
        region=None,
        channel=None,
        contract_type=None,
        renewal_of_contract_key=None,
        judgements=(),
        material_rights=(),
        modifications=(),
        noncash_consideration=(),
        consideration_payable=(),
        payment_schedule=(),
        scope_605_35=False,
    )
    recorded_at = datetime.combine(booking, time(12), tzinfo=UTC)
    payload: dict[str, object] = {"lines": lines}
    booked = EventInput(
        event_key=f"{CASE_CONTRACT}/EV-000001",
        contract_key=CASE_CONTRACT,
        stream_version=1,
        event_type="CONTRACT_BOOKED",
        schema_version=1,
        effective_date=booking,
        recorded_at=recorded_at,
        record_seq=1,
        origin="API",
        is_manual=False,
        obligation_keys=tuple(str(line["obligation_key"]) for line in lines),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
        supersedes_event_key=None,
        modification_key=None,
        estimate_version_key=None,
        manual_adjustment_key=None,
    )
    bundle = InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="DRY_RUN",
        known_at=max(known_at, recorded_at),
        tenant_preset="DEFAULT",
        currencies={currency: ISO_4217[currency]},
        books=(book,),
        entities=(calendar,),
        group=GroupInput(
            group_key=CASE_GROUP,
            transaction_currency=currency,
            inception_date=booking,
            member_contract_keys=(CASE_CONTRACT,),
            criterion=None,
            previous_stream_heads=(),
            products=products,
            portfolios=(),
        ),
        contracts=(header,),
        events=(booked,),
        ssp_versions=(),
        pob_template_versions=(template,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    canonical = s01_canonicalize.run(bundle, tb)
    ctx = BookContext(
        book_code=EngineBookCode.ASC606,
        framework=EngineBookCode.ASC606,
        currencies=bundle.currencies,
        txn_currency=currency,
        entities={CASE_ENTITY: calendar},
        horizon={CASE_ENTITY: calendar.periods[-1].period_key},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=bundle.trigger,
        tenant_preset=bundle.tenant_preset,
    )
    identified = s02_contract_identification.run(ctx, canonical, tb)
    findings: list[Finding] = []
    drafts = s03_pob_builder.build_lines(
        ctx,
        identified,
        lines,
        booking,
        tb,
        contract_key=CASE_CONTRACT,
        source_event_key=booked.event_key,
        findings=findings,
    )
    return drafts, sorted(findings, key=Finding.sort_key)


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def draft_out(
    draft: PobDraft, *, version_id: UUID, template_code: str, version_no: int
) -> dict[str, Any]:
    """The recorded draft of one case line: API-S-Obligation terms with ``pob_template_version``
    (04 §16.2) and the template's version key."""
    return {
        "subject_key": draft.subject_key,
        "obligation_key": draft.obligation_key,
        "product_code": draft.product_code,
        "quantity": format_exact(draft.quantity),
        "stated_price": format_exact(draft.stated_price),
        "start_date": _iso(draft.start_date),
        "end_date": _iso(draft.end_date),
        "pricing_date": draft.pricing_date.isoformat(),
        "obligation_kind": draft.obligation_kind.value,
        "distinctness": draft.distinctness.value,
        "series_increment_unit": draft.series_increment_unit,
        "satisfaction_pattern": draft.satisfaction_pattern.value,
        "over_time_criterion": draft.over_time_criterion,
        "recognition_method": draft.recognition_method.value,
        "ratable_convention": None
        if draft.ratable_convention is None
        else draft.ratable_convention.value,
        "principal_agent": draft.principal_agent.value,
        "warranty_type": draft.warranty_type.value,
        "licence_nature": draft.licence_nature.value,
        "revenue_category": draft.revenue_category,
        "account_overrides": dict(draft.account_overrides),
        "template_code": draft.template_code,
        "template_version_key": draft.template_version_key,
        "pob_template_version": {
            "id": str(version_id),
            "template_code": template_code,
            "version_no": version_no,
        },
    }


def finding_out(finding: Finding) -> dict[str, Any]:
    return {
        "code": finding.code,
        "severity": finding.severity,
        "subject_key": finding.subject_key,
        "detail": dict(finding.detail),
    }


def case_passes(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    """PASS when the case ran, its finding codes equal ``expected_output.findings`` (without that
    member: no ``ERROR`` finding), and each expected draft's members equal the draft's, in order."""
    if actual.get("error") is not None:
        return False
    codes = [finding["code"] for finding in actual["findings"]]
    if "findings" in expected:
        if list(expected["findings"]) != codes:
            return False
    elif any(finding["severity"] == "ERROR" for finding in actual["findings"]):
        return False
    if "drafts" not in expected:
        return True
    wanted, got = list(expected["drafts"]), list(actual["drafts"])
    if len(wanted) != len(got):
        return False
    return all(
        all(name in draft and draft[name] == value for name, value in want.items())
        for want, draft in zip(wanted, got, strict=True)
    )


def run_case(
    session: Session,
    version: Mapping[str, Any],
    template_code: str,
    case: Mapping[str, Any],
    *,
    known_at: datetime,
) -> tuple[str, dict[str, Any]]:
    """The result of one example case and what it produced: the drafts and findings, or the error
    that stopped the run."""
    facts, expected = case["input"], case["expected_output"]
    if case_errors(facts, expected):
        error = {"code": "CASE_INVALID", "message": "The test case does not have the case shape."}
        return CASE_FAIL, {"drafts": [], "findings": [], "error": error}
    try:
        drafts, findings = _build_drafts(session, version, template_code, facts, known_at=known_at)
    except (EngineError, ValueError, TypeError, LookupError) as raised:
        code = raised.code if isinstance(raised, EngineError) else type(raised).__name__
        return CASE_FAIL, {
            "drafts": [],
            "findings": [],
            "error": {"code": code, "message": str(raised)},
        }
    actual: dict[str, Any] = {
        "drafts": [
            draft_out(
                draft,
                version_id=UUID(str(version["id"])),
                template_code=template_code,
                version_no=int(version["version_no"]),
            )
            for draft in drafts
        ],
        "findings": [finding_out(finding) for finding in findings],
        "error": None,
    }
    return (CASE_PASS if case_passes(expected, actual) else CASE_FAIL), actual


def case_evidence(session: Session, version_ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    """``test_evidence`` of each version: its example cases by last result (REQ-POL-003)."""
    evidence: dict[UUID, dict[str, Any]] = {
        UUID(str(version_id)): {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "not_run": 0,
            "last_run_at": None,
        }
        for version_id in version_ids
    }
    if not version_ids:
        return evidence
    rows = session.execute(
        select(
            rule_test_case.c.subject_id, rule_test_case.c.last_result, rule_test_case.c.last_run_at
        ).where(
            rule_test_case.c.subject_type == SUBJECT_TYPE,
            rule_test_case.c.subject_id.in_(version_ids),
        )
    ).all()
    for subject_id, result, run_at in rows:
        entry = evidence[UUID(str(subject_id))]
        entry["total"] += 1
        key = {CASE_PASS: "passed", CASE_FAIL: "failed"}.get(result, "not_run")
        entry[key] += 1
        if run_at is not None and (entry["last_run_at"] is None or run_at > entry["last_run_at"]):
            entry["last_run_at"] = run_at
    return evidence


def lock_version(session: Session, version_id: UUID) -> Mapping[str, Any]:
    """The ``pob_template_version`` row under ``FOR UPDATE``; 404 when it is not visible."""
    return lifecycle.lock(session, POB_TEMPLATE_VERSION_KIND, version_id)


def template_code_of(session: Session, template_id: UUID) -> str:
    return str(
        session.execute(
            select(pob_template.c.code).where(pob_template.c.id == template_id)
        ).scalar_one()
    )


def run_test_cases(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /pob-template-versions/{id}/test``: run every example case (REQ-POL-003; RFD-10).

    409 ``invalid-transition`` unless the version is DRAFT or TESTED; 422 without example cases.
    Each case records its result. When every case passes, a DRAFT version becomes TESTED with its
    content hash; otherwise it stays as it is. The audit detail carries each case's drafts and
    findings.
    """
    session = uow.session
    version = lock_version(session, version_id)
    if version["status"] not in lifecycle.EDITABLE:
        raise lifecycle.refused(NOT_TESTABLE)
    template_code = template_code_of(session, UUID(str(version["pob_template_id"])))
    cases = (
        session.execute(
            select(rule_test_case)
            .where(
                rule_test_case.c.subject_type == SUBJECT_TYPE,
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
                ProblemError(field="test_cases", rule_id=RULE_EVIDENCE, message=CASES_REQUIRED)
            ],
        )
    principal = uow.principal
    results: list[dict[str, Any]] = []
    for case in cases:
        result, actual = run_case(session, version, template_code, dict(case), known_at=uow.now)
        session.execute(
            update(rule_test_case)
            .where(rule_test_case.c.id == case["id"])
            .values(
                last_result=result,
                last_run_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
        results.append(
            {"test_case_id": case["id"], "name": case["name"], "result": result, "actual": actual}
        )
    passed = sum(1 for item in results if item["result"] == CASE_PASS)
    detail = {"passed": passed, "failed": len(results) - passed, "cases": results}
    record_facts(
        uow,
        action=RUN_CASES_ACTION,
        object_type=OBJECT_TEST_CASE,
        ids=[UUID(str(case["id"])) for case in cases],
        detail={"subject_type": SUBJECT_TYPE, "subject_id": str(version_id)},
    )
    if passed == len(results):
        lifecycle.mark_tested(
            uow,
            POB_TEMPLATE_VERSION_KIND,
            version,
            content_sha256=lifecycle.current_sha256(session, POB_TEMPLATE_VERSION_KIND, version_id),
            detail=detail,
        )
        return
    uow.audit(
        action=TEST_ACTION,
        object_type=OBJECT_VERSION,
        object_id=version_id,
        after={"status": version["status"]},
        detail=detail,
    )


# --- read models (04 §16.2 API-S-VersionSummary, §16.14 list additions) -----------------------


type Summary = dict[str, Any]


def version_summaries(
    session: Session, template_ids: Sequence[UUID]
) -> dict[UUID, tuple[Summary | None, Summary | None]]:
    """For each template, API-S-VersionSummary of ``current_version`` (the latest PUBLISHED
    version) and ``latest_version`` (the highest ``version_no``); ``rule_count`` and
    ``lint_status`` are null for template versions (04 §16.2)."""
    if not template_ids:
        return {}
    rows = (
        session.execute(
            select(
                pob_template_version.c.id,
                pob_template_version.c.pob_template_id,
                pob_template_version.c.version_no,
                pob_template_version.c.status,
                pob_template_version.c.effective_from,
                pob_template_version.c.published_at,
            )
            .where(pob_template_version.c.pob_template_id.in_(template_ids))
            .order_by(pob_template_version.c.pob_template_id, pob_template_version.c.version_no)
        )
        .mappings()
        .all()
    )
    current: dict[UUID, Summary] = {}
    latest: dict[UUID, Summary] = {}
    for row in rows:  # ascending version_no: later versions replace earlier ones
        summary: Summary = {
            "id": row["id"],
            "version_no": row["version_no"],
            "status": row["status"],
            "effective_from": row["effective_from"],
            "published_at": row["published_at"],
            "rule_count": None,
            "lint_status": None,
        }
        template_id = UUID(str(row["pob_template_id"]))
        latest[template_id] = summary
        if row["status"] == ConfigStatus.PUBLISHED.value:
            current[template_id] = summary
    return {tid: (current.get(tid), latest.get(tid)) for tid in template_ids}


def template_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-PobTemplate of each ``pob_template`` row with its version summaries."""
    summaries = version_summaries(session, [UUID(str(row["id"])) for row in rows])
    outs: list[dict[str, Any]] = []
    for row in rows:
        current, latest = summaries.get(UUID(str(row["id"])), (None, None))
        outs.append(
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "description": row["description"],
                "current_version": current,
                "latest_version": latest,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "row_version": row["row_version"],
            }
        )
    return outs


def version_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-PobTemplateVersion of each ``pob_template_version`` row: the T-REF-23 and SC-V columns
    with the template code, test evidence and pending approval request (L2-1-Q-43)."""
    if not rows:
        return []
    codes = {
        UUID(str(template_id)): str(code)
        for template_id, code in session.execute(
            select(pob_template.c.id, pob_template.c.code).where(
                pob_template.c.id.in_({row["pob_template_id"] for row in rows})
            )
        ).tuples()
    }
    ids = [UUID(str(row["id"])) for row in rows]
    evidence = case_evidence(session, ids)
    pending = {
        UUID(str(subject_id)): request_id
        for subject_id, request_id in session.execute(
            select(approval_request.c.subject_id, approval_request.c.id).where(
                approval_request.c.subject_type == ApprovalSubjectType.POB_TEMPLATE_VERSION.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.subject_id.in_(ids),
            )
        ).tuples()
    }
    outs: list[dict[str, Any]] = []
    for row in rows:
        version_id = UUID(str(row["id"]))
        outs.append(
            {
                "id": row["id"],
                "pob_template_id": row["pob_template_id"],
                "template_code": codes[UUID(str(row["pob_template_id"]))],
                "version_no": row["version_no"],
                "status": row["status"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "content_sha256": row["content_sha256"],
                "approval_request_id": row["approval_request_id"],
                "pending_approval_request_id": pending.get(version_id),
                "published_at": row["published_at"],
                "published_by": row["published_by"],
                "supersedes_version_id": row["supersedes_version_id"],
                **{name: row[name] for name in OUTPUT_COLUMNS},
                "test_evidence": evidence[version_id],
                "created_at": row["created_at"],
                "created_by": row["created_by"],
                "updated_at": row["updated_at"],
                "row_version": row["row_version"],
            }
        )
    return outs


# --- resolution for booking lines (S03-R-02; CTL-031) ------------------------------------------

_IN_FORCE: Final = (ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value)


def _utc_date(value: datetime) -> date:
    return value.astimezone(UTC).date()


def template_inputs(
    session: Session, *, known_at: datetime, codes: Collection[str] | None = None
) -> tuple[TemplateInput, ...]:
    """The PUBLISHED and SUPERSEDED versions published at or before ``known_at`` as engine inputs,
    ordered (template code, version number) (ENGINE_SPEC §0.4).

    [J] A version is effective from the UTC date of ``effective_from``, or of ``published_at`` when
    that is null, to the UTC date of ``effective_to`` (exclusive) (L2-1-Q-47).
    """
    statement = (
        select(pob_template.c.code.label("template_code"), pob_template_version)
        .select_from(
            pob_template_version.join(
                pob_template,
                and_(
                    pob_template.c.tenant_id == pob_template_version.c.tenant_id,
                    pob_template.c.id == pob_template_version.c.pob_template_id,
                ),
            )
        )
        .where(
            pob_template_version.c.status.in_(_IN_FORCE),
            pob_template_version.c.published_at <= known_at,
        )
        .order_by(pob_template.c.code, pob_template_version.c.version_no)
    )
    if codes is not None:
        statement = statement.where(pob_template.c.code.in_(sorted(codes)))
    inputs: list[TemplateInput] = []
    for row in session.execute(statement).mappings():
        starts = row["effective_from"] or row["published_at"]
        base = _template_input(
            dict(row), str(row["template_code"]), effective_from=_utc_date(starts)
        )
        ends = row["effective_to"]
        inputs.append(
            TemplateInput(
                **{
                    **{name: getattr(base, name) for name in TemplateInput.__dataclass_fields__},
                    "effective_to": None if ends is None else _utc_date(ends),
                }
            )
        )
    return tuple(inputs)


def resolve_template_version(
    session: Session, code: str, *, at: date, known_at: datetime
) -> TemplateInput | None:
    """The version of template ``code`` that stage 03 pins for a line at ``at``: the greatest
    version whose ``[effective_from, effective_to)`` holds ``at`` (S03-R-02)."""
    eligible = [
        version
        for version in template_inputs(session, known_at=known_at, codes=[code])
        if version.effective_from <= at
        and (version.effective_to is None or at < version.effective_to)
    ]
    return max(eligible, key=lambda version: version.version_no, default=None)


def has_published_version(session: Session, template_id: UUID) -> bool:
    """Whether the template has a PUBLISHED version (``product.default_pob_template_id``)."""
    found = session.execute(
        select(func.count())
        .select_from(pob_template_version)
        .where(
            pob_template_version.c.pob_template_id == template_id,
            pob_template_version.c.status == ConfigStatus.PUBLISHED.value,
        )
    ).scalar_one()
    return int(found) > 0


# --- the configuration lifecycle of template versions (RFD-5 primitives) -----------------------


def _submit_errors(session: Session, version: Mapping[str, Any]) -> list[ProblemError]:
    evidence = case_evidence(session, [UUID(str(version["id"]))])[UUID(str(version["id"]))]
    if evidence["total"] > 0 and evidence["passed"] == evidence["total"]:
        return []
    return [ProblemError(field="status", rule_id=RULE_EVIDENCE, message=EVIDENCE_INCOMPLETE)]


def _publish_errors(_session: Session, _version: Mapping[str, Any]) -> list[ProblemError]:
    return []


def _snapshot(session: Session, version_id: UUID) -> dict[str, Any]:
    """The field-level ``before`` and ``after`` of publication audits: the outputs."""
    return {"outputs": subjects.pob_template_version_content(session, version_id)["outputs"]}


def _summary(session: Session, version: Mapping[str, Any]) -> str:
    code = template_code_of(session, UUID(str(version["pob_template_id"])))
    return f"Publish version {version['version_no']} of obligation template {code}"


def _chosen_by(_version: Mapping[str, Any]) -> str:
    """The engine chooses a template version by the contract's inception or the line's pricing
    date (ENGINE_SPEC S03-R-02), so a superseding version is dated ahead (PRD ERR-75)."""
    return lifecycle.BY_DATE


POB_TEMPLATE_VERSION_KIND: Final = lifecycle.ConfigVersionKind(
    table=pob_template_version,
    subject_type=ApprovalSubjectType.POB_TEMPLATE_VERSION,
    scope_columns=("pob_template_id",),
    content=subjects.pob_template_version_content,
    snapshot=_snapshot,
    submit_errors=_submit_errors,
    publish_errors=_publish_errors,
    summary=_summary,
    chosen_by=_chosen_by,
)


def _on_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.approve(uow, POB_TEMPLATE_VERSION_KIND, subject_id, approval_request_id)


def _on_rejected(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(
        uow,
        POB_TEMPLATE_VERSION_KIND,
        subject_id,
        approval_request_id,
        to_status=ConfigStatus.REJECTED,
    )


def _on_voided(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(
        uow,
        POB_TEMPLATE_VERSION_KIND,
        subject_id,
        approval_request_id,
        to_status=ConfigStatus.WITHDRAWN,
    )


subjects.register_lifecycle(
    ApprovalSubjectType.POB_TEMPLATE_VERSION,
    subjects.SubjectLifecycle(
        on_approved=_on_approved, on_rejected=_on_rejected, on_voided=_on_voided
    ),
)

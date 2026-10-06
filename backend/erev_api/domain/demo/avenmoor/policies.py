"""Avenmoor revenue policy templates, tenant policy versions and approval rule sets (PRD §2.5
settings and routing table; §2.6 templates; BUILD_SPEC RFD-16).

``maya`` (Revenue Accountant, ``config.author``) prepares every version and ``marcus`` (Controller,
``config.approve``) approves it:

1. the nine PUBLISHED templates of §2.6, each with one passing example case, then the products'
   default templates;
2. the TENANT versions holding ``billing.posting``, ``je.posting_mode``, ``je.summarization``,
   ``ui.negative_number_style`` and ``data.quarantine_failed_rows``, and one ENTITY version per
   entity with ``entity.reporting_type = PBE`` (POL-190 allows the ENTITY level only);
3. rule set ``APPROVAL_ROUTING`` version 1 with a rule for every subject row of the §2.5 routing
   table, and rule set ``AUTO_APPROVAL`` version 1 with ``AUTO-CON-01`` and ``AUTO-IMP-01``.

The ``ACCOUNTING_POLICY`` version and the ``DISCLOSURE_ELECTION`` versions are period-scoped (pin
P), so they take effect at the first day of a future period (``next_period_start``). The
``PLATFORM`` and ``INTEGRATION`` versions hold workspace settings and name no date: a version of a
settings category takes effect when it is approved (04 §16.5 "Order of effective instants";
``registry_versions.INSTANT_CATEGORIES``; the supervisor's ruling of 2026-10-01 on item
CFG-PLATFORM-PIN-1) — dated at the next period start they kept every later change of a workspace
setting waiting for that day (PRD ERR-81). The routing rule sets are published last, so the earlier
approvals of the seed take the single-step fallback of DG-KRN-APR-01.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import product
from erev_api.domain.demo.avenmoor import (
    ACCOUNTANT,
    CONTROLLER,
    GO_LIVE,
    expect_version,
    next_period_start,
)
from erev_api.domain.demo.avenmoor import reference as avenmoor_reference
from erev_api.domain.policies import commands, lifecycle, registry_versions
from erev_api.domain.policies import rule_sets as rule_set_rules
from erev_api.domain.policies import templates as template_rules
from erev_api.domain.reference import commands as reference_commands
from erev_api.enums import ApprovalSubjectType, RegistryCategory, RegistryScope, RuleSetKind
from erev_api.schemas.pob_templates import PobTemplateVersionIn

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

CONFIG_AUTHOR: Final = "config.author"
MASTERDATA_MAINTAIN: Final = "masterdata.maintain"
SUBMIT_COMMENT: Final = "Ready for review."
_VERSION_MEMBERS: Final = frozenset({"effective_from", "source_version_id"})

# --- revenue policy templates (PRD §2.6, REQ-POL-001) --------------------------------------------

_OVER_TIME_A: Final = {"satisfaction_pattern": "OVER_TIME", "over_time_criterion": "OT_A"}
_POINT_IN_TIME: Final = {
    "satisfaction_pattern": "POINT_IN_TIME",
    "over_time_criterion": "NOT_APPLICABLE",
}


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    code: str
    name: str
    outputs: Mapping[str, Any]
    case_currency: str
    case_line: Mapping[str, Any]  # one example line; obligation key POB-01


TEMPLATES: Final[tuple[TemplateSpec, ...]] = (
    TemplateSpec(
        "TPL-SUB-DAILY",
        "Subscription, daily over time",
        {
            "distinctness": "series",
            "series_increment_unit": "day",
            **_OVER_TIME_A,
            "recognition_method": "TIME_ELAPSED",
            "ratable_convention": "DAILY",
        },
        "USD",
        {
            "product_code": "AVM-PLAT-ENT",
            "total_price": "120000.00",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    ),
    TemplateSpec(
        "TPL-SVC-PCT",
        "Services, output percent",
        {"distinctness": "distinct", **_OVER_TIME_A, "recognition_method": "OUTPUT_PERCENT"},
        "USD",
        {"product_code": "AVM-IMPL-STD", "total_price": "15000.00"},
    ),
    TemplateSpec(
        "TPL-SVC-HOURS",
        "Services, labour hours",
        {"distinctness": "distinct", **_OVER_TIME_A, "recognition_method": "LABOUR_HOURS"},
        "USD",
        {"product_code": "AVM-IMPL-PLUS", "total_price": "20000.00"},
    ),
    TemplateSpec(
        "TPL-USAGE",
        "Usage series",
        {
            "distinctness": "series",
            "series_increment_unit": "transaction",
            **_OVER_TIME_A,
            "recognition_method": "USAGE",
        },
        "USD",
        {
            "product_code": "AVM-API-CALL",
            "total_price": "25000.00",
            "quantity": "250000",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    ),
    TemplateSpec(
        "TPL-ENG-C2C",
        "Engineering project, cost to cost",
        {
            "distinctness": "distinct",
            "satisfaction_pattern": "OVER_TIME",
            "over_time_criterion": "OT_B",
            "recognition_method": "COST_TO_COST",
        },
        "USD",
        {"product_code": "AVM-ENG-BUILD", "total_price": "1000000.00"},
    ),
    TemplateSpec(
        "TPL-PROD-PIT",
        "Product, point in time on delivery",
        {"distinctness": "distinct", **_POINT_IN_TIME, "recognition_method": "POINT_IN_TIME"},
        "EUR",
        {"product_code": "AVM-KIT", "total_price": "10000.00", "quantity": "100"},
    ),
    TemplateSpec(
        "TPL-PROD-UNITS",
        "Product, units delivered",
        {"distinctness": "distinct", **_POINT_IN_TIME, "recognition_method": "UNITS_DELIVERED"},
        "EUR",
        {"product_code": "AVM-GW", "total_price": "90000.00", "quantity": "200"},
    ),
    TemplateSpec(
        "TPL-OPTION",
        "Customer option, material right",
        {
            "obligation_kind": "MATERIAL_RIGHT",
            "distinctness": "distinct",
            **_POINT_IN_TIME,
            "recognition_method": "POINT_IN_TIME",
        },
        "EUR",
        {"product_code": "AVM-EXP-CREDIT", "total_price": "12000.00"},
    ),
    TemplateSpec(
        "TPL-LIC-FUNC",
        "Functional IP licence",
        {
            "obligation_kind": "LICENCE",
            "licence_nature": "FUNCTIONAL",
            "distinctness": "distinct",
            **_POINT_IN_TIME,
            "recognition_method": "POINT_IN_TIME",
            "start_date_rule": "LICENCE_START_OR_AVAILABLE",
        },
        "JPY",
        {
            "product_code": "AVM-LIB-LIC",
            "total_price": "50000000",
            "start_date": "2026-04-01",
            "end_date": "2029-03-31",
        },
    ),
)
CASE_KEY: Final = "POB-01"

# --- tenant policy versions (PRD §2.5 settings) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicySpec:
    category: RegistryCategory
    scope: RegistryScope
    entity_code: str | None
    values: Mapping[str, Any]


TENANT_POLICIES: Final[tuple[PolicySpec, ...]] = (
    PolicySpec(
        RegistryCategory.ACCOUNTING_POLICY,
        RegistryScope.TENANT,
        None,
        {
            "billing.posting": "ERP",
            "je.posting_mode": "GROSS",
            "je.summarization": "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
        },
    ),
    PolicySpec(
        RegistryCategory.PLATFORM,
        RegistryScope.TENANT,
        None,
        {"ui.negative_number_style": "PARENTHESES"},
    ),
    PolicySpec(
        RegistryCategory.INTEGRATION,
        RegistryScope.TENANT,
        None,
        {"data.quarantine_failed_rows": False},
    ),
)
REPORTING_TYPE: Final = "PBE"


def entity_policies() -> tuple[PolicySpec, ...]:
    return tuple(
        PolicySpec(
            RegistryCategory.DISCLOSURE_ELECTION,
            RegistryScope.ENTITY,
            code,
            {registry_versions.REPORTING_TYPE: REPORTING_TYPE},
        )
        for code in avenmoor_reference.entity_codes()
    )


# --- approval routing and auto-approval (PRD §2.5 routing table) ---------------------------------

APPROVAL_ROUTING: Final = "APPROVAL_ROUTING"  # [J] L4-5-Q-5: the rule set codes are the kind names
AUTO_APPROVAL: Final = "AUTO_APPROVAL"
_S = ApprovalSubjectType


@dataclass(frozen=True, slots=True)
class RoutingRule:
    rule_key: str
    subjects: tuple[ApprovalSubjectType, ...]
    # (name, permission, min_approvers), or (name, permission, min_approvers, role code)
    steps: tuple[tuple[str, str, int] | tuple[str, str, int, str], ...]
    description: str
    extra: tuple[Mapping[str, Any], ...] = ()
    case_facts: Mapping[str, Any] = field(default_factory=dict)


def _one(name: str, permission: str, approvers: int = 1) -> tuple[tuple[str, str, int], ...]:
    return ((name, permission, approvers),)


def _two(first: str, permission: str) -> tuple[tuple[str, str, int], ...]:
    return ((first, permission, 1), ("Controller approval", permission, 1))


def _two_controller(
    first: str, permission: str
) -> tuple[tuple[str, str, int] | tuple[str, str, int, str], ...]:
    """A second step held by a Controller: the step carries the ``controller`` role reference
    (04 T-REF-26 ``role``; D-98 93), so the matched rule enforces it like the fallback does."""
    return ((first, permission, 1), ("Controller approval", permission, 1, "controller"))


def _amount(op: str, value: str) -> Mapping[str, Any]:
    return {"field": "amount.functional", "op": op, "value": value}


# [J] L4-5-Q-6: the routing fields are subject.type, entity.code, amount.functional and flags
# (BS1-D-05). "Held by a Controller" is the step name only, "absolute" amounts take a gte and an
# lte rule, and origin conditions (manual, AI-assisted) have no field.
# D-98 93 (F-CTR-VOID-2): ROUTE-VOID-02's Controller step carries the role reference (T-REF-26
# "role", parsed into T-PLT-18 required_role_id), and so do the one step of ROUTE-LCK-01
# (supervisor ruling R-41 (7)) and the one step of ROUTE-SHRED-01 (ruling R-49 (a): "one step, the
# Controller role") — the step role of their subjects, which a rule may not lower; the other
# "Controller approval" steps keep the [J] shortcut until their owning lanes adopt the member.
ROUTING_RULES: Final[tuple[RoutingRule, ...]] = (
    RoutingRule(
        "ROUTE-CON-01",
        (_S.CONTRACT_ACTIVATION,),
        _one("Revenue review", "contract.approve"),
        "Contract activation: one Revenue Reviewer.",
        case_facts={"amount.functional": "250000.00"},
    ),
    RoutingRule(
        "ROUTE-CON-02",
        (_S.CONTRACT_ACTIVATION,),
        _two("Revenue review", "contract.approve"),
        "Contract activation at TP of USD 1,000,000.00 or more: a Controller second.",
        extra=(_amount("gte", "1000000.00"),),
        case_facts={"amount.functional": "1000000.00"},
    ),
    RoutingRule(
        "ROUTE-MOD-01",
        (_S.MODIFICATION,),
        _one("Revenue review", "modification.approve"),
        "Modification: one Revenue Reviewer.",
        case_facts={"amount.functional": "1000.00"},
    ),
    RoutingRule(
        "ROUTE-MOD-02",
        (_S.MODIFICATION,),
        _two("Revenue review", "modification.approve"),
        "Modification with a catch-up of USD 50,000.00 or more: a Controller second.",
        extra=(_amount("gte", "50000.00"),),
        case_facts={"amount.functional": "50000.00"},
    ),
    RoutingRule(
        "ROUTE-MOD-03",
        (_S.MODIFICATION,),
        _two("Revenue review", "modification.approve"),
        "Modification with a catch-up of USD -50,000.00 or less: a Controller second.",
        extra=(_amount("lte", "-50000.00"),),
        case_facts={"amount.functional": "-50000.00"},
    ),
    RoutingRule(
        "ROUTE-EST-01",
        (_S.ESTIMATE_VERSION,),
        _one("Revenue review", "estimate.approve"),
        "Estimate version: one Revenue Reviewer.",
        case_facts={"amount.functional": "1000.00"},
    ),
    RoutingRule(
        "ROUTE-EST-02",
        (_S.ESTIMATE_VERSION,),
        _two("Revenue review", "estimate.approve"),
        "Estimate version with a P&L impact of USD 50,000.00 or more: a Controller second.",
        extra=(_amount("gte", "50000.00"),),
        case_facts={"amount.functional": "50000.00"},
    ),
    RoutingRule(
        "ROUTE-EST-03",
        (_S.ESTIMATE_VERSION,),
        _two("Revenue review", "estimate.approve"),
        "Estimate version with a P&L impact of USD -50,000.00 or less: a Controller second.",
        extra=(_amount("lte", "-50000.00"),),
        case_facts={"amount.functional": "-50000.00"},
    ),
    RoutingRule(
        "ROUTE-EVT-01",
        (_S.MANUAL_EVENT,),
        _one("Event review", "event.approve"),
        "Manual event: one approver.",
    ),
    RoutingRule(
        "ROUTE-JDG-01",
        (_S.JUDGEMENT_RECORD,),
        _one("Judgement review", "judgement.review"),
        "Judgement record: one reviewer.",
    ),
    RoutingRule(
        "ROUTE-CMB-01",
        (_S.COMBINATION_GROUP,),
        _one("Combination review", "contract.approve"),
        "Combination group: one approver.",
    ),
    RoutingRule(
        "ROUTE-SSPO-01",
        (_S.SSP_OVERRIDE,),
        _one("SSP override review", "ssp.approve"),
        "SSP override: one SSP Approver.",
    ),
    RoutingRule(
        "ROUTE-ADJ-01",
        (_S.MANUAL_ADJUSTMENT,),
        _one("Adjustment review", "adjustment.approve"),
        "Manual adjustment under USD 10,000.00: one approver.",
        case_facts={"amount.functional": "9999.99"},
    ),
    RoutingRule(
        "ROUTE-ADJ-02",
        (_S.MANUAL_ADJUSTMENT,),
        _two("Revenue review", "adjustment.approve"),
        "Manual adjustment of USD 10,000.00 or more: a Controller second.",
        extra=(_amount("gte", "10000.00"),),
        case_facts={"amount.functional": "10000.00"},
    ),
    RoutingRule(
        "ROUTE-ADJ-03",
        (_S.MANUAL_ADJUSTMENT,),
        _two("Revenue review", "adjustment.approve"),
        "Manual adjustment of USD -10,000.00 or less: a Controller second.",
        extra=(_amount("lte", "-10000.00"),),
        case_facts={"amount.functional": "-10000.00"},
    ),
    RoutingRule(
        "ROUTE-IMP-01",
        (_S.IMPORT_COMMIT,),
        _one("Import review", "import.approve"),
        "Import commit uploaded by a user: one approver.",
    ),
    RoutingRule(
        "ROUTE-SSP-01",
        (_S.SSP_BOOK_VERSION,),
        _one("SSP review", "ssp.approve"),
        "SSP book version: one SSP Approver.",
    ),
    RoutingRule(
        "ROUTE-SSP-02",
        (_S.SSP_BOOK_VERSION,),
        (("SSP review", "ssp.approve", 1), ("Second SSP review", "ssp.approve", 1)),
        "SSP book version changing a method or a mid value by more than 10%: a second approver.",
        extra=({"field": "flags", "op": "in", "value": ["ABOVE_THRESHOLD", "METHODOLOGY_CHANGE"]},),
        case_facts={"flags": ["ABOVE_THRESHOLD"]},
    ),
    RoutingRule(
        "ROUTE-CFG-01",
        (
            _S.REGISTRY_VERSION,
            _S.RULE_SET_VERSION,
            _S.POB_TEMPLATE_VERSION,
            _S.ACCOUNT_MAPPING_VERSION,
            _S.FX_RATE_SET_VERSION,
            _S.PRINCIPAL_AGENT_CHANGE,
            _S.MAPPING_PROFILE_VERSION,
        ),
        _one("Configuration review", "config.approve"),
        "Configuration versions: one Controller.",
    ),
    RoutingRule(
        "ROUTE-OVR-01",
        (_S.POLICY_OVERRIDE,),
        _one("Revenue review", "contract.approve"),
        "Contract- or obligation-level policy override: one Revenue Reviewer.",
    ),
    RoutingRule(
        "ROUTE-ATR-01",
        (_S.ATTRIBUTE_CHANGE,),
        _one("Revenue review", "event.approve"),
        "Change of accounts, entity or SSP version pin: one Revenue Reviewer.",
    ),
    RoutingRule(
        "ROUTE-AIP-01",
        (_S.AI_PROPOSAL_ACCEPTANCE,),
        _one("Revenue review", "contract.approve"),
        "Accepted AI proposal fields: one Revenue Reviewer.",
    ),
    RoutingRule(
        "ROUTE-EXW-01",
        (_S.EXCEPTION_WAIVER,),
        _one("Waiver review", "exception.waive"),
        "Exception waiver: one approver other than the requester and the owner.",
    ),
    RoutingRule(
        "ROUTE-JRN-01",
        (_S.JOURNAL_RUN,),
        _one("Journal review", "journal.approve"),
        "Journal run: one approver.",
    ),
    RoutingRule(
        "ROUTE-LCK-01",
        (_S.PERIOD_LOCK,),
        # PRD §2.5 "1: period.lock (Controller)": the step carries the role reference, as the
        # subject's own step does (04 §16.10 rev 1.104; supervisor ruling R-41 (7)).
        (("Controller approval", "period.lock", 1, "controller"),),
        "Period lock or permanent lock: one Controller.",
    ),
    RoutingRule(
        "ROUTE-RPN-01",
        (_S.PERIOD_REOPEN,),
        _one("Reopen approval", "period.reopen_approve", 2),
        "Period reopen: two approvers, at least one Controller.",
    ),
    RoutingRule(
        "ROUTE-MIG-01",
        (_S.MIGRATION_PROMOTION,),
        _one("Controller approval", "migration.approve"),
        "Migration promotion: one Controller other than the runner.",
    ),
    RoutingRule(
        "ROUTE-VOID-01",
        (_S.CONTRACT_VOID,),
        _one("Revenue review", "contract.approve"),
        "Contract void without posted lines: one Revenue Reviewer.",
    ),
    RoutingRule(
        "ROUTE-VOID-02",
        (_S.CONTRACT_VOID,),
        _two_controller("Revenue review", "contract.approve"),
        "Contract void with posted lines: a Controller second.",
        extra=({"field": "flags", "op": "eq", "value": "POSTED_LINES"},),
        case_facts={"flags": ["POSTED_LINES"]},
    ),
    RoutingRule(
        "ROUTE-ACC-01",
        (_S.ROLE_ASSIGNMENT, _S.ROLE_CHANGE, _S.SOD_EXCEPTION),
        _one("Access review", "access.approve"),
        "Access changes: one Tenant Admin other than the requester.",
    ),
    RoutingRule(
        "ROUTE-SUP-01",
        (_S.SUPPORT_GRANT,),
        _one("Support grant review", "support_grant.approve"),
        "Provider support grant: one Tenant Admin other than the requester.",
    ),
    RoutingRule(
        "ROUTE-SHRED-01",
        (_S.EVIDENCE_SHRED,),
        (("Controller approval", "config.approve", 1, "controller"),),
        "Shredding a file that a record holds as its evidence: one Controller.",
    ),
)


@dataclass(frozen=True, slots=True)
class AutoRule:
    rule_key: str
    subject: ApprovalSubjectType
    source_channel: str
    description: str


# [J] L4-5-Q-7: the auto-approval fields (BS1-D-05) name no amount, flag or control-total fact.
AUTO_RULES: Final[tuple[AutoRule, ...]] = (
    AutoRule(
        "AUTO-CON-01",
        _S.CONTRACT_ACTIVATION,
        "API_CLIENT",
        "Contract activation originated by an API client such as svc-salesforce.",
    ),
    AutoRule(
        "AUTO-IMP-01",
        _S.IMPORT_COMMIT,
        "API_CLIENT",
        "Import commit uploaded by an API client.",
    ),
    # ``AUTO-MIG-01`` is not a rule of this set: the legacy SSP replay is approved only by the rule
    # set provisioning seeds for every tenant — this one too (04 §14.3 item 2; supervisor ruling
    # R-41 (7)) — and a tenant's own rule that names ``MIGRATION_SSP_REPLAY`` is refused.
)


def routing_conditions(rule: RoutingRule) -> list[Mapping[str, Any]]:
    subject: Mapping[str, Any] = (
        {"field": "subject.type", "op": "eq", "value": rule.subjects[0].value}
        if len(rule.subjects) == 1
        else {"field": "subject.type", "op": "in", "value": [s.value for s in rule.subjects]}
    )
    return [subject, *rule.extra]


def routing_outputs(rule: RoutingRule) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step in rule.steps:
        name, permission, approvers = step[0], step[1], step[2]
        item: dict[str, Any] = {"name": name, "permission": permission, "min_approvers": approvers}
        if len(step) == 4:
            item["role"] = step[3]  # 04 T-REF-26 ``role`` (D-98 93)
        steps.append(item)
    return {"steps": steps}


def auto_conditions(rule: AutoRule) -> list[Mapping[str, Any]]:
    return [
        {"field": "subject.type", "op": "eq", "value": rule.subject.value},
        {"field": "source.channel", "op": "eq", "value": rule.source_channel},
    ]


# --- builder -------------------------------------------------------------------------------------


def _midnight_go_live() -> datetime:
    return datetime(GO_LIVE.year, GO_LIVE.month, GO_LIVE.day, tzinfo=UTC)


def _template(ctx: BuildContext, spec: TemplateSpec) -> UUID:
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        template_id = commands.create_pob_template(
            uow, code=spec.code, name=spec.name, description=None
        )
    body = PobTemplateVersionIn.model_validate(
        {**spec.outputs, "effective_from": _midnight_go_live()}
    )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        version_id = commands.create_pob_template_version(
            uow,
            template_id,
            changes=body.model_dump(exclude_unset=True, exclude=set(_VERSION_MEMBERS)),
            effective_from=body.effective_from,
            source_version_id=None,
        )
    line = {**spec.case_line, "obligation_key": CASE_KEY}
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.create_config_test_case(
            uow,
            subject_type=template_rules.SUBJECT_TYPE,
            subject_id=version_id,
            name=f"{spec.case_line['product_code']} booking",
            facts={
                "booking_date": GO_LIVE.isoformat(),
                "currency": spec.case_currency,
                "lines": [line],
            },
            expected_output={"drafts": [{"obligation_key": CASE_KEY}]},
        )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.run_pob_template_version_tests(uow, version_id)
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.submit_pob_template_version(uow, version_id, comment=SUBMIT_COMMENT)
    ctx.approve(ApprovalSubjectType.POB_TEMPLATE_VERSION, version_id, [CONTROLLER])
    return template_id


def _default_templates(ctx: BuildContext, template_ids: Mapping[str, UUID]) -> None:
    for spec in avenmoor_reference.PRODUCTS:
        if spec.template_code is None:
            continue
        with ctx.read() as session:
            found = session.execute(
                select(product.c.id, product.c.row_version).where(product.c.code == spec.code)
            ).one()
        with ctx.command(ACCOUNTANT, MASTERDATA_MAINTAIN) as uow:
            reference_commands.update_product(
                uow,
                product_id=UUID(str(found.id)),
                changes={"default_pob_template_id": template_ids[spec.template_code]},
                check_version=expect_version(int(found.row_version)),
            )


def _policy(ctx: BuildContext, spec: PolicySpec, effective_from: datetime | None) -> UUID:
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        version_id = registry_versions.create_policy(
            uow,
            category=spec.category,
            scope=spec.scope,
            entity_code=spec.entity_code,
            book_code=None,
            values=dict(spec.values),
            effective_from=effective_from,
        )
    # [J] L4-5-Q-8: the seed runs the POLICY_SIMULATION runner inline as the preparer, as the worker
    # would, instead of deferring a job that no worker runs during make seed.
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        digest = lifecycle.current_sha256(uow.session, registry_versions.KIND, version_id)
        registry_versions.run_test(
            uow,
            version_id,
            {
                "subject_type": registry_versions.SUBJECT_TYPE,
                "subject_id": str(version_id),
                "run_simulation": True,
                "content_sha256": digest,
            },
        )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        registry_versions.submit_policy(uow, version_id, comment=SUBMIT_COMMENT)
    ctx.approve(ApprovalSubjectType.REGISTRY_VERSION, version_id, [CONTROLLER])
    return version_id


def _rule_set(
    ctx: BuildContext,
    code: str,
    kind: RuleSetKind,
    name: str,
    rules: Sequence[tuple[str, list[Mapping[str, Any]], dict[str, Any], str]],
    cases: Sequence[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
) -> UUID:
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        rule_set_id = commands.create_rule_set(
            uow, code=code, kind=kind, name=name, description=None
        )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        version_id = commands.create_rule_set_version(
            uow, rule_set_id, effective_from=_midnight_go_live(), source_version_id=None
        )
    for rule_key, conditions, outputs, description in rules:
        with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
            commands.upsert_rule(
                uow,
                version_id,
                rule_key=rule_key,
                priority=0,
                conditions=conditions,
                outputs=outputs,
                description=description,
            )
    for case_name, facts, expected in cases:
        with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
            commands.create_config_test_case(
                uow,
                subject_type=rule_set_rules.SUBJECT_TYPE,
                subject_id=version_id,
                name=case_name,
                facts=facts,
                expected_output=expected,
            )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.run_rule_set_version_tests(uow, version_id)
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.submit_rule_set_version(uow, version_id, comment=SUBMIT_COMMENT)
    ctx.approve(ApprovalSubjectType.RULE_SET_VERSION, version_id, [CONTROLLER])
    return version_id


def _routing(ctx: BuildContext) -> None:
    rules = [
        (rule.rule_key, routing_conditions(rule), routing_outputs(rule), rule.description)
        for rule in ROUTING_RULES
    ]
    cases = [
        (
            f"{rule.rule_key} {rule.subjects[0].value}",
            {"subject.type": rule.subjects[0].value, **rule.case_facts},
            {"rule_key": rule.rule_key},
        )
        for rule in ROUTING_RULES
    ]
    _rule_set(ctx, APPROVAL_ROUTING, RuleSetKind.APPROVAL_ROUTING, "Approval routing", rules, cases)
    auto = [
        (rule.rule_key, auto_conditions(rule), {"auto_approve": True}, rule.description)
        for rule in AUTO_RULES
    ]
    auto_cases: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = [
        (
            f"{rule.rule_key} {rule.subject.value}",
            {"subject.type": rule.subject.value, "source.channel": rule.source_channel},
            {"rule_key": rule.rule_key},
        )
        for rule in AUTO_RULES
    ]
    auto_cases.append(
        (
            "Activation prepared by a user",
            {"subject.type": _S.CONTRACT_ACTIVATION.value, "source.channel": "USER"},
            {"matched": False},
        )
    )
    _rule_set(ctx, AUTO_APPROVAL, RuleSetKind.AUTO_APPROVAL, "Auto-approval", auto, auto_cases)


def build(ctx: BuildContext) -> None:
    """PRD §2.5 and §2.6 policies of WLD-T-01 (module docstring order)."""
    template_ids = {spec.code: _template(ctx, spec) for spec in TEMPLATES}
    _default_templates(ctx, template_ids)
    effective_from = next_period_start(ctx.clock.now())
    for spec in (*TENANT_POLICIES, *entity_policies()):
        dated = spec.category not in registry_versions.INSTANT_CATEGORIES
        _policy(ctx, spec, effective_from if dated else None)
    _routing(ctx)

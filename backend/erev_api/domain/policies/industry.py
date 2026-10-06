"""Industry policy templates (03 REQ-POL-009; PRD §2.4, §2.10, §5.3 BR-POL-03; POLICIES §0.4, §0.5;
research 05 §26, §28 Q6; BUILD_SPEC RFD-17, BS3-D-10).

``create_industry_templates(uow, cluster)`` creates, for one of the six 1.0 industry clusters
(REQ-DEMO-001), the cluster's POB templates as DRAFT versions and one DRAFT ``TENANT`` accounting
policy version holding the cluster's suggested tenant-level values. Nothing is tested, submitted or
published: the tenant must test and approve each version before it resolves (BR-POL-03), so
``GET /policies/resolve`` and booking-line template resolution ignore the drafts until then. No
route exposes the command (04 API-R-13 has none); the demo seed calls it for WLD-T-02 to WLD-T-07
(``erev_api.domain.demo.industry``).

[J] The template outputs and the tenant values are the playbooks' common conclusions (research
05, sections named per cluster), written as defaults the tenant reviews. Product-level policies
travel in ``policy_values`` of the template (POLICIES §0.5 level P); tenant-level ones in the
registry version. The principal-or-agent conclusion (POL-030) uses the template's
``principal_agent`` column, which the tenant confirms at publication; ``billing.posting`` (POL-004)
is not a draft value, because the seed publishes it where PRD §2.10 fixes it (Riverbend, D-14a).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_api.domain.policies import commands, registry_versions
from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.uow import UnitOfWork

TEMPLATE_PREFIX: Final = "IND"

_OVER_TIME_A: Final[Mapping[str, Any]] = MappingProxyType(
    {"satisfaction_pattern": "OVER_TIME", "over_time_criterion": "OT_A"}
)
_OVER_TIME_C: Final[Mapping[str, Any]] = MappingProxyType(
    {"satisfaction_pattern": "OVER_TIME", "over_time_criterion": "OT_C"}
)
_POINT_IN_TIME: Final[Mapping[str, Any]] = MappingProxyType(
    {"satisfaction_pattern": "POINT_IN_TIME", "over_time_criterion": "NOT_APPLICABLE"}
)
_RATABLE_DAILY: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "distinctness": "series",
        "series_increment_unit": "day",
        **_OVER_TIME_A,
        "recognition_method": "TIME_ELAPSED",
        "ratable_convention": "DAILY",
    }
)
_DISTINCT_DAILY: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "distinctness": "distinct",
        **_OVER_TIME_A,
        "recognition_method": "TIME_ELAPSED",
        "ratable_convention": "DAILY",
    }
)


@dataclass(frozen=True, slots=True)
class IndustryTemplate:
    """One suggested POB template of a cluster: the T-REF-22 identity and the T-REF-23 outputs."""

    code: str
    name: str
    description: str
    outputs: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class IndustryCluster:
    """A research 05 §26 cluster: its templates and suggested TENANT accounting policy values."""

    code: str
    name: str
    playbooks: str
    templates: tuple[IndustryTemplate, ...]
    tenant_values: Mapping[str, Any]


def template_code(cluster: str, suffix: str) -> str:
    """``IND-<cluster>-<suffix>``, for example ``IND-D01-SAAS-RATABLE``."""
    return f"{TEMPLATE_PREFIX}-{cluster}-{suffix}"


def _template(
    cluster: str, suffix: str, name: str, description: str, **outputs: Any
) -> IndustryTemplate:
    return IndustryTemplate(
        code=template_code(cluster, suffix),
        name=name,
        description=description,
        outputs=MappingProxyType(dict(outputs)),
    )


def _cluster(
    code: str,
    name: str,
    playbooks: str,
    templates: tuple[IndustryTemplate, ...],
    **tenant_values: Any,
) -> IndustryCluster:
    return IndustryCluster(
        code=code,
        name=name,
        playbooks=playbooks,
        templates=templates,
        tenant_values=MappingProxyType(dict(tenant_values)),
    )


# --- D01 Software and cloud (research 05 §2, §3, §21) -------------------------------------------

_D01: Final = "D01"
D01_SOFTWARE: Final = _cluster(
    _D01,
    "Software and cloud",
    "research 05 §2, §3, §21",
    (
        _template(
            _D01,
            "SAAS-RATABLE",
            "SaaS subscription, ratable by day",
            "A stand-ready series of daily service periods recognised evenly by day.",
            **_RATABLE_DAILY,
            revenue_category="SUBSCRIPTION",
            policy_values={
                "recognition.time_convention": "DAILY",
                "costs.amortisation_period": "TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE",
            },
        ),
        _template(
            _D01,
            "TERM-LICENCE",
            "Term licence, functional intellectual property",
            "A right to use functional IP recognised when the licence starts and is available.",
            obligation_kind="LICENCE",
            licence_nature="FUNCTIONAL",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="POINT_IN_TIME",
            start_date_rule="LICENCE_START_OR_AVAILABLE",
            revenue_category="LICENCE",
        ),
        _template(
            _D01,
            "PCS",
            "Post-contract support, ratable by day",
            "Unspecified updates and support as a stand-ready series recognised by day.",
            **_RATABLE_DAILY,
            revenue_category="SERVICES",
        ),
        _template(
            _D01,
            "IMPLEMENTATION-HOURS",
            "Implementation, labour hours",
            "A distinct fixed-fee implementation measured by labour hours against the estimate.",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="LABOUR_HOURS",
            revenue_category="SERVICES",
        ),
        _template(
            _D01,
            "TM-RIGHT-TO-INVOICE",
            "Time and materials, right to invoice",
            "Services billed as performed under the right-to-invoice expedient (606-10-55-18).",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="RIGHT_TO_INVOICE",
            revenue_category="SERVICES",
        ),
        _template(
            _D01,
            "USAGE-OVERAGE",
            "Usage and overage, series by transaction",
            "Committed drawdown and overage as a series recognised on usage.",
            distinctness="series",
            series_increment_unit="transaction",
            **_OVER_TIME_A,
            recognition_method="USAGE",
            revenue_category="SERVICES",
            policy_values={"usage.tier_minimum_method": "DERIVED"},
        ),
    ),
    # [J] The one non-default value is the journal summarisation (POL-006): contract-level journal
    # lines for the NetSuite mock target of the software demo (PRD §2.10), a grouping of the same
    # postings with no recognition or measurement content. Accounting-relevant defaults are never
    # loosened in reference data, even as drafts (team-lead ruling Q19); the other values restate
    # the framework defaults the cluster relies on, so that the tenant sees them in one place.
    **{
        "recognition.time_convention": "DAILY",
        "material_right.exercise": "CONTINUATION",
        "je.summarization": "CONTRACT_ACCOUNT_DIMENSIONS",
        "ssp.residual_failure": "REQUIRE_ESTIMATED_SSP",
    },
)

# --- D02 Devices and industrial products (research 05 §4, §8) -----------------------------------

_D02: Final = "D02"
D02_DEVICES: Final = _cluster(
    _D02,
    "Devices and industrial products",
    "research 05 §4, §8",
    (
        _template(
            _D02,
            "DEVICE-DELIVERY",
            "Device sale, units delivered",
            "Hardware recognised per unit when control transfers, with expected returns.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="UNITS_DELIVERED",
            revenue_category="PRODUCT",
            policy_values={
                "returns.model": "EXPECTED_RETURNS",
                "recognition.control_trigger": "ANY_TRANSFER",
            },
        ),
        _template(
            _D02,
            "DISTRIBUTOR-SELL-THROUGH",
            "Consignment stock, sell-through",
            "Units at distributor or customer sites recognised on sell-through only.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="UNITS_DELIVERED",
            revenue_category="PRODUCT",
            policy_values={"recognition.control_trigger": "SELL_THROUGH_ONLY"},
        ),
        _template(
            _D02,
            "EXTENDED-WARRANTY",
            "Extended warranty, ratable by day",
            "A service-type warranty sold separately, recognised evenly over its term.",
            obligation_kind="SERVICE_WARRANTY",
            warranty_type="SERVICE",
            **_RATABLE_DAILY,
            revenue_category="SERVICES",
        ),
        _template(
            _D02,
            "PLATFORM-SUBSCRIPTION",
            "Connected platform subscription",
            "The device platform subscription as a stand-ready series recognised by day.",
            **_RATABLE_DAILY,
            revenue_category="SUBSCRIPTION",
        ),
        _template(
            _D02,
            "CUSTODIAL",
            "Bill-and-hold custodial service",
            "The custodial service of a bill-and-hold arrangement, recognised by day held.",
            obligation_kind="CUSTODIAL",
            **_DISTINCT_DAILY,
            revenue_category="SERVICES",
        ),
        _template(
            _D02,
            "TOOLING-COST-TO-COST",
            "Customised tooling, cost to cost",
            "Customer-specific tooling with an enforceable right to payment, measured by costs.",
            distinctness="distinct",
            **_OVER_TIME_C,
            recognition_method="COST_TO_COST",
            revenue_category="PRODUCT",
        ),
    ),
    **{
        "bill_and_hold.custodial_pob": "CREATE_WHEN_SSP_PROVIDED",
        "pob.assurance_warranty_accrual": "ENGINE",
        "returns.reversal_rate": "AVERAGE_CARRYING_RATE",
        "recognition.time_convention": "DAILY",
    },
)

# --- D04 Engineering, construction and government (research 05 §6, §7) --------------------------

_D04: Final = "D04"
D04_ENGINEERING: Final = _cluster(
    _D04,
    "Engineering, construction and government",
    "research 05 §6, §7",
    (
        _template(
            _D04,
            "EPC-COST-TO-COST",
            "Fixed-price EPC, cost to cost",
            "A single over-time obligation measured by costs incurred to total expected costs.",
            distinctness="distinct",
            **_OVER_TIME_C,
            recognition_method="COST_TO_COST",
            revenue_category="SERVICES",
        ),
        _template(
            _D04,
            "CPIF-COST-TO-COST",
            "Cost-plus incentive fee programme, cost to cost",
            "Cost reimbursement with a constrained incentive fee, measured by costs.",
            distinctness="distinct",
            **_OVER_TIME_C,
            recognition_method="COST_TO_COST",
            revenue_category="SERVICES",
        ),
        _template(
            _D04,
            "MILESTONE",
            "Milestone programme",
            "An over-time obligation measured by contractual output milestones.",
            distinctness="distinct",
            **_OVER_TIME_C,
            recognition_method="MILESTONE",
            revenue_category="SERVICES",
        ),
        _template(
            _D04,
            "TASK-ORDER-RIGHT-TO-INVOICE",
            "IDIQ task order, right to invoice",
            "Task orders billed as performed under the right-to-invoice expedient.",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="RIGHT_TO_INVOICE",
            revenue_category="SERVICES",
        ),
        _template(
            _D04,
            "DESIGN-SERVICES-HOURS",
            "Design services, labour hours",
            "Engineering design services measured by labour hours.",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="LABOUR_HOURS",
            revenue_category="SERVICES",
        ),
    ),
    **{
        "loss.unit": "CONTRACT",
        "mod.catch_up_scope": "PARTIALLY_SATISFIED_NONDISTINCT_ONLY",
        "recognition.time_convention": "DAILY",
    },
)

# --- D05 Consumer brands and franchising (research 05 §9, §13) ----------------------------------

_D05: Final = "D05"
D05_CONSUMER: Final = _cluster(
    _D05,
    "Consumer brands and franchising",
    "research 05 §9, §13",
    (
        _template(
            _D05,
            "POS-SALE",
            "Point-of-sale product",
            "Goods sold at the till, recognised at the sale.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="POINT_IN_TIME",
            revenue_category="PRODUCT",
        ),
        _template(
            _D05,
            "LOYALTY-POINTS",
            "Loyalty points, material right by redemption",
            "Points as a material right recognised on the redemption pattern with breakage.",
            obligation_kind="MATERIAL_RIGHT",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="REDEMPTION_PATTERN",
            revenue_category="MATERIAL_RIGHT",
            policy_values={
                "breakage.method": "PROPORTIONAL_TO_EXERCISE",
                "material_right.ssp_method": "DISCOUNT_X_LIKELIHOOD",
            },
        ),
        _template(
            _D05,
            "GIFT-CARD",
            "Gift card, redemption with breakage",
            "Stored value recognised as redeemed, breakage in proportion to redemptions.",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="REDEMPTION_PATTERN",
            revenue_category="PRODUCT",
            policy_values={"breakage.method": "PROPORTIONAL_TO_EXERCISE"},
        ),
        _template(
            _D05,
            "MEMBERSHIP",
            "Paid membership, ratable by day",
            "A paid membership as a stand-ready series recognised by day.",
            **_RATABLE_DAILY,
            revenue_category="SUBSCRIPTION",
        ),
        _template(
            _D05,
            "FRANCHISE-RIGHT",
            "Franchise right, symbolic licence over the term",
            "The franchise licence (symbolic IP) recognised over the term; the initial fee "
            "follows the contract term.",
            obligation_kind="LICENCE",
            licence_nature="SYMBOLIC",
            **_DISTINCT_DAILY,
            revenue_category="LICENCE",
            # No POL-029 value (04 T-REF-23 rev 1.323): no computation reads
            # ``upfront_fee.recognition_period`` from a template
            # (``reference.products.LEVEL_P_NOT_READ``), and without a renewal option the fee
            # follows the term under either option.
        ),
    ),
    **{
        "material_right.exercise": "CONTINUATION",
        "recognition.time_convention": "DAILY",
        "rollforward.opening_liability_consumption": "FIFO_WITHIN_CONTRACT",
    },
)

# --- D08 Healthcare providers (research 05 §12) --------------------------------------------------

_D08: Final = "D08"
D08_HEALTHCARE: Final = _cluster(
    _D08,
    "Healthcare providers",
    "research 05 §12",
    (
        _template(
            _D08,
            "INPATIENT-STAY",
            "Inpatient stay, over the stay by day",
            "Inpatient services recognised over the stay; in-house patients at month-end carry "
            "the days performed.",
            **_DISTINCT_DAILY,
            revenue_category="SERVICES",
        ),
        _template(
            _D08,
            "OUTPATIENT-ENCOUNTER",
            "Outpatient encounter, point in time",
            "An encounter recognised when the service is rendered, net of contractual adjustments.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="POINT_IN_TIME",
            revenue_category="SERVICES",
        ),
        _template(
            _D08,
            "CAPITATION-PMPM",
            "Capitation, per member per month",
            "A stand-ready series of monthly coverage periods recognised evenly by month.",
            distinctness="series",
            series_increment_unit="month",
            **_OVER_TIME_A,
            recognition_method="TIME_ELAPSED",
            ratable_convention="MONTHLY_EVEN",
            revenue_category="SERVICES",
        ),
        _template(
            _D08,
            "SELF-PAY-COHORT",
            "Self-pay cohort, net of implicit price concessions",
            "Self-pay services recognised at the encounter at the portfolio's expected "
            "collections; later credit losses are not revenue.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="POINT_IN_TIME",
            revenue_category="SERVICES",
        ),
    ),
    **{
        "recognition.time_convention": "DAILY",
        "je.posting_mode": "GROSS",
        "vc.reassessment_gate": "REQUIRE_VERSION_OR_ATTESTATION",
    },
)

# --- D12 Platforms and travel (research 05 §17, §18) --------------------------------------------

_D12: Final = "D12"
D12_PLATFORMS: Final = _cluster(
    _D12,
    "Platforms and travel",
    "research 05 §17, §18",
    (
        _template(
            _D12,
            "MARKETPLACE-COMMISSION",
            "Third-party marketplace commission, agent",
            "The platform arranges the sale as agent and recognises its commission at the order.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="POINT_IN_TIME",
            principal_agent="AGENT",
            revenue_category="SERVICES",
        ),
        _template(
            _D12,
            "FIRST-PARTY-GOODS",
            "First-party inventory sale, principal",
            "Owned inventory recognised gross per unit delivered, with expected returns.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="UNITS_DELIVERED",
            principal_agent="PRINCIPAL",
            revenue_category="PRODUCT",
            policy_values={"returns.model": "EXPECTED_RETURNS"},
        ),
        _template(
            _D12,
            "PLATFORM-CREDITS",
            "Platform credits, material right with breakage",
            "Credits recognised as redeemed, breakage in proportion to redemptions including "
            "expected rollover use.",
            obligation_kind="MATERIAL_RIGHT",
            distinctness="distinct",
            **_OVER_TIME_A,
            recognition_method="REDEMPTION_PATTERN",
            revenue_category="MATERIAL_RIGHT",
            policy_values={
                "breakage.method": "PROPORTIONAL_TO_EXERCISE",
                "credits.rollover_treatment": "BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE",
            },
        ),
        _template(
            _D12,
            "MERCHANT-STAY",
            "Merchant-model hotel stay, principal",
            "The platform controls the room night and recognises gross over the stay.",
            **_DISTINCT_DAILY,
            principal_agent="PRINCIPAL",
            revenue_category="SERVICES",
        ),
        _template(
            _D12,
            "AGENCY-BOOKING",
            "Agency-model booking, agent at booking",
            "The platform arranges the stay as agent and recognises its fee at the booking.",
            distinctness="distinct",
            **_POINT_IN_TIME,
            recognition_method="POINT_IN_TIME",
            principal_agent="AGENT",
            revenue_category="SERVICES",
        ),
    ),
    **{
        "material_right.exercise": "CONTINUATION",
        "recognition.time_convention": "DAILY",
        "ssp.residual_failure": "REQUIRE_ESTIMATED_SSP",
    },
)

CLUSTERS: Final[Mapping[str, IndustryCluster]] = MappingProxyType(
    {
        cluster.code: cluster
        for cluster in (
            D01_SOFTWARE,
            D02_DEVICES,
            D04_ENGINEERING,
            D05_CONSUMER,
            D08_HEALTHCARE,
            D12_PLATFORMS,
        )
    }
)


def cluster_of(code: str) -> IndustryCluster:
    """The cluster of ``code``; ``LookupError`` for a code outside the six 1.0 clusters."""
    try:
        return CLUSTERS[code]
    except KeyError:
        known = ", ".join(CLUSTERS)
        raise LookupError(f"Unknown industry cluster {code}; one of {known}") from None


@dataclass(frozen=True, slots=True)
class IndustryDrafts:
    """What ``create_industry_templates`` created: every id is a DRAFT version."""

    cluster: str
    template_ids: Mapping[str, UUID]  # template code → T-REF-22 id
    template_version_ids: Mapping[str, UUID]  # template code → T-REF-23 id
    registry_version_id: UUID


def create_industry_templates(uow: UnitOfWork, cluster: str) -> IndustryDrafts:
    """Create the cluster's POB templates as DRAFT versions and its DRAFT TENANT accounting policy
    version (BS3-D-10). The caller is the preparer (``config.author``); a taken template code or an
    open TENANT accounting policy version raises the command's ``Problem`` (422 or 409 SM-04)."""
    spec = cluster_of(cluster)
    template_ids: dict[str, UUID] = {}
    version_ids: dict[str, UUID] = {}
    for template in spec.templates:
        template_id = commands.create_pob_template(
            uow, code=template.code, name=template.name, description=template.description
        )
        version_ids[template.code] = commands.create_pob_template_version(
            uow,
            template_id,
            changes=dict(template.outputs),
            effective_from=None,
            source_version_id=None,
        )
        template_ids[template.code] = template_id
    registry_version_id = registry_versions.create_policy(
        uow,
        category=RegistryCategory.ACCOUNTING_POLICY,
        scope=RegistryScope.TENANT,
        entity_code=None,
        book_code=None,
        values=dict(spec.tenant_values),
        effective_from=None,
    )
    return IndustryDrafts(
        cluster=spec.code,
        template_ids=MappingProxyType(template_ids),
        template_version_ids=MappingProxyType(version_ids),
        registry_version_id=registry_version_id,
    )

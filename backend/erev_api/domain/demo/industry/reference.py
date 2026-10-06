"""Industry tenant reference data (PRD §2.4, §2.10; research 05 §26; 03 REQ-DEMO-001, REQ-POL-009;
BUILD_SPEC RFD-17, BS3-D-10, BS3-D-09; D-14a).

Order and personas, as in the Avenmoor builders (WLD-R-02):

1. ``tomas`` creates the January calendar with FY2026 and FY2027, enables the tenant currencies and
   creates the entities (the first is the reporting parent; FS-UK and WM-UK carry the IFRS15 book
   beside ASC606), and ``marcus`` opens Jan to Sep 2026 for every entity and book; Oct 2026 onward
   stays ``future`` (WLD-P-02; BS3-D-09).
2. ``maya`` creates the chart of accounts (the PRD §2.6 chart, reused) and the account mapping,
   which ``marcus`` approves. Riverbend adds the RECEIVABLE_CONTRA account for implicit price
   concessions (JET-04c; D-14a).
3. Riverbend: ``maya`` prepares ``billing.posting = ENGINE`` (POL-004) effective from the next
   period and ``marcus`` approves it (PRD §2.10).
4. ``maya`` creates the cluster's industry templates and tenant policy version as drafts
   (``create_industry_templates``); they stay unpublished until the tenant tests and approves them
   (BR-POL-03).

[J] The PRD §2.10 table gives entity codes, currencies and books only; legal names, countries and
time zones follow the functional currency. Customers, products, SSP books and the scenario contracts
of the industry tenants arrive with the items that seed their scenarios (REQ-DEMO-003; J-24).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.tables import legal_entity, period, period_state
from erev_api.domain.demo.avenmoor import (
    CURRENT_PERIOD_START,
    GO_LIVE,
    expect_version,
    next_period_start,
)
from erev_api.domain.demo.avenmoor.reference import CHART, AccountSpec, MappedRole
from erev_api.domain.demo.industry import ACCOUNTANT, CLUSTER_BY_WLD, CONTROLLER, TENANT_ADMIN
from erev_api.domain.policies import lifecycle, registry_versions
from erev_api.domain.policies.industry import IndustryDrafts, create_industry_templates
from erev_api.domain.reference import commands, queries
from erev_api.enums import (
    AccountRole,
    AccountType,
    ApprovalSubjectType,
    BookCode,
    PeriodState,
    RegistryCategory,
    RegistryScope,
)
from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingRuleIn
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.calendars import CalendarIn, GenerateYearIn
from erev_api.schemas.currencies import TenantCurrenciesIn
from erev_api.schemas.entities import EntityBookIn, EntityIn
from erev_api.schemas.periods import PeriodOpenIn

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

SETTINGS_MANAGE: Final = "settings.manage"
CONFIG_AUTHOR: Final = "config.author"
OPEN_COMMENT: Final = "Opened for the industry demo go-live (WLD-P-02)."
SUBMIT_COMMENT: Final = "Ready for review."
FISCAL_YEARS: Final = (2026, 2027)
FIRST_PERIOD_KEY: Final = "FY2026-P01"  # Jan 2026 in a January calendar
ENGINE_BILLING: Final[Mapping[str, Any]] = {"billing.posting": "ENGINE"}


@dataclass(frozen=True, slots=True)
class IndustryEntity:
    code: str
    name: str
    country_code: str
    functional_currency: str
    time_zone: str
    books: tuple[BookCode, ...]  # primary first


@dataclass(frozen=True, slots=True)
class IndustryTenant:
    wld_id: str
    cluster: str
    prefix: str  # entity code prefix; also the calendar and mapping code prefix
    calendar_name: str
    entities: tuple[IndustryEntity, ...]  # the first is the reporting parent
    engine_billing: bool = False  # PRD §2.10 ``billing.posting = ENGINE`` (D-14a)


_US: Final = ("US", "USD", "America/New_York")
_ASC: Final = (BookCode.ASC606,)
_ASC_IFRS: Final = (BookCode.ASC606, BookCode.IFRS15)


def _entity(
    code: str, name: str, place: tuple[str, str, str], books: tuple[BookCode, ...] = _ASC
) -> IndustryEntity:
    country, currency, zone = place
    return IndustryEntity(code, name, country, currency, zone, books)


# PRD §2.10 table; the cluster of each WLD id is CLUSTER_BY_WLD (PRD §2.4).
TENANTS: Final[tuple[IndustryTenant, ...]] = (
    IndustryTenant(
        "WLD-T-02",
        CLUSTER_BY_WLD["WLD-T-02"],
        "FS",
        "Fernhill, January year",
        (
            _entity("FS-US", "Fernhill Software, Inc. (Demo)", _US),
            _entity(
                "FS-UK",
                "Fernhill Software UK Ltd (Demo)",
                ("GB", "GBP", "Europe/London"),
                _ASC_IFRS,
            ),
        ),
    ),
    IndustryTenant(
        "WLD-T-03",
        CLUSTER_BY_WLD["WLD-T-03"],
        "BR",
        "Bracken, January year",
        (
            _entity("BR-US", "Bracken Robotics Corp. (Demo)", _US),
            _entity("BR-DE", "Bracken Robotics GmbH (Demo)", ("DE", "EUR", "Europe/Berlin")),
            _entity("BR-JP", "Bracken Robotics KK (Demo)", ("JP", "JPY", "Asia/Tokyo")),
        ),
    ),
    IndustryTenant(
        "WLD-T-04",
        CLUSTER_BY_WLD["WLD-T-04"],
        "GE",
        "Granitefield, January year",
        (
            _entity("GE-US", "Granitefield Engineering Group, Inc. (Demo)", _US),
            _entity(
                "GE-CA",
                "Granitefield Engineering Canada Ltd (Demo)",
                ("CA", "CAD", "America/Toronto"),
            ),
        ),
    ),
    IndustryTenant(
        "WLD-T-05",
        CLUSTER_BY_WLD["WLD-T-05"],
        "JS",
        "Juniper Street, January year",
        (
            _entity("JS-US", "Juniper Street Coffee Co. (Demo)", _US),
            _entity(
                "JS-CA",
                "Juniper Street Coffee Canada Inc. (Demo)",
                ("CA", "CAD", "America/Toronto"),
            ),
        ),
    ),
    IndustryTenant(
        "WLD-T-06",
        CLUSTER_BY_WLD["WLD-T-06"],
        "RB",
        "Riverbend, January year",
        (_entity("RB-US", "Riverbend Health System (Demo)", ("US", "USD", "America/Chicago")),),
        engine_billing=True,
    ),
    IndustryTenant(
        "WLD-T-07",
        CLUSTER_BY_WLD["WLD-T-07"],
        "WM",
        "Wayfarer, January year",
        (
            _entity("WM-US", "Wayfarer Marketplace, Inc. (Demo)", _US),
            _entity(
                "WM-IE", "Wayfarer Marketplace Ireland Ltd (Demo)", ("IE", "EUR", "Europe/Dublin")
            ),
            _entity(
                "WM-UK",
                "Wayfarer Marketplace UK Ltd (Demo)",
                ("GB", "GBP", "Europe/London"),
                _ASC_IFRS,
            ),
        ),
    ),
)
BY_WLD: Final[Mapping[str, IndustryTenant]] = {tenant.wld_id: tenant for tenant in TENANTS}

# D-14a: with ``billing.posting = ENGINE`` the engine posts implicit price concessions against the
# receivable through RECEIVABLE_CONTRA (JET-04c); a contra asset with a credit normal balance.
CONCESSION_ACCOUNT: Final = AccountSpec(
    "1150",
    "Allowance for implicit price concessions",
    AccountType.ASSET,
    "C",
    (MappedRole(AccountRole.RECEIVABLE_CONTRA),),
)
MAPPING_NOTES: Final = (
    "The PRD §2.6 chart of accounts, reused for the industry tenants. No rule for "
    "PRE_STANDARD_REVENUE (no LEGACY book)."
)
ENGINE_MAPPING_NOTES: Final = (
    f"{MAPPING_NOTES} RECEIVABLE_CONTRA is mapped for implicit price concessions "
    "(billing.posting = ENGINE; JET-04c; D-14a)."
)


def tenant_spec(wld_id: str) -> IndustryTenant:
    """The industry tenant of ``wld_id``; ``LookupError`` for any other id."""
    try:
        return BY_WLD[wld_id]
    except KeyError:
        raise LookupError(f"{wld_id} is not an industry demo tenant") from None


def chart_of(spec: IndustryTenant) -> tuple[AccountSpec, ...]:
    """The accounts of the tenant: the PRD §2.6 chart, plus the concession contra under D-14a."""
    return (*CHART, CONCESSION_ACCOUNT) if spec.engine_billing else CHART


def currencies_of(spec: IndustryTenant) -> tuple[str, ...]:
    """The tenant currencies: USD (the reporting currency) and every functional currency."""
    return tuple(sorted({"USD", *(entity.functional_currency for entity in spec.entities)}))


def entity_codes(wld_id: str) -> Sequence[str]:
    return tuple(entity.code for entity in tenant_spec(wld_id).entities)


# --- builder -------------------------------------------------------------------------------------


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _calendar(ctx: BuildContext, spec: IndustryTenant) -> UUID:
    with ctx.command(TENANT_ADMIN) as uow:
        created = commands.create_calendar(
            uow,
            body=CalendarIn(
                code=f"{spec.prefix}-JAN", name=spec.calendar_name, fiscal_year_start_month=1
            ),
        )
    for year in FISCAL_YEARS:
        with ctx.command(TENANT_ADMIN) as uow:
            commands.generate_year(
                uow, calendar_id=created.id, body=GenerateYearIn(fiscal_year=year)
            )
    return created.id


def _enable_tenant_book(ctx: BuildContext, code: BookCode) -> None:
    with ctx.read() as session:
        current = queries.book_row(session, code.value)
    if current is None or current["is_enabled"]:
        return
    with ctx.command(TENANT_ADMIN) as uow:
        commands.update_book(
            uow,
            code=code,
            changes={"is_enabled": True},
            check_version=expect_version(int(current["row_version"])),
        )


def _create_entity(
    ctx: BuildContext, entity: IndustryEntity, calendar_id: UUID, parent_id: UUID | None
) -> UUID:
    with ctx.command(TENANT_ADMIN) as uow:
        created = commands.create_entity(
            uow,
            body=EntityIn(
                code=entity.code,
                name=entity.name,
                functional_currency=entity.functional_currency,
                time_zone=entity.time_zone,
                calendar_id=calendar_id,
                parent_entity_id=parent_id,
                country_code=entity.country_code,
                first_period_key=FIRST_PERIOD_KEY,
            ),
        )
    for code in entity.books[1:]:
        _enable_tenant_book(ctx, code)
        with ctx.command(TENANT_ADMIN) as uow:
            commands.put_entity_book(
                uow,
                entity_id=created.id,
                code=code,
                body=EntityBookIn(is_enabled=True, first_period_key=FIRST_PERIOD_KEY),
            )
    return created.id


def _open_periods(ctx: BuildContext, entity_code: str) -> None:
    """``marcus`` opens every future state of the entity from Jan 2026 to Sep 2026 (WLD-P-02;
    BS3-D-09)."""
    joined = period_state.join(
        period,
        and_(
            period.c.tenant_id == period_state.c.tenant_id, period.c.id == period_state.c.period_id
        ),
    ).join(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == period_state.c.tenant_id,
            legal_entity.c.id == period_state.c.entity_id,
        ),
    )
    with ctx.read() as session:
        states = session.execute(
            select(period_state.c.id, period_state.c.row_version)
            .select_from(joined)
            .where(
                legal_entity.c.code == entity_code,
                period.c.start_date >= GO_LIVE,
                period.c.start_date <= CURRENT_PERIOD_START,
                period_state.c.state == PeriodState.FUTURE.value,
            )
            .order_by(period_state.c.book_code, period.c.start_date)
        ).all()
    for state_id, row_version in states:
        with ctx.command(CONTROLLER) as uow:
            commands.open_period(
                uow,
                state_id=UUID(str(state_id)),
                body=PeriodOpenIn(comment=OPEN_COMMENT),
                check_version=expect_version(int(row_version)),
            )


def _chart_and_mapping(ctx: BuildContext, spec: IndustryTenant) -> UUID:
    accounts: dict[str, UUID] = {}
    for account in chart_of(spec):
        with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
            created = commands.create_gl_account(
                uow,
                body=GlAccountIn(
                    code=account.code,
                    name=account.name,
                    account_type=account.account_type,
                    normal_balance=account.normal_balance,
                ),
            )
        accounts[account.code] = created.id
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        version_id = commands.create_account_mapping_version(
            uow,
            body=AccountMappingIn(
                name=f"{spec.prefix}-MAP-2026-01",
                notes=ENGINE_MAPPING_NOTES if spec.engine_billing else MAPPING_NOTES,
                effective_from=_midnight(GO_LIVE),
            ),
        )
    for account in chart_of(spec):
        for mapped in account.roles:
            with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
                commands.add_account_mapping_rule(
                    uow,
                    version_id,
                    body=AccountMappingRuleIn(
                        account_role=mapped.role,
                        clearing_purpose=mapped.clearing_purpose,
                        revenue_category=mapped.revenue_category,
                        gl_account_id=accounts[account.code],
                    ),
                )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.run_account_mapping_tests(uow, version_id)
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.submit_account_mapping_version(uow, version_id, comment=SUBMIT_COMMENT)
    ctx.approve(ApprovalSubjectType.ACCOUNT_MAPPING_VERSION, version_id, [CONTROLLER])
    return version_id


def _engine_billing_policy(ctx: BuildContext) -> UUID:
    """PRD §2.10 Riverbend: ``billing.posting = ENGINE`` published from the next period (POL-004 is
    period-scoped), prepared by ``maya`` and approved by ``marcus``."""
    effective_from = next_period_start(ctx.clock.now())
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        version_id = registry_versions.create_policy(
            uow,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.TENANT,
            entity_code=None,
            book_code=None,
            values=dict(ENGINE_BILLING),
            effective_from=effective_from,
        )
    # As the Avenmoor seed: the POLICY_SIMULATION runner runs inline as the preparer (L4-5-Q-8).
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


def _industry_drafts(ctx: BuildContext, cluster: str) -> IndustryDrafts:
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        return create_industry_templates(uow, cluster)


def build(ctx: BuildContext) -> None:
    """PRD §2.10 reference data of the industry tenant ``ctx.wld_id`` (module docstring order)."""
    spec = tenant_spec(ctx.wld_id)
    calendar_id = _calendar(ctx, spec)
    with ctx.command(TENANT_ADMIN, SETTINGS_MANAGE) as uow:
        commands.put_tenant_currencies(
            uow, body=TenantCurrenciesIn(currency_codes=list(currencies_of(spec)))
        )
    parent: UUID | None = None
    for entity in spec.entities:
        entity_id = _create_entity(ctx, entity, calendar_id, parent)
        parent = parent or entity_id
        _open_periods(ctx, entity.code)
    _chart_and_mapping(ctx, spec)
    if spec.engine_billing:
        _engine_billing_policy(ctx)
    _industry_drafts(ctx, spec.cluster)

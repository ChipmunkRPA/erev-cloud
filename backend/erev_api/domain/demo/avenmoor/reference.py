"""Avenmoor reference data (PRD §2.5 structure, periods and FX rate sets; §2.6 chart of accounts,
account mapping and products; §2.7 customers; BUILD_SPEC RFD-16, BS3-D-09).

Order and personas:

1. ``tomas`` creates the January calendar with FY2026 and FY2027, enables the tenant currencies,
   creates AVM-US and AVM-UK (with the IFRS15 book) and AVM-DE, and ``marcus`` opens Jan to Sep 2026
   for every entity and book; Oct 2026 onward stays ``future`` (BS3-D-09).
2. ``maya`` enters the ``AVM-RATES`` spot, closing and average rate sets and ``marcus`` approves
   them.
3. ``tomas`` creates the April calendar with FY2026 to FY2028 and AVM-JP from Jan 2026
   (``FY2026-P10``), and ``marcus`` opens its Jan to Sep 2026 periods.
4. ``maya`` creates the 32 accounts and mapping ``AVM-MAP-2026-01``, which ``marcus`` approves.
5. ``maya`` creates group ``HOLLENBRAND``, the 13 customers and the 17 products.

[J] L4-5-Q-1: closing and average rates name their period by ``period_key``, and FY keys of the
April calendar name other months than the January calendar's keys, so the rates are entered while
only the January calendar exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.tables import legal_entity, period, period_state
from erev_api.domain.demo.avenmoor import (
    ACCOUNTANT,
    CONTROLLER,
    CURRENT_PERIOD_START,
    GO_LIVE,
    TENANT_ADMIN,
    expect_version,
)
from erev_api.domain.reference import commands, queries
from erev_api.enums import (
    AccountRole,
    AccountType,
    ApprovalSubjectType,
    BookCode,
    ClearingPurpose,
    PeriodState,
    RateType,
    SourceSystem,
)
from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingRuleIn
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.calendars import CalendarIn, GenerateYearIn
from erev_api.schemas.currencies import (
    FxRateIn,
    FxRateSetIn,
    FxRateSetVersionCommandIn,
    FxRateSetVersionIn,
    TenantCurrenciesIn,
)
from erev_api.schemas.customers import CustomerIn, RelatedPartyGroupIn
from erev_api.schemas.entities import EntityBookIn, EntityIn
from erev_api.schemas.periods import PeriodOpenIn
from erev_api.schemas.products import ProductIn

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

SETTINGS_MANAGE: Final = "settings.manage"
CONFIG_AUTHOR: Final = "config.author"
MASTERDATA_MAINTAIN: Final = "masterdata.maintain"
OPEN_COMMENT: Final = "Opened for the Avenmoor go-live (WLD-P-02)."
SUBMIT_COMMENT: Final = "Ready for review."


@dataclass(frozen=True, slots=True)
class CalendarSpec:
    code: str
    name: str
    start_month: int
    fiscal_years: tuple[int, ...]


# [J] Calendar codes and names; PRD §2.5 gives the fiscal year starts only.
JANUARY_CALENDAR: Final = CalendarSpec("AVM-JAN", "Avenmoor, January year", 1, (2026, 2027))
APRIL_CALENDAR: Final = CalendarSpec("AVM-APR", "Avenmoor Media, April year", 4, (2026, 2027, 2028))


@dataclass(frozen=True, slots=True)
class EntitySpec:
    code: str
    name: str
    country_code: str
    functional_currency: str
    time_zone: str
    calendar: CalendarSpec
    first_period_key: str  # Jan 2026 in the entity's calendar
    books: tuple[BookCode, ...]  # primary first


# PRD §2.5 entity table; AVM-US, created first, is the reporting parent of the others.
ENTITIES: Final[tuple[EntitySpec, ...]] = (
    EntitySpec(
        "AVM-US",
        "Avenmoor Inc. (Demo)",
        "US",
        "USD",
        "America/New_York",
        JANUARY_CALENDAR,
        "FY2026-P01",
        # D-87 L6-5-Q-24: AVM-US keeps the IFRS15 book beside the primary ASC606 book, so the
        # IFRS15 book of K-04 posts its AVM-US performing part (CTR-20).
        (BookCode.ASC606, BookCode.IFRS15),
    ),
    EntitySpec(
        "AVM-UK",
        "Avenmoor UK Ltd (Demo)",
        "GB",
        "GBP",
        "Europe/London",
        JANUARY_CALENDAR,
        "FY2026-P01",
        (BookCode.ASC606, BookCode.IFRS15),
    ),
    EntitySpec(
        "AVM-DE",
        "Avenmoor Devices GmbH (Demo)",
        "DE",
        "EUR",
        "Europe/Berlin",
        JANUARY_CALENDAR,
        "FY2026-P01",
        (BookCode.ASC606,),
    ),
    EntitySpec(
        "AVM-JP",
        "Avenmoor Media KK (Demo)",
        "JP",
        "JPY",
        "Asia/Tokyo",
        APRIL_CALENDAR,
        "FY2026-P10",
        (BookCode.ASC606,),
    ),
)
TENANT_CURRENCIES: Final = ("USD", "EUR", "GBP", "JPY")

# --- FX rate sets (PRD §2.5 FX rate sets) --------------------------------------------------------

COVERAGE_FROM: Final = GO_LIVE
COVERAGE_TO: Final = date(2026, 9, 30)
RATE_PAIRS: Final = ("EUR", "GBP", "JPY")  # each → USD; cross rates derive through USD
# (average, closing) per pair for Aug 2026 and Sep 2026; Jan to Jul 2026 every rate is Aug average.
AUGUST_RATES: Final = {
    "EUR": ("1.100000", "1.105000"),
    "GBP": ("1.270000", "1.275000"),
    "JPY": ("0.006800", "0.006850"),
}
SEPTEMBER_RATES: Final = {
    "EUR": ("1.110000", "1.120000"),
    "GBP": ("1.280000", "1.290000"),
    "JPY": ("0.006900", "0.006950"),
}
# [J] L4-5-Q-2: a rate set has one rate type (T-REF-10), so AVM-RATES is three sets.
RATE_SET_CODE: Final = "AVM-RATES"
RATE_SETS: Final = (
    (RateType.SPOT, f"{RATE_SET_CODE}-SPOT", "AVM-RATES spot"),
    (RateType.CLOSING, f"{RATE_SET_CODE}-CLOSING", "AVM-RATES closing"),
    (RateType.AVERAGE, f"{RATE_SET_CODE}-AVERAGE", "AVM-RATES average"),
)


def month_rates(currency: str, month: int) -> tuple[str, str]:
    """(average, closing) of ``currency`` → USD for a month of 2026 (1 to 9)."""
    if month == 9:
        return SEPTEMBER_RATES[currency]
    if month == 8:
        return AUGUST_RATES[currency]
    average = AUGUST_RATES[currency][0]
    return average, average


def rate_rows(rate_type: RateType) -> list[FxRateIn]:
    """The entered rates of a set: spot per day (the month average), closing and average per
    January-calendar period."""
    rows: list[FxRateIn] = []
    if rate_type is RateType.SPOT:
        day = COVERAGE_FROM
        while day <= COVERAGE_TO:
            for currency in RATE_PAIRS:
                average, _ = month_rates(currency, day.month)
                rows.append(
                    FxRateIn(
                        base_currency=currency,
                        quote_currency="USD",
                        rate=average,
                        effective_date=day,
                    )
                )
            day += timedelta(days=1)
        return rows
    for month in range(1, 10):
        for currency in RATE_PAIRS:
            average, closing = month_rates(currency, month)
            rows.append(
                FxRateIn(
                    base_currency=currency,
                    quote_currency="USD",
                    rate=average if rate_type is RateType.AVERAGE else closing,
                    period_key=f"FY2026-P{month:02d}",
                )
            )
    return rows


# --- chart of accounts and account mapping (PRD §2.6) --------------------------------------------


@dataclass(frozen=True, slots=True)
class MappedRole:
    role: AccountRole
    clearing_purpose: ClearingPurpose | None = None
    revenue_category: str | None = None


@dataclass(frozen=True, slots=True)
class AccountSpec:
    code: str
    name: str
    account_type: AccountType
    normal_balance: str
    roles: tuple[MappedRole, ...]


def _account(
    code: str, name: str, kind: AccountType, *roles: MappedRole | AccountRole
) -> AccountSpec:
    normal = "D" if kind in (AccountType.ASSET, AccountType.EXPENSE) else "C"
    mapped = tuple(role if isinstance(role, MappedRole) else MappedRole(role) for role in roles)
    return AccountSpec(code, name, kind, normal, mapped)


_R = AccountRole
_A, _L, _REV, _EXP = (
    AccountType.ASSET,
    AccountType.LIABILITY,
    AccountType.REVENUE,
    AccountType.EXPENSE,
)
CHART: Final[tuple[AccountSpec, ...]] = (
    _account("1100", "Accounts receivable", _A, _R.ACCOUNTS_RECEIVABLE),
    _account("1105", "Unbilled receivable", _A, _R.UNBILLED_RECEIVABLE),
    _account("1200", "Contract asset", _A, _R.CONTRACT_ASSET),
    _account("1210", "Customer incentive asset", _A, _R.CUSTOMER_INCENTIVE_ASSET),
    _account("1310", "Asset for right to recover products", _A, _R.RETURN_ASSET),
    _account("1400", "Capitalised costs to obtain a contract", _A, _R.COST_TO_OBTAIN_ASSET),
    _account("1410", "Capitalised costs to fulfil a contract", _A, _R.COST_TO_FULFILL_ASSET),
    _account("1500", "Noncash consideration received", _A, _R.NONCASH_CONSIDERATION_ASSET),
    _account("1800", "Intercompany due from", _A, _R.INTERCOMPANY_DUE_FROM),
    _account("2020", "Commissions payable (contract cost clearing)", _L, _R.CONTRACT_COST_CLEARING),
    _account(
        "2090",
        "Subledger clearing",
        _L,
        *(MappedRole(_R.BILLING_CLEARING, clearing_purpose=purpose) for purpose in ClearingPurpose),
    ),
    _account("2100", "Contract liability", _L, _R.CONTRACT_LIABILITY),
    _account("2105", "Deposit liability", _L, _R.DEPOSIT_LIABILITY),
    _account("2110", "Refund liability", _L, _R.REFUND_LIABILITY),
    _account("2200", "Sales tax payable", _L, _R.SALES_TAX_PAYABLE),
    _account("2300", "Provision for anticipated losses", _L, _R.LOSS_PROVISION),
    _account("2400", "Consideration payable to customers", _L, _R.CONSIDERATION_PAYABLE),
    _account("2600", "Assurance warranty provision", _L, _R.WARRANTY_PROVISION),
    _account("2800", "Intercompany due to", _L, _R.INTERCOMPANY_DUE_TO),
    _account(
        "4000", "Revenue - products", _REV, MappedRole(_R.REVENUE, revenue_category="PRODUCT")
    ),
    _account(
        "4010",
        "Revenue - services and subscriptions",
        _REV,
        MappedRole(_R.REVENUE, revenue_category="SUBSCRIPTION"),
        MappedRole(_R.REVENUE, revenue_category="SERVICES"),
    ),
    _account(
        "4020",
        "Revenue - licences and royalties",
        _REV,
        MappedRole(_R.REVENUE, revenue_category="LICENCE"),
        MappedRole(_R.REVENUE, revenue_category="ROYALTY"),
    ),
    _account(
        "4030",
        "Revenue - material rights and breakage",
        _REV,
        MappedRole(_R.REVENUE, revenue_category="MATERIAL_RIGHT"),
    ),
    _account("5000", "Cost of revenue", _EXP, _R.COST_OF_REVENUE),
    _account("5100", "Amortisation of contract costs", _EXP, _R.CONTRACT_COST_AMORTIZATION),
    _account("5200", "Warranty expense", _EXP, _R.WARRANTY_EXPENSE),
    _account("5300", "Anticipated loss expense", _EXP, _R.LOSS_EXPENSE),
    _account("6000", "Impairment of contract cost assets", _EXP, _R.CONTRACT_COST_IMPAIRMENT),
    # PRD §2.6 lists interest income with type Revenue: a credit-balance account.
    _account("7000", "Interest income", _REV, _R.INTEREST_INCOME),
    _account("7100", "Interest expense", _EXP, _R.INTEREST_EXPENSE),
    _account("7200", "Foreign exchange gain or loss", _EXP, _R.FX_GAIN_LOSS),
    _account("7900", "Rounding", _EXP, _R.ROUNDING),
)
MAPPING_NAME: Final = "AVM-MAP-2026-01"
MAPPING_NOTES: Final = (
    "Avenmoor chart of accounts (PRD §2.6). No rule for PRE_STANDARD_REVENUE (no LEGACY book) or "
    "RECEIVABLE_CONTRA (billing.posting = ERP)."
)

# --- customers (PRD §2.7) ------------------------------------------------------------------------

HOLLENBRAND: Final = "HOLLENBRAND"


@dataclass(frozen=True, slots=True)
class CustomerSpec:
    code: str
    name: str
    country_code: str
    source_system: SourceSystem | None
    external_id: str | None
    group: str | None = None


CUSTOMERS: Final[tuple[CustomerSpec, ...]] = (
    CustomerSpec(
        "WLD-C-01", "Pellworth Logistics Inc. (Demo)", "US", SourceSystem.SALESFORCE, "001DEMO0001"
    ),
    CustomerSpec(
        "WLD-C-02",
        "Marrowby Health Partners LLC (Demo)",
        "US",
        SourceSystem.SALESFORCE,
        "001DEMO0002",
    ),
    # [J] L4-5-Q-3: E-38 has no project-system literal; the project system integrates through API.
    CustomerSpec(
        "WLD-C-03", "Castellan Build Group Inc. (Demo)", "US", SourceSystem.API, "CB-2026"
    ),
    CustomerSpec(
        "WLD-C-04", "Saltmarsh Freight Ltd (Demo)", "GB", SourceSystem.SALESFORCE, "001DEMO0104"
    ),
    CustomerSpec(
        "WLD-C-05",
        "Hollenbrand Klinikbedarf GmbH (Demo)",
        "DE",
        SourceSystem.NETSUITE,
        "C-DE-3001",
        HOLLENBRAND,
    ),
    CustomerSpec(
        "WLD-C-06", "Drossel Fahrzeugtechnik GmbH (Demo)", "DE", SourceSystem.NETSUITE, "C-DE-3002"
    ),
    CustomerSpec(
        "WLD-C-07", "Fenwright Logistik AG (Demo)", "DE", SourceSystem.NETSUITE, "C-DE-3003"
    ),
    CustomerSpec(
        "WLD-C-08", "Ulvane Telematics Inc. (Demo)", "US", SourceSystem.SALESFORCE, "001DEMO0005"
    ),
    CustomerSpec(
        "WLD-C-09", "Orrin Vale Architects LLP (Demo)", "US", SourceSystem.SALESFORCE, "001DEMO0006"
    ),
    CustomerSpec("WLD-C-10", "Kumotori Media KK (Demo)", "JP", SourceSystem.NETSUITE, "C-JP-0001"),
    CustomerSpec(
        "WLD-C-11",
        "Hollenbrand Medizintechnik GmbH (Demo)",
        "DE",
        SourceSystem.NETSUITE,
        "C-DE-3004",
        HOLLENBRAND,
    ),
    CustomerSpec(
        "WLD-C-12", "Kinsley Marrow Foods Inc. (Demo)", "US", SourceSystem.SALESFORCE, "001DEMO0417"
    ),
    CustomerSpec("WLD-C-13", "Tamsin Row Hotels Inc. (Demo)", "US", None, None),
)

# --- products (PRD §2.6) -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProductSpec:
    code: str
    name: str
    revenue_category: str
    template_code: str | None  # the default revenue policy template (REQ-POL-001)
    unit_of_measure: str = "EA"


PRODUCTS: Final[tuple[ProductSpec, ...]] = (
    ProductSpec(
        "AVM-PLAT-ENT", "Platform, enterprise tier, 12 months", "SUBSCRIPTION", "TPL-SUB-DAILY"
    ),
    ProductSpec(
        "AVM-SEAT-MO",
        "Platform seat, per seat per month",
        "SUBSCRIPTION",
        "TPL-SUB-DAILY",
        "SEAT_MONTH",
    ),
    ProductSpec("AVM-PLAT-100", "Platform, 100 seats, 12 months", "SUBSCRIPTION", "TPL-SUB-DAILY"),
    ProductSpec("AVM-IMPL-STD", "Implementation, standard", "SERVICES", "TPL-SVC-PCT"),
    ProductSpec("AVM-IMPL-PLUS", "Implementation, extended scope", "SERVICES", "TPL-SVC-HOURS"),
    ProductSpec("AVM-API-CALL", "API calls (usage)", "SERVICES", "TPL-USAGE", "CALL"),
    ProductSpec("AVM-ENG-BUILD", "Engineered facility build", "SERVICES", "TPL-ENG-C2C"),
    ProductSpec("AVM-KIT", "Sensor kit", "PRODUCT", "TPL-PROD-PIT"),
    ProductSpec("AVM-PART", "Automotive sensor part", "PRODUCT", "TPL-PROD-PIT"),
    ProductSpec("AVM-GW", "Sensor gateway unit", "PRODUCT", "TPL-PROD-UNITS"),
    ProductSpec("AVM-FLEET", "Gateway fleet package", "PRODUCT", "TPL-PROD-PIT"),
    ProductSpec("AVM-SUP-12", "Platform support, 12 months", "SERVICES", "TPL-SUB-DAILY"),
    ProductSpec(
        "AVM-EXP-CREDIT", "Expansion credit (customer option)", "MATERIAL_RIGHT", "TPL-OPTION"
    ),
    ProductSpec(
        "AVM-PLAT-UK", "Platform, enterprise tier, 12 months (UK)", "SUBSCRIPTION", "TPL-SUB-DAILY"
    ),
    ProductSpec("AVM-IMPL-UK", "Implementation, UK standard", "SERVICES", "TPL-SVC-PCT"),
    ProductSpec("AVM-LIB-LIC", "Film library licence", "LICENCE", "TPL-LIC-FUNC"),
    # Not an obligation: a royalty variable-consideration element (REQ-REC-011).
    ProductSpec("AVM-ROYALTY", "Royalty on licensee streaming revenue", "ROYALTY", None),
)


# --- builder -------------------------------------------------------------------------------------


def _calendar(ctx: BuildContext, spec: CalendarSpec) -> UUID:
    with ctx.command(TENANT_ADMIN) as uow:
        created = commands.create_calendar(
            uow,
            body=CalendarIn(
                code=spec.code, name=spec.name, fiscal_year_start_month=spec.start_month
            ),
        )
    for year in spec.fiscal_years:
        with ctx.command(TENANT_ADMIN) as uow:
            commands.generate_year(
                uow, calendar_id=created.id, body=GenerateYearIn(fiscal_year=year)
            )
    return created.id


def _entity(ctx: BuildContext, spec: EntitySpec, calendar_id: UUID, parent_id: UUID | None) -> UUID:
    with ctx.command(TENANT_ADMIN) as uow:
        created = commands.create_entity(
            uow,
            body=EntityIn(
                code=spec.code,
                name=spec.name,
                functional_currency=spec.functional_currency,
                time_zone=spec.time_zone,
                calendar_id=calendar_id,
                parent_entity_id=parent_id,
                country_code=spec.country_code,
                first_period_key=spec.first_period_key,
            ),
        )
    for code in spec.books[1:]:
        _enable_tenant_book(ctx, code)
        with ctx.command(TENANT_ADMIN) as uow:
            commands.put_entity_book(
                uow,
                entity_id=created.id,
                code=code,
                body=EntityBookIn(is_enabled=True, first_period_key=spec.first_period_key),
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


def _open_periods(ctx: BuildContext, entity_code: str) -> None:
    """``marcus`` opens every future state of the entity from Jan 2026 to Sep 2026 (WLD-P-02 before
    CLO, BS3-D-09)."""
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


def _rate_sets(ctx: BuildContext) -> None:
    for rate_type, code, name in RATE_SETS:
        with ctx.command(ACCOUNTANT) as uow:
            created = commands.create_fx_rate_set(
                uow, body=FxRateSetIn(code=code, name=name, rate_type=rate_type)
            )
        with ctx.command(ACCOUNTANT) as uow:
            version = commands.create_fx_rate_set_version(
                uow,
                set_id=created.id,
                body=FxRateSetVersionIn(
                    coverage_from=COVERAGE_FROM, coverage_to=COVERAGE_TO, rates=rate_rows(rate_type)
                ),
            )
        with ctx.command(ACCOUNTANT) as uow:
            commands.submit_fx_rate_set_version(
                uow,
                version_id=version.id,
                body=FxRateSetVersionCommandIn(comment=SUBMIT_COMMENT),
                check_version=expect_version(version.row_version),
            )
        ctx.approve(ApprovalSubjectType.FX_RATE_SET_VERSION, version.id, [CONTROLLER])


def _chart_and_mapping(ctx: BuildContext) -> None:
    accounts: dict[str, UUID] = {}
    for spec in CHART:
        with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
            created = commands.create_gl_account(
                uow,
                body=GlAccountIn(
                    code=spec.code,
                    name=spec.name,
                    account_type=spec.account_type,
                    normal_balance=spec.normal_balance,
                ),
            )
        accounts[spec.code] = created.id
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        version_id = commands.create_account_mapping_version(
            uow,
            body=AccountMappingIn(
                name=MAPPING_NAME, notes=MAPPING_NOTES, effective_from=_midnight(GO_LIVE)
            ),
        )
    for spec in CHART:
        for mapped in spec.roles:
            with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
                commands.add_account_mapping_rule(
                    uow,
                    version_id,
                    body=AccountMappingRuleIn(
                        account_role=mapped.role,
                        clearing_purpose=mapped.clearing_purpose,
                        revenue_category=mapped.revenue_category,
                        gl_account_id=accounts[spec.code],
                    ),
                )
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.run_account_mapping_tests(uow, version_id)
    with ctx.command(ACCOUNTANT, CONFIG_AUTHOR) as uow:
        commands.submit_account_mapping_version(uow, version_id, comment=SUBMIT_COMMENT)
    ctx.approve(ApprovalSubjectType.ACCOUNT_MAPPING_VERSION, version_id, [CONTROLLER])


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _customers(ctx: BuildContext) -> None:
    with ctx.command(ACCOUNTANT, MASTERDATA_MAINTAIN) as uow:
        group = commands.create_related_party_group(
            uow,
            body=RelatedPartyGroupIn(
                code=HOLLENBRAND,
                name="Hollenbrand group (Demo)",
                description="Related purchasing entities of the Hollenbrand group.",
            ),
        )
    for spec in CUSTOMERS:
        with ctx.command(ACCOUNTANT, MASTERDATA_MAINTAIN) as uow:
            commands.create_customer(
                uow,
                body=CustomerIn(
                    code=spec.code,
                    name=spec.name,
                    country_code=spec.country_code,
                    related_party_group_id=group.id if spec.group == HOLLENBRAND else None,
                    source_system=spec.source_system,
                    external_id=spec.external_id,
                ),
            )


def _products(ctx: BuildContext) -> None:
    for spec in PRODUCTS:
        with ctx.command(ACCOUNTANT, MASTERDATA_MAINTAIN) as uow:
            commands.create_product(
                uow,
                body=ProductIn(
                    code=spec.code,
                    name=spec.name,
                    revenue_category=spec.revenue_category,
                    unit_of_measure=spec.unit_of_measure,
                ),
            )


def build(ctx: BuildContext) -> None:
    """PRD §2.5 to §2.7 reference data of WLD-T-01 (module docstring order)."""
    january = _calendar(ctx, JANUARY_CALENDAR)
    with ctx.command(TENANT_ADMIN, SETTINGS_MANAGE) as uow:
        commands.put_tenant_currencies(
            uow, body=TenantCurrenciesIn(currency_codes=list(TENANT_CURRENCIES))
        )
    parent: UUID | None = None
    for spec in ENTITIES:
        if spec.calendar is not JANUARY_CALENDAR:
            continue
        entity_id = _entity(ctx, spec, january, parent)
        parent = parent or entity_id
        _open_periods(ctx, spec.code)
    _rate_sets(ctx)
    april = _calendar(ctx, APRIL_CALENDAR)
    for spec in ENTITIES:
        if spec.calendar is APRIL_CALENDAR:
            _entity(ctx, spec, april, parent)
            _open_periods(ctx, spec.code)
    _chart_and_mapping(ctx)
    _customers(ctx)
    _products(ctx)


def entity_codes() -> Sequence[str]:
    return tuple(spec.code for spec in ENTITIES)

"""SSP resolution by effective date and named version (04 §15.3 API-R-26 ``GET /ssp/resolve``,
§16.4 API-S-SspResolution; ENGINE_SPEC Table 0.2-A, §5.3 S05-R-01 to S05-R-08; POLICIES §1.5
POL-070 to POL-072, §3.4 CHK-035; PRD WLD-X-23, WLD-X-25, J-02-AC-4, IMP-09; 03 REQ-SSP-006;
CTL-011; BUILD_SPEC RFD-14, BS3-D-06).

``resolve`` assembles one case bundle, runs stages 01 and 02 over it and calls
``s05_allocation.resolve_ssp`` for its one line; the engine owns every selection rule, so this
module changes no engine behaviour. The case bundle holds:

- one line of the requested product, quantity, stated price and stratification, booked on the
  requested date by the named legal entity (else the case entity ``SSP-RESOLVE``) in the requested
  currency;
- every APPROVED ``ssp_book_version`` with its entries and bands (T-REF-28 to T-REF-31). A version
  in any other status is never loaded (CTL-011); its ``approved_at`` is ``published_at``;
- every accounting parameter resolved through ``registry.resolve`` for the entity at the request
  instant (DG-KRN-REG-03); when ``book_version`` names a version, the POL-070 level O shape
  ``{option: NAMED_VERSION, version_label}`` for the line (L3-1-Q-12);
- the tenant preset ``LEGACY_PARITY`` when the TENANT accounting policy set in force carries it
  (S05-R-02 step 3).

[J] L3-1-Q-11: ``SSP_ASSIGNMENT`` rule sets (S05-R-02 step 1) and spot rates (S05-R-05) are not
loaded, so the book follows the scope members and an entry in another currency answers
``FX_RATE_MISSING``.

The read answers what a computation would take (item SSP-ENTITY-SCOPE-1; supervisor ruling
R-28): the versions are loaded under the tenant's scope, as ``contracts.bundles.build`` loads
them (05 TXN-10), so a book's scope entity is the stored one whoever asks. Read in the caller's
own session, a book of an entity the row policy hides showed no scope entity, and the engine
took it for a book of all entities: a member of one entity was answered the approved prices of
another entity's book — and, for her own entity, a book no computation selects — whenever that
book's code sorted first (S05-R-02: equal scope count, ascending code). The entity of the case
stays the caller's to name: one the session does not read, or one her ``ssp.read`` does not
cover, answers as an entity that does not exist; without an entity the case is booked by
``SSP-RESOLVE``, which no book of an entity matches.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
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
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    ssp_range_key,
)
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.dates import add_months, month_end
from erev_engine.enums import BookCode as EngineBookCode
from erev_engine.money import format_exact
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s05_allocation
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s03_pob_builder.templates import collect
from erev_engine.stages.state import BookContext, Finding, PolicyResolver
from erev_engine.trace import TraceBuilder
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.session import system_entity_scope, tenant_session
from erev_api.db.tables import (
    gl_account,
    legal_entity,
    product,
    registry_version,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
)
from erev_api.domain.policies import registry_versions
from erev_api.domain.policies.templates import engine_policy_value
from erev_api.domain.reference import fx
from erev_api.domain.ssp import scope
from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, RegistryScope
from erev_api.money import money_out
from erev_api.problems import Problem, ProblemError
from erev_api.registry import presets
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext

CASE_KEY: Final = "SSP-RESOLVE"  # contract, group, customer and default entity of the case
CASE_OBLIGATION: Final = "POB-01"
CASE_HORIZON_MONTHS: Final = 12
ZERO_SHA256: Final = "0" * 64
INSIDE_POLICY: Final = "ssp.inside_range_point"  # POL-071
OUTSIDE_POLICY: Final = "ssp.outside_range_point"  # POL-072
VERSION_BASIS: Final = "ssp.version_basis"  # POL-070
NAMED_VERSION: Final = "NAMED_VERSION"
REQUEST_SOURCE: Final = "GET /ssp/resolve book_version"
DEFAULT_PRESET: Final = "DEFAULT"
RULE_PRODUCT: Final = "T-REF-20"
RULE_ENTITY: Final = "T-REF-01"
RULE_MONEY: Final = "API-C-06"
RULE_QUANTITY: Final = "S03-R-04"
_IN_FORCE: Final = (ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value)
# [J] Copy the documents leave open; the not-found copy is PRD IMP-09.
PRODUCT_UNKNOWN: Final = "Choose an existing product."
ENTITY_UNKNOWN: Final = "Choose a legal entity of this workspace."
CURRENCY_UNKNOWN: Final = "Choose an active ISO 4217 currency."
QUANTITY_ZERO: Final = "Enter a quantity other than 0."
PRICE_NOT_EXACT: Final = "Enter the stated price with at most the currency's minor-unit decimals."
NOT_FOUND: Final = "No approved SSP for {product} / {stratification} / {version}."
RATE_MISSING: Final = "No spot rate converts {base} to {quote} on {date}."


def _exact(value: Fraction | None) -> str | None:
    return None if value is None else format_exact(value)


def _entry_key(version_key: str, row: Mapping[Any, Any]) -> str:
    """ENGINE_SPEC CV-22 ``<version_key>/<product_code>/<stratification>/<dims>/<currency>``."""
    dims = "|".join(str(row[name] or "") for name in _DIMENSIONS)
    return f"{version_key}/{row['product_code']}/{row['stratification']}/{dims}/{row['currency']}"


_DIMENSIONS: Final = ("region", "channel", "segment", "deal_size_band", "term_band")


def _entry_order(entry: SspEntryInput) -> tuple[str, ...]:
    """The stage 01 order of a version's entries (``_assert_reference_order``)."""
    return (
        entry.product_code,
        entry.stratification,
        entry.region or "",
        entry.channel or "",
        entry.segment or "",
        entry.deal_size_band or "",
        entry.term_band or "",
        entry.currency,
    )


def approved_versions(
    session: Session,
) -> tuple[tuple[SspVersionInput, ...], dict[str, Mapping[Any, Any]], dict[str, UUID]]:
    """Every APPROVED SSP book version as the engine reads it, in (book code, version number) order;
    with the platform rows by version key and the entry ids by entry key."""
    joined = ssp_book_version.join(
        ssp_book,
        and_(
            ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
            ssp_book.c.id == ssp_book_version.c.ssp_book_id,
        ),
    ).outerjoin(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == ssp_book.c.tenant_id,
            legal_entity.c.id == ssp_book.c.entity_id,
        ),
    )
    rows = (
        session.execute(
            select(
                ssp_book_version,
                ssp_book.c.code.label("book_code"),
                ssp_book.c.resolution_mode,
                ssp_book.c.currency.label("scope_currency"),
                ssp_book.c.channel.label("scope_channel"),
                ssp_book.c.segment.label("scope_segment"),
                legal_entity.c.code.label("scope_entity_code"),
            )
            .select_from(joined)
            .where(ssp_book_version.c.status == ConfigStatus.APPROVED.value)
        )
        .mappings()
        .all()
    )
    version_ids = [row["id"] for row in rows]
    entry_rows = (
        session.execute(
            select(
                ssp_entry,
                product.c.code.label("product_code"),
                gl_account.c.code.label("revenue_account_code"),
            )
            .select_from(
                ssp_entry.join(
                    product,
                    and_(
                        product.c.tenant_id == ssp_entry.c.tenant_id,
                        product.c.id == ssp_entry.c.product_id,
                    ),
                ).outerjoin(
                    gl_account,
                    and_(
                        gl_account.c.tenant_id == ssp_entry.c.tenant_id,
                        gl_account.c.id == ssp_entry.c.revenue_gl_account_id,
                    ),
                )
            )
            .where(ssp_entry.c.ssp_book_version_id.in_(version_ids))
        )
        .mappings()
        .all()
    )
    bands: dict[UUID, list[SspRangeInput]] = {}
    for band in session.execute(
        select(ssp_range).where(ssp_range.c.ssp_entry_id.in_([row["id"] for row in entry_rows]))
    ).mappings():
        bands.setdefault(UUID(str(band["ssp_entry_id"])), []).append(
            SspRangeInput(
                band_dimension=str(band["band_dimension"]),
                band_from=band["band_from"],
                band_to=band["band_to"],
                point_value=band["point_value"],
                low_value=band["low_value"],
                mid_value=band["mid_value"],
                high_value=band["high_value"],
            )
        )
    keys = {UUID(str(row["id"])): f"{row['book_code']}@v{row['version_no']}" for row in rows}
    entries: dict[UUID, list[SspEntryInput]] = {}
    entry_ids: dict[str, UUID] = {}
    for row in entry_rows:
        version_id = UUID(str(row["ssp_book_version_id"]))
        entry_key = _entry_key(keys[version_id], row)
        entry_ids[entry_key] = UUID(str(row["id"]))
        ranges = sorted(
            bands.get(UUID(str(row["id"])), ()),
            key=lambda r: (r.band_dimension, r.band_from is not None, r.band_from or Decimal(0)),
        )
        entries.setdefault(version_id, []).append(
            SspEntryInput(
                entry_key=entry_key,
                product_code=str(row["product_code"]),
                stratification=str(row["stratification"]),
                region=row["region"],
                channel=row["channel"],
                segment=row["segment"],
                deal_size_band=row["deal_size_band"],
                term_band=row["term_band"],
                currency=str(row["currency"]).strip(),
                method=str(row["method"]),
                value_basis=str(row["value_basis"]),
                quantity_unit=None if row["quantity_unit"] is None else str(row["quantity_unit"]),
                unit_list_price=row["unit_list_price"],
                midpoint_discount_ratio=row["midpoint_discount_ratio"],
                range_ratio=row["range_ratio"],
                cost_basis=row["cost_basis"],
                margin_ratio=row["margin_ratio"],
                distinctness=str(row["distinctness"]),
                # REQ-SSP-014: the entry's revenue account, which stage 05 merges below the line's
                # overrides (T-REF-15 step 1; END-6).
                revenue_account_code=row["revenue_account_code"],
                observable_point=row["observable_point"],
                ranges=tuple(ranges),
            )
        )
    versions: list[SspVersionInput] = []
    by_key: dict[str, Mapping[Any, Any]] = {}
    for row in rows:
        version_id = UUID(str(row["id"]))
        version_key = keys[version_id]
        by_key[version_key] = row
        currency = row["scope_currency"]
        versions.append(
            SspVersionInput(
                ssp_book_code=str(row["book_code"]),
                version_key=version_key,
                version_no=int(row["version_no"]),
                resolution_mode=str(row["resolution_mode"]),
                legacy_version_label=row["legacy_version_label"],
                effective_from_date=row["effective_from_date"],
                effective_to_date=row["effective_to_date"],
                status=ConfigStatus.APPROVED.value,
                approved_at=row["published_at"] or row["updated_at"],
                content_sha256=row["content_sha256"] or ZERO_SHA256,
                scope_entity_code=row["scope_entity_code"],
                scope_currency=None if currency is None else str(currency).strip(),
                scope_channel=row["scope_channel"],
                scope_segment=row["scope_segment"],
                entries=tuple(sorted(entries.get(version_id, ()), key=_entry_order)),
            )
        )
    ordered = tuple(sorted(versions, key=lambda v: (v.ssp_book_code, v.version_no)))
    return ordered, by_key, entry_ids


def tenant_preset(session: Session, *, known_at: datetime) -> str:
    """``LEGACY_PARITY`` when the TENANT accounting policy set in force at ``known_at`` carries that
    preset (REQ-POL-005), else ``DEFAULT``."""
    table = registry_version
    found = session.execute(
        select(table.c.preset_code)
        .where(
            table.c.category == RegistryCategory.ACCOUNTING_POLICY.value,
            table.c.scope == RegistryScope.TENANT.value,
            table.c.status.in_(_IN_FORCE),
            table.c.published_at <= known_at,
            (table.c.effective_from.is_(None)) | (table.c.effective_from <= known_at),
            (table.c.effective_to.is_(None)) | (table.c.effective_to > known_at),
        )
        .order_by(table.c.published_at.desc(), table.c.version_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    return presets.LEGACY_PARITY if found == presets.LEGACY_PARITY else DEFAULT_PRESET


def case_policies(
    session: Session,
    *,
    entity_id: UUID | None,
    calendar: EntityInput,
    known_at: datetime,
    book_version: str | None,
) -> tuple[ResolvedPolicyInput, ...]:
    """Every accounting parameter of the ASC606 book resolved for the entity at ``known_at``
    (DG-KRN-REG-03): pin K at the GROUP scope, pin P per case period."""
    resolved: list[ResolvedPolicyInput] = []
    for code, spec in sorted(POLICY_PARAMETERS.items()):
        found = registry.resolve(
            session, code, book_code=BookCode.ASC606, entity_id=entity_id, known_at=known_at
        )
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
    if book_version is not None:
        resolved.append(
            ResolvedPolicyInput(
                VERSION_BASIS,
                "OBLIGATION",
                obligation_subject_key(CASE_KEY, CASE_OBLIGATION),
                {"option": NAMED_VERSION, "version_label": book_version},
                "O",
                REQUEST_SOURCE,
                "K",
            )
        )
    return tuple(sorted(resolved, key=lambda p: (p.code, p.scope, p.subject_key)))


def _calendar(code: str, currency: str, at: date) -> EntityInput:
    """Monthly open ASC606 periods from the month of ``at`` (the case horizon)."""
    periods: list[PeriodInput] = []
    start = date(at.year, at.month, 1)
    for _ in range(CASE_HORIZON_MONTHS):
        periods.append(
            PeriodInput(
                period_key=f"FY{start.year}-P{start.month:02d}",
                fiscal_year=start.year,
                period_no=start.month,
                start_date=start,
                end_date=month_end(start),
                states=((BookCode.ASC606.value, "open"),),
            )
        )
        start = add_months(start, 1)
    return EntityInput(code, currency, "UTC", "MONTHLY", tuple(periods))


def _product_input(row: Mapping[Any, Any]) -> ProductInput:
    """The requested product without a template, bundle components or level P values: the case
    prices the line itself (S05-R-04)."""
    return ProductInput(
        code=str(row["code"]),
        sku_number=row["sku_number"],
        product_family=row["product_family"],
        revenue_category=row["revenue_category"],
        default_template_code=None,
        principal_agent=str(row["principal_agent"]),
        distinctness_default=str(row["distinctness_default"]),
        unit_of_measure=str(row["unit_of_measure"]),
        is_bundle=False,
        policy_values={},
        assurance_cost_per_unit=row["assurance_cost_per_unit"],
        components=(),
        is_franchisor_preopening_service=bool(row["is_franchisor_preopening_service"]),
    )


def _header(entity_code: str, currency: str, at: date) -> ContractInput:
    return ContractInput(
        external_id=CASE_KEY,
        customer_code=CASE_KEY,
        related_party_group=None,
        contracting_entity_code=entity_code,
        transaction_currency=currency,
        inception_date=at,
        signature_date=at,
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


def _problem(findings: Sequence[Finding], at: date) -> Problem:
    """422 ``validation-failed`` for the first blocking finding (ENGINE_SPEC Table 0.8-A)."""
    blocking = sorted(
        (finding for finding in findings if finding.severity == "ERROR"), key=Finding.sort_key
    )
    first = blocking[0]
    detail = first.detail
    if first.code == "FX_RATE_MISSING":
        message = RATE_MISSING.format(
            base=detail.get("base_currency", ""),
            quote=detail.get("quote_currency", ""),
            date=detail.get("pricing_date", at.isoformat()),
        )
        return Problem(
            "validation-failed",
            errors=[ProblemError(field="currency", rule_id=first.code, message=message)],
        )
    message = NOT_FOUND.format(
        product=detail.get("product_code", ""),
        stratification=detail.get("stratification") or "-",
        version=detail.get("ssp_version_label") or at.isoformat(),
    )
    return Problem(
        "validation-failed",
        errors=[ProblemError(field="product", rule_id=first.code, message=message)],
    )


def resolve(
    ctx: RequestContext,
    *,
    product_code: str,
    at: date,
    currency: str,
    quantity: Decimal,
    stated_price: Decimal | None,
    stratification: str | None,
    book_version: str | None,
    entity_ref: str | None,
) -> dict[str, Any]:
    """API-S-SspResolution of one line priced at ``at`` (S05-R-01 to S05-R-08).

    422 ``validation-failed`` collects an unknown product, entity or currency, a zero quantity and a
    stated price that is not exact at the minor unit; then ``SSP_KEY_NOT_FOUND`` (product,
    stratification and version label or date, PRD IMP-09) or ``FX_RATE_MISSING``.
    """
    known_at = ctx.now
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        errors: list[ProblemError] = []
        found_product = (
            session.execute(select(product).where(product.c.code == product_code))
            .mappings()
            .one_or_none()
        )
        if found_product is None:
            errors.append(
                ProblemError(field="product", rule_id=RULE_PRODUCT, message=PRODUCT_UNKNOWN)
            )
        entity_id: UUID | None = None
        entity_code = CASE_KEY
        if entity_ref is not None:
            try:
                condition = legal_entity.c.id == UUID(entity_ref)
            except ValueError:
                condition = legal_entity.c.code == entity_ref
            entity_row = session.execute(
                select(legal_entity.c.id, legal_entity.c.code).where(condition)
            ).one_or_none()
            if entity_row is None or not scope.reaches(ctx.principal, scope.READ, entity_row.id):
                errors.append(
                    ProblemError(field="entity", rule_id=RULE_ENTITY, message=ENTITY_UNKNOWN)
                )
            else:
                entity_id, entity_code = UUID(str(entity_row.id)), str(entity_row.code)
        if currency not in ISO_4217 or currency not in fx.active_currencies(session, [currency]):
            errors.append(
                ProblemError(field="currency", rule_id=RULE_MONEY, message=CURRENCY_UNKNOWN)
            )
        if quantity == 0:
            errors.append(
                ProblemError(field="quantity", rule_id=RULE_QUANTITY, message=QUANTITY_ZERO)
            )
        stated = None
        if stated_price is not None and currency in ISO_4217:
            try:
                stated = money_out(stated_price, currency, {currency: ISO_4217[currency]})
            except ValueError:
                errors.append(
                    ProblemError(field="stated_price", rule_id=RULE_MONEY, message=PRICE_NOT_EXACT)
                )
        if errors or found_product is None:
            raise Problem("validation-failed", errors=errors)

        with system_entity_scope(session):
            # As the bundle reads them: a book's scope entity is the stored one whoever asks.
            versions, by_key, entry_ids = approved_versions(session)
        calendar = _calendar(entity_code, currency, at)
        policies = case_policies(
            session,
            entity_id=entity_id,
            calendar=calendar,
            known_at=known_at,
            book_version=book_version,
        )
        book = BookInput(
            BookCode.ASC606.value,
            True,
            (entity_code,),
            policies,
            AccountMappingInput(f"{CASE_KEY}@v0", ZERO_SHA256, ()),
        )
        header = _header(entity_code, currency, at)
        line: dict[str, object] = {
            "obligation_key": CASE_OBLIGATION,
            "product_code": product_code,
            "quantity": quantity,
            "total_price": Decimal(0) if stated_price is None else stated_price,
        }
        if stratification is not None:
            line["stratification"] = stratification
        if book_version is not None:
            line["ssp_version_label"] = book_version
        payload: dict[str, object] = {"lines": [line]}
        booked = EventInput(
            event_key=f"{CASE_KEY}/EV-000001",
            contract_key=CASE_KEY,
            stream_version=1,
            event_type="CONTRACT_BOOKED",
            schema_version=1,
            effective_date=at,
            recorded_at=known_at,
            record_seq=1,
            origin="API",
            is_manual=False,
            obligation_keys=(CASE_OBLIGATION,),
            payload=payload,
            payload_sha256=sha256_hex(payload),
            idempotency_key=None,
            supersedes_event_key=None,
            modification_key=None,
            estimate_version_key=None,
            manual_adjustment_key=None,
        )
        preset = tenant_preset(session, known_at=known_at)
        bundle = InputBundle(
            format_version=1,
            engine_version=ENGINE_VERSION,
            trigger="DRY_RUN",
            known_at=known_at,
            tenant_preset=preset,
            currencies={currency: ISO_4217[currency]},
            books=(book,),
            entities=(calendar,),
            group=GroupInput(
                group_key=CASE_KEY,
                transaction_currency=currency,
                inception_date=at,
                member_contract_keys=(CASE_KEY,),
                criterion=None,
                previous_stream_heads=(),
                products=(_product_input(found_product),),
                portfolios=(),
            ),
            contracts=(header,),
            events=(booked,),
            ssp_versions=versions,
            pob_template_versions=(),
            rule_set_versions=(),
            estimate_versions=(),
            fx_rates=(),
            posted=(),
        )
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        canonical = s01_canonicalize.run(bundle, tb)
        engine_ctx = BookContext(
            book_code=EngineBookCode.ASC606,
            framework=EngineBookCode.ASC606,
            currencies=bundle.currencies,
            txn_currency=currency,
            entities={entity_code: calendar},
            horizon={entity_code: calendar.periods[-1].period_key},
            policies=PolicyResolver(book.policies),
            mapping=book.account_mapping,
            trigger=bundle.trigger,
            tenant_preset=preset,
        )
        identified = s02_contract_identification.run(engine_ctx, canonical, tb)
        raw = collect(identified, CASE_KEY, line, pricing_date=at, template_date=at, truncations={})
        findings: list[Finding] = []
        price = None if stated_price is None else Fraction(stated_price)
        found = s05_allocation.resolve_ssp(
            engine_ctx, raw, at, price, findings=findings, identified=identified
        )
        if found is None:
            raise _problem(findings, at)
        version = by_key[found.version_key]
        sources = {
            name: registry_versions.resolution(
                session, key=code, book_code=BookCode.ASC606, entity_id=entity_id, known_at=known_at
            )
            for name, code in (
                ("inside_range_point", INSIDE_POLICY),
                ("outside_range_point", OUTSIDE_POLICY),
            )
        }
        return {
            "ssp_book_version": {
                "id": version["id"],
                "book_code": found.book_code,
                "version_no": version["version_no"],
                "legacy_version_label": version["legacy_version_label"],
            },
            "ssp_entry_id": entry_ids[found.entry_key],
            "method": found.method,
            "low": _exact(found.low),
            "mid": _exact(found.mid),
            "high": _exact(found.high),
            "stated_price": None if stated is None else stated.model_dump(),
            "in_range": found.in_range,
            "selected_ssp": format_exact(found.selected),
            "policy_sources": {
                name: {
                    "value": source["value"],
                    "level": source["level"],
                    "source_id": source["source"]["id"],
                }
                for name, source in sources.items()
            },
        }


def approved_range_ids(session: Session, entry_ids: Mapping[str, UUID]) -> dict[str, UUID]:
    """Resolve only bands belonging to the approved entries included in the bundle index."""
    keys = {value: key for key, value in entry_ids.items()}
    return {
        ssp_range_key(keys[row.ssp_entry_id], row.band_dimension, row.band_from): row.id
        for row in session.execute(
            select(
                ssp_range.c.id,
                ssp_range.c.ssp_entry_id,
                ssp_range.c.band_dimension,
                ssp_range.c.band_from,
            ).where(ssp_range.c.ssp_entry_id.in_(keys))
        )
    }

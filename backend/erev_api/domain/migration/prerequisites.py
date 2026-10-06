"""LM-CL-09 / LM-CL-03 CONFIRMED entity and product writers of the opening-balance import (04 §17.2
rev 1.64; D-98 candidate 133; BUILD_SPEC LMG-2 rev 1.11; SCREENS_B §10.3 "Entity mapping"; lane
record §26).

``resolve_entities`` runs at ``POST /migrations/{id}/import`` (the confirmation): for every
"Will be created" selling entity it resolves the inputs the legacy mapping does not carry —
``functional_currency`` = the tenant reporting currency, ``calendar_id`` = the tenant's ONLY fiscal
calendar when exactly one exists else the confirmed value (per entity, else the batch default),
``time_zone`` = the confirmed value — and refuses by name, one finding per unresolvable entity; no
value is invented. The resolved rows travel in the ``MIGRATION_IMPORT`` job's params as the
confirmation (captured once with the cutover, D-98 candidate 128).

``plan`` runs in the import phase over the staging and the confirmed rows: entities still absent and
products still absent (``create_missing_products``: ``name = code``, ``default_pob_template_id`` =
the row's parity template, and — rev 1.66, integrated batch #6 test-pg return — ``principal_agent =
PRINCIPAL`` with the ``LEGACY_PARITY`` product-level policy values exactly as LM-SSP-02 creates a
legacy SKU, unconditionally: legacy SKUs carry no agent concept, and S03-R-09 otherwise blocks the
activated migrated contract with the CV-15 finding ``PRINCIPAL_AGENT_NOT_ASSESSED``; a SKU mapped to
two templates is refused by name before any write; with the flag false a missing product is a named
refusal, never a silent skip). ``apply`` creates them
through the reference writers (``create_entity`` / ``create_product`` — AUD-CMD each) in the import
job's OUTER transaction, before the dry run, under the job's principal (``masterdata.maintain``),
idempotent by code (an existing row is never updated), and writes ONE
``migration_batch.prerequisites`` audit event listing what the batch created.
``capture.PlatformApplier._check_prerequisites`` is unchanged: a product with another default
template or a disabled reporting currency is still refused.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select, update

from erev_api.db.tables import (
    approval_request,
    fiscal_calendar,
    gl_account,
    legal_entity,
    period,
    pob_template,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    tenant,
)
from erev_api.domain.imports.legacy_v1.sku_ssp import product_parity_values
from erev_api.domain.migration import legacy_db
from erev_api.domain.migration.opening_balances import Staging
from erev_api.domain.reference.commands import create_entity, create_gl_account, create_product
from erev_api.domain.ssp import publication
from erev_api.domain.ssp.commands import (
    create_ssp_book,
    create_ssp_book_version,
    upsert_ssp_entries,
)
from erev_api.enums import (
    AccountType,
    ApprovalRequestStatus,
    Distinctness,
    PrincipalAgent,
    SourceSystem,
    SspMethod,
)
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.entities import EntityIn
from erev_api.schemas.products import ProductIn
from erev_api.schemas.ssp_books import SspBookIn, SspBookVersionIn, SspEntriesIn, SspEntryIn
from erev_api.uow import UnitOfWork

__all__ = [
    "OBJECT_TYPE",
    "PREREQUISITES_ACTION",
    "RULE",
    "Applied",
    "EntityPlan",
    "PrerequisitePlan",
    "ProductPlan",
    "ResolvedEntity",
    "apply",
    "plan",
    "resolve_entities",
]

RULE: Final = "LM-CL-09"
PRODUCT_RULE: Final = "LM-CL-03"
OBJECT_TYPE: Final = "migration_batch"
PREREQUISITES_ACTION: Final = "migration_batch.prerequisites"
WILL_BE_CREATED: Final = "Will be created"
MATCHED: Final = "Matched"
# SCREENS_B §10.3 validation copy (D-98 candidate 133)
NO_CALENDAR_COPY: Final = "Choose a calendar for {name}."
NO_TIME_ZONE_COPY: Final = "Choose a time zone for {name}."
UNKNOWN_CALENDAR_COPY: Final = "Calendar {calendar_id} is not a fiscal calendar of this workspace."
CALENDAR_WITHOUT_PERIODS_COPY: Final = "Calendar {code!r} has no periods; generate a year first."
ENTITY_NOT_IN_SOURCE_COPY: Final = (
    "Entity mapping names {name!r}, which is not a selling entity of the legacy database."
)
TEMPLATE_CONFLICT_COPY: Final = (
    "SKU {sku} maps to two templates ({first}, {second}); resolve it in the legacy database "
    "before importing."
)
TEMPLATE_MISSING_COPY: Final = (
    "The parity template {code!r} is not in this workspace; the product {sku!r} cannot be created."
)
PRODUCT_MISSING_COPY: Final = (
    "Product {sku!r} is not in this workspace and create_missing_products is false (S07-R-03)."
)
SHARED_TARGET_CONFLICT_COPY: Final = (
    "Rows mapped to entity code {code!r} disagree on the {what} ({first!r} vs {second!r}); "
    "confirm one {what} for that entity."
)
ENTITY_MISSING_COPY: Final = (
    "Entity {code!r} is not in this workspace and create_missing_entities is false (S07-R-03)."
)


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    """One confirmed "Will be created" entity with every input the writer needs (04 LM-CL-09)."""

    legacy_name: str
    code: str
    functional_currency: str
    calendar_id: UUID
    time_zone: str

    def as_params(self) -> dict[str, str]:
        return {
            "legacy_name": self.legacy_name,
            "entity_code": self.code,
            "functional_currency": self.functional_currency,
            "calendar_id": str(self.calendar_id),
            "time_zone": self.time_zone,
        }


@dataclass(frozen=True, slots=True)
class EntityPlan:
    code: str
    name: str
    functional_currency: str
    calendar_id: UUID
    time_zone: str


@dataclass(frozen=True, slots=True)
class ProductPlan:
    code: str
    template_code: str
    template_id: UUID
    distinctness: str
    # rev 1.66 (batch #6 return): LM-SSP-02's parity values — never the ProductIn defaults
    principal_agent: str = PrincipalAgent.PRINCIPAL.value
    policy_values: Mapping[str, Any] = field(default_factory=product_parity_values)


@dataclass(frozen=True, slots=True)
class SspEntryPlan:
    """One ``SKU_SSP`` row as a LEGACY-SKU-SSP entry (04 §17.3 LM-SSP-01..09; rev 1.72)."""

    product_code: str
    stratification: str
    distinctness: str
    unit_list_price: str
    midpoint_discount_ratio: str
    range_ratio: str
    revenue_account_code: str | None


@dataclass(frozen=True, slots=True)
class SspVersionPlan:
    """One LEGACY-SKU-SSP version per distinct ``SSP Version`` label (LM-SSP-08); ``existing_id``
    names an
    equal APPROVED version already in the tenant (reused, never rewritten)."""

    label: str
    entries: tuple[SspEntryPlan, ...]
    existing_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PrerequisitePlan:
    entities: tuple[EntityPlan, ...]
    products: tuple[ProductPlan, ...]
    ssp_versions: tuple[SspVersionPlan, ...] = ()
    revenue_accounts: tuple[str, ...] = ()  # LM-SSP-09: created when absent

    @property
    def empty(self) -> bool:
        return (
            not self.entities
            and not self.products
            and not self.ssp_versions
            and not self.revenue_accounts
        )


@dataclass(frozen=True, slots=True)
class Applied:
    entity_ids: Mapping[str, UUID] = field(default_factory=dict)  # code → legal_entity.id
    product_ids: Mapping[str, UUID] = field(default_factory=dict)  # code → product.id
    ssp_version_ids: Mapping[str, UUID] = field(default_factory=dict)  # label → ssp_book_version.id
    ssp_entry_counts: Mapping[str, int] = field(default_factory=dict)  # label → entries
    ssp_reused: tuple[str, ...] = ()  # labels whose equal APPROVED version already existed

    @property
    def empty(self) -> bool:
        return not self.entity_ids and not self.product_ids and not self.ssp_version_ids

    def replayed_ssp_versions(self, source_sha256: str) -> list[dict[str, Any]]:
        """The profile's ``replayed_ssp_versions`` (04 §16.10 rev 1.72): what the
        MIGRATION_PROMOTION
        content will name — label, version id, entry count, source digest."""
        return [
            {
                "legacy_version_label": label,
                "ssp_book_version_id": str(version_id),
                "entry_count": int(self.ssp_entry_counts.get(label, 0)),
                "source_sha256": source_sha256,
                "reused": label in self.ssp_reused,
            }
            for label, version_id in sorted(self.ssp_version_ids.items())
        ]


# ---- the confirmation at /import ----------------------------------------------------------------


def _validation(errors: list[ProblemError]) -> Problem:
    count = len(errors)
    return Problem(
        "validation-failed",
        f"{count} field{'s' if count != 1 else ''} need{'s' if count == 1 else ''} attention.",
        errors=errors,
    )


def reporting_currency(session: Any, tenant_id: UUID) -> str:
    """The tenant reporting currency — the functional currency of every created entity."""
    return str(
        session.execute(
            select(tenant.c.reporting_currency).where(tenant.c.id == tenant_id)
        ).scalar_one()
    ).strip()


def tenant_calendars(session: Any) -> dict[UUID, str]:
    """``{id: code}`` of the tenant's fiscal calendars (RLS-scoped)."""
    rows = session.execute(select(fiscal_calendar.c.id, fiscal_calendar.c.code)).all()
    return {UUID(str(row[0])): str(row[1]) for row in rows}


def calendars_with_periods(session: Any, calendar_ids: Iterable[UUID]) -> set[UUID]:
    wanted = sorted(set(calendar_ids))
    if not wanted:
        return set()
    rows = session.execute(
        select(period.c.calendar_id).where(period.c.calendar_id.in_(wanted)).distinct()
    ).all()
    return {UUID(str(row[0])) for row in rows}


def existing_entity_codes(session: Any, codes: Iterable[str]) -> set[str]:
    wanted = sorted(set(codes))
    if not wanted:
        return set()
    rows = session.execute(select(legal_entity.c.code).where(legal_entity.c.code.in_(wanted))).all()
    return {str(row[0]) for row in rows}


def selling_entities(staging: Staging) -> tuple[str, ...]:
    """The legacy ``Selling Entity`` texts of the staged contracts, sorted (LM-CL-09 exact text)."""
    return tuple(sorted({contract.entity_code for contract in staging.contracts}))


def resolve_entities(
    session: Any,
    *,
    tenant_id: UUID,
    staging: Staging,
    entity_mapping: Sequence[Mapping[str, Any]],
    entity_defaults: Mapping[str, Any] | None,
    create_missing_entities: bool,
) -> tuple[ResolvedEntity, ...]:
    """The confirmation step of ``POST /migrations/{id}/import`` (D-98 candidate 133).

    Every confirmed row must name a selling entity of the legacy database, and EVERY selling
    entity of the source is confirmed (Codex 1106 R2): a name without a submitted row is the
    identity mapping (legacy text = code) resolved from ``entity_defaults`` — a partial or omitted
    mapping never queues an unresolved entity. For each row whose
    entity code is absent from the tenant ("Will be created"): ``functional_currency`` = the tenant
    reporting currency; ``calendar_id`` = the row's value, else ``entity_defaults.calendar_id``,
    else the tenant's ONLY calendar when exactly one exists; ``time_zone`` = the row's value, else
    the default. Missing or unknown inputs are refused by name, ONE finding per entity per field; a
    calendar without periods is refused (the writer keeps the primary book from the earliest
    period).
    Rows sharing a TARGET code — an explicit row plus the implicit identity row of that code, or
    two explicit rows — are ONE entity, created once and NAMED BY ITS CODE; their confirmed
    calendar / time zone must agree, else the submitted row is refused by name (Codex 1227 F2).
    With ``create_missing_entities`` false an absent entity is a named S07-R-03 refusal.
    """
    known = selling_entities(staging)
    defaults = dict(entity_defaults or {})
    calendars = tenant_calendars(session)
    only_calendar = next(iter(calendars)) if len(calendars) == 1 else None
    # Codex 1106 R2: the confirmation covers EVERY selling entity of the source — a row that was
    # not submitted is the identity mapping (exact legacy text = entity code, LM-CL-09) resolved
    # from the batch defaults; its findings are named on ``entity_defaults`` with the entity in the
    # copy
    submitted = {str(row["legacy_name"]) for row in entity_mapping}
    rows: list[tuple[str, Mapping[str, Any]]] = [
        (f"entity_mapping[{index}]", row) for index, row in enumerate(entity_mapping)
    ]
    rows.extend(
        ("entity_defaults", {"legacy_name": name, "entity_code": name})
        for name in known
        if name not in submitted
    )
    codes = [str(row["entity_code"]) for _field, row in rows]
    present = existing_entity_codes(session, codes)
    currency = reporting_currency(session, tenant_id)
    errors: list[ProblemError] = []
    resolved: list[tuple[str, ResolvedEntity]] = []
    for field_prefix, row in rows:
        name = str(row["legacy_name"])
        code = str(row["entity_code"])
        if name not in known:
            errors.append(
                ProblemError(
                    field=f"{field_prefix}.legacy_name",
                    rule_id=RULE,
                    message=ENTITY_NOT_IN_SOURCE_COPY.format(name=name),
                )
            )
            continue
        if code in present:
            continue  # "Matched": nothing to resolve, nothing to create
        if not create_missing_entities:
            errors.append(
                ProblemError(
                    field=f"{field_prefix}.entity_code",
                    rule_id="S07-R-03",
                    message=ENTITY_MISSING_COPY.format(code=code),
                )
            )
            continue
        calendar_raw = row.get("calendar_id") or defaults.get("calendar_id") or only_calendar
        time_zone = row.get("time_zone") or defaults.get("time_zone")
        if calendar_raw is None:
            errors.append(
                ProblemError(
                    field=f"{field_prefix}.calendar_id",
                    rule_id=RULE,
                    message=NO_CALENDAR_COPY.format(name=name),
                )
            )
        else:
            calendar_id = UUID(str(calendar_raw))
            if calendar_id not in calendars:
                errors.append(
                    ProblemError(
                        field=f"{field_prefix}.calendar_id",
                        rule_id=RULE,
                        message=UNKNOWN_CALENDAR_COPY.format(calendar_id=calendar_id),
                    )
                )
                calendar_raw = None
        if not time_zone:
            errors.append(
                ProblemError(
                    field=f"{field_prefix}.time_zone",
                    rule_id=RULE,
                    message=NO_TIME_ZONE_COPY.format(name=name),
                )
            )
        if calendar_raw is not None and time_zone:
            resolved.append(
                (
                    field_prefix,
                    ResolvedEntity(
                        legacy_name=name,
                        code=code,
                        functional_currency=currency,
                        calendar_id=UUID(str(calendar_raw)),
                        time_zone=str(time_zone),
                    ),
                )
            )
    consolidated = _consolidate(resolved, errors)
    if not errors:
        with_periods = calendars_with_periods(
            session, (entity.calendar_id for entity in consolidated)
        )
        for entity in consolidated:
            if entity.calendar_id not in with_periods:
                errors.append(
                    ProblemError(
                        field="entity_mapping",
                        rule_id=RULE,
                        message=CALENDAR_WITHOUT_PERIODS_COPY.format(
                            code=calendars.get(entity.calendar_id, str(entity.calendar_id))
                        ),
                    )
                )
    if errors:
        raise _validation(errors)
    return tuple(consolidated)


def _consolidate(
    resolved: Sequence[tuple[str, ResolvedEntity]], errors: list[ProblemError]
) -> tuple[ResolvedEntity, ...]:
    """Codex 1227 F2: rows sharing a TARGET code are ONE entity. The first row of a code stands;
    a later row of the same code must carry the same calendar and time zone — a disagreeing
    SUBMITTED row is refused by name, one finding per differing field (an implicit identity row
    has no field of its own: the submitted row is named) — and the consolidated entity is NAMED BY
    ITS CODE, deterministic whatever the order of the rows."""
    consolidated: list[ResolvedEntity] = []
    index_by_code: dict[str, int] = {}
    prefix_by_code: dict[str, str] = {}
    for prefix, entity in resolved:
        index = index_by_code.get(entity.code)
        if index is None:
            index_by_code[entity.code] = len(consolidated)
            prefix_by_code[entity.code] = prefix
            consolidated.append(entity)
            continue
        earlier = consolidated[index]
        named = prefix if prefix != "entity_defaults" else prefix_by_code[entity.code]
        disagreements = [
            (field_name, "calendar", str(earlier.calendar_id), str(entity.calendar_id))
            for field_name in ("calendar_id",)
            if earlier.calendar_id != entity.calendar_id
        ] + [
            (field_name, "time zone", earlier.time_zone, entity.time_zone)
            for field_name in ("time_zone",)
            if earlier.time_zone != entity.time_zone
        ]
        for field_name, what, first, second in disagreements:
            errors.append(
                ProblemError(
                    field=f"{named}.{field_name}",
                    rule_id=RULE,
                    message=SHARED_TARGET_CONFLICT_COPY.format(
                        code=entity.code, what=what, first=first, second=second
                    ),
                )
            )
        if not disagreements:
            consolidated[index] = replace(earlier, legacy_name=earlier.code)
    return tuple(consolidated)


# ---- the import phase: plan and apply -----------------------------------------------------------


def _refuse(detail: str, *, rule: str, field_name: str = "migration_id") -> Problem:
    return Problem(
        "invalid-transition",
        detail,
        errors=[ProblemError(field=field_name, rule_id=rule, message=detail)],
    )


def product_templates(staging: Staging) -> dict[str, tuple[str, str]]:
    """``{sku: (template_code, distinctness)}`` over the staged rows; a SKU mapped to two templates
    is refused by name BEFORE any write (LM-CL-03 rev 1.64)."""
    found: dict[str, tuple[str, str]] = {}
    for contract in staging.contracts:
        for row in contract.rows:
            sku = row.mapped.product_code
            pair = (row.mapped.template_code, row.mapped.distinctness)
            earlier = found.get(sku)
            if earlier is not None and earlier[0] != pair[0]:
                raise _refuse(
                    TEMPLATE_CONFLICT_COPY.format(sku=sku, first=earlier[0], second=pair[0]),
                    rule=PRODUCT_RULE,
                )
            found.setdefault(sku, pair)
    return found


def plan(
    session: Any,
    staging: Staging,
    *,
    resolved_entities: Sequence[Mapping[str, Any]],
    create_missing_entities: bool,
    create_missing_products: bool,
    sku_ssp_rows: Sequence[Mapping[str, str | None]] = (),
) -> PrerequisitePlan:
    """What the import phase creates: the confirmed entities still absent (idempotent — a code that
    now exists is skipped) and the staged SKUs absent from ``product`` with their parity templates.
    A missing template or, with the flag false, a missing product is a named refusal."""
    entities: list[EntityPlan] = []
    codes = [str(row["entity_code"]) for row in resolved_entities]
    present = existing_entity_codes(session, codes) if codes else set()
    planned: set[str] = set()
    for row in resolved_entities:
        code = str(row["entity_code"])
        if code in present or code in planned:  # Codex 1227 F2: one entity per code, never twice
            continue
        planned.add(code)
        if not create_missing_entities:
            raise _refuse(ENTITY_MISSING_COPY.format(code=code), rule="S07-R-03")
        entities.append(
            EntityPlan(
                code=code,
                name=str(row["legacy_name"]),
                functional_currency=str(row["functional_currency"]),
                calendar_id=UUID(str(row["calendar_id"])),
                time_zone=str(row["time_zone"]),
            )
        )
    wanted = product_templates(staging)
    skus = sorted(wanted)
    # FLMG-SSP-EXISTING-PRODUCT-1 (Codex 0644 §2): ONE existence query over the COMPLETE
    # population — the staged Contract_Live SKUs AND every SKU_SSP SKU — so a product found only in
    # SKU_SSP that already exists is KNOWN (kept: identity and facts unchanged, never recreated)
    # and only an ABSENT SKU is planned (LM-SSP-02 rev 1.72)
    ssp_skus = sorted({str(row.get(_SSP_SKU) or "") for row in sku_ssp_rows} - {""})
    all_skus = sorted(set(skus) | set(ssp_skus))
    existing = (
        {
            str(r[0])
            for r in session.execute(
                select(product.c.code).where(product.c.code.in_(all_skus))
            ).all()
        }
        if all_skus
        else set()
    )
    missing = [sku for sku in skus if sku not in existing]
    products: list[ProductPlan] = []
    if missing:
        if not create_missing_products:
            raise _refuse(PRODUCT_MISSING_COPY.format(sku=missing[0]), rule="S07-R-03")
        template_codes = sorted({wanted[sku][0] for sku in missing})
        templates = {
            str(r[1]): UUID(str(r[0]))
            for r in session.execute(
                select(pob_template.c.id, pob_template.c.code).where(
                    pob_template.c.code.in_(template_codes)
                )
            ).all()
        }
        for sku in missing:
            template_code, distinctness = wanted[sku]
            template_id = templates.get(template_code)
            if template_id is None:
                raise _refuse(
                    TEMPLATE_MISSING_COPY.format(code=template_code, sku=sku), rule=PRODUCT_RULE
                )
            products.append(
                ProductPlan(
                    code=sku,
                    template_code=template_code,
                    template_id=template_id,
                    distinctness=distinctness,
                    # LM-SSP-02's parity values (rev 1.66): PRINCIPAL — legacy SKUs carry no agent
                    # concept — and the LEGACY_PARITY product-level policy values, unconditionally
                    principal_agent=PrincipalAgent.PRINCIPAL.value,
                    policy_values=product_parity_values(),
                )
            )
    ssp_versions, ssp_products, accounts = _plan_ssp_replay(
        session, sku_ssp_rows, {p.code for p in products} | existing
    )
    return PrerequisitePlan(
        entities=tuple(entities),
        products=tuple(products) + ssp_products,
        ssp_versions=ssp_versions,
        revenue_accounts=accounts,
    )


# ---- the legacy SSP replay (04 §17.2 LM-CL-10 rev 1.72; D-98 133 AMENDMENTS 3 and 4)
# ---------------

SSP_BOOK_CODE: Final = "LEGACY-SKU-SSP"  # S01-R-05; LM-SSP-08
SSP_BOOK_NAME: Final = "Legacy SKU SSP"
SSP_METHODOLOGY: Final = "Legacy SSP replay of migration {migration_no}"
SSP_FLAGS: Final[Mapping[str, str]] = {"Distinct": "distinct", "Nondistinct": "nondistinct"}
SSP_TEMPLATES: Final[Mapping[str, str]] = {
    "distinct": "LEGACY-DISTINCT",
    "nondistinct": "LEGACY-NONDISTINCT",
}
SSP_CONFLICT_COPY: Final = (
    "SSP version {label!r} is already approved in this workspace with a different entry for {sku} "
    "/ {stratification}; "
    "the legacy replay cannot change it."
)
SSP_LABEL_HELD_COPY: Final = (
    "SSP version {label!r} of book LEGACY-SKU-SSP is {status}, not APPROVED; the legacy replay "
    "cannot reuse it."
)
SSP_FLAG_COPY: Final = (
    "SKU {sku!r} carries the flag {flag!r}; Distinct or Nondistinct are the legacy values."
)
SSP_NO_REQUEST_COPY: Final = (
    "The migration's legacy SSP replay has no APPROVED approval request (MIGRATION_SSP_REPLAY); "
    "the import cannot approve "
    "the LEGACY-SKU-SSP versions it needs."
)
SSP_RULE: Final = "LM-CL-10"
# legacy column names (04 §17.3), exact text
_SSP_VERSION: Final = "SSP Version"
_SSP_SKU: Final = "SKU Name"
_SSP_STRAT: Final = "ASC 606 Stratification"
_SSP_FLAG: Final = "Distinct or Nondistinct"
_SSP_LIST: Final = "SKU Unit List Price"
_SSP_DISCOUNT: Final = "Midpoint Discount Percentage"
_SSP_RANGE: Final = "SSP Range Method (+-)"
_SSP_ACCOUNT: Final = "Revenue Account"


def _entry_key(entry: SspEntryPlan) -> tuple[str, str]:
    return (entry.product_code, entry.stratification)


def _entry_values(entry: SspEntryPlan) -> tuple[Decimal, Decimal, Decimal, str | None, str]:
    """The comparable form of an entry (FLMG-SSP-REUSE-SCALE-1, Codex 0644 §2): the three values as
    EXACT Decimals — equality is exact and scale-insensitive, Decimal("100") equals
    Decimal("100.000000000000000000") — the account code and the flag as text; never rounded, no
    tolerance."""
    return (
        _exact_decimal(entry.unit_list_price),
        _exact_decimal(entry.midpoint_discount_ratio),
        _exact_decimal(entry.range_ratio),
        entry.revenue_account_code,
        entry.distinctness,
    )


def _plan_ssp_replay(
    session: Any, rows: Sequence[Mapping[str, str | None]], known_products: set[str]
) -> tuple[tuple[SspVersionPlan, ...], tuple[ProductPlan, ...], tuple[str, ...]]:
    """One version per distinct label with its entries (LM-SSP-01..09), the SKUs present only in
    ``SKU_SSP`` as products to create (LM-SSP-02), and the revenue accounts to create (LM-SSP-09).
    An
    equal APPROVED version in the tenant is reused — equal = exact numeric equality of the three
    values (scale-insensitive) with the same account code and flag (FLMG-SSP-REUSE-SCALE-1); a
    conflicting entry, or a label held by a non-approved version, is refused by name BEFORE any
    write (idempotence, D-98 133 AMENDMENT 3).
    """
    if not rows:
        return (), (), ()
    grouped: dict[str, list[SspEntryPlan]] = {}
    ssp_only: dict[str, str] = {}
    for row in rows:
        sku = str(row.get(_SSP_SKU) or "")
        flag = str(row.get(_SSP_FLAG) or "")
        distinctness = SSP_FLAGS.get(flag)
        if distinctness is None:
            raise _refuse(SSP_FLAG_COPY.format(sku=sku, flag=flag), rule=SSP_RULE)
        entry = SspEntryPlan(
            product_code=sku,
            stratification=str(row.get(_SSP_STRAT) or ""),
            distinctness=distinctness,
            unit_list_price=_decimal_text(row.get(_SSP_LIST)),
            midpoint_discount_ratio=_decimal_text(row.get(_SSP_DISCOUNT)),
            range_ratio=_decimal_text(row.get(_SSP_RANGE)),
            revenue_account_code=(
                str(row[_SSP_ACCOUNT]) if row.get(_SSP_ACCOUNT) not in (None, "") else None
            ),
        )
        grouped.setdefault(str(row.get(_SSP_VERSION) or ""), []).append(entry)
        if sku not in known_products:
            ssp_only.setdefault(sku, distinctness)
    labels = sorted(grouped)
    existing = {
        str(r[1]): (UUID(str(r[0])), str(r[2]))
        for r in session.execute(
            select(
                ssp_book_version.c.id,
                ssp_book_version.c.legacy_version_label,
                ssp_book_version.c.status,
            )
            .select_from(
                ssp_book_version.join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
            )
            .where(
                ssp_book.c.code == SSP_BOOK_CODE,
                ssp_book_version.c.legacy_version_label.in_(labels),
            )
        ).all()
    }
    versions: list[SspVersionPlan] = []
    for label in labels:
        entries = tuple(sorted(grouped[label], key=_entry_key))
        found = existing.get(label)
        if found is None:
            versions.append(SspVersionPlan(label=label, entries=entries))
            continue
        version_id, status = found
        if status != publication.APPROVED:
            raise _refuse(SSP_LABEL_HELD_COPY.format(label=label, status=status), rule=SSP_RULE)
        stored = {
            (str(r[0]), str(r[1])): (
                # the persisted NUMERIC(38,18) values as exact Decimals — compared numerically,
                # never as scaled text (FLMG-SSP-REUSE-SCALE-1)
                _exact_decimal(r[2]),
                _exact_decimal(r[3]),
                _exact_decimal(r[4]),
                None if r[5] is None else str(r[5]),
                str(r[6]),
            )
            for r in session.execute(
                select(
                    product.c.code,
                    ssp_entry.c.stratification,
                    ssp_entry.c.unit_list_price,
                    ssp_entry.c.midpoint_discount_ratio,
                    ssp_entry.c.range_ratio,
                    gl_account.c.code.label("account_code"),
                    ssp_entry.c.distinctness,
                )
                .select_from(
                    ssp_entry.join(product, product.c.id == ssp_entry.c.product_id).outerjoin(
                        gl_account, gl_account.c.id == ssp_entry.c.revenue_gl_account_id
                    )
                )
                .where(ssp_entry.c.ssp_book_version_id == version_id)
            ).all()
        }
        for entry in entries:
            held = stored.get(_entry_key(entry))
            if held is None or held != _entry_values(entry):
                raise _refuse(
                    SSP_CONFLICT_COPY.format(
                        label=label,
                        sku=entry.product_code,
                        stratification=entry.stratification or "-",
                    ),
                    rule=SSP_RULE,
                )
        versions.append(SspVersionPlan(label=label, entries=entries, existing_id=version_id))
    accounts = sorted(
        {
            e.revenue_account_code
            for v in versions
            if v.existing_id is None
            for e in v.entries
            if e.revenue_account_code
        }
    )
    present_accounts = (
        {
            str(r[0])
            for r in session.execute(
                select(gl_account.c.code).where(gl_account.c.code.in_(accounts))
            ).all()
        }
        if accounts
        else set()
    )
    template_codes = sorted({SSP_TEMPLATES[d] for d in ssp_only.values()})
    templates = (
        {
            str(r[1]): UUID(str(r[0]))
            for r in session.execute(
                select(pob_template.c.id, pob_template.c.code).where(
                    pob_template.c.code.in_(template_codes)
                )
            ).all()
        }
        if template_codes
        else {}
    )
    products: list[ProductPlan] = []
    for sku in sorted(ssp_only):
        distinctness = ssp_only[sku]
        template_code = SSP_TEMPLATES[distinctness]
        template_id = templates.get(template_code)
        if template_id is None:
            raise _refuse(
                TEMPLATE_MISSING_COPY.format(code=template_code, sku=sku), rule=PRODUCT_RULE
            )
        products.append(
            ProductPlan(
                code=sku,
                template_code=template_code,
                template_id=template_id,
                distinctness=distinctness,
                principal_agent=PrincipalAgent.PRINCIPAL.value,
                policy_values=product_parity_values(),
            )
        )
    return tuple(versions), tuple(products), tuple(a for a in accounts if a not in present_accounts)


def _decimal_text(value: object) -> str:
    """A legacy numeric cell as exact decimal text (``format(Decimal, "f")``); blank = "0" as the
    legacy template writes it (LM-SSP-04 blank is a row error the PROFILE already refused). The
    WRITER's form — comparisons use ``_exact_decimal``."""
    if value is None or value == "":
        return "0"
    return format(Decimal(str(value)), "f")


def _exact_decimal(value: object) -> Decimal:
    """A source cell or a persisted NUMERIC value as an exact Decimal for comparison
    (FLMG-SSP-REUSE-SCALE-1, Codex 0644 §2): ``Decimal(str(value))`` is exact and Decimal equality
    is scale-insensitive, so 100 and 100.000000000000000000 compare equal without rounding or
    tolerance; blank = 0 as the legacy template writes it."""
    if value is None or value == "":
        return Decimal(0)
    return Decimal(str(value))


def apply(
    uow: UnitOfWork,
    batch_id: UUID,
    plan_: PrerequisitePlan,
    *,
    replay_request_id: UUID | None = None,
    migration_no: str = "",
    sku_ssp_sha256: str = "",
) -> Applied:
    """Create the planned rows through the reference writers (each AUD-CMD audited) in the caller's
    unit of work — the import job's OUTER transaction — and write ONE
    ``migration_batch.prerequisites`` event listing them. Nothing is updated; an empty plan writes
    nothing. Rev 1.72: the LEGACY-SKU-SSP versions of the plan are created DRAFT, filled and moved
    to
    APPROVED under ``replay_request_id`` (the APPROVED ``MIGRATION_SSP_REPLAY`` request — the basis
    EREV-CFG-002 requires; refused by name without it)."""
    if plan_.empty:
        return Applied()
    entity_ids: dict[str, UUID] = {}
    for entity in plan_.entities:
        created = create_entity(
            uow,
            body=EntityIn(
                code=entity.code,
                name=entity.name,
                functional_currency=entity.functional_currency,
                time_zone=entity.time_zone,
                calendar_id=entity.calendar_id,
            ),
        )
        entity_ids[entity.code] = UUID(str(created.id))
    product_ids: dict[str, UUID] = {}
    for item in plan_.products:
        created_product = create_product(
            uow,
            body=ProductIn(
                code=item.code,
                name=item.code,  # LM-SSP-02: name = code
                default_pob_template_id=item.template_id,
                distinctness_default=Distinctness(item.distinctness),
                principal_agent=PrincipalAgent(
                    item.principal_agent
                ),  # rev 1.66: never NOT_ASSESSED
                policy_values=dict(item.policy_values),
            ),
        )
        product_ids[item.code] = UUID(str(created_product.id))
    ssp_version_ids: dict[str, UUID] = {}
    ssp_entry_counts: dict[str, int] = {}
    ssp_reused: list[str] = []
    if plan_.ssp_versions:
        to_create = [v for v in plan_.ssp_versions if v.existing_id is None]
        if to_create:
            _require_approved_request(uow, replay_request_id)
        for code in plan_.revenue_accounts:
            create_gl_account(
                uow,
                body=GlAccountIn(
                    code=code,
                    name=f"Revenue {code}",
                    account_type=AccountType.REVENUE,
                    normal_balance="C",
                ),
                source_system=SourceSystem.LEGACY_TEMPLATE_V1,
            )
        currency = reporting_currency(uow.session, uow.principal.tenant_id)
        book_id = _ssp_book(uow) if to_create else None
        for version in plan_.ssp_versions:
            if version.existing_id is not None:
                ssp_version_ids[version.label] = version.existing_id
                ssp_entry_counts[version.label] = len(version.entries)
                ssp_reused.append(version.label)
                continue
            assert book_id is not None and replay_request_id is not None
            version_id = create_ssp_book_version(
                uow,
                book_id,
                body=SspBookVersionIn(
                    legacy_version_label=version.label,
                    methodology_label=SSP_METHODOLOGY.format(
                        migration_no=migration_no or "(unknown)"
                    ),
                ),
            )
            upsert_ssp_entries(
                uow,
                version_id,
                body=SspEntriesIn(
                    entries=[
                        SspEntryIn(
                            product_code=entry.product_code,
                            stratification=entry.stratification,
                            currency=currency,
                            method=SspMethod.LEGACY_RANGE,
                            unit_list_price=entry.unit_list_price,
                            midpoint_discount_ratio=entry.midpoint_discount_ratio,
                            range_ratio=entry.range_ratio,
                            revenue_account_code=entry.revenue_account_code,
                            distinctness=Distinctness(entry.distinctness),
                        )
                        for entry in version.entries
                    ]
                ),
            )
            _approve_replayed(uow, version_id, replay_request_id, sku_ssp_sha256)
            ssp_version_ids[version.label] = version_id
            ssp_entry_counts[version.label] = len(version.entries)
    uow.audit(
        action=PREREQUISITES_ACTION,
        object_type=OBJECT_TYPE,
        object_id=batch_id,
        after={
            "ssp_versions": [
                {
                    "legacy_version_label": label,
                    "id": str(version_id),
                    "entry_count": ssp_entry_counts.get(label, 0),
                    "reused": label in ssp_reused,
                }
                for label, version_id in sorted(ssp_version_ids.items())
            ],
            "revenue_accounts": list(plan_.revenue_accounts),
            "sku_ssp_sha256": sku_ssp_sha256,
            "ssp_replay_request_id": None if replay_request_id is None else str(replay_request_id),
            "entities": [
                {
                    "code": entity.code,
                    "name": entity.name,
                    "functional_currency": entity.functional_currency,
                    "calendar_id": str(entity.calendar_id),
                    "time_zone": entity.time_zone,
                    "id": str(entity_ids[entity.code]),
                }
                for entity in plan_.entities
            ],
            "products": [
                {
                    "code": item.code,
                    "template_code": item.template_code,
                    "default_pob_template_id": str(item.template_id),
                    "distinctness": item.distinctness,
                    "principal_agent": item.principal_agent,
                    "policy_values": dict(item.policy_values),
                    "id": str(product_ids[item.code]),
                }
                for item in plan_.products
            ],
        },
    )
    return Applied(
        entity_ids=entity_ids,
        product_ids=product_ids,
        ssp_version_ids=ssp_version_ids,
        ssp_entry_counts=ssp_entry_counts,
        ssp_reused=tuple(ssp_reused),
    )


def _require_approved_request(uow: UnitOfWork, request_id: UUID | None) -> None:
    """The replay's approval basis: an APPROVED ``MIGRATION_SSP_REPLAY`` request (EREV-CFG-002)."""
    if request_id is None:
        raise _refuse(SSP_NO_REQUEST_COPY, rule=SSP_RULE)
    found = uow.session.execute(
        select(approval_request.c.status).where(approval_request.c.id == request_id)
    ).first()
    status = None if found is None else str(found[0])
    if status != ApprovalRequestStatus.APPROVED.value:
        raise _refuse(SSP_NO_REQUEST_COPY, rule=SSP_RULE)


def _ssp_book(uow: UnitOfWork) -> UUID:
    """Book ``LEGACY-SKU-SSP`` (``resolution_mode = BY_LABEL``), created when absent (S01-R-05)."""
    found = uow.session.execute(
        select(ssp_book.c.id).where(ssp_book.c.code == SSP_BOOK_CODE)
    ).first()
    if found is not None:
        return UUID(str(found[0]))
    return create_ssp_book(
        uow, body=SspBookIn(code=SSP_BOOK_CODE, name=SSP_BOOK_NAME, resolution_mode="BY_LABEL")
    )


def _approve_replayed(
    uow: UnitOfWork, version_id: UUID, request_id: UUID, sku_ssp_sha256: str
) -> None:
    """DRAFT → TESTED → SUBMITTED → APPROVED under the APPROVED replay request (the legacy_v1
    sku_ssp
    ``_approve`` shape; ``published_by`` null = automatic approval; 04 §16.10 rev 1.72)."""
    # local import: the approvals kernel is imported by the domain, never the reverse
    from erev_api.approvals import subjects

    session = uow.session
    row = session.execute(
        select(ssp_book_version).where(ssp_book_version.c.id == version_id)
    ).first()
    if row is None:
        raise _refuse(
            SSP_LABEL_HELD_COPY.format(label=str(version_id), status="missing"), rule=SSP_RULE
        )
    version = dict(row._mapping)
    content_sha256 = sha256_hex(subjects.ssp_book_version_content(session, version_id))
    summary = publication.diff_summary(
        session, version_id, publication.latest_approved(session, version)
    )
    principal = uow.principal
    stamps = {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    where = ssp_book_version.c.id == version_id
    session.execute(
        update(ssp_book_version)
        .where(where)
        .values(
            status=publication.TESTED, content_sha256=content_sha256, diff_summary=summary, **stamps
        )
    )
    session.execute(update(ssp_book_version).where(where).values(status=publication.SUBMITTED))
    session.execute(
        update(ssp_book_version)
        .where(where)
        .values(
            status=publication.APPROVED,
            approval_request_id=request_id,
            published_at=uow.now,
            published_by=None,
        )
    )
    uow.audit(
        action=publication.APPROVE_ACTION,
        object_type="ssp_book_version",
        object_id=version_id,
        before={"status": publication.DRAFT, "content_sha256": None},
        after={
            "status": publication.APPROVED,
            "content_sha256": content_sha256,
            "published_by": None,
        },
        detail={
            "basis": "legacy replay (MIGRATION_SSP_REPLAY; 04 rev 1.72)",
            "sku_ssp_sha256": sku_ssp_sha256,
            "lifecycle": [
                publication.DRAFT,
                publication.TESTED,
                publication.SUBMITTED,
                publication.APPROVED,
            ],
        },
        approval_request_id=request_id,
    )


def selling_entity_texts(rows: Iterable[legacy_db.LegacyRow]) -> tuple[str, ...]:
    """The distinct legacy ``Selling Entity`` texts of raw rows (the profile's list)."""
    return tuple(sorted({row.values.get(legacy_db.SELLING_ENTITY) or "" for row in rows} - {""}))

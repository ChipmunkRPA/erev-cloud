"""Volume tenant generator (BUILD_SPEC PRF-1; 05 PERF-10 to PERF-15; dev-guide DG-PERF-01;
REQ-OPS-009; D-75 Q7).

``manifest(scale)`` is pure and deterministic: with seed 20260912 it describes the dataset of
tenant ``perf-volume`` — three entities, 24 periods, a synthetic chart of GL accounts with one
published wildcard account mapping, 400 products, one SSP book with two versions, 12 POB
templates, 10,000 contracts with 50,000 obligations and the parameters of every event — and
the same seed yields byte-identical JSON, whose SHA-256 identifies the dataset (PERF-10). The event
set is not stored in the JSON: ``VolumeManifest.events()`` streams it from the manifest, contract by
contract, and every event carries the idempotency key ``perf:<16 hex>:<event seq>`` (PERF-14;
PROP-idempotency). ``seed(ctx, …)`` writes the dataset into a tenant through the product's
commands
in chunks (PRD WLD-R-02: no direct table insert), month by month, and recomputes every group.

Scale: ``manifest(scale=Fraction(1, 1000))`` keeps the shape (entities, books, periods, templates,
mix) and scales the counts (10 contracts, 50 obligations); the test-database seed of PRF-1 uses it.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from functools import partial
from typing import TYPE_CHECKING, Any, Final, NamedTuple
from uuid import UUID

from erev_engine.money import format_money, minor_to_decimal, round_half_up

from erev_api.enums import (
    AccountRole,
    AccountType,
    BookCode,
    ClearingPurpose,
    ContractEventType,
    PeriodState,
)

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext
    from erev_api.jobs.context import JobRuntime

SEED: Final = 20260912
FULL_CONTRACTS: Final = 10_000
FULL_OBLIGATIONS: Final = 50_000
MONTHS: Final = 24
FULL_PRODUCTS: Final = 400
FULL_CUSTOMERS: Final = 1_000
FIRST_MONTH: Final = date(2025, 1, 1)  # FY2025-P01; the January calendar of the volume tenant
KEY_PREFIX: Final = "perf"
# 1 → 2 (2026-09-22): manifest products still NOT_ASSESSED are assessed PRINCIPAL by the seed.
# 2 → 3 (2026-09-22): the seed creates the chart of GL accounts and ONE published wildcard
# account-mapping version (T-REF-15; ENGINE_SPEC_B S14-R-14 — record §4.22); the SSP book has
# no currency scope and one entry per product per tenant currency (§4.24); every ordered FX pair
# is published and combination suggestions are dismissed (§4.25). The event-set digest changed
# by the inception clamp before version 3 was frozen (§4.25 A): version 3 was never persisted.
# 3 → 4 (2026-09-30, lane FIX-A; supervisor ruling of 2026-09-29): a PROSPECTIVE modification
# is sent with kind ADD_OBLIGATION. Kind UPGRADE with the seed's ADD line is refused at
# ``/classify`` (ENGINE_SPEC S06-R-19; 04 §16.14 rev 1.84; PRD ERR-55), so under version 3 no
# PROSPECTIVE modification of the dataset could apply (record §4.27). The event set is unchanged.
# 4 → 5 (2026-10-01, lane SECFIX-CLO; BUILD_SPEC CTR-6; the supervisor's ruling of 2026-10-01 on
# the lane's addendum, addition 3): a contract-month that holds a delivery, a return, a milestone
# or a cost event is the accountant's request — one event submission, with the entity's evidence
# document of the month where the product asks for one — and the event reviewer's approval
# appends it as SYSTEM (``_record_batch``). The seeded state changes (event submissions,
# ``MANUAL_EVENT`` requests and decisions, the rows' creator); the recipe's other members and the
# event set are those of version 3.
# 5 → 6 (2026-10-01, lane SECFIX-CLO; item EVT-USAGE-MANUAL-1; 05 PERF-15 rev 1.187): a usage
# report is a manual event (04 §16.3 rev 1.238), so a contract-month that holds one waits for the
# event reviewer too — 13,255 further contract-months of the dataset's 122,493, 95,013 in all.
# The seeded state changes in the same way as at version 5; the recipe's other members and the
# event set are those of version 3.
# 6 → 7 (2026-10-01, lane SECFIX-ACT; BUILD_SPEC CTR-12; the supervisor's rulings of 2026-10-01,
# items EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement record; 04 §16.14 rev 1.241): an
# estimate version is submitted with what the product asks of it — one evidence document of its
# own, attached by the accountant, and, for a variable-consideration version, the ``CONSTRAINT``
# record of its element: a record of the version, reviewed by the cast's reviewer and named on
# the version (``_ready_estimate_version``). The seeded state changes (one file and one
# attachment per estimate version; one judgement record with its request and decision, and one
# more computation of the group, per variable-consideration version); the recipe's other members
# and the event set are those of version 3.
# 7 → 8 (2026-10-02, lane SECFIX-CLO; item EVT-EVIDENCE-1; 05 PERF-15 rev 1.192): the
# approval of an event submission attaches the request's evidence to every event it appends
# (04 T-CON-24 rev 1.268), so each event of a contract-month that is sent with the entity's
# evidence document gains an attachment — 343,807 over months 1 to 23, in 26,101 of the
# 112,678 requests. The seeded state changes; the recipe's other members and the event set
# are those of version 3.
# 8 → 9 (2026-10-02, lane FIX-D2; item ACT-FLAGS-1, register index 260; 05 PERF-15 rev 1.204):
# every generated contract states ``acceptance_clause`` and ``side_letter`` false (04 T-CON-01
# rev 1.287), and the request of an activation states the flags of its record and its amount in
# US dollars — of the manifest's 10,000 contracts the activations of 335 gain the Controller's
# second step and those of 114 gain ABOVE_THRESHOLD alone. The seeded state changes; the
# manifest, the recipe's other members and the event set are those of version 3.
# 9 → 10 (2026-10-02, lane F-ADM-WEB; item PERF-SEED-LOCK-1, register index 198; the
# supervisor's ruling of 2026-10-01 on the lane's pre-build line, point (1); 05 PERF-15 rev
# 1.182 — numbered 5 → 6 on the lane's branch and restated at the supervisor's join): a
# contract's events of a recorded month are sent by effective date, an estimate change and an
# amendment through their own commands at their place among the dates (``month_steps``). The
# seeded state changes — the order in which a contract's events are recorded, the appends of a
# contract-month that a command divides, the ``LATE_EVENT`` items, which are now those of the
# events the generator records a month late, and the impact of an estimate change, which is
# applied after the events dated before it (at 1/1000 two estimate versions take the
# Controller's second step that took one step before); the recipe's other members and the
# event set are those of version 3.
# 10 → 11 (2026-10-03, lane ENG-FX; item ENG-COST-READBACK-1; supervisor ruling R-11
# as amended on 2026-10-02): a ledger line stores the subject of its entry (04 T-SL-04
# ``subject_key``, Alembic 0124) and the RCP-05 read-back answers it. Before, every
# computation after the first took the lines of a cost asset, of a refund-liability
# component and of a contract-level loss unit back and posted them again, so the seeded
# ledger held those pairs; it no longer does. The seeded state changes (ledger lines and
# their seals); the recipe's other members and the event set are unchanged by this version.
# 11 → 13 (2026-10-03, lane SECFIX-CLO; item USAGE-REPORT-PERIOD-ENDED-1, register index 306;
# the supervisor's rulings of 2026-10-03; 04 §16.3 "The usage period of a report", rev 1.320;
# 05 PERF-15 rev 1.214): a usage report states usage that has occurred, and the door refuses
# one whose usage period ends after its date. A report of the dataset named the whole month
# and was dated inside it — 55,879 of the manifest's 55,991 usage reports, of 4,000
# obligations in 3,227 contracts; it now ends its period at its own date (``payload``), the
# year-end true-up alike. The seeded state changes: the fee of a report is realised on the
# report's date, so the version rows of a usage obligation hold it from that date. The
# manifest, the recipe's other members and the event set are those of version 3. Version 12
# was withdrawn with register index 87 (ENG-USAGE-FIXED-SCHEDULE-1, taken back on
# 2026-10-03) and never seeded; its number is not reused.
# 13 → 14 (2026-10-03, lane SECFIX-CLO; item ENG-USAGE-FIXED-SCHEDULE-1, register index 87,
# returned behind register index 306; the supervisor's rulings of 2026-10-03; 05 PERF-15 rev
# 1.212): the engine calls the fixed fee of a usage obligation deterministic (ENGINE_SPEC_B
# S09-R-45 rev 1.126), so a seed stores every usage obligation — 4,000 of the manifest's
# 50,000, in 3,227 of its 10,000 contracts, each with a stated price — with its remainder
# scheduled where it was awaiting trigger, with schedule lines to its term end where they
# ended at the horizon, and with those lines flagged as released at close. No posting moves.
# The seeded state changes; the manifest, the recipe's other members and the event set are
# those of version 3.
# Bumps when the recipe OR the seeded state changes (MANIFEST-BINDING-1; supervisor ruling):
# the same manifest with a different seeded state must not share one perf:<16 hex> identity.
# 14 → 15 (2026-10-07): retain the exact two-decimal delivery split. Independently rounding
# each batch to an integer could exceed (or undershoot) the contracted quantity.
# 16: computation also persists immutable FX layer movements (T-CON-18).
GENERATOR_VERSION: Final = 18
TENANT_CODE: Final = "perf-volume"
CALENDAR_CODE: Final = "VOL-JAN"
SSP_BOOK_CODE: Final = "VOL-SSP"
SSP_CURRENCY: Final = "USD"
TENANT_CURRENCIES: Final = ("USD", "GBP", "EUR")
MAX_OBLIGATIONS_PER_CONTRACT: Final = 12
FX_BASE: Final[Mapping[str, str]] = {"GBP": "1.270000", "EUR": "1.100000"}  # → USD, month 1
FISCAL_YEARS_AHEAD: Final = 3  # calendars reach the longest term (36 months) past the horizon
MINOR_UNIT: Final = (
    2  # USD, GBP and EUR (05 PERF-12); rounding through erev_engine.money (DG-ARC-06)
)

# --- shape (05 PERF-12) ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VolumeEntity:
    code: str
    name: str
    country_code: str
    functional_currency: str
    time_zone: str
    books: tuple[str, ...]  # primary first
    contract_share: str  # Fraction as text, JSON-stable


ENTITIES: Final[tuple[VolumeEntity, ...]] = (
    VolumeEntity("VOL-US", "Volume US Inc.", "US", "USD", "America/New_York", ("ASC606",), "3/5"),
    VolumeEntity(
        "VOL-UK", "Volume UK Ltd", "GB", "GBP", "Europe/London", ("ASC606", "IFRS15"), "1/4"
    ),
    VolumeEntity("VOL-DE", "Volume DE GmbH", "DE", "EUR", "Europe/Berlin", ("ASC606",), "3/20"),
)
ENTITY_BY_CODE: Final = {entity.code: entity for entity in ENTITIES}


@dataclass(frozen=True, slots=True)
class MixClass:
    """One row of the recognition mix (05 PERF-13); ``share`` of the obligations."""

    name: str
    recognition_method: str
    obligation_kind: str
    share: str  # Fraction as text
    revenue_category: str


MIX: Final[tuple[MixClass, ...]] = (
    MixClass("TIME_ELAPSED", "TIME_ELAPSED", "STANDARD", "9/20", "SUBSCRIPTION"),
    MixClass("POINT_IN_TIME", "POINT_IN_TIME", "STANDARD", "1/5", "PRODUCT"),
    MixClass("UNITS_DELIVERED", "UNITS_DELIVERED", "STANDARD", "3/20", "PRODUCT"),
    MixClass("USAGE", "USAGE", "STANDARD", "2/25", "SERVICES"),
    MixClass("MILESTONE", "MILESTONE", "STANDARD", "1/20", "SERVICES"),
    MixClass("COST_TO_COST", "COST_TO_COST", "STANDARD", "1/25", "SERVICES"),
    MixClass("MATERIAL_RIGHT", "POINT_IN_TIME", "MATERIAL_RIGHT", "3/100", "MATERIAL_RIGHT"),
)
MIX_BY_NAME: Final = {row.name: row for row in MIX}

_OT_A: Final = {"satisfaction_pattern": "OVER_TIME", "over_time_criterion": "OT_A"}
_OT_B: Final = {"satisfaction_pattern": "OVER_TIME", "over_time_criterion": "OT_B"}
_PIT: Final = {"satisfaction_pattern": "POINT_IN_TIME", "over_time_criterion": "NOT_APPLICABLE"}
_SUBSCRIPTION: Final = {
    "distinctness": "series",
    "series_increment_unit": "day",
    **_OT_A,
    "recognition_method": "TIME_ELAPSED",
    "ratable_convention": "DAILY",
}
_GOODS: Final = {"distinctness": "distinct", **_PIT, "recognition_method": "POINT_IN_TIME"}
_UNITS: Final = {"distinctness": "distinct", **_PIT, "recognition_method": "UNITS_DELIVERED"}
_OPTION: Final = {"obligation_kind": "MATERIAL_RIGHT", **_GOODS}


@dataclass(frozen=True, slots=True)
class VolumeTemplate:
    code: str
    name: str
    mix_class: str
    outputs: Mapping[str, str]


TEMPLATES: Final[tuple[VolumeTemplate, ...]] = (
    VolumeTemplate("TPL-VOL-SUB", "Subscription, daily over time", "TIME_ELAPSED", _SUBSCRIPTION),
    VolumeTemplate(
        "TPL-VOL-SUPPORT", "Support plan, daily over time", "TIME_ELAPSED", _SUBSCRIPTION
    ),
    VolumeTemplate("TPL-VOL-HOSTING", "Hosting, daily over time", "TIME_ELAPSED", _SUBSCRIPTION),
    VolumeTemplate("TPL-VOL-GOODS", "Goods, point in time on delivery", "POINT_IN_TIME", _GOODS),
    VolumeTemplate(
        "TPL-VOL-LICENCE",
        "Functional IP licence",
        "POINT_IN_TIME",
        {
            "obligation_kind": "LICENCE",
            "licence_nature": "FUNCTIONAL",
            **_GOODS,
            "start_date_rule": "LICENCE_START_OR_AVAILABLE",
        },
    ),
    VolumeTemplate("TPL-VOL-UNITS", "Units delivered", "UNITS_DELIVERED", _UNITS),
    VolumeTemplate("TPL-VOL-UNITS-BATCH", "Units delivered in batches", "UNITS_DELIVERED", _UNITS),
    VolumeTemplate(
        "TPL-VOL-USAGE",
        "Usage series",
        "USAGE",
        {
            "distinctness": "series",
            "series_increment_unit": "transaction",
            **_OT_A,
            "recognition_method": "USAGE",
        },
    ),
    VolumeTemplate(
        "TPL-VOL-MILESTONE",
        "Milestone project",
        "MILESTONE",
        {"distinctness": "distinct", **_OT_B, "recognition_method": "MILESTONE"},
    ),
    VolumeTemplate(
        "TPL-VOL-C2C",
        "Engineering project, cost to cost",
        "COST_TO_COST",
        {"distinctness": "distinct", **_OT_B, "recognition_method": "COST_TO_COST"},
    ),
    VolumeTemplate(
        "TPL-VOL-OPTION-RENEWAL", "Renewal option, material right", "MATERIAL_RIGHT", _OPTION
    ),
    VolumeTemplate(
        "TPL-VOL-OPTION-CREDIT", "Expansion credit, material right", "MATERIAL_RIGHT", _OPTION
    ),
)
TEMPLATES_BY_CLASS: Final[Mapping[str, tuple[VolumeTemplate, ...]]] = {
    row.name: tuple(t for t in TEMPLATES if t.mix_class == row.name) for row in MIX
}
# Base list prices per class (SSP currency), varied per product.
_BASE_PRICE: Final = {
    "TIME_ELAPSED": Decimal("12000.00"),
    "POINT_IN_TIME": Decimal("8000.00"),
    "UNITS_DELIVERED": Decimal("450.00"),  # per unit
    "USAGE": Decimal("0.20"),  # per transaction
    "MILESTONE": Decimal("60000.00"),
    "COST_TO_COST": Decimal("250000.00"),
    "MATERIAL_RIGHT": Decimal("1500.00"),
}
_UNIT_OF_MEASURE: Final = {"USAGE": "CALL", "UNITS_DELIVERED": "EA"}


@dataclass(frozen=True, slots=True)
class VolumeProduct:
    code: str
    name: str
    mix_class: str
    template_code: str
    revenue_category: str
    unit_of_measure: str
    list_price: str  # SSP currency, 2 decimals (per unit for units and usage)


@dataclass(frozen=True, slots=True)
class VolumeSspVersion:
    label: str
    effective_from: str  # ISO date
    uplift: str  # Fraction as text applied to every list price


SSP_VERSIONS: Final[tuple[VolumeSspVersion, ...]] = (
    VolumeSspVersion("2025", "2025-01-01", "1"),
    VolumeSspVersion("2026", "2026-01-01", "103/100"),
)


@dataclass(frozen=True, slots=True)
class VolumeObligation:
    key: str  # POB-01 …
    mix_class: str
    recognition_method: str
    obligation_kind: str
    template_code: str
    product_code: str
    quantity: str
    total_price: str  # contract currency, 2 decimals
    term_months: int | None  # TIME_ELAPSED 12 to 36; USAGE 12 to 24; C2C / MILESTONE duration
    performing_entity_code: str | None  # a cross-entity line (05 PERF-13)
    billing: str  # MONTHLY | QUARTERLY | ANNUAL
    timing: str  # ADVANCE | ARREARS
    units: int  # deliveries (UNITS_DELIVERED), milestones (MILESTONE), else 0
    exercised: bool  # MATERIAL_RIGHT: exercised (else expires)


@dataclass(frozen=True, slots=True)
class VolumeContract:
    seq: int  # 1 …
    external_id: str
    entity_code: str
    currency: str
    customer_code: str
    inception_month: int  # 1 … months
    inception_date: str  # ISO
    foreign_currency: bool
    cross_entity: bool
    cost_asset: bool  # a COST_TO_OBTAIN cost at inception (2 per 10 contracts)
    modifications: tuple[tuple[int, str], ...]  # (month, PROSPECTIVE | CUMULATIVE_CATCH_UP)
    vc_changes: tuple[int, ...]  # months of VARIABLE_CONSIDERATION estimate changes
    obligations: tuple[VolumeObligation, ...]


def fx_rate(base: str, month: int) -> str:
    """``base`` → USD for month ``month``: the base rate with a deterministic monthly drift."""
    rate = Decimal(FX_BASE[base]) * (Decimal(1) + Decimal(month % 7) / Decimal(1000))
    return str(rate.quantize(Decimal("0.000001")))


def _to_usd(currency: str, month: int) -> Decimal:
    return Decimal(1) if currency == "USD" else Decimal(fx_rate(currency, month))


def fx_pair_rate(base: str, quote: str, month: int) -> str:
    """``base`` → ``quote`` for month ``month``, derived from the two ``→ USD`` rates (USD → USD is
    1) and quantized to six decimals — synthetic cross and inverse rates (record §4.25). Stage 12
    reads a (transaction, functional) pair exactly as stored (S12-R-01; no inverse), so every
    ordered pair of the tenant currencies is published. Synthetic cross rates derived from the
    USD legs; not market rates."""
    rate = _to_usd(base, month) / _to_usd(quote, month)
    return str(rate.quantize(Decimal("0.000001")))


def _fx_pairs(months: int) -> Mapping[str, tuple[str, ...]]:
    """``"BASE/QUOTE"`` → the monthly rates of every ordered pair of ``TENANT_CURRENCIES``."""
    return {
        f"{base}/{quote}": tuple(fx_pair_rate(base, quote, month) for month in range(1, months + 1))
        for base in TENANT_CURRENCIES
        for quote in TENANT_CURRENCIES
        if base != quote
    }


def _fx_rates(months: int) -> Mapping[str, tuple[str, ...]]:
    return {
        base: tuple(fx_rate(base, month) for month in range(1, months + 1))
        for base in sorted(FX_BASE)
    }


@dataclass(frozen=True, slots=True)
class VolumeRecipe:
    """Every generated reference value and seeding constant that shapes stored rows beyond the
    contracts and events (Codex 2306 MANIFEST-BINDING-1): part of the manifest, so the hash binds
    them."""

    generator_version: int
    calendar: str
    currencies: tuple[str, ...]
    fiscal_years: tuple[int, ...]
    fx_rates: Mapping[str, tuple[str, ...]]  # base currency → USD rate per month
    fx_pairs: Mapping[str, tuple[str, ...]]  # "BASE/QUOTE" → rate per month, every ordered pair
    customer_name: str  # format pattern
    methodology: str
    collectibility_conclusion: str
    collectibility_rationale: str
    submit_comment: str
    open_comment: str
    mapping_name: str  # the ONE account-mapping version's name (T-REF-15)
    ssp_book_scope: str | None  # the SSP book's currency SCOPE: None = every currency (S05-R-02)
    ssp_entry_currencies: tuple[str, ...]  # one entry per product per currency (S05-R-04)
    chart: tuple[tuple[str, str, str, str], ...]  # (role, GL code, name, account type)
    mapping_rules: tuple[str, ...]  # override keys: <role> or BILLING_CLEARING:<purpose>
    deferred_event_types: tuple[str, ...]  # counted, not appended (§4.26)


@dataclass(frozen=True, slots=True)
class VolumeCounts:
    contracts: int
    obligations: int
    obligations_by_class: Mapping[str, int]
    contracts_by_entity: Mapping[str, int]
    foreign_currency_contracts: int
    cross_entity_contracts: int
    modifications: int
    vc_changes: int
    cost_assets: int
    events: int
    events_by_month: tuple[int, ...]
    events_by_type: Mapping[str, int]
    late_events: int
    events_sha256: str  # SHA-256 over the canonical event facts in stream order


class VolumeEvent(NamedTuple):
    """One appended event of the dataset; ``detail`` carries the payload facts as text pairs."""

    seq: int  # 1 … in stream order; the idempotency key suffix
    contract_seq: int
    obligation_key: str | None
    event_type: str
    effective_month: int
    effective_date: date
    recorded_month: int  # the month of the seeding pass that appends it (late: effective + 1)
    late: bool
    detail: tuple[tuple[str, str], ...]


def canonical_event(
    seq: int,
    contract_seq: int,
    obligation_key: str | None,
    event_type: str,
    effective_month: int,
    effective_date: date,
    recorded_month: int,
    late: bool,
    detail: tuple[tuple[str, str], ...],
) -> bytes:
    """The canonical facts of one event (the ``VolumeEvent`` fields in order), hashed into
    ``counts.events_sha256`` one line each."""
    facts = "|".join(
        (
            str(seq),
            str(contract_seq),
            obligation_key or "",
            event_type,
            str(effective_month),
            effective_date.isoformat(),
            str(recorded_month),
            "1" if late else "0",
            ";".join(f"{k}={v}" for k, v in detail),
        )
    )
    return (facts + "\n").encode("utf-8")


def _effective_day(ordinal: int, contract_seq: int) -> int:
    """Day of month (1 to 28) of an event; part of the event facts the manifest hash binds."""
    return min(28, 1 + (ordinal * 7 + contract_seq) % 28)


@dataclass(frozen=True, slots=True)
class VolumeManifest:
    seed: int
    scale: str  # Fraction as text
    months: int
    periods: tuple[str, ...]
    entities: tuple[VolumeEntity, ...]
    mix: tuple[MixClass, ...]
    templates: tuple[VolumeTemplate, ...]
    products: tuple[VolumeProduct, ...]
    ssp_book: str
    ssp_currency: str
    ssp_versions: tuple[VolumeSspVersion, ...]
    customers: int
    recipe: VolumeRecipe
    contracts: tuple[VolumeContract, ...]
    counts: VolumeCounts
    _json: bytes = field(default=b"", repr=False, compare=False)
    _sha256: str = field(default="", repr=False, compare=False)

    # -- identity (05 PERF-10, PERF-11) --

    def to_json(self) -> bytes:
        return self._json

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def hash16(self) -> str:
        return self._sha256[:16]

    @property
    def industry_cluster(self) -> str:
        """``tenant.industry_cluster`` of the volume tenant built from this manifest (PERF-11)."""
        return f"{KEY_PREFIX}:{self.hash16}"

    def idempotency_key(self, seq: int) -> str:
        return f"{KEY_PREFIX}:{self.hash16}:{seq}"

    # -- events (05 PERF-14) --

    def events(self) -> Iterator[VolumeEvent]:
        """Every event of the dataset in stream order (contract by contract, then by month and
        ordinal); ``seq`` numbers them from 1."""
        seq = 0
        for contract in self.contracts:
            for scheduled in _schedule(contract, self.seed, self.months):
                seq += 1
                yield VolumeEvent(seq, *scheduled)

    def events_for_month(self, recorded_month: int) -> Iterator[VolumeEvent]:
        """The events a seeding pass appends in ``recorded_month`` (the month-24 events are the
        set ``make perf`` appends to the sandbox, DG-PERF-02)."""
        return (event for event in self.events() if event.recorded_month == recorded_month)


# --- manifest ------------------------------------------------------------------------------------


def period_key(month: int) -> str:
    """``FYyyyy-Pnn`` of month 1 … (January calendar from FIRST_MONTH)."""
    year, index = divmod(month - 1, 12)
    return f"FY{FIRST_MONTH.year + year}-P{index + 1:02d}"


def month_start(month: int) -> date:
    year, index = divmod(FIRST_MONTH.month - 1 + month - 1, 12)
    return date(FIRST_MONTH.year + year, index + 1, 1)


def month_end(month: int) -> date:
    return month_start(month + 1) - timedelta(days=1)


def _quotas(total: int, shares: Sequence[Fraction]) -> list[int]:
    """Largest-remainder apportionment of ``total`` over ``shares`` (sums to ``total``)."""
    exact = [total * share for share in shares]
    floors = [int(value) for value in exact]
    remainder = total - sum(floors)
    order = sorted(range(len(shares)), key=lambda i: (exact[i] - floors[i], -i), reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def _money(value: Decimal) -> str:
    """Two-decimal text of ``value`` (half-up) through the engine's money helpers."""
    return format_money(round_half_up(value, MINOR_UNIT), MINOR_UNIT)


def _products(count: int) -> tuple[VolumeProduct, ...]:
    """``count`` products: one per template first (every class stays reachable at a small scale),
    the rest apportioned to the classes by the mix shares, alternating a class's templates."""
    count = max(count, len(TEMPLATES))
    extra = _quotas(count - len(TEMPLATES), [Fraction(row.share) for row in MIX])
    products: list[VolumeProduct] = []
    index = 0
    for row, quota in zip(MIX, extra, strict=True):
        templates = TEMPLATES_BY_CLASS[row.name]
        for n in range(len(templates) + quota):
            index += 1
            template = templates[n % len(templates)]
            price = _BASE_PRICE[row.name] * (Decimal(1) + Decimal(index % 17) / Decimal(20))
            products.append(
                VolumeProduct(
                    code=f"VOL-P-{index:04d}",
                    name=f"{template.name} {index:04d}",
                    mix_class=row.name,
                    template_code=template.code,
                    revenue_category=row.revenue_category,
                    unit_of_measure=_UNIT_OF_MEASURE.get(row.name, "EA"),
                    list_price=_money(price),
                )
            )
    return tuple(products)


def _obligation_counts(rng: random.Random, contracts: int, obligations: int) -> list[int]:
    """1 to 12 obligations per contract summing exactly to ``obligations`` (mean 5.0 at full
    scale; 05 PERF-12)."""
    if contracts <= 0:
        return []
    weights = (18, 17, 15, 12, 10, 8, 6, 5, 4, 3, 1, 1)  # 1 … 12, mean about 4.4 before repair
    counts = rng.choices(range(1, MAX_OBLIGATIONS_PER_CONTRACT + 1), weights=weights, k=contracts)
    target = max(contracts, min(obligations, contracts * MAX_OBLIGATIONS_PER_CONTRACT))
    step = 1 if sum(counts) < target else -1
    i = 0
    while sum(counts) != target:
        candidate = counts[i % contracts]
        if 1 <= candidate + step <= MAX_OBLIGATIONS_PER_CONTRACT:
            counts[i % contracts] = candidate + step
        i += 1
    return counts


def _pick(rng: random.Random, total: int, share: Fraction) -> frozenset[int]:
    """Exactly ``round(total * share)`` indices in ``range(total)``."""
    wanted = int(round(total * share))
    return frozenset(rng.sample(range(total), wanted)) if wanted else frozenset()


def manifest(
    scale: Fraction = Fraction(1),
    *,
    contracts: int = FULL_CONTRACTS,
    obligations: int = FULL_OBLIGATIONS,
    months: int = MONTHS,
    seed: int = SEED,
) -> VolumeManifest:
    """The deterministic dataset description (05 PERF-10 to PERF-14). Pure: no clock, no I/O."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    if months < 1:
        raise ValueError("months must be at least 1")
    rng = random.Random(f"{seed}:manifest")
    n_contracts = max(1, int(round(contracts * scale)))
    n_obligations = max(n_contracts, int(round(obligations * scale)))
    n_products = max(len(TEMPLATES), int(round(FULL_PRODUCTS * scale)))
    n_customers = max(1, int(round(FULL_CUSTOMERS * scale)))
    products = _products(n_products)
    products_by_class = {
        row.name: tuple(p for p in products if p.mix_class == row.name) for row in MIX
    }

    # Contracts by entity (6,000 / 2,500 / 1,500), inception spread evenly by month, exact quotas
    # for the foreign-currency and cross-entity contracts (PERF-13).
    entity_quota = _quotas(n_contracts, [Fraction(e.contract_share) for e in ENTITIES])
    entity_codes = [e.code for e, q in zip(ENTITIES, entity_quota, strict=True) for _ in range(q)]
    rng.shuffle(entity_codes)
    inception_months = [(i % months) + 1 for i in range(n_contracts)]
    rng.shuffle(inception_months)
    foreign = _pick(rng, n_contracts, Fraction(1, 10))
    cross = _pick(rng, n_contracts, Fraction(1, 20))
    cost_assets = _pick(rng, n_contracts, Fraction(1, 5))
    counts = _obligation_counts(rng, n_contracts, n_obligations)
    classes = [
        row.name
        for row, quota in zip(
            MIX, _quotas(n_obligations, [Fraction(r.share) for r in MIX]), strict=True
        )
        for _ in range(quota)
    ]
    rng.shuffle(classes)

    contract_rows: list[VolumeContract] = []
    class_index = 0
    for i in range(n_contracts):
        seq = i + 1
        entity = ENTITY_BY_CODE[entity_codes[i]]
        currency = entity.functional_currency
        if i in foreign:
            currency = rng.choice([c for c in TENANT_CURRENCIES if c != currency])
        m0 = inception_months[i]
        inception = month_start(m0) + timedelta(days=rng.randrange(0, 28))
        billing = rng.choices(("MONTHLY", "QUARTERLY", "ANNUAL"), weights=(85, 10, 5))[0]
        timing = "ADVANCE" if rng.random() < 0.70 else "ARREARS"
        performing = None
        if i in cross:
            performing = rng.choice([e.code for e in ENTITIES if e.code != entity.code])
        obligations_of: list[VolumeObligation] = []
        for k in range(counts[i]):
            name = classes[class_index]
            class_index += 1
            row = MIX_BY_NAME[name]
            product = rng.choice(products_by_class[name])
            term: int | None = None
            units = 0
            quantity = Decimal(1)
            if name == "TIME_ELAPSED":
                # 12 to 36 months; most subscriptions run through the 24-month horizon, so the
                # active base grows linearly and month 24 carries about 2/25 of the events.
                term = rng.randint(24, 36) if rng.random() < 0.90 else rng.randint(12, 23)
            elif name == "USAGE":
                term = rng.randint(18, 24)
                quantity = Decimal(rng.randint(20, 200) * 1000)
            elif name == "UNITS_DELIVERED":
                units = rng.randint(12, 24)  # monthly deliveries
                quantity = Decimal(rng.randint(20, 400))
            elif name == "MILESTONE":
                term = rng.randint(12, 24)
                units = rng.randint(3, 5)
            elif name == "COST_TO_COST":
                term = rng.randint(12, 24)
            elif name == "POINT_IN_TIME":
                quantity = Decimal(rng.randint(1, 50))
                term = rng.randint(12, 24)  # instalment billing window
            if term is not None and name != "TIME_ELAPSED":
                # Delivery, usage, milestone, cost and instalment schedules run to the end of the
                # 24-month horizon at least, so the active base grows linearly and the measured
                # month 24 carries about 8% of the events (05 PERF-14).
                term = min(36, max(term, months - m0 + 1))
            if name == "UNITS_DELIVERED":
                units = min(36, max(units, months - m0 + 1))
            unit_price = Decimal(product.list_price)
            price = unit_price * quantity
            if name == "TIME_ELAPSED" and term is not None:
                price = unit_price * Decimal(term) / Decimal(12)
            price = price * (Decimal(1) - Decimal(rng.randint(0, 15)) / Decimal(100))  # discount
            obligations_of.append(
                VolumeObligation(
                    key=f"POB-{k + 1:02d}",
                    mix_class=name,
                    recognition_method=row.recognition_method,
                    obligation_kind=row.obligation_kind,
                    template_code=product.template_code,
                    product_code=product.code,
                    quantity=str(quantity),
                    total_price=_money(max(price, Decimal("1.00"))),
                    term_months=term,
                    performing_entity_code=performing if (performing and k == 0) else None,
                    billing=billing,
                    timing=timing,
                    units=units,
                    exercised=(name == "MATERIAL_RIGHT" and rng.random() < 0.60),
                )
            )
        # Contract-level events: modifications (2 prospective + 1 catch-up per 100 contract-years),
        # VC estimate changes (3% of contracts per quarter).
        modifications: list[tuple[int, str]] = []
        vc_changes: list[int] = []
        for year_start in range(m0 + 1, months + 1, 12):
            draw = rng.random()
            if draw < 0.02:
                modifications.append(
                    (rng.randint(year_start, min(year_start + 11, months)), "PROSPECTIVE")
                )
            elif draw < 0.03:
                modifications.append(
                    (rng.randint(year_start, min(year_start + 11, months)), "CUMULATIVE_CATCH_UP")
                )
        for quarter_start in range(m0 + 1, months + 1, 3):
            if rng.random() < 0.03:
                vc_changes.append(quarter_start)
        contract_rows.append(
            VolumeContract(
                seq=seq,
                external_id=f"VOL-C-{seq:06d}",
                entity_code=entity.code,
                currency=currency,
                customer_code=f"VOL-CUST-{rng.randrange(n_customers) + 1:04d}",
                inception_month=m0,
                inception_date=inception.isoformat(),
                foreign_currency=i in foreign,
                cross_entity=i in cross,
                cost_asset=i in cost_assets,
                modifications=tuple(modifications),
                vc_changes=tuple(vc_changes),
                obligations=tuple(obligations_of),
            )
        )

    counts_out = _count(contract_rows, seed, months)
    first_year = FIRST_MONTH.year
    last_year = FIRST_MONTH.year + (months - 1) // 12 + FISCAL_YEARS_AHEAD
    recipe = VolumeRecipe(
        generator_version=GENERATOR_VERSION,
        calendar=CALENDAR_CODE,
        currencies=TENANT_CURRENCIES,
        fiscal_years=tuple(range(first_year, last_year + 1)),
        fx_rates=_fx_rates(months),
        fx_pairs=_fx_pairs(months),
        customer_name="Volume customer {index:04d}",
        methodology=METHODOLOGY,
        collectibility_conclusion=COLLECTIBILITY_CONCLUSION,
        collectibility_rationale=COLLECTIBILITY_RATIONALE,
        submit_comment=SUBMIT_COMMENT,
        open_comment=OPEN_COMMENT,
        mapping_name=MAPPING_NAME,
        ssp_book_scope=None,
        ssp_entry_currencies=TENANT_CURRENCIES,
        chart=chart_rows(),
        mapping_rules=mapping_rule_keys(),
        deferred_event_types=tuple(sorted(DEFERRED_EVENT_TYPES)),
    )
    body = VolumeManifest(
        seed=seed,
        scale=str(scale),
        months=months,
        periods=tuple(period_key(m) for m in range(1, months + 1)),
        entities=ENTITIES,
        mix=MIX,
        templates=TEMPLATES,
        products=products,
        ssp_book=SSP_BOOK_CODE,
        ssp_currency=SSP_CURRENCY,
        ssp_versions=SSP_VERSIONS,
        customers=n_customers,
        recipe=recipe,
        contracts=tuple(contract_rows),
        counts=counts_out,
    )
    encoded = json.dumps(
        _plain(body), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return VolumeManifest(**{**_fields(body), "_json": encoded, "_sha256": digest})


def _fields(value: VolumeManifest) -> dict[str, Any]:
    return {
        name: getattr(value, name)
        for name in value.__dataclass_fields__
        if not name.startswith("_")
    }


def _plain(value: Any) -> Any:
    """JSON-ready view: dataclasses to dicts (private members dropped), mappings sorted."""
    if isinstance(value, VolumeManifest):
        return {k: _plain(v) for k, v in _fields(value).items()}
    if hasattr(value, "__dataclass_fields__"):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return value


# --- event schedule (05 PERF-14) ------------------------------------------------------------------

_Scheduled = tuple[int, str | None, str, int, date, int, bool, tuple[tuple[str, str], ...]]
LATE_SHARE: Final = 0.005
_STEP: Final = {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}


def _split(total: Decimal, parts: int) -> list[Decimal]:
    """``parts`` two-decimal amounts summing exactly to ``total`` (the last takes the remainder)."""
    if parts <= 0:
        return []
    total_minor = round_half_up(total, MINOR_UNIT)
    each = total_minor // parts
    amounts = [minor_to_decimal(each, MINOR_UNIT)] * (parts - 1)
    amounts.append(minor_to_decimal(total_minor - each * (parts - 1), MINOR_UNIT))
    return amounts


def _schedule(contract: VolumeContract, seed: int, months: int) -> list[_Scheduled]:
    """The events of one contract in stream order, deterministic from the manifest and the seed."""
    rng = random.Random(f"{seed}:events:{contract.seq}")
    raw: list[
        tuple[int, str | None, str, tuple[tuple[str, str], ...]]
    ] = []  # (month, key, type, detail)
    currency = contract.currency
    m0 = contract.inception_month
    invoice_no = 0

    def bill(month: int, key: str | None, amount: Decimal) -> None:
        nonlocal invoice_no
        if month > months or amount <= 0:
            return
        invoice_no += 1
        number = f"VOL-INV-{contract.seq:06d}-{invoice_no:03d}"
        raw.append(
            (
                month,
                key,
                ContractEventType.BILLING_RECORDED.value,
                (("invoice_number", number), ("amount", _money(amount)), ("currency", currency)),
            )
        )
        paid = month + rng.randint(0, 1)  # received in the invoice month or the next
        if paid <= months:
            raw.append(
                (
                    paid,
                    None,
                    ContractEventType.PAYMENT_RECEIVED.value,
                    (
                        ("receipt_reference", f"{number}-R"),
                        ("amount", _money(amount)),
                        ("currency", currency),
                    ),
                )
            )

    def schedule_billing(
        key: str | None, total: Decimal, first: int, last: int, step: int, timing: str
    ) -> None:
        months_of = list(range(first, last + 1, step))
        if not months_of:
            return
        amounts = _split(total, len(months_of))
        for month, amount in zip(months_of, amounts, strict=True):
            issued = month if timing == "ADVANCE" else min(month + step - 1, last)
            bill(issued, key, amount)

    for ob in contract.obligations:
        key = ob.key
        total = Decimal(ob.total_price)
        step = _STEP[ob.billing]
        if ob.mix_class == "TIME_ELAPSED" and ob.term_months:
            last = m0 + ob.term_months - 1
            schedule_billing(key, total, m0, last, step, ob.timing)
        elif ob.mix_class == "USAGE" and ob.term_months:
            per_month = _split(total, ob.term_months)
            quantity = _split(Decimal(ob.quantity), ob.term_months)
            for offset in range(ob.term_months):
                month = m0 + offset
                if month > months:
                    break
                raw.append(
                    (
                        month,
                        key,
                        ContractEventType.USAGE_REPORTED.value,
                        (
                            ("quantity", str(quantity[offset].quantize(Decimal(1)))),
                            ("rated_amount", _money(per_month[offset])),
                            ("currency", currency),
                        ),
                    )
                )
                bill(month, key, per_month[offset])
                if month % 12 == 0:
                    # Fiscal year-end true-up of the usage statement (5% of the year's rated
                    # amount): the year-end months carry the reconciliation load (05 PERF-14).
                    true_up = Decimal(
                        _money(
                            sum(per_month[max(0, offset - 11) : offset + 1], Decimal(0))
                            * Decimal("0.05")
                        )
                    )
                    raw.append(
                        (
                            month,
                            key,
                            ContractEventType.USAGE_REPORTED.value,
                            (
                                (
                                    "quantity",
                                    str(
                                        (
                                            sum(
                                                quantity[max(0, offset - 11) : offset + 1],
                                                Decimal(0),
                                            )
                                            * Decimal("0.05")
                                        ).quantize(Decimal(1))
                                    ),
                                ),
                                ("rated_amount", _money(true_up)),
                                ("currency", currency),
                                ("true_up", "true"),
                            ),
                        )
                    )
                    bill(month, key, true_up)
        elif ob.mix_class == "UNITS_DELIVERED":
            batches = _split(Decimal(ob.quantity), ob.units)
            amounts = _split(total, ob.units)
            for n in range(ob.units):
                month = m0 + n
                if month > months:
                    break
                raw.append(
                    (
                        month,
                        key,
                        ContractEventType.DELIVERY_RECORDED.value,
                        (
                            ("quantity", str(batches[n])),
                            ("trigger", "DELIVERY"),
                        ),
                    )
                )
                bill(month if ob.timing == "ARREARS" else m0, key, amounts[n])
        elif ob.mix_class == "POINT_IN_TIME":
            delivered = m0 + rng.randint(0, 2)
            if delivered <= months:
                raw.append(
                    (
                        delivered,
                        key,
                        ContractEventType.DELIVERY_RECORDED.value,
                        (("quantity", ob.quantity), ("trigger", "CONTROL_TRANSFER")),
                    )
                )
                if rng.random() < 0.01 and delivered + 1 <= months:
                    raw.append(
                        (
                            delivered + 1,
                            key,
                            ContractEventType.RETURN_RECORDED.value,
                            (("quantity", "1"), ("reason", "damaged")),
                        )
                    )
            if ob.billing == "MONTHLY" and ob.term_months:
                schedule_billing(key, total, m0, m0 + ob.term_months - 1, 1, ob.timing)
            else:
                bill(m0 if ob.timing == "ADVANCE" else delivered, key, total)
        elif ob.mix_class == "MILESTONE" and ob.term_months:
            amounts = _split(total, ob.units)
            for n in range(ob.units):
                month = m0 + ((n + 1) * ob.term_months) // ob.units - 1
                if month > months:
                    break
                weight = Fraction(n + 1, ob.units)
                raw.append(
                    (
                        month,
                        key,
                        ContractEventType.MILESTONE_ACHIEVED.value,
                        (
                            ("milestone_code", f"MS-{n + 1}"),
                            ("cumulative_weight", f"{weight.numerator}/{weight.denominator}"),
                        ),
                    )
                )
                bill(month, key, amounts[n])
        elif ob.mix_class == "COST_TO_COST" and ob.term_months:
            eac = total * Decimal("0.80")
            costs = _split(eac, ob.term_months)
            for offset in range(ob.term_months):
                month = m0 + offset
                if month > months:
                    break
                raw.append(
                    (
                        month,
                        key,
                        ContractEventType.COST_INCURRED.value,
                        (
                            ("purpose", "PROGRESS_INPUT"),
                            ("amount", _money(costs[offset])),
                            ("currency", currency),
                        ),
                    )
                )
                if offset % 3 == 2:
                    raw.append(
                        (
                            month,
                            key,
                            ContractEventType.ESTIMATE_CHANGED.value,
                            (
                                ("estimate_kind", "EAC"),
                                (
                                    "amount",
                                    _money(eac * (Decimal(1) + Decimal(offset) / Decimal(100))),
                                ),
                                ("currency", currency),
                            ),
                        )
                    )
            schedule_billing(key, total, m0, m0 + ob.term_months - 1, 1, "ARREARS")
        elif ob.mix_class == "MATERIAL_RIGHT":
            if ob.exercised:
                month = m0 + rng.randint(3, 12)
                if month <= months:
                    raw.append(
                        (
                            month,
                            key,
                            ContractEventType.MATERIAL_RIGHT_EXERCISED.value,
                            (
                                ("exercised_quantity", "1"),
                                ("additional_consideration", _money(total)),
                                ("currency", currency),
                            ),
                        )
                    )
                    bill(month, key, total)
            elif m0 + 12 <= months:
                raw.append((m0 + 12, key, ContractEventType.MATERIAL_RIGHT_EXPIRED.value, ()))
    if contract.cost_asset:
        commission = Decimal(sum(Decimal(o.total_price) for o in contract.obligations)) * Decimal(
            "0.05"
        )
        raw.append(
            (
                m0,
                None,
                ContractEventType.COST_INCURRED.value,
                (
                    ("purpose", "COST_TO_OBTAIN"),
                    ("amount", _money(commission)),
                    ("currency", currency),
                    ("is_incremental", "true"),
                ),
            )
        )
    for month, treatment in contract.modifications:
        raw.append(
            (month, None, ContractEventType.CONTRACT_AMENDED.value, (("treatment", treatment),))
        )
    for month in contract.vc_changes:
        raw.append(
            (
                month,
                None,
                ContractEventType.ESTIMATE_CHANGED.value,
                (("estimate_kind", "VARIABLE_CONSIDERATION"),),
            )
        )
    raw.sort(key=lambda item: item[0])
    out: list[_Scheduled] = []
    inception = date.fromisoformat(contract.inception_date)
    for ordinal, (month, ob_key, event_type, detail) in enumerate(raw, start=1):
        if month > months:
            continue
        late = month < months and rng.random() < LATE_SHARE
        recorded = month + 1 if late else month
        day = _effective_day(ordinal, contract.seq)
        # An inception-month event never precedes the inception: the engine refuses one with
        # EVENT_BEFORE_INCEPTION (S01-R-15, ERROR) and the refused recompute leaves the group
        # dirty, which blocks the month's lock (record §4.25, finding A — the day of 85,879
        # events moved to the inception date; the event count is unchanged). Representativeness:
        # those events cluster on the inception day; the RNG stream is untouched.
        effective = max(month_start(month) + timedelta(days=day - 1), inception)
        out.append((contract.seq, ob_key, event_type, month, effective, recorded, late, detail))
    return out


def _count(contracts: Sequence[VolumeContract], seed: int, months: int) -> VolumeCounts:
    by_class: dict[str, int] = {row.name: 0 for row in MIX}
    by_entity: dict[str, int] = {e.code: 0 for e in ENTITIES}
    by_month = [0] * months
    by_type: dict[str, int] = {}
    late = 0
    events = 0
    digest = hashlib.sha256()
    for contract in contracts:
        by_entity[contract.entity_code] += 1
        for ob in contract.obligations:
            by_class[ob.mix_class] += 1
        for scheduled in _schedule(contract, seed, months):
            events += 1
            by_month[scheduled[5] - 1] += 1
            by_type[scheduled[2]] = by_type.get(scheduled[2], 0) + 1
            late += int(scheduled[6])
            digest.update(canonical_event(events, *scheduled))
    return VolumeCounts(
        contracts=len(contracts),
        obligations=sum(len(c.obligations) for c in contracts),
        obligations_by_class=by_class,
        contracts_by_entity=by_entity,
        foreign_currency_contracts=sum(c.foreign_currency for c in contracts),
        cross_entity_contracts=sum(c.cross_entity for c in contracts),
        modifications=sum(len(c.modifications) for c in contracts),
        vc_changes=sum(len(c.vc_changes) for c in contracts),
        cost_assets=sum(c.cost_asset for c in contracts),
        events=events,
        events_by_month=tuple(by_month),
        events_by_type=dict(sorted(by_type.items())),
        late_events=late,
        events_sha256=digest.hexdigest(),
    )


# --- seeding through commands (05 PERF-15; PRD WLD-R-02) ------------------------------------------

DEFERRED_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        ContractEventType.MATERIAL_RIGHT_EXERCISED.value,
        ContractEventType.MATERIAL_RIGHT_EXPIRED.value,
    }
)
"""Event types the seed COUNTS instead of appending (``deferred_by_type``): the material-right
exercise and expiry, until their own command lands — ``record_events`` refuses both by name
(API-R-30 ``RECORDED_TYPES``) and BUILD_SPEC ENB-5 (stage 06 material-right exercise, expiry)
is unbuilt (record §4.26; the sixth database measurement, 2026-09-22; the D-98 148 A3 precedent
of CONTRACT_AMENDED / ESTIMATE_CHANGED before CTR-17 and the estimate commands landed). The
billing of an exercised option is an ordinary BILLING_RECORDED and is appended. Representativeness:
the material-right exercise / expiry branch is NOT exercised by the seed. ``CONTRACT_AMENDED``
goes through the modification commands (``_apply_modification``) and ``ESTIMATE_CHANGED``
through the estimate commands (``_apply_estimate``; D-98 148 A5 (4)). The report's
``deferred_by_type`` also counts a modification the engine classified ``SEPARATE_CONTRACT`` (it
books a new contract instead of amending this one). The set is bound by the recipe."""
SEPARATE_OUTCOME: Final = "CONTRACT_AMENDED (engine chose SEPARATE_CONTRACT)"
# Per-event outcomes of the seeding paths (Codex 0206 §5): what THIS run did with one manifest
# event.
APPLIED: Final = "applied"  # newly appended by this run
REUSED: Final = "reused"  # found already persisted by an earlier run (a resume replays nothing)
SEPARATE: Final = "separate"  # a modification the engine classified SEPARATE_CONTRACT (not amended)


class MonthTally(NamedTuple):
    """One month's counts: newly appended, reused (already persisted), counted-not-appended."""

    appended: int
    reused: int
    deferred: dict[str, int]


def append_outcome(recorded: Any, requested: int) -> int:
    """How many of the ``requested`` events an append command PERSISTED (Codex 0233
    APPEND-OUTCOME-1):
    ``record_events`` returns ``appended`` (the events and a synchronous computation), or ``job``
    with ``appended = None`` when the events were appended and the computation was DEFERRED — fresh
    appends either way — or ``submission`` when the request was stored for approval and NOTHING was
    appended, which is no outcome of an append and is refused by name here: ``_record_batch`` has
    such a request approved and counts what the approval applied (BUILD_SPEC CTR-6). The
    computation payload never decides the append outcome."""
    if getattr(recorded, "submission", None) is not None:
        raise LookupError("the append was routed for approval; the volume seed appends directly")
    appended = getattr(recorded, "appended", None)
    if appended is not None:
        events = getattr(appended, "events", None)
        return requested if events is None else len(events)
    if getattr(recorded, "job", None) is not None:
        return requested  # appended; the group's computation runs in the deferred job
    raise LookupError("the append returned neither appended events nor a deferred computation")


def tally(outcomes: Iterable[str]) -> tuple[int, int, int]:
    """(applied, reused, separate) over per-event outcomes — the pure counter rule the report uses:
    a reused effect is never reported as appended, a separate one never as an amendment."""
    applied = reused = separate = 0
    for outcome in outcomes:
        if outcome == APPLIED:
            applied += 1
        elif outcome == REUSED:
            reused += 1
        elif outcome == SEPARATE:
            separate += 1
        else:
            raise ValueError(f"unknown event outcome {outcome!r}")
    return applied, reused, separate


# The order in which a contract's events of one recorded month are sent (PERF-SEED-LOCK-1; 05
# PERF-14, PERF-15). The engine raises a LATE_EVENT item for an event that arrives after a
# later-dated event of its contract, and an open item holds every lock of its entity. Sent with
# the commands first and then as the manifest lists the month — by obligation, then by kind —
# three fifths of the events arrived late (1,122 of 1,877 at 1/1000), where PERF-14 plans the
# 0.5 % the generator records a month late. So a contract-month is sent by effective date, and
# what raises an item is an event of that 0.5 %.
OWN_COMMAND: Final[frozenset[str]] = frozenset(
    {ContractEventType.ESTIMATE_CHANGED.value, ContractEventType.CONTRACT_AMENDED.value}
)


class MonthStep(NamedTuple):
    """One durable step of a contract's recorded month: an ``ESTIMATE_CHANGED`` or a
    ``CONTRACT_AMENDED`` through its own command, or one append of the events that stand between
    two such commands."""

    events: tuple[VolumeEvent, ...]  # the one event of a command; the events of one append
    part: int  # 0 for a command of its own, else the append's number among ``parts``, from 1
    parts: int  # the appends of the contract-month


def sent_events(contract: VolumeContract, events: Iterable[VolumeEvent]) -> list[VolumeEvent]:
    """The events of ``contract`` the seed sends — every one but a deferred type and one without
    a payload, which are counted and never appended (``DEFERRED_EVENT_TYPES``)."""
    return [
        event
        for event in events
        if event.event_type in OWN_COMMAND
        or (event.event_type not in DEFERRED_EVENT_TYPES and payload(event, contract) is not None)
    ]


def month_steps(events: Iterable[VolumeEvent]) -> tuple[MonthStep, ...]:
    """The steps of one contract-month in the order they are sent: by effective date; a command
    of its own at its place among the dates, before the other events of its day, and the events
    before and after it as appends of their own; the manifest's order otherwise. A month that no
    such command divides is one append, as it always was."""
    runs: list[tuple[bool, list[VolumeEvent]]] = []
    ordered = sorted(
        events, key=lambda e: (e.effective_date, e.event_type not in OWN_COMMAND, e.seq)
    )
    for event in ordered:
        own = event.event_type in OWN_COMMAND
        if own or not runs or runs[-1][0]:
            runs.append((own, [event]))
        else:
            runs[-1][1].append(event)
    parts = sum(1 for own, _ in runs if not own)
    steps: list[MonthStep] = []
    part = 0
    for own, run in runs:
        if not own:
            part += 1
        steps.append(MonthStep(tuple(run), 0 if own else part, parts))
    return tuple(steps)


def append_comment(month: int, cluster: str, part: int, parts: int) -> str:
    """The comment of one append of a contract-month, which is its mark in the resume ledger
    (``perf_seed.months_from_audit``, ``perf_seed.parts_from_audit``). The LAST append carries the
    month's plain comment — the ledger's "this contract-month's events are appended" — and an
    earlier append of a divided month names its part."""
    if part == parts:
        return f"Volume month {month} ({cluster})"
    return f"Volume month {month} part {part} of {parts} ({cluster})"


def late_among(dates: Iterable[date]) -> list[bool]:
    """For the effective dates of one contract's events in the order they are recorded, whether
    each arrives late: dated before the latest date recorded before it. The engine's rule
    (ENGINE_SPEC S08-R-10, the out-of-order clause; ``late._recorded_earlier_latest``): the
    latest date only rises, so an event that follows a late one is measured against the same
    latest date, and an event of that very date is not late. Pure."""
    flags: list[bool] = []
    latest: date | None = None
    for effective in dates:
        flags.append(latest is not None and effective < latest)
        latest = effective if latest is None else max(latest, effective)
    return flags


def late_arrivals(m: VolumeManifest, through_month: int | None = None) -> list[VolumeEvent]:
    """The events that arrive after a later-dated event of their contract when the months
    through ``through_month`` are sent in the order of ``month_steps`` — the events the engine
    answers with a LATE_EVENT item (``late_among``) — in the order they are sent. Pure."""
    last = m.months if through_month is None else min(m.months, through_month)
    contracts = {contract.seq: contract for contract in m.contracts}
    by_month: dict[tuple[int, int], list[VolumeEvent]] = {}
    for event in m.events():
        if event.recorded_month <= last:
            by_month.setdefault((event.recorded_month, event.contract_seq), []).append(event)
    order: list[VolumeEvent] = []
    by_contract: dict[int, list[VolumeEvent]] = {}
    for month, seq in sorted(by_month):
        for step in month_steps(sent_events(contracts[seq], by_month[month, seq])):
            order.extend(step.events)
            by_contract.setdefault(seq, []).extend(step.events)
    late = {
        event.seq
        for events in by_contract.values()
        for event, flag in zip(events, late_among(e.effective_date for e in events), strict=True)
        if flag
    }
    return [event for event in order if event.seq in late]


def recompute_due(states: Iterable[str]) -> bool:
    """05 PERF-15: the bulk recompute of every group is made with every period open. ``states``
    are the period states of the manifest's months, for every entity and book. A seed starts the
    close of its first month only after that recompute, so a state other than ``open`` — a soft
    close, a lock — shows a later run that it was made: a resumed seed, or one that extends an
    earlier ``through_month``, does not repeat it. The condition is PERF-15's own. It is not the
    answer to the engine's defect of item ENG-COST-READBACK-1 — what a recomputation behind a
    lock posts for a capitalised contract cost — and does not stand in for it. Pure."""
    return all(str(state) == PeriodState.OPEN.value for state in states)


SETTINGS_MANAGE: Final = "settings.manage"
MASTERDATA_MAINTAIN: Final = "masterdata.maintain"
SSP_CREATE: Final = "ssp.create"
CONFIG_AUTHOR: Final = "config.author"
CONTRACT_CREATE: Final = "contract.create"
EVENT_RECORD: Final = "event.record"
MODIFICATION_CREATE: Final = "modification.create"
JUDGEMENT_CREATE: Final = "judgement.create"
SUBMIT_COMMENT: Final = "Volume dataset (PRF-1)."
OPEN_COMMENT: Final = "Opened for the volume dataset (05 PERF-15)."
COLLECTIBILITY_CONCLUSION: Final = "Collection of the consideration is probable."
PRINCIPAL_RATIONALE: Final = (
    "Volume dataset: this product is assessed as principal — synthetic seed configuration "
    "following the manifest, not an accounting judgement (PRF-1)."
)
DISTINCT_RATIONALE: Final = (
    "Volume dataset: the template concludes distinct; the customer can benefit from the good or "
    "service on its own and the promise is separately identifiable (PRF-1)."
)
COLLECTIBILITY_RATIONALE: Final = "Generated volume customer; credit review not applicable."
# 04 T-CON-19 "Step 1 criteria" (supervisor rulings R-113 (f), R-115 (f)): a record that serves
# Step 1 answers the five criteria of 606-10-25-1 when it is sent for review. The seeded
# contracts are contracts: every criterion is met.
STEP1_CRITERIA_MET: Final = dict.fromkeys(("a", "b", "c", "d", "e"), "YES")
SUGGESTION_RATIONALE: Final = (
    "Volume dataset (PRF-1): the contracts of one generated customer are independent by "
    "construction; synthetic seed data, not an accounting judgement on combination."
)
METHODOLOGY: Final = "Generated list-price study"

# --- chart of GL accounts and the ONE wildcard account mapping (record §4.22, ruled) --------------
# The fourth database measurement (2026-09-22) found the seed never created a T-REF-15 mapping, so
# stage 14 quarantined the first computation that posted revenue (ENGINE_SPEC_B S14-R-14
# ACCOUNT_MAPPING_MISSING). SYNTHETIC seed configuration following the manifest, not an accounting
# judgement; no chart of accounts is certified. PERF-representativeness limitation: stage-14
# resolution runs only the wildcard branch (entity, book, product and category NULL), so the cost
# of a richer mapping is not measured by this seed.
MAPPING_NAME: Final = "VOL-MAP"
MAPPING_NOTES: Final = (
    "Volume dataset (PRF-1): synthetic seed configuration following the manifest, not an "
    "accounting judgement; no chart of accounts is certified. One wildcard rule per account role, "
    "BILLING_CLEARING once per clearing purpose; entity, book, product and category unrestricted."
)
# ONE role-kind table: every AccountRole member exactly once → the synthetic GL account's type; the
# normal balance follows the type (D for assets and expenses, C otherwise). Pinned in CPU against
# the enum (tests/unit/perf), so a new member fails the pin instead of quarantining the seed.
ROLE_KIND: Final[tuple[tuple[AccountRole, AccountType], ...]] = (
    (AccountRole.CONTRACT_ASSET, AccountType.ASSET),
    (AccountRole.UNBILLED_RECEIVABLE, AccountType.ASSET),
    (AccountRole.ACCOUNTS_RECEIVABLE, AccountType.ASSET),
    (AccountRole.RETURN_ASSET, AccountType.ASSET),
    (AccountRole.CUSTOMER_INCENTIVE_ASSET, AccountType.ASSET),
    (AccountRole.COST_TO_OBTAIN_ASSET, AccountType.ASSET),
    (AccountRole.COST_TO_FULFILL_ASSET, AccountType.ASSET),
    (AccountRole.INTERCOMPANY_DUE_FROM, AccountType.ASSET),
    (AccountRole.NONCASH_CONSIDERATION_ASSET, AccountType.ASSET),
    (AccountRole.RECEIVABLE_CONTRA, AccountType.ASSET),
    (AccountRole.CONTRACT_LIABILITY, AccountType.LIABILITY),
    (AccountRole.BILLING_CLEARING, AccountType.LIABILITY),
    (AccountRole.REFUND_LIABILITY, AccountType.LIABILITY),
    (AccountRole.DEPOSIT_LIABILITY, AccountType.LIABILITY),
    (AccountRole.CONSIDERATION_PAYABLE, AccountType.LIABILITY),
    (AccountRole.LOSS_PROVISION, AccountType.LIABILITY),
    (AccountRole.WARRANTY_PROVISION, AccountType.LIABILITY),
    (AccountRole.INTERCOMPANY_DUE_TO, AccountType.LIABILITY),
    (AccountRole.SALES_TAX_PAYABLE, AccountType.LIABILITY),
    (AccountRole.CONTRACT_COST_CLEARING, AccountType.LIABILITY),
    (AccountRole.FINANCING_OBLIGATION, AccountType.LIABILITY),
    (AccountRole.RETAINED_EARNINGS, AccountType.EQUITY),
    (AccountRole.REVENUE, AccountType.REVENUE),
    (AccountRole.INTEREST_INCOME, AccountType.REVENUE),
    (AccountRole.PRE_STANDARD_REVENUE, AccountType.REVENUE),
    (AccountRole.CONTRACT_COST_AMORTIZATION, AccountType.EXPENSE),
    (AccountRole.CONTRACT_COST_IMPAIRMENT, AccountType.EXPENSE),
    (AccountRole.LOSS_EXPENSE, AccountType.EXPENSE),
    (AccountRole.WARRANTY_EXPENSE, AccountType.EXPENSE),
    (AccountRole.INTEREST_EXPENSE, AccountType.EXPENSE),
    (AccountRole.COST_OF_REVENUE, AccountType.EXPENSE),
    (AccountRole.FX_GAIN_LOSS, AccountType.EXPENSE),
    (AccountRole.ROUNDING, AccountType.EXPENSE),
)
KIND_PREFIX: Final[Mapping[AccountType, str]] = {
    AccountType.ASSET: "1",
    AccountType.LIABILITY: "2",
    AccountType.EQUITY: "3",
    AccountType.REVENUE: "4",
    AccountType.EXPENSE: "5",
}


def normal_balance(kind: AccountType | str) -> str:
    """``D`` for assets and expenses, ``C`` otherwise (synthetic; follows the account type)."""
    return "D" if AccountType(kind) in (AccountType.ASSET, AccountType.EXPENSE) else "C"


def chart_rows() -> tuple[tuple[str, str, str, str], ...]:
    """(role, GL code, name, account type) per ``ROLE_KIND`` row: the code is the kind's prefix and
    the row's position within its kind (``1001``, ``1002``, … ``2001``, …); the name is the role's
    words. Part of the recipe (MANIFEST-BINDING-1)."""
    rows: list[tuple[str, str, str, str]] = []
    seen: dict[AccountType, int] = {}
    for role, kind in ROLE_KIND:
        seen[kind] = seen.get(kind, 0) + 1
        name = role.value.replace("_", " ").capitalize()
        rows.append((role.value, f"{KIND_PREFIX[kind]}{seen[kind]:03d}", name, kind.value))
    return tuple(rows)


def mapping_rule_keys() -> tuple[str, ...]:
    """The override keys of the wildcard rules, in ``ROLE_KIND`` order: every role the product
    accepts a rule for (D-14a reserved roles excluded), ``BILLING_CLEARING`` once per
    ``ClearingPurpose`` as ``BILLING_CLEARING:<purpose>``. Part of the recipe."""
    from erev_api.domain.reference.mapping import RESERVED_ROLES, override_key

    keys: list[str] = []
    for role, _kind in ROLE_KIND:
        if role.value in RESERVED_ROLES:
            continue
        if role is AccountRole.BILLING_CLEARING:
            keys.extend(override_key(role.value, purpose.value) for purpose in ClearingPurpose)
        else:
            keys.append(override_key(role.value, None))
    return tuple(keys)


@dataclass(frozen=True, slots=True)
class VolumeCast:
    """Persona keys of a ``BuildContext.cast`` acting in the seed (WLD-R-02: the approver is never
    the preparer)."""

    admin: str  # structure, currencies, calendars
    accountant: str  # products, FX, SSP, templates, contracts, events
    controller: str  # opens periods
    reviewer: str  # approves SSP versions, templates, FX versions and activations
    event_reviewer: str  # approves the accountant's manual events (event.approve; CTR-6)


# The demo scaffold cast (the interim PRF-1 database test): the single reviewer slot must hold
# every approval permission the seed needs — config.approve (FX rate sets, templates), ssp.approve,
# judgement.review, contract.approve, estimate.approve, modification.approve — which marcus
# (controller + ssp_approver) does and priya (revenue_reviewer + ssp_approver) does not (first DB
# measurement, 2026-09-22). ``event.approve`` is the Revenue Reviewer's alone (PRD §5.6), so the
# accountant's manual events are priya's to approve (BUILD_SPEC CTR-6). The controller slot is
# the demo world's second Controller, elena: a request of two steps — an activation of USD
# 1,000,000.00 and more, an estimate version whose impact reaches USD 50,000.00 — is decided
# by the reviewer and then by the controller, and no approver decides two steps of one request
# (measured 2026-10-02, item PERF-SEED-LOCK-1: sent by effective date, two estimate versions
# of the 1/1000 manifest take the second step, and marcus in both slots was refused there).
DEMO_CAST: Final = VolumeCast(
    admin="tomas",
    accountant="maya",
    controller="elena",
    reviewer="marcus",
    event_reviewer="priya",
)
PERF_CAST: Final = VolumeCast(
    admin="perf-admin",
    accountant="perf-accountant",
    controller="perf-controller",
    reviewer="perf-reviewer",
    event_reviewer="perf-reviewer",
)
# Configuration versions the seed treats as finished (nothing left to submit or approve).
DONE_CONFIG: Final = frozenset({"APPROVED", "PUBLISHED", "SUPERSEDED"})
# Versions a human must resolve before the seed proceeds (it never re-creates around them).
STUCK_CONFIG: Final = frozenset({"REJECTED", "WITHDRAWN"})


@dataclass(frozen=True, slots=True)
class SeedLedger:
    """What an earlier run already wrote (``perf_seed.read_ledger`` reads it from the database):
    the resume point of an idempotent re-run (DG-MK-perf-seed step 3)."""

    calendar: bool
    products: int
    templates: int
    contracts: frozenset[str]  # external ids present
    months_appended: Mapping[str, frozenset[int]]  # external id -> recorded months appended
    # external id -> (recorded month, part) of the earlier appends of a divided month
    # (``append_comment``): the month's last append is the entry of ``months_appended``.
    parts_appended: Mapping[str, frozenset[tuple[int, int]]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SeedReport:
    manifest_sha256: str
    contracts: int
    obligations: int
    months_appended: int
    events_appended: int  # newly appended by this run
    events_reused: int  # already persisted by an earlier run and found again (resume)
    events_deferred: int  # counted, not appended (the SEPARATE_CONTRACT modifications)
    deferred_by_type: Mapping[str, int]
    groups_recomputed: int


def _fraction_money(value: Decimal, uplift: str) -> str:
    return _money(
        value * Decimal(Fraction(uplift).numerator) / Decimal(Fraction(uplift).denominator)
    )


def payload(event: VolumeEvent, contract: VolumeContract) -> dict[str, Any] | None:
    """The API-S-EventAppend payload of ``event`` (04 §16.3 members); None for a deferred type."""
    detail = dict(event.detail)
    currency: str = detail.get("currency") or contract.currency
    money = {"amount": detail.get("amount"), "currency": currency}
    key = event.obligation_key
    match event.event_type:
        case ContractEventType.BILLING_RECORDED.value:
            body: dict[str, Any] = {
                "invoice_number": detail["invoice_number"],
                "line_external_id": f"{detail['invoice_number']}-1",
                "amount": money,
                "issue_date": event.effective_date.isoformat(),
            }
            if key:
                body["obligation_key"] = key
            return body
        case ContractEventType.PAYMENT_RECEIVED.value:
            return {
                "receipt_reference": detail["receipt_reference"],
                "amount": money,
                "receipt_date": event.effective_date.isoformat(),
                "applied_invoice_numbers": [detail["receipt_reference"].removesuffix("-R")],
            }
        case ContractEventType.USAGE_REPORTED.value:
            # The usage of the month up to the report's own date (04 §16.3 "The usage period
            # of a report", rev 1.320; generator version 13): a period that ended after the
            # report's date — the whole month, until version 11 — is refused at the door.
            return {
                "obligation_key": key,
                "usage_period_start": month_start(event.effective_month).isoformat(),
                "usage_period_end": event.effective_date.isoformat(),
                "metric": "transactions",
                "quantity": detail["quantity"],
                "rated_amount": {"amount": detail["rated_amount"], "currency": currency},
            }
        case ContractEventType.DELIVERY_RECORDED.value:
            return {
                "obligation_key": key,
                "quantity": detail["quantity"],
                "trigger": detail["trigger"],
            }
        case ContractEventType.RETURN_RECORDED.value:
            return {
                "obligation_key": key,
                "quantity": detail["quantity"],
                "reason": detail["reason"],
            }
        case ContractEventType.MILESTONE_ACHIEVED.value:
            weight = Fraction(detail["cumulative_weight"])
            return {
                "obligation_key": key,
                "milestone_code": detail["milestone_code"],
                "cumulative_weight": str(
                    (Decimal(weight.numerator) / Decimal(weight.denominator)).quantize(
                        Decimal("0.0001")
                    )
                ),
            }
        case ContractEventType.COST_INCURRED.value:
            body = {"purpose": detail["purpose"], "amount": money}
            if key:
                body["obligation_key"] = key
            if detail.get("is_incremental") == "true":
                body["is_incremental"] = True
            return body
        case ContractEventType.MATERIAL_RIGHT_EXERCISED.value:
            return {
                "obligation_key": key,
                "exercised_quantity": detail["exercised_quantity"],
                "additional_consideration": {
                    "amount": detail["additional_consideration"],
                    "currency": currency,
                },
            }
        case ContractEventType.MATERIAL_RIGHT_EXPIRED.value:
            return {"obligation_key": key}
        case _:
            return None


def _line(ob: VolumeObligation, contract: VolumeContract) -> dict[str, Any]:
    line: dict[str, Any] = {
        "obligation_key": ob.key,
        "product_code": ob.product_code,
        "quantity": ob.quantity,
        "total_price": {"amount": ob.total_price, "currency": contract.currency},
    }
    if ob.term_months is not None and ob.mix_class in {"TIME_ELAPSED", "USAGE"}:
        start = date.fromisoformat(contract.inception_date)
        line["start_date"] = start.isoformat()
        line["end_date"] = (
            month_start(contract.inception_month + ob.term_months) - timedelta(days=1)
        ).isoformat()
    if ob.performing_entity_code is not None:
        line["performing_entity_code"] = ob.performing_entity_code
    return line


def distinct_reviews_needed(m: VolumeManifest, contract: VolumeContract) -> tuple[str, ...]:
    """The obligation keys whose distinctness the activation checklist wants REVIEWED
    (``DISTINCT_REVIEW``, [J] L4-1-Q-19; IMP-102): in a contract of two or more obligations, every
    obligation whose template concludes ``distinct`` or ``nondistinct``; a ``series`` template
    records its own conclusion and needs none; a single-obligation contract needs none. Pure."""
    if len(contract.obligations) < 2:
        return ()
    distinctness = {t.code: str(t.outputs.get("distinctness", "")) for t in m.templates}
    return tuple(
        ob.key
        for ob in contract.obligations
        if distinctness.get(ob.template_code) in {"distinct", "nondistinct"}
    )


def contract_body(contract: VolumeContract, customer_id: UUID) -> dict[str, Any]:
    """The API-S-ContractCreate members of a manifest contract."""
    return {
        "external_id": contract.external_id,
        "customer_id": str(customer_id),
        "contracting_entity_code": contract.entity_code,
        "transaction_currency": contract.currency,
        "inception_date": contract.inception_date,
        "document_ref": contract.external_id,
        # 04 §16.3 rev 1.287 (item ACT-FLAGS-1): a generated contract states its two terms.
        "acceptance_clause": False,
        "side_letter": False,
        "lines": [_line(ob, contract) for ob in contract.obligations],
    }


def seed(
    ctx: BuildContext,
    *,
    contracts: int = FULL_CONTRACTS,
    obligations: int = FULL_OBLIGATIONS,
    months: int = MONTHS,
    seed: int = SEED,
    scale: Fraction = Fraction(1),
    cast: VolumeCast = PERF_CAST,
    chunk: int = 250,
    through_month: int | None = None,
    ledger: SeedLedger | None = None,
    runtime: JobRuntime | None = None,
) -> SeedReport:
    """Write the dataset of ``manifest(scale, …)`` into ``ctx``'s tenant through the product's
    commands as the cast's personas, in chunks (DG-PERF-01): reference data, the chart of GL
    accounts with its published wildcard account mapping, products, the SSP book and its two
    versions, the twelve templates, every product assessed as principal
    (PRINCIPAL_AGENT_CHANGE), every contract (booked, Step 1 recorded, distinct reviews, activated),
    then the events month by month up to ``through_month`` (default every month), then one
    recompute of every group with every period open (05 PERF-15) — not repeated by a run that
    finds a month in soft close or locked (``recompute_due``). ``ESTIMATE_CHANGED`` goes
    through the estimate commands (``_apply_estimate``) and ``CONTRACT_AMENDED`` through the CTR-17
    modification commands (``_apply_modification``; ``runtime`` — key ring and file store — runs the
    impact preview inline, default the context's own). Every step reads what exists and creates
    only what is missing, so a re-run (``ledger``) resumes at the first unfinished step without
    duplicates. Database-bound: never run in the lane."""
    from erev_api.domain.demo.builders import refuse_non_demo
    from erev_api.jobs.context import JobRuntime as _JobRuntime

    refuse_non_demo(ctx)
    if runtime is None:
        runtime = _JobRuntime(clock=ctx.clock, keyring=ctx.keyring, files=ctx.files)
    m = manifest(scale, contracts=contracts, obligations=obligations, months=months, seed=seed)
    last_month = months if through_month is None else min(months, through_month)
    if ledger is None or not ledger.calendar:
        _reference(ctx, m, cast)
    _chart_and_mapping(ctx, m, cast)
    customers = _customers(ctx, m, cast)
    # SEED-ORDER-1 (Codex 2306): real products exist before the template example cases run their
    # tests; the published templates are then bound as the products' defaults.
    _create_products(ctx, m, cast)
    template_ids = _templates(ctx, m, cast)
    _bind_default_templates(ctx, m, cast, template_ids)
    _assess_products(ctx, m, cast)
    _ssp(ctx, m, cast)
    contract_ids = _contracts(ctx, m, cast, customers, chunk)
    appended = reused = 0
    deferred: dict[str, int] = {}
    done = {} if ledger is None else ledger.months_appended
    parts_done = {} if ledger is None else ledger.parts_appended
    for month in range(1, last_month + 1):
        month_tally = _append_month(
            ctx,
            m,
            cast,
            contract_ids,
            month,
            chunk,
            done=done,
            parts_done=parts_done,
            runtime=runtime,
        )
        appended += month_tally.appended
        reused += month_tally.reused
        for kind, count in month_tally.deferred.items():
            deferred[kind] = deferred.get(kind, 0) + count
    groups = _recompute_all(ctx, cast) if recompute_due(_month_states(ctx, m)) else 0
    return SeedReport(
        manifest_sha256=m.sha256,
        contracts=len(m.contracts),
        obligations=m.counts.obligations,
        months_appended=last_month,
        events_appended=appended,
        events_reused=reused,
        events_deferred=sum(deferred.values()),
        deferred_by_type=dict(sorted(deferred.items())),
        groups_recomputed=groups,
    )


def _reference(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> None:
    from sqlalchemy import and_, select

    from erev_api.db.tables import legal_entity, period, period_state
    from erev_api.domain.demo.avenmoor import expect_version
    from erev_api.domain.reference import commands, queries
    from erev_api.enums import ApprovalSubjectType, PeriodState, RateType
    from erev_api.schemas.calendars import CalendarIn, GenerateYearIn
    from erev_api.schemas.currencies import (
        FxRateIn,
        FxRateSetIn,
        FxRateSetVersionCommandIn,
        FxRateSetVersionIn,
        TenantCurrenciesIn,
    )
    from erev_api.schemas.entities import EntityBookIn, EntityIn
    from erev_api.schemas.periods import PeriodOpenIn

    with ctx.command(cast.admin, SETTINGS_MANAGE) as uow:
        commands.put_tenant_currencies(
            uow, body=TenantCurrenciesIn(currency_codes=list(TENANT_CURRENCIES))
        )
    with ctx.command(cast.admin) as uow:
        calendar = commands.create_calendar(
            uow,
            body=CalendarIn(
                code=CALENDAR_CODE, name="Volume January calendar", fiscal_year_start_month=1
            ),
        )
    for year in m.recipe.fiscal_years:
        with ctx.command(cast.admin) as uow:
            commands.generate_year(
                uow, calendar_id=calendar.id, body=GenerateYearIn(fiscal_year=year)
            )
    parent: UUID | None = None
    for entity in m.entities:
        with ctx.command(cast.admin) as uow:
            created = commands.create_entity(
                uow,
                body=EntityIn(
                    code=entity.code,
                    name=entity.name,
                    functional_currency=entity.functional_currency,
                    time_zone=entity.time_zone,
                    calendar_id=calendar.id,
                    parent_entity_id=parent,
                    country_code=entity.country_code,
                    first_period_key=m.periods[0],
                ),
            )
        parent = parent or created.id
        for code in entity.books[1:]:
            book = BookCode(code)
            with ctx.read() as session:
                current = queries.book_row(session, book.value)
            if current is not None and not current["is_enabled"]:
                with ctx.command(cast.admin) as uow:
                    commands.update_book(
                        uow,
                        code=book,
                        changes={"is_enabled": True},
                        check_version=expect_version(int(current["row_version"])),
                    )
            with ctx.command(cast.admin) as uow:
                commands.put_entity_book(
                    uow,
                    entity_id=created.id,
                    code=book,
                    body=EntityBookIn(is_enabled=True, first_period_key=m.periods[0]),
                )
        # Every period of the horizon open (PERF-15: the bulk recompute needs every period open).
        joined = period_state.join(
            period,
            and_(
                period.c.tenant_id == period_state.c.tenant_id,
                period.c.id == period_state.c.period_id,
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
                    legal_entity.c.code == entity.code,
                    period.c.start_date >= month_start(1),
                    period.c.start_date <= month_start(m.months),
                    period_state.c.state == PeriodState.FUTURE.value,
                )
                .order_by(period_state.c.book_code, period.c.start_date)
            ).all()
        for state_id, row_version in states:
            with ctx.command(cast.controller) as uow:
                commands.open_period(
                    uow,
                    state_id=UUID(str(state_id)),
                    body=PeriodOpenIn(comment=OPEN_COMMENT),
                    check_version=expect_version(int(row_version)),
                )
    # FX rate sets: one set per rate type, monthly rates of EVERY ordered pair of the tenant
    # currencies over the horizon (record §4.25): stage 12 converts transaction → functional and
    # intercompany pairs with a rate stored for that exact (base, quote) (S12-R-01, no inverse),
    # and the manifest has GBP / EUR / USD contracts in each entity. Synthetic cross rates.
    coverage_from, coverage_to = month_start(1), month_end(m.months)
    for rate_type, code in (
        (RateType.SPOT, "VOL-RATES-SPOT"),
        (RateType.CLOSING, "VOL-RATES-CLOSING"),
        (RateType.AVERAGE, "VOL-RATES-AVERAGE"),
    ):
        rows: list[FxRateIn] = []
        for month in range(1, m.months + 1):
            for pair, rates in m.recipe.fx_pairs.items():
                base, _, quote = pair.partition("/")
                rate = rates[month - 1]
                if rate_type is RateType.SPOT:
                    rows.append(
                        FxRateIn(
                            base_currency=base,
                            quote_currency=quote,
                            rate=rate,
                            effective_date=month_start(month),
                        )
                    )
                else:
                    rows.append(
                        FxRateIn(
                            base_currency=base,
                            quote_currency=quote,
                            rate=rate,
                            period_key=m.periods[month - 1],
                        )
                    )
        with ctx.command(cast.accountant) as uow:
            rate_set = commands.create_fx_rate_set(
                uow, body=FxRateSetIn(code=code, name=code, rate_type=rate_type)
            )
        with ctx.command(cast.accountant) as uow:
            version = commands.create_fx_rate_set_version(
                uow,
                set_id=rate_set.id,
                body=FxRateSetVersionIn(
                    coverage_from=coverage_from, coverage_to=coverage_to, rates=rows
                ),
            )
        with ctx.command(cast.accountant) as uow:
            commands.submit_fx_rate_set_version(
                uow,
                version_id=version.id,
                body=FxRateSetVersionCommandIn(comment=SUBMIT_COMMENT),
                check_version=expect_version(version.row_version),
            )
        ctx.approve(ApprovalSubjectType.FX_RATE_SET_VERSION, version.id, [cast.reviewer])


def _chart_and_mapping(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> None:
    """The synthetic chart of GL accounts and ONE published wildcard account-mapping version
    (T-REF-15) through the real commands — the fourth database measurement (2026-09-22) found the
    seed never created one, so stage 14 quarantined the first computation that posted revenue
    (ENGINE_SPEC_B S14-R-14 ``ACCOUNT_MAPPING_MISSING``; record §4.22). One GL account per
    ``ROLE_KIND`` row (``create_gl_account``); one rule per ``mapping_rule_keys`` entry with entity,
    book, product and revenue category NULL — the T-REF-15 wildcards; the publish lint, the
    submission and the reviewer's ``ACCOUNT_MAPPING_VERSION`` approval, which publishes. SYNTHETIC
    seed configuration following the manifest, not an accounting judgement; no chart of accounts is
    certified. SoD: the accountant (``config.author``) creates, tests and submits; the reviewer
    (``config.approve``) approves. Resume by persisted state: GL accounts by code; the version by
    its name — PUBLISHED → nothing; DRAFT / TESTED → only the missing rules are added, then lint,
    submit, approve; SUBMITTED with a PENDING request → approve; any other state raises by name."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from erev_api.db.tables import (
        account_mapping_rule,
        account_mapping_version,
        approval_request,
        gl_account,
    )
    from erev_api.domain.reference import commands
    from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType, ConfigStatus
    from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingRuleIn
    from erev_api.schemas.accounts import GlAccountIn

    def text(value: object) -> str:
        return str(getattr(value, "value", value))

    version_table = account_mapping_version
    with ctx.read() as session:
        existing = {
            text(code): UUID(str(account_id))
            for account_id, code in session.execute(
                select(gl_account.c.id, gl_account.c.code)
            ).tuples()
        }
        versions = [
            (UUID(str(version_id)), text(status))
            for version_id, status in session.execute(
                select(version_table.c.id, version_table.c.status)
                .where(version_table.c.name == m.recipe.mapping_name)
                .order_by(version_table.c.version_no.desc())
            ).tuples()
        ]
    accounts: dict[str, UUID] = {}
    for role, code, name, kind in m.recipe.chart:
        account_id = existing.get(code)
        if account_id is None:
            with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                created = commands.create_gl_account(
                    uow,
                    body=GlAccountIn(
                        code=code,
                        name=name,
                        account_type=AccountType(kind),
                        normal_balance=normal_balance(kind),
                    ),
                )
            account_id = created.id
        accounts[role] = account_id
    if any(status == ConfigStatus.PUBLISHED.value for _, status in versions):
        return
    live = [
        (version_id, status)
        for version_id, status in versions
        if status
        in (
            ConfigStatus.DRAFT.value,
            ConfigStatus.TESTED.value,
            ConfigStatus.SUBMITTED.value,
            ConfigStatus.APPROVED.value,
        )
    ]
    if live:
        version_id, status = live[0]
    elif versions:
        raise LookupError(
            f"account mapping {m.recipe.mapping_name} is {sorted({s for _, s in versions})}"
        )
    else:
        first = FIRST_MONTH
        with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
            version_id = commands.create_account_mapping_version(
                uow,
                body=AccountMappingIn(
                    name=m.recipe.mapping_name,
                    notes=MAPPING_NOTES,
                    effective_from=datetime(first.year, first.month, first.day, tzinfo=UTC),
                ),
            )
        status = ConfigStatus.DRAFT.value
    if status in (ConfigStatus.DRAFT.value, ConfigStatus.TESTED.value):
        with ctx.read() as session:
            present = {
                (text(role), None if purpose is None else text(purpose))
                for role, purpose in session.execute(
                    select(
                        account_mapping_rule.c.account_role, account_mapping_rule.c.clearing_purpose
                    ).where(account_mapping_rule.c.account_mapping_version_id == version_id)
                ).tuples()
            }
        for key in m.recipe.mapping_rules:
            role, _, purpose = key.partition(":")
            if (role, purpose or None) in present:
                continue
            with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                commands.add_account_mapping_rule(
                    uow,
                    version_id,
                    body=AccountMappingRuleIn(
                        account_role=AccountRole(role),
                        clearing_purpose=ClearingPurpose(purpose) if purpose else None,
                        gl_account_id=accounts[role],
                    ),
                )
        with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
            commands.run_account_mapping_tests(uow, version_id)
        with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
            commands.submit_account_mapping_version(uow, version_id, comment=SUBMIT_COMMENT)
        status = ConfigStatus.SUBMITTED.value
    if status == ConfigStatus.SUBMITTED.value:
        with ctx.read() as session:
            pending = session.execute(
                select(approval_request.c.id).where(
                    approval_request.c.subject_type
                    == ApprovalSubjectType.ACCOUNT_MAPPING_VERSION.value,
                    approval_request.c.subject_id == version_id,
                    approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                )
            ).first()
        if pending is None:
            raise LookupError(
                f"account mapping {m.recipe.mapping_name} is SUBMITTED without a pending request"
            )
        ctx.approve(ApprovalSubjectType.ACCOUNT_MAPPING_VERSION, version_id, [cast.reviewer])
        return
    # APPROVED publishes in the approval's own transaction (reference/mapping.approve), so an
    # APPROVED-but-unpublished version is a state this seed does not know.
    raise LookupError(f"account mapping {m.recipe.mapping_name} is {status}")


def _customers(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> dict[str, UUID]:
    from sqlalchemy import select

    from erev_api.db.tables import customer
    from erev_api.domain.reference import commands
    from erev_api.schemas.customers import CustomerIn

    with ctx.read() as session:
        ids: dict[str, UUID] = {
            str(code): UUID(str(value))
            for code, value in session.execute(select(customer.c.code, customer.c.id)).tuples()
        }
    for index in range(1, m.customers + 1):
        code = f"VOL-CUST-{index:04d}"
        if code in ids:
            continue
        with ctx.command(cast.accountant, MASTERDATA_MAINTAIN) as uow:
            created = commands.create_customer(
                uow, body=CustomerIn(code=code, name=f"Volume customer {index:04d}")
            )
        ids[code] = created.id
    return ids


def _templates(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> dict[str, UUID]:
    """The twelve templates, resumed by PERSISTED LIFECYCLE STATE (Codex 0105 RESUME-1): the
    header, its latest version's status (DRAFT → tests → TESTED → SUBMITTED → approved) and the
    presence of its test case decide the first unfinished step; an interrupted run never leaves a
    header behind that a later run mistakes for a published template, and nothing is created
    twice."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from erev_api.db.tables import pob_template, pob_template_version, rule_test_case
    from erev_api.domain.policies import commands
    from erev_api.domain.policies import templates as template_rules
    from erev_api.enums import ApprovalSubjectType, ConfigStatus
    from erev_api.schemas.pob_templates import PobTemplateVersionIn

    effective = datetime(FIRST_MONTH.year, FIRST_MONTH.month, 1, tzinfo=UTC)
    example = {row.mix_class: row for row in m.products}
    with ctx.read() as session:
        headers = {
            str(code): UUID(str(value))
            for code, value in session.execute(
                select(pob_template.c.code, pob_template.c.id)
            ).tuples()
        }
        latest: dict[UUID, tuple[UUID, str]] = {}
        for template_id, version_id, status, _no in session.execute(
            select(
                pob_template_version.c.pob_template_id,
                pob_template_version.c.id,
                pob_template_version.c.status,
                pob_template_version.c.version_no,
            ).order_by(pob_template_version.c.version_no)
        ).tuples():
            latest[UUID(str(template_id))] = (UUID(str(version_id)), str(status))
        cases = {
            UUID(str(value))
            for value in session.execute(
                select(rule_test_case.c.subject_id).where(
                    rule_test_case.c.subject_type == template_rules.SUBJECT_TYPE
                )
            ).scalars()
        }
    ids: dict[str, UUID] = {}
    for template in m.templates:
        template_id = headers.get(template.code)
        if template_id is None:
            with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                template_id = commands.create_pob_template(
                    uow, code=template.code, name=template.name, description=None
                )
        ids[template.code] = template_id
        found = latest.get(template_id)
        version_id, status = (None, None) if found is None else found
        if status in DONE_CONFIG:
            continue
        if status in STUCK_CONFIG:
            raise LookupError(f"template {template.code} version ended {status}; resolve it first")
        if version_id is None:
            body = PobTemplateVersionIn.model_validate(
                {**template.outputs, "effective_from": effective}
            )
            with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                version_id = commands.create_pob_template_version(
                    uow,
                    template_id,
                    changes=body.model_dump(
                        exclude_unset=True, exclude={"effective_from", "source_version_id"}
                    ),
                    effective_from=body.effective_from,
                    source_version_id=None,
                )
            status = ConfigStatus.DRAFT.value
        if status == ConfigStatus.DRAFT.value:
            if version_id not in cases:
                product = example[template.mix_class]
                line: dict[str, Any] = {
                    "obligation_key": "POB-01",
                    "product_code": product.code,
                    "total_price": product.list_price,
                }
                if template.mix_class in {"TIME_ELAPSED", "USAGE"}:
                    line["start_date"] = month_start(1).isoformat()
                    line["end_date"] = month_end(12).isoformat()
                if template.mix_class in {"USAGE", "UNITS_DELIVERED"}:
                    line["quantity"] = "100"
                with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                    commands.create_config_test_case(
                        uow,
                        subject_type=template_rules.SUBJECT_TYPE,
                        subject_id=version_id,
                        name=f"{product.code} booking",
                        facts={
                            "booking_date": month_start(1).isoformat(),
                            "currency": SSP_CURRENCY,
                            "lines": [line],
                        },
                        expected_output={"drafts": [{"obligation_key": "POB-01"}]},
                    )
            with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                commands.run_pob_template_version_tests(uow, version_id)
            status = ConfigStatus.TESTED.value
        if status == ConfigStatus.TESTED.value:
            with ctx.command(cast.accountant, CONFIG_AUTHOR) as uow:
                commands.submit_pob_template_version(uow, version_id, comment=SUBMIT_COMMENT)
        # SUBMITTED (now, or by the interrupted run): the reviewer's approval publishes it.
        ctx.approve(ApprovalSubjectType.POB_TEMPLATE_VERSION, version_id, [cast.reviewer])
    return ids


def _create_products(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> None:
    """Products without a default template (bound after the templates are published)."""
    from sqlalchemy import select

    from erev_api.db.tables import product
    from erev_api.domain.reference import commands
    from erev_api.schemas.products import ProductIn

    with ctx.read() as session:
        existing = {str(code) for code in session.execute(select(product.c.code)).scalars()}
    for spec in m.products:
        if spec.code in existing:
            continue
        with ctx.command(cast.accountant, MASTERDATA_MAINTAIN) as uow:
            commands.create_product(
                uow,
                body=ProductIn(
                    code=spec.code,
                    name=spec.name,
                    revenue_category=spec.revenue_category,
                    unit_of_measure=spec.unit_of_measure,
                ),
            )


def _assess_products(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> None:
    """Manifest products still ``NOT_ASSESSED`` are assessed PRINCIPAL through the real proposal
    and approval (``propose_principal_agent_change`` → PRINCIPAL_AGENT_CHANGE, ``config.approve``);
    products already PRINCIPAL or AGENT are skipped and a pending proposal is resumed by product
    identity — nothing is described as certified all-PRINCIPAL (Codex 0545 §4). ENGINE_SPEC
    S03-R-09 refuses the first computation of a contract while a line's product is
    ``NOT_ASSESSED`` (the T-REF-20 default) — the second database measurement (2026-09-22) found
    the seed never assessed its products. SYNTHETIC seed data following the manifest, not an
    accounting judgement. Resume-safe: PRINCIPAL / AGENT products are skipped; a product whose
    proposal is already PENDING is approved, never re-proposed."""
    from sqlalchemy import select

    from erev_api.db.tables import approval_request, product
    from erev_api.domain.reference import commands
    from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType, PrincipalAgent
    from erev_api.schemas.products import PrincipalAgentChangeIn

    codes = {p.code for p in m.products}
    with ctx.read() as session:
        unassessed = [
            UUID(str(value))
            for value, code in session.execute(
                select(product.c.id, product.c.code)
                .where(product.c.principal_agent == PrincipalAgent.NOT_ASSESSED.value)
                .order_by(product.c.code)
            ).tuples()
            if str(code) in codes
        ]
        pending = {
            UUID(str(value))
            for value in session.execute(
                select(approval_request.c.subject_id).where(
                    approval_request.c.subject_type
                    == ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE.value,
                    approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                )
            ).scalars()
        }
    for product_id in unassessed:
        if product_id not in pending:
            with ctx.command(cast.accountant, MASTERDATA_MAINTAIN) as uow:
                commands.propose_principal_agent_change(
                    uow,
                    product_id=product_id,
                    body=PrincipalAgentChangeIn(
                        principal_agent=PrincipalAgent.PRINCIPAL, rationale=PRINCIPAL_RATIONALE
                    ),
                )
        ctx.approve(ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE, product_id, [cast.reviewer])


def _bind_default_templates(
    ctx: BuildContext, m: VolumeManifest, cast: VolumeCast, template_ids: Mapping[str, UUID]
) -> None:
    """``PATCH /products/{id}`` per product with its published template (REQ-POL-001), the row
    version just read as ``If-Match``."""
    from sqlalchemy import select

    from erev_api.db.tables import product as product_table
    from erev_api.domain.demo.avenmoor import expect_version
    from erev_api.domain.reference import commands

    template_by_code = {p.code: p.template_code for p in m.products}
    with ctx.read() as session:
        rows = session.execute(
            select(product_table.c.id, product_table.c.code, product_table.c.row_version)
        ).all()
    for product_id, code, row_version in rows:
        template_code = template_by_code.get(str(code))
        if template_code is None:
            continue
        with ctx.command(cast.accountant, MASTERDATA_MAINTAIN) as uow:
            commands.update_product(
                uow,
                product_id=UUID(str(product_id)),
                changes={"default_pob_template_id": template_ids[template_code]},
                check_version=expect_version(int(row_version)),
            )


def _ssp(ctx: BuildContext, m: VolumeManifest, cast: VolumeCast) -> None:
    """The SSP book and its two versions, resumed by PERSISTED LIFECYCLE STATE (Codex 0105
    RESUME-1): the book header, each version by its label and status, and its attached study
    decide the first unfinished step; entries upsert idempotently; nothing is created twice.

    The book carries NO currency scope (record §4.22, folded; the supervisor's option A):
    ``SspBookIn.currency`` is the book's scope and S05-R-02 keeps only books whose non-null scope
    members equal the line facts, so a USD-scoped book never served the GBP / EUR contracts —
    4,419 of 10,000 — whose booking computation was refused ``SSP_KEY_NOT_FOUND`` and whose
    activation checklist failed ``PRODUCT_TEMPLATE_SSP``. The entries stay in ``m.ssp_currency``;
    a line in another currency converts at inception spot (POL-079 default) from the seed's
    PUBLISHED spot rate sets — which the bundle carries only between the GROUP's currencies
    (transaction + functional; bundles.py ``currency_codes``), so a USD-only entry could not
    convert for a GBP contract of a GBP entity (FX_RATE_MISSING, S05-R-05; record §4.24). Hence
    every version holds one entry per product PER TENANT CURRENCY with the same synthetic point:
    S05-R-04 ranks the entry in the transaction currency first and no line converts. Synthetic
    seed configuration, not an accounting judgement — no SSP is asserted. Representativeness:
    S05-R-02 multi-book scope matching and the S05-R-05 conversion path are NOT measured by this
    seed; S05-R-04 currency-ranked entry selection IS exercised by the 4,419 GBP / EUR contracts.
    A book of this code found with a currency scope raises by name (no update branch)."""
    import csv
    import io

    from sqlalchemy import select

    from erev_api.db.tables import file_attachment, ssp_book, ssp_book_version
    from erev_api.domain.demo.avenmoor import expect_version
    from erev_api.domain.platform import attachments
    from erev_api.domain.ssp import commands, publication
    from erev_api.enums import (
        ApprovalSubjectType,
        ConfigStatus,
        Distinctness,
        FilePurpose,
        SspMethod,
        SspValueBasis,
    )
    from erev_api.schemas.ssp_books import (
        SspBookIn,
        SspBookVersionIn,
        SspEntriesIn,
        SspEntryIn,
        SspRangeIn,
    )

    with ctx.read() as session:
        found_book = session.execute(
            select(ssp_book.c.id, ssp_book.c.currency).where(ssp_book.c.code == m.ssp_book)
        ).first()
        book_id = None if found_book is None else UUID(str(found_book[0]))
        if found_book is not None and found_book[1] != m.recipe.ssp_book_scope:
            # A book of this code with another currency scope is a state this seed does not
            # know (an earlier generator's USD-scoped book); resolve it, never repurpose it.
            raise LookupError(
                f"SSP book {m.ssp_book} carries the currency scope {found_book[1]!r}; expected"
                f" {m.recipe.ssp_book_scope!r}"
            )
        versions: dict[str, tuple[UUID, str]] = {}
        if book_id is not None:
            for version_id, label, status in session.execute(
                select(
                    ssp_book_version.c.id,
                    ssp_book_version.c.legacy_version_label,
                    ssp_book_version.c.status,
                ).where(ssp_book_version.c.ssp_book_id == book_id)
            ).tuples():
                versions[str(label)] = (UUID(str(version_id)), str(status))
        attached = {
            UUID(str(value))
            for value in session.execute(
                select(file_attachment.c.subject_id).where(
                    file_attachment.c.subject_type == "ssp_book_version",
                    file_attachment.c.voided_at.is_(None),
                )
            ).scalars()
        }
    if book_id is None:
        with ctx.command(cast.accountant, SSP_CREATE) as uow:
            # No currency SCOPE (``SspBookIn.currency`` is the book's scope, not its entries'
            # currency): S05-R-02 keeps only books whose non-null scope members equal the line
            # facts, so a USD-scoped book never served the GBP / EUR contracts (4,419 of 10,000)
            # — their booking computation was refused SSP_KEY_NOT_FOUND and the activation
            # checklist's PRODUCT_TEMPLATE_SSP failed (record §4.22, folded). Every version
            # holds one entry per product PER TENANT CURRENCY (record §4.24): the bundle carries
            # FX rates only between the group's own currencies (bundles.py currency_codes), so a
            # USD-only entry could not convert for a GBP group of a GBP entity (FX_RATE_MISSING,
            # S05-R-05); with an entry in the transaction currency S05-R-04 needs no conversion.
            # Synthetic configuration.
            book_id = commands.create_ssp_book(
                uow,
                body=SspBookIn(
                    code=m.ssp_book, name="Volume SSP book", currency=m.recipe.ssp_book_scope
                ),
            )
    for version in m.ssp_versions:
        found = versions.get(version.label)
        version_id, status = (None, None) if found is None else found
        if status in DONE_CONFIG:
            continue
        if status in STUCK_CONFIG:
            raise LookupError(f"SSP version {version.label} ended {status}; resolve it first")
        points = [
            (product.code, _fraction_money(Decimal(product.list_price), version.uplift))
            for product in m.products
        ]
        if version_id is None:
            with ctx.command(cast.accountant, SSP_CREATE) as uow:
                version_id = commands.create_ssp_book_version(
                    uow,
                    book_id,
                    body=SspBookVersionIn(
                        legacy_version_label=version.label,
                        effective_from_date=date.fromisoformat(version.effective_from),
                        methodology_label=METHODOLOGY,
                    ),
                )
            status = ConfigStatus.DRAFT.value
        if status == ConfigStatus.DRAFT.value:
            # One entry per product per tenant currency, the SAME synthetic point value in each
            # (record §4.24, option A+): the stored key includes the currency, and S05-R-04 ranks
            # the entry in the transaction currency first, so no line needs an FX conversion.
            entries = [
                SspEntryIn(
                    product_code=code,
                    currency=currency,
                    method=SspMethod.OBSERVABLE,
                    value_basis=SspValueBasis.AMOUNT,
                    distinctness=Distinctness.DISTINCT,
                    unit_list_price=None,
                    ranges=[SspRangeIn(point_value=point)],
                )
                for code, point in points
                for currency in m.recipe.ssp_entry_currencies
            ]
            with ctx.command(cast.accountant, SSP_CREATE) as uow:
                commands.upsert_ssp_entries(uow, version_id, body=SspEntriesIn(entries=entries))
            if version_id not in attached:
                study = io.StringIO()
                writer = csv.writer(study, lineterminator="\n")
                writer.writerow(("product_code", "currency", "point_value"))
                for code, point in points:
                    for currency in m.recipe.ssp_entry_currencies:
                        writer.writerow((code, currency, point))
                with ctx.command(cast.accountant) as uow:
                    stored = attachments.upload_file(
                        uow,
                        purpose=FilePurpose.SSP_STUDY.value,
                        stream=io.BytesIO(study.getvalue().encode("utf-8")),
                        original_filename=f"{m.ssp_book}-{version.label}.csv",
                        media_type="text/csv",
                    )
                with ctx.command(cast.accountant) as uow:
                    attachments.attach(
                        uow,
                        file_object_id=UUID(str(stored["id"])),
                        subject_type="ssp_book_version",
                        subject_id=version_id,
                        description=f"{m.ssp_book} {version.label} generated list-price study",
                    )
            with ctx.read() as session:
                row_version = session.execute(
                    select(ssp_book_version.c.row_version).where(
                        ssp_book_version.c.id == version_id
                    )
                ).scalar_one()
            with ctx.command(cast.accountant, SSP_CREATE) as uow:
                publication.submit_ssp_book_version(
                    uow,
                    version_id,
                    comment=SUBMIT_COMMENT,
                    check_version=expect_version(int(row_version)),
                )
        # SUBMITTED (now, or by the interrupted run): the reviewer's approval.
        ctx.approve(ApprovalSubjectType.SSP_BOOK_VERSION, version_id, [cast.reviewer])


def _head(ctx: BuildContext, contract_id: UUID) -> int:
    from sqlalchemy import select

    from erev_api.db.tables import contract

    with ctx.read() as session:
        value = session.execute(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        ).scalar_one()
    return int(value)


def _contracts(
    ctx: BuildContext,
    m: VolumeManifest,
    cast: VolumeCast,
    customers: Mapping[str, UUID],
    chunk: int,
) -> dict[int, UUID]:
    """Every contract booked, Step 1 recorded, its distinct reviews REVIEWED and activated, resumed
    by PERSISTED LIFECYCLE STATE (Codex 0105 RESUME-1): an existing row's status, its
    COLLECTIBILITY judgement's status, the presence of its COLLECTIBILITY_ASSESSED events, the
    ``POB_DISTINCT_OVERRIDE`` records of its obligations (the activation checklist's
    ``DISTINCT_REVIEW`` item — the first database measurement of 2026-09-22 found the seed never
    recorded them) and a pending activation request decide the first unfinished step; a draft
    left by an interrupted run is finished, never re-created."""
    from sqlalchemy import select

    from erev_api.db.tables import (
        approval_request,
        contract,
        contract_event,
        judgement_record,
        obligation,
    )
    from erev_api.domain.contracts import activation, combination, commands
    from erev_api.domain.contracts import events as contract_events
    from erev_api.domain.policies import judgements
    from erev_api.enums import (
        ApprovalRequestStatus,
        ApprovalSubjectType,
        ContractStatus,
        Distinctness,
        JudgementStatus,
        JudgementTopic,
    )
    from erev_api.schemas.combinations import SuggestionDismissIn
    from erev_api.schemas.contracts import ContractCreateIn, DistinctReviewIn, SubmitActivationIn
    from erev_api.schemas.events import EventAppendIn, EventAppendItemIn
    from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn

    with ctx.read() as session:
        present = {
            str(external_id): (UUID(str(value)), str(status))
            for external_id, value, status in session.execute(
                select(contract.c.external_id, contract.c.id, contract.c.status)
            ).tuples()
        }
        records = {
            UUID(str(subject_id)): (UUID(str(record_id)), str(status))
            for subject_id, record_id, status in session.execute(
                select(
                    judgement_record.c.subject_id, judgement_record.c.id, judgement_record.c.status
                ).where(
                    judgement_record.c.subject_type == "contract",
                    judgement_record.c.topic == JudgementTopic.COLLECTIBILITY.value,
                )
            ).tuples()
        }
        assessed = {
            UUID(str(value))
            for value in session.execute(
                select(contract_event.c.contract_id)
                .where(
                    contract_event.c.event_type == ContractEventType.COLLECTIBILITY_ASSESSED.value
                )
                .distinct()
            ).scalars()
        }
        # Distinct reviews already recorded: obligation id → (record id, status).
        distinct_records = {
            UUID(str(subject_id)): (UUID(str(record_id)), str(status))
            for subject_id, record_id, status in session.execute(
                select(
                    judgement_record.c.subject_id, judgement_record.c.id, judgement_record.c.status
                ).where(
                    judgement_record.c.subject_type == "obligation",
                    judgement_record.c.topic == JudgementTopic.POB_DISTINCT_OVERRIDE.value,
                )
            ).tuples()
        }
        pending_activation = {
            UUID(str(value))
            for value in session.execute(
                select(approval_request.c.subject_id).where(
                    approval_request.c.subject_type
                    == ApprovalSubjectType.CONTRACT_ACTIVATION.value,
                    approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                )
            ).scalars()
        }
    finished = {
        ContractStatus.ACTIVE.value,
        ContractStatus.COMPLETED.value,
        ContractStatus.TERMINATED.value,
    }
    ids: dict[int, UUID] = {}
    for start in range(0, len(m.contracts), chunk):
        for spec in m.contracts[start : start + chunk]:
            found = present.get(spec.external_id)
            if found is None:
                body = ContractCreateIn.model_validate(
                    contract_body(spec, customers[spec.customer_code])
                )
                with ctx.command(cast.accountant, CONTRACT_CREATE) as uow:
                    created = commands.create_contract(uow, body=body)
                contract_id, status = created.id, ContractStatus.DRAFT.value
            else:
                contract_id, status = found
            ids[spec.seq] = contract_id
            if status in finished:
                continue
            if status != ContractStatus.DRAFT.value:
                raise LookupError(f"contract {spec.external_id} is {status}; resolve it first")
            # Step 1: a reviewed COLLECTIBILITY record, finished from wherever it stopped.
            record = records.get(contract_id)
            if record is None:
                with ctx.command(cast.accountant, JUDGEMENT_CREATE) as uow:
                    created_record = judgements.create_judgement(
                        uow,
                        body=JudgementCreateIn(
                            topic=JudgementTopic.COLLECTIBILITY,
                            subject_type="contract",
                            subject_id=contract_id,
                            conclusion=COLLECTIBILITY_CONCLUSION,
                            rationale=COLLECTIBILITY_RATIONALE,
                            questionnaire={"criteria": dict(STEP1_CRITERIA_MET)},
                        ),
                    )
                record = (created_record.id, JudgementStatus.DRAFT.value)
            record_id, record_status = record
            if record_status == JudgementStatus.DRAFT.value:
                with ctx.command(cast.accountant, JUDGEMENT_CREATE) as uow:
                    judgements.submit_judgement(
                        uow, judgement_id=record_id, body=JudgementSubmitIn(comment=SUBMIT_COMMENT)
                    )
                record_status = JudgementStatus.SUBMITTED.value
            if record_status == JudgementStatus.SUBMITTED.value:
                ctx.approve(ApprovalSubjectType.JUDGEMENT_RECORD, record_id, [cast.reviewer])
            elif record_status != JudgementStatus.REVIEWED.value:
                raise LookupError(f"judgement of {spec.external_id} is {record_status}")
            # The probable assessment per enabled book: one append, all or nothing.
            if contract_id not in assessed:
                with ctx.read() as session:
                    entity_id = session.execute(
                        select(contract.c.contracting_entity_id).where(contract.c.id == contract_id)
                    ).scalar_one()
                    books = activation.enabled_books(session, UUID(str(entity_id)))
                assessment = EventAppendIn(
                    events=[
                        EventAppendItemIn(
                            event_type=ContractEventType.COLLECTIBILITY_ASSESSED,
                            effective_date=date.fromisoformat(spec.inception_date),
                            payload={
                                "book": code,
                                "is_probable": True,
                                "judgement_record_id": str(record_id),
                            },
                        )
                        for code in books
                    ]
                )
                with ctx.command(cast.accountant, EVENT_RECORD) as uow:
                    contract_events.record_events(
                        uow,
                        contract_id=contract_id,
                        expected_stream_version=_head(ctx, contract_id),
                        body=assessment,
                    )
            # Step 2: the distinct review of every reviewable obligation (DISTINCT_REVIEW), through
            # the real command and the reviewer's approval; REVIEWED ones skipped, SUBMITTED ones
            # approved.
            needed = distinct_reviews_needed(m, spec)
            if needed:
                with ctx.read() as session:
                    obligation_ids = {
                        str(key): UUID(str(value))
                        for key, value in session.execute(
                            select(obligation.c.obligation_key, obligation.c.id).where(
                                obligation.c.contract_id == contract_id
                            )
                        ).tuples()
                    }
                for key in needed:
                    # Codex 0431 §1 (a): record_distinct_review always creates a NEW record, so the
                    # persisted record decides — absent → create; DRAFT → submit; SUBMITTED →
                    # decide its EXISTING request; REVIEWED → reuse; anything else refused by name.
                    review = distinct_records.get(obligation_ids[key])
                    if review is None:
                        with ctx.command(cast.accountant, JUDGEMENT_CREATE) as uow:
                            recorded = activation.record_distinct_review(
                                uow,
                                contract_id=contract_id,
                                obligation_key=key,
                                body=DistinctReviewIn(
                                    distinctness=Distinctness.DISTINCT,
                                    rationale=DISTINCT_RATIONALE,
                                ),
                            )
                        review_id, review_status = (
                            recorded.judgement_record_id,
                            JudgementStatus.SUBMITTED.value,
                        )
                    else:
                        review_id, review_status = review
                    if review_status == JudgementStatus.REVIEWED.value:
                        continue
                    if review_status == JudgementStatus.DRAFT.value:
                        with ctx.command(cast.accountant, JUDGEMENT_CREATE) as uow:
                            judgements.submit_judgement(
                                uow,
                                judgement_id=review_id,
                                body=JudgementSubmitIn(comment=SUBMIT_COMMENT),
                            )
                        review_status = JudgementStatus.SUBMITTED.value
                    if review_status != JudgementStatus.SUBMITTED.value:
                        raise LookupError(
                            f"distinct review of {spec.external_id} {key} is {review_status}"
                        )
                    ctx.approve(ApprovalSubjectType.JUDGEMENT_RECORD, review_id, [cast.reviewer])
            # S02-R-14 raises COMBINATION_SUGGESTED for every other contract of the customer whose
            # inception lies within the 30-day detection window (POL-016 default; 4,050 pairs,
            # 3,332 contracts at full scale), and the checklist's COMBINATION_SUGGESTIONS item
            # fails while one is open (record §4.25). The generated customers' contracts are
            # independent by construction, so each open suggestion naming the contract is
            # dismissed through the real command with that rationale — resume-safe: only OPEN
            # items are read. Synthetic data, not an accounting judgement on combination.
            # Representativeness: the combination-review path is exercised only as dismissal.
            with ctx.read() as session:
                open_suggestions = [
                    UUID(str(row["id"]))
                    for row in session.execute(
                        combination.suggestions_statement(contract_id)
                    ).mappings()
                ]
            for item_id in open_suggestions:
                with ctx.command(cast.accountant, CONTRACT_CREATE) as uow:
                    combination.dismiss_suggestion(
                        uow,
                        item_id=item_id,
                        body=SuggestionDismissIn(rationale=SUGGESTION_RATIONALE),
                    )
            # Activation: submitted now unless the interrupted run left the request pending.
            if contract_id not in pending_activation:
                with ctx.command(cast.accountant, CONTRACT_CREATE) as uow:
                    activation.submit_activation(
                        uow,
                        contract_id=contract_id,
                        expected_stream_version=_head(ctx, contract_id),
                        body=SubmitActivationIn(comment=SUBMIT_COMMENT),
                    )
            # An activation of USD 1,000,000.00 and more routes a second step, held by a
            # Controller (PRD §2.5; ``activation.activation_flags``): the reviewer decides the
            # first and the cast's controller the second, as for an estimate version.
            ctx.approve(
                ApprovalSubjectType.CONTRACT_ACTIVATION,
                contract_id,
                [cast.reviewer, cast.controller],
            )
    return ids


def _append_month(
    ctx: BuildContext,
    m: VolumeManifest,
    cast: VolumeCast,
    contract_ids: Mapping[int, UUID],
    month: int,
    chunk: int,
    *,
    done: Mapping[str, frozenset[int]] | None = None,
    parts_done: Mapping[str, frozenset[tuple[int, int]]] | None = None,
    runtime: JobRuntime | None = None,
) -> MonthTally:
    """Send the events recorded in ``month`` contract by contract, each contract-month in the
    order of ``month_steps``: by effective date, ``ESTIMATE_CHANGED`` through the estimate commands
    (D-98 148 A5 (4)) and ``CONTRACT_AMENDED`` through the CTR-17 modification commands at their
    place among the dates, the events between two such commands as one append of at most
    ``MAX_EVENTS``. Returns the month's ``MonthTally``: newly appended (what the append command
    persisted — a deferred computation is still a fresh append, Codex 0233), reused (an effect an
    earlier run already persisted — an appended contract-month or part, a complete estimate
    version, an APPLIED modification — is REUSED, never reported as appended; Codex 0206 §5) and
    counted-not-appended by type. An append that holds a manual event waits for the event
    reviewer's approval, which appends it (``_record_batch``; BUILD_SPEC CTR-6).

    The resume (``done``, ``parts_done``; ``perf_seed.read_ledger``). An append is found again by
    its comment (``append_comment``): the month's last append by the plain comment of ``done``,
    an earlier one of a divided month by its part in ``parts_done``; a command of its own finds
    its version or its modification itself. A contract-month of one append whose month is in
    ``done`` is skipped whole. A divided one is walked again step by step, because its last
    durable step may be a command that follows its last append: each append that is done is
    counted REUSED and not sent."""
    from erev_api.domain.contracts import events as contract_events
    from erev_api.schemas.events import MAX_EVENTS, EventAppendItemIn

    appended = reused = 0
    deferred: dict[str, int] = {}
    by_contract = {c.seq: c for c in m.contracts}
    grouped: dict[int, list[VolumeEvent]] = {}
    for event in m.events_for_month(month):  # one pass over the stream per month
        grouped.setdefault(event.contract_seq, []).append(event)
    size = min(chunk, MAX_EVENTS)
    manual = {member.value for member in contract_events.MANUAL_TYPES}
    documents: dict[str, UUID] = {}

    def evidence_of(entity_code: str) -> UUID:
        """The month's evidence document of one entity's manual events, stored by the accountant
        at its first use (a resumed month stores it again; nothing reads the earlier file)."""
        if entity_code not in documents:
            documents[entity_code] = _store_evidence(
                ctx,
                cast,
                evidence_filename(entity_code, month),
                evidence_document(
                    (by_contract[seq].external_id, event)
                    for seq in sorted(grouped)
                    if by_contract[seq].entity_code == entity_code
                    for event in grouped[seq]
                    if event.event_type in manual
                ),
            )
        return documents[entity_code]

    for seq in sorted(grouped):
        spec = by_contract[seq]
        sent = sent_events(spec, grouped[seq])
        steps = month_steps(sent)
        whole = bool(done) and month in (done or {}).get(spec.external_id, frozenset())
        if whole and all(step.part for step in steps):
            # The earlier run appended this contract-month (its submission comment is the ledger):
            # every event of it is a persisted effect found again — REUSED, so the returned
            # counters cover the manifest across a resume (Codex 0233 POSTCOMMIT-WITNESS-1).
            reused += len(grouped[seq])
            continue
        if whole:
            reused += len(grouped[seq]) - len(sent)
        else:
            # Counted, never appended: the product refuses these types at record_events until
            # their own command lands (record §4.26).
            kept = {event.seq for event in sent}
            for event in grouped[seq]:
                if event.seq not in kept:
                    deferred[event.event_type] = deferred.get(event.event_type, 0) + 1
        contract_id = contract_ids[seq]
        earlier = (parts_done or {}).get(spec.external_id, frozenset())
        for step in steps:
            if step.part == 0:
                (event,) = step.events
                if event.event_type == ContractEventType.ESTIMATE_CHANGED.value:
                    outcome = _apply_estimate(ctx, cast, contract_id, spec, event)
                else:
                    outcome = _apply_modification(ctx, cast, m, contract_id, spec, event, runtime)
                new, old, apart = tally([outcome])
                appended += new
                reused += old
                if apart:
                    deferred[SEPARATE_OUTCOME] = deferred.get(SEPARATE_OUTCOME, 0) + apart
                continue
            if (whole and step.part == step.parts) or (month, step.part) in earlier:
                reused += len(step.events)  # this append is in the ledger: found again, not sent
                continue
            if len(step.events) > size:
                # The resume ledger knows an append by its comment; a second append under one
                # comment would make an interruption between them unrecoverable, so refuse loudly.
                raise LookupError(
                    f"{spec.external_id} month {month}: {len(step.events)} events exceed one "
                    f"append ({size})"
                )
            items = [
                EventAppendItemIn(
                    event_type=ContractEventType(event.event_type),
                    effective_date=event.effective_date,
                    obligation_key=event.obligation_key,
                    # ``sent_events`` keeps no event without a payload.
                    payload=payload(event, spec) or {},
                )
                for event in step.events
            ]
            newly = _record_batch(
                ctx,
                cast,
                contract_id,
                items,
                comment=append_comment(month, m.industry_cluster, step.part, step.parts),
                evidence=partial(evidence_of, spec.entity_code),
            )
            appended += newly
            reused += len(items) - newly
    return MonthTally(appended, reused, deferred)


EVIDENCE_MEDIA_TYPE: Final = "text/csv"
EVIDENCE_HEADER: Final = "contract,event_type,effective_date,obligation_key"


def evidence_filename(entity_code: str, month: int) -> str:
    return f"volume-{entity_code.lower()}-month-{month:02d}-evidence.csv"


def evidence_document(rows: Iterable[tuple[str, VolumeEvent]]) -> bytes:
    """The evidence document of one entity's manual events of a month (04 §16.3
    ``evidence_file_ids``; BUILD_SPEC CTR-6) as CSV (UTF-8, LF line ends): one row per manual
    event — a delivery, a return, a milestone, a cost and, since generator version 6, a usage
    report — with the contract, the event type, the effective date and the obligation, in stream
    order. Generated with the dataset: it states what the manifest states and nothing a person
    observed. Pure."""
    lines = [EVIDENCE_HEADER]
    lines.extend(
        ",".join(
            (
                external_id,
                event.event_type,
                event.effective_date.isoformat(),
                event.obligation_key or "",
            )
        )
        for external_id, event in rows
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def needs_evidence(items: Iterable[Any]) -> bool:
    """Whether a person's request of ``items`` (API-S-EventAppend items) is refused without an
    evidence file (04 §16.3 ``evidence_file_ids``, rule REQ-DAT-014): it holds a progress, a
    milestone or a cost event, or a delivery whose trigger is acceptance. The product's rule,
    read from its own constants. Pure."""
    from erev_api.domain.contracts import events as contract_events

    return any(
        item.event_type in contract_events.EVIDENCE_TYPES
        or (
            item.event_type is ContractEventType.DELIVERY_RECORDED
            and str(item.payload.get("trigger")) == contract_events.ACCEPTANCE_TRIGGER
        )
        for item in items
    )


def _store_evidence(ctx: BuildContext, cast: VolumeCast, filename: str, document: bytes) -> UUID:
    """``POST /files`` with purpose ``ATTACHMENT`` as the accountant: the stored file's id."""
    import io

    from erev_api.domain.platform import attachments
    from erev_api.enums import FilePurpose

    with ctx.command(cast.accountant) as uow:
        stored = attachments.upload_file(
            uow,
            purpose=FilePurpose.ATTACHMENT.value,
            stream=io.BytesIO(document),
            original_filename=filename,
            media_type=EVIDENCE_MEDIA_TYPE,
        )
    return UUID(str(stored["id"]))


def _record_batch(
    ctx: BuildContext,
    cast: VolumeCast,
    contract_id: UUID,
    items: Sequence[Any],
    *,
    comment: str,
    evidence: Callable[[], UUID],
) -> int:
    """One contract-month through ``record_events`` as the accountant; how many of its events
    THIS run persisted. A request that holds a manual event — a delivery, a return, a milestone,
    a cost or (04 rev 1.238) a usage report: ``events.MANUAL_TYPES`` is the product's list —
    appends nothing (BUILD_SPEC CTR-6; 04 §16.3 "Manual events"; PRD BR-REC-01): it waits whole
    as ONE event submission — with the month's evidence document where the product asks for one
    — and the event reviewer's approval appends it as SYSTEM for the accountant and computes the
    group. Every other request is appended directly (``append_outcome``). Resumed by PERSISTED
    LIFECYCLE STATE: the submission that carries this contract-month's comment is finished from
    its status (SUBMITTED → approve; APPLIED done, nothing counted; REJECTED / VOIDED refused by
    name), never sent a second time."""
    from sqlalchemy import select

    from erev_api.db.tables import event_submission
    from erev_api.domain.contracts import events as contract_events
    from erev_api.enums import ApprovalSubjectType, ModificationStatus
    from erev_api.schemas.events import EventAppendIn

    with ctx.read() as session:
        waiting = (
            session.execute(
                select(event_submission.c.id, event_submission.c.status).where(
                    event_submission.c.contract_id == contract_id,
                    event_submission.c.comment == comment,
                )
            )
            .mappings()
            .one_or_none()
        )
    if waiting is not None:
        submission_id, status = UUID(str(waiting["id"])), str(waiting["status"])
        if status == ModificationStatus.APPLIED.value:
            return 0
        if status != ModificationStatus.SUBMITTED.value:
            raise LookupError(f"event submission {submission_id} ({comment}) ended {status}")
    else:
        before = _head(ctx, contract_id)
        attached = [evidence()] if needs_evidence(items) else []
        with ctx.command(cast.accountant, EVENT_RECORD) as uow:
            recorded = contract_events.record_events(
                uow,
                contract_id=contract_id,
                expected_stream_version=before,
                body=EventAppendIn(events=list(items), comment=comment, evidence_file_ids=attached),
            )
        if recorded.submission is None:
            return append_outcome(recorded, len(items))
        submission_id = recorded.submission.event_submission_id
    ctx.approve(ApprovalSubjectType.MANUAL_EVENT, submission_id, [cast.event_reviewer])
    with ctx.read() as session:
        applied = session.execute(
            select(event_submission.c.applied_event_ids).where(
                event_submission.c.id == submission_id
            )
        ).scalar_one()
    if len(applied) != len(items):
        raise LookupError(
            f"event submission {submission_id} ({comment}) applied {len(applied)} of "
            f"{len(items)} events"
        )
    return len(items)


def estimate_rationale(event: VolumeEvent) -> str:
    """The version's ``rationale``, unique per manifest event: the resume marker by which an
    interrupted month finds the version it already created (Codex 0105 RESUME-1, the same seam
    closed for ESTIMATE_CHANGED — a re-run must never create a second version for one event)."""
    return (
        f"Volume dataset estimate change (PRF-2), event {event.seq}, month {event.effective_month}."
    )


ESTIMATE_VERSION_SUBJECT: Final = "estimate_version"  # of an attachment and of a judgement record
ESTIMATE_EVIDENCE_HEADER: Final = "contract,element,effective_date,manifest_event"
ESTIMATE_EVIDENCE_NOTE: Final = "Generated estimate evidence of the volume dataset (PRF-2)."
CONSTRAINT_CONCLUSION: Final = (
    "The constrained amount of this estimate version is the amount the manifest states."
)
CONSTRAINT_RATIONALE: Final = (
    "Generated volume estimate: the constraint follows the manifest; synthetic seed data, not an "
    "accounting judgement on variable consideration (PRF-2)."
)


def estimate_evidence_filename(external_id: str, event: VolumeEvent) -> str:
    return f"volume-{external_id.lower()}-estimate-event-{event.seq}-evidence.csv"


def estimate_evidence_document(external_id: str, element_code: str, event: VolumeEvent) -> bytes:
    """The evidence document of one estimate version (04 §16.14 "Estimates" rev 1.241: a version
    is submitted with its evidence attached; BUILD_SPEC CTR-12) as CSV (UTF-8, LF line ends): the
    contract, the element, the effective date and the manifest event the version stands for.
    Generated with the dataset: it states what the manifest states and nothing a person
    observed. Pure."""
    row = ",".join((external_id, element_code, event.effective_date.isoformat(), str(event.seq)))
    return f"{ESTIMATE_EVIDENCE_HEADER}\n{row}\n".encode()


def _ready_estimate_version(
    ctx: BuildContext,
    cast: VolumeCast,
    spec: VolumeContract,
    event: VolumeEvent,
    version_id: UUID,
    element_code: str,
    *,
    constrained: bool,
) -> None:
    """What the submission of a DRAFT estimate version asks beyond its values (04 §16.14 rev
    1.241; PRD IMP-138, IMP-140, ERR-94), through the real commands as the accountant, finished
    from PERSISTED STATE so that a resumed run repeats nothing:

    - its evidence: one generated document (``estimate_evidence_document``), stored and attached
      unless the version already holds an attachment;
    - with ``constrained`` (a variable-consideration version): the ``CONSTRAINT`` record of its
      element — a record of the version itself, which holds no contract and appends nothing —
      created, submitted, reviewed by the cast's reviewer and named on the version. A record an
      interrupted run left is finished from its status (DRAFT → submit → review; SUBMITTED →
      review; REVIEWED → named); any other status is refused by name.

    Every version takes both, also one whose values repeat the approved version's: the product
    would take that one as an attestation of no change without a file, and asks of a record it
    names what it asks of any. Synthetic seed data, not an accounting judgement."""
    from sqlalchemy import select

    from erev_api.db.tables import estimate_version, file_attachment, judgement_record
    from erev_api.domain.contracts import estimates
    from erev_api.domain.platform import attachments
    from erev_api.domain.policies import judgements
    from erev_api.enums import ApprovalSubjectType, JudgementStatus, JudgementTopic
    from erev_api.schemas.estimates import EstimateVersionUpdateIn
    from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn

    subject = ESTIMATE_VERSION_SUBJECT
    with ctx.read() as session:
        attached = session.execute(
            select(file_attachment.c.id)
            .where(
                file_attachment.c.subject_type == subject,
                file_attachment.c.subject_id == version_id,
                file_attachment.c.voided_at.is_(None),
            )
            .limit(1)
        ).first()
        named = session.execute(
            select(estimate_version.c.judgement_record_id).where(
                estimate_version.c.id == version_id
            )
        ).scalar_one()
        record = (
            session.execute(
                select(judgement_record.c.id, judgement_record.c.status).where(
                    judgement_record.c.subject_type == subject,
                    judgement_record.c.subject_id == version_id,
                    judgement_record.c.topic == JudgementTopic.CONSTRAINT.value,
                )
            )
            .mappings()
            .one_or_none()
        )
    if attached is None:
        stored = _store_evidence(
            ctx,
            cast,
            estimate_evidence_filename(spec.external_id, event),
            estimate_evidence_document(spec.external_id, element_code, event),
        )
        with ctx.command(cast.accountant) as uow:
            attachments.attach(
                uow,
                file_object_id=stored,
                subject_type=subject,
                subject_id=version_id,
                description=ESTIMATE_EVIDENCE_NOTE,
            )
    if not constrained:
        return
    if record is None:
        with ctx.command(cast.accountant, JUDGEMENT_CREATE) as uow:
            created = judgements.create_judgement(
                uow,
                body=JudgementCreateIn(
                    topic=JudgementTopic.CONSTRAINT,
                    subject_type=subject,
                    subject_id=version_id,
                    conclusion=CONSTRAINT_CONCLUSION,
                    rationale=CONSTRAINT_RATIONALE,
                    questionnaire={"estimate_key": element_code, "remote": False},
                ),
            )
        record_id, record_status = created.id, JudgementStatus.DRAFT.value
    else:
        record_id, record_status = UUID(str(record["id"])), str(record["status"])
    if record_status == JudgementStatus.DRAFT.value:
        with ctx.command(cast.accountant, JUDGEMENT_CREATE) as uow:
            judgements.submit_judgement(
                uow, judgement_id=record_id, body=JudgementSubmitIn(comment=SUBMIT_COMMENT)
            )
        record_status = JudgementStatus.SUBMITTED.value
    if record_status == JudgementStatus.SUBMITTED.value:
        ctx.approve(ApprovalSubjectType.JUDGEMENT_RECORD, record_id, [cast.reviewer])
    elif record_status != JudgementStatus.REVIEWED.value:
        raise LookupError(
            f"CONSTRAINT record of the estimate version for event {event.seq} of "
            f"{spec.external_id} is {record_status}"
        )
    if named is None or UUID(str(named)) != record_id:
        with ctx.command(cast.accountant, EVENT_RECORD) as uow:
            estimates.update_version(
                uow,
                version_id=version_id,
                body=EstimateVersionUpdateIn(judgement_record_id=record_id),
            )


def _apply_estimate(
    ctx: BuildContext, cast: VolumeCast, contract_id: UUID, spec: VolumeContract, event: VolumeEvent
) -> str:
    """One ``ESTIMATE_CHANGED`` event through the real estimate commands (D-20; D-98 148 A5 (4)):
    the T-CON-12 element on first use (an ``EAC`` element on the cost-to-cost obligation, or the
    contract's ``VARIABLE_CONSIDERATION`` bonus element), a DRAFT version with the new amount,
    what its submission asks of it (``_ready_estimate_version``: its evidence document and, for
    the bonus, its reviewed ``CONSTRAINT`` record), submit, then the reviewer's approval, which
    appends ``ESTIMATE_CHANGED`` as SYSTEM and recomputes the group. Resumed by PERSISTED
    LIFECYCLE STATE: the version carrying this event's ``estimate_rationale`` is finished from
    its status (DRAFT → made ready → submit → approve; SUBMITTED → approve; APPROVED / SUPERSEDED
    done; REJECTED / WITHDRAWN refused by name), never re-created. Returns ``REUSED`` when the
    version was already complete, else ``APPLIED`` (Codex 0206 §5)."""
    from sqlalchemy import select

    from erev_api.db.tables import estimate, estimate_version
    from erev_api.domain.contracts import estimates
    from erev_api.enums import ApprovalSubjectType, ConfigStatus, EstimateKind, EstimateMethod
    from erev_api.schemas.estimates import (
        EstimateCreateIn,
        EstimateVersionCreateIn,
        EstimateVersionSubmitIn,
    )

    detail = dict(event.detail)
    kind = EstimateKind(str(detail.get("estimate_kind", EstimateKind.VARIABLE_CONSIDERATION.value)))
    is_eac = kind is EstimateKind.EAC
    element_code = f"EAC-{event.obligation_key}" if is_eac else "VC-BONUS"
    with ctx.read() as session:
        found = session.execute(
            select(estimate.c.id).where(
                estimate.c.contract_id == contract_id, estimate.c.element_code == element_code
            )
        ).scalar_one_or_none()
    estimate_id = None if found is None else UUID(str(found))
    if estimate_id is None:
        create = EstimateCreateIn.model_validate(
            {
                "estimate_kind": kind.value,
                "element_code": element_code,
                "obligation_key": event.obligation_key if is_eac else None,
                "vc_element_type": None if is_eac else "BONUS",
                "method": EstimateMethod.ENTERED_AMOUNT.value,
            }
        )
        with ctx.command(cast.accountant, EVENT_RECORD) as uow:
            estimate_id = estimates.create_estimate(uow, contract_id=contract_id, body=create).id
    rationale = estimate_rationale(event)
    with ctx.read() as session:
        existing = (
            session.execute(
                select(estimate_version.c.id, estimate_version.c.status).where(
                    estimate_version.c.estimate_id == estimate_id,
                    estimate_version.c.rationale == rationale,
                )
            )
            .mappings()
            .one_or_none()
        )
    if existing is not None:
        version_id, status = UUID(str(existing["id"])), str(existing["status"])
        if status in DONE_CONFIG:
            return REUSED
        if status in STUCK_CONFIG:
            raise LookupError(
                f"estimate version for event {event.seq} of {spec.external_id} ended {status}"
            )
    else:
        if "amount" in detail:
            amount = Decimal(str(detail["amount"]))
        else:  # the VC bonus: two percent of the contract, new each change (deterministic)
            total = sum((Decimal(o.total_price) for o in spec.obligations), Decimal(0))
            amount = total * Decimal(2 + event.effective_month % 3) / Decimal(100)
        version: dict[str, Any] = {
            "effective_date": event.effective_date.isoformat(),
            "method": EstimateMethod.ENTERED_AMOUNT.value,
            "currency": spec.currency,
            "rationale": rationale,
        }
        if is_eac:
            version["expected_total_amount"] = _money(amount)
        else:
            version["unconstrained_amount"] = _money(amount)
            version["constrained_amount"] = _money(amount * Decimal("0.9"))
        with ctx.command(cast.accountant, EVENT_RECORD) as uow:
            created = estimates.create_version(
                uow, estimate_id=estimate_id, body=EstimateVersionCreateIn.model_validate(version)
            )
        version_id, status = created.id, ConfigStatus.DRAFT.value
    if status == ConfigStatus.DRAFT.value:
        _ready_estimate_version(
            ctx, cast, spec, event, version_id, element_code, constrained=not is_eac
        )
        with ctx.command(cast.accountant, EVENT_RECORD) as uow:
            estimates.submit_version(
                uow, version_id=version_id, body=EstimateVersionSubmitIn(comment=SUBMIT_COMMENT)
            )
    # SUBMITTED (now, or by the interrupted run): the reviewer's approval appends the event. A
    # version whose P&L impact reaches USD 50,000.00 takes a second step that only a Controller
    # decides (PRD §2.5; 04 T-PLT-17 ``PL_IMPACT_GE_50K``): the cast's controller, after the
    # reviewer.
    ctx.approve(ApprovalSubjectType.ESTIMATE_VERSION, version_id, [cast.reviewer, cast.controller])
    return APPLIED


def modification_body(
    m: VolumeManifest, spec: VolumeContract, event: VolumeEvent
) -> dict[str, Any]:
    """The API-S-Modification create members (04 T-CON-06 ``lines``: ``{obligation_key, action,
    product_code, quantity_delta, consideration_delta, start_date, end_date}``) of a manifest
    ``CONTRACT_AMENDED`` event, pure. The manifest's ``treatment`` is the INTENDED shape — the
    engine's S06 classification governs and the seed accepts its proposal (REQ-MOD-001/-002):
    PROSPECTIVE → ``ADD_OBLIGATION`` adding a distinct subscription product priced below its SSP
    (S06-R-04: distinct, not at SSP); CUMULATIVE_CATCH_UP → ``PRICE_CHANGE`` on an existing
    obligation, a cost-to-cost or milestone one when the contract has it (remaining goods not
    distinct, S06-R-05). Currency = the contract's (T-CON-06 native money); ``reference`` unique
    per event.

    The added line runs twelve months from the effective month, whatever the contract's own
    term, so the generic kind is the one ENGINE_SPEC S06-R-19 admits for it: ``UPGRADE`` is a
    CHANGE line on the subscription obligation and ``CO_TERM`` an ADD line ending on the original
    end date — either kind with this line is refused by name at ``/classify`` (04 §16.14 rev 1.84;
    PRD ERR-55). The kind reaches the engine's shape gate only, never a figure."""
    detail = dict(event.detail)
    treatment = str(detail.get("treatment", "PROSPECTIVE"))
    start = event.effective_date
    body: dict[str, Any] = {
        "effective_date": start.isoformat(),
        "reference": f"{spec.external_id}/MOD-{event.seq}",
        "rationale": (
            f"Volume dataset modification (PRF-2), month {event.effective_month}; intended "
            f"treatment {treatment}."
        ),
    }
    if treatment == "CUMULATIVE_CATCH_UP":
        preferred = [o for o in spec.obligations if o.mix_class in {"COST_TO_COST", "MILESTONE"}]
        target = (preferred or list(spec.obligations))[0]
        delta = Decimal(target.total_price) * Decimal("0.10")
        body["kind"] = "PRICE_CHANGE"
        body["lines"] = [
            {
                "obligation_key": target.key,
                "action": "CHANGE",
                "quantity_delta": "0",
                "consideration_delta": {"amount": _money(delta), "currency": spec.currency},
            }
        ]
        return body
    subscriptions = [p for p in m.products if p.mix_class == "TIME_ELAPSED"] or list(m.products)
    product = subscriptions[event.seq % len(subscriptions)]
    below_ssp = Decimal(product.list_price) * Decimal("0.85")
    end = month_start(event.effective_month + 12) - timedelta(days=1)
    body["kind"] = "ADD_OBLIGATION"
    body["lines"] = [
        {
            "obligation_key": f"MOD-{event.seq}",
            "action": "ADD",
            "product_code": product.code,
            "quantity_delta": "1",
            "consideration_delta": {"amount": _money(below_ssp), "currency": spec.currency},
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
    ]
    return body


def _apply_modification(
    ctx: BuildContext,
    cast: VolumeCast,
    m: VolumeManifest,
    contract_id: UUID,
    spec: VolumeContract,
    event: VolumeEvent,
    runtime: JobRuntime | None,
) -> str:
    """One ``CONTRACT_AMENDED`` through the real CTR-17 commands (no direct inserts): DRAFT
    (``create_modification``) → ``classify`` (the engine's proposal; the seed chooses nothing
    else) → the impact preview run inline through the registered ``CONTRACT_COMPUTE`` handler in
    mode ``MODIFICATION_PREVIEW`` with the members ``request_preview`` defers (no job row is left
    queued) → ``submit`` (REQ-PLT-015 satisfied by that preview) → the reviewer's approval, which
    appends ``CONTRACT_AMENDED`` as SYSTEM and recomputes. Resume-safe by ``reference``: an APPLIED
    row is skipped (``REUSED``), a DRAFT or SUBMITTED one continues (``APPLIED``). Returns
    ``SEPARATE`` when the engine classified ``SEPARATE_CONTRACT`` (the approval books a new
    contract; nothing is amended here) — Codex 0206 §5: the three outcomes are reported apart."""
    from sqlalchemy import select

    from erev_api.db.tables import modification
    from erev_api.domain.contracts import modifications
    from erev_api.domain.contracts.compute_job import MODIFICATION_PREVIEW_MODE
    from erev_api.enums import ApprovalSubjectType, JobKind, ModificationStatus
    from erev_api.jobs import registry
    from erev_api.schemas.modifications import ModificationCreateIn, ModificationSubmitIn

    body = modification_body(m, spec, event)
    with ctx.read() as session:
        found = (
            session.execute(
                select(
                    modification.c.id, modification.c.status, modification.c.treatment_summary
                ).where(
                    modification.c.contract_id == contract_id,
                    modification.c.reference == body["reference"],
                )
            )
            .mappings()
            .one_or_none()
        )
    if found is not None and str(found["status"]) == ModificationStatus.APPLIED.value:
        separate = str(found["treatment_summary"] or "") == "SEPARATE_CONTRACT"
        return SEPARATE if separate else REUSED
    if found is not None and str(found["status"]) not in (
        ModificationStatus.DRAFT.value,
        ModificationStatus.SUBMITTED.value,
    ):
        # REJECTED / VOIDED / APPROVED-but-not-applied: a human resolves it; never re-created.
        raise LookupError(
            f"modification {body['reference']} of {spec.external_id} is {found['status']}"
        )
    if found is None:
        with ctx.command(cast.accountant, MODIFICATION_CREATE) as uow:
            created = modifications.create_modification(
                uow, contract_id=contract_id, body=ModificationCreateIn.model_validate(body)
            )
        modification_id, status = created.id, ModificationStatus.DRAFT.value
    else:
        modification_id, status = UUID(str(found["id"])), str(found["status"])
    if status == ModificationStatus.DRAFT.value:
        with ctx.command(cast.accountant, MODIFICATION_CREATE) as uow:
            classified = modifications.classify(uow, modification_id=modification_id)
            principal = uow.principal
        registry.run_inline(
            JobKind.CONTRACT_COMPUTE,
            {
                "mode": MODIFICATION_PREVIEW_MODE,
                "modification_id": str(modification_id),
                "row_version": int(classified.row_version),
                "contract_id": str(contract_id),
                "expected_stream_version": _head(ctx, contract_id),
            },
            tenant_id=ctx.tenant_id,
            principal=principal,
            clock=ctx.clock,
            runtime=runtime,
        )
        with ctx.command(cast.accountant, MODIFICATION_CREATE) as uow:
            modifications.submit(
                uow,
                modification_id=modification_id,
                body=ModificationSubmitIn(comment=SUBMIT_COMMENT),
            )
    ctx.approve(ApprovalSubjectType.MODIFICATION, modification_id, [cast.reviewer])
    with ctx.read() as session:
        applied = (
            session.execute(
                select(modification.c.status, modification.c.treatment_summary).where(
                    modification.c.id == modification_id
                )
            )
            .mappings()
            .one()
        )
    if str(applied["status"]) != ModificationStatus.APPLIED.value:
        raise LookupError(f"modification {modification_id} ended {applied['status']}")
    return SEPARATE if str(applied["treatment_summary"] or "") == "SEPARATE_CONTRACT" else APPLIED


def _month_states(ctx: BuildContext, m: VolumeManifest) -> list[str]:
    """The period states of the manifest's months, for every entity and book of the tenant."""
    from sqlalchemy import and_, select

    from erev_api.db.tables import period, period_state

    with ctx.read() as session:
        return [
            str(getattr(state, "value", state))
            for state in session.execute(
                select(period_state.c.state)
                .select_from(
                    period_state.join(
                        period,
                        and_(
                            period.c.tenant_id == period_state.c.tenant_id,
                            period.c.id == period_state.c.period_id,
                        ),
                    )
                )
                .where(
                    period.c.start_date >= month_start(1),
                    period.c.start_date <= month_start(m.months),
                )
            ).scalars()
        ]


def _recompute_all(ctx: BuildContext, cast: VolumeCast) -> int:
    from sqlalchemy import select

    from erev_api.db.tables import combination_group
    from erev_api.domain.contracts import computation

    with ctx.read() as session:
        groups = [
            UUID(str(row)) for row in session.execute(select(combination_group.c.id)).scalars()
        ]
    for group_id in groups:
        with ctx.command(cast.accountant, EVENT_RECORD) as uow:
            computation.recompute(uow, group_id)
    return len(groups)

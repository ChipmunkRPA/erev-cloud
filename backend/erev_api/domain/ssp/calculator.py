"""Historical SSP calculator (04 T-REF-32 to T-REF-34, §15.3 API-R-27, §16.14; 05 §5.6 execution
profile ``SSP_CALCULATOR``; SCREENS §11.5; PRD §2.8 WLD-X-24, §2.12 WLD-F-18, BR-SSP-04, J-02.1 to
J-02.5; POLICIES §3.3; 03 REQ-SSP-009; BUILD_SPEC RFD-15, BS3-D-15, BS3-D-18).

- ``create_run`` (``POST /ssp-calculator-runs``): validates the parameters, inserts a QUEUED run and
  defers one ``SSP_CALCULATOR`` job on it (DG-KRN-JOB-02). The pool is an ``IMPORT_SOURCE`` CSV file
  named by ``parameters.pool_file_id`` (L2-1-Q-53).
- ``ssp_calculator`` (the job handler; 05 §5.6 one attempt): the run becomes RUNNING, the source's
  provider returns the observations, and the statistics per product and key, the observations file
  and SUCCEEDED are written in one transaction. A failure ends the run FAILED and re-raises, so the
  job fails with its problem.
- Providers (BS3-D-15): ``source_order_lines`` reads the pool file; ``committed_obligations`` reads
  the computed obligation versions of ACTIVE single-obligation contracts (CTR-2, BS3-D-21).
- ``exclude_observation`` (``POST …/exclusions``): stores the exclusion with the BS3-D-15 reference
  and recomputes the statistics in the same transaction (L2-1-Q-57).
- ``create_draft_version`` (``POST …/create-draft-version``): a DRAFT version of the run's book that
  copies the latest APPROVED version and sets each result's band (L2-1-Q-58).
- ``linked_prices``: the non-excluded unit prices of the run linked to a version, which POL-073
  coverage counts at publication (POLICIES §3.3; PRD J-02.5; L2-1-Q-59).

A run reads within its requester's entities (04 T-REF-32 rev 1.277; supervisor ruling R-28, row
N-29; item SSP-ENTITY-SCOPE-1). What a run shows is contract data — the order, its unit price,
its customer — and the job runs as SYSTEM, so the scope is taken where the caller is known:
``create_run`` stores the requester's ``contract.read`` scope on the run (``requested_scope``),
the job hands it to the provider, and ``committed_obligations`` reads the contracts of those
entities only. The run is then read and commanded by a member whose ``contract.read`` covers
that scope (``reaches_run``) and is absent for anyone else: left out of the list, and 404 for
the read, the results, the observations, an exclusion and the draft version. Measured before
(lane F-RPS-REG's row 4): an SSP Analyst of one entity read the run, the results and the
observations of another entity's order, and her own run read that order.

A run posts nothing and needs no approval (PRD BR-SSP-04). Results are append-only (IM-A): a
recomputation appends a set, and the results of a run are the latest row of each product and key.
Statistics are exact decimals at the ``erev.exact`` scale, rounded half up (L2-1-Q-56).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Context, Decimal
from functools import reduce
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import (
    ColumnElement,
    Select,
    Uuid,
    and_,
    func,
    insert,
    literal,
    select,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    book,
    contract,
    contract_version,
    customer,
    legal_entity,
    obligation,
    obligation_version,
    product,
    ssp_book,
    ssp_book_version,
    ssp_calculator_exclusion,
    ssp_calculator_result,
    ssp_calculator_run,
)
from erev_api.db.transitions import apply
from erev_api.domain.platform import file_access
from erev_api.domain.platform.approval_queries import actor, display_names
from erev_api.domain.reference import fx
from erev_api.domain.reference.products import exact_text, series_product_ids
from erev_api.domain.ssp import books, commands, queries, scope
from erev_api.enums import (
    ConfigStatus,
    ContractStatus,
    FilePurpose,
    JobKind,
    RunStatus,
    SspQuantityUnit,
    SspValueBasis,
)
from erev_api.files.store import open_file, store_file
from erev_api.jobs.registry import JobOutcome, RetryPolicy, problem_slug, task
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.ssp_books import SspBookVersionIn, SspEntriesIn, SspEntryIn
from erev_api.schemas.users import LABEL_LENGTH

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.domain.reference.queries import Page
    from erev_api.files.store import FileStore
    from erev_api.jobs.context import JobContext
    from erev_api.schemas.ssp_calculator import (
        SspCalculatorDraftVersionIn,
        SspCalculatorExclusionIn,
        SspCalculatorRunIn,
    )
    from erev_api.uow import UnitOfWork

TABLE: Final = "ssp_calculator_run"
OBJECT_RUN: Final = "ssp_calculator_run"
OBJECT_RESULT: Final = "ssp_calculator_result"
OBJECT_EXCLUSION: Final = "ssp_calculator_exclusion"
RUN_CREATE: Final = "ssp_calculator_run.create"
RUN_START: Final = "ssp_calculator_run.start"
RUN_SUCCEED: Final = "ssp_calculator_run.succeed"
RUN_FAIL: Final = "ssp_calculator_run.fail"
RUN_RECOMPUTE: Final = "ssp_calculator_run.recompute"
RUN_DRAFT: Final = "ssp_calculator_run.create_draft_version"
RESULT_CREATE: Final = "ssp_calculator_result.create"
EXCLUSION_CREATE: Final = "ssp_calculator_exclusion.create"
RULE_RUN: Final = "T-REF-32"
# The permission a run's provider is limited to and its readers are held to: what a run shows
# is contract data.
SCOPE_PERMISSION: Final = "contract.read"
ENTITY_DIMENSION: Final = "entity"
RULE_RESULT: Final = "T-REF-33"
RULE_EXCLUSION: Final = "T-REF-34"
RULE_POOL: Final = "BR-SSP-04"
RULE_LIFECYCLE: Final = "E-67"

SOURCE_ORDER_LINES: Final = "source_order_lines"
SOURCE_COMMITTED_OBLIGATIONS: Final = "committed_obligations"
SOURCES: Final = (SOURCE_ORDER_LINES, SOURCE_COMMITTED_OBLIGATIONS)
REF_ORDER_LINE: Final = "source_order_line"  # T-REF-34 source_ref_type
# BS3-D-15: the uuid5 name of a pool observation.
POOL_REFERENCE: Final = "https://erev.dev/ns/ssp-pool/{sha256}/{external_id}"
# [J] Filters of ``parameters.dimensions`` and the pool column each reads (L2-1-Q-55).
DIMENSION_COLUMNS: Final[Mapping[str, str]] = {
    "entity": "entity_code",
    "region": "region",
    "channel": "channel",
    "segment": "segment",
    "deal_size_band": "deal_size_band",
    "term_band": "term_band",
}
REQUIRED_POOL_COLUMNS: Final = (
    "order_line_external_id",
    "order_date",
    "product_code",
    "quantity",
    "unit_price",
    "currency",
)
OPTIONAL_POOL_COLUMNS: Final = (
    "entity_code",
    "customer_code",
    "stratification",
    "region",
    "channel",
    "segment",
    "deal_size_band",
    "term_band",
)
MAX_POOL_ERRORS: Final = 100
MIN_REASON_LENGTH: Final = 10  # SCREENS §11.5 exclude modal
HISTOGRAM_BINS: Final = 10
CSV_MEDIA_TYPE: Final = "text/csv"
RESULT_FORMAT: Final = "erev.ssp_calculator_observations.v1"
RESULT_MEDIA_TYPE: Final = "application/json"
RUN_HREF: Final = "/api/v1/ssp-calculator-runs/{run_id}"
CALCULATOR_RETRY: Final = RetryPolicy(max_attempts=1)  # 05 §5.6 SSP_CALCULATOR: 1 attempt
MEDIAN: Final = Decimal("0.5")
PERCENTILES: Final[Mapping[str, Decimal]] = {
    "p10_unit_price": Decimal("0.1"),
    "p25_unit_price": Decimal("0.25"),
    "p75_unit_price": Decimal("0.75"),
    "p90_unit_price": Decimal("0.9"),
}
_SCALE: Final = Decimal("1E-18")  # erev.exact NUMERIC(38,18)
_WIDE: Final = Context(prec=80)
_ONE: Final = Decimal(1)
_DECIMAL_TEXT: Final = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_DATE_TEXT: Final = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CURRENCY_TEXT: Final = re.compile(r"^[A-Z]{3}$")

QUEUED: Final = RunStatus.QUEUED.value
RUNNING: Final = RunStatus.RUNNING.value
SUCCEEDED: Final = RunStatus.SUCCEEDED.value
FAILED: Final = RunStatus.FAILED.value

# [J] Copy the documents leave open (SCREENS §11.5 names the reason minimum only).
NAME_REQUIRED: Final = "Enter a name for the run."
PRODUCTS_UNKNOWN: Final = "Choose existing products."
DATE_ORDER: Final = "Date to must be on or after date from."
BAND_RATIO_RANGE: Final = "Enter a band around the median above 0% and below 100%."
CURRENCY_UNKNOWN: Final = "Choose an active ISO 4217 currency."
BOOK_UNKNOWN: Final = "Choose an existing SSP book."
DIMENSION_UNKNOWN: Final = (
    "Filter by entity, region, channel, segment, deal size band or term band only."
)
DIMENSION_VALUE: Final = "Enter a value for this filter."
POOL_REQUIRED: Final = "Upload the pool of standalone sales as a CSV import file."
POOL_NOT_ALLOWED: Final = "Committed contract lines need no pool file. Remove it."
POOL_CHANGED: Final = "The pool file no longer matches its SHA-256."
POOL_ENCODING: Final = "The pool file must be UTF-8 text."
POOL_HEADER: Final = "The pool file needs the columns {columns}."
POOL_VALUE_REQUIRED: Final = "Enter a value."
POOL_DATE: Final = "Enter the date as YYYY-MM-DD."
POOL_DECIMAL: Final = "Enter a decimal number with digits only, at most 18 decimals."
POOL_QUANTITY: Final = "Enter a quantity above zero."
POOL_CURRENCY: Final = "Enter a three-letter ISO 4217 code."
POOL_DUPLICATE: Final = "Order line {external_id} appears twice in the pool file."
NOT_SUCCEEDED: Final = "Only a succeeded run can change."
REASON_SHORT: Final = "Enter a reason of at least 10 characters."
OBSERVATION_UNKNOWN: Final = "Choose an observation of this run."
ALREADY_EXCLUDED: Final = "This observation is already excluded."
LAST_OBSERVATION: Final = "Keep at least one observation of {product_code}."
DRAFT_EXISTS: Final = "A draft version was already created from this run."
NO_RESULTS: Final = "This run has no results to propose."
LABEL_REQUIRED: Final = "Enter the version label."
DEFAULT_METHODOLOGY: Final = "Historical SSP calculator run: {name}"
# What a study proposes nothing for (04 §16.14; item SSP-STUDY-SERIES-BASIS-1). A study states one
# price per unit of line quantity; a draft takes every result of its run, so the remedy names the
# products to leave out of another run.
NOT_PROPOSED: Final = "No draft version was created. {reasons} Start a run without {codes}."
PER_SERVICE_UNIT_INCREMENT: Final = (
    "{product_code} is priced per increment of a service unit in the approved version, and the "
    "study states a price per unit of line quantity."
)
SHARE_OF_LIST: Final = (
    "{product_code} is priced as a percentage of list price in the approved version, and the "
    "study states a price per unit of line quantity."
)
NO_BASIS_STATED: Final = (
    "{product_code} is a series product, and no approved entry states its value basis."
)


# --- values --------------------------------------------------------------------------------------


def quantize(value: Decimal) -> Decimal:
    """A value at the ``erev.exact`` scale, half up (L2-1-Q-56)."""
    return value.quantize(_SCALE, rounding=ROUND_HALF_UP, context=_WIDE)


def _text(value: Decimal) -> str:
    text = exact_text(value)
    return "0" if text is None else text


@dataclass(frozen=True, slots=True)
class RunParameters:
    """T-REF-32 ``parameters`` as stored (L2-1-Q-53)."""

    source: str
    product_ids: tuple[UUID, ...]
    dimensions: Mapping[str, str]
    date_from: date
    date_to: date
    band_ratio: Decimal
    currency: str
    ssp_book_id: UUID
    pool_file_id: UUID | None

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "product_ids": [str(value) for value in self.product_ids],
            "dimensions": dict(sorted(self.dimensions.items())),
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "band_ratio": _text(self.band_ratio),
            "currency": self.currency,
            "ssp_book_id": str(self.ssp_book_id),
            "pool_file_id": None if self.pool_file_id is None else str(self.pool_file_id),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> RunParameters:
        pool = value.get("pool_file_id")
        dimensions = value.get("dimensions") or {}
        return cls(
            source=str(value["source"]),
            product_ids=tuple(UUID(str(item)) for item in value["product_ids"]),
            dimensions={str(name): str(text) for name, text in dict(dimensions).items()},
            date_from=date.fromisoformat(str(value["date_from"])),
            date_to=date.fromisoformat(str(value["date_to"])),
            band_ratio=Decimal(str(value["band_ratio"])),
            currency=str(value["currency"]),
            ssp_book_id=UUID(str(value["ssp_book_id"])),
            pool_file_id=None if pool is None else UUID(str(pool)),
        )


@dataclass(frozen=True, slots=True)
class RunScope:
    """The entities a run's provider may read: every entity, or the named ones. Stored as
    T-REF-32 ``entity_ids`` — NULL for every entity, the named set otherwise, never empty
    (``ck_ssp_calculator_run__entity_ids``)."""

    is_all_entities: bool
    entity_ids: tuple[UUID, ...] = ()

    @classmethod
    def of(cls, run: Mapping[str, Any]) -> RunScope:
        stored = run["entity_ids"]
        if stored is None:
            return cls(True)
        return cls(False, tuple(UUID(str(value)) for value in stored))

    def column(self) -> list[UUID] | None:
        """The value of ``entity_ids`` for this scope."""
        return None if self.is_all_entities else list(self.entity_ids)


@dataclass(frozen=True, slots=True)
class Observation:
    """One standalone sale of a run: its reference, product, key and unit price."""

    source_ref_type: str
    source_ref_id: UUID
    source_reference: str
    date: date
    product_id: UUID
    product_code: str
    customer_code: str | None
    quantity: Decimal
    unit_price: Decimal
    currency: str
    stratification: str
    dimension_key: Mapping[str, str]
    exclusion_reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "source_ref_type": self.source_ref_type,
            "source_ref_id": str(self.source_ref_id),
            "source_reference": self.source_reference,
            "date": self.date.isoformat(),
            "product_id": str(self.product_id),
            "product_code": self.product_code,
            "customer_code": self.customer_code,
            "quantity": _text(self.quantity),
            "unit_price": _text(self.unit_price),
            "currency": self.currency,
            "stratification": self.stratification,
            "dimension_key": dict(sorted(self.dimension_key.items())),
            "exclusion_reason": self.exclusion_reason,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Observation:
        customer_code = value.get("customer_code")
        return cls(
            source_ref_type=str(value["source_ref_type"]),
            source_ref_id=UUID(str(value["source_ref_id"])),
            source_reference=str(value["source_reference"]),
            date=date.fromisoformat(str(value["date"])),
            product_id=UUID(str(value["product_id"])),
            product_code=str(value["product_code"]),
            customer_code=None if customer_code is None else str(customer_code),
            quantity=Decimal(str(value["quantity"])),
            unit_price=Decimal(str(value["unit_price"])),
            currency=str(value["currency"]),
            stratification=str(value["stratification"]),
            dimension_key={str(k): str(v) for k, v in dict(value["dimension_key"]).items()},
            exclusion_reason=None,
        )


def result_key(
    product_code: str, stratification: str, dimension_key: Mapping[str, str], currency: str
) -> tuple[str, str, str, str]:
    """The T-REF-33 key of a result: product, stratification, dimension key and currency."""
    dimensions = json.dumps(dict(sorted(dimension_key.items())), sort_keys=True)
    return (product_code, stratification, dimensions, currency)


def _observation_key(observation: Observation) -> tuple[str, str, str, str]:
    return result_key(
        observation.product_code,
        observation.stratification,
        observation.dimension_key,
        observation.currency,
    )


def _observation_order(observation: Observation) -> tuple[date, str]:
    return (observation.date, observation.source_reference)


# --- statistics (REQ-SSP-009) --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Statistics:
    """The T-REF-33 statistics of the non-excluded unit prices of one product and key."""

    observation_count: int
    excluded_count: int
    median_unit_price: Decimal
    mean_unit_price: Decimal
    p10_unit_price: Decimal
    p25_unit_price: Decimal
    p75_unit_price: Decimal
    p90_unit_price: Decimal
    band_ratio: Decimal
    compliance_ratio: Decimal
    inside_count: int
    proposed_low: Decimal
    proposed_mid: Decimal
    proposed_high: Decimal
    histogram: tuple[Mapping[str, Any], ...]

    def columns(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "excluded_count": self.excluded_count,
            "median_unit_price": self.median_unit_price,
            "mean_unit_price": self.mean_unit_price,
            "p10_unit_price": self.p10_unit_price,
            "p25_unit_price": self.p25_unit_price,
            "p75_unit_price": self.p75_unit_price,
            "p90_unit_price": self.p90_unit_price,
            "band_ratio": self.band_ratio,
            "compliance_ratio": self.compliance_ratio,
            "inside_count": self.inside_count,
            "proposed_low": self.proposed_low,
            "proposed_mid": self.proposed_mid,
            "proposed_high": self.proposed_high,
            "histogram": [dict(item) for item in self.histogram],
        }


def percentile(values: Sequence[Decimal], ratio: Decimal) -> Decimal:
    """[J] The ``ratio`` percentile of ascending ``values`` by linear interpolation between the
    closest ranks, rank h = (n − 1) × ratio (Hyndman and Fan type 7; L2-1-Q-56)."""
    if not values:
        raise ValueError("a percentile needs at least one value")
    position = _WIDE.multiply(Decimal(len(values) - 1), ratio)
    lower = int(position.to_integral_value(rounding=ROUND_FLOOR))
    if lower >= len(values) - 1:
        return quantize(values[-1])
    fraction = _WIDE.subtract(position, Decimal(lower))
    spread = _WIDE.subtract(values[lower + 1], values[lower])
    return quantize(_WIDE.add(values[lower], _WIDE.multiply(fraction, spread)))


def histogram(values: Sequence[Decimal], bins: int = HISTOGRAM_BINS) -> tuple[dict[str, Any], ...]:
    """[J] ``bins`` equal-width bins from the lowest to the highest of ascending ``values``; a bin
    holds its ``from`` value, and the last bin also its ``to`` value (L2-1-Q-56)."""
    if not values:
        return ()
    low, high = values[0], values[-1]
    if low == high:
        return ({"from": _text(low), "to": _text(high), "count": len(values)},)
    width = _WIDE.divide(_WIDE.subtract(high, low), Decimal(bins))
    counts = [0] * bins
    for value in values:
        index = _WIDE.divide(_WIDE.subtract(value, low), width)
        counts[min(int(index.to_integral_value(rounding=ROUND_FLOOR)), bins - 1)] += 1
    edges = [quantize(_WIDE.add(low, _WIDE.multiply(width, Decimal(i)))) for i in range(bins)]
    return tuple(
        {
            "from": _text(edges[i]),
            "to": _text(high if i == bins - 1 else edges[i + 1]),
            "count": counts[i],
        }
        for i in range(bins)
    )


def statistics(
    prices: Iterable[Decimal], *, excluded_count: int, band_ratio: Decimal
) -> Statistics:
    """Count, median, mean, P10, P25, P75, P90, the band of ± ``band_ratio`` around the median, the
    observations inside it (inclusive) and their share (REQ-SSP-009; PRD WLD-X-24)."""
    values = sorted(prices)
    if not values:
        raise ValueError("statistics need at least one observation")
    count = len(values)
    median = percentile(values, MEDIAN)
    total = reduce(_WIDE.add, values, Decimal(0))
    low = quantize(_WIDE.multiply(median, _WIDE.subtract(_ONE, band_ratio)))
    high = quantize(_WIDE.multiply(median, _WIDE.add(_ONE, band_ratio)))
    inside = sum(1 for value in values if low <= value <= high)
    return Statistics(
        observation_count=count,
        excluded_count=excluded_count,
        median_unit_price=median,
        mean_unit_price=quantize(_WIDE.divide(total, Decimal(count))),
        p10_unit_price=percentile(values, PERCENTILES["p10_unit_price"]),
        p25_unit_price=percentile(values, PERCENTILES["p25_unit_price"]),
        p75_unit_price=percentile(values, PERCENTILES["p75_unit_price"]),
        p90_unit_price=percentile(values, PERCENTILES["p90_unit_price"]),
        band_ratio=quantize(band_ratio),
        compliance_ratio=quantize(_WIDE.divide(Decimal(inside), Decimal(count))),
        inside_count=inside,
        proposed_low=low,
        proposed_mid=median,
        proposed_high=high,
        histogram=histogram(values),
    )


# --- pool file (BR-SSP-04; BS3-D-15) -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PoolRow:
    """One row of a pool file; ``row`` is its line number, the header being line 1."""

    row: int
    order_line_external_id: str
    order_date: date
    product_code: str
    quantity: Decimal
    unit_price: Decimal
    currency: str
    customer_code: str | None
    stratification: str
    dimensions: Mapping[str, str]


def pool_reference(sha256: str, external_id: str) -> UUID:
    """BS3-D-15 ``source_ref_id``: uuid5 of the pool file's SHA-256 and the order line id."""
    name = POOL_REFERENCE.format(sha256=sha256, external_id=external_id)
    return uuid.uuid5(uuid.NAMESPACE_URL, name)


def _pool_error(row: int | None, field: str | None, message: str) -> ProblemError:
    return ProblemError(field=field, row=row, rule_id=RULE_POOL, message=message)


def _cell(record: Mapping[str | None, Any], column: str) -> str | None:
    value = record.get(column)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _pool_decimal(
    text: str | None, *, row: int, column: str, errors: list[ProblemError]
) -> Decimal | None:
    if text is None:
        return None
    value = Decimal(text) if _DECIMAL_TEXT.fullmatch(text) else None
    exponent = None if value is None else value.as_tuple().exponent
    if value is None or not isinstance(exponent, int) or exponent < -18:
        errors.append(_pool_error(row, column, POOL_DECIMAL))
        return None
    if value >= books.EXACT_LIMIT:
        errors.append(_pool_error(row, column, POOL_DECIMAL))
        return None
    return value


def _pool_row(
    row: int, record: Mapping[str | None, Any]
) -> tuple[PoolRow | None, list[ProblemError]]:
    errors: list[ProblemError] = []
    cells = {name: _cell(record, name) for name in (*REQUIRED_POOL_COLUMNS, *OPTIONAL_POOL_COLUMNS)}
    errors += [
        _pool_error(row, name, POOL_VALUE_REQUIRED)
        for name in REQUIRED_POOL_COLUMNS
        if cells[name] is None
    ]
    order_date: date | None = None
    date_text = cells["order_date"]
    if date_text is not None:
        try:
            order_date = date.fromisoformat(date_text) if _DATE_TEXT.fullmatch(date_text) else None
        except ValueError:
            order_date = None
        if order_date is None:
            errors.append(_pool_error(row, "order_date", POOL_DATE))
    quantity = _pool_decimal(cells["quantity"], row=row, column="quantity", errors=errors)
    if quantity is not None and quantity <= 0:
        errors.append(_pool_error(row, "quantity", POOL_QUANTITY))
    unit_price = _pool_decimal(cells["unit_price"], row=row, column="unit_price", errors=errors)
    currency_code = cells["currency"]
    if currency_code is not None and not _CURRENCY_TEXT.fullmatch(currency_code):
        errors.append(_pool_error(row, "currency", POOL_CURRENCY))
    external_id, product_code = cells["order_line_external_id"], cells["product_code"]
    if (
        errors
        or external_id is None
        or product_code is None
        or order_date is None
        or quantity is None
        or unit_price is None
        or currency_code is None
    ):
        return None, errors
    dimensions = {
        name: value
        for name, column in DIMENSION_COLUMNS.items()
        if (value := cells[column]) is not None
    }
    return (
        PoolRow(
            row=row,
            order_line_external_id=external_id,
            order_date=order_date,
            product_code=product_code,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency_code,
            customer_code=cells["customer_code"],
            stratification=cells["stratification"] or "",
            dimensions=dimensions,
        ),
        [],
    )


def parse_pool(data: bytes) -> tuple[PoolRow, ...]:
    """The rows of a pool file: UTF-8 CSV (a byte order mark is allowed) with the columns
    ``REQUIRED_POOL_COLUMNS`` and optionally ``OPTIONAL_POOL_COLUMNS``. Quantities are above zero,
    unit prices at least zero, and an order line appears once. 422 ``validation-failed`` lists up
    to 100 findings with their line numbers (L2-1-Q-55)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise Problem(
            "validation-failed", errors=[_pool_error(None, None, POOL_ENCODING)]
        ) from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [name.strip() for name in reader.fieldnames or ()]
    missing = [name for name in REQUIRED_POOL_COLUMNS if name not in header]
    if missing:
        message = POOL_HEADER.format(columns=", ".join(missing))
        raise Problem("validation-failed", errors=[_pool_error(1, None, message)])
    reader.fieldnames = header
    rows: list[PoolRow] = []
    errors: list[ProblemError] = []
    seen: set[str] = set()
    for record in reader:
        pool_row, found = _pool_row(reader.line_num, record)
        errors += found
        if pool_row is None:
            continue
        if pool_row.order_line_external_id in seen:
            message = POOL_DUPLICATE.format(external_id=pool_row.order_line_external_id)
            errors.append(_pool_error(pool_row.row, "order_line_external_id", message))
            continue
        seen.add(pool_row.order_line_external_id)
        rows.append(pool_row)
    if errors:
        raise Problem("validation-failed", errors=errors[:MAX_POOL_ERRORS])
    return tuple(rows)


# --- providers (BS3-D-15) ------------------------------------------------------------------------

type Provider = Callable[[UnitOfWork, RunParameters, RunScope], Sequence[Observation]]

# The observation provider of each source (``source_order_lines`` RFD-15, ``committed_obligations``
# CTR-2).
PROVIDERS: Final[dict[str, Provider]] = {}


def register_provider(source: str, provider: Provider) -> None:
    """Register the observation provider of ``source``; a source has one provider."""
    if source not in SOURCES:
        raise ValueError(f"unknown calculator source {source}")
    if source in PROVIDERS:
        raise ValueError(f"calculator source {source} has a provider already")
    PROVIDERS[source] = provider


def _product_codes(session: Session, product_ids: Iterable[UUID]) -> dict[str, UUID]:
    statement = select(product.c.code, product.c.id).where(product.c.id.in_(sorted(product_ids)))
    return {str(code): UUID(str(product_id)) for code, product_id in session.execute(statement)}


def matches(pool_row: PoolRow, parameters: RunParameters) -> bool:
    """A pool row is an observation of the run when its date, currency and every dimension filter
    match (L2-1-Q-55); the product is checked by the caller."""
    return (
        parameters.date_from <= pool_row.order_date <= parameters.date_to
        and pool_row.currency == parameters.currency
        and all(
            pool_row.dimensions.get(name) == value for name, value in parameters.dimensions.items()
        )
    )


def pool_observations(
    uow: UnitOfWork, parameters: RunParameters, limit: RunScope
) -> list[Observation]:
    """``source_order_lines``: the rows of the pool file of the run's products that match the
    date range, currency and dimensions, each referenced as BS3-D-15 describes. The file is
    the one its requester named and could read (``_pool_errors``): its rows are her upload,
    not rows of the workspace, so ``limit`` filters none of them — it bounds who reads the
    run."""
    del limit
    if parameters.pool_file_id is None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="parameters.pool_file_id", rule_id=RULE_POOL, message=POOL_REQUIRED
                )
            ],
        )
    row, stream = open_file(
        uow.session, parameters.pool_file_id, files=uow.files, keyring=uow.keyring
    )
    with stream:
        data = stream.read()
    sha256 = str(row["sha256"])
    if hashlib.sha256(data).hexdigest() != sha256:
        raise Problem("validation-failed", errors=[_pool_error(None, None, POOL_CHANGED)])
    codes = _product_codes(uow.session, parameters.product_ids)
    observations: list[Observation] = []
    for pool_row in parse_pool(data):
        product_id = codes.get(pool_row.product_code)
        if product_id is None or not matches(pool_row, parameters):
            continue
        observations.append(
            Observation(
                source_ref_type=REF_ORDER_LINE,
                source_ref_id=pool_reference(sha256, pool_row.order_line_external_id),
                source_reference=pool_row.order_line_external_id,
                date=pool_row.order_date,
                product_id=product_id,
                product_code=pool_row.product_code,
                customer_code=pool_row.customer_code,
                quantity=pool_row.quantity,
                unit_price=pool_row.unit_price,
                currency=pool_row.currency,
                stratification=pool_row.stratification,
                dimension_key=dict(parameters.dimensions),
            )
        )
    return observations


register_provider(SOURCE_ORDER_LINES, pool_observations)

REF_OBLIGATION_VERSION: Final = "obligation_version"  # T-REF-34 source_ref_type
_EXACT_SCALE: Final = Decimal(1).scaleb(-18)  # TY-02 erev.exact


def _committed_statement(parameters: RunParameters, limit: RunScope) -> Select[Any]:
    single = (
        select(obligation.c.contract_id)
        .group_by(obligation.c.contract_id)
        .having(func.count(obligation.c.id) == 1)
    )
    primary = select(book.c.code).where(book.c.is_primary.is_(True)).scalar_subquery()
    joined = (
        obligation_version.join(
            contract,
            and_(
                contract.c.tenant_id == obligation_version.c.tenant_id,
                contract.c.id == obligation_version.c.contract_id,
            ),
        )
        .join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == contract.c.tenant_id,
                legal_entity.c.id == contract.c.contracting_entity_id,
            ),
        )
        .join(
            customer,
            and_(
                customer.c.tenant_id == contract.c.tenant_id,
                customer.c.id == contract.c.customer_id,
            ),
        )
        .join(
            contract_version,
            and_(
                contract_version.c.tenant_id == obligation_version.c.tenant_id,
                contract_version.c.id == obligation_version.c.contract_version_id,
            ),
        )
    )
    return (
        select(
            obligation_version.c.id,
            obligation_version.c.obligation_id,
            contract_version.c.contract_computation_id,
            obligation_version.c.obligation_key,
            obligation_version.c.product_id,
            obligation_version.c.product_code,
            obligation_version.c.quantity,
            obligation_version.c.stated_price,
            obligation_version.c.stratification,
            contract.c.external_id,
            contract.c.inception_date,
            contract.c.region,
            contract.c.channel,
            legal_entity.c.code.label("entity_code"),
            customer.c.code.label("customer_code"),
            customer.c.segment,
        )
        .select_from(joined)
        .where(
            contract.c.status == ContractStatus.ACTIVE.value,
            contract.c.id.in_(single),
            contract.c.inception_date >= parameters.date_from,
            contract.c.inception_date <= parameters.date_to,
            contract.c.transaction_currency == parameters.currency,
            obligation_version.c.book_code == primary,
            obligation_version.c.product_id.in_(sorted(parameters.product_ids)),
            # The run's scope: the contracts of the entities its requester reads.
            true()
            if limit.is_all_entities
            else contract.c.contracting_entity_id.in_(sorted(limit.entity_ids)),
        )
        .order_by(obligation_version.c.obligation_id, obligation_version.c.version_no)
    )


def committed_observations(
    uow: UnitOfWork, parameters: RunParameters, limit: RunScope
) -> list[Observation]:
    """``committed_obligations`` (BS3-D-21): each obligation of an ``ACTIVE`` contract with exactly
    one obligation and an inception date in the run's range is a standalone sale at stated price ÷
    quantity. [J] L3-1-Q-23: the obligation's latest version in the primary book, in the run's
    currency and products; the ``entity``, ``region``, ``channel`` and ``segment`` filters compare
    the contracting entity code, the contract's region and channel and the customer's segment, and
    the band filters match nothing. The reference is the obligation version: the one of the
    computation that last held the obligation (``subjects.obligation_latest_computation``;
    item SSP-CALC-LATEST-VERSION-1). Only contracts of the entities of ``limit`` are read (the
    run's stored scope; item SSP-ENTITY-SCOPE-1)."""
    held: dict[UUID, list[Mapping[str, Any]]] = {}
    for found in uow.session.execute(_committed_statement(parameters, limit)).mappings():
        held.setdefault(UUID(str(found["obligation_id"])), []).append(dict(found))
    # The obligation's version is the one of the computation that last held it. ``version_no``
    # counts within one combination group, so the highest number across the groups a contract
    # has been in can be a version of a group it left (item SSP-CALC-LATEST-VERSION-1; the
    # reader of item MOD-SSP-PIN-CHAIN-1). A latest version that is outside the run's products
    # is not observed: no earlier version stands in for it.
    latest: dict[UUID, Mapping[str, Any]] = {}
    for obligation_id, versions in held.items():
        computation_id = subjects.obligation_latest_computation(uow.session, obligation_id)
        for version in versions:
            if version["contract_computation_id"] == computation_id:
                latest[obligation_id] = version
    observations: list[Observation] = []
    for row in sorted(
        latest.values(), key=lambda item: (item["inception_date"], item["external_id"])
    ):
        answers = {
            "entity": row["entity_code"],
            "region": row["region"],
            "channel": row["channel"],
            "segment": row["segment"],
        }
        if any(answers.get(name) != value for name, value in parameters.dimensions.items()):
            continue
        quantity = Decimal(row["quantity"])
        if quantity == 0:
            continue
        unit_price = Context(prec=38).divide(Decimal(row["stated_price"]), quantity)
        observations.append(
            Observation(
                source_ref_type=REF_OBLIGATION_VERSION,
                source_ref_id=UUID(str(row["id"])),
                source_reference=f"{row['external_id']} {row['obligation_key']}",
                date=row["inception_date"],
                product_id=UUID(str(row["product_id"])),
                product_code=str(row["product_code"]),
                customer_code=row["customer_code"],
                quantity=quantity,
                unit_price=unit_price.quantize(_EXACT_SCALE, rounding=ROUND_HALF_UP),
                currency=parameters.currency,
                stratification=str(row["stratification"] or ""),
                dimension_key=dict(parameters.dimensions),
            )
        )
    return observations


register_provider(SOURCE_COMMITTED_OBLIGATIONS, committed_observations)


# --- results -------------------------------------------------------------------------------------


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def record_results(
    uow: UnitOfWork, run_id: UUID, parameters: RunParameters, observations: Sequence[Observation]
) -> tuple[UUID, int, int]:
    """Append the statistics of each product and key and store the observations file; returns the
    file id, the non-excluded observation count and the number of results."""
    groups: dict[tuple[str, str, str, str], list[Observation]] = {}
    for observation in observations:
        groups.setdefault(_observation_key(observation), []).append(observation)
    tenant_id = uow.principal.tenant_id
    rows: list[dict[str, Any]] = []
    for key in sorted(groups):
        items = groups[key]
        kept = [item.unit_price for item in items if item.exclusion_reason is None]
        if not kept:
            continue
        found = statistics(
            kept, excluded_count=len(items) - len(kept), band_ratio=parameters.band_ratio
        )
        first = items[0]
        rows.append(
            {
                "tenant_id": tenant_id,
                "id": new_id(),
                "ssp_calculator_run_id": run_id,
                "product_id": first.product_id,
                "stratification": first.stratification,
                "dimension_key": dict(sorted(first.dimension_key.items())),
                "currency": first.currency,
                **found.columns(),
            }
        )
    if rows:
        uow.session.execute(insert(ssp_calculator_result), rows)
        audit_writer.record_facts(
            uow,
            action=RESULT_CREATE,
            object_type=OBJECT_RESULT,
            ids=[row["id"] for row in rows],
            detail={"ssp_calculator_run_id": str(run_id)},
        )
    document = {
        "format": RESULT_FORMAT,
        "ssp_calculator_run_id": str(run_id),
        "generated_at": uow.now,
        "observations": [item.to_json() for item in sorted(observations, key=_observation_order)],
    }
    stored = store_file(
        uow,
        purpose=FilePurpose.REPORT_OUTPUT,
        stream=io.BytesIO(canonical_bytes(document)),
        original_filename=None,
        media_type=RESULT_MEDIA_TYPE,
    )
    count = sum(1 for item in observations if item.exclusion_reason is None)
    return UUID(str(stored["id"])), count, len(rows)


def _exclusion_reasons(session: Session, run_id: Any) -> dict[tuple[str, UUID], str]:
    statement = select(
        ssp_calculator_exclusion.c.source_ref_type,
        ssp_calculator_exclusion.c.source_ref_id,
        ssp_calculator_exclusion.c.reason,
    ).where(ssp_calculator_exclusion.c.ssp_calculator_run_id == run_id)
    return {
        (str(ref_type), UUID(str(ref_id))): str(reason)
        for ref_type, ref_id, reason in session.execute(statement)
    }


def observations_of(
    session: Session, run: Mapping[str, Any], *, files: FileStore, keyring: KeyRing
) -> list[Observation]:
    """The observations of a run from its observations file, with the reasons of the T-REF-34
    exclusions; none before the run succeeds."""
    file_id = run["result_file_id"]
    if file_id is None:
        return []
    _, stream = open_file(session, UUID(str(file_id)), files=files, keyring=keyring)
    with stream:
        document = json.loads(stream.read())
    if not isinstance(document, dict) or document.get("format") != RESULT_FORMAT:
        raise LookupError(f"file {file_id} holds no calculator observations")
    reasons = _exclusion_reasons(session, run["id"])
    found: list[Observation] = []
    for item in document["observations"]:
        observation = Observation.from_json(item)
        reason = reasons.get((observation.source_ref_type, observation.source_ref_id))
        found.append(replace(observation, exclusion_reason=reason))
    return found


def linked_prices(
    uow: UnitOfWork, version: Mapping[str, Any]
) -> dict[tuple[str, str], list[Decimal]] | None:
    """The non-excluded unit prices of the calculator run linked to an SSP book version, by product
    code and currency; None when no run is linked (POLICIES §3.3; PRD J-02.5; L2-1-Q-59)."""
    run_id = version.get("ssp_calculator_run_id")
    if run_id is None:
        return None
    run = (
        uow.session.execute(
            select(ssp_calculator_run.c.id, ssp_calculator_run.c.result_file_id).where(
                ssp_calculator_run.c.id == UUID(str(run_id))
            )
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        return None
    prices: dict[tuple[str, str], list[Decimal]] = {}
    for item in observations_of(uow.session, dict(run), files=uow.files, keyring=uow.keyring):
        if item.exclusion_reason is None:
            prices.setdefault((item.product_code, item.currency), []).append(item.unit_price)
    return prices


# --- commands ------------------------------------------------------------------------------------


def requested_scope(uow: UnitOfWork, parameters: RunParameters) -> RunScope:
    """The scope a new run stores: what its provider may read — the requester's
    ``contract.read`` scope at the request. One narrowing, so that a study of one entity is
    read by that entity's members: a ``committed_obligations`` run whose ``entity`` filter
    names an entity inside that scope stores that entity alone. A code outside it changes
    nothing and matches nothing, as a code nobody knows does. A requester who reads no
    contract at all starts no run: 403 ``forbidden``, recorded (DG-KRN-AUTH-05) — there is
    no scope to store, and she could not read the run."""
    held = entity_scope.held_scope(uow.principal, SCOPE_PERMISSION)
    if held != "*" and not held:
        audit_writer.record_denied(
            uow.ctx,
            action=RUN_CREATE,
            object_type=OBJECT_RUN,
            object_id=None,
            permission=SCOPE_PERMISSION,
            keyring=uow.keyring,
        )
        raise Problem("forbidden")
    named = parameters.dimensions.get(ENTITY_DIMENSION)
    if parameters.source == SOURCE_COMMITTED_OBLIGATIONS and named is not None:
        found = uow.session.execute(
            select(legal_entity.c.id).where(legal_entity.c.code == named)
        ).scalar_one_or_none()
        if found is not None and (held == "*" or UUID(str(found)) in held):
            return RunScope(False, (UUID(str(found)),))
    if held == "*":
        return RunScope(True)
    return RunScope(False, tuple(sorted(held)))


def reaches_run(principal: Principal, run: Mapping[str, Any]) -> bool:
    """Whether ``principal`` reaches the run: its ``contract.read`` covers every entity of the
    run's scope, and all entities for a run of all (the kernel's ``entity_scope.covers``).
    SYSTEM — the job — reaches every run."""
    held = entity_scope.held_scope(principal, SCOPE_PERMISSION)
    stored = RunScope.of(run)
    return entity_scope.covers(held, [(stored.is_all_entities, stored.entity_ids)])


def run_in_reach(principal: Principal) -> ColumnElement[bool]:
    """``reaches_run`` in SQL, over ``ssp_calculator_run``: a run of every entity (NULL) is
    reached by a holder for all entities alone."""
    held = entity_scope.held_scope(principal, SCOPE_PERMISSION)
    if held == "*":
        return true()
    return and_(
        ssp_calculator_run.c.entity_ids.is_not(None),
        ssp_calculator_run.c.entity_ids.contained_by(literal(sorted(held), ARRAY(Uuid()))),
    )


def _require_reach(principal: Principal, run: Mapping[str, Any]) -> None:
    """404 ``not-found`` for a run out of the principal's reach, as for an id that names none."""
    if not reaches_run(principal, run):
        raise Problem("not-found")


def _lock_run(session: Session, run_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(
            select(ssp_calculator_run).where(ssp_calculator_run.c.id == run_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _require_succeeded(run: Mapping[str, Any]) -> None:
    if run["status"] != SUCCEEDED:
        error = ProblemError(field="status", rule_id=RULE_LIFECYCLE, message=NOT_SUCCEEDED)
        raise Problem("invalid-transition", NOT_SUCCEEDED, errors=[error])


def _field(name: str, message: str, rule_id: str = RULE_RUN) -> ProblemError:
    return ProblemError(field=name, rule_id=rule_id, message=message)


def _parameter_errors(
    session: Session, ctx: RequestContext, body: SspCalculatorRunIn
) -> list[ProblemError]:
    parameters = body.parameters
    errors: list[ProblemError] = []
    if not body.name.strip():
        errors.append(_field("name", NAME_REQUIRED))
    found = session.execute(
        select(product.c.id).where(product.c.id.in_(sorted(set(parameters.product_ids))))
    ).all()
    if len(found) != len(set(parameters.product_ids)):
        errors.append(_field("parameters.product_ids", PRODUCTS_UNKNOWN))
    for name, value in sorted(parameters.dimensions.items()):
        if name not in DIMENSION_COLUMNS:
            errors.append(_field(f"parameters.dimensions.{name}", DIMENSION_UNKNOWN))
        elif not value.strip():
            errors.append(_field(f"parameters.dimensions.{name}", DIMENSION_VALUE))
    if parameters.date_to < parameters.date_from:
        errors.append(_field("parameters.date_to", DATE_ORDER))
    ratio = Decimal(parameters.band_ratio)
    if not Decimal(0) < ratio < _ONE:
        errors.append(_field("parameters.band_ratio", BAND_RATIO_RANGE))
    if not fx.active_currencies(session, [parameters.currency]):
        errors.append(_field("parameters.currency", CURRENCY_UNKNOWN))
    # The run's book: one the caller may prepare a version of. A book of an entity her
    # ``ssp.create`` does not cover answers as a book that does not exist (``scope``).
    named_book = session.execute(
        select(ssp_book.c.currency, ssp_book.c.entity_id).where(
            ssp_book.c.id == parameters.ssp_book_id
        )
    ).one_or_none()
    if named_book is None or not scope.reaches(ctx.principal, scope.CREATE, named_book.entity_id):
        errors.append(_field("parameters.ssp_book_id", BOOK_UNKNOWN))
    elif named_book.currency is not None and str(named_book.currency) != parameters.currency:
        message = books.BOOK_CURRENCY.format(currency=named_book.currency)
        errors.append(_field("parameters.currency", message))
    errors += _pool_errors(session, ctx, parameters.source, parameters.pool_file_id)
    return errors


def _pool_errors(
    session: Session, ctx: RequestContext, source: str, pool_file_id: UUID | None
) -> list[ProblemError]:
    """The pool a run names: an ``IMPORT_SOURCE`` CSV the caller may read. A pool the caller may
    not read is answered as one that does not exist (04 T-PLT-29 Read access, rev 1.151)."""
    if source != SOURCE_ORDER_LINES:
        if pool_file_id is not None:
            return [_field("parameters.pool_file_id", POOL_NOT_ALLOWED, RULE_POOL)]
        return []
    # The file-read question of GET /files/{id}, asked first (T-PLT-29 Binding): the job reads
    # the pool as SYSTEM, so the caller's right to read it is asked here, where the caller names it.
    pool = None if pool_file_id is None else file_access.bound(session, ctx, pool_file_id)
    if (
        pool is None
        or pool["shredded_at"] is not None
        or pool["purpose"] != FilePurpose.IMPORT_SOURCE.value
        or pool["media_type"] != CSV_MEDIA_TYPE
    ):
        return [_field("parameters.pool_file_id", POOL_REQUIRED, RULE_POOL)]
    return []


def create_run(uow: UnitOfWork, *, body: SspCalculatorRunIn) -> tuple[UUID, UUID]:
    """``POST /ssp-calculator-runs``: a QUEUED run and its ``SSP_CALCULATOR`` job; returns the run
    and job ids. 422 collects the findings on the name and each parameter. The run stores the
    scope its provider may read (``requested_scope``)."""
    session = uow.session
    errors = _parameter_errors(session, uow.ctx, body)
    if errors:
        raise Problem("validation-failed", errors=errors)
    incoming = body.parameters
    parameters = RunParameters(
        source=incoming.source,
        product_ids=tuple(dict.fromkeys(incoming.product_ids)),
        dimensions={name: value.strip() for name, value in incoming.dimensions.items()},
        date_from=incoming.date_from,
        date_to=incoming.date_to,
        band_ratio=Decimal(incoming.band_ratio),
        currency=incoming.currency,
        ssp_book_id=incoming.ssp_book_id,
        pool_file_id=incoming.pool_file_id,
    )
    stored = requested_scope(uow, parameters)
    run_id = new_id()
    job = uow.defer(
        JobKind.SSP_CALCULATOR,
        {"ssp_calculator_run_id": str(run_id)},
        subject_type=OBJECT_RUN,
        subject_id=run_id,
    )
    job_id = UUID(str(job["id"]))
    values = {
        "name": body.name.strip(),
        "parameters": parameters.to_json(),
        "job_id": job_id,
        "entity_ids": stored.column(),
    }
    session.execute(
        insert(ssp_calculator_run).values(
            tenant_id=uow.principal.tenant_id,
            id=run_id,
            status=QUEUED,
            **values,
            **_created(uow),
        )
    )
    uow.audit(
        action=RUN_CREATE,
        object_type=OBJECT_RUN,
        object_id=run_id,
        after={
            **values,
            "job_id": str(job_id),
            "entity_ids": (
                None if stored.is_all_entities else [str(value) for value in stored.entity_ids]
            ),
            "status": QUEUED,
        },
    )
    return run_id, job_id


def _run_href(run_id: UUID) -> str:
    return RUN_HREF.format(run_id=run_id)


def run_job_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The job's failure hook (05 §5.6 rev 1.165; item JOB-FAILED-ITEM-1). The handler ends the
    run itself for an error it catches (``_fail_run``); this is for the job that ends FAILED
    without the handler's own ending — a worker that died while the run was ``RUNNING``, or a
    job that never ran — so that the run ends ``FAILED`` with the job. Before, such a run
    stayed ``RUNNING`` for good. A run that has ended is left alone, and so is a run whose row
    another transaction holds, which is not waited for. The holder is never the job's own
    computation — while its transaction is open, the job is not settled and this hook is not
    reached (05 JOB-06 rev 1.200)."""
    run_id = UUID(str(params["ssp_calculator_run_id"]))
    status = uow.session.execute(
        select(ssp_calculator_run.c.status)
        .where(ssp_calculator_run.c.id == run_id)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if status is None or str(getattr(status, "value", status)) not in (QUEUED, RUNNING):
        return
    before = str(getattr(status, "value", status))
    apply(
        uow.session,
        TABLE,
        run_id,
        to_status=FAILED,
        set_values={"finished_at": uow.now},
        expected_status=before,
    )
    uow.audit(
        action=RUN_FAIL,
        object_type=OBJECT_RUN,
        object_id=run_id,
        before={"status": before},
        after={"status": FAILED, "finished_at": uow.now.isoformat()},
        detail={"problem": problem_slug(problem)},
    )


@task(JobKind.SSP_CALCULATOR, retry=CALCULATOR_RETRY, on_failure=run_job_failed)
def ssp_calculator(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``SSP_CALCULATOR``: compute the run named by ``params.ssp_calculator_run_id``. A run that
    is no longer QUEUED is left alone (duplicate delivery). A failure at the start or during the
    computation ends the run FAILED, then re-raises so the job fails with its problem."""
    run_id = UUID(str(params["ssp_calculator_run_id"]))
    href = _run_href(run_id)
    try:
        with jc.unit_of_work() as uow:
            run = _lock_run(uow.session, run_id)
            if run["status"] != QUEUED:
                counts = {"observations": run["observation_count"] or 0}
                return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": counts})
            apply(
                uow.session,
                TABLE,
                run_id,
                to_status=RUNNING,
                set_values={"started_at": uow.now},
                expected_status=QUEUED,
            )
            uow.audit(
                action=RUN_START,
                object_type=OBJECT_RUN,
                object_id=run_id,
                before={"status": QUEUED},
                after={"status": RUNNING, "started_at": uow.now.isoformat()},
                detail={"job_id": str(jc.job_id)},
            )
            uow.commit()
        with jc.unit_of_work() as uow:
            run = _lock_run(uow.session, run_id)
            parameters = RunParameters.from_json(run["parameters"])
            provider = PROVIDERS.get(parameters.source)
            observations = (
                [] if provider is None else list(provider(uow, parameters, RunScope.of(run)))
            )
            jc.heartbeat()
            file_id, count, results = record_results(uow, run_id, parameters, observations)
            apply(
                uow.session,
                TABLE,
                run_id,
                to_status=SUCCEEDED,
                set_values={
                    "observation_count": count,
                    "result_file_id": file_id,
                    "finished_at": uow.now,
                },
                expected_status=RUNNING,
            )
            uow.audit(
                action=RUN_SUCCEED,
                object_type=OBJECT_RUN,
                object_id=run_id,
                before={"status": RUNNING},
                after={
                    "status": SUCCEEDED,
                    "observation_count": count,
                    "result_file_id": str(file_id),
                    "finished_at": uow.now.isoformat(),
                },
                detail={"results": results, "provider": provider is not None},
            )
            uow.commit()
    except Exception as error:
        _fail_run(jc, run_id, error)
        raise
    return JobOutcome(
        state="SUCCEEDED",
        result={"href": href, "counts": {"observations": count, "results": results}},
    )


def _fail_run(jc: JobContext, run_id: UUID, error: Exception) -> None:
    """End a QUEUED or RUNNING run FAILED in its own transaction; the audit detail names the
    problem, or only the error class of an unexpected error (DG-LOG-03)."""
    with jc.unit_of_work() as uow:
        found = (
            uow.session.execute(
                select(ssp_calculator_run.c.status)
                .where(ssp_calculator_run.c.id == run_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        # A missing run has nothing to end; the original error still fails the job.
        if found is None or found["status"] not in (QUEUED, RUNNING):
            return
        run = dict(found)
        apply(
            uow.session,
            TABLE,
            run_id,
            to_status=FAILED,
            set_values={"finished_at": uow.now},
            expected_status=str(run["status"]),
        )
        detail: dict[str, Any] = (
            {"problem": error.slug, "errors": [item.message for item in error.errors]}
            if isinstance(error, Problem)
            else {"error_class": type(error).__name__}
        )
        uow.audit(
            action=RUN_FAIL,
            object_type=OBJECT_RUN,
            object_id=run_id,
            before={"status": run["status"]},
            after={"status": FAILED, "finished_at": uow.now.isoformat()},
            detail=detail,
        )
        uow.commit()


def exclude_observation(uow: UnitOfWork, run_id: UUID, *, body: SspCalculatorExclusionIn) -> UUID:
    """``POST /ssp-calculator-runs/{id}/exclusions``: 404; 409 ``invalid-transition`` unless the run
    SUCCEEDED; 422 on a reason below 10 characters, an unknown or excluded observation, or the last
    observation of its product and key. The statistics are recomputed at once (L2-1-Q-57)."""
    session = uow.session
    run = _lock_run(session, run_id)
    _require_reach(uow.principal, run)
    _require_succeeded(run)
    reason = body.reason.strip()
    reference = body.source_reference.strip()
    errors: list[ProblemError] = []
    if len(reason) < MIN_REASON_LENGTH:
        errors.append(_field("reason", REASON_SHORT, RULE_EXCLUSION))
    observations = observations_of(session, run, files=uow.files, keyring=uow.keyring)
    chosen = next((item for item in observations if item.source_reference == reference), None)
    if chosen is None:
        errors.append(_field("source_reference", OBSERVATION_UNKNOWN, RULE_EXCLUSION))
    elif chosen.exclusion_reason is not None:
        errors.append(_field("source_reference", ALREADY_EXCLUDED, RULE_EXCLUSION))
    elif not any(
        item is not chosen
        and item.exclusion_reason is None
        and _observation_key(item) == _observation_key(chosen)
        for item in observations
    ):
        message = LAST_OBSERVATION.format(product_code=chosen.product_code)
        errors.append(_field("source_reference", message, RULE_EXCLUSION))
    if errors or chosen is None:
        raise Problem("validation-failed", errors=errors)
    exclusion_id = new_id()
    session.execute(
        insert(ssp_calculator_exclusion).values(
            tenant_id=uow.principal.tenant_id,
            id=exclusion_id,
            ssp_calculator_run_id=run_id,
            source_ref_type=chosen.source_ref_type,
            source_ref_id=chosen.source_ref_id,
            reason=reason,
            **_created(uow),
        )
    )
    audit_writer.record_facts(
        uow,
        action=EXCLUSION_CREATE,
        object_type=OBJECT_EXCLUSION,
        ids=[exclusion_id],
        detail={"ssp_calculator_run_id": str(run_id), "source_reference": reference},
    )
    updated = [
        replace(item, exclusion_reason=reason) if item is chosen else item for item in observations
    ]
    parameters = RunParameters.from_json(run["parameters"])
    file_id, count, results = record_results(uow, run_id, parameters, updated)
    apply(
        session,
        TABLE,
        run_id,
        to_status=None,
        set_values={"observation_count": count, "result_file_id": file_id},
    )
    uow.audit(
        action=RUN_RECOMPUTE,
        object_type=OBJECT_RUN,
        object_id=run_id,
        before={
            "observation_count": run["observation_count"],
            "result_file_id": None if run["result_file_id"] is None else str(run["result_file_id"]),
        },
        after={"observation_count": count, "result_file_id": str(file_id)},
        detail={"ssp_calculator_exclusion_id": str(exclusion_id), "results": results},
    )
    return exclusion_id


def _proposed_entry(result: Mapping[str, Any], copied: Mapping[str, Any] | None) -> SspEntryIn:
    """The entry a result proposes: its band around the median, method ``observable``; the
    distinctness, revenue account and observable point of the copied entry stay (L2-1-Q-58), and
    so do its pricing basis and quantity unit (04 T-REF-30 ``value_basis``, ``quantity_unit``;
    ruling R-50 (c)): the study states a price per line quantity, which is what the band of the
    copied entry states under each basis ``not_proposed`` lets through."""
    dimension_key = dict(result["dimension_key"])
    return SspEntryIn.model_validate(
        {
            "product_code": result["product_code"],
            "stratification": result["stratification"],
            **{name: dimension_key.get(name) for name in books.DIMENSION_KEYS},
            "currency": result["currency"],
            "method": "observable",
            "value_basis": None if copied is None else copied["value_basis"],
            "quantity_unit": None if copied is None else copied["quantity_unit"],
            "observable_point": None if copied is None else copied["observable_point"],
            "revenue_account_code": None if copied is None else copied["revenue_account_code"],
            "distinctness": "distinct" if copied is None else copied["distinctness"],
            "ranges": [
                {
                    "low_value": result["proposed_low"],
                    "mid_value": result["proposed_mid"],
                    "high_value": result["proposed_high"],
                }
            ],
        }
    )


def _listed(codes: Sequence[str]) -> str:
    """``A``, ``A and B`` or ``A, B and C``."""
    return codes[0] if len(codes) == 1 else f"{', '.join(codes[:-1])} and {codes[-1]}"


def not_proposed(
    session: Session,
    results: Sequence[Mapping[str, Any]],
    approved: Mapping[books.EntryKey, Mapping[str, Any]],
) -> list[tuple[str, str]]:
    """(product code, sentence) of every result the study proposes nothing for, in result order,
    a product once per reason (04 §16.14; ruling R-50 (c) and the supervisor's rulings of
    2026-10-01 on item SSP-STUDY-SERIES-BASIS-1). ``approved`` holds the entries of the version the
    draft copies, by key. A study states one price per unit of line quantity, which is what a band
    states under ``AMOUNT``, under ``PER_BOOKED_TERM`` and under ``PER_INCREMENT`` when the line
    quantity counts increments. It is neither a price per increment of a service unit nor a
    share of list price, and nothing is converted. A series product without an approved entry of
    the result's key has no stated basis to keep (D-97 (3a))."""
    series = series_product_ids(session, [UUID(str(item["product_id"])) for item in results])
    found: list[tuple[str, str]] = []
    for item in results:
        copied = approved.get(_result_entry_key(item))
        if copied is None:
            reason = NO_BASIS_STATED if UUID(str(item["product_id"])) in series else None
        elif copied["value_basis"] == SspValueBasis.PERCENT_OF_LIST.value:
            reason = SHARE_OF_LIST
        elif (
            copied["value_basis"] == SspValueBasis.PER_INCREMENT.value
            and copied["quantity_unit"] == SspQuantityUnit.SERVICE_UNITS.value
        ):
            reason = PER_SERVICE_UNIT_INCREMENT
        else:
            reason = None
        if reason is not None:
            code = str(item["product_code"])
            refused = (code, reason.format(product_code=code))
            if refused not in found:
                found.append(refused)
    return found


def _result_entry_key(result: Mapping[str, Any]) -> books.EntryKey:
    dimension_key = dict(result["dimension_key"])
    return books.EntryKey(
        product_code=str(result["product_code"]),
        stratification=str(result["stratification"]),
        region=dimension_key.get("region"),
        channel=dimension_key.get("channel"),
        segment=dimension_key.get("segment"),
        deal_size_band=dimension_key.get("deal_size_band"),
        term_band=dimension_key.get("term_band"),
        currency=str(result["currency"]),
    )


def create_draft_version(
    uow: UnitOfWork, run_id: UUID, *, body: SspCalculatorDraftVersionIn
) -> UUID:
    """``POST /ssp-calculator-runs/{id}/create-draft-version``: 404; 409 ``invalid-transition``
    unless the run SUCCEEDED without a draft version; 422 without a label or results, and 422
    without a field, naming each product, for a result the study proposes nothing for
    (``not_proposed``). The DRAFT version of the run's book copies the latest APPROVED version,
    names the run, and each result sets its entry's band (PRD J-02.3; L2-1-Q-58)."""
    session = uow.session
    run = _lock_run(session, run_id)
    _require_reach(uow.principal, run)
    _require_succeeded(run)
    if run["draft_ssp_book_version_id"] is not None:
        error = _field("draft_ssp_book_version_id", DRAFT_EXISTS)
        raise Problem("invalid-transition", DRAFT_EXISTS, errors=[error])
    results = latest_results(session, run_id)
    label = body.version_label.strip()
    errors: list[ProblemError] = []
    if not label:
        errors.append(_field("version_label", LABEL_REQUIRED, books.RULE_VERSION))
    if not results:
        errors.append(ProblemError(rule_id=RULE_RESULT, message=NO_RESULTS))
    if errors:
        # A refusal that names no member of the body states its sentence in ``detail``, which
        # is what a form shows for a problem without field errors (dev-guide DG-KRN-ERR-01).
        raise Problem("validation-failed", None if results else NO_RESULTS, errors=errors)
    parameters = RunParameters.from_json(run["parameters"])
    book_id = parameters.ssp_book_id
    # The draft is a version of the run's book: the book must be the actor's to prepare.
    scope.require_book(session, uow.principal, scope.CREATE, book_id)
    source_id = session.execute(
        select(ssp_book_version.c.id)
        .where(
            ssp_book_version.c.ssp_book_id == book_id,
            ssp_book_version.c.status == ConfigStatus.APPROVED.value,
        )
        .order_by(ssp_book_version.c.version_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    approved = (
        {}
        if source_id is None
        else {
            books.key_of(entry): entry
            for entry in queries.entries_of(session, UUID(str(source_id)))
        }
    )
    refused = not_proposed(session, results, approved)
    if refused:
        # One problem without a field: the body names no result, and a draft takes them all.
        codes = list(dict.fromkeys(code for code, _ in refused))
        raise Problem(
            "validation-failed",
            NOT_PROPOSED.format(
                reasons=" ".join(sentence for _, sentence in refused), codes=_listed(codes)
            ),
            errors=[ProblemError(rule_id=RULE_RESULT, message=sentence) for _, sentence in refused],
        )
    methodology = (body.methodology_label or "").strip() or DEFAULT_METHODOLOGY.format(
        name=run["name"]
    )[:LABEL_LENGTH]
    version_id = commands.create_ssp_book_version(
        uow,
        book_id,
        body=SspBookVersionIn(
            copy_from_version_id=None if source_id is None else UUID(str(source_id)),
            legacy_version_label=label,
            effective_from_date=body.effective_from_date,
            effective_to_date=body.effective_to_date,
            methodology_label=methodology,
        ),
    )
    principal = uow.principal
    session.execute(
        update(ssp_book_version)
        .where(ssp_book_version.c.id == version_id)
        .values(
            ssp_calculator_run_id=run_id,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=commands.VERSION_UPDATE,
        object_type=books.OBJECT_VERSION,
        object_id=version_id,
        before={"ssp_calculator_run_id": None},
        after={"ssp_calculator_run_id": str(run_id)},
    )
    copied = {books.key_of(entry): entry for entry in queries.entries_of(session, version_id)}
    entries = [_proposed_entry(item, copied.get(_result_entry_key(item))) for item in results]
    commands.upsert_ssp_entries(uow, version_id, body=SspEntriesIn(entries=entries))
    apply(
        session,
        TABLE,
        run_id,
        to_status=None,
        set_values={"draft_ssp_book_version_id": version_id},
    )
    uow.audit(
        action=RUN_DRAFT,
        object_type=OBJECT_RUN,
        object_id=run_id,
        before={"draft_ssp_book_version_id": None},
        after={"draft_ssp_book_version_id": str(version_id)},
        detail={
            "ssp_book_id": str(book_id),
            "copy_from_version_id": None if source_id is None else str(source_id),
            "results": len(results),
        },
    )
    return version_id


# --- read models ---------------------------------------------------------------------------------

RUN_COLUMNS: Final = (
    ssp_calculator_run.c.id,
    ssp_calculator_run.c.name,
    ssp_calculator_run.c.parameters,
    ssp_calculator_run.c.status,
    ssp_calculator_run.c.observation_count,
    ssp_calculator_run.c.result_file_id,
    ssp_calculator_run.c.draft_ssp_book_version_id,
    ssp_calculator_run.c.job_id,
    ssp_calculator_run.c.started_at,
    ssp_calculator_run.c.finished_at,
    ssp_calculator_run.c.created_at,
    ssp_calculator_run.c.created_by,
    ssp_calculator_run.c.created_by_kind,
)
STATISTIC_COLUMNS: Final = (
    "median_unit_price",
    "mean_unit_price",
    "p10_unit_price",
    "p25_unit_price",
    "p75_unit_price",
    "p90_unit_price",
    "band_ratio",
    "compliance_ratio",
    "proposed_low",
    "proposed_mid",
    "proposed_high",
)
RESULT_COLUMNS: Final = (
    ssp_calculator_result.c.id,
    ssp_calculator_result.c.ssp_calculator_run_id,
    ssp_calculator_result.c.product_id,
    product.c.code.label("product_code"),
    ssp_calculator_result.c.stratification,
    ssp_calculator_result.c.dimension_key,
    ssp_calculator_result.c.currency,
    ssp_calculator_result.c.observation_count,
    ssp_calculator_result.c.excluded_count,
    *(ssp_calculator_result.c[name] for name in STATISTIC_COLUMNS),
    ssp_calculator_result.c.inside_count,
    ssp_calculator_result.c.histogram,
)
EXCLUSION_COLUMNS: Final = (
    ssp_calculator_exclusion.c.id,
    ssp_calculator_exclusion.c.ssp_calculator_run_id,
    ssp_calculator_exclusion.c.source_ref_type,
    ssp_calculator_exclusion.c.source_ref_id,
    ssp_calculator_exclusion.c.reason,
    ssp_calculator_exclusion.c.created_at,
    ssp_calculator_exclusion.c.created_by,
    ssp_calculator_exclusion.c.created_by_kind,
)


def run_select() -> Select[Any]:
    """T-REF-32 rows."""
    return select(*RUN_COLUMNS)


def _with_actor(session: Session, rows: Sequence[Mapping[Any, Any]]) -> list[dict[str, Any]]:
    names = display_names(session, [row["created_by"] for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {str(key): value for key, value in row.items()}
        user_id, kind = item.pop("created_by"), item.pop("created_by_kind")
        item["created_by"] = actor(user_id, str(kind), names)
        items.append(item)
    return items


def list_runs[T: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the calculator runs the caller reaches (``run_in_reach``)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, run_select().where(run_in_reach(ctx.principal)))
        return result, _with_actor(session, result.items)


def run_row(session: Session, run_id: UUID) -> dict[str, Any] | None:
    """The API-S-SspCalculatorRun visible to ``session``, or None."""
    row = session.execute(run_select().where(ssp_calculator_run.c.id == run_id)).mappings().first()
    return None if row is None else _with_actor(session, [row])[0]


def get_run(ctx: RequestContext, run_id: UUID) -> dict[str, Any]:
    """``GET /ssp-calculator-runs/{id}``; 404 ``not-found`` for an unknown run and for a run
    out of the caller's reach."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _require_run(session, ctx.principal, run_id)
        row = run_row(session, run_id)
    if row is None:
        raise Problem("not-found")
    return row


def result_select(run_id: UUID) -> Select[Any]:
    """The latest T-REF-33 row of each product and key of a run, with the product code. T-REF-33
    has no SC-C, so [J] the latest row is the one with the highest UUIDv7 id (L2-1-Q-57)."""
    table = ssp_calculator_result
    latest = (
        select(table.c.id)
        .where(table.c.ssp_calculator_run_id == run_id)
        .distinct(
            table.c.product_id, table.c.stratification, table.c.dimension_key, table.c.currency
        )
        .order_by(
            table.c.product_id,
            table.c.stratification,
            table.c.dimension_key,
            table.c.currency,
            table.c.id.desc(),
        )
    )
    joined = table.join(
        product, and_(product.c.tenant_id == table.c.tenant_id, product.c.id == table.c.product_id)
    )
    return select(*RESULT_COLUMNS).select_from(joined).where(table.c.id.in_(latest))


def results_out(rows: Sequence[Mapping[Any, Any]]) -> list[dict[str, Any]]:
    """API-S-SspCalculatorResult items with API-C-06 decimal text."""
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {str(key): value for key, value in row.items()}
        for name in STATISTIC_COLUMNS:
            item[name] = _text(Decimal(item[name]))
        items.append(item)
    return items


def latest_results(session: Session, run_id: UUID) -> list[dict[str, Any]]:
    """Every current result of a run in product code and key order."""
    statement = result_select(run_id).order_by(
        product.c.code, ssp_calculator_result.c.stratification, ssp_calculator_result.c.currency
    )
    return results_out(session.execute(statement).mappings().all())


def _require_run(session: Session, principal: Principal, run_id: UUID) -> dict[str, Any]:
    """The run's id, result file and scope, or 404 ``not-found``: for an id that names no
    run, and for a run out of the principal's reach."""
    found = (
        session.execute(
            select(
                ssp_calculator_run.c.id,
                ssp_calculator_run.c.result_file_id,
                ssp_calculator_run.c.entity_ids,
            ).where(ssp_calculator_run.c.id == run_id)
        )
        .mappings()
        .one_or_none()
    )
    run = None if found is None else dict(found)
    if run is None or not reaches_run(principal, run):
        raise Problem("not-found")
    return run


def list_results[T: Page](
    ctx: RequestContext, run_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the current results of a run; 404 ``not-found`` for an unknown run."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _require_run(session, ctx.principal, run_id)
        result = page(session, result_select(run_id))
        return result, results_out(result.items)


def _customer_refs(session: Session, codes: Iterable[str | None]) -> dict[str, dict[str, Any]]:
    wanted = sorted({code for code in codes if code is not None})
    if not wanted:
        return {}
    statement = select(customer.c.id, customer.c.code, customer.c.name).where(
        customer.c.code.in_(wanted)
    )
    return {
        str(code): {"id": customer_id, "code": str(code), "name": str(name)}
        for customer_id, code, name in session.execute(statement)
    }


def observation_items(
    ctx: RequestContext, run_id: UUID, *, files: FileStore, keyring: KeyRing
) -> list[dict[str, Any]]:
    """The observations of a run in date and reference order (04 §16.14): ``customer`` is the
    customer whose code the pool row names, else null; ``in_band`` compares the unit price with the
    proposed band of its product and key; 404 ``not-found`` for an unknown run."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        run = _require_run(session, ctx.principal, run_id)
        observations = sorted(
            observations_of(session, run, files=files, keyring=keyring), key=_observation_order
        )
        bands = {
            result_key(
                str(item["product_code"]),
                str(item["stratification"]),
                dict(item["dimension_key"]),
                str(item["currency"]),
            ): (Decimal(item["proposed_low"]), Decimal(item["proposed_high"]))
            for item in latest_results(session, run_id)
        }
        customers = _customer_refs(session, (item.customer_code for item in observations))
    items: list[dict[str, Any]] = []
    for item in observations:
        band = bands.get(_observation_key(item))
        items.append(
            {
                "date": item.date,
                "source_reference": item.source_reference,
                "product_code": item.product_code,
                "customer": None
                if item.customer_code is None
                else customers.get(item.customer_code),
                "quantity": _text(item.quantity),
                "unit_price": _text(item.unit_price),
                "in_band": band is not None and band[0] <= item.unit_price <= band[1],
                "exclusion_reason": item.exclusion_reason,
            }
        )
    return items


def exclusion_row(session: Session, exclusion_id: UUID, *, source_reference: str) -> dict[str, Any]:
    """API-S-SspCalculatorExclusion of a stored exclusion; ``source_reference`` is the order line id
    the command excluded, because T-REF-34 stores only its uuid (BS3-D-15)."""
    row = (
        session.execute(
            select(*EXCLUSION_COLUMNS).where(ssp_calculator_exclusion.c.id == exclusion_id)
        )
        .mappings()
        .one()
    )
    item = _with_actor(session, [row])[0]
    item["source_reference"] = source_reference
    return item

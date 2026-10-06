"""Platform-layer property support (BUILD_SPEC PRP-4 to PRP-7; dev-guide §9.7, DG-PROP-01).

The in-memory platform part of the properties: a generated world of ``support.prop_worlds`` is
driven as the platform drives it — the engine computed over the world (``erev_engine.compute``),
then the close-run passes the platform runs at a checkpoint (``FX_REMEASUREMENT``,
``CLOSE_RELEASE``, ``NETTING_RECLASS``; ``support.answer_keys.runners.CLOSE_PASSES``,
``intent_totals.close_pass``), each posting over the intents posted so far (RCP-08(b); S14-R-05,
S14-R-07). The journal batches of every (entity, period, mode) are summarised through the landed
platform runner's grain (``platform_runner.summarise_intents``, POL-006: amounts of different
currencies never net) and its balance flag (``journal_totals``); the functional-currency twin
summarises ``amount_functional`` the same way. Balances, positions, RPO and schedules are read from
the computed books.

What this module does NOT do: run the database platform (``DbPlatform`` — the domain command
handlers, report runs, ``lock_period`` / ``reopen_period``, the ``Idempotency-Key`` command
layer). Those parts of P5, P6, P7, P9, P11 and the stateful machine are DB-bound and are reported
NOT RUN until the lane databases exist (the platform runner's own rule, XR-12).

``platform_settings()`` caps examples at 25 under ``ci`` and 100 under ``thorough`` (DG-PROP-01);
``dev`` keeps 10. Standard library, Hypothesis, the engine's public API and the test support only.
"""

from __future__ import annotations

import dataclasses
import decimal
import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine import compute
from erev_engine.bundle import (
    BookOutput,
    EstimateVersionInput,
    EventInput,
    FxRateInput,
    InputBundle,
    OutputBundle,
    PostedAmountInput,
    PostingIntent,
)
from erev_engine.money import DECIMAL_CONTEXT, to_fraction
from hypothesis import settings
from support import bundles, intent_totals, prop_worlds
from support.answer_keys.platform_runner import JournalLine, journal_totals, summarise_intents
from support.answer_keys.runners import CLOSE_PASSES

PLATFORM_EXAMPLES: Final[Mapping[str, int]] = {"dev": 10, "ci": 25, "thorough": 100}
PRIMARY: Final = "ASC606"
LEGACY: Final = "LEGACY"
GROSS: Final = "GROSS"
DELTA: Final = "DELTA"
LIABILITY_ROLES: Final = frozenset({"CONTRACT_LIABILITY"})
ASSET_ROLES: Final = frozenset({"CONTRACT_ASSET", "UNBILLED_RECEIVABLE"})
INCLUDED: Final = frozenset({"UNSATISFIED", "PARTIALLY_SATISFIED"})
BALANCE_COLUMNS: Final[Mapping[str, str]] = {
    "CONTRACT_LIABILITY": "contract_liability",
    "CONTRACT_ASSET": "contract_asset",
    "UNBILLED_RECEIVABLE": "unbilled_receivable",
}


def platform_settings(**overrides: object) -> settings:
    """DG-PROP-01: the loaded profile with the platform example cap (25 ci / 100 thorough)."""
    name = os.environ.get("HYPOTHESIS_PROFILE", "dev")
    parent = settings.get_profile(name)
    return settings(
        parent,
        max_examples=PLATFORM_EXAMPLES.get(name, PLATFORM_EXAMPLES["dev"]),
        deadline=None,
        **overrides,  # type: ignore[arg-type]
    )


# --- the close run -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CloseRun:
    """One platform-style checkpoint: the command computation and its close-run passes."""

    bundle: InputBundle
    command: OutputBundle
    passes: tuple[OutputBundle, ...]

    @property
    def outputs(self) -> tuple[OutputBundle, ...]:
        return (self.command, *self.passes)

    def books(self, *codes: str) -> list[BookOutput]:
        wanted = set(codes)
        return [
            book for output in self.outputs for book in output.books if book.book_code in wanted
        ]

    def primary(self) -> BookOutput:
        """The primary book of the command computation (targets, versions, balances, schedules)."""
        return next(book for book in self.command.books if book.book_code == PRIMARY)


def close_run(value: InputBundle, pass_names: Sequence[str] = CLOSE_PASSES) -> CloseRun:
    """``compute`` over ``value``, then each close-run pass over the intents posted so far — the
    checkpoint of ``platform_runner.InMemoryPlatform`` (``runners._checkpoint_run``)."""
    first = compute(value)
    done: list[OutputBundle] = []
    with decimal.localcontext(DECIMAL_CONTEXT):
        for name in pass_names:
            done.append(intent_totals.close_pass(value, [first, *done], name))
    return CloseRun(value, first, tuple(done))


def intents(run: CloseRun, *codes: str) -> list[tuple[str, tuple[str, ...], PostingIntent]]:
    """(group key, member contract keys, intent) over the command computation and every pass."""
    group = run.bundle.group
    return [
        (group.group_key, tuple(group.member_contract_keys), intent)
        for book in run.books(*codes)
        for intent in book.posting_intents
    ]


def periods_posted(run: CloseRun, *codes: str) -> list[tuple[str, str]]:
    """Every (entity, posting period) some intent of ``codes`` posts to, sorted."""
    return sorted({(i.entity, i.posting_period_key) for _, _, i in intents(run, *codes)})


# --- journal batches at the platform grain -------------------------------------------------------


def batch(run: CloseRun, entity: str, period_key: str, mode: str) -> tuple[JournalLine, ...]:
    """The journal run of (entity, period, mode) as the platform summarises it: ``GROSS`` = the
    primary book's lines, ``DELTA`` = primary plus ``LEGACY`` (JET-02, JET-15; S14-R-23)."""
    codes = (PRIMARY, LEGACY) if mode == DELTA else (PRIMARY,)
    return summarise_intents(
        intents(run, *codes), entity=entity, period_key=period_key, per_contract=False
    )


def functional_batch(
    run: CloseRun, entity: str, period_key: str, mode: str
) -> tuple[JournalLine, ...]:
    """The same batch netted over the functional amounts (per account and functional currency),
    the grain the entity ledger books (DB-16: balanced in functional amounts too)."""
    codes = (PRIMARY, LEGACY) if mode == DELTA else (PRIMARY,)
    totals: dict[tuple[str, str], Fraction] = {}
    for _, _, intent in intents(run, *codes):
        if intent.entity != entity or intent.posting_period_key != period_key:
            continue
        for line in intent.lines:
            sign = 1 if line.side == "D" else -1
            amount = Fraction(line.amount_functional, 10 ** _minor_unit(line.functional_currency))
            key = (line.account_code, line.functional_currency)
            totals[key] = totals.get(key, Fraction(0)) + sign * amount
    return tuple(
        JournalLine(account, net, currency, None)
        for (account, currency), net in sorted(totals.items())
        if net != 0
    )


def unbalanced(lines: Sequence[JournalLine]) -> list[str]:
    """The currencies whose debits and credits differ, per ``journal_totals`` (empty = balanced)."""
    totals = journal_totals(lines)
    return sorted(
        key.split(" ", 1)[1]
        for key, value in totals.items()
        if key.startswith("balanced ") and value != "true"
    )


def modes(run: CloseRun) -> tuple[str, ...]:
    return (GROSS, DELTA) if any(b.book_code == LEGACY for b in run.bundle.books) else (GROSS,)


# --- balances, movements and positions -----------------------------------------------------------


def balance_rows(book: BookOutput) -> dict[tuple[str, str], Mapping[str, object]]:
    """(balance subject ``<contract>@<entity>``, period key) -> the balance columns."""
    return {(row.subject_key, row.period_key): row.columns for row in book.balances}


def role_movement(
    run: CloseRun, *, contract: str, entity: str, period_key: str, role: str, functional: bool
) -> int:
    """The signed posted movement (debit positive) of ``role`` for ``contract`` in the period, over
    the command computation and every pass of the primary book — S15-INV-01's "lines"."""
    total = 0
    for _, _, intent in intents(run, PRIMARY):
        if intent.entity != entity or intent.posting_period_key != period_key:
            continue
        for line in intent.lines:
            if line.account_role != role or line.dimensions.get("contract_key") != contract:
                continue
            amount = line.amount_functional if functional else line.amount_txn
            total += amount if line.side == "D" else -amount
    # the amounts sealed before this run (RCP-05 ``posted``) are lines of the period too
    for sealed in run.bundle.posted:
        if (
            sealed.book_code != PRIMARY
            or sealed.entity_code != entity
            or sealed.period_key != period_key
            or sealed.account_role != role
            or sealed.subject_key.split("/", 1)[0] != contract
        ):
            continue
        total += sealed.amount_functional if functional else sealed.amount_txn
    return total


def movement_by_kind(
    run: CloseRun, *, contract: str, entity: str, period_key: str, role: str
) -> dict[str, int]:
    """The role's signed movement (debit positive, transaction amounts) split by entry kind (E-29)
    — the labelled lines of the rollforward report before FIFO layering (S15-R-03)."""
    found: dict[str, int] = {}
    for _, _, intent in intents(run, PRIMARY):
        if intent.entity != entity or intent.posting_period_key != period_key:
            continue
        for line in intent.lines:
            if line.account_role != role or line.dimensions.get("contract_key") != contract:
                continue
            amount = line.amount_txn if line.side == "D" else -line.amount_txn
            found[intent.entry_kind] = found.get(intent.entry_kind, 0) + amount
    return {kind: amount for kind, amount in sorted(found.items()) if amount}


def billings_by_period(value: InputBundle, *, contract: str, entity: str) -> dict[str, int]:
    """Σ billed minor units per period of the contract's ``BILLING_RECORDED`` events — the billing
    lines the platform's invoice pipeline books (Dr receivable / Cr CONTRACT_LIABILITY, JET-02),
    which the engine's intents do not carry (the ERP side); S15-R-03 "increases by kind BILLING"."""
    calendar = next(item for item in value.entities if item.code == entity)
    currency = next(c.transaction_currency for c in value.contracts if c.external_id == contract)
    scale = 10 ** _minor_unit(currency)
    found: dict[str, int] = {}
    for event in value.events:
        if event.contract_key != contract or event.event_type != "BILLING_RECORDED":
            continue
        amount = to_fraction(str(event.payload["amount"])) * scale
        assert amount.denominator == 1, (event.event_key, amount)
        period = next(
            p.period_key
            for p in calendar.periods
            if p.start_date <= event.effective_date <= p.end_date
        )
        found[period] = found.get(period, 0) + int(amount)
    return found


def balance(columns: Mapping[str, object], role: str, functional: bool) -> int:
    suffix = "functional" if functional else "txn"
    value = columns[f"{BALANCE_COLUMNS[role]}_{suffix}"]
    assert isinstance(value, int), (role, value)
    return value


def period_keys(value: InputBundle, entity: str) -> list[str]:
    calendar = next(item for item in value.entities if item.code == entity)
    return [period.period_key for period in sorted(calendar.periods, key=lambda p: p.start_date)]


def version_period(book: BookOutput, value: InputBundle, entity: str) -> str | None:
    """The period of the latest obligation version date (d_v) of ``entity``, or None."""
    dates: list[date] = []
    for version in book.obligation_versions:
        if version.columns.get("performing_entity_code") != entity:
            continue
        effective = version.columns.get("effective_date")
        if isinstance(effective, date):
            dates.append(effective)
    if not dates:
        return None
    latest = max(dates)
    calendar = next(item for item in value.entities if item.code == entity)
    for period in calendar.periods:
        if period.start_date <= latest <= period.end_date:
            return period.period_key
    return None


# --- RPO and waterfall ---------------------------------------------------------------------------


def _int(value: object, name: str) -> int:
    assert isinstance(value, int) and not isinstance(value, bool), (name, value)
    return value


@dataclass(frozen=True, slots=True)
class RpoRow:
    subject_key: str
    included: bool
    allocated: int
    revenue_cum: int
    scheduled: int
    awaiting: int

    @property
    def rpo(self) -> int:
        """S15-R-08: allocated constrained transaction price − cumulative revenue when included."""
        return self.allocated - self.revenue_cum if self.included else 0


def rpo_rows(book: BookOutput) -> list[RpoRow]:
    rows = []
    for version in book.obligation_versions:
        c = version.columns
        rows.append(
            RpoRow(
                version.subject_key,
                c["satisfaction_status"] in INCLUDED,
                _int(c["allocated_amount"], "allocated_amount"),
                _int(c["revenue_cum"], "revenue_cum"),
                _int(c["scheduled_amount"], "scheduled_amount"),
                _int(c["awaiting_trigger_amount"], "awaiting_trigger_amount"),
            )
        )
    return rows


def schedule_total(book: BookOutput, subject_key: str) -> int:
    """Σ amounts of the obligation's REVENUE schedule lines (the waterfall's schedule total)."""
    return sum(
        _int(line.amount, "schedule amount")
        for line in book.schedules
        if line.subject_key == subject_key
        and str(line.schedule_kind) in ("REVENUE", "ScheduleKind.REVENUE")
    )


def _is_revenue_schedule(line: object) -> bool:
    kind = getattr(line, "schedule_kind", None)
    return str(getattr(kind, "value", kind)) == "REVENUE"


def scheduled_by_period(book: BookOutput) -> dict[str, int]:
    """Σ REVENUE schedule amounts per period (the waterfall's scheduled column by period)."""
    found: dict[str, int] = {}
    for line in book.schedules:
        if _is_revenue_schedule(line):
            found[line.period_key] = found.get(line.period_key, 0) + _int(line.amount, "amount")
    return {key: amount for key, amount in sorted(found.items()) if amount}


def recognised_by_period(run: CloseRun, entity: str) -> dict[str, int]:
    """Σ ``REVENUE`` credits per posting period over the primary book's intents (S15-R-01
    recognised = Σ REVENUE subledger lines by posting period)."""
    found: dict[str, int] = {}
    for _, _, intent in intents(run, PRIMARY):
        if intent.entity != entity:
            continue
        for line in intent.lines:
            if line.account_role != "REVENUE":
                continue
            amount = -line.amount_txn if line.side == "D" else line.amount_txn
            found[intent.posting_period_key] = found.get(intent.posting_period_key, 0) + amount
    return {key: amount for key, amount in sorted(found.items()) if amount}


# --- the stateful machine's bundle ------------------------------------------------------------


def sealed_through(
    outputs: Iterable[OutputBundle], period_keys: Sequence[str], through: str
) -> tuple[PostedAmountInput, ...]:
    """The intents of ``outputs`` posted to periods up to and including ``through``, sealed as
    ``posted`` (RCP-05) — what the platform's journal runs have booked when ``through`` is locked;
    intents the engine emits for later periods are not journal runs yet and are recomputed."""
    limit = period_keys.index(through)
    return tuple(
        item
        for item in intent_totals.posted(*outputs)
        if item.period_key in period_keys and period_keys.index(item.period_key) <= limit
    )


def merge_sealed(*groups: Iterable[PostedAmountInput]) -> tuple[PostedAmountInput, ...]:
    """Sealed amounts of several locks summed per posting key (the amounts are increments)."""
    found: dict[tuple[str, ...], PostedAmountInput] = {}
    for group in groups:
        for item in group:
            members = (
                item.book_code,
                item.entity_code,
                item.subject_key,
                item.entry_kind,
                item.account_role,
                item.clearing_purpose or "",
                item.counterparty_entity_code or "",
                item.period_key,
                item.origin_period_key or "",
                item.posting_class,
                item.reason_code or "",
            )
            previous = found.get(members)
            if previous is None:
                found[members] = item
            else:
                found[members] = dataclasses.replace(
                    previous,
                    amount_txn=previous.amount_txn + item.amount_txn,
                    amount_functional=previous.amount_functional + item.amount_functional,
                    rate_refs=tuple(sorted({*previous.rate_refs, *item.rate_refs})),
                )
    return tuple(found[key] for key in sorted(found))


def machine_bundle(
    spec: prop_worlds.WorldSpec,
    *,
    voids: Sequence[tuple[int, date]] = (),
    period_states: Mapping[str, str] | None = None,
    posted: Iterable[PostedAmountInput] = (),
    books: Sequence[str] = ("ASC606", "LEGACY"),
    months: int = prop_worlds.MONTHS,
    functional_currency: str | None = None,
    fx_rates: Sequence[FxRateInput] = (),
    trigger: str = "COMMAND",
    policies: Mapping[str, str] | None = None,
    estimate_versions: Sequence[EstimateVersionInput] = (),
    vc_events: Sequence[tuple[str, str, date]] = (),
) -> InputBundle:
    """``prop_worlds.bundle`` of ``spec`` (its measures in arrival order — a measure dated before
    the current clock is a late event) plus an ``EVENT_VOIDED`` per (measure index, void date)
    naming the measure's event (S01-R-12; the CV-22 key follows the contract's stream: the booking
    is EV-000001, the activation EV-000002, then version 1 of a variable-consideration element when
    the contract carries one, and the contract's n-th measure EV-(n + ``prop_worlds.stream_base``)),
    plus an ``ESTIMATE_CHANGED`` per later version in ``vc_events`` = (contract, version key,
    effective date), arriving after the measures (a version effective in a locked period is a late
    version). ``functional_currency``, ``fx_rates``, ``trigger``, ``policies`` and
    ``estimate_versions`` pass through to ``prop_worlds.bundle`` (PRP-7 ``publish_fx_rates`` /
    ``change_vc``)."""
    base = prop_worlds.bundle(
        spec,
        books=books,
        period_states=period_states,
        posted=posted,
        months=months,
        functional_currency=functional_currency,
        fx_rates=fx_rates,
        trigger=trigger,
        policies=policies,
        estimate_versions=estimate_versions,
    )
    if not voids and not vc_events:
        return base
    events: list[EventInput] = list(base.events)
    heads = {
        contract: max(e.stream_version for e in events if e.contract_key == contract)
        for contract, _ in spec.contracts
    }
    seq = max(e.record_seq for e in events)
    ordinal: dict[str, int] = {}
    targets: list[str] = []
    for measure in spec.measures:
        ordinal[measure.contract] = ordinal.get(measure.contract, 0) + 1
        base_no = prop_worlds.stream_base(spec, measure.contract)
        targets.append(f"{measure.contract}/EV-{ordinal[measure.contract] + base_no:06d}")
    for contract, version_key, on in vc_events:
        heads[contract] += 1
        seq += 1
        events.append(
            bundles.event(
                contract,
                heads[contract],
                "ESTIMATE_CHANGED",
                on,
                {"estimate_version_id": version_key},
                record_seq=seq,
            )
        )
    for index, on in voids:
        measure = spec.measures[index]
        heads[measure.contract] += 1
        seq += 1
        void = bundles.event(
            measure.contract,
            heads[measure.contract],
            "EVENT_VOIDED",
            on,
            {"reason_code": "DUPLICATE", "comment": f"void of {targets[index]}"},
            record_seq=seq,
            obligation_keys=[measure.line],
        )
        events.append(dataclasses.replace(void, supersedes_event_key=targets[index]))
    ordered = tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key)))
    return dataclasses.replace(base, events=ordered)


def layer_movements(book: BookOutput) -> list[Mapping[str, object]]:
    """The T-CON-18 FX layer movement rows of ``book`` in the engine's processing order (stage
    12; ``BookOutput.fx_layer_movements``), as column mappings."""
    return [row.columns for row in book.fx_layer_movements]


# --- helpers -------------------------------------------------------------------------------------


def _minor_unit(currency: str) -> int:
    return {"JPY": 0, "BHD": 3, "CLF": 4}.get(currency, 2)


def iter_contracts(value: InputBundle) -> Iterator[str]:
    for header in value.contracts:
        yield header.external_id


def dataclass_fields(item: object) -> Iterable[str]:
    return (field.name for field in dataclasses.fields(item))  # type: ignore[arg-type]

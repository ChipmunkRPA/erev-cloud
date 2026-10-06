"""Posting-intent totals for engine tests (BUILD_SPEC END-10; ENGINE_SPEC_B S13-R-09, S14-R-23).

``totals`` sums the posting intents of ``OutputBundle`` values by contract, account and effective
window, in the legacy summarisation grain (POL-006 ``LEGACY_CONTRACT_POB``; legacy 06 §3.3):
balance-sheet lines per contract and account, revenue lines per obligation and account. Amounts are
signed minor units, debit positive, and zero totals are dropped. The ``GROSS`` view reads the
primary book; the ``DELTA`` view is primary-book lines plus ``LEGACY``-book lines per grouping key,
the LEGACY book holding the reversal of what the ERP booked (JET-15; S13-R-09; S14-R-23; D-89
L7-6-Q-8). A window selects the posting periods whose dates meet
``[start, end]``, because the engine posts by period where the legacy JE selects versions by event
date (legacy 06 §3.1).

The helpers stand in for the platform around ``compute``:

- ``activated`` appends ``CONTRACT_ACTIVATED`` at inception for every member without one, as the
  promotion of a legacy import does (T-MIG-01; L2-5-Q-38);
- ``posted`` seals the intents of earlier outputs as ``PostedAmountInput`` (RCP-05);
- ``close_pass`` runs the framework books of a ``CLOSE_RELEASE`` computation for one close-run pass,
  with stage 14 bound to the pass (RCP-08(b); S14-R-05), because ``InputBundle`` names no pass and
  ``compute`` posts only ``EVENT`` amounts (L3-2-Q-21);
- ``computations`` is ``compute`` followed by the ``NETTING_RECLASS`` pass, and ``golden`` caches
  it for an activated golden stream under ``LEGACY_PARITY`` with the books ``ASC606`` and
  ``LEGACY``.

No database, clock or network (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import Final

from erev_engine import ENGINE_VERSION, assemble_output, compute
from erev_engine.bundle import EventInput, InputBundle, OutputBundle, PostedAmountInput
from erev_engine.canonical import sha256_hex
from erev_engine.stages import STAGES, StageSpec, s01_canonicalize, s13_books
from erev_engine.trace import TraceBuilder
from support import golden_streams

__all__ = [
    "BOOKS",
    "DELTA",
    "GROSS",
    "Computed",
    "Key",
    "activated",
    "balance",
    "by_account",
    "close_pass",
    "computations",
    "golden",
    "posted",
    "totals",
]

GROSS: Final = "GROSS"
DELTA: Final = "DELTA"
LEGACY: Final = "LEGACY"
BOOKS: Final = ("ASC606", LEGACY)
NETTING_RECLASS: Final = "NETTING_RECLASS"
# Roles summarised per obligation under LEGACY_CONTRACT_POB (legacy 06 §3.3 property 2).
PROFIT_AND_LOSS_ROLES: Final = frozenset({"REVENUE", "PRE_STANDARD_REVENUE"})

Key = tuple[str, str | None, str]  # (contract key, obligation key or None, account code)


@dataclasses.dataclass(frozen=True, slots=True)
class Computed:
    """One computation: the bundle it read and the output it produced."""

    bundle: InputBundle
    output: OutputBundle


def activated(value: InputBundle, *, origin: str = "IMPORT") -> InputBundle:
    """``value`` with ``CONTRACT_ACTIVATED`` at inception for every contract booked without one."""
    events = list(value.events)
    for header in value.contracts:
        own = [event for event in events if event.contract_key == header.external_id]
        if not own or any(event.event_type == "CONTRACT_ACTIVATED" for event in own):
            continue
        booked = next(event for event in own if event.event_type == "CONTRACT_BOOKED")
        head = max(event.stream_version for event in own) + 1
        payload: dict[str, object] = {"checklist": {}}
        events.append(
            EventInput(
                event_key=f"{booked.event_key.rsplit('/', 1)[0]}/EV-{head:06d}",
                contract_key=header.external_id,
                stream_version=head,
                event_type="CONTRACT_ACTIVATED",
                schema_version=1,
                effective_date=booked.effective_date,
                recorded_at=max(event.recorded_at for event in events) + timedelta(seconds=1),
                record_seq=max(event.record_seq for event in events) + 1,
                origin=origin,
                is_manual=False,
                obligation_keys=(),
                payload=payload,
                payload_sha256=sha256_hex(payload),
                idempotency_key=None,
                supersedes_event_key=None,
                modification_key=None,
                estimate_version_key=None,
                manual_adjustment_key=None,
            )
        )
    ordered = sorted(
        events, key=lambda item: (item.effective_date, item.record_seq, item.event_key)
    )
    return dataclasses.replace(value, events=tuple(ordered))


def posted(
    *outputs: OutputBundle, sealed: Iterable[PostedAmountInput] = ()
) -> tuple[PostedAmountInput, ...]:
    """The posted amounts after sealing every intent of ``outputs`` (RCP-05; §0.4 order) on top of
    the amounts already ``sealed`` — each posting identity (book, entity, subject, entry kind,
    role, clearing purpose, counterparty, posting period, origin period, posting class, reason)
    exactly once, its amounts summed and the rate references of its lines united
    (``BookOutput.line_rates``; S14-R-28). ``sealed`` is the bundle's own ``posted`` history: a
    close pass must not lose it (S14-R-07 reverses the reclass ACTUALLY POSTED for t − 1, including
    from a sealed, locked period; T1-PRP7-CLOSE-HISTORY-1, Codex production-20260922-0031)."""
    found: dict[tuple[str, ...], PostedAmountInput] = {}
    for item in sealed:
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
        found[members] = (
            item
            if previous is None
            else dataclasses.replace(
                previous,
                amount_txn=previous.amount_txn + item.amount_txn,
                amount_functional=previous.amount_functional + item.amount_functional,
                rate_refs=tuple(sorted({*previous.rate_refs, *item.rate_refs})),
            )
        )
    for output in outputs:
        for book in output.books:
            line_rates = dict(book.line_rates)
            for intent in book.posting_intents:
                for line in intent.lines:
                    sign = 1 if line.side == "D" else -1
                    members = (
                        intent.book_code,
                        intent.entity,
                        intent.subject_key,
                        intent.entry_kind,
                        line.account_role,
                        line.clearing_purpose or "",
                        line.counterparty_entity or "",
                        intent.posting_period_key,
                        intent.origin_period_key or "",
                        intent.posting_class,
                        intent.reason_code or "",
                    )
                    previous = found.get(members)
                    amount_txn = sign * line.amount_txn
                    amount_functional = sign * line.amount_functional
                    rate_refs = set(line_rates.get(line.line_key, ()))
                    if previous is not None:
                        amount_txn += previous.amount_txn
                        amount_functional += previous.amount_functional
                        rate_refs.update(previous.rate_refs)
                    found[members] = PostedAmountInput(
                        book_code=intent.book_code,
                        entity_code=intent.entity,
                        subject_key=intent.subject_key,
                        entry_kind=intent.entry_kind,
                        account_role=line.account_role,
                        clearing_purpose=line.clearing_purpose,
                        counterparty_entity_code=line.counterparty_entity,
                        period_key=intent.posting_period_key,
                        origin_period_key=intent.origin_period_key,
                        posting_class=intent.posting_class,
                        txn_currency=line.txn_currency,
                        functional_currency=line.functional_currency,
                        amount_txn=amount_txn,
                        amount_functional=amount_functional,
                        reason_code=intent.reason_code,
                        rate_refs=tuple(sorted(rate_refs)),
                    )
    return tuple(found[members] for members in sorted(found))


def _with_pass(spec: StageSpec, pass_name: str) -> StageSpec:
    entry = spec.entry

    def run(ctx: object, state: object, tb: object, **bound: object) -> object:
        return entry(ctx, state, tb, **bound, pass_name=pass_name)

    return dataclasses.replace(spec, entry=run)


def close_pass(
    value: InputBundle, prior: Sequence[OutputBundle], pass_name: str = NETTING_RECLASS
) -> OutputBundle:
    """The framework books of a ``CLOSE_RELEASE`` computation for ``pass_name`` over ``value``,
    with the intents of ``prior`` posted ON TOP OF ``value.posted`` (RCP-08(b); S14-R-05, S14-R-07):
    the sealed history the bundle carries stays in force and the pass adds only the new increments,
    each posting identity once (T1-PRP7-CLOSE-HISTORY-1, Codex production-20260922-0031)."""
    framework = tuple(book for book in value.books if book.book_code != LEGACY)
    run_value = dataclasses.replace(
        value,
        trigger="CLOSE_RELEASE",
        books=framework,
        posted=posted(*prior, sealed=value.posted),
    )
    cb = s01_canonicalize.run(run_value, TraceBuilder(engine_version=ENGINE_VERSION))
    specs = tuple(_with_pass(spec, pass_name) if spec.stage == "14" else spec for spec in STAGES)
    errors: list[str] = []

    def check(book: str | None, state: object) -> None:
        errors.extend(
            f"{book}:{finding.code}:{finding.subject_key}"
            for finding in getattr(state, "findings", ())
            if finding.severity == "ERROR"
        )

    results = s13_books.run_books(cb, specs, check=check)
    if errors:
        raise AssertionError(f"the close pass collected blocking findings {sorted(set(errors))}")
    return assemble_output(run_value, cb, results)


def computations(value: InputBundle) -> tuple[Computed, Computed]:
    """``compute`` over ``value``, then the ``NETTING_RECLASS`` pass over its intents."""
    first = compute(value)
    return Computed(value, first), Computed(value, close_pass(value, [first]))


@functools.cache
def golden(contract: str, through_step: str) -> tuple[Computed, Computed]:
    """``computations`` of the activated golden stream of ``contract`` through ``through_step``."""
    stream = golden_streams.stream(contract, through_step)
    return computations(activated(stream.input_bundle(preset="LEGACY_PARITY", books=BOOKS)))


def _periods(value: InputBundle) -> Mapping[tuple[str, str], tuple[date, date]]:
    return {
        (entity.code, period.period_key): (period.start_date, period.end_date)
        for entity in value.entities
        for period in entity.periods
    }


def _primary(value: InputBundle) -> str:
    return next(book.book_code for book in value.books if book.is_primary)


def totals(
    computed: Iterable[Computed],
    *,
    view: str = GROSS,
    start: date | None = None,
    end: date | None = None,
) -> dict[Key, int]:
    """Signed totals by (contract, obligation for revenue roles, account) over the window."""
    if view not in (GROSS, DELTA):
        raise ValueError(f"view must be {GROSS} or {DELTA}, not {view!r}")
    found: dict[Key, int] = {}
    for item in computed:
        periods = _periods(item.bundle)
        primary = _primary(item.bundle)
        signs = {primary: 1, **({LEGACY: 1} if view == DELTA else {})}
        for book in item.output.books:
            sign = signs.get(book.book_code)
            if sign is None:
                continue
            for intent in book.posting_intents:
                first, last = periods[(intent.entity, intent.posting_period_key)]
                if (start is not None and last < start) or (end is not None and first > end):
                    continue
                for line in intent.lines:
                    contract = line.dimensions.get("contract_key", "")
                    obligation = (
                        line.dimensions.get("obligation_key")
                        if line.account_role in PROFIT_AND_LOSS_ROLES
                        else None
                    )
                    key = (contract, obligation, line.account_code)
                    amount = line.amount_txn if line.side == "D" else -line.amount_txn
                    found[key] = found.get(key, 0) + sign * amount
    return {key: amount for key, amount in sorted(found.items(), key=_order) if amount != 0}


def _order(item: tuple[Key, int]) -> tuple[str, str, str]:
    (contract, obligation, account), _ = item
    return (contract, obligation or "", account)


def by_account(found: Mapping[Key, int]) -> dict[str, int]:
    """Totals by account code across contracts and obligations, zeros dropped."""
    out: dict[str, int] = {}
    for (_, _, account), amount in found.items():
        out[account] = out.get(account, 0) + amount
    return {account: amount for account, amount in sorted(out.items()) if amount != 0}


def balance(found: Mapping[Key, int]) -> tuple[int, int]:
    """(Σ debits, Σ credits) of summarised lines, both positive (legacy 06 §5.3 footers)."""
    debits = sum(amount for amount in found.values() if amount > 0)
    credits = -sum(amount for amount in found.values() if amount < 0)
    return debits, credits

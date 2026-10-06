"""A simple reference implementation for the stateful property machine (BUILD_SPEC PRP-7;
dev-guide §9.7 "Stateful"; research 06 §18.4): allocation, units and time recognition, billing
position and period locks, written from ENGINE_SPEC and the ALG rules — never from ``erev_engine``.

Scope (the machine's world family): one combination group of one or more contracts sharing an
inception; lines are point-in-time goods (``PIT``: units delivered) or ``DAILY`` ratable services
over an inclusive term; one transaction currency, and a functional currency that may differ (the
FX clauses below are pure functions over published rates); deliveries, billings, voids of either,
rate publications and period states. Rules re-stated here:

- ALG-01 §2.1.1 ``round_half_up``: sign(x) × ⌊|x| × 10^μ + ½⌋.
- ALG-01 §2.1.2 largest remainder (CV-34, CV-36): the posted total T (minor units) apportioned
  over weights w; floors first, then one unit each to the largest fractional remainders — ties by
  larger remainder, then larger weight, then ascending key. The exact quota is
  x = (T ÷ 10^μ) × w ÷ Σw.
- Relative SSP (S05-R-10): weights are the selected SSP × quantity of every line of the group; the
  posted total is the group's Σ line prices.
- ALG-01 §2.1.3 (CV-35, D-11a): cumulative posted revenue C = round_half_up(x × f) bounded to
  [0, A]; C = A when f = 1.
- Progress (CV-61, ALG-11): ``PIT`` f = units delivered ÷ quantity (capped at 1); ``DAILY``
  f = inclusive days from the start through d ÷ inclusive days of the term, 0 before the start,
  1 on and after the end.
- Version date d_v (04 T-CON-11 ``effective_date``): the latest effective date of the events the
  version includes; a voided event and its void leave the stream (S01-R-12).
- Billing position (D-12): position = cumulative billed − cumulative revenue per obligation;
  ``net_position`` of the group = Σ.
- Variable consideration (S04-R-02, S04-R-05, S04-R-07; S08-R-01, S08-R-03, S08-R-06, S08-R-07): a
  contract may carry one ``VARIABLE_CONSIDERATION`` element whose APPROVED versions are world
  facts — scenarios, the most conservative amount and the preparer's constrained amount K (the
  constraint judgement is the world's, never computed here); U = Σ amount × probability
  (``EXPECTED_VALUE``); the transaction price is Σ fixed prices + Σ K of the versions in force
  (the latest version effective on or before the date); a new version changes the price by
  ΔTP = K_new − K_old, routed over the element's contract's obligations by their weights as exact
  quota increments (x′ = x + δ), and the posted allocations are one largest-remainder apportionment
  of the new price over the exact quotas of the whole group (S08-R-07); every change opens a new
  ``INCEPTION`` segment, so cumulative revenue at a date uses the allocation in force at that date
  and the catch-up falls in the change's period (S08-R-06).
- Period locks (E-04): ``open`` / ``closing`` / ``reopened`` are postable; ``closed`` and
  ``permanently_locked`` are not (S14-R-05, S14-R-06: a closed period's amount posts in the
  earliest postable period on or after its date, tagged ``LATE_EVENT`` with its origin).
- FX (ENGINE_SPEC_B §12; PRP-7 ``publish_fx_rates``): S12-R-01 a rate converts one unit of the
  transaction currency into the functional currency (base = transaction, quote = functional);
  spot is the latest rate on or before the date, average and closing are the rates of the period
  (closing may be dated the period end). S12-R-02 every functional amount is
  round_half_up(transaction exact × rate) at the functional minor unit. S12-R-05 the relief of a
  contract-liability layer is the cumulatively rounded share of its historical functional amount
  (``cumulative_posted`` over consumed ÷ original); a fully consumed layer ends at 0. §12.2.2
  ``carrying_portion``: the settled share of an asset layer's carrying is ``cumulative_posted``
  over take ÷ open. S12-R-07 ``PRO_RATA`` apportions a debit over the open liability layers by
  open transaction balance with the largest remainder, keys = layer keys. S12-R-09 asset
  positions are remeasured to the closing rate at every period end. ``layer_ledger`` re-states
  ALG-08 §2.9.1 / §12.2.2 in transaction terms: flows in ENG-06 order (time-driven debits first
  on a day); a credit settles the open asset layers in creation order, then creates a liability
  layer; a debit relieves the open liability layers ``FIFO`` in creation order or ``PRO_RATA``,
  then creates an asset layer; layer keys are ``<role>:<source>`` with ``#n`` for a repeat
  (T-CON-18).

Standard library only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction

POSTABLE = frozenset({"open", "closing", "reopened"})


def round_half_up(x: Fraction, minor_unit: int) -> int:
    scaled = abs(x) * 10**minor_unit
    magnitude = (2 * scaled.numerator + scaled.denominator) // (2 * scaled.denominator)
    return -magnitude if x < 0 else magnitude


def largest_remainder(total: int, weights: Mapping[str, Fraction]) -> dict[str, int]:
    """ALG-01 §2.1.2 over ``weights`` (key -> weight ≥ 0, Σ > 0); a negative total apportions its
    magnitude and flips the signs (S05-R-10 symmetric negative T; a price decrease's shares)."""
    if total < 0:
        return {key: -share for key, share in largest_remainder(-total, weights).items()}
    sigma = sum(weights.values(), Fraction(0))
    if sigma <= 0:
        raise ValueError("weights must sum to a positive amount")
    exact = {key: Fraction(total) * weight / sigma for key, weight in weights.items()}
    floors = {key: value.numerator // value.denominator for key, value in exact.items()}
    left = total - sum(floors.values())
    order = sorted(
        weights,
        key=lambda key: (-(exact[key] - floors[key]), -weights[key], key),
    )
    for key in order[:left]:
        floors[key] += 1
    return floors


def days_inclusive(start: date, end: date) -> int:
    return (end - start).days + 1


def time_fraction_daily(start: date, end: date, d: date) -> Fraction:
    if d < start:
        return Fraction(0)
    if d >= end:
        return Fraction(1)
    return Fraction(days_inclusive(start, d), days_inclusive(start, end))


def units_fraction(delivered: int, quantity: int) -> Fraction:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return min(Fraction(delivered, quantity), Fraction(1))


def cumulative_posted(x_exact: Fraction, a_posted: int, f: Fraction, minor_unit: int) -> int:
    if not 0 <= f <= 1:
        raise ValueError("progress must lie between 0 and 1")
    if f == 1:
        return a_posted
    return min(max(round_half_up(x_exact * f, minor_unit), 0), a_posted)


@dataclass(frozen=True, slots=True)
class Line:
    contract: str
    key: str  # obligation key within the contract
    kind: str  # "PIT" | "DAILY"
    price: int  # minor units
    ssp: int  # SSP point per unit, minor units
    quantity: int
    start: date
    end: date  # == start for a point-in-time line

    @property
    def subject(self) -> str:
        return f"{self.contract}/{self.key}"

    @property
    def weight(self) -> Fraction:
        return Fraction(self.ssp * self.quantity)


@dataclass(frozen=True, slots=True)
class Event:
    """A delivery (units) or a billing (minor units) of a line, effective on ``day``."""

    contract: str
    line: str
    kind: str  # "DELIVERY" | "BILLING"
    day: date
    amount: int
    voided: bool = False


@dataclass(frozen=True, slots=True)
class VcVersion:
    """An APPROVED version of a contract's variable-consideration element (T-CON-12 / T-CON-13):
    ``scenarios`` = (amount in currency units, probability) pairs, the most conservative amount and
    the constrained amount K in minor units — the world's facts (S04-R-05, S04-R-07)."""

    contract: str
    version_no: int
    effective_date: date
    scenarios: tuple[tuple[Fraction, Fraction], ...]
    most_conservative: int
    constrained: int


def expected_value(scenarios: Iterable[tuple[Fraction, Fraction]]) -> Fraction:
    """S04-R-05 ``EXPECTED_VALUE``: Σ amount × probability; the probabilities sum to 1."""
    rows = list(scenarios)
    if sum((p for _, p in rows), Fraction(0)) != 1:
        raise ValueError("probabilities must sum to 1 (S04-R-05)")
    return sum((a * p for a, p in rows), Fraction(0))


def most_likely(scenarios: Iterable[tuple[Fraction, Fraction]], sign: int = 1) -> Fraction:
    """S04-R-05 ``MOST_LIKELY_AMOUNT``: the amount of the most probable scenario; ties take the
    amount giving the lower transaction price (``sign`` −1 for a decrease element)."""
    rows = list(scenarios)
    greatest = max(p for _, p in rows)
    return min((a for a, p in rows if p == greatest), key=lambda a: sign * a)


@dataclass(slots=True)
class Oracle:
    minor_unit: int
    inception: date
    lines: list[Line] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    period_states: dict[str, str] = field(default_factory=dict)  # period key -> E-04 state
    vc: list[VcVersion] = field(default_factory=list)  # APPROVED versions, arrival order

    # -- the world --

    def add_contract(self, contract: str, lines: Iterable[Line]) -> None:
        self.lines.extend(lines)

    def record(self, event: Event) -> int:
        self.events.append(event)
        return len(self.events) - 1

    def void(self, index: int) -> None:
        item = self.events[index]
        if item.voided:
            raise ValueError("an event is voided once (S01-R-12)")
        self.events[index] = Event(
            item.contract, item.line, item.kind, item.day, item.amount, voided=True
        )

    def live(self) -> list[Event]:
        return [event for event in self.events if not event.voided]

    def contracts(self) -> list[str]:
        seen: list[str] = []
        for line in self.lines:
            if line.contract not in seen:
                seen.append(line.contract)
        return seen

    # -- variable consideration (S04-R-05, S04-R-07; S08-R-01) --

    def add_vc(self, version: VcVersion) -> None:
        self.vc.append(version)

    def vc_in_force(self, contract: str, at: date) -> VcVersion | None:
        """S08-R-01: the latest version (by version number) effective on or before ``at``."""
        found = [v for v in self.vc if v.contract == contract and v.effective_date <= at]
        return max(found, key=lambda v: v.version_no) if found else None

    def vc_constrained(self, at: date) -> int:
        """Σ K of the versions in force at ``at`` (S04-R-02: fixed + constrained VC)."""
        return sum(
            v.constrained
            for v in (self.vc_in_force(c, at) for c in self.contracts())
            if v is not None
        )

    def vc_excluded(self, at: date) -> int:
        """round_half_up(Σ (U − K)) over the versions in force — the ``vc_excluded`` member's
        posted value (S04-R-07; one member, rounded once, S04-R-01)."""
        total = Fraction(0)
        for contract in self.contracts():
            v = self.vc_in_force(contract, at)
            if v is not None:
                scale = 10**self.minor_unit
                total += expected_value(v.scenarios) - Fraction(v.constrained, scale)
        return round_half_up(total, self.minor_unit)

    # -- allocation (group level, relative SSP, largest remainder; S08-R-07 changes) --

    def fixed_posted(self) -> int:
        return sum(line.price for line in self.lines)

    def total_posted(self, at: date | None = None) -> int:
        """The posted transaction price at ``at`` (default: the version date): Σ fixed line
        prices + Σ K in force (S04-R-02)."""
        return self.fixed_posted() + self.vc_constrained(self.version_date() if at is None else at)

    def _changes(self) -> list[tuple[date, str, int]]:
        """The price changes after the inception in ENG-06 order: (effective date, contract, ΔTP)
        with ΔTP = K_new − K_previous (S08-R-03). A version effective on or before the inception is
        not a change: it re-pins the element at the inception, so the inception price carries the
        latest such version's K (S08-R-01; ``estimates.apply`` returns unchanged for an event at or
        before the inception date)."""
        out = []
        for contract in self.contracts():
            versions = sorted(
                (v for v in self.vc if v.contract == contract), key=lambda v: v.version_no
            )
            pinned = self.vc_in_force(contract, self.inception)
            running = 0 if pinned is None else pinned.constrained
            for current in versions:
                if current.effective_date <= self.inception:
                    continue
                out.append((current.effective_date, contract, current.constrained - running))
                running = current.constrained
        return sorted(out, key=lambda c: (c[0], c[1]))

    def segments(self) -> list[tuple[date, dict[str, Fraction], dict[str, int]]]:
        """The allocation in force by date: the inception (S05-R-10 over the price including the
        K pinned at the inception), then one segment per price change: δ_p = ΔTP × w_p ÷ Σw over
        the element's contract's obligations and x′ = x + δ (S08-R-07 (a)); the posted amounts
        are one apportionment of the members' price over their exact quotas when the members are
        the whole group on inception segments and every x′ ≥ 0 (S08-R-07 (b)), else incremental
        shares largest_remainder(ΔTP, w) added to the amounts in force (S08-R-04, S08-R-06)."""
        weights = {line.subject: line.weight for line in self.lines}
        sigma = sum(weights.values(), Fraction(0))
        total = self.fixed_posted() + self.vc_constrained(self.inception)
        exact = {s: Fraction(total, 10**self.minor_unit) * w / sigma for s, w in weights.items()}
        posted = largest_remainder(total, weights)
        out = [(self.inception, exact, posted)]
        for when, contract, delta in self._changes():
            members = {s: w for s, w in weights.items() if s.startswith(f"{contract}/")}
            share = sum(members.values(), Fraction(0))
            step = Fraction(delta, 10**self.minor_unit)
            exact = {
                s: x + (step * members[s] / share if s in members else 0) for s, x in exact.items()
            }
            total += delta
            basis_after = sum(posted[s] for s in members) + delta
            posted = dict(posted)
            if set(members) == set(weights) and all(exact[s] >= 0 for s in members):
                # S08-R-07 (b): the element's obligations are the whole group on inception
                # segments — one apportionment of their posted price over the exact quotas
                if basis_after == 0:
                    posted.update(dict.fromkeys(members, 0))
                else:
                    posted.update(largest_remainder(basis_after, {s: exact[s] for s in members}))
            else:
                # S08-R-04 / S08-R-06: incremental posted shares of ΔTP over the element's
                # contract's obligations by inception weights (a group of several contracts)
                for s, delta_s in largest_remainder(delta, members).items():
                    posted[s] += delta_s
            out.append((when, exact, posted))
        return out

    def _segment_at(self, at: date) -> tuple[dict[str, Fraction], dict[str, int]]:
        current = self.segments()[0]
        for segment in self.segments():
            if segment[0] <= at:
                current = segment
        return current[1], current[2]

    def allocation(self) -> dict[str, int]:
        return self._segment_at(self.version_date())[1]

    def allocation_at(self, d: date) -> dict[str, int]:
        """The posted allocation in force at ``d`` (the segment whose date is the latest on or
        before ``d``; S08-R-06) — the bound of a period's cumulative revenue (P4)."""
        return self._segment_at(d)[1]

    def allocation_exact(self) -> dict[str, Fraction]:
        return self._segment_at(self.version_date())[0]

    # -- the version date and recognition --

    def version_date(self) -> date:
        """d_v: the latest effective date of the included events (booking and activation at the
        inception count; a voided event and its void do not)."""
        return max(
            [
                self.inception,
                *(event.day for event in self.live()),
                *(version.effective_date for version in self.vc),
            ]
        )

    def delivered(self, line: Line, through: date) -> int:
        return sum(
            event.amount
            for event in self.live()
            if event.kind == "DELIVERY"
            and (event.contract, event.line) == (line.contract, line.key)
            and event.day <= through
        )

    def billed(self, line: Line, through: date) -> int:
        return sum(
            event.amount
            for event in self.live()
            if event.kind == "BILLING"
            and (event.contract, event.line) == (line.contract, line.key)
            and event.day <= through
        )

    def progress(self, line: Line, d: date) -> Fraction:
        if line.kind == "PIT":
            return units_fraction(self.delivered(line, d), line.quantity)
        return time_fraction_daily(line.start, line.end, d)

    def revenue_cum(self) -> dict[str, int]:
        return self.revenue_at(self.version_date())

    def revenue_at(self, d: date) -> dict[str, int]:
        """Cumulative posted revenue per obligation at ``d`` (ALG-01 §2.1.3 over the progress at
        ``d`` with the allocation in force at ``d`` — an ``INCEPTION`` segment, S08-R-06; the stage
        09 target of the period ending ``d``)."""
        exact, posted = self._segment_at(d)
        return {
            line.subject: cumulative_posted(
                exact[line.subject], posted[line.subject], self.progress(line, d), self.minor_unit
            )
            for line in self.lines
        }

    def billed_cum(self) -> dict[str, int]:
        d = self.version_date()
        return {line.subject: self.billed(line, d) for line in self.lines}

    def positions(self) -> dict[str, int]:
        """D-12: cumulative billed − cumulative revenue per obligation."""
        revenue, billed = self.revenue_cum(), self.billed_cum()
        return {key: billed[key] - revenue[key] for key in revenue}

    def net_position(self) -> int:
        return sum(self.positions().values())

    def satisfaction(self) -> dict[str, str]:
        d = self.version_date()
        found = {}
        for line in self.lines:
            f = self.progress(line, d)
            found[line.subject] = (
                "SATISFIED" if f == 1 else "UNSATISFIED" if f == 0 else "PARTIALLY_SATISFIED"
            )
        return found

    # -- period locks --

    def state(self, period_key: str) -> str:
        return self.period_states.get(period_key, "open")

    def set_state(self, period_key: str, state: str) -> None:
        self.period_states[period_key] = state

    def locked(self) -> set[str]:
        return {key for key, state in self.period_states.items() if state not in POSTABLE}

    def first_postable_on_or_after(self, period_keys: Sequence[str], period_key: str) -> str | None:
        index = period_keys.index(period_key)
        for candidate in period_keys[index:]:
            if self.state(candidate) in POSTABLE:
                return candidate
        return None


def month_period_key(d: date) -> str:
    return f"FY{d.year}-P{d.month:02d}"


def add_months(d: date, months: int) -> date:
    years, month = divmod(d.month - 1 + months, 12)
    return date(d.year + years, month + 1, 1)


def term_end(start: date, months: int) -> date:
    return add_months(start, months) - timedelta(days=1)


# --- FX (ENGINE_SPEC_B §12; PRP-7 ``publish_fx_rates``) ---------------------------------------

SPOT = "spot"
AVERAGE = "average"
CLOSING = "closing"


@dataclass(frozen=True, slots=True)
class RateRow:
    """One published rate (04 T-REF-12): ``kind`` is ``spot`` (dated), ``average`` or ``closing``
    (of ``period_key``; a closing row may instead be dated the period end); base = transaction
    currency, quote = functional currency (S12-R-01)."""

    key: str
    version: str
    kind: str
    effective_date: date
    period_key: str | None
    rate: Fraction


def spot_rate(rows: Iterable[RateRow], on: date) -> RateRow:
    """S12-R-01: the latest ``spot`` row on or before ``on``; ties by greater version, then key."""
    candidates = [row for row in rows if row.kind == SPOT and row.effective_date <= on]
    if not candidates:
        raise LookupError(f"no spot rate on or before {on.isoformat()} (S12-R-01)")
    return max(candidates, key=lambda row: (row.effective_date, row.version, row.key))


def period_rate(rows: Iterable[RateRow], kind: str, period_key: str, period_end: date) -> RateRow:
    """S12-R-01: the one ``average`` or ``closing`` row of the period; a closing row dated the
    period end serves when no row names the period."""
    if kind not in (AVERAGE, CLOSING):
        raise ValueError(f"a period rate is average or closing, not {kind!r}")
    typed = [row for row in rows if row.kind == kind]
    candidates = [row for row in typed if row.period_key == period_key]
    if not candidates and kind == CLOSING:
        candidates = [row for row in typed if row.effective_date == period_end]
    if len(candidates) != 1:
        raise LookupError(f"{len(candidates)} {kind} rates of {period_key} (S12-R-01)")
    return candidates[0]


def functional(amount_txn: int, rate: Fraction, minor_unit_txn: int, minor_unit_fn: int) -> int:
    """S12-R-02: round_half_up(transaction exact × rate) at the functional minor unit."""
    return round_half_up(Fraction(amount_txn, 10**minor_unit_txn) * rate, minor_unit_fn)


def layer_relief(
    fn_original: int, txn_original: int, consumed_before: int, take: int, minor_unit_fn: int
) -> int:
    """S12-R-05: functional relief of ``take`` from a liability layer = cumulative_posted(original
    functional exact, original functional, consumed ÷ original transaction) after − before."""

    def cumulative(consumed: int) -> int:
        return cumulative_posted(
            Fraction(fn_original, 10**minor_unit_fn),
            fn_original,
            Fraction(consumed, txn_original),
            minor_unit_fn,
        )

    return cumulative(consumed_before + take) - cumulative(consumed_before)


def carrying_share(carrying: int, open_before: int, take: int, minor_unit_fn: int) -> int:
    """§12.2.2 ``carrying_portion``: the cumulatively rounded share of an asset layer's carrying
    that ``take`` of its ``open_before`` transaction balance carries out."""
    return cumulative_posted(
        Fraction(carrying, 10**minor_unit_fn), carrying, Fraction(take, open_before), minor_unit_fn
    )


def pro_rata_shares(total: int, open_by_key: Mapping[str, int]) -> dict[str, int]:
    """S12-R-07 ``PRO_RATA``: ``total`` apportioned over the open liability layers by open
    transaction balance (ALG-01 §2.1.2, keys = layer keys)."""
    return largest_remainder(total, {key: Fraction(value) for key, value in open_by_key.items()})


CONTRACT_LIABILITY = "CONTRACT_LIABILITY"
CONTRACT_ASSET = "CONTRACT_ASSET"
FIFO = "FIFO"
PRO_RATA = "PRO_RATA"


@dataclass(frozen=True, slots=True)
class Flow:
    """One control-role flow in transaction minor units (S12-R-03): a ``BILLING`` credit (its
    invoice date; ``order`` = (1, arrival position)), a ``REVENUE`` debit of one obligation at a
    period end, or a ``NEGATIVE_REVENUE`` credit when the obligation's cumulative revenue falls in
    the period (a price decrease's catch-up); time-driven flows carry ``order`` = (0, source) and
    run first on their day, by source."""

    day: date
    order: tuple[int, object]
    kind: str  # "BILLING" | "REVENUE" | "NEGATIVE_REVENUE"
    source: str  # the CV-22 event key, or "<subject>@<period>"
    amount: int


@dataclass(slots=True)
class LedgerLayer:
    key: str
    role: str
    source: str
    original: int
    open: int


@dataclass(frozen=True, slots=True)
class LedgerMovement:
    """A predicted T-CON-18 movement in transaction terms."""

    kind: str
    layer_key: str
    amount: int
    source: str
    day: date


def layer_ledger(flows: Iterable[Flow], consumption: str) -> list[LedgerMovement]:
    """ALG-08 §2.9.1 / ENGINE_SPEC_B §12.2.2 in transaction terms, from the flows alone: a credit
    settles the open asset layers in creation order and creates a liability layer with the rest;
    a debit relieves the open liability layers — ``FIFO`` in creation order (each but the last
    fully), or ``PRO_RATA`` by open balance with the largest remainder over the layer keys
    (S12-R-07) — and creates an asset layer with the rest (S12-R-06). A ``NEGATIVE_REVENUE`` credit
    is a credit like a billing (§12.2.2: every credit settles assets first, then layers the rest
    at spot on its own date)."""
    if consumption not in (FIFO, PRO_RATA):
        raise ValueError(f"POL-161 is FIFO or PRO_RATA, not {consumption!r}")
    layers: dict[str, LedgerLayer] = {}
    out: list[LedgerMovement] = []

    def new_key(role: str, source: str) -> str:
        base = f"{role}:{source}"
        if base not in layers:
            return base
        number = 2
        while f"{base}#{number}" in layers:
            number += 1
        return f"{base}#{number}"

    def create(role: str, kind: str, flow: Flow, amount: int) -> None:
        key = new_key(role, flow.source)
        layers[key] = LedgerLayer(key, role, flow.source, amount, amount)
        out.append(LedgerMovement(kind, key, amount, flow.source, flow.day))

    def opened(role: str) -> list[LedgerLayer]:
        return [layer for layer in layers.values() if layer.role == role and layer.open > 0]

    for flow in sorted(flows, key=lambda f: (f.day, f.order)):
        left = flow.amount
        if flow.kind in ("BILLING", "NEGATIVE_REVENUE"):
            for layer in opened(CONTRACT_ASSET):
                if left == 0:
                    break
                take = min(layer.open, left)
                layer.open -= take
                left -= take
                out.append(
                    LedgerMovement("ASSET_LAYER_SETTLED", layer.key, take, flow.source, flow.day)
                )
            if left:
                create(CONTRACT_LIABILITY, "LIABILITY_LAYER_CREATED", flow, left)
        elif flow.kind == "REVENUE":
            liabilities = opened(CONTRACT_LIABILITY)
            if consumption == FIFO:
                for layer in liabilities:
                    if left == 0:
                        break
                    take = min(layer.open, left)
                    layer.open -= take
                    left -= take
                    out.append(
                        LedgerMovement(
                            "LIABILITY_LAYER_CONSUMED", layer.key, take, flow.source, flow.day
                        )
                    )
            else:
                total = min(left, sum(layer.open for layer in liabilities))
                if total > 0:
                    ordered = sorted(liabilities, key=lambda layer: layer.key)
                    shares = largest_remainder(
                        total, {layer.key: Fraction(layer.open) for layer in ordered}
                    )
                    for layer in ordered:
                        share = shares[layer.key]
                        if share == 0:
                            continue
                        layer.open -= share
                        out.append(
                            LedgerMovement(
                                "LIABILITY_LAYER_CONSUMED", layer.key, share, flow.source, flow.day
                            )
                        )
                    left -= total
            if left:
                create(CONTRACT_ASSET, "ASSET_LAYER_CREATED", flow, left)
        else:
            raise ValueError(f"a flow is BILLING, REVENUE or NEGATIVE_REVENUE, not {flow.kind!r}")
    return out

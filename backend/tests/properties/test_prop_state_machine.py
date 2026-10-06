"""The stateful property machine over the platform (BUILD_SPEC PRP-7; dev-guide §9.7 "Stateful";
research 06 §18.4).

``RevenueMachine`` drives a world in memory as the platform would drive a fresh tenant: rules
append contracts, deliveries, billings, period-state transitions, late events and voids to the
event stream (``support.platform_props.machine_bundle``), the engine computes and closes it as the
platform closes a checkpoint (``platform_props.close_run``), and a lock seals the lines posted so
far as ``posted`` (RCP-05) before the period turns ``closed``. After every step the invariant
checks P1 (Σ allocations = the posted transaction price), P4 (schedule cumulative amounts within
[0, allocation]), P5 (every journal batch balances per currency, transaction and functional), P6
(the net presented position — liability − contract asset − unbilled receivable — rolls forward by
billings − revenue per period at the entity level, transaction and functional, with a locked period
presenting its lock snapshot and the JET-06 netting kinds excluded by construction) and P11
(nothing posts into a locked period; a line whose origin is locked carries ``LATE_EVENT`` and posts
in the earliest postable period on or after its origin), and that allocations, cumulative revenue,
cumulative billing, positions, satisfaction, the version date and ``net_position`` equal the
reference oracle's (``support.oracle``, written from ENGINE_SPEC and independent of
``erev_engine``).

Rules implemented with exact oracles: ``create_contract``, ``record_progress``, ``record_billing``,
``start_close``, ``lock``, ``submit_late_event``, ``void_event``, ``publish_fx_rates`` and
``change_vc``.

``change_vc`` (ENGINE_SPEC §4, §8): a contract may be created with one ``VARIABLE_CONSIDERATION``
element (``PERFORMANCE_INCENTIVE``, ``EXPECTED_VALUE``, untargeted) whose APPROVED version 1 is
part of the contract's inception stream; the rule approves a later version — new scenarios whose
probabilities sum to 1 (S04-R-05), the most conservative amount and the preparer's constrained
amount K drawn inside [most conservative, U] (S04-INV-02) — effective at a drawn day up to today,
possibly inside a locked period (a late version). The constraint judgement is the WORLD's: neither
the test nor the oracle computes how much to constrain (S04-R-07, POL-041). The oracle re-states
U = Σ amount × probability, the price Σ fixed + Σ K in force (S04-R-02), ΔTP = K_new − K_old
(S08-R-03) routed over the element's contract's obligations by inception weights as exact quota
increments and re-apportioned over the whole group by largest remainder (S08-R-07), and
recognition on the allocation in force at each date (S08-R-06 segments; the catch-up falls in the
change's period). Checked after every step: allocations, the transaction price, the
``vc_constrained_amount`` / ``vc_excluded_amount`` columns (S04-R-07), P1, P4, P5, P6 (the catch-up
through the intents) and P11 (a late version's lines carry LATE_EVENT).

``publish_fx_rates`` (ENGINE_SPEC_B §12): the entity's functional currency is drawn at the start
and may differ from the transaction currency; version 1 of the ``spot`` (dated the first of each
month), ``average`` and ``closing`` rates of the 24 calendar periods is published, and the rule
republishes one or more rate types of one period as a new version that replaces the period's rows
(the platform pins the highest APPROVED version covering a date, 04 T-REF-10; the recompute runs
under trigger ``FX_REPUBLISH``, E-87, which stage 14 treats as ``COMMAND``, RCP-08). A postable
period takes every type; a LOCKED period takes ``average`` and ``closing`` only — its ``spot``
would re-rate the historical layers of ERP-booked invoices (S12-R-04) for which the engine posts no
line (ERP mode, S10-R-06), so the rollforward across the lock would have no explaining line —
FX-LOCKED-SPOT-REPUBLISH-1, open for Ray with a Technical Accounting component (whether a corrected
historical rate re-rates a non-monetary layer at all, and who books it); not decided here, reduced
coverage. POL-161 (``FIFO`` / ``PRO_RATA``) and
POL-162 (``PERIOD_AVERAGE`` / ``TRANSACTION_DATE_SPOT``) are drawn as policy inputs. The oracle
side is ``support.oracle``'s FX functions written from S12-R-01 / -02 / -05 / -06 / -07 / -09 and
§12.2.2; the transaction-side decomposition — which layer, which take, in which order — is derived
oracle-side by ``oracle.layer_ledger`` from the world's own flows (the live billings and the
per-period revenue of every obligation) and compared with the engine's T-CON-18 movements; every
conversion, rate selection, relief rounding, settlement and remeasurement is checked against the
clause functions, and the presented functional net position against the layers' carrying. The
functional side of P5 and P6 holds; P6 is one identity in both currencies: the net presented
position rolls forward by the period's billings (the engine's view of the ERP's lines — the RC-02
tie-out to the ERP's own functional amounts is the platform's) plus the engine's lines to the three
balance roles.

World domain (Codex production-20260922-1442 §4): periods close in calendar order —
``start_close`` and ``lock`` act only on the earliest period not yet closed (``_next_to_close``).
Since supervisor ruling R-6 (CLO-LOCK-ORDER-1; PRD BR-CLS-08, ERR-65) this is the PRODUCT RULE for
the lock, not a coverage restriction: a period is not submitted for lock, and not locked, while an
earlier period of its entity and book is postable, so an out-of-order lock is not a reachable
state. Its former pin is the refusal witness
``test_clo_lock_order_1_a_later_period_is_not_locked_first`` of
``tests/unit/test_prp7_open_items.py``, which also keeps the arithmetic of what the refusal
prevents. The rate kinds of a period are drawn freely again: the former bound (a month's
``average`` and ``closing`` within a factor of 2 of its ``spot``) kept the machine away from
ENG-S14R10-FX-SIGN-1, which is closed — a delta whose transaction and functional amounts differ
in sign posts as a transaction line and a functional line (ENGINE_SPEC_B S14-R-10; supervisor
ruling R-44 (a)); the two former pins are passing witnesses in the same module.

NOT implemented in this slice (named open items of PRP-7): ``modify`` (the oracle does not model
it yet; the added-capacity and term kinds wait on Technical Accounting) and ``reopen`` — the
presentation of a reopened period that already
had lines redirected out of it is not specified: a billing effective in locked January arrives and
is booked in February (the earliest postable period); reopening January makes its recomputed
presented position carry the billing at its effective date while the booked line stays in
February, so the per-period rollforward has no defined opening / closing for January until the
CLO-7 reopen command and a §15.2.7 rule for reopened periods exist (measured on a deterministic
probe, T1 record). Lock snapshots are therefore never released here. The same machine over the
database platform (``DbPlatform``, the domain command handlers, ``lock_period`` /
``reopen_period`` — CLO-6 / CLO-7 gaps) is the DB-bound part, not written here (DG-TST-07).

The groups a changed rate reaches (item FX-REPUBLISH-DIRTY-1; 04 T-REF-11 rev 1.297; fragment
rev 1.14). The platform half of ``publish_fx_rates`` is built: the approval of a rate set
version marks the groups its changed rates reach, and the recompute of a marked group that
brings no event is stored under ``FX_REPUBLISH`` (``erev_api.domain.close.rate_reach``; the
database witnesses are ``tests/domain/contracts/test_fx_republish_mark.py`` and
``tests/domain/close/test_rate_reach_db.py`` — the former open items RCP17-FX-DIRTY-1 and
CLO19-FX-CAUSE-1). What the machine holds is the rule that says WHICH groups: after every
republication, whenever a line the platform would post moves — of the recompute or of a
period-end pass — ``rate_reach.at_work`` finds the group at work in the reach
(``rate_reach.reach_of``) of one of the changed keys, read from what the group's last
computation left: its events, its schedule lines, its sealed lines and the positions of its
balances. The lines of the period-end passes of a period that is not locked are NOT among
those facts: the platform holds none before that period's close run, and the rule has to
hold without them. Examples and the fail-first witness: ``test_prop_rate_reach.py``.

P6 is rewritten from the landed ``billed − Σ REVENUE credits`` form to ``billed + Σ (credit −
debit) of the engine's lines to the three balance roles``: in a single currency the two are the
same identity term by term (the only role lines are the revenue relief and the netting reclass,
which nets to zero) — the invariant asserts that equality on every example in the transaction
column and, in single-currency worlds, in the functional column too; in a two-currency world the
functional column also carries the JET-10a remeasurement lines, which the landed form lacked.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import math
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_api.domain.close.rate_reach import POSITIONS, at_work, reach_of
from erev_api.domain.contracts import computation
from erev_engine.bundle import EstimateVersionInput, FxRateInput, PostedAmountInput
from erev_engine.dates import month_end
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule
from support import bundles, intent_totals, oracle, platform_props
from support.prop_worlds import INCEPTION, LineSpec, MeasureSpec, WorldSpec, stream_base
from support.strategies import currencies, fx_rate_paths

pytestmark = pytest.mark.property

MAX_DAY = 540  # the machine's horizon in days after the inception (18 of the 24 months)
MONTHS = 24  # the entity calendar the machine drives (prop_worlds keeps 60 for the suites)
MAX_STEPS = 6
LATE_EVENT = "LATE_EVENT"
VOID = "VOID"
ROLES = ("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE")
_MINOR_UNIT = {"JPY": 0, "USD": 2, "BHD": 3, "CLF": 4}
RATE_KINDS = (oracle.SPOT, oracle.AVERAGE, oracle.CLOSING)
# The functional pieces a billing credit moves in the engine's view: the liability layer it creates
# and the asset layers it settles at spot (§12.2.2; the settlement remeasurement is a JET-10a line).
BILLING_PIECES = frozenset({"LIABILITY_LAYER_CREATED", "ASSET_LAYER_SETTLED"})
# The transaction-side movement kinds the oracle's layer ledger predicts (the remeasurements are
# functional-only and are checked by clause instead).
LEDGER_KINDS = frozenset(
    {
        "LIABILITY_LAYER_CREATED",
        "LIABILITY_LAYER_CONSUMED",
        "ASSET_LAYER_CREATED",
        "ASSET_LAYER_SETTLED",
    }
)
POL_161 = "fx.cl_layer_consumption"
POL_162 = "fx.unbilled_revenue_rate"


def _period_keys() -> list[str]:
    return [oracle.month_period_key(oracle.add_months(INCEPTION, n)) for n in range(MONTHS)]


class RevenueMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.currency = "USD"
        self.oracle = oracle.Oracle(minor_unit=2, inception=INCEPTION)
        self.contracts: list[tuple[str, tuple[LineSpec, ...]]] = []
        self.measures: list[MeasureSpec] = []
        self.voids: list[tuple[int, date]] = []
        self.clock = 0  # days after the inception: arrivals never move backwards
        self.states: dict[str, str] = {}
        self.sealed: tuple[PostedAmountInput, ...] = ()  # the journal runs booked so far
        self.snapshots: dict[str, dict[str, int]] = {}  # lock snapshot: period -> captions (kept)
        self.keys = _period_keys()
        # the ERP side of billing (Dr receivable / Cr CONTRACT_LIABILITY, JET-02): (period the
        # invoice line was booked in, signed amount) per booked line; a billing effective in a
        # locked period is booked in the earliest postable period when it arrives; a void of a
        # billing still in a postable period removes its line, of a billing in a locked period
        # books the reversal in the earliest postable period on or after the line's own
        self.billing_lines: dict[int, tuple[str, int]] = {}
        self.billing_reversals: list[tuple[str, int]] = []
        # FX (publish_fx_rates): the functional currency, the published rates by (kind, period
        # index) with the version that published each row, the drawn POL-161 / POL-162 values,
        # the E-87 trigger of the next recompute, and the engine-view functional amount of every
        # billing whose booking period is locked (frozen at the lock, as the ERP's line is)
        self.functional = "USD"
        self.rates: dict[tuple[str, int], Decimal] = {}
        self.rate_versions: dict[tuple[str, int], int] = {}
        self.rate_version = 0
        self.fx_policies: dict[str, str] = {}
        self.trigger = "COMMAND"
        self.booked_fn: dict[int, int] = {}
        self.billing_reversals_fn: list[tuple[str, int]] = []
        # variable consideration (change_vc): the APPROVED versions per contract, in arrival order,
        # and their engine inputs
        self.vc_versions: dict[str, list[oracle.VcVersion]] = {}
        self.vc_inputs: list[EstimateVersionInput] = []
        # the groups a changed rate reaches: the lines and the facts of the run the invariant
        # checked last — the world as its last computation left it, kept as plain data (a deep
        # copy of the machine copies them; a run's bundles do not copy) — and the (kind, period
        # index) keys a republication has changed since
        self.posted_amounts: dict[tuple[object, ...], tuple[int, int]] | None = None
        self.reach_facts: dict[str, object] | None = None
        self.republished: list[tuple[str, int]] = []

    # -- the world as a bundle --

    def spec(self) -> WorldSpec:
        return WorldSpec(
            self.currency,
            tuple(self.contracts),
            tuple(self.measures),
            vc=tuple(sorted(self.vc_versions)),
        )

    def two_currencies(self) -> bool:
        return self.functional != self.currency

    def bundle(self):  # type: ignore[no-untyped-def]
        return platform_props.machine_bundle(
            self.spec(),
            voids=tuple(self.voids),
            period_states=dict(self.states) or None,
            posted=self.sealed,
            months=MONTHS,
            functional_currency=self.functional,
            fx_rates=self.rate_rows() if self.two_currencies() else (),
            trigger=self.trigger,
            policies=self.fx_policies if self.two_currencies() else None,
            estimate_versions=tuple(self.vc_inputs),
            vc_events=tuple(
                (v.estimate_key.split("/")[0], v.version_key, v.effective_date)
                for v in self.vc_inputs
                if v.version_no >= 2
            ),
        )

    # -- published rates (S12-R-01; 04 T-REF-10 to T-REF-12) --

    def _period_dates(self, index: int) -> tuple[str, date, date]:
        start = oracle.add_months(INCEPTION, index)
        return self.keys[index], start, month_end(start)

    def rate_rows(self) -> tuple[FxRateInput, ...]:
        """The pinned rows of the current publication: one row per (kind, period); spot is dated
        the first of the month, average and closing name the period and are dated its end."""
        rows = []
        for (kind, index), value in sorted(self.rates.items()):
            period, start, end = self._period_dates(index)
            version = f"FX@v{self.rate_versions[(kind, index)]}"
            key = f"{kind.upper()}-{period}"
            if kind == oracle.SPOT:
                row = FxRateInput(
                    key, version, kind, self.currency, self.functional, start, None, value
                )
            else:
                row = FxRateInput(
                    key, version, kind, self.currency, self.functional, end, period, value
                )
            rows.append(row)
        return tuple(rows)

    def oracle_rows(self) -> list[oracle.RateRow]:
        return [
            oracle.RateRow(
                row.rate_key,
                row.version_key,
                row.rate_type,
                row.effective_date,
                row.period_key,
                oracle.Fraction(row.rate),
            )
            for row in self.rate_rows()
        ]

    def _publish(self, kinds: Sequence[str], index: int, values: Sequence[Decimal]) -> None:
        """A new rate-set version of ``kinds`` for the period at ``index``, replacing its rows."""
        self.rate_version += 1
        for kind, value in zip(kinds, values, strict=True):
            if self.rates.get((kind, index), value) != value:
                self.republished.append((kind, index))  # a changed key (T-REF-11)
            self.rates[(kind, index)] = value
            self.rate_versions[(kind, index)] = self.rate_version
        self.trigger = "FX_REPUBLISH"

    def _publish_all(self, paths: dict[str, Sequence[Decimal]]) -> None:
        """Version 1: every kind for every calendar period (the horizon needs closing rates while
        an asset layer is open, S12-R-09 / S12-R-13; revenue of future periods needs averages)."""
        for index in range(MONTHS):
            self._publish(
                RATE_KINDS, index, [paths[kind][index % len(paths[kind])] for kind in RATE_KINDS]
            )
        self.rate_version = 1
        self.rate_versions = dict.fromkeys(self.rate_versions, 1)
        self.trigger = "COMMAND"

    def today(self) -> date:
        return INCEPTION + timedelta(days=self.clock)

    def current_period_index(self) -> int:
        return self.keys.index(oracle.month_period_key(self.today()))

    def lines(self) -> list[tuple[str, LineSpec]]:
        return [(contract, line) for contract, lines in self.contracts for line in lines]

    def _delivered(self, contract: str, key: str) -> int:
        return sum(
            m.amount
            for i, m in enumerate(self.measures)
            if (m.contract, m.line, m.kind) == (contract, key, "DELIVERY")
            and all(v != i for v, _ in self.voids)
        )

    def _billed(self, contract: str, key: str) -> int:
        return sum(
            m.amount
            for i, m in enumerate(self.measures)
            if (m.contract, m.line, m.kind) == (contract, key, "BILLING")
            and all(v != i for v, _ in self.voids)
        )

    def _booking_period(self, day: int) -> str:
        """Where the platform books a line effective on ``day`` now: its own period when postable,
        else the earliest postable period on or after it (S14-R-06 for the engine's lines)."""
        own = oracle.month_period_key(INCEPTION + timedelta(days=day))
        placed = self.oracle.first_postable_on_or_after(self.keys, own)
        assert placed is not None, ("no postable period on or after", own)
        return placed

    def _record(self, contract: str, line: LineSpec, kind: str, day: int, amount: int) -> None:
        self.trigger = "COMMAND"
        self.measures.append(MeasureSpec(contract, line.key, kind, day, amount))
        self.oracle.record(
            oracle.Event(contract, line.key, kind, INCEPTION + timedelta(days=day), amount)
        )
        if kind == "BILLING":
            self.billing_lines[len(self.measures) - 1] = (self._booking_period(day), amount)

    # -- rules --

    @initialize(currency=currencies(), functional=currencies(), data=st.data())
    def start(self, currency: str, functional: str, data: st.DataObject) -> None:
        self.currency = currency
        self.functional = functional
        self.oracle = oracle.Oracle(minor_unit=_MINOR_UNIT[currency], inception=INCEPTION)
        if self.two_currencies():
            self.fx_policies = {
                POL_161: data.draw(st.sampled_from(("FIFO", "PRO_RATA"))),
                POL_162: data.draw(st.sampled_from(("PERIOD_AVERAGE", "TRANSACTION_DATE_SPOT"))),
            }
            self._publish_all({kind: data.draw(fx_rate_paths(MONTHS)) for kind in RATE_KINDS})
        self.create_contract(data)

    def _vc_floor(self, contract: str) -> int:
        """The lowest K a new version may carry without driving an exact quota of the contract's
        obligations below 0 — the engine refuses such a change (S08-R-06 VC_ALLOCATION_NEGATIVE, no
        segment), so the world stays inside the accepted domain (the refusal is not exercised)."""
        exact = self.oracle.segments()[-1][1]
        members = {
            line.subject: line.weight for line in self.oracle.lines if line.contract == contract
        }
        share = sum(members.values(), Fraction(0))
        mu = _MINOR_UNIT[self.currency]
        allowance = min(math.floor(exact[s] * share / w * 10**mu) for s, w in members.items())
        return max(0, self.vc_versions[contract][-1].constrained - allowance)

    def _admits_contract(
        self, lines: list[LineSpec], facts: tuple[list[tuple[int, int]], int, int] | None
    ) -> bool:
        """Whether booking ``lines`` at the inception keeps every exact quota of every segment
        non-negative: a new contract re-pools the group's inception allocation, so an earlier
        price decrease on another contract may then drive a quota below 0 — the engine refuses the
        recompute (VC_ALLOCATION_NEGATIVE, S08-R-06); such bookings are skipped (not exercised)."""
        trial = copy.deepcopy(self)
        trial._create_contract(lines, facts)
        return all(
            quota >= 0 for _, exact, _ in trial.oracle.segments() for quota in exact.values()
        )

    def _draw_vc(
        self, data: st.DataObject, floor_k: int = 0
    ) -> tuple[list[tuple[int, int]], int, int] | None:
        """The world's facts of one estimate version: 2 to 3 scenarios (amount in minor units,
        probability in hundredths summing to 100), the most conservative amount and the preparer's
        constrained amount K drawn inside [max(most conservative, floor_k), U] (S04-INV-02) —
        "how much to constrain" is drawn, never computed; None when no K fits."""
        count = data.draw(st.integers(2, 3))
        amounts = [data.draw(st.integers(0, 10**7)) for _ in range(count)]
        cuts = sorted(
            data.draw(
                st.lists(st.integers(1, 99), min_size=count - 1, max_size=count - 1, unique=True)
            )
        )
        bounds = [0, *cuts, 100]
        hundredths = [b - a for a, b in itertools.pairwise(bounds)]
        scenarios = list(zip(amounts, hundredths, strict=True))
        unconstrained = sum(Fraction(a, 1) * Fraction(h, 100) for a, h in scenarios)  # minor units
        conservative = min(amounts)
        lowest = max(conservative, floor_k)
        if lowest > math.floor(unconstrained):
            return None
        constrained = data.draw(st.integers(lowest, math.floor(unconstrained)))
        return scenarios, conservative, constrained

    def _add_vc_version(
        self, contract: str, day: int, facts: tuple[list[tuple[int, int]], int, int]
    ) -> None:
        """Approve the next version of the contract's element, effective ``day`` (the oracle's
        ``VcVersion`` and the engine's ``EstimateVersionInput``)."""
        scenarios, conservative, constrained = facts
        mu = _MINOR_UNIT[self.currency]
        versions = self.vc_versions.setdefault(contract, [])
        number = len(versions) + 1
        when = INCEPTION + timedelta(days=day)
        versions.append(
            oracle.VcVersion(
                contract,
                number,
                when,
                tuple((Fraction(a, 10**mu), Fraction(h, 100)) for a, h in scenarios),
                conservative,
                constrained,
            )
        )
        self.oracle.add_vc(versions[-1])
        self.vc_inputs.append(
            bundles.estimate_version(
                contract,
                number,
                when,
                scenarios=[(Decimal(a).scaleb(-mu), Decimal(h).scaleb(-2)) for a, h in scenarios],
                most_conservative=Decimal(conservative).scaleb(-mu),
                constrained=Decimal(constrained).scaleb(-mu),
                currency=self.currency,
            )
        )
        self.trigger = "COMMAND"

    def _create_contract(
        self, lines: list[LineSpec], vc: tuple[list[tuple[int, int]], int, int] | None = None
    ) -> None:
        """A contract of the given lines booked and activated at the inception, with one
        variable-consideration element (version 1 at the inception) when ``vc`` gives its facts."""
        contract = f"K-{len(self.contracts) + 1}"
        self.contracts.append((contract, tuple(lines)))
        end = {
            line.key: (
                INCEPTION if line.kind == "PIT" else oracle.term_end(INCEPTION, line.term_months)
            )
            for line in lines
        }
        self.oracle.add_contract(
            contract,
            [
                oracle.Line(
                    contract,
                    line.key,
                    line.kind,
                    line.price,
                    line.ssp,
                    line.quantity,
                    INCEPTION,
                    end[line.key],
                )
                for line in lines
            ],
        )
        if vc is not None:
            self._add_vc_version(contract, 0, vc)

    @rule(data=st.data())
    def create_contract(self, data: st.DataObject) -> None:
        """A contract of 1 to 3 lines booked and activated at the inception, with a
        variable-consideration element half of the time."""
        if len(self.contracts) >= 3:
            return
        lines = []
        for index in range(1, data.draw(st.integers(1, 3)) + 1):
            kind = data.draw(st.sampled_from(("PIT", "DAILY")))
            lines.append(
                LineSpec(
                    key=f"POB-{index:02d}",
                    kind=kind,
                    price=data.draw(st.integers(1, 10**7)),
                    ssp=data.draw(st.integers(1, 10**6)),
                    quantity=data.draw(st.integers(1, 4)) if kind == "PIT" else 1,
                    start_offset=0,
                    term_months=0 if kind == "PIT" else data.draw(st.integers(1, 18)),
                )
            )
        facts = self._draw_vc(data) if data.draw(st.booleans()) else None
        if self.vc_versions and not self._admits_contract(lines, facts):
            return  # booking it would drive an earlier change's exact quota below 0 (refused)
        self._create_contract(lines, facts)

    @precondition(lambda self: bool(self.vc_versions))
    @rule(data=st.data())
    def change_vc(self, data: st.DataObject) -> None:
        """A new APPROVED version of a contract's variable-consideration element, effective at a
        day between the previous version's and today (inside a locked period: a late version)."""
        contract = data.draw(st.sampled_from(sorted(self.vc_versions)))
        previous = (self.vc_versions[contract][-1].effective_date - INCEPTION).days
        self.clock = data.draw(st.integers(self.clock, min(self.clock + 90, MAX_DAY)))
        day = data.draw(st.integers(previous, max(previous, self.clock)))
        facts = self._draw_vc(data, self._vc_floor(contract) if day > 0 else 0)
        if facts is not None:
            self._add_vc_version(contract, day, facts)

    @precondition(
        lambda self: any(
            line.kind == "PIT" and self._delivered(c, line.key) < line.quantity
            for c, line in self.lines()
        )
    )
    @rule(data=st.data())
    def record_progress(self, data: st.DataObject) -> None:
        """A delivery of 1 to the remaining units of a point-in-time line, today or later."""
        open_lines = [
            (c, line)
            for c, line in self.lines()
            if line.kind == "PIT" and self._delivered(c, line.key) < line.quantity
        ]
        contract, line = data.draw(st.sampled_from(open_lines))
        remaining = line.quantity - self._delivered(contract, line.key)
        self.clock = data.draw(st.integers(self.clock, min(self.clock + 90, MAX_DAY)))
        self._record(contract, line, "DELIVERY", self.clock, data.draw(st.integers(1, remaining)))

    @precondition(
        lambda self: any(self._billed(c, line.key) < line.price for c, line in self.lines())
    )
    @rule(data=st.data())
    def record_billing(self, data: st.DataObject) -> None:
        """A billing within the line's remaining price, today or later."""
        open_lines = [
            (c, line) for c, line in self.lines() if self._billed(c, line.key) < line.price
        ]
        contract, line = data.draw(st.sampled_from(open_lines))
        remaining = line.price - self._billed(contract, line.key)
        self.clock = data.draw(st.integers(self.clock, min(self.clock + 90, MAX_DAY)))
        self._record(contract, line, "BILLING", self.clock, data.draw(st.integers(1, remaining)))

    def _periods_through_today(self) -> list[str]:
        return self.keys[: self.current_period_index() + 1]

    def _next_to_close(self) -> str | None:
        """The earliest period through today that is not closed — periods close in calendar order
        (the machine's close-order domain; out-of-order locks are not exercised)."""
        for key in self._periods_through_today():
            if self.oracle.state(key) in oracle.POSTABLE:
                return key
        return None

    @precondition(
        lambda self: (
            (period := self._next_to_close()) is not None and self.oracle.state(period) == "open"
        )
    )
    @rule(data=st.data())
    def start_close(self, data: st.DataObject) -> None:
        """``open`` → ``closing`` (still postable) for the earliest period not yet closed."""
        period = self._next_to_close()
        assert period is not None
        self.states[period] = "closing"
        self.oracle.set_state(period, "closing")
        self.trigger = "COMMAND"

    @precondition(lambda self: self._next_to_close() is not None)
    @rule(data=st.data())
    def lock(self, data: st.DataObject) -> None:
        """The platform posts the journals of the checkpoint, then locks the earliest period not
        yet closed: the lines posted so far are sealed as ``posted`` and the period turns
        ``closed``."""
        period = self._next_to_close()
        assert period is not None
        self._lock(period)

    def _lock(self, period: str) -> None:
        run = platform_props.close_run(self.bundle())
        # the journal runs through ``period`` are booked (RCP-05) and the lock snapshot of the
        # period's presented balances is taken (ENGINE_SPEC_B §15.2.7; the rollforward's opening)
        self.sealed = platform_props.merge_sealed(
            self.sealed, platform_props.sealed_through(run.outputs, self.keys, period)
        )
        self.snapshots[period] = self._presented(run, period)
        # the ERP's invoice lines booked in the period are frozen with it: their engine-view
        # functional amounts (the layer created and the asset layers settled at spot) stop moving
        for index, (booked, _) in self.billing_lines.items():
            if booked == period and index not in self.booked_fn:
                self.booked_fn[index] = self._billing_fn(run, index)
        self.states[period] = "closed"
        self.oracle.set_state(period, "closed")
        self.trigger = "COMMAND"

    @precondition(lambda self: bool(self.oracle.locked()) and bool(self.lines()))
    @rule(data=st.data())
    def submit_late_event(self, data: st.DataObject) -> None:
        """A delivery or billing effective inside a locked period, arriving now (S08-R-08)."""
        locked = sorted(self.oracle.locked(), key=self.keys.index)
        period = data.draw(st.sampled_from(locked))
        start = oracle.add_months(INCEPTION, self.keys.index(period))
        day = (start - INCEPTION).days + data.draw(st.integers(0, 27))
        candidates = [
            (c, line)
            for c, line in self.lines()
            if (line.kind == "PIT" and self._delivered(c, line.key) < line.quantity)
            or self._billed(c, line.key) < line.price
        ]
        if not candidates:
            return
        contract, line = data.draw(st.sampled_from(candidates))
        if line.kind == "PIT" and self._delivered(contract, line.key) < line.quantity:
            remaining = line.quantity - self._delivered(contract, line.key)
            self._record(contract, line, "DELIVERY", day, data.draw(st.integers(1, remaining)))
        else:
            remaining = line.price - self._billed(contract, line.key)
            self._record(contract, line, "BILLING", day, data.draw(st.integers(1, remaining)))

    @precondition(lambda self: self.two_currencies())
    @rule(data=st.data())
    def publish_fx_rates(self, data: st.DataObject) -> None:
        """A new rate-set version republishing one or more rate types of one period (RCP-17;
        the recompute runs under ``FX_REPUBLISH``): every type of a postable period; ``average``
        and ``closing`` only of a locked period (its ``spot`` is excluded — see the module note)."""
        index = data.draw(st.integers(0, MONTHS - 1))
        postable = self.oracle.state(self.keys[index]) in oracle.POSTABLE
        kinds = list(RATE_KINDS) if postable else [oracle.AVERAGE, oracle.CLOSING]
        chosen = data.draw(st.lists(st.sampled_from(kinds), min_size=1, unique=True))
        values = [Decimal(data.draw(st.integers(1, 10**16))).scaleb(-12) for _ in chosen]
        self._publish(chosen, index, values)

    @precondition(
        lambda self: any(all(v != i for v, _ in self.voids) for i in range(len(self.measures)))
    )
    @rule(data=st.data())
    def void_event(self, data: st.DataObject) -> None:
        """An ``EVENT_VOIDED`` of a delivery or billing not voided yet (S01-R-12), effective today
        or later."""
        live = [i for i in range(len(self.measures)) if all(v != i for v, _ in self.voids)]
        index = data.draw(st.sampled_from(live))
        self.clock = max(self.clock, self.measures[index].day)
        self.clock = data.draw(st.integers(self.clock, min(self.clock + 30, MAX_DAY)))
        self._void(index)

    def _void(self, index: int) -> None:
        self.trigger = "COMMAND"
        self.voids.append((index, self.today()))
        self.oracle.void(index)
        booked = self.billing_lines.get(index)
        if booked is None:
            return
        if self.oracle.state(booked[0]) in oracle.POSTABLE:
            # the invoice line still sits in a postable period: the ERP removes it in place
            del self.billing_lines[index]
        else:
            # the invoice line sits in a locked period: it STAYS booked there (the lock snapshot
            # carries it) and the ERP books the credit note in the earliest postable period now
            # (T1-PRP7-BILLING-VOID-1, Codex production-20260922-0017); the credit note reverses
            # the frozen functional amount (a credit memo relieves at historical carrying,
            # S12-R-08). "Earliest postable" is counted from the period the line is booked in, NOT
            # from the void's arrival day (T1-PRP7-VOID-PERIOD-1, the batch-#9 example): a void
            # removes the event from the replay (ENGINE_SPEC S01-R-12) and the difference of a
            # closed period posts in the first later open period (05 RCP-04, RCP-06; ENGINE_SPEC_B
            # S14-R-06, S14-R-08) — the void's own date plays no part, and under
            # ``billing.posting = ENGINE`` the engine posts this very reversal there (pinned
            # below). The landed model used ``_booking_period(self.clock)``, which names a later
            # period whenever a postable period lies between the locked line and today.
            now = self.oracle.first_postable_on_or_after(self.keys, booked[0])
            assert now is not None, ("no postable period on or after", booked[0])
            self.billing_reversals.append((now, -booked[1]))
            if self.two_currencies():
                self.billing_reversals_fn.append((now, -self.booked_fn[index]))

    # -- the engine's view of the billings and the FX layers --

    def _event_key(self, index: int) -> str:
        """The CV-22 key of measure ``index``: the contract's n-th measure is EV-(n + base), the
        base being 2, or 3 when the contract carries a variable-consideration element."""
        contract = self.measures[index].contract
        ordinal = sum(1 for m in self.measures[: index + 1] if m.contract == contract)
        return f"{contract}/EV-{ordinal + stream_base(self.spec(), contract):06d}"

    def _billing_fn(self, run: platform_props.CloseRun, index: int) -> int:
        """The functional amount of billing ``index`` in the engine's view: the liability layer it
        created plus the asset layers it settled at spot (§12.2.2)."""
        key = self._event_key(index)
        return sum(
            int(str(m["amount_functional"]))
            for m in platform_props.layer_movements(run.primary())
            if m["source_key"] == key and m["movement_kind"] in BILLING_PIECES
        )

    def _billed_fn_by_period(self, run: platform_props.CloseRun) -> dict[str, int]:
        """Billings per booking period in the engine's functional view: frozen once the booking
        period is locked, else read from this run; the credit notes of voided locked billings."""
        found: dict[str, int] = {}
        for index, (booked, _) in self.billing_lines.items():
            amount = self.booked_fn.get(index)
            if amount is None:
                amount = self._billing_fn(run, index)
            found[booked] = found.get(booked, 0) + amount
        for period, amount in self.billing_reversals_fn:
            found[period] = found.get(period, 0) + amount
        return found

    def _oracle_flows(self) -> list[oracle.Flow]:
        """The control-role flows of the world from the machine's own facts (S12-R-03): every live
        billing as a credit on its invoice date in arrival order, and each obligation's revenue
        movement of each period (ALG-01 §2.1.3 at the period end, from the oracle, on the
        allocation in force) as a time-driven debit — or a ``NEGATIVE_REVENUE`` credit when a price
        decrease lowers the cumulative revenue (a negative catch-up)."""
        flows = [
            oracle.Flow(
                INCEPTION + timedelta(days=m.day),
                (1, index),
                "BILLING",
                self._event_key(index),
                m.amount,
            )
            for index, m in enumerate(self.measures)
            if m.kind == "BILLING" and all(v != index for v, _ in self.voids)
        ]
        previous = {line.subject: 0 for line in self.oracle.lines}
        for n in range(MONTHS):
            period, _, end = self._period_dates(n)
            revenue = self.oracle.revenue_at(end)
            for subject in sorted(revenue):
                movement = revenue[subject] - previous[subject]
                previous[subject] = revenue[subject]
                if movement:
                    source = f"{subject}@{period}"
                    kind = "REVENUE" if movement > 0 else "NEGATIVE_REVENUE"
                    flows.append(oracle.Flow(end, (0, source), kind, source, abs(movement)))
        return flows

    def _remainder_row(self, rows: list[oracle.RateRow], when: date) -> oracle.RateRow:
        """S12-R-06 / POL-162: the rate of revenue recognised beyond the available liability."""
        if self.fx_policies[POL_162] == "PERIOD_AVERAGE":
            return oracle.period_rate(
                rows, oracle.AVERAGE, oracle.month_period_key(when), month_end(when)
            )
        return oracle.spot_rate(rows, when)

    def _fx_checks(self, run: platform_props.CloseRun) -> None:
        """The engine's T-CON-18 layer movements of the primary book against the oracle: the
        transaction-side decomposition (which layer, which take, in which order — FIFO or pro rata)
        equals ``oracle.layer_ledger`` over the world's own flows (S12-R-03, S12-R-06, S12-R-07;
        §12.2.2); every functional amount follows its clause (S12-R-01, S12-R-02, S12-R-05,
        S12-R-06, S12-R-09; §12.2.2); the presented functional net position of every period is
        the layers' carrying at its end (S12-INV-03)."""
        moves = platform_props.layer_movements(run.primary())
        rows = self.oracle_rows()
        expected = [
            (m.kind, m.layer_key, m.amount, m.source)
            for m in oracle.layer_ledger(self._oracle_flows(), self.fx_policies[POL_161])
        ]
        actual = [
            (
                str(m["movement_kind"]),
                str(m["layer_key"]),
                int(str(m["amount_txn"])),
                str(m["source_key"]),
            )
            for m in moves
            if m["movement_kind"] in LEDGER_KINDS
        ]
        if actual != expected:
            first = next(
                (
                    i
                    for i, pair in enumerate(zip(actual, expected, strict=False))
                    if pair[0] != pair[1]
                ),
                min(len(actual), len(expected)),
            )
            raise AssertionError(
                (
                    "I5 layer ledger: the engine's decomposition differs from the oracle's",
                    {
                        "at": first,
                        "engine": actual[first : first + 3],
                        "oracle": expected[first : first + 3],
                    },
                    {"engine movements": len(actual), "oracle movements": len(expected)},
                )
            )
        mu_txn, mu_fn = _MINOR_UNIT[self.currency], _MINOR_UNIT[self.functional]
        layers: dict[str, dict[str, int | str]] = {}
        order: list[str] = []
        pending: dict[str, int] = {}  # a settlement remeasurement awaiting its settlement

        def amount(row: object, name: str) -> int:
            return int(str(row[name]))  # type: ignore[index]

        def create(key: str, role: str, txn: int, fn: int) -> None:
            layers[key] = {
                "role": role,
                "txn": txn,
                "fn": fn,
                "consumed": 0,
                "open": txn,
                "carrying": fn,
            }
            order.append(key)

        def consume(group: list) -> None:  # type: ignore[type-arg]
            # the consecutive consumptions of one debit flow (their order and takes are the
            # ledger's, compared below); each relief is the S12-R-05 cumulative share
            for g in group:
                k, take, relief = (
                    str(g["layer_key"]),
                    amount(g, "amount_txn"),
                    amount(g, "amount_functional"),
                )
                layer = layers[k]
                expected_relief = oracle.layer_relief(
                    int(layer["fn"]), int(layer["txn"]), int(layer["consumed"]), take, mu_fn
                )
                assert relief == expected_relief, ("S12-R-05 relief", g, expected_relief)
                layer["consumed"] = int(layer["consumed"]) + take
                layer["open"] = int(layer["open"]) - take
                layer["carrying"] = int(layer["carrying"]) - relief
                if layer["open"] == 0:
                    assert layer["carrying"] == 0, ("S12-R-05 a consumed layer ends at 0", g)

        def step(position: int) -> int:
            m = moves[position]
            kind, key, when = str(m["movement_kind"]), str(m["layer_key"]), m["effective_date"]
            assert isinstance(when, date)
            txn, fn = amount(m, "amount_txn"), amount(m, "amount_functional")
            if kind == "LIABILITY_LAYER_CREATED":
                row = oracle.spot_rate(rows, when)  # the ERP-mode layer date is the invoice date
                assert fn == oracle.functional(txn, row.rate, mu_txn, mu_fn), ("S12-R-02 spot", m)
                assert m["rate_key"] == row.key, ("S12-R-01 spot row", m, row)
                create(key, "L", txn, fn)
                return position + 1
            if kind == "ASSET_LAYER_CREATED":
                assert "@FY" in str(m["source_key"]), ("a revenue remainder", m)
                row = self._remainder_row(rows, when)
                assert fn == oracle.functional(txn, row.rate, mu_txn, mu_fn), ("S12-R-06", m)
                assert m["rate_key"] == row.key, ("S12-R-06 row", m, row)
                create(key, "A", txn, fn)
                return position + 1
            if kind == "LIABILITY_LAYER_CONSUMED":
                source, group = m["source_key"], []
                while (
                    position < len(moves)
                    and moves[position]["movement_kind"] == "LIABILITY_LAYER_CONSUMED"
                    and moves[position]["source_key"] == source
                ):
                    group.append(moves[position])
                    position += 1
                consume(group)
                return position
            layer = layers[key]
            if kind == "ASSET_LAYER_REMEASURED":
                if m["reason"] == "PERIOD_END":
                    period_key = oracle.month_period_key(when)
                    row = oracle.period_rate(rows, oracle.CLOSING, period_key, month_end(when))
                    target = oracle.functional(int(layer["open"]), row.rate, mu_txn, mu_fn)
                    assert fn == target - int(layer["carrying"]), ("S12-R-09 closing", m, target)
                    assert m["rate_key"] == row.key, ("S12-R-09 row", m, row)
                else:
                    assert m["reason"] == "SETTLEMENT", m
                    pending[key] = fn
                layer["carrying"] = int(layer["carrying"]) + fn
                return position + 1
            if kind == "ASSET_LAYER_SETTLED":
                difference = pending.pop(key, 0)
                carrying_before = int(layer["carrying"]) - difference
                row = oracle.spot_rate(rows, when)
                at_spot = oracle.functional(txn, row.rate, mu_txn, mu_fn)
                assert fn == at_spot, ("§12.2.2 settled at spot", m, at_spot)
                share = oracle.carrying_share(carrying_before, int(layer["open"]), txn, mu_fn)
                assert difference == at_spot - share, ("§12.2.2 settlement", m, at_spot, share)
                layer["open"] = int(layer["open"]) - txn
                layer["carrying"] = int(layer["carrying"]) - fn
                return position + 1
            raise AssertionError(("unexpected layer movement", m))

        position = 0
        net_by_period: dict[str, int] = {}
        for index in range(MONTHS):
            period_key, _, end = self._period_dates(index)
            while position < len(moves) and moves[position]["effective_date"] <= end:  # type: ignore[operator]
                position = step(position)
            net_by_period[period_key] = sum(
                int(layer["carrying"]) * (1 if layer["role"] == "L" else -1)
                for layer in layers.values()
            )
        assert position == len(moves), ("movements beyond the horizon", moves[position:])
        assert not pending, ("a settlement remeasurement without its settlement", pending)
        for period_key in self.keys:
            presented = self._net(self._presented(run, period_key), True)
            assert presented == net_by_period[period_key], (
                "S12-INV-03 functional: presented net position vs the layers' carrying",
                period_key,
                presented,
                net_by_period[period_key],
            )

    # -- presented balances --

    def _presented(self, run: platform_props.CloseRun, period_key: str) -> dict[str, int]:
        """The entity's presented captions at the period end, transaction and functional, summed
        over the group's contracts (the ALG-02 pool)."""
        rows = platform_props.balance_rows(run.primary())
        entity = run.bundle.entities[0].code
        found: dict[str, int] = {}
        for functional in (False, True):
            for role in ROLES:
                found[f"{role}:{int(functional)}"] = sum(
                    platform_props.balance(rows[(f"{c}@{entity}", period_key)], role, functional)
                    for c in platform_props.iter_contracts(run.bundle)
                )
        return found

    @staticmethod
    def _net(captions: dict[str, int], functional: bool) -> int:
        """D-12: the net presented position = liability − contract asset − unbilled receivable."""
        f = int(functional)
        return (
            captions[f"CONTRACT_LIABILITY:{f}"]
            - captions[f"CONTRACT_ASSET:{f}"]
            - captions[f"UNBILLED_RECEIVABLE:{f}"]
        )

    def _revenue_posted(
        self, run: platform_props.CloseRun, period_key: str, functional: bool
    ) -> int:
        """Σ REVENUE credits posted to the period: this run's intents plus the sealed runs (the
        landed P6 form's revenue term; kept as the witness of the rewrite)."""
        total = 0
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY):
            if intent.posting_period_key != period_key:
                continue
            for line in intent.lines:
                if line.account_role == "REVENUE":
                    amount = line.amount_functional if functional else line.amount_txn
                    total += amount if line.side == "C" else -amount
        for item in run.bundle.posted:
            if (
                item.book_code == platform_props.PRIMARY
                and item.period_key == period_key
                and item.account_role == "REVENUE"
            ):
                total -= item.amount_functional if functional else item.amount_txn  # debit +
        return total

    def _role_lines_net_credit(
        self, run: platform_props.CloseRun, period_key: str, functional: bool
    ) -> int:
        """Σ (credit − debit) of the engine's lines to the three balance roles posted to the
        period: this run's intents plus the sealed runs (debit positive)."""
        total = 0
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY):
            if intent.posting_period_key != period_key:
                continue
            for line in intent.lines:
                if line.account_role in ROLES:
                    amount = line.amount_functional if functional else line.amount_txn
                    total += amount if line.side == "C" else -amount
        for item in run.bundle.posted:
            if (
                item.book_code == platform_props.PRIMARY
                and item.period_key == period_key
                and item.account_role in ROLES
            ):
                total -= item.amount_functional if functional else item.amount_txn  # debit +
        return total

    # -- the invariant --

    # -- the groups a changed rate reaches (close.rate_reach; item FX-REPUBLISH-DIRTY-1) --

    @staticmethod
    def _amounts(*outputs, sealed=()):  # type: ignore[no-untyped-def]
        """What the platform's ledger holds once ``outputs`` are posted on top of ``sealed``: the
        two amounts of every posting identity, without the rates stamped on them — a rate that
        is replaced moves a line only when it moves an amount."""
        found = {}
        for item in intent_totals.posted(*outputs, sealed=sealed):
            if item.amount_txn or item.amount_functional:
                identity = dataclasses.replace(
                    item, amount_txn=0, amount_functional=0, rate_refs=()
                )
                found[dataclasses.astuple(identity)] = (item.amount_txn, item.amount_functional)
        return found

    def _reach_facts(self, run: platform_props.CloseRun) -> dict[str, object]:
        """What ``rate_reach.at_work`` reads of the group as the computation of ``run`` leaves
        it: the group's inception, the effective dates of its events, the period ends of its
        schedule lines and of its sealed lines — those the locks sealed and those its
        COMPUTATION posts; the lines of the period-end passes of a period no close run has locked
        are left out, as the platform holds none before that period's run — and whether a
        balance the version stores holds a position."""
        ends = {key: self._period_dates(index)[2] for index, key in enumerate(self.keys)}
        books = run.command.books
        return {
            "inception": run.bundle.group.inception_date,
            "events": [event.effective_date for event in run.bundle.events],
            "scheduled": [ends[line.period_key] for book in books for line in book.schedules],
            "sealed": [
                ends[item.period_key]
                for item in intent_totals.posted(run.command, sealed=self.sealed)
            ],
            "position": any(
                int(str(balance.columns.get(name) or 0)) != 0
                for book in books
                for balance in computation._latest_balances(run.bundle, book.balances).values()
                for name in POSITIONS
            ),
        }

    def _the_reach_holds(self, run: platform_props.CloseRun) -> None:
        """Whenever a republication moves a line the platform would post — of the recompute or
        of a period-end pass — the reach of one of its changed keys finds the group at work (04
        T-REF-11 "The groups a changed rate reaches"; ``close.rate_reach``): the rule by which
        the approval marks leaves out no group a rate can move. Held against the lines and the
        facts of the run the invariant checked last, before the republication."""
        before, facts, changed = self.posted_amounts, self.reach_facts, self.republished
        if before is None or facts is None or not changed:
            return
        if self._amounts(*run.outputs, sealed=self.sealed) == before:
            return
        months = [self._period_dates(index)[1:] for index in range(MONTHS)]
        horizon = max(
            end
            for (_, end), key in zip(months, self.keys, strict=True)
            if self.oracle.state(key) in oracle.POSTABLE
        )
        reaches = []
        for kind, index in changed:
            _, start, end = self._period_dates(index)
            spot = kind == oracle.SPOT
            later = self._period_dates(index + 1)[1] if spot and index + 1 < MONTHS else None
            reaches.append(
                reach_of(
                    kind, start if spot else end, periods=months, horizon=horizon, next_spot=later
                )
            )
        assert any(reach is not None and at_work(*reach, **facts) for reach in reaches), (
            "the reach",
            changed,
            reaches,
            {name: value for name, value in facts.items() if name in {"inception", "position"}},
        )

    @invariant()
    def engine_agrees_with_the_oracle_and_the_properties_hold(self) -> None:
        if not self.contracts:
            return
        run = platform_props.close_run(self.bundle())
        book = run.primary()
        versions = {v.subject_key: v.columns for v in book.obligation_versions}
        # the oracle: allocation, recognition, billing, position, status, version date
        assert set(versions) == {line.subject for line in self.oracle.lines}
        allocation, revenue = self.oracle.allocation(), self.oracle.revenue_cum()
        billed, positions = self.oracle.billed_cum(), self.oracle.positions()
        status, d_v = self.oracle.satisfaction(), self.oracle.version_date()
        for subject, columns in versions.items():
            assert columns["allocated_amount"] == allocation[subject], ("allocation", subject)
            assert columns["revenue_cum"] == revenue[subject], ("revenue_cum", subject, d_v)
            assert columns["billed_cum"] == billed[subject], ("billed_cum", subject)
            assert columns["position_obligation"] == positions[subject], ("position", subject)
            assert columns["satisfaction_status"] == status[subject], ("status", subject)
            assert columns["effective_date"] == d_v, (
                "version date",
                columns["effective_date"],
                d_v,
            )
        assert book.contract_version is not None
        contract_columns = book.contract_version.columns
        assert contract_columns["net_position"] == self.oracle.net_position()
        # P1: Σ allocations = the posted transaction price of the group = Σ line prices
        total = self.oracle.total_posted()
        assert sum(allocation.values()) == total
        assert contract_columns["transaction_price"] == total
        if self.vc_versions:
            # S04-R-07: Σ K in force and the excluded Σ (U − K), one member rounded once
            assert contract_columns["vc_constrained_amount"] == self.oracle.vc_constrained(d_v), (
                "vc_constrained_amount",
                contract_columns["vc_constrained_amount"],
            )
            assert contract_columns["vc_excluded_amount"] == self.oracle.vc_excluded(d_v), (
                "vc_excluded_amount",
                contract_columns["vc_excluded_amount"],
            )
        # P4: schedule bounds — the engine schedules revenue by cause: a NORMAL stream (the pattern
        # on the allocation in force, net of the catch-ups) and a TP_CHANGE stream whose rows sit in
        # the periods of the price changes (the catch-ups, cumulative); the recognised revenue at a
        # period end is the sum of every stream's latest cumulative at or before it. Per
        # (obligation, period) that sum lies within [0, the allocation in force at the period's
        # end] (S08-R-06) and equals the oracle's recognised revenue at that date. Without a price
        # change there is one NORMAL line per (obligation, period) and the bound is the landed one,
        # the current allocation (the witness).
        streams: dict[str, dict[str, dict[str, int]]] = {}
        for line in book.schedules:
            if platform_props._is_revenue_schedule(line):
                kind = str(line.line_type.value)  # type: ignore[attr-defined]
                streams.setdefault(line.subject_key, {}).setdefault(line.period_key, {})[kind] = (
                    line.cumulative_amount
                )
        changed = bool(self.oracle._changes())
        for subject, by_period in streams.items():
            latest: dict[str, int] = {}
            for period_key in sorted(by_period, key=self.keys.index):
                latest.update(by_period[period_key])
                end = self._period_dates(self.keys.index(period_key))[2]
                bound = self.oracle.allocation_at(end)[subject]
                cumulative = sum(latest.values())
                if not changed:
                    assert list(by_period[period_key]) == ["NORMAL"], ("P4 one stream", subject)
                    assert bound == allocation[subject], ("P4 bound witness", subject, period_key)
                assert 0 <= cumulative <= bound, ("P4", subject, period_key, cumulative, bound)
                assert cumulative == self.oracle.revenue_at(end)[subject], (
                    "P4 scheduled cumulative vs the oracle's recognised revenue",
                    subject,
                    period_key,
                    cumulative,
                    self.oracle.revenue_at(end)[subject],
                )
        # P5: every batch of the checkpoint balances (transaction and functional)
        for e, period_key in platform_props.periods_posted(run, platform_props.PRIMARY, "LEGACY"):
            for mode in platform_props.modes(run):
                assert (
                    platform_props.unbalanced(platform_props.batch(run, e, period_key, mode)) == []
                )
                functional = platform_props.functional_batch(run, e, period_key, mode)
                assert platform_props.unbalanced(functional) == []
        # P11: nothing posts into a locked period; redirected lines are tagged and placed
        locked = self.oracle.locked()
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY, "LEGACY"):
            assert intent.posting_period_key not in locked, ("P11 posted into locked", intent)
            if intent.origin_period_key is not None and intent.origin_period_key in locked:
                # S14-R-06 late event, or S14-R-08 a subject of a contract with a new void
                assert intent.reason_code in (LATE_EVENT, VOID), ("P11 reason", intent.entry_kind)
                expected = self.oracle.first_postable_on_or_after(
                    self.keys, intent.origin_period_key
                )
                assert intent.posting_period_key == expected, (
                    "P11 placement",
                    intent.origin_period_key,
                    intent.posting_period_key,
                    expected,
                )
        # P6 with locks: the net presented position rolls forward by the period's billings plus
        # the engine's lines to the three balance roles (revenue relief, JET-10a remeasurement;
        # the JET-06 netting reclass moves between captions and nets to zero), in both currencies
        # (D-12 per period; S15-R-07 opening + lines = closing). A locked period presents its lock
        # snapshot (ENGINE_SPEC_B §15.2.7): a late event's lines reach the first open period as
        # LATE_EVENT lines and the snapshot stays. Billings are the ERP's lines: transaction
        # amounts as booked; functional amounts in the engine's view (the layer a billing created
        # and the asset layers it settled at spot), frozen once the booking period is locked.
        billed_by_period: dict[str, int] = {}
        for period, amount in [*self.billing_lines.values(), *self.billing_reversals]:
            billed_by_period[period] = billed_by_period.get(period, 0) + amount
        billed_fn_by_period = self._billed_fn_by_period(run) if self.two_currencies() else None
        posted_periods = {p for _, p in platform_props.periods_posted(run, platform_props.PRIMARY)}
        posted_periods |= {s.period_key for s in run.bundle.posted if s.book_code == "ASC606"}
        posted_periods |= set(billed_by_period)
        last = max((self.keys.index(p) for p in posted_periods), default=-1)
        presented = {
            key: self.snapshots.get(key) or self._presented(run, key)
            for key in self.keys[: last + 1]
        }
        for functional in (False, True):
            billed = (
                billed_fn_by_period
                if functional and billed_fn_by_period is not None
                else billed_by_period
            )
            for index, period_key in enumerate(self.keys[: last + 1]):
                opening = self._net(presented[self.keys[index - 1]], functional) if index else 0
                closing = self._net(presented[period_key], functional)
                billed_now = billed.get(period_key, 0)
                lines_now = self._role_lines_net_credit(run, period_key, functional)
                if not functional or not self.two_currencies():
                    # the rewrite's witness: the landed form's revenue term equals, term by term,
                    # the engine's role lines (revenue relief; the reclass nets to zero) — in the
                    # transaction column always, in the functional column of a single currency
                    revenue_now = self._revenue_posted(run, period_key, functional)
                    assert lines_now == -revenue_now, ("P6 rewrite witness", period_key, functional)
                assert closing - opening == billed_now + lines_now, (
                    "P6 net position",
                    period_key,
                    "functional" if functional else "transaction",
                    {
                        "opening": opening,
                        "closing": closing,
                        "billed": billed_now,
                        "role lines net credit": lines_now,
                        "locked": sorted(locked),
                    },
                )
        # FX: every layer movement against the oracle; the presented functional net position
        if self.two_currencies():
            self._fx_checks(run)
            self._the_reach_holds(run)
        self.posted_amounts = self._amounts(*run.outputs, sealed=self.sealed)
        self.reach_facts, self.republished = self._reach_facts(run), []


RevenueMachine.TestCase.settings = platform_props.platform_settings(stateful_step_count=MAX_STEPS)
TestRevenueStateMachine = RevenueMachine.TestCase


def test_billing_then_lock_then_void_keeps_the_booked_line() -> None:
    """Pinned (DG-PROP-02; T1-PRP7-BILLING-VOID-1, Codex production-20260922-0017): one USD
    point-in-time line, price and SSP 100 minor units, no delivery; bill 100 on 1 January; lock
    January; void the billing. The January lock snapshot carries the invoice (net liability 100,
    recognition 0), so the booked line must stay in January and the credit note is booked in the
    earliest postable period — February: opening 100 − 100 = 0 = the recomputed presented
    position. The earlier model dropped the January line and read 100 − 0 = 0 − 0."""
    machine = RevenueMachine()
    machine.currency = "USD"
    machine.oracle = oracle.Oracle(minor_unit=2, inception=INCEPTION)
    line = LineSpec("POB-01", "PIT", 100, 100, 1, 0, 0)
    machine._create_contract([line])
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    machine._record("K-1", line, "BILLING", 0, 100)
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    machine._lock("FY2026-P01")
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    assert machine._net(machine.snapshots["FY2026-P01"], False) == 100
    machine._void(0)
    assert machine.billing_lines == {0: ("FY2026-P01", 100)}, "the locked line stays booked"
    assert machine.billing_reversals == [("FY2026-P02", -100)], "the credit note is booked next"
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    assert machine.oracle.net_position() == 0


# T1-PRP7-VOID-PERIOD-1 — the three rule lines the credit-note period follows, quoted:
#   ENGINE_SPEC S01-R-12: "The target and the void are both removed from `events`; the void never
#     becomes a measure or boundary event. […] [J] Removing both makes the replay equal to a stream
#     in which the voided event never existed; stage 14 posts the difference as target minus posted
#     in the first open period (RCP-06, ALG-09)"
#   ENGINE_SPEC_B S14-R-08: "A voided event or contract changes targets (S01-R-12, S01-R-13); the
#     difference posts as a delta in the first open period with `reason_code = VOID`, posting kind
#     `VOID_REVERSAL` for `CONTRACT_VOIDED`. Posted lines are never updated (REQ-JE-006)"
#   05 RCP-04: "the posting period is the period of the effective date in the posting entity's
#     calendar when that period is `open`, `closing` or `reopened`; when it is `closed` or
#     `permanently_locked`, the first later period whose state is `open`, `closing` or `reopened`,
#     with `origin_period_id` and `reason_code = 'LATE_EVENT'` (ALG-09)"
# None of them reads the void's own date. The engine already behaved so (the pins below observe
# it, unchanged); the machine's ERP model did not.
#
# The falsifying example of the batch-#9 ``make ci`` run (main 8b304854, 2026-09-22; ci profile,
# derandomised): BHD contract of a CLF entity, FIFO / PERIOD_AVERAGE, the drawn 24-month spot path
# and the drawn average / closing percentages of each month's spot. The machine drew those two
# kinds as a percentage of the spot at the time; it draws them freely since ruling R-44 (a), and
# ``_batch9_rate`` keeps the arithmetic for this recorded example only.
_BATCH9_SPOT = tuple(
    Decimal(text)
    for text in (
        "2.0402E-8",
        "2.52741E-7",
        "0.000001713969",
        "4.80E-10",
        "2E-12",
        "0.000054300060",
        "9999.999999999999",
        "17.989412690327",
        "1.546E-9",
        "8.22E-10",
        "274.345939263406",
        "2.09E-10",
        "1.087E-9",
        "0.000001191569",
        "2.261E-9",
        "8.32425E-7",
        "1130.221456921306",
        "1.08900E-7",
        "8.86E-10",
        "0.000208665652",
        "3.265E-9",
        "9.817271869204",
        "5.4303E-8",
        "0.000827854005",
    )
)
_BATCH9_AVERAGE = (
    *(163, 134, 155, 132, 183, 80, 124, 118, 90, 145, 67, 172),
    *(174, 86, 109, 149, 110, 149, 195, 150, 53, 187, 179, 87),
)
_BATCH9_CLOSING = (
    *(141, 123, 125, 86, 119, 163, 74, 59, 145, 174, 139, 100),
    *(148, 72, 137, 180, 84, 104, 75, 87, 58, 144, 182, 192),
)


def _batch9_rate(spot: Decimal, percent: int) -> Decimal:
    """The example's average or closing rate of a month: spot × percent / 100 at 12 decimal
    places, never below the smallest positive rate."""
    value = (spot * Decimal(percent) / Decimal(100)).quantize(Decimal("1E-12"))
    return max(value, Decimal("1E-12"))


def _batch9_world(machine: RevenueMachine, currency: str, functional: str) -> RevenueMachine:
    """The batch-#9 example's steps on ``machine``: two point-in-time lines (217832 / SSP 253 × 1
    and 384 / SSP 2312 × 2); bill 1 minor unit of POB-01 on day 30 (31 January); start the close of
    January and lock it; bill 222 on day 86 (28 March); the invariant after every step — up to,
    not including, the void of the January billing."""
    machine.currency, machine.functional = currency, functional
    machine.oracle = oracle.Oracle(minor_unit=_MINOR_UNIT[currency], inception=INCEPTION)
    if machine.two_currencies():
        machine.fx_policies = {POL_161: "FIFO", POL_162: "PERIOD_AVERAGE"}
        machine._publish_all(
            {
                oracle.SPOT: _BATCH9_SPOT,
                oracle.AVERAGE: [
                    _batch9_rate(_BATCH9_SPOT[n], _BATCH9_AVERAGE[n]) for n in range(MONTHS)
                ],
                oracle.CLOSING: [
                    _batch9_rate(_BATCH9_SPOT[n], _BATCH9_CLOSING[n]) for n in range(MONTHS)
                ],
            }
        )
    first = LineSpec("POB-01", "PIT", 217832, 253, 1, 0, 0)
    second = LineSpec("POB-02", "PIT", 384, 2312, 2, 0, 0)
    machine._create_contract([first, second])
    check = machine.engine_agrees_with_the_oracle_and_the_properties_hold
    check()
    machine.clock = 30
    machine._record("K-1", first, "BILLING", 30, 1)
    check()
    machine.states["FY2026-P01"] = "closing"
    machine.oracle.set_state("FY2026-P01", "closing")
    check()
    machine._lock("FY2026-P01")
    check()
    machine.clock = 86
    machine._record("K-1", first, "BILLING", 86, 222)
    check()
    return machine


@pytest.mark.parametrize(
    ("currency", "functional"),
    [("BHD", "CLF"), ("USD", "USD")],
    ids=["batch-9-example", "single-currency"],
)
def test_a_void_arriving_in_a_later_period_books_the_credit_note_in_the_first_open_period(
    currency: str, functional: str
) -> None:
    """Pinned (DG-PROP-02; T1-PRP7-VOID-PERIOD-1 — the batch-#9 ``make ci`` failure ``('P6 net
    position', 'FY2026-P02', 'transaction', {'opening': 1, 'closing': 0, 'billed': 0, 'role lines
    net credit': 0, …})``): a billing of 1 minor unit sits in locked January; it is voided on 28
    March while February is still open. The replay equals a stream in which the billing never
    existed (ENGINE_SPEC S01-R-12), so February — the first later open period — already closes
    without it, and the difference of a closed period belongs to that period (05 RCP-04, RCP-06;
    ENGINE_SPEC_B S14-R-06, S14-R-08): the credit note is February's, not March's. The landed
    model booked it in the period of the void's arrival day (March) and P6 then read
    (0 − 1) = (0 + 0) for February — a test-model defect: the "one minor unit" was the voided
    billing itself, no FX or rounding loss (the single-currency case fails the same way)."""
    machine = _batch9_world(RevenueMachine(), currency, functional)
    machine._void(0)  # the January billing, voided today — day 86, 28 March
    assert machine.today() == date(2026, 3, 28)
    assert machine.billing_lines == {0: ("FY2026-P01", 1), 1: ("FY2026-P03", 222)}
    assert machine.billing_reversals == [("FY2026-P02", -1)], "the first later open period"
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    # fail-first, kept as the witness: the landed placement — the period of the void's own day —
    # breaks the rollforward of the open period in between, with the batch-#9 message
    landed = copy.deepcopy(machine)
    assert landed._booking_period(landed.clock) == "FY2026-P03"
    landed.billing_reversals = [("FY2026-P03", amount) for _, amount in machine.billing_reversals]
    landed.billing_reversals_fn = [
        ("FY2026-P03", amount) for _, amount in machine.billing_reversals_fn
    ]
    batch_9_message = (
        r"\('P6 net position', 'FY2026-P02', 'transaction', "
        r"\{'opening': 1, 'closing': 0, 'billed': 0, 'role lines net credit': 0, "
    )
    with pytest.raises(AssertionError, match=batch_9_message):
        landed.engine_agrees_with_the_oracle_and_the_properties_hold()


class _EngineBilledMachine(RevenueMachine):
    """The machine's world under POL-004 ``billing.posting = ENGINE``: the engine posts the invoice
    lines itself (JET-03), so where IT places the reversal of a voided billing is observable."""

    def bundle(self):  # type: ignore[no-untyped-def]
        return platform_props.machine_bundle(
            self.spec(),
            voids=tuple(self.voids),
            period_states=dict(self.states) or None,
            posted=self.sealed,
            months=MONTHS,
            functional_currency=self.functional,
            trigger=self.trigger,
            policies={"billing.posting": "ENGINE"},
        )


def test_under_engine_billing_the_engine_posts_that_reversal_in_the_first_open_period() -> None:
    """The document rule behind T1-PRP7-VOID-PERIOD-1, observed on the engine: the same world
    under ``billing.posting = ENGINE``. January's invoice line (Dr ACCOUNTS_RECEIVABLE 1 / Cr
    CONTRACT_LIABILITY 1) is sealed with the lock; after the void on 28 March the engine posts its
    reversal — Dr CONTRACT_LIABILITY 1 / Cr ACCOUNTS_RECEIVABLE 1 — in FEBRUARY with origin
    January (the first later open period: 05 RCP-04; ENGINE_SPEC_B S14-R-06, S14-R-08), not in
    March, and March carries only its own billing of 222. The ERP-mode machine books the ERP's
    credit note in the same period."""
    machine = _EngineBilledMachine()
    machine.currency = machine.functional = "USD"
    machine.oracle = oracle.Oracle(minor_unit=2, inception=INCEPTION)
    first = LineSpec("POB-01", "PIT", 217832, 253, 1, 0, 0)
    machine._create_contract([first, LineSpec("POB-02", "PIT", 384, 2312, 2, 0, 0)])
    machine.clock = 30
    machine._record("K-1", first, "BILLING", 30, 1)
    machine._lock("FY2026-P01")
    sealed = sorted(
        (s.period_key, s.entry_kind, s.account_role, s.amount_txn) for s in machine.sealed
    )
    assert sealed == [
        ("FY2026-P01", "BILLING", "ACCOUNTS_RECEIVABLE", 1),  # debit positive
        ("FY2026-P01", "BILLING", "CONTRACT_LIABILITY", -1),
    ]
    machine.clock = 86
    machine._record("K-1", first, "BILLING", 86, 222)
    machine._void(0)
    assert machine.today() == date(2026, 3, 28)
    run = platform_props.close_run(machine.bundle())
    billing = sorted(
        (
            intent.posting_period_key,
            intent.origin_period_key,
            sorted((line.account_role, line.side, line.amount_txn) for line in intent.lines),
        )
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY)
        if intent.entry_kind == "BILLING"
    )
    assert billing == [
        (
            "FY2026-P02",
            "FY2026-P01",
            [("ACCOUNTS_RECEIVABLE", "C", 1), ("CONTRACT_LIABILITY", "D", 1)],
        ),
        (
            "FY2026-P03",
            None,
            [("ACCOUNTS_RECEIVABLE", "D", 222), ("CONTRACT_LIABILITY", "C", 222)],
        ),
    ]
    reversal = next(
        intent
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY)
        if intent.entry_kind == "BILLING" and intent.origin_period_key == "FY2026-P01"
    )
    assert reversal.reason_code in (LATE_EVENT, VOID)


def _two_currency_machine() -> RevenueMachine:
    """A USD world of a JPY entity with version 1 of the rates published (two-period paths)."""
    machine = RevenueMachine()
    machine.currency, machine.functional = "USD", "JPY"
    machine.oracle = oracle.Oracle(minor_unit=2, inception=INCEPTION)
    machine.fx_policies = {POL_161: "FIFO", POL_162: "PERIOD_AVERAGE"}
    machine._publish_all(
        {
            oracle.SPOT: [Decimal("150.123456789012"), Decimal("148.5")],
            oracle.AVERAGE: [Decimal("149.25"), Decimal("151")],
            oracle.CLOSING: [Decimal("152.75"), Decimal("147.001")],
        }
    )
    return machine


def test_the_fx_checks_fail_against_a_stale_rate_table_and_pass_against_the_published() -> None:
    """Fail-first (DG-PROP-02): a USD → JPY world — a DAILY line 1,200.00 over 12 months and a
    point-in-time line 50.00 × 2; bill 600.00 on day 10, deliver one unit on day 40, bill 300.00
    on day 100 — so the billings are consumed before the term ends and revenue beyond the
    liability creates asset layers remeasured at closing. Against the published table every
    check passes; against a table whose January spot (the first billing layer's rate, S12-R-02)
    or whose closing of a remeasured period (S12-R-09) is stale, the checks FAIL."""
    machine = _two_currency_machine()
    daily = LineSpec("POB-01", "DAILY", 120000, 100, 1, 0, 12)
    pit = LineSpec("POB-02", "PIT", 5000, 50, 2, 0, 0)
    machine._create_contract([daily, pit])
    machine._record("K-1", daily, "BILLING", 10, 60000)
    machine._record("K-1", pit, "DELIVERY", 40, 1)
    machine._record("K-1", daily, "BILLING", 100, 30000)
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    run = platform_props.close_run(machine.bundle())
    machine._fx_checks(run)
    moves = platform_props.layer_movements(run.primary())
    remeasured = next(
        m
        for m in moves
        if m["movement_kind"] == "ASSET_LAYER_REMEASURED" and m["reason"] == "PERIOD_END"
    )
    when = remeasured["effective_date"]
    assert isinstance(when, date)
    closing_index = machine.keys.index(oracle.month_period_key(when))
    spot = machine.rates[(oracle.SPOT, 0)]
    machine.rates[(oracle.SPOT, 0)] = spot + Decimal("1")
    with pytest.raises(AssertionError, match="S12-R-02 spot"):
        machine._fx_checks(run)
    machine.rates[(oracle.SPOT, 0)] = spot
    closing = machine.rates[(oracle.CLOSING, closing_index)]
    machine.rates[(oracle.CLOSING, closing_index)] = closing + Decimal("1")
    with pytest.raises(AssertionError, match="S12-R-09 closing"):
        machine._fx_checks(run)
    machine.rates[(oracle.CLOSING, closing_index)] = closing
    machine._fx_checks(run)


def test_republishing_the_average_rate_of_a_locked_period_redirects_the_functional_delta() -> None:
    """A USD → JPY DAILY line 1,200.00 over 12 months billed 10.00 on 1 January: January's revenue
    exceeds the liability, so an asset layer is created at January's average (S12-R-06). Lock
    January, then republish January's ``average`` as a new version (RCP-17 pins the highest
    APPROVED version). The recompute under ``FX_REPUBLISH`` posts the functional difference into
    February with origin January and reason ``LATE_EVENT`` (S12-R-13; S14-R-05, S14-R-06) — zero
    transaction amount, functional only — January's sealed lines stay, and every invariant
    holds."""
    machine = _two_currency_machine()
    daily = LineSpec("POB-01", "DAILY", 120000, 100, 1, 0, 12)
    machine._create_contract([daily])
    machine._record("K-1", daily, "BILLING", 0, 1000)
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    machine.clock = 40
    machine._lock("FY2026-P01")
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    average = machine.rates[(oracle.AVERAGE, 0)]
    machine._publish([oracle.AVERAGE], 0, [average * 2])
    assert machine.trigger == "FX_REPUBLISH"
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    run = platform_props.close_run(machine.bundle())
    assert run.bundle.trigger == "FX_REPUBLISH"
    intents = [intent for _, _, intent in platform_props.intents(run, platform_props.PRIMARY)]
    assert all(intent.posting_period_key != "FY2026-P01" for intent in intents)
    redirected = [
        intent
        for intent in intents
        if intent.origin_period_key == "FY2026-P01" and intent.posting_period_key == "FY2026-P02"
    ]
    assert redirected and all(intent.reason_code == LATE_EVENT for intent in redirected)
    assert any(
        line.amount_txn == 0 and line.amount_functional != 0
        for intent in redirected
        for line in intent.lines
    )


def test_the_p6_rewrite_equals_the_landed_form_in_single_currency_worlds() -> None:
    """Witness for the P6 rewrite (a landed invariant changed): in a single-currency world the
    engine's lines to the three balance roles are the revenue relief and the netting reclass (which
    nets to zero), so Σ (credit − debit) of those lines equals −Σ REVENUE credits in every period —
    the landed ``billed − revenue`` form and the rewritten ``billed + role lines`` form are one
    identity term by term. A USD world: a DAILY line 1,200.00 over 12 months and a point-in-time
    line 50.00 × 2; billings on days 3 and 25, a delivery on day 20, January locked, a billing on
    day 45 and the void of the locked January billing (a February credit note); every period of
    the horizon, both currency columns (equal in a single currency)."""
    machine = RevenueMachine()
    machine.currency = machine.functional = "USD"
    machine.oracle = oracle.Oracle(minor_unit=2, inception=INCEPTION)
    daily = LineSpec("POB-01", "DAILY", 120000, 100, 1, 0, 12)
    pit = LineSpec("POB-02", "PIT", 5000, 50, 2, 0, 0)
    machine._create_contract([daily, pit])
    machine._record("K-1", daily, "BILLING", 3, 40000)
    machine._record("K-1", pit, "DELIVERY", 20, 1)
    machine._record("K-1", pit, "BILLING", 25, 2500)
    machine.clock = 45
    machine._lock("FY2026-P01")
    machine._record("K-1", daily, "BILLING", 45, 20000)
    machine._void(2)
    assert machine.billing_reversals == [("FY2026-P02", -2500)]
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    run = platform_props.close_run(machine.bundle())
    for period in machine.keys:
        for functional in (False, True):
            lines = machine._role_lines_net_credit(run, period, functional)
            revenue = machine._revenue_posted(run, period, functional)
            assert lines == -revenue, (period, functional, lines, revenue)


def _vc_probe_world() -> RevenueMachine:
    """Two USD contracts — K-1: DAILY 1,200.00 over 12 months + a point-in-time line 50.00 × 2
    with a variable-consideration element (v1: scenarios 100.00 @ 0.60 / 300.00 @ 0.40, U 180.00,
    most conservative 100.00, K 150.00); K-2: DAILY 600.00 over 6 months — billed 600.00 on day
    10, one unit delivered on day 40."""
    machine = RevenueMachine()
    machine.currency = machine.functional = "USD"
    machine.oracle = oracle.Oracle(minor_unit=2, inception=INCEPTION)
    daily = LineSpec("POB-01", "DAILY", 120000, 100, 1, 0, 12)
    pit = LineSpec("POB-02", "PIT", 5000, 50, 2, 0, 0)
    machine._create_contract([daily, pit], ([(10000, 60), (30000, 40)], 10000, 15000))
    machine._create_contract([LineSpec("POB-01", "DAILY", 60000, 100, 1, 0, 6)])
    machine._record("K-1", daily, "BILLING", 10, 60000)
    machine._record("K-1", pit, "DELIVERY", 40, 1)
    return machine


def test_a_variable_consideration_change_reallocates_per_s08_r07_not_by_the_naive_form() -> None:
    """Fail-first (DG-PROP-02): version 2 of K-1's element on day 75 (U 260.00, K 240.00; ΔTP
    +90.00) routes the change over K-1's obligations only and re-apportions the new price over the
    exact quotas of the whole group (S08-R-07): the engine allocates 711.67 / 711.67 / 666.66,
    which equals the oracle and DIFFERS from a naive relative-SSP apportionment of the new price
    (696.67 / 696.67 / 696.66) — the naive form fails against the engine."""
    machine = _vc_probe_world()
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    machine.clock = 75
    machine._add_vc_version("K-1", 75, ([(10000, 20), (30000, 80)], 10000, 24000))
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    run = platform_props.close_run(machine.bundle())
    book = run.primary()
    allocated = {v.subject_key: v.columns["allocated_amount"] for v in book.obligation_versions}
    assert allocated == {"K-1/POB-01": 71167, "K-1/POB-02": 71167, "K-2/POB-01": 66666}
    assert allocated == machine.oracle.allocation()
    naive = oracle.largest_remainder(
        machine.oracle.total_posted(), {line.subject: line.weight for line in machine.oracle.lines}
    )
    assert naive == {"K-1/POB-01": 69667, "K-1/POB-02": 69667, "K-2/POB-01": 69666}
    with pytest.raises(AssertionError):
        assert allocated == naive
    columns = book.contract_version.columns
    assert columns["transaction_price"] == 209000 == machine.oracle.total_posted()
    assert columns["vc_constrained_amount"] == 24000
    assert columns["vc_excluded_amount"] == 2000  # U 260.00 − K 240.00


def test_a_late_variable_consideration_version_posts_its_catch_up_as_a_late_event() -> None:
    """K-1's element re-estimated (K 150.00 → 240.00) effective 20 January, approved in March
    after January was locked: the re-allocation and its catch-up post in February with origin
    January and reason LATE_EVENT (S08-R-01 / S14-R-06), nothing posts into January, and every
    invariant holds."""
    machine = _vc_probe_world()
    machine.clock = 70
    machine._lock("FY2026-P01")
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    machine._add_vc_version("K-1", 19, ([(10000, 20), (30000, 80)], 10000, 24000))
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    run = platform_props.close_run(machine.bundle())
    intents = [intent for _, _, intent in platform_props.intents(run, platform_props.PRIMARY)]
    assert all(intent.posting_period_key != "FY2026-P01" for intent in intents)
    redirected = [
        intent
        for intent in intents
        if intent.origin_period_key == "FY2026-P01" and intent.posting_period_key == "FY2026-P02"
    ]
    assert redirected and all(intent.reason_code == LATE_EVENT for intent in redirected)
    assert any(line.amount_txn != 0 for intent in redirected for line in intent.lines)

"""Stage 14 functional amounts, entries, accounts and keys.

ENGINE_SPEC_B §14.2.3 (S14-R-10, S14-R-11), §14.2.4 (S14-R-12 to S14-R-15), §14.4 (S14-INV-01,
S14-INV-04, S14-INV-05, S14-INV-09), §14.8 EX-14-A; POLICIES §0.8, §2.3 JET R3 and §6.3 (mapping
preset; CHK-010, CHK-022); dev-guide §5.17; D-16; REQ-JE-002, REQ-FX-006. Stages 10 and 11 are
built in lane L2-4, so the tests pass a fake consumed state carrying ``PartInputs`` and fake
producer nodes (D-81 integration after merge; L2-5-Q-24); stages 01 to 05 fold the golden
contracts, stage 12 runs for real, and every trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    AccountMappingInput,
    FxRateInput,
    InputBundle,
    MappingRuleInput,
    PostedAmountInput,
)
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.dates import month_end
from erev_engine.enums import AccountRole, BookCode, PrincipalAgent
from erev_engine.errors import EngineError
from erev_engine.money import format_money, largest_remainder
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
    s12_fx_entities,
    s14_posting,
)
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows
from erev_engine.stages.s14_posting import ACCOUNT_MAPPING_MISSING, PartInputs, PostingState
from erev_engine.stages.s14_posting.assign import subject_contracts
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    Finding,
    ObligationState,
    PolicyResolver,
    PostedIndex,
    RateIndex,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, reevaluate
from support import bundles, golden_streams
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
UK = "UK01"
CL, REVENUE, AP = "CONTRACT_LIABILITY", "REVENUE", "BILLING_CLEARING"
AGENT_SUBJECT = "TKT-001/POB-01"
LINE_KEY_VECTOR = "83300736c63604193d4d84963e7a4730332dce8962cf245e22f2b15cb5e99b0a"
PURPOSES = ("AP_SUPPLIER", "BILLING", "EQUITY", "INVENTORY", "INVESTMENTS", "UNAPPLIED_CASH")


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stages 12 and 14 read it (L2-5-Q-10, L2-5-Q-24)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


def _period(month: int, year: int = 2026) -> str:
    return f"FY{year}-P{month:02d}"


def _target(
    measure: str,
    subject: str,
    period_key: str,
    value: int,
    *,
    cause: str | None = None,
    entity: str = ENTITY,
) -> Target:
    node = f"{measure}:{subject}" + ("" if cause is None else f"#{cause}") + f":{period_key}"
    return Target(BookCode.ASC606, entity, subject, measure, period_key, cause, value, None, node)


def _relief(subject: str, values: Mapping[str, int]) -> tuple[Target, ...]:
    return tuple(
        _target("revenue_relief_cum", subject, key, value) for key, value in values.items()
    )


def _emit(tb: TraceBuilder, targets: Iterable[Target], currency: str) -> None:
    """Fake producer nodes of stages 09 to 11 (D-81 integration after merge)."""
    mu = bundles.currencies(currency)[currency].minor_unit
    for target in targets:
        measure, subject, period_key = target.node_id.rsplit(":", 2)
        detail = {"value": format_money(target.value, mu)}
        tb.node(
            measure=measure,
            subject_key=subject,
            period_key=period_key,
            value=target.value,
            currency=currency,
            minor_unit=mu,
            formula_id="rec.catch_up.sum.v1",
            inputs=[SourceRef("source_record", target.node_id, detail)],
            narrative_key="rec.catch_up.sum",
        )


def _mapping(
    version_key: str = "MAP-ALL@v1", *, drop: Iterable[tuple[str, str | None]] = ()
) -> AccountMappingInput:
    """A chart with one rule per E-01 role (and per E-109 purpose on ``BILLING_CLEARING``)."""
    dropped = set(drop)
    rules = []
    for index, role in enumerate(sorted(AccountRole)):
        if role in ("RETAINED_EARNINGS", "FINANCING_OBLIGATION"):
            continue
        purposes = PURPOSES if role == AP else (None,)
        for offset, purpose in enumerate(purposes):
            if (role, purpose) in dropped:
                continue
            code = str(1000 + 10 * index + offset)
            rules.append(MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0))
    return AccountMappingInput(version_key, bundles.ZERO_SHA256, tuple(rules))


def _code(role: str, purpose: str | None = None) -> str:
    return next(
        rule.account_code
        for rule in _mapping().rules
        if (rule.account_role, rule.clearing_purpose) == (role, purpose)
    )


def _compute(
    ctx: BookContext,
    allocated: AllocatedState,
    inputs: PartInputs,
    *,
    flows: Iterable[ControlFlow] = (),
    rates: Iterable[FxRateInput] = (),
    posted: Iterable[PostedAmountInput] = (),
    pass_name: str | None = None,
) -> tuple[PostingState, Trace]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    _emit(
        tb,
        (*inputs.relief, *inputs.reclass, *inputs.invoices, *inputs.refund_liabilities),
        ctx.txn_currency,
    )
    costs = _Costs(allocated, FxFlows(tuple(flows)), inputs)
    fx = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(tuple(rates)))
    posting = s14_posting.run(ctx, fx, tb, posted=PostedIndex(tuple(posted)), pass_name=pass_name)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return posting, trace


def _posted(*states: PostingState) -> tuple[PostedAmountInput, ...]:
    """The posted amounts after sealing every intent of ``states`` (RCP-05)."""
    items = [
        PostedAmountInput(
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
            amount_txn=line.amount_txn if line.side == "D" else -line.amount_txn,
            amount_functional=(
                line.amount_functional if line.side == "D" else -line.amount_functional
            ),
        )
        for state in states
        for intent in state.posting_intents
        for line in intent.lines
    ]
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.subject_key,
                item.entry_kind,
                item.account_role,
                item.clearing_purpose or "",
                item.period_key,
                item.origin_period_key or "",
                item.posting_class,
            ),
        )
    )


def _entries(state: PostingState) -> list[tuple[object, ...]]:
    return [
        (
            intent.posting_period_key,
            intent.origin_period_key,
            intent.reason_code,
            [
                (line.side, line.account_role, line.clearing_purpose, line.amount_txn)
                for line in intent.lines
            ],
        )
        for intent in state.posting_intents
    ]


def _balanced(state: PostingState) -> None:
    """S14-INV-01: debits equal credits per entry in both currencies."""
    for intent in state.posting_intents:
        debit = [line for line in intent.lines if line.side == "D"]
        credit = [line for line in intent.lines if line.side == "C"]
        assert sum(line.amount_txn for line in debit) == sum(line.amount_txn for line in credit)
        assert sum(line.amount_functional for line in debit) == sum(
            line.amount_functional for line in credit
        )
        assert all(line.amount_txn >= 0 and line.amount_functional >= 0 for line in intent.lines)


def _agent_obligation() -> ObligationState:
    seg = segment(
        Fraction(1000),
        usd("1000.00"),
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        quantity=Fraction(3),
        measure="UNITS_DELIVERED",
    )
    ob = obligation(
        "POB-01",
        [seg],
        contract_key="TKT-001",
        method="UNITS_DELIVERED",
        convention=None,
        start=date(2026, 1, 1),
        quantity=Fraction(3),
    )
    basis = {"gross_to_net_basis": "COMMISSION_RATE", "rate": "0.15"}
    return dataclasses.replace(ob, principal_agent=PrincipalAgent.AGENT, gross_to_net=basis)


def _ex_14_a() -> tuple[PostingState, PostingState]:
    allocated = allocated_state([_agent_obligation()])
    mapping = _mapping()
    january = dataclasses.replace(
        book_context(bundles.entity(months=3), horizon=_period(1)), mapping=mapping
    )
    unit_1 = PartInputs(relief=_relief(AGENT_SUBJECT, {_period(1): 33333}))
    first, _ = _compute(january, allocated, unit_1)
    # Unit 2 effective 28 February, recorded 5 March after February was locked; unit 3 on 20 March.
    march = dataclasses.replace(
        book_context(bundles.entity(months=3, states={_period(1): "closed", _period(2): "closed"})),
        mapping=mapping,
    )
    units = PartInputs(
        relief=_relief(AGENT_SUBJECT, {_period(1): 33333, _period(2): 66667, _period(3): 100000})
    )
    second, _ = _compute(march, allocated, units, posted=_posted(first))
    return first, second


def test_ex_14_a_agent_split_and_late_carry() -> None:
    # Cumulative gross 333.33 / 666.67 / 1,000.00 split 3 : 17 by largest remainder.
    assert [
        largest_remainder(gross, [Fraction(3), Fraction(17)], [REVENUE, "AP"])
        for gross in (33333, 66667, 100000)
    ] == [[5000, 28333], [10000, 56667], [15000, 85000]]
    first, second = _ex_14_a()
    purpose = "AP_SUPPLIER"
    assert _entries(first) == [
        (
            _period(1),
            None,
            None,
            [("D", CL, None, 33333), ("C", AP, purpose, 28333), ("C", REVENUE, None, 5000)],
        )
    ]
    assert sorted(_entries(second), key=lambda row: str(row[1])) == [
        (
            _period(3),
            _period(2),
            "LATE_EVENT",
            [("D", CL, None, 33334), ("C", AP, purpose, 28334), ("C", REVENUE, None, 5000)],
        ),
        (
            _period(3),
            None,
            None,
            [("D", CL, None, 33333), ("C", AP, purpose, 28333), ("C", REVENUE, None, 5000)],
        ),
    ]
    # The two March entries are distinct because their origin periods differ (S14-R-12).
    assert len({intent.entry_key for intent in second.posting_intents}) == 2
    assert [intent.entry_key for intent in second.posting_intents] == sorted(
        intent.entry_key for intent in second.posting_intents
    )
    _balanced(first)
    _balanced(second)
    accounts = {
        (line.account_role, line.clearing_purpose): line.account_code
        for intent in second.posting_intents
        for line in intent.lines
    }
    assert accounts == {
        (CL, None): _code(CL),
        (AP, purpose): _code(AP, purpose),
        (REVENUE, None): _code(REVENUE),
    }
    carry = next(intent for intent in second.posting_intents if intent.origin_period_key)
    assert second.effective_dates[carry.entry_key] == date(2026, 2, 28)
    assert {line.dimensions["obligation_key"] for line in carry.lines} == {"POB-01"}


def test_s14_r15_line_key_test_vector() -> None:
    _, second = _ex_14_a()
    carry = next(intent for intent in second.posting_intents if intent.origin_period_key)
    line = next(line for line in carry.lines if line.account_role == CL)
    expected = (
        '{"account_role":"CONTRACT_LIABILITY","book_code":"ASC606","clearing_purpose":null,'
        '"counterparty_entity":null,"entity":"US01","entry_kind":"REVENUE_RECOGNITION",'
        '"origin_period_key":"FY2026-P02","posting_class":"EVENT","posting_period_key":"FY2026-P03",'
        '"subject_key":"TKT-001/POB-01"}'
    )
    members = {
        "account_role": line.account_role,
        "book_code": carry.book_code,
        "clearing_purpose": line.clearing_purpose,
        "counterparty_entity": line.counterparty_entity,
        "entity": carry.entity,
        "entry_kind": carry.entry_kind,
        "origin_period_key": carry.origin_period_key,
        "posting_class": carry.posting_class,
        "posting_period_key": carry.posting_period_key,
        "subject_key": carry.subject_key,
    }
    assert canonical_bytes(members).decode() == expected
    assert line.line_key == LINE_KEY_VECTOR
    # entry_key covers the entry members, reason code included.
    delta = next(d for d in second.deltas if d.origin_period_key and d.key.account_role == CL)
    assert carry.entry_key == s14_posting.entry_key(delta)
    # S14-R-15: the functional line of an opposed delta (S14-R-10) adds ``currency_leg``; its
    # transaction line and every other line keep the ten-member object. A reason-variant line
    # (S14-R-27) keeps its ``reason_code`` member beside it.
    assert s14_posting.line_key(delta) == LINE_KEY_VECTOR
    assert s14_posting.line_key(delta, functional_leg=True) == sha256_hex(
        {**members, "currency_leg": "FUNCTIONAL"}
    )
    tagged = dataclasses.replace(delta, reason_code="CLAWBACK")
    assert s14_posting.line_key(tagged, functional_leg=True) == sha256_hex(
        {**members, "currency_leg": "FUNCTIONAL", "reason_code": "CLAWBACK"}
    )
    assert (
        len(
            {
                LINE_KEY_VECTOR,
                s14_posting.line_key(delta, functional_leg=True),
                s14_posting.line_key(tagged),
                s14_posting.line_key(tagged, functional_leg=True),
            }
        )
        == 4
    )


def _rate(kind: str, month: int, rate: str) -> FxRateInput:
    period_key = _period(month)
    first = date(2026, month, 1)
    key = f"EURUSD-{kind.upper()}-{period_key}"
    return FxRateInput(
        key, "EURUSD@v1", kind, "EUR", "USD", month_end(first), period_key, Decimal(rate)
    )


def _release(subject: str, month: int, amount: str, entity: str = ENTITY) -> ControlFlow:
    on = month_end(date(2026, month, 1))
    key = f"{subject}@{_period(month)}"
    return ControlFlow("REVENUE", entity, subject, key, on, None, usd(amount))


def _foreign_context(months: int = 2) -> BookContext:
    ctx = book_context(bundles.entity(months=months), currency="EUR")
    return dataclasses.replace(ctx, currencies=bundles.currencies("EUR", "USD"), mapping=_mapping())


@dataclass(frozen=True, slots=True)
class _ForeignWorld:
    """An agent obligation A (EUR 1,000.00 in January; three roles) and a principal obligation P
    (EUR 333.33 and 666.67) of a USD entity, with the rates of January and February."""

    ctx: BookContext
    allocated: AllocatedState
    inputs: PartInputs
    flows: tuple[ControlFlow, ...]
    rates: tuple[FxRateInput, ...]
    agent: str
    principal: str

    def compute(self, posted: Iterable[PostedAmountInput] = ()) -> PostingState:
        state, _ = _compute(
            self.ctx, self.allocated, self.inputs, flows=self.flows, rates=self.rates, posted=posted
        )
        return state


def _foreign_world() -> _ForeignWorld:
    agent = dataclasses.replace(
        _agent_obligation(),
        subject_key=f"{CONTRACT_KEY}/A",
        contract_key=CONTRACT_KEY,
        obligation_key="A",
    )
    principal = obligation(
        "P",
        [segment(Fraction(2000), usd("2000.00"), start=date(2026, 1, 1), end=date(2026, 2, 28))],
        start=date(2026, 1, 1),
        end=date(2026, 2, 28),
    )
    a, p = agent.subject_key, principal.subject_key
    return _ForeignWorld(
        ctx=_foreign_context(),
        allocated=allocated_state([agent, principal]),
        inputs=PartInputs(
            relief=(
                *_relief(a, {_period(1): 100000, _period(2): 100000}),
                *_relief(p, {_period(1): 33333, _period(2): 100000}),
            )
        ),
        flows=(_release(a, 1, "1000.00"), _release(p, 1, "333.33"), _release(p, 2, "666.67")),
        rates=(
            _rate("average", 1, "1.1100"),
            _rate("average", 2, "1.1300"),
            _rate("closing", 1, "1.1200"),
            _rate("closing", 2, "1.1400"),
        ),
        agent=a,
        principal=p,
    )


def test_s14_r10_pairs_from_one_amount() -> None:
    world = _foreign_world()
    a, p = world.agent, world.principal
    state = world.compute()
    _balanced(state)
    lines = {
        (intent.posting_period_key, intent.subject_key, line.account_role): line
        for intent in state.posting_intents
        for line in intent.lines
    }
    # EUR 1,000.00 at 1.1100 = USD 1,110.00: one functional amount, the credits apportioned with
    # largest_remainder over the transaction split 150.00 : 850.00 (S14-R-10; D-16).
    debit = lines[(_period(1), a, CL)]
    revenue, supplier = lines[(_period(1), a, REVENUE)], lines[(_period(1), a, AP)]
    assert (debit.amount_txn, debit.amount_functional) == (100000, 111000)
    assert (revenue.amount_txn, supplier.amount_txn) == (15000, 85000)
    assert [revenue.amount_functional, supplier.amount_functional] == largest_remainder(
        111000, [Fraction(15000), Fraction(85000)], [REVENUE, "AP"]
    )
    # A principal pair takes one amount on both sides in each currency.
    for month in (1, 2):
        cl, rev = lines[(_period(month), p, CL)], lines[(_period(month), p, REVENUE)]
        assert (cl.amount_txn, cl.amount_functional) == (rev.amount_txn, rev.amount_functional)
    assert lines[(_period(2), p, CL)].amount_functional == 75334  # 666.67 × 1.1300 = 753.34


def test_s14_r10_opposed_deltas_post_a_transaction_line_and_a_functional_line() -> None:
    """S14-R-10 and S14-INV-09 in an entry of three roles (supervisor ruling R-44 (a)). The agent
    entry of January is posted, and the posted amounts then stand so that the January deltas are
    CONTRACT_LIABILITY +10.00 EUR / −5.00 USD and REVENUE −8.50 EUR / +7.00 USD — the two amounts
    of each differ in sign — and the supplier clearing −1.50 EUR / −2.00 USD, which agree. The two
    opposed roles post a transaction line and a functional line each, the third its one line;
    debits come first, then the roles; the entry balances in each currency; every line has its own
    key and names the rates of its role target."""
    world = _foreign_world()
    a = world.agent
    deltas = {CL: (1000, -500), REVENUE: (-850, 700), AP: (-150, -200)}
    assert [sum(amounts) for amounts in zip(*deltas.values(), strict=True)] == [0, 0]
    posted = tuple(
        dataclasses.replace(
            item,
            amount_txn=item.amount_txn - deltas[item.account_role][0],
            amount_functional=item.amount_functional - deltas[item.account_role][1],
        )
        if (item.subject_key, item.period_key) == (a, _period(1))
        else item
        for item in _posted(world.compute())
    )
    state = world.compute(posted)
    _balanced(state)
    (entry,) = state.posting_intents
    assert (entry.subject_key, entry.posting_period_key, entry.origin_period_key) == (
        a,
        _period(1),
        None,
    )
    assert [
        (line.side, line.account_role, line.amount_txn, line.amount_functional)
        for line in entry.lines
    ] == [
        ("D", CL, 1000, 0),
        ("D", REVENUE, 0, 700),
        ("C", AP, 150, 200),
        ("C", CL, 0, 500),
        ("C", REVENUE, 850, 0),
    ]
    keys = [line.line_key for line in entry.lines]
    assert len(set(keys)) == 5
    assert all(state.line_rates[key] for key in keys)
    by_role = {delta.key.account_role: delta for delta in state.deltas}
    assert keys == [
        s14_posting.line_key(by_role[CL]),
        s14_posting.line_key(by_role[REVENUE], functional_leg=True),
        s14_posting.line_key(by_role[AP]),
        s14_posting.line_key(by_role[CL], functional_leg=True),
        s14_posting.line_key(by_role[REVENUE]),
    ]
    # S14-INV-02: the recompute over these five lines posts nothing.
    merged: dict[tuple[str, ...], PostedAmountInput] = {}
    for item in (*posted, *_posted(state)):
        grain = (item.subject_key, item.account_role, item.clearing_purpose or "", item.period_key)
        found = merged.get(grain)
        merged[grain] = (
            item
            if found is None
            else dataclasses.replace(
                found,
                amount_txn=found.amount_txn + item.amount_txn,
                amount_functional=found.amount_functional + item.amount_functional,
            )
        )
    assert world.compute(tuple(merged[grain] for grain in sorted(merged))).posting_intents == ()


def test_s14_r11_engine_never_emits_rounding() -> None:
    first, second = _ex_14_a()
    for state in (first, second):
        assert {line.account_role for intent in state.posting_intents for line in intent.lines}
        assert all(
            line.account_role != "ROUNDING" and intent.entry_kind != "FX_ROUNDING"
            for intent in state.posting_intents
            for line in intent.lines
        )
    # A posted ROUNDING amount on an engine role key is a platform artefact the engine refuses.
    rounding = PostedAmountInput(
        "ASC606", ENTITY, AGENT_SUBJECT, "REVENUE_RECOGNITION", "ROUNDING", None, None,
        _period(1), None, "EVENT", "USD", "USD", 1, 1,
    )  # fmt: skip
    allocated = allocated_state([_agent_obligation()])
    ctx = dataclasses.replace(book_context(bundles.entity(months=1)), mapping=_mapping())
    with pytest.raises(EngineError) as refused:
        _compute(ctx, allocated, PartInputs(), posted=[rounding])
    assert refused.value.detail["invariant"] == "S14-INV-05"


def _context(calendars: Sequence[bundles.EntityInput]) -> BookContext:
    """One book over several entities with every calendar and PERIOD policy value (CV-17)."""
    ctx = book_context(calendars[0])
    resolved = {(p.code, p.scope, p.subject_key): p for p in ctx.policies.all()}
    for calendar in calendars[1:]:
        for policy in bundles.policy_set(entity=calendar):
            resolved.setdefault((policy.code, policy.scope, policy.subject_key), policy)
    return dataclasses.replace(
        ctx,
        entities={calendar.code: calendar for calendar in calendars},
        horizon={calendar.code: calendar.periods[-1].period_key for calendar in calendars},
        policies=PolicyResolver(tuple(resolved[key] for key in sorted(resolved))),
        mapping=_mapping(),
    )


def test_s14_r13_dimensions() -> None:
    ctx = _context([bundles.entity(ENTITY, months=2), bundles.entity(UK, months=2)])
    licence = dataclasses.replace(
        obligation(
            "L1",
            [segment(Fraction(600), usd("600.00"), start=date(2026, 1, 1), end=date(2026, 1, 31))],
        ),
        product_code=None,
        revenue_category="LICENCE",
    )
    services = dataclasses.replace(
        obligation(
            "S2",
            [segment(Fraction(400), usd("400.00"), start=date(2026, 1, 1), end=date(2026, 2, 28))],
        ),
        performing_entity=UK,
    )
    agent = dataclasses.replace(
        _agent_obligation(),
        subject_key=f"{CONTRACT_KEY}/A3",
        contract_key=CONTRACT_KEY,
        obligation_key="A3",
    )
    allocated = allocated_state([licence, services, agent])
    flows = [
        _release(services.subject_key, 1, "200.00"),
        _release(services.subject_key, 2, "200.00"),
    ]
    inputs = PartInputs(
        relief=(
            *_relief(licence.subject_key, {_period(1): 60000}),
            *_relief(services.subject_key, {_period(1): 20000, _period(2): 40000}),
            *_relief(agent.subject_key, {_period(2): 10000}),
        ),
        reclass=(
            _target(
                "netting_reclass_amount",
                licence.subject_key,
                _period(1),
                60000,
                cause="UNBILLED_RECEIVABLE",
            ),
        ),
    )
    command, _ = _compute(ctx, allocated, inputs, flows=flows)
    reclass, _ = _compute(
        dataclasses.replace(ctx, trigger="CLOSE_RELEASE"),
        allocated,
        inputs,
        flows=flows,
        pass_name="NETTING_RECLASS",
    )
    obligations = {ob.subject_key: ob for ob in allocated.obligations}
    roles: set[tuple[str, str]] = set()
    for state in (command, reclass):
        _balanced(state)
        for intent in state.posting_intents:
            for line in intent.lines:
                roles.add((intent.entity, line.account_role))
                assert line.dimensions["contract"] == allocated.group_code
                ob = obligations[intent.subject_key]
                assert line.dimensions["obligation_key"] == ob.obligation_key
                assert line.dimensions["contract_key"] == ob.contract_key
                assert {"product", "revenue_category"} & set(line.dimensions)
                intercompany = line.account_role in ("INTERCOMPANY_DUE_TO", "INTERCOMPANY_DUE_FROM")
                assert (line.counterparty_entity is not None) == intercompany
                if intercompany:
                    assert line.counterparty_entity == ({ENTITY, UK} - {intent.entity}).pop()
                assert (line.clearing_purpose is not None) == (line.account_role == AP)
    assert roles >= {
        (ENTITY, CL),
        (ENTITY, "INTERCOMPANY_DUE_TO"),
        (UK, "INTERCOMPANY_DUE_FROM"),
        (UK, REVENUE),
        (ENTITY, AP),
        (ENTITY, "UNBILLED_RECEIVABLE"),
    }
    licence_line = next(
        line
        for intent in command.posting_intents
        if intent.subject_key == licence.subject_key
        for line in intent.lines
    )
    assert (licence_line.dimensions["revenue_category"], "product" in licence_line.dimensions) == (
        "LICENCE",
        False,
    )


def _two_member_group() -> AllocatedState:
    """Members C-A and C-B of group G, one January obligation each (D-90d L9-RUN-Q-4)."""
    seg = segment(Fraction(600), usd("600.00"), start=date(2026, 1, 1), end=date(2026, 1, 31))
    members = [obligation("POB-001", [seg], contract_key=key) for key in ("C-A", "C-B")]
    return dataclasses.replace(allocated_state(members), group_code="G")


def test_l9_run_q4_subject_contracts_name_the_component_contract_of_a_multi_member_group() -> None:
    """``assign.subject_contracts`` resolves a stage 10 component key
    ``<group>@<entity>/<KIND>/<source>`` to the owning member through its source before the
    every-member fallback (D-90d L9-RUN-Q-4); group-level and unknown-source keys, obligation and
    contract subjects, and singleton groups are unchanged."""
    st = _two_member_group()
    cases = {
        f"G@{ENTITY}/RETURN/C-B/POB-001": ("C-B",),
        f"G@{ENTITY}/CONCESSION/C-B/EV-000003/C-B/POB-001": ("C-B",),
        f"G@{ENTITY}/TERMINATION/C-A/EV-000002": ("C-A",),
        f"G@{ENTITY}/VARIABLE_CONSIDERATION/C-A/VC-1": ("C-A",),
        f"G@{ENTITY}": ("C-A", "C-B"),  # FX_REMEASUREMENT stays unattributed (L9-RUN-Q-9)
        f"G@{ENTITY}/RETURN/C-Z/POB-009": ("C-A", "C-B"),
        f"G@{ENTITY}/RETURN": ("C-A", "C-B"),
        f"G@{ENTITY}/LAYER/C-B/POB-001": ("C-A", "C-B"),  # not a component kind
        "C-A/POB-001": ("C-A",),
        f"C-B@{ENTITY}": ("C-B",),
    }
    assert {key: subject_contracts(st, key) for key in cases} == cases
    # An encoded group head (CV-21; L9-RUN-Q-3) parses the same way.
    encoded = dataclasses.replace(st, group_code="G/1")
    assert subject_contracts(encoded, f"G%2F1@{ENTITY}/RETURN/C-B/POB-001") == ("C-B",)
    assert subject_contracts(encoded, f"G/1@{ENTITY}/RETURN/C-B/POB-001") == ("C-A", "C-B")
    january = segment(Fraction(600), usd("600.00"), start=date(2026, 1, 1), end=date(2026, 1, 31))
    singleton = allocated_state([obligation("P1", [january])])
    assert subject_contracts(singleton, f"CG-1@{ENTITY}/RETURN/{CONTRACT_KEY}/P1") == (
        CONTRACT_KEY,
    )
    assert subject_contracts(singleton, f"CG-1@{ENTITY}") == (CONTRACT_KEY,)


def test_l9_run_q4_multi_member_refund_component_lines_carry_contract_key() -> None:
    """JET-04b lines of a two-member group's RETURN component carry the owning member as
    ``contract_key`` and its product (S14-R-13; D-90d L9-RUN-Q-4); before the fix
    ``subject_contracts`` named both members, so the lines carried neither."""
    ctx = dataclasses.replace(book_context(bundles.entity(months=1)), mapping=_mapping())
    st = _two_member_group()
    a, b = (ob.subject_key for ob in st.obligations)
    component = f"G@{ENTITY}/RETURN/{b}"
    inputs = PartInputs(
        relief=(*_relief(a, {_period(1): 60000}), *_relief(b, {_period(1): 58000})),
        refund_liabilities=(
            _target("refund_liability", component, _period(1), 2000, cause="RETURN"),
        ),
    )
    state, _ = _compute(ctx, st, inputs)
    _balanced(state)
    (jet_04b,) = [intent for intent in state.posting_intents if intent.subject_key == component]
    assert {(line.side, line.account_role, line.amount_txn) for line in jet_04b.lines} == {
        ("C", "REFUND_LIABILITY", 2000),
        ("D", CL, 2000),
    }
    for line in jet_04b.lines:
        assert (
            line.dimensions["contract"],
            line.dimensions["contract_key"],
            line.dimensions["product"],
            "obligation_key" in line.dimensions,
        ) == ("G", "C-B", "SKU-1", False)
    # The obligation subjects keep their own member.
    by_subject = {intent.subject_key: intent for intent in state.posting_intents}
    assert {line.dimensions["contract_key"] for line in by_subject[a].lines} == {"C-A"}
    assert {line.dimensions["contract_key"] for line in by_subject[b].lines} == {"C-B"}


def test_s14_r14_account_mapping_missing() -> None:
    p1 = f"{CONTRACT_KEY}/P1"
    principal = obligation(
        "P1", [segment(Fraction(500), usd("500.00"), start=date(2026, 1, 1), end=date(2026, 1, 31))]
    )
    inputs = PartInputs(relief=_relief(p1, {_period(1): 50000}))
    unmapped = dataclasses.replace(
        book_context(bundles.entity(months=1)), mapping=_mapping(drop=[(REVENUE, None)])
    )
    state, _ = _compute(unmapped, allocated_state([principal]), inputs)
    assert state.posting_intents == ()
    assert state.findings == (
        Finding(
            ACCOUNT_MAPPING_MISSING,
            "ERROR",
            p1,
            {
                "book": "ASC606",
                "contract": CONTRACT_KEY,
                "entity": ENTITY,
                "obligation": "P1",
                "role": REVENUE,
                "rule": "S14-R-14",
            },
            14,
            None,
        ),
    )
    # A clearing line names its purpose.
    agent = allocated_state([_agent_obligation()])
    no_supplier = dataclasses.replace(unmapped, mapping=_mapping(drop=[(AP, "AP_SUPPLIER")]))
    agent_state, _ = _compute(
        no_supplier, agent, PartInputs(relief=_relief(AGENT_SUBJECT, {_period(1): 10000}))
    )
    assert agent_state.posting_intents == ()
    ((finding),) = agent_state.findings
    assert (finding.detail["role"], finding.detail["clearing_purpose"]) == (AP, "AP_SUPPLIER")
    # An obligation override resolves the role at T-REF-15 step 1.
    overridden = dataclasses.replace(principal, account_overrides={REVENUE: "4999"})
    resolved, trace = _compute(unmapped, allocated_state([overridden]), inputs)
    assert resolved.findings == ()
    line = next(line for line in resolved.posting_intents[0].lines if line.account_role == REVENUE)
    assert line.account_code == "4999"
    node = next(
        node for node in trace.nodes if node.id.startswith(f"account_resolution:{line.line_key}:")
    )
    assert (node.formula_id, node.value, node.params["account_code"]) == (
        "post.account_resolution.v1",
        "1",
        "4999",
    )


def _fold(bundle: InputBundle) -> tuple[BookContext, AllocatedState]:
    """Stages 01 to 05 of one book, as ``tests/engine/s05_allocation`` folds them."""
    book = bundle.books[0]
    ctx = BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=bundle.currencies,
        txn_currency=bundle.group.transaction_currency,
        entities={entity.code: entity for entity in bundle.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in bundle.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=bundle.trigger,
        tenant_preset=bundle.tenant_preset,
    )
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb)
    # The golden streams book without CONTRACT_ACTIVATED, so stage 02 publishes DRAFT and nothing
    # would post (S02-R-02); the promoted legacy contract is active (L2-5-Q-38).
    active = tuple(
        dataclasses.replace(
            view,
            status_in_book={
                book: ((history[0][0], "ACTIVE"),) for book, history in view.status_in_book.items()
            },
        )
        for view in allocated.contracts
    )
    return ctx, dataclasses.replace(allocated, contracts=active)


def test_legacy_preset_account_resolution() -> None:
    # Contract 1: January revenue 128.84 / 118.53 / 48.32 (CHK-022).
    ctx, allocated = _fold(golden_streams.stream("Contract 1", "02").input_bundle())
    assert ctx.tenant_preset == "LEGACY_PARITY"
    january = next(iter(ctx.entities.values())).periods[0].period_key
    obligations = {ob.obligation_key: ob for ob in allocated.obligations}
    entity = obligations["POB #1"].contracting_entity
    figures = {"POB #1": 12884, "POB #2": 11853, "POB #3": 4832}
    relief = tuple(
        _target("revenue_relief_cum", obligations[key].subject_key, january, value, entity=entity)
        for key, value in figures.items()
    )
    state, _ = _compute(ctx, allocated, PartInputs(relief=relief))
    accounts = {
        (intent.subject_key.rsplit("/", 1)[-1], line.account_role): line.account_code
        for intent in state.posting_intents
        for line in intent.lines
    }
    assert {role: code for (_, role), code in accounts.items() if role == CL} == {CL: "21001"}
    assert {ob: code for (ob, role), code in accounts.items() if role == REVENUE} == {
        "POB %231": "5001",
        "POB %232": "5002",
        "POB %233": "5003",
    }
    # Contract 2: CL 21002; unbilled receivable and contract asset both resolve to 15002.
    ctx2, allocated2 = _fold(golden_streams.stream("Contract 2", "02").input_bundle())
    obligations2 = {ob.obligation_key: ob for ob in allocated2.obligations}
    first = obligations2["POB #1"]
    third = obligations2["POB #3"]
    period = next(iter(ctx2.entities.values())).periods[0].period_key
    entity2 = first.contracting_entity
    inputs = PartInputs(
        relief=(_target("revenue_relief_cum", first.subject_key, period, 5885, entity=entity2),),
        reclass=(
            _target(
                "netting_reclass_amount",
                first.subject_key,
                period,
                5885,
                cause="UNBILLED_RECEIVABLE",
                entity=entity2,
            ),
            _target(
                "netting_reclass_amount",
                third.subject_key,
                period,
                1000,
                cause="CONTRACT_ASSET",
                entity=entity2,
            ),
        ),
    )
    command, _ = _compute(ctx2, allocated2, inputs)
    reclass, _ = _compute(
        dataclasses.replace(ctx2, trigger="CLOSE_RELEASE"),
        allocated2,
        inputs,
        pass_name="NETTING_RECLASS",
    )
    codes = {
        (intent.entry_kind, line.account_role): line.account_code
        for state2 in (command, reclass)
        for intent in state2.posting_intents
        for line in intent.lines
    }
    assert codes == {
        ("REVENUE_RECOGNITION", CL): "21002",
        ("REVENUE_RECOGNITION", REVENUE): "5001",
        ("NETTING_RECLASS", "UNBILLED_RECEIVABLE"): "15002",
        ("NETTING_RECLASS", "CONTRACT_ASSET"): "15002",
        ("NETTING_RECLASS", CL): "21002",
        # The pass also reverses January's reclass in February (S14-R-07), on the same accounts.
        ("NETTING_RECLASS_REVERSAL", "UNBILLED_RECEIVABLE"): "15002",
        ("NETTING_RECLASS_REVERSAL", "CONTRACT_ASSET"): "15002",
        ("NETTING_RECLASS_REVERSAL", CL): "21002",
    }


def test_rate_key_on_every_line() -> None:
    ctx = _foreign_context()
    start, end = date(2026, 1, 1), date(2026, 2, 28)
    services = obligation(
        "S", [segment(Fraction(2000), usd("2000.00"), start=start, end=end)], start=start, end=end
    )
    subject = services.subject_key
    flows = [_release(subject, 1, "1000.00"), _release(subject, 2, "1000.00")]
    rates = [
        _rate("average", 1, "1.1100"),
        _rate("average", 2, "1.1300"),
        _rate("closing", 1, "1.1200"),
        _rate("closing", 2, "1.1400"),
    ]
    inputs = PartInputs(relief=_relief(subject, {_period(1): 100000, _period(2): 200000}))
    state, _ = _compute(ctx, allocated_state([services]), inputs, flows=flows, rates=rates)
    lines = [(intent, line) for intent in state.posting_intents for line in intent.lines]
    assert lines and all(
        line.txn_currency == "EUR" and line.functional_currency == "USD" for _, line in lines
    )
    published = {rate.rate_key for rate in rates}
    for intent, line in lines:
        keys = {ref.rate_key for ref in state.line_rates[line.line_key]}
        assert keys and keys <= published
        if intent.posting_period_key == _period(2):
            assert "EURUSD-AVERAGE-FY2026-P02" in keys
    # A same-currency line carries no rate.
    first, _ = _ex_14_a()
    assert dict(first.line_rates) == {}


def test_s14_inv_04_control_role_equals_np() -> None:
    # CHK-010, ENGINE mode: P1 R 3,000.00 B 0; P2 R 10,000.00 B 4,000.00; P3 R 1,000.00 B 5,000.00
    base = book_context(bundles.entity(months=1))
    engine_mode = PolicyResolver(
        tuple(
            dataclasses.replace(policy, value="ENGINE", level="T", source_ref="OVR-TEST")
            if policy.code == "billing.posting"
            else policy
            for policy in base.policies.all()
        )
    )
    ctx = dataclasses.replace(base, policies=engine_mode, mapping=_mapping())
    obligations = [
        obligation(
            key,
            [
                segment(
                    Fraction(amount), amount * 100, start=date(2026, 1, 1), end=date(2026, 1, 31)
                )
            ],
        )
        for key, amount in (("P1", 3000), ("P2", 10000), ("P3", 1000))
    ]
    p1, p2, p3 = (ob.subject_key for ob in obligations)
    period = _period(1)
    inputs = PartInputs(
        relief=(
            _target("revenue_relief_cum", p1, period, 300000),
            _target("revenue_relief_cum", p2, period, 1000000),
            _target("revenue_relief_cum", p3, period, 100000),
        ),
        invoices=(
            _target("billed_unconditional_cum", p2, period, 400000),
            _target("billed_unconditional_cum", p3, period, 500000),
        ),
        reclass=(
            _target("netting_reclass_amount", p1, period, 300000, cause="UNBILLED_RECEIVABLE"),
            _target("netting_reclass_amount", p2, period, 200000, cause="CONTRACT_ASSET"),
        ),
    )
    allocated = allocated_state(obligations)
    command, _ = _compute(ctx, allocated, inputs)
    reclass, _ = _compute(
        dataclasses.replace(ctx, trigger="CLOSE_RELEASE"),
        allocated,
        inputs,
        posted=_posted(command),
        pass_name="NETTING_RECLASS",
    )
    for state in (command, reclass):
        _balanced(state)
    intents = [*command.posting_intents, *reclass.posting_intents]

    def balance(role: str, kinds: Iterable[str] | None = None) -> int:
        return sum(
            (line.amount_txn if line.side == "D" else -line.amount_txn)
            for intent in intents
            if kinds is None or intent.entry_kind in kinds
            for line in intent.lines
            if line.account_role == role
        )

    billed, revenue = 900000, 1400000
    net_position = billed - revenue  # NP = −5,000.00 (D-12: positive means a liability)
    control = balance(
        CL,
        [
            kind
            for kind in {i.entry_kind for i in intents}
            if not kind.startswith("NETTING_RECLASS")
        ],
    )
    assert -control == net_position == -500000
    # JET-06: Dr UR 3,000.00, Dr CA 2,000.00 / Cr CL 5,000.00; AR 9,000.00 from JET-03.
    assert (balance("UNBILLED_RECEIVABLE"), balance("CONTRACT_ASSET")) == (300000, 200000)
    assert balance(CL, ["NETTING_RECLASS"]) == -500000
    assert balance("ACCOUNTS_RECEIVABLE") == billed

"""Stage 10 receivables, presentation split, reclass attribution and current parts (ENC-13, ENC-14).

ENGINE_SPEC_B §10.2.6 to §10.2.8 (S10-R-18 to S10-R-25), §10.3 S10-INV-01, S10-INV-03 and
S10-INV-09, §10.7 EX-10-A to EX-10-C; POLICIES ALG-02 §2.2 (CHK-010 to CHK-012), ALG-03 §2.4
(CHK-013, CHK-014), JET-04c (CHK-138), JET-06 and PT-07 (CHK-117). Stages 09 and 10 run over an
``AllocatedState`` built against the documented contract (support.recognition; D-81 integration
after merge). Revenue of ``RIGHT_TO_INVOICE`` and ``MILESTONE`` obligations, whose measures are
post-rc (ENC-5, ENC-6), comes from a time-elapsed stand-in over the same term; stage 10 then reads
the obligation with its own measure, which is what ALG-03 classifies. The EX-10-A reclass is
asserted in the CHK-010 world, whose 31 January figures are the EX-10-A row of that date.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.enums import RecognitionMethod
from erev_engine.money import largest_remainder
from erev_engine.stages import STAGES, s09_recognition, s10_billing_balances
from erev_engine.stages.s10_billing_balances import BalanceState, ReclassAttribution, reclass
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ContractView,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    PolicyResolver,
    SpecialistTargets,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import INCEPTION, entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    contract_view,
    emit_catch_up_nodes,
    estimate_version,
    event_view,
    obligation,
    segment,
    usd,
)

CTX = book_context(entity(months=3))
JAN_31 = date(2026, 1, 31)
O1, O2, O3 = (f"{CONTRACT_KEY}/P{index}" for index in (1, 2, 3))
GROUP_AT_ENTITY = "CG-1@US01"
BALANCES = ("contract_liability", "contract_asset", "unbilled_receivable")
DECLARED = {
    formula_id for spec in STAGES if spec.stage in ("09", "10") for formula_id in spec.formula_ids
}


def _engine(ctx: BookContext) -> BookContext:
    """The book with POL-004 ``ENGINE`` in every period (pin P; POL-123 derived)."""
    policies = [
        dataclasses.replace(policy, value="ENGINE") if policy.code == "billing.posting" else policy
        for policy in ctx.policies.all()
    ]
    return dataclasses.replace(ctx, policies=PolicyResolver(tuple(policies)))


def _run(
    ctx: BookContext,
    st: AllocatedState,
    *,
    methods: Mapping[str, str] | None = None,
    tb: TraceBuilder | None = None,
) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one book; ``methods`` replaces stand-in measures for stage 10. The
    trace re-evaluates node for node and every node formula is declared by ``STAGES``."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION) if tb is None else tb
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    if methods:
        obligations = tuple(
            dataclasses.replace(
                ob,
                recognition_method=RecognitionMethod(methods[ob.subject_key]),
                ratable_convention=None,
            )
            if ob.subject_key in methods
            else ob
            for ob in st.obligations
        )
        allocated = dataclasses.replace(st, obligations=obligations)
        recognition = dataclasses.replace(recognition, allocated=allocated)
    state = s10_billing_balances.run(ctx, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert {node.formula_id for node in trace.nodes} <= DECLARED
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _value(targets: Sequence[Target], measure: str, subject_key: str, period_key: str) -> int:
    return next(
        target.value
        for target in targets
        if (target.measure, target.subject_key, target.period_key)
        == (measure, subject_key, period_key)
    )


def _presented(
    state: BalanceState, period_key: str, subject_key: str = GROUP_AT_ENTITY
) -> tuple[int, int, int]:
    """(contract liability, contract asset, unbilled receivable) at a period end."""
    cl, ca, ur = (_value(state.presentation, name, subject_key, period_key) for name in BALANCES)
    return cl, ca, ur


def _members(state: BalanceState, period_key: str, subject_key: str) -> tuple[int, int, int]:
    """Member-contract (contract liability, contract asset, unbilled receivable) (S10-R-23)."""
    cl, ca, ur = (_value(state.member_balances, name, subject_key, period_key) for name in BALANCES)
    return cl, ca, ur


def _net_position(state: BalanceState, period_key: str, subject_key: str = GROUP_AT_ENTITY) -> int:
    return _value(state.positions, "net_position", subject_key, period_key)


def _attributions(state: BalanceState, period_key: str) -> dict[str, ReclassAttribution]:
    return {
        item.subject_key: item for item in state.netting_reclass if item.period_key == period_key
    }


def _invoice(
    version: int,
    when: date,
    number: str,
    amount: str,
    key: str | None,
    *,
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload: dict[str, object] = {
        "invoice_number": number,
        "line_external_id": "1",
        "amount": Decimal(amount),
        "issue_date": when,
    }
    if key is not None:
        payload["obligation_key"] = key
    keys = [] if key is None else [key]
    return event_view(
        contract_key, version, "BILLING_RECORDED", when, payload, obligation_keys=keys
    )


def _delivery(
    version: int,
    when: date,
    key: str,
    quantity: str = "1",
    *,
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return event_view(
        contract_key, version, "DELIVERY_RECORDED", when, payload, obligation_keys=[key]
    )


def _service(
    key: str, amount: str, start: date, end: date, *, contract_key: str = CONTRACT_KEY
) -> ObligationState:
    services = segment(Fraction(Decimal(amount)), usd(amount), start=start, end=end)
    return obligation(key, [services], contract_key=contract_key, convention="DAILY")


def _goods(key: str, amount: str, *, contract_key: str = CONTRACT_KEY) -> ObligationState:
    goods = segment(
        Fraction(Decimal(amount)),
        usd(amount),
        start=INCEPTION,
        end=INCEPTION,
        measure="POINT_IN_TIME",
    )
    return obligation(
        key, [goods], contract_key=contract_key, method="POINT_IN_TIME", convention=None
    )


def _chk_010() -> tuple[BalanceState, Trace]:
    """CHK-010: P1 time and materials (unconditional), P2 milestone and P3 conditional."""
    obligations = [
        _service("P1", "3000", INCEPTION, JAN_31),
        _service("P2", "10000", INCEPTION, JAN_31),
        _goods("P3", "1000"),
    ]
    events = [
        _delivery(2, date(2026, 1, 20), "P3"),
        _invoice(3, JAN_31, "INV-P2", "4000.00", "P2"),
        _invoice(4, JAN_31, "INV-P3", "5000.00", "P3"),
    ]
    methods = {O1: "RIGHT_TO_INVOICE", O2: "MILESTONE"}
    return _run(CTX, allocated_state(obligations, events=events), methods=methods)


def _chk_012() -> tuple[BalanceState, BalanceState]:
    """CHK-012: contract X (licence and services) and contract Y, not combined."""
    x_events = [
        _delivery(2, date(2026, 1, 10), "LICENCE", contract_key="X"),
        _invoice(3, JAN_31, "INV-X-1", "10000.00", "LICENCE", contract_key="X"),
        _invoice(4, JAN_31, "INV-X-2", "40000.00", "SERVICES", contract_key="X"),
    ]
    x = allocated_state(
        [
            _goods("LICENCE", "60000", contract_key="X"),
            _service("SERVICES", "20000", INCEPTION, JAN_31, contract_key="X"),
        ],
        events=x_events,
    )
    y = allocated_state(
        [_service("SERVICES", "5000", date(2026, 2, 1), date(2026, 2, 28), contract_key="Y")],
        events=[_invoice(2, JAN_31, "INV-Y-1", "5000.00", "SERVICES", contract_key="Y")],
    )
    x_state, _ = _run(CTX, dataclasses.replace(x, group_code="CG-X"))
    y_state, _ = _run(CTX, dataclasses.replace(y, group_code="CG-Y"))
    return x_state, y_state


def _chk_013() -> BalanceState:
    """CHK-013 (FASB Example 39, ENGINE mode): A 400.00 and B 600.00, payment on both transfers."""
    events = [
        _delivery(2, date(2026, 1, 20), "P1"),
        _delivery(3, date(2026, 2, 15), "P2"),
        _invoice(4, date(2026, 2, 15), "INV-1", "1000.00", None),  # noncancellable
    ]
    st = allocated_state([_goods("P1", "400"), _goods("P2", "600")], events=events)
    state, _ = _run(_engine(CTX), st)
    return state


def _chk_014() -> BalanceState:
    """CHK-014: 120 hours × 25.00 performed in December under a right to invoice, invoiced in
    January."""
    december = date(2025, 12, 1)
    ctx = book_context(entity(start=december, months=2))
    ob = _service("P1", "3000", december, date(2025, 12, 31))
    events = [_invoice(2, date(2026, 1, 15), "INV-1", "3000.00", "P1")]
    st = allocated_state([ob], events=events, inception=december, statuses=((december, "ACTIVE"),))
    state, _ = _run(ctx, st, methods={O1: "RIGHT_TO_INVOICE"})
    return state


def test_chk_012_presentation_netting() -> None:
    x_state, y_state = _chk_012()
    assert _net_position(x_state, "FY2026-P01", "CG-X@US01") == usd("-30000.00")
    assert _presented(x_state, "FY2026-P01", "CG-X@US01") == (0, usd("30000.00"), 0)
    assert _presented(y_state, "FY2026-P01", "CG-Y@US01") == (usd("5000.00"), 0, 0)
    assert {target.subject_key for target in x_state.presentation} == {"CG-X@US01"}


def test_chk_013_example_39() -> None:
    state = _chk_013()
    # After A transfers: NP (400.00), U 0, contract asset 400.00 and no receivable.
    assert _net_position(state, "FY2026-P01") == usd("-400.00")
    assert state.right_classes[(O1, "FY2026-P01")] == "CONDITIONAL"
    assert _presented(state, "FY2026-P01") == (0, usd("400.00"), 0)
    assert _value(state.accounts_receivable, "accounts_receivable", "K-01@US01", "FY2026-P01") == 0
    # After B transfers and the invoice: AR 1,000.00, NP 0.00, contract asset 0.00.
    assert _value(
        state.accounts_receivable, "accounts_receivable", "K-01@US01", "FY2026-P02"
    ) == usd("1000.00")
    assert _net_position(state, "FY2026-P02") == 0
    assert _presented(state, "FY2026-P02") == (0, 0, 0)


def test_chk_014_right_to_invoice_presentation() -> None:
    state = _chk_014()
    assert state.right_classes[(O1, "FY2025-P12")] == "UNCONDITIONAL"
    assert _net_position(state, "FY2025-P12") == usd("-3000.00")
    assert _presented(state, "FY2025-P12") == (0, 0, usd("3000.00"))
    # January after the invoice: the unbilled receivable is 0.00.
    assert _presented(state, "FY2026-P01") == (0, 0, 0)


def test_ex_10_c_financing_in_r_p() -> None:
    ob = _goods("P1", "848346.53")
    events = [_delivery(2, INCEPTION, "P1"), _invoice(3, JAN_31, "INV-1", "18871.00", "P1")]
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    detail = {"member": "financing_interest", "value": "8483.47"}
    interest_node = tb.node(  # the stage 04 JET-11a target stage 10 cites (S04-R-13; D-81)
        measure="financing_interest_cum",
        subject_key=f"{CONTRACT_KEY}@US01",
        period_key="FY2026-P01",
        value=usd("8483.47"),
        currency="USD",
        minor_unit=2,
        formula_id="rec.catch_up.sum.v1",
        inputs=[SourceRef("contract_event", f"{CONTRACT_KEY}/EV-000001", detail)],
        params={"as_of": JAN_31.isoformat()},
        narrative_key="rec.catch_up.sum",
    )
    interest = Target(
        CTX.book_code,
        "US01",
        f"{CONTRACT_KEY}@US01",
        "financing_interest_cum",
        "FY2026-P01",
        "JET-11a",
        usd("8483.47"),
        None,
        interest_node,
    )
    st = dataclasses.replace(
        allocated_state([ob], events=events),
        specialist_targets=SpecialistTargets((), (interest,), (), (), ()),
    )
    state, trace = _run(CTX, st, tb=tb)
    assert _value(state.accretion_attributed, "accretion_attributed_cum", O1, "FY2026-P01") == usd(
        "8483.47"
    )
    assert state.right_classes[(O1, "FY2026-P01")] == "UNCONDITIONAL"  # table 2.4-A row 3
    # R_p = 848,346.53 + 8,483.47 = 856,830.00; U = 856,830.00 − 18,871.00 = 837,959.00.
    split = _node(trace, f"unbilled_receivable:{GROUP_AT_ENTITY}:FY2026-P01")
    assert (split.params["relief"], split.params["billed"]) == ("85683000", "1887100")
    assert _presented(state, "FY2026-P01") == (0, 0, usd("837959.00"))


def test_chk_138_receivable_contra() -> None:
    version = dataclasses.replace(
        estimate_version(f"{CONTRACT_KEY}/IPC", "IMPLICIT_PRICE_CONCESSION", 1, INCEPTION),
        rate=Decimal("0.6"),
    )
    pins = EstimatePins(
        {version.estimate_key: (EstimatePin(version, (INCEPTION, 2, "K-01/EV-000002")),)}
    )
    events = [
        _delivery(3, date(2026, 1, 20), "P1"),
        _invoice(4, date(2026, 1, 20), "INV-1", "1000000.00", "P1"),
    ]
    st = allocated_state([_goods("P1", "400000")], events=events, estimates=pins)
    state, trace = _run(_engine(CTX), st)
    contra = _value(state.receivable_contra, "receivable_contra", "K-01@US01", "FY2026-P01")
    receivable = _value(state.accounts_receivable, "accounts_receivable", "K-01@US01", "FY2026-P01")
    assert (contra, receivable, receivable - contra) == (
        usd("600000.00"),
        usd("1000000.00"),
        usd("400000.00"),
    )
    assert _net_position(state, "FY2026-P01") == 0
    assert _presented(state, "FY2026-P01")[0] == 0  # contract liability 0.00
    node = _node(trace, "receivable_contra:K-01@US01:FY2026-P01")
    assert (node.formula_id, node.params["kappa"], node.inputs) == (
        "pos.receivable_contra.v1",
        "3/5",
        ("billed_unconditional_cum:K-01@US01:FY2026-P01",),
    )


def test_s10_r21_default_classification() -> None:
    view = contract_view()
    goods, services, empty = (
        _goods("P1", "1000"),
        _service("P2", "2000", INCEPTION, JAN_31),
        _goods("P3", "0"),
    )
    other_contract = _goods("P9", "500", contract_key="K-02")

    def right(
        ob: ObligationState,
        obligations: Sequence[ObligationState],
        ctx: BookContext = CTX,
        contract: ContractView = view,
    ) -> str:
        return reclass.right_class(ctx, contract, ob, obligations, JAN_31)

    # A point-in-time obligation is unconditional only when it is the sole obligation of its
    # contracting entity in the contract with a non-zero posted allocation.
    assert right(goods, [goods]) == "UNCONDITIONAL"
    assert right(goods, [goods, empty]) == "UNCONDITIONAL"
    assert right(goods, [goods, other_contract]) == "UNCONDITIONAL"
    assert right(goods, [goods, services]) == "CONDITIONAL"
    # Right to invoice, usage billed in arrears and royalties are unconditional; others are not.
    for method in ("RIGHT_TO_INVOICE", "USAGE", "ROYALTY"):
        measured = dataclasses.replace(
            services, recognition_method=RecognitionMethod(method), ratable_convention=None
        )
        assert right(measured, [goods, measured]) == "UNCONDITIONAL"
    assert right(services, [goods, services]) == "CONDITIONAL"
    # A customer termination right without penalty makes every obligation conditional.
    header = dataclasses.replace(
        view.header, termination_party="CUSTOMER", termination_has_penalty=False
    )
    terminable = dataclasses.replace(view, header=header)
    invoiced = dataclasses.replace(
        services, recognition_method=RecognitionMethod.RIGHT_TO_INVOICE, ratable_convention=None
    )
    assert right(goods, [goods], contract=terminable) == "CONDITIONAL"
    assert right(invoiced, [invoiced], contract=terminable) == "CONDITIONAL"
    penalty = dataclasses.replace(
        view, header=dataclasses.replace(header, termination_has_penalty=True)
    )
    assert right(goods, [goods], contract=penalty) == "UNCONDITIONAL"
    # POL-122 set at obligation level governs (OVR).
    override = book_context(
        entity(months=3),
        overrides=[("balance.right_to_consideration", "OBLIGATION", O2, "UNCONDITIONAL")],
    )
    assert right(services, [goods, services], ctx=override) == "UNCONDITIONAL"


def test_s10_inv_01_presented_identity() -> None:
    chk_010, _ = _chk_010()
    # CHK-010: NP (5,000.00); U 3,000.00; unbilled receivable 3,000.00; contract asset 2,000.00.
    assert _net_position(chk_010, "FY2026-P01") == usd("-5000.00")
    assert _presented(chk_010, "FY2026-P01") == (0, usd("2000.00"), usd("3000.00"))
    checked = 0
    for state in (chk_010, *_chk_012(), _chk_013(), _chk_014()):
        for parts in state.position_components.values():
            cl, ca, ur = _presented(state, parts.period_key, parts.subject_key)
            assert min(cl, ca, ur) >= 0  # S10-INV-02
            assert cl - ca - ur == parts.net_position  # S10-INV-01
            # S10-INV-03: the attributions sum to the presented balances.
            items = [
                item
                for item in state.netting_reclass
                if item.entity == parts.entity and item.period_key == parts.period_key
            ]
            assert (sum(item.asset for item in items), sum(item.receivable for item in items)) == (
                ca,
                ur,
            )
            checked += 1
    assert checked == 3 + 3 + 3 + 3 + 2


def test_chk_010_split_and_attribution() -> None:
    state, trace = _chk_010()
    assert _net_position(state, "FY2026-P01") == usd("-5000.00")
    # U = max(0, 3,000.00 − 0.00) over P1, the only obligation with an unconditional right.
    split = _node(trace, f"unbilled_receivable:{GROUP_AT_ENTITY}:FY2026-P01")
    assert (split.params["keys"], split.params["relief"], split.params["billed"]) == (
        O1,
        "300000",
        "0",
    )
    assert _presented(state, "FY2026-P01") == (0, usd("2000.00"), usd("3000.00"))
    january = _attributions(state, "FY2026-P01")
    parts = {key: (item.receivable, item.asset, item.role) for key, item in january.items()}
    assert parts == {
        O1: (usd("3000.00"), 0, "UNBILLED_RECEIVABLE"),
        O2: (0, usd("2000.00"), "CONTRACT_ASSET"),  # entirely P2 under POB_DEBIT_POSITIONS
        O3: (0, 0, None),
    }
    node = _node(trace, f"netting_reclass_amount:{O2}:FY2026-P01")
    assert (
        node.formula_id,
        node.params["ca_keys"],
        node.params["ca_weights"],
        node.params["ca_basis"],
        node.inputs,
    ) == (
        "pos.reclass_attribution.pob_debit_positions.v1",
        f"{O2}|{O3}",
        "600000|0",
        "positions",
        (f"net_position:{GROUP_AT_ENTITY}:FY2026-P01",),
    )
    assert (node.value, node.rounding_residue) == ("2000.00", "0")
    # JET-06: Dr unbilled receivable 3,000.00 and Dr contract asset 2,000.00 / Cr contract
    # liability 5,000.00.
    posted = [
        entry
        for entry in state.reclass_entries
        if entry.period_key == "FY2026-P01" and entry.kind == "NETTING_RECLASS"
    ]
    assert sorted((entry.debit_role, entry.amount) for entry in posted) == [
        ("CONTRACT_ASSET", usd("2000.00")),
        ("UNBILLED_RECEIVABLE", usd("3000.00")),
    ]
    assert {entry.credit_role for entry in posted} == {"CONTRACT_LIABILITY"}
    assert sum(entry.amount for entry in posted) == usd("5000.00")
    # The single member contract carries the group's balances (S10-R-23).
    assert _members(state, "FY2026-P01", "K-01@US01") == (0, usd("2000.00"), usd("3000.00"))


def _golden_contract_2() -> list[ObligationState]:
    """Golden Contract 2 (legacy 02 §5.3): X = 900 × extended SSP ÷ 1,170, unit SSP per line."""
    setup = date(2023, 1, 1)
    lines = (("POB #1", "8", 612), ("POB #2", "3", 408), ("POB #3", "1", 150), ("VC #1", "1", 0))
    total = sum(ssp for _, _, ssp in lines)
    posted = largest_remainder(
        90000, [Fraction(ssp) for _, _, ssp in lines], [key for key, _, _ in lines]
    )
    obligations = []
    for (key, quantity, ssp), a_posted in zip(lines, posted, strict=True):
        units = Fraction(quantity)
        seg = segment(
            Fraction(900 * ssp, total),
            a_posted,
            start=setup,
            end=date(2023, 12, 31),
            quantity=units,
            measure="UNITS_DELIVERED",
        )
        obligations.append(
            obligation(
                key,
                [dataclasses.replace(seg, unit_ssp=Fraction(ssp) / units)],
                contract_key="Contract 2",
                method="UNITS_DELIVERED",
                convention=None,
                start=setup,
                quantity=units,
                kind="VC_LINE" if key.startswith("VC") else "STANDARD",
            )
        )
    return obligations


def test_chk_011_parity_reclass_by_cumulative_ssp_delivered() -> None:
    setup, mar_31 = date(2023, 1, 1), date(2023, 3, 31)
    parity = book_context(entity(start=setup, months=12), preset="LEGACY_PARITY")
    events = [
        _delivery(2, date(2023, 1, 31), "POB #1", contract_key="Contract 2"),
        _delivery(3, mar_31, "POB #3", "0.4", contract_key="Contract 2"),
    ]
    st = allocated_state(
        _golden_contract_2(), events=events, inception=setup, statuses=((setup, "ACTIVE"),)
    )
    state, trace = _run(parity, st)
    pob_1, pob_2, pob_3, vc_1 = (
        f"Contract 2/{key}" for key in ("POB #1", "POB #2", "POB #3", "VC #1")
    )
    revenue = {
        key: _value(state.recognition.revenue_targets, "revenue_cum", key, "FY2023-P03")
        for key in (pob_1, pob_3)
    }
    assert revenue == {pob_1: usd("58.85"), pob_3: usd("46.15")}
    assert {_value(state.billing, "billed_cum", key, "FY2023-P03") for key in (pob_1, pob_3)} == {0}
    by_key = {ob.subject_key: ob for ob in st.obligations}
    delivered = {key: reclass.ssp_delivered_cum(st, by_key[key], mar_31) for key in (pob_1, pob_3)}
    assert delivered == {pob_1: Fraction("76.5"), pob_3: Fraction(60)}
    assert _net_position(state, "FY2023-P03") == usd("-105.00")
    march = _attributions(state, "FY2023-P03")
    assert {key: item.amount for key, item in march.items()} == {
        pob_1: usd("58.85"),
        pob_2: 0,
        pob_3: usd("46.15"),
        vc_1: 0,
    }
    node = _node(trace, f"netting_reclass_amount:{pob_1}:FY2023-P03")
    assert (node.formula_id, node.params["basis"], node.params["keys"], node.params["weights"]) == (
        "pos.reclass_attribution.cumulative_ssp_delivered.v1",
        "ssp_delivered",
        f"{pob_1}|{pob_2}|{pob_3}",  # VC lines take no share (DEV-057)
        "153/2|0|60",
    )
    # Units delivered beside other non-zero allocations are conditional (ALG-03), so the shares
    # present as contract asset; both roles map to one account under the preset (DEV-074).
    assert _presented(state, "FY2023-P03") == (0, usd("105.00"), 0)


def test_chk_117_attribution_totals_tie_to_reclass() -> None:
    state, _ = _chk_010()
    january = _attributions(state, "FY2026-P01")
    posted = [
        entry
        for entry in state.reclass_entries
        if entry.period_key == "FY2026-P01" and entry.kind == "NETTING_RECLASS"
    ]
    for role, total in (("UNBILLED_RECEIVABLE", "3000.00"), ("CONTRACT_ASSET", "2000.00")):
        attributed = sum(
            item.receivable if role == "UNBILLED_RECEIVABLE" else item.asset
            for item in january.values()
        )
        reclassified = sum(entry.amount for entry in posted if entry.debit_role == role)
        assert attributed == reclassified == usd(total)
    # Each attribution carries the date of its obligation's latest revenue event (B3-AK-09): the
    # time-elapsed terms of P1 and P2 run to 31 January, so both age in the 0 to 30 day bucket.
    ages = {key: item.revenue_date for key, item in january.items() if item.amount}
    assert ages == {O1: JAN_31, O2: JAN_31}
    assert all(0 <= (JAN_31 - revenue_on).days <= 30 for revenue_on in ages.values())
    # P3's latest revenue event is its delivery on 20 January, not its invoice.
    assert january[O3].revenue_date == date(2026, 1, 20)


def test_ex_10_b_current_noncurrent() -> None:
    ctx = book_context(entity(months=36), horizon="FY2026-P12")
    services = segment(Fraction(36000), usd("36000"), start=INCEPTION, end=date(2028, 12, 31))
    ob = obligation("P1", [services], convention="MONTHLY_EVEN")
    events = [_invoice(2, INCEPTION, "INV-1", "36000.00", "P1")]
    state, trace = _run(ctx, allocated_state([ob], events=events))
    december = "FY2026-P12"
    liability = _value(state.presentation, "contract_liability", GROUP_AT_ENTITY, december)
    current = _value(state.current_split, "contract_liability_current", GROUP_AT_ENTITY, december)
    assert (liability, current, liability - current) == (
        usd("24000.00"),
        usd("12000.00"),
        usd("12000.00"),
    )
    node = _node(trace, f"contract_liability_current:{GROUP_AT_ENTITY}:{december}")
    assert (node.formula_id, node.params["horizon"], node.params["relief"]) == (
        "pos.current_split.v1",
        "2027-12-31",
        "1200000",
    )
    checked = 0
    for target in state.current_split:  # S10-INV-09: current parts never exceed their balances
        balance = _value(
            state.presentation,
            target.measure.removesuffix("_current"),
            target.subject_key,
            target.period_key,
        )
        assert 0 <= target.value <= balance
        checked += 1
    assert checked == 12 * 3
    # The preset view is suppressed under POL-124 NONE (T-CON-09 defaults).
    parity = book_context(entity(months=36), horizon="FY2026-P12", preset="LEGACY_PARITY")
    suppressed, _ = _run(parity, allocated_state([ob], events=events))
    assert {target.value for target in suppressed.current_split} == {0}


def test_s10_r24_the_fixed_fee_of_a_usage_obligation_is_relieved_by_its_projection() -> None:
    """S10-R-24 with the one predicate of S09-R-45 (rev 1.126; item ENG-USAGE-FIXED-SCHEDULE-1;
    supervisor ruling R-116 (a)): EX-10-B with the obligation measured by usage — 36,000.00 for
    three years, invoiced at the inception, recognised 1,000.00 a month. At December 2026 the
    liability is 24,000.00 and the twelve months of 2027 relieve 12,000.00 of it. Before, a usage
    obligation that ended after the twelve months counted for nothing: the current part read 0."""
    monthly = ("recognition.time_convention", "ENTITY", "US01", "MONTHLY_EVEN")
    ctx = book_context(entity(months=36), horizon="FY2026-P12", overrides=[monthly])
    end = date(2028, 12, 31)
    fee = segment(Fraction(36000), usd("36000"), start=INCEPTION, end=end, measure="USAGE")
    fees = segment(Fraction(0), 0, start=INCEPTION, end=end, component="PERIOD_VC", measure="USAGE")
    ob = obligation("P1", [fee, fees], method="USAGE", convention=None)
    events = [_invoice(2, INCEPTION, "INV-1", "36000.00", "P1")]
    state, trace = _run(ctx, allocated_state([ob], events=events))
    december = "FY2026-P12"
    liability = _value(state.presentation, "contract_liability", GROUP_AT_ENTITY, december)
    current = _value(state.current_split, "contract_liability_current", GROUP_AT_ENTITY, december)
    assert (liability, current, liability - current) == (
        usd("24000.00"),
        usd("12000.00"),
        usd("12000.00"),
    )
    node = _node(trace, f"contract_liability_current:{GROUP_AT_ENTITY}:{december}")
    assert (node.params["horizon"], node.params["keys"], node.params["relief"]) == (
        "2027-12-31",
        f"{CONTRACT_KEY}/P1",
        "1200000",
    )
    # A usage obligation without a fixed fee is not deterministic: ending after the twelve months,
    # it relieves nothing, as before.
    bare = obligation(
        "P1",
        [dataclasses.replace(fee, x_exact=Fraction(0), a_posted=0), fees],
        method="USAGE",
        convention=None,
    )
    state, trace = _run(ctx, allocated_state([bare], events=events))
    node = _node(trace, f"contract_liability_current:{GROUP_AT_ENTITY}:{december}")
    assert (node.value, node.params["keys"], node.params["relief"]) == ("0.00", "", "")


def test_ex_10_a_reclass_reverses_next_period() -> None:
    state, _ = _chk_010()
    january = [entry for entry in state.reclass_entries if entry.period_key == "FY2026-P01"]
    reclassified = sorted(
        (entry.subject_key, entry.debit_role, entry.credit_role, entry.amount, entry.posting_date)
        for entry in january
        if entry.kind == "NETTING_RECLASS"
    )
    assert reclassified == [
        (O1, "UNBILLED_RECEIVABLE", "CONTRACT_LIABILITY", usd("3000.00"), JAN_31),
        (O2, "CONTRACT_ASSET", "CONTRACT_LIABILITY", usd("2000.00"), JAN_31),
    ]
    reversed_ = sorted(
        (
            entry.subject_key,
            entry.debit_role,
            entry.credit_role,
            entry.amount,
            entry.posting_date,
            entry.reason_code,
        )
        for entry in january
        if entry.kind == "NETTING_RECLASS_REVERSAL"
    )
    feb_1 = date(2026, 2, 1)
    assert reversed_ == [
        (
            O1,
            "CONTRACT_LIABILITY",
            "UNBILLED_RECEIVABLE",
            usd("3000.00"),
            feb_1,
            "RECLASS_REVERSAL",
        ),
        (O2, "CONTRACT_LIABILITY", "CONTRACT_ASSET", usd("2000.00"), feb_1, "RECLASS_REVERSAL"),
    ]
    # EX-10-A: the reclass posts again on 28 February and 31 March.
    for period_key, end in (("FY2026-P02", date(2026, 2, 28)), ("FY2026-P03", date(2026, 3, 31))):
        again = sorted(
            (entry.subject_key, entry.debit_role, entry.amount, entry.posting_date)
            for entry in state.reclass_entries
            if entry.period_key == period_key and entry.kind == "NETTING_RECLASS"
        )
        assert again == [
            (O1, "UNBILLED_RECEIVABLE", usd("3000.00"), end),
            (O2, "CONTRACT_ASSET", usd("2000.00"), end),
        ]


def test_s10_r23_member_balances() -> None:
    x = _service("SERVICES", "1000", INCEPTION, JAN_31, contract_key="X")
    y = _goods("GOODS", "1500", contract_key="Y")
    events = [
        _invoice(2, JAN_31, "INV-X-1", "500.00", "SERVICES", contract_key="X"),
        _delivery(2, date(2026, 1, 20), "GOODS", contract_key="Y"),
        _invoice(3, date(2026, 2, 10), "INV-X-2", "2500.00", "SERVICES", contract_key="X"),
    ]
    state, _ = _run(CTX, allocated_state([x, y], events=events))
    # January: NP (2,000.00); Y's goods are its contract's only non-zero allocation, so U 1,500.00.
    assert _presented(state, "FY2026-P01") == (0, usd("500.00"), usd("1500.00"))
    assert _members(state, "FY2026-P01", "X@US01") == (0, usd("500.00"), 0)
    assert _members(state, "FY2026-P01", "Y@US01") == (0, 0, usd("1500.00"))
    # February: NP 500.00, apportioned by max(0, Σ (B_p − R_p)): X 2,000.00, Y 0.00.
    assert _presented(state, "FY2026-P02") == (usd("500.00"), 0, 0)
    assert _members(state, "FY2026-P02", "X@US01") == (usd("500.00"), 0, 0)
    assert _members(state, "FY2026-P02", "Y@US01") == (0, 0, 0)


def test_l8_d_member_contract_without_obligations_publishes_zero_balances() -> None:
    """D-88 L7-5-Q-10 (3): a member contract none of whose lines is an obligation (ONB-RB-06) gets
    its T-CON-09 member balance targets for each period end, all zero; outside ENGINE mode
    accounts_receivable is added, and in ENGINE mode S10-R-19 publishes the receivable itself.
    The member with obligations keeps its S10-R-23 rows."""
    grant = "RB-06"
    views = [contract_view(CONTRACT_KEY), contract_view(grant)]
    st = allocated_state(
        [_goods("P1", "1000.00")],
        contracts=views,
        events=[_delivery(3, INCEPTION, "P1"), _invoice(4, INCEPTION, "INV-1", "1000.00", "P1")],
    )
    periods = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
    for ctx, receivable in ((CTX, True), (_engine(CTX), False)):
        state, _ = _run(ctx, st)
        subject = f"{grant}@US01"
        empty = [target for target in state.member_balances if target.subject_key == subject]
        measures = {*BALANCES, "accounts_receivable"} if receivable else set(BALANCES)
        assert {(target.measure, target.period_key) for target in empty} == {
            (measure, period) for measure in measures for period in periods
        }
        assert all(target.value == 0 for target in empty)
        assert _members(state, "FY2026-P01", f"{CONTRACT_KEY}@US01") == (0, 0, 0)

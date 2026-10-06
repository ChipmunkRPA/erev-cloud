"""Refund-liability components resolve their owner's opening (ENGINE_SPEC_B S14-R-26 rev 1.18;
ENGINE_SPEC S07-R-07 rev 1.19; D-98 35a — ENG-C5 phase 3; Codex C5-PH2-R2 for RETURN / CONCESSION).
Walker level on the CHK-121 allocated state after stage 07 (the one obligation's baseline at the
2025-12-31 cutover under RECOMPUTE_FROM_INCEPTION, and the ``<contract>@<entity>`` opening it
implies) with native component keys and dense JET-04b part targets: pre-cutover periods post
nothing, the zero-import difference posts once at the cutover on the component subject with the
owner named on its node, later movements post ordinarily, and the amounts are conserved across
the cutover. Mixed contracts (an obligation without a baseline) refuse explicitly. Fail-first on
50f7bfa (`.run/eng-c5p2/fail-first-overlay-50f7bfa.log`): TERMINATION / VARIABLE_CONSIDERATION /
UNCLAIMED_PROPERTY components were refused outright (the interim containment) and no owner was
named. No database (DG-TST-18).
"""

from __future__ import annotations

from datetime import date
from types import MappingProxyType

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s01_canonicalize.convert import group_entity_subject_key
from erev_engine.stages.s14_posting import onboarding
from erev_engine.stages.s14_posting.assign import PostedTotals, derive_deltas
from erev_engine.stages.s14_posting.targets import PartTarget, encode_component, role_targets
from erev_engine.stages.state import PostedIndex
from erev_engine.trace import TraceBuilder
from support import bundles, fold
from support import onboarding_worlds as w

REASON = "ONBOARDING_DIFFERENCE"
ENTITY = bundles.ENTITY_CODE
CONTRACT_AT_ENTITY = contract_entity_subject_key(w.CONTRACT, ENTITY)
KINDS = [
    ("RETURN", w.SUBJECT, w.SUBJECT),
    ("CONCESSION", f"{w.CONTRACT}/EV-000007/{w.SUBJECT}", w.SUBJECT),
    ("UNCLAIMED_PROPERTY", w.SUBJECT, w.SUBJECT),
    ("TERMINATION", f"{w.CONTRACT}/EV-000009", CONTRACT_AT_ENTITY),
    ("VARIABLE_CONSIDERATION", f"{w.CONTRACT}/EST-RR-1", CONTRACT_AT_ENTITY),
]
PERIODS = ("FY2025-P06", "FY2025-P07", "FY2025-P08", "FY2025-P09", "FY2025-P10", "FY2025-P11")


def _component_part(subject: str, period_key: str, amount: int) -> PartTarget:  # JET-04b
    return PartTarget(
        book_code="ASC606",
        entity=ENTITY,
        subject_key=subject,
        part="JET-04b",
        component=None,
        period_key=period_key,
        txn_currency="USD",
        amount_txn=amount,
        functional_currency="USD",
        amount_functional=amount,
        counterparty_entity=None,
        by_cause=(),
        rates=(),
        node_ids=(),
    )


def _chk_121_state():
    bundle = w.chk_121(books=("ASC606",))
    st, _ = fold.fold_trace(bundle, "ASC606")
    return st, fold.book_context(bundle, "ASC606")


def _rows(deltas):
    return sorted(
        (
            d.posting_period_key,
            d.origin_period_key or "",
            d.reason_code,
            d.key.subject_key,
            d.key.account_role,
            d.amount_txn,
        )
        for d in deltas
    )


def _walk(ctx, st, parts, found):
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    roles = role_targets(ctx, parts, tb)
    imported, refused = onboarding.imported_role_amounts(ctx, parts, found, frozenset())
    deltas = derive_deltas(
        ctx,
        st,
        roles,
        PostedTotals.of(ctx, PostedIndex(())),
        tb,
        pass_name=None,
        voided=(),
        imported=imported,
        openings=found,
    )
    return imported, refused, deltas, tb.build(root_measures={})


@pytest.mark.parametrize(("kind", "source", "owner"), KINDS)
def test_component_resolves_its_owner_and_conserves_its_amounts_across_the_cutover(
    kind: str, source: str, owner: str
) -> None:
    """Per kind (S14-R-26 rev 1.18): the native component key resolves to its owner's opening —
    the obligation for RETURN / CONCESSION / UNCLAIMED_PROPERTY, ``<contract>@<entity>`` for
    TERMINATION / VARIABLE_CONSIDERATION. A liability of 500 minor units from FY2025-P06 through
    the cutover and 700 in FY2026-P01: the six pre-cutover periods post nothing; the zero-import
    difference posts the whole 500 once at the cutover (Dr CONTRACT_LIABILITY / Cr
    REFUND_LIABILITY, ONBOARDING_DIFFERENCE, FY2026-P01 with origin FY2025-P12, closed) on the
    component subject; the January movement of 200 posts ordinarily (no reason code); the
    difference node names the owner. Conservation: imported 0 + difference 500 + movement 200 =
    the FY2026-P01 target 700 on both roles, and the onboarding lines balance."""
    st, ctx = _chk_121_state()
    subject = f"{group_entity_subject_key(st.group_code, ENTITY)}/{kind}/{source}"
    parts = [_component_part(subject, p, 500) for p in (*PERIODS, "FY2025-P12")]
    parts.append(_component_part(subject, "FY2026-P01", 700))
    found = onboarding.openings(st)
    imported, refused, deltas, trace = _walk(ctx, st, parts, found)
    # Fail-first: the rev 1.13 interim containment refused the three kinds here.
    assert refused == ()
    assert {k.subject_key for k in imported} == {subject}
    assert {(v.status, v.imported, v.recomputed[0]) for v in imported.values()} == {
        (onboarding.ELIGIBLE, (0, 0), 500),
        (onboarding.ELIGIBLE, (0, 0), -500),
    }
    assert _rows(deltas) == [
        ("FY2026-P01", "", None, subject, "CONTRACT_LIABILITY", 200),
        ("FY2026-P01", "", None, subject, "REFUND_LIABILITY", -200),
        ("FY2026-P01", "FY2025-P12", REASON, subject, "CONTRACT_LIABILITY", 500),
        ("FY2026-P01", "FY2025-P12", REASON, subject, "REFUND_LIABILITY", -500),
    ]
    by_role: dict[str, int] = {}
    for d in deltas:
        by_role[d.key.account_role] = by_role.get(d.key.account_role, 0) + d.amount_txn
    assert by_role == {"CONTRACT_LIABILITY": 700, "REFUND_LIABILITY": -700}
    assert sum(d.amount_txn for d in deltas if d.reason_code == REASON) == 0
    named = [
        node
        for node in trace.nodes
        if node.measure == "posting_delta" and node.params.get("reason") == REASON
    ]
    assert len(named) == 2
    assert {node.params["owner"] for node in named} == {owner}
    assert {node.params["cutover_date"] for node in named} == {"2025-12-31"}
    assert onboarding.resolve(found, subject, ENTITY) is found[owner]
    assert onboarding.unresolved(found, subject, ENTITY) is None


def test_component_whose_parts_start_after_the_cutover_posts_ordinarily() -> None:
    """A TERMINATION component created after the cutover (parts from FY2026-P01) has no
    pre-cutover history: no difference, no refusal, an ordinary January posting."""
    st, ctx = _chk_121_state()
    group = group_entity_subject_key(st.group_code, ENTITY)
    subject = f"{group}/TERMINATION/{w.CONTRACT}/EV-000011"
    found = onboarding.openings(st)
    imported, refused, deltas, _ = _walk(
        ctx, st, [_component_part(subject, "FY2026-P01", 500)], found
    )
    assert (dict(imported), refused) == ({}, ())
    assert _rows(deltas) == [
        ("FY2026-P01", "", None, subject, "CONTRACT_LIABILITY", 500),
        ("FY2026-P01", "", None, subject, "REFUND_LIABILITY", -500),
    ]


def _mixed_openings() -> dict[str, onboarding.Opening]:
    """A contract with two obligations of which only one carries a baseline: no
    ``<contract>@<entity>`` opening exists (S14-R-26)."""
    opening = onboarding.Opening(
        date(2025, 12, 31),
        onboarding.RECOMPUTE,
        f"{w.CONTRACT}/EV-000003",
        MappingProxyType({"revenue_cum": 12000000, "billed_cum": 24000000, "deposit_liability": 0}),
        w.CONTRACT,
        w.SUBJECT,
    )
    return {w.SUBJECT: opening}


@pytest.mark.parametrize(
    ("kind", "source"),
    [
        ("TERMINATION", f"{w.CONTRACT}/EV-000009"),
        ("VARIABLE_CONSIDERATION", f"{w.CONTRACT}/EST-RR-1"),
        ("UNCLAIMED_PROPERTY", f"{w.CONTRACT}/L2-OTHER"),
    ],
)
def test_mixed_contract_refuses_a_component_without_a_resolvable_owner(
    kind: str, source: str
) -> None:
    """A mixed contract (an obligation without a baseline): a TERMINATION or VARIABLE_CONSIDERATION
    component has no ``<contract>@<entity>`` owner and an UNCLAIMED_PROPERTY component naming the
    obligation without a baseline has no owner either — ONBOARDING_DIFFERENCE_UNPOSTED (ERROR) with
    reason component_owner_unresolved, kind, contract, entity and the owner candidates, once per
    component and part, bound to the component subject and the opening event; parts after the
    latest candidate cutover record nothing (an explicit refusal replacing the interim
    containment)."""
    _, ctx = _chk_121_state()
    found = _mixed_openings()
    subject = f"{group_entity_subject_key('CG-1', ENTITY)}/{kind}/{source}"
    assert onboarding.resolve(found, subject, ENTITY) is None
    missing = onboarding.unresolved(found, subject, ENTITY)
    assert missing is not None
    detail, candidates = missing
    assert dict(detail) == {
        "contract": w.CONTRACT,
        "entity": ENTITY,
        "kind": kind,
        "owner_candidates": w.SUBJECT,
    }
    assert [c.owner for c in candidates] == [w.SUBJECT]
    parts = [
        _component_part(subject, "FY2025-P06", 500),
        _component_part(subject, "FY2025-P12", 500),
    ]
    states, refused = onboarding.imported_role_amounts(ctx, parts, found, frozenset())
    assert dict(states) == {}
    assert [(f.code, f.severity, f.subject_key, f.event_key, f.detail) for f in refused] == [
        (
            "ONBOARDING_DIFFERENCE_UNPOSTED",
            "ERROR",
            subject,
            f"{w.CONTRACT}/EV-000003",
            {
                "contract": w.CONTRACT,
                "cutover_date": "2025-12-31",
                "entity": ENTITY,
                "kind": kind,
                "owner_candidates": w.SUBJECT,
                "part": "JET-04b",
                "reason": "component_owner_unresolved",
                "recomputed": "500",
                "role": "JET-04b",
                "rule": "S07-R-07",
            },
        )
    ]
    after = [_component_part(subject, "FY2026-P01", 500)]
    assert onboarding.imported_role_amounts(ctx, after, found, frozenset()) == ({}, ())


def test_a_contract_without_openings_keeps_every_component_ordinary() -> None:
    """No opening for the component's contract: ``resolve`` and ``unresolved`` are both None and
    nothing is refused (the component posts as before onboarding existed)."""
    _, ctx = _chk_121_state()
    subject = f"{group_entity_subject_key('CG-1', ENTITY)}/TERMINATION/K-OTHER/EV-000002"
    found = _mixed_openings()
    assert onboarding.resolve(found, subject, ENTITY) is None
    assert onboarding.unresolved(found, subject, ENTITY) is None
    assert onboarding.imported_role_amounts(
        ctx, [_component_part(subject, "FY2025-P06", 500)], found, frozenset()
    ) == ({}, ())


COLLIDING_SOURCES = [
    ("TERMINATION", f"{encode_component('K/A')}/EV-000002"),
    ("VARIABLE_CONSIDERATION", f"{encode_component('K/A')}/VC-REFUND"),
]


def _totals(deltas) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in deltas:
        out[d.key.account_role] = out.get(d.key.account_role, 0) + d.amount_txn
    return out


def _dense(subject: str) -> list[PartTarget]:
    parts = [_component_part(subject, p, 500) for p in (*PERIODS, "FY2025-P12")]
    parts.append(_component_part(subject, "FY2026-P01", 700))
    return parts


@pytest.mark.parametrize(("kind", "source"), COLLIDING_SOURCES)
def test_colliding_contract_ids_resolve_the_encoded_owner_on_synthetic_openings(
    kind: str, source: str
) -> None:
    """Codex C5-PH3-R1's exact counterexample: contracts ``K/A`` (RECOMPUTE) and ``K%2FA``
    (OPENING_BALANCES), both US01; the canonical source head ``K%2FA`` is ``K/A``'s encoded id and
    the collider's raw id, and the sorted owner order puts the collider first. The owner is the
    encoded match ``K%2FA@US01`` (method RECOMPUTE): signed role totals 700 minor (500 cutover
    difference + 200 movement) with the collider present, as in the standalone control; the
    difference nodes name that owner. Fail-first on c61e5f7: owner ``K%252FA@US01``
    (OPENING_BALANCES) and 200 only."""
    _, ctx = _chk_121_state()
    openings: dict[str, onboarding.Opening] = {}
    for contract, method in (
        ("K/A", onboarding.RECOMPUTE),
        ("K%2FA", "OPENING_BALANCES_AT_CUTOVER"),
    ):
        for owner in (f"{contract}/L1-SUB", contract_entity_subject_key(contract, ENTITY)):
            openings[owner] = onboarding.Opening(
                date(2025, 12, 31),
                method,
                f"{contract}/EV-000003",
                MappingProxyType(
                    {"revenue_cum": 12000000, "billed_cum": 24000000, "deposit_liability": 0}
                ),
                contract,
                owner,
            )
    found = dict(sorted(openings.items()))
    assert list(found)[0].startswith("K%252FA@")  # the collider sorts first
    intended = contract_entity_subject_key("K/A", ENTITY)
    subject = f"{group_entity_subject_key('CG-1', ENTITY)}/{kind}/{source}"
    assert onboarding.resolve(found, subject, ENTITY) is found[intended]
    st, _ = _chk_121_state()
    standalone = {k: v for k, v in found.items() if v.contract_key == "K/A"}
    _, _, alone, _ = _walk(ctx, st, _dense(subject), standalone)
    imported, refused, deltas, trace = _walk(ctx, st, _dense(subject), found)
    assert refused == ()
    assert (
        _totals(alone) == _totals(deltas) == {"CONTRACT_LIABILITY": 700, "REFUND_LIABILITY": -700}
    )
    assert sum(d.amount_txn for d in deltas if d.reason_code == REASON) == 0
    assert {
        node.params["owner"]
        for node in trace.nodes
        if node.measure == "posting_delta" and node.params.get("reason") == REASON
    } == {intended}


@pytest.mark.parametrize(("kind", "source"), COLLIDING_SOURCES)
def test_colliding_contract_ids_resolve_the_encoded_owner_in_a_full_world(
    kind: str, source: str
) -> None:
    """The production regression on a valid chronology (inception 2025-01-01, opening
    2025-12-31): the two-contract world ``K/A`` (RECOMPUTE) / ``K%2FA`` (OPENING_BALANCES) folded
    through stage 07 gives both ``<contract>@<entity>`` openings; a TERMINATION or
    VARIABLE_CONSIDERATION component whose source head is ``K/A``'s encoded id resolves to
    ``K%2FA@US01`` and conserves 700 minor across the cutover with the owner named."""
    bundle = w.two_contracts()
    st, _ = fold.fold_trace(bundle, "ASC606")
    ctx = fold.book_context(bundle, "ASC606")
    found = onboarding.openings(st)
    intended = contract_entity_subject_key("K/A", ENTITY)
    collider = contract_entity_subject_key("K%2FA", ENTITY)
    assert found[intended].method == onboarding.RECOMPUTE
    assert found[collider].method == "OPENING_BALANCES_AT_CUTOVER"
    subject = f"{group_entity_subject_key(st.group_code, ENTITY)}/{kind}/{source}"
    assert onboarding.resolve(found, subject, ENTITY) is found[intended]
    imported, refused, deltas, trace = _walk(ctx, st, _dense(subject), found)
    assert refused == ()
    assert _totals(deltas) == {"CONTRACT_LIABILITY": 700, "REFUND_LIABILITY": -700}
    assert _rows(deltas)[2:] == [
        ("FY2026-P01", "FY2025-P12", REASON, subject, "CONTRACT_LIABILITY", 500),
        ("FY2026-P01", "FY2025-P12", REASON, subject, "REFUND_LIABILITY", -500),
    ]
    assert {
        node.params["owner"]
        for node in trace.nodes
        if node.measure == "posting_delta" and node.params.get("reason") == REASON
    } == {intended}

"""P6 rollforward ties (dev-guide §9.7 row P6; BUILD_SPEC PRP-4; ENGINE_SPEC_B §15.2.2 S15-R-07,
S15-INV-01; D-12).

Platform part in memory (``support.platform_props``): a generated world of ``support.prop_worlds``
is computed and closed as the platform closes it (the command computation, then the
``FX_REMEASUREMENT``, ``CLOSE_RELEASE`` and ``NETTING_RECLASS`` passes over the intents posted so
far). For every entity, book, currency view and presented balance — contract liability, contract
asset, unbilled receivable — opening + lines = closing per period, where the lines are the role's
posted subledger movements of the period (the engine's intents over all passes) plus, for the
contract liability, the billing lines the platform's invoice pipeline books (``BILLING_RECORDED``
amounts of the period: Dr receivable / Cr CONTRACT_LIABILITY, JET-02 — the ERP side the engine's
intents do not carry). The identity is asserted at the entity level because the ALG-02 netting
attribution is a pool per entity and period (the same pool law the metamorphic suite states): a
member contract's presented liability may be settled by another member's asset. ``net_position`` =
cumulative billed − cumulative revenue (D-12 overrides research 06's inverted sign, DG-OQ-08).

The ``contract_balance_rollforward`` report run itself (RPT-05 to RPT-07 through the report
framework, CTL-030) is the DB-bound part: it needs the database platform (``DbPlatform``, the
domain command handlers, the report framework's runs) and is NOT written here — DG-TST-07 keeps
database tests under ``tests/pg/``; it is the open PRP-4 item once the lane databases exist.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from support import platform_props, strategies
from support.prop_worlds import LineSpec, WorldSpec, bundle

pytestmark = pytest.mark.property

ROLES = ("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE")


def _ties(spec: WorldSpec, functional: bool) -> None:
    run = platform_props.close_run(bundle(spec, books=("ASC606", "LEGACY")))
    book = run.primary()
    entity = run.bundle.entities[0].code
    contracts = list(platform_props.iter_contracts(run.bundle))
    rows = platform_props.balance_rows(book)
    keys = platform_props.period_keys(run.bundle, entity)
    posted = [period for _, period in platform_props.periods_posted(run, platform_props.PRIMARY)]
    last = max((keys.index(period) for period in posted), default=-1)
    billings = {
        contract: platform_props.billings_by_period(run.bundle, contract=contract, entity=entity)
        for contract in contracts
    }
    for index, period_key in enumerate(keys[: last + 1]):
        for role in ROLES:
            opening = (
                sum(
                    platform_props.balance(
                        rows[(f"{c}@{entity}", keys[index - 1])], role, functional
                    )
                    for c in contracts
                )
                if index
                else 0
            )
            closing = sum(
                platform_props.balance(rows[(f"{c}@{entity}", period_key)], role, functional)
                for c in contracts
            )
            movement = sum(
                platform_props.role_movement(
                    run,
                    contract=c,
                    entity=entity,
                    period_key=period_key,
                    role=role,
                    functional=functional,
                )
                for c in contracts
            )
            billed = sum(billings[c].get(period_key, 0) for c in contracts)
            # S15-R-07: opening + lines = closing. A liability grows with billing credits and
            # shrinks with revenue debits (credit-positive); the asset captions are debit-positive.
            expected = billed - movement if role == "CONTRACT_LIABILITY" else movement
            assert closing - opening == expected, (
                period_key,
                role,
                "functional" if functional else "transaction",
                {"opening": opening, "closing": closing, "movement": movement, "billed": billed},
                {
                    c: platform_props.movement_by_kind(
                        run, contract=c, entity=entity, period_key=period_key, role=role
                    )
                    for c in contracts
                },
            )
    assert book.contract_version is not None
    columns = book.contract_version.columns
    # D-12: net_position = cumulative billed − cumulative revenue (DG-OQ-08).
    assert columns["net_position"] == columns["billed_cum"] - columns["revenue_cum"]


@platform_props.platform_settings()
@given(spec=strategies.world_specs())
def test_p06_rollforward_ties(spec: WorldSpec) -> None:
    """PROP:P6: opening + billings − revenue ± reclass ± FX remeasurement = closing for contract
    liability and contract asset (and the unbilled receivable caption), in transaction and in
    functional currency, per entity and period; ``net_position`` = billed − revenue (D-12)."""
    _ties(spec, functional=False)
    _ties(spec, functional=True)


# --- deterministic regression: the sealed history across a lock (T1-PRP7-CLOSE-HISTORY-1) --------

CL, CA = "CONTRACT_LIABILITY", "CONTRACT_ASSET"
P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
REVERSAL_AND_RECLASS = [
    ("NETTING_RECLASS", CA, "D", 1),
    ("NETTING_RECLASS", CL, "C", 1),
    ("NETTING_RECLASS_REVERSAL", CA, "C", 1),
    ("NETTING_RECLASS_REVERSAL", CL, "D", 1),
]


def _lines(run: platform_props.CloseRun, period_key: str) -> list[tuple[str, str, str, int]]:
    """(entry kind, role, side, minor units) of the primary book's intents posted to the period."""
    found = []
    for _, _, intent in platform_props.intents(run, platform_props.PRIMARY):
        if intent.posting_period_key != period_key:
            continue
        for line in intent.lines:
            found.append((intent.entry_kind, line.account_role, line.side, line.amount_txn))
    return sorted(found)


def _cumulative(role: str, run: platform_props.CloseRun, keys: list[str], through: str) -> int:
    """Debit-positive cumulative posting of ``role`` through ``through`` (inclusive): the run's
    sealed history plus its own intents, both limited to posting periods up to ``through`` — the
    claim is bounded to the period whose presented caption it is compared with (Codex 0110 W2)."""
    limit = keys.index(through)
    total = sum(
        item.amount_txn
        for item in run.bundle.posted
        if item.book_code == platform_props.PRIMARY
        and item.account_role == role
        and keys.index(item.period_key) <= limit
    )
    for _, _, intent in platform_props.intents(run, platform_props.PRIMARY):
        if keys.index(intent.posting_period_key) > limit:
            continue
        for line in intent.lines:
            if line.account_role == role:
                total += line.amount_txn if line.side == "D" else -line.amount_txn
    return total


def _nodes(run: platform_props.CloseRun, period_key: str) -> set[str]:
    """The trace node ids the period's netting lines cite (``posting_target:…:<period>``)."""
    return {
        line.trace_node_id
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY)
        if intent.posting_period_key == period_key
        and intent.entry_kind.startswith("NETTING_RECLASS")
        for line in intent.lines
    }


def test_close_run_reverses_the_locked_period_reclass_from_the_sealed_history() -> None:
    """T1-PRP7-CLOSE-HISTORY-1 (Codex production-20260922-0031 §1–§4): one USD ratable line of one
    cent, recognised in January and unbilled, so January's netting reclass is Dr CONTRACT_ASSET
    0.01 / Cr CONTRACT_LIABILITY 0.01. January is locked with its journal run sealed as ``posted``.
    S14-R-07: the reversal target of February is the negation of the reclass ACTUALLY POSTED for
    January, dated 1 February — so the sealed history must survive the close passes. Through the
    actual ``close_run`` seam: nothing posts into locked January; February carries the reversal
    (Dr CL / Cr CA) and its own reclass (Dr CA / Cr CL); a repeat pass over the sealed February
    posts nothing into January or February and only March's reversal and reclass; the gross
    postings tie to the presented captions — cumulative CONTRACT_ASSET 0.01 and CONTRACT_LIABILITY
    0 through February and through March, each bounded to its own period and read from that run's
    own balance rows (Codex 0110 W2). The earlier helper dropped the sealed January reclass and
    posted no reversal: CONTRACT_ASSET 0.02 / CONTRACT_LIABILITY −0.01 against a presented 0.01 /
    0 — the net position alone passes both, so the gross ties are asserted. Dates (W1, Codex
    production-20260922-0133): a posting intent carries its posting period, not a calendar date,
    and the trace nodes it cites (``posting_target:…:<period>``) carry none either — so this test
    asserts the periods and the node ids only. The S14-R-07 calendar dates are stage-14 delta
    dates, asserted at the delta level by
    ``tests/engine/s14_posting/test_s14_deltas.py::test_s14_r07_netting_reclass_and_reversal``:
    the January reclass on 31 January, February's reversal on 1 February and reclass on 28
    February, March's reversal on 1 March and reclass on 31 March, and April's reversal on 1
    April (no further claim is made here)."""
    spec = WorldSpec("USD", (("K-1", (LineSpec("POB-01", "DAILY", 1, 1, 1, 0, 1),)),), ())
    before = platform_props.close_run(platform_props.machine_bundle(spec, months=24))
    keys = platform_props.period_keys(before.bundle, "US01")
    assert _lines(before, P01) == [
        ("NETTING_RECLASS", CA, "D", 1),
        ("NETTING_RECLASS", CL, "C", 1),
        ("REVENUE_RECOGNITION", CL, "D", 1),
        ("REVENUE_RECOGNITION", "REVENUE", "C", 1),
    ]
    sealed = platform_props.sealed_through(before.outputs, keys, P01)
    assert {item.period_key for item in sealed} == {P01}
    after = platform_props.close_run(
        platform_props.machine_bundle(spec, period_states={P01: "closed"}, posted=sealed, months=24)
    )
    # (i) immutability: nothing posts into the locked period
    assert _lines(after, P01) == []
    # (ii) February: the reversal of January's ACTUALLY POSTED reclass, then February's own reclass;
    # the lines cite February's posting-target nodes (W1: period provenance at this seam)
    assert _lines(after, P02) == REVERSAL_AND_RECLASS
    assert _nodes(after, P02) == {
        f"posting_target:K-1/POB-01/{kind}/{role}:{P02}"
        for kind in ("NETTING_RECLASS", "NETTING_RECLASS_REVERSAL")
        for role in (CA, CL)
    }
    # (iv) gross ties through February against February's presented captions (bounded, W2)
    rows = platform_props.balance_rows(after.primary())
    assert _cumulative(CA, after, keys, P02) == 1 == rows[("K-1@US01", P02)]["contract_asset_txn"]
    assert (
        _cumulative(CL, after, keys, P02) == 0 == -rows[("K-1@US01", P02)]["contract_liability_txn"]
    )
    # (iii) repeat-pass idempotency: seal February too, lock it, run again
    sealed_2 = platform_props.merge_sealed(
        sealed, platform_props.sealed_through(after.outputs, keys, P02)
    )
    again = platform_props.close_run(
        platform_props.machine_bundle(
            spec, period_states={P01: "closed", P02: "closed"}, posted=sealed_2, months=24
        )
    )
    assert _lines(again, P01) == [] and _lines(again, P02) == []
    assert _lines(again, P03) == REVERSAL_AND_RECLASS
    assert _nodes(again, P03) == {
        f"posting_target:K-1/POB-01/{kind}/{role}:{P03}"
        for kind in ("NETTING_RECLASS", "NETTING_RECLASS_REVERSAL")
        for role in (CA, CL)
    }
    # gross ties through March against the REPEAT run's own presented captions (fresh rows, W2)
    rows_again = platform_props.balance_rows(again.primary())
    assert (
        _cumulative(CA, again, keys, P03)
        == 1
        == rows_again[("K-1@US01", P03)]["contract_asset_txn"]
    )
    assert (
        _cumulative(CL, again, keys, P03)
        == 0
        == -rows_again[("K-1@US01", P03)]["contract_liability_txn"]
    )

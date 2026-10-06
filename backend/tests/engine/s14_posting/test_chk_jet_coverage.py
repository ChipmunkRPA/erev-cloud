"""JET template coverage and conservation over the END-11 / END-12 worlds (BUILD_SPEC END-11,
END-12; ENGINE_SPEC_B Table 14-A, S14-R-12, S14-R-13, S14-INV-01; lane ENG-C8).

Positive and negative coverage: for every CHK world the set of E-29 entry kinds the public path
posts (compute and the three close passes) equals the set its templates imply — a template whose
triggers the world does not carry posts nothing (no BILLING under ERP, no FX_REMEASUREMENT in a
single-currency world, no LOSS_PROVISION without a loss unit, no DEPOSIT without a deposit) and
every template the world does carry posts. Conservation: every entry balances in both currencies
(per event, S14-INV-01); a REVENUE_RECOGNITION entry's lines carry the obligation of its subject
(per obligation, S14-R-13); and, where the version date is a period end, the signed REVENUE lines
posted through that period equal the obligation's ``revenue_cum`` and the contract's (T-CON-08,
T-CON-11). No database (DG-TST-18).
"""

from __future__ import annotations

from datetime import date

import pytest
from support.answer_keys.runners import obligation_subject_key
from support.jet_lines import Posted, run_checkpoint

RECOGNITION = "REVENUE_RECOGNITION"
# (key, checkpoint) -> the entry kinds the world's templates post through compute and the passes.
WORLDS: dict[tuple[str, str], frozenset[str]] = {
    ("JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY", "june-close-after-criteria-met"): (
        frozenset({"DEPOSIT", RECOGNITION})
    ),
    ("JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING", "january-close"): frozenset(
        {"BILLING", RECOGNITION}
    ),
    ("JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE", "march-close"): frozenset(
        {"BILLING", RECOGNITION}
    ),
    ("JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE", "march-close"): frozenset(
        {"BILLING", RECOGNITION}
    ),
    ("JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY", "q2-close"): frozenset(
        {"REFUND_LIABILITY", RECOGNITION}
    ),
    ("JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP", "year-3-close"): frozenset(
        {"NETTING_RECLASS", "NETTING_RECLASS_REVERSAL", RECOGNITION}
    ),
    ("JE-CHK-130-S8-CONTRACT-COSTS-EX2-AMORTISATION", "year-end-2032"): frozenset(
        {
            "CONTRACT_COST_AMORTIZATION",
            "CONTRACT_COST_CAPITALIZATION",
            "NETTING_RECLASS",
            "NETTING_RECLASS_REVERSAL",
            RECOGNITION,
        }
    ),
    ("JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL", "ifrs15-period-2"): frozenset(
        {
            "CONTRACT_COST_AMORTIZATION",
            "CONTRACT_COST_CAPITALIZATION",
            "CONTRACT_COST_IMPAIRMENT",
            RECOGNITION,
        }
    ),
    ("JE-CHK-131-S8-EXPEDIENT-ONE-YEAR-COMMISSION-EXPENSED", "january-close"): frozenset(
        {RECOGNITION}
    ),
    ("JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE", "year-end-2028"): frozenset(
        {"LOSS_PROVISION", RECOGNITION}
    ),
    ("CPC-CHK-133-S3-EX32", "end-of-month-1"): frozenset({"CONSIDERATION_PAYABLE", RECOGNITION}),
    ("POB-CHK-134-S2-WARRANTY-OWN", "end-of-month-24"): frozenset(
        {"WARRANTY_ACCRUAL", RECOGNITION}
    ),
    ("NCC-CHK-135-S3-EX31", "end-of-january"): frozenset({"NONCASH_CONSIDERATION", RECOGNITION}),
    ("JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION", "transfer"): frozenset(
        {"FINANCING_INTEREST", RECOGNITION}
    ),
    ("SFC-CHK-136-S3-EX29-ANNUAL", "transfer"): frozenset({"FINANCING_INTEREST", RECOGNITION}),
    ("SFC-CHK-137-S3-EX28-CASEB", "end-of-month-60"): frozenset(
        {"FINANCING_INTEREST", "NETTING_RECLASS", "NETTING_RECLASS_REVERSAL", RECOGNITION}
    ),
    ("JE-CHK-138-S1-EX2-IMPLICIT-PRICE-CONCESSION-RECEIVABLE-CONTRA", "march-close"): frozenset(
        {"BILLING", "RECEIVABLE_CONTRA", RECOGNITION}
    ),
    ("MOD-CHK-112", "after-credit-memo"): frozenset(
        {
            "CONTRACT_COST_AMORTIZATION",
            "CONTRACT_COST_CAPITALIZATION",
            "REFUND_LIABILITY",
            RECOGNITION,
        }
    ),
    ("ENT-CHK-070-INTERCOMPANY-PAIR-PERFORMING-ENTITY", "end-of-p1"): frozenset(
        {"INTERCOMPANY", RECOGNITION}
    ),
    ("FX-CHK-084-A-REFUND-LIABILITY-REMEASURED", "may-close"): frozenset(
        {"FX_REMEASUREMENT", "REFUND_LIABILITY", RECOGNITION}
    ),
}
# The E-29 kinds no END-11 / END-12 world posts: their templates are witnessed elsewhere (JET-15
# in the LEGACY parity worlds, JET-05c / JET-07 / JET-08 in the RET, MR and MOD keys) or, for
# CREDIT_MEMO and SALES_TAX, are ERP-side kinds the engine never emits.
NEVER_HERE = frozenset(
    {
        "CREDIT_MEMO",
        "RETURN_ASSET",
        "PRE_STANDARD_REVENUE",
        "SALES_TAX",
        "MANUAL_ADJUSTMENT",
        "REVERSAL",
    }
)
IDS = [f"{key}::{checkpoint}" for key, checkpoint in WORLDS]


@pytest.fixture(scope="module")
def posted_worlds() -> dict[tuple[str, str], Posted]:
    return {world: run_checkpoint(*world) for world in WORLDS}


def _kinds(posted: Posted) -> frozenset[str]:
    return frozenset(
        intent.entry_kind
        for output in posted.outputs
        for intent in posted.book(output).posting_intents
    )


@pytest.mark.parametrize("world", list(WORLDS), ids=IDS)
def test_world_posts_exactly_its_templates(
    world: tuple[str, str], posted_worlds: dict[tuple[str, str], Posted]
) -> None:
    posted = posted_worlds[world]
    assert _kinds(posted) == WORLDS[world]
    assert not (_kinds(posted) & NEVER_HERE)


def test_every_end_11_12_template_is_witnessed(
    posted_worlds: dict[tuple[str, str], Posted],
) -> None:
    """Positive coverage across the worlds: the entry kinds of every END-11 / END-12 template."""
    witnessed = frozenset().union(*(_kinds(p) for p in posted_worlds.values()))
    assert witnessed >= {
        "DEPOSIT",  # JET-01b
        "BILLING",  # JET-03
        "REFUND_LIABILITY",  # JET-04b
        "RECEIVABLE_CONTRA",  # JET-04c
        "NETTING_RECLASS",
        "NETTING_RECLASS_REVERSAL",  # JET-06
        "CONTRACT_COST_CAPITALIZATION",  # JET-09a, 09a′
        "CONTRACT_COST_AMORTIZATION",  # JET-09b, 09e
        "CONTRACT_COST_IMPAIRMENT",  # JET-09c, 09d
        "FX_REMEASUREMENT",  # JET-10d
        "FINANCING_INTEREST",  # JET-11a, 11b
        "LOSS_PROVISION",  # JET-12
        "INTERCOMPANY",  # JET-13
        "CONSIDERATION_PAYABLE",  # JET-14
        "WARRANTY_ACCRUAL",  # JET-16
        "NONCASH_CONSIDERATION",  # JET-17
        RECOGNITION,  # JET-02, JET-04a
    }


@pytest.mark.parametrize("world", list(WORLDS), ids=IDS)
def test_every_entry_balances_and_names_its_obligation(
    world: tuple[str, str], posted_worlds: dict[tuple[str, str], Posted]
) -> None:
    """Per event: every intent balances in both currencies (S14-INV-01). Per obligation: a
    REVENUE_RECOGNITION entry is the obligation's own — its subject is the obligation subject key
    and every line carries that obligation's dimensions (S14-R-12, S14-R-13)."""
    posted = posted_worlds[world]
    posted.entries_balance()
    for output in posted.outputs:
        for intent in posted.book(output).posting_intents:
            if intent.entry_kind != RECOGNITION:
                continue
            for line in intent.lines:
                dims = line.dimensions
                assert intent.subject_key == obligation_subject_key(
                    dims["contract_key"], dims["obligation_key"]
                ), intent.entry_key


def _period_end_worlds() -> list[tuple[str, str]]:
    """The worlds whose version date (``known_at``) is a period end, where the T-CON-08 / T-CON-11
    ``revenue_cum`` and the posted REVENUE lines through that period are the same cumulative."""
    return [
        ("JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY", "june-close-after-criteria-met"),
        ("JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE", "march-close"),
        ("JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE", "march-close"),
        ("JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP", "year-3-close"),
        ("JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL", "ifrs15-period-2"),
        ("JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE", "year-end-2028"),
        ("CPC-CHK-133-S3-EX32", "end-of-month-1"),
        ("SFC-CHK-136-S3-EX29-ANNUAL", "transfer"),
        ("SFC-CHK-137-S3-EX28-CASEB", "end-of-month-60"),
        ("ENT-CHK-070-INTERCOMPANY-PAIR-PERFORMING-ENTITY", "end-of-p1"),
    ]


@pytest.mark.parametrize("world", _period_end_worlds(), ids=lambda w: f"{w[0]}::{w[1]}")
def test_revenue_lines_conserve_the_version_and_obligation_cumulatives(
    world: tuple[str, str], posted_worlds: dict[tuple[str, str], Posted]
) -> None:
    """Σ signed REVENUE-role lines (credits positive) of the posting periods ending on or before the
    version date equal the contract version ``revenue_cum`` (contract-level lines such as the
    JET-14 release Dr REVENUE included) and, per obligation dimension, the obligation version
    ``revenue_cum``. Worlds whose version date falls inside a period (CHK-023, 025, 130, 131X,
    134, 135, 136 monthly, 138, 112, 084) compare a partial period and are covered by the
    answer-key runner's to-date comparison instead."""
    posted = posted_worlds[world]
    known: date = posted.bundle.known_at.date()
    ends = {
        (entity.code, period.period_key): period.end_date
        for entity in posted.bundle.entities
        for period in entity.periods
    }
    assert known in set(ends.values())
    total = 0
    per_obligation: dict[str, int] = {}
    for output in posted.outputs:
        for intent in posted.book(output).posting_intents:
            if ends[(intent.entity, intent.posting_period_key)] > known:
                continue
            for line in intent.lines:
                if line.account_role != "REVENUE":
                    continue
                signed = line.amount_txn if line.side == "C" else -line.amount_txn
                total += signed
                obligation = line.dimensions.get("obligation_key")
                if obligation is not None:
                    per_obligation[obligation] = per_obligation.get(obligation, 0) + signed
    assert total == posted.version("revenue_cum")
    versions = {
        v.columns["obligation_key"]: v.columns["revenue_cum"]
        for v in posted.book(posted.compute).obligation_versions
    }
    assert per_obligation == {key: value for key, value in versions.items() if value != 0}

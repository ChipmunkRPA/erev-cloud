"""The billing mode is read per period (item PINP-PERIOD-VALUE-1; ENGINE_SPEC_B S10-R-06; POLICIES
POL-004, POL-123).

POL-123 ``balance.position_invoice_basis`` is period-pinned and has no framework default: it is
"derived" from POL-004 where no version holds it. Since the orchestrator resolves each period at
its own instant, a first POL-123 version that takes effect in a later period leaves the earlier
periods without a POL-123 value. ``billing_mode_at`` read POL-123 for a period whenever the bundle
held ANY POL-123 value, and the resolver refused the earlier period: "policy
balance.position_invoice_basis has no value for the requested scope (CV-17)". It now asks whether
the PERIOD holds the value and reads POL-004 there otherwise. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Any

import erev_engine
import pytest
from erev_engine.bundle import (
    BookInput,
    EntityInput,
    InputBundle,
    OutputBundle,
    ResolvedPolicyInput,
)
from erev_engine.stages.state import (
    BILLING_BASIS_POLICY,
    BILLING_POSTING_POLICY,
    PolicyResolver,
    billing_mode_at,
)
from support import bundles
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

FROM = "FY2026-P06"  # the first period the POL-123 version holds


def with_basis(book: BookInput, entity: EntityInput, value: str, *, first: str) -> BookInput:
    """``book`` with POL-123 ``value`` for the periods of ``entity`` from ``first`` on."""
    rows = [
        ResolvedPolicyInput(
            BILLING_BASIS_POLICY,
            "PERIOD",
            f"{entity.code}@{item.period_key}",
            value,
            "T",
            "V1",
            "P",
        )
        for item in entity.periods
        if item.period_key >= first
    ]
    policies = sorted([*book.policies, *rows], key=lambda p: (p.code, p.scope, p.subject_key))
    return dataclasses.replace(book, policies=tuple(policies))


def test_s10_r06_a_period_without_a_pol_123_value_reads_pol_004() -> None:
    entity = bundles.entity(start=date(2026, 1, 1), months=12)
    book = with_basis(
        bundles.book("ASC606", entity=entity), entity, "UNCONDITIONAL_INVOICES_ONLY", first=FROM
    )
    policies = PolicyResolver(book.policies)
    assert policies.value(BILLING_POSTING_POLICY, entity=entity.code, period="FY2026-P05") == "ERP"
    assert billing_mode_at(policies, entity, date(2026, 5, 31)) == "ERP"  # POL-004
    assert billing_mode_at(policies, entity, date(2026, 6, 1)) == "ENGINE"  # POL-123
    # the bundle holds POL-123, but not for the periods before its first version
    assert policies.has(BILLING_BASIS_POLICY)
    assert not policies.has(BILLING_BASIS_POLICY, entity=entity.code, period="FY2026-P05")
    assert policies.has(BILLING_BASIS_POLICY, entity=entity.code, period=FROM)
    with pytest.raises(ValueError, match="pass entity and period together"):
        policies.has(BILLING_BASIS_POLICY, entity=entity.code)


def _measured(output: OutputBundle) -> tuple[Any, ...]:
    """Every column of the contract version but the policies it records, every obligation
    version, the balances and the posting intents of the first book."""
    book = output.books[0]
    assert book.contract_version is not None
    contract = {
        name: value
        for name, value in book.contract_version.columns.items()
        if name != "pinned_policies"
    }
    obligations = [(item.subject_key, item.columns) for item in book.obligation_versions]
    intents = [
        (
            intent.posting_period_key,
            intent.entry_kind,
            [(line.account_role, line.side, line.amount_txn) for line in intent.lines],
        )
        for intent in book.posting_intents
    ]
    return contract, obligations, intents


def _stp1() -> InputBundle:
    loaded = load(ANSWER_KEY_ROOT / "stp1" / "STP1-S1-EX2.yaml")
    (bundle,) = runners._build_checkpoint_bundles(loaded)[0].bundles
    return bundle


def test_a_bundle_with_pol_123_from_a_later_period_computes_the_billing_of_an_earlier_one() -> None:
    """FASB Example 2 (STP1-S1-EX2: a billing line of 15 January 2026 under POL-004 ``ENGINE``)
    with a POL-123 value from FY2026-P06 on: the January line is dated by POL-004 and the
    computation gives the key's own figures. Before the repair it was refused (CV-17)."""
    bundle = _stp1()
    (book,) = bundle.books
    (entity,) = bundle.entities
    assert not any(policy.code == BILLING_BASIS_POLICY for policy in book.policies)
    later = dataclasses.replace(
        bundle, books=(with_basis(book, entity, "UNCONDITIONAL_INVOICES_ONLY", first=FROM),)
    )
    own, found = erev_engine.compute(bundle), erev_engine.compute(later)
    assert _measured(found) == _measured(own)
    assert [d.code for d in found.diagnostics] == [d.code for d in own.diagnostics]

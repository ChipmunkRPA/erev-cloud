"""``bundles.onboarding_pins`` — POL-210 at level C for a D-31 mode (a) migration (lane FIX-E,
FLMG-ONBOARDING-METHOD-PIN-1; 05 RCP-15 rev 1.36; dev-guide DG-KRN-REG-03 rev 1.80; ENGINE_SPEC
§7.1 "resolved ``onboarding.method`` (pinned from the import batch onto the contract, level C)";
POLICIES POL-210 "legacy database import per D-31: mode (a) ``OPENING_BALANCES_AT_CUTOVER``";
S07-R-11 ``reason = LEGACY_MIGRATION``).

The registry has no level for an import batch (``allowed_levels`` of ``onboarding.method`` is
empty), so the bundle builder answered the framework default ``RECOMPUTE_FROM_INCEPTION`` and the
engine ignored the imported balances — WLD-F-15 Contract 1 was captured with revenue 0.00 instead
of 295.69 (PRD WLD-X-27; ENGINE_SPEC EX-07-A). The builder now names the contracts a legacy
migration opened from their own stream: the fact is the contract's ``OPENING_BALANCE_ESTABLISHED``
event, never the ``migration_batch`` row, so a replay resolves the same value. The database
witnesses are in ``tests/pg/test_migration_capture_pg.py``. CPU only.
"""

from __future__ import annotations

from datetime import date

from erev_api.domain.contracts import bundles
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine.bundle import EventInput
from erev_engine.stages.state import PolicyResolver
from support.bundles import event

BATCH = "01a0f0ff-684d-7de2-9744-8186d008a23f"
INCEPTION = date(2023, 1, 1)
CUTOVER = date(2023, 1, 31)


def _opening(contract: str, version: int, reason: str, batch: str | None = BATCH) -> EventInput:
    payload: dict[str, object] = {"reason": reason, "cutover_date": CUTOVER.isoformat()}
    if batch is not None:
        payload["migration_batch_id"] = batch
    return event(contract, version, "OPENING_BALANCE_ESTABLISHED", CUTOVER, payload)


def test_a_legacy_migration_opening_pins_its_own_contract_and_names_the_event() -> None:
    events = [
        event("Contract 1", 1, "CONTRACT_BOOKED", INCEPTION, {}),
        event("Contract 1", 2, "CONTRACT_ACTIVATED", INCEPTION, {}),
        _opening("Contract 1", 3, "LEGACY_MIGRATION"),
        event("Contract 2", 1, "CONTRACT_BOOKED", INCEPTION, {}),
        event("Contract 2", 2, "ESTIMATE_CHANGED", INCEPTION, {}),
        event("Contract 2", 3, "CONTRACT_ACTIVATED", INCEPTION, {}),
        _opening("Contract 2", 4, "LEGACY_MIGRATION"),
        # the other opening-balance reasons take their method from their own import batch
        # (BUILD_SPEC BS3-D-25; S07-R-13) — this pin does not decide them
        _opening("K-ONB", 3, "SYSTEM_ONBOARDING", None),
        _opening("K-BC", 3, "BUSINESS_COMBINATION", None),
        # a contract without an opening balance has no pin: the registry value governs it
        event("K-NATIVE", 1, "CONTRACT_BOOKED", INCEPTION, {}),
        event("K-NATIVE", 2, "CONTRACT_ACTIVATED", INCEPTION, {}),
    ]
    # the source reference is the contract's own opening event (CV-22 key) — an immutable fact
    assert bundles.onboarding_pins(events) == {
        "Contract 1": "Contract 1/EV-000003",
        "Contract 2": "Contract 2/EV-000004",
    }
    assert bundles.onboarding_pins([]) == {}


def test_the_pin_reads_the_event_only_never_the_batch() -> None:
    """The same stream gives the same pin whatever the payload's batch id is, and a payload that
    names no batch at all still pins — nothing of the ``migration_batch`` row (status, profile,
    parameters) can change the resolved value, so a replay resolves what the first run did."""
    for batch in (BATCH, "00000000-0000-0000-0000-000000000001", None):
        events = [
            event("Contract 1", 1, "CONTRACT_BOOKED", INCEPTION, {}),
            event("Contract 1", 2, "CONTRACT_ACTIVATED", INCEPTION, {}),
            _opening("Contract 1", 3, "LEGACY_MIGRATION", batch),
        ]
        assert bundles.onboarding_pins(events) == {"Contract 1": "Contract 1/EV-000003"}


def test_the_pin_is_pol_210s_literal_at_contract_scope_and_the_engine_resolves_it() -> None:
    """The literals are POL-210's; a CONTRACT-scope row answers for its own contract only and the
    GROUP-scope registry value keeps governing the others (CV-17: OBLIGATION, CONTRACT, ENTITY,
    then GROUP)."""
    spec = POLICY_PARAMETERS[bundles.ONBOARDING_METHOD]
    assert spec.pol_id == "POL-210" and spec.pin == "K"
    assert bundles.OPENING_BALANCES_AT_CUTOVER in spec.value_schema["enum"]
    assert spec.default_asc606 == "RECOMPUTE_FROM_INCEPTION"
    assert spec.allowed_levels == frozenset()  # no registry level names an import batch
    rows = (
        bundles._policy(
            bundles.ONBOARDING_METHOD,
            "CONTRACT",
            "Contract 1",
            bundles.OPENING_BALANCES_AT_CUTOVER,
            "C",
            "Contract 1/EV-000003",
            "K",
        ),
        bundles._policy(
            bundles.ONBOARDING_METHOD, "GROUP", "", spec.default_asc606, "DEFAULT", "POL-210", "K"
        ),
    )
    resolver = PolicyResolver(rows)
    pinned = resolver.resolved(bundles.ONBOARDING_METHOD, contract="Contract 1")
    assert (pinned.value, pinned.scope, pinned.level) == (
        "OPENING_BALANCES_AT_CUTOVER",
        "CONTRACT",
        "C",
    )
    assert pinned.source_ref == "Contract 1/EV-000003"
    other = resolver.resolved(bundles.ONBOARDING_METHOD, contract="K-NATIVE")
    assert (other.value, other.scope, other.level) == (
        "RECOMPUTE_FROM_INCEPTION",
        "GROUP",
        "DEFAULT",
    )

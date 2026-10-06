"""Stage registry: ``STAGES`` and ``BOUNDARY_HANDLERS`` (ENGINE_SPEC §0.2, §0.3, §0.10; EKC-6).

``STAGES`` holds the built stages among 02 to 12, 14 and 15 in Table 0.2-A order; stage 01 runs
before the book loop and stage 13 is the book loop itself (ENGINE_SPEC_B §0.4).
``BOUNDARY_HANDLERS`` maps the E-03 literals of Table 0.3-A to their entry functions. The item that
builds a stage registers it here, and ``tests/engine/kernel/test_stage_registry.py`` lists what is
still pending (B3-BS2-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.formulas import FORMULAS

__all__ = ["BOUNDARY_EVENT_TYPES", "BOUNDARY_HANDLERS", "STAGES", "StageSpec"]

# Table 0.3-A: E-03 literals folded by a boundary handler. The first CONTRACT_BOOKED of each member
# is absorbed by the inception fold (CV-10); every other event is a measure event (CV-11).
BOUNDARY_EVENT_TYPES: Final = frozenset(
    {
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_CRITERIA_MET",
        "SIGNIFICANT_CHANGE_FLAGGED",
        "CONTRACT_AMENDED",
        "CONTRACT_TERMINATED",
        "REGROUPED",
        "LINE_ATTRIBUTES_CHANGED",
        "MATERIAL_RIGHT_EXERCISED",
        "OPENING_BALANCE_ESTABLISHED",
        "ESTIMATE_CHANGED",
    }
)

# Stages the book loop runs (ENGINE_SPEC §0.10), in Table 0.2-A order.
_BOOK_LOOP_STAGES: Final = ("02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12")
_BOOK_LOOP_STAGES_LATE: Final = ("14", "15")
_PACKAGE: Final = re.compile(r"s(\d{2})_[a-z0-9]+(?:_[a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class StageSpec:
    """One registered stage (ENGINE_SPEC §0.10): number, package, entry, policy keys, formulas."""

    stage: str  # "02" to "12", "14" or "15"
    package: str  # for example "s09_recognition" (Table 0.2-A)
    entry: Callable[..., object]  # run(ctx, state, tb) -> state
    policy_keys: tuple[str, ...]  # STAGE_POLICY_KEYS entry (Table 0.10-A, Table 13-A), sorted
    formula_ids: tuple[str, ...]  # FORMULAS keys the stage emits, sorted

    def __post_init__(self) -> None:
        if self.stage not in _BOOK_LOOP_STAGES + _BOOK_LOOP_STAGES_LATE:
            raise ValueError(f"stage {self.stage!r} is not one of stages 02 to 12, 14 and 15")
        package = _PACKAGE.fullmatch(self.package)
        if package is None or package.group(1) != self.stage:
            raise ValueError(f"package {self.package!r} does not name stage {self.stage}")
        for name, keys in (("policy_keys", self.policy_keys), ("formula_ids", self.formula_ids)):
            if list(keys) != sorted(set(keys)):
                raise ValueError(f"{name} of stage {self.stage} must be sorted and unique")
        unknown = [formula_id for formula_id in self.formula_ids if formula_id not in FORMULAS]
        if unknown:
            raise ValueError(f"stage {self.stage} names unregistered formulas {unknown}")

    def run(self, ctx: object, state: object, tb: object) -> object:
        """Call the stage entry as the book loop does (ENGINE_SPEC_B §13.2.1)."""
        return self.entry(ctx, state, tb)


# The stage packages are imported after the constants above, because stage 01 reads
# BOUNDARY_EVENT_TYPES while this package initialises.
from erev_engine.stages import (  # noqa: E402
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
    s06_modifications,
    s07_onboarding,
    s08_estimates_late_events,
    s09_recognition,
    s10_billing_balances,
    s11_costs_loss,
    s12_fx_entities,
    s14_posting,
    s15_disclosures,
)

# Table 0.3-A handlers (ENB-13). Stages 06 and 08 take keyword arguments the fold binds: stage 06
# ``identified`` and ``price_at``, stage 08 ``price_at`` (L2-3-Q-1; L1-3-Q-26). No module reads the
# mapping while the stage packages initialise, so it is built once, read-only (DG-ENG-08).
BOUNDARY_HANDLERS: Final[Mapping[str, Callable[..., object]]] = MappingProxyType(
    {
        "COLLECTIBILITY_ASSESSED": s02_contract_identification.apply,
        "CONTRACT_CRITERIA_MET": s02_contract_identification.apply,
        "SIGNIFICANT_CHANGE_FLAGGED": s02_contract_identification.apply,
        "CONTRACT_AMENDED": s06_modifications.apply,
        "CONTRACT_TERMINATED": s06_modifications.apply,
        "REGROUPED": s06_modifications.apply,
        "LINE_ATTRIBUTES_CHANGED": s06_modifications.apply,
        "MATERIAL_RIGHT_EXERCISED": s06_modifications.apply,
        "OPENING_BALANCE_ESTABLISHED": s07_onboarding.apply,
        "ESTIMATE_CHANGED": s08_estimates_late_events.apply,
    }
)

STAGES: Final[tuple[StageSpec, ...]] = (
    StageSpec(
        "02",
        "s02_contract_identification",
        s02_contract_identification.run,
        s02_contract_identification.POLICY_KEYS,
        s02_contract_identification.FORMULA_IDS,
    ),
    StageSpec(
        "03",
        "s03_pob_builder",
        s03_pob_builder.run,
        s03_pob_builder.POLICY_KEYS,
        s03_pob_builder.FORMULA_IDS,
    ),
    StageSpec(
        "04",
        "s04_transaction_price",
        s04_transaction_price.run,
        s04_transaction_price.POLICY_KEYS,
        s04_transaction_price.FORMULA_IDS,
    ),
    StageSpec(
        "05",
        "s05_allocation",
        s05_allocation.run,
        s05_allocation.POLICY_KEYS,
        s05_allocation.FORMULA_IDS,
    ),
    # Stages 06 to 08 are boundary handlers: their entry is ``apply(ctx, st, ev, tb)``, which the
    # boundary fold calls per event (CV-11), not ``run``.
    StageSpec(
        "06",
        "s06_modifications",
        s06_modifications.apply,
        s06_modifications.POLICY_KEYS,
        s06_modifications.FORMULA_IDS,
    ),
    StageSpec(
        "07",
        "s07_onboarding",
        s07_onboarding.apply,
        s07_onboarding.POLICY_KEYS,
        s07_onboarding.FORMULA_IDS,
    ),
    StageSpec(
        "08",
        "s08_estimates_late_events",
        s08_estimates_late_events.apply,
        s08_estimates_late_events.POLICY_KEYS,
        s08_estimates_late_events.FORMULA_IDS,
    ),
    StageSpec(
        "09",
        "s09_recognition",
        s09_recognition.run,
        s09_recognition.POLICY_KEYS,
        s09_recognition.FORMULA_IDS,
    ),
    StageSpec(
        "10",
        "s10_billing_balances",
        s10_billing_balances.run,
        s10_billing_balances.POLICY_KEYS,
        s10_billing_balances.FORMULA_IDS,
    ),
    StageSpec(
        "11",
        "s11_costs_loss",
        s11_costs_loss.run,
        s11_costs_loss.POLICY_KEYS,
        s11_costs_loss.FORMULA_IDS,
    ),
    StageSpec(
        "12",
        "s12_fx_entities",
        s12_fx_entities.run,
        s12_fx_entities.POLICY_KEYS,
        s12_fx_entities.FORMULA_IDS,
    ),
    StageSpec(
        "14",
        "s14_posting",
        s14_posting.run,
        s14_posting.POLICY_KEYS,
        s14_posting.FORMULA_IDS,
    ),
    # EDS-1: the book loop binds the stage 09 state as ``recognition`` (L3-2-Q-26).
    StageSpec(
        "15",
        "s15_disclosures",
        s15_disclosures.run,
        s15_disclosures.POLICY_KEYS,
        s15_disclosures.FORMULA_IDS,
    ),
)

"""Pure deal-preview computation boundary, with no contract or posting persistence.

The worker must resolve authorized products, approved SSP and policies into the proposed
contract's bundle before calling this boundary. It retains both fingerprints and pinned
references with the preview record; this module never creates a production contract.
"""

from dataclasses import dataclass, replace

import erev_engine
from erev_engine.bundle import InputBundle, OutputBundle


@dataclass(frozen=True, slots=True)
class DealComputation:
    input: InputBundle
    output: OutputBundle
    input_sha256: str
    result_sha256: str


def compute(bundle: InputBundle) -> DealComputation:
    """Use the complete revenue engine, retaining allocation, schedules, trace and findings.

    A proposed deal has exactly one new contract and no posted amounts. Reject an existing
    ledger baseline rather than silently removing it to produce an apparently valid preview.
    Engine diagnostics/refusals propagate unchanged; no fallback arithmetic is provided.
    """
    if len(bundle.contracts) != 1:
        raise ValueError("A deal preview requires exactly one proposed contract.")
    if bundle.posted:
        raise ValueError("A proposed deal cannot include posted ledger amounts.")
    dry_run = replace(bundle, trigger="DRY_RUN")
    output = erev_engine.compute(dry_run)
    input_sha256 = dry_run.sha256()
    if output.input_sha256 != input_sha256:
        raise ValueError("The engine result does not match the preview input.")
    return DealComputation(dry_run, output, input_sha256, output.sha256())

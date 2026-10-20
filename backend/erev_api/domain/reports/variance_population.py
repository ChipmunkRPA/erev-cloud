"""Changes in whole independent groups entering or leaving the frozen population.

No empty computation is invented. The existing endpoint must reproduce exactly;
absence on the other side is established by the complete frozen population. This
is a scope contribution, not a claim to replay an absent contract's business events.
"""

from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Literal

from erev_engine import ENGINE_VERSION, compute
from erev_engine.stages.s15_disclosures.variance import Evaluation, decompose

from .computation_sources import VerifiedComputation
from .variance_execution import SourceExecution, verify_source
from .variance_projection import Projection
from .variance_replay import Engine, Execution, Metrics, Replay, validate_reporting_pair
from .variance_reporting import Basis


@dataclass(frozen=True)
class PopulationReplay:
    earlier: SourceExecution | None
    later: SourceExecution | None
    normalized_fields: tuple[str, ...]
    replay_input_sha256: str
    replay: Replay


def execute(
    source: VerifiedComputation,
    metrics: Metrics,
    *,
    entering: bool,
    entity_code: str,
    book_code: str,
    period_key: str,
    engine: Engine = compute,
    currency_view: Literal["transaction", "functional", "reporting"] = "transaction",
    earlier_reporting_basis: Basis | None = None,
    later_reporting_basis: Basis | None = None,
) -> PopulationReplay:
    validate_reporting_pair(currency_view, earlier_reporting_basis, later_reporting_basis)
    verified, output = verify_source(
        source,
        metrics,
        entity_code=entity_code,
        book_code=book_code,
        period_key=period_key,
        engine=engine,
        currency_view=currency_view,
        reporting_basis=later_reporting_basis if entering else earlier_reporting_basis,
    )
    # Absence alone does not prove termination or a particular business event.
    driver = "NEW_CONTRACT" if entering else "OTHER"
    change = "population.entered" if entering else "population.left"
    entry = (
        Projection(
            source.bundle,
            entity_code,
            book_code,
            period_key,
            currency_view,
            earlier_reporting_basis,
        )(output)
        if entering and currency_view == "reporting"
        else metrics
    )
    executions = [Execution(driver, (), verified.input_sha256, verified.output_sha256, (change,))]
    if entering and currency_view == "reporting":
        executions.append(
            Execution("FX", (), verified.input_sha256, verified.output_sha256, ("reporting_rates",))
        )
    replay = Replay(
        ENGINE_VERSION,
        tuple(executions),
        MappingProxyType(
            {
                key: decompose(
                    Fraction(0) if entering else value,
                    [
                        Evaluation(
                            driver, entry.get(key, Fraction(0)) if entering else Fraction(0)
                        ),
                        *(
                            [Evaluation("FX", value)]
                            if entering and currency_view == "reporting"
                            else []
                        ),
                    ],
                )
                for key, value in metrics.items()
            }
        ),
        (earlier_reporting_basis.evidence_sha256, later_reporting_basis.evidence_sha256)
        if earlier_reporting_basis is not None and later_reporting_basis is not None
        else None,
    )
    return PopulationReplay(
        None if entering else verified,
        verified if entering else None,
        (),
        verified.input_sha256,
        replay,
    )

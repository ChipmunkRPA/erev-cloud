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
from .variance_replay import Engine, Execution, Metrics, Replay


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
    currency_view: Literal["transaction", "functional"] = "transaction",
) -> PopulationReplay:
    verified, _ = verify_source(
        source,
        metrics,
        entity_code=entity_code,
        book_code=book_code,
        period_key=period_key,
        engine=engine,
        currency_view=currency_view,
    )
    # Absence alone does not prove termination or a particular business event.
    driver = "NEW_CONTRACT" if entering else "OTHER"
    change = "population.entered" if entering else "population.left"
    replay = Replay(
        ENGINE_VERSION,
        (
            Execution(
                driver,
                (),
                verified.input_sha256,
                verified.output_sha256,
                (change,),
            ),
        ),
        MappingProxyType(
            {
                key: decompose(
                    Fraction(0) if entering else value,
                    [Evaluation(driver, value if entering else Fraction(0))],
                )
                for key, value in metrics.items()
            }
        ),
    )
    return PopulationReplay(
        None if entering else verified,
        verified if entering else None,
        (),
        verified.input_sha256,
        replay,
    )

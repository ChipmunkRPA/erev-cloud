"""Native functional POL-126 classification using original document and revenue evidence."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.stages.state import BookContext, ObligationState

from .acquisition_sources import intercompany_enabled

if TYPE_CHECKING:
    from .rollforward import BalanceInputs


def classify(
    ctx: BookContext,
    records: "BalanceInputs",
    own: Sequence[ObligationState],
    entity: str,
    period: PeriodInput,
    previous: PeriodInput | None,
    lines: dict[str, dict[str, int]],
    *,
    opening_obligations: Mapping[str, int] | None = None,
) -> None:
    from .rollforward import _entered

    liability = lines["CONTRACT_LIABILITY"]
    opening_code = "REVENUE_FROM_OPENING_BALANCE"
    other_code = "REVENUE_FROM_OTHER_INCREASES"
    consumed = -(liability[opening_code] + liability[other_code])

    def fail(message: str) -> None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            message,
            detail={"rule": "POL-126", "stage": "15", "entity": entity},
        )

    formula = 0
    if previous is not None and liability["OPENING"] > 0 and consumed > 0:
        fx = records.fx
        assert fx is not None
        if any(
            (ob.performing_entity != entity and not intercompany_enabled(records, ob))
            or ob.principal_agent.value != "PRINCIPAL"
            or (ob.opening is not None and not records.opening_billing_sources)
            for ob in own
        ):
            fail("functional POB classification requires original principal opening sources")
        subjects = {ob.subject_key for ob in own}
        documents: dict[tuple[str, str], int] = {}
        revenue_before = dict.fromkeys(subjects, 0)
        revenue_end = dict.fromkeys(subjects, 0)
        for flow in records.flows:
            when = _entered(flow)
            if flow.entity != entity or when is None or when > period.end_date:
                continue
            if flow.kind in {"BILLING", "CREDIT_MEMO"} and when < period.start_date:
                shares = records.attribution.get(flow.source_key, {})
                sign = 1 if flow.kind == "BILLING" else -1
                if not shares or sum(shares.values()) != sign * flow.amount:
                    fail("functional POB billing lacks complete original document attribution")
                for subject, amount in shares.items():
                    key = (flow.source_key, subject)
                    if subject not in subjects or key in documents:
                        fail("functional POB billing has duplicate or unknown sources")
                    documents[key] = amount
            elif flow.kind in {"REVENUE", "NEGATIVE_REVENUE"}:
                if flow.subject_key not in subjects:
                    fail("functional POB revenue has an unknown obligation")
                amount = flow.amount if flow.kind == "REVENUE" else -flow.amount
                revenue_end[flow.subject_key] += amount
                if when < period.start_date:
                    revenue_before[flow.subject_key] += amount
        sources = {}
        for source in fx.billing_attribution_sources:
            if source.entity != entity or source.period_key > previous.period_key:
                continue
            key = (source.source_key, source.subject_key)
            if key in sources:
                fail("functional POB billing repeats an original source")
            sources[key] = source
        if set(sources) != set(documents):
            fail("functional POB billing source population differs from original documents")
        billed = dict.fromkeys(subjects, 0)
        for key, txn in documents.items():
            source = sources[key]
            if source.amount_txn != txn:
                fail("functional POB billing source transaction amount differs")
            billed[source.subject_key] += source.amount_functional

        def revenue(subject: str, at: str, expected: int) -> int:
            targets = [
                target
                for target in fx.functional_targets
                if target.entity == entity
                and target.subject_key == subject
                and target.measure == "revenue_cum"
                and target.period_key <= at
            ]
            if not targets:
                if expected != 0:
                    fail("functional POB revenue sources are missing")
                return 0
            latest = max(targets, key=lambda target: target.period_key)
            if sum(target.period_key == latest.period_key for target in targets) != 1 or (
                latest.amount_txn != expected
                or latest.txn_currency != ctx.txn_currency
                or latest.functional_currency != ctx.entities[entity].functional_currency
            ):
                fail("functional POB revenue differs from its original transaction sources")
            return latest.amount_functional

        for subject in sorted(subjects):
            before = revenue(subject, previous.period_key, revenue_before[subject])
            end = revenue(subject, period.period_key, revenue_end[subject])
            available = (
                opening_obligations[subject]
                if opening_obligations is not None
                else max(0, billed[subject] - before)
            )
            formula += min(available, max(0, end - before))
    relief = min(max(0, consumed), max(0, liability["OPENING"]), formula)
    liability[opening_code] = -relief
    liability[other_code] = -(consumed - relief)

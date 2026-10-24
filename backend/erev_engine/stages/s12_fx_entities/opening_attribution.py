"""Attach original POB billing evidence to the existing cutover adjustment flow."""

from fractions import Fraction

from erev_engine import money
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import AllocatedState
from erev_engine.trace import SourceRef

from .layers import ControlFlow, UnitBook


def bind(book: UnitBook, allocated: AllocatedState, flows: tuple[ControlFlow, ...]) -> None:
    for flow in flows:
        if flow.entity != book.entity or not flow.source_key.endswith("/opening_billed_cum"):
            continue
        own = [
            ob
            for ob in allocated.obligations
            if contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
            == flow.subject_key
        ]
        if not own:
            continue
        baselines = {ob.subject_key: baseline_of(ob) for ob in own}
        if any(b is None or b.cutover_date != flow.effective_date for b in baselines.values()):
            continue
        previous: dict[str, list[tuple[int, str]]] = {ob.subject_key: [] for ob in own}
        complete = True
        for prior in flows:
            if (
                prior.entity != flow.entity
                or prior.subject_key != flow.subject_key
                or prior.source_key == flow.source_key
                or prior.kind not in {"BILLING", "CREDIT_MEMO"}
                or prior.effective_date > flow.effective_date
            ):
                continue
            shares = book.billing_attribution.get(prior.source_key, {})
            sign = -1 if prior.kind == "CREDIT_MEMO" else 1
            if (
                not shares
                or set(shares) - set(previous)
                or sum(value for value, _ in shares.values()) != sign * prior.amount
            ):
                complete = False
                break
            for subject, item in shares.items():
                previous[subject].append(item)
        if not complete:
            continue
        corrections = {
            subject: baseline.billed_cum - sum(amount for amount, _ in previous[subject])
            for subject, baseline in baselines.items()
            if baseline is not None
        }
        sign = -1 if flow.kind == "CREDIT_MEMO" else 1
        if sum(corrections.values()) != sign * flow.amount or any(
            sign * amount < 0 for amount in corrections.values()
        ):
            # Mixed signed offsets have no unique per-POB share of the net FX flow.
            continue
        prepared: dict[str, list[str | SourceRef]] = {}
        for ob in own:
            baseline = baselines[ob.subject_key]
            assert baseline is not None and ob.opening is not None
            event = str(ob.opening["event_key"])
            source: str | SourceRef
            if ob.opening.get("measurement") == "FAIR_VALUE_IFRS3":
                source = f"opening_allocation@{event}:{ob.subject_key}:-"
            else:
                if "billed_cum" not in ob.opening:
                    complete = False
                    break
                raw = Fraction(str(ob.opening["billed_cum"]))
                if money.round_half_up(raw, book.mu_txn) != baseline.billed_cum:
                    complete = False
                    break
                source = SourceRef(
                    "contract_event",
                    event,
                    {
                        "member": f"obligations[{ob.obligation_key}].billed_cum",
                        "value": money.format_exact(raw),
                    },
                )
            prepared[ob.subject_key] = [source, *(node for _, node in previous[ob.subject_key])]
        if not complete:
            continue
        attributed = {}
        for ob in own:
            assert ob.opening is not None
            event = str(ob.opening["event_key"])
            node = book.tb.node(
                measure=f"billing_opening_attributed@{flow.source_key}",
                subject_key=ob.subject_key,
                period_key=None,
                value=corrections[ob.subject_key],
                currency=book.txn,
                minor_unit=book.mu_txn,
                formula_id="fx.gain_loss.sum.v1",
                inputs=prepared[ob.subject_key],
                params={
                    "signs": "|".join(["1", *["-1" for _ in previous[ob.subject_key]]]),
                    "as_of": flow.effective_date.isoformat(),
                    "event_key": event,
                },
                narrative_key="fx.gain_loss.sum",
            )
            attributed[ob.subject_key] = (corrections[ob.subject_key], node)
        if complete:
            book.billing_attribution[flow.source_key] = attributed

"""Stage 12 performing and contracting entities (ENGINE_SPEC_B §12.2.5; BUILD_SPEC END-3).

Private to stage 12 (DG-ENG-07). Allocation spans the combination group across entities in the
transaction currency, while balances, netting and layers belong to the contracting entity; the
performing entity holds no contract balance (S12-R-14; POLICIES ALG-07 steps 1 to 3). Under POL-170
``PERFORMING_ENTITY`` the revenue of an obligation performed by another entity posts through JET-13:
the contracting entity relieves its contract liability against ``INTERCOMPANY_DUE_TO`` at the layer
relief, and the performing entity books ``INTERCOMPANY_DUE_FROM`` against ``REVENUE`` at its own
POL-162 rate (S12-R-15). The pair carries the revenue amount in the transaction currency (POL-171
``REVENUE_AMOUNT``), so due-to and due-from agree per entity pair and period (S12-R-16,
S12-INV-07). Under ``CONTRACTING_ENTITY`` JET-02 posts in the contracting entity and no pair exists.

``PairBook`` records every revenue flow of a cross-entity obligation as the contracting unit
processes it: the transaction amount, the functional pieces the flow moved in the contracting unit
(layer reliefs and asset-layer creations, ALG-07 step 5) and the performing-entity amount, converted
per flow at the POL-162 rate of the performing entity's period of the flow date (C-04). ``publish``
aggregates them per (obligation, performing entity, contracting period, performing period) and
emits the §12.5 nodes: ``ic_pair_txn`` and ``ic_pair_functional_contracting`` at the contracting
entity's period, ``ic_pair_functional_performing`` at the performing entity's period (S12-R-17;
L2-5-Q-20). Intercompany balances are not remeasured by the engine (ALG-07 step 5). Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s12_fx_entities.layers import ControlFlow, Piece, RateRef, UnitBook
from erev_engine.stages.s12_fx_entities.rates import AVERAGE, Rates, RateView, to_functional
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState, RateIndex
from erev_engine.trace import SourceRef

__all__ = ["IcPair", "PairBook"]

_POL_162: Final = frozenset({"PERIOD_AVERAGE", "TRANSACTION_DATE_SPOT"})
_POL_170: Final = frozenset({"PERFORMING_ENTITY", "CONTRACTING_ENTITY"})
_POL_171: Final = frozenset({"REVENUE_AMOUNT"})
_REVENUE_SIGNS: Final[Mapping[str, int]] = MappingProxyType({"REVENUE": 1, "NEGATIVE_REVENUE": -1})
_PAIR: Final = "ent.pair.v1"
_PERFORMING: Final = "ent.performing_revenue_rate.v1"


@dataclass(frozen=True, slots=True)
class IcPair:
    """One intercompany pair per obligation and period (ENGINE_SPEC_B §12.1 ``ic_pairs``).

    Amounts are signed period amounts: ``amount_txn`` in the transaction currency (POL-171),
    ``amount_contracting`` in the contracting entity's functional currency (the layer pieces of the
    revenue, ALG-07 step 5) and ``amount_performing`` in the performing entity's functional currency
    (POL-162). The contracting side is dated in the contracting entity's calendar, the performing
    side in the performing entity's calendar (S12-R-17).
    """

    book_code: BookCode
    obligation: str  # obligation subject key
    contracting_entity: str  # holds INTERCOMPANY_DUE_TO, counterparty = performing entity
    performing_entity: str  # holds INTERCOMPANY_DUE_FROM, counterparty = contracting entity
    contracting_period_key: str
    performing_period_key: str
    txn_currency: str
    amount_txn: int
    contracting_currency: str
    amount_contracting: int
    performing_currency: str
    amount_performing: int
    contracting_rates: tuple[RateRef, ...]  # rates of the layer pieces (REQ-FX-006)
    performing_rates: tuple[RateRef, ...]  # POL-162 rates of the performing entity
    txn_node_id: str
    contracting_node_id: str
    performing_node_id: str

    @property
    def subject_key(self) -> str:
        """``<obligation>@<contracting entity>><performing entity>`` (§12.5)."""
        return f"{self.obligation}@{self.contracting_entity}>{self.performing_entity}"


@dataclass(frozen=True, slots=True)
class _PairFlow:
    obligation: str
    performing_entity: str
    contracting_period_key: str
    performing_period_key: str
    amount: int  # signed transaction minor units
    pieces: tuple[tuple[Piece, int], ...]  # (functional piece in the contracting unit, sign)
    performing: int  # signed performing-entity minor units
    rate: RateView  # performing-entity rate
    performing_currency: str
    performing_minor_unit: int


class PairBook:
    """The intercompany pairs of one (group, contracting entity, book) (S12-R-15, S12-R-16)."""

    def __init__(
        self,
        ctx: BookContext,
        allocated: AllocatedState,
        rates: RateIndex | None,
        book: UnitBook,
    ) -> None:
        self.ctx = ctx
        self.book = book
        self.rows = () if rates is None else rates.rates
        self.bound = rates is not None
        self.obligations: Mapping[str, ObligationState] = {
            ob.subject_key: ob for ob in allocated.obligations
        }
        self.flows: list[_PairFlow] = []
        self._rates: dict[str, Rates] = {}

    def revenue(self, flow: ControlFlow, when: date, pieces: Sequence[Piece]) -> None:
        """Record the pair of a revenue flow of an obligation performed by another entity."""
        sign = _REVENUE_SIGNS.get(flow.kind)
        ob = self.obligations.get(flow.subject_key)
        if sign is None or ob is None or ob.performing_entity == ob.contracting_entity:
            return
        if ob.contracting_entity != self.book.entity:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a revenue flow names an entity other than its obligation's contracting entity",
                subject_key=ob.subject_key,
                detail={"entity": self.book.entity, "rule": "S12-R-14"},
            )
        if not self.pairs_performing_entity(ob):
            return  # JET-02 in the contracting entity (S12-R-15)
        performing = self.ctx.entities.get(ob.performing_entity)
        if performing is None:
            raise ValueError(
                f"obligation {ob.subject_key} names the performing entity "
                f"{ob.performing_entity!r}, absent from the book (CV-45)"
            )
        contracting_period = self.book.period(when)
        performing_period = dates.period_of(performing, when)
        rate = self.performing_rate(ob.performing_entity, flow, when, performing_period)
        currency = performing.functional_currency
        minor_unit = self.ctx.currencies[currency].minor_unit
        amount = sign * to_functional(flow.amount, rate, self.book.mu_txn, minor_unit)
        self.flows.append(
            _PairFlow(
                obligation=ob.subject_key,
                performing_entity=ob.performing_entity,
                contracting_period_key=contracting_period.period_key,
                performing_period_key=performing_period.period_key,
                amount=sign * flow.amount,
                pieces=tuple((piece, sign) for piece in pieces),
                performing=amount,
                rate=rate,
                performing_currency=currency,
                performing_minor_unit=minor_unit,
            )
        )

    def pairs_performing_entity(self, ob: ObligationState) -> bool:
        """POL-170 at the contracting entity (pin K) and the FORCED POL-171 (CV-17)."""
        option = self.ctx.policies.value("ic.revenue_entity", entity=ob.contracting_entity)
        if not isinstance(option, str) or option not in _POL_170:
            raise ValueError(f"policy ic.revenue_entity holds an unknown option {option!r} (CV-17)")
        amount = self.ctx.policies.value("ic.pair_amount", entity=ob.contracting_entity)
        if not isinstance(amount, str) or amount not in _POL_171:
            raise ValueError(f"policy ic.pair_amount holds an unknown option {amount!r} (CV-17)")
        return option == "PERFORMING_ENTITY"

    def performing_rate(
        self, entity: str, flow: ControlFlow, when: date, period: dates.PeriodLike
    ) -> RateView:
        """The POL-162 rate of the performing entity for the flow (ENGINE_SPEC_B §12.2.5)."""
        functional = self.ctx.entities[entity].functional_currency
        rates = self._rates.get(entity)
        if rates is None:
            if functional != self.book.txn and not self.bound:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "stage 12 converts a pair without a bound rate index",
                    subject_key=flow.subject_key,
                    detail={"rule": "S12-R-01"},
                )
            rates = Rates(self.rows, self.book.txn, functional)
            self._rates[entity] = rates
        option = self.ctx.policies.value(
            "fx.unbilled_revenue_rate", entity=entity, period=period.period_key
        )
        if not isinstance(option, str) or option not in _POL_162:
            raise ValueError(
                f"policy fx.unbilled_revenue_rate holds an unknown option {option!r} (CV-17)"
            )
        if option == "PERIOD_AVERAGE":
            return rates.period_rate(AVERAGE, period)
        return rates.spot(when)

    # --- publication ---------------------------------------------------------------------------

    def publish(self) -> tuple[IcPair, ...]:
        """Emit the pair nodes and return the pairs in (obligation, entities, periods) order."""
        contracting: dict[tuple[str, str, str], list[_PairFlow]] = {}
        performing: dict[tuple[str, str, str], list[_PairFlow]] = {}
        groups: dict[tuple[str, str, str, str], list[_PairFlow]] = {}
        for item in self.flows:
            head = (item.obligation, item.performing_entity)
            contracting.setdefault((*head, item.contracting_period_key), []).append(item)
            performing.setdefault((*head, item.performing_period_key), []).append(item)
            group = (*head, item.contracting_period_key, item.performing_period_key)
            groups.setdefault(group, []).append(item)
        txn_nodes: dict[tuple[str, str, str], str] = {}
        contracting_nodes: dict[tuple[str, str, str], str] = {}
        for side in sorted(contracting):
            nodes = self._contracting_nodes(side, contracting[side])
            txn_nodes[side], contracting_nodes[side] = nodes
        performing_nodes = {
            side: self._performing_node(side, performing[side]) for side in sorted(performing)
        }
        pairs: list[IcPair] = []
        for key in sorted(groups):
            obligation, entity, contracting_period, performing_period = key
            items = groups[key]
            head = (obligation, entity)
            pieces = [(piece, sign) for item in items for piece, sign in item.pieces]
            pairs.append(
                IcPair(
                    book_code=self.ctx.book_code,
                    obligation=obligation,
                    contracting_entity=self.book.entity,
                    performing_entity=entity,
                    contracting_period_key=contracting_period,
                    performing_period_key=performing_period,
                    txn_currency=self.book.txn,
                    amount_txn=sum(item.amount for item in items),
                    contracting_currency=self.book.fn,
                    amount_contracting=sum(sign * piece.amount for piece, sign in pieces),
                    performing_currency=items[0].performing_currency,
                    amount_performing=sum(item.performing for item in items),
                    contracting_rates=_refs(piece.rate for piece, _ in pieces),
                    performing_rates=_refs(item.rate for item in items),
                    txn_node_id=txn_nodes[(*head, contracting_period)],
                    contracting_node_id=contracting_nodes[(*head, contracting_period)],
                    performing_node_id=performing_nodes[(*head, performing_period)],
                )
            )
        return tuple(pairs)

    def _subject(self, obligation: str, performing_entity: str) -> str:
        return f"{obligation}@{self.book.entity}>{performing_entity}"

    def _contracting_nodes(
        self, key: tuple[str, str, str], items: Sequence[_PairFlow]
    ) -> tuple[str, str]:
        obligation, entity, period_key = key
        book = self.book
        subject = self._subject(obligation, entity)
        amounts = [item.amount for item in items]
        txn_node = book.tb.node(
            measure="ic_pair_txn",
            subject_key=subject,
            period_key=period_key,
            value=sum(amounts),
            currency=book.txn,
            minor_unit=book.mu_txn,
            formula_id=_PAIR,
            inputs=[],
            params={"amounts": "|".join(str(amount) for amount in amounts), "output": "TXN"},
            narrative_key="ent.pair",
        )
        pieces = [(piece, sign) for item in items for piece, sign in item.pieces]
        contracting_node = book.tb.node(
            measure="ic_pair_functional_contracting",
            subject_key=subject,
            period_key=period_key,
            value=sum(sign * piece.amount for piece, sign in pieces),
            currency=book.fn,
            minor_unit=book.mu_fn,
            formula_id=_PAIR,
            inputs=[piece.node_id for piece, _ in pieces],
            params={"output": "CONTRACTING", "signs": "|".join(str(sign) for _, sign in pieces)},
            narrative_key="ent.pair",
        )
        return txn_node, contracting_node

    def _performing_node(self, key: tuple[str, str, str], items: Sequence[_PairFlow]) -> str:
        obligation, entity, period_key = key
        book = self.book
        first = items[0]
        inputs: list[str | SourceRef] = []
        for item in items:
            inputs.extend(item.rate.inputs())
        exact = sum(
            (Fraction(item.amount, 10**book.mu_txn) * item.rate.value for item in items),
            Fraction(0),
        )
        return book.tb.node(
            measure="ic_pair_functional_performing",
            subject_key=self._subject(obligation, entity),
            period_key=period_key,
            value=sum(item.performing for item in items),
            currency=first.performing_currency,
            minor_unit=first.performing_minor_unit,
            formula_id=_PERFORMING,
            inputs=inputs,
            params={
                "amounts": "|".join(str(item.amount) for item in items),
                "rate_inputs": "|".join(
                    "true" if item.rate.rate_key is not None else "false" for item in items
                ),
                "rate_types": "|".join(item.rate.rate_type for item in items),
                "rates": "|".join(rational_param(item.rate.value) for item in items),
                "txn_minor_unit": str(book.mu_txn),
            },
            exact=exact,
            narrative_key="ent.performing_revenue_rate",
        )


def _refs(views: Iterable[RateView]) -> tuple[RateRef, ...]:
    found: set[RateRef] = set()
    for view in views:
        if view.rate_key is not None and view.version_key is not None:
            found.add(RateRef(view.rate_key, view.version_key))
    return tuple(sorted(found, key=lambda ref: (ref.rate_key, ref.version_key)))

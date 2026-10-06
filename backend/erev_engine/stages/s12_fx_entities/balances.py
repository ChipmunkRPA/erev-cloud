"""T-CON-09 functional columns of foreign-currency entities from the stage 12 layers (04 T-CON-09;
ENGINE_SPEC_B S12-R-03 to S12-R-09, S12-INV-03, S10-R-23; lane L5-5, cluster "functional balances").

Stage 10 publishes the labelled balances per member contract and entity in transaction currency;
T-CON-09 also holds ``contract_liability_functional``, ``contract_asset_functional`` and
``unbilled_receivable_functional``, and until now only a same-currency entity carried them. For an
entity whose functional currency differs from the transaction currency:

- the contract liability is the functional carrying of the open ``CONTRACT_LIABILITY`` layers at
  the period end (historical, or remeasured under the S12-R-10 override), apportioned over the
  member contracts by their transaction liabilities with largest remainder (S10-R-23; L5-5-Q-13);
- the contract asset and the unbilled receivable are the period's S12-R-09 reclass shares of the
  remeasured asset carrying, the difference between the cumulative ``netting_reclass_amount``
  functional targets at the period end and at the previous one, summed over the member's
  obligations;
- the refund liability is the carrying of the open ``REFUND_LIABILITY`` layers at the period end,
  remeasured at the closing rate (D-25b; S12-INV-08; lane L6-5);
- the deposit liability is the carrying of the open ``DEPOSIT_LIABILITY`` layers at the period end,
  remeasured at the closing rate (S02-R-08 rev 1.2; lane L6-5);
- the consideration payable is the carrying of the open ``CONSIDERATION_PAYABLE`` layers at the
  period end, remeasured at the closing rate (S12-R-21; D-87 L6-5-Q-18);
- the customer incentive asset is the JET-14 promised functional amount at spot on the promise
  dates less the released share at that historical carrying, never remeasured (POL-164; D-87
  L6-5-Q-18).

A same-currency row is returned unchanged. Private to stage 12 (DG-ENG-07). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erev_engine.bundle import BalanceOut
from erev_engine.errors import EngineError
from erev_engine.money import cumulative_posted, largest_remainder
from erev_engine.stages.s12_fx_entities.layers import ACCOUNTS_RECEIVABLE as _ACCOUNTS_RECEIVABLE
from erev_engine.stages.s12_fx_entities.layers import CONTRACT_LIABILITY, FxTarget, UnitBook
from erev_engine.stages.state import BookContext, Target
from erev_engine.trace import TraceBuilder

if TYPE_CHECKING:
    from erev_engine.stages.s12_fx_entities import FxState

__all__ = [
    "FUNCTIONAL_MEMBER_FORMULA",
    "functional_balance_columns",
    "functional_member_targets",
    "release_functional",
    "release_targets",
]
FUNCTIONAL_MEMBER_FORMULA: Final = "fx.functional_member.v1"

_RECLASS: Final = "netting_reclass_amount"  # S12-R-09 cumulative targets per <obligation>#<role>
_PRESENTED: Final[Mapping[str, str]] = MappingProxyType(
    {
        "CONTRACT_ASSET": "contract_asset_functional",
        "UNBILLED_RECEIVABLE": "unbilled_receivable_functional",
    }
)
_LIABILITY: Final = "contract_liability_functional"
_RECEIVABLE: Final = "accounts_receivable_functional"  # ENGINE mode (S10-R-19; L6-5)
_REFUND: Final = "refund_liability_functional"  # monetary layers (D-25b; S12-INV-08; L6-5)
_REFUND_ROLE: Final = "REFUND_LIABILITY"
_DEPOSIT: Final = "deposit_liability_functional"  # monetary layers (S02-R-08 rev 1.2; L6-5)
_DEPOSIT_ROLE: Final = "DEPOSIT_LIABILITY"
_PAYABLE: Final = "consideration_payable_functional"  # open layers at closing (S12-R-21)
_PAYABLE_ROLE: Final = "CONSIDERATION_PAYABLE"
_PROMISED: Final = "consideration_payable"  # the JET-14 promised functional target (S14-R-01)
_INCENTIVE: Final = "customer_incentive_asset_functional"  # historical carrying (POL-164)
# The stage 04 EMOD-22 release measures and the JET-14 release node formula (D-88 L7-6-Q-6).
# The JET-14 release part: the stage 04 ordinary release on its own (S04-R-16 rev 1.6; D-91 (5)).
_RELEASE: Final = "incentive_release_ordinary_cum"
_SETTLEMENT: Final = "fx.settlement.spot.v1"


def functional_balance_columns(
    rows: Sequence[BalanceOut],
    fx: FxState,
    *,
    txn_currency: str,
    functional: Mapping[str, str],
    periods: Mapping[str, Sequence[str]],
    member_of: Mapping[str, str],
) -> tuple[BalanceOut, ...]:
    """The rows with the functional contract liability, asset and unbilled receivable columns.

    ``functional`` maps entity codes to functional currencies, ``periods`` each entity's period
    keys in calendar order, and ``member_of`` an obligation subject key to its member balance
    subject ``<contract>@<contracting entity>``.
    """
    carrying: dict[tuple[str, str], int] = {}
    for layer in fx.layer_balances:
        if layer.balance_role == CONTRACT_LIABILITY:
            key = (layer.entity, layer.period_key)
            carrying[key] = carrying.get(key, 0) + layer.fn_carrying
    presented = _presented_shares(fx, periods, member_of)
    receivable = _receivable_carrying(fx)
    refunds = _refund_carrying(fx, member_of)
    deposits = _deposit_carrying(fx, member_of)
    payables = _payable_carrying(fx, member_of)
    promised = _promised_functional(fx, periods)
    released = _released_functional(fx)
    foreign: dict[tuple[str, str], list[BalanceOut]] = {}
    for row in rows:
        entity = str(row.columns.get("entity"))
        if functional.get(entity, txn_currency) != txn_currency:
            foreign.setdefault((entity, row.period_key), []).append(row)
    liability: dict[tuple[str, str], int] = {}
    for (entity, period_key), members in sorted(foreign.items()):
        total = carrying.get((entity, period_key), 0)
        for row, share in zip(members, _apportion(total, members, period_key), strict=True):
            liability[(row.subject_key, period_key)] = share
    out: list[BalanceOut] = []
    for row in rows:
        found = liability.get((row.subject_key, row.period_key))
        if found is None:
            out.append(row)
            continue
        columns = dict(row.columns)
        columns[_LIABILITY] = found
        for role, name in _PRESENTED.items():
            columns[name] = presented.get((row.subject_key, role, row.period_key), 0)
        if "accounts_receivable_txn" in columns:  # ENGINE mode (S10-R-19; JET-10a′; L6-5)
            columns[_RECEIVABLE] = receivable.get((row.subject_key, row.period_key), 0)
        if "refund_liability_txn" in columns:  # remeasured at the closing rate (JET-10d; L6-5)
            columns[_REFUND] = refunds.get((row.subject_key, row.period_key), 0)
        if "deposit_liability_txn" in columns:  # remeasured at the closing rate (JET-10d; L6-5)
            columns[_DEPOSIT] = deposits.get((row.subject_key, row.period_key), 0)
        if "consideration_payable_txn" in columns:  # D-87 L6-5-Q-18
            columns[_PAYABLE] = payables.get((row.subject_key, row.period_key), 0)
        if "customer_incentive_asset_txn" in columns:  # D-87 L6-5-Q-18; D-88 L7-6-Q-6
            columns[_INCENTIVE] = _incentive_functional(
                promised.get((row.subject_key, row.period_key), 0),
                _money(columns.get("consideration_payable_txn")),
                released.get((row.subject_key, row.period_key), 0),
            )
        out.append(
            BalanceOut(
                subject_key=row.subject_key,
                period_key=row.period_key,
                columns=MappingProxyType(columns),
                trace_nodes=row.trace_nodes,
            )
        )
    return tuple(out)


def _presented_shares(
    fx: FxState, periods: Mapping[str, Sequence[str]], member_of: Mapping[str, str]
) -> dict[tuple[str, str, str], int]:
    """Per (member subject, role, period): the period's reclass share in functional currency."""
    cumulative: dict[tuple[str, str, str, str], int] = {}
    for target in fx.functional_targets:
        role = target.balance_role
        if target.measure != _RECLASS or role is None or role not in _PRESENTED:
            continue
        obligation = target.subject_key.rsplit("#", 1)[0]
        cumulative[(target.entity, obligation, role, target.period_key)] = target.amount_functional
    out: dict[tuple[str, str, str], int] = {}
    for (entity, obligation, role, period_key), amount in sorted(cumulative.items()):
        member = member_of.get(obligation)
        if member is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a reclass target names an obligation absent from the group",
                subject_key=obligation,
                detail={"period_key": period_key, "rule": "S10-R-23"},
            )
        keys = list(periods.get(entity, ()))
        index = keys.index(period_key) if period_key in keys else -1
        previous = (
            cumulative.get((entity, obligation, role, keys[index - 1])) if index > 0 else None
        )
        share = amount - (previous or 0)
        key = (member, role, period_key)
        out[key] = out.get(key, 0) + share
    return out


def _receivable_carrying(fx: FxState) -> dict[tuple[str, str], int]:
    """Per (member subject, period): the functional carrying of the open receivable items, the
    ``ENGINE`` mode receivable remeasured at the closing rate (JET-10a′; L6-5)."""
    flows = getattr(getattr(fx.costs, "fx_flows", None), "receivables", ())
    subject_of = {flow.invoice_key: flow.subject_key for flow in flows}
    out: dict[tuple[str, str], int] = {}
    for layer in fx.layer_balances:
        if layer.balance_role != _ACCOUNTS_RECEIVABLE or layer.component_key is None:
            continue
        subject = subject_of.get(layer.component_key)
        if subject is None:
            continue
        key = (subject, layer.period_key)
        out[key] = out.get(key, 0) + layer.fn_carrying
    return out


def _refund_carrying(fx: FxState, member_of: Mapping[str, str]) -> dict[tuple[str, str], int]:
    """Per (member subject, period): the functional carrying of the open refund-liability layers,
    remeasured at the closing rate (JET-10d; S12-R-11, S12-INV-08; L6-5). A layer belongs to the
    member of its component's subject, an obligation or ``<contract>@<entity>``."""
    flows = getattr(getattr(fx.costs, "fx_flows", None), "monetary", ())
    subject_of = {
        flow.component_key: flow.subject_key for flow in flows if flow.role == _REFUND_ROLE
    }
    out: dict[tuple[str, str], int] = {}
    for layer in fx.layer_balances:
        if layer.balance_role != _REFUND_ROLE or layer.component_key is None:
            continue
        subject = subject_of.get(layer.component_key)
        if subject is None:
            continue
        key = (member_of.get(subject, subject), layer.period_key)
        out[key] = out.get(key, 0) + layer.fn_carrying
    return out


def _deposit_carrying(fx: FxState, member_of: Mapping[str, str]) -> dict[tuple[str, str], int]:
    """Per (member subject, period): the functional carrying of the open deposit-liability layers,
    remeasured at the closing rate (JET-10d; S02-R-08 rev 1.2, S12-INV-08; L6-5). The component of
    a deposit layer is ``<contract>@<entity>``."""
    flows = getattr(getattr(fx.costs, "fx_flows", None), "monetary", ())
    subject_of = {
        flow.component_key: flow.subject_key for flow in flows if flow.role == _DEPOSIT_ROLE
    }
    out: dict[tuple[str, str], int] = {}
    for layer in fx.layer_balances:
        if layer.balance_role != _DEPOSIT_ROLE or layer.component_key is None:
            continue
        subject = subject_of.get(layer.component_key)
        if subject is None:
            continue
        key = (member_of.get(subject, subject), layer.period_key)
        out[key] = out.get(key, 0) + layer.fn_carrying
    return out


def _payable_carrying(fx: FxState, member_of: Mapping[str, str]) -> dict[tuple[str, str], int]:
    """Per (member subject, period): the functional carrying of the open consideration-payable
    layers, remeasured at the closing rate (S12-R-21, S12-INV-08; D-87 L6-5-Q-18). The subject of a
    promise flow is ``<contract>@<entity>``."""
    flows = getattr(getattr(fx.costs, "fx_flows", None), "monetary", ())
    subject_of = {
        flow.component_key: flow.subject_key for flow in flows if flow.role == _PAYABLE_ROLE
    }
    out: dict[tuple[str, str], int] = {}
    for layer in fx.layer_balances:
        if layer.balance_role != _PAYABLE_ROLE or layer.component_key is None:
            continue
        subject = subject_of.get(layer.component_key)
        if subject is None:
            continue
        key = (member_of.get(subject, subject), layer.period_key)
        out[key] = out.get(key, 0) + layer.fn_carrying
    return out


def _promised_functional(
    fx: FxState, periods: Mapping[str, Sequence[str]]
) -> dict[tuple[str, str], int]:
    """Per (member subject, period): the cumulative JET-14 promised functional amount, the payable
    layers created at spot (S12-R-19), carried forward to the periods after its last target."""
    found: dict[tuple[str, str], dict[str, int]] = {}
    for target in fx.functional_targets:
        if target.measure == _PROMISED:
            key = (target.entity, target.subject_key)
            found.setdefault(key, {})[target.period_key] = target.amount_functional
    out: dict[tuple[str, str], int] = {}
    for (entity, subject_key), amounts in sorted(found.items()):
        current: int | None = None
        for period_key in periods.get(entity, ()):
            current = amounts.get(period_key, current)
            if current is not None:
                out[(subject_key, period_key)] = current
    return out


def _released_functional(fx: FxState) -> dict[tuple[str, str], int]:
    """Per (member subject, period): the functional JET-14 release stage 12 publishes
    (``release_targets``); 0 where nothing is released (D-88 L7-6-Q-6)."""
    return {
        (target.subject_key, target.period_key): target.amount_functional
        for target in fx.functional_targets
        if target.measure == _RELEASE
    }


def _incentive_functional(promised: int, payable_txn: int, released: int) -> int:
    """The functional customer incentive asset: ``promised`` (functional, at spot on the promise
    dates) less ``released``, the functional JET-14 release at that historical carrying that stage
    12 publishes and stage 14 posts (``release_functional``; POL-164; D-87 L6-5-Q-18, D-88
    L7-6-Q-6), so T-CON-09 and the GL tie."""
    if payable_txn <= 0 or promised == 0:
        return 0
    return promised - released


def release_functional(
    promised_fn: int, promised_txn: int, released_txn: int, minor_unit: int
) -> int:
    """F_rel = cumulative_posted(P_fn ÷ 10^μ_fn, P_fn, Rel ÷ P_txn, μ_fn): the released share of the
    cumulative JET-14 promised functional amount at its historical carrying (POL-164; D-88
    L7-6-Q-6). 1.10 promised with 1/3 released gives 0.37."""
    if promised_txn <= 0 or released_txn <= 0 or promised_fn == 0:
        return 0
    return cumulative_posted(
        Fraction(promised_fn, 10**minor_unit),
        promised_fn,
        Fraction(released_txn, promised_txn),
        minor_unit,
    )


def release_targets(
    book: UnitBook, consideration: Sequence[Target], published: Sequence[FxTarget]
) -> tuple[FxTarget, ...]:
    """The functional JET-14 release per ``<contract>@<entity>`` and period end (D-88 L7-6-Q-6 as
    amended by D-91 C606-03).

    For an entity whose functional currency differs from the transaction currency, Rel(t) = the
    posted stage 04 ``incentive_release_ordinary_cum`` read from the Table 14-A producer targets
    (``PartInputs.customer_consideration``, the stage 10 set): the share-based reduction is its own
    JET-14 part and is never netted into or out of the release (S14-R-01). When Rel > 0 the target
    carries F_rel (``release_functional``) of the promised FxTarget of that period, P_fn and P_txn,
    with its rates; its node is ``fx_layer_settled`` ``<contract>@<entity>#JET-14 release``
    (``fx.settlement.spot.v1``, output ``SHARE``). Nothing is published when Rel = 0, and a release
    without a promised functional amount to release fails closed. There is no JET-10 line (POL-164).
    """
    if book.fn == book.txn:
        return ()
    found: dict[tuple[str, str], int] = {}
    for target in consideration:
        if target.entity == book.entity and target.measure == _RELEASE:
            found[(target.subject_key, target.period_key)] = target.value
    promised = {
        (target.subject_key, target.period_key): target
        for target in published
        if target.measure == _PROMISED and target.entity == book.entity
    }
    out: list[FxTarget] = []
    for (subject_key, period_key), released in sorted(found.items()):
        if released <= 0:
            continue
        payable = promised.get((subject_key, period_key))
        if payable is None or released > payable.amount_txn:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a foreign-currency incentive release has no promised functional amount to release",
                subject_key=subject_key,
                detail={"period_key": period_key, "released": str(released), "rule": "POL-164"},
            )
        value = release_functional(
            payable.amount_functional, payable.amount_txn, released, book.mu_fn
        )
        node = book.tb.node(
            measure="fx_layer_settled",
            subject_key=f"{subject_key}#JET-14 release",
            period_key=period_key,
            value=value,
            currency=book.fn,
            minor_unit=book.mu_fn,
            formula_id=_SETTLEMENT,
            inputs=[],
            params={
                "amount_txn": str(released),
                "carrying_before": str(payable.amount_functional),
                "open_before": str(payable.amount_txn),
                "output": "SHARE",
            },
            exact=Fraction(payable.amount_functional * released, payable.amount_txn)
            / 10**book.mu_fn,
            narrative_key=_SETTLEMENT.rsplit(".v", 1)[0],
        )
        out.append(
            FxTarget(
                book_code=book.ctx.book_code,
                entity=book.entity,
                subject_key=subject_key,
                measure=_RELEASE,
                part=None,
                balance_role=None,
                period_key=period_key,
                txn_currency=book.txn,
                amount_txn=released,
                functional_currency=book.fn,
                amount_functional=value,
                rates=payable.rates,
                node_id=node,
            )
        )
    return tuple(out)


def _apportion(total: int, members: Sequence[BalanceOut], period_key: str) -> list[int]:
    """S10-R-23 over the member liabilities; one member takes the whole carrying."""
    if len(members) == 1:
        return [total]
    weights = [
        max(Fraction(0), Fraction(_money(row.columns.get("contract_liability_txn"))))
        for row in members
    ]
    if total == 0:
        return [0] * len(members)
    if sum(weights, Fraction(0)) == 0:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the functional contract liability has no member to attribute to",
            subject_key=members[0].subject_key,
            detail={"period_key": period_key, "rule": "S10-R-23"},
        )
    return largest_remainder(total, weights, [row.subject_key for row in members])


def _money(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def functional_member_targets(
    ctx: BookContext,
    fx: FxState,
    *,
    members: Sequence[Target],
    txn_currency: str,
    functional: Mapping[str, str],
    periods: Mapping[str, Sequence[str]],
    member_of: Mapping[str, str],
    receivable_members: frozenset[tuple[str, str]],
    payable_txn: Mapping[tuple[str, str], int],
    tb: TraceBuilder,
) -> tuple[Target, ...]:
    """The T-CON-09 ``_functional`` columns of foreign-currency entities as targets with nodes
    (D-97 (8), supervisor ruling T1F-Q-4; DG-KRN-EXP-01; lane ENG-T1F): per member row of an
    entity whose functional currency differs from the transaction currency, one
    ``fx.functional_member.v1`` node ``<column>:<member>:<period>`` in the functional currency for
    ``contract_liability_functional`` (the S10-R-23 share of the open layers' carrying),
    ``contract_asset_functional`` and ``unbilled_receivable_functional`` (the S12-R-09 reclass
    shares, citing the reclass targets), ``refund_liability_functional``,
    ``deposit_liability_functional``, ``consideration_payable_functional`` (open layers at the
    closing rate), ``customer_incentive_asset_functional`` (promised less released at historical
    carrying, citing those targets) and, for a member the book measures receivables of
    (``receivable_members``), ``accounts_receivable_functional``. The incentive condition is the
    TRANSACTION payable of the member (``payable_txn``, the stage 10 member sum): the asset exists
    while the transaction payable is non-zero and its functional amount is then the historical
    measure (Codex T1F-R2; never the closing functional payable, which can round to 0 while the
    transaction payable does not). The values are the ones ``functional_balance_columns``
    publishes; the assembler checks them against it and links these nodes.
    ``fx.functional_member.v1`` re-evaluates from params ``value``, so formula replay alone does
    not validate the derivation — the assembler's cross-check does; the inputs are lineage (the
    reclass, promised and release targets behind the presented and incentive amounts).
    """
    rows = sorted({(m.subject_key, m.period_key, m.entity) for m in members})
    foreign_rows = [
        (subject, period_key, entity)
        for subject, period_key, entity in rows
        if functional.get(entity, txn_currency) != txn_currency
    ]
    if not foreign_rows:
        return ()
    liabilities = {
        (m.subject_key, m.period_key): m.value for m in members if m.measure == "contract_liability"
    }
    carrying: dict[tuple[str, str], int] = {}
    for layer in fx.layer_balances:
        if layer.balance_role == CONTRACT_LIABILITY:
            key = (layer.entity, layer.period_key)
            carrying[key] = carrying.get(key, 0) + layer.fn_carrying
    presented = _presented_shares(fx, periods, member_of)
    receivable = _receivable_carrying(fx)
    refunds = _refund_carrying(fx, member_of)
    deposits = _deposit_carrying(fx, member_of)
    payables = _payable_carrying(fx, member_of)
    promised = _promised_functional(fx, periods)
    released = _released_functional(fx)
    reclass_nodes: dict[tuple[str, str, str], list[str]] = {}
    for target in fx.functional_targets:
        role = target.balance_role
        if target.measure != _RECLASS or role is None or role not in _PRESENTED:
            continue
        member = member_of.get(target.subject_key.rsplit("#", 1)[0])
        if member is not None:
            reclass_nodes.setdefault((member, role, target.period_key), []).append(target.node_id)
    promise_nodes: dict[tuple[str, str], list[str]] = {}
    for target in fx.functional_targets:
        if target.measure in (_PROMISED, _RELEASE):  # both dependencies, never one over the other
            promise_nodes.setdefault((target.subject_key, target.period_key), []).append(
                target.node_id
            )
    by_entity_period: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for row in foreign_rows:
        by_entity_period.setdefault((row[2], row[1]), []).append(row)
    out: list[Target] = []
    for (entity, period_key), group_rows in sorted(by_entity_period.items()):
        total = carrying.get((entity, period_key), 0)
        weights = [
            max(Fraction(0), Fraction(liabilities.get((subject, period_key), 0)))
            for subject, _, _ in group_rows
        ]
        if len(group_rows) == 1:
            shares = [total]
        elif total == 0:
            shares = [0] * len(group_rows)
        elif sum(weights, Fraction(0)) == 0:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the functional contract liability has no member to attribute to",
                subject_key=group_rows[0][0],
                detail={"period_key": period_key, "rule": "S10-R-23"},
            )
        else:
            shares = largest_remainder(total, weights, [subject for subject, _, _ in group_rows])
        currency = functional[entity]
        minor_unit = ctx.currencies[currency].minor_unit
        for (subject, _, _), share in zip(group_rows, shares, strict=True):
            values: dict[str, tuple[int, list[str]]] = {_LIABILITY: (share, [])}
            for role, name in _PRESENTED.items():
                values[name] = (
                    presented.get((subject, role, period_key), 0),
                    reclass_nodes.get((subject, role, period_key), []),
                )
            if (subject, period_key) in receivable_members:
                values[_RECEIVABLE] = (receivable.get((subject, period_key), 0), [])
            values[_REFUND] = (refunds.get((subject, period_key), 0), [])
            values[_DEPOSIT] = (deposits.get((subject, period_key), 0), [])
            values[_PAYABLE] = (payables.get((subject, period_key), 0), [])
            values[_INCENTIVE] = (
                _incentive_functional(
                    promised.get((subject, period_key), 0),
                    payable_txn.get((subject, period_key), 0),  # T1F-R2: the transaction payable
                    released.get((subject, period_key), 0),
                ),
                sorted(promise_nodes.get((subject, period_key), [])),
            )
            for name, (value, inputs) in values.items():
                node_id = tb.node(
                    measure=name,
                    subject_key=subject,
                    period_key=period_key,
                    value=value,
                    currency=currency,
                    minor_unit=minor_unit,
                    formula_id=FUNCTIONAL_MEMBER_FORMULA,
                    inputs=inputs,
                    params={"as_of": period_key, "value": str(value)},
                    narrative_key=FUNCTIONAL_MEMBER_FORMULA.rsplit(".v", 1)[0],
                )
                out.append(
                    Target(
                        ctx.book_code, entity, subject, name, period_key, None, value, None, node_id
                    )
                )
    return tuple(out)

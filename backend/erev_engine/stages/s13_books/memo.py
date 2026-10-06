"""Stage 13 stage keys, memo, aliases and book labels (ENGINE_SPEC_B §13.2.2; RCP-12, RCP-13).

``STAGE_POLICY_KEYS`` holds ENGINE_SPEC Table 0.10-A (stages 02 to 08) and ENGINE_SPEC_B Table 13-A
(stages 09 to 15), plus the key stage 08 declares beyond its row (``vc.reassessment_gate``,
L2-5-Q-3). ``STAGE_CONTEXT_MEMBERS`` names the book-dependent inputs a stage reads (S13-R-05); each
member has a view of this book's content, so books with equal inputs share the key (L3-2-Q-5).
``stage_key`` hashes the stage id, its formula ids, the previous key, the declared policy values and
the context views (S13-R-04).

``Memo`` lives inside one ``run_books`` call (S13-R-02; DG-ENG-08). A stage output names its book
only in labels: ``Target.book_code``, the ``ContractView.status_in_book`` key and a finding's
``detail["book_code"]``. A reused output is relabelled for the book that reuses it (L3-2-Q-6), and
the source nodes are aliased with params ``alias_of_book`` and ``stage_key`` (§13.5; CV-55).
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.enums import BookCode
from erev_engine.formulas import minor_unit_of
from erev_engine.money import decimal_to_minor
from erev_engine.stages import StageSpec
from erev_engine.stages.state import (
    BookContext,
    CanonicalBundle,
    ContractView,
    EstimatePins,
    EventView,
    Finding,
    QuantityLedger,
    Target,
)
from erev_engine.trace import TraceBuilder, TraceNode

__all__ = [
    "CONTEXT_VIEWS",
    "FOLD_STAGES",
    "STAGE_CONTEXT_MEMBERS",
    "STAGE_POLICY_KEYS",
    "Memo",
    "MemoEntry",
    "alias",
    "chain",
    "relabel",
    "stage_key",
]

# Stages 06 to 08 are the boundary handlers the book loop folds as one step (CV-11).
FOLD_STAGES: Final = frozenset({"06", "07", "08"})


def _keys(*codes: str) -> tuple[str, ...]:
    return tuple(sorted(codes))


STAGE_POLICY_KEYS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "02": _keys(
            "step1.collectibility_threshold",
            "step1.event_c_enabled",
            "step1.criteria_met_transition",
            "step1.term_with_termination_rights",
            "step1.portfolio_approach",
            "balance.deposit_liability",
        ),
        "03": _keys(
            "pob.immaterial_promise_relief",
            "pob.shipping_as_fulfilment",
            "pob.assurance_warranty_accrual",
            "licence.nature_model",
            "licence.renewal_start",
            "licence.combined_pob_nature",
            "material_right.ssp_method",
            "upfront_fee.recognition_period",
            "pob.principal_or_agent",
            "franchisor.preopening_expedient",
            "recognition.measure_of_progress",
            "recognition.time_convention",
            "bill_and_hold.custodial_pob",
            "scope.nonfinancial_asset_sale_610_20",
            "scope.lessor_combination_expedient",
            "scope.repurchase_classification",
            "scope.collaboration_808",
            "migration.nondistinct_mapping",
            "migration.material_right_convention",
            "migration.legacy_vc_rows",
        ),
        "04": _keys(
            "vc.estimation_method",
            "vc.constraint",
            "tp.sales_tax_exclusion",
            "sfc.one_year_expedient",
            "sfc.discount_rate_basis",
            "noncash.measurement_date",
            "cpc.incentive_asset_release_basis",
            "cpc.share_based_timing",
            "returns.model",
            "billing.posting",
            "usage.tier_minimum_method",
            "royalty.minimum_guarantee",
            "claims.recognition_gate",
        ),
        "05": _keys(
            "rounding.apportionment",
            "ssp.version_basis",
            "ssp.inside_range_point",
            "ssp.outside_range_point",
            "ssp.method_hierarchy",
            "ssp.residual_failure",
            "alloc.discount_exception",
            "alloc.zero_total_ssp",
            "alloc.negative_booking_lines",
            "ssp.currency_conversion",
            "vc.targeted_allocation_tolerance",
            "migration.split_upload_allocation",
        ),
        "06": _keys(
            "mod.ssp_basis",
            "mod.reduction_ssp",
            "mod.route_selection",
            "mod.separate_contract_price_test",
            "mod.catch_up_scope",
            "mod.mixed_allocation",
            "mod.price_change_on_satisfied_performance",
            "mod.unpriced_change_orders",
            "mod.post_modification_vc_routing",
            "mod.catch_up_progress_basis",
            "material_right.exercise",
            "termination.refund_settlement",
            "concession.allocation_basis",
            "returns.returned_units_scope",
        ),
        "07": _keys(
            "onboarding.method",
            "migration.material_right_convention",
            "bc.acquired_contract_measurement",
            "bc.expedient_modification_aggregation",
            "bc.expedient_ssp_at_acquisition",
        ),
        "08": _keys(
            "estimates.versioning",
            "estimates.change_classification",
            "late_events.posting",
            "late_events.fx_rates",
            "disclosure.prior_period_pob_revenue_basis",
            "vc.reassessment_gate",  # POL-042, read by S08-R-13 (L2-5-Q-3)
        ),
        "09": _keys(
            "rounding.schedule",
            "recognition.time_convention",
            "recognition.measure_of_progress",
            "recognition.control_trigger",
            "recognition.right_to_invoice_guard",
            "bill_and_hold.custodial_pob",
            "returns.model",
            "returns.reversal_rate",
            "returns.returned_units_scope",
            "breakage.method",
            "royalty.unreported_sales",
            "royalty.minimum_guarantee",
            "usage.tier_minimum_method",
            "credits.rollover_treatment",
            "licence.renewal_start",
            "scope.repurchase_classification",
        ),
        "10": _keys(
            "billing.posting",
            "balance.position_invoice_basis",
            "position.netting_unit",
            "position.reclass_attribution_key",
            "balance.right_to_consideration",
            "balance.current_noncurrent",
            "balance.credit_losses",
            "balance.refund_liability_presentation",
            "balance.deposit_liability",
            "tp.sales_tax_exclusion",
            "termination.refund_settlement",
            "concession.allocation_basis",
        ),
        "11": _keys(
            "recognition.time_convention",
            "costs.obtain_expedient",
            "costs.amortisation_period",
            "costs.commensurate_ratio",
            "costs.amortisation_pattern",
            "costs.impairment_reversal",
            "costs.termination_acceleration",
            "costs.fulfilment_capitalisation",
            "loss.unit",
            "loss.scope",
            "loss.cost_basis",
            "loss.consideration_basis",
        ),
        "12": _keys(
            "fx.cl_layer_date",
            "fx.cl_layer_consumption",
            "fx.unbilled_revenue_rate",
            "fx.cl_historical_layering",
            "fx.monetary_remeasurement",
            "ic.revenue_entity",
            "ic.pair_amount",
            "late_events.fx_rates",
        ),
        "14": _keys(
            "je.posting_mode",
            "je.summarization",
            "billing.posting",
            "rounding.posting_mode",
            "late_events.posting",
            "pob.principal_or_agent",
            "pob.assurance_warranty_accrual",
        ),
        "15": _keys(
            "rpo.time_bands",
            "rpo.exemption_original_duration_one_year",
            "rpo.exemption_right_to_invoice",
            "rpo.exemption_royalty_vc",
            "rpo.exemption_vc_wholly_unsatisfied",
            "rollforward.opening_liability_consumption",
            "disclosure.prior_period_pob_revenue_basis",
            "entity.reporting_type",
            "disclosure.nonpublic_disaggregation_relief",
            "disclosure.nonpublic_contract_balances_relief",
            "disclosure.nonpublic_rpo_relief",
            "disclosure.nonpublic_judgements_relief",
            "disclosure.nonpublic_expedient_relief",
            "disclosure.nonpublic_cost_relief",
            "disclosure.interim_revenue_pack",
        ),
    }
)

# S13-R-05 and Table 13-A. Stages 02 to 05, 09 and 11 filter judgement records by book; stages 08
# to 12, 14 and 15 read the book's period states; stages 11, 12, 14 and 15 read ``book_code``.
STAGE_CONTEXT_MEMBERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "02": ("judgements",),
        "03": ("judgements",),
        "04": ("judgements",),
        "05": ("judgements",),
        "06": (),
        "07": (),
        "08": ("calendars", "period_states"),
        "09": ("calendars", "horizon", "judgements", "period_states"),
        "10": ("calendars", "horizon", "period_states"),
        "11": ("book_code", "calendars", "horizon", "judgements", "period_states"),
        "12": ("book_code", "calendars", "horizon", "period_states"),
        "14": ("book_code", "mapping", "period_states"),
        "15": ("book_code", "horizon", "period_states"),
    }
)

ContextView = Callable[[BookContext, CanonicalBundle], object]


def _book_code(ctx: BookContext, cb: CanonicalBundle) -> object:
    return str(ctx.book_code)


def _horizon(ctx: BookContext, cb: CanonicalBundle) -> object:
    return [[code, ctx.horizon[code]] for code in sorted(ctx.horizon)]


def _calendars(ctx: BookContext, cb: CanonicalBundle) -> object:
    # Functional currency, time zone and period ranges, without the per-book period states.
    return [
        sha256_hex(
            dataclasses.replace(
                entity,
                periods=tuple(dataclasses.replace(period, states=()) for period in entity.periods),
            )
        )
        for _, entity in sorted(ctx.entities.items())
    ]


def _period_states(ctx: BookContext, cb: CanonicalBundle) -> object:
    book = str(ctx.book_code)
    return [
        [code, period.period_key, dict(period.states).get(book, "")]
        for code, entity in sorted(ctx.entities.items())
        for period in entity.periods
    ]


def _judgements(ctx: BookContext, cb: CanonicalBundle) -> object:
    # Records scoped to this book; records for every book (book_code None) are book-independent.
    book = str(ctx.book_code)
    return sorted(
        sha256_hex(record)
        for key in sorted(cb.contracts)
        for record in cb.contracts[key].header.judgements
        if record.book_code == book
    )


def _mapping(ctx: BookContext, cb: CanonicalBundle) -> object:
    return sha256_hex(ctx.mapping)


CONTEXT_VIEWS: Final[Mapping[str, ContextView]] = MappingProxyType(
    {
        "book_code": _book_code,
        "calendars": _calendars,
        "horizon": _horizon,
        "judgements": _judgements,
        "mapping": _mapping,
        "period_states": _period_states,
    }
)


def stage_key(spec: StageSpec, previous: str, ctx: BookContext, cb: CanonicalBundle) -> str:
    """S13-R-04: SHA-256 over the stage, its formula ids, the previous key, the resolved values of
    its declared policy keys and its context views (§13.2.2)."""
    declared = set(STAGE_POLICY_KEYS.get(spec.stage, ())) | set(spec.policy_keys)
    policies = sorted(
        [p.code, p.scope, p.subject_key, canonical_bytes(p.value).decode("utf-8"), p.level]
        for p in ctx.policies.all()
        if p.code in declared
    )
    members = STAGE_CONTEXT_MEMBERS.get(spec.stage, ())
    context = {member: CONTEXT_VIEWS[member](ctx, cb) for member in sorted(members)}
    return sha256_hex(
        {
            "context": context,
            "formulas": sorted(spec.formula_ids),
            "policies": policies,
            "previous": previous,
            "stage": spec.stage,
        }
    )


def chain(
    cb: CanonicalBundle, ctx: BookContext, stages: Sequence[StageSpec]
) -> tuple[tuple[str, str], ...]:
    """(stage, key) of every stage in order, each key covering the previous one (RCP-12)."""
    previous = "root"
    found: list[tuple[str, str]] = []
    for spec in stages:
        previous = stage_key(spec, previous, ctx, cb)
        found.append((spec.stage, previous))
    return tuple(found)


@dataclasses.dataclass(frozen=True, slots=True)
class MemoEntry:
    """A computed stage output with the nodes it emitted, keyed by stage key."""

    book_code: str  # the book that computed the output
    output: object
    nodes: tuple[TraceNode, ...]


class Memo:
    """The memo of one ``run_books`` call (S13-R-02; RCP-13): stage key -> ``MemoEntry``."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, MemoEntry] = {}

    def entries(self) -> tuple[MemoEntry, ...]:
        """The entries in insertion order."""
        return tuple(self._entries.values())

    def run(
        self, key: str, book_code: str, tb: TraceBuilder, compute: Callable[[], object]
    ) -> object:
        """The output of ``key``: reused and relabelled with aliased nodes, else computed."""
        entry = self._entries.get(key)
        if entry is not None:
            for node in entry.nodes:
                alias(tb, node, entry.book_code, key)
            return relabel(entry.output, entry.book_code, book_code)
        before = {node.id for node in tb.build(root_measures={}).nodes}
        output = compute()
        nodes = tuple(node for node in tb.build(root_measures={}).nodes if node.id not in before)
        self._entries[key] = MemoEntry(book_code, output, nodes)
        return output


def alias(tb: TraceBuilder, node: TraceNode, book_code: str, key: str) -> str:
    """The node of a memoised stage in the reusing book's trace (§13.5; CV-55): the source node's
    id, value, formula, inputs and params, with ``alias_of_book`` and ``stage_key`` added."""
    _, rest = node.id.split(":", 1)
    subject_key, period = rest.rsplit(":", 1)
    params = {**node.params, "alias_of_book": book_code, "stage_key": key}
    if node.rounding_residue is None:
        return tb.node(
            measure=node.measure,
            subject_key=subject_key,
            period_key=None if period == "-" else period,
            value=Fraction(Decimal(node.value)),
            currency=node.currency,
            minor_unit=None,
            formula_id=node.formula_id,
            inputs=node.inputs,
            params=params,
            narrative_key=node.narrative_key,
        )
    minor_unit = minor_unit_of(node.params)
    posted = decimal_to_minor(Decimal(node.value), minor_unit)
    exact = Fraction(posted, 10**minor_unit) + Fraction(Decimal(node.rounding_residue))
    return tb.node(
        measure=node.measure,
        subject_key=subject_key,
        period_key=None if period == "-" else period,
        value=posted,
        currency=node.currency,
        minor_unit=minor_unit,
        formula_id=node.formula_id,
        inputs=node.inputs,
        params=params,
        exact=exact,
        narrative_key=node.narrative_key,
    )


_ATOMS: Final = (str, int, Fraction, Decimal, date, datetime, bytes)
# Book-independent inputs a state carries: never relabelled, never walked.
_INPUTS: Final = (CanonicalBundle, EventView, EstimatePins, QuantityLedger, TraceNode)


def relabel(value: object, source: str, target: str) -> object:
    """``value`` computed for book ``source`` as the output of book ``target`` (L3-2-Q-6)."""
    if source == target:
        return value
    return _Relabel(BookCode(source), BookCode(target)).apply(value)


class _Relabel:
    __slots__ = ("seen", "source", "target")

    def __init__(self, source: BookCode, target: BookCode) -> None:
        self.source = source
        self.target = target
        self.seen: dict[int, tuple[object, object]] = {}

    def apply(self, value: object) -> object:
        if value is None or isinstance(value, _ATOMS) or isinstance(value, _INPUTS):
            return value
        found = self.seen.get(id(value))
        if found is not None:
            return found[1]
        result = self._walk(value)
        self.seen[id(value)] = (value, result)
        return result

    def _walk(self, value: object) -> object:
        if type(value).__module__ == "erev_engine.bundle":
            return value
        if isinstance(value, Target):
            if value.book_code != self.source:
                return value
            return dataclasses.replace(value, book_code=self.target)
        if isinstance(value, Finding):
            if value.detail.get("book_code") != str(self.source):
                return value
            detail = {**value.detail, "book_code": str(self.target)}
            return dataclasses.replace(value, detail=MappingProxyType(detail))
        if isinstance(value, ContractView):
            if self.source not in value.status_in_book:
                return value
            status = {
                (self.target if book == self.source else book): segments
                for book, segments in value.status_in_book.items()
            }
            return dataclasses.replace(value, status_in_book=MappingProxyType(status))
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            changes: dict[str, object] = {}
            for member in dataclasses.fields(value):
                if not member.init:
                    continue
                current = getattr(value, member.name)
                walked = self.apply(current)
                if walked is not current:
                    changes[member.name] = walked
            return dataclasses.replace(value, **changes) if changes else value
        if isinstance(value, tuple):
            items = tuple(self.apply(item) for item in value)
            unchanged = all(new is old for new, old in zip(items, value, strict=True))
            return value if unchanged else items
        if isinstance(value, Mapping):
            walked_items = {key: self.apply(item) for key, item in value.items()}
            if all(walked_items[key] is value[key] for key in value):
                return value
            return MappingProxyType(walked_items)
        return value

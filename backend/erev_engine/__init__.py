"""eRev revenue engine: a pure function over one contract's event stream (D-10).

The package imports only the Python standard library and performs no database, filesystem,
network, clock, randomness or float access (docs/dev-guide.md §7; DG-ARC-02).

``compute`` is the orchestration of ENGINE_SPEC §0.3 (BUILD_SPEC END-9): the float guard and the
version check on entry; stage 01 once; the book loop of ENGINE_SPEC_B §13 inside the local Decimal
context, which raises CV-15 after any stage that collected an ``ERROR`` finding (CV-42);
``assemble_output`` of §0.5 with the non-blocking findings as diagnostics in CV-43 order; the
fail-closed identities of DG-ENG-05 (CTL-012); and the float guard on exit. ``fold_book`` is the
§0.3 fold of stages 02 to 08 for one book. Stage packages are imported when a function runs,
because they import ``ENGINE_VERSION`` from this package.
"""

from __future__ import annotations

import dataclasses
import decimal
import functools
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erev_engine import guards, money
from erev_engine.bundle import (
    BalanceOut,
    BookInput,
    BookOutput,
    ContractVersionOut,
    CostAssetVersionOut,
    Diagnostic,
    FxLayerMovementOut,
    InputBundle,
    LossProvisionOut,
    ObligationVersionOut,
    OutputBundle,
)
from erev_engine.canonical import canonical_bytes
from erev_engine.errors import EngineError
from erev_engine.money import EXACT_PLACES
from erev_engine.trace import (
    ABSENCE_COLUMNS,
    ABSENT_PREFIX,
    TraceBuilder,
    TraceNode,
    absence_state,
    admitted_absence,
    exact_companion_failures,
)

if TYPE_CHECKING:
    from erev_engine.stages.s09_recognition import ObligationMeasures
    from erev_engine.stages.s10_billing_balances import BalanceState
    from erev_engine.stages.s13_books import BookResult
    from erev_engine.stages.s13_books.legacy_book import PreStandard
    from erev_engine.stages.s15_disclosures import DisclosureState
    from erev_engine.stages.state import (
        AllocatedState,
        AllocationSegment,
        BookContext,
        CanonicalBundle,
        Finding,
        ObligationState,
    )

__all__ = [
    "ENGINE_VERSION",
    "IDENTITY_BASIS",
    "IDENTITY_ENTRY",
    "IDENTITY_OBLIGATION",
    "IDENTITY_PRICE",
    "assemble_output",
    "assert_identities",
    "compute",
    "findings_json",
    "fold_book",
]

# Semantic version (DG-ENG-10); "1.0.0" at release. 0.1.0 → 0.2.0: D-91 C606-01 changed the
# refund liability of the ENGINE memo-only and status-update shapes (a "changed result" under the
# 0.x line; the T-PLT-38 release row is stamped on first start). 0.2.0 → 0.3.0 (D-93 (5);
# ENC-VC-direction): a changed-result minor bump under the D-91 A4 reading of DG-ENG-10 for the
# 0.x line — the T-CON-12 direction enters the canonical input and VC-FS-02's error becomes an
# output (a changed result); refund-liability components follow explicit targets of the five
# refund-settled types. Two separate measured facts (236 active engine keys, 658 assembled
# checkpoint bundles, 12 keys failing assembly on both versions): (a) normalised value
# compatibility with engine_version blanked — 654 of 658 inputs value-equal and all 583 common
# successful outputs value-equal, the exceptions being the four intended VC-FS-02 changes (the
# CV-25 hash view canonicalises pre-0.3.0 bundles: an absent or default-equal direction is
# omitted; 235 of 236 keys identical); (b) actual hashes — all 658 input hashes and all 583 common
# output hashes differ, through the stamp. Replay is version-pinned to the stored engine_release
# (RCP-28 to RCP-30); no silent rewriting or reposting of history; historical-integrity replay
# (RCP-28/29) and candidate-upgrade validation (REL-06) remain mandatory; new computations use
# 0.3.0.
# OWED at the next release cut (supervisor on lane ENG-C8 Q-1, D-98 candidate 19; S14-R-27): one
# DG-ENG-10 minor step 0.3.0 → 0.4.0 for the canonical-input widening PostedAmountInput.reason_code
# (the CV-25 view omits it when None, so historical inputs hash identically) together with the
# identity INPUT_TRANSFORM in the D-96 registry once it exists. A version names a release, not a
# lane merge, so the lane keeps 0.3.0 and the bump is applied once, at the cut.
# OWED at the same cut (lane F-CTR, D-98 140 AMENDMENT 16; ENGINE_SPEC 1.32; DG-ENG-10): the
# additive MODIFICATION_TREATMENT proposal detail member ssp_version[<key>] alters the output of an
# existing input that carries a pending modification — a minor step, folded into the one
# 0.3.0 → 0.4.0 step.
# OWED at the same cut (lane ENG-FX, ENG-FXREM-RATEPIN-1; ENGINE_SPEC 1.43, ENGINE_SPEC_B 1.50;
# DG-ENG-10): the canonical-input widening PostedAmountInput.rate_refs (the CV-25 view omits it
# when empty, so single-currency inputs hash identically) and three changes to the output of an
# existing foreign-currency input — a JET-06 reversal and a delta that only reverses posted
# amounts name their rate references in line_rates (S14-R-28), a posted FX_REMEASUREMENT amount
# answers the group's role key (S14-R-04) and a foreign-currency line without any rate reference
# raises S14-INV-08. One minor step, folded into the one 0.3.0 → 0.4.0 step.
# OWED at the same cut (lane ENG-FX, ENG-S14R10-FX-SIGN-1; supervisor ruling R-44 (a);
# ENGINE_SPEC_B 1.65; DG-ENG-10): an input with a role delta whose transaction and functional
# amounts differ in sign raised ENGINE_INVARIANT_VIOLATED and now computes, posting a transaction
# line and a functional line (S14-R-10, S14-INV-09); the output of an input that computed before
# is unchanged. A minor step, folded into the one 0.3.0 → 0.4.0 step.
# OWED at the same cut (lane ENG-FX, ENG-S12-DUE-DATE-1; supervisor ruling R-81; ENGINE_SPEC_B
# 1.83; DG-ENG-10): an input whose billing line has its POL-160 layer date in another accounting
# period than the date the line enters the position — an ERP invoice due, and not paid, after the
# end of its issue period; a receipt dated in an earlier period than the line it names — raised
# ENGINE_INVARIANT_VIOLATION (S12-INV-03) and now computes (S12-R-04); the output of an input
# that computed before is unchanged (1,648 of 1,648 corpus output hashes). A minor step, folded
# into the one 0.3.0 → 0.4.0 step.
# OWED at the same cut (lane F-CLO-A, BUILD_SPEC CLO-12; supervisor ruling R-51 (a); ENGINE_SPEC_B
# 1.63; DG-ENG-10): an included MANUAL_ADJUSTMENT_APPLIED event whose payload carries the approved
# lines of a manual journal or reclassification gives stage 14 role targets of entry kind
# MANUAL_ADJUSTMENT (S14-R-09a) where it gave none, and a payload that names book_code applies in
# that book only (S09-R-41). No stored input carries either member — the bundle builder writes
# them from CLO-12 on — so the output of an input that computed before is unchanged. A minor
# step, folded into the one 0.3.0 → 0.4.0 step.
# OWED at the same cut (lane ENG-FX, ENG-S10-FUTURE-INCEPTION-1; supervisor ruling R-107 (a);
# ENGINE_SPEC_B 1.100; DG-ENG-10): an input none of whose periods from the group's inception
# period lies inside the horizon of a contracting entity — a contract booked ahead of the entity's
# open periods — raised IndexError in stage 10, and ValueError in stage 12 behind it, and now
# computes (C-05, S10-R-22, S12-R-13): nothing presented or posted for that entity, and the
# version-state reclass node of its obligations under the new formula
# pos.reclass_attribution.no_measured_period.v1; the output of an input that computed before is
# unchanged (1,648 of 1,648 corpus output hashes). A minor step, folded into the one
# 0.3.0 → 0.4.0 step.
# OWED at the same cut (lane ENG-FX, ENG-COST-READBACK-1; supervisor ruling R-11 as amended on
# 2026-10-02; ENGINE_SPEC_B 1.165; DG-ENG-10): a posted amount answers the role key of the subject
# stored on its ledger lines, under ONE regrouping rule (S14-R-04, ``regrouped_subject_key``); the
# entry-kind match of rev 1.50 is gone. The output changes for two classes of input. (1) A posted
# amount, other than an FX remeasurement, under the group-level subject of ANOTHER combination
# group — a refund-liability component ``<group>@<entity>/<kind>/<source>`` posted before a
# combination — was reversed under its stored key and posted again under the current group's;
# it now answers the current group's key and only a difference posts. (2) A posted
# FX_REMEASUREMENT amount spelled ``<contract>@<entity>``, as the ledger read-back spelled it
# until 04 T-SL-04 stored ``subject_key``, answered the group's role key by its entry kind; it
# now answers its own subject. No ledger the product writes gives class (2): the read-back
# answers the stored key, and ``<group>@<entity>`` for a remeasurement line without one (05
# RCP-05). The output of every other input is unchanged (1,648 of 1,648 corpus output hashes).
# A minor step, folded into the one 0.3.0 → 0.4.0 step.
# SSP range provenance also changes output metadata/trace; include it in the pending
# 0.4.0 release cut and candidate-upgrade evidence. Historical traces remain immutable.
ENGINE_VERSION: Final[str] = "0.3.0"

# DG-ENG-05 identities, named in ``EngineError.detail["identity"]`` (CTL-012).
IDENTITY_BASIS: Final = "S04-R-02 sum a_posted = allocation_basis"
IDENTITY_PRICE: Final = "DB-17 V1 sum allocated_amount = transaction_price - consideration_payable"
IDENTITY_OBLIGATION: Final = "DB-17 allocated_amount = revenue_cum + scheduled + awaiting_trigger"
IDENTITY_ENTRY: Final = "D-16 entry debits = credits"

_ERROR: Final = "ERROR"
# E-77 literal of the rows DB-17 V1 sums (D-88 L7-5-Q-6: routed-out LEASE_842 rows leave the price).
_IN_SCOPE: Final = "IN_SCOPE_606"
# T-CON-09 EMOD-22 balances (S04-R-14 to S04-R-16); both publish a functional column since D-87
# L6-5-Q-18 (stage 12 fills a foreign-currency entity's).
_CPC_BALANCES: Final = frozenset({"customer_incentive_asset", "consideration_payable"})
_DIAGNOSTIC: Final = frozenset({"WARNING", "INFO"})
_BOOK_RANK: Final = MappingProxyType({"ASC606": 0, "IFRS15": 1, "LEGACY": 2})
# T-CON-11 values stage 09 publishes (ObligationMeasures) and their values without measures.
_RECOGNITION_COLUMNS: Final = MappingProxyType(
    {
        "progress_ratio": Fraction(0),
        "revenue_cum": 0,
        "remaining_allocation": 0,
        "remaining_quantity": Fraction(0),
        "scheduled_amount": 0,
        "awaiting_trigger_amount": 0,
        "catch_up_amount": 0,
        "catch_up_cum": 0,
        "catch_up_modification_cum": 0,
        "catch_up_tp_change_cum": 0,
        "catch_up_estimate_cum": 0,
        "satisfaction_status": "UNSATISFIED",
        "satisfied_date": None,
        "hold_types": (),
        "delivered_quantity": Fraction(0),
        "revenue_amount": 0,
        "ssp_delivered": Fraction(0),
        "ssp_delivered_cum": Fraction(0),
    }
)
# T-CON-11 values stage 10 publishes (BalanceMeasures).
_BALANCE_COLUMNS: Final = MappingProxyType(
    {
        "billed_cum": 0,
        "billed_amount": 0,
        "remaining_billing": 0,
        "position_obligation": 0,
        "position_contract_entity": 0,
        "netting_reclass_amount": 0,
        "netting_reclass_role": None,
        "gross_amount_memo": None,  # D-87 L4-3-Q-24 (b)
    }
)
_REMAINDER_PARTS: Final = ("revenue_cum", "scheduled_amount", "awaiting_trigger_amount")


# --- compute (ENGINE_SPEC §0.3) ------------------------------------------------------------------


def compute(bundle: InputBundle) -> OutputBundle:
    """One computation: every enabled book of ``bundle``, or ``EngineError`` (ENGINE_SPEC §0.3)."""
    guards.no_floats(bundle)  # FLOAT_DETECTED before any stage runs (DG-ENG-03)
    if bundle.engine_version != ENGINE_VERSION:
        raise EngineError(
            "ENGINE_VERSION_MISMATCH",
            "bundle engine version differs",
            detail={"bundle": bundle.engine_version, "engine": ENGINE_VERSION},
        )
    from erev_engine import stages
    from erev_engine.stages import s01_canonicalize, s13_books

    with decimal.localcontext(money.DECIMAL_CONTEXT):  # ENG-03; restored on exit
        blocking = _Blocking()
        cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
        blocking.check(None, cb)
        results = s13_books.run_books(cb, stages.STAGES, check=blocking.check)
        output = assemble_output(bundle, cb, results)
        assert_identities(output, results)
    guards.no_floats(output)
    return output


def fold_book(ctx: BookContext, cb: CanonicalBundle, tb: TraceBuilder) -> AllocatedState:
    """Stages 02 to 05 at the group inception, then the boundary fold (ENGINE_SPEC §0.3)."""
    from erev_engine.stages import (
        s02_contract_identification,
        s03_pob_builder,
        s04_transaction_price,
        s05_allocation,
        s13_books,
    )

    identified = s02_contract_identification.run(ctx, cb, tb, deposits=False)
    pob = s03_pob_builder.run(ctx, identified, tb)
    identified = s02_contract_identification.run_deposits(ctx, identified, pob, tb)  # D-91 (iii)
    pob = dataclasses.replace(pob, identified=identified)
    priced = s04_transaction_price.run(ctx, pob, tb)
    allocated = s05_allocation.run(ctx, priced, tb)
    return s13_books.fold(ctx, cb, allocated, tb, identified=identified, pob=pob)


class _Blocking:
    """CV-15, CV-42: the findings collected so far; any ``ERROR`` stops the computation."""

    __slots__ = ("_found",)

    def __init__(self) -> None:
        self._found: dict[tuple[tuple[int, str, str, str, bytes], int], tuple[str | None, Finding]]
        self._found = {}

    def check(self, book: str | None, state: object) -> None:
        for finding in _findings_of(state):
            self._found.setdefault((finding.sort_key(), _rank(book)), (book, finding))
        ordered = [self._found[key] for key in sorted(self._found)]
        first = next((item for _, item in ordered if item.severity == _ERROR), None)
        if first is not None:
            raise EngineError(
                first.code,
                "a stage collected a blocking finding (CV-15)",
                subject_key=first.subject_key,
                detail={"findings": findings_json(ordered)},
            )


def findings_json(items: Iterable[tuple[str | None, Finding]]) -> str:
    """CV-15 ``detail["findings"]``: canonical JSON of the findings in CV-43 order."""
    rows = [
        {
            "book_code": book,
            "code": finding.code,
            "detail": dict(finding.detail),
            "event_key": finding.event_key,
            "severity": finding.severity,
            "stage": finding.stage,
            "subject_key": finding.subject_key,
        }
        for book, finding in items
    ]
    return canonical_bytes(rows).decode("utf-8")


def _rank(book: str | None) -> int:
    return -1 if book is None else _BOOK_RANK.get(book, len(_BOOK_RANK))


def _findings_of(state: object) -> tuple[Finding, ...]:
    found = getattr(state, "findings", ())
    return tuple(found) if isinstance(found, tuple) else ()


# --- Output bundle (ENGINE_SPEC §0.5) ------------------------------------------------------------


def assemble_output(
    bundle: InputBundle, cb: CanonicalBundle, results: Sequence[BookResult]
) -> OutputBundle:
    """§0.5: one ``BookOutput`` per book in RCP-11 order and the diagnostics in CV-43 order."""
    from erev_engine.stages.s13_books import book_context, legacy_book

    books: list[BookOutput] = []
    for result in results:
        if isinstance(result.state, legacy_book.LegacyState):
            books.append(legacy_book.book_output(result.book, result.state, result.trace))
        else:
            ctx = book_context(cb, cb.books[result.book])  # POL-053 (L5-3-Q-5)
            books.append(_framework_output(bundle, result, ctx))
    return OutputBundle(
        engine_version=ENGINE_VERSION,
        input_sha256=bundle.sha256(),
        books=tuple(books),
        diagnostics=_diagnostics(cb, results),
    )


def _state[T](states: Mapping[str, object], stage: str, kind: type[T]) -> T | None:
    found = states.get(stage)
    return found if isinstance(found, kind) else None


def _allocated_of(result: BookResult) -> AllocatedState | None:
    from erev_engine.stages.state import AllocatedState

    for candidate in (result.state, *result.states.values()):
        if isinstance(candidate, AllocatedState):
            return candidate
        found = getattr(candidate, "allocated", None)
        if isinstance(found, AllocatedState):
            return found
    return None


def _framework_output(bundle: InputBundle, result: BookResult, ctx: BookContext) -> BookOutput:
    from erev_engine.stages.s01_canonicalize import group_entity_subject_key
    from erev_engine.stages.s09_recognition import RecognitionState
    from erev_engine.stages.s09_recognition.schedule import delivered_quantity_cum
    from erev_engine.stages.s10_billing_balances import BalanceState
    from erev_engine.stages.s11_costs_loss import CostLossState
    from erev_engine.stages.s12_fx_entities import FxState
    from erev_engine.stages.s13_books.output_measures import OUTPUT_KEY
    from erev_engine.stages.s14_posting import PostingState
    from erev_engine.stages.s15_disclosures import DisclosureState

    allocated = _allocated_of(result)
    if allocated is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the book loop published no allocated state",
            detail={"book_code": result.book, "rule": "CV-11"},
        )
    states = result.states
    recognition = _state(states, "09", RecognitionState)
    balances = _state(states, "10", BalanceState)
    costs = _state(states, "11", CostLossState)
    fx = _state(states, "12", FxState)
    posting = _state(states, "14", PostingState)
    disclosure = _state(states, "15", DisclosureState)
    currency = bundle.group.transaction_currency
    minor_unit = bundle.currencies[currency].minor_unit
    nodes = {node.id: node for node in result.trace.nodes}
    measures = {} if recognition is None else dict(recognition.obligation_measures)
    balance_measures = {} if balances is None else dict(balances.obligation_measures)
    pre_standard = {item.subject_key: item for item in result.pre_standard}
    as_of = _version_date(allocated)
    memos = _memos(allocated, as_of)  # CV-47 (a)
    output = states.get(OUTPUT_KEY)
    rates = getattr(output, "obligation_values", {})
    rate_nodes = getattr(output, "obligation_nodes", {})
    versions = tuple(
        _obligation_version(
            ob,
            allocated,
            as_of,
            measures.get(ob.subject_key),
            balance_measures.get(ob.subject_key),
            pre_standard.get(ob.subject_key),
            nodes,
            currency,
            minor_unit,
            delivered_quantity_cum=delivered_quantity_cum(ctx, allocated, ob),
            memos=memos.get((ob.contract_key, ob.obligation_key), MappingProxyType({})),
            unit_rates=rates.get(ob.subject_key, MappingProxyType({})),
            unit_rate_nodes=rate_nodes.get(ob.subject_key, MappingProxyType({})),
        )
        for ob in sorted(allocated.obligations, key=lambda item: item.subject_key)
    )
    versions = (*versions, *_excluded_line_versions(result, allocated, as_of, currency, memos))
    book_input = next(item for item in bundle.books if item.book_code == result.book)
    starts = {
        (entity.code, period.period_key): period.start_date
        for entity in bundle.entities
        for period in entity.periods
    }
    lines = (
        *(() if recognition is None else recognition.schedule_lines),
        *(() if costs is None else costs.schedule_lines),
    )
    schedules = tuple(
        sorted(
            lines,
            key=lambda line: (
                str(line.schedule_kind),
                line.subject_key,
                str(line.line_type),
                starts.get((line.entity, line.period_key), date.min),
            ),
        )
    )
    return BookOutput(
        book_code=result.book,
        contract_version=_apply_output_measures(
            _sales_tax_at_version_date(
                _net_of_incentive_release(
                    _contract_version(
                        result.book,
                        allocated,
                        versions,
                        book_input,
                        nodes,
                        currency,
                        minor_unit,
                        disclosure,
                        measures,
                    ),
                    bundle,
                    allocated,
                    balances
                    if balances is not None
                    else (None if costs is None else costs.balances),
                ),
                bundle,
                allocated,
            ),
            states.get(OUTPUT_KEY),
        ),
        status_in_book=_statuses(allocated, result.book),
        obligation_versions=versions,
        balances=()
        if balances is None
        else _functional_balances(
            bundle,
            allocated,
            fx,
            _cost_loss_columns(bundle, costs, _balances(bundle, balances)),
        ),
        schedules=schedules,
        cost_asset_versions=()
        if costs is None
        else tuple(
            CostAssetVersionOut(
                subject_key=item.asset_key,
                columns=_columns(item, ("segments", "trace_nodes")),
                trace_nodes=MappingProxyType(dict(sorted(item.trace_nodes.items()))),
            )
            for _, item in sorted(costs.cost_asset_measures.items())
        ),
        loss_provision_versions=()
        if costs is None
        else tuple(
            LossProvisionOut(
                subject_key=item.unit_key,
                period_key=item.period_key,
                columns=_columns(item, ("trace_nodes",)),
                trace_nodes=MappingProxyType(dict(sorted(item.trace_nodes.items()))),
            )
            for _, item in sorted(costs.loss_measures.items())
        ),
        fx_layer_movements=()
        if fx is None
        else tuple(
            FxLayerMovementOut(
                subject_key=(
                    f"{group_entity_subject_key(allocated.group_code, item.entity)}"
                    f"/{item.layer_key}"
                ),
                columns=_columns(item, ("trace_node_id",)),
                trace_nodes=MappingProxyType({"amount_functional": item.trace_node_id}),
            )
            for item in fx.layer_movements
        ),
        posting_intents=() if posting is None else posting.posting_intents,
        proposals=tuple(sorted(allocated.proposals, key=lambda p: (p.kind, p.subject_key))),
        time_triggers=tuple(
            sorted(allocated.time_triggers, key=lambda t: (t.date, t.kind, t.subject_key))
        ),
        trace=result.trace,
        # D-88 L7-6-Q-1: the pinned rates of each foreign-currency posting line (REQ-FX-006).
        line_rates=()
        if posting is None
        else tuple(
            (key, tuple((ref.rate_key, ref.version_key) for ref in refs))
            for key, refs in sorted(posting.line_rates.items())
        ),
    )


def _apply_output_measures(version: ContractVersionOut, output: object) -> ContractVersionOut:
    """D-97 (8) T1F-Q-1 (A): the stage 13 output measures (``s13_books/output_measures.py``) hold
    the T-CON-08 sums and version-date re-measurements WITH their nodes. The assembler's own
    figures must agree (else ``ENGINE_INVARIANT_VIOLATED``); the links come from the measures.
    Without the measures (no stage 09 in the stage list) the version keeps the assembler's figures
    and links."""
    from erev_engine.stages.s13_books.output_measures import OutputMeasures

    if not isinstance(output, OutputMeasures):
        return version
    columns = dict(version.columns)
    trace_nodes = dict(version.trace_nodes)
    for column, value in output.values.items():
        held = columns.get(column)
        if held != value:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the assembled contract version disagrees with the stage 13 output measure",
                subject_key=version.subject_key,
                detail={
                    "rule": "DG-KRN-EXP-01",
                    "column": column,
                    "assembled": str(held),
                    "measured": str(value),
                },
            )
        node_id = output.nodes.get(column)
        if node_id is not None:
            trace_nodes[column] = node_id
    return dataclasses.replace(
        version,
        columns=MappingProxyType(columns),
        trace_nodes=MappingProxyType(dict(sorted(trace_nodes.items()))),
    )


def _sales_tax_at_version_date(
    version: ContractVersionOut, bundle: InputBundle, allocated: AllocatedState
) -> ContractVersionOut:
    """S04-R-20: ``sales_tax_excluded_amount`` = Σ tax of the included invoices dated on or before
    d_v. The build-up of the last reallocating boundary measures the memo at that boundary, so the
    tax of a later invoice never reached the version (TAX-WM-08; lane L5-5)."""
    from erev_engine.stages.s04_transaction_price.taxes import collected_tax

    members = {view.header.external_id for view in allocated.contracts}
    exact = collected_tax(allocated.measure_events, members, _version_date(allocated))
    currency = bundle.group.transaction_currency
    posted = money.round_half_up(exact, bundle.currencies[currency].minor_unit)
    if posted == version.columns.get("sales_tax_excluded_amount"):
        return version
    columns = dict(version.columns)
    columns["sales_tax_excluded_amount"] = posted
    trace_nodes = {k: v for k, v in version.trace_nodes.items() if k != "sales_tax_excluded_amount"}
    return dataclasses.replace(
        version, columns=MappingProxyType(columns), trace_nodes=MappingProxyType(trace_nodes)
    )


def _net_of_incentive_release(
    version: ContractVersionOut,
    bundle: InputBundle,
    allocated: AllocatedState,
    balances: BalanceState | None,
) -> ContractVersionOut:
    """S04-R-02 (rev 1.6): ``contract_version.revenue_cum`` is Σ obligation ``revenue_cum`` less the
    cumulative JET-14 release ``incentive_release_cum`` = the posted ordinary release plus the sum
    of the posted, individually rounded share-based element targets (D-91 C606-03).

    The release is the posted stage 10 target (``BalanceState.customer_consideration``,
    ENGINE_SPEC_B S10-R-26) of each member ``<contract>@<entity>`` at the contracting entity's
    period holding d_v,
    0 before the first promise or pin and when no stage 10 state exists. CHK-133: 2,000,000.00 −
    200,000.00; CHK-120: 400,000.00 − 20,000.00 = 380,000.00. The period-end basis is the rc rule
    (a d_v-dated measurement for a mid-period version date is post-rc).
    """
    if balances is None:
        return version
    on = _version_date(allocated)
    holding = {
        entity.code: period.period_key
        for entity in bundle.entities
        for period in entity.periods
        if period.start_date <= on <= period.end_date
    }
    released = sum(
        target.value
        for target in balances.customer_consideration
        if target.measure == "incentive_release_cum"
        and holding.get(target.entity) == target.period_key
    )
    if released == 0:
        return version
    columns = dict(version.columns)
    columns["revenue_cum"] = _integer(columns.get("revenue_cum"), "revenue_cum") - released
    return dataclasses.replace(version, columns=MappingProxyType(columns))


def _version_date(st: AllocatedState) -> date:
    """d_v: the latest effective date the version includes (04 T-CON-11 ``effective_date``)."""
    latest = max((event.effective_date for event in st.events), default=st.inception_date)
    return max(latest, st.inception_date)


def _current(ob: ObligationState) -> dict[str, AllocationSegment]:
    """The segment in force per component: the last one (segments ascend, CV-60)."""
    found: dict[str, AllocationSegment] = {}
    for segment in ob.segments:
        found[segment.component] = segment
    return found


def _selected_ssp(ob: ObligationState, nodes: Mapping[str, TraceNode]) -> Fraction:
    """T-CON-11 ``original_ssp_selected`` (S05-R-16): the selected SSP, which for the residual
    candidate is R, node ``residual_ssp:<ob>:-`` (S05-R-12). The stage 05 snapshot keeps 0 for a
    residual entry (L4-3-Q-13)."""
    ssp = ob.ssp
    if ssp is None:
        return Fraction(0)
    residual = nodes.get(f"residual_ssp:{ob.subject_key}:-") if ssp.residual_candidate else None
    return ssp.selected if residual is None else Fraction(Decimal(residual.value))


def _exact(node: TraceNode | None) -> Fraction | None:
    if node is None:
        return None
    value = Fraction(Decimal(node.value))
    if node.rounding_residue is not None:
        value += Fraction(Decimal(node.rounding_residue))
    return value


def _memos(
    allocated: AllocatedState, as_of: date
) -> Mapping[tuple[str, str], Mapping[str, str | None]]:
    """CV-47 (a) (D-98 candidate 88): the memos of every obligation as of ``as_of`` — the booking
    line's ``memo_1..3``, then the ``MEMO_UPDATED`` events of the obligation with effective date
    ≤ d_v in stream order, each setting the members its presence set ``named`` lists (a supplied
    null clears); an event without ``named`` reads as strings replace, nulls are omissions."""
    found: dict[tuple[str, str], dict[str, str | None]] = {}
    for view in allocated.contracts:
        contract_key = view.header.external_id
        lines = view.booking.get("lines", ())
        if not isinstance(lines, Sequence):
            continue
        for line in lines:
            if not isinstance(line, Mapping):
                continue
            key = line.get("obligation_key")
            if not isinstance(key, str):
                continue
            found[(contract_key, key)] = {
                member: (value if isinstance(value, str) else None)
                for member in _MEMO_MEMBERS
                for value in (line.get(member),)
            }
    for event in sorted(allocated.events, key=lambda item: item.order_key):
        if event.event_type != "MEMO_UPDATED" or event.effective_date > as_of:
            continue
        key = event.payload.get("obligation_key")
        if not isinstance(key, str):
            continue
        current = found.setdefault((event.contract_key, key), dict.fromkeys(_MEMO_MEMBERS))
        named = event.payload.get("named")
        if isinstance(named, Sequence) and not isinstance(named, str):
            # The presence set (04 §16.3; Codex T1F2-MEMO-R1): a named member takes the event's
            # value, a supplied null clears it; unnamed members keep theirs although the stored
            # form writes them as null.
            for member in _MEMO_MEMBERS:
                if member in named:
                    value = event.payload.get(member)
                    current[member] = value if isinstance(value, str) else None
            continue
        # An event without ``named`` (persisted before rev 1.27 / 1.52): strings replace, nulls
        # are omissions — the one reading that never reinterprets its ambiguous stored form.
        for member in _MEMO_MEMBERS:
            value = event.payload.get(member)
            if isinstance(value, str):
                current[member] = value
    return MappingProxyType({key: MappingProxyType(value) for key, value in found.items()})


_MEMO_MEMBERS: Final = ("memo_1", "memo_2", "memo_3")


def _obligation_version(
    ob: ObligationState,
    allocated: AllocatedState,
    as_of: date,
    measures: ObligationMeasures | None,
    balances: object | None,
    pre_standard: PreStandard | None,
    nodes: Mapping[str, TraceNode],
    currency: str,
    minor_unit: int,
    *,
    delivered_quantity_cum: Fraction,
    memos: Mapping[str, str | None] = MappingProxyType({}),
    unit_rates: Mapping[str, Fraction] = MappingProxyType({}),
    unit_rate_nodes: Mapping[str, str] = MappingProxyType({}),
) -> ObligationVersionOut:
    """T-CON-11 columns of one obligation version, natural keys in place of surrogate ids."""
    current = _current(ob)
    fixed = current.get("FIXED")
    stated = money.round_half_up(ob.stated_price, minor_unit)
    if measures is None:
        amount = sum(segment.a_posted for segment in current.values())
        recognised: dict[str, object] = dict(_RECOGNITION_COLUMNS)
        recognised["remaining_allocation"] = amount
        recognised["awaiting_trigger_amount"] = amount
        measure_nodes: Mapping[str, str] = {}
        effective = as_of
    else:
        amount = measures.allocated_amount
        recognised = {name: getattr(measures, name) for name in _RECOGNITION_COLUMNS}
        measure_nodes = measures.trace_nodes
        effective = measures.as_of
    billed = {
        name: default if balances is None else getattr(balances, name, default)
        for name, default in _BALANCE_COLUMNS.items()
    }
    balance_nodes: Mapping[str, str] = getattr(balances, "trace_nodes", {}) if balances else {}
    exact = _exact(nodes.get(measure_nodes.get("allocated_amount", "")))
    if exact is None:
        exact = sum((segment.x_exact for segment in current.values()), Fraction(0))
    # CV-50 rev 1.29 (D-98 124): a created obligation's weight is its constructor's ratio node,
    # stamped on the state; the stage 05 node otherwise; 0 only when neither exists (an excluded
    # line publishes its own row, `_excluded_line_versions`).
    weight_node = ob.snapshot_producer_links.get(
        "allocation_weight", f"allocation_weight:{ob.subject_key}:-"
    )
    weight = (
        None  # a contract-permitted absence (DEV-054): the existing 0 display, no node
        if weight_node.startswith(ABSENT_PREFIX)
        else _exact(nodes.get(weight_node))
    )
    ssp = ob.ssp
    point = allocated.ledger.at(ob.subject_key)
    columns: dict[str, object] = {
        "obligation_key": ob.obligation_key,
        "legacy_record_key": ob.obligation_key,
        "product_code": ob.product_code,
        "sku_number": ob.sku_number,
        "stratification": ob.stratification or "",
        "obligation_kind": _plain(ob.obligation_kind),
        "distinctness": _plain(ob.distinctness),
        "series_increment_unit": ob.series_increment_unit,
        "pob_template_version_key": ob.template_version_key,
        "scope_flag": _plain(ob.scope_flag),
        "satisfaction_pattern": _plain(ob.satisfaction_pattern),
        "over_time_criterion": ob.over_time_criterion,
        "recognition_method": _plain(ob.recognition_method),
        "ratable_convention": _plain(ob.ratable_convention),
        "principal_agent": _plain(ob.principal_agent),
        "licence_nature": _plain(ob.licence_nature),
        "warranty_type": _plain(ob.warranty_type),
        "start_date": ob.start_date,
        "end_date": ob.end_date,
        "contracting_entity_code": ob.contracting_entity,
        "performing_entity_code": ob.performing_entity,
        "txn_currency": currency,
        "account_overrides": _plain(ob.account_overrides),
        "original_quantity": ob.original_quantity,
        "original_stated_price": money.round_half_up(ob.original_stated_price, minor_unit),
        "quantity": ob.quantity,
        "stated_price": stated,
        "ssp_book_version_key": None if ssp is None else ssp.version_key,
        "ssp_entry_key": None if ssp is None else ssp.entry_key,
        "ssp_range_key": None if ssp is None else ssp.range_key,
        "ssp_method": None if ssp is None else ssp.method,
        "ssp_version_label": None if ssp is None else ssp.version_label,
        "ssp_unit_list_price": None if ssp is None else ssp.unit_list_price,
        "ssp_midpoint_discount_ratio": None if ssp is None else ssp.midpoint_discount_ratio,
        "ssp_range_ratio": None if ssp is None else ssp.range_ratio,
        "original_ssp_mid": None if ssp is None else ssp.mid,
        "original_ssp_high": None if ssp is None else ssp.high,
        "original_ssp_low": None if ssp is None else ssp.low,
        "original_ssp_selected": _selected_ssp(ob, nodes),
        "original_ssp_in_range": None if ssp is None else ssp.in_range,
        "original_total_contract_price": money.round_half_up(
            ob.original_total_contract_price, minor_unit
        ),
        "original_total_contract_ssp": ob.original_total_contract_ssp,
        "original_allocated_amount": ob.original_allocation.a_posted,
        "original_allocated_exact": ob.original_allocation.x_exact,
        "original_unit_ssp": None
        if ssp is None or ob.original_quantity == 0
        else _selected_ssp(ob, nodes) / ob.original_quantity,
        "allocation_weight": Fraction(0) if weight is None else weight,
        "allocated_amount": amount,
        "allocated_exact": exact,
        "allocation_adjustment": amount - stated,
        "unit_ssp": None if fixed is None else fixed.unit_ssp,
        "remaining_ssp": Fraction(0) if fixed is None else fixed.remaining_ssp,
        # Net of returns only under POL-053 RESTORE_REMAINING_QUANTITY (D-87 L5-3-Q-5).
        "delivered_quantity_cum": delivered_quantity_cum,
        "returned_quantity_cum": point.returned_cum,
        **{name: _plain(value) for name, value in recognised.items()},
        **{name: _plain(value) for name, value in billed.items()},
        "pre_standard_revenue_cum": 0 if pre_standard is None else pre_standard.cumulative,
        "pre_standard_revenue_amount": 0 if pre_standard is None else pre_standard.amount,
        "modification_boundary_no": max(
            (segment.modification_boundary_no for segment in ob.segments), default=0
        ),
        "last_modification_key": ob.last_modification_key,
        "effective_date": effective,
    }
    # CV-47 (D-98 candidates 88): the memos passed through and the unit revenue rates of the
    # stage 13 output step (NULL where no node exists), with their links.
    for member in ("memo_1", "memo_2", "memo_3"):
        columns[member] = memos.get(member)
    for member in ("original_unit_revenue_rate", "remaining_unit_revenue_rate"):
        columns[member] = unit_rates.get(member)
    trace_nodes = {
        **measure_nodes,
        **balance_nodes,
        **({} if pre_standard is None else pre_standard.trace_nodes),
        **_snapshot_links(ob, allocated, columns, nodes, minor_unit),
        **unit_rate_nodes,
    }
    return ObligationVersionOut(
        subject_key=ob.subject_key,
        columns=MappingProxyType(columns),
        trace_nodes=MappingProxyType(dict(sorted(trace_nodes.items()))),
    )


# T-CON-11 columns whose version-state node a stage before 09 emits under the column's own measure
# (stage 03 template match, stage 05 allocation and SSP snapshot; DG-KRN-EXP-01, CV-50 links).
_SNAPSHOT_LINKS: Final = (
    "allocation_weight",
    "original_quantity",
    "original_ssp_selected",
    "original_stated_price",
    "ssp_unit_list_price",
    "ssp_midpoint_discount_ratio",
    "ssp_range_ratio",
    "original_ssp_mid",
    "original_ssp_high",
    "original_ssp_low",
    "original_total_contract_price",
    "original_total_contract_ssp",
    "original_unit_ssp",
)
# Columns re-measured at a boundary (D-97 (8) T1F-Q-3 (c)): the last ``<column>@<event>`` node of
# stage 06 links; without one the inception node (stage 03 ``stated_price``, stage 05
# ``allocation_adjustment``) links while its value ties (CV-50 links).
_TIED_LINKS: Final = ("stated_price", "allocation_adjustment")
# CV-50 (D-98 candidate 121): the two allocation columns publish the CURRENT original allocation
# (S05-R-10 total; the repin's share; a created obligation's quota) and link the node that produced
# it BY PRODUCER IDENTITY — the pair the state stamps at the write of the original allocation
# (``original_allocation_links``: the stage 05 sum pair under the booking event when targeted
# shares exist; the repin's pair; a created obligation's pair), else the stage 05 version-state
# node. The identified node must hold the stored value (``_holds_allocation``), else the assembly
# fails closed; a node is never selected because it happens to hold the value.
_CURRENT_ALLOCATION_LINKS: Final = ("original_allocated_amount", "original_allocated_exact")
_ENCODING_HALF_UNIT: Final = Fraction(1, 2 * 10**EXACT_PLACES)


def _last_boundary_node(
    column: str,
    ob: ObligationState,
    allocated: AllocatedState,
    nodes: Mapping[str, TraceNode],
    held: object,
    minor_unit: int,
    posted: bool,
) -> str | None:
    """The ``<column>@<event>:<ob>:<slot>`` node of the latest event that re-measured ``column``
    and holds the stored value: the CV-50 ``returns`` qualifier (the returns-netted re-measurement,
    Codex T1F-R3 ruling) before the boundary's own ``-`` node."""
    for event in sorted(allocated.events, key=lambda item: item.order_key, reverse=True):
        for slot in ("returns", "-"):
            node_id = f"{column}@{event.event_key}:{ob.subject_key}:{slot}"
            node = nodes.get(node_id)
            if node is not None and _ties(node, held, minor_unit, posted):
                return node_id
    return None


_POSTED_SNAPSHOT_COLUMNS: Final = frozenset(
    {"original_stated_price", "original_total_contract_price"}
)


def _holds_snapshot(node: TraceNode, held: object, column: str, minor_unit: int) -> bool:
    """A stamped snapshot producer holds the published column: the posted amount exactly for the
    posted columns, the exact value within the CV-51 limit otherwise (CV-50 rev 1.29)."""
    return _holds_allocation(node, held, minor_unit, column in _POSTED_SNAPSHOT_COLUMNS)


def _holds_allocation(node: TraceNode, held: object, minor_unit: int, posted: bool) -> bool:
    """The allocation node holds the stored value: the posted amount exactly; the exact quota
    within the CV-51 limit of the node's exact value (an exact node holds the 18-place encoding
    of a non-terminating quota such as 1/3: half a unit at 18 places)."""
    if posted:
        return _ties(node, held, minor_unit, True)
    exact = _exact(node)
    return (
        exact is not None
        and isinstance(held, Fraction | int)
        and not isinstance(held, bool)
        and abs(exact - Fraction(held)) <= _ENCODING_HALF_UNIT
    )


def _snapshot_links(
    ob: ObligationState,
    allocated: AllocatedState,
    columns: Mapping[str, object],
    nodes: Mapping[str, TraceNode],
    minor_unit: int,
) -> dict[str, str]:
    """Links of the snapshot and inception columns to the nodes that produced them (D-97 (8))."""
    links: dict[str, str] = {}
    stamped = ob.snapshot_producer_links
    for column in _SNAPSHOT_LINKS:
        node_id = f"{column}:{ob.subject_key}:-"
        if column in stamped:
            # CV-50 rev 1.29 (D-98 123 / 124): the producer identity stamped at the write — the
            # repin's or the creating boundary's ``<column>@<event>`` node — linked and asserted;
            # never a node chosen by value, never a fallback to the stage 05 node.
            held = columns.get(column)
            if held is None:
                continue
            if stamped[column].startswith(ABSENT_PREFIX):
                # A contract-permitted absence (DEV-054 Σw = 0; a LEGACY-VC created line): no
                # producer exists BY CONTRACT. Asserted BY IDENTITY against the one reason admitted
                # for this column (never by prefix), accepted only over the column's existing
                # display (0), no node fabricated, and the NAMED absence published as the column's
                # link so a consumer tells it from an unlinked column and from a node id — distinct
                # from a missing REQUIRED producer, which refuses below (CV-50 rev 1.29).
                state = absence_state(column, stamped[column], held)  # the shared recognition
                if admitted_absence(column, stamped[column]) is None:
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED",
                        "a snapshot column is stamped with an absence not admitted for it",
                        subject_key=ob.subject_key,
                        detail={
                            "rule": "CV-50",
                            "column": column,
                            "state": stamped[column],
                            "admitted": ABSENCE_COLUMNS.get(column, "none"),
                        },
                    )
                if state != "absent":  # an admitted reason over a non-zero (or NULL) value
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED",
                        "a snapshot column stamped absent-by-contract publishes a non-zero value",
                        subject_key=ob.subject_key,
                        detail={
                            "rule": "CV-50",
                            "column": column,
                            "state": stamped[column],
                            "column_value": str(held),
                        },
                    )
                links[column] = stamped[column]
                continue
            node = nodes.get(stamped[column])
            if node is None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "the stamped producer of a snapshot column is absent from the trace",
                    subject_key=ob.subject_key,
                    detail={"rule": "CV-50", "column": column, "node_id": stamped[column]},
                )
            if not _holds_snapshot(node, held, column, minor_unit):
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "the stamped producer of a snapshot column does not hold the published value",
                    subject_key=ob.subject_key,
                    detail={
                        "rule": "CV-50",
                        "column": column,
                        "node_id": stamped[column],
                        "column_value": str(held),
                        "node_value": node.value,
                    },
                )
            links[column] = stamped[column]
            continue
        if column == "original_ssp_selected" and ob.ssp is not None and ob.ssp.residual_candidate:
            # D-98 candidate 23 (T1F-Q-5): the column holds R from ``residual_ssp:<ob>:-``
            # (S05-R-12) and links that node under the alias — one value, one node (CV-53).
            residual = f"residual_ssp:{ob.subject_key}:-"
            if columns.get(column) is not None and residual in nodes:
                links[column] = residual
            continue
        if columns.get(column) is not None and node_id in nodes:
            links[column] = node_id
    for column in _TIED_LINKS:
        held = columns.get(column)
        if held is None:
            continue
        posted = isinstance(held, int) and not isinstance(held, bool)
        boundary = _last_boundary_node(column, ob, allocated, nodes, held, minor_unit, posted)
        if boundary is not None:
            links[column] = boundary  # CV-50 links: the last re-measurement (T1F-Q-3 (c), R3)
            continue
        node_id = f"{column}:{ob.subject_key}:-"
        node = nodes.get(node_id)
        if node is None:
            continue
        if _ties(node, held, minor_unit, posted):
            links[column] = node_id
    for column in _CURRENT_ALLOCATION_LINKS:
        held = columns.get(column)
        if held is None:
            continue
        posted = column == "original_allocated_amount"
        if ob.original_allocation_links is not None:
            node_id = ob.original_allocation_links[1 if posted else 0]  # the stamped producer
        else:
            node_id = f"{column}:{ob.subject_key}:-"  # stage 05's write: the version-state node
        node = nodes.get(node_id)
        if node is None:
            continue  # the producer's node is not in this trace: no link (never another node)
        if not _holds_allocation(node, held, minor_unit, posted):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the producer of the current original allocation does not hold the published "
                "column value",
                subject_key=ob.subject_key,
                detail={
                    "rule": "CV-50",
                    "column": column,
                    "node_id": node_id,
                    "column_value": str(held),
                    "node_value": node.value,
                },
            )
        links[column] = node_id
    return links


def _holds_posted(
    nodes: Mapping[str, TraceNode], node_id: str, value: int, minor_unit: int
) -> bool:
    node = nodes.get(node_id)
    return node is not None and _ties(node, value, minor_unit, True)


def _ties(node: TraceNode, held: object, minor_unit: int, posted: bool) -> bool:
    """The node holds the stored value (posted minor units, or the exact value)."""
    exact = _exact(node)
    if exact is None:
        return False
    if posted:
        return bool(Fraction(Decimal(node.value)) * 10**minor_unit == held)
    return bool(exact == held)


def _excluded_line_versions(
    result: BookResult,
    allocated: AllocatedState,
    as_of: date,
    currency: str,
    memos: Mapping[tuple[str, str], Mapping[str, str | None]] = MappingProxyType({}),
) -> tuple[ObligationVersionOut, ...]:
    """D-88 L7-5-Q-10 (2): one T-CON-11 row per S03-R-11 excluded line of a group that allocated
    nothing (every line excluded): ``obligation_key``, ``scope_flag``, every money column 0, no
    trace nodes, targets, schedules or journal lines. Deviation L8-D-Q-2: a group with obligations
    publishes no excluded-line row, because the platform refuses rows without SSP lineage (CTL-011)
    or an obligation row (test_out_of_scope_line_removed_from_price)."""
    if allocated.obligations:
        return ()
    pob = result.states.get("03")
    drafts = getattr(pob, "routed_out", ())
    rows: list[ObligationVersionOut] = []
    for draft in sorted(drafts, key=lambda item: item.subject_key):
        columns: dict[str, object] = {
            "obligation_key": draft.obligation_key,
            "legacy_record_key": draft.obligation_key,
            "product_code": draft.product_code,
            "scope_flag": _plain(draft.scope_flag),
            "contracting_entity_code": draft.contracting_entity,
            "txn_currency": currency,
            "original_stated_price": 0,
            "stated_price": 0,
            "original_allocated_amount": 0,
            "original_allocated_exact": Fraction(0),
            "allocation_weight": Fraction(0),
            "allocated_amount": 0,
            "allocated_exact": Fraction(0),
            "allocation_adjustment": 0,
            **{name: _plain(value) for name, value in _RECOGNITION_COLUMNS.items()},
            **{name: _plain(value) for name, value in _BALANCE_COLUMNS.items()},
            "pre_standard_revenue_cum": 0,
            "pre_standard_revenue_amount": 0,
            "effective_date": as_of,
            # CV-47: the booking line's memos pass through; no allocation, so no unit rates.
            **memos.get(
                (draft.contract_key, draft.obligation_key),
                MappingProxyType(dict.fromkeys(_MEMO_MEMBERS)),
            ),
            "original_unit_revenue_rate": None,
            "remaining_unit_revenue_rate": None,
        }
        rows.append(
            ObligationVersionOut(
                subject_key=draft.subject_key,
                columns=MappingProxyType(columns),
                trace_nodes=MappingProxyType({}),
            )
        )
    return tuple(rows)


def _statuses(allocated: AllocatedState, book: str) -> tuple[tuple[str, str], ...]:
    """(contract key, E-17) of every member: the latest status segment in the book."""
    found = []
    for view in allocated.contracts:
        history = view.status_in_book.get(book, ())
        if history:
            found.append((view.header.external_id, history[-1][1]))
    return tuple(sorted(found))


def _group_status(allocated: AllocatedState, book: str) -> str | None:
    """T-CON-08 ``status_in_book``: the latest status segment across the members (L3-2-Q-16)."""
    latest = [
        history[-1]
        for view in allocated.contracts
        if (history := view.status_in_book.get(book, ()))
    ]
    return max(latest)[1] if latest else None


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a version column is not integer minor units",
            detail={"column": name, "rule": "DG-ENG-05"},
        )
    return value


def _contract_version(
    book: str,
    allocated: AllocatedState,
    versions: Sequence[ObligationVersionOut],
    book_input: BookInput,
    nodes: Mapping[str, TraceNode],
    currency: str,
    minor_unit: int,
    disclosure: DisclosureState | None = None,
    measures: Mapping[str, ObligationMeasures] | None = None,
) -> ContractVersionOut:
    """T-CON-08 columns of the group's version in the book (ENGINE_SPEC §0.5); ``rpo_amount`` from
    stage 15 — gross of the S15-R-09 exemptions (S15-R-08 rev 1.26; D-98 91a) — and 0 when the
    stage list holds no stage 15 (EDS-1)."""
    from erev_engine.stages.s04_transaction_price import TP_COMPONENTS
    from erev_engine.stages.s13_books.output_measures import boundary_build_up_node

    group = allocated.group_code
    tp = allocated.tp_history[-1] if allocated.tp_history else None
    columns: dict[str, object] = {
        "book_code": book,
        "transaction_currency": currency,
        "status_in_book": _group_status(allocated, book),
        "status_reason_in_book": None,
    }
    trace_nodes: dict[str, str] = {}
    for member, column in TP_COMPONENTS:
        if column == "tp_allocation_basis":
            continue
        columns[column] = 0 if tp is None else getattr(tp, member).posted
        if column == "vc_constrained_amount":
            # A magnitude: R-SGN-01 signs only the returns and payable members (L4-3-Q-33).
            columns[column] = abs(_integer(columns[column], column))
        # D-97 (8) T1-F-2: the build-up of the last reallocating boundary, never the inception
        # node when a boundary re-measured the column (CV-50 links): the latest boundary whose
        # traced build-up holds the appended figure (a boundary that appended no price, or whose
        # build-up was not traced, has no node), else the inception node.
        boundary = (
            None
            if tp is None
            else boundary_build_up_node(
                column,
                group,
                allocated,
                functools.partial(
                    _holds_posted, nodes, value=getattr(tp, member).posted, minor_unit=minor_unit
                ),
            )
        )
        for node_id in (*(() if boundary is None else (boundary,)), f"{column}:{group}:-"):
            if node_id in nodes:
                trace_nodes[column] = node_id
                break
    memo = _returns_memo(allocated, measures)
    if tp is not None and memo is not None and memo != tp.expected_returns.posted:
        # The memo at d_v, not at the last reallocating boundary: a RETURN_RATE version, a return
        # or window expiry moves it without a boundary (S04-R-08, S08-R-02; EX-04-G2; L5-3-Q-1).
        columns["transaction_price"] = tp.total.posted + memo - tp.expected_returns.posted
        columns["expected_returns_amount"] = memo
        trace_nodes.pop("transaction_price", None)
        trace_nodes.pop("expected_returns_amount", None)
    leased = _routed_out_lease_allocation(allocated)
    if tp is not None and leased:
        # D-88 L7-5-Q-6: the price excludes the allocation of routed-out LEASE_842 obligations at
        # the version date; the pool, P1 and out_of_scope_amount stay gross (PT-09; DB-17 V1).
        price = _integer(columns["transaction_price"], "transaction_price")
        columns["transaction_price"] = price - leased
        trace_nodes.pop("transaction_price", None)
    total_ssp = _exact(nodes.get(f"total_ssp:{group}:-"))
    if total_ssp is None:
        total_ssp = sum((ob.resolved_ssp for ob in allocated.obligations), Fraction(0))
    else:
        trace_nodes["total_ssp"] = f"total_ssp:{group}:-"
    columns["total_ssp"] = total_ssp
    for name in ("revenue_cum", "billed_cum", "scheduled_amount", "awaiting_trigger_amount"):
        columns[name] = sum(_integer(version.columns.get(name), name) for version in versions)
    columns["net_position"] = sum(
        _integer(version.columns.get("position_obligation"), "position_obligation")
        for version in versions
    )
    # Gross of the exemptions (S15-R-08 rev 1.26; D-98 candidates 91 / 91a): the expedient contract
    # carries its contractual remaining amount, never 0; the net is disclosure.rpo_after_exemptions.
    columns["rpo_amount"] = 0 if disclosure is None else disclosure.rpo_amount
    if disclosure is not None:
        trace_nodes["rpo_amount"] = disclosure.trace_nodes["rpo_amount"]
    columns["modification_boundary_no"] = max(
        (
            segment.modification_boundary_no
            for ob in allocated.obligations
            for segment in ob.segments
        ),
        default=0,
    )
    columns["pinned_policies"] = _pinned(book_input)
    return ContractVersionOut(
        subject_key=group,
        columns=MappingProxyType(columns),
        trace_nodes=MappingProxyType(dict(sorted(trace_nodes.items()))),
    )


def _routed_out_lease_allocation(allocated: AllocatedState) -> int:
    """Σ a_posted of the routed-out ``LEASE_842`` obligations (S03-R-11, PT-09; D-88 L7-5-Q-6);
    the stage 13 output measures compute the same figure with its node."""
    from erev_engine.stages.s13_books.output_measures import routed_out_lease_allocation

    return routed_out_lease_allocation(allocated)


def _returns_memo(
    allocated: AllocatedState, measures: Mapping[str, ObligationMeasures] | None
) -> int | None:
    """``expected_returns_amount`` at d_v (S04-R-08, S09-R-23; D-77 decision 2); the stage 13
    output measures compute the same figure with its node."""
    from erev_engine.stages.s13_books.output_measures import returns_memo

    return returns_memo(allocated, measures)


def _pinned(book: BookInput) -> Mapping[str, Mapping[str, str]]:
    """T-CON-08 ``pinned_policies``: POL key -> {value, level, source_id} of the widest scope."""
    found: dict[str, Mapping[str, str]] = {}
    for policy in book.policies:
        if policy.scope in {"PRODUCT", "CONTRACT_PERIOD"}:
            continue
        if policy.code in found and policy.scope != "GROUP":
            continue
        found[policy.code] = MappingProxyType(
            {
                "level": policy.level,
                "source_id": policy.source_ref,
                "value": canonical_bytes(policy.value).decode("utf-8"),
            }
        )
    return MappingProxyType(dict(sorted(found.items())))


def _balances(bundle: InputBundle, st: BalanceState) -> tuple[BalanceOut, ...]:
    """T-CON-09 per member contract, entity and period from the stage 10 member balances.

    ``refund_liability``, ``return_asset``, ``deposit_liability``, ``customer_incentive_asset``,
    ``consideration_payable`` and (``ENGINE`` mode, S10-R-19) ``accounts_receivable`` are the stage
    10 member sums (``member_sums.py``): one node per member, period and measure, 0 when no
    component is open (§10.2.4, §10.2.5; D-15). Every ``_txn`` column links its node; at rate 1 the
    ``_functional`` column is a copy of the ``_txn`` value and links the same node (DG-KRN-EXP-01;
    D-97 (8); lane ENG-T1F, T1F-Q-4).
    """
    currency = bundle.group.transaction_currency
    functional = {entity.code: entity.functional_currency for entity in bundle.entities}
    grouped: dict[tuple[str, str], tuple[dict[str, object], dict[str, str]]] = {}
    for target in st.member_balances:
        key = (target.subject_key, target.period_key)
        if key not in grouped:
            columns: dict[str, object] = {
                "entity": target.entity,
                "functional_currency": functional[target.entity],
                "txn_currency": currency,
            }
            grouped[key] = (columns, {})
        columns, trace_nodes = grouped[key]
        columns[f"{target.measure}_txn"] = target.value
        trace_nodes[target.measure] = target.node_id
        if functional[target.entity] == currency:
            columns[f"{target.measure}_functional"] = target.value
            trace_nodes[f"{target.measure}_functional"] = target.node_id
    for target in st.member_sums:
        found = grouped.get((target.subject_key, target.period_key))
        if found is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a member sum names no member balance row",
                subject_key=target.subject_key,
                detail={
                    "rule": "S10-R-23",
                    "measure": target.measure,
                    "period_key": target.period_key,
                },
            )
        columns, trace_nodes = found
        columns[f"{target.measure}_txn"] = target.value
        trace_nodes[target.measure] = target.node_id
        if functional[target.entity] == currency:
            columns[f"{target.measure}_functional"] = target.value
            trace_nodes[f"{target.measure}_functional"] = target.node_id
    return tuple(
        BalanceOut(
            subject_key=subject_key,
            period_key=period_key,
            columns=MappingProxyType(columns),
            trace_nodes=MappingProxyType(dict(sorted(trace_nodes.items()))),
        )
        for (subject_key, period_key), (columns, trace_nodes) in sorted(grouped.items())
    )


def _functional_balances(
    bundle: InputBundle,
    allocated: AllocatedState,
    fx: object,
    rows: tuple[BalanceOut, ...],
) -> tuple[BalanceOut, ...]:
    """T-CON-09 functional columns of foreign-currency entities from stage 12 (lane L5-5).

    ``_balances`` fills ``<column>_functional`` only at rate 1; a foreign-currency entity takes
    the contract liability, asset and unbilled receivable from the stage 12 layers and reclass
    shares (S12-R-09, S10-R-23; L5-5-Q-13) and links the stage 12 member nodes (D-97 (8) T1F-Q-4).
    """
    from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
    from erev_engine.stages.s12_fx_entities import FxState
    from erev_engine.stages.s12_fx_entities.balances import functional_balance_columns

    currency = bundle.group.transaction_currency
    functional = {entity.code: entity.functional_currency for entity in bundle.entities}
    if not isinstance(fx, FxState) or all(code == currency for code in functional.values()):
        return rows
    periods = {
        entity.code: tuple(
            period.period_key for period in sorted(entity.periods, key=lambda p: p.start_date)
        )
        for entity in bundle.entities
    }
    member_of = {
        ob.subject_key: contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
        for ob in allocated.obligations
    }
    computed = functional_balance_columns(
        rows,
        fx,
        txn_currency=currency,
        functional=functional,
        periods=periods,
        member_of=member_of,
    )
    # D-97 (8) T1F-Q-4: the stage 12 member targets carry the same values with their nodes
    # (``balances.functional_member_targets``, ``fx.functional_member.v1``); the assembler checks
    # every foreign-currency functional column against them and links.
    targets = {
        (item.subject_key, item.period_key, item.measure): item
        for item in fx.functional_member_balances
    }
    out: list[BalanceOut] = []
    for row in computed:
        entity = str(row.columns.get("entity"))
        if functional.get(entity, currency) == currency:
            out.append(row)
            continue
        columns = dict(row.columns)
        trace_nodes = dict(row.trace_nodes)
        for column, held in list(columns.items()):
            if not column.endswith("_functional"):
                continue
            found = targets.get((row.subject_key, row.period_key, column))
            if found is None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a foreign-currency functional column has no stage 12 member target",
                    subject_key=row.subject_key,
                    detail={"rule": "S12-R-09", "column": column, "period_key": row.period_key},
                )
            if found.value != held:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "the assembled functional column disagrees with the stage 12 member target",
                    subject_key=row.subject_key,
                    detail={
                        "rule": "DG-KRN-EXP-01",
                        "column": column,
                        "assembled": str(held),
                        "measured": str(found.value),
                    },
                )
            trace_nodes[column] = found.node_id
        out.append(
            BalanceOut(
                subject_key=row.subject_key,
                period_key=row.period_key,
                columns=MappingProxyType(columns),
                trace_nodes=MappingProxyType(dict(sorted(trace_nodes.items()))),
            )
        )
    return tuple(out)


def _cost_loss_columns(
    bundle: InputBundle, costs: object, rows: tuple[BalanceOut, ...]
) -> tuple[BalanceOut, ...]:
    """T-CON-09 ``cost_asset_carrying_txn`` and ``loss_provision_txn`` from the stage 11 member
    sums (S11-R-14, S11-R-15; D-92 (3); lanes L5-5 and ENG-C7): every row takes the member's value
    and links its node (DG-KRN-EXP-01; D-97 (8); lane ENG-T1F)."""
    from erev_engine.stages.s11_costs_loss import CostLossState

    if not isinstance(costs, CostLossState):
        return rows
    sums = {(item.subject_key, item.period_key, item.measure): item for item in costs.member_sums}
    out: list[BalanceOut] = []
    for row in rows:
        columns = dict(row.columns)
        trace_nodes = dict(row.trace_nodes)
        for measure_name in ("cost_asset_carrying", "loss_provision"):
            found = sums.get((row.subject_key, row.period_key, measure_name))
            if found is None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a member balance row has no stage 11 member sum",
                    subject_key=row.subject_key,
                    detail={
                        "rule": "S11-R-15",
                        "measure": measure_name,
                        "period_key": row.period_key,
                    },
                )
            # T-CON-09 keeps no ``_functional`` column for these two measures.
            columns[f"{measure_name}_txn"] = found.value
            trace_nodes[measure_name] = found.node_id
        out.append(
            BalanceOut(
                subject_key=row.subject_key,
                period_key=row.period_key,
                columns=MappingProxyType(columns),
                trace_nodes=MappingProxyType(dict(sorted(trace_nodes.items()))),
            )
        )
    return tuple(out)


def _plain(value: object) -> object:
    """A column value: enum literals as strings, mappings and tuples read-only."""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _plain(item) for key, item in sorted(value.items())})
    if isinstance(value, list | tuple):
        return tuple(_plain(item) for item in value)
    return value


def _columns(item: object, drop: Sequence[str]) -> Mapping[str, object]:
    if not dataclasses.is_dataclass(item) or isinstance(item, type):
        raise TypeError(f"no columns of {type(item).__name__}")
    return MappingProxyType(
        {
            member.name: _plain(getattr(item, member.name))
            for member in dataclasses.fields(item)
            if member.name not in drop
        }
    )


def _diagnostics(cb: CanonicalBundle, results: Sequence[BookResult]) -> tuple[Diagnostic, ...]:
    """CV-41, CV-43: the ``WARNING`` and ``INFO`` findings, once per book using the output
    (S13-R-03); stage 01 findings carry no book."""
    found: dict[tuple[tuple[int, str, str, str, bytes], int], tuple[str | None, Finding]] = {}
    for finding in cb.findings:
        if finding.severity in _DIAGNOSTIC:
            found.setdefault((finding.sort_key(), _rank(None)), (None, finding))
    for result in results:
        for state in (*result.states.values(), result.state):
            for finding in _findings_of(state):
                if finding.severity in _DIAGNOSTIC:
                    key = (finding.sort_key(), _rank(result.book))
                    found.setdefault(key, (result.book, finding))
    return tuple(
        Diagnostic(
            code=finding.code,
            severity=finding.severity,
            book_code=book,
            subject_key=finding.subject_key,
            event_key=finding.event_key,
            detail=MappingProxyType(dict(finding.detail)),
        )
        for book, finding in (found[key] for key in sorted(found))
    )


# --- Fail-closed identities (DG-ENG-05; CTL-012) -------------------------------------------------


def assert_identities(output: OutputBundle, results: Sequence[BookResult]) -> None:
    """Raise ``ENGINE_INVARIANT_VIOLATED`` naming the first identity that fails (DG-ENG-05)."""
    for book, result in zip(output.books, results, strict=True):
        version = book.contract_version
        if version is not None:
            _assert_allocation(book, version, _allocated_of(result))
        _assert_entries(book)
        _assert_exact_companions(book)


def _assert_exact_companions(book: BookOutput) -> None:
    """ENGINE_SPEC CV-64 rev 1.30 as amended (D-98 134 amendment 1): every posted node that names
    an exact companion in ``params["exact_node"]`` is validated per stored field against its own
    encoding of the replayed exact (``exact_companion_failures``: the companion's value and the
    node's residue, each independently) — the PRODUCTION side of the cross-check, run on every
    computation; the explain verification and the replay-verify paths run it again on the stored
    trace."""
    failures = exact_companion_failures(book.trace)
    if failures:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a posted node fails the per-field validation against its replayed exact companion",
            detail={
                "rule": "CV-64",
                "book_code": book.book_code,
                "failures": "; ".join(failures[:8]),
            },
        )


def _identity(
    identity: str, book: BookOutput, subject_key: str, expected: int, actual: int, **extra: str
) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        f"{identity} fails",
        subject_key=subject_key,
        detail={
            **extra,
            "actual": str(actual),
            "book_code": book.book_code,
            "expected": str(expected),
            "identity": identity,
        },
    )


def _assert_allocation(
    book: BookOutput, version: ContractVersionOut, allocated: AllocatedState | None
) -> None:
    columns = version.columns
    total = sum(
        _integer(item.columns.get("allocated_amount"), "allocated_amount")
        for item in book.obligation_versions
    )
    if allocated is not None and allocated.tp_history:
        basis = allocated.tp_history[-1].allocation_basis.posted
        returns = _integer(columns.get("expected_returns_amount"), "expected_returns_amount")
        if total - returns != basis:
            raise _identity(IDENTITY_BASIS, book, version.subject_key, basis, total - returns)
    price = _integer(columns.get("transaction_price"), "transaction_price")
    payable = _integer(columns.get("consideration_payable_amount"), "consideration_payable_amount")
    # DB-17 V1 over the IN_SCOPE_606 rows: routed-out lease rows leave the price (D-88 L7-5-Q-6).
    in_scope = sum(
        _integer(item.columns.get("allocated_amount"), "allocated_amount")
        for item in book.obligation_versions
        if item.columns.get("scope_flag", _IN_SCOPE) == _IN_SCOPE
    )
    if in_scope != price - payable:
        raise _identity(IDENTITY_PRICE, book, version.subject_key, price - payable, in_scope)
    for item in book.obligation_versions:
        amount = _integer(item.columns.get("allocated_amount"), "allocated_amount")
        parts = sum(_integer(item.columns.get(name), name) for name in _REMAINDER_PARTS)
        if amount != parts:
            raise _identity(IDENTITY_OBLIGATION, book, item.subject_key, amount, parts)


def _assert_entries(book: BookOutput) -> None:
    for intent in book.posting_intents:
        sides: dict[tuple[str, str], list[int]] = {}
        for line in intent.lines:
            for measure, code, amount in (
                ("transaction", line.txn_currency, line.amount_txn),
                ("functional", line.functional_currency, line.amount_functional),
            ):
                totals = sides.setdefault((measure, code), [0, 0])
                totals[0 if line.side == "D" else 1] += amount
        for (measure, code), (debits, credits) in sorted(sides.items()):
            if debits != credits:
                raise _identity(
                    IDENTITY_ENTRY,
                    book,
                    intent.subject_key,
                    debits,
                    credits,
                    currency=code,
                    entity=intent.entity,
                    entry_key=intent.entry_key,
                    measure=measure,
                    posting_period_key=intent.posting_period_key,
                )

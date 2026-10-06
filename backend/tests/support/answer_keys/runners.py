"""Answer-key runners (docs/dev-guide.md §9.5.8 DG-AK-40, DG-AK-44; ENGINE_SPEC §0.4; EKC-11).

``run_engine`` assembles, per checkpoint, one ``InputBundle`` for every combination group with a
contract booked at the checkpoint, from the key's world, its contracts and the timeline items with
``seq ≤ after_seq``. Events carry ``record_seq = seq`` and the §9.5.5 record times; ``known_at`` is
the record time of the ``after_seq`` item; period states start from ``world.period_states`` and
follow the ``period_state`` items at their ``seq`` position. Handles resolve to natural keys
(ENGINE_SPEC CV-21, CV-22). The runner needs no database and reads no clock. Until BUILD_SPEC END-9
builds ``erev_engine.compute``, ``run_engine`` fails closed (B3-BS2-06).

A timeline item carrying ``expect_problem`` (§9.5.5; D-79) enters only its own step bundle: the
items of its combination group with ``seq`` up to its own, earlier ``expect_problem`` items
excluded. ``compute`` must raise ``EngineError`` with that code. The item never enters a checkpoint
bundle or a later step bundle, and the ``ERROR`` findings of the step (CV-15) join the exception
rows of every checkpoint at or after it.

``population_findings`` evaluates POLICIES §3.3 for every ``world.ssp_books`` entry that carries
``population`` through ``erev_api.domain.ssp.range_validation.validate_ranges``, without the
engine (DG-AK-45; BUILD_SPEC RFD-13, BS3-D-11). ``run_engine`` stores those findings on the
result, and a checkpoint ``exceptions`` row with ``subject`` compares with them (§9.5.6).
"""

from __future__ import annotations

import decimal
import json
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast
from zoneinfo import ZoneInfo

import erev_engine
from erev_api.domain.ssp import range_validation
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    BookOutput,
    BundleComponentInput,
    ContractInput,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    FxRateInput,
    GroupInput,
    InputBundle,
    IntentLine,
    JudgementInput,
    MappingRuleInput,
    MaterialRightInput,
    ModificationInput,
    NoncashInput,
    ObligationVersionOut,
    OutputBundle,
    PayableInput,
    PaymentPointInput,
    PeriodInput,
    PortfolioInput,
    PostingIntent,
    ProductInput,
    ResolvedPolicyInput,
    RuleInput,
    RuleSetInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217, CurrencyTable
from erev_engine.dates import month_end
from erev_engine.errors import EngineError
from erev_engine.money import (
    DECIMAL_CONTEXT,
    format_exact,
    format_money,
    round_half_up,
    to_fraction,
)
from erev_engine.rules import validate_conditions
from erev_engine.stages import BOUNDARY_EVENT_TYPES
from erev_engine.trace import reevaluate
from pydantic import BaseModel
from support import intent_totals
from support.answer_keys.loader import (
    MONEY_PAYLOAD_MEMBERS,
    AnswerKeyError,
    LoadedKey,
    contract_version_columns,
    obligation_columns,
)
from support.answer_keys.models import (
    AnswerKey,
    BalanceAmounts,
    BalanceRow,
    Checkpoint,
    Contract,
    ContractBlock,
    ContractLine,
    DeltaLine,
    Entity,
    Estimate,
    EstimateVersion,
    EventItem,
    ExceptionRow,
    GroupBlock,
    Judgement,
    Modification,
    Money,
    MoneyAmount,
    PeriodStateItem,
    PolicyValue,
    PolicyValues,
    SubledgerBlock,
    VersionBlock,
)
from support.answer_keys.terms import ADD, REMOVE, terms_line_action
from support.bundles import policy_set, policy_value
from support.golden_streams import LEGACY_MATERIAL_RIGHT, parity_templates

__all__ = [
    "PLATFORM_RUNNER_MISSING",
    "CheckpointBundles",
    "CheckpointMismatchError",
    "CheckpointRun",
    "Mismatch",
    "RunResult",
    "StepBundle",
    "StepOutcome",
    "assert_checkpoints",
    "population_findings",
    "run_engine",
]

BOOK_ORDER: Final = ("ASC606", "IFRS15", "LEGACY")  # RCP-11
TRIGGER: Final = "COMMAND"  # E-87
# The close-run passes a checkpoint also runs over the compute intents: RCP-08(b), S14-R-05 and
# S14-R-07 post JET-06 and its reversal in the NETTING_RECLASS pass, and POLICIES JET-06 posts both
# at every period end in both modes (L5-3-Q-6, L5-5-Q-3; D-85).
# D-85a (L6-2-Q-2): every pass RCP-08(b) orders after compute, so FX_REMEASUREMENT (JET-10a, 10a′,
# 10b and 10d period end; S14-R-05) runs first and NETTING_RECLASS reads its intents as posted.
# D-91 gaps (iii) (lane ENG-D1): the CLOSE_RELEASE pass runs too, after FX_REMEASUREMENT and before
# NETTING_RECLASS, so the TIME amounts of the close period post (the JET-01b 25-7 revenue at a dated
# point; S14-R-05). FX_REMEASUREMENT keeps the first place so the JET-10 period-end remeasurements,
# whose parts name both passes, post where D-85a measured them; no corpus key releases another
# CLOSE_RELEASE TIME amount (no obligation is released at close, L3-2-Q-15), so the earlier keys are
# unchanged. RCP-08 lists CLOSE_RELEASE first; the ordering is a lane question (ENG-D1 record).
CLOSE_PASSES: Final = ("FX_REMEASUREMENT", "CLOSE_RELEASE", "NETTING_RECLASS")
EVENT_ORIGIN: Final = "API"  # T-CON-05 origin of events appended through commands
DEFAULT_PERIOD_STATE: Final = "open"  # §9.5.3: unlisted periods are open
FUTURE_PERIOD_STATE: Final = "future"  # E-04: calendar months after world.periods.to (RCP-03)
MAPPING_VERSION_KEY: Final = "ACCOUNT-MAPPING@v1"
# D-83 ruling 1: a key product without `principal_agent` resolves as PRINCIPAL, because the keys'
# figures assume gross revenue. Platform products keep the T-REF-20 default NOT_ASSESSED.
KEY_PRINCIPAL_AGENT: Final = "PRINCIPAL"
# D-85 ruling 3: keys win for numbers, so the runner supplies the questionnaire outcome the key's
# figures imply and records the derivation in the run note. A price change whose checkpoints expect
# a REFUND_LIABILITY credit in the modification's period settles CREDIT_OR_REFUND (JET-05c). The
# engine default FUTURE_PRICING (S06-R-07) stays for platform commands.
SETTLEMENT_MEMBER: Final = "price_change_settlement"
KEY_IMPLIED_SETTLEMENT: Final = "CREDIT_OR_REFUND"
# D-87 L6-5-Q-27: a key's catch_up_estimate_cum compares with the engine's catch_up_tp_change_cum +
# catch_up_estimate_cum for that row; a row that also asserts catch_up_tp_change_cum is strict.
CATCH_UP_ESTIMATE: Final = "catch_up_estimate_cum"
CATCH_UP_TP_CHANGE: Final = "catch_up_tp_change_cum"
# D-87 L5-3-Q-9 (D-85 pattern): a key line resolving EXPECTED_RETURNS with no RETURN_RATE element,
# no RETURN_RECORDED and no such judgement gets a REVIEWED OTHER judgement returns_immaterial true.
# S04-R-08a and RETURN_ESTIMATE_MISSING stay for platform commands.
RETURNS_MODEL: Final = "returns.model"  # POL-051
EXPECTED_RETURNS_MODEL: Final = "EXPECTED_RETURNS"
RETURN_RATE_KIND: Final = "RETURN_RATE"
IMMATERIAL_RETURNS_HANDLE: Final = "RUNNER-RETURNS-IMMATERIAL"
# D-87 L5-3-Q-19 = L5-5-Q-17: the runner converts terms-form modification lines to T-CON-06 delta
# form; T-CON-06 and the engine are unchanged (606-10-25-12, 25-13).
# D-88 L7-5-Q-13 (a): a delta-form CHANGE line (quantity_delta 0) of a TERMINATION ending by d is
# read as REMOVE, as S06-R-21 carries it; S06-R-21 stays unchanged for platform commands.
TERMINATION_KIND: Final = "TERMINATION"
# D-88 L7-5-Q-2 (ii) (D-85 pattern): an existing obligation that a checkpoint's
# modifications[].proposed_treatments lists, and the key modification leaves unanswered, gets the
# T-CON-06 questionnaire member remaining_goods_distinct_from_transferred (true for PROSPECTIVE,
# false for CUMULATIVE_CATCH_UP) with a run note; the S06-R-05 defaults stay for platform commands.
REMAINING_DISTINCT_MEMBER: Final = "remaining_goods_distinct_from_transferred"
PROPOSED_DISTINCT: Final[Mapping[str, bool]] = MappingProxyType(
    {"PROSPECTIVE": True, "CUMULATIVE_CATCH_UP": False}
)
# D-88 L7-5-Q-11 (D-85 pattern): a key line whose template obligation_kind is STANDARD, that names
# bundle_parent_obligation_key, and whose obligation key no checkpoint row and no timeline payload
# names gets a REVIEWED POB_DISTINCT_OVERRIDE {distinctness nondistinct,
# integrates_into_obligation_key the bundle parent}, recorded in the run note; S03-R-05 stays
# unchanged for platform commands.
NONDISTINCT_TOPIC: Final = "POB_DISTINCT_OVERRIDE"
NONDISTINCT_HANDLE: Final = "RUNNER-POB-NONDISTINCT"
STANDARD_KIND: Final = "STANDARD"
_TERMS_MEMBERS: Final = (
    "start_date", "end_date", "stratification", "ssp_version_label", "memo_1", "memo_2", "memo_3",
)  # fmt: skip
# D-87 L4-3-Q-24 (a): an AGENT key product without a PRINCIPAL_AGENT record gets the REVIEWED
# outcome {conclusion AGENT, gross_to_net_basis FIXED_FEE, amount the line total price}, recorded in
# the run note; S03-R-09 still raises for platform commands.
KEY_AGENT_BASIS: Final = "FIXED_FEE"
AGENT_RECORD_HANDLE: Final = "D87-L4-3-Q-24-PA"
# Level P assembly as erev_api.domain.contracts.bundles does it (TERM_EVENTS, CONVENTION_POLICY).
TERM_EVENTS: Final = frozenset({"CONTRACT_BOOKED", "CONTRACT_AMENDED"})
CONVENTION_POLICY: Final = "recognition.time_convention"  # POL-090
MISSING_COMPUTE: Final = (
    "erev_engine.compute is not built yet (BUILD_SPEC END-9); the engine runner fails closed "
    "(B3-BS2-06)"
)
# A passing activation checklist for CONTRACT_ACTIVATED with `payload: {}` (§9.5.5).
PASSING_CHECKLIST: Final = ({"code": "ANSWER_KEY_WORLD", "status": "PASSED"},)
# 04 §16.3 payload members typed Decimal or date; MONEY_PAYLOAD_MEMBERS are Money.
DECIMAL_PAYLOAD_MEMBERS: Final = frozenset({
    "quantity", "cumulative_progress_ratio", "cumulative_weight", "hours_to_date",
    "exercised_quantity", "units_received",
})  # fmt: skip
DATE_PAYLOAD_MEMBERS: Final = frozenset({
    "issue_date", "due_date", "receipt_date", "usage_period_start", "usage_period_end",
    "service_period_start", "service_period_end", "cutover_date",
})  # fmt: skip
# API-S-ContractLine and T-CON-06 delta line members typed Decimal (or Money) and date.
LINE_DECIMAL_MEMBERS: Final = frozenset({
    "quantity", "total_price", "unit_price", "out_of_scope_amount", "quantity_delta",
    "consideration_delta",
})  # fmt: skip
LINE_DATE_MEMBERS: Final = frozenset({"start_date", "end_date"})
# Contract members that are objects of their own rather than API-S-ContractCreate header fields.
NON_HEADER_MEMBERS: Final = frozenset({
    "external_id", "customer", "contracting_entity", "renewal_of", "combination_group",
    "combination_criterion", "lines", "policy_overrides", "judgements", "estimates",
    "material_rights", "modifications", "payment_schedule", "noncash_consideration",
    "consideration_payable",
})  # fmt: skip

_SUBJECT_ESCAPES: Final = str.maketrans(
    {"%": "%25", "/": "%2F", "@": "%40", "#": "%23", ":": "%3A"}
)


@dataclass(frozen=True, slots=True)
class CheckpointBundles:
    """The engine inputs of one checkpoint (DG-AK-40)."""

    name: str
    after_seq: int
    as_of: date
    book: str
    known_at: datetime
    bundles: tuple[InputBundle, ...]  # one per combination group with a booked member; group code


@dataclass(frozen=True, slots=True)
class CheckpointRun:
    checkpoint: CheckpointBundles
    outputs: tuple[OutputBundle, ...]  # aligned with ``checkpoint.bundles``
    # The ``CLOSE_PASSES`` outputs over each bundle's compute intents, aligned with the bundles
    # when present (RCP-08(b); L5-3-Q-6).
    passes: tuple[tuple[OutputBundle, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class StepBundle:
    """The engine input of one timeline item carrying ``expect_problem`` (§9.5.5; D-79)."""

    seq: int
    expected_code: str
    known_at: datetime
    bundle: InputBundle  # the item's combination group only


@dataclass(frozen=True, slots=True)
class StepOutcome:
    step: StepBundle
    actual: str  # the code of the EngineError raised, or COMPUTED when compute returned
    detail: Mapping[str, str]  # the EngineError detail; ``findings`` holds CV-15 canonical JSON


@dataclass(frozen=True, slots=True)
class RunResult:
    key_id: str
    runner: str
    checkpoints: tuple[CheckpointRun, ...]  # key order
    steps: tuple[StepOutcome, ...] = ()  # timeline order
    range_findings: tuple[range_validation.RangeFinding, ...] = ()  # DG-AK-45, world order
    notes: tuple[str, ...] = ()  # the run note: inputs the runner derived from the key (D-85)


COMPUTED: Final = "computed"
PARITY_PRESET: Final = "LEGACY_PARITY"


def run_engine(key: LoadedKey) -> RunResult:
    """Build every checkpoint's and step's bundles and compute them (DG-AK-40; D-79), and evaluate
    the SSP populations of the world (DG-AK-45)."""
    if key.key.runner != "engine":
        raise AnswerKeyError(key.path, "/runner", "run_engine runs keys with runner: engine")
    assembler = _Assembler(key)
    checkpoints = assembler.checkpoints()
    steps = assembler.steps()
    findings = population_findings(key)
    compute = getattr(erev_engine, "compute", None)
    if compute is None:
        raise AnswerKeyError(key.path, "", MISSING_COMPUTE)
    pass_names = CLOSE_PASSES if compute is _ENGINE_COMPUTE else ()
    runs = tuple(_checkpoint_run(compute, checkpoint, pass_names) for checkpoint in checkpoints)
    outcomes = tuple(_step_outcome(compute, step) for step in steps)
    return RunResult(key.key.id, key.key.runner, runs, outcomes, findings, tuple(assembler.notes))


# The engine's own compute. A test that stubs ``erev_engine.compute`` stands in for the whole run,
# so no close pass runs over the stub's outputs.
_ENGINE_COMPUTE: Final = getattr(erev_engine, "compute", None)


def _checkpoint_run(
    compute: Callable[[InputBundle], object],
    checkpoint: CheckpointBundles,
    pass_names: Sequence[str],
) -> CheckpointRun:
    """``compute`` per bundle, then each close-run pass of ``pass_names`` over the intents posted
    so far (RCP-08(b); S14-R-05, S14-R-07; L5-3-Q-6)."""
    outputs = tuple(cast(OutputBundle, compute(bundle)) for bundle in checkpoint.bundles)
    if not pass_names:
        return CheckpointRun(checkpoint, outputs)
    passes: list[tuple[OutputBundle, ...]] = []
    with decimal.localcontext(DECIMAL_CONTEXT):  # the context compute runs the stages in (ENG-03)
        for bundle, output in zip(checkpoint.bundles, outputs, strict=True):
            done: list[OutputBundle] = []
            for name in pass_names:
                done.append(intent_totals.close_pass(bundle, [output, *done], name))
            passes.append(tuple(done))
    return CheckpointRun(checkpoint, outputs, tuple(passes))


def _forced(code: str, book_code: str) -> bool:
    """POLICIES §1 "FORCED": the framework fixes the value for the book, so no key value applies;
    ``LEGACY`` follows the ASC 606 flags (``erev_api.registry.resolve.is_forced``; L5-5-Q-25)."""
    spec = POLICY_PARAMETERS[code]
    return spec.is_forced_ifrs15 if book_code == "IFRS15" else spec.is_forced_asc606


def population_findings(key: LoadedKey) -> tuple[range_validation.RangeFinding, ...]:
    """DG-AK-45: the POLICIES §3.3 findings of every ``world.ssp_books`` entry that carries
    ``population``, under the tenant value of POL-073 or, without one, the preset's value. Each
    range row of such an entry has the subject ``ssp:<book code>:<version label>:<product>``, the
    label being ``legacy_version_label``, else ``effective_from_date`` (§9.5.6). No engine call."""
    world = key.key.world
    raw = world.policies.tenant.get(range_validation.PARAMETER)
    if raw is None:
        spec = POLICY_PARAMETERS[range_validation.PARAMETER]
        parity = world.tenant.preset == PARITY_PRESET and spec.legacy_parity_value is not None
        raw = spec.legacy_parity_value if parity else spec.default_asc606
    rows: list[range_validation.RangeRow] = []
    for book in world.ssp_books:
        for version in book.versions:
            label = version.legacy_version_label or version.effective_from_date or ""
            for entry in version.entries:
                if entry.population is None:
                    continue
                population = range_validation.Population(
                    int(entry.population.observation_count), int(entry.population.inside_count)
                )
                rows.extend(
                    range_validation.RangeRow(
                        subject=f"ssp:{book.code}:{label}:{entry.product}",
                        label=entry.product,
                        low_value=None if band.low_value is None else Decimal(band.low_value),
                        mid_value=None if band.mid_value is None else Decimal(band.mid_value),
                        high_value=None if band.high_value is None else Decimal(band.high_value),
                        population=population,
                    )
                    for band in entry.ranges
                )
    return range_validation.validate_ranges(rows, policy_value(raw))


def _step_outcome(compute: Callable[[InputBundle], object], step: StepBundle) -> StepOutcome:
    try:
        compute(step.bundle)
    except EngineError as error:
        return StepOutcome(step, error.code, error.detail)
    return StepOutcome(step, COMPUTED, {})


def _build_checkpoint_bundles(loaded: LoadedKey) -> tuple[CheckpointBundles, ...]:
    """One ``CheckpointBundles`` per checkpoint, in key order."""
    return _Assembler(loaded).checkpoints()


def _build_step_bundles(loaded: LoadedKey) -> tuple[StepBundle, ...]:
    """One ``StepBundle`` per ``expect_problem`` item, in timeline order."""
    return _Assembler(loaded).steps()


# --- Scalars -------------------------------------------------------------------------------------


def subject_component(value: str) -> str:
    """CV-21: percent-encode ``%``, ``/``, ``@``, ``#`` and ``:`` in a subject key component."""
    return value.translate(_SUBJECT_ESCAPES)


def obligation_subject_key(contract_key: str, obligation_key: str) -> str:
    return f"{subject_component(contract_key)}/{subject_component(obligation_key)}"


def _estimate_parameters(estimate: Estimate, version: EstimateVersion) -> dict[str, object]:
    """The version's T-CON-13 parameters plus the element's T-CON-12
    ``allocation_criteria_evidence`` when the key states it (S05-R-14; D-91)."""
    parameters: dict[str, object] = dict(version.parameters or {})
    if estimate.allocation_criteria_evidence is not None:
        parameters["allocation_criteria_evidence"] = estimate.allocation_criteria_evidence
    return dict(sorted(parameters.items()))


def _amount(value: object) -> Decimal:
    """A Money member (``{amount, currency}`` or a string) or a decimal string as ``Decimal``."""
    if isinstance(value, MoneyAmount):
        value = value.amount
    elif isinstance(value, Mapping):
        value = value["amount"]
    if not isinstance(value, str):
        raise TypeError(f"expected a decimal string, got {type(value).__qualname__}")
    return Decimal(value)


def _optional_amount(value: object) -> Decimal | None:
    return None if value is None else _amount(value)


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise TypeError(f"expected an ISO date string, got {type(value).__qualname__}")
    return date.fromisoformat(value)


def _optional_date(value: object) -> date | None:
    return None if value is None else _date(value)


def _render(value: object) -> str:
    """Table 0.4-A outcome members as strings: ``true`` or ``false`` for booleans."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _content_sha256(model: BaseModel) -> str:
    return sha256_hex(model.model_dump(mode="json", by_alias=True))


def _month_start(text: str) -> date:
    return date.fromisoformat(f"{text}-01")


def _line_payload(line: ContractLine | DeltaLine) -> dict[str, object]:
    """API-S-ContractLine (or T-CON-06 delta line) members with Decimal and date values."""
    payload: dict[str, object] = {}
    for name, value in line.model_dump(exclude_none=True).items():
        if name in LINE_DECIMAL_MEMBERS:
            payload[name] = _amount(value)
        elif name in LINE_DATE_MEMBERS:
            payload[name] = _date(value)
        else:
            payload[name] = value
    return payload


def _names_key(value: object, obligation_key: str) -> bool:
    """A JSON payload value names ``obligation_key``, as a string or a member name (L7-5-Q-11)."""
    if isinstance(value, str):
        return value == obligation_key
    if isinstance(value, Mapping):
        return any(
            name == obligation_key or _names_key(member, obligation_key)
            for name, member in value.items()
        )
    if isinstance(value, Sequence):
        return any(_names_key(member, obligation_key) for member in value)
    return False


def _flat_policy_values(values: PolicyValues | None, path: Path, pointer: str) -> dict[str, str]:
    """Level P values (T-REF-20, T-REF-23 ``policy_values``) as option literals."""
    flat: dict[str, str] = {}
    for code, value in sorted((values or {}).items()):
        rendered = policy_value(value)
        if isinstance(rendered, Mapping):
            raise AnswerKeyError(
                path, f"{pointer}/{code}", "structured level P values are not supported"
            )
        flat[code] = rendered if isinstance(rendered, str) else ",".join(rendered)
    return flat


def _pinned_values(values: PolicyValues | None) -> dict[str, PolicyValue]:
    """The pin K members of level P values; pin P values stay PERIOD-scoped."""
    return {
        code: value
        for code, value in (values or {}).items()
        if code in POLICY_PARAMETERS and POLICY_PARAMETERS[code].pin == "K"
    }


# --- Assembly ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _EventRefs:
    modification_key: str | None = None
    estimate_version_key: str | None = None


class _Assembler:
    """Shared world state of one key; ``checkpoints`` builds the per-checkpoint bundles."""

    def __init__(self, loaded: LoadedKey) -> None:
        self.path = loaded.path
        self.key: AnswerKey = loaded.key
        world = self.key.world
        self.contracts = {contract.external_id: contract for contract in self.key.contracts}
        self.timeline = sorted(self.key.timeline, key=lambda item: item.seq)
        self.positions = {item.seq: index for index, item in enumerate(self.key.timeline)}
        self.times = self._recorded_times()
        self.world_start = self._world_start()
        # The tenant is configured before the period it reports on: setup happens one second before
        # the first period starts in every entity's time zone (and before the first item), so a
        # policy effective from that period start is a future period start at setup (04 §16.5;
        # POLICIES §0.5 rule 3; batch #6 keys-platform).
        first_item = self.times[self.timeline[0].seq]
        self.policy_effective_from = self._period_start_instant()
        self.setup_at = min(first_item, self._earliest_local_midnight()) - timedelta(seconds=1)
        self.world_end = _month_start(world.periods.to)
        self.calendar_end = self._calendar_end()
        self.books = self._books()
        self.products = {product.code: product for product in world.products}
        self.customers = {customer.code: customer for customer in world.customers}
        self.account_mapping = self._account_mapping()
        self.templates = self._templates()
        self.ssp_versions = self._ssp_versions()
        self.rule_sets = self._rule_sets()
        self.fx_rates = self._fx_rates()
        # (contract, modification reference) -> the engine-proposed treatments (§9.5.4).
        self.proposed: dict[tuple[str, str], dict[str, str]] = {}
        self.notes: list[str] = []
        # (contract, modification reference) -> delta lines of a TERMINATION whose delta-form CHANGE
        # lines ending by d were read as REMOVE (D-88 L7-5-Q-13); filled by _terms_conversions.
        self.terminations: dict[tuple[str, str], tuple[dict[str, object], ...]] = {}
        # (contract, modification reference) -> delta lines of terms-form lines (L5-3-Q-19).
        self.terms = self._terms_conversions()
        # (contract, modification reference) -> obligation key -> the supplied answer
        # remaining_goods_distinct_from_transferred (D-88 L7-5-Q-2 (ii)).
        self.distinct_answers = self._implied_distinct_answers()
        # (contract, modification reference) -> the implied price_change_settlement (D-85).
        self.settlements = self._implied_settlements()
        # contract -> seq of the assessment the supplied CONTRACT_ACTIVATED follows (L6-5-Q-12).
        self.activations = self._implied_activations()
        self._catch_up_aliases()
        # contract -> obligation keys given the supplied returns_immaterial judgement (L5-3-Q-9).
        self.immaterial = self._implied_immaterial_returns()
        # contract external id -> the REVIEWED agent records the key implies (D-87 L4-3-Q-24 (a)).
        self.agent_records = self._implied_agent_records()
        # contract external id -> the REVIEWED POB_DISTINCT_OVERRIDE records the key implies
        # (D-88 L7-5-Q-11).
        self.nondistinct = self._implied_nondistinct_lines()

    def error(self, pointer: str, message: str) -> AnswerKeyError:
        return AnswerKeyError(self.path, pointer, message)

    def _implied_settlements(self) -> dict[tuple[str, str], str]:
        """D-85: the ``price_change_settlement`` a key's figures imply for a modification that names
        none. A ``price_change_amount`` whose checkpoints expect a ``REFUND_LIABILITY`` credit in
        the contracting entity's period of the effective date is settled by credit memo or refund
        (JET-05c; S06-R-07). Each derivation is recorded as a run note."""
        found: dict[tuple[str, str], str] = {}
        for contract in self.key.contracts:
            for modification in contract.modifications or ():
                named = any(
                    SETTLEMENT_MEMBER in answers
                    for answers in (modification.questionnaire or {}).values()
                )
                if modification.price_change_amount is None or named:
                    continue
                if (contract.external_id, modification.reference) in self.terms:
                    continue  # the converted price_change_amount is null (L5-3-Q-19)
                effective = _date(modification.effective_date)
                # The runner's calendars are MONTHLY with the fiscal year from month 1.
                period_key = f"FY{effective.year}-P{effective.month:02d}"
                for checkpoint in self.key.checkpoints:
                    credit = next(
                        (
                            line
                            for block in checkpoint.subledger or ()
                            if block.period_key == period_key
                            and block.entity == contract.contracting_entity
                            and block.contract in (None, contract.external_id)
                            for line in block.lines
                            if line.account_role == "REFUND_LIABILITY" and line.cr is not None
                        ),
                        None,
                    )
                    if credit is None:
                        continue
                    found[(contract.external_id, modification.reference)] = KEY_IMPLIED_SETTLEMENT
                    self.notes.append(
                        f"D-85: {contract.external_id} {modification.reference} "
                        f"{SETTLEMENT_MEMBER} {KEY_IMPLIED_SETTLEMENT}, implied by checkpoint "
                        f"{checkpoint.name} "
                        f"subledger {period_key} {contract.contracting_entity} REFUND_LIABILITY "
                        f"cr {credit.cr} (JET-05c)"
                    )
                    break
        return found

    def _terms_conversions(self) -> dict[tuple[str, str], tuple[dict[str, object], ...]]:
        """D-87 L5-3-Q-19 = L5-5-Q-17: the delta form of every modification whose lines carry the
        post-modification terms (dev-guide §9.5.4 OQ-AKI-06). Modifications of a contract apply in
        (effective date, key order); each is measured against the lines in force at its date d:
        the booked lines with the earlier modifications' deltas. Each derivation is a run note."""
        found: dict[tuple[str, str], tuple[dict[str, object], ...]] = {}
        for contract in self.key.contracts:
            state: dict[str, tuple[Decimal, Decimal]] = {
                line.obligation_key: (_amount(line.quantity), _amount(line.total_price))
                for line in contract.lines
            }
            ordered = sorted(
                enumerate(contract.modifications or ()),
                key=lambda pair: (_date(pair[1].effective_date), pair[0]),
            )
            for _, modification in ordered:
                if any(isinstance(line, ContractLine) for line in modification.lines):
                    lines = self._convert_terms(contract, modification, state)
                    found[(contract.external_id, modification.reference)] = lines
                else:
                    lines = tuple(_line_payload(line) for line in modification.lines)
                    ended = self._ended_termination_lines(contract, modification, state, lines)
                    if ended is not None:
                        self.terminations[(contract.external_id, modification.reference)] = ended
                        lines = ended
                for line in lines:
                    key = str(line["obligation_key"])
                    quantity, price = state.get(key, (Decimal(0), Decimal(0)))
                    state[key] = (
                        quantity + cast(Decimal, line.get("quantity_delta", Decimal(0))),
                        price + cast(Decimal, line.get("consideration_delta", Decimal(0))),
                    )
        return found

    def _convert_terms(
        self,
        contract: Contract,
        modification: Modification,
        state: Mapping[str, tuple[Decimal, Decimal]],
    ) -> tuple[dict[str, object], ...]:
        """ADD: key not in force at d (ΔQ = quantity, ΔC = total price). REMOVE: kind
        REMOVE_OBLIGATION or TERMINATION, or line ``end_date`` < d (ΔQ = −(quantity in force − net
        delivered)). CHANGE otherwise (ΔQ = quantity − quantity in force). The in-force lines share
        D = ``price_change_amount`` − Σ ADD total price by largest remainder over the weights
        |terms total price − in-force total price| (equal when all are 0)."""
        pointer = f"/contracts/{self.key.contracts.index(contract)}/modifications"
        d = _date(modification.effective_date)
        mu = _minor_unit(contract.transaction_currency)
        converted: list[dict[str, object]] = []
        weights: list[tuple[int, Decimal]] = []  # (index into converted, weight) of in-force lines
        added = Decimal(0)
        for line in modification.lines:
            if not isinstance(line, ContractLine):
                raise self.error(pointer, "terms-form and delta-form lines are mixed (L5-3-Q-19)")
            quantity, price = _amount(line.quantity), _amount(line.total_price)
            members: dict[str, object] = {
                "obligation_key": line.obligation_key,
                "product_code": line.product_code,
            }
            for name in _TERMS_MEMBERS:
                value = getattr(line, name)
                if value is not None:
                    members[name] = _date(value) if name in LINE_DATE_MEMBERS else value
            if line.performing_entity_code is not None:
                members["selling_entity_code"] = line.performing_entity_code
            if line.account_overrides is not None:
                members["account_codes"] = line.account_overrides
            in_force = state.get(line.obligation_key)
            action = terms_line_action(  # shared with the loader's CHANGE-only guard (D-97 (1c))
                modification.kind, line, in_force=in_force is not None, effective_date=d
            )
            if in_force is None or action == ADD:
                members.update(action="ADD", quantity_delta=quantity, consideration_delta=price)
                added += price
            else:
                if action == REMOVE:
                    delivered = self._net_delivered(contract, line.obligation_key, d)
                    members.update(action="REMOVE", quantity_delta=-(in_force[0] - delivered))
                else:
                    members.update(action="CHANGE", quantity_delta=quantity - in_force[0])
                weights.append((len(converted), abs(price - in_force[1])))
            converted.append(members)
        amount = modification.price_change_amount
        if weights and amount is None:
            if any(weight != 0 for _, weight in weights):
                raise self.error(
                    f"{pointer}/price_change_amount",
                    "terms-form lines that change in-force prices need price_change_amount "
                    "(L5-3-Q-19)",
                )
            amount_units = 0
        else:
            amount_units = 0 if amount is None else int((_amount(amount) - added).scaleb(mu))
        shares = _largest_remainder(amount_units, [weight for _, weight in weights])
        for (index, _), share in zip(weights, shares, strict=True):
            converted[index]["consideration_delta"] = Decimal(share).scaleb(-mu)
        self.notes.append(
            f"L5-3-Q-19: {contract.external_id} {modification.reference} terms-form lines "
            f"converted to delta form at {d.isoformat()} (price_change_amount "
            f"{_render_expected(amount) if amount is not None else 'null'} -> null): "
            + "; ".join(
                f"{line['obligation_key']} {line['action']} quantity_delta "
                f"{format_exact(to_fraction(cast(Decimal, line['quantity_delta'])))} "
                f"consideration_delta "
                f"{format_money(int(cast(Decimal, line['consideration_delta']).scaleb(mu)), mu)}"
                for line in converted
            )
        )
        return tuple(converted)

    def _ended_termination_lines(
        self,
        contract: Contract,
        modification: Modification,
        state: Mapping[str, tuple[Decimal, Decimal]],
        lines: Sequence[dict[str, object]],
    ) -> tuple[dict[str, object], ...] | None:
        """D-88 L7-5-Q-13 (a): in the delta branch, a line of a ``TERMINATION`` modification with
        action CHANGE, quantity_delta 0 and ``end_date`` on or before d becomes action REMOVE with
        quantity_delta = −(quantity in force − net delivered on or before d). consideration_delta
        and the dates stay as keyed; S06-R-21 carries REMOVE lines. None when no line converts.
        Each conversion is a run note."""
        if modification.kind != TERMINATION_KIND:
            return None
        d = _date(modification.effective_date)
        converted: list[dict[str, object]] = []
        changed = False
        for line in lines:
            end = line.get("end_date")
            quantity_delta = cast(Decimal, line.get("quantity_delta", Decimal(0)))
            if line["action"] != "CHANGE" or quantity_delta != 0 or not isinstance(end, date):
                converted.append(line)
                continue
            if end > d:
                converted.append(line)
                continue
            key = str(line["obligation_key"])
            in_force = state.get(key, (Decimal(0), Decimal(0)))[0]
            delivered = self._net_delivered(contract, key, d)
            removed = -(in_force - delivered)
            converted.append({**line, "action": "REMOVE", "quantity_delta": removed})
            changed = True
            self.notes.append(
                f"L7-5-Q-13: {contract.external_id} {modification.reference} delta-form "
                f"{TERMINATION_KIND} line {key} CHANGE quantity_delta 0 with end_date "
                f"{end.isoformat()} on or before {d.isoformat()} read as REMOVE quantity_delta "
                f"{format_exact(to_fraction(removed))} (quantity in force "
                f"{format_exact(to_fraction(in_force))} less net delivered "
                f"{format_exact(to_fraction(delivered))}); consideration_delta and dates as keyed"
            )
        return tuple(converted) if changed else None

    def _net_delivered(self, contract: Contract, obligation_key: str, d: date) -> Decimal:
        """Units delivered less units returned on the obligation, effective on or before d."""
        total = Decimal(0)
        for item in self.timeline:
            if (
                not isinstance(item, EventItem)
                or item.contract != contract.external_id
                or item.payload.get("obligation_key") != obligation_key
                or _date(item.effective_date) > d
            ):
                continue
            quantity = item.payload.get("quantity")
            if isinstance(quantity, str) and item.event_type == "DELIVERY_RECORDED":
                total += Decimal(quantity)
            elif isinstance(quantity, str) and item.event_type == "RETURN_RECORDED":
                total -= Decimal(quantity)
        return total

    def _modification_lines(
        self, contract: Contract, modification: Modification
    ) -> list[dict[str, object]]:
        """T-CON-06 lines of the modification: the delta form, converted from terms (L5-3-Q-19), or
        with the ended CHANGE lines of a TERMINATION read as REMOVE (L7-5-Q-13)."""
        reference = (contract.external_id, modification.reference)
        converted = self.terms.get(reference, self.terminations.get(reference))
        if converted is not None:
            return [dict(line) for line in converted]
        return [_line_payload(line) for line in modification.lines]

    def _implied_distinct_answers(self) -> dict[tuple[str, str], dict[str, bool]]:
        """D-88 L7-5-Q-2 (ii) (D-85 pattern): when a key modification has no answer
        ``remaining_goods_distinct_from_transferred`` for an existing obligation that a checkpoint
        ``modifications[].proposed_treatments`` of that reference lists, the runner supplies it:
        true for ``PROSPECTIVE``, false for ``CUMULATIVE_CATCH_UP``. The existing obligations are
        the booked lines and the lines of the modifications before it in (effective date, key
        order). Two checkpoints that imply different answers fail closed. Each derivation is a run
        note."""
        found: dict[tuple[str, str], dict[str, bool]] = {}
        for contract in self.key.contracts:
            existing = {line.obligation_key for line in contract.lines}
            ordered = sorted(
                enumerate(contract.modifications or ()),
                key=lambda pair: (_date(pair[1].effective_date), pair[0]),
            )
            for _, modification in ordered:
                answered = modification.questionnaire or {}
                supplied: dict[str, bool] = {}
                for index, checkpoint in enumerate(self.key.checkpoints):
                    rows = (
                        row
                        for block in checkpoint.contracts or ()
                        if block.contract == contract.external_id
                        for row in block.modifications or ()
                        if row.reference == modification.reference
                    )
                    for row in rows:
                        for obligation_key, treatment in sorted(row.proposed_treatments.items()):
                            value = PROPOSED_DISTINCT.get(treatment)
                            if value is None or obligation_key not in existing:
                                continue
                            if REMAINING_DISTINCT_MEMBER in answered.get(obligation_key, {}):
                                continue
                            earlier = supplied.get(obligation_key)
                            if earlier is not None and earlier != value:
                                raise self.error(
                                    f"/checkpoints/{index}/contracts",
                                    f"proposed_treatments of {modification.reference} imply "
                                    f"different {REMAINING_DISTINCT_MEMBER} answers for "
                                    f"{obligation_key} (L7-5-Q-2 (ii))",
                                )
                            if earlier is not None:
                                continue
                            supplied[obligation_key] = value
                            self.notes.append(
                                f"L7-5-Q-2 (ii): {contract.external_id} {modification.reference} "
                                f"{obligation_key} questionnaire {REMAINING_DISTINCT_MEMBER} "
                                f"{'true' if value else 'false'} supplied; checkpoint "
                                f"{checkpoint.name} proposed_treatments {treatment} and the key "
                                "modification gives no answer"
                            )
                if supplied:
                    found[(contract.external_id, modification.reference)] = supplied
                existing.update(line.obligation_key for line in modification.lines)
        return found

    def _questionnaire(
        self, contract: Contract, modification: Modification
    ) -> dict[str, dict[str, object]]:
        """T-CON-06 ``questionnaire`` sections: the key's answers with the supplied
        ``remaining_goods_distinct_from_transferred`` members (L7-5-Q-2 (ii))."""
        sections: dict[str, dict[str, object]] = {
            obligation: dict(answers)
            for obligation, answers in (modification.questionnaire or {}).items()
        }
        supplied = self.distinct_answers.get((contract.external_id, modification.reference), {})
        for obligation, value in supplied.items():
            sections.setdefault(obligation, {})[REMAINING_DISTINCT_MEMBER] = value
        return dict(sorted(sections.items()))

    def _settlement_member(self, contract: Contract, modification: Modification) -> dict[str, str]:
        """The contract-level ``price_change_settlement`` member the key implies, if any (D-85)."""
        implied = self.settlements.get((contract.external_id, modification.reference))
        return {} if implied is None else {SETTLEMENT_MEMBER: implied}

    def _implied_activations(self) -> dict[str, int]:
        """D-87 L6-5-Q-12 (i): a key contract with ``CONTRACT_BOOKED`` and a
        ``COLLECTIBILITY_ASSESSED`` but no ``CONTRACT_ACTIVATED`` gets ``CONTRACT_ACTIVATED`` with a
        passing checklist right after its first assessment, at the same effective date and record
        time. Table 2.2-A and S02-R-02 stay unchanged for platform commands. Each derivation is
        recorded as a run note."""
        found: dict[str, int] = {}
        for contract in self.key.contracts:
            items = [
                item
                for item in self.timeline
                if isinstance(item, EventItem) and item.contract == contract.external_id
            ]
            types = {item.event_type for item in items}
            if "CONTRACT_BOOKED" not in types or "CONTRACT_ACTIVATED" in types:
                continue
            first = next((i for i in items if i.event_type == "COLLECTIBILITY_ASSESSED"), None)
            if first is None:
                continue
            found[contract.external_id] = first.seq
            self.notes.append(
                f"L6-5-Q-12: {contract.external_id} CONTRACT_ACTIVATED with a passing checklist "
                f"supplied after COLLECTIBILITY_ASSESSED seq {first.seq} (effective "
                f"{first.effective_date}); the key books and assesses collectibility but never "
                "activates"
            )
        return found

    def _catch_up_aliases(self) -> None:
        """D-87 L6-5-Q-27: the run note of every obligation row that asserts
        ``catch_up_estimate_cum`` without ``catch_up_tp_change_cum``; the comparison reads the sum
        of both engine columns for it (``_CheckpointComparison.contract``)."""
        for checkpoint in self.key.checkpoints:
            for block in checkpoint.contracts or ():
                for row in block.obligations or ():
                    if CATCH_UP_ESTIMATE not in row or CATCH_UP_TP_CHANGE in row:
                        continue
                    self.notes.append(
                        f"L6-5-Q-27: checkpoint {checkpoint.name} obligation "
                        f"{block.contract}/{row['obligation_key']} {CATCH_UP_ESTIMATE} compares "
                        f"with {CATCH_UP_TP_CHANGE} + {CATCH_UP_ESTIMATE}"
                    )

    def _implied_immaterial_returns(self) -> dict[str, tuple[str, ...]]:
        """D-87 L5-3-Q-9 (D-85 pattern): a key line whose ``returns.model`` resolves
        ``EXPECTED_RETURNS``, with no ``RETURN_RATE`` element targeting its obligation, no
        ``RETURN_RECORDED`` naming it and no ``OTHER`` judgement carrying ``returns_immaterial`` for
        it, gets a REVIEWED judgement ``{topic: OTHER, questionnaire: {obligation_key,
        returns_immaterial: true}}`` (``_immaterial_judgements``). Each derivation is recorded as a
        run note."""
        found: dict[str, tuple[str, ...]] = {}
        for contract in self.key.contracts:
            estimates = [
                *(contract.estimates or ()),
                *(
                    estimate
                    for portfolio in self.key.world.portfolios
                    if contract.external_id in portfolio.members
                    for estimate in portfolio.estimates or ()
                ),
            ]
            lines: dict[str, str] = {}  # obligation key -> product code, booked lines first
            for line in contract.lines:
                lines.setdefault(line.obligation_key, line.product_code)
            for modification in contract.modifications or ():
                for member in modification.lines:
                    if member.product_code is not None:
                        lines.setdefault(member.obligation_key, member.product_code)
            supplied: list[str] = []
            for obligation_key, product_code in lines.items():
                level = self._returns_model_level(contract, obligation_key, product_code)
                if level is None:
                    continue
                targeted = any(
                    estimate.estimate_kind == RETURN_RATE_KIND
                    and (
                        estimate.obligation_key == obligation_key
                        or obligation_key in (estimate.target_obligation_keys or ())
                    )
                    for estimate in estimates
                )
                returned = any(
                    isinstance(item, EventItem)
                    and item.contract == contract.external_id
                    and item.event_type == "RETURN_RECORDED"
                    and (
                        item.payload.get("obligation_key") == obligation_key
                        or obligation_key
                        in cast(Sequence[str], item.payload.get("obligation_keys", ()))
                    )
                    for item in self.timeline
                )
                judged = any(
                    judgement.topic == "OTHER"
                    and (judgement.questionnaire or {}).get("obligation_key") == obligation_key
                    and "returns_immaterial" in (judgement.questionnaire or {})
                    for judgement in contract.judgements or ()
                )
                if targeted or returned or judged:
                    continue
                supplied.append(obligation_key)
                self.notes.append(
                    f"L5-3-Q-9: {contract.external_id} {obligation_key} REVIEWED judgement OTHER "
                    f"returns_immaterial true supplied; {RETURNS_MODEL} {EXPECTED_RETURNS_MODEL} "
                    f"at level {level}, no {RETURN_RATE_KIND} element targets the obligation, no "
                    "RETURN_RECORDED names it and no such judgement exists"
                )
            if supplied:
                found[contract.external_id] = tuple(sorted(supplied))
        return found

    def _returns_model_level(
        self, contract: Contract, obligation_key: str, product_code: str
    ) -> str | None:
        """The level at which ``returns.model`` resolves ``EXPECTED_RETURNS`` for a key line, else
        None. Precedence as the bundle builds it: obligation and contract overrides, the product and
        template ``policy_values`` merged as ``_product_levels`` does, then the world's book,
        contracting-entity and tenant values."""
        overrides = contract.policy_overrides or ()
        candidates: list[tuple[str, PolicyValue | None]] = [
            (
                "O",
                next(
                    (
                        o.value
                        for o in overrides
                        if o.policy_key == RETURNS_MODEL and o.obligation_key == obligation_key
                    ),
                    None,
                ),
            ),
            (
                "C",
                next(
                    (
                        o.value
                        for o in overrides
                        if o.policy_key == RETURNS_MODEL and o.obligation_key is None
                    ),
                    None,
                ),
            ),
        ]
        product = self.products.get(product_code)
        if product is not None:
            template = next(
                (t for t in self.key.world.pob_templates if t.code == product.pob_template), None
            )
            merged = {
                **_pinned_values(product.policy_values),
                **_pinned_values(None if template is None else template.policy_values),
            }
            candidates.append(("P", merged.get(RETURNS_MODEL)))
        world = self.key.world.policies
        for book_code in self.books:
            candidates.append(("B", world.books.get(book_code, {}).get(RETURNS_MODEL)))
        entity_values = world.entities.get(contract.contracting_entity, {})
        candidates.append(("E", entity_values.get(RETURNS_MODEL)))
        candidates.append(("T", world.tenant.get(RETURNS_MODEL)))
        for level, value in candidates:
            if value is not None:
                return level if policy_value(value) == EXPECTED_RETURNS_MODEL else None
        return None

    def _immaterial_judgements(self, contract: Contract) -> tuple[JudgementInput, ...]:
        """The REVIEWED ``OTHER`` judgements the runner supplies for the contract (L5-3-Q-9)."""
        return tuple(
            JudgementInput(
                judgement_key=self._judgement_key(
                    contract, f"{IMMATERIAL_RETURNS_HANDLE}-{obligation_key}"
                ),
                topic="OTHER",
                subject_key=obligation_subject_key(contract.external_id, obligation_key),
                book_code=None,
                outcome={"obligation_key": obligation_key, "returns_immaterial": "true"},
            )
            for obligation_key in self.immaterial.get(contract.external_id, ())
        )

    def _implied_agent_records(self) -> dict[str, tuple[JudgementInput, ...]]:
        """D-87 L4-3-Q-24 (a): a booked line whose key product is ``AGENT`` and that no
        ``PRINCIPAL_AGENT`` record names (by ``obligation_key`` or ``product_code``) gets a REVIEWED
        record {conclusion AGENT, gross_to_net_basis FIXED_FEE, amount the line total price}. Each
        derivation is recorded as a run note (DG-AK-43)."""
        found: dict[str, tuple[JudgementInput, ...]] = {}
        for contract in self.key.contracts:
            named = {
                (judgement.questionnaire or {}).get(member)
                for judgement in contract.judgements or ()
                if judgement.topic == "PRINCIPAL_AGENT"
                for member in ("obligation_key", "product_code")
            }
            records: list[JudgementInput] = []
            for line in contract.lines:
                product = self.products.get(line.product_code)
                if product is None or product.principal_agent != "AGENT":
                    continue
                if line.obligation_key in named or line.product_code in named:
                    continue
                amount = str(_amount(line.total_price))
                handle = f"{AGENT_RECORD_HANDLE}-{line.obligation_key}"
                records.append(
                    JudgementInput(
                        judgement_key=self._judgement_key(contract, handle),
                        topic="PRINCIPAL_AGENT",
                        subject_key=obligation_subject_key(
                            contract.external_id, line.obligation_key
                        ),
                        book_code=None,
                        outcome={
                            "amount": amount,
                            "conclusion": "AGENT",
                            "gross_to_net_basis": KEY_AGENT_BASIS,
                            "obligation_key": line.obligation_key,
                        },
                    )
                )
                self.notes.append(
                    f"D-87 L4-3-Q-24 (a): {contract.external_id} {line.obligation_key} product "
                    f"{line.product_code} is AGENT without a PRINCIPAL_AGENT record; REVIEWED "
                    f"outcome conclusion AGENT, gross_to_net_basis {KEY_AGENT_BASIS}, amount "
                    f"{amount} (the line total price)"
                )
            if records:
                found[contract.external_id] = tuple(records)
        return found

    def _implied_nondistinct_lines(self) -> dict[str, tuple[JudgementInput, ...]]:
        """D-88 L7-5-Q-11 (D-85 pattern): a key line whose template ``obligation_kind`` is
        ``STANDARD``, that names ``bundle_parent_obligation_key``, and whose obligation key no
        checkpoint row (obligations, schedule, subledger ``obligation_key``, modifications) and no
        timeline payload names, gets a REVIEWED ``POB_DISTINCT_OVERRIDE`` {obligation_key,
        distinctness nondistinct, integrates_into_obligation_key the bundle parent}. A line the key
        already overrides gets none. Each derivation is recorded as a run note."""
        templates = {template.code: template for template in self.key.world.pob_templates}
        found: dict[str, tuple[JudgementInput, ...]] = {}
        for contract in self.key.contracts:
            overridden = {
                (judgement.questionnaire or {}).get("obligation_key")
                for judgement in contract.judgements or ()
                if judgement.topic == NONDISTINCT_TOPIC
            }
            records: list[JudgementInput] = []
            for line in contract.lines:
                parent = line.bundle_parent_obligation_key
                product = self.products.get(line.product_code)
                template = None if product is None else templates.get(product.pob_template)
                if (
                    parent is None
                    or template is None
                    or template.obligation_kind != STANDARD_KIND
                    or line.obligation_key in overridden
                    or self._named(line.obligation_key)
                ):
                    continue
                handle = f"{NONDISTINCT_HANDLE}-{line.obligation_key}"
                records.append(
                    JudgementInput(
                        judgement_key=self._judgement_key(contract, handle),
                        topic=NONDISTINCT_TOPIC,
                        subject_key=obligation_subject_key(
                            contract.external_id, line.obligation_key
                        ),
                        book_code=None,
                        outcome={
                            "distinctness": "nondistinct",
                            "integrates_into_obligation_key": parent,
                            "obligation_key": line.obligation_key,
                        },
                    )
                )
                self.notes.append(
                    f"L7-5-Q-11: {contract.external_id} {line.obligation_key} REVIEWED judgement "
                    f"{NONDISTINCT_TOPIC} distinctness nondistinct integrates_into_obligation_key "
                    f"{parent} supplied; template {template.code} is {STANDARD_KIND}, the line "
                    f"names bundle_parent_obligation_key {parent} and no checkpoint row or "
                    f"timeline payload names {line.obligation_key}"
                )
            if records:
                found[contract.external_id] = tuple(records)
        return found

    def _named(self, obligation_key: str) -> bool:
        """A checkpoint row (obligations, schedule, subledger ``obligation_key``, modifications) or
        a timeline payload names the obligation key (L7-5-Q-11)."""
        for checkpoint in self.key.checkpoints:
            for block in checkpoint.contracts or ():
                if any(
                    row.get("obligation_key") == obligation_key for row in block.obligations or ()
                ):
                    return True
                if any(row.obligation_key == obligation_key for row in block.schedule or ()):
                    return True
                if any(
                    obligation_key in row.proposed_treatments for row in block.modifications or ()
                ):
                    return True
            for subledger in checkpoint.subledger or ():
                if any(line.obligation_key == obligation_key for line in subledger.lines):
                    return True
        return any(
            isinstance(item, EventItem) and _names_key(item.payload, obligation_key)
            for item in self.timeline
        )

    # Timeline

    def _recorded_times(self) -> dict[int, datetime]:
        """§9.5.5 record times: explicit values, else local noon of the effective date in the
        contracting entity's time zone, at least one second after the previous item."""
        zones = {entity.code: ZoneInfo(entity.time_zone) for entity in self.key.world.entities}
        times: dict[int, datetime] = {}
        previous: datetime | None = None
        for item in self.timeline:
            pointer = f"/timeline/{self.positions[item.seq]}"
            if item.recorded_at is not None:
                at = datetime.strptime(item.recorded_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            elif isinstance(item, EventItem):
                zone = zones[self.contracts[item.contract].contracting_entity]
                noon = datetime.combine(_date(item.effective_date), time(12), tzinfo=zone)
                at = noon.astimezone(UTC)
                if previous is not None:
                    at = max(at, previous + timedelta(seconds=1))
            elif previous is None:
                raise self.error(pointer, "the first item needs an effective date or recorded_at")
            else:
                at = previous + timedelta(seconds=1)
            if previous is not None and at <= previous:
                raise self.error(f"{pointer}/recorded_at", "recorded_at is not strictly increasing")
            times[item.seq] = at
            previous = at
        return times

    def checkpoints(self) -> tuple[CheckpointBundles, ...]:
        built: list[CheckpointBundles] = []
        for index, checkpoint in enumerate(self.key.checkpoints):
            if checkpoint.after_seq not in self.times:
                raise self.error(f"/checkpoints/{index}/after_seq", "after_seq names no item")
            known_at = self.times[checkpoint.after_seq]
            items = [
                item
                for item in self.timeline
                if item.seq <= checkpoint.after_seq and item.expect_problem is None
            ]
            bundles = self._bundles(items, known_at)
            built.append(
                CheckpointBundles(
                    checkpoint.name,
                    checkpoint.after_seq,
                    _date(checkpoint.as_of),
                    checkpoint.book,
                    known_at,
                    bundles,
                )
            )
        return tuple(built)

    def steps(self) -> tuple[StepBundle, ...]:
        """The step bundle of every ``expect_problem`` item (§9.5.5; D-79)."""
        built: list[StepBundle] = []
        for item in self.timeline:
            if item.expect_problem is None:
                continue
            pointer = f"/timeline/{self.positions[item.seq]}/expect_problem"
            if not isinstance(item, EventItem):
                raise self.error(pointer, "the engine runner checks expect_problem on events only")
            items = [
                other
                for other in self.timeline
                if other.seq < item.seq and other.expect_problem is None
            ]
            known_at = self.times[item.seq]
            contract = self.contracts[item.contract]
            group = contract.combination_group or f"CG-{contract.external_id}"
            bundles = self._bundles([*items, item], known_at, only_group=group)
            if not bundles:
                raise self.error(pointer, f"contract {item.contract} is not booked at this step")
            built.append(StepBundle(item.seq, item.expect_problem.code, known_at, bundles[0]))
        return tuple(built)

    def _bundles(
        self,
        items: Sequence[object],
        known_at: datetime,
        *,
        only_group: str | None = None,
        pending: frozenset[str] = frozenset(),
    ) -> tuple[InputBundle, ...]:
        """``pending`` names modifications the bundle carries without an event (S06-R-01)."""
        booked = {
            item.contract
            for item in items
            if isinstance(item, EventItem) and item.event_type == "CONTRACT_BOOKED"
        }
        states = self._period_states(items)
        entities = tuple(self._entity(entity, states) for entity in self._sorted_entities())
        groups: dict[str, list[Contract]] = {}
        for contract in self.key.contracts:
            if contract.external_id in booked:
                code = contract.combination_group or f"CG-{contract.external_id}"
                if only_group is None or code == only_group:
                    groups.setdefault(code, []).append(contract)
        bundles: list[InputBundle] = []
        for code in sorted(groups):
            members = sorted(groups[code], key=lambda contract: contract.external_id)
            bundles.append(self._bundle(code, members, items, booked, entities, known_at, pending))
        return tuple(bundles)

    def _bundle(
        self,
        group_code: str,
        members: Sequence[Contract],
        items: Sequence[object],
        booked: set[str],
        entities: tuple[EntityInput, ...],
        known_at: datetime,
        pending: frozenset[str] = frozenset(),
    ) -> InputBundle:
        member_keys = {contract.external_id for contract in members}
        events, estimate_versions, modification_keys = self._events(items, member_keys)
        modification_keys |= pending
        contracts = tuple(self._contract(contract, modification_keys) for contract in members)
        products = self._group_products(members, events)
        first = next(c for c in self.key.contracts if c.external_id in member_keys)
        portfolios = tuple(
            PortfolioInput(
                portfolio.code, tuple(sorted(m for m in portfolio.members if m in booked))
            )
            for portfolio in sorted(self.key.world.portfolios, key=lambda p: p.code)
            if member_keys & set(portfolio.members)
        )
        inception = min(_date(contract.inception_date) for contract in members)
        group = GroupInput(
            group_key=group_code,
            transaction_currency=members[0].transaction_currency,
            inception_date=inception,
            member_contract_keys=tuple(sorted(member_keys)),
            criterion=first.combination_criterion if first.combination_group else None,
            previous_stream_heads=self._previous_heads(items, member_keys),
            products=tuple(self._product(code, inception) for code in sorted(products)),
            portfolios=portfolios,
        )
        books = tuple(
            BookInput(
                book_code,
                book_code == self.books[0],
                tuple(sorted(e.code for e in self.key.world.entities if book_code in e.books)),
                self._policies(book_code, entities, members, events),
                self.account_mapping,
            )
            for book_code in self.books
        )
        return InputBundle(
            format_version=1,
            engine_version=ENGINE_VERSION,
            trigger=TRIGGER,
            known_at=known_at,
            tenant_preset=self.key.world.tenant.preset,
            currencies=self._currencies(members),
            books=books,
            entities=entities,
            group=group,
            contracts=contracts,
            events=events,
            ssp_versions=self.ssp_versions,
            pob_template_versions=self.templates,
            rule_set_versions=self.rule_sets,
            estimate_versions=estimate_versions,
            fx_rates=self.fx_rates,
            posted=(),
        )

    def _previous_heads(
        self, items: Sequence[object], member_keys: set[str]
    ) -> tuple[tuple[str, int], ...]:
        """``GroupInput.previous_stream_heads`` (ENGINE_SPEC §0.4; S08-R-10 ``is_new``; L5-5-Q-1).

        A period changes state only after the events recorded before it were computed, so the
        previous computation of a bundle includes the events before its latest ``period_state``
        item. Without such an item every event is new, as before.
        """
        last = max((item.seq for item in items if isinstance(item, PeriodStateItem)), default=None)
        if last is None:
            return ()
        heads: dict[str, int] = {}
        for item in items:
            if isinstance(item, EventItem) and item.seq < last:
                added = 1
                if item.event_type == "CONTRACT_BOOKED":
                    added += len(self._parity_vc_elements(self.contracts[item.contract]))
                if self.activations.get(item.contract) == item.seq:
                    added += 1  # the supplied CONTRACT_ACTIVATED (L6-5-Q-12)
                heads[item.contract] = heads.get(item.contract, 0) + added
        return tuple(sorted((key, head) for key, head in heads.items() if key in member_keys))

    # World

    def _books(self) -> tuple[str, ...]:
        unknown = sorted(set(self.key.books) - set(BOOK_ORDER))
        if unknown:
            raise self.error("/books", f"unknown books {', '.join(unknown)}")
        return tuple(book for book in BOOK_ORDER if book in self.key.books)

    def _currencies(self, members: Sequence[Contract]) -> CurrencyTable:
        world = self.key.world
        codes = {*world.currencies, *(e.functional_currency for e in world.entities)}
        codes.update(contract.transaction_currency for contract in members)
        unknown = sorted(code for code in codes if code not in ISO_4217)
        if unknown:
            raise self.error("/world/currencies", f"unknown ISO 4217 codes {', '.join(unknown)}")
        return {code: ISO_4217[code] for code in sorted(codes)}

    def _zones(self) -> tuple[ZoneInfo, ...]:
        return tuple(sorted({ZoneInfo(e.time_zone) for e in self.key.world.entities}, key=str))

    def _earliest_local_midnight(self) -> datetime:
        """The first instant at which the world's first period has started ANYWHERE: local midnight
        of ``world_start`` in the easternmost entity zone (UTC when the world has no entity)."""
        midnights = [
            datetime.combine(self.world_start, time(0), tzinfo=zone).astimezone(UTC)
            for zone in self._zones()
        ]
        return (
            min(midnights) if midnights else datetime.combine(self.world_start, time(0), tzinfo=UTC)
        )

    def _period_start_instant(self) -> datetime:
        """The instant whose date is ``world_start`` in EVERY entity zone: local midnight in the
        westernmost zone (the latest); a policy effective here starts the first period for every
        entity (``period_start_errors`` evaluates the date per entity zone)."""
        midnights = [
            datetime.combine(self.world_start, time(0), tzinfo=zone).astimezone(UTC)
            for zone in self._zones()
        ]
        instant = (
            max(midnights) if midnights else datetime.combine(self.world_start, time(0), tzinfo=UTC)
        )
        for zone in self._zones():
            if instant.astimezone(zone).date() != self.world_start:
                raise self.error(
                    "/world/entities",
                    f"entity time zones spread the first period start over two dates ({zone.key})",
                )
        return instant

    def _world_start(self) -> date:
        """The first day of the first calendar month: ``world.periods.from``, or the month of the
        earliest contract inception when that is earlier. A contract signed before the world's
        first period needs a period holding its inception and a template version in force at it
        (S03-R-02 ``PRODUCT_UNMAPPED``; CV-12; L6-3-Q-16)."""
        first = _month_start(self.key.world.periods.from_)
        for contract in self.key.contracts:
            inception = date.fromisoformat(str(contract.inception_date)).replace(day=1)
            first = min(first, inception)
        return first

    def _calendar_end(self) -> date:
        """The first day of the last calendar month: ``world.periods.to``, or the month of the
        latest date a contract line, a modification line or a timeline item carries when that is
        later. RCP-15 supplies the calendar through the horizon plus the future, and CV-12 needs a
        period for every date the engine places (a line end beyond the world, SSP-FS-05). An
        estimate version with ``amortization_months`` extends it to the last amortisation month
        from its effective date (a cost asset amortised beyond the world, CV-12; L5-3-Q-21)."""
        latest = self.world_end
        for contract in self.key.contracts:
            lines: list[ContractLine | DeltaLine] = list(contract.lines)
            for modification in contract.modifications or ():
                lines.extend(modification.lines)
            for line in lines:
                for name in LINE_DATE_MEMBERS:
                    value = getattr(line, name, None)
                    if isinstance(value, str):
                        latest = max(latest, _date(value).replace(day=1))
            for estimate in contract.estimates or ():
                for version in estimate.versions:
                    if version.amortization_months is None:
                        continue
                    start = _date(version.effective_date)
                    years, month = divmod(
                        start.month - 1 + int(version.amortization_months) - 1, 12
                    )
                    latest = max(latest, date(start.year + years, month + 1, 1))
        for item in self.key.timeline:
            value = getattr(item, "effective_date", None)
            if isinstance(value, str):
                latest = max(latest, _date(value).replace(day=1))
        return latest

    def _sorted_entities(self) -> list[tuple[int, Entity]]:
        return sorted(enumerate(self.key.world.entities), key=lambda pair: pair[1].code)

    def _period_states(self, items: Sequence[object]) -> dict[tuple[str, str, str], str]:
        """(entity, book, period_key) → E-04 state at the checkpoint (DG-AK-44)."""
        states = {
            (row.entity, row.book, row.period_key): row.state
            for row in self.key.world.period_states
        }
        for item in items:
            if isinstance(item, PeriodStateItem):
                states[(item.entity, item.book, item.period_key)] = item.state
        return states

    def _entity(
        self, pair: tuple[int, Entity], states: Mapping[tuple[str, str, str], str]
    ) -> EntityInput:
        index, entity = pair
        calendar = entity.calendar
        if calendar.pattern != "MONTHLY" or calendar.fiscal_year_start_month != 1:
            raise self.error(
                f"/world/entities/{index}/calendar",
                "the engine runner generates MONTHLY calendars whose fiscal year starts in month 1",
            )
        periods: list[PeriodInput] = []
        first = self.world_start
        while first <= self.calendar_end:
            period_key = f"FY{first.year}-P{first.month:02d}"
            default = DEFAULT_PERIOD_STATE if first <= self.world_end else FUTURE_PERIOD_STATE
            periods.append(
                PeriodInput(
                    period_key=period_key,
                    fiscal_year=first.year,
                    period_no=first.month,
                    start_date=first,
                    end_date=month_end(first),
                    states=tuple(
                        (book, states.get((entity.code, book, period_key), default))
                        for book in sorted(entity.books)
                    ),
                )
            )
            first = month_end(first) + timedelta(days=1)
        return EntityInput(
            entity.code,
            entity.functional_currency,
            entity.time_zone,
            calendar.pattern,
            tuple(periods),
        )

    def _policies(
        self,
        book_code: str,
        entities: Sequence[EntityInput],
        members: Sequence[Contract],
        events: Sequence[EventInput],
    ) -> tuple[ResolvedPolicyInput, ...]:
        """The preset defaults overlaid by tenant (T), entity (E), book (B), product (P), contract
        (C) and obligation (O) values; pin ``P`` codes take the PERIOD scope of every period
        (CV-17)."""
        index: dict[tuple[str, str, str], ResolvedPolicyInput] = {}
        for calendar in entities:
            for policy in policy_set(
                self.key.world.tenant.preset, book_code=book_code, entity=calendar
            ):
                index[(policy.code, policy.scope, policy.subject_key)] = policy

        overridden: dict[tuple[str, str], object] = {}

        def put(
            code: str,
            value: PolicyValue,
            level: str,
            source: str,
            scope: str,
            subject: str,
            entity: str | None = None,
        ) -> None:
            """Set a pin K value at ``scope``; a pin P value replaces the PERIOD values of every
            period of ``entity`` (every entity when None). A code FORCED in the book keeps its
            framework value (POLICIES §1; L5-5-Q-25, L5-3-Q-26)."""
            if _forced(code, book_code):
                return
            rendered = policy_value(value)
            if POLICY_PARAMETERS[code].pin != "P":
                index[(code, scope, subject)] = ResolvedPolicyInput(
                    code, scope, subject, rendered, level, source, "K"
                )
                return
            if (
                level in ("C", "O")
                and overridden.setdefault((code, entity or ""), rendered) != rendered
            ):
                raise self.error(
                    f"/contracts/{source}",
                    f"{code} is pinned per period (pin P); group members override it differently",
                )
            for calendar in entities:
                if entity is not None and calendar.code != entity:
                    continue
                for period in calendar.periods:
                    subject_key = f"{calendar.code}@{period.period_key}"
                    index[(code, "PERIOD", subject_key)] = ResolvedPolicyInput(
                        code, "PERIOD", subject_key, rendered, level, source, "P"
                    )

        world = self.key.world.policies
        book_values = world.books.get(book_code, {})
        for code, value in sorted(world.tenant.items()):
            put(code, value, "T", "world.policies.tenant", "GROUP", "")
        # POL-007 is the entity's books (§9.5.3 entities[].books; S13-INV-05; L5-5-Q-26); an
        # explicit world.policies.entities value below still replaces it.
        declared = {entity.code: entity for entity in self.key.world.entities}
        for calendar in entities:
            found = declared.get(calendar.code)
            books = [] if found is None else [code for code in BOOK_ORDER if code in found.books]
            if books:
                primary = "ASC606" if "ASC606" in books else books[0]
                source = f"world.entities.{calendar.code}.books"
                value = {"set": books, "primary": primary}
                put("books.enabled", value, "E", source, "ENTITY", calendar.code, calendar.code)
        for entity_code, values in sorted(world.entities.items()):
            for code, value in sorted(values.items()):
                if code not in book_values:
                    source = f"world.policies.entities.{entity_code}"
                    put(code, value, "E", source, "ENTITY", entity_code, entity_code)
        for code, value in sorted(book_values.items()):
            put(code, value, "B", f"world.policies.books.{book_code}", "GROUP", "")
        self._product_levels(index, members, events, book_code)
        for contract in members:
            position = self.key.contracts.index(contract)
            entity_code = contract.contracting_entity
            for number, override in enumerate(contract.policy_overrides or ()):
                source = f"{position}/policy_overrides/{number}"
                code, value = override.policy_key, override.value
                if override.obligation_key is None:
                    subject = contract.external_id
                    put(code, value, "C", source, "CONTRACT", subject, entity_code)
                else:
                    subject = obligation_subject_key(contract.external_id, override.obligation_key)
                    put(code, value, "O", source, "OBLIGATION", subject, entity_code)
        return tuple(index[item] for item in sorted(index))

    def _product_levels(
        self,
        index: dict[tuple[str, str, str], ResolvedPolicyInput],
        members: Sequence[Contract],
        events: Sequence[EventInput],
        book_code: str,
    ) -> None:
        """Level P as the platform assembles it (``erev_api.domain.contracts.bundles``): for every
        line of a CONTRACT_BOOKED or CONTRACT_AMENDED event, the pin K ``policy_values`` of the
        product, then of its template, and the template's ``ratable_convention`` as POL-090 when
        neither sets it, at the OBLIGATION scope (L4-3-Q-2). A code the contract overrides at level
        C stays with that override (POLICIES §0.5 rule 2)."""
        overridden = {
            (contract.external_id, override.policy_key)
            for contract in members
            for override in contract.policy_overrides or ()
            if override.obligation_key is None
        }
        templates = {template.code: template for template in self.key.world.pob_templates}
        for event in events:
            if event.event_type not in TERM_EVENTS:
                continue
            for line in cast(Sequence[Mapping[str, object]], event.payload.get("lines", ())):
                product = self.products.get(str(line.get("product_code")))
                if product is None:
                    continue
                template = templates.get(product.pob_template)
                merged = {
                    **_pinned_values(product.policy_values),
                    **_pinned_values(None if template is None else template.policy_values),
                }
                if template is not None and template.ratable_convention is not None:
                    merged.setdefault(CONVENTION_POLICY, template.ratable_convention)
                subject = obligation_subject_key(event.contract_key, str(line["obligation_key"]))
                source = product.code if template is None else f"{template.code}@v1"
                for code, value in sorted(merged.items()):
                    if (event.contract_key, code) in overridden or _forced(code, book_code):
                        continue
                    index[(code, "OBLIGATION", subject)] = ResolvedPolicyInput(
                        code, "OBLIGATION", subject, policy_value(value), "P", source, "K"
                    )

    def _account_mapping(self) -> AccountMappingInput:
        rules = [
            MappingRuleInput(
                account_role=row.account_role,
                clearing_purpose=row.clearing_purpose,
                entity_code=row.entity,
                book_code=row.book_code,
                product_code=row.product,
                revenue_category=row.revenue_category,
                account_code=row.account,
                default_dimensions={},
                priority=row.priority or 0,
                specificity=sum(
                    value is not None
                    for value in (row.entity, row.book_code, row.product, row.revenue_category)
                ),
            )
            for row in self.key.world.account_mapping
        ]
        rules.sort(
            key=lambda r: (
                r.account_role, r.clearing_purpose or "", -r.specificity, -r.priority,
                r.account_code, r.entity_code or "", r.book_code or "", r.product_code or "",
                r.revenue_category or "",
            )
        )  # fmt: skip
        return AccountMappingInput(MAPPING_VERSION_KEY, sha256_hex(tuple(rules)), tuple(rules))

    def _templates(self) -> tuple[TemplateInput, ...]:
        """One PUBLISHED version of each template, T-REF-23 defaults for absent members."""
        templates: list[TemplateInput] = []
        for index, template in enumerate(self.key.world.pob_templates):
            templates.append(
                TemplateInput(
                    template_code=template.code,
                    version_key=f"{template.code}@v1",
                    version_no=1,
                    content_sha256=_content_sha256(template),
                    obligation_kind=template.obligation_kind,
                    distinctness=template.distinctness,
                    series_increment_unit=template.series_increment_unit,
                    satisfaction_pattern=template.satisfaction_pattern,
                    over_time_criterion=template.over_time_criterion,
                    recognition_method=template.recognition_method,
                    ratable_convention=template.ratable_convention,
                    start_date_rule=template.start_date_rule or "LINE_START",
                    end_date_rule=template.end_date_rule or "LINE_END",
                    term_months=template.term_months,
                    principal_agent=template.principal_agent or "PRINCIPAL",
                    warranty_type=template.warranty_type or "NONE",
                    licence_nature=template.licence_nature or "NOT_APPLICABLE",
                    sfc_assessment_required=bool(template.sfc_assessment_required),
                    revenue_category=template.revenue_category,
                    disaggregation={},
                    account_role_overrides=dict(
                        sorted((template.account_role_overrides or {}).items())
                    ),
                    stratification_label=None,
                    is_excluded_from_netting_attribution=bool(
                        template.is_excluded_from_netting_attribution
                    ),
                    policy_values=_flat_policy_values(
                        template.policy_values,
                        self.path,
                        f"/world/pob_templates/{index}/policy_values",
                    ),
                    effective_from=self.world_start,
                    effective_to=None,
                )
            )
        if self.key.world.tenant.preset == PARITY_PRESET:
            # S03-R-18 assigns the seeded parity templates by line, whatever the product's
            # template; the preset provides them (T-MIG-01) unless the key defines the code.
            defined = {template.template_code for template in templates}
            templates.extend(
                seeded
                for seeded in parity_templates(self.world_start)
                if seeded.template_code not in defined
            )
        return tuple(sorted(templates, key=lambda t: (t.template_code, t.version_no)))

    def _product(self, code: str, inception: date) -> ProductInput:
        product = self.products.get(code)
        if product is None:
            raise self.error("/world/products", f"product {code} is not defined")
        index = self.key.world.products.index(product)
        components = tuple(
            BundleComponentInput(
                component_product_code=component.product,
                quantity_per_bundle=Decimal(component.quantity_per_bundle),
                split_basis=component.split_basis,
                split_ratio=_optional_amount(component.split_ratio),
                sequence=number,
                valid_from=inception,
                valid_to=None,
            )
            for number, component in enumerate(product.components or (), start=1)
        )
        template = product.pob_template
        if self.key.world.tenant.preset == PARITY_PRESET and any(
            item.code == template and item.obligation_kind == "MATERIAL_RIGHT"
            for item in self.key.world.pob_templates
        ):
            # S03-R-18: a key template of kind MATERIAL_RIGHT marks the product as a material right,
            # as the golden tenant's migration mapping profile does (L5-3-Q-24).
            template = LEGACY_MATERIAL_RIGHT
        return ProductInput(
            code=product.code,
            sku_number=product.sku_number,
            product_family=product.product_family,
            revenue_category=product.revenue_category,
            default_template_code=template,
            principal_agent=product.principal_agent or KEY_PRINCIPAL_AGENT,
            distinctness_default=product.distinctness_default or "distinct",
            unit_of_measure="EA",
            is_bundle=bool(product.is_bundle),
            policy_values=_flat_policy_values(
                product.policy_values, self.path, f"/world/products/{index}/policy_values"
            ),
            assurance_cost_per_unit=_optional_amount(product.assurance_cost_per_unit),
            components=components,
        )

    def _group_products(
        self, members: Sequence[Contract], events: Sequence[EventInput]
    ) -> set[str]:
        """Every product a member line, a modification line or a new line references, with the
        components of bundles."""
        codes: set[str] = set()
        for contract in members:
            codes.update(line.product_code for line in contract.lines)
            for modification in contract.modifications or ():
                codes.update(line.product_code for line in modification.lines if line.product_code)
        for event in events:
            for line in cast(Sequence[Mapping[str, object]], event.payload.get("new_lines", ())):
                codes.add(str(line["product_code"]))
        pending = list(codes)
        while pending:
            product = self.products.get(pending.pop())
            for component in (product.components or ()) if product else ():
                if component.product not in codes:
                    codes.add(component.product)
                    pending.append(component.product)
        # S05-R-11: a bundle product regularly sold together enters the group when all of its
        # components are products of the group, so the discount exception can resolve S_b
        # (L4-3-Q-17).
        for product in self.key.world.products:
            components = {component.product for component in product.components or ()}
            if product.is_bundle and components and components <= codes:
                codes.add(product.code)
        return codes

    def _ssp_versions(self) -> tuple[SspVersionInput, ...]:
        versions: list[SspVersionInput] = []
        for book in self.key.world.ssp_books:
            for number, version in enumerate(book.versions, start=1):
                version_key = f"{book.code}@v{number}"
                entries = []
                for entry in version.entries:
                    dims = (
                        entry.region,
                        entry.channel,
                        entry.segment,
                        entry.deal_size_band,
                        entry.term_band,
                    )
                    components = (
                        version_key,
                        subject_component(entry.product),
                        subject_component(entry.stratification or ""),
                        ",".join(subject_component(dim or "") for dim in dims),
                        entry.currency,
                    )
                    ranges = tuple(
                        sorted(
                            (
                                SspRangeInput(
                                    band_dimension=row.band_dimension or "NONE",
                                    band_from=_optional_amount(row.band_from),
                                    band_to=_optional_amount(row.band_to),
                                    point_value=_optional_amount(row.point_value),
                                    low_value=_optional_amount(row.low_value),
                                    mid_value=_optional_amount(row.mid_value),
                                    high_value=_optional_amount(row.high_value),
                                )
                                for row in entry.ranges
                            ),
                            key=lambda r: (
                                r.band_dimension,
                                r.band_from is not None,
                                r.band_from or 0,
                            ),
                        )
                    )
                    entries.append(
                        SspEntryInput(
                            entry_key="/".join(components),
                            product_code=entry.product,
                            stratification=entry.stratification or "",
                            region=entry.region,
                            channel=entry.channel,
                            segment=entry.segment,
                            deal_size_band=entry.deal_size_band,
                            term_band=entry.term_band,
                            currency=entry.currency,
                            method=entry.method,
                            # T-REF-30 default for an omitted basis on a non-series entry; a
                            # series entry always declares one (the loader rule of dev-guide
                            # §9.5.3 `ssp_books`, D-93 (4)).
                            value_basis=entry.value_basis or "AMOUNT",
                            quantity_unit=entry.quantity_unit,
                            unit_list_price=_optional_amount(entry.unit_list_price),
                            midpoint_discount_ratio=_optional_amount(entry.midpoint_discount_ratio),
                            range_ratio=_optional_amount(entry.range_ratio),
                            cost_basis=_optional_amount(entry.cost_basis),
                            margin_ratio=_optional_amount(entry.margin_ratio),
                            distinctness=entry.distinctness,
                            revenue_account_code=entry.revenue_account,
                            observable_point=_optional_amount(entry.observable_point),
                            ranges=ranges,
                        )
                    )
                entries.sort(
                    key=lambda e: (
                        e.product_code, e.stratification, e.region or "", e.channel or "",
                        e.segment or "", e.deal_size_band or "", e.term_band or "", e.currency,
                    )
                )  # fmt: skip
                versions.append(
                    SspVersionInput(
                        ssp_book_code=book.code,
                        version_key=version_key,
                        version_no=number,
                        resolution_mode=book.resolution_mode,
                        legacy_version_label=version.legacy_version_label,
                        effective_from_date=_optional_date(version.effective_from_date),
                        effective_to_date=_optional_date(version.effective_to_date),
                        status="APPROVED",
                        approved_at=self.setup_at,
                        content_sha256=_content_sha256(version),
                        scope_entity_code=book.entity,
                        scope_currency=book.currency,
                        scope_channel=None,
                        scope_segment=None,
                        entries=tuple(entries),
                    )
                )
        return tuple(sorted(versions, key=lambda v: (v.ssp_book_code, v.version_no)))

    def _rule_sets(self) -> tuple[RuleSetInput, ...]:
        rule_sets: list[RuleSetInput] = []
        for index, rule_set in enumerate(self.key.world.rule_sets):
            rules: list[RuleInput] = []
            for number, rule in enumerate(rule_set.rules):
                pointer = f"/world/rule_sets/{index}/rules/{number}"
                conditions = rule.conditions
                if not isinstance(conditions, list) or not all(
                    isinstance(c, dict) for c in conditions
                ):
                    raise self.error(f"{pointer}/conditions", "conditions are a list of mappings")
                if not isinstance(rule.outputs, dict):
                    raise self.error(f"{pointer}/outputs", "outputs are a mapping")
                condition_maps = tuple(cast(Mapping[str, object], c) for c in conditions)
                try:
                    specificity = validate_conditions(rule_set.kind, condition_maps)
                except (TypeError, ValueError) as problem:
                    raise self.error(f"{pointer}/conditions", str(problem)) from problem
                outputs = {name: str(value) for name, value in sorted(rule.outputs.items())}
                rules.append(
                    RuleInput(rule.rule_key, rule.priority, specificity, condition_maps, outputs)
                )
            rules.sort(key=lambda r: (-r.specificity, -r.priority, r.rule_key))
            rule_sets.append(
                RuleSetInput(
                    rule_set_code=rule_set.code,
                    kind=rule_set.kind,
                    version_key=f"{rule_set.code}@v1",
                    version_no=1,
                    content_sha256=_content_sha256(rule_set),
                    effective_from=self.world_start,
                    effective_to=None,
                    rules=tuple(rules),
                )
            )
        return tuple(sorted(rule_sets, key=lambda r: (r.rule_set_code, r.version_no)))

    def _fx_rates(self) -> tuple[FxRateInput, ...]:
        rates = [
            FxRateInput(
                rate_key="/".join(
                    (
                        rate_set.code,
                        rate.base_currency,
                        rate.quote_currency,
                        rate.effective_date,
                        rate.period_key or "",
                    )
                ),
                version_key=f"{rate_set.code}@v1",
                rate_type=rate_set.rate_type,
                base_currency=rate.base_currency,
                quote_currency=rate.quote_currency,
                effective_date=_date(rate.effective_date),
                period_key=rate.period_key,
                rate=Decimal(rate.rate),
            )
            for rate_set in self.key.world.fx_rate_sets
            for rate in rate_set.rates
        ]
        rates.sort(
            key=lambda r: (
                r.rate_type,
                r.base_currency,
                r.quote_currency,
                r.effective_date,
                r.version_key,
                r.rate_key,
            )
        )
        return tuple(rates)

    # Contracts

    def _contract(self, contract: Contract, modification_keys: set[str]) -> ContractInput:
        customer = self.customers.get(contract.customer)
        termination = contract.termination
        return ContractInput(
            external_id=contract.external_id,
            customer_code=contract.customer,
            related_party_group=customer.related_party_group if customer else None,
            contracting_entity_code=contract.contracting_entity,
            transaction_currency=contract.transaction_currency,
            inception_date=_date(contract.inception_date),
            signature_date=_optional_date(contract.signature_date),
            document_ref=None,
            termination_party=termination.party if termination else None,
            termination_has_penalty=termination.has_penalty if termination else None,
            termination_notice_days=termination.notice_days if termination else None,
            has_commercial_substance=contract.has_commercial_substance is not False,
            region=contract.region,
            channel=contract.channel,
            contract_type=contract.contract_type,
            renewal_of_contract_key=contract.renewal_of,
            judgements=tuple(
                sorted(
                    (
                        *(
                            self._judgement(contract, judgement)
                            for judgement in contract.judgements or ()
                        ),
                        *self._immaterial_judgements(contract),  # L5-3-Q-9
                        *self.agent_records.get(contract.external_id, ()),
                        *self.nondistinct.get(contract.external_id, ()),  # L7-5-Q-11
                    ),
                    key=lambda j: j.judgement_key,
                )
            ),
            material_rights=tuple(
                sorted(
                    (
                        MaterialRightInput(
                            obligation_key=right.obligation_key,
                            option_type=right.option_type,
                            incremental_discount_ratio=_optional_amount(
                                right.incremental_discount_ratio
                            ),
                            is_discount_available_without_contract=bool(
                                right.is_discount_available_without_contract
                            ),
                            expected_purchase_amount=_optional_amount(
                                right.expected_purchase_amount
                            ),
                            currency=contract.transaction_currency,
                            ssp_method=right.ssp_method,
                            expiry_date=_optional_date(right.expiry_date),
                            likelihood_estimate_key=(
                                obligation_subject_key(
                                    contract.external_id, right.likelihood_estimate
                                )
                                if right.likelihood_estimate
                                else None
                            ),
                            is_legacy_quantity_ssp_dollars=bool(
                                right.is_legacy_quantity_ssp_dollars
                            ),
                        )
                        for right in contract.material_rights or ()
                    ),
                    key=lambda m: m.obligation_key,
                )
            ),
            modifications=tuple(
                self._modification(contract, modification)
                for modification in sorted(contract.modifications or (), key=lambda m: m.reference)
                if modification.reference in modification_keys
            ),
            noncash_consideration=self._noncash(contract),
            consideration_payable=self._payable(contract),
            payment_schedule=tuple(
                PaymentPointInput(_date(point.date), _amount(point.amount))
                for point in contract.payment_schedule or ()
            ),
            scope_605_35=contract.scope_605_35,
        )

    @staticmethod
    def _judgement_key(contract: Contract, handle: str) -> str:
        return obligation_subject_key(contract.external_id, handle)

    def _judgement(self, contract: Contract, judgement: Judgement) -> JudgementInput:
        """A REVIEWED T-CON-19 record; the questionnaire members as strings (DG-AK-40 rev 1.3)."""
        subject = (
            obligation_subject_key(contract.external_id, judgement.subject_obligation_key)
            if judgement.subject_obligation_key
            else contract.external_id
        )
        return JudgementInput(
            judgement_key=self._judgement_key(contract, judgement.handle),
            topic=judgement.topic,
            subject_key=subject,
            book_code=judgement.book_code,
            outcome={
                name: _render(value)
                for name, value in sorted((judgement.questionnaire or {}).items())
            },
        )

    @staticmethod
    def _noncash(contract: Contract) -> tuple[NoncashInput, ...]:
        return tuple(
            NoncashInput(
                units=Decimal(item.units),
                fair_value_per_unit=Decimal(item.fair_value_per_unit),
                measurement_date=_date(item.measurement_date),
                variability=item.variability,
                asset_type=item.asset_type,
            )
            for item in contract.noncash_consideration or ()
        )

    @staticmethod
    def _payable(contract: Contract) -> tuple[PayableInput, ...]:
        return tuple(
            PayableInput(
                amount=_amount(item.amount),
                promise_date=_date(item.promise_date),
                related_obligation_keys=tuple(item.related_obligation_keys),
                distinct_good_fair_value=_optional_amount(item.distinct_good_fair_value),
                committed_purchases=_optional_amount(item.committed_purchases),
                share_based=item.share_based,
            )
            for item in contract.consideration_payable or ()
        )

    def _modification(self, contract: Contract, modification: Modification) -> ModificationInput:
        return ModificationInput(
            modification_key=modification.reference,
            effective_date=_date(modification.effective_date),
            kind=modification.kind,
            template_mode=modification.template_mode,
            status="APPROVED",
            reference=modification.reference,
            questionnaire={
                **self._questionnaire(contract, modification),  # L7-5-Q-2 (ii)
                **self._settlement_member(contract, modification),
            },
            lines=tuple(self._modification_lines(contract, modification)),
            price_change_amount=(
                None  # the converted price_change_amount is null (L5-3-Q-19)
                if (contract.external_id, modification.reference) in self.terms
                else _optional_amount(modification.price_change_amount)
            ),
            noncash_consideration=None,
            consideration_payable=None,
            scope_605_35=None,
            currency=contract.transaction_currency,
            proposed_treatments={},
            chosen_treatments=dict(sorted((modification.chosen_treatments or {}).items())),
            treatment_summary=None,
            ssp_basis={},
            judgement_key=None,
            # Lines dump one by one: the discriminated union does not serialise through the parent.
            content_sha256=sha256_hex(
                {
                    **modification.model_dump(mode="json", exclude={"lines"}),
                    "lines": [line.model_dump(mode="json") for line in modification.lines],
                }
            ),
        )

    # Events

    def _events(
        self, items: Sequence[object], member_keys: set[str]
    ) -> tuple[tuple[EventInput, ...], tuple[EstimateVersionInput, ...], set[str]]:
        streams: dict[str, int] = {}
        latest_estimate: dict[str, str] = {}
        estimate_versions: dict[str, EstimateVersionInput] = {}
        modification_keys: set[str] = set()
        events: list[EventInput] = []
        for item in items:
            if not isinstance(item, EventItem):
                continue
            if item.contract in member_keys:
                separate = self._separate_contract(item)
                if separate is not None:
                    # S06-R-03: no event; the modification stays, so its proposal publishes.
                    modification_keys.add(separate)
                    continue
            stream_version = streams[item.contract] = streams.get(item.contract, 0) + 1
            if item.contract not in member_keys:
                continue
            contract = self.contracts[item.contract]
            pointer = f"/timeline/{self.positions[item.seq]}/payload"
            payload, refs = self._payload(contract, item, pointer)
            if refs.modification_key is not None:
                modification_keys.add(refs.modification_key)
            estimate_version_key: str | None = None
            if refs.estimate_version_key is not None:
                version = self._estimate_version(
                    contract, refs.estimate_version_key, latest_estimate, pointer
                )
                estimate_versions[version.version_key] = version
                estimate_version_key = version.version_key
                payload["estimate_version_id"] = version.version_key
                if version.supersedes_version_key is not None:
                    payload["previous_estimate_version_id"] = version.supersedes_version_key
            events.append(
                EventInput(
                    event_key=f"{subject_component(contract.external_id)}/EV-{stream_version:06d}",
                    contract_key=contract.external_id,
                    stream_version=stream_version,
                    event_type=item.event_type,
                    schema_version=1,
                    effective_date=_date(item.effective_date),
                    recorded_at=self.times[item.seq],
                    record_seq=item.seq,
                    origin=EVENT_ORIGIN,
                    is_manual=item.is_manual,
                    obligation_keys=self._obligation_keys(payload),
                    payload=payload,
                    payload_sha256=sha256_hex(payload),
                    idempotency_key=None,
                    supersedes_event_key=None,
                    modification_key=refs.modification_key,
                    estimate_version_key=estimate_version_key,
                    manual_adjustment_key=None,
                )
            )
            if item.event_type == "CONTRACT_BOOKED":
                # S01-R-06, S01-R-18: version 1 of each parity VC element applies after booking.
                for version in self._parity_vc_elements(contract):
                    stream_version = streams[item.contract] = streams[item.contract] + 1
                    estimate_versions[version.version_key] = version
                    applied: dict[str, object] = {"estimate_version_id": version.version_key}
                    events.append(
                        EventInput(
                            event_key=f"{subject_component(contract.external_id)}/"
                            f"EV-{stream_version:06d}",
                            contract_key=contract.external_id,
                            stream_version=stream_version,
                            event_type="ESTIMATE_CHANGED",
                            schema_version=1,
                            effective_date=_date(contract.inception_date),
                            recorded_at=self.times[item.seq],
                            record_seq=item.seq,
                            origin=EVENT_ORIGIN,
                            is_manual=False,
                            obligation_keys=(),
                            payload=applied,
                            payload_sha256=sha256_hex(applied),
                            idempotency_key=None,
                            supersedes_event_key=None,
                            modification_key=None,
                            estimate_version_key=version.version_key,
                            manual_adjustment_key=None,
                        )
                    )
            if self.activations.get(item.contract) == item.seq:
                # L6-5-Q-12 (i): CONTRACT_ACTIVATED right after the first assessment.
                stream_version = streams[item.contract] = streams[item.contract] + 1
                activated: dict[str, object] = {
                    "checklist": [dict(check) for check in PASSING_CHECKLIST]
                }
                events.append(
                    EventInput(
                        event_key=f"{subject_component(contract.external_id)}/"
                        f"EV-{stream_version:06d}",
                        contract_key=contract.external_id,
                        stream_version=stream_version,
                        event_type="CONTRACT_ACTIVATED",
                        schema_version=1,
                        effective_date=_date(item.effective_date),
                        recorded_at=self.times[item.seq],
                        record_seq=item.seq,
                        origin=EVENT_ORIGIN,
                        is_manual=False,
                        obligation_keys=(),
                        payload=activated,
                        payload_sha256=sha256_hex(activated),
                        idempotency_key=None,
                        supersedes_event_key=None,
                        modification_key=None,
                        estimate_version_key=None,
                        manual_adjustment_key=None,
                    )
                )
        events.sort(key=lambda e: (e.effective_date, e.record_seq, e.event_key))
        versions = tuple(
            sorted(estimate_versions.values(), key=lambda v: (v.estimate_key, v.version_no))
        )
        return tuple(events), versions, modification_keys

    @staticmethod
    def _obligation_keys(payload: Mapping[str, object]) -> tuple[str, ...]:
        keys: set[str] = set()
        if isinstance(payload.get("obligation_key"), str):
            keys.add(cast(str, payload["obligation_key"]))
        keys.update(cast(Sequence[str], payload.get("obligation_keys", ())))
        for member in ("lines", "new_lines"):
            for line in cast(Sequence[Mapping[str, object]], payload.get(member, ())):
                keys.add(str(line["obligation_key"]))
        return tuple(sorted(keys))

    def _payload(
        self, contract: Contract, item: EventItem, pointer: str
    ) -> tuple[dict[str, object], _EventRefs]:
        """04 §16.3 payload with typed values and handles resolved to natural keys (§9.5.5)."""
        payload: dict[str, object] = {}
        if item.event_type == "CONTRACT_BOOKED":
            payload.update(self._booking_payload(contract))
        elif item.event_type == "CONTRACT_ACTIVATED" and not item.payload:
            payload["checklist"] = [dict(check) for check in PASSING_CHECKLIST]
        modification_key: str | None = None
        estimate_version_key: str | None = None
        for name, value in sorted(item.payload.items()):
            if name == "judgement":
                handles = {j.handle for j in contract.judgements or ()}
                if value not in handles:
                    raise self.error(f"{pointer}/judgement", f"judgement {value} is not defined")
                payload["judgement_record_id"] = self._judgement_key(contract, str(value))
            elif name == "modification":
                modification = self._find_modification(contract, str(value), pointer)
                modification_key = modification.reference
                payload["modification_id"] = modification.reference
                if item.event_type == "CONTRACT_AMENDED":
                    payload["treatments"] = self._payload_treatments(
                        contract, modification, item.seq
                    )
                    payload["lines"] = self._modification_lines(contract, modification)
                    payload["ssp_basis"] = {}
                    payload.update(self._settlement_member(contract, modification))  # D-85
            elif name == "estimate":
                version_no = item.payload.get("version_no")
                if not isinstance(version_no, str) or not version_no.isdigit():
                    raise self.error(f"{pointer}/version_no", "an estimate handle needs version_no")
                estimate_version_key = f"{value}@v{int(version_no)}"
            elif name == "version_no":
                continue
            elif name == "tax_lines":
                lines = [
                    {**line, "amount": _amount(line["amount"])}
                    for line in cast(Sequence[Mapping[str, object]], value)
                ]
                payload["tax_lines"] = lines
                payload["tax_amount"] = sum(
                    (cast(Decimal, line["amount"]) for line in lines), Decimal(0)
                )
            elif name == "new_lines":
                payload[name] = [
                    _line_payload(ContractLine.model_validate(line))
                    for line in cast(Sequence[object], value)
                ]
            elif name == "obligations":
                payload[name] = [
                    {
                        member: member_value
                        if member == "obligation_key"
                        else _amount(member_value)
                        for member, member_value in sorted(cast(Mapping[str, object], row).items())
                    }
                    for row in cast(Sequence[object], value)
                ]
            elif name in MONEY_PAYLOAD_MEMBERS or name in DECIMAL_PAYLOAD_MEMBERS:
                payload[name] = _amount(value)
            elif name in DATE_PAYLOAD_MEMBERS:
                payload[name] = _date(value)
            else:
                payload[name] = value
        return payload, _EventRefs(modification_key, estimate_version_key)

    @staticmethod
    def _treatments(contract: Contract, modification: Modification) -> dict[str, str]:
        """``CONTRACT_AMENDED.treatments``: the chosen treatments of the modification.

        A legacy template names one treatment, and it applies to every obligation of the contract,
        untouched and fully delivered ones included (ENGINE_SPEC S06-R-28; L4-3-Q-31). The
        obligations are the booked lines and the lines of this and the earlier modifications.
        """
        chosen = dict(sorted((modification.chosen_treatments or {}).items()))
        kinds = set(chosen.values())
        if modification.template_mode is None or len(kinds) != 1:
            return chosen
        (kind,) = kinds
        if not kind.startswith("LEGACY_"):
            return chosen
        keys = {line.obligation_key for line in contract.lines}
        for earlier in contract.modifications or ():
            keys.update(line.obligation_key for line in earlier.lines)
            if earlier.reference == modification.reference:
                break
        return {key: chosen.get(key, kind) for key in sorted(keys)}

    def _payload_treatments(
        self, contract: Contract, modification: Modification, seq: int
    ) -> dict[str, str]:
        """``CONTRACT_AMENDED.treatments``: the chosen treatments, else the engine-proposed ones
        (§9.5.4, §9.5.5; S06-R-01; L4-3-Q-23, L5-3-Q-18)."""
        if modification.chosen_treatments:
            return self._treatments(contract, modification)
        return self._proposed(contract, modification, seq)

    def _proposed(self, contract: Contract, modification: Modification, seq: int) -> dict[str, str]:
        """The proposal ``compute`` publishes for the modification over the items before its event.

        The bundle carries the modification without an event, as the platform classifies a draft
        through ``compute`` (BUILD_SPEC CTR-17; S06-R-01). The primary book's proposal of kind
        ``MODIFICATION_TREATMENT`` with ``detail.modification_key`` gives the treatments.
        """
        cache_key = (contract.external_id, modification.reference)
        cached = self.proposed.get(cache_key)
        if cached is not None:
            return cached
        pointer = f"/timeline/{self.positions[seq]}/payload/modification"
        compute = getattr(erev_engine, "compute", None)
        if compute is None:
            raise self.error(pointer, MISSING_COMPUTE)
        items = [item for item in self.timeline if item.seq < seq and item.expect_problem is None]
        group = contract.combination_group or f"CG-{contract.external_id}"
        pending = frozenset({modification.reference})
        (bundle,) = self._bundles(items, self.times[seq], only_group=group, pending=pending)
        output = cast(OutputBundle, compute(bundle))
        book = next(item for item in output.books if item.book_code == self.books[0])
        subject = subject_component(contract.external_id)
        proposal = next(
            (
                item
                for item in book.proposals
                if item.kind == MODIFICATION_PROPOSAL
                and item.subject_key == subject
                and item.detail.get("modification_key") == modification.reference
            ),
            None,
        )
        if proposal is None:
            raise self.error(pointer, f"compute published no proposal for {modification.reference}")
        found = dict(sorted(proposal.treatments.items()))
        self.proposed[cache_key] = found
        return found

    def _separate_contract(self, item: EventItem) -> str | None:
        """The modification a ``CONTRACT_AMENDED`` item names when every treatment is
        ``SEPARATE_CONTRACT``. The platform then books a new contract and appends nothing to the
        original stream (S06-R-03), so the runner skips the event and keeps the modification in
        the bundle, which publishes its proposal (L5-3-Q-18)."""
        reference = item.payload.get("modification")
        if item.event_type != "CONTRACT_AMENDED" or not isinstance(reference, str):
            return None
        contract = self.contracts[item.contract]
        modification = next(
            (found for found in contract.modifications or () if found.reference == reference), None
        )
        if modification is None:
            return None  # _payload raises for an undefined modification
        treatments = self._payload_treatments(contract, modification, item.seq)
        return reference if set(treatments.values()) == {"SEPARATE_CONTRACT"} else None

    def _booking_payload(self, contract: Contract) -> dict[str, object]:
        """The API-S-ContractCreate header fields and ``lines`` of the contract (§9.5.5)."""
        payload: dict[str, object] = {
            "external_id": contract.external_id,
            "customer": {"code": contract.customer},
            "contracting_entity_code": contract.contracting_entity,
        }
        for name, value in contract.model_dump(
            exclude_none=True, exclude=set(NON_HEADER_MEMBERS)
        ).items():
            payload[name] = _date(value) if name in ("inception_date", "signature_date") else value
        if contract.renewal_of is not None:
            payload["renewal_of_contract_id"] = contract.renewal_of
        if contract.payment_schedule:
            payload["payment_schedule"] = [
                {"date": _date(point.date), "amount": _amount(point.amount)}
                for point in contract.payment_schedule
            ]
        if contract.noncash_consideration:
            payload["noncash_consideration"] = [
                {
                    "units": Decimal(item.units),
                    "fair_value_per_unit": Decimal(item.fair_value_per_unit),
                    "measurement_date": _date(item.measurement_date),
                    "variability": item.variability,
                    "asset_type": item.asset_type,
                }
                for item in contract.noncash_consideration
            ]
        if contract.consideration_payable:
            payload["consideration_payable"] = [
                {
                    name: value
                    for name, value in (
                        ("amount", item.amount),
                        ("promise_date", item.promise_date),
                        ("related_obligation_keys", list(item.related_obligation_keys)),
                        ("distinct_good_fair_value", item.distinct_good_fair_value),
                        ("committed_purchases", item.committed_purchases),
                        ("share_based", item.share_based),
                    )
                    if value is not None
                }
                for item in self._payable(contract)
            ]
        payload["lines"] = [self._parity_line(line, _line_payload(line)) for line in contract.lines]
        return payload

    def _parity_line(self, line: ContractLine, payload: dict[str, object]) -> dict[str, object]:
        """S01-R-06, S03-R-18: under the parity preset the engine assigns ``LEGACY-VC`` (kind
        ``VC_LINE``) by the stratification ``VC`` the legacy setup import gives a VC row."""
        if self._parity_vc_row(line) and line.stratification is None:
            return {**payload, "stratification": "VC"}
        return payload

    def _parity_vc_row(self, line: ContractLine) -> bool:
        """A VC row of the legacy setup import under the parity preset (S01-R-06): stratification
        ``VC``, or no stratification and a product whose key template is of kind ``VC_LINE``
        (L5-5-Q-2)."""
        if self.key.world.tenant.preset != PARITY_PRESET:
            return False
        if line.stratification is not None:
            return line.stratification == "VC"
        product = self.products.get(line.product_code)
        kinds = {
            template.code: template.obligation_kind for template in self.key.world.pob_templates
        }
        return product is not None and kinds.get(product.pob_template) == "VC_LINE"

    def _parity_vc_elements(self, contract: Contract) -> tuple[EstimateVersionInput, ...]:
        """S01-R-06: each VC row adds the contract-level VC element ``<contract>/VC-<obligation
        key>``, ``ENTERED_AMOUNT``, version 1 constrained amount = ``total_price``, effective on the
        inception date, ``allocation_target = CONTRACT`` (POL-213; REQ-TP-016), which the platform
        applies at activation (S01-R-18; ``support.golden_streams``). The parity element carries
        no ``direction`` and its signed row price as stored by the L5 fixtures; CTR-12 stores
        |price| with ``DECREASE`` for a negative row (``legacy_v1.contract_setup``, L5-1-Q-15), a
        representation difference kept as a supervisor question (ENC-VC-direction Q-3)."""
        found: list[EstimateVersionInput] = []
        for line in contract.lines:
            if not self._parity_vc_row(line) or line.total_price is None:
                continue
            element = f"VC-{line.obligation_key}"
            estimate_key = obligation_subject_key(contract.external_id, element)
            version_key = f"{estimate_key}@v1"
            price = _amount(line.total_price)
            found.append(
                EstimateVersionInput(
                    estimate_key=estimate_key,
                    estimate_kind="VARIABLE_CONSIDERATION",
                    element_code=element,
                    method="ENTERED_AMOUNT",
                    vc_element_type=None,
                    allocation_target="CONTRACT",
                    target_obligation_keys=(),
                    obligation_key=None,
                    version_key=version_key,
                    version_no=1,
                    status="APPROVED",
                    effective_date=_date(contract.inception_date),
                    scenarios=(),
                    parameters={},
                    unconstrained_amount=None,
                    most_conservative_amount=None,
                    constrained_amount=price,
                    rate=None,
                    expected_total_amount=None,
                    expected_quantity=None,
                    amortization_months=None,
                    currency=contract.transaction_currency,
                    supersedes_version_key=None,
                    judgement_key=None,
                    content_sha256=sha256_hex(
                        {"version_key": version_key, "constrained_amount": price}
                    ),
                )
            )
        return tuple(found)

    def _find_modification(self, contract: Contract, reference: str, pointer: str) -> Modification:
        for modification in contract.modifications or ():
            if modification.reference == reference:
                return modification
        raise self.error(f"{pointer}/modification", f"modification {reference} is not defined")

    def _estimate_version(
        self,
        contract: Contract,
        handle: str,
        latest: dict[str, str],
        pointer: str,
    ) -> EstimateVersionInput:
        """The APPROVED version an ESTIMATE_CHANGED item applies (T-CON-12, T-CON-13)."""
        element_code, _, number = handle.rpartition("@v")
        estimate_key, estimate = self._find_estimate(contract, element_code, pointer)
        version_no = int(number)
        version = next((v for v in estimate.versions if v.version_no == version_no), None)
        if version is None:
            raise self.error(
                f"{pointer}/version_no", f"estimate {element_code} has no version {version_no}"
            )
        version_key = f"{estimate_key}@v{version_no}"
        previous = latest.get(estimate_key)
        latest[estimate_key] = version_key
        return self._estimate_input(estimate_key, estimate, version, version_key, previous)

    def _find_estimate(
        self, contract: Contract, element_code: str, pointer: str
    ) -> tuple[str, Estimate]:
        """§9.5.3: an estimate handle resolves in the item's contract, then in its portfolios."""
        for estimate in contract.estimates or ():
            if estimate.element_code == element_code:
                return obligation_subject_key(contract.external_id, element_code), estimate
        for portfolio in self.key.world.portfolios:
            if contract.external_id in portfolio.members:
                for estimate in portfolio.estimates or ():
                    if estimate.element_code == element_code:
                        key = f"PORTFOLIO:{subject_component(portfolio.code)}"
                        key = f"{key}/{subject_component(element_code)}"
                        return key, estimate
        raise self.error(f"{pointer}/estimate", f"estimate {element_code} is not defined")

    @staticmethod
    def _estimate_input(
        estimate_key: str,
        estimate: Estimate,
        version: EstimateVersion,
        version_key: str,
        previous: str | None,
    ) -> EstimateVersionInput:
        # T-CON-12 `allocation_criteria_evidence` reaches the engine on each version's parameters
        # (S05-R-14 `targeted.evidenced`), beside the T-CON-13 parameters of the version. The
        # T-CON-12 `direction` is the key's explicit value or the loader's B3-DG-17 derivation
        # (models.Estimate; ENC-VC-direction); amounts are magnitudes (B3-D16).
        return EstimateVersionInput(
            estimate_key=estimate_key,
            estimate_kind=estimate.estimate_kind,
            element_code=estimate.element_code,
            method=estimate.method,
            vc_element_type=estimate.vc_element_type,
            direction=estimate.direction,
            allocation_target=estimate.allocation_target or "CONTRACT",
            target_obligation_keys=tuple(estimate.target_obligation_keys or ()),
            obligation_key=estimate.obligation_key,
            version_key=version_key,
            version_no=version.version_no,
            status="APPROVED",
            effective_date=_date(version.effective_date),
            scenarios=tuple(
                {"amount": Decimal(s.amount), "probability": Decimal(s.probability)}
                for s in version.scenarios or ()
            ),
            parameters=_estimate_parameters(estimate, version),
            unconstrained_amount=_optional_amount(version.unconstrained_amount),
            most_conservative_amount=_optional_amount(version.most_conservative_amount),
            constrained_amount=_optional_amount(version.constrained_amount),
            rate=_optional_amount(version.rate),
            expected_total_amount=_optional_amount(version.expected_total_amount),
            expected_quantity=_optional_amount(version.expected_quantity),
            amortization_months=version.amortization_months,
            currency=version.currency,
            supersedes_version_key=previous,
            judgement_key=None,
            content_sha256=_content_sha256(version),
        )


# --- Checkpoint assertions (§9.5.6; §9.5.7 DG-AK-50 to DG-AK-57) ---------------------------------

ABSENT: Final = "<absent>"
# D-90: a posting intent a contract-filtered subledger block cannot attribute (§9.5.6 `contract`).
UNATTRIBUTED: Final = "<unattributed>"
# D-90: the stage 10 refund component kinds whose source names contracts (refund_liability.py; the
# key form is matched here, not imported).
RETURN_COMPONENT: Final = "RETURN"
VC_COMPONENT: Final = "VARIABLE_CONSIDERATION"
TERMINATION_COMPONENT: Final = "TERMINATION"
CONCESSION_COMPONENT: Final = "CONCESSION"
PLATFORM_RUNNER_MISSING: Final = (
    "platform answer keys run through support.answer_keys.platform_runner.run_platform "
    "(BUILD_SPEC PRP-1), never the engine runner (XR-12)"
)
LEGACY_BOOK: Final = "LEGACY"  # ENGINE_SPEC §0.5: the only book without a contract version
ALLOCATION_BASIS_MEASURE: Final = "tp_allocation_basis"  # ENGINE_SPEC §4.4 trace nodes
MODIFICATION_PROPOSAL: Final = "MODIFICATION_TREATMENT"  # ENGINE_SPEC CV-16
STEP_CHECKPOINT: Final = "timeline"  # the checkpoint label of expect_problem mismatches
IDENTITY_BASIS: Final = (
    "DG-AK-54 sum allocated_amount - expected_returns_amount = tp_allocation_basis"
)
IDENTITY_PRICE: Final = (
    "DG-AK-54 sum allocated_amount = transaction_price - consideration_payable_amount"
)
IDENTITY_OBLIGATION: Final = (
    "DG-AK-54 allocated_amount = revenue_cum + scheduled_amount + awaiting_trigger_amount"
)
IDENTITY_TRACE: Final = "DG-AK-54 reevaluate(trace)"
_REMAINDER_PARTS: Final = ("revenue_cum", "scheduled_amount", "awaiting_trigger_amount")
_SUBJECT_ESCAPE: Final = re.compile("%(2F|40|23|3A|25)")
_SUBJECT_DECODED: Final = {"2F": "/", "40": "@", "23": "#", "3A": ":", "25": "%"}
# D-90: one CV-21 encoded component (no raw delimiter, every `%` an escape encode_key writes) and
# the CV-22 event serial of a global event key `<encoded external_id>/EV-<6 digits>`.
_ENCODED_COMPONENT: Final = re.compile("(?:[^%/@#:]|%(?:2F|40|23|3A|25))+")
_EVENT_SERIAL: Final = re.compile("EV-[0-9]{6,}")

GrainKey = tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class Mismatch:
    """One DG-AK-55 difference between a checkpoint expectation and the run."""

    key_id: str
    checkpoint: str
    subject: str  # the object compared, for example "obligation C-1/L1"
    field: str
    expected: str
    actual: str

    def render(self) -> str:
        return (
            f"{self.key_id} {self.checkpoint} {self.subject} {self.field}: "
            f"expected {self.expected}, actual {self.actual}"
        )

    def to_json(self) -> dict[str, str]:
        return {
            "checkpoint": self.checkpoint,
            "object": self.subject,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
        }


class CheckpointMismatchError(AssertionError):
    """Every mismatch of every checkpoint of one key, raised once (DG-AK-55)."""

    def __init__(self, key_id: str, mismatches: Sequence[Mismatch]) -> None:
        self.key_id = key_id
        self.mismatches = tuple(mismatches)
        lines = [f"answer key {key_id}: {len(self.mismatches)} checkpoint mismatches"]
        lines += [f"- {mismatch.render()}" for mismatch in self.mismatches]
        super().__init__("\n".join(lines))


def assert_checkpoints(key: LoadedKey, result: RunResult) -> None:
    """Compare every checkpoint with its run, collect every mismatch, then fail once (§9.5.7).

    Explicit blocks compare under DG-AK-50 to DG-AK-53, DG-AK-56 and DG-AK-57; every computed book
    of every checkpoint also meets the DG-AK-54 identities. Every ``expect_problem`` item must have
    raised its code (§9.5.5; D-79).
    """
    if result.runner != "engine":
        raise AnswerKeyError(key.path, "/runner", PLATFORM_RUNNER_MISSING)
    runs = {run.checkpoint.name: run for run in result.checkpoints}
    mismatches = _step_mismatches(key.key, result.steps)
    for checkpoint in key.key.checkpoints:
        run = runs.get(checkpoint.name)
        if run is None:
            mismatches.append(
                Mismatch(key.key.id, checkpoint.name, "checkpoint", "run", "computed", ABSENT)
            )
            continue
        steps = tuple(
            outcome for outcome in result.steps if outcome.step.seq <= checkpoint.after_seq
        )
        comparison = _CheckpointComparison(key.key, checkpoint, run, steps, result.range_findings)
        mismatches.extend(comparison.mismatches())
    if mismatches:
        raise CheckpointMismatchError(key.key.id, mismatches)


def _step_mismatches(key: AnswerKey, steps: Sequence[StepOutcome]) -> list[Mismatch]:
    """An ``expect_problem`` item whose step returned, raised another code or was not run."""
    outcomes = {outcome.step.seq: outcome for outcome in steps}
    found: list[Mismatch] = []
    for item in sorted(key.timeline, key=lambda item: item.seq):
        if item.expect_problem is None:
            continue
        outcome = outcomes.get(item.seq)
        actual = ABSENT if outcome is None else outcome.actual
        if actual != item.expect_problem.code:
            subject = f"timeline seq {item.seq}"
            code = item.expect_problem.code
            found.append(Mismatch(key.id, STEP_CHECKPOINT, subject, "expect_problem", code, actual))
    return found


# --- Values (DG-AK-50 to DG-AK-53) ---------------------------------------------------------------


def _minor_unit(currency: str) -> int:
    return ISO_4217[currency].minor_unit


def _kind(column_type: str) -> str:
    """DG-AK-50: the comparison kind of a 04 column type."""
    if column_type == "erev.money":
        return "money"
    if column_type in ("erev.exact", "erev.fx_rate"):
        return "exact"
    if column_type in ("integer", "boolean"):
        return column_type
    return "text"


def _number(value: object) -> Fraction | None:
    if isinstance(value, bool) or not isinstance(value, int | Decimal | Fraction | str):
        return None
    try:
        return to_fraction(value)
    except Exception:  # an unparsable engine value compares as a mismatch
        return None


def _money_units(value: object, currency: str | None) -> Fraction | None:
    """A posted amount in currency units: int minor units (XR-03), else a decimal value."""
    if isinstance(value, int) and not isinstance(value, bool) and currency is not None:
        return Fraction(value, 10 ** _minor_unit(currency))
    return _number(value)


def _format_units(value: Fraction, currency: str | None) -> str:
    if currency is not None:
        scaled = value * 10 ** _minor_unit(currency)
        if scaled.denominator == 1:
            return format_money(scaled.numerator, _minor_unit(currency))
    return format_exact(value)


def _render_actual(value: object) -> str:
    if value is None:
        return ABSENT
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return ",".join(_render_actual(item) for item in value)
    if isinstance(value, Fraction):
        return format_exact(value)
    return str(value)


def _render_expected(value: object) -> str:
    return value.amount if isinstance(value, MoneyAmount) else _render_actual(value)


def _money_text(value: Money | None) -> Fraction:
    if value is None:
        return Fraction(0)
    return to_fraction(value.amount if isinstance(value, MoneyAmount) else value)


def _differs(kind: str, expected: object, actual: object, currency: str | None) -> str | None:
    """The rendered actual value when it differs from ``expected``, else None."""
    if actual is None:
        return ABSENT
    if kind == "money":  # DG-AK-51: equal to the minor unit
        code = expected.currency if isinstance(expected, MoneyAmount) else currency
        units = _money_units(actual, code)
        if units is None:
            return _render_actual(actual)
        return None if units == _money_text(cast(Money, expected)) else _format_units(units, code)
    if kind == "exact":  # DG-AK-52: the full-precision value rounded half up to d places
        text = str(expected)
        value = _number(actual)
        if value is None:
            return _render_actual(actual)
        places = len(text.partition(".")[2])
        matches = round_half_up(value, places) == int(text.replace(".", ""))
        return None if matches else format_exact(value)
    if kind == "integer":
        whole = isinstance(actual, int) and not isinstance(actual, bool)
        return None if whole and str(actual) == str(expected) else _render_actual(actual)
    if kind == "boolean":
        return None if actual is expected else _render_actual(actual)
    rendered = _render_actual(actual)  # DG-AK-53: equality
    return None if rendered == _render_expected(expected) else rendered


def _largest_remainder(total: int, weights: Sequence[Decimal]) -> list[int]:
    """``total`` minor units apportioned over ``weights`` by largest remainder, ties in line order;
    equal weights when every weight is 0 (L5-3-Q-19)."""
    if not weights:
        return []
    basis = (
        [Fraction(w) for w in weights]
        if any(w != 0 for w in weights)
        else [Fraction(1)] * len(weights)
    )
    whole = sum(basis, Fraction(0))
    magnitude, sign = abs(total), (-1 if total < 0 else 1)
    exact = [magnitude * w / whole for w in basis]
    shares = [int(value) for value in exact]  # floor: every value is non-negative
    left = magnitude - sum(shares)
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] - shares[i]), i))
    for index in order[:left]:
        shares[index] += 1
    return [sign * share for share in shares]


def _catch_up_alias(columns: Mapping[str, object]) -> object:
    """D-87 L6-5-Q-27: ``catch_up_tp_change_cum`` + ``catch_up_estimate_cum`` of an obligation row
    (S09-R-36 sums a variable consideration change into the first); the estimate column alone when
    either is not an amount."""
    estimate, tp_change = columns.get(CATCH_UP_ESTIMATE), columns.get(CATCH_UP_TP_CHANGE)
    amounts = [
        value
        for value in (estimate, tp_change)
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    return sum(amounts) if len(amounts) == 2 else estimate


def _render_mapping(mapping: Mapping[str, str]) -> str:
    return ", ".join(f"{name}: {value}" for name, value in sorted(mapping.items()))


def _render_net(value: Fraction, currency: str | None) -> str:
    return (
        f"dr {_format_units(value, currency)}"
        if value >= 0
        else f"cr {_format_units(-value, currency)}"
    )


def _decode_component(component: str) -> str:
    return _SUBJECT_ESCAPE.sub(lambda match: _SUBJECT_DECODED[match.group(1)], component)


def _subject_parts(subject_key: str) -> tuple[str, str | None]:
    """The leading (contract or group) component of a CV-21 subject key and its obligation key."""
    head, slash, rest = subject_key.partition("/")
    if slash:
        obligation = rest.partition("#")[0]
        return _decode_component(head), None if "/" in obligation else _decode_component(obligation)
    return _decode_component(subject_key.partition("@")[0]), None


def _line_obligation(intent: PostingIntent, line: IntentLine) -> str | None:
    return line.dimensions.get("obligation_key") or _subject_parts(intent.subject_key)[1]


def _source_contracts(kind: str, source: Sequence[str]) -> tuple[str, ...] | None:
    """The contracts the source of a stage 10 refund component names, decoded, else None when the
    source does not match the grammar of its kind (D-90; refund_liability.py).

    ``source`` is the encoded source split on ``/``; every part is one encoded component:
    - ``RETURN``: the obligation subject key ``<contract>/<obligation>`` (``_key`` over
      ``ob.subject_key``);
    - ``VARIABLE_CONSIDERATION``: the estimate key ``<contract>/<element>``;
    - ``TERMINATION``: the global event key ``<contract>/EV-<n>`` (CV-22);
    - ``CONCESSION``: ``<event key>/<subject key>`` (``_concessions``), the event key
      ``<contract>/EV-<n>`` then the obligation subject key ``<contract>/<obligation>`` or
      ``<contract>@<entity>``; it names both contracts.
    ``UNCLAIMED_PROPERTY`` has no producer (ENC-8, post-rc) and any other kind has no grammar.
    """
    if not source or not all(_ENCODED_COMPONENT.fullmatch(part) for part in source[:-1]):
        return None
    last = source[-1]
    if kind in (RETURN_COMPONENT, VC_COMPONENT) and len(source) == 2:
        return (_decode_component(source[0]),) if _ENCODED_COMPONENT.fullmatch(last) else None
    event_named = len(source) >= 2 and _EVENT_SERIAL.fullmatch(source[1]) is not None
    if kind == TERMINATION_COMPONENT and len(source) == 2 and event_named:
        return (_decode_component(source[0]),)
    if kind != CONCESSION_COMPONENT or not event_named:
        return None
    if len(source) == 4 and _ENCODED_COMPONENT.fullmatch(last):
        return _decode_component(source[0]), _decode_component(source[2])
    contract, at, entity = last.partition("@")
    if len(source) == 3 and at and all(_ENCODED_COMPONENT.fullmatch(p) for p in (contract, entity)):
        return _decode_component(source[0]), _decode_component(contract)
    return None


def _named_contracts(
    subject_key: str, group_key: str, members: Collection[str]
) -> tuple[str, ...] | None:
    """The contracts a posting intent's subject key names, decoded, else None when a refund
    component key does not match its grammar (D-90).

    CV-21 ``<contract>/<…>`` (obligation, estimate element, cost asset, recognition component)
    names its leading component. ``<name>@<entity>`` names ``<name>`` unless it is the group code
    and no member (group and entity). A stage 10 refund component key
    ``<group>@<entity>/<KIND>/<source>`` (refund_liability.py ``_key``; L2-4-Q-15) names every
    contract its source names (``_source_contracts``), and its head when that is not the group
    code; a key whose head or source breaks the grammar names nothing attributable. Delimiters
    split the encoded key before any component is decoded.
    """
    head, slash, rest = subject_key.partition("/")
    encoded_name, at, entity = head.partition("#")[0].partition("@")
    name = _decode_component(encoded_name)
    if slash and not at:
        return (name,)
    if slash:
        if head != f"{encoded_name}@{entity}" or not all(
            _ENCODED_COMPONENT.fullmatch(part) for part in (encoded_name, entity)
        ):
            return None  # the head is not `<group>@<entity>`
        kind, _, source = rest.partition("/")
        from_source = _source_contracts(kind, source.split("/"))
        if from_source is None:
            return None
        return from_source if name == group_key else (name, *from_source)
    return () if name == group_key and name not in members else (name,)


def _intent_contract(intent: PostingIntent, group_key: str, members: Collection[str]) -> str | None:
    """The member contract a posting intent posts for, else None (D-90; §9.5.6 `contract`).

    The intent belongs to the ``contract_key`` its lines carry: the member-contract dimension that
    ``erev_engine/stages/s14_posting/intents.py`` ``_dimensions`` sets beside the S14-R-13
    dimensions. Attribution fails closed: every line carries the same value, the value is a member
    of the intent's combination group, the subject key matches its grammar, and no contract its
    subject key or component source names differs from it.
    """
    owners = {line.dimensions.get("contract_key") for line in intent.lines}
    if len(owners) != 1:
        return None  # the lines disagree, or only some carry the dimension
    (owner,) = owners
    if owner is None or owner not in members:
        return None
    named = _named_contracts(intent.subject_key, group_key, members)
    if named is None or any(item != owner for item in named):
        return None
    return owner


def _grain(
    grain: str,
    *,
    with_kind: bool,
    role: str,
    purpose: str | None,
    account: str | None,
    obligation: str | None,
    origin: str | None,
    counterparty: str | None,
    entry_kind: str | None,
) -> GrainKey:
    """DG-AK-56: the members a subledger block sums over."""
    return (
        role,
        purpose,
        account if grain != "role" else None,
        obligation if grain == "role_account_obligation" else None,
        origin,
        counterparty,
        entry_kind if with_kind else None,
    )


def _render_grain(grain: GrainKey) -> str:
    return "/".join(part for part in grain if part)


_RPO_STATUSES: Final = frozenset({"UNSATISFIED", "PARTIALLY_SATISFIED"})  # P7
# Estimate kinds no stage 03 to 06 reads: stage 08 pins them as measures, stage 09 books their
# change as CATCH_UP and stage 11 reads the EAC costs, so their versions start no allocation
# segment (L7-6).
_SEGMENT_NEUTRAL_KINDS: Final = frozenset({"EAC"})


def _starts_no_segment(bundle: InputBundle, event: EventInput) -> bool:
    """True for an ``ESTIMATE_CHANGED`` whose pinned version is of a segment-neutral kind (L7-6)."""
    if event.event_type != "ESTIMATE_CHANGED":
        return False
    version_key = event.payload.get("estimate_version_id")
    return any(
        version.version_key == version_key and version.estimate_kind in _SEGMENT_NEUTRAL_KINDS
        for version in bundle.estimate_versions
    )


_REDUCE_SCOPE: Final = "REDUCE_CONTRACT_QUANTITY"  # POL-053


def _returns_reduction(node: object, minor_unit: int) -> int | None:
    """round(r × (Y + E)) of a ``returns.revenue_target.v1`` node under REDUCE (S09-R-23)."""
    params = getattr(node, "params", None)
    if not isinstance(params, Mapping) or params.get("scope") != _REDUCE_SCOPE:
        return None
    units = Fraction(str(params["returned"])) + Fraction(str(params["expected"]))
    return round_half_up(Fraction(str(params["unit_rate"])) * units, minor_unit)


def _returns_shift(
    nodes: Mapping[str, object], subject_key: str, period_key: str, minor_unit: int
) -> int:
    """The change of the returns reduction from d_v to the period end at `as_of`.

    The version memo is −Σ round(r × (Y + E)) and the obligation's ``allocated_amount`` nets the
    same reduction (S04-R-08, S09-R-23). E moves without an event at window expiry (S09-R-26), so
    the price and the allocation at `as_of` move by the change between the stage 09 nodes
    ``revenue_target_exact:<ob>#FIXED:-`` and ``…:<period>`` (EX-04-G2; L5-3-Q-1).
    """
    at_version = _returns_reduction(
        nodes.get(f"revenue_target_exact:{subject_key}#FIXED:-"), minor_unit
    )
    at_period = _returns_reduction(
        nodes.get(f"revenue_target_exact:{subject_key}#FIXED:{period_key}"), minor_unit
    )
    if at_version is None or at_period is None:
        return 0
    return at_period - at_version


@dataclass(frozen=True, slots=True)
class _ToDate:
    """The version and obligation columns a checkpoint compares at `as_of` (API-C-10)."""

    version: Mapping[str, object]
    obligations: Mapping[str, Mapping[str, object]]  # overlaid obligations only, by subject key


@dataclass(slots=True)
class _Net:
    txn: Fraction = Fraction(0)
    functional: Fraction = Fraction(0)
    txn_currency: str | None = None
    functional_currency: str | None = None


# --- Comparison of one checkpoint ----------------------------------------------------------------


class _CheckpointComparison:
    """The mismatches of one checkpoint against its run.

    The engine emits one version per computation, so version, obligation, schedule, proposal and
    trace values compare as emitted. Labelled balances are those of the period containing `as_of`
    in the entity calendar; a subledger block compares the entries of its own period from the
    checkpoint's outputs, whatever `as_of` (D-88 L7-5-Q-12 (b); the §9.5.6 editorial amendment is
    post-rc).
    """

    def __init__(
        self,
        key: AnswerKey,
        checkpoint: Checkpoint,
        run: CheckpointRun,
        steps: Sequence[StepOutcome] = (),
        range_findings: Sequence[range_validation.RangeFinding] = (),
    ) -> None:
        self.key = key
        self.checkpoint = checkpoint
        self.steps = tuple(steps)  # expect_problem steps at or before `after_seq`
        self.range_findings = tuple(range_findings)  # DG-AK-45 findings of the world
        self.as_of = date.fromisoformat(checkpoint.as_of)
        self.contracts = {contract.external_id: contract for contract in key.contracts}
        self.functional = {entity.code: entity.functional_currency for entity in key.world.entities}
        self.outputs = tuple(zip(run.checkpoint.bundles, run.outputs, strict=True))
        self.found: list[Mismatch] = []
        self.periods: dict[str, tuple[PeriodInput, ...]] = {}
        self.books: dict[str, BookOutput] = {}  # member contract key -> checkpoint book
        self._to_date: dict[int, _ToDate] = {}  # id(book) -> to-date columns at `as_of`
        # The checkpoint book of every group with the group (D-90), then of every close-pass
        # output: pass intents join the subledger (§9.5.6).
        self.group_books: list[tuple[GroupInput, BookOutput]] = []
        for bundle, output in self.outputs:
            for entity in bundle.entities:
                self.periods.setdefault(entity.code, entity.periods)
            book = next((item for item in output.books if item.book_code == checkpoint.book), None)
            if book is not None:
                self.group_books.append((bundle.group, book))
                self.books.update((member, book) for member in bundle.group.member_contract_keys)
        self.pass_outputs = tuple(
            zip(run.checkpoint.bundles, run.passes, strict=True) if run.passes else ()
        )
        self.group_books.extend(
            (bundle.group, book)
            for bundle, outputs in self.pass_outputs
            for output in outputs
            for book in output.books
            if book.book_code == checkpoint.book
        )
        # (period, entity, contract, entry key) of every unattributed intent reported (D-90).
        self.unattributed: set[tuple[str, str, str, str]] = set()

    def add(self, subject: str, field: str, expected: str, actual: str) -> None:
        self.found.append(
            Mismatch(self.key.id, self.checkpoint.name, subject, field, expected, actual)
        )

    def compare(
        self,
        subject: str,
        field: str,
        kind: str,
        expected: object,
        actual: object,
        currency: str | None = None,
    ) -> None:
        """DG-AK-53: absent expectations are not asserted."""
        if expected is None:
            return
        differs = _differs(kind, expected, actual, currency)
        if differs is not None:
            self.add(subject, field, _render_expected(expected), differs)

    def mismatches(self) -> list[Mismatch]:
        for bundle, output in self.outputs:
            self.books_computed(bundle, output)
            for book in output.books:
                self.identities(bundle, book)
        for bundle, outputs in self.pass_outputs:
            for output in outputs:
                for book in output.books:  # D-16 and reevaluate(trace) of the pass (DG-AK-54)
                    self.identities(bundle, replace(book, contract_version=None))
        for block in self.checkpoint.contracts or ():
            self.contract(block)
        for subledger in self.checkpoint.subledger or ():
            self.subledger(subledger)
        for group in self.checkpoint.groups or ():
            self.group(group)
        if self.checkpoint.exceptions is not None:
            self.exceptions(self.checkpoint.exceptions)
        return self.found

    def period_of(self, entity: str) -> str | None:
        """The period of the entity calendar that contains ``as_of``."""
        periods = self.periods.get(entity, ())
        return next(
            (p.period_key for p in periods if p.start_date <= self.as_of <= p.end_date), None
        )

    def books_computed(self, bundle: InputBundle, output: OutputBundle) -> None:
        """RCP-11, ENGINE_SPEC §0.5: a ``BookOutput`` per ``BookInput``, and a contract version in
        every book except LEGACY (D-79)."""
        group = bundle.group.group_key
        computed = {book.book_code for book in output.books}
        for book_input in bundle.books:
            if book_input.book_code not in computed:
                self.add(f"book {book_input.book_code}", "computed", f"group {group}", ABSENT)
        for book in output.books:
            if book.book_code != LEGACY_BOOK and book.contract_version is None:
                self.add(
                    f"group {group} book {book.book_code}", "contract_version", "computed", ABSENT
                )

    # DG-AK-54

    def identities(self, bundle: InputBundle, book: BookOutput) -> None:
        group = bundle.group.group_key
        currency = bundle.group.transaction_currency
        subject = f"group {group} book {book.book_code}"
        if book.contract_version is not None:
            columns = book.contract_version.columns
            allocated: list[tuple[ObligationVersionOut, Fraction]] = []
            for obligation in book.obligation_versions:
                units = _money_units(obligation.columns.get("allocated_amount"), currency)
                if units is None:
                    where = f"obligation {obligation.subject_key}"
                    self.add(where, "allocated_amount", "computed", ABSENT)
                else:
                    allocated.append((obligation, units))
            total = sum((units for _, units in allocated), Fraction(0))
            # Σ a_posted = Σ allocated_amount − expected_returns_amount (S04-R-02; D-79), against
            # the basis of the latest boundary that traced a price, else the version-state node
            # (CV-50; L5-3-Q-2).
            nodes = {n.id: n for n in book.trace.nodes}
            group_component = subject_component(group)
            node = nodes.get(f"{ALLOCATION_BASIS_MEASURE}:{group_component}:-")
            for event in bundle.events:
                boundary = nodes.get(
                    f"{ALLOCATION_BASIS_MEASURE}@{event.event_key}:{group_component}:-"
                )
                if boundary is not None:
                    node = boundary
            basis = _number(node.value) if node is not None else None
            returns = _money_units(columns.get("expected_returns_amount"), currency)
            posted = None if returns is None else total - returns
            if basis is None or posted is None or basis != posted:
                expected = ABSENT if basis is None else _format_units(basis, currency)
                actual = ABSENT if posted is None else _format_units(posted, currency)
                self.add(subject, IDENTITY_BASIS, expected, actual)
            price = _money_units(columns.get("transaction_price"), currency)
            payable = _money_units(columns.get("consideration_payable_amount"), currency)
            # DB-17 V1 sums the IN_SCOPE_606 rows: routed-out lease rows leave the price (D-88
            # L7-5-Q-6); a row without the column takes the T-CON-11 default IN_SCOPE_606.
            in_scope = sum(
                (
                    units
                    for obligation, units in allocated
                    if obligation.columns.get("scope_flag", "IN_SCOPE_606") == "IN_SCOPE_606"
                ),
                Fraction(0),
            )
            if price is None or payable is None or price - payable != in_scope:
                expected = (
                    ABSENT
                    if price is None or payable is None
                    else _format_units(price - payable, currency)
                )
                self.add(subject, IDENTITY_PRICE, expected, _format_units(in_scope, currency))
            for obligation, units in allocated:
                parts = [
                    _money_units(obligation.columns.get(name), currency)
                    for name in _REMAINDER_PARTS
                ]
                remainder = None if None in parts else sum(cast(list[Fraction], parts), Fraction(0))
                if remainder != units:
                    actual = ABSENT if remainder is None else _format_units(remainder, currency)
                    where = f"obligation {obligation.subject_key}"
                    self.add(where, IDENTITY_OBLIGATION, _format_units(units, currency), actual)
        # D-16: entries balance per (entity, book, currency, period) in both measures.
        sides: dict[tuple[str, str, str, str], list[int]] = {}
        for intent in book.posting_intents:
            for line in intent.lines:
                for measure, code, amount in (
                    ("transaction", line.txn_currency, line.amount_txn),
                    ("functional", line.functional_currency, line.amount_functional),
                ):
                    totals = sides.setdefault(
                        (measure, intent.entity, code, intent.posting_period_key), [0, 0]
                    )
                    totals[0 if line.side == "D" else 1] += amount
        for (measure, entity, code, period), (debits, credits) in sorted(sides.items()):
            if debits != credits:
                unit = _minor_unit(code)
                self.add(
                    f"journal {entity} {book.book_code} {code} {period}",
                    f"DG-AK-54 debits = credits ({measure})",
                    format_money(debits, unit),
                    format_money(credits, unit),
                )
        try:
            values = reevaluate(book.trace)
        except Exception as error:  # a trace that cannot be re-evaluated is a mismatch (DG-AK-55)
            actual = f"{type(error).__name__}: {error}"
            self.add(f"trace {subject}", IDENTITY_TRACE, "every node reproduced", actual)
            return
        for node in book.trace.nodes:
            if values.get(node.id) != node.value:
                where = f"trace {node.id} book {book.book_code}"
                self.add(where, IDENTITY_TRACE, node.value, values.get(node.id, ABSENT))

    # Contract blocks

    def contract(self, block: ContractBlock) -> None:
        handle = block.contract
        subject = f"contract {handle}"
        book = self.books.get(handle)
        if book is None:
            self.add(subject, "computed", f"book {self.checkpoint.book}", ABSENT)
            return
        currency = self.contracts[handle].transaction_currency
        statuses = dict(book.status_in_book)
        self.compare(subject, "status_in_book", "text", block.status_in_book, statuses.get(handle))
        to_date = self.to_date(book, currency)
        if block.version is not None:
            columns = to_date.version
            types = contract_version_columns()
            for name in VersionBlock.model_fields:
                kind = _kind(types.get(name, "text"))
                expected = getattr(block.version, name)
                self.compare(subject, name, kind, expected, columns.get(name), currency)
        versions = {version.subject_key: version for version in book.obligation_versions}
        types = obligation_columns()
        for row in block.obligations or ():
            obligation_key = str(row["obligation_key"])
            where = f"obligation {handle}/{obligation_key}"
            version = versions.get(obligation_subject_key(handle, obligation_key))
            if version is None:
                self.add(where, "obligation_version", "computed", ABSENT)
                continue
            columns = to_date.obligations.get(version.subject_key, version.columns)
            for name, expected in row.items():
                if name != "obligation_key":
                    kind = _kind(types.get(name, "text"))
                    actual = columns.get(name)
                    if name == CATCH_UP_ESTIMATE and CATCH_UP_TP_CHANGE not in row:
                        actual = _catch_up_alias(columns)  # L6-5-Q-27
                    self.compare(where, name, kind, expected, actual, currency)
        for balance in block.balances or ():
            self.balance(f"balance {handle}@{balance.entity}", (handle,), balance, currency)
        self.schedule(block, book, currency)
        self.modifications(block, book)
        self.trace(block, book)

    def to_date(self, book: BookOutput, currency: str) -> _ToDate:
        """API-C-10: to-date measures include activity with effective date ≤ `as_of`.

        The engine emits the version at d_v, its latest included effective date (Table 0.9-A).
        When `as_of` is the end of a later period of the performing entity's calendar, no event
        separates d_v from `as_of`, so the stage 09 period nodes ``revenue_cum:<ob>:<period>`` and
        ``progress_ratio:<ob>:<period>`` give the obligation at `as_of` (ENGINE_SPEC_B §9 trace
        table). With Δ = C(as_of) − C(d_v): ``remaining_allocation`` and ``scheduled_amount`` fall
        by Δ (the segment in force is unchanged), ``satisfaction_status`` follows S09-R-46, and the
        version's ``revenue_cum`` and ``scheduled_amount`` move by ΣΔ. ``rpo_amount`` keeps the
        stage 15 inclusion of each obligation (``disc.rpo.v1`` param ``included``) and drops an
        obligation that is satisfied at `as_of` (P7). An `as_of` before d_v reads the same nodes
        when no boundary event of the bundle is effective after `as_of`, so the segment in force at
        `as_of` is the one emitted (a checkpoint that knows later invoices; L5-3-Q-11). An
        ``ESTIMATE_CHANGED`` that pins an ``EAC`` version starts no allocation segment, so it does
        not count as such an event (L7-6; COST-S8-CONTRACT-COSTS-IMPAIRMENT). Any other `as_of`
        compares as emitted (L4-3-Q-10)."""
        cached = self._to_date.get(id(book))
        if cached is not None:
            return cached
        version = dict(book.contract_version.columns) if book.contract_version is not None else {}
        nodes = {node.id: node for node in book.trace.nodes}
        scale = 10 ** _minor_unit(currency)
        obligations: dict[str, Mapping[str, object]] = {}
        moved = 0
        rpo_moved = 0
        returns_moved = 0
        bundle = next(
            (item for item, output in self.outputs if any(found is book for found in output.books)),
            None,
        )
        boundary_after = bundle is None or any(
            event.event_type in BOUNDARY_EVENT_TYPES
            and event.effective_date > self.as_of
            and not _starts_no_segment(bundle, event)
            for event in bundle.events
        )
        for ob in book.obligation_versions:
            columns = ob.columns
            d_v = columns.get("effective_date")
            entity = columns.get("performing_entity_code")
            revenue = columns.get("revenue_cum")
            if not isinstance(d_v, date) or not isinstance(revenue, int):
                continue
            if self.as_of <= d_v and boundary_after:
                continue
            period = next(
                (p for p in self.periods.get(str(entity), ()) if p.end_date == self.as_of), None
            )
            node = (
                None
                if period is None
                else nodes.get(f"revenue_cum:{ob.subject_key}:{period.period_key}")
            )
            if period is None or node is None:
                continue
            at = Fraction(Decimal(node.value)) * scale
            if at.denominator != 1:
                continue
            delta = at.numerator - revenue
            overlay = dict(columns)
            overlay["revenue_cum"] = at.numerator
            for name in ("remaining_allocation", "scheduled_amount"):
                value = columns.get(name)
                if isinstance(value, int) and not isinstance(value, bool):
                    overlay[name] = value - delta
            progress_node = nodes.get(f"progress_ratio:{ob.subject_key}:{period.period_key}")
            progress = (
                columns.get("progress_ratio")
                if progress_node is None
                else Fraction(Decimal(progress_node.value))
            )
            overlay["progress_ratio"] = progress
            status = columns.get("satisfaction_status")
            if status != "CANCELLED":
                if progress == 1:
                    status = "SATISFIED"
                elif at.numerator == 0 and progress == 0:
                    status = "UNSATISFIED"
                else:
                    status = "PARTIALLY_SATISFIED"
                overlay["satisfaction_status"] = status
            rpo = nodes.get(f"rpo_amount:{ob.subject_key}:-")
            if rpo is not None and rpo.params.get("included") == "true":
                before = Fraction(Decimal(rpo.value)) * scale
                after = before - delta if status in _RPO_STATUSES else Fraction(0)
                rpo_moved += int(before - after)
            shift = _returns_shift(nodes, ob.subject_key, period.period_key, _minor_unit(currency))
            for name in ("allocated_amount", "remaining_allocation"):
                value = overlay.get(name)
                if shift and isinstance(value, int) and not isinstance(value, bool):
                    overlay[name] = value - shift
            returns_moved += shift
            obligations[ob.subject_key] = MappingProxyType(overlay)
            moved += delta
        # billed_cum at `as_of`: the stage 10 node of the contracting entity's period ending on
        # `as_of` counts the billing effective on or before it (API-C-10; ENGINE_SPEC_B §10.5).
        # It applies before d_v too, when the checkpoint knows invoices effective after `as_of`
        # (SFC-CHK-137 instalments; L5-3-Q-11).
        billed_moved = 0
        for ob in book.obligation_versions:
            billed = ob.columns.get("billed_cum")
            entity = ob.columns.get("contracting_entity_code")
            period = next(
                (p for p in self.periods.get(str(entity), ()) if p.end_date == self.as_of), None
            )
            node = (
                None
                if period is None
                else nodes.get(f"billed_cum:{ob.subject_key}:{period.period_key}")
            )
            if node is None or not isinstance(billed, int) or isinstance(billed, bool):
                continue
            at = Fraction(Decimal(node.value)) * scale
            if at.denominator != 1 or at.numerator == billed:
                continue
            overlay = dict(obligations.get(ob.subject_key, ob.columns))
            overlay["billed_cum"] = at.numerator
            obligations[ob.subject_key] = MappingProxyType(overlay)
            billed_moved += at.numerator - billed
        for name, change in (
            ("revenue_cum", moved),
            ("billed_cum", billed_moved),
            ("scheduled_amount", -moved),
            ("rpo_amount", -rpo_moved),
            ("expected_returns_amount", -returns_moved),
            ("transaction_price", -returns_moved),
        ):
            value = version.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                version[name] = value + change
        result = _ToDate(MappingProxyType(version), MappingProxyType(obligations))
        self._to_date[id(book)] = result
        return result

    def balance(self, subject: str, members: Sequence[str], row: BalanceRow, currency: str) -> None:
        """API-S-ContractBalance fields against T-CON-09 `<field>_txn` and `<field>_functional`."""
        period = self.period_of(row.entity)
        where = f"{subject} {period or ABSENT}"
        functional = self.functional.get(row.entity)
        # S10-INV-08: an entity that only performs obligations of the members holds no balance, so
        # its absent T-CON-09 row reads as zero balances (ALG-07 step 3; L6-5).
        zero = 0 if self.performing_only(members, row.entity) else None
        for name in BalanceAmounts.model_fields:
            actual = self.member_total(members, row.entity, period, f"{name}_txn")
            actual = zero if actual is None else actual
            self.compare(where, name, "money", getattr(row, name), actual, currency)
            if row.functional is not None:
                expected = getattr(row.functional, name)
                actual = self.member_total(members, row.entity, period, f"{name}_functional")
                actual = zero if actual is None else actual
                self.compare(where, f"functional.{name}", "money", expected, actual, functional)

    def performing_only(self, members: Sequence[str], entity: str) -> bool:
        """``entity`` performs a line of a member contract (``performing_entity_code``) and is the
        contracting entity of none (S10-INV-08)."""
        contracts = [self.contracts[member] for member in members if member in self.contracts]
        if any(contract.contracting_entity == entity for contract in contracts):
            return False
        return any(
            getattr(line, "performing_entity_code", None) == entity
            for contract in contracts
            for line in (
                *contract.lines,
                *(line for mod in contract.modifications or () for line in mod.lines),
            )
        )

    def member_total(
        self, members: Sequence[str], entity: str, period: str | None, column: str
    ) -> int | None:
        """DG-AK-57: the sum of the members' T-CON-09 column for the entity and period."""
        total: int | None = None
        for member in members:
            book = self.books.get(member)
            subject_key = f"{subject_component(member)}@{subject_component(entity)}"
            for balance in book.balances if book is not None else ():
                value = balance.columns.get(column)
                if (
                    balance.subject_key == subject_key
                    and balance.period_key == period
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                ):
                    total = (total or 0) + value
        return total

    def schedule(self, block: ContractBlock, book: BookOutput, currency: str) -> None:
        handle = block.contract
        for row in block.schedule or ():
            if row.obligation_key is not None:
                subject_key = obligation_subject_key(handle, row.obligation_key)
                label = row.obligation_key
            else:
                cost_asset = str(row.cost_asset)
                subject_key = f"{subject_component(handle)}/COST/{subject_component(cost_asset)}"
                label = f"COST/{cost_asset}"
            lines = {
                line.period_key: line
                for line in book.schedules
                if line.subject_key == subject_key
                and line.schedule_kind == row.schedule_kind
                and line.line_type == row.line_type
            }
            where = f"schedule {handle}/{label} {row.schedule_kind} {row.line_type}"
            if row.amounts is not None:
                for period_key, amount in row.amounts.items():
                    line = lines.get(period_key)
                    # S09-R-48: the engine emits the complete set but no zero amount, so a period
                    # of the map without a line holds 0.
                    actual = line.amount if line is not None else 0
                    self.compare(
                        f"{where} {period_key}", "amount", "money", amount, actual, currency
                    )
                continue
            line = lines.get(str(row.period_key))
            at = f"{where} {row.period_key}"
            if line is None:
                self.add(at, "amount", _render_expected(row.amount), ABSENT)
                continue
            self.compare(at, "amount", "money", row.amount, line.amount, currency)
            self.compare(
                at,
                "cumulative_amount",
                "money",
                row.cumulative_amount,
                line.cumulative_amount,
                currency,
            )
            self.compare(at, "quantity", "exact", row.quantity, line.quantity)

    def modifications(self, block: ContractBlock, book: BookOutput) -> None:
        """CV-16 proposals of kind ``MODIFICATION_TREATMENT``. The engine keys each by the contract
        subject, with ``detail.modification_key``; the listed obligations are compared, and an
        obligation the key does not list is not asserted (DG-AK-53; L5-3-Q-18)."""
        subject = subject_component(block.contract)
        proposals = {
            p.detail.get("modification_key"): p
            for p in book.proposals
            if p.kind == MODIFICATION_PROPOSAL and p.subject_key == subject
        }
        for expected in block.modifications or ():
            where = f"modification {block.contract}/{expected.reference}"
            proposal = proposals.get(expected.reference)
            wanted = _render_mapping(expected.proposed_treatments)
            actual = ABSENT
            if proposal is not None:
                treatments = proposal.treatments
                listed = {key: treatments.get(key, ABSENT) for key in expected.proposed_treatments}
                actual = _render_mapping(listed)
            if wanted != actual:
                self.add(where, "proposed_treatments", wanted, actual)
            summary = proposal.summary if proposal is not None else None
            self.compare(where, "treatment_summary", "text", expected.treatment_summary, summary)

    def trace(self, block: ContractBlock, book: BookOutput) -> None:
        handle = block.contract
        contract = self.contracts[handle]
        obligations = {line.obligation_key for line in contract.lines}
        for modification in contract.modifications or ():
            obligations.update(line.obligation_key for line in modification.lines)
        nodes = {node.id: node for node in book.trace.nodes}
        for assertion in block.trace or ():
            subject_key = assertion.subject_key
            if subject_key in obligations:
                subject_key = obligation_subject_key(handle, subject_key)
            node_id = f"{assertion.measure}:{subject_key}:{assertion.period_key or '-'}"
            node = nodes.get(node_id)
            where = f"trace {node_id}"
            value = node.value if node is not None else None
            self.compare(where, "value", "exact", assertion.value, value)
            formula = node.formula_id if node is not None else None
            self.compare(where, "formula_id", "text", assertion.formula_id, formula)

    # Subledger, groups and exceptions

    def subledger(self, block: SubledgerBlock) -> None:
        where = f"subledger {block.period_key} {block.entity}"
        if block.contract is not None:
            where += f" {block.contract}"
        with_kind = bool(block.lines) and all(line.entry_kind is not None for line in block.lines)
        intents, unattributed = self.block_intents(block)
        for intent in unattributed:  # D-90: reported once, never dropped silently
            reported = (block.period_key, block.entity, str(block.contract), intent.entry_key)
            if reported not in self.unattributed:
                self.unattributed.add(reported)
                subject = f"{where} entry {intent.entry_key} {intent.subject_key}"
                self.add(subject, "contract", str(block.contract), UNATTRIBUTED)
        actual = self.net(block, intents, with_kind)
        listed: set[GrainKey] = set()
        for line in block.lines:
            grain = _grain(
                block.grain,
                with_kind=with_kind,
                role=line.account_role,
                purpose=line.clearing_purpose,
                account=line.account,
                obligation=line.obligation_key,
                origin=line.origin_period_key,
                counterparty=line.counterparty_entity,
                entry_kind=line.entry_kind,
            )
            listed.add(grain)
            label = f"{where} {_render_grain(grain)}"
            side, amount = ("dr", line.dr) if line.dr is not None else ("cr", line.cr)
            net = actual.get(grain)
            if net is None:
                self.add(label, side, _render_expected(amount), ABSENT)
                continue
            if _money_text(line.dr) - _money_text(line.cr) != net.txn:
                self.add(
                    label, side, _render_expected(amount), _render_net(net.txn, net.txn_currency)
                )
            if line.functional_dr is not None or line.functional_cr is not None:
                functional = (
                    line.functional_dr if line.functional_dr is not None else line.functional_cr
                )
                name = "functional_dr" if line.functional_dr is not None else "functional_cr"
                if (
                    _money_text(line.functional_dr) - _money_text(line.functional_cr)
                    != net.functional
                ):
                    rendered = _render_net(net.functional, net.functional_currency)
                    self.add(label, name, _render_expected(functional), rendered)
        if block.match == "exact":
            for grain, net in sorted(actual.items(), key=lambda item: _render_grain(item[0])):
                if grain not in listed:
                    rendered = (
                        f"{_render_net(net.txn, net.txn_currency)}; "
                        f"functional {_render_net(net.functional, net.functional_currency)}"
                    )
                    self.add(f"{where} {_render_grain(grain)}", "line", ABSENT, rendered)

    def aggregate(self, block: SubledgerBlock, with_kind: bool) -> dict[GrainKey, _Net]:
        """DG-AK-56: the non-zero net amounts per grain key of the block's period and entity.

        D-88 L7-5-Q-12 (b): the block compares the entries of its own ``period_key`` from the
        checkpoint's outputs, whatever ``as_of``; ``as_of`` still selects the labelled balances.
        Records no mismatch: ``subledger()`` reports the intents a contract filter cannot attribute.
        """
        return self.net(block, self.block_intents(block)[0], with_kind)

    def block_intents(
        self, block: SubledgerBlock
    ) -> tuple[list[PostingIntent], list[PostingIntent]]:
        """The posting intents of the block's period and entity, and those it cannot attribute.

        Without ``contract`` every intent of the checkpoint books counts. With ``contract`` (D-90;
        §9.5.6), only the books of the contract's combination group are read, and an intent counts
        when ``_intent_contract`` attributes it to that contract; an intent it cannot attribute is
        returned apart.
        """
        periods = self.periods.get(block.entity, ())
        if not any(p.period_key == block.period_key for p in periods):
            return [], []
        intents: list[PostingIntent] = []
        unattributed: list[PostingIntent] = []
        for group, book in self.group_books:
            members = group.member_contract_keys
            if block.contract is not None and block.contract not in members:
                continue
            for intent in book.posting_intents:
                if intent.entity != block.entity or intent.posting_period_key != block.period_key:
                    continue
                if block.contract is None:
                    intents.append(intent)
                    continue
                owner = _intent_contract(intent, group.group_key, members)
                if owner is None:
                    unattributed.append(intent)
                elif owner == block.contract:
                    intents.append(intent)
        return intents, unattributed

    def net(
        self, block: SubledgerBlock, intents: Sequence[PostingIntent], with_kind: bool
    ) -> dict[GrainKey, _Net]:
        """DG-AK-56: the non-zero net amounts of ``intents`` per grain key of the block."""
        totals: dict[GrainKey, _Net] = {}
        for intent in intents:
            for line in intent.lines:
                grain = _grain(
                    block.grain,
                    with_kind=with_kind,
                    role=line.account_role,
                    purpose=line.clearing_purpose,
                    account=line.account_code,
                    obligation=_line_obligation(intent, line),
                    origin=intent.origin_period_key,
                    counterparty=line.counterparty_entity,
                    entry_kind=intent.entry_kind,
                )
                net = totals.setdefault(grain, _Net())
                sign = 1 if line.side == "D" else -1
                net.txn += sign * Fraction(line.amount_txn, 10 ** _minor_unit(line.txn_currency))
                net.functional += sign * Fraction(
                    line.amount_functional, 10 ** _minor_unit(line.functional_currency)
                )
                net.txn_currency = line.txn_currency
                net.functional_currency = line.functional_currency
        return {grain: net for grain, net in totals.items() if net.txn or net.functional}

    def group(self, block: GroupBlock) -> None:
        members = sorted(
            c.external_id for c in self.key.contracts if c.combination_group == block.group
        )
        currency = self.contracts[members[0]].transaction_currency
        for row in block.balances:
            self.balance(f"group {block.group}@{row.entity}", members, row, currency)

    def exceptions(self, rows: Sequence[ExceptionRow]) -> None:
        """Exact set per listed code: each row matches one finding on code, severity and the
        members it names; leftovers on either side are mismatches. A row with ``subject`` matches
        a DG-AK-45 range finding on code, severity and subject."""
        listed = {row.code for row in rows}
        ranged = [
            (finding.code, finding.severity, finding.subject)
            for finding in self.range_findings
            if finding.code in listed
        ]
        findings: list[tuple[str, str, str | None, str | None]] = [
            (item.code, item.severity, *_subject_parts(item.subject_key))
            if item.subject_key
            else (item.code, item.severity, None, None)
            for _, output in self.outputs
            for item in output.diagnostics
            if item.code in listed and item.book_code in (None, self.checkpoint.book)
        ]
        findings += [
            finding
            for outcome in self.steps
            for finding in self.blocking_findings(outcome)
            if finding[0] in listed
        ]
        for row in rows:
            where = f"exception {row.code}"
            if row.subject is not None:
                expected = (row.code, row.severity, row.subject)
                if expected in ranged:
                    ranged.remove(expected)
                else:
                    self.add(f"{where} {row.subject}", "finding", " ".join(expected), ABSENT)
                continue
            match = next(
                (
                    finding
                    for finding in findings
                    if finding[:2] == (row.code, row.severity)
                    and row.contract in (None, finding[2])
                    and row.obligation_key in (None, finding[3])
                ),
                None,
            )
            parts = (row.code, row.severity, row.contract, row.obligation_key)
            if match is None:
                self.add(where, "finding", " ".join(p for p in parts if p), ABSENT)
            else:
                findings.remove(match)
        for finding in findings:
            self.add(
                f"exception {finding[0]}", "finding", ABSENT, " ".join(p for p in finding if p)
            )
        for code, severity, subject in ranged:
            self.add(
                f"exception {code} {subject}", "finding", ABSENT, f"{code} {severity} {subject}"
            )

    def blocking_findings(
        self, outcome: StepOutcome
    ) -> list[tuple[str, str, str | None, str | None]]:
        """The ``ERROR`` findings of a step's ``detail["findings"]`` (CV-15, CV-41; D-79)."""
        text = outcome.detail.get("findings")
        if text is None:
            return []
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if not isinstance(parsed, list) or not all(
            isinstance(finding, dict) and isinstance(finding.get("code"), str) for finding in parsed
        ):
            where = f"timeline seq {outcome.step.seq}"
            self.add(where, "findings", "canonical JSON of findings (CV-15)", text)
            return []
        rows: list[tuple[str, str, str | None, str | None]] = []
        for finding in parsed:
            if finding.get("severity") != "ERROR":
                continue
            subject = finding.get("subject_key")
            parts = (
                _subject_parts(subject) if isinstance(subject, str) and subject else (None, None)
            )
            rows.append((finding["code"], "ERROR", *parts))
        return rows

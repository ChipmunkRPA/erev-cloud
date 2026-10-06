"""RPT-05 ``revenue_from_prior_period_obligations`` Revenue from obligations satisfied in prior
periods (SCREENS_B §5.6.1 RPT-05 rev 1.12 and 1.16; ENGINE_SPEC_B §15.2.4 S15-R-13, S15-R-14,
§15.2.7 row ``PRIOR_PERIOD_POB_REVENUE`` rev 1.25, §15.5; 04 T-CLS-05 rev 1.40 and 1.51, E-64;
POLICIES POL-204, ALG-10 §2.11.3; 03 REQ-RPT-008; ASC 606-10-50-12A; D-98 candidates 85, 87, 96,
104; BUILD_SPEC RPS-3; Codex C4-PP-R1, C4-PP-R2).

One row per (performing entity, contract, obligation) — the §15.2.7 row key carried as the code
columns ``entity_code``, ``contract_external_id``, ``obligation_key`` — with the revenue of the
range attributable to performance satisfied before each period, split by cause.

Source (S15-R-14; SCREENS_B rev 1.16 reading rule): the range's ``REVENUE`` subledger lines
recorded by ``known_at`` name the contract versions whose traces are read. Per combination group
and period the latest recorded version (highest ``version_no``, ``known_at`` not after the run's
version cutoff) is read once, and every stage 08 node ``revenue_prior_period:<obligation>:<period>``
of that trace for the period is read — the contract's complete obligation population, every
performing entity, before any entity filter.

Identity ``PRIOR_PERIOD_ROWS_EQ_SUM_NODES`` (C4-PP-R1): stage 15 ``prior_period._sums`` emits
``revenue_prior_period_sum:<contract>@<CONTRACTING entity>:<period key>`` collecting the contract's
obligation nodes of that period key across every performing entity (S15-R-13;
``disc.prior_period_sum.v1``). The reader reconciles per (contract, period key): Σ of the obligation
nodes read = the sum node's value, and the sum node's inputs are exactly those nodes. It never seeks
a sum under a performing entity; a missing sum node, a value difference or an input set that
differs is refused by name (``RPT05_SUM_NODE_MISMATCH``). Only after the identity holds are the
rows restricted to the run's entity scope (a row's ``entity_code`` is the obligation's performing
entity), so ``prior_period_sum_total`` — Σ of the sum nodes read — equals ``revenue_total`` when
the scope covers every performing entity of the contracts read and differs from it by the signed
sum of the out-of-scope rows otherwise.

Cause columns: a node's boundary parts — its ``contract_event`` source references with
``rule_<k>`` / ``version_<k>`` params — and its late carries (``late_target_<k>`` −
``late_posted_<k>``): ``ESTIMATE_CHANGED`` on a reallocating version → ``from_price_changes``, on
a measure-only ``EAC`` version (``version_<k>`` present) → ``from_estimate_changes``;
``CONTRACT_AMENDED``, ``LINE_ATTRIBUTES_CHANGED`` and ``REGROUPED`` → ``from_modifications``;
carries → ``from_late_events``; terminations (``S09-R-06``, ``CONTRACT_TERMINATED``),
material-right exercises and CV-63 zero parts → ``from_other``. Σ of the cause columns =
``revenue`` = the node value; anything else is refused by name (``RPT05_NODE_SPLIT_MISMATCH``).
The event type behind a part is resolved from its CV-22 key ``<encoded external id>/EV-<n>``
(``domain/contracts/bundles._event_key``, the CV-21 ``contract_subject_key`` prefix) by matching
the ENCODED prefix against the candidate contracts' encoded external ids — never a raw id, never a
permissive decode (C4-PP-R2) — and the stream version against the stored ``contract_event``. The
candidates are the selected versions' HISTORICAL membership as of ``known_at``: every contract whose
T-CON-04 ``combination_group_member`` row in a selected group has ``valid_from_known_at`` ≤
``known_at`` (a later LEAVE or JOIN never removes it), plus the versions' own obligation contracts —
never the CURRENT ``contract.combination_group_id``, so a membership move recorded after the run's
cutoff leaves the historical report reproducible (C4-PP-R3).

One version per contract and period (item RPT-FORMER-GROUP-VERSIONS-1). The selection is per
(group, period); a contract whose group changed within a period — computed in its own group and
combined later, or uncombined — has revenue lines of that period under versions of both groups,
and the later version restates the period for it. Of the selected versions that hold a contract
for a period, the one recorded last states it (``stated_elsewhere``); the others are read for
their other contracts and periods only. A period before the change is still read from the group
that posted it.

Rows whose every amount is 0 across the range are omitted; ``cause`` joins the labels of the
non-zero causes with "; " in the SCREENS_B order. ``row_key``
``obligation:<entity>:<contract>:<key>`` carries each component CV-21 percent-encoded, so the
joined key is injective (D-98 104); the code columns carry the raw codes. Money cells are typed
API-S-Money (``tie_outs.money``; C6-RPT-R1). A run naming ``period_lock_id`` is refused by name
(``RPT05_LOCK_SOURCE_NOT_SUPPORTED``) until the framework's locked-dataset branch lands (D-98 96;
F-CLO CLO-8).

The pure half — ``read_trace``, ``split_node``, ``classify``, ``event_refs``, ``aggregate``,
``section_rows``, ``control_totals``, ``check_identity``, ``require_key_columns`` and ``row_key`` —
works in minor units on engine traces and is CPU-tested on native traces; ``build`` is the
database reader.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    contract_subject_key,
    encode_key,
    obligation_subject_key,
)
from erev_engine.stages.s15_disclosures.prior_period import MEASURE, SUM_MEASURE
from erev_engine.trace import SourceRef, Trace, TraceNode
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_event,
    contract_version,
    legal_entity,
    obligation_version,
    subledger_line,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import Calendar, EntityRef, PeriodRef
from erev_api.explain.store import load_trace
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

CODE: Final = "revenue_from_prior_period_obligations"
KEY_COLUMNS: Final = ("entity_code", "contract_external_id", "obligation_key")
CAUSE_FIELDS: Final = (
    "from_price_changes",
    "from_estimate_changes",
    "from_modifications",
    "from_late_events",
    "from_other",
)
REVENUE_FIELD: Final = "revenue"
MEASURE_COLUMNS: Final = (*CAUSE_FIELDS, REVENUE_FIELD)
IDENTITY: Final = "PRIOR_PERIOD_ROWS_EQ_SUM_NODES"
ROW_KEY_PREFIX: Final = "obligation"
DEFAULT_CURRENCY_VIEW: Final = "transaction"
EVENT_KEY_SEPARATOR: Final = "/EV-"  # CV-22 ``<encoded external id>/EV-<6 digits>``

# Refusals by name (rule ids of the 422 ``validation-failed`` problem).
KEY_COLUMN_MISSING: Final = "RPT05_KEY_COLUMN_MISSING"
KEY_COLUMN_UNRESOLVED: Final = "RPT05_KEY_COLUMN_UNRESOLVED"
NODE_SPLIT_MISMATCH: Final = "RPT05_NODE_SPLIT_MISMATCH"
SUM_NODE_MISMATCH: Final = "RPT05_SUM_NODE_MISMATCH"
EVENT_UNRESOLVED: Final = "RPT05_EVENT_UNRESOLVED"
TRACE_MISSING: Final = "RPT05_TRACE_MISSING"
LOCK_SOURCE_NOT_SUPPORTED: Final = "RPT05_LOCK_SOURCE_NOT_SUPPORTED"
LOCK_MESSAGE: Final = (
    "As-locked runs of this report read the frozen PRIOR_PERIOD_POB_REVENUE dataset once the "
    "framework's locked-dataset source lands (D-98 96); run without period_lock_id."
)

# The stage 08 literals of a ``revenue_prior_period`` node's params (ENGINE_SPEC S08-R-14 to
# S08-R-16; ``erev_engine.stages.s08_estimates_late_events.decompose``; parity-tested).
RULE_BOUNDARY: Final = "S08-R-14"
RULE_PROSPECTIVE: Final = "CV-63"
RULE_TERMINATION: Final = "S09-R-06"
ESTIMATE_CHANGED: Final = "ESTIMATE_CHANGED"
CONTRACT_TERMINATED: Final = "CONTRACT_TERMINATED"
MATERIAL_RIGHT_EXERCISED: Final = "MATERIAL_RIGHT_EXERCISED"
MODIFICATION_TYPES: Final = frozenset({"CONTRACT_AMENDED", "LINE_ATTRIBUTES_CHANGED", "REGROUPED"})
CONTRACT_EVENT: Final = "contract_event"
SATISFIED: Final = "SATISFIED"
REVENUE_ROLE: Final = tie_outs.REVENUE

# SCREENS_B RPT-05 "Cause" labels in their listed order; "Other boundary" names a CV-63 zero part
# or an unlisted boundary type (always ``from_other``).
LABEL_PRICE: Final = "Transaction price change"
LABEL_ESTIMATE: Final = "Estimate change"
LABEL_MODIFICATION: Final = "Modification"
LABEL_TERMINATION: Final = "Termination"
LABEL_MATERIAL_RIGHT: Final = "Material right exercised"
LABEL_LATE: Final = "Late event"
LABEL_OTHER: Final = "Other boundary"
LABEL_ORDER: Final = (
    LABEL_PRICE,
    LABEL_ESTIMATE,
    LABEL_MODIFICATION,
    LABEL_TERMINATION,
    LABEL_MATERIAL_RIGHT,
    LABEL_LATE,
    LABEL_OTHER,
)
CAUSE_SEPARATOR: Final = "; "

COLUMNS: Final = (
    Column("entity_code", "Entity", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("product_code", "Product", "code"),
    Column("satisfied_period_key", "Satisfied in", "code"),
    Column("cause", "Cause", "text"),
    Column("currency", "Currency", "code"),
    Column("from_price_changes", "From price changes", "money"),
    Column("from_estimate_changes", "From estimate changes", "money"),
    Column("from_modifications", "From modifications", "money"),
    Column("from_late_events", "From late events", "money"),
    Column("from_other", "From other boundaries", "money"),
    Column("revenue", "Revenue in range", "money"),
)


def refusal(code: str, message: str, *, field: str | None = None) -> Problem:
    """A refusal by name: 422 ``validation-failed`` whose error carries ``code`` as its rule id."""
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field=field, rule_id=code, message=message)],
    )


def require_key_columns(header: Sequence[str]) -> None:
    """Refuse by name when a governed key column is missing from ``header`` (D-98 85; S15-R-20a)."""
    missing = [name for name in KEY_COLUMNS if name not in header]
    if missing:
        raise refusal(
            KEY_COLUMN_MISSING,
            "PRIOR_PERIOD_POB_REVENUE key column(s) missing from the header: "
            f"{', '.join(missing)}.",
            field="header",
        )


def row_key(entity_code: str, contract_external_id: str, obligation_key: str) -> str:
    """``obligation:<entity>:<contract>:<key>`` with each component CV-21 encoded (D-98 104)."""
    parts = (entity_code, contract_external_id, obligation_key)
    return ":".join((ROW_KEY_PREFIX, *(encode_key(part) for part in parts)))


# --- the pure half ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObligationRef:
    """One obligation of a selected version: its trace subject key and the attributes a row
    carries. ``contracting_entity_code`` names the sum node's entity (C4-PP-R1)."""

    subject_key: str
    contract_external_id: str
    obligation_key: str
    product_code: str | None
    performing_entity_code: str
    contracting_entity_code: str
    satisfied_period_key: str | None
    currency: str
    minor_unit: int


@dataclass(frozen=True, slots=True)
class NodeRef:
    """One ``revenue_prior_period`` node of the range, resolved to its row key and attributes."""

    entity_code: str
    contract_external_id: str
    obligation_key: str
    product_code: str | None
    satisfied_period_key: str | None
    currency: str
    minor_unit: int
    period_key: str
    node: TraceNode
    event_types: Mapping[str, str]  # event key → event type of the node's boundary parts


@dataclass(frozen=True, slots=True)
class Split:
    """A node value in minor units by cause field, with the labels of its non-zero causes."""

    amounts: Mapping[str, int]  # CAUSE_FIELDS → minor units
    labels: frozenset[str]
    total: int


@dataclass(frozen=True, slots=True)
class IdentityItem:
    """One ``PRIOR_PERIOD_ROWS_EQ_SUM_NODES`` reconciliation: a contract's complete obligation
    population for one period key against the contracting entity's sum node."""

    subject: str  # ``<contract>@<contracting entity>:<period key>``
    obligation_total: int  # Σ obligation node values, minor units
    obligation_nodes: frozenset[str]  # every ``revenue_prior_period`` node id of the population
    sum_value: int | None  # the sum node's value; None when absent
    sum_inputs: frozenset[str] | None  # the sum node's inputs; None when absent


@dataclass(frozen=True, slots=True)
class TraceRead:
    """What one trace yields for the wanted period keys."""

    reads: tuple[tuple[NodeRef, Split], ...]  # the in-scope rows' nodes, split by cause
    identity: tuple[IdentityItem, ...]  # every (contract, period key) reconciliation
    sum_nodes: Mapping[tuple[str, int], int]  # (currency, minor unit) → Σ sum-node values


@dataclass(frozen=True, slots=True)
class RowCore:
    """One report row before typing: minor-unit amounts by field and the ordered cause labels."""

    entity_code: str
    contract_external_id: str
    obligation_key: str
    product_code: str | None
    satisfied_period_key: str | None
    currency: str
    minor_unit: int
    amounts: Mapping[str, int]  # MEASURE_COLUMNS → minor units
    causes: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.entity_code, self.contract_external_id, self.obligation_key)


def _minor(text: str, minor_unit: int, subject: str) -> int:
    """A money string in minor units; refused by name when it is not whole at the currency."""
    try:
        scaled = Decimal(text).scaleb(minor_unit)
    except InvalidOperation as exc:
        raise refusal(NODE_SPLIT_MISMATCH, f"{subject}: {text!r} is not a money amount.") from exc
    if scaled != scaled.to_integral_value():
        raise refusal(
            NODE_SPLIT_MISMATCH, f"{subject}: {text} is not whole at {minor_unit} decimals."
        )
    return int(scaled)


def classify(rule: str, event_type: str | None, version: str | None) -> tuple[str, str]:
    """(cause field, label) of one boundary part (SCREENS_B RPT-05 cause attribution)."""
    if rule == RULE_PROSPECTIVE:
        return "from_other", LABEL_OTHER
    if rule == RULE_TERMINATION or event_type == CONTRACT_TERMINATED:
        return "from_other", LABEL_TERMINATION
    if event_type == MATERIAL_RIGHT_EXERCISED:
        return "from_other", LABEL_MATERIAL_RIGHT
    if event_type in MODIFICATION_TYPES:
        return "from_modifications", LABEL_MODIFICATION
    if event_type == ESTIMATE_CHANGED:
        if version is not None:
            return "from_estimate_changes", LABEL_ESTIMATE
        return "from_price_changes", LABEL_PRICE
    return "from_other", LABEL_OTHER


def split_node(node: TraceNode, minor_unit: int, event_types: Mapping[str, str]) -> Split:
    """The cause split of one ``revenue_prior_period`` node from its parts and carries; Σ = value
    or refused by name (``RPT05_NODE_SPLIT_MISMATCH``)."""
    value = _minor(node.value, minor_unit, node.id)
    refs = [
        item
        for item in node.inputs
        if isinstance(item, SourceRef) and item.ref_type == CONTRACT_EVENT
    ]
    boundaries = int(node.params.get("boundaries", "0"))
    carries = int(node.params.get("carries", "0"))
    if len(refs) != boundaries:
        raise refusal(
            NODE_SPLIT_MISMATCH,
            f"{node.id}: {boundaries} boundaries but {len(refs)} contract_event inputs.",
        )
    amounts = dict.fromkeys(CAUSE_FIELDS, 0)
    labels: set[str] = set()
    total = 0
    for index, ref in enumerate(refs, start=1):
        detail_value = ref.detail.get("value")
        rule = node.params.get(f"rule_{index}")
        if detail_value is None or rule is None:
            raise refusal(NODE_SPLIT_MISMATCH, f"{node.id}: part {index} carries no value or rule.")
        amount = _minor(detail_value, minor_unit, f"{node.id} part {index}")
        event_type = event_types.get(ref.ref_id)
        if rule == RULE_BOUNDARY and event_type is None:
            raise refusal(
                EVENT_UNRESOLVED,
                f"{node.id}: boundary event {ref.ref_id} is not a stored contract event.",
            )
        field, label = classify(rule, event_type, node.params.get(f"version_{index}"))
        amounts[field] += amount
        total += amount
        if amount != 0:
            labels.add(label)
    for index in range(1, carries + 1):
        target = node.params.get(f"late_target_{index}")
        posted = node.params.get(f"late_posted_{index}")
        if target is None or posted is None:
            raise refusal(NODE_SPLIT_MISMATCH, f"{node.id}: carry {index} has no target / posted.")
        late = int(target) - int(posted)
        amounts["from_late_events"] += late
        total += late
        if late != 0:
            labels.add(LABEL_LATE)
    if total != value:
        raise refusal(
            NODE_SPLIT_MISMATCH,
            f"{node.id}: parts and carries sum to {total} minor, the node value is {value}.",
        )
    return Split(amounts=amounts, labels=frozenset(labels), total=total)


def event_refs[T](
    ref_ids: Iterable[str], encoded_contracts: Mapping[str, T]
) -> dict[str, tuple[T, int]]:
    """CV-22 event key → (contract, stream version), matching the key's ENCODED contract prefix
    against ``encoded_contracts`` (each candidate's ``contract_subject_key``); a key whose prefix
    is not a candidate, or whose tail is not ``EV-<digits>``, resolves to nothing (C4-PP-R2). No
    decoding: raw and encoded ids are never compared with each other."""
    found: dict[str, tuple[T, int]] = {}
    for ref_id in ref_ids:
        prefix, separator, tail = ref_id.rpartition(EVENT_KEY_SEPARATOR)
        if not separator or not prefix or not tail.isdigit():
            continue
        candidate = encoded_contracts.get(prefix)
        if candidate is not None:
            found[ref_id] = (candidate, int(tail))
    return found


def historical_candidates(
    memberships: Iterable[tuple[UUID, UUID, datetime]],
    group_ids: Iterable[UUID],
    known_at: datetime,
) -> set[UUID]:
    """The contracts whose membership in one of ``group_ids`` had started by ``known_at``:
    ``memberships`` are (group id, contract id, ``valid_from_known_at``) rows of T-CON-04
    ``combination_group_member``. A membership that ends later (LEAVE) or a JOIN elsewhere never
    removes a candidate; a membership that starts after ``known_at`` is not one (C4-PP-R3)."""
    wanted = set(group_ids)
    return {
        contract_id
        for group_id, contract_id, valid_from in memberships
        if group_id in wanted and valid_from <= known_at
    }


def encoded_index(contracts: Iterable[tuple[UUID, str]]) -> dict[str, UUID]:
    """``contract_subject_key(external_id)`` → contract id: the encoded candidates ``event_refs``
    matches against (C4-PP-R2)."""
    return {
        contract_subject_key(external_id): contract_id for contract_id, external_id in contracts
    }


def check_identity(items: Iterable[IdentityItem]) -> None:
    """``PRIOR_PERIOD_ROWS_EQ_SUM_NODES``: refused by name when the contracting entity's sum node
    is absent, differs in value, or collects a different set of obligation nodes (S15-R-13)."""
    for item in items:
        if item.sum_value is None or item.sum_inputs is None:
            raise refusal(
                SUM_NODE_MISMATCH,
                f"{item.subject}: no revenue_prior_period_sum node under the contracting entity.",
            )
        if item.sum_value != item.obligation_total:
            raise refusal(
                SUM_NODE_MISMATCH,
                f"{item.subject}: the obligation nodes sum to {item.obligation_total} minor, the "
                f"sum node is {item.sum_value}.",
            )
        if item.sum_inputs != item.obligation_nodes:
            raise refusal(
                SUM_NODE_MISMATCH,
                f"{item.subject}: the sum node collects {sorted(item.sum_inputs)}, the trace holds "
                f"{sorted(item.obligation_nodes)} for the period.",
            )


def read_trace(
    trace: Trace,
    obligations: Mapping[str, ObligationRef],
    period_keys: Sequence[str],
    in_scope: frozenset[tuple[str, str]],
    event_types: Mapping[str, str],
    elsewhere: frozenset[tuple[str, str]] = frozenset(),
) -> TraceRead:
    """Read one version's trace for ``period_keys``: every ``revenue_prior_period`` node of each
    key (the complete population; an unknown subject is refused by name), the identity items per
    (contract, key) against the CONTRACTING entity's sum node, and the row reads of the nodes whose
    (performing entity, key) is in ``in_scope`` (C4-PP-R1). A (contract external id, period key)
    of ``elsewhere`` is stated by another selected version (``stated_elsewhere``) and is not read
    from this one: neither its identity nor its rows."""
    nodes = {node.id: node for node in trace.nodes}
    reads: list[tuple[NodeRef, Split]] = []
    identity: list[IdentityItem] = []
    sum_nodes: dict[tuple[str, int], int] = {}
    for period_key in period_keys:
        suffix = f":{period_key}"
        by_contract: dict[str, list[tuple[TraceNode, ObligationRef]]] = {}
        for node in trace.nodes:
            if node.measure != MEASURE or not node.id.endswith(suffix):
                continue
            subject = node.id[len(MEASURE) + 1 : -len(suffix)]
            obligation = obligations.get(subject)
            if obligation is None:
                raise refusal(
                    KEY_COLUMN_UNRESOLVED,
                    f"{node.id}: no obligation of the version carries this subject.",
                )
            by_contract.setdefault(obligation.contract_external_id, []).append((node, obligation))
        for external_id, members in sorted(by_contract.items()):
            if (external_id, period_key) in elsewhere:
                continue
            contracting = sorted({item.contracting_entity_code for _, item in members})
            currencies = sorted({(item.currency, item.minor_unit) for _, item in members})
            if len(contracting) != 1 or len(currencies) != 1:
                raise refusal(
                    SUM_NODE_MISMATCH,
                    f"{external_id}:{period_key}: obligations name {contracting} as contracting "
                    f"entity and {currencies} as currency; one of each is expected.",
                )
            currency, minor_unit = currencies[0]
            subject = f"{contract_entity_subject_key(external_id, contracting[0])}:{period_key}"
            total = sum(_minor(node.value, minor_unit, node.id) for node, _ in members)
            sum_node = nodes.get(f"{SUM_MEASURE}:{subject}")
            sum_value = (
                None if sum_node is None else _minor(sum_node.value, minor_unit, sum_node.id)
            )
            identity.append(
                IdentityItem(
                    subject=subject,
                    obligation_total=total,
                    obligation_nodes=frozenset(node.id for node, _ in members),
                    sum_value=sum_value,
                    sum_inputs=None
                    if sum_node is None
                    else frozenset(item for item in sum_node.inputs if isinstance(item, str)),
                )
            )
            if sum_value is not None:
                key = (currency, minor_unit)
                sum_nodes[key] = sum_nodes.get(key, 0) + sum_value
            for node, obligation in members:
                if (obligation.performing_entity_code, period_key) not in in_scope:
                    continue
                reads.append(
                    (
                        NodeRef(
                            entity_code=obligation.performing_entity_code,
                            contract_external_id=obligation.contract_external_id,
                            obligation_key=obligation.obligation_key,
                            product_code=obligation.product_code,
                            satisfied_period_key=obligation.satisfied_period_key,
                            currency=obligation.currency,
                            minor_unit=obligation.minor_unit,
                            period_key=period_key,
                            node=node,
                            event_types=event_types,
                        ),
                        split_node(node, minor_unit, event_types),
                    )
                )
    return TraceRead(reads=tuple(reads), identity=tuple(identity), sum_nodes=sum_nodes)


def aggregate(reads: Iterable[tuple[NodeRef, Split]]) -> tuple[RowCore, ...]:
    """One ``RowCore`` per (entity, contract, obligation) over the range, sorted by that key; rows
    whose every amount is 0 are omitted; attributes come from the last read of the key."""
    amounts: dict[tuple[str, str, str], dict[str, int]] = {}
    labels: dict[tuple[str, str, str], set[str]] = {}
    latest: dict[tuple[str, str, str], NodeRef] = {}
    for ref, split in reads:
        key = (ref.entity_code, ref.contract_external_id, ref.obligation_key)
        into = amounts.setdefault(key, dict.fromkeys(MEASURE_COLUMNS, 0))
        for field in CAUSE_FIELDS:
            into[field] += split.amounts[field]
        into[REVENUE_FIELD] += split.total
        labels.setdefault(key, set()).update(split.labels)
        previous = latest.get(key)
        if previous is not None and previous.currency != ref.currency:
            raise refusal(
                NODE_SPLIT_MISMATCH,
                f"{'/'.join(key)}: nodes in {previous.currency} and {ref.currency}.",
            )
        latest[key] = ref
    rows: list[RowCore] = []
    for key in sorted(amounts):
        if all(amount == 0 for amount in amounts[key].values()):
            continue
        ref = latest[key]
        rows.append(
            RowCore(
                entity_code=ref.entity_code,
                contract_external_id=ref.contract_external_id,
                obligation_key=ref.obligation_key,
                product_code=ref.product_code,
                satisfied_period_key=ref.satisfied_period_key,
                currency=ref.currency,
                minor_unit=ref.minor_unit,
                amounts=dict(amounts[key]),
                causes=tuple(label for label in LABEL_ORDER if label in labels[key]),
            )
        )
    return tuple(rows)


def _money(minor: int, currency: str, minor_unit: int) -> dict[str, str]:
    return tie_outs.money(Decimal(minor).scaleb(-minor_unit), currency)


def section_rows(cores: Sequence[RowCore]) -> tuple[dict[str, Any], ...]:
    """The typed rows of ``cores`` (API-S-Money cells; C6-RPT-R1), in the given order."""
    rows: list[dict[str, Any]] = []
    for core in cores:
        rows.append(
            {
                "row_key": row_key(
                    core.entity_code, core.contract_external_id, core.obligation_key
                ),
                "entity_code": core.entity_code,
                "contract_external_id": core.contract_external_id,
                "obligation_key": core.obligation_key,
                "product_code": core.product_code,
                "satisfied_period_key": core.satisfied_period_key,
                "cause": CAUSE_SEPARATOR.join(core.causes) if core.causes else None,
                "currency": core.currency,
                **{
                    field: _money(core.amounts[field], core.currency, core.minor_unit)
                    for field in MEASURE_COLUMNS
                },
            }
        )
    return tuple(rows)


def control_totals(
    cores: Sequence[RowCore], sum_nodes: Mapping[tuple[str, int], int]
) -> dict[str, Any]:
    """``row_count``, ``revenue_total`` and ``prior_period_sum_total`` per currency (04 T-CLS-05 rev
    1.51 and the empty-report rule); ``sum_nodes`` maps (currency, minor unit) to Σ of the sum nodes
    read. ``revenue_total`` is Σ over the published rows (the builders' convention: no row, no
    currency). ``prior_period_sum_total`` carries a currency when a published row carries it or its
    Σ of sum nodes is non-zero, so an empty report carries ``{}`` for both totals, rows netting to
    0.00 show "0.00" in both, and a non-zero out-of-scope population still shows in the sum total
    (the signed-difference rule) — a population of zero-valued sum nodes with no row adds no
    entry."""
    revenue: dict[str, Decimal] = {}
    for core in cores:
        tie_outs.add(
            revenue, core.currency, Decimal(core.amounts[REVENUE_FIELD]).scaleb(-core.minor_unit)
        )
    sums: dict[str, Decimal] = {}
    for (currency, minor_unit), minor in sum_nodes.items():
        if minor != 0 or currency in revenue:
            tie_outs.add(sums, currency, Decimal(minor).scaleb(-minor_unit))
    return {
        "row_count": len(cores),
        "revenue_total": tie_outs.by_currency(revenue),
        "prior_period_sum_total": tie_outs.by_currency(sums),
    }


# --- the database reader ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ObligationRow:
    subject_key: str
    contract_external_id: str
    obligation_key: str
    product_code: str | None
    performing_entity_id: UUID
    contracting_entity_id: UUID
    satisfied_date: date | None
    satisfaction_status: str
    currency: str


@dataclass(frozen=True, slots=True)
class _Selected:
    group_id: UUID
    period_ids: frozenset[UUID]
    known_at: datetime | None = None
    version_no: int = 0


def stated_elsewhere(
    selected: Mapping[UUID, _Selected], contracts: Mapping[UUID, Iterable[str]]
) -> dict[UUID, frozenset[tuple[str, UUID]]]:
    """Per selected version, the (contract external id, period id) pairs another selected version
    states (module docstring "One version per contract and period"): ``contracts`` names the
    contracts each version holds; of the versions that hold a contract for a period, the one
    recorded last — then the highest ``version_no``, then the id — states it. Pure."""
    holders: dict[tuple[str, UUID], list[UUID]] = {}
    for version_id, item in selected.items():
        for external_id in sorted(set(contracts.get(version_id, ()))):
            for period_id in item.period_ids:
                holders.setdefault((external_id, period_id), []).append(version_id)

    def rank(version_id: UUID) -> tuple[bool, Any, int, str]:
        item = selected[version_id]
        return (item.known_at is not None, item.known_at, item.version_no, str(version_id))

    found: dict[UUID, set[tuple[str, UUID]]] = {}
    for key, version_ids in holders.items():
        if len(version_ids) < 2:
            continue
        owner = max(version_ids, key=rank)
        for version_id in version_ids:
            if version_id != owner:
                found.setdefault(version_id, set()).add(key)
    return {version_id: frozenset(pairs) for version_id, pairs in found.items()}


def _references(
    session: Session,
    *,
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    known_at: datetime,
) -> dict[tuple[UUID, UUID], set[UUID]]:
    """(entity, period) → the contract versions the range's REVENUE lines reference."""
    wanted = {(entity_id, item.id) for entity_id, items in periods.items() for item in items}
    if not wanted:
        return {}
    statement = (
        select(
            subledger_line.c.entity_id,
            subledger_line.c.period_id,
            subledger_line.c.contract_version_id,
        )
        .where(
            subledger_line.c.book_code == book_code,
            subledger_line.c.entity_id.in_(sorted({item[0] for item in wanted}, key=str)),
            subledger_line.c.period_id.in_(sorted({item[1] for item in wanted}, key=str)),
            subledger_line.c.recorded_at <= known_at,
            subledger_line.c.account_role == REVENUE_ROLE,
            subledger_line.c.contract_version_id.is_not(None),
        )
        .distinct()
    )
    found: dict[tuple[UUID, UUID], set[UUID]] = {}
    for entity_id, period_id, version_id in session.execute(statement).tuples():
        key = (UUID(str(entity_id)), UUID(str(period_id)))
        if key in wanted:
            found.setdefault(key, set()).add(UUID(str(version_id)))
    return found


def _selected_versions(
    session: Session,
    referenced: Mapping[tuple[UUID, UUID], set[UUID]],
    cutoff: datetime,
    *,
    params: ReportParams,
    book_code: str,
) -> dict[UUID, _Selected]:
    """version id → its group and the period ids it is read for: per (group, period) the latest
    recorded version (highest ``version_no``, ``known_at`` ≤ ``cutoff``) among the referenced.
    S15-R-24 (frps3b): under a bound run the candidates are restricted to the BOUND version ids
    (never a new selection); a live build records the ids it selected as the consumed versions."""
    ids = sorted({item for items in referenced.values() for item in items}, key=str)
    if not ids:
        return {}
    rows = session.execute(
        select(
            contract_version.c.id,
            contract_version.c.combination_group_id,
            contract_version.c.version_no,
            contract_version.c.known_at,
        ).where(
            contract_version.c.id.in_(ids),
            contract_version.c.known_at <= cutoff,
            *tie_outs.bound_version_where(params, contract_version.c.id, book_code),
        )
    ).tuples()
    recorded: dict[UUID, datetime] = {}
    versions: dict[UUID, tuple[UUID, int]] = {}
    for version_id, group_id, version_no, known_at in rows:
        versions[UUID(str(version_id))] = (UUID(str(group_id)), int(version_no))
        recorded[UUID(str(version_id))] = known_at
    best: dict[tuple[UUID, UUID], tuple[int, UUID]] = {}
    for (_entity_id, period_id), candidates in referenced.items():
        for version_id in candidates:
            found = versions.get(version_id)
            if found is None:
                continue
            group_id, version_no = found
            current = best.get((group_id, period_id))
            if current is None or (version_no, str(version_id)) > (current[0], str(current[1])):
                best[(group_id, period_id)] = (version_no, version_id)
    periods_of: dict[UUID, set[UUID]] = {}
    for (_group_id, period_id), (_version_no, version_id) in best.items():
        periods_of.setdefault(version_id, set()).add(period_id)
    tie_outs.record_consumed_versions(params, book_code, sorted(periods_of, key=str))
    return {
        version_id: _Selected(
            group_id=versions[version_id][0],
            period_ids=frozenset(period_ids),
            known_at=recorded[version_id],
            version_no=versions[version_id][1],
        )
        for version_id, period_ids in periods_of.items()
    }


def _obligations(session: Session, version_ids: Sequence[UUID]) -> dict[UUID, list[_ObligationRow]]:
    """The obligation rows of each selected version, keyed for the trace's subject keys."""
    if not version_ids:
        return {}
    statement = (
        select(
            obligation_version.c.contract_version_id,
            obligation_version.c.obligation_key,
            obligation_version.c.product_code,
            obligation_version.c.performing_entity_id,
            obligation_version.c.contracting_entity_id,
            obligation_version.c.satisfied_date,
            obligation_version.c.satisfaction_status,
            obligation_version.c.txn_currency,
            contract.c.external_id,
        )
        .select_from(
            obligation_version.join(contract, obligation_version.c.contract_id == contract.c.id)
        )
        .where(obligation_version.c.contract_version_id.in_(list(version_ids)))
        .order_by(contract.c.external_id, obligation_version.c.obligation_key)
    )
    found: dict[UUID, list[_ObligationRow]] = {}
    for row in session.execute(statement).mappings():
        external_id = str(row["external_id"])
        obligation_key = str(row["obligation_key"])
        found.setdefault(UUID(str(row["contract_version_id"])), []).append(
            _ObligationRow(
                subject_key=obligation_subject_key(external_id, obligation_key),
                contract_external_id=external_id,
                obligation_key=obligation_key,
                product_code=None if row["product_code"] is None else str(row["product_code"]),
                performing_entity_id=UUID(str(row["performing_entity_id"])),
                contracting_entity_id=UUID(str(row["contracting_entity_id"])),
                satisfied_date=row["satisfied_date"],
                satisfaction_status=str(row["satisfaction_status"]),
                currency=str(row["txn_currency"]).strip(),
            )
        )
    return found


def _entity_codes(
    session: Session, entity_ids: Iterable[UUID], *, params: ReportParams
) -> dict[UUID, str]:
    """Entity codes as consumed (`labels.entity_code`; frps3c-1): bound values under a binding —
    no live `legal_entity` read — else the live codes, recorded."""
    ids = sorted(set(entity_ids), key=str)
    if not ids:
        return {}
    if params.binding is not None:
        return {entity_id: tie_outs.entity_code_for(params, entity_id, "") for entity_id in ids}
    rows = session.execute(
        select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.id.in_(ids))
    ).tuples()
    return {
        UUID(str(entity_id)): tie_outs.entity_code_for(params, UUID(str(entity_id)), str(code))
        for entity_id, code in rows
    }


def _encoded_contracts(
    session: Session,
    group_ids: Iterable[UUID],
    version_ids: Sequence[UUID],
    known_at: datetime,
    *,
    params: ReportParams,
) -> dict[str, UUID]:
    """``contract_subject_key(external_id)`` → contract id of the candidates an event key's encoded
    prefix is matched against (C4-PP-R2): the selected groups' HISTORICAL membership as of
    ``known_at`` (T-CON-04 ``combination_group_member``, ``valid_from_known_at`` ≤ ``known_at``)
    plus the selected versions' own obligation contracts — never the current
    ``contract.combination_group_id`` (C4-PP-R3)."""
    ids = sorted(set(group_ids), key=str)
    candidates: set[UUID] = set()
    if ids:
        rows = session.execute(
            select(
                combination_group_member.c.combination_group_id,
                combination_group_member.c.contract_id,
                combination_group_member.c.valid_from_known_at,
            ).where(
                combination_group_member.c.combination_group_id.in_(ids),
                combination_group_member.c.valid_from_known_at <= known_at,
            )
        ).tuples()
        candidates |= historical_candidates(
            (
                (UUID(str(group_id)), UUID(str(contract_id)), valid_from)
                for group_id, contract_id, valid_from in rows
            ),
            (UUID(str(item)) for item in ids),
            known_at,
        )
    if version_ids:
        owned = session.execute(
            select(obligation_version.c.contract_id)
            .where(obligation_version.c.contract_version_id.in_(list(version_ids)))
            .distinct()
        ).tuples()
        candidates |= {UUID(str(contract_id)) for (contract_id,) in owned}
    # S15-R-24 (frps3b): the candidate contract ids are the historical identities the read used —
    # a live build records them (``members.contract``); a bound run uses exactly the bound ones.
    if params.binding is not None:
        candidates = {UUID(item) for item in params.binding.member_ids("contract")}
    else:
        tie_outs.record_members(params, "contract", sorted(candidates, key=str))
    if not candidates:
        return {}
    named = session.execute(
        select(contract.c.id, contract.c.external_id).where(
            contract.c.id.in_(sorted(candidates, key=str))
        )
    ).tuples()
    return encoded_index(
        (UUID(str(contract_id)), str(external_id)) for contract_id, external_id in named
    )


def _event_types(
    session: Session, ref_ids: Iterable[str], encoded_contracts: Mapping[str, UUID]
) -> dict[str, str]:
    """event key → stored event type of every boundary reference that resolves (C4-PP-R2)."""
    resolved = event_refs(ref_ids, encoded_contracts)
    if not resolved:
        return {}
    rows = session.execute(
        select(
            contract_event.c.contract_id,
            contract_event.c.stream_version,
            contract_event.c.event_type,
        ).where(
            contract_event.c.contract_id.in_(
                sorted({item[0] for item in resolved.values()}, key=str)
            ),
            contract_event.c.stream_version.in_(sorted({item[1] for item in resolved.values()})),
        )
    ).tuples()
    by_pair = {
        (UUID(str(contract_id)), int(stream_version)): str(event_type)
        for contract_id, stream_version, event_type in rows
    }
    return {ref_id: by_pair[pair] for ref_id, pair in resolved.items() if pair in by_pair}


def _satisfied_period(row: _ObligationRow, calendar: Calendar | None) -> str | None:
    if row.satisfaction_status != SATISFIED or row.satisfied_date is None or calendar is None:
        return None
    found = calendar.holding(row.satisfied_date)
    return None if found is None else found.key


def _check_view(params: ReportParams, found: Sequence[EntityRef], cores: Sequence[RowCore]) -> None:
    view = str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW)
    functional = {entity.code: entity.functional_currency for entity in found}
    if view != DEFAULT_CURRENCY_VIEW and any(
        core.currency != functional.get(core.entity_code) for core in cores
    ):
        raise tie_outs.invalid("currency_view", rollforward.FUNCTIONAL_ONLY)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise refusal(LOCK_SOURCE_NOT_SUPPORTED, LOCK_MESSAGE, field="parameters.period_lock_id")
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, _before = rollforward.ranges(session, params)
    calendars = tie_outs.calendars(session, found, params=params)
    cutoff = tie_outs.cutoff_for(session, params)  # S15-R-24: the bound cutoff under a binding
    referenced = _references(
        session, book_code=book_code, periods=periods, known_at=params.known_at
    )
    selected = _selected_versions(session, referenced, cutoff, params=params, book_code=book_code)
    version_ids = sorted(selected, key=str)
    obligations = _obligations(session, version_ids)
    entity_codes = _entity_codes(
        session,
        (
            entity_id
            for rows in obligations.values()
            for row in rows
            for entity_id in (row.performing_entity_id, row.contracting_entity_id)
        ),
        params=params,
    )
    code_of = {item.id: item.code for item in found}
    period_key_of = {item.id: item.key for items in periods.values() for item in items}
    in_scope = frozenset(
        (code_of[entity_id], item.key) for entity_id, items in periods.items() for item in items
    )
    traces: dict[UUID, Trace] = {}
    for version_id in version_ids:
        trace = load_trace(session, version_id)
        if trace is None:
            raise refusal(TRACE_MISSING, f"contract version {version_id} has no stored trace.")
        traces[version_id] = trace
    event_types = _event_types(
        session,
        {
            item.ref_id
            for trace in traces.values()
            for node in trace.nodes
            if node.measure == MEASURE
            for item in node.inputs
            if isinstance(item, SourceRef) and item.ref_type == CONTRACT_EVENT
        },
        _encoded_contracts(
            session,
            (item.group_id for item in selected.values()),
            version_ids,
            params.known_at,
            params=params,
        ),
    )
    reads: list[tuple[NodeRef, Split]] = []
    identity: list[IdentityItem] = []
    sum_nodes: dict[tuple[str, int], int] = {}
    elsewhere = stated_elsewhere(
        selected,
        {
            version_id: [row.contract_external_id for row in rows]
            for version_id, rows in obligations.items()
        },
    )
    for version_id in version_ids:
        refs: dict[str, ObligationRef] = {}
        for row in obligations.get(version_id, ()):
            performing = entity_codes.get(row.performing_entity_id)
            contracting = entity_codes.get(row.contracting_entity_id)
            if performing is None or contracting is None:
                raise refusal(
                    KEY_COLUMN_UNRESOLVED,
                    f"{row.subject_key}: its performing or contracting entity is not a legal "
                    "entity.",
                )
            refs[row.subject_key] = ObligationRef(
                subject_key=row.subject_key,
                contract_external_id=row.contract_external_id,
                obligation_key=row.obligation_key,
                product_code=row.product_code,
                performing_entity_code=performing,
                contracting_entity_code=contracting,
                satisfied_period_key=_satisfied_period(
                    row, calendars.get(row.performing_entity_id)
                ),
                currency=row.currency,
                minor_unit=tie_outs.minor_unit(row.currency),
            )
        period_keys = sorted(
            {period_key_of[period_id] for period_id in selected[version_id].period_ids}
        )
        read = read_trace(
            traces[version_id],
            refs,
            period_keys,
            in_scope,
            event_types,
            frozenset(
                (external_id, period_key_of[period_id])
                for external_id, period_id in elsewhere.get(version_id, ())
            ),
        )
        reads.extend(read.reads)
        identity.extend(read.identity)
        for key, value in read.sum_nodes.items():
            sum_nodes[key] = sum_nodes.get(key, 0) + value
    check_identity(identity)
    cores = aggregate(reads)
    _check_view(params, found, cores)
    rows = section_rows(cores)
    require_key_columns([column.key for column in COLUMNS])
    return ReportData(columns=COLUMNS, rows=rows, control_totals=control_totals(cores, sum_nodes))

"""Stage 14 onboarding differences (ENGINE_SPEC S07-R-07 rev 1.17; ENGINE_SPEC_B S14-R-26 rev
1.18; BUILD_SPEC ENB-9; readiness row ONB-DIFF-ROLES).

Private to stage 14 (DG-ENG-07). Under POL-210 ``RECOMPUTE_FROM_INCEPTION`` the ERP holds the
imported cutover balances while the engine recomputes the contract from inception; the difference
per role key at the cutover — the recomputed cumulative role target less the imported amount the
family's own Table 14-A template maps from the stage 07 ``OpeningBaseline`` — posts once, dated the
cutover, with ``reason_code = ONBOARDING_DIFFERENCE`` (``assign._Walker.difference``). This module
resolves the openings of a book and the imported role amounts:

- ``FAMILIES`` names the baseline member each part family compares against: revenue relief
  (JET-02 principal, JET-04a) ← ``revenue_cum``; billing in ``ENGINE`` mode (JET-03 invoice) ←
  ``billed_cum`` with the tax side 0 and the credit-memo part 0, only where the ledger holds
  ENGINE-mode lines of the contract dated on or before the cutover (``recomputed_billing``, the
  S10-R-03 ``engine_lines_through`` predicate; otherwise the imported billing is the ERP's, the
  baseline is counted and JET-03 has no difference); deposits (JET-01b receipt) ← the optional
  payload member ``deposit_liability`` with the transfer and refund parts 0 — an absent member
  with a non-zero recomputed target records ``ONBOARDING_MEMBER_MISSING`` (ERROR; CV-15; never
  read as 0, D-98 candidate 22), an explicit 0 posts the whole recomputed deposit; refund
  liabilities (JET-04b) and return assets (JET-07c) ← 0 (the payload carries no member);
- a part outside the families is deemed posted at the cutover without a difference (S14-R-26);
- a part the template cannot map — JET-02 agent (a split credit), an intercompany counterparty, a
  foreign functional currency — records ``ONBOARDING_DIFFERENCE_UNPOSTED`` (ERROR; CV-15).

- eligibility is explicit per role key (S14-R-26 rev 1.17; Codex C5-PH2-R1): ``Imported`` carries
  ``ELIGIBLE`` (with the imported amount — a zero import is eligible — and the recomputed shares of
  the eligible parts), ``DEEMED_POSTED`` (a family outside S07-R-07, a JET-03 key without recomputed
  ENGINE lines, an absent optional member with a zero target) or ``REFUSED``; the walker computes a
  difference for ``ELIGIBLE`` keys only and never infers eligibility from key presence or a non-zero
  amount, and a key shared by an eligible and a deemed-posted part measures the eligible part only;
- a refund-liability component (``<group>@<entity>/<KIND>/<source>``, S10-R-13) resolves to its
  owner's opening before the cutover, eligibility and refusal checks (``resolve``; S14-R-26 rev
  1.18; D-98 35a): ``RETURN``, ``CONCESSION`` and ``UNCLAIMED_PROPERTY`` to the obligation the
  source names, ``TERMINATION`` and ``VARIABLE_CONSIDERATION`` to the ``<contract>@<entity>``
  opening of the contract the source's head names; the role keys keep the component subject and the
  difference node names the owner. A component whose owner cannot be resolved while its contract
  carries openings (mixed baselines) records ``ONBOARDING_DIFFERENCE_UNPOSTED`` with reason
  ``component_owner_unresolved`` (``unresolved``) for its parts up to the latest candidate cutover.

Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s10_billing_balances.billing import BillingDocumentOut, engine_lines_through
from erev_engine.stages.s14_posting.targets import PartTarget, RoleKey, _shares, encode_component
from erev_engine.stages.s14_posting.templates import JET_PARTS
from erev_engine.stages.state import AllocatedState, BookContext, Finding

__all__ = [
    "COMPONENT_CONTRACT_OWNED",
    "COMPONENT_OBLIGATION_OWNED",
    "COMPONENT_OWNED",
    "DEEMED_POSTED",
    "ELIGIBLE",
    "FAMILIES",
    "Imported",
    "REFUSED",
    "REASON",
    "RECOMPUTE",
    "UNMAPPABLE",
    "MEMBER_MISSING",
    "UNPOSTED",
    "ZERO",
    "Opening",
    "imported_role_amounts",
    "openings",
    "recomputed_billing",
    "resolve",
    "unresolved",
]

REASON: Final = "ONBOARDING_DIFFERENCE"  # the posting reason code (S07-R-07)
UNPOSTED: Final = "ONBOARDING_DIFFERENCE_UNPOSTED"  # 04 table 15.4-C (rev 1.25)
MEMBER_MISSING: Final = "ONBOARDING_MEMBER_MISSING"  # 04 table 15.4-C rev 1.26 (D-98 candidate 22)
RECOMPUTE: Final = "RECOMPUTE_FROM_INCEPTION"  # POL-210
ZERO: Final = "zero"
ELIGIBLE: Final = "ELIGIBLE"  # Imported.status: a difference is computed (a zero import counts)
DEEMED_POSTED: Final = "DEEMED_POSTED"  # Imported.status: deemed posted at D, no difference
REFUSED: Final = "REFUSED"  # Imported.status: a finding refuses the key (CV-15)
# Refund-liability component kinds (S10-R-13 keys ``<group>@<entity>/<KIND>/<source>``) and their
# owners (S14-R-26 rev 1.18; D-98 35a): the obligation the source names, or the
# ``<contract>@<entity>`` opening of the contract the source names (its head is the CV-21 encoded
# contract id).
COMPONENT_OBLIGATION_OWNED: Final = frozenset({"RETURN", "CONCESSION", "UNCLAIMED_PROPERTY"})
COMPONENT_CONTRACT_OWNED: Final = frozenset({"TERMINATION", "VARIABLE_CONSIDERATION"})
COMPONENT_OWNED: Final = COMPONENT_OBLIGATION_OWNED | COMPONENT_CONTRACT_OWNED
UNRESOLVED_REASON: Final = "component_owner_unresolved"
# Part → the OpeningBaseline member holding the imported cumulative of its family (S07-R-07).
FAMILIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "JET-02 principal": "revenue_cum",
        "JET-04a": "revenue_cum",
        "JET-03 invoice": "billed_cum",
        "JET-03 credit memo": ZERO,
        "JET-01b receipt": "deposit_liability",
        "JET-01b criteria met": ZERO,
        "JET-01b refund": ZERO,
        "JET-04b": ZERO,
        "JET-07c": ZERO,
    }
)
# Parts whose imported amount the template cannot map to one plain side (S07-R-07 refusal).
UNMAPPABLE: Final = frozenset({"JET-02 agent"})
_ON_SPLIT: Final = "CONTRACT_LIABILITY"  # the split label the whole imported amount goes to


@dataclass(frozen=True, slots=True)
class Opening:
    """The opening of one subject: cutover, POL-210 method and the imported members (S07-R-05)."""

    cutover: date
    method: str  # OPENING_BALANCES_AT_CUTOVER | RECOMPUTE_FROM_INCEPTION
    event_key: str  # the OPENING_BALANCE_ESTABLISHED event
    members: Mapping[str, int | None]  # revenue_cum, billed_cum, deposit_liability (minor units)
    contract_key: str
    owner: str = ""  # the subject key this opening is keyed by (named on the difference node)

    def imported(self, member: str) -> int | None:
        """The imported amount of a family member; None when the payload omits an optional one."""
        return 0 if member == ZERO else self.members[member]


@dataclass(frozen=True, slots=True)
class Imported:
    """The onboarding-difference state of one role key at the cutover period (S14-R-26 rev 1.17):
    ``ELIGIBLE`` with the imported amount and the recomputed shares of the eligible parts,
    ``DEEMED_POSTED`` or ``REFUSED`` (amounts unused)."""

    status: str
    imported: tuple[int, int] = (0, 0)  # (txn, functional) minor units
    recomputed: tuple[int, int] = (0, 0)  # Σ shares of the eligible parts at the cutover period


def _component(subject_key: str) -> tuple[str, str] | None:
    """(kind, source) of a refund-liability component key ``<group>@<entity>/<KIND>/<source>``;
    None for any other subject."""
    head, _, rest = subject_key.partition("/")
    kind, _, source = rest.partition("/")
    if "@" not in head or kind not in COMPONENT_OWNED or not source:
        return None
    return kind, source


def _contract_of(found: Mapping[str, Opening], head: str) -> str | None:
    """The raw contract key whose CV-21 encoded form equals the canonical source ``head`` among the
    openings' contracts — an exact encoded match, never a raw one: a raw id can equal another
    contract's encoded form (``K%2FA`` against ``K/A``) and the sorted order would let it steal the
    source (Codex C5-PH3-R1; D-98 candidate 53; the refund producer and
    ``assign._component_contract`` match the same way)."""
    for item in found.values():
        if head == encode_component(item.contract_key):
            return item.contract_key
    return None


def _obligation_owner(found: Mapping[str, Opening], source: str) -> Opening | None:
    opening = found.get(source)
    if opening is not None:
        return opening
    for owner, opening in found.items():
        if "/" in owner and "@" not in owner.split("/", 1)[0] and source.endswith(f"/{owner}"):
            return opening
    return None


def resolve(found: Mapping[str, Opening], subject_key: str, entity: str) -> Opening | None:
    """The opening of a subject: its own, or — for a refund-liability component — its owner's
    (S14-R-26 rev 1.18; D-98 35a): ``RETURN``, ``CONCESSION`` and ``UNCLAIMED_PROPERTY`` resolve to
    the obligation their source names; ``TERMINATION`` and ``VARIABLE_CONSIDERATION`` to the
    ``<contract>@<entity>`` opening of the contract the source's head names at ``entity``. The
    component keeps its own subject on every role key; None when no owner opening exists."""
    opening = found.get(subject_key)
    if opening is not None:
        return opening
    component = _component(subject_key)
    if component is None:
        return None
    kind, source = component
    if kind in COMPONENT_OBLIGATION_OWNED:
        return _obligation_owner(found, source)
    contract = _contract_of(found, source.split("/", 1)[0])
    if contract is None:
        return None
    return found.get(contract_entity_subject_key(contract, entity))


def unresolved(
    found: Mapping[str, Opening], subject_key: str, entity: str
) -> tuple[Mapping[str, str], tuple[Opening, ...]] | None:
    """When ``subject_key`` is a refund-liability component whose owner ``resolve`` cannot find
    while its contract carries openings: (the refusal detail — ``kind``, ``contract``, ``entity``,
    ``owner_candidates``; the contract's openings in owner order); None otherwise (S14-R-26 rev
    1.18: a contract without openings is ordinary; a resolved component needs no refusal)."""
    component = _component(subject_key)
    if component is None or resolve(found, subject_key, entity) is not None:
        return None
    kind, source = component
    contract = _contract_of(found, source.split("/", 1)[0])
    if contract is None:
        return None
    candidates = tuple(item for _, item in sorted(found.items()) if item.contract_key == contract)
    if not candidates:
        return None
    detail = {
        "contract": contract,
        "entity": entity,
        "kind": kind,
        "owner_candidates": "|".join(item.owner for item in candidates),
    }
    return MappingProxyType(detail), candidates


def openings(st: AllocatedState) -> Mapping[str, Opening]:
    """Subject key → opening: every obligation with a stage 07 baseline, and a
    ``<contract>@<entity>`` subject when every obligation of the contract at that entity carries
    a baseline with one cutover and one method (its members summed)."""
    out: dict[str, Opening] = {}
    per_contract: dict[tuple[str, str], list[Opening | None]] = {}
    for ob in st.obligations:
        baseline = baseline_of(ob)
        group = per_contract.setdefault((ob.contract_key, ob.contracting_entity), [])
        if baseline is None:
            group.append(None)
            continue
        event_key = None if ob.opening is None else ob.opening.get("event_key")
        item = Opening(
            baseline.cutover_date,
            baseline.method,
            str(event_key),
            MappingProxyType(
                {
                    "revenue_cum": baseline.revenue_cum,
                    # An omitted billed_cum is never read as 0 where JET-03 carries a difference
                    # (D-98 candidate 35, P2-Q-5); stages 10 and 13 keep the baseline's 0.
                    "billed_cum": (
                        None if "billed_cum" in baseline.absent_members else baseline.billed_cum
                    ),
                    "deposit_liability": baseline.deposit_liability,
                }
            ),
            ob.contract_key,
            ob.subject_key,
        )
        out[ob.subject_key] = item
        group.append(item)
    for (contract_key, entity), found in per_contract.items():
        items = [item for item in found if item is not None]
        if len(items) != len(found) or not items:
            continue
        if len({(item.cutover, item.method) for item in items}) != 1:
            continue
        first = items[0]
        out[contract_entity_subject_key(contract_key, entity)] = Opening(
            first.cutover,
            first.method,
            first.event_key,
            MappingProxyType(
                {
                    member: _summed(items, member)
                    for member in ("revenue_cum", "billed_cum", "deposit_liability")
                }
            ),
            contract_key,
            contract_entity_subject_key(contract_key, entity),
        )
    return MappingProxyType(out)


def _summed(items: Sequence[Opening], member: str) -> int | None:
    """Σ of a member over the obligations of a contract; None when any obligation omits it."""
    values = [item.members[member] for item in items]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def recomputed_billing(
    found: Mapping[str, Opening], documents: Sequence[BillingDocumentOut]
) -> frozenset[str]:
    """The subjects of ``found`` under ``RECOMPUTE_FROM_INCEPTION`` whose contract holds
    ``ENGINE``-mode lines dated on or before the cutover (S10-R-03 ``engine_lines_through``): the
    baseline ``billed_cum`` is not counted for them and JET-03 carries the billing difference."""
    return frozenset(
        subject
        for subject, opening in found.items()
        if opening.method == RECOMPUTE
        and engine_lines_through(documents, opening.contract_key, opening.cutover)
    )


def imported_role_amounts(
    ctx: BookContext,
    parts: Sequence[PartTarget],
    found: Mapping[str, Opening],
    recomputed: Collection[str],
) -> tuple[Mapping[RoleKey, Imported], tuple[Finding, ...]]:
    """(role key → ``Imported`` state at the cutover period, refusals) for the parts of RECOMPUTE
    subjects at their cutover period (S07-R-07; S14-R-26 rev 1.17); ``recomputed`` names the
    subjects whose billing the engine recomputes through the cutover (``recomputed_billing``).

    The imported amount of an eligible part is its family's baseline member run through the part's
    own template (``_shares`` on a copy of the part carrying the imported amount), so the debit and
    credit roles receive the signs and splits the recomputed target has; a split side takes the
    whole imported amount on ``CONTRACT_LIABILITY`` (JET-03: tax imported as 0). The recomputed
    amount of a key is the sum of the eligible parts' actual shares. Status precedence per key:
    ``REFUSED`` over ``ELIGIBLE`` over ``DEEMED_POSTED``; a part refused as unmappable records its
    finding and no state (CV-15 blocks the compute; a key without a state has no difference).
    """
    states: dict[RoleKey, Imported] = {}
    findings: list[Finding] = []
    refused: set[tuple[str, str]] = set()

    def mark(
        key: RoleKey,
        status: str,
        imported: tuple[int, int] = (0, 0),
        amount: tuple[int, int] = (0, 0),
    ) -> None:
        prior = states.get(key)
        if prior is None:
            states[key] = Imported(status, imported, amount)
        elif REFUSED in (prior.status, status):
            states[key] = Imported(REFUSED)
        elif status == ELIGIBLE and prior.status == ELIGIBLE:
            states[key] = Imported(
                ELIGIBLE,
                (prior.imported[0] + imported[0], prior.imported[1] + imported[1]),
                (prior.recomputed[0] + amount[0], prior.recomputed[1] + amount[1]),
            )
        elif status == ELIGIBLE:
            states[key] = Imported(ELIGIBLE, imported, amount)

    for part in parts:
        opening = resolve(found, part.subject_key, part.entity)
        if opening is None:
            missing = unresolved(found, part.subject_key, part.entity)
            if missing is not None and (part.subject_key, part.part) not in refused:
                detail, candidates = missing
                latest = max(item.cutover for item in candidates)
                calendar = ctx.entities[part.entity]
                period = next(
                    (p for p in calendar.periods if p.period_key == part.period_key), None
                )
                if (
                    period is not None
                    and period.end_date <= dates.period_of(calendar, latest).end_date
                ):
                    refused.add((part.subject_key, part.part))
                    findings.append(
                        Finding(
                            UNPOSTED,
                            "ERROR",
                            part.subject_key,
                            {
                                **detail,
                                "cutover_date": latest.isoformat(),
                                "part": part.part,
                                "reason": UNRESOLVED_REASON,
                                "recomputed": str(part.amount_txn),
                                "role": part.part.split(" ")[0],
                                "rule": "S07-R-07",
                            },
                            14,
                            candidates[0].event_key,
                        )
                    )
            continue
        if opening.method != RECOMPUTE:
            continue
        calendar = ctx.entities[part.entity]
        if dates.period_of(calendar, opening.cutover).period_key != part.period_key:
            continue
        member = FAMILIES.get(part.part)
        refusal = (
            "agent_split"
            if part.part in UNMAPPABLE
            else "intercompany"
            if part.counterparty_entity is not None
            else "foreign_currency"
            if part.txn_currency != part.functional_currency
            else None
        )
        if refusal is not None and (member is not None or part.part in UNMAPPABLE):
            findings.append(
                Finding(
                    UNPOSTED,
                    "ERROR",
                    part.subject_key,
                    {
                        "cutover_date": opening.cutover.isoformat(),
                        "part": part.part,
                        "reason": refusal,
                        "recomputed": str(part.amount_txn),
                        "role": part.part.split(" ")[0],
                        "rule": "S07-R-07",
                    },
                    14,
                    opening.event_key,
                )
            )
            continue  # the finding blocks the compute (CV-15); the part's keys carry no state
        actual = _shares(part)
        if member is None or (member == "billed_cum" and part.subject_key not in recomputed):
            # A family outside S07-R-07, or a JET-03 key with no ENGINE line recomputed through the
            # cutover (the imported billing stays the ERP's, S10-R-03): deemed posted at D.
            for key, _ in actual:
                mark(key, DEEMED_POSTED)
            continue
        amount = opening.imported(member)
        if amount is None:
            # The payload omits the family's optional member: never read as 0 (S07-R-07 rev 1.18).
            if part.amount_txn != 0 or part.amount_functional != 0:
                findings.append(
                    Finding(
                        MEMBER_MISSING,
                        "ERROR",
                        part.subject_key,
                        {
                            "cutover_date": opening.cutover.isoformat(),
                            "member": member,
                            "part": part.part,
                            "recomputed": str(part.amount_txn),
                            "rule": "S07-R-07",
                        },
                        14,
                        opening.event_key,
                    )
                )
                for key, _ in actual:
                    mark(key, REFUSED)
            else:
                for key, _ in actual:
                    mark(key, DEEMED_POSTED)
            continue
        weights = part.weights
        spec = JET_PARTS[part.part]
        for side in (spec.debit, spec.credit):
            if side is not None and side.selection == "SPLIT":
                weights = tuple(
                    (label, Fraction(1) if label == _ON_SPLIT else Fraction(0))
                    for label in side.labels
                )
        synthetic = dataclasses.replace(
            part,
            amount_txn=amount,
            amount_functional=amount,
            time_txn=0,
            time_functional=0,
            weights=weights,
            value_inputs=(),
            split_inputs=(),
        )
        imported_by_key: dict[RoleKey, tuple[int, int]] = {}
        for key, share in _shares(synthetic):
            prior = imported_by_key.get(key, (0, 0))
            imported_by_key[key] = (prior[0] + share.txn, prior[1] + share.functional)
        recomputed_by_key: dict[RoleKey, tuple[int, int]] = {}
        for key, share in actual:
            prior = recomputed_by_key.get(key, (0, 0))
            recomputed_by_key[key] = (prior[0] + share.txn, prior[1] + share.functional)
        keys = list(imported_by_key)
        keys.extend(key for key in recomputed_by_key if key not in imported_by_key)
        for key in keys:
            mark(
                key, ELIGIBLE, imported_by_key.get(key, (0, 0)), recomputed_by_key.get(key, (0, 0))
            )
    return MappingProxyType(dict(states)), tuple(sorted(findings, key=Finding.sort_key))

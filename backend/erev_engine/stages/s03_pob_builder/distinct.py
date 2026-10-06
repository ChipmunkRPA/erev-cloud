"""Stage 03 distinctness, series and merging (ENGINE_SPEC S03-R-05, S03-R-06; S03-INV-01).

Private to stage 03. ``classify`` applies the reviewed ``POB_DISTINCT_OVERRIDE`` and
``SERIES_CLASSIFICATION`` outcomes (Table 0.4-A); ``group`` merges non-distinct lines into their
integration target (606-10-25-19 to 25-22); ``merge`` is shared with the S03-R-14 and S03-R-15
elections. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Final

from erev_engine.bundle import ContractInput, JudgementInput
from erev_engine.enums import Distinctness
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder.templates import PRICE_MERGED, PobDraft
from erev_engine.stages.state import BookContext

__all__ = ["SERIES_UNITS", "classify", "group", "merge", "obligation_judgement"]

SERIES_UNITS: Final = frozenset({"day", "month", "transaction", "unit"})  # T-REF-23


def obligation_judgement(
    header: ContractInput, topic: str, book_code: str, obligation_key: str
) -> JudgementInput | None:
    """The reviewed judgement of ``topic`` whose outcome ``obligation_key`` names the line.

    ``subject_key`` is the contract external id or the obligation subject key, raw or CV-21
    encoded; ``book_code`` None applies to every book. Of several records the greatest
    ``judgement_key`` governs (bundle order), as in stage 02.
    """
    contract = header.external_id
    subjects = {
        contract,
        contract_subject_key(contract),
        f"{contract}/{obligation_key}",
        obligation_subject_key(contract, obligation_key),
    }
    found: JudgementInput | None = None
    for record in header.judgements:
        if (
            record.topic == topic
            and record.subject_key in subjects
            and record.book_code in (None, book_code)
            and record.outcome.get("obligation_key") == obligation_key
        ):
            found = record
    return found


def classify(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PobDraft:
    """S03-R-05 and S03-R-06: distinctness, series increment unit and integration target.

    ``series`` without an increment unit in ``SERIES_UNITS`` raises
    ``EngineError("ENGINE_INVARIANT_VIOLATED")`` (CV-45; T-REF-23 check).
    """
    header = st.canonical.contracts[draft.contract_key].header
    key = draft.obligation_key
    override = obligation_judgement(header, "POB_DISTINCT_OVERRIDE", ctx.book_code, key)
    series = obligation_judgement(header, "SERIES_CLASSIFICATION", ctx.book_code, key)
    distinctness, unit = draft.distinctness, draft.series_increment_unit
    if series is not None:
        distinctness, unit = Distinctness.SERIES, series.outcome.get("series_increment_unit")
    integrates: str | None = None
    if override is not None:
        literal = override.outcome.get("distinctness")
        if literal is None:
            raise ValueError(f"{override.judgement_key}: outcome member distinctness is required")
        distinctness = Distinctness(literal)
        integrates = override.outcome.get("integrates_into_obligation_key") or None
    if distinctness == Distinctness.SERIES:
        if unit not in SERIES_UNITS:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a series obligation has no valid increment unit",
                subject_key=draft.subject_key,
                detail={"rule": "S03-R-06", "series_increment_unit": str(unit)},
            )
    else:
        unit = None
    if distinctness != Distinctness.NONDISTINCT:
        integrates = None
    return dataclasses.replace(
        draft,
        distinctness=distinctness,
        series_increment_unit=unit,
        integrates_into_obligation_key=integrates,
    )


def group(drafts: Sequence[PobDraft], merging: Mapping[str, bool]) -> list[PobDraft]:
    """S03-R-05: merge every non-distinct line into its integration target, per contract.

    The target is the reviewed ``integrates_into_obligation_key``, else the line's
    ``bundle_parent_obligation_key`` when that parent is a line of the contract. Chains resolve to
    their root. ``merging[contract]`` False (POL-211 ``SINGLE_POB``) keeps every line apart. A
    repeated key, an unknown target or a cycle raises ``EngineError("ENGINE_INVARIANT_VIOLATED")``.
    """
    by_contract: dict[str, dict[str, PobDraft]] = {}
    for draft in drafts:
        lines = by_contract.setdefault(draft.contract_key, {})
        if draft.obligation_key in lines:
            raise _invariant("S03-INV-02", "an obligation key repeats", draft.subject_key)
        lines[draft.obligation_key] = draft
    obligations: list[PobDraft] = []
    for contract_key in sorted(by_contract):
        lines = by_contract[contract_key]
        targets = _targets(lines) if merging.get(contract_key, True) else {}
        roots = {key: _root(key, targets, lines) for key in sorted(lines)}
        for root in sorted(set(roots.values())):
            members = [lines[key] for key in sorted(lines) if roots[key] == root and key != root]
            obligations.append(merge(lines[root], members, rule="S03-R-05"))
    return obligations


def merge(
    host: PobDraft, others: Sequence[PobDraft], *, rule: str, weighted: bool = True
) -> PobDraft:
    """The host obligation with ``others`` merged into it (S03-R-05, S03-R-14, S03-R-15).

    The host keeps its key, template, kind and measure; P sums over every member. With
    ``weighted`` the quantity sums too, start is the earliest and end the latest date; without it
    (shipping) the members join by price only and their SSP weight is 0.
    """
    if not others:
        return host
    members = list(host.members)
    for other in others:
        members.extend(
            dataclasses.replace(member, rule=rule, weighted=weighted)
            if member.subject_key == other.subject_key
            else member
            for member in other.members
        )
    price = host.stated_price + sum((other.stated_price for other in others), Fraction(0))
    quantity, start, end = host.quantity, host.start_date, host.end_date
    if weighted:
        quantity += sum((other.quantity for other in others), Fraction(0))
        everyone = (host, *others)
        start = min((d.start_date for d in everyone if d.start_date is not None), default=None)
        end = max((d.end_date for d in everyone if d.end_date is not None), default=None)
    return dataclasses.replace(
        host,
        quantity=quantity,
        stated_price=price,
        original_quantity=quantity,
        original_stated_price=price,
        start_date=start,
        end_date=end,
        members=tuple(sorted(members, key=lambda member: member.subject_key)),
        price_basis=PRICE_MERGED,
        split=None,
    )


def _targets(lines: Mapping[str, PobDraft]) -> dict[str, str]:
    targets: dict[str, str] = {}
    for key in sorted(lines):
        draft = lines[key]
        if draft.distinctness != Distinctness.NONDISTINCT:
            continue
        target = draft.integrates_into_obligation_key
        parent = draft.bundle_parent_obligation_key
        if target is None and parent is not None and parent != key and parent in lines:
            target = parent
        if target is None:
            continue
        if target not in lines:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a non-distinct line integrates into an unknown obligation",
                subject_key=draft.subject_key,
                detail={"integrates_into_obligation_key": target, "rule": "S03-R-05"},
            )
        targets[key] = target
    return targets


def _root(key: str, targets: Mapping[str, str], lines: Mapping[str, PobDraft]) -> str:
    seen = {key}
    while key in targets:
        key = targets[key]
        if key in seen:
            raise _invariant(
                "S03-INV-01", "integration targets form a cycle", lines[key].subject_key
            )
        seen.add(key)
    return key


def _invariant(invariant: str, message: str, subject_key: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=subject_key,
        detail={"invariant": invariant},
    )

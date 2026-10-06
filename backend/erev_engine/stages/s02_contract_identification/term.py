"""Stage 02 enforceable term and judgement readers (ENGINE_SPEC S02-R-06; Table 0.4-A; POL-014).

Private to stage 02. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.bundle import ContractInput, JudgementInput
from erev_engine.money import to_fraction
from erev_engine.stages.s01_canonicalize import contract_subject_key, payload_date, payload_text
from erev_engine.stages.state import BookContext, CanonicalBundle
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "FORMULA_ID",
    "EnforceableTerm",
    "enforceable",
    "judgement",
    "outcome_date",
    "outcome_flag",
    "substantive_penalty",
]

FORMULA_ID: Final = "step1.enforceable_term.v1"
POLICY_CODE: Final = "step1.term_with_termination_rights"
EARLIEST_TERMINATION: Final = "TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY"
TERMINATING_PARTIES: Final = frozenset({"CUSTOMER", "BOTH"})


@dataclass(frozen=True, slots=True)
class EnforceableTerm:
    """The accounting term of a contract (ENGINE_SPEC §2.1)."""

    contract_key: str
    end_date: date | None
    basis: str  # STATED_TERM | JUDGEMENT | STATED_TERM_PENDING_JUDGEMENT
    # (obligation_key, end_date, enforceable consideration or None) of each truncated line
    truncated_lines: tuple[tuple[str, date, Fraction | None], ...]


def judgement(header: ContractInput, topic: str, book_code: str) -> JudgementInput | None:
    """The reviewed judgement of ``topic`` on the contract for ``book_code``.

    ``subject_key`` is the contract external id, raw or CV-21 encoded; ``book_code`` None applies to
    every book. Of several records the greatest ``judgement_key`` governs (bundle order).
    """
    subjects = {header.external_id, contract_subject_key(header.external_id)}
    found: JudgementInput | None = None
    for record in header.judgements:
        if (
            record.topic == topic
            and record.subject_key in subjects
            and record.book_code in (None, book_code)
        ):
            found = record
    return found


def outcome_flag(record: JudgementInput | None, member: str) -> bool | None:
    """A ``true``/``false`` outcome member; ``None`` when the record or member is absent."""
    value = None if record is None else record.outcome.get(member)
    if value is None:
        return None
    if value not in ("true", "false"):
        raise ValueError(f"judgement outcome member {member} is neither true nor false")
    return value == "true"


def outcome_date(record: JudgementInput | None, member: str) -> date | None:
    """An ISO date outcome member; ``None`` when the record or member is absent."""
    value = None if record is None else record.outcome.get(member)
    return None if value is None else date.fromisoformat(value)


def substantive_penalty(header: ContractInput, book_code: str) -> bool:
    """S02-R-06: the reviewed ``CONTRACT_TERM`` outcome, else ``termination_has_penalty``."""
    record = judgement(header, "CONTRACT_TERM", book_code)
    flag = outcome_flag(record, "termination_penalty_substantive")
    return bool(header.termination_has_penalty) if flag is None else flag


def _stated_end(lines: Sequence[Mapping[str, object]]) -> date | None:
    ends = [end for line in lines if (end := payload_date(line, "end_date")) is not None]
    return max(ends, default=None)


def _truncated(
    record: JudgementInput | None, lines: Sequence[Mapping[str, object]], end: date
) -> Iterator[tuple[str, date, Fraction | None]]:
    for line in lines:
        key, line_end = payload_text(line, "obligation_key"), payload_date(line, "end_date")
        if key is None or line_end is None or line_end <= end:
            continue
        member = None if record is None else record.outcome.get(f"enforceable_consideration[{key}]")
        yield key, end, None if member is None else to_fraction(member)


def enforceable(
    ctx: BookContext,
    cb: CanonicalBundle,
    contract_key: str,
    lines: Sequence[Mapping[str, object]],
    tb: TraceBuilder,
) -> EnforceableTerm:
    """S02-R-06 under POL-014, with node ``enforceable_end_date:<contract>:-``.

    ``STATED_TERM`` ends at the latest line end. Under the earliest-termination option, when the
    customer (or both parties) can terminate without a substantive penalty, a reviewed
    ``CONTRACT_TERM`` outcome ``enforceable_end_date`` gives basis ``JUDGEMENT`` and truncates every
    later line to that date, with total price replaced by ``enforceable_consideration[<key>]`` when
    present; without it the basis is ``STATED_TERM_PENDING_JUDGEMENT`` and nothing is truncated.
    """
    header = cb.contracts[contract_key].header
    policy = ctx.policies.value(POLICY_CODE, contract=contract_key)
    basis, end_date = "STATED_TERM", _stated_end(lines)
    truncated: tuple[tuple[str, date, Fraction | None], ...] = ()
    terminable = header.termination_party in TERMINATING_PARTIES
    if policy == EARLIEST_TERMINATION and terminable:
        if not substantive_penalty(header, ctx.book_code):
            record = judgement(header, "CONTRACT_TERM", ctx.book_code)
            judged = outcome_date(record, "enforceable_end_date")
            if judged is None:
                basis = "STATED_TERM_PENDING_JUDGEMENT"
            else:
                basis, end_date = "JUDGEMENT", judged
                truncated = tuple(_truncated(record, lines, judged))
    term = EnforceableTerm(contract_key, end_date, basis, truncated)
    if end_date is not None:
        ordinal = str(end_date.toordinal())
        booking = next(
            (
                e
                for e in cb.events
                if e.contract_key == contract_key and e.event_type == "CONTRACT_BOOKED"
            ),
            None,
        )
        inputs = (
            []
            if booking is None
            else [SourceRef("contract_event", booking.event_key, {"value": ordinal})]
        )
        tb.node(
            measure="enforceable_end_date",
            subject_key=contract_subject_key(contract_key),
            period_key=None,
            value=end_date.toordinal(),
            currency=None,
            minor_unit=None,
            formula_id=FORMULA_ID,
            inputs=inputs,
            params={
                "basis": basis,
                "date": end_date.isoformat(),
                "policy": policy if isinstance(policy, str) else str(policy),
                "value": ordinal,
            },
            narrative_key="step1.enforceable_term",
        )
    return term

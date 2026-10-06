"""Terms-form modification lines: the action the runner's conversion gives a line (dev-guide §9.5.4;
D-87 L5-3-Q-19; D-97 (1c) v3).

``runners._convert_terms`` and the loader's CHANGE-only guard (DG-AK-32) share this classification,
so the loader refuses exactly the lines the conversion would read as CHANGE: ADD when the obligation
key is not in force at the modification date; REMOVE for kind ``REMOVE_OBLIGATION`` or
``TERMINATION``, or a line whose ``end_date`` is before that date; CHANGE otherwise. A key-format
rule of the test loader, not API or import enforcement.
"""

from __future__ import annotations

from datetime import date
from typing import Final, Literal

from support.answer_keys.models import ContractLine

TERMS_REMOVE_KINDS: Final = frozenset({"REMOVE_OBLIGATION", "TERMINATION"})
ADD: Final = "ADD"
REMOVE: Final = "REMOVE"
CHANGE: Final = "CHANGE"

Action = Literal["ADD", "REMOVE", "CHANGE"]


def terms_line_action(
    kind: str, line: ContractLine, *, in_force: bool, effective_date: date
) -> Action:
    """The delta-form action of a terms-form ``line`` of a modification of ``kind`` effective on
    ``effective_date``; ``in_force`` is whether the line's obligation key is in force then (the
    booked lines with the earlier modifications' deltas). Raises ``ValueError`` on a malformed
    ``end_date`` (the conversion reports it)."""
    if not in_force:
        return ADD
    ending = line.end_date is not None and date.fromisoformat(line.end_date) < effective_date
    return REMOVE if kind in TERMS_REMOVE_KINDS or ending else CHANGE

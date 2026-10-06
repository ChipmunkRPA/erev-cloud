"""Stage 02 status timeline per book (ENGINE_SPEC Table 2.2-A; S02-R-01, S02-R-02, S02-R-05).

Private to stage 02. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import ContractInput
from erev_engine.enums import ContractStatus
from erev_engine.stages.s01_canonicalize import payload_bool, payload_text
from erev_engine.stages.state import EventView

__all__ = ["PERFORMANCE_EVENT_TYPES", "STATUS_ORDINAL", "StatusMachine", "StatusSegment"]

# The E-17 ordinal a status node holds: the 1-based position of the literal in 04 §3.4 order.
STATUS_ORDINAL: Final = MappingProxyType(
    {status.value: index + 1 for index, status in enumerate(ContractStatus)}
)
# Performance that ends MUTUAL_TERMINATION_UNPERFORMED (Table 2.2-A; 606-10-25-4).
PERFORMANCE_EVENT_TYPES: Final = frozenset(
    {"BILLING_RECORDED", "DELIVERY_RECORDED", "PAYMENT_RECEIVED"}
)


@dataclass(frozen=True, slots=True)
class StatusSegment:
    """A status in force from ``from_date`` (ENGINE_SPEC §2.1)."""

    contract_key: str
    book_code: str
    from_date: date
    from_event_key: str | None  # None for the booking segment
    status: str  # E-17: DRAFT | NOT_A_CONTRACT | ACTIVE | TERMINATED | VOIDED
    # BOOKED | ACTIVATED | NOT_PROBABLE | NO_COMMERCIAL_SUBSTANCE | MUTUAL_TERMINATION_UNPERFORMED |
    # CRITERIA_MET | EVENT_25_7_B | TERMINATED | VOIDED (T-CON-08 status_reason_in_book)
    reason: str
    transition: str | None  # POL-013 literal on CRITERIA_MET


class StatusMachine:
    """Table 2.2-A over one contract's included events in ENG-06 order, for one book.

    ``COLLECTIBILITY_ASSESSED`` and ``CONTRACT_CRITERIA_MET`` act only in the book their payload
    names (S02-R-01); the payload boolean decides collectibility, never a percentage (POL-011).
    Events (a) and (c) of 25-7 leave the status unchanged and are recorded on the deposit targets.
    An instance lives for one call only (DG-ENG-08).
    """

    def __init__(
        self,
        *,
        contract_key: str,
        book_code: str,
        header: ContractInput,
        booked_on: date,
        penalty_substantive: bool,
        criteria_met_transition: str,
        consideration_nonrefundable: bool,
    ) -> None:
        self._book_code = book_code
        self._header = header
        self._penalty_substantive = penalty_substantive
        self._transition = criteria_met_transition
        self._nonrefundable = consideration_nonrefundable
        self._probable: bool | None = None
        self._significant_change = False
        self._performed = False
        self.segments: list[StatusSegment] = [
            StatusSegment(contract_key, book_code, booked_on, None, "DRAFT", "BOOKED", None)
        ]

    @property
    def current(self) -> StatusSegment:
        return self.segments[-1]

    def step(self, event: EventView) -> StatusSegment | None:
        """Apply ``event``; the new segment, or ``None`` when the status does not change."""
        segment = self._next(event)
        self._observe(event)
        if segment is not None:
            self.segments.append(segment)
        return segment

    def _segment(
        self, event: EventView, status: str, reason: str, transition: str | None = None
    ) -> StatusSegment:
        return StatusSegment(
            self.current.contract_key,
            self._book_code,
            event.effective_date,
            event.event_key,
            status,
            reason,
            transition,
        )

    def _for_book(self, event: EventView) -> bool:
        book = payload_text(event.payload, "book")
        if book is None:
            raise ValueError(f"{event.event_key}: payload member book is required (§16.3)")
        return book == self._book_code

    @staticmethod
    def _probable_flag(event: EventView) -> bool:
        flag = payload_bool(event.payload, "is_probable")
        if flag is None:
            raise ValueError(f"{event.event_key}: payload member is_probable is required (§16.3)")
        return flag

    def _next(self, event: EventView) -> StatusSegment | None:
        current, kind = self.current, event.event_type
        if kind == "CONTRACT_VOIDED":
            return self._segment(event, "VOIDED", "VOIDED")
        if current.status == "DRAFT" and kind == "CONTRACT_ACTIVATED":
            return self._activation(event)
        if current.status == "NOT_A_CONTRACT":
            unperformed = current.reason == "MUTUAL_TERMINATION_UNPERFORMED"
            if (kind == "CONTRACT_CRITERIA_MET" and self._for_book(event)) or (
                unperformed and kind in PERFORMANCE_EVENT_TYPES
            ):
                return self._segment(event, "ACTIVE", "CRITERIA_MET", self._transition)
            if kind == "CONTRACT_TERMINATED" and self._nonrefundable:
                return self._segment(event, "TERMINATED", "EVENT_25_7_B")
            return None
        if current.status == "ACTIVE":
            if (
                kind == "COLLECTIBILITY_ASSESSED"
                and self._for_book(event)
                and not self._probable_flag(event)
                and self._significant_change
            ):
                return self._segment(event, "NOT_A_CONTRACT", "NOT_PROBABLE")  # 25-5, 25-6
            if kind == "CONTRACT_TERMINATED" and event.payload.get("termination_kind") == "FULL":
                return self._segment(event, "TERMINATED", "TERMINATED")  # applied by S06-R-24
        return None

    def _activation(self, event: EventView) -> StatusSegment:
        header = self._header
        if self._probable is False:
            return self._segment(event, "NOT_A_CONTRACT", "NOT_PROBABLE")  # 25-1(e)
        if not header.has_commercial_substance:
            return self._segment(event, "NOT_A_CONTRACT", "NO_COMMERCIAL_SUBSTANCE")  # 25-1(d)
        if (
            header.termination_party == "BOTH"
            and not self._penalty_substantive
            and not header.termination_notice_days
            and not self._performed
        ):
            return self._segment(event, "NOT_A_CONTRACT", "MUTUAL_TERMINATION_UNPERFORMED")  # 25-4
        return self._segment(event, "ACTIVE", "ACTIVATED")

    def _observe(self, event: EventView) -> None:
        kind = event.event_type
        if kind == "COLLECTIBILITY_ASSESSED" and self._for_book(event):
            self._probable = self._probable_flag(event)
            self._significant_change = False
        elif kind == "SIGNIFICANT_CHANGE_FLAGGED":
            self._significant_change = True
        elif kind in PERFORMANCE_EVENT_TYPES:
            self._performed = True

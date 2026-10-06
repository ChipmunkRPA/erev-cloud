"""BR-CLS-04 and BR-CLS-06 (REQ-CLS-003, REQ-CLS-011; BUILD_SPEC CLO-3, CLO-7): a posting dated into
a period of its entity and book that is in soft close, or that was locked once and is not locked
now, needs a human approval by someone other than the submitter — no ``AUTO_APPROVAL`` rule
applies (PRD §2.5 "in a reopened period"; SoD-6). The predicate the posting commands pass as
``auto_approval=not …`` to ``approvals.submit``: manual events with the contracting entity, the
book and the event's effective date (F-CTR's ``record_events`` hunk after their 14f7adc0); imports
keep their row-level scan in ``imports.commands.posts_into_closing_period``. Both ask
``periods.auto_approval_barred`` (supervisor ruling R-117 (c); DG-KRN-TIME-04 rev 1.167): the
period is ``closing``, or its current lock record is a ``REOPEN`` — a reopened period, also
through the soft close that follows its reopen.

A date without a postable period posts nothing here, so it does not restrict; the posting command
itself refuses it (DG-KRN-TIME-04, DB-07).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from erev_api.enums import BookCode
from erev_api.periods import auto_approval_barred, posting_period
from erev_api.problems import Problem


def posts_into_restricted_period(
    session: Session, *, entity_id: UUID, book_code: BookCode | str, effective_date: date
) -> bool:
    """True when ``effective_date`` posts into a period of the entity and book that is in soft
    close or under reopen (BR-CLS-04, BR-CLS-06; ``periods.auto_approval_barred``); False for any
    other period and for a date without a postable period."""
    book = BookCode(str(getattr(book_code, "value", book_code)))
    try:
        posting, _origin = posting_period(
            session, entity_id=entity_id, book_code=book, effective_date=effective_date
        )
    except Problem:
        return False
    return auto_approval_barred(session, entity_id=entity_id, book_code=book, period_id=posting.id)

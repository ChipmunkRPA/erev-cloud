"""SQLSTATE and EREV-xxx-nnn mapping (dev-guide §1.1 ``db/errors.py``; 04 §14.1; DG-KRN-ERR-02).

Database invariants raise ``P0001`` with a message that starts with a §14.1 error code, for
example ``EREV-IMM-001 row is append-only``. These helpers read the SQLSTATE and the code from a
SQLAlchemy ``DBAPIError``; ``erev_api.problems.from_db_error`` maps them to problem slugs.

``is_transient`` is the one table of what a database error says about the work that met it (05
RCP-20 rev 1.82; supervisor ruling R-105 (2)): a transient error may not recur when the same work
is done again — a wait, a deadlock, a cancelled statement, resources, the connection, the period
guard's refusal, which a new plan avoids — and a deterministic one will. The computation of a
group stores nothing for the first and a FAILED computation for the second
(``compute_job.compute_group``); the mapping of database errors to problems and the retry
predicate of jobs read the same table. ``server_unavailable`` (ruling R-53 (5)) names the part of
the transient table that is answered 503 with ``Retry-After``: every error it accepts is
transient.
"""

from __future__ import annotations

import re
from typing import Final

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

RAISE_EXCEPTION: Final = "P0001"
INSUFFICIENT_PRIVILEGE: Final = "42501"
DEADLOCK_DETECTED: Final = "40P01"  # DG-KRN-DB-08 / DG-KRN-ERR-02: 409 lock-conflict
LOCK_NOT_AVAILABLE: Final = (
    "55P03"  # DG-KRN-ERR-02 rev 1.61: a wait beyond lock_timeout, 409 lock-conflict
)
# 04 DB-07: the posting period closed after the posting was planned; planned again, the posting
# goes to the period that is open (DG-KRN-TIME-04). Recognised by its §14.1 code in the message
# of a ``P0001``.
PERIOD_GUARD: Final = "EREV-LED-003"
# SQLSTATE classes (the first two characters), R-105 (2). Transient: connection (08), invalid
# transaction state (25), transaction rollback (40: serialization failure, deadlock), insufficient
# resources (53), object not in prerequisite state (55: lock not available), operator intervention
# (57: statement timeout, cancel, shutdown), system error (58), snapshot too old (72), internal
# error (XX).
TRANSIENT_CLASSES: Final = frozenset({"08", "25", "40", "53", "55", "57", "58", "72", "XX"})
# Deterministic: feature not supported (0A), cardinality (21), data exception (22), integrity
# constraint (23), triggered data change (27), SQL routine (2F), syntax or access rule (42: a
# row-level-security refusal is 42501), WITH CHECK OPTION (44), program limit (54) and a raised
# exception (P0) other than the period guard's — the immutability, seal and invariant triggers.
DETERMINISTIC_CLASSES: Final = frozenset(
    {"0A", "21", "22", "23", "27", "2F", "42", "44", "54", "P0"}
)
# DG-KRN-ERR-02 rev 1.127 (supervisor rulings R-97 (5), (6)): a serialization failure is the same
# 409 lock-conflict as a deadlock - the transaction lost to another one and nothing was saved - and
# a cancelled statement (the platform's own statement_timeout, or a cancel request) is the named
# 503 `statement-timeout`.
SERIALIZATION_FAILURE: Final = "40001"
QUERY_CANCELED: Final = "57014"
# 04 API-C-05 rev 1.114 / DG-KRN-ERR-03 rev 1.97 (supervisor ruling R-53 (5)): the errors that say
# the server could not do it at that moment. Class 53 is insufficient resources (53200, "out of
# shared memory", is the lock table of 05 §2.7); the class 08 codes are a connection that was
# refused, lost or never existed; the 57P codes a server that is shutting down, has crashed or is
# still starting. Deliberately absent: 08007 (the outcome of a commit is unknown), 08P01 (a
# protocol violation is a defect) and 57014 (a cancelled statement, the platform's own
# statement_timeout included).
SERVER_UNAVAILABLE_CLASS: Final = "53"
SERVER_UNAVAILABLE_STATES: Final = frozenset(
    {"08000", "08001", "08003", "08004", "08006", "57P01", "57P02", "57P03"}
)
_ERROR_CODE: Final = re.compile(r"^(EREV-[A-Z]{2,3}-\d{3})\b")


def sqlstate(exc: DBAPIError) -> str | None:
    """The five-character SQLSTATE of the driver error, when the driver reports one."""
    value = getattr(exc.orig, "sqlstate", None)
    return value if isinstance(value, str) else None


def message_primary(exc: DBAPIError) -> str:
    """The primary message of the driver error (psycopg ``diag.message_primary``, else ``str``)."""
    diag = getattr(exc.orig, "diag", None)
    primary = getattr(diag, "message_primary", None)
    return primary if isinstance(primary, str) else str(exc.orig)


def erev_code(exc: DBAPIError) -> str | None:
    """The §14.1 error code of a ``P0001`` error whose message starts ``EREV-``, else None."""
    if sqlstate(exc) != RAISE_EXCEPTION:
        return None
    match = _ERROR_CODE.match(message_primary(exc).strip())
    return match.group(1) if match else None


def server_unavailable(exc: DBAPIError) -> bool:
    """True when ``exc`` says the server could not do it at that moment (DG-KRN-ERR-03 rev 1.97).

    With a SQLSTATE the set decides: class 53 and ``SERVER_UNAVAILABLE_STATES``. Without one
    nothing came from a server: the driver lost the connection or could not open it (its
    ``OperationalError``, or a connection SQLAlchemy found dead). Such an error is answered 503
    with ``Retry-After`` and is never recorded as the result of the work it interrupted.
    """
    state = sqlstate(exc)
    if state is not None:
        return state.startswith(SERVER_UNAVAILABLE_CLASS) or state in SERVER_UNAVAILABLE_STATES
    return bool(exc.connection_invalidated) or isinstance(exc, OperationalError)


def database_error_in(exc: BaseException) -> DBAPIError | None:
    """The first database error among ``exc``, its causes and its contexts, else None."""
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in seen):
        if isinstance(current, DBAPIError):
            return current
        seen.append(current)
        current = current.__cause__ or current.__context__
    return None


def server_unavailable_in(exc: BaseException) -> bool:
    """``server_unavailable`` of the database error ``exc`` is or was raised from, if any."""
    found = database_error_in(exc)
    return found is not None and server_unavailable(found)


def is_transient(exc: DBAPIError) -> bool:
    """Whether the work that met ``exc`` may succeed when it is done again (R-105 (2)).

    Deterministic are the classes of ``DETERMINISTIC_CLASSES``, the period guard's refusal
    excepted. Everything else is transient: the classes of ``TRANSIENT_CLASSES``, a class in
    neither table and an error for which the driver reports no SQLSTATE (a lost connection)."""
    state = sqlstate(exc)
    if state is None:
        return True
    if erev_code(exc) == PERIOD_GUARD:
        return True
    return state[:2] not in DETERMINISTIC_CLASSES


def pool_timeout_in(exc: BaseException) -> bool:
    """True when ``exc`` is, or was raised from, SQLAlchemy's pool timeout: the application's own
    connection pool gave no connection within its wait (DG-KRN-ERR-03 rev 1.127; supervisor ruling
    R-103 (c)). It is no database error - no statement reached a server - and it is the server's
    state, not a conflict with another command: 503 with ``Retry-After``."""
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in seen):
        if isinstance(current, PoolTimeoutError):
            return True
        seen.append(current)
        current = current.__cause__ or current.__context__
    return False

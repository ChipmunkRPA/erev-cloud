"""``db.errors.is_transient``: what a database error says about the work that met it (05 RCP-20
rev 1.82; dev-guide DG-CMD-09 rev 1.126; supervisor ruling R-105 (2)).

One table for the computation of a group (``compute_job.compute_group``), the mapping of database
errors to problems and the retry predicate of jobs: a transient error may not recur when the work
is done again and propagates; a deterministic one would recur and is stored as a FAILED
computation.
"""

from __future__ import annotations

from typing import Final

import pytest
from erev_api.db import errors
from sqlalchemy.exc import DBAPIError, OperationalError


class _Diag:
    def __init__(self, message: str) -> None:
        self.message_primary = message


class _Orig(Exception):
    def __init__(self, sqlstate: str | None, message: str = "") -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = _Diag(message)


def raised(sqlstate: str | None, message: str = "") -> DBAPIError:
    return DBAPIError("INSERT INTO erev.probe DEFAULT VALUES", {}, _Orig(sqlstate, message))


# SQLSTATE → what PostgreSQL means by it (Appendix A of its manual).
TRANSIENT: Final = {
    "08006": "connection_failure",
    "08P01": "protocol_violation",
    "25P02": "in_failed_sql_transaction",
    "40001": "serialization_failure",
    "40P01": "deadlock_detected",
    "53100": "disk_full",
    "53200": "out_of_memory",
    "53300": "too_many_connections",
    "55006": "object_in_use",
    "55P03": "lock_not_available",
    "57014": "query_canceled (statement timeout)",
    "57P01": "admin_shutdown",
    "57P03": "cannot_connect_now",
    "58030": "io_error",
    "72000": "snapshot_too_old",
    "XX000": "internal_error",
    "XX001": "data_corrupted",
}
DETERMINISTIC: Final = {
    "0A000": "feature_not_supported",
    "21000": "cardinality_violation",
    "22003": "numeric_value_out_of_range",
    "22P02": "invalid_text_representation",
    "23502": "not_null_violation",
    "23503": "foreign_key_violation",
    "23505": "unique_violation",
    "23514": "check_violation",
    "27000": "triggered_data_change_violation",
    "2F005": "function_executed_no_return_statement",
    "42501": "insufficient_privilege (a row-level-security refusal)",
    "42703": "undefined_column",
    "42P01": "undefined_table",
    "44000": "with_check_option_violation",
    "54000": "program_limit_exceeded",
    "P0001": "raise_exception",
    "P0002": "no_data_found",
}
# A class in neither table counts as transient (R-105 (2)).
UNLISTED: Final = {
    "01000": "warning",
    "0L000": "invalid_grantor",
    "28P01": "invalid_password",
    "3D000": "invalid_catalog_name",
    "F0000": "config_file_error",
    "HV000": "fdw_error",
}


def test_the_two_tables_are_disjoint_and_hold_the_ruled_classes() -> None:
    assert frozenset({"08", "25", "40", "53", "55", "57", "58", "72", "XX"}) == (
        errors.TRANSIENT_CLASSES
    )
    assert frozenset({"0A", "21", "22", "23", "27", "2F", "42", "44", "54", "P0"}) == (
        errors.DETERMINISTIC_CLASSES
    )
    assert not errors.TRANSIENT_CLASSES & errors.DETERMINISTIC_CLASSES
    assert {state[:2] for state in TRANSIENT} == set(errors.TRANSIENT_CLASSES)
    assert {state[:2] for state in DETERMINISTIC} == set(errors.DETERMINISTIC_CLASSES)
    assert not {state[:2] for state in UNLISTED} & (
        errors.TRANSIENT_CLASSES | errors.DETERMINISTIC_CLASSES
    )


@pytest.mark.parametrize("sqlstate", sorted(TRANSIENT))
def test_a_transient_class_propagates(sqlstate: str) -> None:
    assert errors.is_transient(raised(sqlstate, TRANSIENT[sqlstate])) is True


@pytest.mark.parametrize("sqlstate", sorted(DETERMINISTIC))
def test_a_deterministic_class_is_a_failure_of_the_work(sqlstate: str) -> None:
    assert errors.is_transient(raised(sqlstate, DETERMINISTIC[sqlstate])) is False


@pytest.mark.parametrize("sqlstate", sorted(UNLISTED))
def test_a_class_in_neither_table_is_transient(sqlstate: str) -> None:
    assert errors.is_transient(raised(sqlstate, UNLISTED[sqlstate])) is True


def test_an_error_without_a_sqlstate_is_transient() -> None:
    """A lost connection: the driver reports no SQLSTATE."""
    assert errors.is_transient(raised(None, "server closed the connection unexpectedly")) is True
    assert errors.is_transient(DBAPIError("SELECT 1", {}, RuntimeError("connection is closed")))


def test_the_period_guard_is_transient_and_every_other_trigger_is_not() -> None:
    """``EREV-LED-003`` (04 DB-07) is recognised by its §14.1 code in the message of a ``P0001``:
    the period closed after the posting was planned, and a new plan posts into the open period.
    The other triggers — immutability, seal, invariants — refuse the same work every time."""
    guard = raised(
        "P0001", "EREV-LED-003: period 0190 of entity 0191 is closed in book ASC606 (state closed)"
    )
    assert errors.erev_code(guard) == errors.PERIOD_GUARD == "EREV-LED-003"
    assert errors.is_transient(guard) is True
    for message in (
        "EREV-IMM-001 row is append-only",
        "EREV-LED-001: posting 0192 is not balanced",
        "EREV-LED-004: seal mismatch",
        "a plain RAISE EXCEPTION without a code",
    ):
        assert errors.is_transient(raised("P0001", message)) is False, message
    # the code is read from a P0001 only: the same text under another state decides nothing
    assert errors.is_transient(raised("23514", "EREV-LED-003: quoted in a check")) is False


def test_what_the_server_could_not_do_now_is_part_of_the_transient_table() -> None:
    """``server_unavailable`` (ruling R-53 (5)) names the errors answered 503: each of them is
    transient, with and without a SQLSTATE; a wrapped one is found through its cause."""
    for sqlstate in sorted(errors.SERVER_UNAVAILABLE_STATES) + ["53000", "53200", "53300"]:
        error = raised(sqlstate)
        assert errors.server_unavailable(error) and errors.is_transient(error), sqlstate
    lost = OperationalError("SELECT 1", {}, RuntimeError("server closed the connection"))
    assert errors.server_unavailable(lost) and errors.is_transient(lost)
    # transient without being the server's: a wait, a deadlock, a cancelled statement
    for sqlstate in ("55P03", "40P01", "40001", "57014"):
        error = raised(sqlstate)
        assert errors.is_transient(error) and not errors.server_unavailable(error), sqlstate
    try:
        try:
            raise raised("55P03")
        except DBAPIError as inner:
            raise RuntimeError("wrapped by the caller") from inner
    except RuntimeError as outer:
        found = errors.database_error_in(outer)
    assert found is not None and errors.is_transient(found)

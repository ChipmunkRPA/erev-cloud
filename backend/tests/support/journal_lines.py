"""A journal line that reaches a batch behind its guard (04 DB-16 rev 1.205; revision 0104;
supervisor ruling R-112 (b) (6)).

Since revision 0104 ``tg_journal_line__batch_draft`` refuses a line whose batch is not ``draft``,
so the application's database role can no longer put a line into an approved batch. The recount at
every exit of a batch (05 ADP-31; item JRN-DISPATCH-RECOUNT-1) and the deferred check of an
approved batch (DB-16) are the layers behind that guard, and their witnesses need the state the
guard prevents. ``guard_disabled`` gives it the only way left: the owner role disables that one
trigger, the application's role writes as it always did — every other trigger of the table fires,
and row-level security applies, which admits no row of a tenant to the owner role — and the owner
enables the trigger again when the block ends, whatever happened in it.

``run_guard_disabled`` does the same for the run's own guard of that revision (04 DB-07): a
journal run written beside a lock decision, which the guard now makes wait.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import journal_line
from sqlalchemy import insert
from support.db import TestDatabase

GUARD: Final = "tg_journal_line__batch_draft"


@contextmanager
def guard_disabled(database: TestDatabase) -> Iterator[None]:
    """``tg_journal_line__batch_draft`` disabled for the block and enabled again after it."""
    with database.owner_engine.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE erev.journal_line DISABLE TRIGGER {GUARD}")
    try:
        yield
    finally:
        with database.owner_engine.begin() as connection:
            connection.exec_driver_sql(f"ALTER TABLE erev.journal_line ENABLE TRIGGER {GUARD}")


def insert_behind_the_guard(
    database: TestDatabase, context: DbContext, values: Mapping[str, Any]
) -> None:
    """Insert the journal line ``values`` as the application's role in ``context``, past
    ``tg_journal_line__batch_draft``."""
    with guard_disabled(database), tenant_session(context) as session:
        session.execute(insert(journal_line).values(**dict(values)))


RUN_GUARD: Final = "tg_journal_run__period_guard"


@contextmanager
def run_guard_disabled(database: TestDatabase) -> Iterator[None]:
    """``tg_journal_run__period_guard`` (04 DB-07 rev 1.205; revision 0104; supervisor ruling
    R-97 (7)) disabled for the block and enabled again after it, by the owner role.

    Since that revision a journal run inserted or cancelled beside a lock decision waits for the
    decision's lock on the period's state row, and is refused once the period is closed. What
    stands behind the guard — the freeze's comparison of the period's runs before and after the
    datasets are produced (S15-R-18c) — is therefore witnessed only without it. The trigger is
    disabled before the decision starts: disabling it takes the table exclusively, which a
    decision in flight would make wait."""
    with database.owner_engine.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE erev.journal_run DISABLE TRIGGER {RUN_GUARD}")
    try:
        yield
    finally:
        with database.owner_engine.begin() as connection:
            connection.exec_driver_sql(f"ALTER TABLE erev.journal_run ENABLE TRIGGER {RUN_GUARD}")

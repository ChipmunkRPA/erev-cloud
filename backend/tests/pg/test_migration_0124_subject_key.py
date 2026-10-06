"""Revision 0124 over an empty and over a POPULATED ledger (item ENG-COST-READBACK-1; supervisor
ruling R-11 as amended on 2026-10-02 and its condition 1; 04 T-SL-04 ``subject_key`` rev 1.282 and
§18 rule 17; dev-guide DG-MIG-13 "A revision an earlier pre-release ledger cannot cross";
01-DECISIONS D-99 (3)).

The revision adds ``subledger_line.subject_key`` and backfills nothing: the subject of a posted
line cannot be derived from its row, a sealed line is never rewritten, and the key is a member of
the sealed line document. A table that already holds a line is therefore refused by name
(``EREV-MIG-0124``), with a sentence that says what the person does next — reset the database and
seed it anew. The question is asked through a constraint's validation scan, which reads every
physical row whatever row-level security hides from the owner connection (DG-MIG-13).

Both branches, in one walk that starts from a data-free head (``fresh_head``; FLMG-WALK-RESET-1):

1. an empty ledger: the revision applies — the column is there, nullable, of type text;
2. a ledger with lines: K-11 with its delivery of 120 units is computed through the product, which
   stores a subject on every line; the revision is taken back (its downgrade drops the column and
   leaves the lines — what a ledger written under the earlier schema holds) and applied again: it
   is REFUSED BY NAME and the whole revision rolls back — the version table still names the parent,
   the column is absent, the lines are as they were;
3. the database is reset, as the sentence says, and is at head again.

The DG-MIG-05 round trip (``test_migrations.py::test_upgrade_downgrade_upgrade``) walks an empty
database through the revision and back; this module leaves the database data-free at head.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import subledger_line
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from sqlalchemy import exc, func, select, text
from support.db import TestDatabase, alembic_config, fresh_head
from support.factories import computed, delivered_k11, k11_world

pytestmark = pytest.mark.pg

REVISION = "0124"
PARENT = "0129"
VERSION = text("SELECT version_num FROM erev.alembic_version")
COLUMN = text(
    "SELECT data_type, is_nullable FROM information_schema.columns "
    "WHERE table_schema = 'erev' AND table_name = 'subledger_line' AND column_name = 'subject_key'"
)
PROBE = text(
    "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_subledger_line__subject_key_probe'"
)
SENTENCE = (
    "EREV-MIG-0124: subledger_line holds lines written before revision 0124; the subject key of a "
    "posted line cannot be derived and a sealed line is never rewritten. A pre-release ledger does "
    "not cross this revision (01-DECISIONS D-99 (3)): reset the database and seed it anew"
)


def _head() -> str:
    """The chain's head: 0124 itself at its merge and a later revision since (the chain is in
    merge order, supervisor ruling R-68 (e)) — read from the script directory, so that the walk
    stays about 0124's column and refusal wherever the head stands."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert isinstance(head, str)
    return head


def _new_pools(test_database: TestDatabase) -> None:
    """The pooled connections belong to a schema that was dropped or altered (their statements
    name its type ids), so they go."""
    test_database.app_engine.dispose()
    test_database.owner_engine.dispose()


def test_0124_applies_to_an_empty_ledger_and_refuses_one_that_holds_a_line(
    test_database: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    # The descent must not meet rows earlier tests committed (DG-MIG-06): a data-free head first.
    fresh_head()
    _new_pools(test_database)
    owner = test_database.owner_engine
    # 1. an empty ledger: the revision applied, and the probe constraint is gone again
    with owner.connect() as connection:
        assert connection.execute(VERSION).scalar_one() == _head()
        assert connection.execute(COLUMN).one() == ("text", "YES")
        assert connection.execute(PROBE).scalar_one() == 0
    try:
        # 2. a ledger with lines, written through the product: every line stores its subject
        app = create_app(app_settings, clock=clock)
        world = k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
        booked = delivered_k11(world)
        computed(world.place, booked.combination_group["id"])
        count = select(func.count()).select_from(subledger_line)
        held = int(world.place.scalar(count))
        assert held >= 2
        assert world.place.scalar(count.where(subledger_line.c.subject_key.is_(None))) == 0
        # the revision taken back: the column goes, the lines stay — a ledger of the earlier schema
        test_database.app_engine.dispose()
        command.downgrade(alembic_config(), PARENT)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == PARENT
            assert connection.execute(COLUMN).one_or_none() is None
        # applied again over those lines: refused by name, and the whole revision rolls back
        with pytest.raises(exc.DBAPIError) as refused:
            command.upgrade(alembic_config(), "head")
        assert SENTENCE in str(refused.value.orig)
        owner.dispose()
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == PARENT
            assert connection.execute(COLUMN).one_or_none() is None
            assert connection.execute(PROBE).scalar_one() == 0
        test_database.app_engine.dispose()
        assert int(world.place.scalar(count)) == held  # nothing deleted, nothing rewritten
    finally:
        # 3. what the sentence tells the person to do: the database is reset, and is at head
        fresh_head()
        _new_pools(test_database)
    with owner.connect() as connection:
        assert connection.execute(VERSION).scalar_one() == _head()
        assert connection.execute(COLUMN).one() == ("text", "YES")

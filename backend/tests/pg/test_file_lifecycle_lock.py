"""The per-storage-key advisory lock that serialises upload, rewrap and shred of one object
(hosted runtime contract §"GCS immutable file and wrapped-key contract"; lane P2)."""

from __future__ import annotations

import pytest
from erev_api.db.session import identity_session
from erev_api.files.lifecycle import lock_storage_key, storage_key_lock_id
from sqlalchemy import text
from support.db import TestDatabase

pytestmark = pytest.mark.pg
KEY = "0191e0a0-0000-7000-8000-000000000001/ATTACHMENT/lock-probe"
OTHER = "0191e0a0-0000-7000-8000-000000000001/ATTACHMENT/other"
TRY_LOCK = text("SELECT pg_try_advisory_xact_lock(:lock_id)")


def test_p2_storage_key_lock_serialises_writers_of_one_key(test_database: TestDatabase) -> None:
    """Two writers are two sessions with a context (DG-KRN-DB-04): the holder's transaction owns
    the key's lock; a contender in its own transaction cannot take it until the holder ends."""
    with identity_session(request_id="tests-lock-holder") as holder:
        lock_storage_key(holder, KEY)
        with identity_session(request_id="tests-lock-contender") as contender:
            held = contender.execute(TRY_LOCK, {"lock_id": storage_key_lock_id(KEY)})
            assert held.scalar_one() is False, "a second writer waits for the same key"
            free = contender.execute(TRY_LOCK, {"lock_id": storage_key_lock_id(OTHER)})
            assert free.scalar_one() is True, "another key is not serialised behind it"
    with identity_session(request_id="tests-lock-after") as contender:
        released = contender.execute(TRY_LOCK, {"lock_id": storage_key_lock_id(KEY)})
        assert released.scalar_one() is True, "the lock ends with the holder's transaction"

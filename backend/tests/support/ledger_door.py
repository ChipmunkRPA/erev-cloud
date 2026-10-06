"""The ledger's one door as a test builder uses it (04 T-SL-04 ``subject_key`` rev 1.282; 05 RCP-05
rev 1.202; supervisor ruling R-11 as amended on 2026-10-02; item ENG-COST-READBACK-1).

``journals.subledger.post`` requires the subject key of every product caller
(``require_subject_key=True``). A test builder that posts through the door states no such
requirement, and its lines store no key; the read-back of posted amounts then answers the spelling
of decision L3-1-Q-32 for them. ``keyless`` makes the product's own commands post that way for one
test, so that a witness reads lines without a key that are otherwise exactly what the product
writes.
"""

from __future__ import annotations

from typing import Any

import pytest
from erev_api.domain.journals import subledger


def keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    """Until the test ends, every posting through the door stores its lines without
    ``subject_key`` and without the caller's requirement."""
    door = subledger.post

    def post(uow: Any, *, lines: Any, require_subject_key: bool = False, **rest: Any) -> Any:
        assert require_subject_key is True  # every product caller says so
        bare = [
            {name: value for name, value in line.items() if name != subledger.SUBJECT_KEY}
            for line in lines
        ]
        return door(uow, lines=bare, **rest)

    monkeypatch.setattr(subledger, "post", post)

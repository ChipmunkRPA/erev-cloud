"""API-R-55 search schemas: API-S-SearchResult (04 §16.13 rev 1.195; SCREENS R-01, §1.4; BUILD_SPEC
CTR-28)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from erev_api.enums import SearchScope


class SearchItemOut(BaseModel):
    """One found record. ``href`` is an API link (04 B3-D11): the record itself, and for an
    invoice the contract its lines name; ``status`` is the literal the scope's single read
    answers — E-17 of a contract, E-22 of an obligation, E-34 of a journal run — and null where
    the scope has none or the record cannot answer it yet."""

    id: uuid.UUID
    primary: str
    secondary: str
    status: str | None
    href: str


class SearchScopeOut(BaseModel):
    """The items of one E-120 scope, at most ``limit``; ``next_cursor`` continues the scope with
    the same ``q`` and is null when no further item of the caller's exists."""

    scope: SearchScope
    items: list[SearchItemOut]
    next_cursor: str | None


class SearchResultsOut(BaseModel):
    """``GET /search`` without ``scope``: one entry per E-120 scope, in E-120 order."""

    results: list[SearchScopeOut]

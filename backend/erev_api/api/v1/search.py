"""API-R-55 Search: ``GET /search`` over the E-120 scopes (04 §15.3 API-R-55, §16.13
API-S-SearchResult rev 1.195; dev-guide DG-LST-11; SCREENS R-01, §1.4; BUILD_SPEC CTR-28).

The cursor is the list kernel's (DG-LST-03): base64url of canonical JSON, bound to the trimmed
``q`` and the scope, so a cursor replayed with another query or scope is refused. It carries the
position of the last item — its tier, the instant its row was written and its id."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Final

from erev_engine.canonical import sha256_hex
from fastapi import APIRouter, Depends, Query

from erev_api.api.deps import API_PREFIX, GuardedRoute, KernelDeps, kernel_deps, problem_responses
from erev_api.api.lists import decode_cursor, encode_cursor
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.domain.contracts import search
from erev_api.enums import SearchScope
from erev_api.schemas.search import SearchItemOut, SearchResultsOut, SearchScopeOut

TAG: Final = "API-R-55 Search"
CURSOR_NEEDS_SCOPE: Final = "Send cursor together with scope."
CURSOR_INVALID: Final = "This cursor is not valid. Search again."

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _sort(scope: SearchScope) -> str:
    return f"search:{scope.value}"


def _bound_to(q: str, scope: SearchScope) -> str:
    return sha256_hex({"q": q, "scope": scope.value})


def _after(cursor: str, *, q: str, scope: SearchScope) -> search.After:
    """The position a cursor of this ``q`` and ``scope`` carries; 422 for any other cursor."""
    last = decode_cursor(cursor, sort=_sort(scope), filters_sha256=_bound_to(q, scope))
    try:
        tier, updated, item_id = last
        if not isinstance(tier, int) or isinstance(tier, bool):
            raise TypeError
        return tier, datetime.fromisoformat(str(updated)), uuid.UUID(str(item_id))
    except (TypeError, ValueError):
        raise search.invalid("cursor", CURSOR_INVALID) from None


def _scope_out(found: search.Found, *, q: str) -> SearchScopeOut:
    next_cursor = None
    if found.last is not None:
        tier, updated, item_id = found.last
        values: list[Any] = [tier, updated.isoformat(), str(item_id)]
        next_cursor = encode_cursor(_sort(found.scope), _bound_to(q, found.scope), values)
    return SearchScopeOut(
        scope=found.scope,
        items=[SearchItemOut.model_validate(item) for item in found.items],
        next_cursor=next_cursor,
    )


@router.get(
    "/search",
    operation_id="search",
    response_model=SearchScopeOut | SearchResultsOut,
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "validation-failed"
    ),
)
def search_records(
    ctx: Annotated[RequestContext, Depends(require(search.READ_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    q: Annotated[
        str,
        Query(description="2 to 200 characters after trimming, with a letter or digit"),
    ],
    scope: Annotated[
        SearchScope | None, Query(description="One E-120 scope. Default: every scope")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=search.MAX_LIMIT, description="Items for each scope")
    ] = search.DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(description="Only with scope")] = None,
) -> SearchScopeOut | SearchResultsOut:
    """Records whose ``primary`` or ``secondary`` holds a word that begins with each term of
    ``q``: with ``scope`` one page of that scope, without it the first page of every scope in
    E-120 order. A record the caller could not open is not answered and nothing counts it."""
    trimmed = search.checked(q)
    if cursor is not None and scope is None:
        raise search.invalid("cursor", CURSOR_NEEDS_SCOPE)
    after = None if cursor is None or scope is None else _after(cursor, q=trimmed, scope=scope)
    found = search.search(
        ctx, q=trimmed, scope=scope, limit=limit, after=after, now=deps.clock.now()
    )
    if scope is not None:
        return _scope_out(found[0], q=trimmed)
    return SearchResultsOut(results=[_scope_out(item, q=trimmed) for item in found])

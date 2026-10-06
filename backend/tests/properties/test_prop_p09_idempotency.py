"""P9 idempotency (dev-guide §9.7 row P9, §5.7 DG-KRN-IDEM-01 / IDEM-02; BUILD_SPEC PRP-5; 03
REQ-PLT-026).

CPU part: the request identity every command route keys its ``Idempotency-Key`` record on —
``erev_api.idempotency.store.request_sha256``, the canonical digest of {method, route, path
params, query, body} (DG-KRN-IDEM-02). A repeat of the same request is the same digest whatever
the JSON formatting, key order, method case or query insertion order; a different body, method,
route, path parameter or query value is a different digest; a multipart retry with another
boundary hashes its ``form`` and stays the same request (SPEC-Q-159).

The platform part — resubmitting an event command or an import with the same ``Idempotency-Key``
creates no new event, import row or subledger line and replays the original response (``begin`` /
``complete`` over the database, TXN-06) — is DB-bound and is NOT written here (DG-TST-07 keeps
database tests under ``tests/pg/``; ``tests/api/test_idempotency.py`` holds the route-level
cases); it is the open PRP-5 item once the lane databases exist.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import pytest
from erev_api.idempotency.store import request_sha256
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.property

JSON = "application/json"
METHODS = ("POST", "PUT", "PATCH", "DELETE")

_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.text(min_size=0, max_size=12),
)
_keys = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=10,
)
bodies = st.recursive(
    _scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4), st.dictionaries(_keys, children, max_size=4)
    ),
    max_leaves=12,
)
queries = st.dictionaries(_keys, st.lists(st.text(max_size=8), min_size=1, max_size=3), max_size=4)
path_params = st.dictionaries(_keys, st.text(min_size=1, max_size=12), max_size=3)


def _digest(
    method: str,
    route: str,
    params: Mapping[str, str],
    query: Mapping[str, Sequence[str]],
    body: object,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    text = json.dumps(body, indent=indent, sort_keys=sort_keys, ensure_ascii=False)
    return request_sha256(
        method=method,
        route_template=route,
        path_params=params,
        query=query,
        body=text.encode(),
        content_type=JSON,
    )


@pytest.mark.control("CTL-001")
@given(
    method=st.sampled_from(METHODS),
    route=st.sampled_from(("/contracts", "/contracts/{contract_id}/events", "/imports")),
    params=path_params,
    query=queries,
    body=bodies,
    indent=st.sampled_from((None, 2)),
)
def test_p09_same_request_same_digest(
    method: str,
    route: str,
    params: Mapping[str, str],
    query: Mapping[str, Sequence[str]],
    body: object,
    indent: int | None,
) -> None:
    """A repeat is the same request: formatting, key order, method case and query insertion order
    do not change the digest (DG-KRN-IDEM-02 canonical encoding).

    Of CTL-001's row (its second clause; 03 REQ-PLT-026, PROP:P9) this is what makes
    a repeat "the same key and payload": the request's digest.
    """
    reference = _digest(method, route, params, query, body)
    assert _digest(method, route, params, query, body) == reference
    assert _digest(method, route, params, query, body, indent=indent, sort_keys=True) == reference
    assert _digest(method.lower(), route, params, query, body) == reference
    reordered = dict(reversed(list(query.items())))
    assert _digest(method, route, params, reordered, body) == reference


@pytest.mark.control("CTL-001")
@given(
    method=st.sampled_from(METHODS),
    params=path_params,
    query=queries,
    body=st.dictionaries(_keys, _scalars, min_size=1, max_size=4),
    extra=st.text(min_size=1, max_size=6),
)
def test_p09_different_request_different_digest(
    method: str,
    params: Mapping[str, str],
    query: Mapping[str, Sequence[str]],
    body: Mapping[str, object],
    extra: str,
) -> None:
    """A changed body, method, route, path parameter or query value is another request.

    Of CTL-001's row (its second clause; 03 REQ-PLT-026, PROP:P9) this is what makes
    a reused key "a different payload".
    """
    route = "/contracts/{contract_id}/events"
    reference = _digest(method, route, params, query, body)
    changed = {**body, "__p09__": extra}
    assert _digest(method, route, params, query, changed) != reference
    other_method = next(item for item in METHODS if item != method)
    assert _digest(other_method, route, params, query, body) != reference
    assert _digest(method, route + "/x", params, query, body) != reference
    assert _digest(method, route, {**params, "__p09__": extra}, query, body) != reference
    assert _digest(method, route, params, {**query, "__p09__": [extra]}, body) != reference


@pytest.mark.control("CTL-001")
@given(
    fields=st.dictionaries(
        _keys, st.lists(st.text(max_size=8), min_size=1, max_size=2), max_size=3
    ),
    boundary_a=st.text(min_size=4, max_size=12),
    boundary_b=st.text(min_size=4, max_size=12),
)
def test_p09_multipart_retry_ignores_the_boundary(
    fields: Mapping[str, Sequence[str]], boundary_a: str, boundary_b: str
) -> None:
    """SPEC-Q-159: a multipart body hashes as its form, so a retry with another boundary (other
    raw bytes) is the same request.

    Of CTL-001's row (its second clause, PROP:P9): the retry of an upload is the
    same request although its raw bytes differ.
    """
    first = request_sha256(
        method="POST",
        route_template="/imports",
        path_params={},
        query={},
        body=f"--{boundary_a}\r\n".encode(),
        content_type=f"multipart/form-data; boundary={boundary_a}",
        form=fields,
    )
    second = request_sha256(
        method="POST",
        route_template="/imports",
        path_params={},
        query={},
        body=f"--{boundary_b}\r\n".encode(),
        content_type=f"multipart/form-data; boundary={boundary_b}",
        form=fields,
    )
    assert first == second

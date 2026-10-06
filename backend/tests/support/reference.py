"""Reference data through the RFD routes (BUILD_SPEC RFD-1, RFD-2; dev-guide DG-TST-16).

Tests create calendars, fiscal years and legal entities through ``POST /calendars``,
``generate-year`` and ``POST /entities`` rather than raw inserts. ``holding`` assigns a role, for
all entities or for named ones, and signs the member in to the workspace.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from erev_api.db.session import DbContext, tenant_session
from fastapi import FastAPI
from support.http import HttpResponse, call
from support.principals import Actor, Member, cookie_headers, sign_in, workspace
from support.rows import insert_role_assignment

CALENDARS = "/api/v1/calendars"
ENTITIES = "/api/v1/entities"
BOOKS = "/api/v1/books"
PERIODS = "/api/v1/periods"
PROBLEM_BASE = "https://erev.dev/problems/"


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def _headers(actor: Actor, *, key: bool, if_match: str | None) -> dict[str, str]:
    headers = cookie_headers(actor.token, actor.csrf_token, key=key)
    if if_match is not None:
        headers["If-Match"] = if_match
    return headers


def get(
    app: FastAPI, path: str, actor: Actor, params: Mapping[str, Any] | None = None
) -> HttpResponse:
    headers = cookie_headers(actor.token, key=False)
    return call(app, "GET", path, params=dict(params or {}), headers=headers)


def post(
    app: FastAPI,
    path: str,
    actor: Actor,
    json: Mapping[str, Any],
    *,
    if_match: str | None = None,
) -> HttpResponse:
    headers = _headers(actor, key=True, if_match=if_match)
    return call(app, "POST", path, json=dict(json), headers=headers)


def patch(
    app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any], *, if_match: str | None
) -> HttpResponse:
    headers = _headers(actor, key=True, if_match=if_match)
    return call(app, "PATCH", path, json=dict(json), headers=headers)


def put(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    headers = _headers(actor, key=True, if_match=None)
    return call(app, "PUT", path, json=dict(json), headers=headers)


def assign(someone: Member, role_code: str, *, entity_ids: Sequence[UUID] = ()) -> None:
    """Assign the tenant's role ``role_code`` for all entities, or for ``entity_ids``."""
    ctx = DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code=role_code,
            entity_ids=entity_ids,
        )


def holding(
    app: FastAPI, someone: Member, role_code: str, *, entity_ids: Sequence[UUID] = ()
) -> Actor:
    """Assign ``role_code``, then sign in to the workspace."""
    assign(someone, role_code, entity_ids=entity_ids)
    return workspace(app, someone, sign_in(app, someone.email))


def calendar(
    app: FastAPI, actor: Actor, *, code: str = "GREGORIAN", years: Sequence[int] = (2026,)
) -> str:
    """A monthly calendar starting in January with the named fiscal years; returns its id."""
    created = post(app, CALENDARS, actor, {"code": code, "name": f"{code} calendar"})
    assert created.status_code == 201, created.text
    calendar_id = str(created.json()["id"])
    for year in years:
        generated = post(
            app, f"{CALENDARS}/{calendar_id}/generate-year", actor, {"fiscal_year": year}
        )
        assert generated.status_code == 200, generated.text
    return calendar_id


def entity(
    app: FastAPI,
    actor: Actor,
    *,
    code: str,
    calendar_id: str,
    functional_currency: str = "USD",
    time_zone: str = "America/New_York",
    **extra: Any,
) -> dict[str, Any]:
    """``POST /entities``; returns the 201 body."""
    body = {
        "code": code,
        "name": f"{code} (Demo)",
        "functional_currency": functional_currency,
        "time_zone": time_zone,
        "calendar_id": calendar_id,
        **extra,
    }
    created = post(app, ENTITIES, actor, body)
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def periods(app: FastAPI, actor: Actor, **params: Any) -> list[dict[str, Any]]:
    """Every API-S-Period row of ``GET /periods`` under ``params``, in period order."""
    listed = get(app, PERIODS, actor, {"limit": 200, **params})
    assert listed.status_code == 200, listed.text
    items: list[dict[str, Any]] = listed.json()["items"]
    return items


# --- chart of accounts and account mappings (BUILD_SPEC RFD-6, RFD-7) ---------------------------

GL_ACCOUNTS = "/api/v1/gl-accounts"
ACCOUNT_MAPPINGS = "/api/v1/account-mappings"
APPROVALS = "/api/v1/approvals"


def delete(app: FastAPI, path: str, actor: Actor) -> HttpResponse:
    headers = _headers(actor, key=True, if_match=None)
    return call(app, "DELETE", path, headers=headers)


def gl_account(
    app: FastAPI,
    actor: Actor,
    *,
    code: str,
    name: str,
    account_type: str = "ASSET",
    normal_balance: str = "D",
    **extra: Any,
) -> str:
    """``POST /gl-accounts``; returns the account id."""
    body = {
        "code": code,
        "name": name,
        "account_type": account_type,
        "normal_balance": normal_balance,
        **extra,
    }
    created = post(app, GL_ACCOUNTS, actor, body)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def approve(app: FastAPI, request_id: str, approver: Actor) -> HttpResponse:
    """``POST /approvals/{id}/approve`` with the subject hash, and the impact preview hash when the
    request has a preview, that the request shows the approver (REQ-PLT-014, REQ-PLT-015)."""
    detail = get(app, f"{APPROVALS}/{request_id}", approver)
    assert detail.status_code == 200, detail.text
    request = detail.json()
    body = {"subject_content_sha256": request["subject"]["content_sha256"], "comment": "OK"}
    if request["impact_preview"] is not None:
        body["impact_preview_sha256"] = request["impact_preview"]["sha256"]
    return post(app, f"{APPROVALS}/{request_id}/approve", approver, body)


def reject(app: FastAPI, request_id: str, approver: Actor, comment: str) -> HttpResponse:
    """``POST /approvals/{id}/reject`` with the approver's comment."""
    return post(app, f"{APPROVALS}/{request_id}/reject", approver, {"comment": comment})


def assert_approval_hidden(
    app: FastAPI,
    request_id: str,
    outsider: Actor,
    *,
    reader: Actor,
) -> None:
    """The refusals 04 §16.10 rev 1.104 ("Entity scope of a request"; REQ-PLT-012) asks for a
    request the ``outsider`` cannot read — no step permission for any of its entities, not its
    preparer, not one of its deciders: 404 on the read, absence from the queue and from its count,
    and 404 on approve, reject and withdraw alike, with the very hashes ``reader`` (who
    legitimately sees the request) would send — whatever other role the outsider holds on the
    request's entity (supervisor ruling R-41 (8): no command confirms an id the read denies) — and
    a bulk item that reports 404 and no status. The caller asserts afterwards that nothing was
    decided."""
    shown = get(app, f"{APPROVALS}/{request_id}", reader)
    assert shown.status_code == 200, shown.text
    request = shown.json()
    hashes: dict[str, Any] = {"subject_content_sha256": request["subject"]["content_sha256"]}
    if request["impact_preview"] is not None:
        hashes["impact_preview_sha256"] = request["impact_preview"]["sha256"]

    hidden = get(app, f"{APPROVALS}/{request_id}", outsider)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    for params in ({}, {"assigned_to_me": "true"}, {"status": "PENDING"}):
        listed = get(app, APPROVALS, outsider, {**params, "count": "true"})
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert request_id not in [item["id"] for item in items], params
        if listed.json()["next_cursor"] is None:  # one page: the count is the page
            assert int(listed.headers["X-Erev-Total-Count"]) == len(items), params

    approved = post(
        app, f"{APPROVALS}/{request_id}/approve", outsider, {**hashes, "comment": "Not mine."}
    )
    assert (approved.status_code, slug(approved)) == (404, "not-found"), approved.text
    rejected = post(app, f"{APPROVALS}/{request_id}/reject", outsider, {"comment": "Not mine."})
    assert (rejected.status_code, slug(rejected)) == (404, "not-found"), rejected.text
    withdrawn = post(app, f"{APPROVALS}/{request_id}/withdraw", outsider, {})
    assert (withdrawn.status_code, slug(withdrawn)) == (404, "not-found"), withdrawn.text
    bulk = post(
        app,
        f"{APPROVALS}/bulk-approve",
        outsider,
        {"items": [{"approval_request_id": request_id, **hashes}]},
    )
    assert bulk.status_code == 200, bulk.text
    (result,) = bulk.json()["results"]
    assert result["status"] is None, result
    assert str(result["problem"]["type"]).removeprefix(PROBLEM_BASE) == "not-found", result

    unchanged = get(app, f"{APPROVALS}/{request_id}", reader)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["status"] == request["status"]
    assert [step["decisions"] for step in unchanged.json()["steps"]] == [
        step["decisions"] for step in request["steps"]
    ]


# --- products and bundle components (BUILD_SPEC RFD-9) -------------------------------------------

PRODUCTS = "/api/v1/products"


def new_product(
    app: FastAPI, actor: Actor, *, code: str, name: str, **extra: Any
) -> dict[str, Any]:
    """``POST /products``; returns the 201 body."""
    created = post(app, PRODUCTS, actor, {"code": code, "name": name, **extra})
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def mapping_draft(
    app: FastAPI,
    author: Actor,
    *,
    name: str,
    effective_from: str | None,
    rules: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """``POST /account-mappings`` and one ``POST …/rules`` per rule; returns the 201 body."""
    created = post(app, ACCOUNT_MAPPINGS, author, {"name": name, "effective_from": effective_from})
    assert created.status_code == 201, created.text
    version: dict[str, Any] = created.json()
    for rule in rules:
        added = post(app, f"{ACCOUNT_MAPPINGS}/{version['id']}/rules", author, rule)
        assert added.status_code == 201, added.text
    return version


def mapping_submitted(
    app: FastAPI,
    author: Actor,
    *,
    name: str,
    effective_from: str | None,
    rules: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """A draft that ``author`` tests and submits; returns the SUBMITTED version body."""
    version_id = mapping_draft(app, author, name=name, effective_from=effective_from, rules=rules)[
        "id"
    ]
    tested = post(app, f"{ACCOUNT_MAPPINGS}/{version_id}/test", author, {})
    assert tested.status_code == 200, tested.text
    submitted = post(app, f"{ACCOUNT_MAPPINGS}/{version_id}/submit", author, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    result: dict[str, Any] = submitted.json()
    return result


def mapping_published(
    app: FastAPI,
    author: Actor,
    approver: Actor,
    *,
    name: str,
    effective_from: str,
    rules: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """A version ``author`` submits and ``approver`` approves, which publishes it."""
    submitted = mapping_submitted(
        app, author, name=name, effective_from=effective_from, rules=rules
    )
    approved = approve(app, submitted["pending_approval_request_id"], approver)
    assert approved.status_code == 200, approved.text
    shown = get(app, f"{ACCOUNT_MAPPINGS}/{submitted['id']}", author)
    assert shown.status_code == 200, shown.text
    result: dict[str, Any] = shown.json()
    assert result["status"] == "PUBLISHED", result
    return result

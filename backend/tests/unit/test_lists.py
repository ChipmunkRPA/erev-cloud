"""List cursors and pages LST (dev-guide §6.3 DG-LST-01 to DG-LST-06 and DG-LST-08; 04 API-C-09;
PLF-8, PLF-16)."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from typing import Annotated, Any, cast

import pytest
import sqlalchemy as sa
from erev_api.api.lists import (
    COUNT_CAP,
    FilterSpec,
    ListParams,
    ListSpec,
    decode_cursor,
    encode_cursor,
    list_params,
    paginate,
)
from erev_api.db import new_id
from erev_api.db.session import DbContext
from erev_api.problems import Problem, install_handlers
from erev_engine.canonical import sha256_hex
from fastapi import Depends, FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from support.http import call


def test_dg_lst_03_cursor_round_trip() -> None:
    cursor = encode_cursor("-id", "f" * 64, ["0199a1b2-0000-7000-8000-000000000001"])
    assert "=" not in cursor
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    assert payload == {
        "f": "f" * 64,
        "k": ["0199a1b2-0000-7000-8000-000000000001"],
        "s": "-id",
        "v": 1,
    }
    assert decode_cursor(cursor, sort="-id", filters_sha256="f" * 64) == [
        "0199a1b2-0000-7000-8000-000000000001"
    ]


@pytest.mark.parametrize(
    ("cursor", "sort", "filters_sha256"),
    [
        (encode_cursor("-id", "f" * 64, ["a"]), "id", "f" * 64),
        (encode_cursor("-id", "f" * 64, ["a"]), "-id", "0" * 64),
        ("not base64 json", "-id", "f" * 64),
        (base64.urlsafe_b64encode(b'{"v": 2, "k": []}').decode(), "-id", "f" * 64),
    ],
)
def test_dg_lst_03_foreign_or_malformed_cursor(cursor: str, sort: str, filters_sha256: str) -> None:
    with pytest.raises(Problem) as excinfo:
        decode_cursor(cursor, sort=sort, filters_sha256=filters_sha256)
    assert excinfo.value.slug == "validation-failed"
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("cursor", "API-C-09")
    ]


def _probe_list(rows: int) -> tuple[sa.Select[Any], ListSpec]:
    """``rows`` probe rows: ids 1 to ``rows``, submitted one second apart, all PENDING."""
    series = (
        sa.func.generate_series(1, rows).table_valued(sa.column("n", sa.Integer)).render_derived()
    )
    probe = sa.select(
        series.c.n.label("id"),
        sa.func.to_timestamp(series.c.n, type_=sa.DateTime(timezone=True)).label("submitted_at"),
        sa.literal("PENDING", sa.Text).label("status"),
    ).subquery("probe")
    spec = ListSpec(
        resource="probes",
        sort_keys={"id": probe.c.id, "submitted_at": probe.c.submitted_at},
        default_sort="-id",
        filters={"status": FilterSpec(name="status", column=probe.c.status, kind="exact")},
    )
    return sa.select(probe.c.id, probe.c.submitted_at, probe.c.status), spec


def _params(**values: Any) -> ListParams:
    defaults: dict[str, Any] = {
        "limit": 2,
        "cursor": None,
        "sort": None,
        "q": None,
        "count": False,
        "filters": {},
    }
    return ListParams(**{**defaults, **values})


def _rule_errors(problem: Problem) -> list[tuple[str | None, str | None]]:
    return [(error.field, error.rule_id) for error in problem.errors]


def test_dg_lst_03_cursor_bound_to_sort_and_filters(db: Callable[[DbContext], Session]) -> None:
    session = db(DbContext(tenant_id=new_id(), user_id=None, entity_scope="*"))
    statement, spec = _probe_list(5)
    first = paginate(session, statement, spec, _params(sort="-submitted_at"))
    assert [item["id"] for item in first.items] == [5, 4]
    assert first.next_cursor is not None
    following = paginate(
        session, statement, spec, _params(sort="-submitted_at", cursor=first.next_cursor)
    )
    assert [item["id"] for item in following.items] == [3, 2]

    for foreign in (
        _params(sort="submitted_at", cursor=first.next_cursor),
        _params(sort="-submitted_at", cursor=first.next_cursor, filters={"status": ("PENDING",)}),
    ):
        with pytest.raises(Problem) as excinfo:
            paginate(session, statement, spec, foreign)
        assert excinfo.value.slug == "validation-failed"
        assert _rule_errors(excinfo.value) == [("cursor", "API-C-09")]

    app = FastAPI()
    install_handlers(app)

    @app.get("/probe")
    def probe(params: Annotated[ListParams, Depends(list_params)]) -> dict[str, int]:
        return {"limit": params.limit}

    assert call(app, "GET", "/probe?limit=500").json() == {"limit": 500}
    refused = call(app, "GET", "/probe?limit=501")
    assert refused.status_code == 422, refused.text
    assert refused.json()["type"] == "https://erev.dev/problems/validation-failed"
    assert [error["field"] for error in refused.json()["errors"]] == ["query.limit"]

    capped_statement, capped_spec = _probe_list(COUNT_CAP + 1)
    capped = paginate(session, capped_statement, capped_spec, _params(limit=1, count=True))
    assert capped.total_count == "100000+"
    exact_statement, exact_spec = _probe_list(COUNT_CAP)
    exact = paginate(session, exact_statement, exact_spec, _params(limit=1, count=True))
    assert exact.total_count == "100000"


def test_dg_lst_02_fixed_direction_and_filter_literals(db: Callable[[DbContext], Session]) -> None:
    session = db(DbContext(tenant_id=new_id(), user_id=None, entity_scope="*"))
    statement, spec = _probe_list(3)
    fixed = ListSpec(
        resource=spec.resource,
        sort_keys=spec.sort_keys,
        default_sort=spec.default_sort,
        filters={
            "status": FilterSpec(
                name="status",
                column=spec.filters["status"].column,
                kind="exact",
                choices=frozenset({"PENDING", "APPROVED"}),
            )
        },
        directions={"submitted_at": "desc"},
        custom_filters=frozenset({"assigned_to_me"}),
    )
    page = paginate(
        session,
        statement,
        fixed,
        _params(sort="submitted_at", filters={"assigned_to_me": ("true",), "status": ("PENDING",)}),
    )
    assert [item["id"] for item in page.items] == [3, 2]
    for refused, field in (
        (_params(sort="-submitted_at"), "sort"),
        (_params(filters={"status": ("OPEN",)}), "status"),
        (_params(filters={"unknown": ("x",)}), "unknown"),
    ):
        with pytest.raises(Problem) as excinfo:
            paginate(session, statement, fixed, refused)
        assert _rule_errors(excinfo.value) == [(field, "API-C-09")]


_ORDER = sa.MetaData()
_THING = sa.Table(
    "thing",
    _ORDER,
    sa.Column("tenant_id", sa.Uuid(), primary_key=True),
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("owner_id", sa.Uuid(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "status",
        postgresql.ENUM("OPEN", "DONE", name="thing_status", schema="erev", create_type=False),
        nullable=False,
    ),
)
_OWNER = sa.Table(
    "owner",
    _ORDER,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("name", sa.Text(), nullable=False),
)


class _Recorder:
    """Stands in for a session: keeps the statements ``paginate`` runs and answers no rows."""

    def __init__(self) -> None:
        self.statements: list[sa.Select[Any]] = []

    def execute(self, statement: sa.Select[Any]) -> _Recorder:
        self.statements.append(statement)
        return self

    def mappings(self) -> _Recorder:
        return self

    def all(self) -> list[Any]:
        return []


def _sql(
    keys: dict[str, sa.ColumnElement[Any]],
    sort: str,
    *,
    cursor: str | None = None,
    specs: dict[str, FilterSpec] | None = None,
    filters: dict[str, tuple[str, ...]] | None = None,
) -> str:
    """The statement ``paginate`` runs for ``sort`` over a list with the sort keys ``keys``,
    under the filter values ``filters`` of the filter specifications ``specs``."""
    spec = ListSpec(resource="things", sort_keys=keys, default_sort="-id", filters=specs or {})
    params = ListParams(
        limit=50, cursor=cursor, sort=sort, q=None, count=False, filters=filters or {}
    )
    recorder = _Recorder()
    paginate(cast(Session, recorder), sa.select(*keys.values()), spec, params)
    return " ".join(str(recorder.statements[-1].compile(dialect=postgresql.dialect())).split())


def _order_by(keys: dict[str, sa.ColumnElement[Any]], sort: str) -> str:
    found = re.search(r"ORDER BY (.*) LIMIT", _sql(keys, sort))
    assert found is not None
    return found.group(1)


def test_dg_lst_08_a_key_that_is_never_null_is_ordered_without_the_nulls_clause() -> None:
    """A NOT NULL column of the table the list's ``id`` belongs to: ``NULLS LAST`` would state
    the same order and keep every index from supplying it."""
    keys: dict[str, sa.ColumnElement[Any]] = {
        "id": _THING.c.id,
        "created_at": _THING.c.created_at,
    }
    assert _order_by(keys, "-created_at") == "thing.created_at DESC, thing.id DESC"
    assert _order_by(keys, "created_at") == "thing.created_at ASC, thing.id DESC"
    assert _order_by(keys, "-id") == "thing.id DESC"
    assert _order_by(keys, "id") == "thing.id ASC"
    # ... of an alias of the table as well, and under a label (the trail of a contract sorts by
    # the link's sequence and names the link's event id ``id``)
    other = _THING.alias("other")
    aliased: dict[str, sa.ColumnElement[Any]] = {
        "id": other.c.id.label("id"),
        "created_at": other.c.created_at,
    }
    assert _order_by(aliased, "-created_at") == "other.created_at DESC, id DESC"


def test_dg_lst_08_any_other_key_keeps_nulls_last() -> None:
    """A nullable column; a NOT NULL column of ANOTHER table, which an outer join leaves NULL
    whatever its definition; an expression; a column of a subquery, which is not looked into."""
    inner = sa.select(_THING).subquery("inner")
    cases: list[tuple[sa.ColumnElement[Any], sa.ColumnElement[Any], str]] = [
        (_THING.c.closed_at, _THING.c.id, "thing.closed_at DESC NULLS LAST, thing.id DESC"),
        (_OWNER.c.name, _THING.c.id, "owner.name DESC NULLS LAST, thing.id DESC"),
        (
            sa.func.coalesce(_THING.c.closed_at, _THING.c.created_at),
            _THING.c.id,
            "coalesce(thing.closed_at, thing.created_at) DESC NULLS LAST, thing.id DESC",
        ),
        (inner.c.created_at, inner.c.id, '"inner".created_at DESC NULLS LAST, "inner".id DESC'),
    ]
    for key, row_id, expected in cases:
        assert _order_by({"id": row_id, "key": key}, "-key") == expected
    ascending = _order_by({"id": _THING.c.id, "key": _THING.c.closed_at}, "key")
    assert ascending == "thing.closed_at ASC NULLS LAST, thing.id DESC"


def test_dg_lst_08_the_cursor_comparison_is_the_same_for_every_key() -> None:
    """Leaving the clause out changes the ORDER BY alone: a page after a cursor is bounded as
    before, for a key that is never NULL as for one that may be."""
    last = ["2026-09-12T12:00:00+00:00", "0199a1b2-0000-7000-8000-000000000001"]
    for key in (_THING.c.created_at, _THING.c.closed_at):
        keys: dict[str, sa.ColumnElement[Any]] = {"id": _THING.c.id, "key": key}
        filters_sha256 = sha256_hex({"filters": {}, "q": None})
        sql = _sql(keys, "-key", cursor=encode_cursor("-key", filters_sha256, last))
        name = f"thing.{key.name}"
        assert f"{name} < CAST(" in sql and f"{name} = CAST(" in sql and f"{name} IS NULL" in sql


def test_dg_lst_04_an_enumeration_literal_is_bound_as_a_value_of_its_column() -> None:
    """A filter value that is one of the spec's enumeration literals is a constant of the column's
    type when the statement is planned: PostgreSQL proves a partial index on a status from it
    (DG-KRN-DB-10). Text cast to the enumeration when the statement runs — the form of every other
    filter value — is no constant, and a list by status entered no partial index."""
    keys: dict[str, sa.ColumnElement[Any]] = {"id": _THING.c.id}
    specs = {
        "status": FilterSpec(
            name="status",
            column=_THING.c.status,
            kind="exact",
            choices=frozenset({"OPEN", "DONE"}),
        ),
        "owner_id": FilterSpec(name="owner_id", column=_THING.c.owner_id, kind="exact"),
        "from": FilterSpec(name="from", column=_THING.c.created_at, kind="from"),
    }

    def where(**filters: tuple[str, ...]) -> str:
        sql = _sql(keys, "-id", specs=specs, filters=filters)
        found = re.search(r"WHERE (.*) ORDER BY", sql)
        assert found is not None
        return found.group(1)

    assert where(status=("OPEN",)) == "thing.status = %(param_1)s"
    assert where(status=("OPEN", "DONE")) == "thing.status IN (%(param_1)s, %(param_2)s)"
    # ... and a value that is no enumeration literal is cast as before
    owner = "0199a1b2-0000-7000-8000-000000000001"
    assert where(owner_id=(owner,)) == "thing.owner_id = CAST(%(param_1)s AS UUID)"
    since = where(**{"from": ("2026-09-01T00:00:00Z",)})
    assert since == "thing.created_at >= CAST(%(param_1)s AS TIMESTAMP WITH TIME ZONE)"

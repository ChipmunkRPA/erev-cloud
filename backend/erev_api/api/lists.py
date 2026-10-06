"""Lists: keyset pagination, filtering and sorting LST (docs/dev-guide.md §6.3; 04 API-C-09).

``paginate`` orders by one catalogue sort key, NULLs last, and then ``id`` descending (API-C-09 rev
1.2), and continues after the cursor's last values. A key that is never NULL is ordered without
the ``NULLS LAST`` clause, which states the same order and would keep every index from supplying
it (DG-LST-08). A catalogue key with a stated direction (for
example approvals ``amount``, largest first) takes no ``-`` prefix. The cursor is base64url of
canonical JSON ``{"v": 1, "s": sort, "f": filters_sha256, "k": last_values}``, so a cursor replayed
with another sort or filter set is refused (DG-LST-03). Filters a resource applies itself, such as
approvals ``assigned_to_me``, are named in ``ListSpec.custom_filters`` and still bind the cursor.
RLS scopes every page.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from uuid import UUID

import sqlalchemy as sa
from erev_engine.canonical import canonical_bytes, sha256_hex
from fastapi import Query, Request
from sqlalchemy.orm import Session

from erev_api.problems import Problem, ProblemError

RULE_ID: Final = "API-C-09"
DEFAULT_LIMIT: Final = 50
MAX_LIMIT: Final = 500
COUNT_CAP: Final = 100_000
TOTAL_COUNT_HEADER: Final = "X-Erev-Total-Count"
RESERVED_PARAMETERS: Final = frozenset({"limit", "cursor", "sort", "q", "count"})
# PRD ERR-05.
_DETAIL: Final = "1 field needs attention."
_CURSOR_INVALID: Final = "This cursor is not valid. Reload the list."


@dataclass(frozen=True, slots=True)
class FilterSpec:
    name: str
    column: sa.ColumnElement[Any]
    kind: Literal["exact", "in", "min", "max", "from", "to", "bool"]
    choices: frozenset[str] | None = None  # enumeration literals; any other value is 422


@dataclass(frozen=True, slots=True)
class ListSpec:
    resource: str
    sort_keys: Mapping[str, sa.ColumnElement[Any]]  # API-R catalogue sort keys, including "id"
    default_sort: str  # "-id"
    filters: Mapping[str, FilterSpec]
    search_columns: tuple[sa.ColumnElement[Any], ...] = ()
    # Catalogue keys whose direction the catalogue states; they refuse the "-" prefix.
    directions: Mapping[str, Literal["asc", "desc"]] = field(default_factory=dict)
    # Filters the resource applies to the statement itself; paginate accepts and hashes them.
    custom_filters: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ListParams:
    limit: int
    cursor: str | None
    sort: str | None
    q: str | None
    count: bool
    filters: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class ListResult:
    items: list[Mapping[str, Any]]
    next_cursor: str | None
    total_count: str | None  # the X-Erev-Total-Count value when count=true


def invalid(field: str, message: str) -> Problem:
    """422 ``validation-failed`` on one list parameter, rule API-C-09."""
    return Problem(
        "validation-failed",
        _DETAIL,
        errors=[ProblemError(field=field, rule_id=RULE_ID, message=message)],
    )


def list_params(
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    sort: str | None = None,
    q: str | None = None,
    count: bool = False,
) -> ListParams:
    """The list parameters of a request; every other query parameter is a filter (DG-LST-04)."""
    filters: dict[str, list[str]] = {}
    for name, value in request.query_params.multi_items():
        if name not in RESERVED_PARAMETERS:
            filters.setdefault(name, []).append(value)
    return ListParams(
        limit=limit,
        cursor=cursor,
        sort=sort,
        q=q,
        count=count,
        filters={name: tuple(values) for name, values in filters.items()},
    )


def encode_cursor(sort: str, filters_sha256: str, last_values: Sequence[Any]) -> str:
    payload = canonical_bytes({"v": 1, "s": sort, "f": filters_sha256, "k": list(last_values)})
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str, *, sort: str, filters_sha256: str) -> list[Any]:
    """The cursor's last values; 422 ``validation-failed`` for a malformed or foreign cursor."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (binascii.Error, ValueError):
        raise invalid("cursor", _CURSOR_INVALID) from None
    if (
        not isinstance(payload, dict)
        or payload.get("v") != 1
        or not isinstance(payload.get("k"), list)
    ):
        raise invalid("cursor", _CURSOR_INVALID)
    if payload.get("s") != sort or payload.get("f") != filters_sha256:
        raise invalid("cursor", "This cursor belongs to another sort or filter. Reload the list.")
    return list(payload["k"])


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _check_values(spec: FilterSpec, values: tuple[str, ...]) -> None:
    """Unknown literals and malformed ids are 422, never a database error (XR-12)."""
    for value in values:
        if spec.choices is not None and value not in spec.choices:
            raise invalid(
                spec.name, f"{spec.name} must be one of {', '.join(sorted(spec.choices))}."
            )
        if spec.kind != "bool" and isinstance(spec.column.type, sa.Uuid):
            try:
                UUID(value)
            except ValueError:
                raise invalid(spec.name, f"{spec.name} must be an id.") from None


def _value(spec: FilterSpec, value: str) -> sa.ColumnElement[Any]:
    """A filter value as the statement compares it. An enumeration literal — one of
    ``spec.choices``, checked before — is bound as a value of the column's type: a constant when
    the statement is planned, from which PostgreSQL proves a partial index on that status or kind
    (DG-KRN-DB-10). Any other value is text cast to the column's type, which is converted only
    when the statement runs — ``status = CAST(:text AS <enum>)`` is no constant and enters no
    partial index."""
    if spec.choices is not None:
        return sa.literal(value, type_=spec.column.type)
    return sa.cast(sa.literal(value), spec.column.type)


def _filter_clause(spec: FilterSpec, values: tuple[str, ...]) -> sa.ColumnElement[bool]:
    _check_values(spec, values)
    column = spec.column
    if spec.kind == "in" or (spec.kind == "exact" and len(values) > 1):
        return column.in_([_value(spec, value) for value in values])
    if len(values) != 1:
        raise invalid(spec.name, f"Send {spec.name} once.")
    (value,) = values
    if spec.kind == "bool":
        if value not in {"true", "false"}:
            raise invalid(spec.name, f"{spec.name} must be true or false.")
        return column.is_(value == "true")
    bound = _value(spec, value)
    match spec.kind:
        case "exact":
            return column == bound
        case "min" | "from":
            return column >= bound
        case "max":
            return column <= bound
        case _:
            return column < bound


def _bound(value: Any, column: sa.ColumnElement[Any]) -> sa.ColumnElement[Any]:
    if not isinstance(value, str):
        raise invalid("cursor", _CURSOR_INVALID)
    return sa.cast(sa.literal(value), column.type)


def _after(
    column: sa.ColumnElement[Any],
    id_column: sa.ColumnElement[Any],
    last: Sequence[Any],
    *,
    by_id: bool,
    descending: bool,
) -> sa.ColumnElement[bool]:
    """Rows after the cursor under ``ORDER BY column NULLS LAST, id DESC`` — the order of
    ``_ordering`` for every key, whether or not the clause is written."""
    if by_id:
        bound = _bound(last[0], id_column)
        return id_column < bound if descending else id_column > bound
    value, last_id = last
    earlier_id = id_column < _bound(last_id, id_column)
    if value is None:
        return sa.and_(column.is_(None), earlier_id)
    bound = _bound(value, column)
    beyond = column < bound if descending else column > bound
    return sa.or_(beyond, sa.and_(column == bound, earlier_id), column.is_(None))


def _never_null(column: sa.ColumnElement[Any], id_column: sa.ColumnElement[Any]) -> bool:
    """Whether ``column`` holds a value in every row of the list: a NOT NULL column of the very
    table (or alias of a table) the list's ``id`` belongs to, each possibly under a label. A
    column of another table may be NULL through an outer join whatever its definition, and an
    expression or a column of a subquery is not looked into."""
    key = column.element if isinstance(column, sa.Label) else column
    row_id = id_column.element if isinstance(id_column, sa.Label) else id_column
    if not isinstance(key, sa.Column) or not isinstance(row_id, sa.Column):
        return False
    source: sa.FromClause = key.table
    if source is not row_id.table or key.nullable is not False:
        return False
    if isinstance(source, sa.Alias):
        source = source.element
    return isinstance(source, sa.Table)


def _ordering(
    column: sa.ColumnElement[Any],
    id_column: sa.ColumnElement[Any],
    *,
    by_id: bool,
    descending: bool,
) -> list[sa.ColumnElement[Any]]:
    """DG-LST-01, DG-LST-08: the key, then ``id`` descending as the tie-breaker; nulls last in
    either direction. For a key that is never NULL the clause is left out: it states the same
    order, and without it a b-tree read backwards supplies ``DESC`` — an index yields ``DESC
    NULLS FIRST``, so ``DESC NULLS LAST`` sorts the whole filtered set before the limit."""
    if by_id:
        return [id_column.desc() if descending else id_column.asc()]
    keyed = column.desc() if descending else column.asc()
    if not _never_null(column, id_column):
        keyed = keyed.nulls_last()
    return [keyed, id_column.desc()]


def paginate(
    session: Session, stmt: sa.Select[Any], spec: ListSpec, params: ListParams
) -> ListResult:
    """One page of ``stmt`` under ``params`` (DG-LST-01 to DG-LST-07)."""
    sort = params.sort or spec.default_sort
    key = sort.removeprefix("-")
    if key not in spec.sort_keys:
        raise invalid("sort", f"Sort by one of {', '.join(sorted(spec.sort_keys))}.")
    fixed = spec.directions.get(key)
    if fixed is not None and sort != key:
        raise invalid("sort", f"Sort by {key} without a leading -; its order is fixed.")
    descending = fixed == "desc" if fixed is not None else sort.startswith("-")
    unknown = sorted(set(params.filters) - set(spec.filters) - spec.custom_filters)
    if unknown:
        raise invalid(unknown[0], f"{unknown[0]} is not a filter of {spec.resource}.")
    for name, values in sorted(params.filters.items()):
        if name in spec.filters:
            stmt = stmt.where(_filter_clause(spec.filters[name], values))
    if params.q:
        if not spec.search_columns:
            raise invalid("q", f"{spec.resource} has no search.")
        pattern = f"%{_escape_like(params.q)}%"
        stmt = stmt.where(
            sa.or_(*(column.ilike(pattern, escape="\\") for column in spec.search_columns))
        )
    total_count: str | None = None
    if params.count:
        capped = session.execute(
            sa.select(sa.func.count()).select_from(stmt.limit(COUNT_CAP + 1).subquery())
        ).scalar_one()
        total_count = f"{COUNT_CAP}+" if capped > COUNT_CAP else str(capped)
    filters_sha256 = sha256_hex(
        {"filters": {name: list(values) for name, values in params.filters.items()}, "q": params.q}
    )
    column = spec.sort_keys[key]
    id_column = spec.sort_keys["id"]
    by_id = key == "id"
    if params.cursor is not None:
        last = decode_cursor(params.cursor, sort=sort, filters_sha256=filters_sha256)
        if len(last) != (1 if by_id else 2):
            raise invalid("cursor", _CURSOR_INVALID)
        stmt = stmt.where(_after(column, id_column, last, by_id=by_id, descending=descending))
    ordering = _ordering(column, id_column, by_id=by_id, descending=descending)
    rows = session.execute(stmt.order_by(*ordering).limit(params.limit + 1)).mappings().all()
    items: list[Mapping[str, Any]] = [dict(row) for row in rows[: params.limit]]
    next_cursor = None
    if len(rows) > params.limit:
        last_row = rows[params.limit - 1]
        last_values: list[str | None] = []
        if not by_id:
            value = last_row[column]
            last_values.append(None if value is None else str(value))
        last_values.append(str(last_row[id_column]))
        next_cursor = encode_cursor(sort, filters_sha256, last_values)
    return ListResult(items=items, next_cursor=next_cursor, total_count=total_count)

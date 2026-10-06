"""CSV v2 framework: NC-19 flattening, row models and command plans (04 NC-19, T-IMP-01; 05 IPL-03
to IPL-05, IPL-07, IPL-10; BUILD_SPEC DIN-3).

``flatten`` turns a command request model into template columns: nested objects become dotted
names (``customer.code``, ``lines.total_price.amount``) and the ``lines`` array becomes one row per
line with the header members repeated. A column is required when its field and every enclosing
field are required. ``unflatten`` rebuilds the nested request from a row's non-blank cells.

[J] L5-1-Q-4:
- Members that hold arrays or free-form objects other than ``lines`` (``payment_schedule``,
  ``noncash_consideration``, ``consideration_payable``, ``custom_attributes``,
  ``account_overrides``) have no single-row form and are not columns.
- Column types, which pick the DIN-1 cell coercion: ``date`` for dates, ``quantity`` for members
  named ``quantity``, ``amount`` for members named ``amount``, else ``text``; the command model
  validates the rest when the plan is built.
- The seeded ``import_template.headers`` of a CSV v2 template stay empty (L4-1-Q-26); validation
  takes the flattened columns (``effective``).
"""

from __future__ import annotations

import types
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model

from erev_api.domain.imports import templates
from erev_api.enums import ApprovalSubjectType, SourceObjectType, SourceSystem

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

__all__ = [
    "Applied",
    "ContractChange",
    "CsvColumn",
    "CsvRow",
    "CsvTemplate",
    "Performed",
    "Plan",
    "Repeated",
    "UNEVALUATED",
    "Underlying",
    "effective",
    "flatten",
    "grouped",
    "header_cells",
    "line_cells",
    "row_model",
    "unflatten",
]

LINES: Final = "lines"
SKIPPED_OBJECTS: Final = frozenset({"custom_attributes", "account_overrides"})
ColumnType = Literal["text", "amount", "quantity", "date"]


@dataclass(frozen=True, slots=True)
class CsvColumn:
    name: str
    type: ColumnType
    required: bool


@dataclass(frozen=True, slots=True)
class CsvRow:
    """One validated data row of an upload (T-IMP-03)."""

    id: UUID
    sheet_name: str
    row_number: int
    raw: Mapping[str, Any]
    normalized: Mapping[str, Any]
    business_key: str | None


@dataclass(frozen=True, slots=True)
class Plan:
    """One command of the file: its key, its rows in file order and its request members."""

    key: str
    rows: tuple[CsvRow, ...]
    body: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Repeated:
    """Cells that several rows of a file repeat (04 NC-19 "the header members repeated"; 05 IPL-05
    rev 1.210; item IMPORT-HEADER-CELL-CONFLICT-1): the rows whose ``key`` cells are equal — the
    rows of one object, or of one line of it — state each of ``cells`` once, and the emitter
    reads it from the FIRST of those rows. A later row that states another value states what the
    import would not store, and validation refuses it there (``validate.repeated_conflicts``).
    ``group`` is what the finding calls those rows ("mapping version") and ``named_by`` the key
    columns whose cells name them."""

    group: str
    key: tuple[str, ...]
    cells: tuple[str, ...]
    named_by: tuple[str, ...]


def grouped(rows: Sequence[CsvRow], key: Sequence[str]) -> dict[tuple[str, ...], list[CsvRow]]:
    """The rows by the text of their ``key`` cells, in worksheet order; a blank cell reads ""."""
    found: dict[tuple[str, ...], list[CsvRow]] = {}
    for row in rows:
        found.setdefault(tuple(str(row.normalized.get(name) or "") for name in key), []).append(row)
    return found


def header_cells(columns: Sequence[CsvColumn], key: Sequence[str]) -> tuple[str, ...]:
    """The cells the rows of one object repeat: every column that is not a line's and not of the
    object's ``key``."""
    return tuple(
        column.name
        for column in columns
        if not column.name.startswith(f"{LINES}.") and column.name not in key
    )


def line_cells(
    columns: Sequence[CsvColumn], key: Sequence[str], *, own: Sequence[str] = ()
) -> tuple[str, ...]:
    """The cells the rows of one line repeat: every column of a line that is not of the line's
    ``key`` and not one a row states for itself (``own``: a name, or a prefix ending in a dot)."""
    return tuple(
        column.name
        for column in columns
        if column.name.startswith(f"{LINES}.")
        and column.name not in key
        and not any(
            column.name == name or (name.endswith(".") and column.name.startswith(name))
            for name in own
        )
    )


@dataclass(slots=True)
class Applied:
    """What one plan emitted: lineage targets per row and the contracts it changed."""

    targets: list[tuple[str, UUID]] = field(default_factory=list)  # (target_type, id), all rows
    row_targets: dict[UUID, list[tuple[str, UUID]]] = field(default_factory=dict)
    contracts: list[tuple[str, UUID, UUID, int | None]] = field(default_factory=list)
    # (external_id, contract id, combination group id, stream head before the plan or None)
    # Supervisor ruling R-98 (4): False when a computation the plan ran did not SUCCEED (it is
    # stored QUARANTINED or FAILED, not raised — DG-CMD-09). The stored version is then not the
    # plan's, so no figure read from it is the plan's either.
    computed: bool = True


@dataclass(frozen=True, slots=True)
class ContractChange:
    """What one dry-run plan did to a contract, in the contract currency (05 IPL-07): the figures
    the thresholds of an underlying approval read (ruling R-38 (ii))."""

    currency: str
    transaction_price_before: Decimal  # 0 for a contract the plan books
    transaction_price_after: Decimal
    # the sum over the obligations of cumulative revenue after the plan less before it: 04
    # API-S-ImpactSummary ``catch_up_total``
    catch_up_total: Decimal


@dataclass(frozen=True, slots=True)
class Performed:
    """One approval the commit of a plan performs by itself, with the routing facts a request of
    the underlying subject would carry on its own path (supervisor rulings R-38 (ii) and R-98;
    item IMP-FLOOR-AMOUNT-1; 04 §16.6 rev 1.147 ``diff_summary.underlying_approvals``)."""

    # The subject's routing flags of the plan's content, as the subject's own flags function
    # states them; None = the file does not let them be evaluated, so a second step of that
    # subject counts as applying.
    flags: frozenset[str] | None
    # The functional amount that request would carry as its ``amount``, with its currency; None
    # = it would carry none (a subject without an amount; an activation whose rate to the
    # entity's functional currency is not published — 04 §16.10 rev 1.287).
    amount: tuple[Decimal, str] | None = None
    # False: the dry run cannot state the amount — it counts as the strictest outcome of a rule
    # that reads it, as unevaluated flags do.
    amount_evaluated: bool = True


# An approval the commit performs of which the dry run can state nothing: a plan that failed, a
# computation that did not succeed.
UNEVALUATED: Final = Performed(flags=None, amount=None, amount_evaluated=False)

# Ruling R-38 (ii); 04 §16.6 rev 1.147 ``diff_summary.underlying_approvals``. The approvals the
# commit of one plan performs by itself, read in the dry run while the plan's objects exist:
# (session, plan, applied, context, the changes by contract external id) -> per approval subject
# one ``Performed`` for every approval of that subject the plan's commit performs.
type Underlying = Callable[
    [Session, Plan, Applied, ApplyContext, Mapping[str, ContractChange]],
    Mapping[ApprovalSubjectType, Sequence[Performed]],
]


@dataclass(frozen=True, slots=True)
class CsvTemplate:
    """A template emitter: its code, target, columns, key column and command services. The legacy
    v1 emitters (BUILD_SPEC DIN-4 to DIN-6) use the same shape with ``source_system``
    ``LEGACY_TEMPLATE_V1`` and no columns."""

    code: str
    object_type: SourceObjectType
    target_type: str
    key_column: str
    columns: tuple[CsvColumn, ...]
    plans: Callable[[Sequence[CsvRow]], list[Plan]]
    apply: Callable[..., Applied]  # (uow, plan, *, context) -> Applied
    source_system: SourceSystem = SourceSystem.CSV_V2
    # R-38 (ii): set by exactly the templates whose commit performs an approval-coded act
    # (``imports.scope.TEMPLATE_SCOPES`` ``puts_in_force``); a unit test keeps the two equal.
    underlying: Underlying | None = None
    # dev-guide DG-KRN-DB-08 (1c) rev 1.218 (finding F4 of the independent review of 2026-10-01):
    # set by the templates whose ``apply`` computes the plan's contract group in the transaction
    # (legacy progress and modifications). The first plan that posts takes the book's chain head,
    # so the windows of every contract the plans name are held before the first plan
    # (``diff.hold_plan_windows``).
    computes: bool = False
    # The columns whose cells make ONE object of several rows — what ``plans`` groups by; empty
    # for a template each of whose rows is an object of its own. And the cells those rows, or
    # the rows of one line, repeat (``Repeated``; 05 IPL-05 rev 1.210). A unit test holds that no
    # column of a template with a ``group_key`` stands outside its key, its repeated cells and
    # the cells a row states for itself.
    group_key: tuple[str, ...] = ()
    repeats: tuple[Repeated, ...] = ()


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """The annotation without ``Annotated`` and ``None``; True when ``None`` was a member."""
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _unwrap(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType):
        members = [item for item in typing.get_args(annotation) if item is not type(None)]
        optional = len(members) != len(typing.get_args(annotation))
        if len(members) == 1:
            inner, _ = _unwrap(members[0])
            return inner, optional
        return annotation, optional
    return annotation, False


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _column_type(name: str, annotation: Any) -> ColumnType:
    leaf = name.rsplit(".", 1)[-1]
    if annotation is date:
        return "date"
    if leaf == "quantity":
        return "quantity"
    if leaf == "amount":
        return "amount"
    return "text"


def flatten(model: type[BaseModel], *, prefix: str = "", required: bool = True) -> list[CsvColumn]:
    """NC-19 columns of ``model`` in field order."""
    columns: list[CsvColumn] = []
    for name, info in model.model_fields.items():
        dotted = f"{prefix}{name}"
        annotation, optional = _unwrap(info.annotation)
        here = required and info.is_required() and not optional
        origin = typing.get_origin(annotation)
        if _is_model(annotation):
            columns += flatten(annotation, prefix=f"{dotted}.", required=here)
            continue
        if origin in (tuple, list):
            items = [item for item in typing.get_args(annotation) if item is not Ellipsis]
            item = _unwrap(items[0])[0] if items else None
            if name == LINES and not prefix and _is_model(item):
                columns += flatten(
                    cast("type[BaseModel]", item), prefix=f"{dotted}.", required=True
                )
            continue
        if origin is dict or annotation is dict or name in SKIPPED_OBJECTS:
            continue
        columns.append(CsvColumn(name=dotted, type=_column_type(dotted, annotation), required=here))
    return columns


def headers(columns: Sequence[CsvColumn]) -> tuple[templates.Header, ...]:
    """The T-IMP-01 ``headers`` entries of the columns."""
    rules = {
        "text": ("REQUIRED_VALUE_BLANK",),
        "amount": ("REQUIRED_VALUE_BLANK", "VALUE_NOT_NUMERIC"),
        "quantity": ("REQUIRED_VALUE_BLANK", "VALUE_NOT_NUMERIC"),
        "date": ("REQUIRED_VALUE_BLANK", "DATE_INVALID"),
    }
    return tuple(
        templates.Header(
            name=column.name,
            type=column.type,
            required=column.required,
            rule_ids=rules[column.type] if column.required else rules[column.type][1:],
        )
        for column in columns
    )


def effective(
    template: templates.Template, registry: Mapping[str, CsvTemplate]
) -> templates.Template:
    """``template`` with the flattened columns of a registered CSV v2 template as headers."""
    found = registry.get(template.code)
    if template.family != "CSV_V2" or found is None or template.headers:
        return template
    return replace(template, headers=headers(found.columns))


_PYTHON: Final[Mapping[str, Any]] = {"text": str, "amount": Any, "quantity": Any, "date": date}


def row_model(class_name: str, columns: Sequence[CsvColumn]) -> type[BaseModel]:
    """A frozen row model whose fields carry the dotted column names as aliases."""
    fields: dict[str, Any] = {}
    for index, column in enumerate(columns):
        python_type: Any = _PYTHON[column.type]
        annotation: Any = python_type if column.required else python_type | None
        fields[f"column_{index}"] = (
            annotation,
            Field(... if column.required else None, alias=column.name),
        )
    return create_model(
        class_name, __config__=ConfigDict(extra="forbid", frozen=True, strict=False), **fields
    )


def unflatten(values: Mapping[str, Any], *, skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    """The nested request members of dotted ``values``; blank cells are left out."""
    nested: dict[str, Any] = {}
    for name, value in values.items():
        if value is None or value == "" or name.split(".", 1)[0] in skip:
            continue
        parts = name.split(".")
        target = nested
        for part in parts[:-1]:
            child = target.setdefault(part, {})
            target = child
        target[parts[-1]] = value
    return nested


@dataclass(frozen=True, slots=True)
class ApplyContext:
    """The upload a plan belongs to, and whether the apply is a dry run (IPL-07). A commit also
    names the import number, the original file name, the upload parameters, the uploader, the
    approval request and its approver (BUILD_SPEC DIN-4, BS3-D-23)."""

    import_upload_id: UUID
    file_sha256: str
    template_code: str
    template_version: int
    dry_run: bool
    record_ids: Mapping[UUID, UUID] = field(
        default_factory=dict
    )  # import_row id → source_record id
    import_no: str = ""
    original_filename: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    uploader_id: UUID | None = None
    approval_request_id: UUID | None = None
    approver_id: UUID | None = None
    # Per approval subject the commit performs, the approver who answered for it by ordinal
    # (``imports.scope.answering_approvers``; ruling R-98 (9) as refined, 04 §16.10 rev 1.198).
    answered_by: Mapping[ApprovalSubjectType, UUID] = field(default_factory=dict)
    # DG-KRN-APR-05 rev 1.51 (D-98 candidate 119): the composition of the consumed import approval
    # a commit carries into the hooks it drives (contract activation, BR-DAT-06); None on a dry run.
    consumed: Any | None = None

    def approver_of(self, subject_type: ApprovalSubjectType) -> UUID | None:
        """The person an act of ``subject_type`` names as its approver: the one who answered for
        that approval of the commit — the request's last approver where the commit states none,
        and nobody for an automatic approval."""
        return self.answered_by.get(subject_type, self.approver_id)


def plan_rows(plans: Sequence[Plan]) -> int:
    return sum(len(plan.rows) for plan in plans)


def uow_now(uow: UnitOfWork) -> Any:  # pragma: no cover - small accessor kept for typing
    return uow.now

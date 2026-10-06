"""Reference area queries (dev-guide DG-LAY-04, DG-CMD-13): fiscal calendars and their periods
(04 API-R-18, T-REF-04, T-REF-05; BUILD_SPEC RFD-1); GL accounts and dimensions (04 API-R-20,
API-R-21, T-REF-13, T-REF-16, T-REF-17; BUILD_SPEC RFD-6); legal entities, books and period states
(04 API-R-17, API-R-18, T-REF-01 to T-REF-03, T-REF-06, API-S-Period; BUILD_SPEC RFD-2); customers
and related-party groups (04 API-R-22, T-REF-18, T-REF-19, §16.14; BUILD_SPEC RFD-8); account
mapping versions, their rules and account resolution (04 API-R-20, T-REF-14, T-REF-15; BUILD_SPEC
RFD-7); products and bundle components (04 API-R-23, T-REF-20, T-REF-21; BUILD_SPEC RFD-9).

Every read runs in the principal's context, so row-level security limits entities, entity books and
period states to the principal's entity scope, and an id outside it reads as 404 (API-C-03)."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Protocol
from uuid import UUID

from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    approval_request,
    book,
    currency,
    customer,
    dimension_definition,
    dimension_value,
    entity_book,
    fiscal_calendar,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    legal_entity,
    period,
    period_state,
    product,
    product_bundle_component,
    related_party_group,
    tenant,
    tenant_currency,
)
from erev_api.domain.platform import actors
from erev_api.domain.reference import fx, mapping, products
from erev_api.domain.reference import periods as period_rules
from erev_api.enums import (
    AccountRole,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ClearingPurpose,
    PeriodState,
)
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext

CALENDAR_COLUMNS: Final = (
    fiscal_calendar.c.id,
    fiscal_calendar.c.code,
    fiscal_calendar.c.name,
    fiscal_calendar.c.pattern,
    fiscal_calendar.c.fiscal_year_start_month,
    fiscal_calendar.c.week_end_day,
    fiscal_calendar.c.year_end_anchor,
    fiscal_calendar.c.created_at,
    fiscal_calendar.c.updated_at,
    fiscal_calendar.c.row_version,
)
PERIOD_COLUMNS: Final = (
    period.c.id,
    period.c.period_key,
    period.c.name,
    period.c.fiscal_year,
    period.c.period_no,
    period.c.quarter_no,
    period.c.start_date,
    period.c.end_date,
)


def list_calendars[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the tenant's calendars; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*CALENDAR_COLUMNS))


def calendar_row(session: Session, calendar_id: UUID) -> Mapping[str, Any] | None:
    """The T-REF-04 row visible to ``session``, or None."""
    statement = select(*CALENDAR_COLUMNS).where(fiscal_calendar.c.id == calendar_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def fiscal_year_periods(
    session: Session, calendar_id: UUID, fiscal_year: int
) -> list[Mapping[str, Any]]:
    """The periods of one fiscal year of a calendar, in period order."""
    statement = (
        select(*PERIOD_COLUMNS)
        .where(period.c.calendar_id == calendar_id, period.c.fiscal_year == fiscal_year)
        .order_by(period.c.period_no)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


GL_ACCOUNT_COLUMNS: Final = (
    gl_account.c.id,
    gl_account.c.code,
    gl_account.c.name,
    gl_account.c.account_type,
    gl_account.c.normal_balance,
    gl_account.c.entity_ids,
    gl_account.c.required_dimensions,
    gl_account.c.source_system,
    gl_account.c.is_active,
    gl_account.c.created_at,
    gl_account.c.updated_at,
    gl_account.c.row_version,
)
DIMENSION_COLUMNS: Final = (
    dimension_definition.c.id,
    dimension_definition.c.code,
    dimension_definition.c.name,
    dimension_definition.c.is_builtin,
    dimension_definition.c.position,
    dimension_definition.c.is_active,
    dimension_definition.c.created_at,
    dimension_definition.c.updated_at,
    dimension_definition.c.row_version,
)
DIMENSION_VALUE_COLUMNS: Final = (
    dimension_value.c.id,
    dimension_value.c.dimension_definition_id,
    dimension_value.c.code,
    dimension_value.c.name,
    dimension_value.c.parent_value_id,
    dimension_value.c.is_active,
    dimension_value.c.created_at,
    dimension_value.c.updated_at,
    dimension_value.c.row_version,
)


def list_gl_accounts[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the tenant's GL accounts; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*GL_ACCOUNT_COLUMNS))


def gl_account_row(session: Session, account_id: UUID) -> Mapping[str, Any] | None:
    """The T-REF-13 row visible to ``session``, or None."""
    statement = select(*GL_ACCOUNT_COLUMNS).where(gl_account.c.id == account_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def get_gl_account(ctx: RequestContext, account_id: UUID) -> Mapping[str, Any]:
    """``GET /gl-accounts/{id}``; 404 ``not-found`` for an account the caller cannot see."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = gl_account_row(session, account_id)
    if row is None:
        raise Problem("not-found")
    return row


def list_dimensions[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the tenant's dimensions, built-in ones included."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*DIMENSION_COLUMNS))


def dimension_row(session: Session, dimension_id: UUID) -> Mapping[str, Any] | None:
    """The T-REF-16 row visible to ``session``, or None."""
    statement = select(*DIMENSION_COLUMNS).where(dimension_definition.c.id == dimension_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def list_dimension_values[T](
    ctx: RequestContext, code: str, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the stored values of dimension ``code``; 404 ``not-found`` for an unknown
    dimension. Product and customer store no values, so their pages are empty (T-REF-17)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        definition = select(dimension_definition.c.id).where(dimension_definition.c.code == code)
        definition_id = session.execute(definition).scalar_one_or_none()
        if definition_id is None:
            raise Problem("not-found")
        statement = select(*DIMENSION_VALUE_COLUMNS).where(
            dimension_value.c.dimension_definition_id == definition_id
        )
        return page(session, statement)


def dimension_value_row(session: Session, value_id: UUID) -> Mapping[str, Any] | None:
    """The T-REF-17 row visible to ``session``, or None."""
    statement = select(*DIMENSION_VALUE_COLUMNS).where(dimension_value.c.id == value_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


# --- customers and related-party groups (BUILD_SPEC RFD-8) --------------------------------------

CUSTOMER_COLUMNS: Final = (
    customer.c.id,
    customer.c.code,
    customer.c.name,
    customer.c.related_party_group_id,
    customer.c.parent_customer_id,
    customer.c.credit_grade,
    customer.c.segment,
    customer.c.country_code,
    customer.c.source_system,
    customer.c.external_id,
    customer.c.is_active,
    customer.c.created_at,
    customer.c.updated_at,
    customer.c.row_version,
)
RELATED_PARTY_GROUP_COLUMNS: Final = (
    related_party_group.c.id,
    related_party_group.c.code,
    related_party_group.c.name,
    related_party_group.c.description,
    related_party_group.c.created_at,
    related_party_group.c.updated_at,
    related_party_group.c.row_version,
)
_GROUP_CODE: Final = "related_party_group_code"
_GROUP_NAME: Final = "related_party_group_name"


def customer_select() -> Select[Any]:
    """T-REF-19 rows with the code and name of their related-party group."""
    joined = customer.outerjoin(
        related_party_group,
        and_(
            related_party_group.c.tenant_id == customer.c.tenant_id,
            related_party_group.c.id == customer.c.related_party_group_id,
        ),
    )
    return select(
        *CUSTOMER_COLUMNS,
        related_party_group.c.code.label(_GROUP_CODE),
        related_party_group.c.name.label(_GROUP_NAME),
    ).select_from(joined)


def customer_out(row: Mapping[Any, Any]) -> dict[str, Any]:
    """An API-R-22 customer: the row, with ``related_party_group`` as API-S-Ref or null."""
    item = {str(key): value for key, value in row.items()}
    code, name = item.pop(_GROUP_CODE, None), item.pop(_GROUP_NAME, None)
    group_id = item["related_party_group_id"]
    item["related_party_group"] = (
        None if group_id is None else {"id": group_id, "code": code, "name": name}
    )
    return item


def list_customers[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the tenant's customers; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, customer_select())


def customer_row(session: Session, customer_id: UUID) -> dict[str, Any] | None:
    """The API-R-22 customer visible to ``session``, or None."""
    statement = customer_select().where(customer.c.id == customer_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else customer_out(row)


def get_customer(ctx: RequestContext, customer_id: UUID) -> dict[str, Any]:
    """``GET /customers/{id}``; 404 ``not-found`` for a customer the caller cannot see."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = customer_row(session, customer_id)
    if row is None:
        raise Problem("not-found")
    return row


def related_party_group_select() -> Select[Any]:
    """T-REF-18 rows with ``member_count``: the customers of the group, active or not (§16.14;
    L1-1-Q-39)."""
    members = (
        select(func.count())
        .select_from(customer)
        .where(
            customer.c.tenant_id == related_party_group.c.tenant_id,
            customer.c.related_party_group_id == related_party_group.c.id,
        )
        .scalar_subquery()
    )
    return select(*RELATED_PARTY_GROUP_COLUMNS, members.label("member_count"))


def list_related_party_groups[T](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the tenant's related-party groups with their member counts."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, related_party_group_select())


def related_party_group_row(session: Session, group_id: UUID) -> dict[str, Any] | None:
    """The API-R-22 related-party group visible to ``session``, or None."""
    statement = related_party_group_select().where(related_party_group.c.id == group_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


# --- products and bundle components (BUILD_SPEC RFD-9) -------------------------------------------

PRODUCT_COLUMNS: Final = (
    product.c.id,
    product.c.code,
    product.c.sku_number,
    product.c.name,
    product.c.product_family,
    product.c.revenue_category,
    product.c.default_pob_template_id,
    product.c.disaggregation,
    product.c.principal_agent,
    product.c.distinctness_default,
    product.c.unit_of_measure,
    product.c.is_bundle,
    product.c.assurance_cost_per_unit,
    product.c.is_franchisor_preopening_service,
    product.c.policy_values,
    product.c.is_active,
    product.c.created_at,
    product.c.updated_at,
    product.c.row_version,
)
BUNDLE_COMPONENT_COLUMNS: Final = (
    product_bundle_component.c.id,
    product_bundle_component.c.component_product_id,
    product_bundle_component.c.quantity_per_bundle,
    product_bundle_component.c.split_basis,
    product_bundle_component.c.split_ratio,
    product_bundle_component.c.sequence,
    product_bundle_component.c.valid_from,
    product_bundle_component.c.valid_to,
    product_bundle_component.c.created_at,
    product_bundle_component.c.updated_at,
    product_bundle_component.c.row_version,
)
_COMPONENT_CODE: Final = "component_code"
_COMPONENT_NAME: Final = "component_name"


def product_select() -> Select[Any]:
    """T-REF-20 rows with the id of their PENDING ``PRINCIPAL_AGENT_CHANGE`` request."""
    pending = (
        select(approval_request.c.id)
        .where(
            approval_request.c.subject_type == ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE.value,
            approval_request.c.subject_id == product.c.id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
        .limit(1)
        .scalar_subquery()
    )
    return select(*PRODUCT_COLUMNS, pending.label("pending_approval_request_id"))


def product_out(
    row: Mapping[Any, Any],
    mandatory: Sequence[str],
    series: Collection[UUID] = (),
    *,
    frozen: Collection[UUID],
) -> dict[str, Any]:
    """An API-R-23 product: the row with API-C-06 decimal text, ``usability`` and the two derived
    read-only members — ``requires_explicit_ssp_basis`` (``series`` holds the ids
    ``products.series_product_ids`` returned for the page; SSP-ADMISSION-R1) and ``code_frozen``
    (``frozen`` holds the ids ``products.code_holders`` names for the page; DB-05)."""
    item = {str(key): value for key, value in row.items()}
    item["assurance_cost_per_unit"] = products.exact_text(item["assurance_cost_per_unit"])
    item["usability"] = products.usability_of(
        is_active=bool(item["is_active"]),
        disaggregation=dict(item["disaggregation"]),
        mandatory=mandatory,
    )
    item["requires_explicit_ssp_basis"] = UUID(str(item["id"])) in series
    item["code_frozen"] = UUID(str(item["id"])) in frozen
    return item


def list_products[T: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the tenant's products; ``page`` applies the list parameters. The derived
    members are read for the page at once (DG-LST-10)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, product_select())
        mandatory = products.mandatory_attributes(session)
        ids = [UUID(str(item["id"])) for item in result.items]
        series = products.series_product_ids(session, ids)
        frozen = products.code_holders(session, ids)
        return result, [
            product_out(item, mandatory, series, frozen=frozen) for item in result.items
        ]


def product_row(session: Session, product_id: UUID) -> dict[str, Any] | None:
    """The API-R-23 product visible to ``session``, or None."""
    row = session.execute(product_select().where(product.c.id == product_id)).mappings().first()
    if row is None:
        return None
    series = products.series_product_ids(session, [product_id])
    frozen = products.code_holders(session, [product_id])
    return product_out(row, products.mandatory_attributes(session), series, frozen=frozen)


def get_product(ctx: RequestContext, product_id: UUID) -> dict[str, Any]:
    """``GET /products/{id}``; 404 ``not-found`` for a product the caller cannot see."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = product_row(session, product_id)
    if row is None:
        raise Problem("not-found")
    return row


def bundle_components_of(session: Session, product_id: UUID) -> dict[str, Any]:
    """Every T-REF-21 row of the bundle with its component as API-S-Ref, in ``valid_from``, then
    ``sequence`` order."""
    component = product.alias("component")
    joined = product_bundle_component.join(
        component,
        and_(
            component.c.tenant_id == product_bundle_component.c.tenant_id,
            component.c.id == product_bundle_component.c.component_product_id,
        ),
    )
    statement = (
        select(
            *BUNDLE_COMPONENT_COLUMNS,
            component.c.code.label(_COMPONENT_CODE),
            component.c.name.label(_COMPONENT_NAME),
        )
        .select_from(joined)
        .where(product_bundle_component.c.bundle_product_id == product_id)
        .order_by(
            product_bundle_component.c.valid_from,
            product_bundle_component.c.sequence,
            product_bundle_component.c.id,
        )
    )
    items: list[dict[str, Any]] = []
    for row in session.execute(statement).mappings():
        item = {str(key): value for key, value in row.items()}
        code, name = item.pop(_COMPONENT_CODE), item.pop(_COMPONENT_NAME)
        item["component_product"] = {"id": item["component_product_id"], "code": code, "name": name}
        item["quantity_per_bundle"] = products.exact_text(item["quantity_per_bundle"])
        item["split_ratio"] = products.exact_text(item["split_ratio"])
        items.append(item)
    return {"bundle_product_id": product_id, "components": items}


def get_bundle_components(ctx: RequestContext, product_id: UUID) -> dict[str, Any]:
    """``GET /products/{id}/bundle-components``; 404 ``not-found`` for an unknown product."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        found = session.execute(select(product.c.id).where(product.c.id == product_id)).first()
        if found is None:
            raise Problem("not-found")
        return bundle_components_of(session, product_id)


# --- legal entities, books and period states (BUILD_SPEC RFD-2) ---------------------------------


class Page(Protocol):
    """A list page: ``api.lists.ListResult`` (domain code does not import ``api``)."""

    @property
    def items(self) -> list[Mapping[str, Any]]: ...


ENTITY_COLUMNS: Final = (
    legal_entity.c.id,
    legal_entity.c.code,
    legal_entity.c.name,
    legal_entity.c.functional_currency,
    legal_entity.c.time_zone,
    legal_entity.c.calendar_id,
    legal_entity.c.parent_entity_id,
    legal_entity.c.country_code,
    legal_entity.c.tax_id,
    legal_entity.c.is_active,
    legal_entity.c.created_at,
    legal_entity.c.updated_at,
    legal_entity.c.row_version,
)
ENTITY_BOOK_COLUMNS: Final = (
    entity_book.c.id,
    entity_book.c.entity_id,
    entity_book.c.book_code,
    entity_book.c.first_period_id,
    period.c.period_key.label("first_period_key"),
    period.c.start_date.label("first_period_start_date"),
    entity_book.c.is_enabled,
    entity_book.c.created_at,
    entity_book.c.updated_at,
    entity_book.c.row_version,
)
BOOK_COLUMNS: Final = (
    book.c.id,
    book.c.code,
    book.c.name,
    book.c.is_primary,
    book.c.is_enabled,
    book.c.posting_target,
    book.c.created_at,
    book.c.updated_at,
    book.c.row_version,
)
PERIOD_COLUMNS_OF_STATE: Final = (
    period_state.c.id,
    period_state.c.book_code,
    period_state.c.state,
    period_state.c.state_changed_at,
    period_state.c.row_version,
    # The `period_end_date` sort key: a full page reads it for its keyset cursor (RFD-19).
    period_state.c.period_end_date,
    legal_entity.c.id.label("entity_id"),
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.name.label("entity_name"),
    period.c.id.label("period_id"),
    period.c.period_key,
    period.c.name.label("period_name"),
    period.c.fiscal_year,
    period.c.period_no,
    period.c.quarter_no,
    period.c.start_date,
    period.c.end_date,
)


def entity_book_select() -> Select[Any]:
    """T-REF-03 rows with the key and start date of their first period."""
    joined = entity_book.join(
        period,
        and_(
            period.c.tenant_id == entity_book.c.tenant_id,
            period.c.id == entity_book.c.first_period_id,
        ),
    )
    return select(*ENTITY_BOOK_COLUMNS).select_from(joined)


def entity_books(session: Session, entity_ids: Sequence[Any]) -> dict[UUID, list[dict[str, Any]]]:
    """The books each entity keeps, in E-02 order."""
    if not entity_ids:
        return {}
    statement = (
        entity_book_select()
        .where(entity_book.c.entity_id.in_(list(entity_ids)))
        .order_by(entity_book.c.entity_id, entity_book.c.book_code)
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in session.execute(statement).mappings():
        found.setdefault(UUID(str(row["entity_id"])), []).append(dict(row))
    return found


def with_books(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    books = entity_books(session, [row["id"] for row in rows])
    return [{**row, "books": books.get(UUID(str(row["id"])), [])} for row in rows]


def list_entities[T: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the entities in the principal's scope, each with the books it keeps."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(*ENTITY_COLUMNS))
        return result, with_books(session, result.items)


def entity_row(session: Session, entity_id: UUID) -> dict[str, Any] | None:
    """The T-REF-01 row visible to ``session`` with its books, or None."""
    statement = select(*ENTITY_COLUMNS).where(legal_entity.c.id == entity_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else with_books(session, [dict(row)])[0]


def get_entity(ctx: RequestContext, entity_id: UUID) -> dict[str, Any]:
    """``GET /entities/{id}``; 404 ``not-found`` for an entity outside the principal's scope."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = entity_row(session, entity_id)
    if row is None:
        raise Problem("not-found")
    return row


def entity_book_row(session: Session, entity_id: UUID, book_code: str) -> dict[str, Any] | None:
    statement = entity_book_select().where(
        entity_book.c.entity_id == entity_id, entity_book.c.book_code == book_code
    )
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def list_books[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """The tenant's three books."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*BOOK_COLUMNS))


def book_row(session: Session, book_code: str) -> dict[str, Any] | None:
    statement = select(*BOOK_COLUMNS).where(book.c.code == book_code)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def primary_book_code(session: Session) -> str:
    """The code of the tenant's primary book (API-C-11 default ``book``)."""
    found = session.execute(select(book.c.code).where(book.c.is_primary.is_(True))).scalar()
    return BookCode.ASC606.value if found is None else str(found)


def period_select() -> Select[Any]:
    """API-S-Period rows: period states joined to their period and entity.

    [J] ``is_first_open``: the state is ``open`` and no earlier period of the same entity and book
    is ``open`` (the ``ix_period_state__open`` lookup; L1-1-Q-16).

    ``follows_book_code`` and ``follows_state`` (04 §16.8 rev 1.155; supervisor rulings R-112 (e)
    and R-114 (d)): for a row of the LEGACY book the tenant's primary book and the state of that
    book's period for the same entity — the close the LEGACY period follows; null for a row of a
    posting book. The row's own state is not rewritten.
    """
    followed = period_state.alias("followed_state")
    is_legacy = period_state.c.book_code == BookCode.LEGACY.value
    # row-level security leaves the tenant's own books: one of them is primary (T-REF-02)
    primary_book = select(book.c.code).where(book.c.is_primary.is_(True)).scalar_subquery()
    primary_state = (
        select(followed.c.state)
        .where(
            followed.c.tenant_id == period_state.c.tenant_id,
            followed.c.entity_id == period_state.c.entity_id,
            followed.c.period_id == period_state.c.period_id,
            followed.c.book_code == primary_book,
        )
        .scalar_subquery()
    )
    earlier = period_state.alias("earlier_open")
    first_open = and_(
        period_state.c.state == PeriodState.OPEN.value,
        ~exists().where(
            earlier.c.tenant_id == period_state.c.tenant_id,
            earlier.c.entity_id == period_state.c.entity_id,
            earlier.c.book_code == period_state.c.book_code,
            earlier.c.state == PeriodState.OPEN.value,
            earlier.c.period_end_date < period_state.c.period_end_date,
        ),
    )
    joined = period_state.join(
        period,
        and_(
            period.c.tenant_id == period_state.c.tenant_id, period.c.id == period_state.c.period_id
        ),
    ).join(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == period_state.c.tenant_id,
            legal_entity.c.id == period_state.c.entity_id,
        ),
    )
    return select(
        *PERIOD_COLUMNS_OF_STATE,
        first_open.label("is_first_open"),
        case((is_legacy, primary_book), else_=None).label("follows_book_code"),
        case((is_legacy, primary_state), else_=None).label("follows_state"),
    ).select_from(joined)


def period_out(row: Mapping[Any, Any]) -> dict[str, Any]:
    """API-S-Period of one ``period_select`` row (04 §16.8)."""
    return {
        "id": row["id"],
        "entity": {"id": row["entity_id"], "code": row["entity_code"], "name": row["entity_name"]},
        "book": row["book_code"],
        "period": {
            "id": row["period_id"],
            "period_key": row["period_key"],
            "name": row["period_name"],
            "fiscal_year": row["fiscal_year"],
            "period_no": row["period_no"],
            "quarter_no": row["quarter_no"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
        },
        "state": row["state"],
        "state_changed_at": row["state_changed_at"],
        "is_first_open": bool(row["is_first_open"]),
        "current_lock": None,
        "dataset_lock": None,
        "blockers": period_rules.blockers(),
        "close_run": None,
        "row_version": row["row_version"],
        "follows": None
        if row["follows_book_code"] is None
        else {"book_code": row["follows_book_code"], "state": row["follows_state"]},
    }


def list_periods[T: Page](
    ctx: RequestContext,
    *,
    entities: Sequence[str],
    book_code: str | None,
    fiscal_year: int | None,
    page: Callable[[Session, Select[Any]], T],
) -> tuple[T, list[dict[str, Any]]]:
    """One page of API-S-Period rows (API-C-11): ``entities`` are codes or ids, and ``book``
    defaults to the primary book."""
    ids: list[UUID] = []
    codes: list[str] = []
    for value in entities:
        try:
            ids.append(UUID(value))
        except ValueError:
            codes.append(value)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        statement = period_select().where(
            period_state.c.book_code == (book_code or primary_book_code(session))
        )
        if entities:
            statement = statement.where(
                or_(legal_entity.c.id.in_(ids), legal_entity.c.code.in_(codes))
            )
        if fiscal_year is not None:
            statement = statement.where(period.c.fiscal_year == fiscal_year)
        result = page(session, statement)
        return result, [period_out(row) for row in result.items]


def period_row(session: Session, state_id: UUID) -> dict[str, Any] | None:
    """API-S-Period of the state visible to ``session``, or None."""
    row = session.execute(period_select().where(period_state.c.id == state_id)).mappings().first()
    return None if row is None else period_out(row)


def get_period(ctx: RequestContext, state_id: UUID) -> dict[str, Any]:
    """``GET /periods/{id}``; 404 ``not-found`` for a state outside the principal's scope."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = period_row(session, state_id)
    if row is None:
        raise Problem("not-found")
    return row


# --- currencies and FX rate sets (BUILD_SPEC RFD-3) ----------------------------------------------

CURRENCY_COLUMNS: Final = (
    currency.c.code,
    currency.c.numeric_code,
    currency.c.name,
    currency.c.minor_unit,
    currency.c.is_active,
)
FX_RATE_SET_COLUMNS: Final = (
    fx_rate_set.c.id,
    fx_rate_set.c.code,
    fx_rate_set.c.name,
    fx_rate_set.c.rate_type,
    fx_rate_set.c.source,
    fx_rate_set.c.created_at,
    fx_rate_set.c.updated_at,
    fx_rate_set.c.row_version,
)


def list_currencies[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the ISO 4217 currencies (RLS-NONE-G)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*CURRENCY_COLUMNS))


def tenant_currency_select() -> Select[Any]:
    """T-REF-09 rows with the currency's name and minor unit and whether it is the tenant's
    reporting currency."""
    joined = tenant_currency.join(
        currency, currency.c.code == tenant_currency.c.currency_code
    ).join(tenant, tenant.c.id == tenant_currency.c.tenant_id)
    return select(
        tenant_currency.c.currency_code,
        currency.c.name,
        currency.c.minor_unit,
        tenant_currency.c.is_enabled,
        (tenant.c.reporting_currency == tenant_currency.c.currency_code).label(
            "is_reporting_currency"
        ),
        tenant_currency.c.created_at,
        tenant_currency.c.updated_at,
        tenant_currency.c.row_version,
    ).select_from(joined)


def list_tenant_currencies[T](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the tenant's currencies."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, tenant_currency_select())


def tenant_currency_rows(session: Session) -> list[dict[str, Any]]:
    """Every tenant currency in code order."""
    statement = tenant_currency_select().order_by(tenant_currency.c.currency_code)
    return [dict(row) for row in session.execute(statement).mappings()]


def list_fx_rate_sets[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the FX rate sets."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*FX_RATE_SET_COLUMNS))


def fx_rate_set_row(session: Session, set_id: UUID) -> dict[str, Any] | None:
    statement = select(*FX_RATE_SET_COLUMNS).where(fx_rate_set.c.id == set_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else dict(row)


def fx_rate_set_version_select() -> Select[Any]:
    """T-REF-11 rows with their set's code and rate type and the id of their PENDING
    ``FX_RATE_SET_VERSION`` request."""
    version = fx_rate_set_version
    pending = (
        select(approval_request.c.id)
        .where(
            approval_request.c.subject_type == ApprovalSubjectType.FX_RATE_SET_VERSION.value,
            approval_request.c.subject_id == version.c.id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
        .limit(1)
        .scalar_subquery()
    )
    joined = version.join(
        fx_rate_set,
        and_(
            fx_rate_set.c.tenant_id == version.c.tenant_id,
            fx_rate_set.c.id == version.c.fx_rate_set_id,
        ),
    )
    return select(
        version.c.id,
        version.c.fx_rate_set_id,
        fx_rate_set.c.code.label("fx_rate_set_code"),
        fx_rate_set.c.rate_type,
        version.c.version_no,
        version.c.status,
        version.c.coverage_from,
        version.c.coverage_to,
        version.c.rate_count,
        version.c.import_upload_id,
        version.c.content_sha256,
        version.c.approval_request_id,
        pending.label("pending_approval_request_id"),
        version.c.published_at,
        version.c.published_by,
        version.c.created_at,
        version.c.created_by,
        version.c.updated_at,
        version.c.row_version,
    ).select_from(joined)


def list_fx_rate_set_versions[T](
    ctx: RequestContext, set_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of a set's versions; 404 ``not-found`` for an unknown set."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        if fx_rate_set_row(session, set_id) is None:
            raise Problem("not-found")
        statement = fx_rate_set_version_select().where(
            fx_rate_set_version.c.fx_rate_set_id == set_id
        )
        return page(session, statement)


def fx_rates_of(session: Session, version_id: UUID) -> list[dict[str, Any]]:
    """Every T-REF-12 rate of a version with its period key, in date and pair order."""
    statement = (
        select(
            fx_rate.c.id,
            fx_rate.c.rate_type,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
            fx_rate.c.period_id,
            period.c.period_key,
            fx_rate.c.rate,
            fx_rate.c.is_derived,
        )
        .select_from(
            fx_rate.outerjoin(
                period,
                and_(period.c.tenant_id == fx_rate.c.tenant_id, period.c.id == fx_rate.c.period_id),
            )
        )
        .where(fx_rate.c.fx_rate_set_version_id == version_id)
        .order_by(
            fx_rate.c.effective_date,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
        )
    )
    return [
        {**row, "rate": fx.format_rate(row["rate"])}
        for row in session.execute(statement).mappings()
    ]


def fx_rate_set_version_row(session: Session, version_id: UUID) -> dict[str, Any] | None:
    """A version visible to ``session`` with its rates, or None."""
    statement = fx_rate_set_version_select().where(fx_rate_set_version.c.id == version_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else {**row, "rates": fx_rates_of(session, version_id)}


def get_fx_rate_set_version(ctx: RequestContext, version_id: UUID) -> dict[str, Any]:
    """``GET /fx-rate-set-versions/{id}``; 404 ``not-found`` for an unknown version."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = fx_rate_set_version_row(session, version_id)
    if row is None:
        raise Problem("not-found")
    return row


def list_fx_rates[T: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the rates in force (``fx.EFFECTIVE_RATES``) with twelve-place rate strings."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, fx.effective_rates_select())
        return result, [{**item, "rate": fx.format_rate(item["rate"])} for item in result.items]


# --- account mappings (RFD-7) ---------------------------------------------------------------------

# [J] Copy the documents leave open.
RESOLVE_ENTITY_UNKNOWN: Final = "Choose an existing entity."
RESOLVE_PRODUCT_UNKNOWN: Final = "Choose an existing product."
RULE_ENTITY: Final = "T-REF-01"
MAPPING_RULE_MEMBERS: Final = (
    "id",
    "account_mapping_version_id",
    "account_role",
    "clearing_purpose",
    "entity_id",
    "book_code",
    "product_id",
    "revenue_category",
    "default_dimensions",
    "priority",
    "specificity",
)


# The ``actors.named`` values and the stored kind ``account_mapping_version_select`` reads with each
# row, for ``account_mapping_out`` alone (dev-guide DG-API-11).
_MAPPING_CREATED_BY_NAMED: Final = "created_by__named"
_MAPPING_PUBLISHED_BY_NAMED: Final = "published_by__named"
_MAPPING_READ_ONLY: Final = frozenset(
    {"created_by_kind", _MAPPING_CREATED_BY_NAMED, _MAPPING_PUBLISHED_BY_NAMED}
)


def account_mapping_version_select() -> Select[Any]:
    """T-REF-14 rows with the id of their PENDING ``ACCOUNT_MAPPING_VERSION`` request, their
    ``rule_count`` (04 §16.14) and who created and who published each, read in the same
    statement."""
    version = account_mapping_version
    pending = (
        select(approval_request.c.id)
        .where(
            approval_request.c.subject_type == ApprovalSubjectType.ACCOUNT_MAPPING_VERSION.value,
            approval_request.c.subject_id == version.c.id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
        .limit(1)
        .scalar_subquery()
    )
    rule_count = (
        select(func.count())
        .select_from(account_mapping_rule)
        .where(
            account_mapping_rule.c.tenant_id == version.c.tenant_id,
            account_mapping_rule.c.account_mapping_version_id == version.c.id,
        )
        .scalar_subquery()
    )
    return select(
        version.c.id,
        version.c.name,
        version.c.notes,
        version.c.version_no,
        version.c.status,
        version.c.effective_from,
        version.c.effective_to,
        version.c.content_sha256,
        version.c.approval_request_id,
        pending.label("pending_approval_request_id"),
        version.c.published_at,
        version.c.published_by,
        version.c.supersedes_version_id,
        version.c.impact_simulation_file_id,
        rule_count.label("rule_count"),
        version.c.created_at,
        version.c.created_by,
        version.c.created_by_kind,
        version.c.updated_at,
        version.c.row_version,
        actors.named(version.c.created_by, tenant_id=version.c.tenant_id).label(
            _MAPPING_CREATED_BY_NAMED
        ),
        actors.named(version.c.published_by, tenant_id=version.c.tenant_id).label(
            _MAPPING_PUBLISHED_BY_NAMED
        ),
    )


def account_mapping_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """The API members of an ``account_mapping_version_select`` row: ``created_by`` and
    ``published_by`` as API-S-Actor (04 §16.14). ``published_by`` is null until the version is
    published; a version published without a publisher (automatic approval) names the system."""
    return {
        **{name: value for name, value in row.items() if name not in _MAPPING_READ_ONLY},
        "created_by": actors.actor(
            row["created_by"], row["created_by_kind"], row[_MAPPING_CREATED_BY_NAMED]
        ),
        "published_by": None
        if row["published_at"] is None
        else actors.actor(row["published_by"], None, row[_MAPPING_PUBLISHED_BY_NAMED]),
    }


def list_account_mapping_versions[T](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the tenant's account mapping versions; its items are
    ``account_mapping_version_select`` rows, shown through ``account_mapping_out``."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, account_mapping_version_select())


def account_mapping_version_row(session: Session, version_id: UUID) -> dict[str, Any] | None:
    """The version as ``account_mapping_out`` shows it, or None."""
    statement = account_mapping_version_select().where(account_mapping_version.c.id == version_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else account_mapping_out(dict(row))


def get_account_mapping_version(ctx: RequestContext, version_id: UUID) -> dict[str, Any]:
    """``GET /account-mappings/{id}``; 404 ``not-found`` for an unknown version."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = account_mapping_version_row(session, version_id)
    if row is None:
        raise Problem("not-found")
    return row


def account_mapping_rule_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """A T-REF-15 rule with its GL account as API-S-Ref."""
    return {
        **{name: row[name] for name in MAPPING_RULE_MEMBERS},
        "gl_account": {
            "id": row["gl_account_id"],
            "code": row["gl_account_code"],
            "name": row["gl_account_name"],
        },
    }


def account_mapping_rule_row(session: Session, rule_id: UUID) -> dict[str, Any] | None:
    statement = (
        select(*mapping.RULE_COLUMNS)
        .select_from(mapping.RULE_JOIN)
        .where(account_mapping_rule.c.id == rule_id)
    )
    row = session.execute(statement).mappings().first()
    return None if row is None else account_mapping_rule_out(dict(row))


def list_account_mapping_rules[T: Page](
    ctx: RequestContext, version_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> tuple[T, list[dict[str, Any]]]:
    """One page of the rules of a version; 404 ``not-found`` for an unknown version."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        found = session.execute(
            select(account_mapping_version.c.id).where(account_mapping_version.c.id == version_id)
        ).first()
        if found is None:
            raise Problem("not-found")
        statement = (
            select(*mapping.RULE_COLUMNS)
            .select_from(mapping.RULE_JOIN)
            .where(account_mapping_rule.c.account_mapping_version_id == version_id)
        )
        result = page(session, statement)
        return result, [account_mapping_rule_out(item) for item in result.items]


def _entity_by_ref(session: Session, ref: str) -> Mapping[str, Any] | None:
    """The visible entity whose id or code is ``ref``."""
    columns = (legal_entity.c.id, legal_entity.c.code, legal_entity.c.name)
    try:
        condition = legal_entity.c.id == UUID(ref)
    except ValueError:
        condition = legal_entity.c.code == ref
    row = session.execute(select(*columns).where(condition)).mappings().first()
    return None if row is None else dict(row)


def _product_by_ref(session: Session, ref: str) -> UUID | None:
    """The id of the visible product whose id or code is ``ref``."""
    try:
        condition = product.c.id == UUID(ref)
    except ValueError:
        condition = product.c.code == ref
    found = session.execute(select(product.c.id).where(condition)).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def resolve_account_mapping(
    ctx: RequestContext,
    *,
    role: AccountRole,
    clearing_purpose: ClearingPurpose | None,
    entity: str | None,
    book: BookCode | None,
    product_ref: str | None,
    revenue_category: str | None,
    known_at: datetime,
) -> dict[str, Any]:
    """``GET /account-mappings/resolve``: step 3 of T-REF-15 for a role at ``known_at``.

    An absent key parameter means the line carries no value for it, so only rules that leave the
    key null match (L2-1-Q-5). 422 ``validation-failed`` for a clearing purpose that does not suit
    the role, an unknown entity or an unknown product (each a code or id); 422
    ``unmapped-account-role`` when no PUBLISHED rule answers.
    """
    purpose = None if clearing_purpose is None else clearing_purpose.value
    errors = [
        error for error in mapping.role_errors(role.value, purpose) if error.field != "account_role"
    ]
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        found = None if entity is None else _entity_by_ref(session, entity)
        if entity is not None and found is None:
            errors.append(
                ProblemError(field="entity", rule_id=RULE_ENTITY, message=RESOLVE_ENTITY_UNKNOWN)
            )
        product_id = None if product_ref is None else _product_by_ref(session, product_ref)
        if product_ref is not None and product_id is None:
            errors.append(
                ProblemError(
                    field="product", rule_id=mapping.RULE_RULE, message=RESOLVE_PRODUCT_UNKNOWN
                )
            )
        if errors:
            raise Problem("validation-failed", errors=errors)
        resolution = mapping.resolve_account(
            session,
            role=role,
            known_at=known_at,
            clearing_purpose=purpose,
            entity_id=None if found is None else UUID(str(found["id"])),
            book_code=book,
            product_id=product_id,
            revenue_category=revenue_category,
            entity_code=None if found is None else str(found["code"]),
        )
    return {
        "role": role.value,
        "clearing_purpose": purpose,
        "entity": None if found is None else dict(found),
        "book": None if book is None else book.value,
        "product_id": product_id,
        "revenue_category": revenue_category,
        "known_at": known_at,
        "gl_account": {
            "id": resolution.gl_account_id,
            "code": resolution.gl_account_code,
            "name": resolution.gl_account_name,
        },
        "default_dimensions": dict(resolution.default_dimensions),
        "source": {
            "type": resolution.source_type,
            "id": resolution.rule_id,
            "override_key": resolution.override_key,
            "account_mapping_version_id": resolution.account_mapping_version_id,
            "version_no": resolution.version_no,
            "specificity": resolution.specificity,
            "priority": resolution.priority,
        },
    }

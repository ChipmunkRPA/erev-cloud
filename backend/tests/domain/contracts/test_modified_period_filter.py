"""Applied effective dates, fiscal calendars and caller scope define modified contracts."""

from datetime import UTC, date, datetime
from typing import Any

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import legal_entity, modification, period
from erev_api.domain.contracts.queries import ListFilters, list_statement
from erev_api.enums import ContractQuickList
from sqlalchemy import insert, select, update
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_contract_rows, modification_values, period_values
from tests.domain.contracts.test_contract_reads import app as app  # noqa: F401
from tests.domain.contracts.test_contract_reads import world as world  # noqa: F401


def test_modified_period_uses_applied_dates_calendar_and_scope(
    committed_db: Any, keyring: Any
) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant, None, "*")
    with tenant_session(context) as session:
        own = insert_contract_rows(session, tenant)
        other = insert_contract_rows(session, tenant)
        draft = insert_contract_rows(session, tenant)
        for chain, start, end in (
            (own, date(2026, 1, 1), date(2026, 1, 31)),
            (other, date(2026, 2, 1), date(2026, 2, 28)),
            (draft, date(2026, 1, 1), date(2026, 1, 31)),
        ):
            calendar = session.scalar(
                select(legal_entity.c.calendar_id).where(legal_entity.c.id == chain.entity_id)
            )
            assert calendar is not None
            session.execute(
                insert(period).values(
                    **period_values(tenant, calendar_id=calendar, start_date=start, end_date=end)
                )
            )
            session.execute(
                update(legal_entity)
                .where(legal_entity.c.id == chain.entity_id)
                .values(time_zone="America/Los_Angeles")
            )
            for effective in (date(2026, 1, 1), date(2026, 1, 31)):
                session.execute(
                    insert(modification).values(
                        **modification_values(
                            tenant,
                            contract_id=chain.contract_id,
                            contracting_entity_id=chain.entity_id,
                            effective_date=effective,
                            status="DRAFT" if chain == draft else "APPLIED",
                        )
                    )
                )

    # Feb 1 UTC is still Jan 31 in the contracting entity's zone.
    now = datetime(2026, 2, 1, 1, tzinfo=UTC)

    def ids(filters: ListFilters, scope: DbContext = context) -> set[Any]:
        with tenant_session(scope, read_only=True) as session:
            return {
                row["id"] for row in session.execute(list_statement(filters, now=now)).mappings()
            }

    assert ids(ListFilters(modified_in_period="FY2026-P01")) == {own.contract_id}
    assert ids(ListFilters(modified_in_period="unknown")) == set()
    quick = ContractQuickList.MODIFIED_THIS_PERIOD
    assert ids(ListFilters(quick_list=quick)) == {own.contract_id}
    assert ids(ListFilters(quick_list=quick, as_of=date(2026, 2, 1))) == set()
    assert ids(ListFilters(quick_list=quick, as_of=date(2026, 1, 1))) == {own.contract_id}
    assert ids(ListFilters(quick_list=quick), DbContext(tenant, None, (other.entity_id,))) == set()


def test_modified_filter_api_counts_and_context(world: Any) -> None:
    from uuid import UUID

    from support.factories import sf_ord_20417_body
    from support.reference import get, post

    actor = world.place.author
    created = post(
        world.app,
        "/api/v1/contracts",
        actor,
        sf_ord_20417_body(world.customer_id, external_id="MOD-FILTER"),
    )
    assert created.status_code == 201, created.text
    contract_id = UUID(created.json()["id"])
    with tenant_session(world.place.principal.db_context) as session:
        from erev_api.db.tables import contract

        entity_id = session.scalar(
            select(contract.c.contracting_entity_id).where(contract.c.id == contract_id)
        )
        assert entity_id is not None
        for day in (date(2026, 1, 1), date(2026, 1, 31)):
            session.execute(
                insert(modification).values(
                    **modification_values(
                        world.place.tenant_id,
                        contract_id=contract_id,
                        contracting_entity_id=entity_id,
                        status="APPLIED",
                        effective_date=day,
                    )
                )
            )
    for params in (
        {"modified_in_period": "FY2026-P01"},
        {"quick_list": "MODIFIED_THIS_PERIOD", "as_of": "2026-01-31"},
    ):
        response = get(
            world.app,
            "/api/v1/contracts",
            actor,
            {**params, "q": "MOD-FILTER", "count": "true", "limit": "1"},
        )
        assert response.status_code == 200, response.text
        assert response.headers["X-Erev-Total-Count"] == "1"
        assert [row["id"] for row in response.json()["items"]] == [str(contract_id)]
        assert response.json()["next_cursor"] is None

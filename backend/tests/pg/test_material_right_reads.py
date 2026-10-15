"""Record-cut option inputs and effective-date status from the persisted contract stream."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, contract_event, estimate, material_right
from erev_api.domain.contracts import material_rights
from sqlalchemy import insert, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, contract_event_values, estimate_values, material_right_row

pytestmark = pytest.mark.pg


def test_material_right_input_and_status_cuts(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    created = datetime(2026, 1, 1, tzinfo=UTC)
    future = datetime(2099, 1, 1, tzinfo=UTC)
    with tenant_session(DbContext(tenant_id=tenant, user_id=None, entity_scope="*")) as session:
        row = material_right_row(RowContext(tenant, new_id()), session)
        parent = (
            session.execute(select(contract).where(contract.c.id == row["contract_id"]))
            .mappings()
            .one()
        )
        likelihood = estimate_values(
            tenant,
            contract_id=row["contract_id"],
            estimate_kind="EXERCISE_LIKELIHOOD",
            method="RATE",
            vc_element_type=None,
            element_code="EXERCISE",
        )
        session.execute(insert(estimate).values(**likelihood))
        session.execute(
            insert(material_right).values(
                **(
                    row
                    | {
                        "created_at": created,
                        "ssp_method": "DISCOUNT_X_LIKELIHOOD",
                        "likelihood_estimate_id": likelihood["id"],
                        "expected_purchase_amount": Decimal("50"),
                        "incremental_discount_ratio": Decimal("0.30"),
                        "expiry_date": date(2026, 12, 31),
                    }
                )
            )
        )
        keys = {row["contract_id"]: parent["external_id"]}
        assert (
            material_rights.inputs(session, keys, known_at=created - timedelta(microseconds=1))
            == {}
        )
        assert material_rights.inputs(session, {}, known_at=future) == {}
        (terms,) = material_rights.inputs(session, keys, known_at=created)[row["contract_id"]]
        assert terms.obligation_key == "O1"
        assert terms.likelihood_estimate_key == f"{parent['external_id']}/EXERCISE"
        assert terms.option_type == "RENEWAL_OPTION"
        assert terms.incremental_discount_ratio == Decimal("0.30")
        assert terms.expected_purchase_amount == Decimal("50")
        assert terms.expiry_date == date(2026, 12, 31)
        assert terms.currency == "USD" and terms.ssp_method == "DISCOUNT_X_LIKELIHOOD"

        def status(as_of: date, known_at: datetime = future) -> tuple[str, date | None]:
            shown = material_rights.outputs(
                session, [row["contract_id"]], known_at=known_at, as_of=as_of
            )
            value = shown[row["obligation_id"]]
            return value.status, value.status_date

        # A date alone never expires the option: the persisted event establishes its status.
        assert status(date(2027, 1, 1)) == ("OPEN", None)
        session.execute(
            update(contract)
            .where(contract.c.id == row["contract_id"])
            .values(head_stream_version=4, updated_by_kind="SYSTEM")
        )
        expired = contract_event_values(
            tenant,
            contract_id=row["contract_id"],
            contracting_entity_id=parent["contracting_entity_id"],
            stream_version=2,
            event_type="MATERIAL_RIGHT_EXPIRED",
            effective_date=date(2026, 2, 1),
            payload={"obligation_key": "O1"},
            obligation_ids=[row["obligation_id"]],
        )
        recorded = session.execute(
            insert(contract_event).values(**expired).returning(contract_event.c.recorded_at)
        ).scalar_one()
        assert status(date(2026, 1, 31)) == ("OPEN", None)
        assert status(date(2026, 2, 1)) == ("EXPIRED", date(2026, 2, 1))
        assert status(date(2026, 2, 1), recorded - timedelta(microseconds=1)) == ("OPEN", None)
        # Recorded timestamps are transaction-time: the correction is a later transaction.
    with tenant_session(DbContext(tenant_id=tenant, user_id=None, entity_scope="*")) as session:
        void = contract_event_values(
            tenant,
            contract_id=row["contract_id"],
            contracting_entity_id=parent["contracting_entity_id"],
            stream_version=3,
            event_type="EVENT_VOIDED",
            effective_date=date(2026, 3, 1),
            payload={"reason": "DATA_CORRECTION"},
            supersedes_event_id=expired["id"],
        )
        void_recorded = session.execute(
            insert(contract_event).values(**void).returning(contract_event.c.recorded_at)
        ).scalar_one()
        assert status(date(2026, 2, 1)) == ("OPEN", None)
        assert status(date(2026, 2, 1), void_recorded - timedelta(microseconds=1)) == (
            "EXPIRED",
            date(2026, 2, 1),
        )
        exercised = contract_event_values(
            tenant,
            contract_id=row["contract_id"],
            contracting_entity_id=parent["contracting_entity_id"],
            stream_version=4,
            event_type="MATERIAL_RIGHT_EXERCISED",
            effective_date=date(2026, 4, 1),
            payload={"obligation_key": "O1", "exercised_quantity": "1"},
        )
        session.execute(insert(contract_event).values(**exercised))
        assert status(date(2026, 4, 1)) == ("EXERCISED", date(2026, 4, 1))

    stranger = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=stranger, user_id=None, entity_scope="*")) as session:
        assert material_rights.inputs(session, keys, known_at=future) == {}
        assert (
            material_rights.outputs(
                session, [row["contract_id"]], known_at=future, as_of=date(2026, 4, 1)
            )
            == {}
        )

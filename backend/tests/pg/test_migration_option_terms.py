"""Converted options use native term validation and remain transactional staging facts."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.tables import contract, material_right
from erev_api.domain.contracts import material_rights
from erev_api.domain.contracts.material_right_facts import insert_terms
from erev_api.domain.migration import option_terms
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.schemas.obligations import MaterialRightCreateIn
from erev_api.uow import unit_of_work
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, material_right_row
from tests.domain.migration.test_option_opening_units import converted
from tests.pg.test_migration_capture_pg import _ctx

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("amount", ["25", "25.00000000"])
def test_converted_terms_preserve_total_and_rollback_with_parent(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, tmp_path: Path, amount: str
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    opening = converted()
    line = opening.obligations[0]
    assert line.mapped.option is not None
    mapped = replace(
        line.mapped,
        obligation_key="O1",
        option=replace(line.mapped.option, option_ssp=Decimal(amount)),
    )
    opening = replace(opening, obligations=(replace(line, mapped=mapped),))
    with unit_of_work(
        _ctx(tenant_id, clock), clock=clock, keyring=keyring, files=LocalFileStore(tmp_path)
    ) as uow:
        savepoint = uow.session.begin_nested()
        parent = material_right_row(RowContext(tenant_id, new_id()), uow.session)
        contract_id = UUID(str(parent["contract_id"]))
        ids = option_terms.persist(uow, opening=opening, contract_id=contract_id, currency="USD")
        (stored,) = uow.session.execute(select(material_right)).mappings().all()
        assert stored["id"] == ids[0]
        assert stored["entered_ssp_amount"] == Decimal("25")
        assert stored["option_type"] == "OTHER" and stored["ssp_method"] == "ENTERED_AMOUNT"
        assert stored["is_legacy_quantity_ssp_dollars"] is False
        assert stored["likelihood_estimate_id"] is None and stored["expiry_date"] is None
        (terms,) = material_rights.inputs(
            uow.session, {contract_id: opening.external_id}, known_at=uow.now
        )[contract_id]
        assert terms.entered_ssp_amount == Decimal("25")
        assert terms.obligation_key == "O1"
        savepoint.rollback()
        assert uow.session.execute(select(material_right.c.id)).first() is None
        assert (
            uow.session.execute(select(contract.c.id).where(contract.c.id == contract_id)).first()
            is None
        )
        assert not uow.audit_events


def test_shared_writer_refuses_foreign_obligation_and_invalid_method_inputs(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with unit_of_work(
        _ctx(tenant_id, clock), clock=clock, keyring=keyring, files=LocalFileStore(tmp_path)
    ) as uow:
        parent = material_right_row(RowContext(tenant_id, new_id()), uow.session)
        other = material_right_row(RowContext(tenant_id, new_id()), uow.session)
        body = MaterialRightCreateIn.model_validate(
            {"option_type": "OTHER", "ssp_method": "ENTERED_AMOUNT"}
        )
        with pytest.raises(Problem, match="obligation of this contract"):
            insert_terms(
                uow,
                contract_id=parent["contract_id"],
                obligation_id=other["obligation_id"],
                currency="USD",
                body=body,
            )
        body = MaterialRightCreateIn.model_validate(
            {"option_type": "OTHER", "ssp_method": "DISCOUNT_X_LIKELIHOOD"}
        )
        with pytest.raises(Problem, match="requires a discount"):
            insert_terms(
                uow,
                contract_id=parent["contract_id"],
                obligation_id=parent["obligation_id"],
                currency="USD",
                body=body,
            )
        assert uow.session.execute(select(material_right.c.id)).first() is None


@pytest.mark.parametrize("amount", ["-1", "25.00001"])
def test_unrepresentable_converted_amount_refuses_without_a_fact(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, tmp_path: Path, amount: str
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    opening = converted()
    line = opening.obligations[0]
    assert line.mapped.option is not None
    mapped = replace(
        line.mapped,
        obligation_key="O1",
        option=replace(line.mapped.option, option_ssp=Decimal(amount)),
    )
    opening = replace(opening, obligations=(replace(line, mapped=mapped),))
    with unit_of_work(
        _ctx(tenant_id, clock), clock=clock, keyring=keyring, files=LocalFileStore(tmp_path)
    ) as uow:
        parent = material_right_row(RowContext(tenant_id, new_id()), uow.session)
        with pytest.raises(Problem, match="cannot be represented"):
            option_terms.persist(
                uow, opening=opening, contract_id=parent["contract_id"], currency="USD"
            )
        assert uow.session.execute(select(material_right.c.id)).first() is None

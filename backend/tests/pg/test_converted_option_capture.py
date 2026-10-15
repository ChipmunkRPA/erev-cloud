"""Real platform booking/computation of converted options with rollback of staging facts."""

from decimal import Decimal
from pathlib import Path

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.tables import (
    contract,
    entity_book,
    fiscal_calendar,
    legal_entity,
    material_right,
    period,
    period_state,
    pob_template,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
)
from erev_api.domain.migration import capture, opening_balances
from erev_api.domain.migration.field_mapping import BatchParameters
from erev_api.enums import ApprovalRequestStatus
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from erev_engine.upgrade import decode_input
from sqlalchemy import insert, select, update
from support.db import TestDatabase
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.legacy_replay import _publish_parity_templates
from support.rows import (
    entity_book_values,
    fiscal_calendar_values,
    insert_approval_request,
    legal_entity_values,
    period_state_values,
    period_values,
    product_values,
    ssp_book_values,
    ssp_book_version_values,
    ssp_entry_values,
    ssp_range_values,
)
from tests.domain.migration.test_field_mapping import CODEX_MATERIAL_RIGHT, _synthetic_row
from tests.domain.migration.test_option_opening_units import CUTOVER
from tests.pg.test_migration_capture_pg import _ctx
from tests.unit.test_migration_capture import _batch

pytestmark = pytest.mark.pg


def _opening() -> opening_balances.ContractOpening:
    zero = dict.fromkeys(opening_balances.OPENING_COLUMNS.values(), "0")
    option = _synthetic_row(
        "OPTION",
        1,
        **(
            CODEX_MATERIAL_RIGHT
            | zero
            | {
                "Original POB Total Qty": "25",
                "Original Extended SSP": "25",
                "Original Total Contract Price": "100",
                "Original Allocation": "25",
                "Current Remaining Qty": "10",
                "Current Delivery - Cumulative": "15",
                "Current Remaining SSP": "10",
                "Current SSP Delivered - Cumulative": "15",
                "Current Rev Rec - Cumulative": "15",
                "Current Remaining Allocation": "10",
                "Current Unit SSP": "1",
                "Current Remaining Unit Rev Rec": "1",
                "Current Contract Position - POB": "-15",
            }
        ),
    )
    paid = _synthetic_row(
        "PAID",
        2,
        **(
            zero
            | {
                "SKU Name": "PAID-SKU",
                "Original POB Total Qty": "1",
                "Original POB Total Selling Price": "100",
                "SKU Unit List Price": "75",
                "Original Extended SSP": "75",
                "Original Total Contract Price": "100",
                "Original Allocation": "75",
                "Current Remaining Qty": "1",
                "Current Remaining SSP": "75",
                "Current Remaining Allocation": "75",
                "Current Billing - Cumulative": "100",
                "Current Contract Position - POB": "100",
                "Current Unit SSP": "75",
                "Current Remaining Unit Rev Rec": "75",
            }
        ),
    )
    return opening_balances.stage(
        [option, paid],
        CUTOVER,
        BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD"),
    ).contracts[0]


def test_platform_applier_captures_converted_option_and_rolls_back(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    stamp_test_release()
    _publish_parity_templates(tenant_id)
    opening = _opening()
    with unit_of_work(
        _ctx(tenant_id, clock), clock=clock, keyring=keyring, files=LocalFileStore(tmp_path)
    ) as uow:
        session = uow.session
        calendar = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        january = period_values(tenant_id, calendar_id=calendar["id"])
        session.execute(insert(period).values(**january))
        entity = legal_entity_values(
            tenant_id, calendar_id=calendar["id"], code=opening.entity_code
        )
        session.execute(insert(legal_entity).values(**entity))
        session.execute(
            insert(entity_book).values(
                **entity_book_values(
                    tenant_id, entity_id=entity["id"], first_period_id=january["id"]
                )
            )
        )
        session.execute(
            insert(period_state).values(
                **period_state_values(
                    tenant_id, entity_id=entity["id"], period_id=january["id"], state="future"
                )
            )
        )
        products = {}
        for row in opening.rows:
            template_id = session.execute(
                select(pob_template.c.id).where(pob_template.c.code == row.mapped.template_code)
            ).scalar_one()
            sku = product_values(
                tenant_id,
                code=row.mapped.product_code,
                default_pob_template_id=template_id,
                principal_agent="PRINCIPAL",
            )
            session.execute(insert(product).values(**sku))
            products[row.mapped.product_code] = sku["id"]
        book = ssp_book_values(tenant_id, code="LEGACY-SKU-SSP", resolution_mode="BY_LABEL")
        session.execute(insert(ssp_book).values(**book))
        version = ssp_book_version_values(
            tenant_id, ssp_book_id=book["id"], legacy_version_label="2026-01-01"
        )
        session.execute(insert(ssp_book_version).values(**version))
        for row in opening.rows:
            point = Decimal("1") if row.mapped.option else Decimal("75")
            entry = ssp_entry_values(
                tenant_id,
                ssp_book_version_id=version["id"],
                product_id=products[row.mapped.product_code],
                stratification=row.mapped.stratification,
                method="legacy_range",
                unit_list_price=point,
                midpoint_discount_ratio=Decimal("0"),
                range_ratio=Decimal("0"),
            )
            session.execute(insert(ssp_entry).values(**entry))
            session.execute(
                insert(ssp_range).values(
                    **ssp_range_values(
                        tenant_id,
                        ssp_entry_id=entry["id"],
                        point_value=point,
                        low_value=point,
                        mid_value=point,
                        high_value=point,
                    )
                )
            )
        where = ssp_book_version.c.id == version["id"]
        session.execute(
            update(ssp_book_version).where(where).values(status="TESTED", content_sha256="a" * 64)
        )
        session.execute(update(ssp_book_version).where(where).values(status="SUBMITTED"))
        request_id = insert_approval_request(
            session,
            tenant_id=tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            subject_type="SSP_BOOK_VERSION",
            subject_id=version["id"],
        )
        session.execute(
            update(ssp_book_version)
            .where(where)
            .values(status="APPROVED", approval_request_id=request_id)
        )
        batch = _batch(id=new_id(), capture_operation_id=new_id(), cutover_date=CUTOVER)
        child = capture.migration_unit(uow)
        savepoint = session.begin_nested()
        try:
            try:
                applied = capture.platform_applier.apply(child, batch=batch, contract=opening)
            except Problem as error:
                pytest.fail(str(error.to_json(instance="converted-option-capture")))
            captured, rows = capture.read_version(
                session, applied=applied, capture_operation_id=batch["capture_operation_id"]
            )
            bundle = decode_input(applied.input_evidence)
            assert bundle.sha256() == applied.input_sha256
            assert len(rows) == 2
            option_row = next(row for row in rows if row.obligation_key == "OPTION")
            assert option_row.obligation_kind == "MATERIAL_RIGHT"
            assert option_row.original_allocated_exact == Decimal("25")
            assert option_row.remaining_quantity == Decimal("0.4")
            assert option_row.revenue_cum == Decimal("15")
            assert option_row.remaining_allocation == Decimal("10")
            assert option_row.billed_cum == 0
            assert sum(row.revenue_cum for row in rows) == 15
            assert sum(row.remaining_allocation for row in rows) == 85
            assert sum(row.billed_cum for row in rows) == 100
            assert captured.expected_output_captured
            assert captured.payload_migration_batch_id == batch["id"]
            assert captured.cutover_date == CUTOVER
            assert bundle.contracts[0].material_rights[0].entered_ssp_amount == Decimal("25")
            facts = [
                event for event in child.audit_events if event["action"] == "material_right.create"
            ]
            assert len(facts) == 1
            assert str(facts[0]["detail"]["contract_id"]) == str(applied.contract_id)
            assert session.execute(select(material_right.c.entered_ssp_amount)).scalar_one() == 25
            assert {member.contract_id for member in captured.members} == {applied.contract_id}
        finally:
            savepoint.rollback()
            child.drain_audit_events()
        assert session.execute(select(contract.c.id)).first() is None
        assert session.execute(select(material_right.c.id)).first() is None

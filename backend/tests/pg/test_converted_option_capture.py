"""Real platform booking/computation of converted options with rollback of staging facts."""

from dataclasses import replace
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
    migration_batch,
    migration_reconciliation_line,
    period,
    period_state,
    pob_template,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
)
from erev_api.domain.migration import (
    capture,
    jobs,
    opening_balances,
    opening_plan,
    option_reconciliation,
    promotion_review,
    repository,
)
from erev_api.domain.migration.field_mapping import BatchParameters
from erev_api.enums import ApprovalRequestStatus, MigrationStatus
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from erev_engine.canonical import sha256_hex
from erev_engine.upgrade import decode_input
from sqlalchemy import insert, select, update
from support.db import TestDatabase
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.legacy_replay import _publish_parity_templates
from support.rows import (
    RowContext,
    entity_book_values,
    fiscal_calendar_values,
    insert_approval_request,
    legal_entity_values,
    migration_batch_row,
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


@pytest.mark.parametrize("corrupt_quantity", [None, "10", "0.40000001"])
def test_platform_applier_captures_converted_option_and_rolls_back(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    corrupt_quantity: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    stamp_test_release()
    _publish_parity_templates(tenant_id)
    opening = _opening()
    parameters = BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD")
    staging = opening_balances.stage([row.source for row in opening.rows], CUTOVER, parameters)
    manifest = opening_plan.record(staging, parameters, {})
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
        batch = migration_batch_row(RowContext(tenant_id, new_id()), session)
        batch.update(
            status="IMPORTED",
            capture_operation_id=new_id(),
            cutover_date=CUTOVER,
            profile={"opening_plan": manifest},
        )
        session.execute(insert(migration_batch).values(**batch))
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

        if corrupt_quantity is not None:
            # Fault injection: even a self-consistent row/document digest must not turn an
            # incorrect option-unit result into an explained conversion or equal raw number.
            changed = []
            for captured_row in rows:
                if captured_row.obligation_key == "OPTION":
                    document, digest = capture.canonical_row(
                        dict(captured_row.row) | {"remaining_quantity": corrupt_quantity}
                    )
                    captured_row = replace(
                        captured_row,
                        remaining_quantity=Decimal(corrupt_quantity),
                        row=document,
                        row_sha256=digest,
                    )
                changed.append(captured_row)
            rows = tuple(changed)
        retained = capture.Capture(
            batch_id=batch["id"],
            capture_operation_id=batch["capture_operation_id"],
            cutover_date=CUTOVER,
            versions=(captured,),
            obligations=rows,
        )
        repository.insert_legacy_rows(uow, batch["id"], [row.source for row in opening.rows])
        repository.insert_population(uow, batch["id"], retained)
        if corrupt_quantity is not None:
            with pytest.raises(Problem) as refused:
                jobs.reconcile_batch(uow, batch["id"])
            assert "exact POL-212" in str(refused.value.to_json(instance="quantity-fault"))
            assert session.execute(select(migration_reconciliation_line.c.id)).first() is None
            assert (
                session.execute(
                    select(migration_batch.c.status).where(migration_batch.c.id == batch["id"])
                ).scalar_one()
                == "IMPORTED"
            )
            return
        with pytest.raises(Problem, match="Reconcile the migration"):
            promotion_review.review_basis(uow, batch["id"])
        totals = jobs.reconcile_batch(uow, batch["id"])
        assert totals.unexplained == 0
        assert totals.explained == 1
        line = (
            session.execute(
                select(migration_reconciliation_line).where(
                    migration_reconciliation_line.c.migration_batch_id == batch["id"],
                    migration_reconciliation_line.c.obligation_key == "OPTION",
                    migration_reconciliation_line.c.measure == "REMAINING_QTY",
                )
            )
            .mappings()
            .one()
        )
        assert line["source_value"] == Decimal("10")
        assert line["erev_value"] == Decimal("0.4")
        assert line["difference"] == Decimal("-9.6")
        assert line["deviation_ref"] == option_reconciliation.REFERENCE
        assert not line["is_within_tolerance"]
        assert (
            session.execute(
                select(migration_batch.c.status).where(migration_batch.c.id == batch["id"])
            ).scalar_one()
            == "RECONCILED"
        )
        assert session.execute(select(contract.c.id)).first() is None

        before = tuple(uow.audit_events)
        basis = promotion_review.review_basis(uow, batch["id"])
        assert basis["control_totals"]["unexplained"] == 0
        assert basis["source_sha256"] == batch["source_sha256"]
        assert basis["capture_operation_id"] == batch["capture_operation_id"]
        assert promotion_review.review_basis(uow, batch["id"]) == basis
        assert tuple(uow.audit_events) == before
        source_rows = [item.source for item in opening.rows]
        keep_parameters = BatchParameters(material_right_convention="KEEP_QUANTITY_CONVENTION")
        keep = opening_balances.stage(source_rows, CUTOVER, keep_parameters)
        remapped = opening_balances.stage(
            source_rows, CUTOVER, parameters, entity_codes={opening.entity_code: "OTHER-ENTITY"}
        )
        changed_plans = [
            None,
            opening_plan.record(keep, keep_parameters, {}),
            opening_plan.record(remapped, parameters, {opening.entity_code: "OTHER-ENTITY"}),
        ]
        for changed_plan in changed_plans:
            nested = session.begin_nested()
            try:
                session.execute(
                    update(migration_batch)
                    .where(migration_batch.c.id == batch["id"])
                    .values(profile={"opening_plan": changed_plan})
                )
                with pytest.raises(Problem) as refused_plan:
                    promotion_review.review_basis(uow, batch["id"])
                assert refused_plan.value.errors[0].rule_id == "MIGRATION_OPENING_PLAN"
            finally:
                nested.rollback()
        assert promotion_review.review_basis(uow, batch["id"]) == basis
        stored_lines = repository.reconciliation_rows(uow, batch["id"])
        broken_sets = [
            stored_lines[:-1],
            stored_lines + [stored_lines[0]],
            [dict(item) | {"erev_value": Decimal("999")} for item in stored_lines],
            [dict(item) | {"deviation_ref": "UNREVIEWED"} for item in stored_lines],
        ]
        for broken in broken_sets:
            with monkeypatch.context() as patch:
                patch.setattr(repository, "reconciliation_rows", lambda *_args, value=broken: value)
                with pytest.raises(Problem, match="does not match"):
                    promotion_review.review_basis(uow, batch["id"])
        repository.transition(
            uow,
            batch["id"],
            to_status=MigrationStatus.SUBMITTED,
            expected_status=MigrationStatus.RECONCILED,
        )
        assert sha256_hex(promotion_review.review_basis(uow, batch["id"])) == sha256_hex(basis)
        session.execute(
            update(migration_batch)
            .where(migration_batch.c.id == batch["id"])
            .values(
                profile={
                    "opening_plan": manifest,
                    "replayed_ssp_versions": [{"ssp_book_version_id": str(version["id"])}],
                }
            )
        )
        assert sha256_hex(promotion_review.review_basis(uow, batch["id"])) != sha256_hex(basis)
        assert session.execute(select(contract.c.id)).first() is None

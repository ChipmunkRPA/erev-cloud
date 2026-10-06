"""LMG-2 opening-balance staging, the pure part (BUILD_SPEC LMG-2
``test_latest_version_per_record`` counts, ``test_cutover_on_or_before_latest_period`` copy,
``test_inconsistent_row_raises_exception`` finding; ENGINE_SPEC S07-R-02, S07-R-03, S07-R-11; 04
T-MIG-01 note; PRD WLD-X-27; BS3-D-26).

The staging is computed from the WLD-F-15 rows without a tenant; writing ``migrated_legacy_row``
and the staged events, and the ``MIGRATION_IMPORT`` job, are the database slice. No database.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

from erev_api.domain.migration import legacy_db, opening_balances
from erev_api.domain.migration.opening_balances import Staging
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
CUTOVER = date(2023, 1, 31)


def _staging() -> Staging:
    return opening_balances.stage(legacy_db.rows(FIXTURE), CUTOVER)


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def test_stage_wld_x_27() -> None:
    # PRD WLD-X-27 at cutover 31 Jan 2023: 4 contracts; 16 legacy POB rows (14 obligations, 2 VC
    # elements); TP 1,300 / 900 / 1,300 / 950; revenue C1 295.69, C2 58.85; billed C1 300, C2 0;
    # C1 contract liability 4.31 (billing − revenue); C2 debit position 58.85 reclassified;
    # 24 migrated rows; no S07-R-03 finding.
    staging = _staging()
    assert staging.cutover_date == CUTOVER
    assert (staging.legacy_pob_rows, staging.obligation_count, staging.vc_count) == (16, 14, 2)
    assert staging.migrated_rows == 24
    assert staging.findings == ()
    by_id = {contract.external_id: contract for contract in staging.contracts}
    assert list(by_id) == ["Contract 1", "Contract 2", "Contract 3", "Contract 4"]
    assert [contract.transaction_price for contract in staging.contracts] == [
        Decimal(1300),
        Decimal(900),
        Decimal(1300),
        Decimal(950),
    ]
    c1, c2 = by_id["Contract 1"], by_id["Contract 2"]
    assert _cents(c1.total("revenue_cum")) == Decimal("295.69")
    assert _cents(c2.total("revenue_cum")) == Decimal("58.85")
    assert c1.total("billed_cum") == Decimal(300) and c2.total("billed_cum") == Decimal(0)
    assert _cents(c1.total("position_obligation")) == Decimal("4.31")
    assert _cents(c2.total("position_obligation")) == Decimal("-58.85")
    assert _cents(c2.total("netting_reclass_amount")) == Decimal("58.85")
    assert (c1.inception_date, c1.latest_period) == (date(2023, 1, 1), CUTOVER)
    assert by_id["Contract 3"].inception_date == date(2023, 2, 1)
    assert (len(c2.obligations), len(c2.vc_elements)) == (3, 1)
    assert {row.mapped.entity_code for row in c1.rows} == {"Mock Entity 1"}


def test_cutover_on_or_before_latest_period() -> None:
    error = opening_balances.validate_cutover(date(2023, 2, 28), date(2023, 1, 31))
    assert error is not None
    assert (error.field, error.message) == ("cutover_date", opening_balances.CUTOVER_COPY)
    assert opening_balances.validate_cutover(date(2023, 1, 31), date(2023, 1, 31)) is None
    assert opening_balances.validate_cutover(date(2022, 12, 31), None) is None


def test_inconsistent_row_raises_finding() -> None:
    # S07-R-03: revenue_cum above the allocation, a negative remaining quantity, a sign clash and
    # a contract whose allocations do not sum to its transaction price each raise
    # OPENING_BALANCE_INCONSISTENT with detail rule S07-R-03.
    contract = _staging().contracts[0]
    row = contract.obligations[0]
    # revenue above the allocation: X_i = revenue_cum + remaining_allocation with a negative
    # remaining allocation, so |revenue_cum| > |X_i| and Σ X_i moves off the transaction price
    excess = dataclasses.replace(
        row, values={**row.values, "remaining_allocation": Decimal("-0.01")}
    )
    broken = dataclasses.replace(contract, obligations=(excess, *contract.obligations[1:]))
    findings = opening_balances.consistency(broken)
    assert [item.code for item in findings] == [
        opening_balances.OPENING_BALANCE_INCONSISTENT,
        opening_balances.OPENING_BALANCE_INCONSISTENT,
    ]
    assert findings[0].subject_key == f"{contract.external_id}/{row.mapped.obligation_key}"
    assert findings[0].detail["rule"] == "S07-R-03"
    assert findings[1].detail["reason"] == "sum of allocations differs from the transaction price"
    negative = dataclasses.replace(row, values={**row.values, "remaining_quantity": Decimal(-1)})
    only_negative = dataclasses.replace(contract, obligations=(negative, *contract.obligations[1:]))
    assert [item.detail["reason"] for item in opening_balances.consistency(only_negative)] == [
        "remaining_quantity is negative"
    ]
    price = dataclasses.replace(contract, transaction_price=contract.transaction_price + 1)
    assert len(opening_balances.consistency(price)) == 1
    assert opening_balances.consistency(contract) == ()


def test_stage_reports_a_finding_and_still_stages() -> None:
    rows = legacy_db.rows(FIXTURE)
    target = rows[0].values["Record Unique ID without time"]
    corrupted = tuple(
        dataclasses.replace(row, values={**row.values, "Current Rev Rec - Cumulative": "999999"})
        if row.record_key == target
        else row
        for row in rows
    )
    staging = opening_balances.stage(corrupted, CUTOVER)
    assert staging.legacy_pob_rows == 16
    assert {item.code for item in staging.findings} == {
        opening_balances.OPENING_BALANCE_INCONSISTENT
    }


def test_payloads() -> None:
    contract = _staging().contracts[0]
    opening = opening_balances.opening_payload(contract, CUTOVER)
    assert opening["reason"] == "LEGACY_MIGRATION" and opening["cutover_date"] == "2023-01-31"
    assert len(opening["rows"]) == 4
    assert set(opening["rows"][0]) == {"obligation_key", *opening_balances.OPENING_COLUMNS}
    assert all(isinstance(value, str) for value in opening["rows"][0].values())
    booking = opening_balances.booking_payload(contract)
    assert booking["external_id"] == "Contract 1"
    assert booking["inception_date"] == "2023-01-01"
    assert len(booking["lines"]) == 4
    line = booking["lines"][0]
    assert line["quantity"] == "5" and line["total_price"] == "500"
    assert line["pob_template_code"] in {
        "LEGACY-DISTINCT",
        "LEGACY-NONDISTINCT",
        "LEGACY-MATERIAL-RIGHT",
    }
    assert line["performing_entity_code"] == "Mock Entity 1"


def test_entity_mapping_creates_missing_entities() -> None:
    """BUILD_SPEC LMG-2 (named case; 04 §17.2 LM-CL-09 rev 1.64): an absent ``Mock Entity 2`` shows
    status "Will be created" in the entity mapping and the import's confirmed writer plans it with
    the tenant reporting currency and the confirmed calendar / time zone; the "created when the
    import runs" half is ``tests/pg/test_migration_capture_pg.py::
    test_import_job_creates_the_confirmed_prerequisites_over_wld_f_15`` (NOT RUN on the lane)."""
    from uuid import UUID

    from erev_api.domain.migration import field_mapping, prerequisites
    from sqlalchemy.dialects import postgresql

    rows = legacy_db.rows(FIXTURE)
    mapping = field_mapping.entity_mapping(
        legacy_db.latest_rows(rows), existing_codes={"Mock Entity 1"}
    )
    assert [(m.legacy_name, m.entity_code, m.status) for m in mapping] == [
        ("Mock Entity 1", "Mock Entity 1", "Matched"),
        ("Mock Entity 2", "Mock Entity 2", "Will be created"),
    ]
    calendar = UUID(int=0xA1)

    class _Result:
        def __init__(self, rows: tuple = (), scalar: object = None) -> None:
            self._rows, self._scalar = rows, scalar

        def all(self) -> list:
            return list(self._rows)

        def scalar_one(self) -> object:
            return self._scalar

    class _Session:
        answers = {
            "tenant": _Result(scalar="USD"),
            "fiscal_calendar": _Result(rows=((calendar, "FY"),)),
            "period": _Result(rows=((calendar,),)),
            "legal_entity": _Result(rows=(("Mock Entity 1",),)),
            "product": _Result(rows=()),
            "pob_template": _Result(rows=()),
        }

        def execute(self, statement: object, params: object = None) -> _Result:
            sql = str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]
            for table, result in self.answers.items():
                if f"FROM erev.{table}" in sql:
                    return result
            return _Result()

    staging = _staging()
    resolved = prerequisites.resolve_entities(
        _Session(),
        tenant_id=UUID(int=1),
        staging=staging,
        entity_mapping=[
            {"legacy_name": m.legacy_name, "entity_code": m.entity_code} for m in mapping
        ],
        entity_defaults={"time_zone": "UTC"},
        create_missing_entities=True,
    )
    # the confirmed writer's plan for the absent entity: the tenant reporting currency, the only
    # calendar, the confirmed time zone; the product half needs the parity templates (the pg case)
    assert [(e.code, e.functional_currency, e.calendar_id, e.time_zone) for e in resolved] == [
        ("Mock Entity 2", "USD", calendar, "UTC")
    ]


def test_confirmed_entity_mapping_reaches_the_staged_identities() -> None:
    """Codex 1227 F1 (04 §17.2 LM-CL-09 rev 1.64): a confirmed NON-identity mapping — Mock
    Entity 1 → AVM-US — is what every staged row and contract carries (contracting / performing
    entity, the booking payload), while the legacy rows keep the original ``Selling Entity`` text
    (T-MIG-02 evidence); an unmapped text is its own code."""
    rows = legacy_db.rows(FIXTURE)
    staging = opening_balances.stage(rows, CUTOVER, entity_codes={"Mock Entity 1": "AVM-US"})
    by_contract = {c.external_id: c for c in staging.contracts}
    remapped = [c for c in staging.contracts if c.entity_code == "AVM-US"]
    assert remapped and all(r.mapped.entity_code == "AVM-US" for c in remapped for r in c.rows)
    untouched = [c for c in staging.contracts if c.entity_code == "Mock Entity 2"]
    assert untouched  # the unmapped selling entity is its own code
    assert not any(c.entity_code == "Mock Entity 1" for c in staging.contracts)
    booking = opening_balances.booking_payload(remapped[0])
    assert booking["contracting_entity_code"] == "AVM-US"
    assert {line["performing_entity_code"] for line in booking["lines"]} == {"AVM-US"}
    # the source rows are untouched: the original text is the T-MIG-02 evidence
    originals = {
        r.values.get(legacy_db.SELLING_ENTITY)
        for r in rows
        if r.contract_external_id == remapped[0].external_id
    }
    assert originals == {"Mock Entity 1"}
    # identity staging is unchanged by an empty mapping
    plain = opening_balances.stage(rows, CUTOVER)
    assert sorted({c.entity_code for c in plain.contracts}) == ["Mock Entity 1", "Mock Entity 2"]
    assert by_contract.keys() == {c.external_id for c in plain.contracts}

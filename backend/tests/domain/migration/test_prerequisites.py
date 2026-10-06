"""LM-CL-09 / LM-CL-03 confirmed entity and product writers (04 §17.2 rev 1.64; D-98 candidate 133;
BUILD_SPEC LMG-2 rev 1.11; lane record §26) — CPU: the confirmation's resolution and refusals, the
import-phase plan over the shipped WLD-F-15 staging, the conflicting-SKU refusal, idempotence, and
``apply`` handing the reference writers exactly the confirmed inputs. The database-bound end-to-end
case (an import over WLD-F-15 with NO provisioned entities / products → IMPORTED with the created
rows) is ``tests/pg/test_migration_capture_pg.py`` (WRITTEN, NOT RUN on the lane).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.migration import legacy_db, opening_balances, prerequisites
from erev_api.enums import PrincipalKind, SspMethod
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from sqlalchemy.dialects import postgresql
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
CUTOVER = date(2023, 1, 31)
TENANT = UUID(int=1)
BATCH = UUID(int=0x48)
CAL_A = UUID(int=0xA1)
CAL_B = UUID(int=0xB2)
TEMPLATES = {
    "LEGACY-DISTINCT": UUID(int=0x11),
    "LEGACY-NONDISTINCT": UUID(int=0x12),
    "LEGACY-MATERIAL-RIGHT": UUID(int=0x13),
    "LEGACY-VC": UUID(int=0x14),
}


class _Result:
    def __init__(self, rows: tuple[Any, ...] = (), scalar: Any = None) -> None:
        self._rows, self._scalar = rows, scalar

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one(self) -> Any:
        return self._scalar

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _Session:
    """Answers each SELECT by the table it reads (the compiled FROM clause), in any order."""

    def __init__(self, answers: dict[str, _Result]) -> None:
        self.answers = answers
        self.statements: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.statements.append(sql)
        for table, result in self.answers.items():
            if f"FROM erev.{table}" in sql or f"FROM {table}" in sql:
                return result
        return _Result()


def _staging() -> opening_balances.Staging:
    return opening_balances.stage(legacy_db.rows(FIXTURE), CUTOVER)


def _session(
    *,
    entities: tuple[str, ...] = (),
    calendars: tuple[tuple[UUID, str], ...] = ((CAL_A, "FY"),),
    with_periods: tuple[UUID, ...] = (CAL_A,),
    products: tuple[str, ...] = (),
    templates: dict[str, UUID] | None = None,
    currency: str = "USD",
) -> _Session:
    tmpl = TEMPLATES if templates is None else templates
    return _Session(
        {
            "tenant": _Result(scalar=currency),
            "fiscal_calendar": _Result(rows=tuple((c, code) for c, code in calendars)),
            "period": _Result(rows=tuple((c,) for c in with_periods)),
            "legal_entity": _Result(rows=tuple((e,) for e in entities)),
            "product": _Result(rows=tuple((p,) for p in products)),
            "pob_template": _Result(rows=tuple((i, code) for code, i in tmpl.items())),
        }
    )


def _rows(*names: str, **extra: Any) -> list[dict[str, Any]]:
    return [{"legacy_name": n, "entity_code": n, **extra} for n in names]


# ---- the confirmation: resolve_entities ----------------------------------------------------------


def test_resolve_fills_currency_calendar_and_time_zone_for_will_be_created_entities() -> None:
    staging = _staging()
    assert prerequisites.selling_entities(staging) == ("Mock Entity 1", "Mock Entity 2")
    session = _session(entities=("Mock Entity 1",))  # Mock Entity 2 is "Will be created"
    resolved = prerequisites.resolve_entities(
        session,
        tenant_id=TENANT,
        staging=staging,
        entity_mapping=_rows("Mock Entity 1", "Mock Entity 2"),
        entity_defaults={"time_zone": "Europe/Dublin"},
        create_missing_entities=True,
    )
    # the only calendar resolves by itself; the default time zone applies; the matched entity is
    # not resolved (nothing to create); the functional currency is the tenant reporting currency
    assert resolved == (
        prerequisites.ResolvedEntity(
            legacy_name="Mock Entity 2",
            code="Mock Entity 2",
            functional_currency="USD",
            calendar_id=CAL_A,
            time_zone="Europe/Dublin",
        ),
    )
    assert resolved[0].as_params()["calendar_id"] == str(CAL_A)


def test_resolve_prefers_the_rows_own_values_over_the_defaults() -> None:
    session = _session(calendars=((CAL_A, "FY"), (CAL_B, "FY-B")), with_periods=(CAL_A, CAL_B))
    resolved = prerequisites.resolve_entities(
        session,
        tenant_id=TENANT,
        staging=_staging(),
        entity_mapping=_rows("Mock Entity 1", calendar_id=CAL_B, time_zone="America/New_York")
        + _rows("Mock Entity 2"),
        entity_defaults={"calendar_id": str(CAL_A), "time_zone": "UTC"},
        create_missing_entities=True,
    )
    by_code = {entity.code: entity for entity in resolved}
    assert by_code["Mock Entity 1"].calendar_id == CAL_B
    assert by_code["Mock Entity 1"].time_zone == "America/New_York"
    assert (
        by_code["Mock Entity 2"].calendar_id == CAL_A
        and by_code["Mock Entity 2"].time_zone == "UTC"
    )


def test_resolve_refuses_by_name_one_finding_per_unresolvable_entity() -> None:
    # two calendars and no confirmed value → no calendar; no time zone anywhere → no time zone;
    # each entity gets its own findings, fields named, nothing invented
    session = _session(calendars=((CAL_A, "FY"), (CAL_B, "FY-B")), with_periods=(CAL_A, CAL_B))
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            session,
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Mock Entity 1", "Mock Entity 2"),
            entity_defaults=None,
            create_missing_entities=True,
        )
    assert refused.value.slug == "validation-failed"
    findings = {(error.field, error.rule_id, error.message) for error in refused.value.errors}
    assert findings == {
        ("entity_mapping[0].calendar_id", "LM-CL-09", "Choose a calendar for Mock Entity 1."),
        ("entity_mapping[0].time_zone", "LM-CL-09", "Choose a time zone for Mock Entity 1."),
        ("entity_mapping[1].calendar_id", "LM-CL-09", "Choose a calendar for Mock Entity 2."),
        ("entity_mapping[1].time_zone", "LM-CL-09", "Choose a time zone for Mock Entity 2."),
    }


def test_resolve_refuses_unknown_calendar_periodless_calendar_and_foreign_entity() -> None:
    session = _session(with_periods=())  # the only calendar has no periods
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            session,
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Mock Entity 1", time_zone="UTC"),
            entity_defaults={"time_zone": "UTC"},  # the omitted Mock Entity 2 resolves from it
            create_missing_entities=True,
        )
    assert {error.message for error in refused.value.errors} == {
        "Calendar 'FY' has no periods; generate a year first."
    }
    assert len(refused.value.errors) == 2  # one finding per absent entity, both on that calendar
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            _session(),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Mock Entity 1", calendar_id=UUID(int=99), time_zone="UTC"),
            entity_defaults=None,
            create_missing_entities=True,
        )
    assert "is not a fiscal calendar of this workspace" in refused.value.errors[0].message
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            _session(),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Nobody", time_zone="UTC"),
            entity_defaults=None,
            create_missing_entities=True,
        )
    assert refused.value.errors[0].field == "entity_mapping[0].legacy_name"


def test_resolve_with_creation_disabled_refuses_an_absent_entity_by_name() -> None:
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            _session(),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Mock Entity 2", time_zone="UTC"),
            entity_defaults=None,
            create_missing_entities=False,
        )
    assert refused.value.errors[0].rule_id == "S07-R-03"
    assert "create_missing_entities is false" in refused.value.errors[0].message


def test_resolve_covers_every_selling_entity_even_when_the_mapping_omits_it() -> None:
    # Codex 1106 R2: an unsubmitted selling entity is the identity mapping resolved from the
    # defaults; without defaults it is refused by name on entity_defaults.*; a matched entity that
    # was omitted needs nothing
    session = _session(entities=("Mock Entity 1",))
    resolved = prerequisites.resolve_entities(
        session,
        tenant_id=TENANT,
        staging=_staging(),
        entity_mapping=[],
        entity_defaults={"time_zone": "UTC"},
        create_missing_entities=True,
    )
    assert [(e.legacy_name, e.code, e.calendar_id, e.time_zone) for e in resolved] == [
        ("Mock Entity 2", "Mock Entity 2", CAL_A, "UTC")
    ]
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            _session(entities=("Mock Entity 1",), calendars=((CAL_A, "FY"), (CAL_B, "FY-B"))),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=[],
            entity_defaults=None,
            create_missing_entities=True,
        )
    assert {(e.field, e.message) for e in refused.value.errors} == {
        ("entity_defaults.calendar_id", "Choose a calendar for Mock Entity 2."),
        ("entity_defaults.time_zone", "Choose a time zone for Mock Entity 2."),
    }
    assert (
        prerequisites.resolve_entities(
            _session(entities=("Mock Entity 1", "Mock Entity 2")),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=[],
            entity_defaults=None,
            create_missing_entities=True,
        )
        == ()
    )


def test_resolve_consolidates_rows_sharing_a_target_code_and_refuses_disagreement() -> None:
    # Codex 1227 F2: both Mock entities absent; the explicit row Mock Entity 1 → Mock Entity 2 plus
    # the implicit identity row of Mock Entity 2 → ONE entity, created once and named by its code;
    # a row whose calendar / time zone disagree with the target's is refused by name
    resolved = prerequisites.resolve_entities(
        _session(),
        tenant_id=TENANT,
        staging=_staging(),
        entity_mapping=_rows("Mock Entity 1", entity_code="Mock Entity 2"),
        entity_defaults={"time_zone": "UTC"},
        create_missing_entities=True,
    )
    assert [(e.legacy_name, e.code, e.time_zone) for e in resolved] == [
        ("Mock Entity 2", "Mock Entity 2", "UTC")
    ]
    plan = prerequisites.plan(
        _session(),
        _staging(),
        resolved_entities=[e.as_params() for e in resolved] * 2,  # the same code twice
        create_missing_entities=True,
        create_missing_products=True,
    )
    assert [e.code for e in plan.entities] == ["Mock Entity 2"]  # planned once
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            _session(),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows(
                "Mock Entity 1", entity_code="Mock Entity 2", time_zone="America/New_York"
            ),
            entity_defaults={"time_zone": "UTC"},
            create_missing_entities=True,
        )
    assert [(e.field, e.rule_id) for e in refused.value.errors] == [
        ("entity_mapping[0].time_zone", "LM-CL-09")
    ]
    assert refused.value.errors[0].message == (
        "Rows mapped to entity code 'Mock Entity 2' disagree on the time zone "
        "('America/New_York' vs 'UTC'); confirm one time zone for that entity."
    )
    # an existing target consolidates to nothing to create (both rows "Matched" on the target)
    assert (
        prerequisites.resolve_entities(
            _session(entities=("Mock Entity 2",)),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Mock Entity 1", entity_code="Mock Entity 2"),
            entity_defaults=None,
            create_missing_entities=True,
        )
        == ()
    )


def test_resolve_refuses_rows_sharing_a_target_code_that_disagree_on_the_calendar() -> None:
    # Codex 1333 (source-inspected, owed at the next touch): the shared-CALENDAR conflict variant
    # of `_consolidate` — two calendars with periods; the explicit row Mock Entity 1 → Mock Entity 2
    # names CAL_B while the implicit identity row of Mock Entity 2 takes the default CAL_A → ONE
    # finding on the SUBMITTED row's calendar_id (the implicit row has no field of its own), with
    # the calendar copy; nothing else refused
    session = _session(calendars=((CAL_A, "FY"), (CAL_B, "FY2")), with_periods=(CAL_A, CAL_B))
    with pytest.raises(Problem) as refused:
        prerequisites.resolve_entities(
            session,
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=_rows("Mock Entity 1", entity_code="Mock Entity 2", calendar_id=CAL_B),
            entity_defaults={"time_zone": "UTC", "calendar_id": str(CAL_A)},
            create_missing_entities=True,
        )
    assert [(e.field, e.rule_id) for e in refused.value.errors] == [
        ("entity_mapping[0].calendar_id", "LM-CL-09")
    ]
    assert refused.value.errors[0].message == (
        f"Rows mapped to entity code 'Mock Entity 2' disagree on the calendar ('{CAL_B}' vs "
        f"'{CAL_A}'); confirm one calendar for that entity."
    )
    # agreeing calendars consolidate to one entity on CAL_B, named by its code
    resolved = prerequisites.resolve_entities(
        session,
        tenant_id=TENANT,
        staging=_staging(),
        entity_mapping=_rows(
            "Mock Entity 1", "Mock Entity 2", entity_code="Mock Entity 2", calendar_id=CAL_B
        ),
        entity_defaults={"time_zone": "UTC"},
        create_missing_entities=True,
    )
    assert [(e.legacy_name, e.code, e.calendar_id) for e in resolved] == [
        ("Mock Entity 2", "Mock Entity 2", CAL_B)
    ]


def test_resolve_consolidation_is_deterministic_whatever_the_order_of_the_rows() -> None:
    # Codex 1333 (source-inspected, owed at the next touch): the input-ORDER variant of
    # `_consolidate` — two SUBMITTED rows sharing the target code, given in both orders: agreeing
    # rows give the SAME single entity named by its code; disagreeing rows give ONE finding naming
    # the LATER row of the order given (the first row of a code stands), the values in that order
    forward = [
        {"legacy_name": "Mock Entity 1", "entity_code": "Mock Entity 2", "time_zone": "UTC"},
        {"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2", "time_zone": "UTC"},
    ]
    for rows in (forward, list(reversed(forward))):
        resolved = prerequisites.resolve_entities(
            _session(),
            tenant_id=TENANT,
            staging=_staging(),
            entity_mapping=rows,
            entity_defaults=None,
            create_missing_entities=True,
        )
        assert [(e.legacy_name, e.code, e.time_zone, e.calendar_id) for e in resolved] == [
            ("Mock Entity 2", "Mock Entity 2", "UTC", CAL_A)
        ]
    disagreeing = [
        {
            "legacy_name": "Mock Entity 1",
            "entity_code": "Mock Entity 2",
            "time_zone": "America/New_York",
        },
        {"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2", "time_zone": "UTC"},
    ]
    for rows, first, second in (
        (disagreeing, "America/New_York", "UTC"),
        (list(reversed(disagreeing)), "UTC", "America/New_York"),
    ):
        with pytest.raises(Problem) as refused:
            prerequisites.resolve_entities(
                _session(),
                tenant_id=TENANT,
                staging=_staging(),
                entity_mapping=rows,
                entity_defaults=None,
                create_missing_entities=True,
            )
        assert [(e.field, e.rule_id) for e in refused.value.errors] == [
            ("entity_mapping[1].time_zone", "LM-CL-09")
        ]
        assert refused.value.errors[0].message == (
            f"Rows mapped to entity code 'Mock Entity 2' disagree on the time zone ('{first}' vs "
            f"'{second}'); confirm one time zone for that entity."
        )


# ---- the import phase: plan ----------------------------------------------------------------------


def _resolved(*codes: str) -> list[dict[str, Any]]:
    return [
        {
            "legacy_name": code,
            "entity_code": code,
            "functional_currency": "USD",
            "calendar_id": str(CAL_A),
            "time_zone": "UTC",
        }
        for code in codes
    ]


def test_plan_over_wld_f_15_creates_the_absent_entities_and_the_six_products() -> None:
    staging = _staging()
    session = _session()  # nothing provisioned
    plan = prerequisites.plan(
        session,
        staging,
        resolved_entities=_resolved("Mock Entity 1", "Mock Entity 2"),
        create_missing_entities=True,
        create_missing_products=True,
    )
    assert [e.code for e in plan.entities] == ["Mock Entity 1", "Mock Entity 2"]
    assert plan.entities[0] == prerequisites.EntityPlan(
        code="Mock Entity 1",
        name="Mock Entity 1",
        functional_currency="USD",
        calendar_id=CAL_A,
        time_zone="UTC",
    )
    # WLD-F-15: six SKUs, each with the parity template of its rows (POL-211 SINGLE_POB default)
    products = {p.code: (p.template_code, p.distinctness, p.template_id) for p in plan.products}
    assert set(products) == {
        "Software 1",
        "Hardware 1",
        "Consulting 1",
        "Material Right - Hardware",
        "Material Right - Services",
        "Variable Consideration",
    }
    assert products["Software 1"] == ("LEGACY-DISTINCT", "distinct", TEMPLATES["LEGACY-DISTINCT"])
    # rev 1.66 (integrated batch #6 test-pg return): every created product carries LM-SSP-02's
    # parity values — PRINCIPAL (never the ProductIn default NOT_ASSESSED, which S03-R-09 blocks
    # with PRINCIPAL_AGENT_NOT_ASSESSED on the activated migrated contract) and the LEGACY_PARITY
    # product-level policy values
    from erev_api.domain.imports.legacy_v1.sku_ssp import product_parity_values

    assert {p.principal_agent for p in plan.products} == {"PRINCIPAL"}
    assert all(dict(p.policy_values) == product_parity_values() for p in plan.products)
    assert product_parity_values()  # the parity values are not an empty mapping
    assert products["Consulting 1"][0] == "LEGACY-NONDISTINCT"
    assert products["Material Right - Hardware"][0] == "LEGACY-MATERIAL-RIGHT"
    assert products["Variable Consideration"][0] == "LEGACY-VC"
    assert not plan.empty


def test_plan_is_idempotent_and_skips_what_exists() -> None:
    staging = _staging()
    session = _session(
        entities=("Mock Entity 1", "Mock Entity 2"),
        products=(
            "Software 1",
            "Hardware 1",
            "Consulting 1",
            "Material Right - Hardware",
            "Material Right - Services",
            "Variable Consideration",
        ),
    )
    plan = prerequisites.plan(
        session,
        staging,
        resolved_entities=_resolved("Mock Entity 2"),  # confirmed earlier, created meanwhile
        create_missing_entities=True,
        create_missing_products=True,
    )
    assert plan.empty  # a second run of the same confirmation creates nothing


def test_plan_refuses_a_missing_product_when_creation_is_off_and_a_missing_template() -> None:
    staging = _staging()
    with pytest.raises(Problem) as refused:
        prerequisites.plan(
            _session(entities=("Mock Entity 1", "Mock Entity 2")),
            staging,
            resolved_entities=[],
            create_missing_entities=True,
            create_missing_products=False,
        )
    assert refused.value.errors[0].rule_id == "S07-R-03"
    assert "create_missing_products is false" in str(refused.value.detail)
    with pytest.raises(Problem) as refused:
        prerequisites.plan(
            _session(entities=("Mock Entity 1", "Mock Entity 2"), templates={}),
            staging,
            resolved_entities=[],
            create_missing_entities=True,
            create_missing_products=True,
        )
    assert "parity template" in str(refused.value.detail) and "cannot be created" in str(
        refused.value.detail
    )


def test_plan_refuses_a_sku_mapped_to_two_templates_before_any_write() -> None:
    import dataclasses

    staging = _staging()
    first = staging.contracts[0]
    row = first.rows[0]
    # the same SKU under a different template in another row of the same contract
    twin = dataclasses.replace(
        row,
        mapped=dataclasses.replace(row.mapped, obligation_key="TWIN", template_code="LEGACY-VC"),
    )
    conflicting = dataclasses.replace(
        staging,
        contracts=(
            dataclasses.replace(first, obligations=(*first.obligations, twin)),
            *staging.contracts[1:],
        ),
    )
    session = _session()
    with pytest.raises(Problem) as refused:
        prerequisites.plan(
            session,
            conflicting,
            resolved_entities=[],
            create_missing_entities=True,
            create_missing_products=True,
        )
    assert "maps to two templates" in str(refused.value.detail)
    assert all("FROM erev.product" not in s and "INSERT" not in s for s in session.statements)


# ---- the import phase: apply ---------------------------------------------------------------------


def test_apply_hands_the_writers_exactly_the_confirmed_inputs_and_audits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_entity(uow: Any, *, body: Any) -> Any:
        calls.append(("entity", body.model_dump(mode="json")))
        return SimpleNamespace(id=UUID(int=0xE1), code=body.code)

    def fake_product(uow: Any, *, body: Any) -> Any:
        calls.append(("product", body.model_dump(mode="json")))
        return SimpleNamespace(id=UUID(int=0xF1), code=body.code)

    monkeypatch.setattr(prerequisites, "create_entity", fake_entity)
    monkeypatch.setattr(prerequisites, "create_product", fake_product)
    audited: list[dict[str, Any]] = []
    uow = cast(
        UnitOfWork,
        SimpleNamespace(
            session=object(),
            principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=TENANT),
            audit=lambda **kwargs: audited.append(kwargs),
        ),
    )
    plan = prerequisites.PrerequisitePlan(
        entities=(
            prerequisites.EntityPlan(
                code="Mock Entity 2",
                name="Mock Entity 2",
                functional_currency="USD",
                calendar_id=CAL_A,
                time_zone="UTC",
            ),
        ),
        products=(
            prerequisites.ProductPlan(
                code="Software 1",
                template_code="LEGACY-DISTINCT",
                template_id=TEMPLATES["LEGACY-DISTINCT"],
                distinctness="distinct",
            ),
        ),
    )
    applied = prerequisites.apply(uow, BATCH, plan)
    assert applied.entity_ids == {"Mock Entity 2": UUID(int=0xE1)}
    assert applied.product_ids == {"Software 1": UUID(int=0xF1)}
    kinds = [kind for kind, _ in calls]
    assert kinds == ["entity", "product"]
    entity_body = calls[0][1]
    assert entity_body["code"] == "Mock Entity 2" and entity_body["name"] == "Mock Entity 2"
    assert entity_body["functional_currency"] == "USD" and entity_body["time_zone"] == "UTC"
    assert entity_body["calendar_id"] == str(CAL_A) and entity_body["first_period_key"] is None
    product_body = calls[1][1]
    assert product_body["code"] == "Software 1" and product_body["name"] == "Software 1"
    assert product_body["default_pob_template_id"] == str(TEMPLATES["LEGACY-DISTINCT"])
    # rev 1.66 (batch #6 return): the writer receives PRINCIPAL and the parity policy values, and
    # the prerequisites event lists them
    from erev_api.domain.imports.legacy_v1.sku_ssp import product_parity_values

    assert product_body["principal_agent"] == "PRINCIPAL"
    assert product_body["policy_values"] == product_parity_values()
    listed = audited[-1]["after"]["products"][0]
    assert listed["principal_agent"] == "PRINCIPAL"
    assert listed["policy_values"] == product_parity_values()
    assert product_body["distinctness_default"] == "distinct"
    assert len(audited) == 1 and audited[0]["action"] == "migration_batch.prerequisites"
    assert audited[0]["object_id"] == BATCH
    assert audited[0]["after"]["entities"][0]["id"] == str(UUID(int=0xE1))
    assert audited[0]["after"]["products"][0]["template_code"] == "LEGACY-DISTINCT"
    # an empty plan writes nothing and audits nothing
    assert prerequisites.apply(uow, BATCH, prerequisites.PrerequisitePlan((), ())).empty
    assert len(audited) == 1


# --- 04 rev 1.72 (D-98 133 AMENDMENTS 3 and 4): the legacy SSP replay writer
# ------------------------------

SSP_ROWS = legacy_db.sku_ssp_rows(FIXTURE)
LABEL = "2023-01-01"
VERSION_ID = UUID(int=0x5A)
REQUEST_ID = UUID(int=0x5E9)


def _ssp_session(
    *,
    versions: tuple[tuple[UUID, str, str], ...] = (),
    entries: tuple[tuple[Any, ...], ...] = (),
    accounts: tuple[str, ...] = (),
    products: tuple[str, ...] = (),
) -> _Session:
    """Answers ordered so a JOIN's FROM clause meets its own table first (``ssp_book_version``
    before ``ssp_book``; ``ssp_entry`` before ``product``)."""
    return _Session(
        {
            # SELECT id, legacy_version_label, status
            "ssp_book_version": _Result(rows=tuple((i, label, s) for i, label, s in versions)),
            "ssp_entry": _Result(rows=tuple(_entry_row(*e) for e in entries)),
            "gl_account": _Result(rows=tuple((a,) for a in accounts)),
            "tenant": _Result(scalar="USD"),
            "fiscal_calendar": _Result(rows=((CAL_A, "FY"),)),
            "period": _Result(rows=((CAL_A,),)),
            "legal_entity": _Result(rows=tuple((e,) for e in ("Mock Entity 1", "Mock Entity 2"))),
            "product": _Result(rows=tuple((p,) for p in products)),
            "pob_template": _Result(rows=tuple((i, code) for code, i in TEMPLATES.items())),
        }
    )


def _entry_row(
    code: str, strat: str, price: str, discount: str, spread: str, account: str | None, flag: str
) -> tuple[Any, ...]:
    # the SELECT order of prerequisites._plan_ssp_replay: code, stratification, unit_list_price,
    # midpoint_discount_ratio, range_ratio, account_code, distinctness
    return (code, strat, price, discount, spread, account, flag)


def _numeric(text: str) -> Decimal:
    """A value as NUMERIC(38,18) hands it back: exact, at scale 18 ("100.000000000000000000")."""
    return Decimal(text).quantize(Decimal("1E-18"))


def _plan_with_ssp(session: _Session) -> prerequisites.PrerequisitePlan:
    return prerequisites.plan(
        session,
        _staging(),
        resolved_entities=_resolved("Mock Entity 1", "Mock Entity 2"),
        create_missing_entities=True,
        create_missing_products=True,
        sku_ssp_rows=SSP_ROWS,
    )


def test_plan_replays_the_sku_ssp_table_as_one_version_per_label_over_an_empty_tenant() -> None:
    plan = _plan_with_ssp(_ssp_session())
    assert [v.label for v in plan.ssp_versions] == [LABEL]
    (version,) = plan.ssp_versions
    assert version.existing_id is None and len(version.entries) == 7
    assert [e.product_code for e in version.entries] == sorted(
        e.product_code for e in version.entries
    )
    hardware = next(e for e in version.entries if e.product_code == "Hardware 1")
    assert (hardware.stratification, hardware.distinctness) == ("Hardware 1", "distinct")
    assert (hardware.unit_list_price, hardware.midpoint_discount_ratio, hardware.range_ratio) == (
        "100",
        "0.1",
        "0.15",
    )
    assert hardware.revenue_account_code == "5001"
    # LM-SSP-02: the SKU present only in SKU_SSP is created too, with the parity template of its
    # flag
    codes = {p.code: p.template_code for p in plan.products}
    assert codes["Material Right - Software"] == "LEGACY-DISTINCT" and len(codes) == 7
    # LM-SSP-09: the revenue accounts, created when absent
    assert plan.revenue_accounts == ("5001", "5002", "5003", "5004")
    assert not plan.empty


def test_plan_reuses_an_equal_approved_version_and_refuses_a_conflicting_or_unapproved_one() -> (
    None
):
    # FLMG-SSP-REUSE-SCALE-1 (Codex 0644 §2): the persisted entries answer as NUMERIC(38,18)
    # Decimals — "100.000000000000000000" against the source cell "100" — and must compare EQUAL
    # (exact, scale-insensitive), never as scaled text
    stored = tuple(
        (
            r["SKU Name"],
            r["ASC 606 Stratification"] or "",
            _numeric(r["SKU Unit List Price"]),
            _numeric(r["Midpoint Discount Percentage"]),
            _numeric(r["SSP Range Method (+-)"]),
            r["Revenue Account"],
            "distinct" if r["Distinct or Nondistinct"] == "Distinct" else "nondistinct",
        )
        for r in SSP_ROWS
    )
    assert str(stored[0][2]).endswith("000000000000000000")  # the scale the fake answers with
    assert str(stored[0][2]) != format(Decimal(SSP_ROWS[0]["SKU Unit List Price"]), "f")
    reused = _plan_with_ssp(
        _ssp_session(
            versions=((VERSION_ID, LABEL, "APPROVED"),),
            entries=stored,
            accounts=("5001", "5002", "5003", "5004"),
        )
    )
    (version,) = reused.ssp_versions
    assert version.existing_id == VERSION_ID and reused.revenue_accounts == ()
    conflicting = stored[:-1] + ((*stored[-1][:2], _numeric("999"), *stored[-1][3:]),)
    with pytest.raises(Problem, match="already approved in this workspace with a different entry"):
        _plan_with_ssp(
            _ssp_session(versions=((VERSION_ID, LABEL, "APPROVED"),), entries=conflicting)
        )
    with pytest.raises(Problem, match="is DRAFT, not APPROVED"):
        _plan_with_ssp(_ssp_session(versions=((VERSION_ID, LABEL, "DRAFT"),)))


def test_plan_keeps_an_existing_ssp_only_product_and_creates_only_absent_ones() -> None:
    # FLMG-SSP-EXISTING-PRODUCT-1 (Codex 0644 §2): "Material Right - Software" appears only in
    # SKU_SSP and ALREADY exists in the tenant → it is known, kept (no ProductPlan), never
    # recreated; the six staged SKUs stay planned; its entries still bind to it by code
    existing_only = "Material Right - Software"
    plan = _plan_with_ssp(_ssp_session(products=(existing_only,)))
    planned = {p.code for p in plan.products}
    assert existing_only not in planned
    assert len(planned) == 6  # the six staged Contract_Live SKUs, absent from the fake tenant
    (version,) = plan.ssp_versions
    assert existing_only in {e.product_code for e in version.entries}
    assert len(version.entries) == 7
    # the plain case (nothing exists) still plans it as an absent SSP-only product (LM-SSP-02)
    fresh = _plan_with_ssp(_ssp_session())
    assert existing_only in {p.code for p in fresh.products}


def test_plan_refuses_an_unknown_distinctness_flag_by_name_before_any_write() -> None:
    rows = (*SSP_ROWS[:-1], {**SSP_ROWS[-1], "Distinct or Nondistinct": "Maybe"})
    with pytest.raises(Problem, match="carries the flag 'Maybe'"):
        prerequisites.plan(
            _ssp_session(),
            _staging(),
            resolved_entities=_resolved("Mock Entity 1", "Mock Entity 2"),
            create_missing_entities=True,
            create_missing_products=True,
            sku_ssp_rows=rows,
        )


def test_apply_creates_fills_and_approves_the_replayed_version_under_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        prerequisites, "_require_approved_request", lambda uow, rid: calls.append(("require", rid))
    )
    monkeypatch.setattr(prerequisites, "_ssp_book", lambda uow: UUID(int=0xB0))
    monkeypatch.setattr(prerequisites, "reporting_currency", lambda session, tenant_id: "USD")
    monkeypatch.setattr(
        prerequisites,
        "create_gl_account",
        lambda uow, *, body, source_system: calls.append(("account", body.code)),
    )
    monkeypatch.setattr(
        prerequisites,
        "create_ssp_book_version",
        lambda uow, book_id, *, body: (
            calls.append(("version", body.legacy_version_label, body.methodology_label)),
            VERSION_ID,
        )[1],
    )
    monkeypatch.setattr(
        prerequisites,
        "upsert_ssp_entries",
        lambda uow, version_id, *, body: (
            calls.append(("entries", version_id, len(body.entries), body.entries[0].method)),
            [],
        )[1],
    )
    monkeypatch.setattr(
        prerequisites,
        "_approve_replayed",
        lambda uow, version_id, request_id, digest: calls.append(
            ("approve", version_id, request_id, digest)
        ),
    )
    audited: list[dict[str, Any]] = []
    uow = cast(
        UnitOfWork,
        SimpleNamespace(
            session=object(),
            principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=TENANT),
            audit=lambda **kwargs: audited.append(kwargs),
        ),
    )
    plan = _plan_with_ssp(_ssp_session(products=tuple(SKU_TEMPLATES_ALL)))
    plan = prerequisites.PrerequisitePlan(
        entities=(),
        products=(),
        ssp_versions=plan.ssp_versions,
        revenue_accounts=plan.revenue_accounts,
    )
    applied = prerequisites.apply(
        uow,
        BATCH,
        plan,
        replay_request_id=REQUEST_ID,
        migration_no="MIG-000001",
        sku_ssp_sha256="d" * 64,
    )
    assert calls[0] == ("require", REQUEST_ID)
    assert [c for c in calls if c[0] == "account"] == [
        ("account", a) for a in ("5001", "5002", "5003", "5004")
    ]
    assert ("version", LABEL, "Legacy SSP replay of migration MIG-000001") in calls
    assert ("entries", VERSION_ID, 7, SspMethod.LEGACY_RANGE) in calls
    assert calls[-1] == ("approve", VERSION_ID, REQUEST_ID, "d" * 64)
    assert applied.ssp_version_ids == {LABEL: VERSION_ID} and applied.ssp_entry_counts == {LABEL: 7}
    assert applied.replayed_ssp_versions("d" * 64) == [
        {
            "legacy_version_label": LABEL,
            "ssp_book_version_id": str(VERSION_ID),
            "entry_count": 7,
            "source_sha256": "d" * 64,
            "reused": False,
        }
    ]
    after = audited[-1]["after"]
    assert after["ssp_versions"] == [
        {"legacy_version_label": LABEL, "id": str(VERSION_ID), "entry_count": 7, "reused": False}
    ]
    assert after["revenue_accounts"] == ["5001", "5002", "5003", "5004"]
    assert after["ssp_replay_request_id"] == str(REQUEST_ID) and after["sku_ssp_sha256"] == "d" * 64


def test_apply_refuses_the_replay_without_an_approved_request() -> None:
    session = _Session({"approval_request": _Result(scalar="PENDING")})
    uow = cast(
        UnitOfWork,
        SimpleNamespace(
            session=session,
            principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=TENANT),
            audit=lambda **kwargs: None,
        ),
    )
    plan = prerequisites.PrerequisitePlan(
        entities=(),
        products=(),
        ssp_versions=(prerequisites.SspVersionPlan(label=LABEL, entries=()),),
    )
    with pytest.raises(Problem, match="no APPROVED approval request"):
        prerequisites.apply(uow, BATCH, plan, replay_request_id=REQUEST_ID)
    with pytest.raises(Problem, match="no APPROVED approval request"):
        prerequisites.apply(uow, BATCH, plan, replay_request_id=None)


SKU_TEMPLATES_ALL = (
    "Software 1",
    "Hardware 1",
    "Consulting 1",
    "Material Right - Hardware",
    "Material Right - Services",
    "Material Right - Software",
    "Variable Consideration",
)

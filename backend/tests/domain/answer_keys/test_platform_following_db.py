"""DB-bound (record §18): the converted request models of the FOLLOWING families against the real
API. Written for the lane's ``erev_rv_l17_test`` database and recorded **not run — databases not
provisioned** (§9.1); it runs in an admitted database stage only.

The adapter-driven path (world application → booking → CONTRACTS steps → the seq-7 approval) needs
the read side for approval ids and subject hashes, so this test drives the handlers directly with
the requests ``request_models`` builds from the keys' actual values on a factory-booked contract
(the K06 world of ``test_estimates.py``: Maya prepares, Priya and Marcus approve):

- FOLL-2: EX42's ``BONUS-C`` element (variable consideration, expected value, INCREASE, CONTRACT)
  and its version 1 (0.00 / 750.00 / 1,000.00 effective 2026-07-01) are created as DRAFT, given
  what a submission asks beyond the key's values (04 §16.14 rev 1.241: the evidence and the
  reviewed ``CONSTRAINT`` record, through the routes), submitted, approved; the approval appends
  one ``ESTIMATE_CHANGED`` naming the version and the version is APPROVED with that event applied.

The module held a second case until register index 308 (POLICY-OVERRIDE-WITHDRAW-1; supervisor
ruling R-126 (c)): POS-CHK-012's ``balance.right_to_consideration = CONDITIONAL`` created and
submitted as a policy override through the request model ``request_models.override_kwargs``. That
request model left with the plan's override steps — release 1.0 offers no policy override — and
the case left with it: it is no skipped and no loosened test, its subject is gone. What the
runner states of a declared override now — none is created, and the key is not passed — is
witnessed on the database where a whole plan runs, ``test_platform_close_run_db.py``, and without
one in ``tests/unit/answer_keys/test_platform_override_tie.py``.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_event, estimate_version
from erev_api.domain.contracts import estimates
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.estimates import EstimateVersionSubmitIn
from fastapi import FastAPI
from sqlalchemy import select
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, load_platform_key
from support.answer_keys.request_models import estimate_request, estimate_version_request
from support.db import TestDatabase
from support.factories import (
    K11_CHART,
    TPL_PROD_UNITS,
    Workspace,
    approved_ssp_version,
    booked_contract,
    customer_id,
    product_with_template,
    published_mapping,
    published_template,
    range_entry,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, holding, put
from support.worlds import estimate_version_ready

_POS_012, _DLT, _EX21, EX42, _POS_117 = PLATFORM_KEY_IDS
PART: Final = "AVM-PART"
PART_CASE: Final = {
    "obligation_key": "POB-01",
    "product_code": PART,
    "quantity": "575",
    "total_price": "57500.00",
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> tuple[Workspace, Actor, UUID]:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    marcus = approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "EUR"]})
    assert enabled.status_code == 200, enabled.text
    world_calendar(
        app, maya, entity_code="AVM-DE", functional_currency="EUR", time_zone="Europe/Berlin"
    )
    buyer = customer_id(app, maya, code="C-06", name="Drossel Fahrzeugtechnik GmbH (Demo)")
    part = product_with_template(
        app, maya, code=PART, name="Drive part, per unit", revenue_category="PRODUCT"
    )
    units = published_template(
        app, maya, marcus, code="TPL-PROD-UNITS", outputs=TPL_PROD_UNITS, case_line=PART_CASE
    )
    set_default_template(app, maya, part, units["template_id"])
    # The approved EUR SSP book of test_estimates.py's K06 world (ENGINE_SPEC S05-R-02): without
    # it the activation compute and the estimate-submission dry run fail closed with
    # SSP_KEY_NOT_FOUND (batch ci on main 065e7f65; test_s05_ssp_book_precondition.py).
    book_id = ssp_book(app, maya, code="DE-LIST", currency="EUR")
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        book_id,
        label="2026",
        effective_from="2026-01-01",
        entries=[range_entry(PART, "90.00", "100.00", "110.00", currency="EUR")],
    )
    published_mapping(app, maya, marcus, chart=K11_CHART)
    stamp_test_release()
    return workspace(app, clock, keyring, files, maya), approvers["priya"], buyer


def _body(customer: UUID) -> dict[str, Any]:
    return {
        "external_id": "NS-SO-DE-5002",
        "customer_id": str(customer),
        "contracting_entity_code": "AVM-DE",
        "transaction_currency": "EUR",
        "inception_date": "2026-07-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PART,
                "quantity": "575",
                "total_price": {"amount": "57500.00", "currency": "EUR"},
            }
        ],
    }


def test_estimate_route_emits_estimate_changed_from_the_keys_values(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    place, priya, buyer = _world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    booked = booked_contract(place, _body(buyer), activate=True)
    contract_id = UUID(str(booked.contract["id"]))
    ex42 = load_platform_key(EX42)
    contract = next(c for c in ex42.key.contracts if c.external_id == "C-EX42-C")
    assert contract.estimates is not None
    bonus = contract.estimates[0]
    with place.uow() as uow:
        element = estimates.create_estimate(
            uow, contract_id=contract_id, body=estimate_request(bonus)
        )
        version = estimates.create_version(
            uow, estimate_id=element.id, body=estimate_version_request(bonus.versions[0])
        )
        uow.commit()
    # What the submission asks of a version beyond the key's values (04 §16.14 rev 1.241): its
    # evidence and the reviewed CONSTRAINT record of the element, given through the routes by
    # the world's people — Maya attaches and prepares, Priya reviews. The key states neither.
    estimate_version_ready(
        app, place.author, str(version.id), constraint_of=bonus.element_code, reviewer=priya
    )
    with place.uow() as uow:
        submitted = estimates.submit_version(
            uow, version_id=version.id, body=EstimateVersionSubmitIn()
        )
        uow.commit()
    assert submitted.approval_request_id is not None
    decided = approve(app, str(submitted.approval_request_id), priya)
    assert decided.status_code == 200, decided.text
    row = place.rows(select(estimate_version).where(estimate_version.c.id == version.id))[0]
    assert row["status"] == "APPROVED" and len(row["applied_event_ids"]) == 1
    assert row["rationale"] == bonus.versions[0].rationale
    assert str(row["effective_date"]) == "2026-07-01"
    events = place.rows(
        select(contract_event).where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == "ESTIMATE_CHANGED",
        )
    )
    assert len(events) == 1
    assert str(events[0]["payload"]["estimate_version_id"]) == str(version.id)
    assert events[0]["payload"]["previous_estimate_version_id"] is None

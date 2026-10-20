"""Exercise a real retained preview and save command in an existing scenario fixture."""

from typing import Any
from uuid import UUID

from erev_api.db import new_id
from erev_api.db.tables import contract, deal_preview
from erev_api.domain.forecast.deal_preview import retain
from erev_api.schemas.deal_previews import DealInputIn
from sqlalchemy import select
from support.http import call
from support.principals import cookie_headers


def exercise_save(world: Any, actor: Any) -> None:
    preview_id = new_id()
    with world.place.uow() as uow:
        existing = uow.session.execute(select(contract)).mappings().first()
        assert existing is not None
        retain(
            uow,
            DealInputIn.model_validate(
                {
                    "customer_id": str(existing["customer_id"]),
                    "entity_code": "AVM-US",
                    "start_date": "2026-01-01",
                    "lines": [
                        {
                            "product_code": "AVM-PLAT-ENT",
                            "quantity": "1",
                            "term_months": 12,
                            "price": {"amount": "120000.00", "currency": "USD"},
                        }
                    ],
                }
            ),
            preview_id,
        )
        uow.commit()
    path = f"/api/v1/deal-previews/{preview_id}/save"
    body = {"contract_external_id": "DEAL-SAVED-001"}
    headers = cookie_headers(actor.token, actor.csrf_token)
    detail = call(world.app, "GET", f"/api/v1/deal-previews/{preview_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["save_allowed"] is True
    saved = call(world.app, "POST", path, headers=headers, json=body)
    assert saved.status_code == 201, saved.text
    repeated = call(world.app, "POST", path, headers=headers, json=body)
    assert repeated.json() == saved.json(), repeated.text
    refused = call(
        world.app, "POST", path, headers=cookie_headers(actor.token, actor.csrf_token), json=body
    )
    assert refused.status_code == 409, refused.text
    detail = call(world.app, "GET", f"/api/v1/deal-previews/{preview_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["save_allowed"] is False
    with world.place.uow() as uow:
        saved_id = UUID(saved.json()["id"])
        assert (
            uow.session.scalar(
                select(deal_preview.c.saved_contract_id).where(deal_preview.c.id == preview_id)
            )
            == saved_id
        )
        assert (
            uow.session.scalar(select(contract.c.status).where(contract.c.id == saved_id))
            == "DRAFT"
        )

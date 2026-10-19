"""Authorized reading of production actuals retained for the current scenario snapshot."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import forecast_actuals_capture, tenant_snapshot
from erev_api.domain.forecast import history
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class Actuals:
    forecast: history.SavedForecast
    capture_id: UUID
    dataset_sha256: str
    rows: tuple[Mapping[str, Any], ...]


def read(uow: UnitOfWork, forecast_run_id: UUID) -> Actuals:
    # Authorize the current logical scenario, historical forecast and every forecast entity
    # before entering the source tenant. No caller-supplied source tenant or file id is trusted.
    saved = history.resolve(uow, forecast_run_id)
    original = uow.principal.db_context
    try:
        set_tenant_context(
            uow.session,
            DbContext(
                tenant_id=saved.source_tenant_id,
                user_id=original.user_id,
                entity_scope="*",
            ),
        )
        capture = (
            uow.session.execute(
                select(forecast_actuals_capture)
                .join(
                    tenant_snapshot,
                    (tenant_snapshot.c.tenant_id == forecast_actuals_capture.c.tenant_id)
                    & (tenant_snapshot.c.id == forecast_actuals_capture.c.tenant_snapshot_id),
                )
                .where(
                    tenant_snapshot.c.id == saved.actuals_snapshot_id,
                    tenant_snapshot.c.target_tenant_id == original.tenant_id,
                    tenant_snapshot.c.status == "SUCCEEDED",
                    tenant_snapshot.c.known_at == saved.actuals_cutoff,
                    forecast_actuals_capture.c.known_at == saved.actuals_cutoff,
                )
            )
            .mappings()
            .one_or_none()
        )
        if capture is None:
            raise Problem("precondition-failed", "This scenario snapshot has no retained actuals.")
        _, stream = open_file(
            uow.session, capture["dataset_file_id"], files=uow.files, keyring=uow.keyring
        )
        with stream:
            content = stream.read()
        if hashlib.sha256(content).hexdigest() != capture["dataset_sha256"]:
            raise Problem("precondition-failed", "The retained actuals dataset digest differs.")
        try:
            document = json.loads(content)
            rows = selected_rows(document, saved, capture["entity_ids"])
        except (ValueError, TypeError, KeyError) as error:
            raise Problem(
                "precondition-failed", "The retained actuals dataset scope differs."
            ) from error
        return Actuals(saved, capture["id"], capture["dataset_sha256"], rows)
    finally:
        set_tenant_context(uow.session, original)


def selected_rows(
    document: Mapping[str, Any],
    saved: history.SavedForecast,
    captured_entities: list[str],
) -> tuple[Mapping[str, Any], ...]:
    """Validate full capture scope but return only the saved run's book, entities and horizon."""
    parameters = saved.run["parameters"]
    selected_entities = set(parameters["entity_ids"])
    scope = set(captured_entities)
    book_code = parameters["book_code"]
    book = document["books"][book_code]
    if (
        document["schema_version"] != 1
        or document["tenant_snapshot_id"] != str(saved.actuals_snapshot_id)
        or book["schema_version"] != 1
        or book["source_tenant_id"] != str(saved.source_tenant_id)
        or datetime.fromisoformat(book["known_at"]) != saved.actuals_cutoff
        or book["book_code"] != book_code
        or set(book["entity_ids"]) != scope
        or len(captured_entities) != len(scope)
        or len(book["entity_ids"]) != len(scope)
        or not selected_entities <= scope
    ):
        raise ValueError("capture identity")
    selected: list[Mapping[str, Any]] = []
    identities: set[str] = set()
    horizon = set(parameters["horizon_periods"])
    for row in book["rows"]:
        if (
            row["entity_id"] not in scope
            or row["book_code"] != book_code
            or row["id"] in identities
            or datetime.fromisoformat(row["created_at"]) > saved.actuals_cutoff
            or datetime.fromisoformat(row["acknowledged_at"]) > saved.actuals_cutoff
            or row["run_state_at_cutoff"] == "cancelled"
        ):
            raise ValueError("journal scope")
        identities.add(row["id"])
        if row["entity_id"] in selected_entities and row["period_key"] in horizon:
            selected.append(dict(row))
    return tuple(selected)

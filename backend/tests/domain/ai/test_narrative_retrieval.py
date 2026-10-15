"""The AI worker reads the real K-01 trace through Explain and current human RLS."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job
from erev_api.domain.ai.retrieval import retrieve_narrative
from erev_api.enums import JobKind
from erev_api.jobs.context import JobAttempt, JobContext, JobRuntime
from erev_api.problems import Problem
from sqlalchemy import insert
from support.principals import Member, colleague
from support.reference import assign, entity
from tests.api.test_explain_api import World, k01_computed, september_line
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world


def context_for(
    actor: Member, clock: FrozenClock, *, queued_params: dict[str, Any] | None = None
) -> JobContext:
    job_id = new_id()
    with tenant_session(DbContext(actor.tenant_id, actor.user_id, "*")) as session:
        session.execute(
            insert(job).values(
                tenant_id=actor.tenant_id,
                id=job_id,
                kind="AI_TASK",
                queue="ai",
                state="RUNNING" if queued_params is None else "QUEUED",
                params={} if queued_params is None else queued_params,
                created_by=actor.user_id,
                created_by_kind="USER",
                updated_by=actor.user_id,
                updated_by_kind="USER",
            )
        )
    return JobContext(
        job_id=job_id,
        tenant_id=actor.tenant_id,
        kind=JobKind.AI_TASK,
        principal=system_principal(actor.tenant_id, on_behalf_of_id=actor.user_id),
        runtime=JobRuntime(
            clock=clock, keyring=None, files=None, attempt=JobAttempt(job_id, actor.tenant_id, None)
        ),
    )


def test_real_trace_identity_values_and_out_of_scope_refusal(
    world: World, clock: FrozenClock
) -> None:
    k01_computed(world)
    line = september_line(world)
    assign(world.maya.member, "viewer")
    context = context_for(world.maya.member, clock)
    result = retrieve_narrative(
        context,
        object_type="schedule_line",
        object_id=line["id"],
        measure="amount",
        model="fixture-model",
        max_tokens=1000,
    )
    assert result.prepared.trace_id == line["calc_trace_id"]
    assert line["amount"] in result.prepared.values.values()
    assert result.prepared.deterministic
    assert result.principal.id == world.maya.member.user_id

    historical = retrieve_narrative(
        context,
        object_type="obligation",
        object_id=line["subject_id"],
        measure="revenue_to_date",
        as_of=date(2026, 8, 31),
        model="fixture-model",
        max_tokens=1000,
    )
    facts = json.loads(historical.prepared.request.messages[0]["content"])["facts"]
    assert facts["root_node_id"].endswith(":FY2026-P08")

    germany = entity(
        world.app,
        world.maya,
        code="AVM-DE",
        calendar_id=world.calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )
    reader = colleague(world.place.tenant_id, "ai_other_entity")
    assign(reader, "viewer", entity_ids=[UUID(germany["id"])])
    restricted = context_for(reader, clock)
    with pytest.raises(Problem) as error:
        retrieve_narrative(
            restricted,
            object_type="schedule_line",
            object_id=line["id"],
            measure="amount",
            model="fixture-model",
            max_tokens=1000,
        )
    assert error.value.slug == "not-found"

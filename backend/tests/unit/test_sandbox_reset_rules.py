"""SNP-3 sandbox reset — the pure parts (BUILD_SPEC SNP-3; 05 SBX-07 rev 1.64; 04 API-R-04 and
§16.14 rev 1.125): the successor's code, the job params, the successor as a load block with an
explicit code, and the refusal of a command in a tenant that is not ACTIVE. The database
witnesses are ``tests/domain/platform/test_sandbox_reset.py``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.api.deps import refuse_inactive_tenant
from erev_api.auth import sessions
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.domain.platform import sandbox_reset as reset
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform.provisioning import TENANT_CODE, TENANT_CODE_LENGTH
from erev_api.enums import TenantKind, TenantStatus
from erev_api.problems import Problem
from hypothesis import given
from hypothesis import strategies as st

OLD = UUID("01a0c1a2-0000-7000-8000-00000000000a")
NEW = UUID("01a0c1a2-0000-7000-8000-000000abc123")
NEXT = UUID("01a0c1a2-0000-7000-8000-000000def456")
USER = UUID("01a0c1a2-0000-7000-8000-00000000000c")
SEED = UUID("01a0c1a2-0000-7000-8000-00000000000d")


def test_successor_code_is_the_old_code_with_a_suffix_of_its_own() -> None:
    first = reset.successor_code("sbx-avenmoor-pre-close-snapshot", NEW)
    assert first == "sbx-avenmoor-pre-close-snapshot-rabc123"
    # a second reset replaces the suffix of the first: codes do not grow with each reset
    assert reset.successor_code(first, NEXT) == "sbx-avenmoor-pre-close-snapshot-rdef456"
    # a name that only looks like a suffix is kept: the pattern is -r and six hex digits
    assert reset.successor_code("sbx-decade-review", NEW) == "sbx-decade-review-rabc123"
    long = "sbx-" + "a" * 36  # a code at the T-PLT-01 limit
    cut = reset.successor_code(long, NEW)
    assert len(cut) == 40 and cut.endswith("-rabc123") and cut.startswith("sbx-aaaa")
    assert reset.successor_code("sbx-trailing-" + "b" * 22 + "-cd", NEW).count("--") == 0


@given(
    st.from_regex(r"[a-z0-9]{1,8}(-[a-z0-9]{1,8}){0,5}", fullmatch=True).filter(
        lambda code: len(code) in TENANT_CODE_LENGTH
    ),
    st.uuids(),
)
def test_every_successor_code_is_a_tenant_code_that_differs_from_the_old_one(
    code: str, successor: UUID
) -> None:
    derived = reset.successor_code(code, successor)
    assert TENANT_CODE.fullmatch(derived) and len(derived) in TENANT_CODE_LENGTH
    assert derived != code and derived.endswith(f"-r{successor.hex[-6:]}")


def _params(**changes: Any) -> dict[str, Any]:
    params = reset.reset_params_of(
        mode=reset.MODE_SNAPSHOT,
        tenant_snapshot_id=SEED,
        reason="Rehearsal complete",
        sandbox_tenant_id=NEW,
        name="Avenmoor pre-close snapshot",
        code="sbx-avenmoor-pre-close-snapshot-rabc123",
        requested_by=USER,
    )
    params.update(changes)
    return params


def test_reset_params_round_trip() -> None:
    parsed = reset.parse_reset(_params())
    assert (parsed.mode, parsed.tenant_snapshot_id, parsed.reason) == (
        "SNAPSHOT",
        SEED,
        "Rehearsal complete",
    )
    successor = parsed.successor
    assert (successor.sandbox_tenant_id, successor.requested_by) == (NEW, USER)
    assert (successor.name, successor.code) == (
        "Avenmoor pre-close snapshot",
        "sbx-avenmoor-pre-close-snapshot-rabc123",
    )
    empty = reset.parse_reset(_params(mode=reset.MODE_EMPTY, tenant_snapshot_id=None))
    assert (empty.mode, empty.tenant_snapshot_id) == ("EMPTY", None)
    # the successor block is the load block the failure hook reads: the same sandbox
    block = sb.parse_load(_params())
    assert block is not None and block.sandbox_tenant_id == NEW and not block.restore


@pytest.mark.parametrize(
    ("changes", "field", "rule_id"),
    [
        ({"mode": "DELETE"}, "mode", "PARAMS_INVALID"),
        ({"tenant_snapshot_id": None}, "tenant_snapshot_id", sb.RULE_SEED),
        ({"tenant_snapshot_id": "not-a-uuid"}, "tenant_snapshot_id", "PARAMS_INVALID"),
        ({"reason": "  "}, "reason", "BR-PLT-08"),
        ({"sandbox": None}, "sandbox", "PARAMS_INVALID"),
    ],
)
def test_reset_params_are_refused_by_member(
    changes: dict[str, Any], field: str, rule_id: str
) -> None:
    with pytest.raises(Problem) as refused:
        reset.parse_reset(_params(**changes))
    assert refused.value.slug == "validation-failed"
    assert (field, rule_id) in {(error.field, error.rule_id) for error in refused.value.errors}


def test_a_successor_block_without_a_code_or_a_requester_is_refused() -> None:
    for name in ("code", "requested_by"):
        block = dict(_params()["sandbox"])
        block[name] = None
        with pytest.raises(Problem) as refused:
            reset.parse_reset(_params(sandbox=block))
        assert [(e.field, e.rule_id) for e in refused.value.errors] == [
            ("sandbox", "PARAMS_INVALID")
        ]


def test_a_load_block_carries_an_explicit_code_only_when_one_is_set() -> None:
    derived = sb.load_params_of(
        sandbox_tenant_id=NEW, name="Q3 review", requested_by=USER, restore=True
    )
    assert "code" not in derived["load"]  # the params of a restore are unchanged by SNP-3
    assert sb.parse_load(derived).code is None  # type: ignore[union-attr]
    explicit = sb.load_params_of(
        sandbox_tenant_id=NEW, name="Q3 review", requested_by=USER, restore=True, code="sbx-q3-r1"
    )
    assert sb.parse_load(explicit).code == "sbx-q3-r1"  # type: ignore[union-attr]
    for bad in ("Sbx-Q3", "sbx--q3", "q", "sbx-" + "a" * 40, 7):
        with pytest.raises(Problem) as refused:
            sb.parse_load({"load": {**explicit["load"], "code": bad}})
        assert [(e.field, e.rule_id) for e in refused.value.errors] == [
            ("load.code", "PARAMS_INVALID")
        ]


def _context(status: TenantStatus | None) -> RequestContext:
    values: dict[str, Any] = {
        "principal": system_principal(OLD),
        "tenant_kind": TenantKind.SANDBOX,
        "request_id": "tests-inactive-tenant",
        "source_ip": None,
        "user_agent": None,
        "idempotency_key": None,
        "if_match": None,
        "now": datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
        "format_locale": "en-US",
    }
    if status is not None:
        values["tenant_status"] = status
    return RequestContext(**values)


def test_only_an_active_tenant_takes_a_command() -> None:
    """05 SBX-07 rev 1.64: the refusal of the command dependency, by status."""
    refuse_inactive_tenant(_context(TenantStatus.ACTIVE))
    refuse_inactive_tenant(_context(None))  # a worker's context: the default is ACTIVE
    for status in (TenantStatus.ARCHIVED, TenantStatus.SUSPENDED):
        with pytest.raises(Problem) as refused:
            refuse_inactive_tenant(_context(status))
        assert (refused.value.slug, refused.value.status) == ("invalid-transition", 409)
        assert refused.value.detail == sessions.WORKSPACE_NOT_ACTIVE[status]
    assert set(sessions.WORKSPACE_NOT_ACTIVE) == set(TenantStatus) - {TenantStatus.ACTIVE}

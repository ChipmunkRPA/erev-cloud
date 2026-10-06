"""The whole value set of a registry version, the order of effective instants and the instant form
of a PLATFORM version (04 T-PLT-32 "Whole value set", §16.5 rev 1.183; PRD ERR-80, ERR-81, ERR-92
and ERR-77; dev-guide DG-KRN-REG-06; supervisor rulings R-115 (e) and R-117 (b) and the rulings of
2026-10-01 on the item's report; items REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1; BUILD_SPEC
RFD-11).

``test_registry_supersession`` holds the two witnesses of the defect — a later version dropped the
values an earlier version of its key stated. This module holds the rule that repaired it, through
the product's commands as in ``test_registry_versions`` (Maya authors, Marcus decides; the frozen
clock reads 2026-09-12T12:00Z):

* a draft states values and, in ``unset``, the codes it returns to the next level; ``basis =
  "DEFAULTS"`` makes the values sent the whole set; a PATCH replaces the member it names;
* the submit stores the predecessor's values overlaid with the stated ones, less ``unset``, and the
  predecessor; the request, the version's answer and the audit events say what changes — changed,
  added and returned to the default, by code;
* the whole set is what is validated, tested, hashed and approved: one hash from the tests to the
  request, a predecessor that moves after the tests asks for the tests again, and one that moves
  after the submit voids the request ``STALE_SUBJECT`` — before the decision's locks and under them;
* a version never takes effect at or before the effective instant of the PUBLISHED version of its
  key (ERR-80, ERR-81), refused at the submit;
* a version of a settings category (PLATFORM, CLOSE, INTEGRATION, SECURITY, AI) needs no
  effective date and no period start: the workspace settings screen's own bodies end PUBLISHED;
* an ENTITY version overlays the predecessor of its own key only;
* the preset a tenant's accounting policy set stands on stays with it through later versions;
* a version that changes a parameter which needs a named human approver — states it, changes it
  or returns it to the default — is withheld from auto-approval (D-98 candidate 86); one that
  only carries it is not, and the retention confirmation is the approval of the version that last
  changed the families — in the manifest and in the refusal of PRD ERR-77;
* a rejected or withdrawn version is reopened as the whole set of its last submit, and only while
  the version it stood on is still the PUBLISHED one of its key (PRD ERR-92);
* a published version answers the difference it made to the version it superseded, and its
  publication event states the content it changed and no list (RPT-23 counts those entries);
* a rejected version is reopened under the lock of its scope key: a create of the same key that
  has not committed is waited for (two sessions), and a create reads its predecessor under that
  lock (two sessions). A rule set version needs no such lock: its create waits for the row a
  reopening holds (two sessions; unchanged behaviour, pinned).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import approval_request, audit_event, registry_version, rule_set_version
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_job, snapshot_retention
from erev_api.domain.policies import lifecycle, registry_versions, rule_sets
from erev_api.domain.reports.builders import config_change_register, register_support
from erev_api.domain.ssp import resolution
from erev_api.enums import RegistryCategory, RegistryScope, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.registry import presets
from erev_api.uow import unit_of_work
from sqlalchemy import select, update
from support.clock import FROZEN_AT
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import fields, slug
from support.rows import publish_registry_version
from test_lifecycle import LARGE_CASE, ROUTE_CON_100K, RULE_SETS
from test_registry_versions import (  # noqa: F401  (``world`` is the fixture of that module)
    APPROVALS,
    POLICIES,
    PUBLISHED_AT,
    World,
    context,
    created,
    kernel,
    pass_tests,
    publish_row,
    published,
    shown,
    submitted,
    work,
    world,
)

# The first day of the month in New York and in Berlin (the pin rule of a period-scoped version).
OCTOBER = "2026-10-01T04:00:00Z"
NOVEMBER = "2026-11-01T04:00:00Z"
DECEMBER = "2026-12-01T05:00:00Z"
MID_OCTOBER = datetime(2026, 10, 15, 12, tzinfo=UTC)
MID_NOVEMBER = datetime(2026, 11, 15, 12, tzinfo=UTC)
MID_DECEMBER = datetime(2026, 12, 15, 12, tzinfo=UTC)
CONCURRENCY = "platform.job_concurrency"
AUDIT_YEARS = "platform.audit_retention_years"
STYLE = "ui.negative_number_style"
OBTAIN = "costs.obtain_expedient"
ONE_YEAR = "sfc.one_year_expedient"
REPORTING_TYPE = "entity.reporting_type"
COST_RELIEF = "disclosure.nonpublic_cost_relief"
LOSS_UNIT = "loss.unit"  # an accounting policy the LEGACY_PARITY preset does not state
PLATFORM: dict[str, Any] = {"category": "PLATFORM", "scope": "TENANT"}
ACCOUNTING: dict[str, Any] = {"category": "ACCOUNTING_POLICY", "scope": "TENANT"}
EXPEDIENT_US: dict[str, Any] = {
    "category": "PRACTICAL_EXPEDIENT",
    "scope": "ENTITY",
    "entity_code": "AVM-US",
}
PRESET = f"{POLICIES}/presets/legacy-parity"


def _events(found: World, version_id: str) -> list[dict[str, Any]]:
    """The audit events of one version, oldest first."""
    return found.policies.rows(
        select(
            audit_event.c.action, audit_event.c.before, audit_event.c.after, audit_event.c.detail
        )
        .where(audit_event.c.object_id == UUID(version_id))
        .order_by(audit_event.c.chain_seq)
    )


def _request(found: World, request_id: str) -> dict[str, Any]:
    """API-S-Approval as the approver reads it."""
    response = found.policies.get(f"{APPROVALS}/{request_id}", found.policies.marcus)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def _request_row(found: World, request_id: str) -> tuple[str, str | None]:
    rows = found.policies.rows(
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(request_id)
        )
    )
    return str(rows[0]["status"]), rows[0]["void_reason"]


def _stored(found: World, category: str) -> list[tuple[int, str, dict[str, Any]]]:
    """(number, status, values) of every version of a category, as the rows hold them."""
    rows = found.policies.rows(
        select(
            registry_version.c.version_no, registry_version.c.status, registry_version.c["values"]
        )
        .where(registry_version.c.category == category)
        .order_by(registry_version.c.scope, registry_version.c.version_no)
    )
    return [(int(row["version_no"]), str(row["status"]), dict(row["values"])) for row in rows]


def _submit(found: World, version_id: str) -> Any:
    return found.policies.post(f"{POLICIES}/{version_id}/submit", {"comment": "Ready"})


def _preset_at(found: World, known_at: datetime) -> str:
    with tenant_session(context(found.tenant_id), read_only=True) as session:
        return resolution.tenant_preset(session, known_at=known_at)


# --- the statement and the whole set --------------------------------------------------------------


def test_unset_returns_a_value_to_the_default_and_the_request_names_it(world: World) -> None:  # noqa: F811
    """A draft that states nothing and unsets one code: the kept value is carried, the unset one
    resolves at the framework default from the version's effective instant, and the draft, the
    submitted version, the request's summary and the audit events name it."""
    first = published(
        world, **PLATFORM, values={CONCURRENCY: 8, AUDIT_YEARS: 10}, effective_from=OCTOBER
    )
    draft = created(world, **PLATFORM, values={}, unset=[CONCURRENCY], effective_from=NOVEMBER)
    returned = {
        "code": CONCURRENCY,
        "before": 8,
        "after": None,
        "change": "RETURNED_TO_DEFAULT",
    }
    assert (draft["values"], draft["unset"], draft["diff_against_current"]) == (
        {},
        [CONCURRENCY],
        [returned],
    )
    pass_tests(world, draft["id"])
    sent = submitted(world, draft["id"])
    assert (sent["values"], sent["unset"], sent["diff_against_current"]) == (
        {AUDIT_YEARS: 10},
        [],
        [returned],
    )
    assert sent["supersedes_version_id"] == first["id"]
    request = _request(world, sent["approval_request_id"])
    assert request["summary"] == (
        "Publish platform version 3 for the workspace. Returns to default: platform.job_concurrency"
    )
    changes = {"changed": [], "added": [], "returned_to_default": [CONCURRENCY]}
    event = _events(world, draft["id"])[-1]
    assert event["action"] == "registry_version.submitted"
    assert event["after"]["values"] == {AUDIT_YEARS: 10}
    assert event["after"]["supersedes_version_id"] == first["id"]
    assert (event["detail"]["predecessor_version_id"], event["detail"]["changes"]) == (
        first["id"],
        changes,
    )
    approved = world.policies.approve(sent["approval_request_id"])
    assert approved.status_code == 200, approved.text
    # The publication states the content it changes — the whole set and the date, before and
    # after — and not the three lists: the submitted event carries those, in its detail.
    event = _events(world, draft["id"])[-1]
    assert event["action"] == "registry_version.published"
    assert (event["before"]["values"], event["after"]["values"]) == (
        {AUDIT_YEARS: 10, CONCURRENCY: 8},
        {AUDIT_YEARS: 10},
    )
    assert "changes" not in event["before"] and "changes" not in event["after"]
    measured = {
        "15 Oct concurrency": kernel(world, CONCURRENCY, known_at=MID_OCTOBER),
        "15 Nov concurrency": kernel(world, CONCURRENCY, known_at=MID_NOVEMBER),
        "15 Nov audit years": kernel(world, AUDIT_YEARS, known_at=MID_NOVEMBER),
    }
    assert measured == {
        "15 Oct concurrency": (8, "TENANT"),
        "15 Nov concurrency": (4, "FRAMEWORK_DEFAULT"),
        "15 Nov audit years": (10, "TENANT"),
    }
    # No version past TESTED holds a null: resolution reads the rows as it always did.
    assert _stored(world, "PLATFORM") == [
        (1, "SUPERSEDED", {}),
        (2, "SUPERSEDED", {AUDIT_YEARS: 10, CONCURRENCY: 8}),
        (3, "PUBLISHED", {AUDIT_YEARS: 10}),
    ]


def test_basis_defaults_takes_the_values_sent_as_the_whole_set(world: World) -> None:  # noqa: F811
    """With ``basis = "DEFAULTS"`` the server names in ``unset`` what the predecessor holds and
    the request does not state; the difference says changed and returned apart."""
    published(world, **PLATFORM, values={CONCURRENCY: 8, AUDIT_YEARS: 10}, effective_from=OCTOBER)
    draft = created(
        world, **PLATFORM, values={AUDIT_YEARS: 12}, basis="DEFAULTS", effective_from=NOVEMBER
    )
    assert (draft["values"], draft["unset"]) == ({AUDIT_YEARS: 12}, [CONCURRENCY])
    assert draft["diff_against_current"] == [
        {"code": AUDIT_YEARS, "before": 10, "after": 12, "change": "CHANGED"},
        {"code": CONCURRENCY, "before": 8, "after": None, "change": "RETURNED_TO_DEFAULT"},
    ]
    pass_tests(world, draft["id"])
    sent = submitted(world, draft["id"])
    assert (sent["values"], sent["unset"]) == ({AUDIT_YEARS: 12}, [])
    event = _events(world, draft["id"])[-1]
    assert event["detail"]["changes"] == {
        "changed": [AUDIT_YEARS],
        "added": [],
        "returned_to_default": [CONCURRENCY],
    }
    assert world.policies.approve(sent["approval_request_id"]).status_code == 200
    assert kernel(world, CONCURRENCY, known_at=MID_NOVEMBER) == (4, "FRAMEWORK_DEFAULT")
    assert kernel(world, AUDIT_YEARS, known_at=MID_NOVEMBER) == (12, "TENANT")


def test_a_patch_replaces_the_member_it_names(world: World) -> None:  # noqa: F811
    """``values`` and ``unset`` are two members of one statement: a code stated leaves the unset
    codes and a code unset leaves the stated values; one request never names a code in both."""
    published(world, **PLATFORM, values={CONCURRENCY: 8, AUDIT_YEARS: 10}, effective_from=OCTOBER)
    draft = created(
        world, **PLATFORM, values={AUDIT_YEARS: 12}, unset=[CONCURRENCY], effective_from=NOVEMBER
    )
    path = f"{POLICIES}/{draft['id']}"
    policies = world.policies
    stated = policies.patch(path, {"values": {CONCURRENCY: 2}}, etag='"r1"')
    assert stated.status_code == 200, stated.text
    assert (stated.json()["values"], stated.json()["unset"]) == ({CONCURRENCY: 2}, [])
    # An unset code the predecessor does not hold is a statement without an effect.
    unset = policies.patch(path, {"unset": [CONCURRENCY, STYLE]}, etag=stated.headers["ETag"])
    assert unset.status_code == 200, unset.text
    assert (unset.json()["values"], unset.json()["unset"]) == ({}, [CONCURRENCY, STYLE])
    assert unset.json()["diff_against_current"] == [
        {"code": CONCURRENCY, "before": 8, "after": None, "change": "RETURNED_TO_DEFAULT"}
    ]
    etag = unset.headers["ETag"]
    for body, field, message in (
        (
            {"values": {AUDIT_YEARS: 9}, "unset": [AUDIT_YEARS]},
            f"unset.{AUDIT_YEARS}",
            registry_versions.UNSET_AND_STATED,
        ),
        ({"values": {AUDIT_YEARS: None}}, f"values.{AUDIT_YEARS}", registry_versions.VALUE_NULL),
        ({"unset": [OBTAIN]}, f"unset.{OBTAIN}", "Use a parameter of category PLATFORM."),
    ):
        refused = policies.patch(path, body, etag=etag)
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            [(field, "POLICY_VALUE_INVALID")],
        ), body
        assert refused.json()["errors"][0]["message"] == message
    whole = policies.patch(path, {"values": {AUDIT_YEARS: 9}, "basis": "DEFAULTS"}, etag=etag)
    assert whole.status_code == 200, whole.text
    assert (whole.json()["values"], whole.json()["unset"]) == ({AUDIT_YEARS: 9}, [CONCURRENCY])
    events = [event for event in _events(world, draft["id"]) if event["action"].endswith("update")]
    assert [(event["before"], event["after"]) for event in events] == [
        (
            {"values": {AUDIT_YEARS: 12}, "unset": [CONCURRENCY]},
            {"values": {CONCURRENCY: 2}, "unset": []},
        ),
        ({"values": {CONCURRENCY: 2}, "unset": []}, {"values": {}, "unset": [CONCURRENCY, STYLE]}),
        (
            {"values": {}, "unset": [CONCURRENCY, STYLE]},
            {"values": {AUDIT_YEARS: 9}, "unset": [CONCURRENCY]},
        ),
    ]
    created_event = _events(world, draft["id"])[0]
    assert (created_event["after"]["values"], created_event["after"]["unset"]) == (
        {AUDIT_YEARS: 12},
        [CONCURRENCY],
    )


def test_the_whole_set_is_what_is_validated(world: World) -> None:  # noqa: F811
    """A value the predecessor holds is judged with the values a successor states: a nonpublic
    election stands only while the entity type is NONPUBLIC (REQ-REF-016), whoever stated it."""
    base = {"category": "DISCLOSURE_ELECTION", "scope": "ENTITY", "entity_code": "AVM-DE"}
    published(
        world,
        **base,
        values={REPORTING_TYPE: "NONPUBLIC", COST_RELIEF: "ELECT"},
        effective_from=OCTOBER,
    )
    public = world.policies.post(
        POLICIES, {**base, "values": {REPORTING_TYPE: "PBE"}, "effective_from": NOVEMBER}
    )
    assert (public.status_code, fields(public)) == (
        422,
        [(f"values.{COST_RELIEF}", "POLICY_VALUE_INVALID")],
    )
    assert public.json()["errors"][0]["message"] == registry_versions.NONPUBLIC_REQUIRED
    without = created(
        world,
        **base,
        values={REPORTING_TYPE: "PBE"},
        unset=[COST_RELIEF],
        effective_from=NOVEMBER,
    )
    pass_tests(world, without["id"])
    assert submitted(world, without["id"])["values"] == {REPORTING_TYPE: "PBE"}


def test_an_entity_version_overlays_the_predecessor_of_its_own_key(world: World) -> None:  # noqa: F811
    """Rule 5: an ENTITY version holds the codes overridden at that level and no TENANT value; a
    code it returns passes to the TENANT level."""
    published(
        world,
        category="PRACTICAL_EXPEDIENT",
        scope="TENANT",
        values={OBTAIN: "DO_NOT_APPLY", ONE_YEAR: "DO_NOT_APPLY"},
        effective_from=OCTOBER,
    )
    first = published(world, **EXPEDIENT_US, values={OBTAIN: "APPLY"}, effective_from=OCTOBER)
    # The first version of the ENTITY key has no predecessor: it holds what it states and none
    # of the TENANT version's values.
    assert (first["values"], first["supersedes_version_id"]) == ({OBTAIN: "APPLY"}, None)
    second = published(world, **EXPEDIENT_US, values={ONE_YEAR: "APPLY"}, effective_from=NOVEMBER)
    assert (second["values"], second["supersedes_version_id"]) == (
        {OBTAIN: "APPLY", ONE_YEAR: "APPLY"},
        first["id"],
    )
    third = published(world, **EXPEDIENT_US, values={}, unset=[OBTAIN], effective_from=DECEMBER)
    assert third["values"] == {ONE_YEAR: "APPLY"}
    measured = {
        "15 Nov US obtain": kernel(world, OBTAIN, known_at=MID_NOVEMBER, entity_id=world.us_id),
        "15 Dec US obtain": kernel(world, OBTAIN, known_at=MID_DECEMBER, entity_id=world.us_id),
        "15 Dec US one year": kernel(world, ONE_YEAR, known_at=MID_DECEMBER, entity_id=world.us_id),
        "15 Dec DE obtain": kernel(world, OBTAIN, known_at=MID_DECEMBER, entity_id=world.de_id),
    }
    assert measured == {
        "15 Nov US obtain": ("APPLY", "ENTITY"),
        "15 Dec US obtain": ("DO_NOT_APPLY", "TENANT"),
        "15 Dec US one year": ("APPLY", "ENTITY"),
        "15 Dec DE obtain": ("DO_NOT_APPLY", "TENANT"),
    }


def test_a_reopened_version_holds_the_whole_set_of_its_last_submit(world: World) -> None:  # noqa: F811
    published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=OCTOBER)
    draft = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, draft["id"])
    submitted(world, draft["id"])
    withdrawn = world.policies.post(f"{POLICIES}/{draft['id']}/withdraw", {"comment": "Redate"})
    assert withdrawn.status_code == 200, withdrawn.text
    reopened = withdrawn.json()
    assert (reopened["status"], reopened["values"], reopened["unset"]) == (
        "DRAFT",
        {AUDIT_YEARS: 10, CONCURRENCY: 8},
        [],
    )
    assert reopened["diff_against_current"] == [
        {"code": AUDIT_YEARS, "before": None, "after": 10, "change": "ADDED"}
    ]
    pass_tests(world, draft["id"])
    again = submitted(world, draft["id"])
    assert again["values"] == {AUDIT_YEARS: 10, CONCURRENCY: 8}


def _rejected(found: World, request_id: str) -> None:
    refused = found.policies.post(
        f"{APPROVALS}/{request_id}/reject", {"comment": "Not now"}, actor=found.policies.marcus
    )
    assert refused.status_code == 200, refused.text


def _redated(found: World, version_id: str, effective_from: str) -> dict[str, Any]:
    """A PATCH of the date alone — which reopens a rejected or withdrawn version (E-12)."""
    etag = f'"r{shown(found, version_id)["row_version"]}"'
    patched = found.policies.patch(
        f"{POLICIES}/{version_id}", {"effective_from": effective_from}, etag=etag
    )
    assert patched.status_code == 200, patched.text
    result: dict[str, Any] = patched.json()
    return result


def test_a_reopened_version_returns_again_what_it_returned(world: World) -> None:  # noqa: F811
    """The submit drops a statement's JSON nulls. So the reopened row names again, as ``unset``,
    what the PUBLISHED version of its key holds beyond the stored set: the next submit stores the
    set of the last one and the request names the code again — after a withdrawal, and after a
    rejection followed by a PATCH of the date alone (finding 1 of the independent review of
    2026-10-01: until then the code came back with the predecessor's value, unnamed)."""
    published(world, **PLATFORM, values={CONCURRENCY: 8, AUDIT_YEARS: 10}, effective_from=OCTOBER)
    returned = {"code": CONCURRENCY, "before": 8, "after": None, "change": "RETURNED_TO_DEFAULT"}
    summary = (
        "Publish platform version 3 for the workspace. Returns to default: platform.job_concurrency"
    )
    draft = created(world, **PLATFORM, values={}, unset=[CONCURRENCY], effective_from=NOVEMBER)
    pass_tests(world, draft["id"])
    assert submitted(world, draft["id"])["values"] == {AUDIT_YEARS: 10}
    withdrawn = world.policies.post(f"{POLICIES}/{draft['id']}/withdraw", {"comment": "Redate"})
    assert withdrawn.status_code == 200, withdrawn.text
    reopened = withdrawn.json()
    assert (
        reopened["status"],
        reopened["values"],
        reopened["unset"],
        reopened["diff_against_current"],
    ) == ("DRAFT", {AUDIT_YEARS: 10}, [CONCURRENCY], [returned])
    pass_tests(world, draft["id"])
    again = submitted(world, draft["id"])
    assert (again["values"], again["unset"], again["diff_against_current"]) == (
        {AUDIT_YEARS: 10},
        [],
        [returned],
    )
    request_id = str(again["approval_request_id"])
    assert _request(world, request_id)["summary"] == summary
    _rejected(world, request_id)
    assert shown(world, draft["id"])["status"] == "REJECTED"
    redated = _redated(world, draft["id"], DECEMBER)
    assert (
        redated["status"],
        redated["values"],
        redated["unset"],
        redated["diff_against_current"],
    ) == ("DRAFT", {AUDIT_YEARS: 10}, [CONCURRENCY], [returned])
    pass_tests(world, draft["id"])
    last = submitted(world, draft["id"])
    assert _request(world, str(last["approval_request_id"]))["summary"] == summary
    assert world.policies.approve(str(last["approval_request_id"])).status_code == 200
    assert _stored(world, "PLATFORM") == [
        (1, "SUPERSEDED", {}),
        (2, "SUPERSEDED", {AUDIT_YEARS: 10, CONCURRENCY: 8}),
        (3, "PUBLISHED", {AUDIT_YEARS: 10}),
    ]
    assert kernel(world, CONCURRENCY, known_at=MID_DECEMBER) == (4, "FRAMEWORK_DEFAULT")


def _not_reopened(found: World, version_id: str, published_no: int, body: dict[str, Any]) -> None:
    """PRD ERR-92: a PATCH that would reopen the version is refused by name — the message, which
    is the detail too, names the published version — and writes nothing."""
    before = (shown(found, version_id), _events(found, version_id))
    refused = found.policies.patch(
        f"{POLICIES}/{version_id}", body, etag=f'"r{before[0]["row_version"]}"'
    )
    message = (
        f"Version {published_no} was published after this version was submitted. "
        "Create a new version: it starts from the published values."
    )
    assert refused.status_code == 409, refused.text
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", message)
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in refused.json()["errors"]
    ] == [("status", "REGISTRY_BASIS_SUPERSEDED", message)]
    assert (shown(found, version_id), _events(found, version_id)) == before


def test_err_92_a_version_is_not_reopened_after_a_later_one_of_its_key_was_published(
    world: World,  # noqa: F811
) -> None:
    """PRD ERR-92 (the supervisor's ruling of 2026-10-01 on the report of this item). A rejected
    version holds the whole set of its last submit, made on a predecessor that another version
    has since superseded. Reopened, it would restate that set against a version its author never
    saw and revert what that version changed — here the concurrency back from 2 to 8 and the
    number style to the default. The reopening is refused by name, whatever the edit, and
    nothing is written; a new version starts from the published values."""
    published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=OCTOBER)
    old = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, old["id"])
    sent = submitted(world, old["id"])
    assert sent["values"] == {AUDIT_YEARS: 10, CONCURRENCY: 8}
    _rejected(world, str(sent["approval_request_id"]))
    later = published(
        world, **PLATFORM, values={CONCURRENCY: 2, STYLE: "MINUS"}, effective_from=NOVEMBER
    )
    assert (later["version_no"], later["values"]) == (4, {CONCURRENCY: 2, STYLE: "MINUS"})
    for body in ({"effective_from": DECEMBER}, {"values": {AUDIT_YEARS: 12}}):
        _not_reopened(world, old["id"], 4, body)
    assert shown(world, old["id"])["status"] == "REJECTED"
    fresh = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=DECEMBER)
    pass_tests(world, fresh["id"])
    again = submitted(world, fresh["id"])
    assert (again["values"], again["supersedes_version_id"]) == (
        {AUDIT_YEARS: 10, CONCURRENCY: 2, STYLE: "MINUS"},
        later["id"],
    )


def test_a_withdrawn_version_is_reopened_while_its_predecessor_is_the_published_one(
    world: World,  # noqa: F811
) -> None:
    """The other side of PRD ERR-92: a version whose request its preparer withdrew on the
    approvals screen stays WITHDRAWN, and an edit reopens it — the version it stood on is still
    the PUBLISHED one of its key, also after a version of ANOTHER key was published."""
    first = published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=OCTOBER)
    old = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, old["id"])
    request_id = str(submitted(world, old["id"])["approval_request_id"])
    withdrawn = world.policies.post(f"{APPROVALS}/{request_id}/withdraw", {"comment": "Later"})
    assert withdrawn.status_code == 200, withdrawn.text
    assert shown(world, old["id"])["status"] == "WITHDRAWN"
    published(world, **ACCOUNTING, values={LOSS_UNIT: "POB"}, effective_from=NOVEMBER)
    reopened = _redated(world, old["id"], DECEMBER)
    assert (reopened["status"], reopened["values"], reopened["supersedes_version_id"]) == (
        "DRAFT",
        {AUDIT_YEARS: 10, CONCURRENCY: 8},
        first["id"],
    )


def test_an_edit_that_states_nothing_reopens_a_version_unless_its_date_has_passed(
    world: World,  # noqa: F811
) -> None:
    """SCREENS §11.3 rev 1.56 (item POLICY-WITHDRAW-ROUTES-1): the editor's "Edit" is the PATCH
    that reopens a rejected or withdrawn version (E-12; PRD SM-04), and it states nothing — the
    version comes back as the statement of its last submit, its date included. A save validates
    the date the version holds (04 §16.5), so a period-scoped version whose period start has
    come since is not reopened as it is: 422 at ``effective_from``, nothing written. The edit
    that states a new date reopens it, which is why the screen opens the field on that refusal.

    The later instant is the command's own ``now``: a signed-in session of the frozen clock
    would not live until November, so the second half calls the function the route calls."""
    policies = world.policies
    # A period-scoped parameter (pin P): its version is dated at the first day of a period.
    disclosure = {"category": "DISCLOSURE_ELECTION", "scope": "ENTITY", "entity_code": "AVM-DE"}
    old = created(world, **disclosure, values={REPORTING_TYPE: "PBE"}, effective_from=NOVEMBER)
    pass_tests(world, old["id"])
    _rejected(world, str(submitted(world, old["id"])["approval_request_id"]))
    rejected = shown(world, old["id"])
    assert rejected["status"] == "REJECTED"
    reopened = policies.patch(f"{POLICIES}/{old['id']}", {}, etag=f'"r{rejected["row_version"]}"')
    assert reopened.status_code == 200, reopened.text
    assert (
        reopened.json()["status"],
        reopened.json()["values"],
        reopened.json()["effective_from"],
    ) == ("DRAFT", {REPORTING_TYPE: "PBE"}, NOVEMBER)

    pass_tests(world, old["id"])
    _rejected(world, str(submitted(world, old["id"])["approval_request_id"]))
    before = (shown(world, old["id"]), _events(world, old["id"]))
    assert before[0]["status"] == "REJECTED"

    def edited_in_mid_november(changes: dict[str, Any]) -> None:
        ctx = RequestContext(
            principal=system_principal(world.tenant_id),
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-registry-reopen",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=MID_NOVEMBER,
            format_locale="en-US",
        )
        files = LocalFileStore(policies.settings.file_root)
        later = FrozenClock(MID_NOVEMBER)  # a unit of work takes its instant from its clock
        with unit_of_work(ctx, clock=later, keyring=policies.keyring, files=files) as uow:
            registry_versions.update_policy(
                uow, UUID(old["id"]), changes=changes, check_version=lambda _actual: None
            )
            uow.commit()

    with pytest.raises(Problem) as refused:
        edited_in_mid_november({})
    assert refused.value.slug == "validation-failed"
    assert [(error.field, error.rule_id, error.message) for error in refused.value.errors] == [
        ("effective_from", "T-PLT-32", registry_versions.PERIOD_START_REQUIRED)
    ]
    assert (shown(world, old["id"]), _events(world, old["id"])) == before
    edited_in_mid_november({"effective_from": datetime(2026, 12, 1, 5, tzinfo=UTC)})
    again = shown(world, old["id"])
    assert (again["status"], again["values"], again["effective_from"]) == (
        "DRAFT",
        {REPORTING_TYPE: "PBE"},
        DECEMBER,
    )


def test_err_92_the_first_version_of_a_key_is_not_reopened_over_a_later_one(world: World) -> None:  # noqa: F811
    """PRD ERR-92 where the rejected version stood on nothing: the first version of an ENTITY
    key has no predecessor (``supersedes_version_id`` is null). Once another version of the key
    is published, the rejected one is not reopened over it either."""
    old = created(world, **EXPEDIENT_US, values={OBTAIN: "APPLY"}, effective_from=OCTOBER)
    assert (old["version_no"], old["supersedes_version_id"]) == (1, None)
    pass_tests(world, old["id"])
    _rejected(world, str(submitted(world, old["id"])["approval_request_id"]))
    later = published(world, **EXPEDIENT_US, values={ONE_YEAR: "APPLY"}, effective_from=OCTOBER)
    assert (later["version_no"], later["values"]) == (2, {ONE_YEAR: "APPLY"})
    _not_reopened(world, old["id"], 2, {"effective_from": NOVEMBER})
    # The provisioned TENANT version of the category, then the ENTITY key's two versions.
    assert _stored(world, "PRACTICAL_EXPEDIENT") == [
        (1, "PUBLISHED", {}),
        (1, "REJECTED", {OBTAIN: "APPLY"}),
        (2, "PUBLISHED", {ONE_YEAR: "APPLY"}),
    ]


def test_err_92_is_decided_again_after_the_look_for_an_open_version(
    world: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A publication takes no advisory lock: it holds the rows of its version and of the one it
    supersedes. One that commits between the refusal's read of the PUBLISHED version and the look
    for an open version would be seen by neither — the version would be reopened and restated on
    a predecessor it never stood on. So the refusal is decided again after the look: with the
    key's lock held and no version of the key open, none can be published before the reopening
    commits (found by an independent reading of the change on 2026-10-01). Here a second session
    publishes a version of the key by rows and commits at the moment of the look."""
    policies = world.policies
    published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=OCTOBER)
    old = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, old["id"])
    _rejected(world, str(submitted(world, old["id"])["approval_request_id"]))
    rejected = shown(world, old["id"])
    events = _events(world, old["id"])
    ctx = RequestContext(
        principal=system_principal(world.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-registry-publication",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=policies.clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(policies.settings.file_root)
    look = lifecycle._open_elsewhere
    looks: list[bool] = []
    with unit_of_work(ctx, clock=policies.clock, keyring=policies.keyring, files=files) as holder:
        publish_registry_version(
            holder.session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.PLATFORM,
            values={CONCURRENCY: 2},
            at=datetime(2026, 11, 1, 4, tzinfo=UTC),
        )

        def look_after_the_commit(*arguments: Any) -> bool:
            if not looks:
                holder.commit()  # the publication commits between the two reads
            looks.append(look(*arguments))
            return looks[-1]

        monkeypatch.setattr(lifecycle, "_open_elsewhere", look_after_the_commit)
        refused = policies.patch(
            f"{POLICIES}/{old['id']}",
            {"effective_from": DECEMBER},
            etag=f'"r{rejected["row_version"]}"',
        )
    message = (
        "Version 4 was published after this version was submitted. "
        "Create a new version: it starts from the published values."
    )
    assert looks == [False]  # the look ran, after the commit, and found no open version
    assert refused.status_code == 409, refused.text
    assert (slug(refused), fields(refused), refused.json()["detail"]) == (
        "invalid-transition",
        [("status", "REGISTRY_BASIS_SUPERSEDED")],
        message,
    )
    after = shown(world, old["id"])
    assert (after["status"], after["row_version"], after["values"]) == (
        "REJECTED",
        rejected["row_version"],
        {AUDIT_YEARS: 10, CONCURRENCY: 8},
    )
    assert _events(world, old["id"]) == events


# --- what a published version says it did ---------------------------------------------------------


def test_a_published_version_answers_the_difference_it_made(world: World) -> None:  # noqa: F811
    """``diff_against_current`` of a version that was published is the difference it made to the
    version it superseded — the ``changes`` of its content (04 §16.5; minor 1 of the independent
    review of 2026-10-01: read against nothing, every value a version carried answered
    ``ADDED``). The answer stays what it was once a later version supersedes it."""
    first = published(
        world, **PLATFORM, values={CONCURRENCY: 8, STYLE: "MINUS"}, effective_from=OCTOBER
    )
    assert first["diff_against_current"] == [
        {"code": CONCURRENCY, "before": None, "after": 8, "change": "ADDED"},
        {"code": STYLE, "before": None, "after": "MINUS", "change": "ADDED"},
    ]
    second = published(
        world,
        **PLATFORM,
        values={AUDIT_YEARS: 10, CONCURRENCY: 2},
        unset=[STYLE],
        effective_from=NOVEMBER,
    )
    made = [
        {"code": AUDIT_YEARS, "before": None, "after": 10, "change": "ADDED"},
        {"code": CONCURRENCY, "before": 8, "after": 2, "change": "CHANGED"},
        {"code": STYLE, "before": "MINUS", "after": None, "change": "RETURNED_TO_DEFAULT"},
    ]
    assert (second["status"], second["values"], second["diff_against_current"]) == (
        "PUBLISHED",
        {AUDIT_YEARS: 10, CONCURRENCY: 2},
        made,
    )
    third = published(world, **PLATFORM, values={STYLE: "PARENTHESES"}, effective_from=DECEMBER)
    assert (third["values"], third["diff_against_current"]) == (
        {AUDIT_YEARS: 10, CONCURRENCY: 2, STYLE: "PARENTHESES"},
        [{"code": STYLE, "before": None, "after": "PARENTHESES", "change": "ADDED"}],
    )
    superseded = shown(world, second["id"])
    assert (superseded["status"], superseded["diff_against_current"]) == ("SUPERSEDED", made)
    assert shown(world, first["id"])["diff_against_current"] == first["diff_against_current"]
    # The list answers the same, for a page that holds the versions of every key: each version
    # is read against the version IT superseded, and the provisioned defaults made no difference.
    listed = world.policies.get(POLICIES, limit="200")
    assert listed.status_code == 200, listed.text
    by_id = {item["id"]: item for item in listed.json()["items"]}
    assert [by_id[item["id"]]["diff_against_current"] for item in (first, second, third)] == [
        first["diff_against_current"],
        made,
        third["diff_against_current"],
    ]
    seeded = [item for item in by_id.values() if item["version_no"] == 1]
    assert len(seeded) > 1 and all(item["diff_against_current"] == [] for item in seeded)


def test_the_publication_event_counts_what_the_version_changed(world: World) -> None:  # noqa: F811
    """RPT-23 ``changed_field_count`` is the content entries of the publication's audit diff
    (finding 4 of the independent review of 2026-10-01): the version returns one value and moves
    the date, so two. With the three lists of the difference in the event's before and after,
    the lists were counted as fields of their own."""
    published(world, **PLATFORM, values={CONCURRENCY: 8, AUDIT_YEARS: 10}, effective_from=OCTOBER)
    third = published(world, **PLATFORM, values={}, unset=[CONCURRENCY], effective_from=NOVEMBER)
    (event,) = world.policies.rows(
        select(audit_event.c.diff).where(
            audit_event.c.object_id == UUID(third["id"]),
            audit_event.c.action == "registry_version.published",
        )
    )
    content = sorted(
        str(entry["path"])
        for entry in event["diff"]
        if str(entry["path"]).split(".", 1)[0] not in config_change_register.LIFECYCLE_PATHS
    )
    assert content == ["effective_from", f"values.{CONCURRENCY}"]
    assert config_change_register.content_changes(event["diff"]) == 2
    # The register's own count for the request: every event the decision caused on the version.
    cutoff = world.policies.clock.now()
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        decided = register_support.requests(
            session, cutoff=cutoff, where=[approval_request.c.subject_id == UUID(third["id"])]
        )
        counted = config_change_register._changes(session, decided, cutoff=cutoff)
    assert counted == {UUID(third["approval_request_id"]): 2}


# --- one hash, one basis --------------------------------------------------------------------------


def test_one_hash_from_the_tests_to_the_request(world: World) -> None:  # noqa: F811
    """The tests, the submitted row and the request carry the hash of the whole set."""
    published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=OCTOBER)
    draft = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    tested = pass_tests(world, draft["id"])
    assert (tested["values"], tested["test_evidence"]["parameters"]) == ({AUDIT_YEARS: 10}, 2)
    sent = submitted(world, draft["id"])
    request = _request(world, sent["approval_request_id"])
    assert (
        tested["content_sha256"]
        == tested["test_evidence"]["content_sha256"]
        == sent["content_sha256"]
        == request["subject"]["content_sha256"]
    )
    assert sent["values"] == {AUDIT_YEARS: 10, CONCURRENCY: 8}


def test_a_predecessor_that_moves_after_the_tests_asks_for_the_tests_again(world: World) -> None:  # noqa: F811
    """No command publishes a second version of a key while one is open (PRD SM-04), so the other
    publication is made by rows: the submit then answers as for any content changed after its
    tests, and the tests run again on the new whole set."""
    draft = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, draft["id"])
    publish_row(world, category=RegistryCategory.PLATFORM, values={CONCURRENCY: 8})
    refused = _submit(world, draft["id"])
    assert (refused.status_code, slug(refused), fields(refused)) == (
        409,
        "invalid-transition",
        [("status", "REQ-POL-003")],
    )
    assert refused.json()["errors"][0]["message"] == lifecycle.CONTENT_CHANGED
    pass_tests(world, draft["id"])
    assert submitted(world, draft["id"])["values"] == {AUDIT_YEARS: 10, CONCURRENCY: 8}


def test_a_predecessor_that_moves_after_the_submit_voids_the_request(world: World) -> None:  # noqa: F811
    """Rule 3, before the decision's locks: the request was made on another predecessor."""
    draft = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, draft["id"])
    request_id = str(submitted(world, draft["id"])["approval_request_id"])
    publish_row(world, category=RegistryCategory.PLATFORM, values={CONCURRENCY: 8})
    stale = world.policies.approve(request_id)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval")
    assert _request_row(world, request_id) == ("VOIDED", "STALE_SUBJECT")
    assert shown(world, draft["id"])["status"] == "WITHDRAWN"
    assert kernel(world, AUDIT_YEARS, known_at=MID_NOVEMBER) == (7, "FRAMEWORK_DEFAULT")
    assert kernel(world, CONCURRENCY, known_at=MID_NOVEMBER) == (8, "TENANT")


def test_the_approval_hook_checks_the_basis_under_its_locks(
    world: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 3, under the locks: a predecessor published between the decision's comparison and
    the hook is found by ``assert_own_fresh_basis`` once the version is locked. The publication
    is made by rows in the decision's own transaction, right after the hook took the version's
    lock; the refusal rolls it back with the decision and voids the request."""
    draft = created(world, **PLATFORM, values={AUDIT_YEARS: 10}, effective_from=NOVEMBER)
    pass_tests(world, draft["id"])
    request_id = str(submitted(world, draft["id"])["approval_request_id"])
    lock = lifecycle.lock
    raced: list[UUID] = []
    order: list[str] = []

    def lock_then_publish(session: Any, kind: Any, version_id: UUID) -> Any:
        row = lock(session, kind, version_id)
        if kind is registry_versions.KIND and not raced:
            order.append("the version's row")
            raced.append(
                publish_registry_version(
                    session,
                    tenant_id=world.tenant_id,
                    category=RegistryCategory.PLATFORM,
                    values={CONCURRENCY: 8},
                    at=PUBLISHED_AT,
                )
            )
        return row

    predecessor_of = registry_versions.predecessor_of
    fresh = approvals.assert_own_fresh_basis

    def predecessor_recorded(session: Any, version: Any, *, for_update: bool = False) -> Any:
        found = predecessor_of(session, version, for_update=for_update)
        order.append(f"the predecessor's row, for_update={for_update}: {found['id']}")
        return found

    def fresh_recorded(uow: Any, approval_request_id: UUID, **arguments: Any) -> None:
        order.append("the basis")
        fresh(uow, approval_request_id, **arguments)

    monkeypatch.setattr(lifecycle, "lock", lock_then_publish)
    monkeypatch.setattr(registry_versions, "predecessor_of", predecessor_recorded)
    monkeypatch.setattr(approvals, "assert_own_fresh_basis", fresh_recorded)
    stale = world.policies.approve(request_id)
    assert len(raced) == 1  # the decision's own comparison passed and the hook was reached
    # The hook's order: the version's row, then the PUBLISHED version of its key FOR UPDATE — the
    # one published in between — and only then the comparison of the basis.
    assert order == [
        "the version's row",
        f"the predecessor's row, for_update=True: {raced[0]}",
        "the basis",
    ]
    assert (stale.status_code, slug(stale)) == (409, "stale-approval")
    assert _request_row(world, request_id) == ("VOIDED", "STALE_SUBJECT")
    assert shown(world, draft["id"])["status"] == "WITHDRAWN"
    assert _stored(world, "PLATFORM") == [(1, "PUBLISHED", {}), (2, "WITHDRAWN", {AUDIT_YEARS: 10})]


# --- the order of effective instants --------------------------------------------------------------


def test_err_80_a_version_never_takes_effect_at_or_before_the_published_one(world: World) -> None:  # noqa: F811
    """Rule 4 at the submit: nothing is stored or routed, the message is the detail, and a later
    date is accepted."""
    published(world, **EXPEDIENT_US, values={OBTAIN: "DO_NOT_APPLY"}, effective_from=NOVEMBER)
    draft = created(
        world, **EXPEDIENT_US, values={ONE_YEAR: "DO_NOT_APPLY"}, effective_from=OCTOBER
    )
    message = "Version 1 takes effect on 01 Nov 2026. Choose an effective date after it."
    etag = '"r1"'
    for effective_from in (OCTOBER, NOVEMBER):
        patched = world.policies.patch(
            f"{POLICIES}/{draft['id']}", {"effective_from": effective_from}, etag=etag
        )
        assert patched.status_code == 200, patched.text
        pass_tests(world, draft["id"])
        refused = _submit(world, draft["id"])
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            [("effective_from", "REGISTRY_EFFECTIVE_ORDER")],
        ), effective_from
        assert (refused.json()["detail"], refused.json()["errors"][0]["message"]) == (
            message,
            message,
        )
        current = shown(world, draft["id"])
        assert (current["status"], current["approval_request_id"]) == ("TESTED", None)
        etag = f'"r{current["row_version"]}"'
    later = world.policies.patch(
        f"{POLICIES}/{draft['id']}", {"effective_from": DECEMBER}, etag=etag
    )
    assert later.status_code == 200, later.text
    pass_tests(world, draft["id"])
    sent = submitted(world, draft["id"])
    assert world.policies.approve(sent["approval_request_id"]).status_code == 200
    assert kernel(world, OBTAIN, known_at=MID_DECEMBER, entity_id=world.us_id) == (
        "DO_NOT_APPLY",
        "ENTITY",
    )


def test_err_81_a_version_without_a_date_waits_for_the_published_one(world: World) -> None:  # noqa: F811
    """A PLATFORM version without an effective date takes effect at its publication: while the
    PUBLISHED version of its key is not in effect yet, it is refused; once that version is in
    effect the same version is submitted and published."""
    clock = world.policies.clock
    soon = clock.now() + timedelta(
        minutes=2
    )  # inside the approver's step-up window (PRD BR-PLT-06)
    published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=soon.isoformat())
    draft = created(world, **PLATFORM, values={AUDIT_YEARS: 10})
    pass_tests(world, draft["id"])
    refused = _submit(world, draft["id"])
    message = (
        "Version 2 takes effect on 12 Sep 2026. Choose an effective date after it, or submit "
        "this version once version 2 is in effect."
    )
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "validation-failed",
        [("effective_from", "REGISTRY_EFFECTIVE_ORDER")],
    )
    assert (refused.json()["detail"], refused.json()["errors"][0]["message"]) == (message, message)
    clock.advance(timedelta(minutes=3))
    sent = submitted(world, draft["id"])
    assert world.policies.approve(sent["approval_request_id"]).status_code == 200
    current = shown(world, draft["id"])
    assert (current["status"], current["effective_from"], current["values"]) == (
        "PUBLISHED",
        None,
        {AUDIT_YEARS: 10, CONCURRENCY: 8},
    )
    assert kernel(world, AUDIT_YEARS, known_at=clock.now()) == (10, "TENANT")


# --- the instant form of a PLATFORM version -------------------------------------------------------


def _press(found: World, values: dict[str, Any], category: str = "PLATFORM") -> dict[str, Any]:
    """SF-15:workspace "Submit for approval" for one changed category (SCREENS_B §9.6): ``POST
    /policies`` with the category, the TENANT scope and the changed values only, the test job
    without a simulation, the submit with the comment — then Marcus's approval."""
    policies = found.policies
    made = policies.post(POLICIES, {"category": category, "scope": "TENANT", "values": values})
    assert made.status_code == 201, made.text
    version_id = str(made.json()["id"])
    requested = policies.post(f"{POLICIES}/{version_id}/test", {"run_simulation": False})
    assert requested.status_code == 202, requested.text
    assert work(found, str(requested.json()["id"]))["state"] == "SUCCEEDED"
    sent = policies.post(
        f"{POLICIES}/{version_id}/submit", {"comment": "Changed in workspace settings"}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED"
    approved = policies.approve(str(sent.json()["approval_request_id"]))
    assert approved.status_code == 200, approved.text
    return shown(found, version_id)


def test_the_workspace_screen_bodies_publish_a_platform_value(world: World) -> None:  # noqa: F811
    """CFG-PLATFORM-PIN-1 with the screen's own bodies: no effective date, the changed value
    only. The version is in force from its publication, a second press works, and each press
    keeps what the press before it changed."""
    clock = world.policies.clock
    # The provisioned version was published at the frozen instant; a setting changes later.
    clock.advance(timedelta(minutes=1))
    first = _press(world, {STYLE: "MINUS"})
    assert (first["status"], first["effective_from"], first["values"]) == (
        "PUBLISHED",
        None,
        {STYLE: "MINUS"},
    )
    assert first["published_at"] is not None
    assert kernel(world, STYLE, known_at=clock.now()) == ("MINUS", "TENANT")
    clock.advance(timedelta(minutes=1))
    second = _press(world, {CONCURRENCY: 8})
    assert (second["status"], second["effective_from"], second["values"]) == (
        "PUBLISHED",
        None,
        {CONCURRENCY: 8, STYLE: "MINUS"},
    )
    measured = {
        "style": kernel(world, STYLE, known_at=clock.now()),
        "concurrency": kernel(world, CONCURRENCY, known_at=clock.now()),
        "concurrency before the second press": kernel(
            world, CONCURRENCY, known_at=clock.now() - timedelta(seconds=30)
        ),
    }
    assert measured == {
        "style": ("MINUS", "TENANT"),
        "concurrency": (8, "TENANT"),
        "concurrency before the second press": (4, "FRAMEWORK_DEFAULT"),
    }


def test_every_settings_category_takes_the_instant_form(world: World) -> None:  # noqa: F811
    """The screen sends CLOSE and INTEGRATION values as it sends PLATFORM ones; SECURITY and AI
    have no screen yet and take the same form (the supervisor's ruling of 2026-10-01, point C:
    none of the four holds a parameter a computation reads through its period rows). Two presses
    of one category follow each other — the first leaves no open version behind."""
    clock = world.policies.clock
    clock.advance(timedelta(minutes=1))
    pressed = {
        "CLOSE": ("close.late_entry_window_days", 7, 5),
        "INTEGRATION": ("data.quarantine_failed_rows", True, False),
        "SECURITY": ("platform.session_idle_minutes", 45, 30),
        "AI": ("ai.enabled", True, False),
    }
    for category, (code, value, default) in pressed.items():
        before = kernel(world, code, known_at=clock.now())
        version = _press(world, {code: value}, category)
        assert (version["status"], version["effective_from"], version["values"]) == (
            "PUBLISHED",
            None,
            {code: value},
        ), category
        assert (before, kernel(world, code, known_at=clock.now())) == (
            (default, "FRAMEWORK_DEFAULT"),
            (value, "TENANT"),
        ), category
    clock.advance(timedelta(minutes=1))
    again = _press(world, {"close.require_reconciliations_for_lock": False}, "CLOSE")
    assert again["values"] == {
        "close.late_entry_window_days": 7,
        "close.require_reconciliations_for_lock": False,
    }


def test_a_platform_version_takes_any_later_instant_and_no_earlier_one(world: World) -> None:  # noqa: F811
    """A PLATFORM version may name an instant that is no period start; an instant that has
    passed is refused as for every version that supersedes (PRD ERR-75). An accounting category
    keeps the period-start rule and needs its date."""
    clock = world.policies.clock
    mid_month = "2026-09-20T12:00:00Z"
    dated = published(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=mid_month)
    assert dated["effective_from"] == "2026-09-20T12:00:00Z"
    past = created(
        world,
        **PLATFORM,
        values={AUDIT_YEARS: 10},
        effective_from=(clock.now() - timedelta(hours=1)).isoformat(),
    )
    pass_tests(world, past["id"])
    refused = _submit(world, past["id"])
    assert (refused.status_code, fields(refused)) == (422, [("effective_from", "REQ-POL-007")])
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    accounting = {
        "category": "DISCLOSURE_ELECTION",
        "scope": "ENTITY",
        "entity_code": "AVM-DE",
    }
    off_period = world.policies.post(
        POLICIES, {**accounting, "values": {REPORTING_TYPE: "PBE"}, "effective_from": mid_month}
    )
    assert (off_period.status_code, fields(off_period)) == (422, [("effective_from", "T-PLT-32")])
    assert off_period.json()["errors"][0]["message"] == registry_versions.PERIOD_START_REQUIRED
    undated = created(world, **accounting, values={REPORTING_TYPE: "PBE"})
    pass_tests(world, undated["id"])
    needs_date = _submit(world, undated["id"])
    assert (needs_date.status_code, fields(needs_date)) == (422, [("effective_from", "T-PLT-32")])
    assert needs_date.json()["errors"][0]["message"] == registry_versions.EFFECTIVE_REQUIRED


# --- the preset -----------------------------------------------------------------------------------


def _preset_published(found: World, effective_from: str) -> dict[str, Any]:
    made = found.policies.post(PRESET, {"scope": "TENANT"})
    assert made.status_code == 201, made.text
    draft = made.json()
    dated = found.policies.patch(
        f"{POLICIES}/{draft['id']}",
        {"effective_from": effective_from},
        etag=f'"r{draft["row_version"]}"',
    )
    assert dated.status_code == 200, dated.text
    pass_tests(found, draft["id"])
    sent = submitted(found, draft["id"])
    assert found.policies.approve(sent["approval_request_id"]).status_code == 200
    return shown(found, draft["id"])


def test_a_legacy_parity_tenant_stays_one_through_later_versions(world: World) -> None:  # noqa: F811
    """A version made on the predecessor basis carries the predecessor's preset when that is not
    DEFAULT: the 31 preset values and the mode ``ssp.resolution.tenant_preset`` reads both stay.
    A version whose values are the whole set (``basis = "DEFAULTS"``) carries none."""
    preset = _preset_published(world, OCTOBER)
    assert (preset["preset_code"], len(preset["values"])) == ("LEGACY_PARITY", 31)
    kept = "alloc.discount_exception"
    assert preset["values"][kept] == "DISABLED"
    later = published(
        world, **ACCOUNTING, values={"billing.posting": "ERP"}, effective_from=NOVEMBER
    )
    assert (later["preset_code"], later["values"]) == (
        "LEGACY_PARITY",
        {**preset["values"], "billing.posting": "ERP"},
    )
    measured = {
        "15 Oct preset": _preset_at(world, MID_OCTOBER),
        "15 Nov preset": _preset_at(world, MID_NOVEMBER),
        "15 Nov kept value": kernel(world, kept, known_at=MID_NOVEMBER),
        "15 Nov billing": kernel(world, "billing.posting", known_at=MID_NOVEMBER),
    }
    assert measured == {
        "15 Oct preset": "LEGACY_PARITY",
        "15 Nov preset": "LEGACY_PARITY",
        "15 Nov kept value": ("DISABLED", "TENANT"),
        "15 Nov billing": ("ERP", "TENANT"),
    }
    alone = published(
        world,
        **ACCOUNTING,
        values={"billing.posting": "ERP"},
        basis="DEFAULTS",
        effective_from=DECEMBER,
    )
    assert (alone["preset_code"], alone["values"]) == (None, {"billing.posting": "ERP"})
    assert _preset_at(world, MID_DECEMBER) == "DEFAULT"
    assert kernel(world, kept, known_at=MID_DECEMBER) == (
        "PROPOSE_WITH_APPROVAL",
        "FRAMEWORK_DEFAULT",
    )


def test_the_legacy_parity_preset_is_a_whole_set(world: World) -> None:  # noqa: F811
    """A preset replaces the accounting policy set: a value the PUBLISHED version holds and the
    preset does not state returns to the default, by name."""
    published(world, **ACCOUNTING, values={LOSS_UNIT: "POB"}, effective_from=OCTOBER)
    made = world.policies.post(PRESET, {"scope": "TENANT"})
    assert made.status_code == 201, made.text
    draft = made.json()
    assert (draft["preset_code"], draft["unset"], len(draft["values"])) == (
        "LEGACY_PARITY",
        [LOSS_UNIT],
        31,
    )
    assert {
        "code": LOSS_UNIT,
        "before": "POB",
        "after": None,
        "change": "RETURNED_TO_DEFAULT",
    } in draft["diff_against_current"]


def test_a_patch_that_states_the_whole_set_carries_no_preset(world: World) -> None:  # noqa: F811
    """Ruling B at a PATCH (finding 3 (a) of the independent review of 2026-10-01). A draft made
    on a LEGACY_PARITY predecessor carries the preset, and a PATCH of its values leaves the code
    alone. A PATCH that states ``basis = "DEFAULTS"`` makes the values sent the whole set — a set
    no preset made — and clears the code: the published version returns every preset value to
    the default and the workspace leaves the mode with its values, not in name only."""
    _preset_published(world, OCTOBER)
    draft = created(world, **ACCOUNTING, values={LOSS_UNIT: "POB"}, effective_from=NOVEMBER)
    assert draft["preset_code"] == "LEGACY_PARITY"
    path = f"{POLICIES}/{draft['id']}"
    restated = world.policies.patch(
        path, {"values": {"billing.posting": "ERP"}}, etag=f'"r{draft["row_version"]}"'
    )
    assert restated.status_code == 200, restated.text
    assert (restated.json()["preset_code"], restated.json()["unset"]) == ("LEGACY_PARITY", [])
    whole = world.policies.patch(
        path,
        {"values": {"billing.posting": "ERP"}, "basis": "DEFAULTS"},
        etag=restated.headers["ETag"],
    )
    assert whole.status_code == 200, whole.text
    body = whole.json()
    assert (body["preset_code"], body["values"], len(body["unset"])) == (
        None,
        {"billing.posting": "ERP"},
        30,
    )
    event = _events(world, draft["id"])[-1]
    assert (event["action"], event["before"]["preset_code"], event["after"]["preset_code"]) == (
        "registry_version.update",
        "LEGACY_PARITY",
        None,
    )
    pass_tests(world, draft["id"])
    sent = submitted(world, draft["id"])
    assert world.policies.approve(sent["approval_request_id"]).status_code == 200
    current = shown(world, draft["id"])
    assert (current["preset_code"], current["values"]) == (None, {"billing.posting": "ERP"})
    assert (_preset_at(world, MID_OCTOBER), _preset_at(world, MID_NOVEMBER)) == (
        "LEGACY_PARITY",
        "DEFAULT",
    )


def test_a_draft_that_keeps_the_presets_values_carries_the_preset(world: World) -> None:  # noqa: F811
    """Ruling B (a) whatever the requests said before (the second reviewer's sequence): a draft
    made with ``basis = "DEFAULTS"`` has no code; a PATCH that empties its ``unset`` makes it
    keep the preset's 31 values, so it stands on the preset again — the draft answers the code
    and the submit stores it. The workspace never holds the preset's values under no preset."""
    preset = _preset_published(world, OCTOBER)
    draft = created(
        world, **ACCOUNTING, values={LOSS_UNIT: "POB"}, basis="DEFAULTS", effective_from=NOVEMBER
    )
    assert (draft["preset_code"], draft["unset"]) == (None, sorted(preset["values"]))
    kept = world.policies.patch(
        f"{POLICIES}/{draft['id']}", {"unset": []}, etag=f'"r{draft["row_version"]}"'
    )
    assert kept.status_code == 200, kept.text
    assert (kept.json()["preset_code"], kept.json()["unset"]) == ("LEGACY_PARITY", [])
    tested = pass_tests(world, draft["id"])
    sent = submitted(world, draft["id"])
    assert tested["content_sha256"] == sent["content_sha256"]
    assert (sent["preset_code"], sent["values"]) == (
        "LEGACY_PARITY",
        {**preset["values"], LOSS_UNIT: "POB"},
    )
    assert world.policies.approve(sent["approval_request_id"]).status_code == 200
    assert _preset_at(world, MID_NOVEMBER) == "LEGACY_PARITY"


def test_err_92_a_version_rejected_before_a_preset_was_published_is_not_reopened(
    world: World,  # noqa: F811
) -> None:
    """Finding 3 (b) of the independent review under PRD ERR-92: a version drafted on the DEFAULT
    predecessor is rejected and the preset is published. The version is not reopened over the
    preset — it would take the workspace out of the mode with a set made before the mode existed
    — and the workspace stays ``LEGACY_PARITY``. The same value in a new version stands on the
    preset: the 31 preset values and the code stay."""
    old = created(world, **ACCOUNTING, values={LOSS_UNIT: "POB"}, effective_from=OCTOBER)
    pass_tests(world, old["id"])
    _rejected(world, str(submitted(world, old["id"])["approval_request_id"]))
    preset = _preset_published(world, OCTOBER)
    assert (preset["preset_code"], len(preset["values"])) == ("LEGACY_PARITY", 31)
    _not_reopened(world, old["id"], int(preset["version_no"]), {"effective_from": NOVEMBER})
    assert shown(world, old["id"])["status"] == "REJECTED"
    assert (_preset_at(world, MID_OCTOBER), _preset_at(world, MID_NOVEMBER)) == (
        "LEGACY_PARITY",
        "LEGACY_PARITY",
    )
    fresh = published(world, **ACCOUNTING, values={LOSS_UNIT: "POB"}, effective_from=NOVEMBER)
    assert (fresh["preset_code"], fresh["values"]) == (
        "LEGACY_PARITY",
        {**preset["values"], LOSS_UNIT: "POB"},
    )
    assert _preset_at(world, MID_NOVEMBER) == "LEGACY_PARITY"
    assert kernel(world, "alloc.discount_exception", known_at=MID_NOVEMBER) == (
        "DISABLED",
        "TENANT",
    )


# --- the named human approver ---------------------------------------------------------------------


def test_a_version_that_changes_the_retention_families_is_withheld_from_auto_approval(
    world: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-98 candidate 86 under the whole set (the supervisor's ruling of 2026-10-01 on the
    independent review): the check reads what a version CHANGES, not the keys of its set.
    Stating the families, changing one of them and returning them to the default are changes of
    the parameter, and each is withheld from auto-approval; a version that only carries them
    forward changes nothing of them and is asked for auto-approval like any other — its approver
    confirms no retention period (``test_the_retention_confirmation_is_…``). No tenant rule
    approves a registry version today (ruling R-26 (b)), so what the submit asks of the engine
    is read at the call."""
    asked: list[bool] = []
    submit = approvals.submit

    def recording(uow: Any, **arguments: Any) -> Any:
        asked.append(arguments["auto_approval"])
        return submit(uow, **arguments)

    monkeypatch.setattr(approvals, "submit", recording)
    families = dict(sd.RETENTION_FAMILIES)
    published(world, **PLATFORM, values={sd.RETENTION_PARAMETER: families}, effective_from=OCTOBER)
    carried = published(world, **PLATFORM, values={STYLE: "MINUS"}, effective_from=NOVEMBER)
    assert carried["values"] == {STYLE: "MINUS", sd.RETENTION_PARAMETER: families}
    family = sorted(families)[0]
    other = next(literal for literal in sd.RETENTION_LITERALS if literal != families[family])
    published(
        world,
        **PLATFORM,
        values={sd.RETENTION_PARAMETER: {**families, family: other}},
        effective_from=DECEMBER,
    )
    returning = created(
        world,
        **PLATFORM,
        values={},
        unset=[sd.RETENTION_PARAMETER],
        effective_from="2027-01-01T05:00:00Z",
    )
    pass_tests(world, returning["id"])
    assert submitted(world, returning["id"])["values"] == {STYLE: "MINUS"}
    assert asked == [False, True, False, False]


def test_the_retention_confirmation_is_the_approval_of_the_version_that_stated_the_families(
    world: World,  # noqa: F811
) -> None:
    """A later PLATFORM version carries the families forward; the person who approved its change
    did not confirm a retention period. The policy's source — the snapshot manifest's
    ``CONFIRMED:`` line — names the version that last changed the families and its approver, and
    beside them the version in force when that is another one (04 T-PLT-31 rev 1.183)."""
    families = dict(sd.RETENTION_FAMILIES)
    clock = world.policies.clock
    stated = published(
        world, **PLATFORM, values={sd.RETENTION_PARAMETER: families}, effective_from=OCTOBER
    )
    # Each approval has its own instant (inside the approver's step-up window, PRD BR-PLT-06), so
    # the source says WHICH approval it names: the carrying version's is a minute later.
    clock.advance(timedelta(minutes=1))
    carried = published(world, **PLATFORM, values={STYLE: "MINUS"}, effective_from=NOVEMBER)
    family = sorted(families)[0]
    other = next(literal for literal in sd.RETENTION_LITERALS if literal != families[family])
    clock.advance(timedelta(minutes=1))
    changed = published(
        world,
        **PLATFORM,
        values={sd.RETENTION_PARAMETER: {**families, family: other}},
        effective_from=DECEMBER,
    )
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        sources = [
            snapshot_job.retention_policy_for(session, known_at).policy.source  # type: ignore[union-attr]
            for known_at in (MID_OCTOBER, MID_NOVEMBER, MID_DECEMBER)
        ]
    marcus = world.policies.marcus.member.user_id
    first = f"approved by {marcus} at {FROZEN_AT.isoformat()}"
    third = f"approved by {marcus} at {(FROZEN_AT + timedelta(minutes=2)).isoformat()}"
    assert sources == [
        f"registry version {stated['id']} {first}",
        f"registry version {stated['id']} {first}; in force as registry version {carried['id']}",
        f"registry version {changed['id']} {third}",
    ]


def test_err_77_names_the_retention_confirmation_and_its_start(world: World) -> None:  # noqa: F811
    """PRD ERR-77 is worded from ``snapshot_retention.ahead``: (approved at, in force from). The
    families were confirmed by the approval of the version that stated them and take effect with
    it. A later PLATFORM version that carries them forward — approved a minute later, dated a
    month later — is the PUBLISHED one and is neither the confirmation nor the start (minor 2
    of the independent review of 2026-10-01: its own day and date were answered). A still later
    version that CHANGES a family does not move the answer, and neither does one that returns
    the families to the default: copies are possible from the first instant at which a
    confirmed policy is in force."""
    clock = world.policies.clock
    families = dict(sd.RETENTION_FAMILIES)
    published(world, **PLATFORM, values={sd.RETENTION_PARAMETER: families}, effective_from=OCTOBER)
    clock.advance(timedelta(minutes=1))
    published(world, **PLATFORM, values={STYLE: "MINUS"}, effective_from=NOVEMBER)
    confirmed = (FROZEN_AT, datetime(2026, 10, 1, 4, tzinfo=UTC))
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        assert snapshot_retention.ahead(session, clock.now()) == confirmed
    assert snapshot_retention.copy(confirmed) == (
        "Sandbox copies are possible from 01 Oct 2026 04:00 UTC: the snapshot retention policy "
        "approved on 12 Sep 2026 takes effect then."
    )
    family = sorted(families)[0]
    other = next(literal for literal in sd.RETENTION_LITERALS if literal != families[family])
    clock.advance(timedelta(minutes=1))
    published(
        world,
        **PLATFORM,
        values={sd.RETENTION_PARAMETER: {**families, family: other}},
        effective_from=DECEMBER,
    )
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        assert snapshot_retention.ahead(session, clock.now()) == confirmed
    # Nor does a version that returns the families to the default from January: it is stepped
    # over, and copies are possible from the first instant a confirmed policy is in force.
    clock.advance(timedelta(minutes=1))
    returned = published(
        world,
        **PLATFORM,
        values={},
        unset=[sd.RETENTION_PARAMETER],
        effective_from="2027-01-01T05:00:00Z",
    )
    assert sd.RETENTION_PARAMETER not in returned["values"]
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        assert snapshot_retention.ahead(session, clock.now()) == confirmed


# --- one open version of a scope key --------------------------------------------------------------


def test_a_create_decides_its_statement_under_the_lock_of_its_key(world: World) -> None:  # noqa: F811
    """Finding 5 of the independent review of 2026-10-01, under two sessions. The holder holds
    the key's advisory lock and has published another version of the key (by rows), uncommitted.
    The request — a create with ``basis = "DEFAULTS"`` — is observed waiting for that lock; the
    holder commits. The draft's ``unset`` names what the version published in between holds: the
    statement is decided under the lock, after the look for an open version, and not from a
    predecessor read before it — which left a draft whose ``supersedes_version_id`` was the new
    version while its ``unset`` came from the old one."""
    policies = world.policies
    answers: list[Any] = []

    def create() -> None:
        answers.append(
            policies.post(POLICIES, {**PLATFORM, "values": {AUDIT_YEARS: 10}, "basis": "DEFAULTS"})
        )

    request = threading.Thread(target=create, name="create-on-basis-defaults")
    ctx = RequestContext(
        principal=system_principal(world.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-registry-create",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=policies.clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(policies.settings.file_root)
    try:
        with (
            observing_checkouts() as backends,
            unit_of_work(
                ctx, clock=policies.clock, keyring=policies.keyring, files=files
            ) as holder,
        ):
            presets.serialise_key(
                holder.session,
                world.tenant_id,
                category=RegistryCategory.PLATFORM,
                scope=RegistryScope.TENANT,
                book_code=None,
                entity_id=None,
            )
            between = publish_registry_version(
                holder.session,
                tenant_id=world.tenant_id,
                category=RegistryCategory.PLATFORM,
                values={CONCURRENCY: 8},
                at=PUBLISHED_AT,
            )
            holder_pid = backend_pid(holder.session)
            request.start()
            blocked_pid, blocked_in = await_lock_wait(
                holder.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=15,
                expect="pg_advisory_xact_lock",
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            holder.commit()
    finally:
        if request.ident is not None:
            request.join(timeout=30)
    assert not request.is_alive()
    answer = answers[0]
    assert answer.status_code == 201, answer.text
    draft = answer.json()
    assert (draft["values"], draft["unset"], draft["supersedes_version_id"]) == (
        {AUDIT_YEARS: 10},
        [CONCURRENCY],
        str(between),
    )
    assert draft["diff_against_current"] == [
        {"code": AUDIT_YEARS, "before": None, "after": 10, "change": "ADDED"},
        {"code": CONCURRENCY, "before": 8, "after": None, "change": "RETURNED_TO_DEFAULT"},
    ]


def test_reopening_a_rejected_version_waits_for_a_create_in_its_scope_key(world: World) -> None:  # noqa: F811
    """PRD SM-04 under two sessions (the supervisor's ruling of 2026-10-01, point E). The holder
    creates a draft of the key and does not commit, so it holds the key's advisory lock. The
    request — an edit that reopens a rejected version of the same key — is observed waiting for
    that lock; once the holder commits, it finds the other version open and is refused. Without
    the lock it saw no open version and both became open."""
    policies = world.policies
    rejected = created(world, **PLATFORM, values={CONCURRENCY: 8}, effective_from=OCTOBER)
    pass_tests(world, rejected["id"])
    request_id = str(submitted(world, rejected["id"])["approval_request_id"])
    declined = policies.post(
        f"{APPROVALS}/{request_id}/reject", {"comment": "Not now"}, actor=policies.marcus
    )
    assert declined.status_code == 200, declined.text
    current = shown(world, rejected["id"])
    assert current["status"] == "REJECTED"
    answers: list[Any] = []

    def reopen() -> None:
        answers.append(
            policies.patch(
                f"{POLICIES}/{rejected['id']}",
                {"effective_from": NOVEMBER},
                etag=f'"r{current["row_version"]}"',
            )
        )

    request = threading.Thread(target=reopen, name="reopen-a-rejected-version")
    ctx = RequestContext(
        principal=system_principal(world.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-registry-reopen",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=policies.clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(policies.settings.file_root)
    try:
        with (
            observing_checkouts() as backends,
            unit_of_work(
                ctx, clock=policies.clock, keyring=policies.keyring, files=files
            ) as holder,
        ):
            registry_versions.create_policy(
                holder,
                category=RegistryCategory.PLATFORM,
                scope=RegistryScope.TENANT,
                entity_code=None,
                book_code=None,
                values={AUDIT_YEARS: 10},
                effective_from=None,
            )
            holder_pid = backend_pid(holder.session)
            request.start()
            blocked_pid, blocked_in = await_lock_wait(
                holder.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=15,
                expect="pg_advisory_xact_lock",
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            holder.commit()
    finally:
        if request.ident is not None:
            request.join(timeout=30)
    assert not request.is_alive()
    answer = answers[0]
    assert (answer.status_code, slug(answer), fields(answer)) == (
        409,
        "invalid-transition",
        [("status", "SM-04")],
    )
    assert [(number, status) for number, status, _ in _stored(world, "PLATFORM")] == [
        (1, "PUBLISHED"),
        (2, "REJECTED"),
        (3, "DRAFT"),
    ]


def test_a_rule_set_version_create_waits_for_the_row_a_reopening_holds(world: World) -> None:  # noqa: F811
    """Why rule set (and obligation template) versions set no ``serialise`` lock: their create
    locks every version row of the set ``FOR UPDATE``, the rejected one among them, and a
    reopening holds that row (``rule_sets.lock_version``). The holder takes the row as a
    reopening does; the request — the create of the next version — is observed waiting for it;
    the holder makes the version a draft again and commits, and the create then finds it open.
    Not a repair: the two already waited for each other on this row.

    What it does not show. ``lifecycle.reopen`` writes twice — the status, then the hash and the
    request of the draft (DB-04 freezes them in the first statement) — and PostgreSQL re-checks
    the foreign keys of a row its own transaction wrote, so the second statement asks for the
    rule set's row, which the create holds ``FOR UPDATE``: in the product this interleaving ends
    in a deadlock that PostgreSQL resolves, and one of the two commands answers 409
    ``lock-conflict`` (measured 2026-10-01: the create, after one second). One version is open
    either way; the cleaner order is the owners' (the lane's report)."""
    policies = world.policies
    rule_set_id, version_id = policies.tested(
        "ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE]
    )
    request_id = str(policies.submit(version_id)["approval_request_id"])
    declined = policies.post(
        f"{APPROVALS}/{request_id}/reject", {"comment": "Not now"}, actor=policies.marcus
    )
    assert declined.status_code == 200, declined.text
    answers: list[Any] = []

    def create() -> None:
        answers.append(policies.post(f"{RULE_SETS}/{rule_set_id}/versions", {}))

    request = threading.Thread(target=create, name="create-the-next-rule-set-version")
    try:
        with (
            observing_checkouts() as backends,
            tenant_session(context(world.tenant_id)) as holder,
        ):
            held = rule_sets.lock_version(holder, UUID(version_id))
            assert held["status"] == "REJECTED"
            holder_pid = backend_pid(holder)
            request.start()
            blocked_pid, blocked_in = await_lock_wait(
                holder,
                holder_pid=holder_pid,
                backends=backends,
                timeout=15,
                expect="for update",
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            assert "rule_set_version" in blocked_in
            holder.execute(
                update(rule_set_version)
                .where(rule_set_version.c.id == UUID(version_id))
                .values(status="DRAFT")
            )
    finally:
        if request.ident is not None:
            request.join(timeout=30)
    assert not request.is_alive()
    answer = answers[0]
    assert (answer.status_code, slug(answer), fields(answer)) == (
        409,
        "invalid-transition",
        [(None, "SM-04")],
    )
    assert policies.rows(
        select(rule_set_version.c.version_no, rule_set_version.c.status).where(
            rule_set_version.c.rule_set_id == UUID(rule_set_id)
        )
    ) == [{"version_no": 1, "status": "DRAFT"}]

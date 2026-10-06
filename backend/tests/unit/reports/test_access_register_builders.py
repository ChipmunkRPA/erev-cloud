"""RPT-23 to RPT-26, RPT-43 and RPT-44 builders — CPU witnesses (BUILD_SPEC RPS-10; SCREENS_B
§5.6.5). The specification grids are parsed from SCREENS_B, so a specification edit or a builder
column drift fails here; the row shaping is proven on pure inputs. The acceptance over worlds built
through the product's commands is ``tests/domain/reports/test_registers_access.py`` (database).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.audit import REDACT
from erev_api.db.tables import audit_event
from erev_api.domain.reports import catalogue, framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import api_client_inventory as inventory
from erev_api.domain.reports.builders import approvals_register as approvals
from erev_api.domain.reports.builders import audit_log_export as audit_export
from erev_api.domain.reports.builders import chain_verification_report as verifications
from erev_api.domain.reports.builders import config_change_register as changes
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.builders import sod_conflict_report as conflicts
from erev_api.domain.reports.builders import user_access_listing as access
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.domain.reports.outputs import NOT_SHOWN
from erev_api.domain.ssp import publication
from erev_api.problems import Problem
from sqlalchemy.dialects import postgresql
from support import report_specs

MAYA: UUID = UUID("00000000-0000-4000-8000-00000000000a")
PRIYA: UUID = UUID("00000000-0000-4000-8000-00000000000b")
MARCUS: UUID = UUID("00000000-0000-4000-8000-00000000000c")
GRACE: UUID = UUID("00000000-0000-4000-8000-00000000000d")
NAMES = {MAYA: "Maya Chen", PRIYA: "Priya Raman", MARCUS: "Marcus Webb", GRACE: "Grace Okafor"}
AT: datetime = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
GRIDS = ((23, changes), (24, access), (25, conflicts), (26, approvals), (44, verifications))
MODULES = (*GRIDS, (43, audit_export))


def _id(number: int) -> UUID:
    return UUID(int=number)


def _params(parameters: dict[str, Any], *, known_at: datetime = AT) -> ReportParams:
    return ReportParams(
        report_code="probe",
        report_version=1,
        parameters=parameters,
        entity_ids=(),
        known_at=known_at,
    )


# --- specification and registration ---------------------------------------------------------------


@pytest.mark.parametrize(("number", "module"), GRIDS)
def test_columns_are_the_specification_grid(number: int, module: Any) -> None:
    """SCREENS_B §5.6.5: the builder's columns are the grid's fields in its order; RPT-26 carries
    the subject id and the content hash the grid gained in rev 1.25 (export and API only)."""
    keys = [column.key for column in module.COLUMNS]
    assert keys == report_specs.fields(number, module.CODE)
    assert len(set(keys)) == len(keys) and "row_key" not in keys
    headers = {column.key: column.header for column in module.COLUMNS}
    for header, names in report_specs.grid(number, module.CODE):
        if len(names) == 1:
            assert headers[names[0]] == header, names


def test_rpt_43_columns_are_t_plt_19_in_the_specified_order() -> None:
    """RPT-43: every T-PLT-19 column but ``tenant_id``, in the order the specification lists,
    with the column names as headers."""
    section = report_specs.section(43, audit_export.CODE)
    listed = section.split("headers equal to the column names:", 1)[1].split("; JSON-valued", 1)[0]
    names = re.findall(r"`([a-z_]+)`", listed)
    assert list(audit_export.FIELDS) == names and len(names) == 28
    assert set(names) == {column.name for column in audit_event.c} - {"tenant_id"}
    assert [(column.key, column.header) for column in audit_export.COLUMNS] == [
        (name, name) for name in names
    ]
    assert "`row_key` `event:<chain_seq>`" in section
    assert "`row_count`, `first_chain_seq`, `last_chain_seq`, `last_hmac`" in section
    assert set(audit_export.JSON_COLUMNS) == {"before", "after", "diff", "detail"}


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_registration_and_catalogue(number: int, module: Any) -> None:
    """``framework.BUILDERS`` admits the six codes with an ``open`` source contract that names
    what it reads; each definition's kind and row key are the specification's."""
    assert framework.BUILDERS[module.CODE] is module.build
    contract = framework.SOURCE_CONTRACTS[module.CODE]
    assert contract.strategy == "open" and len(contract.open) == 1
    assert f"RPT-{number}" in contract.open[0]
    definition = DEFINITIONS_BY_CODE[module.CODE]
    section = report_specs.section(number, module.CODE)
    assert f"| Kind, formats | `{definition.kind}`;" in section
    assert f"`row_key` `{module.ROW_KEY_PREFIX}" in section


def test_parameter_copy_and_defaults_follow_the_specification() -> None:
    assert support.AS_OF_FUTURE in report_specs.section(24, access.CODE)
    assert "as RPT-24" in report_specs.section(25, conflicts.CODE)
    assert f'"{audit_export.START_AFTER_END}"' in report_specs.section(43, audit_export.CODE)
    assert verifications.START_AFTER_END == audit_export.START_AFTER_END
    assert "30 days before now; now" in report_specs.section(44, verifications.CODE)
    assert verifications.DEFAULT_WINDOW == timedelta(days=30)
    assert "Currency view | yes (functional amounts of requests)" in report_specs.section(
        26, approvals.CODE
    )
    assert framework.PARAMETER_DEFAULTS[approvals.CODE] == {"currency_view": "functional"}
    # RPT-23 "Change types": the nine configuration subjects of E-08, each with a reader
    assert set(changes.READERS) == {item.value for item in catalogue.CONFIGURATION_SUBJECTS}
    section = report_specs.section(23, changes.CODE)
    assert all(f"`{code}`" in section for code in changes.SUBJECT_TYPES)
    assert changes.SSP_APPROVE_ACTION == publication.APPROVE_ACTION


def test_as_of_defaults_to_known_at_and_refuses_the_future() -> None:
    assert support.as_of_instant(_params({})) == AT
    earlier = support.as_of_instant(_params({"as_of": "2026-09-12T13:30:00+02:00"}))
    assert earlier == datetime(2026, 9, 12, 11, 30, tzinfo=UTC) and earlier.tzinfo is UTC
    assert support.as_of_instant(_params({"as_of": "2026-09-12T12:00:00Z"})) == AT
    with pytest.raises(Problem) as refused:
        support.as_of_instant(_params({"as_of": "2026-09-12T12:00:01Z"}))
    (error,) = refused.value.errors
    assert (error.field, error.message) == ("parameters.as_of", support.AS_OF_FUTURE)
    assert support.instant(_params({}), "from") is None


# --- RPT-23 ---------------------------------------------------------------------------------------


def _decision(
    index: int,
    approver: UUID | None,
    *,
    kind: str = "APPROVE",
    step_no: int = 1,
    step_name: str = "Approval",
    on_behalf_of: UUID | None = None,
    comment: str | None = "OK",
    rule: UUID | None = None,
    rule_version: UUID | None = None,
) -> support.Decision:
    return support.Decision(
        id=_id(1000 + index),
        decision=kind,
        approver_id=approver,
        approver_kind="SYSTEM" if approver is None else "USER",
        on_behalf_of_id=on_behalf_of,
        step_no=step_no,
        step_name=step_name,
        decided_at=AT + index * MINUTE,
        comment=comment,
        subject_content_sha256=f"{index:064x}",
        auto_rule_id=rule,
        auto_rule_set_version_id=rule_version,
    )


def _request(
    request_no: str,
    *decisions: support.Decision,
    status: str = "APPROVED",
    subject_type: str = "ACCOUNT_MAPPING_VERSION",
    subject: int = 1,
    preparer: UUID | None = MAYA,
    amount: str | None = None,
    currency: str | None = None,
    flags: tuple[str, ...] = (),
    entity: UUID | None = None,
) -> support.Request:
    decided = decisions[-1].decided_at if decisions and status != "PENDING" else None
    return support.Request(
        id=_id(int(request_no[-3:])),
        request_no=request_no,
        subject_type=subject_type,
        subject_id=_id(500 + subject),
        status=status,
        summary=f"Summary of {request_no}",
        entity_id=entity,
        amount_functional=None if amount is None else Decimal(amount),
        amount_currency=currency,
        flags=flags,
        preparer_id=preparer,
        preparer_kind="SYSTEM" if preparer is None else "USER",
        submitted_at=AT - MINUTE,
        decided_at=decided,
        comment=None,
        subject_content_sha256="f" * 64,
        decisions=tuple(decisions),
    )


def test_content_changes_leave_out_the_lifecycle_stamps() -> None:
    diff = [
        {"path": "status", "before": "APPROVED", "after": "PUBLISHED"},
        {"path": "published_at", "before": None, "after": "2026-09-12T12:00:00.000000Z"},
        {"path": "published_by", "before": None, "after": str(MARCUS)},
        {"path": "approval_request_id", "before": None, "after": str(_id(7))},
        {"path": "content_sha256", "before": "a", "after": "b"},
        {"path": "effective_to", "before": None, "after": "2026-10-01"},
        {"path": "name", "before": None, "after": "AVM-MAP-2026-01"},
        {"path": "rules.REVENUE.gl_account_code", "before": "4000", "after": "4010"},
        {"path": "effective_from", "before": None, "after": "2026-01-01"},
    ]
    assert changes.content_changes(diff) == 3
    assert changes.content_changes(None) == changes.content_changes([]) == 0
    summary = {"diff_summary": {"added": 0, "removed": 2, "changed": 1}}
    assert changes.diff_summary_changes(summary) == 3
    assert changes.diff_summary_changes({"diff_summary": {"added": 7, "unchanged": 3}}) == 7
    assert changes.diff_summary_changes({}) == changes.diff_summary_changes(None) == 0
    assert changes.diff_summary_changes({"diff_summary": None}) == 0


def test_author_differs_counts_a_delegated_decision_of_the_author() -> None:
    maya = (MAYA, "USER")
    assert changes.author_differs(maya, [_decision(1, PRIYA), _decision(2, MARCUS)]) is True
    assert changes.author_differs(maya, [_decision(1, MAYA)]) is False
    assert changes.author_differs(maya, [_decision(1, PRIYA, on_behalf_of=MAYA)]) is False
    assert changes.author_differs(maya, [_decision(1, None, kind="AUTO_APPROVE")]) is True
    assert changes.author_differs((None, "SYSTEM"), [_decision(1, PRIYA)]) is True
    assert changes.author_differs(maya, []) is True


def test_config_rows_take_author_label_and_effective_date_from_the_subject() -> None:
    mapping = changes.Source(
        request=_request("APR-000003", _decision(1, MARCUS), preparer=PRIYA),
        subject=changes.Subject(
            label="AVM-MAP-2026-01 v1",
            effective_from=date(2026, 1, 1),
            author=(MAYA, "USER"),
            simulation_attached=True,
        ),
        changed_field_count=9,
        test_evidence_count=2,
    )
    role = changes.Source(
        request=_request(
            "APR-000002", _decision(3, MAYA), subject_type="ROLE_CHANGE", preparer=MAYA
        ),
        subject=changes.Subject(
            label="Deal desk analyst",
            effective_from=None,
            author=None,
            takes_effect_on_approval=True,
        ),
        changed_field_count=1,
        test_evidence_count=0,
    )
    gone = changes.Source(
        request=_request(
            "APR-000001",
            _decision(2, PRIYA, kind="REJECT", comment="No"),
            status="REJECTED",
            subject_type="SSP_BOOK_VERSION",
        ),
        subject=None,
        changed_field_count=0,
        test_evidence_count=0,
    )
    rows, totals = changes.dataset_rows([mapping, role, gone], NAMES)
    assert [row["row_key"] for row in rows] == [
        "change:APR-000001",
        "change:APR-000002",
        "change:APR-000003",
    ]
    rejected, self_approved, published = rows
    assert (published["object_label"], published["effective_from"]) == (
        "AVM-MAP-2026-01 v1",
        date(2026, 1, 1),
    )
    # the author is the version's creator, not the request's preparer (REQ-POL-003)
    assert (published["author"], published["approvers"], published["author_differs"]) == (
        "Maya Chen",
        "Marcus Webb",
        True,
    )
    assert (
        published["changed_field_count"],
        published["simulation_attached"],
        published["test_evidence_count"],
    ) == (9, True, 2)
    # a change without a version takes effect with its approval; its preparer is its author
    assert (self_approved["author"], self_approved["author_differs"]) == ("Maya Chen", False)
    assert self_approved["effective_from"] == (AT + 3 * MINUTE).date()
    # a subject that no longer resolves keeps the request's summary; a rejection approves nobody
    assert (rejected["object_label"], rejected["status"], rejected["approvers"]) == (
        "Summary of APR-000001",
        "REJECTED",
        None,
    )
    assert (rejected["effective_from"], rejected["simulation_attached"]) == (None, False)
    assert totals == {"row_count": 3, "author_equals_approver_count": 1}


# --- RPT-24 ---------------------------------------------------------------------------------------


def _assignment(
    role_code: str,
    *,
    index: int = 1,
    valid_from: datetime = AT - MINUTE,
    valid_to: datetime | None = None,
    revoked_at: datetime | None = None,
    entity_ids: tuple[UUID, ...] = (),
) -> dict[str, Any]:
    return {
        "id": _id(index),
        "role_code": role_code,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "revoked_at": revoked_at,
        "is_all_entities": not entity_ids,
        "entity_ids": list(entity_ids),
    }


def test_in_force_is_d80_rule_2() -> None:
    assert access.in_force(_assignment("viewer", valid_from=AT), AT) is True
    assert access.in_force(_assignment("viewer", valid_from=AT + MINUTE), AT) is False
    # revoked or expired exactly at the instant: no longer in force; afterwards: still in force
    assert access.in_force(_assignment("viewer", revoked_at=AT), AT) is False
    assert access.in_force(_assignment("viewer", revoked_at=AT + MINUTE), AT) is True
    assert access.in_force(_assignment("viewer", valid_to=AT), AT) is False
    assert access.in_force(_assignment("viewer", valid_to=AT + MINUTE), AT) is True


def test_removed_memberships_list_their_latest_grant_per_role() -> None:
    first = _assignment("viewer", index=1, valid_from=AT - 3 * MINUTE, revoked_at=AT - 2 * MINUTE)
    again = _assignment("viewer", index=2, valid_from=AT - MINUTE, revoked_at=AT)
    auditor = _assignment("auditor", index=3, valid_from=AT - 2 * MINUTE, revoked_at=AT)
    later = _assignment("controller", index=4, valid_from=AT + MINUTE)
    rows = [first, again, auditor, later]
    assert access.listed_assignments(rows, at=AT, removed=False) == []
    assert access.listed_assignments(rows, at=AT, removed=True) == [auditor, again]
    assert access.listed_assignments(rows, at=AT - MINUTE, removed=False) == [auditor, again]
    removed = {"status": "REMOVED", "removed_at": AT}
    assert access.removed_by(removed, AT) and not access.removed_by(removed, AT - MINUTE)
    assert not access.removed_by({"status": "SUSPENDED", "removed_at": None}, AT)


class _Answer:
    """What a session answers: a scalar, rows, or rows read as mappings."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def mappings(self) -> Any:
        return iter(self.value)

    def __iter__(self) -> Any:
        return iter(self.value)


class _Reads:
    """A unit of work whose session answers a statement by the table it reads, and keeps what it
    was asked, in order. ``clock`` is the statement without a table: the transaction's time."""

    def __init__(self, **answers: Any) -> None:
        self.session = self
        self.answers = answers
        self.asked: list[str] = []
        self.statements: list[Any] = []

    def _answer(self, statement: Any) -> Any:
        source = next(iter(statement.get_final_froms()), None)
        while hasattr(source, "left"):  # a join: its leftmost table
            source = source.left
        name = "clock" if source is None else str(source.name)
        self.asked.append(name)
        self.statements.append(statement)
        return self.answers[name]

    def execute(self, statement: Any) -> _Answer:
        return _Answer(self._answer(statement))

    def scalars(self, statement: Any) -> Any:
        return iter(self._answer(statement))


def _membership(index: int, name: str, status: str, **values: Any) -> dict[str, Any]:
    return {
        "id": _id(index),
        "user_id": _id(100 + index),
        "email": f"{name}@avenmoor.test",
        "display_name": name.title(),
        "status": status,
        "removed_at": None,
        "updated_at": AT - 30 * MINUTE,
        "user_updated_at": AT - 30 * MINUTE,
        "identity_withheld": False,
        "last_login_at": None,
        **values,
    }


def _found_removed(at: str | None) -> dict[str, Any]:
    """``before`` of the event of an invitation that found the membership REMOVED."""
    return {"status": "REMOVED", "removed_at": at}


# What the listing asks the trail: the invitations that found a membership REMOVED, in the order
# they happened — and no bound on the event's time (``ended_removals`` says why).
_TRAIL_ASKED = (
    "erev.audit_event.action = 'tenant_membership.invite' "
    "AND (erev.audit_event.before ->> 'status') = 'REMOVED' "
    "ORDER BY erev.audit_event.occurred_at, erev.audit_event.chain_seq"
)


def _where(statement: Any) -> str:
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split()).split(" WHERE ", 1)[1]


def test_a_removal_that_a_later_invitation_ended_is_read_from_its_interval() -> None:
    """04 T-PLT-07 rev 1.307 (item ACCESS-LISTING-SECOND-LIFE-1): a membership's row keeps its
    last removal only — invited again, ``removed_at`` is NULL — so ``removed_by`` takes the
    removals a later invitation ended, each as (removed, invited again): removed from the
    removal's instant up to the invitation's, a member from the invitation on. The row of a
    member who is removed now still says it of its own removal.

    Fail-first (317f62a9b): ``removed_by`` took the row alone — ``TypeError``, three arguments."""
    invited = {"status": "INVITED", "removed_at": None}
    ended = [(AT - 10 * MINUTE, AT - 5 * MINUTE), (AT - 2 * MINUTE, AT)]
    assert not access.removed_by(invited, AT - 7 * MINUTE)  # the row alone knows no removal
    assert access.removed_by(invited, AT - 10 * MINUTE, ended)  # from the removal's instant
    assert access.removed_by(invited, AT - 7 * MINUTE, ended)
    assert not access.removed_by(invited, AT - 5 * MINUTE, ended)  # invited again: a member
    assert not access.removed_by(invited, AT - 3 * MINUTE, ended)  # between the two removals
    assert access.removed_by(invited, AT - MINUTE, ended)
    assert not access.removed_by(invited, AT, ended)
    assert not access.removed_by(invited, AT - 11 * MINUTE, ended)  # before the first removal
    removed_now = {"status": "REMOVED", "removed_at": AT}
    assert access.removed_by(removed_now, AT, ended[:1])
    assert not access.removed_by(removed_now, AT - 3 * MINUTE, ended[:1])


def test_the_ended_removals_are_the_invitations_of_removed_members_in_the_trail() -> None:
    """The reader against its writer (``users.invite_user``): the event of an invitation that
    found the membership REMOVED states that status and the ``removed_at`` it cleared in its
    ``before``, in the canonical form of the trail, and the event's time is the invitation's.
    ``ended_removals`` asks the trail for exactly those events — a first invitation and a refused
    one have no ``before`` — whatever their time: the run's cutoff does not bound this read (the
    builder says why). It answers them per membership in the order they happened; an event
    without the removal's instant states no interval. The listing's definition names the trail
    among its sources (REQ-RPT-027), and so does what a run says it read live."""
    lena, otto = UUID(int=0x1E), UUID(int=0x07)
    trail = _Reads(
        audit_event=[
            (lena, _found_removed("2026-09-12T11:50:00.000000Z"), AT - 5 * MINUTE),
            (otto, _found_removed(None), AT - 4 * MINUTE),
            (lena, _found_removed("2026-09-12T11:58:00.000000Z"), AT),
        ]
    )
    assert access.ended_removals(trail) == {
        lena: [(AT - 10 * MINUTE, AT - 5 * MINUTE), (AT - 2 * MINUTE, AT)]
    }
    [statement] = trail.statements
    assert _where(statement) == _TRAIL_ASKED
    assert "audit_event" in DEFINITIONS_BY_CODE[access.CODE].ipe_logic["source_tables"]
    [read_live] = framework.SOURCE_CONTRACTS[access.CODE].open
    assert "the audit events of invitations" in read_live


def test_an_invitation_after_the_cutoff_ends_a_removal_that_stood_at_it() -> None:
    """The trail is the one read of the listing that the run's record cutoff does not bound (04
    T-PLT-07 rev 1.307; the supervisor's ruling of 2026-10-02). Marcus was removed at AT - 10
    minutes and invited again at AT - 5 minutes. A run cut at AT - 7 minutes, whose transaction
    began before the invitation committed, reads his row after it: INVITED, no ``removed_at``.
    The removal that stood at the cutoff is stated by the invitation's event alone, and that
    event is recorded after the cutoff. As of an instant inside the removal the run leaves him
    out and, with removed members, lists him; as of an instant before it he is a member.

    Fail-first (317f62a9b, the row alone; and the event dropped for its time): as of the instant
    inside the removal the run listed Marcus as a member."""
    cut = AT - 7 * MINUTE
    maya = _membership(1, "maya", "ACTIVE")
    marcus = _membership(2, "marcus", "INVITED", updated_at=AT - 5 * MINUTE)
    invitation = (marcus["id"], _found_removed("2026-09-12T11:50:00.000000Z"), AT - 5 * MINUTE)

    runs: list[_Reads] = []

    def listed(at: datetime, **parameters: Any) -> list[tuple[str, str]]:
        run = _Reads(
            clock=cut,  # the transaction's time: the record cutoff is the run's known_at
            tenant_membership=[maya, marcus],
            role_assignment=[],
            audit_event=[invitation],
            user_mfa_factor=[],
        )
        runs.append(run)
        found = access.members(run, _params(parameters, known_at=cut), at=at)
        return [(member.display_name, member.status) for member in found]

    inside, before = AT - 8 * MINUTE, AT - 11 * MINUTE
    assert listed(inside) == [("Maya", "ACTIVE")]
    assert listed(inside, include_removed=True) == [("Maya", "ACTIVE"), ("Marcus", "INVITED")]
    assert listed(before) == [("Maya", "ACTIVE"), ("Marcus", "INVITED")]
    for run in runs:
        assert run.asked == [
            "clock",
            "tenant_membership",
            "role_assignment",
            "audit_event",
            "user_mfa_factor",
        ]
        assert _where(run.statements[3]) == _TRAIL_ASKED  # the run asks it without its cutoff


def test_a_run_cut_inside_an_ended_removal_is_refused_by_name() -> None:
    """REGISTER-CUTOFF-1 where a second invitation has ended a removal (04 T-PLT-07 rev 1.307;
    test only). The invitation writes the membership's row, so an explicit historical run cut
    inside the removal it ended meets a row changed after its cutoff and is refused by name on
    ``known_at``: the row keeps no status of that instant, and the trail states when the member
    was removed — not what the Membership cell read. The refusal comes before the assignments
    and the trail are asked."""
    cut = AT - 7 * MINUTE  # removed at AT - 10 minutes, invited again at AT - 5 minutes
    marcus = _membership(2, "marcus", "INVITED", updated_at=AT - 5 * MINUTE)
    run = _Reads(clock=AT, tenant_membership=[marcus])
    params = ReportParams(
        report_code=access.CODE,
        report_version=1,
        parameters={},
        entity_ids=(),
        known_at=cut,
        historical=True,
    )
    with pytest.raises(Problem) as refused:
        access.members(run, params, at=cut)
    (error,) = refused.value.errors
    assert (error.field, error.message) == (
        "parameters.known_at",
        access.HISTORY_UNAVAILABLE.format(
            email="marcus@avenmoor.test",
            cutoff=cut.isoformat(),
            changed_at=(AT - 5 * MINUTE).isoformat(),
        ),
    )
    assert run.asked == ["clock", "tenant_membership"]


def test_entity_scope_and_last_change() -> None:
    us, de = _id(71), _id(72)
    scoped = _assignment("viewer", entity_ids=(de,))
    assert access.covers(scoped, frozenset({de})) and not access.covers(scoped, frozenset({us}))
    assert access.covers(scoped, frozenset())  # a run without entities keeps every assignment
    assert access.covers(_assignment("viewer"), frozenset({us}))  # all entities
    member = {"updated_at": AT, "user_updated_at": AT + MINUTE, "identity_withheld": False}
    assert access.changed_at(member) == AT + MINUTE
    # a withheld identity shows nothing of the person, so the person's changes do not count
    assert access.changed_at({**member, "identity_withheld": True}) == AT


def test_grantor_names_the_setup_rule_another_rule_or_the_person() -> None:
    bootstrap = {
        "decision": "AUTO_APPROVE",
        "rule_key": "AUTO-BOOTSTRAP",
        "approver_id": None,
        "approver_kind": "SYSTEM",
    }
    assert access.grantor(bootstrap, NAMES) == access.SETUP_GRANT == "Setup grant (AUTO-BOOTSTRAP)"
    assert access.grantor({**bootstrap, "rule_key": "AUTO-VIEWER"}, NAMES) == "AUTO-VIEWER"
    person = {
        "decision": "APPROVE",
        "rule_key": None,
        "approver_id": GRACE,
        "approver_kind": "USER",
    }
    assert access.grantor(person, NAMES) == "Grace Okafor"
    assert access.grantor(None, NAMES) is None


def test_access_rows_list_every_membership_in_email_and_role_order() -> None:
    lena = access.Member(
        email="lena@demo.erev",
        display_name="Lena Fischer",
        status="ACTIVE",
        mfa_enrolled=True,
        last_login_at=AT,
        grants=(
            access.Grant(
                role_code="revenue_accountant",
                role_name="Revenue Accountant",
                is_all_entities=False,
                entity_codes=("AVM-DE", "AVM-UK"),
                granted_at=AT - MINUTE,
                granted_by="Grace Okafor",
                sod_exception_id=_id(9),
                revoked_at=None,
            ),
            access.Grant(
                role_code="revenue_reviewer",
                role_name="Revenue Reviewer",
                is_all_entities=True,
                entity_codes=(),
                granted_at=AT - 2 * MINUTE,
                granted_by=access.SETUP_GRANT,
                sod_exception_id=None,
                revoked_at=AT + MINUTE,
            ),
        ),
    )
    invited = access.Member(
        email="ines@demo.erev",
        display_name="ines@demo.erev",  # D-80 rule 5: the identity is withheld
        status="INVITED",
        mfa_enrolled=None,
        last_login_at=None,
        grants=(),
    )
    rows, totals = access.dataset_rows([lena, invited])
    assert [row["row_key"] for row in rows] == [
        "access:ines@demo.erev:",
        "access:lena@demo.erev:revenue_accountant",
        "access:lena@demo.erev:revenue_reviewer",
    ]
    pending, accountant, reviewer = rows
    assert (pending["display_name"], pending["membership_status"]) == ("ines@demo.erev", "INVITED")
    # an INVITED row: the two cells are not shown — null in the API, "Not shown" in XLSX and PDF
    # (SCREENS_B RPT-24 rev 1.105; 04 T-PLT-02 rev 1.316), where they were empty
    assert (pending["mfa_enrolled"], pending["last_login_at"]) == (NOT_SHOWN, NOT_SHOWN)
    assert "role_name" not in pending and "granted_at" not in pending  # empty cells
    assert (accountant["entity_scope"], accountant["sod_exception_id"]) == (
        ("AVM-DE", "AVM-UK"),
        str(_id(9)),
    )
    assert (reviewer["entity_scope"], reviewer["granted_by"], reviewer["revoked_at"]) == (
        (),
        "Setup grant (AUTO-BOOTSTRAP)",
        AT + MINUTE,
    )
    assert totals == {"membership_count": 2, "assignment_count": 2}
    columns = {column.key: column for column in access.COLUMNS}
    assert columns["entity_scope"].empty_text == "All entities"
    assert columns["last_login_at"].empty_text == "Never"


# --- RPT-25 ---------------------------------------------------------------------------------------


def _exception(
    index: int,
    *,
    approved_at: datetime | None = AT - MINUTE,
    revoked_at: datetime | None = None,
    valid_from: datetime = AT - MINUTE,
    valid_to: datetime = AT + timedelta(days=90),
) -> dict[str, Any]:
    return {
        "id": _id(index),
        "approved_at": approved_at,
        "revoked_at": revoked_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "compensating_control": f"Control {index}",
    }


def test_covering_is_the_exception_status_at_as_of() -> None:
    assert conflicts.covering([], AT) is None
    assert conflicts.covering([_exception(1)], AT) == _exception(1)
    # requested but not approved by then; approved later; revoked by then; outside its validity
    assert conflicts.covering([_exception(1, approved_at=None)], AT) is None
    assert conflicts.covering([_exception(1, approved_at=AT + MINUTE)], AT) is None
    assert conflicts.covering([_exception(1, revoked_at=AT)], AT) is None
    assert conflicts.covering([_exception(1, valid_from=AT + MINUTE)], AT) is None
    assert conflicts.covering([_exception(1, valid_to=AT)], AT) is None
    # revoked after the instant: it covered at the instant
    assert conflicts.covering([_exception(1, revoked_at=AT + MINUTE)], AT) is not None
    # several cover: the one ending last, then the lowest id
    short = _exception(1, valid_to=AT + timedelta(days=30))
    long = _exception(3)
    twin = _exception(2)
    assert conflicts.covering([short, long, twin], AT) == twin


def test_sod_rows_show_held_permissions_roles_and_cover() -> None:
    function_a = frozenset({"contract.create", "contract.update"})
    function_b = frozenset({"contract.approve", "modification.approve"})
    held = (
        conflicts.Held("Revenue Reviewer", frozenset({"contract.approve", "report.run"})),
        conflicts.Held("Revenue Accountant", frozenset({"contract.create", "report.run"})),
        conflicts.Held("Viewer", frozenset({"report.run"})),
    )
    assert conflicts.in_conflict(held, function_a, function_b) is True
    assert conflicts.in_conflict(held[:1], function_a, function_b) is False
    start = datetime(2026, 9, 12, 23, 30, tzinfo=UTC)
    covered = conflicts.Conflict(
        email="lena@demo.erev",
        display_name="Lena Fischer",
        rule_code="SoD-3",
        rule_name="Create and approve the same contract",
        function_a=function_a,
        function_b=function_b,
        held=held,
        cover=conflicts.Cover(
            id=_id(5),
            compensating_control="Controller reviews every approval monthly.",
            valid_from=start,
            valid_to=start + timedelta(days=90),
        ),
    )
    bare = conflicts.Conflict(
        email="ana@demo.erev",
        display_name="Ana Souza",
        rule_code="SoD-1",
        rule_name="User administration with approval",
        function_a=frozenset({"user.manage"}),
        function_b=frozenset({"contract.approve"}),
        held=(conflicts.Held("Everything", frozenset({"user.manage", "contract.approve"})),),
        cover=None,
    )
    rows, totals = conflicts.dataset_rows([covered, bare])
    assert [row["row_key"] for row in rows] == [
        "sod:ana@demo.erev:SoD-1",
        "sod:lena@demo.erev:SoD-3",
    ]
    open_row, row = rows
    assert (row["function_a_permissions"], row["function_b_permissions"]) == (
        ("contract.create",),
        ("contract.approve",),
    )
    assert row["roles"] == "Revenue Accountant, Revenue Reviewer"  # the Viewer grants neither
    assert row["delegations"] is None and open_row["delegations"] is None  # roles alone
    assert (row["sod_exception_id"], row["exception_status"]) == (str(_id(5)), "APPROVED")
    assert (row["valid_from"], row["valid_to"]) == (date(2026, 9, 12), date(2026, 12, 11))
    for name in ("sod_exception_id", "compensating_control", "valid_from", "exception_status"):
        assert name not in open_row  # empty cells; the id reads "None" in XLSX and PDF
    assert totals == {"conflict_count": 2, "uncovered_conflict_count": 1}
    columns = {column.key: column for column in conflicts.COLUMNS}
    assert columns["sod_exception_id"].empty_text == "None"


def test_sod_rows_name_the_delegations_a_conflict_is_held_through() -> None:
    """SCREENS_B RPT-25 rev 1.73 (04 T-PLT-21; supervisor ruling R-111 (4)): a permission held
    through a delegation is held, and the row names the delegation beside the roles — one entry
    per delegation that gives a permission of either function, "<delegator> until <DD MMM
    YYYY>" with the UTC day of its end, in the order of the delegator's name and the end. As
    built the report read roles only: a member who prepared by role and approved by delegation
    was no row."""
    function_a = frozenset({"contract.create", "modification.create"})
    function_b = frozenset({"contract.approve", "event.approve"})
    accountant = conflicts.Held("Revenue Accountant", frozenset({"contract.create", "report.run"}))
    # 13 Oct 01:30 at UTC+2 is 12 Oct 23:30 UTC: the cell shows the UTC day.
    end = datetime(2026, 10, 13, 1, 30, tzinfo=timezone(timedelta(hours=2)))
    by_priya = conflicts.Delegated("Priya Raman", end, frozenset({"contract.approve"}))
    unrelated = conflicts.Delegated("Marcus Webb", end, frozenset({"period.reopen_approve"}))
    assert conflicts.delegation_text(by_priya) == "Priya Raman until 12 Oct 2026"
    assert conflicts.in_conflict((accountant,), function_a, function_b) is False
    assert conflicts.in_conflict((accountant,), function_a, function_b, (unrelated,)) is False
    assert conflicts.in_conflict((accountant,), function_a, function_b, (by_priya,)) is True

    mixed = conflicts.Conflict(
        email="maya@demo.erev",
        display_name="Maya Chen",
        rule_code="SoD-3",
        rule_name="Create and approve the same contract",
        function_a=function_a,
        function_b=function_b,
        held=(accountant,),
        cover=None,
        delegated=(unrelated, by_priya),
    )
    # No role at all: both functions through delegations.
    first = conflicts.Delegated(
        "Ana Souza", datetime(2026, 11, 1, 12, 0, tzinfo=UTC), frozenset({"access.approve"})
    )
    second = conflicts.Delegated(
        "Ana Souza", datetime(2026, 11, 20, 12, 0, tzinfo=UTC), frozenset({"access.approve"})
    )
    alone = conflicts.Conflict(
        email="vic@demo.erev",
        display_name="Vic Tan",
        rule_code="SoD-1",
        rule_name="User administration with approval",
        function_a=frozenset({"access.approve", "user.manage"}),
        function_b=frozenset({"contract.approve"}),
        held=(),
        cover=None,
        delegated=(by_priya, second, first),
    )
    rows, totals = conflicts.dataset_rows([mixed, alone])
    by_key = {row["row_key"]: row for row in rows}
    row = by_key["sod:maya@demo.erev:SoD-3"]
    assert (row["function_a_permissions"], row["function_b_permissions"]) == (
        ("contract.create",),
        ("contract.approve",),
    )
    # The delegation of a permission of neither function is not named.
    assert (row["roles"], row["delegations"]) == (
        "Revenue Accountant",
        "Priya Raman until 12 Oct 2026",
    )
    bare = by_key["sod:vic@demo.erev:SoD-1"]
    assert (bare["function_a_permissions"], bare["function_b_permissions"]) == (
        ("access.approve",),
        ("contract.approve",),
    )
    assert bare["roles"] is None
    assert bare["delegations"] == (
        "Ana Souza until 01 Nov 2026, Ana Souza until 20 Nov 2026, Priya Raman until 12 Oct 2026"
    )
    assert totals == {"conflict_count": 2, "uncovered_conflict_count": 2}
    assert [(column.key, column.header) for column in conflicts.COLUMNS][5:7] == [
        ("roles", "Through roles"),
        ("delegations", "Through delegations"),
    ]
    logic = DEFINITIONS_BY_CODE[conflicts.CODE].ipe_logic
    assert "approval_delegation" in logic["source_tables"]


# --- RPT-26 ---------------------------------------------------------------------------------------


def test_approval_rows_one_per_decision_and_one_for_a_request_without_decision() -> None:
    rule, version = _id(31), _id(32)
    two_steps = _request(
        "APR-000002",
        _decision(1, PRIYA, step_name="Reviewer"),
        _decision(2, MARCUS, step_no=2, step_name="Controller", on_behalf_of=GRACE, comment=None),
        _decision(3, GRACE, step_no=2, step_name="Controller"),
        subject_type="PERIOD_REOPEN",
        amount="1234.5",
        currency="USD",
        flags=("HIGH_VALUE", "CROSS_PERIOD"),
        entity=_id(71),
    )
    automatic = _request(
        "APR-000001",
        _decision(4, None, kind="AUTO_APPROVE", rule=rule, rule_version=version, comment=None),
        subject_type="ROLE_ASSIGNMENT",
        preparer=None,
        amount="50000",
        currency="JPY",
    )
    waiting = _request("APR-000003", status="PENDING", subject_type="ROLE_ASSIGNMENT")
    sources = [
        approvals.Source(two_steps, "AVM-US", None),
        approvals.Source(waiting, None, (1, "Access approval")),
        approvals.Source(automatic, None, None),
    ]
    rows, totals = approvals.dataset_rows(
        sources, NAMES, rule_keys={rule: "AUTO-BOOTSTRAP"}, rule_versions={version: 1}
    )
    assert [row["row_key"] for row in rows] == [
        "decision:APR-000001:1:1",
        "decision:APR-000002:1:1",
        "decision:APR-000002:2:1",
        "decision:APR-000002:2:2",
        "decision:APR-000003:1:0",
    ]
    auto, first, delegated, second, pending = rows
    assert (auto["preparer"], auto["approver"], auto["decision"]) == (
        "System",
        "System",
        "AUTO_APPROVE",
    )
    assert (auto["auto_rule_key"], auto["auto_rule_version"]) == ("AUTO-BOOTSTRAP", 1)
    assert auto["amount_functional"] == {"amount": "50000", "currency": "JPY"}  # no minor unit
    assert (first["entity_code"], first["amount_currency"], first["flags"]) == (
        "AVM-US",
        "USD",
        ("HIGH_VALUE", "CROSS_PERIOD"),
    )
    assert first["amount_functional"] == {"amount": "1234.50", "currency": "USD"}
    assert (first["step_name"], first["step_no"], first["approver"]) == (
        "Reviewer",
        1,
        "Priya Raman",
    )
    assert (first["subject_id"], first["subject_content_sha256"]) == (
        str(two_steps.subject_id),
        f"{1:064x}",
    )
    assert (delegated["approver"], delegated["on_behalf_of"], delegated["comment"]) == (
        "Marcus Webb",
        "Grace Okafor",
        None,
    )
    assert (second["approver"], second["on_behalf_of"], second["status"]) == (
        "Grace Okafor",
        None,
        "APPROVED",
    )
    assert (pending["step_name"], pending["step_no"], pending["status"]) == (
        "Access approval",
        1,
        "PENDING",
    )
    assert pending["subject_content_sha256"] == "f" * 64  # the request's, while nobody decided
    assert "approver" not in pending and "decision" not in pending and "decided_at" not in pending
    assert pending["amount_functional"] is None
    assert totals == {"request_count": 3, "decision_count": 4, "auto_approval_count": 1}


def test_approvals_register_serves_the_functional_view_only() -> None:
    approvals.check_view(_params({}))
    approvals.check_view(_params({"currency_view": "functional"}))
    for view in ("transaction", "reporting"):
        with pytest.raises(Problem) as refused:
            approvals.check_view(_params({"currency_view": view}))
        (error,) = refused.value.errors
        assert (error.field, error.message) == (
            "parameters.currency_view",
            approvals.VIEW_UNSUPPORTED,
        )


# --- RPT-43 and RPT-44 ----------------------------------------------------------------------------


def _event(seq: int, **values: Any) -> dict[str, Any]:
    event: dict[str, Any] = dict.fromkeys(audit_export.FIELDS)
    event |= {
        "chain_seq": seq,
        "occurred_at": AT + seq * MINUTE,
        "id": _id(seq),
        "actor_kind": "USER",
        "actor_roles": ["controller", "ssp_approver"],
        "request_id": f"req-{seq}",
        "action": "contract.active",
        "object_type": "contract",
        "outcome": "SUCCESS",
        "detail": {},
        "hmac": f"{seq:064x}",
        "hmac_key_id": "audit-hmac:1",
    }
    return event | values


def test_audit_cells_are_canonical_and_redacted() -> None:
    assert audit_export.cell("occurred_at", AT) == "2026-09-12T12:00:00.000000Z"
    late = datetime(2026, 9, 12, 14, 0, 0, 123456, tzinfo=UTC)
    assert audit_export.cell("occurred_at", late) == "2026-09-12T14:00:00.123456Z"
    diff = [{"path": "status", "before": "DRAFT", "after": "ACTIVE"}]
    assert audit_export.cell("diff", diff) == (
        '[{"after":"ACTIVE","before":"DRAFT","path":"status"}]'
    )
    # a credential key of erev_api.audit.REDACT never leaves in clear, at any depth
    assert "token" in REDACT and "password_hash" in REDACT
    secret = {"user": {"token": "abc", "name": "Zoë"}, "password_hash": "x", "b": 1, "a": None}
    assert audit_export.cell("after", secret) == (
        '{"a":null,"b":1,"password_hash":"[REDACTED]","user":{"name":"Zoë","token":"[REDACTED]"}}'
    )
    assert audit_export.cell("detail", {}) == "{}"
    assert audit_export.cell("before", None) is None and audit_export.cell("comment", None) is None
    assert audit_export.cell("actor_roles", ["b", "a"]) == ("b", "a")
    assert audit_export.cell("mfa_verified", False) is False
    assert audit_export.cell("object_id", _id(7)) == str(_id(7))
    assert audit_export.cell("chain_seq", 12) == 12


def test_audit_rows_in_chain_order_with_the_manifest_totals() -> None:
    rows, totals = audit_export.dataset_rows(
        [_event(9, diff=[{"path": "status", "before": "DRAFT", "after": "ACTIVE"}]), _event(4)]
    )
    assert [row["row_key"] for row in rows] == ["event:4", "event:9"]
    assert [key for key in rows[0] if key != "row_key"] == list(audit_export.FIELDS)
    assert json.loads(rows[1]["diff"]) == [{"path": "status", "before": "DRAFT", "after": "ACTIVE"}]
    assert (rows[0]["diff"], rows[0]["detail"], rows[0]["actor_id"]) == (None, "{}", None)
    assert totals == {
        "row_count": 2,
        "first_chain_seq": 4,
        "last_chain_seq": 9,
        "last_hmac": f"{9:064x}",
    }
    assert audit_export.dataset_rows([]) == (
        [],
        {"row_count": 0, "first_chain_seq": None, "last_chain_seq": None, "last_hmac": None},
    )


def test_audit_filters_refuse_a_start_after_its_end() -> None:
    both = {
        "from": "2026-09-01T00:00:00Z",
        "to": "2026-09-30T00:00:00Z",
        "action": "contract.active",
    }
    assert len(audit_export.filters(_params(both), cutoff=AT)) == 4  # cutoff, from, to, action
    assert len(audit_export.filters(_params({}), cutoff=AT)) == 1  # the cutoff alone
    with pytest.raises(Problem) as refused:
        audit_export.filters(
            _params({"from": "2026-09-30T00:00:00Z", "to": "2026-09-01T00:00:00Z"}), cutoff=AT
        )
    (error,) = refused.value.errors
    assert (error.field, error.message) == ("parameters.from", "Start must be on or before end.")


def _verification(index: int, finished_at: datetime, **values: Any) -> dict[str, Any]:
    row = {
        "id": _id(index),
        "trigger": "SCHEDULED",
        "from_chain_seq": 1,
        "to_chain_seq": 40,
        "events_checked": 40,
        "result": "PASS",
        "first_failure_seq": None,
        "digest_last_hmac": f"{index:064x}",
        "digest_file_id": _id(800 + index),
        "started_at": finished_at - timedelta(seconds=index),
        "finished_at": finished_at,
    }
    return row | values


def test_verification_rows_in_finishing_order_with_distinct_keys() -> None:
    failed = _verification(
        3,
        AT + MINUTE,
        trigger="ON_DEMAND",
        result="FAIL",
        first_failure_seq=3,
        to_chain_seq=3,
        events_checked=3,
        digest_file_id=None,
    )
    twin_late = _verification(2, AT)
    twin_early = _verification(1, AT, started_at=AT - MINUTE)
    rows, totals = verifications.dataset_rows([failed, twin_late, twin_early])
    assert [row["row_key"] for row in rows] == [
        "verification:2026-09-12T12:00:00.000000Z",
        "verification:2026-09-12T12:00:00.000000Z:2",
        "verification:2026-09-12T12:01:00.000000Z",
    ]
    assert rows[0]["digest_file_id"] == str(_id(801))  # the earlier start keeps the plain key
    last = rows[2]
    assert (last["trigger"], last["result"], last["first_failure_seq"]) == ("ON_DEMAND", "FAIL", 3)
    assert (last["events_checked"], last["digest_file_id"]) == (3, None)
    assert last["digest_last_hmac"] == f"{3:064x}" and last["finished_at"] == AT + MINUTE
    assert totals == {"verification_count": 3, "failure_count": 1}
    assert verifications.dataset_rows([]) == ([], {"verification_count": 0, "failure_count": 0})


# --- rulings R-13, R-63 (a): the permissions of a report ------------------------------------------


def _holder(**scopes: Any) -> Any:
    """A principal that holds each named permission at the given scope (``*`` or entity ids)."""
    from types import SimpleNamespace

    named = {code.replace("_", "."): scope for code, scope in scopes.items()}
    return SimpleNamespace(permissions=frozenset(named), permission_scopes=named)


def _role(code: str) -> Any:
    """A principal that holds one default role (PRD §5.6; ``DEFAULT_ROLES``) for every entity."""
    from types import SimpleNamespace

    from erev_api.auth.permissions import DEFAULT_ROLES

    held = DEFAULT_ROLES[code]
    return SimpleNamespace(permissions=held, permission_scopes=dict.fromkeys(held, "*"))


THREE = (access.CODE, conflicts.CODE, inventory.CODE)  # RPT-24, RPT-25, RPT-27
TWO = (changes.CODE, approvals.CODE)  # RPT-23, RPT-26
AUDIT = framework.RequiredPermission("audit.read")


def test_the_reports_declare_their_permissions() -> None:
    """04 API-R-41 (rulings R-13, R-28, R-63 (a)): the three access registers are run under
    ``audit.read`` in place of ``report.run``; four reports declare ``audit.read`` beside
    ``report.run`` — the audit log export for every entity, its rows naming no entity; every named
    report is registered and the rule is stated in API-R-41."""
    assert dict(framework.RUN_PERMISSIONS) == dict.fromkeys(THREE, "audit.read")
    assert dict(framework.REQUIRED_PERMISSIONS) == {
        audit_export.CODE: (framework.RequiredPermission("audit.read", all_entities=True),),
        verifications.CODE: (AUDIT,),
        changes.CODE: (AUDIT,),
        approvals.CODE: (AUDIT,),
    }
    named = (*framework.RUN_PERMISSIONS, *framework.REQUIRED_PERMISSIONS)
    assert len(set(named)) == len(named) == 7  # a report is in one table, not both
    assert set(named) <= set(framework.BUILDERS)
    assert framework.ADMITTING_PERMISSIONS == ("report.run", "audit.read")
    assert {framework.run_permission(code) for code in THREE} == {"audit.read"}
    assert {framework.run_permission(code) for code in (*TWO, "revenue_waterfall")} == {
        "report.run"
    }
    row = next(
        line
        for line in report_specs.read("docs/04-DATA_MODEL.md").splitlines()
        if line.startswith("| API-R-41 | Reports |")
    )
    assert "rev 1.99; ruling R-13" in row and "403 `forbidden`" in row and "`DENIED`" in row
    assert "ruling R-63 (a)" in row
    for code in named:
        assert f"`{code}`" in row, code


def test_a_declared_permission_is_held_at_its_scope() -> None:
    """A viewer (``report.run`` without ``audit.read``) misses the four declaring reports; a
    holder for every entity misses none; a holder for named entities misses the export only; an
    unscoped grant is not a grant. The run permission is checked the same way."""
    entity = _id(7)
    viewer = _holder(report_run="*", report_export="*")
    auditor = _holder(report_run="*", audit_read="*")
    scoped = _holder(report_run=frozenset({entity}), audit_read=frozenset({entity}))
    declared = (approvals.CODE, audit_export.CODE, verifications.CODE, changes.CODE)  # code order
    assert framework.withheld_reports(viewer) == declared
    assert declared == tuple(sorted(framework.REQUIRED_PERMISSIONS))
    assert framework.withheld_reports(auditor) == ()
    assert framework.withheld_reports(scoped) == (audit_export.CODE,)
    missing = framework.missing_permission(scoped, audit_export.CODE)
    assert missing is not None and (missing.code, missing.all_entities) == ("audit.read", True)
    assert framework.missing_permission(scoped, verifications.CODE) is None
    assert framework.missing_permission(scoped, access.CODE) is None  # audit.read, its entity
    assert framework.missing_permission(viewer, "revenue_waterfall") is None  # nothing declared
    assert framework.missing_permission(viewer, changes.CODE) == AUDIT  # declared (R-63 (a))
    assert framework.missing_permission(viewer, access.CODE) == AUDIT  # its run permission
    unscoped = _holder(report_run="*")
    unscoped.permissions = frozenset({"report.run", "audit.read"})  # a code without a scope
    assert framework.withheld_reports(unscoped) == declared
    assert framework.missing_permission(unscoped, access.CODE) == AUDIT


def test_the_default_roles_and_the_five_registers() -> None:
    """Supervisor ruling R-63 (a) over PRD §5.6 (J-17.6, J-22.7, J-22.8): the user access
    listing, the SoD conflict report and the API client inventory need ``audit.read`` and not
    ``report.run`` — a Tenant Admin and an Auditor run them; the configuration change register and
    the approvals register need both; a viewer and the two SSP roles run none of the five."""
    from erev_api.auth.permissions import DEFAULT_ROLES

    def runs(role: str, codes: tuple[str, ...]) -> bool:
        return all(framework.missing_permission(_role(role), code) is None for code in codes)

    roles = sorted(DEFAULT_ROLES)
    accounting = {"auditor", "controller", "integration_admin", "revenue_accountant"} | {
        "revenue_reviewer"
    }
    assert {role for role in roles if runs(role, THREE)} == accounting | {"tenant_admin"}
    assert {role for role in roles if runs(role, TWO)} == accounting
    for role in ("viewer", "ssp_analyst", "ssp_approver"):
        for code in (*THREE, *TWO):
            assert framework.missing_permission(_role(role), code) == AUDIT, (role, code)
    # a Tenant Admin holds audit.read without report.run: the three registers and nothing else
    admin = _role("tenant_admin")
    assert framework.admitted(admin)
    assert "report.run" not in admin.permissions
    for code in (*TWO, audit_export.CODE, verifications.CODE, "revenue_waterfall"):
        missing = framework.missing_permission(admin, code)
        assert missing is not None and missing.code == "report.run", code
    # the routes stay closed to a principal that may run no report
    assert [role for role in roles if not framework.admitted(_role(role))] == ["service_account"]


def test_the_catalogue_a_caller_reads() -> None:
    """``GET /report-definitions`` (04 API-R-41): every definition for a holder of ``report.run``
    — catalogue text, never rows (rev 1.99) — and, for a caller without it, the definitions of the
    reports it holds the run permission for (R-63 (a))."""
    codes = [definition.code for definition in catalogue.DEFINITIONS]

    def listed(principal: Any) -> list[str]:
        return [code for code in codes if framework.definition_listed(principal, code)]

    assert listed(_role("viewer")) == listed(_role("auditor")) == codes
    assert sorted(listed(_role("tenant_admin"))) == sorted(THREE)
    assert listed(_role("service_account")) == []


def test_a_run_is_visible_under_the_run_permission_of_its_report() -> None:
    """Ruling R-63 (a): the visibility predicate of ``GET /report-runs`` and of every addressed
    read scopes each run by the permission ITS REPORT is run under; an output is also within the
    caller's ``report.export`` scope."""
    from erev_api.db.tables import report_run
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    def compiled(permission: str = framework.RUN_PERMISSION, **scopes: Any) -> tuple[str, Any]:
        statement = framework.visible(select(report_run.c.id), _holder(**scopes), permission)
        found = statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
        )
        return " ".join(str(found).split()), found.params

    in_three = "erev.report_run.report_code IN ("
    not_in_three = "erev.report_run.report_code NOT IN ("
    within = "erev.report_run.entity_ids <@"
    # a Tenant Admin: the runs of the three registers, of every entity
    sql, bound = compiled(audit_read="*")
    assert f"WHERE {in_three}" in sql and not_in_three not in sql and within not in sql
    assert set(THREE) <= {value for value in bound.values() if isinstance(value, str)}
    # a viewer: every other report's runs, never the three
    sql, _ = compiled(report_run="*")
    assert f"WHERE ({not_in_three}" in sql and in_three not in sql.replace(not_in_three, "")
    # report.run for one entity, audit.read for every entity: each family under its own scope
    entity = _id(7)
    sql, bound = compiled(report_run=frozenset({entity}), audit_read="*")
    assert f"({not_in_three}" in sql and f") AND ({within}" in sql and f" OR {in_three}" in sql
    assert [entity] in list(bound.values())
    # neither permission: nothing
    sql, _ = compiled(contract_read="*")
    assert "WHERE false" in sql
    # an output: within the report.export scope as well; without report.export, nothing
    sql, _ = compiled(framework.EXPORT_PERMISSION, report_run="*")
    assert "WHERE false" in sql
    sql, bound = compiled(
        framework.EXPORT_PERMISSION, report_run="*", report_export=frozenset({entity})
    )
    assert f"({not_in_three}" in sql and f") AND ({within}" in sql
    assert [entity] in list(bound.values())

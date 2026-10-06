"""Who is answered the summary of a dry run in the result of its job (04 API-S-Job and §16.10 "Who
reads a stored preview", rev 1.314; item PREVIEW-JOB-RESULT-SCOPE-1): ``jobs.job_outs`` answers
``result.summary`` to a reader the rule answers (``file_access.preview_summary_readable``) and
withholds it from every other, and the rule asks ONE read permission of the dry run's subject for
EVERY entity the subject is bound to. CPU (DG-TST-18): job rows and principals built here, with
stand-ins for the rule and for the kernel's read of a subject's entities. The door itself —
``GET /jobs/{id}`` and ``GET /jobs`` over the four previews of a combination group of two
entities — is witnessed on the database in ``tests/domain/contracts/test_reader_independence.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import ALL_ENTITIES, SubjectEntities, SubjectNotVisible
from erev_api.auth.principal import Principal
from erev_api.domain.contracts import compute_job
from erev_api.domain.platform import file_access, jobs
from erev_api.enums import ApprovalSubjectType, JobKind, PrincipalKind
from erev_api.problems import Problem

TENANT = UUID("0a1b2c3d-0000-4000-8000-0000000000aa")
UK = UUID("0a1b2c3d-0000-4000-8000-0000000000d2")
US = UUID("0a1b2c3d-0000-4000-8000-0000000000d3")
CONTRACT = UUID("0a1b2c3d-0000-4000-8000-0000000000c1")
MODIFICATION = UUID("0a1b2c3d-0000-4000-8000-0000000000c2")
VERSION = UUID("0a1b2c3d-0000-4000-8000-0000000000c3")
ADJUSTMENT = UUID("0a1b2c3d-0000-4000-8000-0000000000c4")
NO_SESSION: Any = None  # the stand-ins below read nothing
Held = Literal["*"] | frozenset[UUID]
SUMMARY: dict[str, Any] = {
    "transaction_price_before": {"amount": "73000.00", "currency": "GBP"},
    "transaction_price_after": {"amount": "78000.00", "currency": "GBP"},
}
# mode → (the params its command defers, the subject the rule is asked about)
DRY_RUNS: dict[str, tuple[dict[str, Any], tuple[str, UUID]]] = {
    "PREVIEW": (
        {"contract_id": str(CONTRACT), "expected_stream_version": 4, "events": []},
        ("contract", CONTRACT),
    ),
    "ESTIMATE_PREVIEW": (
        {"estimate_version_id": str(VERSION)},
        ("ESTIMATE_VERSION", VERSION),
    ),
    # a modification's params name its contract too: the subject is the modification
    "MODIFICATION_PREVIEW": (
        {"modification_id": str(MODIFICATION), "row_version": 2, "contract_id": str(CONTRACT)},
        ("MODIFICATION", MODIFICATION),
    ),
    "ADJUSTMENT_PREVIEW": (
        {"manual_adjustment_id": str(ADJUSTMENT)},
        ("MANUAL_ADJUSTMENT", ADJUSTMENT),
    ),
}
STORED: dict[str, Any] = {
    "href": "/api/v1/modifications/0a1b2c3d-0000-4000-8000-0000000000c2",
    "counts": {"events": 1},
    "summary": SUMMARY,
    "impact_preview_sha256": "ab" * 32,
    "step1_gate": {"appended": True, "reason": None},
}


def _reader(scopes: dict[str, Held]) -> Principal:
    """A member who holds each permission of ``scopes`` for its entities."""
    return Principal(
        kind=PrincipalKind.USER,
        id=UUID(int=7),
        tenant_id=TENANT,
        membership_id=UUID(int=8),
        display_name="Bea",
        roles=("revenue_accountant",),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


BEA = _reader({"contract.read": frozenset({UK})})


def _job(
    mode: str | None,
    params: dict[str, Any] | None,
    result: dict[str, Any] | None,
    *,
    kind: JobKind = JobKind.CONTRACT_COMPUTE,
    number: int = 1,
) -> dict[str, Any]:
    """A ``job`` row as ``jobs.JOB_COLUMNS`` reads it, started by the system."""
    stored = None if params is None else {**params, **({} if mode is None else {"mode": mode})}
    at = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    return {
        "id": UUID(int=number),
        "kind": kind,
        "state": "SUCCEEDED",
        "progress_done": 1,
        "progress_total": 1,
        "result": result,
        "problem": None,
        "created_by": None,
        "created_by_kind": "SYSTEM",
        "created_at": at,
        "started_at": at,
        "finished_at": at,
        "cancel_requested_at": None,
        "params": stored,
    }


def _result(row: dict[str, Any], reader: Principal | None) -> Any:
    """``result`` of API-S-Job as ``reader`` is answered it, as JSON."""
    (answer,) = jobs.job_outs(NO_SESSION, [row], reader=reader)
    return answer.model_dump(mode="json")["result"]


Asked = list[tuple[Principal, str, UUID]]
Rule = Callable[[bool | frozenset[UUID]], Asked]


@pytest.fixture
def rule(monkeypatch: pytest.MonkeyPatch) -> Rule:
    """``file_access.preview_summary_readable`` answers ``shown`` — for every subject, or for
    the subjects whose ids it holds; the list returned holds what it was asked."""

    def install(shown: bool | frozenset[UUID]) -> Asked:
        asked: Asked = []

        def readable(session: Any, reader: Principal, subject_type: str, subject_id: UUID) -> bool:
            asked.append((reader, subject_type, subject_id))
            return shown if isinstance(shown, bool) else subject_id in shown

        monkeypatch.setattr(jobs.file_access, "preview_summary_readable", readable)
        return asked

    return install


# --- the job's answer -----------------------------------------------------------------------------


def test_the_dry_runs_are_the_modes_the_compute_job_answers() -> None:
    """The table spells the modes itself (the modules that defer a preview import ``jobs``): it
    names exactly the four the compute job dispatches, and subjects the rule knows."""
    assert set(jobs.SUMMARY_SUBJECTS) == {
        compute_job.PREVIEW_MODE,
        compute_job.ESTIMATE_PREVIEW_MODE,
        compute_job.MODIFICATION_PREVIEW_MODE,
        compute_job.ADJUSTMENT_PREVIEW_MODE,
    }
    assert set(jobs.SUMMARY_SUBJECTS) == set(DRY_RUNS)
    assert file_access.PENDING_EVENTS == approvals.CONTRACT_SUBJECT
    stored = {kind.value for kind in file_access.STORED_PREVIEW_READERS}
    subjects = {subject_type for subject_type, _ in jobs.SUMMARY_SUBJECTS.values()}
    assert subjects == stored | {file_access.PENDING_EVENTS, "ESTIMATE_VERSION"}


@pytest.mark.parametrize("mode", sorted(DRY_RUNS))
def test_a_summary_is_answered_to_a_reader_the_rule_answers_and_to_no_other(
    mode: str, rule: Rule
) -> None:
    params, subject = DRY_RUNS[mode]
    row = _job(mode, params, dict(STORED))
    assert jobs.summary_subject(row) == subject
    asked = rule(True)
    assert _result(row, BEA) == STORED
    assert asked == [(BEA, *subject)]
    asked = rule(False)
    # the summary alone goes: the link, the counts, the hash and the gate are answered
    assert _result(row, BEA) == {**STORED, "summary": None, "summary_withheld": True}
    assert asked == [(BEA, *subject)]
    assert row["result"] == STORED  # the stored row is not changed


def test_nobody_named_as_the_reader_is_answered_no_summary(rule: Rule) -> None:
    """A command that answers a job names no reader (``job_out_of``): should such a job ever
    hold a summary, it is withheld — the rule fails closed."""
    asked = rule(True)
    params, _ = DRY_RUNS["MODIFICATION_PREVIEW"]
    row = _job("MODIFICATION_PREVIEW", params, dict(STORED))
    assert _result(row, None) == {**STORED, "summary": None, "summary_withheld": True}
    (answer,) = jobs.job_outs(NO_SESSION, [row])
    assert answer.model_dump(mode="json")["result"]["summary_withheld"] is True
    assert asked == []


@pytest.mark.parametrize(
    ("mode", "params", "kind"),
    [
        ("LEASE_PREVIEW", {"contract_id": str(CONTRACT)}, JobKind.CONTRACT_COMPUTE),  # unknown
        (None, {"contract_id": str(CONTRACT)}, JobKind.CONTRACT_COMPUTE),  # a computation
        (None, None, JobKind.CONTRACT_COMPUTE),
        ("MODIFICATION_PREVIEW", {"contract_id": str(CONTRACT)}, JobKind.CONTRACT_COMPUTE),
        ("ESTIMATE_PREVIEW", {"estimate_version_id": "not-an-id"}, JobKind.CONTRACT_COMPUTE),
        ("PREVIEW", {"contract_id": str(CONTRACT)}, JobKind.REPORT_RUN),  # another kind
    ],
    ids=["unknown-mode", "no-mode", "no-params", "no-subject", "no-uuid", "other-kind"],
)
def test_a_summary_that_names_no_dry_run_of_the_table_is_withheld(
    mode: str | None,
    params: dict[str, Any] | None,
    kind: JobKind,
    rule: Rule,
) -> None:
    """A summary is answered by the rule or not at all: a result that holds one and names no
    subject the rule can be asked about is answered without it, whoever reads."""
    asked = rule(True)
    row = _job(mode, params, dict(STORED), kind=kind)
    assert jobs.summary_subject(row) is None
    everything = _reader({"contract.read": "*", "audit.read": "*"})
    assert _result(row, everything) == {**STORED, "summary": None, "summary_withheld": True}
    assert asked == []


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"href": "/api/v1/contracts/c1", "counts": {"groups": 1, "succeeded": 1}},
        {"href": None, "counts": {}, "summary": None},
        {"counts": {"rows": 3}, "report_run_id": "r1"},
    ],
    ids=["none", "counts", "null-summary", "other-members"],
)
def test_a_result_without_a_summary_is_answered_as_stored(
    result: dict[str, Any] | None, rule: Rule
) -> None:
    asked = rule(False)
    params, _ = DRY_RUNS["PREVIEW"]
    answered = _result(_job("PREVIEW", params, result), BEA)
    if result is None:
        assert answered is None
    else:
        assert answered == {"href": None, "counts": {}, **result}
        assert "summary_withheld" not in answered
    assert asked == []


def test_one_page_asks_once_about_one_subject_and_answers_each_job_by_its_own(rule: Rule) -> None:
    """The list: a subject previewed twice is asked about once, and a job is answered by the
    answer for ITS subject — two modifications on one page, one shown and one not."""
    asked = rule(frozenset({MODIFICATION}))
    params, subject = DRY_RUNS["MODIFICATION_PREVIEW"]
    second = {**params, "modification_id": str(ADJUSTMENT)}  # another modification's id
    rows = [
        _job("MODIFICATION_PREVIEW", params, dict(STORED), number=1),
        _job("MODIFICATION_PREVIEW", second, dict(STORED), number=2),
        _job("MODIFICATION_PREVIEW", params, dict(STORED), number=3),
    ]
    answers = jobs.job_outs(NO_SESSION, rows, reader=BEA)
    results = [item.model_dump(mode="json")["result"] for item in answers]
    assert [result["summary"] for result in results] == [SUMMARY, None, SUMMARY]
    assert [result.get("summary_withheld") for result in results] == [None, True, None]
    assert asked == [(BEA, *subject), (BEA, "MODIFICATION", ADJUSTMENT)]


# --- the rule -------------------------------------------------------------------------------------

Read = list[tuple[str, Any, UUID]]


@pytest.fixture
def bound_to(monkeypatch: pytest.MonkeyPatch) -> Callable[[SubjectEntities | Exception], Read]:
    """The kernel's reads of the entities a subject is bound to answer ``entities`` — or raise
    it; the list returned holds what they were asked."""

    def install(entities: SubjectEntities | Exception) -> Read:
        asked: Read = []

        def answer() -> SubjectEntities:
            if isinstance(entities, Exception):
                raise entities
            return entities

        def preparer_scope(
            session: Any, subject_type: ApprovalSubjectType, subject_id: UUID
        ) -> SubjectEntities:
            asked.append(("preparer_scope", subject_type, subject_id))
            return answer()

        def contract_scope(session: Any, contract_id: UUID) -> SubjectEntities:
            asked.append(("contract_scope", None, contract_id))
            return answer()

        monkeypatch.setattr(file_access.approvals, "preparer_scope", preparer_scope)
        monkeypatch.setattr(file_access.approvals, "contract_scope", contract_scope)
        return asked

    return install


UNSTORED = [
    (
        "ESTIMATE_VERSION",
        VERSION,
        ("preparer_scope", ApprovalSubjectType.ESTIMATE_VERSION, VERSION),
    ),
    ("contract", CONTRACT, ("contract_scope", None, CONTRACT)),
]


def _shown(reader: Principal, subject_type: str, subject_id: UUID) -> bool:
    return file_access.preview_summary_readable(NO_SESSION, reader, subject_type, subject_id)


@pytest.mark.parametrize(
    ("subject_type", "subject_id", "read"), UNSTORED, ids=["estimate", "events"]
)
def test_a_dry_run_that_retains_nothing_is_read_with_contract_read_for_every_entity(
    subject_type: str,
    subject_id: UUID,
    read: tuple[str, Any, UUID],
    bound_to: Callable[[SubjectEntities | Exception], Read],
) -> None:
    asked = bound_to(SubjectEntities(frozenset({UK, US})))
    assert _shown(BEA, subject_type, subject_id) is False
    assert asked == [read]  # the set the preview route asks its caller about
    assert _shown(_reader({"contract.read": frozenset({UK, US})}), subject_type, subject_id) is True
    # the read permission, not the one that prepares; and the scopes of two are never added up
    assert (
        _shown(_reader({"estimate.create": "*", "event.record": "*"}), subject_type, subject_id)
        is False
    )
    split = _reader({"contract.read": frozenset({UK}), "event.record": frozenset({US})})
    assert _shown(split, subject_type, subject_id) is False
    # a contract alone in its group: the entity that contracts
    bound_to(SubjectEntities(frozenset({UK})))
    assert _shown(BEA, subject_type, subject_id) is True
    # a member the kernel cannot name makes the subject span every entity
    bound_to(ALL_ENTITIES)
    assert (
        _shown(_reader({"contract.read": frozenset({UK, US})}), subject_type, subject_id) is False
    )
    # a reader of all entities is answered without a read of the subject
    asked = bound_to(ALL_ENTITIES)
    assert _shown(_reader({"contract.read": "*"}), subject_type, subject_id) is True
    assert asked == []


@pytest.mark.parametrize(
    "subject_type", [ApprovalSubjectType.MODIFICATION, ApprovalSubjectType.MANUAL_ADJUSTMENT]
)
@pytest.mark.parametrize("shown", [True, False])
def test_a_subject_that_retains_its_preview_is_asked_through_the_stored_previews_own_function(
    subject_type: ApprovalSubjectType, shown: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fourth door of a stored preview: the job's answer asks the function its three other
    doors ask, with the subject's own readers."""
    asked: list[tuple[Principal, ApprovalSubjectType, UUID]] = []

    def stored(
        session: Any, reader: Principal, kind: ApprovalSubjectType, subject_id: UUID
    ) -> bool:
        asked.append((reader, kind, subject_id))
        return shown

    monkeypatch.setattr(file_access, "stored_preview_readable", stored)
    assert _shown(BEA, subject_type.value, MODIFICATION) is shown
    assert asked == [(BEA, subject_type, MODIFICATION)]


@pytest.mark.parametrize(
    "subject_type", ["MODIFICATION", "MANUAL_ADJUSTMENT", "ESTIMATE_VERSION", "contract"]
)
def test_a_subject_that_is_gone_answers_nobody_but_a_reader_of_all_entities(
    subject_type: str, bound_to: Callable[[SubjectEntities | Exception], Read]
) -> None:
    """A subject row that is gone names no entity: the summary is withheld and the job is still
    read — no error leaves the rule. Another refusal of the kernel is not swallowed."""
    for gone in (SubjectNotVisible("the subject is not visible"), Problem("not-found")):
        bound_to(gone)
        assert (
            _shown(_reader({"contract.read": frozenset({UK, US})}), subject_type, CONTRACT) is False
        )
        assert _shown(_reader({"contract.read": "*"}), subject_type, CONTRACT) is True
    bound_to(Problem("forbidden"))
    with pytest.raises(Problem, match="forbidden"):
        _shown(BEA, subject_type, CONTRACT)

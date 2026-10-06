"""What the platform runner does before an estimate version is submitted (dev-guide DG-AK-41 rev
1.278; 04 §16.14 rev 1.241, table 15.4-D; PRD ERR-93, ERR-94, IMP-138 to IMP-141).

A key states an estimated element, its versions and the ``ESTIMATE_CHANGED`` item of each. Since
lane SECFIX-ACT's estimate head the product asks for the workflow around them, and the plan
supplies it through the product's commands, as a person would (``platform_plan.
_estimate_prerequisites``): a version is created when it is due, at most one open per element; a
variable-consideration version names the reviewed CONSTRAINT record of its element — the key's
own, else the runner's, which is prepared on the version; a variable-consideration, EAC or
return-rate version is submitted with its evidence attached. Until this conversion the plan
drafted every version at the booking and sent the submission alone, and the one platform key with
an estimate — EX42 — stopped at ``estimates.submit_version`` with 422, "2 fields need attention".

No database: the plans, the calls a recording invoker keeps, their conversion to the API's own
request models, the permission each step answers to and the ids the ledger gives back. The
database witness is the key itself (``tests/answer_keys``, EX42 on the database platform).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal
from erev_api.domain.contracts import estimates as estimate_rules
from erev_api.domain.policies import judgements as judgement_rules
from erev_api.enums import FilePurpose, JudgementTopic, PrincipalKind
from erev_api.schemas.db_json import JudgementQuestionnaire
from erev_api.schemas.estimates import EstimateVersionCreateIn, EstimateVersionUpdateIn
from erev_api.schemas.judgements import JudgementCreateIn
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from support.answer_keys import step_permissions
from support.answer_keys.ledger_resolver import LedgerResolver, UnresolvedHandle
from support.answer_keys.loader import LoadedKey
from support.answer_keys.models import EventItem, ExpectProblem, Judgement
from support.answer_keys.platform_plan import (
    APPROVER,
    CONSTRAINT_CONCLUSION,
    CONSTRAINT_RATIONALE,
    ESTIMATE_MARKER,
    EVIDENCE_KINDS,
    PLATFORM_KEY_IDS,
    PREPARER,
    SSP_ANALYST,
    SYSTEM,
    H,
    Step,
    constraint_handle,
    constraint_judgement,
    constraint_of,
    load_platform_key,
    named_constraint,
    plan,
    stated_constraint,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import (
    MockResolver,
    adapt,
    bind_check,
    estimate_evidence,
    ssp_study,
)
from support.answer_keys.workspace_adapter import (
    Call,
    LedgerEntry,
    RecordingInvoker,
    WorkspaceAdapter,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
CONTRACT = "C-EX42-C"
ELEMENT = "BONUS-C"
SEQ = 7  # EX42's ESTIMATE_CHANGED item
RECORD = (H["judgement"], H["judgement_submit"], H["decide"])
EVIDENCE = (H["estimate_evidence"], H["estimate_evidence_attach"])
ROUTE = (H["estimate_submit"], H["decide"], H["compute"])
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/tenant")
AT = datetime(2026, 7, 1, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _calls(loaded: LoadedKey) -> list[Call]:
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock-fixture"
    )
    for step in plan(loaded).steps:
        if step.phase not in ("CHECKPOINT", "RUNNER") and step.gap is None:
            adapter.run(step)
    return invoker.calls


def _item(loaded: LoadedKey, seq: int = SEQ) -> list[Step]:
    """The steps of one timeline item, in the plan's order."""
    return [step for step in plan(loaded).steps if step.seq == seq and step.phase != "CHECKPOINT"]


def _with_contract(loaded: LoadedKey, **members: object) -> LoadedKey:
    """EX42 with members of the contract that holds its estimate replaced (in memory)."""
    contracts = tuple(
        contract.model_copy(update=members) if contract.external_id == CONTRACT else contract
        for contract in loaded.key.contracts
    )
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"contracts": contracts}))


def _with_estimate(loaded: LoadedKey, **members: object) -> LoadedKey:
    """EX42 with members of its one estimated element replaced (in memory)."""
    contract = next(c for c in loaded.key.contracts if c.external_id == CONTRACT)
    assert contract.estimates is not None
    (estimate,) = contract.estimates
    return _with_contract(loaded, estimates=(estimate.model_copy(update=members),))


def _with_timeline(loaded: LoadedKey, *items: object) -> LoadedKey:
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"timeline": items}))


def _principal(actor: str, roles: tuple[str, ...]) -> Principal:
    permissions = frozenset[str]().union(*(DEFAULT_ROLES[code] for code in roles))
    return Principal(
        kind=PrincipalKind.USER,
        id=uuid5(TENANT, actor),
        tenant_id=TENANT,
        membership_id=uuid5(TENANT, f"{actor}-m"),
        display_name=actor,
        roles=tuple(sorted(roles)),
        permissions=permissions,
        permission_scopes={code: "*" for code in permissions},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


# --- the plan -------------------------------------------------------------------------------------


def test_a_variable_consideration_version_is_prepared_before_its_submission() -> None:
    """EX42's item 7 as the product now asks for it: the preparer creates the version — now,
    when it is due —, prepares the CONSTRAINT record of the element on it and sends it for
    review; the approver reviews it; the preparer names the record on the version, uploads
    the version's evidence and attaches it; then the route of the item: the submission, the
    decision that appends ``ESTIMATE_CHANGED``, the computation. Seven steps of the runner's
    own before the route's three, all at the item's clock; the booking drafts no version."""
    ex42 = load_platform_key(EX42)
    command_plan = plan(ex42)
    steps = _item(ex42)
    assert [step.handler for step in steps] == [
        H["estimate_version"],
        *RECORD,
        H["estimate_version_update"],
        *EVIDENCE,
        *ROUTE,
    ]
    assert [step.actor for step in steps] == [
        PREPARER,
        PREPARER,
        PREPARER,
        APPROVER,
        PREPARER,
        PREPARER,
        PREPARER,
        PREPARER,
        APPROVER,
        SYSTEM,
    ]
    own, route = steps[:7], steps[7:]
    assert {step.phase for step in own} == {"CONTRACTS"} and {s.phase for s in route} == {
        "TIMELINE"
    }
    assert {step.subject for step in own} == {f"contract {CONTRACT}"}
    assert {step.detail[ESTIMATE_MARKER] for step in own} == {str(SEQ)}
    assert not any(ESTIMATE_MARKER in step.detail for step in route)
    assert len({step.clock_at for step in steps}) == 1 and steps[0].clock_at is not None
    # one stamp for the item, taken where the event is appended: the version's approval
    assert [step.captures_known_at for step in steps] == [False] * 8 + [True, False]
    assert command_plan.known_at_captures.count(SEQ) == 1
    handle = constraint_handle(ELEMENT, 1)
    version = own[0]
    assert (version.detail["element"], version.detail["version_no"]) == (ELEMENT, "1")
    assert version.detail["kind"] == "VARIABLE_CONSIDERATION"
    # the runner's record is a record OF the version, so the version is created without it
    assert "constraint" not in version.detail
    for step in own[1:4]:
        assert (step.detail["topic"], step.detail["handle"]) == ("CONSTRAINT", handle)
    assert own[3].detail["decision"] == "APPROVE"
    named = own[4]
    assert (named.detail["element"], named.detail["version_no"]) == (ELEMENT, "1")
    assert named.detail["constraint"] == handle
    # the booking leaves the element alone: no version is drafted there any more (PRD ERR-93)
    created = [s for s in command_plan.steps if s.handler == H["estimate_version"]]
    assert created == [version]
    element = [s for s in command_plan.steps if s.handler == H["estimate"]]
    assert [(s.phase, "after_booking" in s.detail) for s in element] == [("CONTRACTS", True)]
    assert command_plan.steps.index(element[0]) < command_plan.steps.index(own[0])


def test_what_a_version_owes_follows_the_kind_of_its_element() -> None:
    """The product's own table (04 table 15.4-D): evidence for a variable-consideration, EAC or
    return-rate version, the CONSTRAINT record for a variable-consideration version alone. A
    version of another kind is created and submitted."""
    assert EVIDENCE_KINDS is estimate_rules.EVIDENCE_KINDS
    assert {"VARIABLE_CONSIDERATION", "EAC", "RETURN_RATE"} == set(EVIDENCE_KINDS)
    ex42 = load_platform_key(EX42)
    expected = {
        "VARIABLE_CONSIDERATION": [
            H["estimate_version"],
            *RECORD,
            H["estimate_version_update"],
            *EVIDENCE,
        ],
        "EAC": [H["estimate_version"], *EVIDENCE],
        "RETURN_RATE": [H["estimate_version"], *EVIDENCE],
        "BREAKAGE": [H["estimate_version"]],
        "RENEWAL_EXPECTATION": [H["estimate_version"]],
    }
    for kind, handlers in expected.items():
        steps = _item(_with_estimate(ex42, estimate_kind=kind))
        assert [step.handler for step in steps] == [*handlers, *ROUTE], kind
        version = next(step for step in steps if step.handler == H["estimate_version"])
        assert "constraint" not in version.detail, kind
        named = [step for step in steps if step.handler == H["estimate_version_update"]]
        assert len(named) == int(kind == "VARIABLE_CONSIDERATION"), kind
        assert named_constraint(
            next(
                c
                for c in _with_estimate(ex42, estimate_kind=kind).key.contracts
                if c.external_id == CONTRACT
            ),
            ELEMENT,
            1,
        ) == (constraint_handle(ELEMENT, 1) if kind == "VARIABLE_CONSIDERATION" else None)


def test_each_version_is_created_at_its_own_item_after_its_predecessor_was_approved() -> None:
    """PRD ERR-93: at most one version of an element is open. With a second version and its own
    item, the second is created only after the decision that approved the first — never two
    creations of one element without that approval between them — and it has a record and an
    evidence file of its own."""
    ex42 = load_platform_key(EX42)
    contract = next(c for c in ex42.key.contracts if c.external_id == CONTRACT)
    assert contract.estimates is not None
    (estimate,) = contract.estimates
    (first,) = estimate.versions
    second = first.model_copy(
        update={"version_no": 2, "effective_date": "2026-12-31", "constrained_amount": "900.00"}
    )
    timeline = ex42.key.timeline
    seven = next(i for i in timeline if isinstance(i, EventItem) and i.seq == SEQ)
    last = max(item.seq for item in timeline)
    later = seven.model_copy(
        update={
            "seq": last + 1,
            "effective_date": "2026-12-31",
            "payload": {"estimate": ELEMENT, "version_no": "2"},
        }
    )
    variant = _with_timeline(_with_estimate(ex42, versions=(first, second)), *timeline, later)
    steps = plan(variant).steps
    created = [s for s in steps if s.handler == H["estimate_version"]]
    assert [(s.seq, s.detail["version_no"]) for s in created] == [(SEQ, "1"), (last + 1, "2")]
    approved_first = next(
        index
        for index, step in enumerate(steps)
        if step.seq == SEQ and step.handler == H["decide"] and step.detail.get("emits")
    )
    assert approved_first < steps.index(created[1])
    assert [step.handler for step in _item(variant, last + 1)] == [
        H["estimate_version"],
        *RECORD,
        H["estimate_version_update"],
        *EVIDENCE,
        *ROUTE,
    ]
    handles = [s.detail["constraint"] for s in steps if s.handler == H["estimate_version_update"]]
    assert handles == [constraint_handle(ELEMENT, 1), constraint_handle(ELEMENT, 2)]
    assert estimate_evidence(CONTRACT, ELEMENT, 1) != estimate_evidence(CONTRACT, ELEMENT, 2)
    # the calls convert: each version is created with the key's values and names its own record
    resolver = MockResolver(EX42)
    calls = _calls(variant)
    for number, version in enumerate((first, second), start=1):
        create = next(
            c
            for c in calls
            if c.handler == H["estimate_version"] and c.kwargs["version_no"] == number
        )
        (kwargs,) = adapt(create, variant.key, resolver)
        assert kwargs["body"].judgement_record_id is None
        assert kwargs["body"].constrained_amount == version.constrained_amount
        update = next(
            c
            for c in calls
            if c.handler == H["estimate_version_update"] and c.kwargs["version_no"] == number
        )
        (kwargs,) = adapt(update, variant.key, resolver)
        assert kwargs["version_id"] == resolver.estimate_version_id(CONTRACT, ELEMENT, number)
        assert kwargs["body"].judgement_record_id == resolver.judgement_id(
            CONTRACT, constraint_handle(ELEMENT, number)
        )


def test_a_key_that_states_the_constraint_record_gets_none_of_the_runners() -> None:
    """A key that states the CONSTRAINT judgement of its element speaks for itself, as a key that
    states Step 1 does: its record follows the booking like every judgement of a key, the plan
    prepares none, and the version names the key's. The key names its element as the product
    reads it — by its code, by the engine's estimate key, or by that key and the version."""
    ex42 = load_platform_key(EX42)
    estimate_key = obligation_subject_key(CONTRACT, ELEMENT)
    for named in (ELEMENT, estimate_key, f"{estimate_key}@v1"):
        own = Judgement(
            handle="J-CONSTRAINT",
            topic="CONSTRAINT",
            conclusion="The bonus is constrained to 750.00.",
            rationale="Stated by the key.",
            questionnaire={"estimate_key": named, "remote": False},
        )
        variant = _with_contract(ex42, judgements=(own,))
        contract = next(c for c in variant.key.contracts if c.external_id == CONTRACT)
        assert stated_constraint(contract, ELEMENT, 1) == own
        steps = _item(variant)
        assert [step.handler for step in steps] == [H["estimate_version"], *EVIDENCE, *ROUTE]
        assert steps[0].detail["constraint"] == "J-CONSTRAINT"
        # the key's record is prepared, sent and reviewed after the booking (FOLL-1)
        every = plan(variant).steps
        sent = next(
            index
            for index, s in enumerate(every)
            if s.handler == H["judgement_submit"] and s.detail.get("handle") == "J-CONSTRAINT"
        )
        booked = every[sent - 1 : sent + 2]
        assert [(s.handler, s.actor) for s in booked] == [
            (H["judgement"], PREPARER),
            (H["judgement_submit"], PREPARER),
            (H["decide"], APPROVER),
        ]
        assert all("after_booking" in s.detail for s in booked)
        assert sent < every.index(steps[0])
        create = next(c for c in _calls(variant) if c.handler == H["estimate_version"])
        resolver = MockResolver(EX42)
        (kwargs,) = adapt(create, variant.key, resolver)
        assert kwargs["body"].judgement_record_id == resolver.judgement_id(CONTRACT, "J-CONSTRAINT")
    # a record of another element, of another version or of another topic is not the element's
    for topic, named in (
        ("CONSTRAINT", "OTHER-ELEMENT"),
        ("CONSTRAINT", f"{estimate_key}@v2"),
        ("OTHER", ELEMENT),
    ):
        other = Judgement(
            handle="J-OTHER",
            topic=topic,
            conclusion="x",
            rationale="y",
            questionnaire={"estimate_key": named},
        )
        contract = next(
            c
            for c in _with_contract(ex42, judgements=(other,)).key.contracts
            if c.external_id == CONTRACT
        )
        assert stated_constraint(contract, ELEMENT, 1) is None
        assert named_constraint(contract, ELEMENT, 1) == constraint_handle(ELEMENT, 1)


def _refused(loaded: LoadedKey, code: str) -> list[Step]:
    """The steps of EX42's item 7 when the key expects its submission refused with ``code``."""
    timeline = tuple(
        item.model_copy(update={"expect_problem": ExpectProblem(code=code)})
        if isinstance(item, EventItem) and item.seq == SEQ
        else item
        for item in loaded.key.timeline
    )
    return _item(_with_timeline(loaded, *timeline))


def test_a_key_that_expects_the_submission_refused_gets_no_record_of_the_runners() -> None:
    """A key that expects the refusal of an estimate change gets the conversions and no
    statement: the plan creates the version, when due, attaches its evidence where its kind owes
    one, and sends the submission the key expects refused. The runner's CONSTRAINT record is not
    prepared — it would state what the expected values of such a key do not imply (DG-AK-41,
    the bound) — and a record the key states itself is named as ever. The product asks the
    version's own values first, so a refusal on them is reached either way; with the evidence
    there, so is a refusal that follows the product's questions — an EAC below the costs
    incurred."""
    ex42 = load_platform_key(EX42)
    steps = _refused(ex42, "validation-failed")
    assert [(step.phase, step.handler) for step in steps] == [
        ("CONTRACTS", H["estimate_version"]),
        ("CONTRACTS", H["estimate_evidence"]),
        ("CONTRACTS", H["estimate_evidence_attach"]),
        ("TIMELINE", H["estimate_submit"]),
    ]
    version, refused = steps[0], steps[-1]
    assert {step.actor for step in steps} == {PREPARER}
    assert all(step.detail[ESTIMATE_MARKER] == str(SEQ) for step in steps[:-1])
    assert ESTIMATE_MARKER not in refused.detail and "constraint" not in version.detail
    assert refused.detail["code"] == "validation-failed"
    assert (refused.detail["element"], refused.detail["version_no"]) == (ELEMENT, "1")
    assert len({step.clock_at for step in steps}) == 1 and version.clock_at is not None
    # by kind: the evidence where the kind owes it, never a record of the runner's
    for kind, code, handlers in (
        ("EAC", "eac-below-costs-incurred", [H["estimate_version"], *EVIDENCE]),
        ("RETURN_RATE", "validation-failed", [H["estimate_version"], *EVIDENCE]),
        ("BREAKAGE", "validation-failed", [H["estimate_version"]]),
    ):
        steps = _refused(_with_estimate(ex42, estimate_kind=kind), code)
        assert [step.handler for step in steps] == [*handlers, H["estimate_submit"]], kind
        assert steps[-1].detail["code"] == code
    # the key's own record is the key's statement: the version names it, refused or not
    own = Judgement(
        handle="J-CONSTRAINT",
        topic="CONSTRAINT",
        conclusion="The bonus is constrained to 750.00.",
        rationale="Stated by the key.",
        questionnaire={"estimate_key": ELEMENT, "remote": False},
    )
    steps = _refused(_with_contract(ex42, judgements=(own,)), "validation-failed")
    assert [step.handler for step in steps] == [
        H["estimate_version"],
        *EVIDENCE,
        H["estimate_submit"],
    ]
    assert steps[0].detail["constraint"] == "J-CONSTRAINT"


# --- the runner's own record ---------------------------------------------------------------------


def test_the_runners_constraint_record_says_what_the_keys_values_imply() -> None:
    """The record of a key that states none: topic CONSTRAINT, of the version itself and of no
    book, naming the element by its code; its conclusion is the one the key's expected values
    imply — the key takes the constrained amount into the transaction price — and ``remote``
    is No. The product's own questionnaire schema takes it as sent.

    The version is the subject the product's screen sends (SCREENS §8.4), and the one that
    leaves the contract alone: a record that names a contract holds it, while it is active,
    from its submission to its review, unless its subject is a modification or an estimate
    version (REQ-POL-010; 04 T-CON-20 "Judgement holds" rev 1.209;
    ``judgements.UNHELD_SUBJECTS``). Measured on the database platform on 2026-10-02: with
    the contract as the subject C-EX42-C's stream reads booked, assessed, activated,
    HOLD_APPLIED, HOLD_RELEASED, ESTIMATE_CHANGED; with the version it reads the first three
    and ESTIMATE_CHANGED."""
    assert "estimate_version" in judgement_rules.UNHELD_SUBJECTS
    assert "contract" not in judgement_rules.UNHELD_SUBJECTS
    record = constraint_judgement(ELEMENT, 1)
    assert (record.handle, record.topic) == (constraint_handle(ELEMENT, 1), "CONSTRAINT")
    assert (record.conclusion, record.rationale) == (CONSTRAINT_CONCLUSION, CONSTRAINT_RATIONALE)
    assert record.subject_obligation_key is None and record.book_code is None
    assert record.questionnaire == {"estimate_key": ELEMENT, "remote": False}
    ex42 = load_platform_key(EX42)
    resolver = MockResolver(EX42)
    calls = _calls(ex42)
    create = next(
        c for c in calls if c.handler == H["judgement"] and c.kwargs["handle"] == record.handle
    )
    version = next(c for c in calls if c.handler == H["estimate_version"])
    assert calls.index(version) < calls.index(create)  # its subject exists when it is made
    (kwargs,) = adapt(create, ex42.key, resolver)
    bind_check(create, [kwargs])
    body = kwargs["body"]
    assert isinstance(body, JudgementCreateIn)
    assert body.topic is JudgementTopic.CONSTRAINT and body.book is None
    assert (body.subject_type, body.subject_id) == (
        "estimate_version",
        resolver.estimate_version_id(CONTRACT, ELEMENT, 1),
    )
    assert body.contract_id == resolver.contract_id(CONTRACT)
    assert (body.conclusion, body.rationale) == (CONSTRAINT_CONCLUSION, CONSTRAINT_RATIONALE)
    assert body.questionnaire == {"estimate_key": ELEMENT, "remote": False}
    assert JudgementQuestionnaire.validate(JudgementTopic.CONSTRAINT, body.questionnaire) == {
        "estimate_key": ELEMENT,
        "remote": False,
    }
    # the handle names its element and version, also for a code that holds the separator
    for element, number in ((ELEMENT, 1), ("A:v2-B", 12), ("X", 3)):
        assert constraint_of(constraint_handle(element, number)) == (element, number)
    for handle in (None, "ak-step1", "ak-constraint:", "ak-constraint:BONUS-C", "J-CONSTRAINT"):
        assert constraint_of(handle) is None


# --- the conversions ----------------------------------------------------------------------------


def test_the_version_names_its_record_and_its_evidence_is_a_file_of_its_own() -> None:
    """The four calls of the version convert to the API's own requests and bind: the creation
    with the key's values, the edit that names the reviewed record and nothing else, the
    upload of a page of the runner's own as an attachment, the link of that file to the
    version."""
    ex42 = load_platform_key(EX42)
    resolver = MockResolver(EX42)
    calls = [c for c in _calls(ex42) if c.step.seq == SEQ]
    create = next(c for c in calls if c.handler == H["estimate_version"])
    (kwargs,) = adapt(create, ex42.key, resolver)
    bind_check(create, [kwargs])
    body = kwargs["body"]
    assert isinstance(body, EstimateVersionCreateIn)
    assert body.judgement_record_id is None
    assert kwargs["estimate_id"] == resolver.estimate_id(CONTRACT, ELEMENT)
    named = next(c for c in calls if c.handler == H["estimate_version_update"])
    (kwargs,) = adapt(named, ex42.key, resolver)
    bind_check(named, [kwargs])
    edit = kwargs["body"]
    assert isinstance(edit, EstimateVersionUpdateIn)
    assert edit.model_fields_set == {"judgement_record_id"}
    assert edit.judgement_record_id == resolver.judgement_id(
        CONTRACT, constraint_handle(ELEMENT, 1)
    )
    assert kwargs["version_id"] == resolver.estimate_version_id(CONTRACT, ELEMENT, 1)
    with pytest.raises(NotProvisioned, match="names no CONSTRAINT record"):
        adapt(
            Call(named.handler, PREPARER, {**named.kwargs, "constraint_handle": None}, named.step),
            ex42.key,
            resolver,
        )
    upload, attach = (next(c for c in calls if c.handler == handler) for handler in EVIDENCE)
    assert upload.kwargs["evidence"] is True and attach.kwargs["evidence"] is True
    (sent,) = adapt(upload, ex42.key, resolver)
    bind_check(upload, [sent])
    page = estimate_evidence(CONTRACT, ELEMENT, 1)
    assert sent["purpose"] == FilePurpose.ATTACHMENT.value
    assert (sent["media_type"], sent["original_filename"]) == (
        "application/pdf",
        "estimate-evidence-c-ex42-c-bonus-c-v1.pdf",
    )
    assert sent["stream"].read() == page and page.startswith(b"%PDF-")
    assert b"answer-key runner" in page and ELEMENT.encode() in page and CONTRACT.encode() in page
    (linked,) = adapt(attach, ex42.key, resolver)
    bind_check(attach, [linked])
    assert linked == {
        "file_object_id": resolver.estimate_evidence_id(CONTRACT, ELEMENT, 1),
        "subject_type": estimate_rules.ATTACHMENT_SUBJECT,
        "subject_id": resolver.estimate_version_id(CONTRACT, ELEMENT, 1),
        "description": None,
    }
    # one file per contract, element and version; never the page of an SSP study
    pages = {
        page,
        estimate_evidence(CONTRACT, ELEMENT, 2),
        estimate_evidence(CONTRACT, "OTHER", 1),
        estimate_evidence("C-OTHER", ELEMENT, 1),
        ssp_study("BOOK", 1),
    }
    assert len(pages) == 5
    # a version of an element without a record is created without one and is never edited
    plain = _with_estimate(ex42, estimate_kind="EAC")
    plain_calls = _calls(plain)
    create = next(c for c in plain_calls if c.handler == H["estimate_version"])
    assert create.kwargs["constraint_handle"] is None
    (kwargs,) = adapt(create, plain.key, resolver)
    assert kwargs["body"].judgement_record_id is None
    assert not [c for c in plain_calls if c.handler == H["estimate_version_update"]]


def test_the_two_shared_commands_are_told_apart_by_the_steps_marker() -> None:
    """``POST /files`` and ``POST /attachments`` carry the study of an SSP version — the
    analyst's — and the evidence of an estimate version — the preparer's. The plan's marker
    tells the two uses apart: in the conversion, in the permission the step answers to (ACT-2)
    and in the id the ledger gives back."""
    assert H["estimate_evidence"] == H["ssp_study"]
    assert H["estimate_evidence_attach"] == H["ssp_study_attach"]
    ex42 = load_platform_key(EX42)
    resolver = MockResolver(EX42)
    calls = _calls(ex42)
    uploads = [c for c in calls if c.handler == H["ssp_study"]]
    studies = [c for c in uploads if c.step.subject.startswith("ssp_book ")]
    evidence = [c for c in uploads if c not in studies]
    assert studies and len(evidence) == 1
    assert {c.actor for c in studies} == {SSP_ANALYST} and evidence[0].actor == PREPARER
    for call in studies:
        (sent,) = adapt(call, ex42.key, resolver)
        assert sent["purpose"] == FilePurpose.SSP_STUDY.value and "evidence" not in call.kwargs
    # ACT-2: each use answers to its own permission, read from the product
    preparer = _principal(PREPARER, ("revenue_accountant",))
    analyst = _principal(SSP_ANALYST, ("ssp_analyst",))
    for handler, own, study in (
        (H["estimate_evidence"], step_permissions.EVIDENCE_UPLOAD, step_permissions.STUDY_UPLOAD),
        (
            H["estimate_evidence_attach"],
            step_permissions.EVIDENCE_ATTACH,
            step_permissions.STUDY_ATTACH,
        ),
    ):
        marked = next(c for c in calls if c.handler == handler and ESTIMATE_MARKER in c.step.detail)
        plain = next(c for c in calls if c.handler == handler and c not in (marked,))
        assert step_permissions.required_permissions(marked, []) == own
        assert step_permissions.required_permissions(plain, []) == study
        assert step_permissions.declaration(handler, {}) == step_permissions.declared(handler)
        step_permissions.check(marked, preparer, [])
        step_permissions.check(plain, analyst, [])
        with pytest.raises(NotProvisioned, match="ACT-2: .* lacks permission ssp.create"):
            step_permissions.check(plain, preparer, [])  # the study is not the preparer's
        if handler == H["estimate_evidence_attach"]:
            # the link asks the write permission of the estimate version: not the analyst's
            with pytest.raises(NotProvisioned, match="lacks permission estimate.create"):
                step_permissions.check(marked, analyst, [])
        else:
            # an attachment is uploaded under the write permission of ANY subject (API-R-10),
            # the analyst's among them: the link is where the estimate's own is asked
            step_permissions.check(marked, analyst, [])
    assert step_permissions.EVIDENCE_ATTACH == frozenset({"estimate.create"})
    assert "estimate.create" in step_permissions.EVIDENCE_UPLOAD
    assert not step_permissions.EVIDENCE_UPLOAD & DEFAULT_ROLES["controller"]
    # the ledger: the evidence upload among the study uploads
    study_id, evidence_id = (uuid5(TENANT, name) for name in ("study", "evidence"))
    ledger = [
        LedgerEntry(studies[0], SSP_ANALYST, AT, AT, None, {"id": study_id}),
        LedgerEntry(evidence[0], PREPARER, AT, AT, None, {"id": evidence_id}),
    ]
    found = LedgerResolver(ledger)
    assert found.estimate_evidence_id(CONTRACT, ELEMENT, 1) == evidence_id
    code, version_no = studies[0].kwargs["code"], studies[0].kwargs["version"]
    assert found.ssp_study_id(code, version_no) == study_id
    with pytest.raises(UnresolvedHandle, match="estimate_evidence"):
        found.estimate_evidence_id(CONTRACT, ELEMENT, 2)
    with pytest.raises(UnresolvedHandle, match="estimate_evidence"):
        LedgerResolver(ledger[:1]).estimate_evidence_id(CONTRACT, ELEMENT, 1)
    assert isinstance(evidence_id, UUID)

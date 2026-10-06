"""Layers 4 to 15 of the platform runner (dev-guide DG-AK-41 rev 1.213 and rev 1.219).

What the runner states on a key's behalf before an activation — a contract reference, a Step 1
review, a distinct review per obligation —, the bound of those statements, and the world the plan
creates around the key's own: the parity templates of a ``LEGACY_PARITY`` key, the calendar the
engine needs, a product's principal conclusion, a legacy SSP entry without bands, a report's
typed parameters. No database: the plans, the calls a recording invoker keeps and their
conversion to the API's own request models; the database witnesses are the keys themselves
(``tests/answer_keys``) and ``tests/domain/answer_keys``.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta

import pytest
from erev_api.enums import ContractEventType, Distinctness, JudgementTopic
from erev_api.schemas.contracts import DistinctReviewIn
from erev_api.schemas.events import EventAppendIn
from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn
from support.answer_keys.loader import LoadedKey
from support.answer_keys.models import EventItem, Judgement, PobTemplate
from support.answer_keys.platform_plan import (
    APPROVER,
    DISTINCT_BOUND,
    DISTINCT_RATIONALE,
    PLATFORM_KEY_IDS,
    PREPARER,
    REVIEWED_DISTINCTNESS,
    STEP1_BOUND,
    STEP1_CONCLUSION,
    STEP1_EVENT,
    STEP1_HANDLE,
    STEP1_RATIONALE,
    H,
    Step,
    load_platform_key,
    plan,
    plan_templates,
    states_step1,
)
from support.answer_keys.platform_runner import (
    EXECUTED,
    NOT_RUN,
    DbPlatform,
    NotProvisioned,
    platform_outcome,
    run_platform,
)
from support.answer_keys.request_models import (
    MockResolver,
    adapt,
    bind_check,
    booking_request,
    case_product,
    judgement_request,
    product_in,
    ssp_entries_in,
)
from support.answer_keys.runners import KEY_PRINCIPAL_AGENT, _Assembler
from support.answer_keys.workspace_adapter import (
    Call,
    RecordingInvoker,
    WorkspaceAdapter,
    report_parameters,
)
from support.golden_streams import parity_templates

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
STATEMENT = (H["judgement"], H["judgement_submit"], H["decide"], H["record_events"])
REVIEW = (H["distinct_review"], H["decide"])


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class _Converting:
    """An invoker that converts every call as the database invoker does before it runs anything
    (``request_models.adapt``; ids from the mock resolver): a call the conversion refuses is
    refused here, by the same name."""

    def __init__(self, loaded: LoadedKey) -> None:
        self.key = loaded.key
        self.resolver = MockResolver(loaded.key.id)
        self.calls: list[Call] = []

    def __call__(self, call: Call) -> object:
        self.calls.append(call)
        bind_check(call, adapt(call, self.key, self.resolver))
        return None


def _calls(loaded: LoadedKey) -> list[Call]:
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock-fixture"
    )
    for step in plan(loaded).steps:
        if step.phase not in ("CHECKPOINT", "RUNNER") and step.gap is None:
            adapter.run(step)
    return invoker.calls


def _with_contracts(loaded: LoadedKey, **first: object) -> LoadedKey:
    """The key with members of its first contract replaced (no platform key states them)."""
    head, *rest = loaded.key.contracts
    contracts = (head.model_copy(update=first), *rest)
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"contracts": contracts}))


def _with_templates(loaded: LoadedKey, *templates: PobTemplate) -> LoadedKey:
    world = loaded.key.world.model_copy(update={"pob_templates": templates})
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"world": world}))


# --- layer 4: the three statements ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("key_id", "count"), [(POS_012, 12), (DLT, 24), (EX21, 12), (EX42, 12), (POS_117, 10)]
)
def test_layer_4_states_a_step_1_review_and_distinct_reviews_before_an_activation(
    key_id: str, count: int
) -> None:
    """A key states a contract's terms and events, not the workflow an activation asks for (04
    table 15.4-I). Before each activation the runner records, as the preparer with the
    approver's review: per obligation of a contract of two or more a distinct review that
    confirms its template's conclusion, then one Step 1 record of the contract and a probable
    assessment per enabled book. The steps sit between the contract's booking and the
    submission of its activation, at the activation item's clock and seq."""
    loaded = load_platform_key(key_id)
    key = loaded.key
    steps = plan(loaded).steps
    own = [step for step in steps if "before_activation" in step.detail]
    assert len(own) == count
    assert all(step.phase == "CONTRACTS" and step.gap is None for step in own)
    templates = {template.code: template for template in plan_templates(key.world)}
    products = {product.code: product for product in key.world.products}
    books = {entity.code: ",".join(sorted(entity.books)) for entity in key.world.entities}
    activations = [
        item
        for item in key.timeline
        if isinstance(item, EventItem) and item.event_type == "CONTRACT_ACTIVATED"
    ]
    assert len(activations) == len(key.contracts)  # every contract of the five keys is activated
    for item in activations:
        contract = next(c for c in key.contracts if c.external_id == item.contract)
        subject = f"contract {contract.external_id}"
        stated = [step for step in own if step.detail["before_activation"] == str(item.seq)]
        assert {step.subject for step in stated} == {subject}
        submission = next(
            step
            for step in steps
            if step.handler == H["submit_activation"] and step.seq == item.seq
        )
        booking = next(
            step
            for step in steps
            if step.handler == H["book"] and contract.external_id in step.subject
        )
        first, last = steps.index(stated[0]), steps.index(stated[-1])
        assert steps.index(booking) < first and last == steps.index(submission) - 1
        assert steps[first : last + 1] == tuple(stated)  # one run of steps, nothing between
        assert {(step.seq, step.clock_at) for step in stated} == {(item.seq, submission.clock_at)}
        assert not any(step.captures_known_at for step in stated)
        reviewed = [
            (line.obligation_key, templates[products[line.product_code].pob_template].distinctness)
            for line in contract.lines
        ]
        reviewed = [] if len(contract.lines) < 2 else reviewed
        assert all(conclusion in REVIEWED_DISTINCTNESS for _, conclusion in reviewed)
        assert [step.handler for step in stated] == [*REVIEW * len(reviewed), *STATEMENT]
        assert [step.actor for step in stated] == [
            *(PREPARER, APPROVER) * len(reviewed),
            PREPARER,
            PREPARER,
            APPROVER,
            PREPARER,
        ]
        reviews = stated[: 2 * len(reviewed) : 2]
        assert [
            (step.detail["obligation_key"], step.detail["distinctness"]) for step in reviews
        ] == reviewed
        record, submit, approval, assessment = stated[-4:]
        assert record.detail["handle"] == submit.detail["handle"] == STEP1_HANDLE
        assert record.detail["topic"] == approval.detail["topic"] == "COLLECTIBILITY"
        assert (assessment.detail["step1"], assessment.detail["books"]) == (
            STEP1_HANDLE,
            books[contract.contracting_entity],
        )
        assert assessment.detail["effective_date"] == contract.inception_date


def test_the_statements_convert_to_the_apis_own_requests() -> None:
    """The three statements as the API takes them. The booking names the contract's own id as
    its order reference (``SOURCE_REFERENCE``); the review confirms ``distinct`` with the
    runner's rationale; the Step 1 record is of the contract and of no book, answers the five
    criteria of 606-10-25-1 with Yes and says why; each assessment is probable, dated at the
    contract's inception and cites that record."""
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        for contract in loaded.key.contracts:
            booked = booking_request(contract, loaded.key.world, MockResolver(key_id))
            assert booked.document_ref == contract.external_id
    loaded = load_platform_key(POS_012)
    resolver = MockResolver(POS_012)
    contract = loaded.key.contracts[0]
    contract_id = resolver.contract_id(contract.external_id)
    stated = [call for call in _calls(loaded) if call.step.detail.get("before_activation") == "2"]
    review, _, second, _, record, submit, _, assessment = stated
    for call in stated:
        bind_check(call, adapt(call, loaded.key, resolver))
    for call, obligation_key in ((review, "X1-LICENCE"), (second, "X2-SERVICES")):
        (sent,) = adapt(call, loaded.key, resolver)
        assert sent == {
            "contract_id": contract_id,
            "obligation_key": obligation_key,
            "body": DistinctReviewIn(
                distinctness=Distinctness.DISTINCT, rationale=DISTINCT_RATIONALE
            ),
        }
        assert sent["body"].integrates_into_obligation_key is None
    (sent,) = adapt(record, loaded.key, resolver)
    body = sent["body"]
    assert isinstance(body, JudgementCreateIn)
    assert (body.topic, body.subject_type, body.subject_id, body.contract_id, body.book) == (
        JudgementTopic.COLLECTIBILITY,
        "contract",
        contract_id,
        contract_id,
        None,
    )
    assert (body.conclusion, body.rationale) == (STEP1_CONCLUSION, STEP1_RATIONALE)
    assert body.questionnaire == {"criteria": dict.fromkeys("abcde", "YES")}
    (sent,) = adapt(submit, loaded.key, resolver)
    record_id = resolver.judgement_id(contract.external_id, STEP1_HANDLE)
    assert sent == {"judgement_id": record_id, "body": JudgementSubmitIn()}
    (sent,) = adapt(assessment, loaded.key, resolver)
    assert (sent["contract_id"], sent["expected_stream_version"]) == (contract_id, 1)
    appended = sent["body"]
    assert isinstance(appended, EventAppendIn)
    (event,) = appended.events  # US01 enables one book
    assert (
        event.event_type
        is ContractEventType.COLLECTIBILITY_ASSESSED
        == ContractEventType(STEP1_EVENT)
    )
    assert event.effective_date == date.fromisoformat(contract.inception_date)
    assert event.payload == {
        "book": "ASC606",
        "is_probable": True,
        "judgement_record_id": str(record_id),
    }
    # GT07's entities enable ASC606 and LEGACY: one assessment per enabled book, in one append,
    # and the stream head moves by two.
    dlt = load_platform_key(DLT)
    assessed = next(call for call in _calls(dlt) if call.kwargs.get("step1"))
    (sent,) = adapt(assessed, dlt.key, MockResolver(DLT))
    assert [event.payload["book"] for event in sent["body"].events] == ["ASC606", "LEGACY"]
    assert all(event.payload["is_probable"] is True for event in sent["body"].events)
    activation = next(call for call in _calls(dlt) if call.handler == H["submit_activation"])
    assert activation.kwargs["expected_stream_version"] == 3  # booking 1, two assessments


def test_a_key_that_states_step_1_itself_gets_no_statement_of_the_runner() -> None:
    """A key that carries a Step 1 judgement or an assessment event of a contract speaks for
    itself there: the runner adds its record and its assessment for the other contracts only."""
    loaded = load_platform_key(POS_012)
    first, second = loaded.key.contracts
    timeline = loaded.key.timeline
    assert not states_step1(first, timeline) and not states_step1(second, timeline)
    for topic, stated in (
        ("COLLECTIBILITY", True),
        ("NOT_A_CONTRACT", True),
        ("CONTRACT_TERM", False),
    ):
        judged = first.model_copy(
            update={"judgements": (Judgement(handle="J1", topic=topic, conclusion="c"),)}
        )
        assert states_step1(judged, timeline) is stated, topic
    event = next(item for item in timeline if isinstance(item, EventItem))
    assessed = event.model_copy(
        update={"event_type": STEP1_EVENT, "contract": first.external_id, "payload": {}}
    )
    assert states_step1(first, (*timeline, assessed))
    assert not states_step1(second, (*timeline, assessed))  # another contract's event
    own = Judgement(
        handle="J1", topic="COLLECTIBILITY", conclusion="Collectible.", rationale="Credit review."
    )
    steps = plan(_with_contracts(loaded, judgements=(own,))).steps
    of_first = [step for step in steps if step.subject == f"contract {first.external_id}"]
    handles = [step.detail["handle"] for step in of_first if "handle" in step.detail]
    assert handles == ["J1"] * 2  # the key's own record, created and submitted after booking
    assert not [step for step in of_first if step.detail.get("step1")]
    assert [step.handler for step in of_first if "before_activation" in step.detail] == [
        *REVIEW * 2  # the reviews of its two obligations stay: the key states none
    ]
    of_second = [step for step in steps if step.subject == f"contract {second.external_id}"]
    assert [step.handler for step in of_second] == list(STATEMENT)


# --- the bound -----------------------------------------------------------------------------------


def test_the_bound_refuses_by_name_what_the_keys_expected_values_do_not_imply() -> None:
    """DG-AK-41 (rev 1.213): the runner states only what the key's expected values already
    imply. An obligation whose template concludes nondistinct, and a contract the key's facts
    make no contract, get no default statement: the conversion refuses them by name. GT07 is
    the one key of the five that meets the bound, with three nondistinct obligations."""
    refused: dict[str, list[str]] = {}
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        resolver = MockResolver(key_id)
        for call in _calls(loaded):
            try:
                adapt(call, loaded.key, resolver)
            except NotProvisioned as bound:
                refused.setdefault(key_id, []).append(str(bound))
    assert set(refused) == {DLT}
    # The bound is its own reason: it says nothing of databases (item AK-NOT-RUN-REASON-1).
    assert refused[DLT] == [
        f"not run — CONTRACTS contract {contract} obligation "
        f"{obligation!r}: {DISTINCT_BOUND} ({H['distinct_review']})"
        for contract, obligation in (
            ("CONTRACT-1", "POB #3"),
            ("CONTRACT-2", "POB #3"),
            ("CONTRACT-2", "VC #1"),
        )
    ]
    assert "nondistinct" in DISTINCT_BOUND and "DG-AK-41" in DISTINCT_BOUND
    # A series template records its conclusion itself: no review is planned at all.
    pos = load_platform_key(POS_012)
    series = tuple(
        template.model_copy(update={"distinctness": "series"})
        if template.code == "TPL-PIT"
        else template
        for template in pos.key.world.pob_templates
    )
    reviews = [
        step
        for step in plan(_with_templates(pos, *series)).steps
        if step.handler == H["distinct_review"]
    ]
    assert [step.detail["obligation_key"] for step in reviews] == ["X2-SERVICES"]
    # A contract without commercial substance is, by the key's own facts, no contract: the
    # runner's Step 1 record of it is refused; the other contract's record converts.
    hollow = _with_contracts(pos, has_commercial_substance=False)
    records = [call for call in _calls(hollow) if call.handler == H["judgement"]]
    assert [call.kwargs["contract"] for call in records] == ["C-POS-012-X", "C-POS-012-Y"]
    with pytest.raises(NotProvisioned) as bound:
        adapt(records[0], hollow.key, MockResolver(POS_012))
    assert str(bound.value) == (
        f"not run — CONTRACTS contract C-POS-012-X: {STEP1_BOUND} ({H['judgement']})"
    )
    (sent,) = adapt(records[1], hollow.key, MockResolver(POS_012))
    assert sent["body"].questionnaire == {"criteria": dict.fromkeys("abcde", "YES")}
    substantial = _with_contracts(pos, has_commercial_substance=True)
    (sent,) = adapt(records[0], substantial.key, MockResolver(POS_012))
    assert sent["body"].questionnaire == {"criteria": dict.fromkeys("abcde", "YES")}
    # A Step 1 record the key itself states is the key's: it converts with the answer its facts
    # give to criterion (d), and the product judges it.
    own = Judgement(handle="J1", topic="COLLECTIBILITY", conclusion="c", rationale="r")
    contract_id = MockResolver(POS_012).contract_id("C-POS-012-X")
    stated = judgement_request(own, contract_id, contract_id, commercial_substance=False)
    assert stated.questionnaire == {"criteria": {**dict.fromkeys("abce", "YES"), "d": "NO"}}


def test_gt07_ends_not_run_at_the_bound_on_the_database_platform() -> None:
    """On the database platform a refused conversion is a refused step, and the platform stops
    there. GT07 runs its world — the parity templates among it — books CONTRACT-1, reviews its
    two distinct obligations and stops at the review of ``POB #3``: nothing after it runs, no
    block is compared, and the key ends not run with the bound as its reason — not on a refusal
    of the product's activation checklist."""
    loaded = load_platform_key(DLT)
    invoker = _Converting(loaded)
    adapter = WorkspaceAdapter(loaded, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock")
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    stopped = next(item for item in result.executed if item.status == NOT_RUN)
    at = result.executed.index(stopped)
    assert (stopped.step.handler, stopped.step.detail["obligation_key"]) == (
        H["distinct_review"],
        "POB #3",
    )
    assert stopped.step.subject == "contract CONTRACT-1"
    assert stopped.reason is not None and DISTINCT_BOUND in stopped.reason
    assert {item.status for item in result.executed[:at]} == {EXECUTED}
    assert {item.status for item in result.executed[at:]} == {NOT_RUN}
    assert invoker.calls[-1].step == stopped.step  # the last call made: nothing ran after it
    assert all(
        "not run after CONTRACTS contract CONTRACT-1 (record_distinct_review)"
        in (item.reason or "")
        for item in result.executed[at + 1 :]
    )
    done = [call.step for call in invoker.calls[:-1]]
    published = {
        step.subject.removeprefix("pob_template ")
        for step in done
        if step.handler == H["template_publish"]
    }
    assert published == {template.code for template in plan_templates(loaded.key.world)}
    assert [
        step.detail["obligation_key"] for step in done if step.handler == H["distinct_review"]
    ] == [
        "POB #1",
        "POB #2",
    ]
    assert not [step for step in done if step.handler == H["submit_activation"]]
    assert sorted(result.known_at) == [1]  # CONTRACT-1's booking alone was stamped
    blocks = [block for checkpoint in result.checkpoints for block in checkpoint.blocks]
    assert blocks and {block.status for block in blocks} == {NOT_RUN}
    assert result.mismatches == ()
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN
    # the outcome opens with what the key waits for (item AK-NOT-RUN-REASON-1)
    assert message.startswith(
        f"not run — CONTRACTS contract CONTRACT-1 obligation 'POB #3': {DISTINCT_BOUND} "
        f"({H['distinct_review']}); db platform: "
    )
    assert "databases not provisioned" not in message


# --- the world around the key's own -------------------------------------------------------------


def test_the_plan_creates_the_parity_templates_of_a_legacy_parity_key() -> None:
    """Stage 03 assigns a line of a ``LEGACY_PARITY`` tenant one of four parity templates by its
    kind (ENGINE_SPEC S03-R-18), and the oracle's bundle holds them beside the key's own. The
    product has no writer of them but the template lifecycle, so the plan takes each through
    it — create, version, case, test, submit, approval, publish — as it takes the key's own. A
    key that defines one of the codes itself keeps its definition; a ``DEFAULT`` key gets none."""
    dlt = load_platform_key(DLT)
    world = dlt.key.world
    seeded = {template.template_code: template for template in parity_templates(date.min)}
    assert sorted(seeded) == [
        "LEGACY-DISTINCT",
        "LEGACY-MATERIAL-RIGHT",
        "LEGACY-NONDISTINCT",
        "LEGACY-VC",
    ]
    planned = plan_templates(world)
    assert planned[: len(world.pob_templates)] == world.pob_templates
    added = planned[len(world.pob_templates) :]
    assert [template.code for template in added] == sorted(seeded)
    for template in added:
        source = seeded[template.code]
        assert (
            template.obligation_kind,
            template.distinctness,
            template.satisfaction_pattern,
            template.over_time_criterion,
            template.recognition_method,
        ) == (
            source.obligation_kind,
            source.distinctness,
            source.satisfaction_pattern,
            source.over_time_criterion,
            source.recognition_method,
        )
    steps = plan(dlt).steps
    lifecycle = [
        H["template"],
        H["template_version"],
        H["template_case"],
        H["template_test"],
        H["template_submit"],
        H["decide"],
        H["template_publish"],
    ]
    bound = min(index for index, step in enumerate(steps) if step.handler == H["product_template"])
    for template in planned:
        own = [
            (index, step)
            for index, step in enumerate(steps)
            if step.subject == f"pob_template {template.code}"
        ]
        assert [step.handler for _, step in own] == lifecycle, template.code
        assert all(step.phase == "WORLD" and index < bound for index, step in own)
    # The example case of a parity template books a product of the key: one whose own template
    # is of the same kind and conclusion, else the world's first.
    assert {template.code: case_product(world, template).code for template in added} == {  # type: ignore[union-attr]
        "LEGACY-DISTINCT": "HARDWARE-1",
        "LEGACY-MATERIAL-RIGHT": "MR-HARDWARE",
        "LEGACY-NONDISTINCT": "CONSULTING-1",
        "LEGACY-VC": "HARDWARE-1",  # no own template is a distinct VC line: the first product
    }
    resolver = MockResolver(DLT)
    cases = [
        call
        for call in _calls(dlt)
        if call.handler == H["template_case"] and call.kwargs["code"].startswith("LEGACY-")
    ]
    assert len(cases) == 4
    for call in cases:
        (sent,) = adapt(call, dlt.key, resolver)
        (line,) = sent["facts"]["lines"]
        template = next(item for item in added if item.code == call.kwargs["code"])
        assert line["product_code"] == case_product(world, template).code  # type: ignore[union-attr]
        assert sent["subject_id"] == resolver.template_version_id(template.code)
    # A key's own definition of a parity code wins; a template no product uses has no case.
    own_vc = PobTemplate(
        code="LEGACY-VC",
        obligation_kind="VC_LINE",
        distinctness="nondistinct",
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="UNITS_DELIVERED",
    )
    redefined = _with_templates(dlt, *world.pob_templates, own_vc).key.world
    codes = [template.code for template in plan_templates(redefined)]
    assert codes.count("LEGACY-VC") == 1 and own_vc in plan_templates(redefined)
    assert case_product(redefined, own_vc) is None
    for key_id in (POS_012, EX21, EX42, POS_117):
        default = load_platform_key(key_id).key.world
        assert plan_templates(default) == default.pob_templates


def test_the_calendar_reaches_every_date_the_engine_places() -> None:
    """The engine needs a period for every date it places (CV-12), so each entity's calendar
    holds the fiscal years from the world's first period to the month of the latest date a
    contract line, an estimate or an item carries (``_Assembler.calendar_end``). The periods of
    ``world.periods`` are opened; the later ones stay as generated."""
    years = {}
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        world, assembler = loaded.key.world, _Assembler(loaded)
        steps = plan(loaded).steps
        for entity in world.entities:
            of_entity = [
                int(step.detail["fiscal_year"])
                for step in steps
                if step.handler == H["fiscal_year"] and step.subject == f"entity {entity.code}"
            ]
            first = min(int(world.periods.from_[:4]), assembler.world_start.year)
            last = max(int(world.periods.to[:4]), assembler.calendar_end.year)
            assert of_entity == list(range(first, last + 1)), (key_id, entity.code)
            years[key_id] = of_entity
        opened = {step.detail["range"] for step in steps if step.handler == H["open_period"]}
        assert opened == {f"{world.periods.from_}..{world.periods.to}"}
    assert years == {
        POS_012: [2026, 2027],  # SUPPORT-Y runs to January 2027; the key's periods end in 2026
        DLT: [2023],
        EX21: [2026, 2027],
        EX42: [2026, 2027, 2028],
        POS_117: [2026],
    }


def test_a_key_product_is_principal_unless_it_says_otherwise() -> None:
    """D-83 ruling 1: the keys' figures assume gross revenue, so a key product that omits
    ``principal_agent`` is created as PRINCIPAL — the product's own default is NOT_ASSESSED,
    which the engine refuses to compute (S03-R-09). A product that states its conclusion keeps
    it."""
    world = load_platform_key(POS_012).key.world
    resolver = MockResolver(POS_012)
    assert all(product.principal_agent is None for product in world.products)
    assert {product_in(product, resolver).principal_agent for product in world.products} == {
        KEY_PRINCIPAL_AGENT
    }
    assert KEY_PRINCIPAL_AGENT == "PRINCIPAL"
    agent = world.products[0].model_copy(update={"principal_agent": "AGENT"})
    assert product_in(agent, resolver).principal_agent == "AGENT"


def test_a_legacy_range_entry_sends_no_bands() -> None:
    """04 T-REF-31: the server derives the one band of a ``legacy_range`` entry from its list
    price, discount and range, and refuses a band from the client, an empty list too. GT07's
    entries state none and send none; an entry that states its bands sends them."""
    legacy = ssp_entries_in(load_platform_key(DLT).key.world.ssp_books[0].versions[0])
    assert {entry.method for entry in legacy.entries} == {"legacy_range"}
    assert not any("ranges" in entry.model_fields_set for entry in legacy.entries)
    observable = ssp_entries_in(load_platform_key(EX21).key.world.ssp_books[0].versions[0])
    assert all(
        "ranges" in entry.model_fields_set and len(entry.ranges or ()) == 1
        for entry in observable.entries
    )


def test_report_parameters_take_the_types_the_reports_schema_declares() -> None:
    """A key carries numbers as strings: EX42 states ``time_bands: ["12", "24"]``, and the
    report run is refused unless they are whole numbers. The parameters go in the JSON types
    the report's own schema declares, and nothing else of them changes."""
    (rpo,) = load_platform_key(EX42).key.checkpoints[0].reports or ()
    assert rpo.parameters["time_bands"] == ["12", "24"]
    sent = report_parameters(rpo)
    assert sent == {**rpo.parameters, "time_bands": [12, 24]}
    assert [type(band) for band in sent["time_bands"]] == [int, int]
    for block in load_platform_key(EX21).key.checkpoints[0].reports or ():
        assert report_parameters(block) == dict(block.parameters)


def test_a_step_is_one_statement_with_its_own_detail() -> None:
    """The plan's own steps carry what their conversion needs and nothing a key does not imply:
    a review names its obligation and the template's conclusion; an assessment the books and
    the inception date."""
    steps = plan(load_platform_key(POS_117)).steps
    reviews = [step for step in steps if step.handler == H["distinct_review"]]
    assert [(step.detail["obligation_key"], step.detail["distinctness"]) for step in reviews] == [
        ("P1", "distinct"),
        ("P2", "distinct"),
        ("P3", "distinct"),
    ]
    (assessment,) = [step for step in steps if step.detail.get("step1")]
    assert isinstance(assessment, Step)
    assert dict(assessment.detail) == {
        "step1": STEP1_HANDLE,
        "books": "ASC606",
        "effective_date": "2026-03-01",
        "before_activation": "2",
    }

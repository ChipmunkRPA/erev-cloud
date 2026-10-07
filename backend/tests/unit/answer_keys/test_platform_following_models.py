"""Record §18: the ``FOLLOWING`` request models — judgements, estimates including
the estimate lifecycle command route, rule sets and FX rate sets — converted to the API's own
request models with the key's actual values, bound to the real handler signatures, ids through the
resolver, refused by name where a handle or value is missing (rules FOLL-1 to FOLL-4).

Fail-first (`.run/f-rps-e1/fail-first-following.log`, head 89ed360f): 19 ``FOLLOWING`` refusals
over the five keys, every ``CONTRACTS`` step before any booking, EX42 seq 7 ``not_run`` (CONV-2),
C-EX42-C stream head 2. Mock-executed: ``RecordingInvoker`` and ``MockResolver``; no database.

Supported policy overrides use native request models and the approval lifecycle. Unsupported
policies remain explicit findings, covered by `test_platform_override_tie`.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta

import pytest
from erev_api.enums import (
    BookCode,
    EstimateKind,
    EstimateMethod,
    JudgementTopic,
    RateType,
    RuleSetKind,
)
from erev_api.schemas.currencies import FxRateSetIn, FxRateSetVersionIn
from erev_api.schemas.estimates import (
    EstimateCreateIn,
    EstimateVersionCreateIn,
    EstimateVersionSubmitIn,
)
from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn
from support.answer_keys.loader import LoadedKey
from support.answer_keys.models import (
    FxRate,
    FxRateSet,
    Judgement,
    Rule,
    RuleExampleCase,
    RuleSet,
)
from support.answer_keys.platform_plan import (
    APPROVER,
    CONSTRAINT_RATIONALE,
    ESTIMATE_MARKER,
    PLATFORM_KEY_IDS,
    PREPARER,
    STEP1_HANDLE,
    STEP1_RATIONALE,
    SYSTEM,
    H,
    Step,
    constraint_handle,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import (
    EXECUTED,
    DbPlatform,
    NotProvisioned,
    run_platform,
)
from support.answer_keys.request_models import (
    SCHEMA_GAPS,
    MockResolver,
    adapt,
    bind_check,
    example_case_kwargs,
    fx_rate_set_request,
    fx_version_request,
    judgement_request,
    rule_kwargs,
)
from support.answer_keys.workspace_adapter import Call, RecordingInvoker, WorkspaceAdapter

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
# Register index 308: the product's two override commands, by dotted path — the plan names
# neither — and the overrides each of the three keys declares (all POL-122 at an obligation).
OVERRIDE_COMMANDS = (
    "erev_api.domain.policies.overrides.create_override",
    "erev_api.domain.policies.overrides.submit_override",
)
OVERRIDES_DECLARED = {POS_012: 2, DLT: 3, POS_117: 3}
ESTIMATE_LIFECYCLE = (H["estimate_submit"], H["decide"], H["compute"])
# 04 §16.14 rev 1.241, a variable-consideration version: created when it is due, its
# CONSTRAINT record prepared on it, sent and reviewed, the record named on the version, its
# evidence uploaded and attached.
ESTIMATE_PREREQUISITES = (
    H["estimate_version"],
    H["judgement"],
    H["judgement_submit"],
    H["decide"],
    H["estimate_version_update"],
    H["estimate_evidence"],
    H["estimate_evidence_attach"],
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _adapter(loaded: LoadedKey, invoker: RecordingInvoker | None = None) -> WorkspaceAdapter:
    return WorkspaceAdapter(
        loaded,
        invoker=invoker or RecordingInvoker(),
        clock=_Clock(),
        fingerprint=lambda: "mock-fixture",
    )


def _run(loaded: LoadedKey) -> tuple[WorkspaceAdapter, RecordingInvoker]:
    invoker = RecordingInvoker()
    adapter = _adapter(loaded, invoker)
    for step in plan(loaded).steps:
        if step.phase in ("CHECKPOINT", "RUNNER") or step.gap is not None:
            continue
        adapter.run(step)  # no refusal is expected on the five keys any more
    return adapter, invoker


def _with_world(loaded: LoadedKey, **update: object) -> LoadedKey:
    """The key with world members added (rule sets / FX rate sets, which no platform key has)."""
    world = loaded.key.world.model_copy(update=update)
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"world": world}))


def _with_judgements(loaded: LoadedKey, *judgements: Judgement) -> LoadedKey:
    """The key with judgements on its first contract (no platform key carries one)."""
    first, *rest = loaded.key.contracts
    contracts = (first.model_copy(update={"judgements": tuple(judgements)}), *rest)
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"contracts": contracts}))


# --- FOLL-1 / FOLL-2: the plan -----------------------------------------------------------------


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_foll_1_contract_configuration_follows_its_booking(key_id: str) -> None:
    """Every CONTRACTS step the key declares sits after its contract's booking and before its
    activation; the detail names the booking seq; the count is the key's judgements and
    estimated elements — a key's policy overrides have no step (register index 308; until then
    three steps each). (Fail-first: every CONTRACTS step preceded the first booking.) A version
    of an element is no longer drafted there: at most one is open (04 T-CON-13 rev 1.241; PRD
    ERR-93), so each is created at its own ``ESTIMATE_CHANGED`` item. The other CONTRACTS steps
    are the runner's own, before an activation (DG-AK-41 layer 4;
    ``test_platform_activation_statements``) or before an estimate's submission
    (``test_platform_estimate_statements``): each carries exactly one of the three markers."""
    loaded = load_platform_key(key_id)
    steps = plan(loaded).steps
    expected = 0
    for contract in loaded.key.contracts:
        expected += 3 * len(contract.judgements or ())
        expected += 3 * len(contract.policy_overrides or ())
        expected += len(contract.estimates or ())
    contracts_phase = [
        (index, step) for index, step in enumerate(steps) if step.phase == "CONTRACTS"
    ]
    configuration = [
        (index, step) for index, step in contracts_phase if "after_booking" in step.detail
    ]
    assert len(configuration) == expected
    markers = ("after_booking", "before_activation", ESTIMATE_MARKER)
    assert all(sum(marker in step.detail for marker in markers) == 1 for _, step in contracts_phase)
    first_booking = next(index for index, step in enumerate(steps) if step.handler == H["book"])
    for index, step in configuration:
        contract = step.subject.removeprefix("contract ")
        booking = next(
            i
            for i, s in enumerate(steps)
            if s.handler == H["book"] and s.subject.split(" ")[2] == contract
        )
        activation = next(
            (
                i
                for i, s in enumerate(steps)
                if s.handler == H["submit_activation"] and s.subject.split(" ")[2] == contract
            ),
            len(steps),
        )
        assert first_booking <= booking < index < activation, (key_id, step)
        assert step.detail["after_booking"] == str(steps[booking].seq)
        # the element only: its versions and their submission are the item's
        assert step.handler not in (H["estimate_version"], H["estimate_submit"])


def test_foll_2_estimate_change_is_submit_then_decide_then_compute() -> None:
    ex42 = load_platform_key(EX42)
    command_plan = plan(ex42)
    seven = [s for s in command_plan.steps if s.seq == 7 and s.phase == "TIMELINE"]
    assert [s.handler for s in seven] == list(ESTIMATE_LIFECYCLE)
    assert [s.actor for s in seven] == [PREPARER, APPROVER, SYSTEM]
    submit, decide, _ = seven
    assert submit.detail["element"] == "BONUS-C" and submit.detail["version_no"] == "1"
    assert decide.detail["emits"] == "ESTIMATE_CHANGED" and decide.detail["contract"] == "C-EX42-C"
    assert [s.captures_known_at for s in seven] == [False, True, False]
    assert command_plan.known_at_captures.count(7) == 1


def test_foll_2_route_executes_on_the_mock_platform_and_advances_the_stream() -> None:
    ex42 = load_platform_key(EX42)
    invoker = RecordingInvoker()
    adapter = _adapter(ex42, invoker)
    result = run_platform(ex42, DbPlatform(ex42, adapter))
    executed = [item for item in result.executed if item.step.seq == 7]
    # 04 §16.14 rev 1.241: the runner's seven steps before the submission, then the route
    assert [(item.step.handler, item.status) for item in executed] == [
        (handler, EXECUTED) for handler in (*ESTIMATE_PREREQUISITES, *ESTIMATE_LIFECYCLE)
    ]
    assert 7 in result.known_at
    calls = [c for c in invoker.calls if c.step.seq == 7 and c.step.phase == "TIMELINE"]
    assert [c.handler for c in calls] == list(ESTIMATE_LIFECYCLE)
    assert calls[1].kwargs["emits"] == "ESTIMATE_CHANGED" and calls[1].kwargs["contract"] == (
        "C-EX42-C"
    )
    # booking 1, the runner's Step 1 assessment 2 (layer 4), the approved activation 3, the
    # approved change 4
    assert adapter.stream["C-EX42-C"] == 4
    assert not any(c.handler == H["record_events"] and c.step.seq == 7 for c in invoker.calls)
    resolver = MockResolver(EX42)
    (converted,) = adapt(calls[0], ex42.key, resolver)
    bind_check(calls[0], [converted])
    assert converted["version_id"] == resolver.estimate_version_id("C-EX42-C", "BONUS-C", 1)
    assert isinstance(converted["body"], EstimateVersionSubmitIn)
    # A version the key does not declare is refused by name before any call.
    wrong = dataclasses.replace(calls[0].step, detail={**calls[0].step.detail, "version_no": "9"})
    with pytest.raises(NotProvisioned, match="no version 9"):
        adapter.plan_call(wrong)


# --- overrides ---------------------------------------------------------------------------------


@pytest.mark.parametrize("key_id", [POS_012, DLT, POS_117])
def test_declared_overrides_are_created_submitted_and_approved(key_id: str) -> None:
    loaded = load_platform_key(key_id)
    declared = [o for c in loaded.key.contracts for o in c.policy_overrides or ()]
    assert len(declared) == OVERRIDES_DECLARED[key_id]
    _, invoker = _run(loaded)
    created = [c for c in invoker.calls if c.handler == H["override"]]
    submitted = [c for c in invoker.calls if c.handler == H["override_submit"]]
    assert len(created) == len(submitted) == len(declared)
    resolver = MockResolver(key_id)
    for call, override in zip(created, declared, strict=True):
        (arguments,) = adapt(call, loaded.key, resolver)
        assert arguments["contract_id"] == resolver.contract_id(call.kwargs["contract"])
        assert arguments["policy_key"] == override.policy_key
        assert arguments["value"] == override.value
        assert arguments["rationale"] == override.rationale
        assert arguments["obligation_key"] == override.obligation_key
    for call in submitted:
        (arguments,) = adapt(call, loaded.key, resolver)
        assert arguments["override_id"] == resolver.override_id(
            call.kwargs["contract"], call.kwargs["policy_key"], call.kwargs["obligation_key"]
        )
        assert arguments["comment"] is None


# --- estimates ---------------------------------------------------------------------------------


def test_estimates_convert_with_the_keys_amounts_and_bind() -> None:
    ex42 = load_platform_key(EX42)
    _, invoker = _run(ex42)
    resolver = MockResolver(EX42)
    contract = next(c for c in ex42.key.contracts if c.external_id == "C-EX42-C")
    assert contract.estimates is not None
    bonus = contract.estimates[0]
    create = next(c for c in invoker.calls if c.handler == H["estimate"])
    assert create.step.phase == "CONTRACTS"
    (kwargs,) = adapt(create, ex42.key, resolver)
    bind_check(create, [kwargs])
    body = kwargs["body"]
    assert isinstance(body, EstimateCreateIn)
    assert body.estimate_kind is EstimateKind.VARIABLE_CONSIDERATION
    assert body.element_code == "BONUS-C" and body.vc_element_type == "BONUS"
    assert body.method is EstimateMethod.EXPECTED_VALUE and body.direction == "INCREASE"
    assert body.allocation_target == "CONTRACT" and body.target_obligation_keys == []
    assert kwargs["contract_id"] == resolver.contract_id("C-EX42-C")
    version = next(c for c in invoker.calls if c.handler == H["estimate_version"])
    # created when it is due — at the item that submits it, not at the booking (PRD ERR-93)
    assert (version.step.phase, version.step.seq) == ("CONTRACTS", 7)
    (kwargs,) = adapt(version, ex42.key, resolver)
    bind_check(version, [kwargs])
    vbody = kwargs["body"]
    assert isinstance(vbody, EstimateVersionCreateIn)
    assert (
        vbody.effective_date,
        vbody.unconstrained_amount,
        vbody.most_conservative_amount,
        vbody.constrained_amount,
    ) == (date(2026, 7, 1), "1000.00", "0.00", "750.00")
    assert vbody.method is None and vbody.currency is None
    assert vbody.rationale == bonus.versions[0].rationale
    assert vbody.scenarios == [] and vbody.parameters == {}
    assert kwargs["estimate_id"] == resolver.estimate_id("C-EX42-C", "BONUS-C")
    # a variable-consideration version names the CONSTRAINT record of its element (ERR-94):
    # the runner's record is a record OF the version, so the version is created without it
    # and names it once it is reviewed
    assert vbody.judgement_record_id is None
    named = next(c for c in invoker.calls if c.handler == H["estimate_version_update"])
    (edit,) = adapt(named, ex42.key, resolver)
    bind_check(named, [edit])
    assert edit["version_id"] == resolver.estimate_version_id("C-EX42-C", "BONUS-C", 1)
    assert edit["body"].model_fields_set == {"judgement_record_id"}
    assert edit["body"].judgement_record_id == resolver.judgement_id(
        "C-EX42-C", constraint_handle("BONUS-C", 1)
    )
    submits = [c for c in invoker.calls if c.handler == H["estimate_submit"]]
    assert [(c.step.phase, c.step.seq) for c in submits] == [("TIMELINE", 7)]
    with pytest.raises(NotProvisioned, match="no version 2"):
        adapt(
            Call(
                H["estimate_version"], PREPARER, {**version.kwargs, "version_no": 2}, version.step
            ),
            ex42.key,
            resolver,
        )
    with pytest.raises(NotProvisioned, match="not in the key"):
        adapt(
            Call(H["estimate"], PREPARER, {**create.kwargs, "element_code": "NOPE"}, create.step),
            ex42.key,
            resolver,
        )


# --- judgements (FOLL-3: rationale) --------------------------------------------------------------


def test_judgements_refuse_the_missing_rationale_and_convert_with_it() -> None:
    """FOLL-3 / Q-11 (D-98 54): without the optional ``rationale`` the judgement is refused by
    name; with it (dev-guide rev 1.26) the request converts from the key's values and binds."""
    base = load_platform_key(POS_012)
    resolver = MockResolver(POS_012)
    judgement = Judgement(
        handle="J1",
        topic="COLLECTIBILITY",
        subject_obligation_key="X1-LICENCE",
        conclusion="Collectible: the customer pays on delivery.",
    )
    step = Step(
        "CONTRACTS",
        PREPARER,
        H["judgement"],
        "contract C-POS-012-X",
        {"topic": "COLLECTIBILITY", "handle": "J1"},
    )
    kwargs = {
        "contract": "C-POS-012-X",
        "handle": "J1",
        "topic": "COLLECTIBILITY",
        "subject_obligation_key": "X1-LICENCE",
        "book_code": None,
        "conclusion": judgement.conclusion,
        "questionnaire": {},
    }
    call = Call(H["judgement"], PREPARER, kwargs, step)
    without = _with_judgements(base, judgement)
    with pytest.raises(NotProvisioned, match="rationale") as refused:
        adapt(call, without.key, resolver)
    assert "Q-11" in str(refused.value)
    with pytest.raises(NotProvisioned, match="not in the key"):
        adapt(call, base.key, resolver)  # the key carries no judgement J1 at all
    contract_id = resolver.contract_id("C-POS-012-X")
    with pytest.raises(NotProvisioned, match="rationale"):
        judgement_request(judgement, contract_id, contract_id)  # neither the key nor the caller
    request = judgement_request(
        judgement,
        contract_id,
        resolver.obligation_id("C-POS-012-X", "X1-LICENCE"),
        rationale="Payment history and credit review.",
    )
    assert isinstance(request, JudgementCreateIn)
    assert request.topic is JudgementTopic.COLLECTIBILITY
    assert request.subject_type == "obligation" and request.book is None
    assert request.conclusion == judgement.conclusion and request.contract_id == contract_id
    bind_check(call, [{"body": request}])
    # With the optional member (rev 1.26) adapt converts the key's own values.
    with_rationale = _with_judgements(
        base, judgement.model_copy(update={"rationale": "Payment history and credit review."})
    )
    (converted,) = adapt(call, with_rationale.key, resolver)
    bind_check(call, [converted])
    body = converted["body"]
    assert isinstance(body, JudgementCreateIn)
    assert body.rationale == "Payment history and credit review."
    assert body.subject_id == resolver.obligation_id("C-POS-012-X", "X1-LICENCE")
    assert body.contract_id == contract_id
    book = base.key.books[0]
    on_contract = judgement_request(
        Judgement(
            handle="J2", topic="CONTRACT_TERM", book_code=book, conclusion="Term ends at notice."
        ),
        contract_id,
        contract_id,
        rationale="r",
    )
    assert on_contract.subject_type == "contract" and on_contract.book is BookCode(book)
    submit = Call(
        H["judgement_submit"],
        PREPARER,
        kwargs,
        dataclasses.replace(step, handler=H["judgement_submit"]),
    )
    (submitted,) = adapt(submit, without.key, resolver)
    bind_check(submit, [submitted])
    assert submitted["judgement_id"] == resolver.judgement_id("C-POS-012-X", "J1")
    assert isinstance(submitted["body"], JudgementSubmitIn)


# --- rule sets (FOLL-3: TESTED) -----------------------------------------------------------------


def test_rule_sets_convert_and_the_submit_refuses_an_untested_version() -> None:
    rule = Rule(
        rule_key="emea-licence",
        priority=10,
        conditions=[{"field": "contract.region", "op": "eq", "value": "EMEA"}],
        outputs={"pob_template_code": "TPL-1"},
    )
    rule_set = RuleSet(code="RS-POB", kind="POB_ASSIGNMENT", rules=(rule,))
    loaded = _with_world(load_platform_key(POS_012), rule_sets=(rule_set,))
    adapter = _adapter(loaded)
    subject = "rule_set RS-POB"
    names = ("rule_set", "rule_set_version", "rule", "rule_set_submit", "rule_set_publish")
    calls = [
        adapter.plan_call(Step("WORLD", PREPARER, H[name], subject, {"kind": "POB_ASSIGNMENT"}))
        for name in names
    ]
    create, version, upsert, submit, publish = calls
    assert all(call is not None for call in calls)
    assert create is not None and version is not None and upsert is not None
    assert submit is not None and publish is not None
    resolver = MockResolver(POS_012)
    (kw,) = adapt(create, loaded.key, resolver)
    bind_check(create, [kw])
    assert kw["kind"] is RuleSetKind.POB_ASSIGNMENT and kw["code"] == "RS-POB"
    with pytest.raises(TypeError, match="RuleSetKind"):  # CONV-1 holds here too
        bind_check(create, [{**kw, "kind": "POB_ASSIGNMENT"}])
    (kw,) = adapt(version, loaded.key, resolver)
    bind_check(version, [kw])
    assert kw["rule_set_id"] == resolver.rule_set_id("RS-POB")
    (kw,) = adapt(upsert, loaded.key, resolver)
    bind_check(upsert, [kw])
    assert kw == {
        "version_id": resolver.rule_set_version_id("RS-POB"),
        "rule_key": "emea-licence",
        "priority": 10,
        "conditions": [{"field": "contract.region", "op": "eq", "value": "EMEA"}],
        "outputs": {"pob_template_code": "TPL-1"},
        "description": None,
    }
    with pytest.raises(NotProvisioned, match="TESTED") as refused:
        adapt(submit, loaded.key, resolver)
    assert "Q-11" in str(refused.value)
    (kw,) = adapt(publish, loaded.key, resolver)
    bind_check(publish, [kw])
    assert kw == {"version_id": resolver.rule_set_version_id("RS-POB")}
    # With the optional example_cases (rev 1.26) the plan tests the version before the submission
    # and the submit converts.
    case = RuleExampleCase(
        name="emea licence",
        input={"contract.region": "EMEA"},
        expected_output={"matched": True, "rule_key": "emea-licence"},
    )
    tested = _with_world(
        load_platform_key(POS_012),
        rule_sets=(rule_set.model_copy(update={"example_cases": (case,)}),),
    )
    handlers = [s.handler for s in plan(tested).steps if s.subject == subject]
    assert handlers[:6] == [
        H["rule_set"],
        H["rule_set_version"],
        H["rule"],
        H["rule_case"],
        H["rule_tests"],
        H["rule_set_submit"],
    ]
    tested_adapter = _adapter(tested)
    case_call = tested_adapter.plan_call(Step("WORLD", PREPARER, H["rule_case"], subject, {}))
    tests_call = tested_adapter.plan_call(Step("WORLD", PREPARER, H["rule_tests"], subject, {}))
    submit_call = tested_adapter.plan_call(
        Step("WORLD", PREPARER, H["rule_set_submit"], subject, {})
    )
    assert case_call is not None and tests_call is not None and submit_call is not None
    assert (
        case_call.kwargs["case_index"] == 0 and case_call.kwargs["case"]["name"] == "emea licence"
    )
    (kw,) = adapt(case_call, tested.key, resolver)
    bind_check(case_call, [kw])
    assert kw == {
        "subject_type": "rule_set_version",
        "subject_id": resolver.rule_set_version_id("RS-POB"),
        "name": "emea licence",
        "facts": {"contract.region": "EMEA"},
        "expected_output": {"matched": True, "rule_key": "emea-licence"},
    }
    (kw,) = adapt(tests_call, tested.key, resolver)
    bind_check(tests_call, [kw])
    assert kw == {"version_id": resolver.rule_set_version_id("RS-POB")}
    (kw,) = adapt(submit_call, tested.key, resolver)
    bind_check(submit_call, [kw])
    assert kw == {"version_id": resolver.rule_set_version_id("RS-POB"), "comment": None}
    with pytest.raises(NotProvisioned, match="mappings"):
        example_case_kwargs(
            RuleExampleCase(name="bad", input="x", expected_output={}),
            resolver.rule_set_version_id("RS-POB"),
        )
    with pytest.raises(NotProvisioned, match="sequence of mappings"):
        rule_kwargs(Rule(rule_key="bad", priority=1, conditions="x", outputs={}))
    with pytest.raises(NotProvisioned, match="not a mapping"):
        rule_kwargs(Rule(rule_key="bad", priority=1, conditions=[], outputs="x"))
    with pytest.raises(NotProvisioned, match="not in the key"):
        _adapter(load_platform_key(POS_012)).plan_call(
            Step("WORLD", PREPARER, H["rule_set"], subject, {})
        )


# --- FX rate sets (FOLL-3: name; FOLL-4: coverage) --------------------------------------------


def test_fx_rate_sets_refuse_the_missing_name_and_convert_the_version() -> None:
    rates = (
        FxRate(base_currency="EUR", quote_currency="USD", effective_date="2026-02-15", rate="1.2"),
        FxRate(base_currency="EUR", quote_currency="USD", effective_date="2026-01-15", rate="1.1"),
    )
    rate_set = FxRateSet(code="FX-SPOT", rate_type="spot", rates=rates)
    loaded = _with_world(load_platform_key(POS_012), fx_rate_sets=(rate_set,))
    adapter = _adapter(loaded)
    subject = "fx_rate_set FX-SPOT"
    detail = {"rates": "2", "rate_type": "spot"}
    calls = [
        adapter.plan_call(Step("WORLD", PREPARER, H[name], subject, detail))
        for name in ("fx_set", "fx_version", "fx_submit")
    ]
    create, version, submit = calls
    assert create is not None and version is not None and submit is not None
    assert create.kwargs["code"] == "FX-SPOT" and len(create.kwargs["rates"]) == 2
    resolver = MockResolver(POS_012)
    with pytest.raises(NotProvisioned, match="name") as refused:
        adapt(create, loaded.key, resolver)
    assert "Q-11" in str(refused.value)
    request = fx_rate_set_request(rate_set, name="EUR/USD spot")
    assert isinstance(request, FxRateSetIn)
    assert request.rate_type is RateType.SPOT and request.source == "MANUAL"
    bind_check(create, [{"body": request}])
    with pytest.raises(NotProvisioned, match="name"):
        fx_rate_set_request(rate_set)  # neither the key nor the caller names it
    # With the optional member (rev 1.26) adapt converts the key's own value.
    named = _with_world(
        load_platform_key(POS_012),
        fx_rate_sets=(rate_set.model_copy(update={"name": "EUR/USD spot"}),),
    )
    named_call = _adapter(named).plan_call(Step("WORLD", PREPARER, H["fx_set"], subject, detail))
    assert named_call is not None
    (kw,) = adapt(named_call, named.key, resolver)
    bind_check(named_call, [kw])
    assert isinstance(kw["body"], FxRateSetIn) and kw["body"].name == "EUR/USD spot"
    (kw,) = adapt(version, loaded.key, resolver)
    bind_check(version, [kw])
    body = kw["body"]
    assert isinstance(body, FxRateSetVersionIn)
    assert (body.coverage_from, body.coverage_to) == (date(2026, 1, 15), date(2026, 2, 15))
    assert [rate.rate for rate in body.rates] == ["1.2", "1.1"]
    assert kw["set_id"] == resolver.fx_set_id("FX-SPOT")
    (kw,) = adapt(submit, loaded.key, resolver)
    bind_check(submit, [kw])
    assert kw["version_id"] == resolver.fx_version_id("FX-SPOT") and callable(kw["check_version"])
    with pytest.raises(NotProvisioned, match="no rates"):
        fx_version_request(FxRateSet(code="FX-EMPTY", rate_type="spot", rates=()))


# --- the gaps, named ---------------------------------------------------------------------------


def test_schema_gaps_are_three_named_values_that_no_platform_key_hits() -> None:
    """No key states a judgement, an FX rate set or a rule set, so no key meets a gap. The one
    gap handler the plans do call is ``create_judgement`` — for the runner's own records, each
    of which states its rationale and converts: the Step 1 record of a contract (DG-AK-41
    layer 4) and, in EX42, the CONSTRAINT record of the one estimate version a platform key
    submits (04 §16.14 rev 1.241)."""
    assert set(SCHEMA_GAPS) == {H["judgement"], H["fx_set"], H["rule_set_submit"]}
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        _, invoker = _run(loaded)
        resolver = MockResolver(key_id)
        named = [c for c in invoker.calls if c.handler in SCHEMA_GAPS]
        assert {c.handler for c in named} == {H["judgement"]}
        own = {STEP1_HANDLE: STEP1_RATIONALE}
        if key_id == EX42:
            own[constraint_handle("BONUS-C", 1)] = CONSTRAINT_RATIONALE
        assert {c.kwargs["handle"] for c in named} == set(own)
        for call in named:
            (converted,) = adapt(call, loaded.key, resolver)
            assert converted["body"].rationale == own[call.kwargs["handle"]]
        assert not loaded.key.world.rule_sets and not loaded.key.world.fx_rate_sets
        assert not any(c.judgements for c in loaded.key.contracts)

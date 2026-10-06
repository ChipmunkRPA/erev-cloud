"""Request-model conversion of the WorkspaceAdapter (record §14.2 "following slices (1)").

No database: the key's payloads and bodies are converted and validated with the API's own pydantic
models, and every converted call is bound to its domain handler's real signature. The five
platform keys are the population; the raw (unconverted) shapes are the fail-first evidence
(`.run/f-rps-e1/fail-first-request-models-raw.log`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pydantic
import pytest
from erev_api.enums import ContractEventType, RegistryCategory, RegistryScope
from erev_api.events.payloads import LATEST_SCHEMA_VERSION, PAYLOADS, ContractBookedV1
from erev_api.registry.presets import PRESET_CATEGORY, legacy_parity_values
from erev_api.registry.versions import validation_problem
from support.answer_keys.models import EventItem
from support.answer_keys.platform_plan import (
    DISTINCT_BOUND,
    PLATFORM_KEY_IDS,
    H,
    load_platform_key,
    plan,
    plan_templates,
    preset_overlay,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import (
    SCHEMA_GAPS,
    MockResolver,
    _period_keys,
    adapt,
    bind_check,
    booking_request,
    convert_payload,
    event_append,
    policy_groups,
    schema_value,
    ssp_study,
)
from support.answer_keys.workspace_adapter import RecordingInvoker, WorkspaceAdapter, booking_body

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
_ACTIVATION = {"CONTRACT_BOOKED", "CONTRACT_ACTIVATED"}


def _raw_invalid(key_id: str) -> int:
    """How many raw key bodies and payloads the API models refuse (the fail-first shape)."""
    loaded = load_platform_key(key_id)
    invalid = 0
    for contract in loaded.key.contracts:
        try:
            ContractBookedV1.model_validate(booking_body(contract))
        except pydantic.ValidationError:
            invalid += 1
    for item in loaded.key.timeline:
        if isinstance(item, EventItem) and item.event_type != "CONTRACT_BOOKED":
            try:
                kind = ContractEventType(item.event_type)
                PAYLOADS[(kind, LATEST_SCHEMA_VERSION[kind])].model_validate(dict(item.payload))
            except pydantic.ValidationError:
                invalid += 1
    return invalid


def test_raw_key_shapes_are_not_api_shapes() -> None:
    """The fail-first fact: money strings, empty activation payloads and estimate handles make the
    raw shapes invalid for the API models (38 refusals over the five keys at ca2e82c)."""
    assert sum(_raw_invalid(key_id) for key_id in PLATFORM_KEY_IDS) == 38


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_converted_bookings_and_payloads_validate(key_id: str) -> None:
    loaded = load_platform_key(key_id)
    resolver = MockResolver(key_id)
    for contract in loaded.key.contracts:
        booked = booking_request(contract, loaded.key.world, resolver)
        assert booked.external_id == contract.external_id
        assert booked.customer is not None and booked.customer.code == contract.customer
        assert all(
            line.total_price.currency == contract.transaction_currency for line in booked.lines
        )
    contracts = {contract.external_id: contract for contract in loaded.key.contracts}
    for item in loaded.key.timeline:
        if not isinstance(item, EventItem) or item.event_type in _ACTIVATION:
            continue
        contract = contracts[item.contract]
        payload = convert_payload(
            item.event_type,
            item.payload,
            currency=contract.transaction_currency,
            contract=contract.external_id,
            resolver=resolver,
        )
        kind = ContractEventType(item.event_type)
        assert type(payload) is PAYLOADS[(kind, LATEST_SCHEMA_VERSION[kind])]
        if item.event_type == "ESTIMATE_CHANGED":  # CONV-2: never appended through record_events
            with pytest.raises(ValueError, match="lifecycle"):
                event_append(item, contract, resolver)
            continue
        appended = event_append(item, contract, resolver)
        assert appended.events[0].event_type.value == item.event_type
        assert appended.events[0].effective_date is not None


def test_money_and_handles_convert() -> None:
    resolver = MockResolver(EX42)
    loaded = load_platform_key(EX42)
    usage = next(item for item in loaded.key.timeline if item.event_type == "USAGE_REPORTED")
    payload = convert_payload(
        "USAGE_REPORTED", usage.payload, currency="USD", contract="C", resolver=resolver
    )
    assert payload.rated_amount is not None and payload.rated_amount.currency == "USD"  # type: ignore[attr-defined]
    assert str(payload.rated_amount.amount) == str(usage.payload["rated_amount"])  # type: ignore[attr-defined]
    estimate = next(item for item in loaded.key.timeline if item.event_type == "ESTIMATE_CHANGED")
    converted = convert_payload(
        "ESTIMATE_CHANGED",
        estimate.payload,
        currency="USD",
        contract=estimate.contract,
        resolver=resolver,
    )
    assert converted.estimate_version_id == resolver.estimate_version_id(  # type: ignore[attr-defined]
        estimate.contract,
        str(estimate.payload["estimate"]),
        int(estimate.payload.get("version_no", 1)),
    )
    assert converted.previous_estimate_version_id is None  # type: ignore[attr-defined]
    billing = {
        "invoice_number": "INV-1",
        "line_external_id": "L1",
        "amount": "100.00",
        "issue_date": "2026-01-01",
    }
    money = convert_payload(
        "BILLING_RECORDED", billing, currency="EUR", contract="C", resolver=resolver
    )
    assert money.amount.currency == "EUR" and str(money.amount.amount) == "100.00"  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="booked or activated"):
        event_append(
            next(item for item in loaded.key.timeline if item.event_type == "CONTRACT_ACTIVATED"),
            loaded.key.contracts[0],
            resolver,
        )


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_every_call_binds_to_its_handler(key_id: str) -> None:
    """Every call the WorkspaceAdapter derives converts to keyword sets that bind to the real
    handler signature — overrides, estimates, the estimate lifecycle route (record §18) and the
    runner's own statements before an activation (DG-AK-41 layer 4) included. The calls that do
    not convert are the reviews of GT07's three nondistinct obligations: the bound of layer 4
    refuses them by name."""
    loaded = load_platform_key(key_id)
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded,
        invoker=invoker,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=len(invoker.calls)),
        fingerprint=lambda: "mock-fixture",  # an explicit, named mock fixture (WSA-2)
    )
    from support.answer_keys.platform_plan import plan

    for step in plan(loaded).steps:
        if step.phase in ("CHECKPOINT", "RUNNER") or step.gap is not None:
            continue
        try:
            adapter.run(step)
        except NotProvisioned:  # gaps of the in-memory plan (none expected on the five keys)
            continue
    resolver = MockResolver(key_id)
    bound = 0
    beyond: list[tuple[str, str]] = []
    for call in invoker.calls:
        if call.handler == H["distinct_review"] and call.kwargs["distinctness"] != "distinct":
            with pytest.raises(NotProvisioned) as refused:
                adapt(call, loaded.key, resolver)
            assert DISTINCT_BOUND in str(refused.value)
            beyond.append((call.kwargs["contract"], call.kwargs["obligation_key"]))
            continue
        kwargs_list = adapt(call, loaded.key, resolver)
        assert kwargs_list, call.handler
        bind_check(call, kwargs_list)
        bound += 1
    assert bound + len(beyond) == len(invoker.calls) and bound > 20
    assert beyond == (
        [("CONTRACT-1", "POB #3"), ("CONTRACT-2", "POB #3"), ("CONTRACT-2", "VC #1")]
        if key_id == DLT
        else []
    )
    # Stream heads follow successful calls (WSA-1): booking 1, the runner's Step 1 assessment —
    # one event per enabled book of the contracting entity, no key states Step 1 itself (layer
    # 4) —, the approved activation, then one per recorded event, the approved estimate change
    # included (FOLL-2); the converted expected version equals the call's.
    books = {entity.code: len(entity.books) for entity in loaded.key.world.entities}
    for contract in loaded.key.contracts:
        appended = sum(
            1
            for item in loaded.key.timeline
            if isinstance(item, EventItem)
            and item.contract == contract.external_id
            and item.event_type != "CONTRACT_BOOKED"
        )
        assessed = books[contract.contracting_entity]
        assert adapter.stream[contract.external_id] == 1 + assessed + appended
    for call in invoker.calls:
        if call.handler == H["record_events"]:
            (converted,) = adapt(call, loaded.key, resolver)
            assert converted["expected_stream_version"] == call.kwargs["expected_stream_version"]


def test_period_keys_and_policy_groups_and_resolver() -> None:
    loaded = load_platform_key(POS_012)
    assert _period_keys(loaded.key.world, loaded.key.world.entities[0]) == [
        "FY2026-P01",
        "FY2026-P02",
    ]
    dlt = load_platform_key(DLT)
    groups = policy_groups(dlt.key.world.policies.tenant)
    assert {code for values in groups.values() for code in values} == {
        "billing.posting",
        "je.posting_mode",
    }
    with pytest.raises(ValueError, match="not in the registry"):
        policy_groups({"not.a.policy": "X"})
    resolver = MockResolver(POS_012)
    assert resolver.customer_id("CUST-1") == MockResolver(POS_012).customer_id("CUST-1")
    assert resolver.customer_id("CUST-1") != resolver.product_id("CUST-1")
    assert isinstance(resolver.pending_approval_id(), UUID)
    assert set(SCHEMA_GAPS) == {H["judgement"], H["fx_set"], H["rule_set_submit"]}


# --- provisioning request: the kernel's own tenant rules (returned item, main 0cb36c14) ----------


def test_tenant_code_is_a_deterministic_kernel_valid_slug() -> None:
    """DG-KRN-TEN-03 [J]: 3 to 40 lowercase letters, digits and single hyphens. A short id stays
    readable; a long id is capped with a digest suffix so two ids sharing a prefix stay distinct;
    no code ends in a hyphen."""
    from erev_api.domain.platform.provisioning import TENANT_CODE, TENANT_CODE_LENGTH
    from support.answer_keys.platform_plan import tenant_code

    assert tenant_code("POS-CHK-012") == "ak-pos-chk-012"
    long_a = "DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS"
    long_b = "DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-REVERSALS"
    for key_id in (long_a, long_b, "A" * 37, "A" * 38, "B-" * 30 + "B"):
        code = tenant_code(key_id)
        assert TENANT_CODE.fullmatch(code) and len(code) in TENANT_CODE_LENGTH, code
        assert code == tenant_code(key_id)
    assert tenant_code(long_a) != tenant_code(long_b)
    assert tenant_code(long_a).startswith("ak-dlt-chk-020-chk-022-gt07-")


def test_provision_requests_meet_the_kernels_tenant_rules_for_every_key() -> None:
    """Without a database: every key's provisioning request passes the kernel's own
    ``validation_errors`` (DG-KRN-TEN-03: code pattern and length, label, ISO 4217, email); the
    codes are distinct across the corpus and deterministic; the in-memory plan's provision step
    names the same code as the request the database platform sends."""
    from erev_api.domain.platform.provisioning import validation_errors
    from support.answer_keys.loader import load_all
    from support.answer_keys.platform_plan import plan
    from support.answer_keys.request_models import provision_request
    from support.answer_keys.workspace_adapter import WorkspaceAdapter

    keys = [loaded.key for loaded in load_all(include_withdrawn=True)]
    assert len(keys) > 200
    failing = {
        key.id: [
            (error.field, error.rule_id) for error in validation_errors(provision_request(key))
        ]
        for key in keys
    }
    assert {key_id: errors for key_id, errors in failing.items() if errors} == {}
    codes = {key.id: provision_request(key).code for key in keys}
    assert len(set(codes.values())) == len(codes)
    assert codes == {key.id: provision_request(key).code for key in keys}
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        adapter = WorkspaceAdapter(
            loaded,
            invoker=RecordingInvoker(),
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            fingerprint=lambda: "mock-fixture",
        )
        step = next(step for step in plan(loaded).steps if step.handler == H["provision"])
        call = adapter.plan_call(step)
        assert call is not None and call.kwargs["code"] == codes[key_id]
        # Codex production-20260921-0216: the full key id stays in the tenant's display name, so a
        # digest-suffixed code still maps unambiguously to its key from the tenant row alone.
        request = provision_request(loaded.key)
        assert request.display_name.startswith(f"{key_id}: ")
        assert call.kwargs["display_name"] == request.display_name


# --- world order: a step's handles are committed by earlier steps (returned item, c9110467) ---


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_world_steps_resolve_only_handles_committed_by_earlier_steps(key_id: str) -> None:
    """On the database platform the invoker converts each call against the LIVE ledger (rule
    RES-1), so a WORLD step may name a customer, product, template, GL account or entity only
    after the step that creates it has committed. The in-memory plan runs here with a resolver
    that records every forward reference; the list must be empty."""
    from support.answer_keys.platform_plan import plan
    from support.answer_keys.request_models import MockResolver, adapt

    loaded = load_platform_key(key_id)
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded,
        invoker=invoker,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=len(invoker.calls)),
        fingerprint=lambda: "mock-fixture",
    )
    creates = {
        H["customer"]: "customer",
        H["product"]: "product",
        H["template"]: "template",
        H["gl_account"]: "gl_account",
        H["entity"]: "entity",
    }
    created: set[tuple[str, str]] = set()
    forward: list[tuple[str, str, str]] = []

    class Probe(MockResolver):
        def _check(self, kind: str, code: str, handler: str) -> None:
            if (kind, code) not in created:
                forward.append((handler.rsplit(".", 1)[-1], kind, code))

        def customer_id(self, code: str) -> UUID:
            self._check("customer", code, current[0])
            return super().customer_id(code)

        def product_id(self, code: str) -> UUID:
            self._check("product", code, current[0])
            return super().product_id(code)

        def template_id(self, code: str) -> UUID:
            self._check("template", code, current[0])
            return super().template_id(code)

        def gl_account_id(self, code: str) -> UUID:
            self._check("gl_account", code, current[0])
            return super().gl_account_id(code)

        def entity_id(self, code: str) -> UUID:
            self._check("entity", code, current[0])
            return super().entity_id(code)

    probe = Probe(key_id)
    current = [""]
    for step in plan(loaded).steps:
        if step.phase != "WORLD" or step.gap is not None:
            continue
        before = len(invoker.calls)
        adapter.run(step)
        for call in invoker.calls[before:]:
            current[0] = call.handler
            adapt(call, loaded.key, probe)
            kind = creates.get(call.handler)
            if kind is not None:
                # The created handle's code: the call's `code` keyword, else the step subject
                # (`entity US01`): the entity step carries its body under other keywords.
                code = call.kwargs.get("code")
                if not isinstance(code, str):
                    code = call.step.subject.removeprefix(f"{kind} ")
                created.add((kind, code))
    assert forward == [], forward


# --- DB-03: a configuration version is TESTED before it is submitted (batch #5 returned item) ---


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_configuration_lifecycles_reach_tested_before_submit(key_id: str) -> None:
    """`lifecycle.submit` refuses a version that is not TESTED (DB-03; REQ-POL-003): a template
    version is tested over at least one example case (`run_pob_template_version_tests`, 422 without
    cases), an account mapping over its rules (`run_account_mapping_tests`), a policy version by the
    POLICY_SIMULATION job `request_test` defers. The plan therefore places, for the same subject, a
    test step before every such submit — and a case step before a template test. A product's
    default template must name a PUBLISHED template, while a template case names an existing
    product: products are created first without a template, and bound to it after publication.
    The generated template cases have the case shape the kernel validates."""
    from erev_api.domain.policies.templates import case_errors
    from support.answer_keys.platform_plan import plan
    from support.answer_keys.request_models import MockResolver, adapt

    loaded = load_platform_key(key_id)
    steps = plan(loaded).steps
    tests_before = {
        H["template_submit"]: H["template_test"],
        H["mapping_submit"]: H["mapping_test"],
        H["policy_submit"]: H["policy_test"],
    }
    for index, step in enumerate(steps):
        needed = tests_before.get(step.handler)
        if needed is None:
            continue
        earlier = [s for s in steps[:index] if s.subject == step.subject]
        assert any(s.handler == needed for s in earlier), (key_id, step.subject, step.handler)
        if step.handler == H["template_submit"]:
            assert any(s.handler == H["template_case"] for s in earlier), (key_id, step.subject)
    # One walk of the plan (Codex 1211): products accumulate as they are created; a template's
    # case names a product created BEFORE it and precedes the template's test, which precedes its
    # submit; a product's default template follows its template's publication.
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded,
        invoker=invoker,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        fingerprint=lambda: "mock-fixture",
    )
    created: set[str] = set()
    cased: set[str] = set()
    tested: set[str] = set()
    published: set[str] = set()
    for step in steps:
        if step.phase != "WORLD":
            continue
        if step.handler == H["product"]:
            created.add(step.subject.removeprefix("product "))
        elif step.handler == H["template_case"] and step.subject.startswith("pob_template "):
            adapter.run(step)
            (kwargs,) = adapt(invoker.calls[-1], loaded.key, MockResolver(key_id))
            assert kwargs["subject_type"] == "pob_template_version"
            assert case_errors(kwargs["facts"], kwargs["expected_output"]) == []
            (line,) = kwargs["facts"]["lines"]
            assert line["product_code"] in created, (key_id, step.subject, line, sorted(created))
            cased.add(step.subject)
        elif step.handler == H["template_test"]:
            assert step.subject in cased, (key_id, step.subject)  # the case precedes the test
            tested.add(step.subject)
        elif step.handler == H["template_submit"]:
            assert step.subject in tested, (key_id, step.subject)  # the test precedes the submit
        elif step.handler == H["template_publish"]:
            published.add(step.subject.removeprefix("pob_template "))
        elif step.handler == H["product_template"]:
            assert step.detail["pob_template"] in published, (key_id, step.subject)
    # Every template the plan creates is cased: the key's own and, under the LEGACY_PARITY
    # preset, the four parity templates stage 03 assigns by line (DG-AK-41 rev 1.219).
    world = loaded.key.world
    assert cased == {f"pob_template {t.code}" for t in plan_templates(world)}
    own = [t.code for t in world.pob_templates]
    parity = ["LEGACY-DISTINCT", "LEGACY-MATERIAL-RIGHT", "LEGACY-NONDISTINCT", "LEGACY-VC"]
    assert [t.code for t in plan_templates(world)] == (own + parity if key_id == DLT else own)


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_policies_take_effect_at_the_first_period_start_the_world_is_set_up_before(
    key_id: str,
) -> None:
    """04 §16.5 / POLICIES §0.5 rule 3 (batch #6 keys-platform): every platform world's policy
    values are period-scoped, so their versions must take effect at the start of a period that has
    not started at submit; the plan therefore sets the world up before its first period starts in
    every entity zone and dates every policy version — scoped ones at creation, the LEGACY_PARITY
    preset through `update_policy` before its test — at that first period start."""
    from zoneinfo import ZoneInfo

    from erev_api.domain.policies.registry_versions import period_scoped
    from support.answer_keys.platform_plan import plan
    from support.answer_keys.request_models import MockResolver, adapt, policy_effective_from
    from support.answer_keys.runners import _Assembler

    loaded = load_platform_key(key_id)
    assembler = _Assembler(loaded)
    zones = [ZoneInfo(e.time_zone) for e in loaded.key.world.entities]
    start = assembler.world_start
    for zone in zones:
        assert assembler.setup_at.astimezone(zone).date() < start  # not started anywhere at setup
        assert (
            assembler.policy_effective_from.astimezone(zone).date() == start
        )  # a period start everywhere
    assert assembler.setup_at < assembler.times[assembler.timeline[0].seq]
    steps = plan(loaded).steps
    assert steps[1].clock_at == assembler.setup_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded,
        invoker=invoker,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        fingerprint=lambda: "mock-fixture",
    )
    dated = 0
    for step in steps:
        if step.phase != "WORLD":
            continue
        if step.handler == H["policy"]:
            adapter.run(step)
            for kwargs in adapt(invoker.calls[-1], loaded.key, MockResolver(key_id)):
                assert period_scoped(dict(kwargs["values"])), (key_id, step.subject)
                assert kwargs["effective_from"] == assembler.policy_effective_from
                dated += 1
        if step.handler == H["policy_effective"]:
            # The preset's version is ONE version of its category at tenant scope: the edit that
            # dates it also lays the key's tenant values of that category over the preset's, each
            # in its JSON type. As a second version they would name the first one's effective
            # date and be refused (04 DB-04), so the plan has no separate lifecycle for them.
            adapter.run(step)
            (kwargs,) = adapt(invoker.calls[-1], loaded.key, MockResolver(key_id))
            overlay = preset_overlay(loaded.key.world)
            preset = legacy_parity_values(scope=RegistryScope.TENANT, book_code=None)
            assert overlay == {"billing.posting": "ERP", "je.posting_mode": "DELTA"}
            assert kwargs["changes"] == {
                "effective_from": assembler.policy_effective_from,
                "values": {**preset, **policy_groups(overlay)[PRESET_CATEGORY]},
            }
            assert preset["je.posting_mode"] == "GROSS"  # the key's value wins over the preset's
            assert kwargs["changes"]["values"]["je.posting_mode"] == "DELTA"
            assert set(overlay) == set(loaded.key.world.policies.tenant)
            assert not [s for s in steps if s.subject == "policies TENANT tenant"]
            dated += 1
    preset_steps = [s.handler for s in steps if s.subject.startswith("preset ")]
    if loaded.key.world.tenant.preset == "LEGACY_PARITY":
        assert preset_steps.index(H["policy_effective"]) < preset_steps.index(H["policy_test"])
    else:  # under the DEFAULT preset no version takes an overlay: the tenant values stay their own
        assert preset_overlay(loaded.key.world) == {} and not preset_steps
    assert dated >= 1
    assert policy_effective_from({"effective_from": "2026-01-01T05:00:00Z"}) == datetime(
        2026, 1, 1, 5, tzinfo=UTC
    )


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_the_account_mapping_is_dated_at_creation_at_the_first_period_start(key_id: str) -> None:
    """`submit_account_mapping_version` refuses a TESTED version without `effective_from` (422
    `mapping.EFFECTIVE_REQUIRED`) and DB-04 freezes the date at submission, so the plan dates the
    mapping at creation — at the instant the world's policy versions take effect, the first period
    start in every entity zone (batch #9, POS-117 database witness: the mapping submit answered
    422 for a version created without a date)."""
    from support.answer_keys.platform_plan import plan
    from support.answer_keys.request_models import MockResolver, adapt, mapping_effective_from
    from support.answer_keys.runners import _Assembler

    loaded = load_platform_key(key_id)
    assembler = _Assembler(loaded)
    steps = plan(loaded).steps
    created = [step for step in steps if step.handler == H["mapping"]]
    assert len(created) == (1 if loaded.key.world.account_mapping else 0), key_id
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded,
        invoker=invoker,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        fingerprint=lambda: "mock-fixture",
    )
    for step in created:
        assert steps.index(step) < next(
            index for index, later in enumerate(steps) if later.handler == H["mapping_submit"]
        )
        adapter.run(step)
        (kwargs,) = adapt(invoker.calls[-1], loaded.key, MockResolver(key_id))
        assert kwargs["body"].effective_from == assembler.policy_effective_from, key_id
    with pytest.raises(NotProvisioned, match="account mapping: the plan step carries no"):
        mapping_effective_from({})


def test_a_policy_value_is_sent_in_the_type_its_parameter_declares() -> None:
    """EX42 states ``rpo.time_bands: ["12", "24"]``: a key carries numbers as strings and the
    loader hands sequences as tuples. The registry validates JSON — an array is a list, an integer
    an int — and refused the raw value on the database platform (422 "Values.rpo.time_bands must
    be of type array"). The conversion follows the parameter's own ``value_schema`` and touches
    nothing else: what the registry would refuse for another reason still reaches it."""
    tenant = load_platform_key(EX42).key.world.policies.tenant
    assert tuple(tenant["rpo.time_bands"]) == ("12", "24")  # the key, as it is written
    groups = policy_groups(tenant)
    assert set(groups) == {RegistryCategory.ACCOUNTING_POLICY}
    values = groups[RegistryCategory.ACCOUNTING_POLICY]
    assert values == {"billing.posting": "ERP", "rpo.time_bands": [12, 24]}
    assert [type(item) for item in values["rpo.time_bands"]] == [int, int]

    def problem(sent: dict[str, object]) -> object:
        return validation_problem(
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.TENANT,
            book_code=None,
            values=sent,
        )

    assert problem(values) is None
    refused = problem({**values, "rpo.time_bands": tenant["rpo.time_bands"]})
    assert refused is not None and [error.field for error in refused.errors] == [
        "values.rpo.time_bands"
    ]
    assert schema_value({"type": "integer"}, "12") == 12
    assert schema_value({"type": "integer"}, "-3") == -3
    assert schema_value({"type": "integer"}, "12.5") == "12.5"  # the registry refuses it
    assert schema_value({"type": "string"}, "12") == "12"
    assert schema_value({"type": "array", "items": {"type": "string"}}, ("A", "B")) == [
        "A",
        "B",
    ]
    assert schema_value({"type": "array"}, "not a sequence") == "not a sequence"


def test_the_study_of_an_ssp_version_is_the_runners_own_page() -> None:
    """REQ-SSP-008: a version is submitted with its study. A key carries prices, not the study
    behind them, so the runner attaches a page of its own — a PDF that names the version, the
    same bytes on every run and other bytes for another version (an upload of identical content
    and purpose answers the stored file) — and it reaches the upload and the link as the API
    takes them."""
    first, second = ssp_study("DE-LIST", 1), ssp_study("DE-LIST", 2)
    assert first == ssp_study("DE-LIST", 1) and first != second != ssp_study("US-LIST", 2)
    assert first.startswith(b"%PDF-1.7\n") and first.endswith(b"%%EOF\n")
    assert b"DE-LIST version 1" in first
    loaded = load_platform_key(DLT)
    adapter = WorkspaceAdapter(loaded, invoker=RecordingInvoker(), clock=lambda: None)
    resolver = MockResolver(DLT)
    book = loaded.key.world.ssp_books[0]
    steps = {
        step.handler: step
        for step in plan(loaded).steps
        if step.subject == f"ssp_book {book.code} version 1"
    }
    upload = adapter.plan_call(steps[H["ssp_study"]])
    assert upload is not None
    (sent,) = adapt(upload, loaded.key, resolver)
    assert (sent["purpose"], sent["media_type"]) == ("SSP_STUDY", "application/pdf")
    assert sent["original_filename"] == f"ssp-study-{book.code}-v1.pdf".lower()
    assert sent["stream"].read() == ssp_study(book.code, 1)
    attach = adapter.plan_call(steps[H["ssp_study_attach"]])
    assert attach is not None
    (linked,) = adapt(attach, loaded.key, resolver)
    assert linked == {
        "file_object_id": resolver.ssp_study_id(book.code, 1),
        "subject_type": "ssp_book_version",
        "subject_id": resolver.ssp_version_id(book.code, 1),
        "description": None,
    }
    bind_check(upload, [sent])
    bind_check(attach, [linked])

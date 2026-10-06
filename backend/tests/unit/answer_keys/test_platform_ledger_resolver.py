"""The database ``IdResolver`` over the ledger (record §17, rule RES-1): ids come from committed
results, never from the resolver; unknown or not-yet-written handles are refused by name;
deterministic for a given ledger. Mock-executed: a shaped fake invoker returns ``*Out``-like
results with deterministic ids, ``RecordingInvoker`` returns None (nothing resolvable).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.principal import Principal
from erev_api.enums import ApprovalSubjectType, PrincipalKind
from support.answer_keys.ledger_resolver import (
    RESULT_MEMBERS,
    SUBJECTS,
    SUBMIT_HANDLERS,
    LedgerResolver,
    UnresolvedHandle,
)
from support.answer_keys.platform_plan import (
    DISTINCT_BOUND,
    INVITED,
    OPERATOR,
    PLATFORM_KEY_IDS,
    PREPARER,
    PRESET_HANDLER,
    H,
    Step,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import (
    MockResolver,
    _period_keys,
    adapt,
    bind_check,
    policy_groups,
)
from support.answer_keys.workspace_adapter import (
    Call,
    LedgerEntry,
    RecordingInvoker,
    WorkspaceAdapter,
    real_invoker,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
AT = datetime(2026, 1, 1, tzinfo=UTC)
# DG-AK-41, the bound of layer 4: the obligations whose template concludes nondistinct. GT07 is
# the one key that has any; the runner states no review of them.
NONDISTINCT = {DLT: [("CONTRACT-1", "POB #3"), ("CONTRACT-2", "POB #3"), ("CONTRACT-2", "VC #1")]}


def _principal(name: str, roles: tuple[str, ...], tenant: UUID) -> Principal:
    """A fake persona whose permissions are what ``DEFAULT_ROLES`` grants its roles (ACT-2)."""
    from erev_api.auth.permissions import DEFAULT_ROLES

    granted = frozenset[str]().union(*(DEFAULT_ROLES.get(code, frozenset()) for code in roles))
    return Principal(
        kind=PrincipalKind.USER,
        id=uuid5(NAMESPACE_URL, f"erev://answer-keys/user/{name}"),
        tenant_id=tenant,
        membership_id=uuid5(NAMESPACE_URL, f"erev://answer-keys/membership/{name}"),
        display_name=name,
        roles=tuple(sorted(roles)),
        permissions=granted,
        permission_scopes={},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/tenant")
PERSONAS = {
    "ak-preparer": _principal("Ak Preparer", ("revenue_accountant",), TENANT),
    "ak-approver": _principal("Ak Approver", ("controller",), TENANT),  # D-98 107: no approver role
    "operator": _principal("Operator", ("tenant_admin",), TENANT),
    "ak-ssp-analyst": _principal("Ak Ssp Analyst", ("ssp_analyst",), TENANT),  # D-98 107a
    "ak-ssp-approver": _principal("Ak Ssp Approver", ("ssp_approver",), TENANT),
}


def _entry(call: Call, result: object) -> LedgerEntry:
    return LedgerEntry(call, call.actor, AT, AT, None, result)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class ShapedFake:
    """An invoker answering ``*Out``-shaped results with deterministic ids per (handler, key)."""

    def __init__(self, key_id: str, *, with_roles: bool = False) -> None:
        self.namespace = uuid5(NAMESPACE_URL, f"erev://fake-results/{key_id}")
        self.with_roles = with_roles
        self.calls: list[Call] = []
        self.loaded = load_platform_key(key_id)
        self.produced: set[UUID] = set()

    def uid(self, *parts: object) -> UUID:
        value = uuid5(self.namespace, "/".join(str(part) for part in parts))
        self.produced.add(value)
        return value

    def __call__(self, call: Call) -> object:
        self.calls.append(call)
        kw = call.kwargs
        handler = call.handler
        if handler == H["provision"]:
            roles = {
                code: self.uid("role", code)
                for code in (
                    "revenue_accountant",
                    "controller",
                    "tenant_admin",
                    "ssp_analyst",
                    "ssp_approver",
                )
            }
            return SimpleNamespace(
                tenant={"id": self.uid("tenant")},
                admin_membership_id=self.uid("admin"),
                roles=roles if self.with_roles else None,
            )
        if handler == H["invite"]:
            return self.uid("membership", kw["display_name"])
        if handler in (
            H["customer"],
            H["product"],
            H["gl_account"],
            H["calendar"],
            H["entity"],
            H["judgement"],
            H["fx_set"],
            H["fx_version"],
        ):
            key = kw.get("code") or kw.get("entity_code") or kw.get("handle")
            return SimpleNamespace(id=self.uid(handler, key))
        if handler == H["estimate"]:
            return SimpleNamespace(id=self.uid(handler, kw["contract"], kw["element_code"]))
        if handler in (H["rule_set"], H["rule_set_version"]):
            return self.uid(handler, kw["code"])
        if handler == H["entity_book"]:
            entity = next(e for e in self.loaded.key.world.entities if e.code == kw["entity_code"])
            states = {
                period: self.uid("period_state", kw["entity_code"], kw["book"], period)
                for period in _period_keys(self.loaded.key.world, entity)
            }
            return {
                "id": self.uid("entity_book", kw["entity_code"], kw["book"]),
                "period_states": states,
            }
        if handler in (
            H["template"],
            H["template_version"],
            H["mapping"],
            H["ssp_book"],
            H["ssp_version"],
            H["ssp_study"],  # the stored file of a version's study
            H["estimate_version"],
            PRESET_HANDLER,
        ):
            return self.uid(
                handler,
                *(
                    str(kw.get(name, ""))
                    for name in (
                        "code",
                        "contract",
                        "element_code",
                        "version_no",
                        "version",
                        "preset",
                    )
                ),
            )
        if handler == H["policy"]:
            return [
                self.uid("policy", kw["scope"], kw["scope_code"], category.value)
                for category in policy_groups(kw["values"])
            ]
        if handler == H["book"]:
            booked = next(c for c in self.loaded.key.contracts if c.external_id == kw["contract"])
            return SimpleNamespace(
                contract={"id": self.uid("contract", kw["contract"])},
                combination_group={
                    "id": self.uid("group", kw["contract"]),
                    # The kernel generates CG-<contract_no>: a stored value no code can derive
                    # from the external id (Codex 1211: a prefix implementation must fail).
                    "code": f"CG-CON-{self.loaded.key.contracts.index(booked) + 1:06d}",
                },
                obligations=tuple(
                    {
                        "id": self.uid("obligation", kw["contract"], line.obligation_key),
                        "obligation_key": line.obligation_key,
                    }
                    for line in booked.lines
                ),
            )
        # RES-4: the native result shapes — Submitted names the request and no digest;
        # EstimateVersionOut / JudgementOut / FxRateSetVersionDetailOut carry content_sha256; a
        # DistinctReviewOut names the record and its request; the other submits return None (the
        # read side answers their approvals).
        request_id = self.uid("approval", handler, call.step.subject, len(self.calls))
        if handler == H["distinct_review"]:
            return SimpleNamespace(
                judgement_record_id=self.uid("review", kw["contract"], kw["obligation_key"]),
                approval_request_id=request_id,
            )
        if handler == H["submit_activation"]:
            return SimpleNamespace(
                contract={"id": self.uid("contract", kw["contract"])},
                approval_request_id=request_id,
            )
        if handler in (H["estimate_submit"], H["judgement_submit"]):
            return SimpleNamespace(approval_request_id=request_id, content_sha256="a" * 64)
        if handler == H["fx_submit"]:
            return SimpleNamespace(pending_approval_request_id=request_id, content_sha256="a" * 64)
        return None


class Mail:
    """The one read an acceptance needs — the token of the invitation a membership was sent —
    answered only for a membership a committed result produced."""

    def __init__(self, produced: set[UUID]) -> None:
        self.produced = produced
        self.asked: list[UUID] = []

    def invitation_token(self, membership_id: UUID, *, where: str) -> str:
        assert membership_id in self.produced, where
        self.asked.append(membership_id)
        return MockResolver(str(membership_id)).invitation_token(where)


def _run(key_id: str, invoker) -> WorkspaceAdapter:  # noqa: ANN001
    loaded = load_platform_key(key_id)
    adapter = WorkspaceAdapter(
        loaded, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock-fixture"
    )
    for step in plan(loaded).steps:
        if step.phase in ("CHECKPOINT", "RUNNER") or step.gap is not None:
            continue
        try:
            adapter.run(step)
        except NotProvisioned:
            continue
    return adapter


def test_ids_come_from_committed_results() -> None:
    fake = ShapedFake(POS_012)
    adapter = _run(POS_012, fake)
    resolver = LedgerResolver(adapter.ledger)
    world = adapter.key.world
    customer = world.customers[0]
    assert resolver.customer_id(customer.code) == fake.uid(H["customer"], customer.code)
    assert resolver.product_id(world.products[0].code) == fake.uid(
        H["product"], world.products[0].code
    )
    assert resolver.gl_account_id(world.gl_accounts[0].code) == fake.uid(
        H["gl_account"], world.gl_accounts[0].code
    )
    entity = world.entities[0]
    assert resolver.calendar_id(entity.code) == fake.uid(H["calendar"], entity.code)
    assert resolver.entity_id(entity.code) == fake.uid(H["entity"], entity.code)
    assert resolver.period_state_id(entity.code, entity.books[0], "FY2026-P01") == fake.uid(
        "period_state", entity.code, entity.books[0], "FY2026-P01"
    )
    contract = adapter.key.contracts[0].external_id
    assert resolver.contract_id(contract) == fake.uid("contract", contract)
    assert resolver.group_id(contract) == fake.uid("group", contract)
    template = world.pob_templates[0].code
    assert resolver.template_id(template) == fake.uid(H["template"], template, "", "", "", "", "")
    assert resolver.mapping_version_id() == fake.uid(H["mapping"], "", "", "", "", "", "")
    assert resolver.membership_id("ak-preparer") == fake.uid("membership", "ak-preparer")
    (category,) = policy_groups(world.policies.tenant)
    assert resolver.policy_version_id("TENANT", "tenant", category.value) == fake.uid(
        "policy", "TENANT", "tenant", category.value
    )
    latest = [entry for entry in adapter.ledger if entry.call.handler in SUBMIT_HANDLERS][-1]
    assert latest.call.handler == H["submit_activation"]  # a Submitted: the id, no digest
    assert resolver.pending_approval_id() == latest.result.approval_request_id
    with pytest.raises(UnresolvedHandle, match="returns no subject digest"):
        resolver.subject_sha256()  # RES-4: read side, never a name search or an older entry
    # Record §18 handles: obligations from the booking result, estimates from their create
    # results. A policy override has none (register index 308): the key declares two for this
    # contract, the plan sent no call of the product's override commands, and the resolver
    # has no handle to read one by. Until that item it read the id from the creation's result.
    line = adapter.key.contracts[0].lines[0]
    assert resolver.obligation_id(contract, line.obligation_key) == fake.uid(
        "obligation", contract, line.obligation_key
    )
    assert len(adapter.key.contracts[0].policy_overrides or ()) == 2
    sent = [entry.call.handler for entry in adapter.ledger]
    assert [handler for handler in sent if ".policies.overrides." in handler] == []
    assert not hasattr(resolver, "override_id")
    ex42 = _run(EX42, ShapedFake(EX42))
    ex42_fake = ShapedFake(EX42)
    assert LedgerResolver(ex42.ledger).estimate_id("C-EX42-C", "BONUS-C") == ex42_fake.uid(
        H["estimate"], "C-EX42-C", "BONUS-C"
    )


def test_unknown_or_not_yet_written_handles_are_refused_by_name() -> None:
    empty = LedgerResolver(())
    with pytest.raises(UnresolvedHandle, match="customer") as refused:
        empty.customer_id("CUST-1")
    assert isinstance(refused.value, NotProvisioned)
    assert (refused.value.kind, refused.value.key) == ("customer", "CUST-1")
    adapter = _run(POS_012, ShapedFake(POS_012))
    resolver = LedgerResolver(adapter.ledger)
    with pytest.raises(UnresolvedHandle, match="customer"):
        resolver.customer_id("NOT-A-CUSTOMER")
    with pytest.raises(UnresolvedHandle, match="role"):
        resolver.role_id("controller")  # the provisioning fake exposed no roles
    with pytest.raises(UnresolvedHandle, match="modification"):
        resolver.modification_id(adapter.key.contracts[0].external_id, "MOD-1")
    with pytest.raises(UnresolvedHandle, match="estimate"):
        resolver.estimate_version_id(adapter.key.contracts[0].external_id, "BONUS", 1)
    with pytest.raises(UnresolvedHandle, match="obligation"):
        resolver.obligation_id(adapter.key.contracts[0].external_id, "NOT-AN-OBLIGATION")
    with pytest.raises(UnresolvedHandle, match="rule_set"):
        resolver.rule_set_id("RS-NONE")
    with pytest.raises(UnresolvedHandle, match="fx_set"):
        resolver.fx_set_id("FX-NONE")
    # A RecordingInvoker answers None: nothing is resolvable, nothing is invented.
    none = LedgerResolver(_run(POS_012, RecordingInvoker()).ledger)
    with pytest.raises(UnresolvedHandle, match="result"):
        none.customer_id(adapter.key.world.customers[0].code)
    with_roles = LedgerResolver(_run(POS_012, ShapedFake(POS_012, with_roles=True)).ledger)
    assert isinstance(with_roles.role_id("controller"), UUID)


def test_resolver_is_deterministic_for_a_given_ledger() -> None:
    adapter = _run(POS_012, ShapedFake(POS_012))
    first, second = LedgerResolver(adapter.ledger), LedgerResolver(adapter.ledger)
    code = adapter.key.world.customers[0].code
    assert first.customer_id(code) == second.customer_id(code)
    assert first.pending_approval_id() == second.pending_approval_id()
    again = _run(POS_012, ShapedFake(POS_012))
    assert LedgerResolver(again.ledger).contract_id(
        adapter.key.contracts[0].external_id
    ) == first.contract_id(adapter.key.contracts[0].external_id)


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_every_converted_call_binds_with_ledger_ids(key_id: str) -> None:
    """Replaying the ledger's calls through adapt() with the LedgerResolver binds every handler,
    the record §18 families and the runner's own statements before an activation included; ids
    are the fake's, never made up. The calls that do not convert are the reviews of GT07's
    nondistinct obligations, refused by name (DG-AK-41, the bound). An acceptance takes its token
    from the read side — the invitation its own membership was sent — and without reads it is
    refused by name."""
    fake = ShapedFake(key_id, with_roles=True)
    adapter = _run(key_id, fake)
    resolver = LedgerResolver(adapter.ledger)
    mail = Mail(fake.produced)
    invited = LedgerResolver(adapter.ledger, mail)  # type: ignore[arg-type]
    bound = 0
    beyond: list[tuple[str, str]] = []
    seen: list[LedgerEntry] = []
    for entry in adapter.ledger:
        call = entry.call
        if call.handler == H["decide"]:
            # RES-4: a decision binds only when the latest submission's native result carries
            # both approval members (estimates, judgements, FX); the others need the read side.
            # The decision resolves over the ledger as it stood at decision time (the adapter's
            # live ledger), so the pair is its own submission's, never a later one's.
            latest = next(e for e in reversed(seen) if e.call.handler in SUBMIT_HANDLERS)
            _, digest_member = RESULT_MEMBERS[latest.call.handler]
            at_decision = LedgerResolver(seen)
            if digest_member is None or latest.result is None:
                with pytest.raises(UnresolvedHandle):
                    adapt(call, adapter.key, at_decision)
                seen.append(entry)
                continue
            (decided,) = adapt(call, adapter.key, at_decision)
            assert decided["approval_request_id"] == latest.result.approval_request_id
            assert decided["subject_content_sha256"] == latest.result.content_sha256
        seen.append(entry)
        if call.handler == H["accept"]:
            with pytest.raises(UnresolvedHandle, match="no reads are available"):
                adapt(call, adapter.key, resolver)
            kwargs_list = adapt(call, adapter.key, invited)
        elif call.handler == H["distinct_review"] and call.kwargs["distinctness"] != "distinct":
            with pytest.raises(NotProvisioned) as refused:
                adapt(call, adapter.key, resolver)
            assert DISTINCT_BOUND in str(refused.value)
            beyond.append((call.kwargs["contract"], call.kwargs["obligation_key"]))
            continue
        else:
            kwargs_list = adapt(call, adapter.key, resolver)
        bind_check(call, kwargs_list)
        bound += 1
        for kwargs in kwargs_list:
            for value in kwargs.values():
                if isinstance(value, UUID):
                    assert value in fake.produced  # every id came from a committed result
    assert bound > 20
    assert beyond == NONDISTINCT.get(key_id, [])
    # The operator accepted for the admin membership of the provisioning, each persona for the
    # membership of its own invite, in the plan's order.
    assert mail.asked == [
        fake.uid("admin"),
        *(fake.uid("membership", persona) for persona, _ in INVITED),
    ]
    assert OPERATOR not in {persona for persona, _ in INVITED}


def test_real_invoker_resolves_over_the_live_ledger_before_the_unit_of_work() -> None:
    class _NoDatabase:
        clock = None
        keyring = None

        def uow(self, principal=None):  # noqa: ANN001, ANN201
            raise NotProvisioned("workspace unit of work", "support.factories.Workspace.uow")

    loaded = load_platform_key(POS_012)
    adapter = WorkspaceAdapter.for_database(loaded, _NoDatabase(), PERSONAS)
    steps = plan(loaded).steps
    currencies = next(s for s in steps if s.handler == H["currencies"])
    with pytest.raises(NotProvisioned, match="unit of work"):
        adapter.run(currencies)  # converted, then the unit of work is refused
    entity = next(s for s in steps if s.handler == H["entity"])
    with pytest.raises(UnresolvedHandle, match="calendar"):
        adapter.run(entity)  # the calendar id was never written: refused before any unit of work
    assert adapter.ledger == []
    assert callable(real_invoker(_NoDatabase(), loaded.key, adapter.ledger))


def test_res_2_approval_pair_is_bound_to_the_latest_submission() -> None:
    """Codex RES-R1 inputs: X submitted (actual ``Submitted``: no hash) and decided (the decision
    Mapping carries X's hash a×64), then Y submitted (no hash). The pair is Y's: its id resolves,
    its digest is refused by name — never X's; a later None-return submit stops any fallback; a
    decision result is never a submission source."""
    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps

    def step(handler: str, seq: int):  # noqa: ANN202
        # the item's own TIMELINE step: the runner's steps before an activation share its seq
        return next(
            s for s in steps if s.seq == seq and s.handler == handler and s.phase == "TIMELINE"
        )

    x_id = UUID("00000000-0000-0000-0000-00000000002e")
    y_id = UUID("00000000-0000-0000-0000-00000000003e")
    submit_x = Call(
        H["submit_activation"],
        PREPARER,
        {"contract": "C-POS-012-X", "expected_stream_version": 1},
        step(H["submit_activation"], 2),
    )
    decide_x = Call(
        H["decide"], "ak-approver", {"approval_request_id": "<pending>"}, step(H["decide"], 2)
    )
    submit_y = Call(
        H["submit_activation"],
        PREPARER,
        {"contract": "C-POS-012-Y", "expected_stream_version": 1},
        step(H["submit_activation"], 4),
    )
    ledger = [
        _entry(
            submit_x,
            SimpleNamespace(contract={"id": uuid5(NAMESPACE_URL, "X")}, approval_request_id=x_id),
        ),
        _entry(decide_x, {"id": x_id, "status": "APPROVED", "subject_content_sha256": "a" * 64}),
        _entry(
            submit_y,
            SimpleNamespace(contract={"id": uuid5(NAMESPACE_URL, "Y")}, approval_request_id=y_id),
        ),
    ]
    resolver = LedgerResolver(ledger)
    assert resolver.pending_approval_id() == y_id
    with pytest.raises(UnresolvedHandle, match="seq 4 C-POS-012-Y") as refused:
        resolver.subject_sha256()
    assert "no fallback" in str(refused.value) and "a" * 64 not in str(refused.value)
    decide_y = Call(
        H["decide"], "ak-approver", {"approval_request_id": "<pending>"}, step(H["decide"], 4)
    )
    with pytest.raises(UnresolvedHandle, match="C-POS-012-Y"):
        adapt(decide_y, loaded.key, resolver)  # refused before invocation, never Y's id + X's hash
    # After X's approval alone, X's pair is X's own: the id resolves, the digest is refused (the
    # actual Submitted carries none; the decision row is not a submission source).
    after_x = LedgerResolver(ledger[:2])
    assert after_x.pending_approval_id() == x_id
    with pytest.raises(UnresolvedHandle, match="seq 2 C-POS-012-X"):
        after_x.subject_sha256()
    # A later real None-return submit (SSP) stops the fallback to X's approval id.
    ssp_step = next(s for s in steps if s.handler == H["ssp_submit"])
    ssp_none = _entry(Call(H["ssp_submit"], PREPARER, {"code": "B", "version": 1}, ssp_step), None)
    with pytest.raises(UnresolvedHandle, match="submit_ssp_book_version"):
        LedgerResolver(ledger[:2] + [ssp_none]).pending_approval_id()
    with pytest.raises(UnresolvedHandle, match="no committed submission yet"):
        LedgerResolver([ledger[1]]).pending_approval_id()  # a decision alone is no source
    # A submission whose native result carries both members (EX42's estimate submit) resolves as
    # one pair from that one entry.
    shaped = _run(EX42, ShapedFake(EX42)).ledger
    latest = next(e for e in reversed(shaped) if e.call.handler in SUBMIT_HANDLERS)
    assert latest.call.handler == H["estimate_submit"]
    pair = LedgerResolver(shaped)
    assert pair.pending_approval_id() == latest.result.approval_request_id
    assert pair.subject_sha256() == latest.result.content_sha256


def test_res_3_preset_identity_matches_scope_and_preset_exactly() -> None:
    """Codex RES-R2 inputs: the original DLT LEGACY_PARITY producer answers only
    TENANT / preset / LEGACY_PARITY; an unknown preset or the ENTITY scope is refused."""
    dlt = load_platform_key(DLT)
    producer = next(s for s in plan(dlt).steps if s.handler == PRESET_HANDLER)
    version = UUID("00000000-0000-0000-0000-0000000000aa")
    call = Call(
        PRESET_HANDLER,
        PREPARER,
        {"preset": "LEGACY_PARITY", "scope": "TENANT", "scope_code": "preset", "values": {}},
        producer,
    )
    resolver = LedgerResolver([_entry(call, version)])
    assert resolver.policy_version_id("TENANT", "preset", "LEGACY_PARITY") == version
    for scope, preset in (("TENANT", "UNKNOWN-PRESET"), ("ENTITY", "LEGACY_PARITY")):
        with pytest.raises(UnresolvedHandle, match=f"{scope}/preset/{preset}"):
            resolver.policy_version_id(scope, "preset", preset)


def test_res_4_native_result_members_are_typed_per_handler() -> None:
    """Codex RES-R3 inputs: the native EstimateVersionOut of EX42 seq 7 (approval id …00ca,
    content_sha256 b×64) resolves its own pair and binds the seq 7 decision; a native Submitted
    names the request and no digest (refused by name, never searched); a JudgementOut names its
    request, and its content_sha256 is the record's digest, not the request's, so it is never
    taken; a DistinctReviewOut names the record and its request; a None-returning submit refuses
    naming the command; the cross-subject negatives of RES-2 stand (test_res_2_…)."""
    from erev_api.domain.contracts.activation import Submitted
    from erev_api.schemas.contracts import ContractOut, DistinctReviewOut
    from erev_api.schemas.estimates import EstimateVersionOut
    from erev_api.schemas.judgements import JudgementOut

    ex42 = load_platform_key(EX42)
    steps = plan(ex42).steps
    submit = next(s for s in steps if s.seq == 7 and s.handler == H["estimate_submit"])
    decide = next(s for s in steps if s.seq == 7 and s.handler == H["decide"])
    request_id = UUID("00000000-0000-0000-0000-0000000000ca")
    native = EstimateVersionOut.model_construct(
        id=uuid5(NAMESPACE_URL, "ev"),
        estimate_id=uuid5(NAMESPACE_URL, "e"),
        version_no=1,
        status="SUBMITTED",
        content_sha256="b" * 64,
        approval_request_id=request_id,
    )
    kwargs = {"contract": "C-EX42-C", "element_code": "BONUS-C", "version_no": 1}
    resolver = LedgerResolver(
        [_entry(Call(H["estimate_submit"], PREPARER, kwargs, submit), native)]
    )
    assert resolver.pending_approval_id() == request_id
    assert resolver.subject_sha256() == "b" * 64
    assert resolver.pending_approvals() == ((request_id, "b" * 64),)
    decision = Call(H["decide"], "ak-approver", {}, decide)
    (decided,) = adapt(decision, ex42.key, resolver)
    assert (decided["approval_request_id"], decided["subject_content_sha256"]) == (
        request_id,
        "b" * 64,
    )
    bind_check(decision, [decided])
    # A native Submitted (activation): the id resolves, the digest is refused by name.
    pos = load_platform_key(POS_012)
    activation = next(
        s for s in plan(pos).steps if s.seq == 4 and s.handler == H["submit_activation"]
    )
    assert activation.phase == "TIMELINE"
    y_id = UUID("00000000-0000-0000-0000-00000000003e")
    submitted = Submitted(
        contract=ContractOut.model_construct(
            id=uuid5(NAMESPACE_URL, "Y"), external_id="C-POS-012-Y"
        ),
        approval_request_id=y_id,
    )
    call = Call(H["submit_activation"], PREPARER, {"contract": "C-POS-012-Y"}, activation)
    from_submitted = LedgerResolver([_entry(call, submitted)])
    assert from_submitted.pending_approval_id() == y_id
    with pytest.raises(UnresolvedHandle, match="returns no subject digest") as refused:
        from_submitted.subject_sha256()
    assert "seq 4 C-POS-012-Y" in str(refused.value) and "no fallback" in str(refused.value)
    # A JudgementOut names its request. Its content_sha256 is the digest of the record — the
    # subject content of a record that names a contract also holds the contract's group and
    # stream head (04 §16.10 rev 1.49), and a decision sent with the record's digest is refused
    # as stale. So the digest is the read side's (READ-3): without reads, refused by name.
    judgement = JudgementOut.model_construct(
        id=uuid5(NAMESPACE_URL, "j"), approval_request_id=request_id, content_sha256="d" * 64
    )
    j_step = Step("CONTRACTS", PREPARER, H["judgement_submit"], "contract C-POS-012-X", {})
    j_call = Call(
        H["judgement_submit"], PREPARER, {"contract": "C-POS-012-X", "handle": "J1"}, j_step
    )
    from_judgement = LedgerResolver([_entry(j_call, judgement)])
    assert from_judgement.pending_approval_id() == request_id
    with pytest.raises(UnresolvedHandle, match="returns no subject digest") as not_taken:
        from_judgement.pending_approvals()
    assert "d" * 64 not in str(not_taken.value)
    # A DistinctReviewOut names the judgement record it made and the request, and no digest.
    review = DistinctReviewOut(
        judgement_record_id=uuid5(NAMESPACE_URL, "r"), approval_request_id=request_id
    )
    r_step = Step("CONTRACTS", PREPARER, H["distinct_review"], "contract C-POS-012-X", {})
    r_call = Call(
        H["distinct_review"],
        PREPARER,
        {"contract": "C-POS-012-X", "obligation_key": "X1-LICENCE", "distinctness": "distinct"},
        r_step,
    )
    from_review = LedgerResolver([_entry(r_call, review)])
    assert from_review.pending_approval_id() == request_id
    assert from_review.distinct_review_id("C-POS-012-X", "X1-LICENCE") == review.judgement_record_id
    with pytest.raises(UnresolvedHandle, match="returns no subject digest"):
        from_review.subject_sha256()
    with pytest.raises(UnresolvedHandle, match="distinct_review"):
        from_review.distinct_review_id("C-POS-012-X", "X2-SERVICES")  # no review of that one yet
    # A None-returning submit names the command; no member is searched. (The witness was the
    # override's submission until register index 308 took that step out of the plan; the
    # mapping version's submission returns None as well.)
    m_step = Step("WORLD", PREPARER, H["mapping_submit"], "account mapping", {})
    m_call = Call(H["mapping_submit"], PREPARER, {}, m_step)
    with pytest.raises(
        UnresolvedHandle,
        match="submit_account_mapping_version returns no approval members",
    ):
        LedgerResolver([_entry(m_call, None)]).pending_approval_id()
    assert set(RESULT_MEMBERS) == SUBMIT_HANDLERS
    # Register index 308: no submission of the plan opens a POLICY_OVERRIDE request.
    assert ApprovalSubjectType.POLICY_OVERRIDE not in SUBJECTS.values()
    assert [handler for handler in SUBMIT_HANDLERS if ".policies.overrides." in handler] == []


def test_group_code_comes_from_the_committed_booking() -> None:
    """READ-2 binds the checkpoint read to the persisted group by identity: the group id AND the
    system-generated group code (`CG-<contract_no>`) both come from the committed `book_contract`
    result, never from a name the plan supplies (batch #5: 'NS-SO-DE-5002' vs 'CG-CON-000001')."""
    fake = ShapedFake(PLATFORM_KEY_IDS[0])
    contract = fake.loaded.key.contracts[0].external_id
    call = Call(
        H["book"],
        "ak-preparer",
        {"contract": contract},
        Step("CONTRACTS", "ak-preparer", H["book"], f"contract {contract}"),
    )
    booked = fake(call)
    resolver = LedgerResolver([_entry(call, booked)], None)
    assert resolver.group_id(contract) == booked.combination_group["id"]
    assert resolver.group_code(contract) == "CG-CON-000001"  # the stored code, not a derivation
    assert resolver.group_code(contract) != f"CG-{contract}"
    with pytest.raises(UnresolvedHandle, match="no committed book_contract call"):
        resolver.group_code("NOT-BOOKED")


def test_fresh_ledger_reaches_the_preset_creation_and_later_steps_use_its_version() -> None:
    """Codex 1211 R1: DLT (GT07) chooses LEGACY_PARITY, whose creation is the first WORLD step. On
    a fresh ledger the creation converts WITHOUT resolving a version (there is none yet), and the
    preset's test / submit / publish then resolve exactly the version the committed creation
    returned — every WORLD call converted against the ledger as it stood before that call."""
    fake = ShapedFake(DLT, with_roles=True)
    adapter = _run(DLT, fake)
    seen: list[LedgerEntry] = []
    created: object = None
    for entry in adapter.ledger:
        call = entry.call
        # The preset lifecycle is the first WORLD block (rule CONV-3); the witness ends with its
        # publish. Decisions and approvals resolve the pending pair through the read side (RES-4)
        # and are covered by test_every_converted_call_binds_with_ledger_ids.
        if call.step.phase == "WORLD" and call.handler != H["decide"]:
            kwargs_list = adapt(call, adapter.key, LedgerResolver(seen))  # the prefix ledger
            bind_check(call, kwargs_list)
            if call.handler == PRESET_HANDLER:
                assert (
                    created is None and seen and all(e.call.handler != PRESET_HANDLER for e in seen)
                )
                created = entry.result
            elif call.step.subject.startswith("preset ") and call.handler in (
                H["policy_test"],
                H["policy_submit"],
                H["policy_publish"],
            ):
                assert created is not None, call.handler
                assert [kw["version_id"] for kw in kwargs_list] == [created], call.handler
                if call.handler == H["policy_publish"]:
                    break
        seen.append(entry)
    assert created is not None and call.handler == H["policy_publish"]

"""``WorkspaceAdapter``: the ``DomainAdapter`` of ``DbPlatform`` over
``support.factories.Workspace`` (dev-guide DG-AK-41; BUILD_SPEC PRP-1 ``platform_world``; record
§14.2, §15).

Every plan step becomes one ``Call``: the dotted handler ``platform_plan`` names plus the keyword
arguments derived from the key (the world's codes, names, currencies and periods; the contracts'
booking bodies in the API-S-ContractCreate shape of ``support.worlds.k01_body``; the timeline
items' event bodies with the expected stream version the adapter tracks per contract). The call is
handed to an ``Invoker``; ``real_invoker`` converts it with ``request_models.adapt`` and runs the
imported handler inside ``Workspace.uow()`` then commits; ``RecordingInvoker`` (mock) keeps the
calls and raises nothing, so the mapping is verified without a database or a live call.

Rules of record §15 (Codex review of 161f90f):

- WSA-1: building a call is side-effect-free. The local stream head of a contract, the
  mapping-rule cursor and the ledger advance only in ``run`` after the invoker returned; a call
  the invoker refused, rejected or could not run leaves every head where it was.
- WSA-2: ``refusal`` needs a real before / after fingerprint collector; without one the step is
  ``not_run`` (``NotProvisioned``), never ``executed``. A constant fingerprint exists only as an
  explicit, named mock fixture in tests.

Plainly: the mapping runs only against the mock today. Its execution against ``erev_rv_l17_test``
waits on the Ray-side databases (record §9.1); the read side (``checkpoint_run``, ``journal_run``,
``report_rows``, ``period_state`` from persisted rows) is the following slice and raises
``NotProvisioned`` here.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, Final, Protocol
from uuid import UUID

from support.answer_keys.loader import LoadedKey
from support.answer_keys.models import (
    AnswerKey,
    Checkpoint,
    Contract,
    EventItem,
    JournalBlock,
    ReportBlock,
)
from support.answer_keys.platform_plan import (
    ESTIMATE_MARKER,
    INTEGRATION,
    JOURNAL,
    PRESET_HANDLER,
    REPORT_GAPS,
    STEP1_EVENT,
    STEP1_HANDLE,
    SYSTEM,
    H,
    Step,
    constraint_judgement,
    constraint_of,
    plan_templates,
    preset_overlay,
    step1_judgement,
    tenant_code,
    tenant_display_name,
    waits_for_approval,
)
from support.answer_keys.platform_runner import JournalLine, NotProvisioned
from support.answer_keys.runners import CheckpointRun, _Assembler
from support.answer_keys.workspace_reads import PersistedReads, WorkspaceRows

__all__ = [
    "Call",
    "Invoker",
    "JournalAnswer",
    "JournalRunFailed",
    "LedgerEntry",
    "RecordingInvoker",
    "WorkspaceAdapter",
    "booking_body",
    "problem_code",
    "real_invoker",
    "report_parameters",
]

PENDING_APPROVAL: Final = "<approval request of the previous submit>"
# A manual event routes through the approver persona (§9.5.5): the preparer's request that holds
# a manual event type waits for the decision (BUILD_SPEC CTR-6;
# ``platform_plan.waits_for_approval``).
ROUTE_APPROVAL: Final = "approval"
ROUTE_DIRECT: Final = "direct"


@dataclass(frozen=True, slots=True)
class Call:
    """One domain call: the handler's dotted path, the acting persona and the keyword arguments."""

    handler: str
    actor: str
    kwargs: Mapping[str, Any]
    step: Step


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One successful invocation: who ran what, under which clocks, with which result (the ids the
    database resolver reads back; §15 "persist the actual result ids …")."""

    call: Call
    actor: str
    app_at: datetime | None  # the application (frozen) clock of the step
    server_at: datetime | None  # the server clock read once after the commit
    known_at: datetime | None  # the stamp kept for a timeline item (= server_at when captured)
    result: object
    # The server's transaction horizon read with ``server_at`` — the first transaction id not
    # yet assigned (AK-CLOSE-RUN-STEP-1; dev-guide DG-AK-41 rev 1.246). What the product stamps
    # with the application clock is placed by the transaction that wrote it against this.
    horizon: int | None = None


@dataclass(frozen=True, slots=True)
class JournalAnswer:
    """What the plan's step of a journals block left in the ledger (item AK-JOURNAL-RUN-PLAN-1):
    the run that answers the block, whether the step read it as it stood or created it, the runs
    it cancelled first, latest first, and the run's lines — read at once, so that the cancel a
    later block needs does not take them from the checkpoint."""

    run_id: UUID
    read: bool
    cancelled: tuple[UUID, ...]
    lines: tuple[JournalLine, ...]


type Invoker = Callable[[Call], object]


class RecordingInvoker:
    """The mock: records every call, answers None, raises only what the test configures."""

    def __init__(self, raises: Mapping[int, Exception] | None = None) -> None:
        self.calls: list[Call] = []
        self.raises = dict(raises or {})  # step seq -> exception the command raises

    def __call__(self, call: Call) -> object:
        self.calls.append(call)
        seq = call.step.seq
        if seq is not None and seq in self.raises:
            raise self.raises[seq]
        return None


def problem_code(error: BaseException) -> str | None:
    """The API problem code (04 §15.2 slug) an exception carries, else its class name."""
    for name in ("slug", "code"):
        value = getattr(error, name, None)
        if isinstance(value, str) and value:
            return value
    return type(error).__name__


def _money(value: object, currency: str) -> dict[str, str] | None:
    """A key money value (string in the contract currency, or ``{amount, currency}``) as a
    ``MoneyIn`` mapping."""
    if value is None:
        return None
    parts = _money_parts(value)
    if parts is not None:
        return {"amount": parts[0], "currency": parts[1]}
    return {"amount": str(value), "currency": currency}


def _money_parts(value: object) -> tuple[str, str] | None:
    """(amount, currency) of an ``{amount, currency}`` mapping or model; None for a string."""
    if isinstance(value, Mapping):
        return str(value["amount"]), str(value["currency"])
    amount = getattr(value, "amount", None)
    if amount is not None and not isinstance(value, str):
        return str(amount), str(getattr(value, "currency", ""))
    return None


def decimal_str(value: object, currency: str, *, field: str) -> str:
    """CONV-4: a ``DecimalStr`` API field from either admitted key encoding. A string is the amount;
    an ``{amount, currency}`` object must carry the contract's transaction currency, else the
    conversion refuses (the key is never weakened)."""
    parts = _money_parts(value)
    if parts is not None:
        amount, given = parts
        if given != currency:
            raise ValueError(
                f"{field}: currency {given!r} differs from the contract's transaction currency "
                f"{currency!r}"
            )
        return amount
    return str(value)


def booking_body(contract: Contract) -> dict[str, Any]:
    """API-S-ContractCreate for ``book_contract`` (the shape of ``support.worlds.k01_body``); the
    customer is named by code and resolved by the request-model conversion. ``unit_price`` stays
    the decimal string of ``ContractLineV1.unit_price`` (a ``DecimalStr``, never money-shaped)."""
    lines: list[dict[str, Any]] = []
    for line in contract.lines:
        item: dict[str, Any] = {
            "obligation_key": line.obligation_key,
            "product_code": line.product_code,
            "quantity": line.quantity,
            "total_price": _money(line.total_price, contract.transaction_currency),
        }
        if line.unit_price is not None:
            item["unit_price"] = decimal_str(
                line.unit_price, contract.transaction_currency, field="unit_price"
            )
        for name in (
            "start_date",
            "end_date",
            "stratification",
            "performing_entity_code",
            "ssp_version_label",
            "scope_flag",
            "bundle_parent_obligation_key",
        ):
            value = getattr(line, name)
            if value is not None:
                item[name] = value
        lines.append(item)
    body: dict[str, Any] = {
        "external_id": contract.external_id,
        "customer_code": contract.customer,
        "contracting_entity_code": contract.contracting_entity,
        "transaction_currency": contract.transaction_currency,
        "inception_date": contract.inception_date,
        "lines": lines,
    }
    for name in (
        "signature_date",
        "payment_terms",
        "region",
        "channel",
        "contract_type",
        "renewal_of",
    ):
        value = getattr(contract, name)
        if value is not None:
            body[name] = value
    if contract.scope_605_35:
        body["scope_605_35"] = True
    return body


class WorkspaceAdapter:
    """``DomainAdapter`` over ``support.factories.Workspace``; see the module docstring."""

    name = "workspace"

    def __init__(
        self,
        loaded: LoadedKey,
        *,
        invoker: Invoker | None = None,
        clock: Callable[[], datetime] | None = None,
        fingerprint: Callable[[], str] | None = None,
        reads: PersistedReads | None = None,
        jobs: JobRunner | None = None,
        horizon: Callable[[], int | None] | None = None,
    ) -> None:
        self.loaded = loaded
        self.key: AnswerKey = loaded.key
        self.invoker = invoker
        self.clock = clock
        self.horizon = horizon  # the server's transaction horizon; None means "keeps none"
        self.fingerprint = fingerprint  # WSA-2: None means "cannot observe"; never a constant
        self.reads = reads  # record §19: the persisted reads; None means "cannot read"
        self.jobs = jobs  # READ-6: journal and report runs (command + deferred job)
        self.contracts = {contract.external_id: contract for contract in self.key.contracts}
        self.items = {item.seq: item for item in self.key.timeline}
        # State that advances only from successful committed results (WSA-1).
        self.stream: dict[str, int] = {}  # contract external id -> stream head
        self.mapping_rules_done = 0
        self.ledger: list[LedgerEntry] = []
        self._last_server_at: datetime | None = None

    @classmethod
    def for_database(
        cls, loaded: LoadedKey, workspace: Any, principals: Mapping[str, Any] | None = None
    ) -> WorkspaceAdapter:
        """The adapter over a real ``support.factories.Workspace``: the real invoker converts each
        call with ``request_models.adapt`` and resolves ids with ``LedgerResolver`` over this
        adapter's live ledger (rule RES-1); the server clock is ``SELECT clock_timestamp()``. The
        row fingerprint collector for expected refusals is the read-side slice, so expected
        refusals stay ``not_run`` on the database platform until then (rule WSA-2). Runs only where
        the lane's databases exist."""
        reads = PersistedReads(WorkspaceRows(workspace), keyring=workspace.keyring)
        adapter = cls(
            loaded,
            clock=lambda: _server_clock(workspace),
            fingerprint=reads.fingerprint,  # READ-4 / WSA-2: the tenant's row digest
            reads=reads,
            # PLAT-G4-R2: the live mapping itself, even while empty — never `principals or {}`,
            # which would hand the jobs a new dict that no later commit ever fills.
            jobs=WorkspaceJobs(workspace, {} if principals is None else principals),
            horizon=lambda: _server_horizon(workspace),
        )
        # ACT-1: every actor the plan uses needs a proven principal (personas and the operator's
        # invites / role assignments); the real invoker refuses a missing or wrong one by name.
        adapter.invoker = real_invoker(workspace, loaded.key, adapter.ledger, principals, reads)
        return adapter

    # -- mapping (side-effect-free) ---------------------------------------------------------------

    def _head(self, contract: str) -> int:
        return self.stream.get(contract, 1)

    def _successes(self, handler: str, contract: str | None = None) -> int:
        """How many calls of ``handler`` (for ``contract`` when given) succeeded so far."""
        return sum(
            1
            for entry in self.ledger
            if entry.call.handler == handler
            and (contract is None or entry.call.kwargs.get("contract") == contract)
        )

    def plan_call(self, step: Step) -> Call | None:
        """The domain call of one plan step; None for steps that run nothing (the RUNNER marker).
        Reads adapter state, never writes it (WSA-1)."""
        if step.phase == "RUNNER" or not step.handler:
            return None
        world = self.key.world
        handler = step.handler
        kwargs: dict[str, Any]
        if handler == H["provision"]:
            kwargs = {
                "code": tenant_code(self.key.id),
                "display_name": tenant_display_name(self.key.id, self.key.title),
                "reporting_currency": world.tenant.reporting_currency,
                "preset": world.tenant.preset,
                "is_demo": False,
                "database": "erev_test",
            }
        elif handler == H["invite"]:
            kwargs = {
                "display_name": step.subject,
                "roles": step.detail.get("roles", "").split(","),
            }
        elif handler == H["accept"]:
            kwargs = {"persona": step.subject}
        elif handler == H["api_client"]:
            # CTR-6: the API client of the world that sends an integrated source's events.
            kwargs = {"name": step.subject, "scopes": step.detail.get("scopes", "").split(",")}
        elif handler == H["assign_role"]:
            kwargs = {"members": step.subject.split(","), "is_all_entities": True}
        elif handler == H["currencies"]:
            kwargs = {"currency_codes": list(world.currencies)}
        elif handler in (
            H["calendar"],
            H["fiscal_year"],
            H["entity"],
            H["entity_book"],
            H["open_period"],
        ):
            code = step.subject.removeprefix("entity ")
            entity = next(item for item in world.entities if item.code == code)
            kwargs = {"entity_code": code}
            if handler == H["calendar"]:
                kwargs.update(
                    {
                        "pattern": entity.calendar.pattern,
                        "fiscal_year_start_month": entity.calendar.fiscal_year_start_month,
                    }
                )
            elif handler == H["fiscal_year"]:
                kwargs["fiscal_year"] = int(step.detail["fiscal_year"])
            elif handler == H["entity"]:
                kwargs.update(
                    {
                        "name": entity.name,
                        "functional_currency": entity.functional_currency,
                        "time_zone": entity.time_zone,
                        "books": list(entity.books),
                    }
                )
            elif handler == H["entity_book"]:
                kwargs["book"] = step.detail["book"]
            else:
                kwargs.update(
                    {"book": step.detail["book"], "range": step.detail["range"], "state": "open"}
                )
        elif handler == H["gl_account"]:
            code = step.subject.removeprefix("gl_account ")
            account = next(item for item in world.gl_accounts if item.code == code)
            kwargs = {
                "code": account.code,
                "name": account.name,
                "account_type": account.account_type,
            }
        elif handler == H["mapping_rule"]:
            index = self.mapping_rules_done  # the next rule not yet created (WSA-1: read only)
            if index >= len(world.account_mapping):
                raise NotProvisioned(
                    f"{step.subject}: no account-mapping rule left at index {index}"
                )
            row = world.account_mapping[index]
            kwargs = {"rule_index": index, "rule": row.model_dump(exclude_none=True)}
        elif handler in (
            H["mapping"],
            H["mapping_test"],
            H["mapping_submit"],
            H["mapping_publish"],
        ):
            kwargs = {"rules": len(world.account_mapping)}
            if handler == H["mapping"]:
                kwargs["effective_from"] = step.detail.get("effective_from")
        elif handler == H["customer"]:
            code = step.subject.removeprefix("customer ")
            customer = next(item for item in world.customers if item.code == code)
            kwargs = {"code": customer.code, "name": customer.name}
        elif handler in (
            H["template"],
            H["template_version"],
            H["template_case"],
            H["template_test"],
            H["template_submit"],
            H["template_publish"],
        ) and step.subject.startswith("pob_template "):
            # `template_case` is the rule sets' case command too: the subject tells them apart.
            code = step.subject.removeprefix("pob_template ")
            template = next(item for item in plan_templates(world) if item.code == code)
            kwargs = {"code": code}
            if handler in (H["template"], H["template_version"]):
                kwargs["outputs"] = template.model_dump(exclude_none=True, exclude={"code"})
        elif handler in (H["product"], H["product_template"]):
            code = step.subject.removeprefix("product ")
            product = next(item for item in world.products if item.code == code)
            kwargs = product.model_dump(exclude_none=True)
        elif handler in (H["estimate_evidence"], H["estimate_evidence_attach"]) and (
            ESTIMATE_MARKER in step.detail
        ):
            # The evidence of an estimate version (04 §16.14 rev 1.241). The two commands are
            # the SSP study's own: the step's marker tells the two uses apart.
            kwargs = {**self._estimate_kwargs(step), "evidence": True}
        elif handler in (
            H["ssp_book"],
            H["ssp_version"],
            H["ssp_entries"],
            H["ssp_study"],
            H["ssp_study_attach"],
            H["ssp_submit"],
        ):
            code = step.subject.split(" ")[1]
            book = next(item for item in world.ssp_books if item.code == code)
            index = int(step.subject.rsplit(" ", 1)[1]) - 1
            version = book.versions[index]
            kwargs = {"code": code, "resolution_mode": book.resolution_mode, "version": index + 1}
            if handler == H["ssp_entries"]:
                kwargs["entries"] = [
                    entry.model_dump(exclude_none=True) for entry in version.entries
                ]
            if handler == H["ssp_version"]:
                kwargs["methodology_label"] = version.methodology_label
        elif handler == PRESET_HANDLER or step.subject.startswith("preset "):
            kwargs = {
                "preset": world.tenant.preset,
                "scope": "TENANT",
                "scope_code": "preset",
                # the tenant values the preset's version takes over its own
                "values": preset_overlay(world),
                "effective_from": step.detail.get("effective_from"),
            }
        elif handler in (
            H["policy"],
            H["policy_effective"],
            H["policy_test"],
            H["policy_submit"],
            H["policy_publish"],
        ):
            _, scope, code = step.subject.split(" ", 2)
            taken = preset_overlay(world)  # those are in the preset's version, not in this one
            values = (
                {k: v for k, v in world.policies.tenant.items() if k not in taken}
                if scope == "TENANT"
                else (world.policies.entities if scope == "ENTITY" else world.policies.books)[code]
            )
            kwargs = {
                "scope": scope,
                "scope_code": code,
                "values": dict(values),
                "effective_from": step.detail.get("effective_from"),
            }
        elif handler == H["decide"]:
            kwargs = {"approval_request_id": PENDING_APPROVAL, "decision": "APPROVE"}
            if step.detail.get("emits"):  # FOLL-2: the approval appends the event named here
                kwargs.update({"emits": step.detail["emits"], "contract": step.detail["contract"]})
        elif handler in (H["judgement"], H["judgement_submit"]):
            kwargs = self._judgement_kwargs(step)
        elif handler == H["distinct_review"]:
            kwargs = {
                "contract": step.subject.removeprefix("contract "),
                "obligation_key": step.detail["obligation_key"],
                "distinctness": step.detail["distinctness"],
            }
        elif handler in (
            H["estimate"],
            H["estimate_version"],
            H["estimate_version_update"],
            H["estimate_submit"],
        ):
            # CONV-2 / FOLL-2: the TIMELINE submit is the estimate lifecycle command route.
            kwargs = self._estimate_kwargs(step)
        elif handler in (
            H["rule_set"],
            H["rule_set_version"],
            H["rule"],
            H["rule_case"],
            H["rule_tests"],
            H["rule_set_submit"],
            H["rule_set_publish"],
        ):
            kwargs = self._rule_set_kwargs(step)
        elif handler in (H["fx_set"], H["fx_version"], H["fx_submit"]):
            code = step.subject.removeprefix("fx_rate_set ")
            rate_set = next((item for item in world.fx_rate_sets if item.code == code), None)
            if rate_set is None:
                raise NotProvisioned(f"{step.subject}: fx_rate_set {code!r} not in the key")
            kwargs = {
                "code": code,
                "rate_type": rate_set.rate_type,
                "rates": [rate.model_dump(exclude_none=True) for rate in rate_set.rates],
            }
        elif handler == H["book"]:
            item = self.items[step.seq or -1]
            assert isinstance(item, EventItem)
            contract = self.contracts[item.contract]
            kwargs = {
                "contract": contract.external_id,
                "body": booking_body(contract),
                "origin": "UI",
            }
        elif handler == H["submit_activation"]:
            item = self.items[step.seq or -1]
            assert isinstance(item, EventItem)
            kwargs = {
                "contract": item.contract,
                "effective_date": item.effective_date,
                "expected_stream_version": self._head(item.contract),
            }
        elif handler == H["record_events"] and step.detail.get("step1"):
            # The runner's own Step 1 assessment of a contract whose key states none: one
            # probable assessment per enabled book, on the runner's reviewed record.
            contract_key = step.subject.removeprefix("contract ")
            kwargs = {
                "contract": contract_key,
                "expected_stream_version": self._head(contract_key),
                "route": ROUTE_DIRECT,
                "step1": step.detail["step1"],
                "events": [
                    {
                        "event_type": STEP1_EVENT,
                        "effective_date": step.detail["effective_date"],
                        "payload": {"book": book, "is_probable": True},
                    }
                    for book in step.detail["books"].split(",")
                ],
            }
        elif handler == H["record_events"]:
            item = self.items[step.seq or -1]
            assert isinstance(item, EventItem)
            kwargs = {
                "contract": item.contract,
                "expected_stream_version": self._head(item.contract),
                "route": ROUTE_APPROVAL if waits_for_approval(item) else ROUTE_DIRECT,
                "events": [
                    {
                        "event_type": item.event_type,
                        "effective_date": item.effective_date,
                        "payload": dict(item.payload),
                    }
                ],
            }
        elif handler == H["close_run"]:
            # AK-CLOSE-RUN-STEP-1: the close run a checkpoint's blocks expect.
            kwargs = {
                "entity": step.detail["entity"],
                "book": step.detail["book"],
                "period_key": step.detail["period_key"],
            }
        elif handler == H["compute"]:
            contract = step.subject.split(" ")[2]
            kwargs = {
                "contract": contract,
                "group": self.contracts[contract].combination_group or f"CG-{contract}",
            }
        else:
            kwargs = {"subject": step.subject, **dict(step.detail)}
        return Call(handler, step.actor, kwargs, step)

    def _judgement_kwargs(self, step: Step) -> dict[str, Any]:
        contract_key = step.subject.removeprefix("contract ")
        contract = self.contracts[contract_key]
        handle = step.detail.get("handle")
        judgement = next((j for j in contract.judgements or () if j.handle == handle), None)
        if judgement is None and handle == STEP1_HANDLE:
            judgement = step1_judgement()  # the runner's own record: the key states none
        named = constraint_of(handle)
        if judgement is None and named is not None:
            # the runner's own CONSTRAINT record of an estimate version: the key states none
            judgement = constraint_judgement(*named)
        if judgement is None:
            raise NotProvisioned(f"{step.subject}: judgement {handle!r} not in the key")
        return {
            "contract": contract_key,
            "handle": judgement.handle,
            "topic": judgement.topic,
            "subject_obligation_key": judgement.subject_obligation_key,
            "book_code": judgement.book_code,
            "conclusion": judgement.conclusion,
            "questionnaire": dict(judgement.questionnaire or {}),
        }

    def _estimate_kwargs(self, step: Step) -> dict[str, Any]:
        if step.phase == "TIMELINE" and step.seq in self.items:  # FOLL-2: the item's contract
            item = self.items[step.seq]
            assert isinstance(item, EventItem)
            contract_key = item.contract
        else:
            contract_key = step.subject.removeprefix("contract ")
        contract = self.contracts[contract_key]
        element = step.detail.get("element")
        estimate = next((e for e in contract.estimates or () if e.element_code == element), None)
        if estimate is None:
            raise NotProvisioned(f"{step.subject}: estimate {element!r} not in the key")
        versions = [version.model_dump(exclude_none=True) for version in estimate.versions]
        declared = step.detail.get("version_no")
        if declared is not None:  # the plan names the version (FOLL-1 drafts; FOLL-2 submit)
            version_no = int(declared)
            if not 1 <= version_no <= len(versions):
                raise NotProvisioned(
                    f"{step.subject}: estimate {element!r} has no version {version_no}"
                )
        else:
            created = sum(
                1
                for entry in self.ledger
                if entry.call.handler == H["estimate_version"]
                and entry.call.kwargs.get("contract") == contract_key
                and entry.call.kwargs.get("element_code") == element
            )
            version_no = max(
                min(created + (1 if step.handler == H["estimate_version"] else 0), len(versions)),
                1,
            )
        return {
            "contract": contract_key,
            "element_code": estimate.element_code,
            "estimate_kind": estimate.estimate_kind,
            "method": estimate.method,
            "obligation_key": estimate.obligation_key,
            "direction": estimate.direction,
            "versions": versions,
            "version_no": version_no,
            # the CONSTRAINT record the step names on the version (04 §16.14 rev 1.241)
            "constraint_handle": step.detail.get("constraint"),
        }

    def _rule_set_kwargs(self, step: Step) -> dict[str, Any]:
        code = step.subject.removeprefix("rule_set ")
        rule_set = next((item for item in self.key.world.rule_sets if item.code == code), None)
        if rule_set is None:
            raise NotProvisioned(f"{step.subject}: rule_set {code!r} not in the key")
        kwargs: dict[str, Any] = {"code": code, "kind": rule_set.kind}
        if step.handler == H["rule"]:
            # The n-th rule, n = rules of that set created so far (WSA-1: read only).
            index = sum(
                1
                for entry in self.ledger
                if entry.call.handler == H["rule"] and entry.call.kwargs.get("code") == code
            )
            if index >= len(rule_set.rules):
                raise NotProvisioned(f"{step.subject}: no rule left at index {index}")
            kwargs.update({"rule_index": index, "rule": rule_set.rules[index].model_dump()})
        if step.handler == H["rule_case"]:
            cases = rule_set.example_cases or ()
            index = sum(
                1
                for entry in self.ledger
                if entry.call.handler == H["rule_case"] and entry.call.kwargs.get("code") == code
            )
            if index >= len(cases):
                raise NotProvisioned(f"{step.subject}: no example case left at index {index}")
            kwargs.update({"case_index": index, "case": cases[index].model_dump()})
        return kwargs

    # -- state advance (only after a successful committed result; WSA-1) -------------------------

    def _advance(self, call: Call) -> None:
        contract = call.kwargs.get("contract")
        if call.handler == H["book"] and isinstance(contract, str):
            self.stream[contract] = 1
        elif call.handler == H["record_events"] and isinstance(contract, str):
            # one stream version per appended event: a key item is one, a batch is its length
            self.stream[contract] = self._head(contract) + len(call.kwargs.get("events") or (1,))
        elif call.handler == H["decide"] and call.kwargs.get("emits") and isinstance(contract, str):
            # The approval appends the event its step names: ESTIMATE_CHANGED (FOLL-2) or
            # CONTRACT_ACTIVATED (the approved activation).
            self.stream[contract] = self._head(contract) + 1
        elif call.handler == H["mapping_rule"]:
            self.mapping_rules_done += 1

    def _record(self, call: Call, result: object) -> None:
        app_at = (
            datetime.strptime(call.step.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if call.step.clock_at
            else None
        )
        # PLAT-G4-R1 (record §37): the committed result is recorded before the server clock is
        # read — the clock read may need what the result committed (the provisioning result is
        # the tenant provenance of the runner workspace's reads). If the read refuses, the entry
        # stays (the command did commit) without a stamp and the refusal propagates to the runner.
        entry = LedgerEntry(call, call.actor, app_at, None, None, result)
        self.ledger.append(entry)
        self._advance(call)
        server_at = self.clock() if self.clock is not None else None
        self._last_server_at = server_at
        known_at = server_at if call.step.captures_known_at else None
        # Nothing commits between the two reads: the steps run one after another.
        horizon = self.horizon() if self.horizon is not None else None
        self.ledger[-1] = replace(entry, server_at=server_at, known_at=known_at, horizon=horizon)

    # -- DomainAdapter ----------------------------------------------------------------------------

    def _invoke(self, call: Call) -> object:
        if self.invoker is None:  # no database behind the adapter (AK-NOT-RUN-REASON-1)
            raise NotProvisioned(
                f"{call.step.phase} {call.step.subject}", call.handler, unprovisioned=True
            )
        return self.invoker(call)

    def run(self, step: Step) -> None:
        call = self.plan_call(step)
        if call is None:
            return
        result = self._invoke(call)  # a raise leaves every head where it was (WSA-1)
        self._record(call, result)

    def clock_timestamp(self) -> datetime:
        """The server clock read once after the last commit (``_record``); not a second read."""
        if self.clock is None:
            raise NotProvisioned("SELECT clock_timestamp()", "workspace.scalar", unprovisioned=True)
        if self._last_server_at is None:
            return self.clock()
        return self._last_server_at

    def refusal(self, step: Step, expected_code: str) -> tuple[str | None, bool]:
        call = self.plan_call(step)
        if call is None:  # PLAT-1: an unbuilt command cannot enforce the refusal it expects
            raise NotProvisioned(
                f"expected refusal seq {step.seq} {expected_code}: the command has no handler "
                f"({step.gap or 'no domain handler'})"
            )
        if self.fingerprint is None:  # WSA-2: no observation, no verification
            raise NotProvisioned(
                f"expected refusal seq {step.seq} {expected_code}: no fingerprint collector, the "
                "unchanged-state observation is unavailable (rule WSA-2)",
                call.handler,
                unprovisioned=True,
            )
        before = self.fingerprint()
        try:
            self._invoke(call)
        except NotProvisioned:
            raise
        except Exception as error:  # noqa: BLE001 - the command's refusal is the observation
            return problem_code(error), self.fingerprint() == before
        return None, self.fingerprint() == before  # the command succeeded: no head advance either

    # -- the read side (record §19) ---------------------------------------------------------------

    def _reads(self, where: str, handler: str) -> PersistedReads:
        if self.reads is None:
            raise NotProvisioned(
                f"{where}: no persisted reads (the database platform supplies them; rule READ-1)",
                handler,
                unprovisioned=True,
            )
        return self.reads

    def _jobs(self, where: str, handler: str) -> JobRunner:
        if self.jobs is None:
            raise NotProvisioned(
                f"{where}: no job runner for the command and its deferred job (rule READ-6)",
                handler,
                unprovisioned=True,
            )
        return self.jobs

    def known_at_of(self, after_seq: int, where: str) -> datetime:
        """READ-1: the checkpoint's known_at is the ledger's stamp of its item."""
        stamps = [
            entry.known_at
            for entry in self.ledger
            if entry.call.step.seq == after_seq and entry.known_at is not None
        ]
        if not stamps:
            raise NotProvisioned(
                f"{where}: known_at of seq {after_seq} is not in the ledger — its item did not "
                "execute (rule READ-1)",
                H["read_version"],
            )
        return stamps[-1]

    def horizon_at(self, known_at: datetime) -> int | None:
        """The transaction horizon the ledger read with the stamp ``known_at``; None when the
        platform keeps none. The reads refuse by name what they cannot place without it."""
        return next(
            (entry.horizon for entry in reversed(self.ledger) if entry.known_at == known_at),
            None,
        )

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        from support.answer_keys.ledger_resolver import LedgerResolver  # local: import cycle

        where = f"checkpoint {checkpoint.name}"
        reads = self._reads(where, H["read_version"])
        as_of_periods = self.as_of_periods(checkpoint, where)  # READ-2 (amended): the period read
        known_at = self.known_at_of(int(checkpoint.after_seq), where)
        bundles = next(
            item for item in _Assembler(self.loaded).checkpoints() if item.name == checkpoint.name
        )
        resolver = LedgerResolver(self.ledger, reads)
        outputs = tuple(
            reads.output_bundle(
                group_id=resolver.group_id(bundle.group.member_contract_keys[0]),
                # READ2-R2 by identity: the persisted group's code from the committed booking, never
                # the name the key gives the group (the kernel generates `CG-<contract_no>`).
                group_key=resolver.group_code(bundle.group.member_contract_keys[0]),
                members=bundle.group.member_contract_keys,
                books=tuple(book.book_code for book in bundle.books),
                known_at=known_at,
                where=f"{where} group {bundle.group.group_key}",
                as_of_periods=as_of_periods,
                # the comparison knows the group by the key's name, never by the product's number
                named_group=bundle.group.group_key,
                # what a close run posted is placed by its transaction (rev 1.246)
                horizon=self.horizon_at(known_at),
            )
            for bundle in bundles.bundles
        )
        run = CheckpointRun(bundles, outputs)
        missing = missing_balances(checkpoint, run, as_of_periods)
        if missing:
            raise NotProvisioned(
                f"{where}: the as-of computation's trace carries no producer node (nor an engine "
                f"zero-fill) for {', '.join(missing)} (rule READ-2 amended, D-98 72; never "
                "derived, never the latest-period row)",
                H["read_balances"],
            )
        return run

    def as_of_periods(self, checkpoint: Checkpoint, where: str) -> dict[str, str]:
        """The checkpoint's ``as_of`` period key per entity — ``FY<year>-P<month>`` under a MONTHLY
        calendar starting in January (the same convention as ``_period_keys``); another calendar
        refuses by name (its periods are generated rows the read side does not map yet)."""
        as_of = date.fromisoformat(str(checkpoint.as_of))
        periods: dict[str, str] = {}
        for entity in self.key.world.entities:
            calendar = entity.calendar
            if calendar.pattern != "MONTHLY" or calendar.fiscal_year_start_month != 1:
                raise NotProvisioned(
                    f"{where}: entity {entity.code} keeps a {calendar.pattern} calendar starting "
                    f"in month {calendar.fiscal_year_start_month}; its as-of period is not mapped "
                    "(rule READ-2 amended)",
                    H["read_period"],
                )
            periods[entity.code] = f"FY{as_of.year}-P{as_of.month:02d}"
        return periods

    def journal_run(self, checkpoint: Checkpoint, block: JournalBlock) -> tuple[JournalLine, ...]:
        """The lines of the run the plan's step of ``block`` read or created where the
        checkpoint stands in the timeline (item AK-JOURNAL-RUN-PLAN-1). Nothing is created here:
        a run made when the checkpoint is read — after the whole plan — would hold what later
        items sealed. A block whose step did not run is not run, by name."""
        run = block.run
        where = f"journals {run.entity} {run.period_key} {run.mode}"
        wanted = {
            "checkpoint": checkpoint.name,
            "entity": run.entity,
            "period_key": run.period_key,
            "mode": run.mode,
            "grain": run.grain,
        }
        for entry in reversed(self.ledger):
            step = entry.call.step
            if step.phase != JOURNAL or any(
                step.detail.get(name) != value for name, value in wanted.items()
            ):
                continue
            if isinstance(entry.result, JournalAnswer):
                return entry.result.lines
            raise NotProvisioned(
                f"{where}: the step of the block ran and kept no journal run", H["journal_create"]
            )
        raise NotProvisioned(
            f"{where}: the step that makes the block's journal run after seq "
            f"{checkpoint.after_seq} did not run",
            H["journal_create"],
        )

    def report_rows(
        self, checkpoint: Checkpoint, block: ReportBlock
    ) -> Sequence[Mapping[str, object]]:
        from erev_api.domain.reports import framework

        code = block.report_code
        where = f"reports {code}"
        gap = None if code in framework.BUILDERS else REPORT_GAPS.get(code, "not registered")
        if gap is not None:
            raise NotProvisioned(f"{where}: {gap}", H["report_create"])
        reads = self._reads(where, H["report_create"])
        jobs = self._jobs(where, H["report_create"])
        known_at = self.known_at_of(int(checkpoint.after_seq), where)
        return reads.report_rows(jobs.report_run(block, known_at), where=where)

    def period_state(self, entity: str, book: str, period_key: str, known_at: datetime) -> str:
        where = f"period {entity} {book} {period_key}"
        return self._reads(where, H["read_period"]).period_state(
            entity, book, period_key, known_at, self.horizon_at(known_at)
        )


def missing_balances(
    checkpoint: Checkpoint, run: CheckpointRun, as_of_periods: Mapping[str, str]
) -> list[str]:
    """READ-2 (amended, D-98 72): the ``<contract>@<entity> <period>`` rows a contract block
    compares that no rebuilt book carries, and the ``… <measure>`` amounts the block asserts that
    the rebuilt row does not carry (neither a producer node nor the engine's own zero-fill)."""
    from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
    from support.answer_keys.models import BalanceAmounts

    present: dict[tuple[str, str], Mapping[str, object]] = {
        (balance.subject_key, balance.period_key): balance.columns
        for output in run.outputs
        for book in output.books
        if book.book_code == checkpoint.book
        for balance in book.balances
    }
    missing: list[str] = []
    for block in checkpoint.contracts or ():
        for row in block.balances or ():
            period = as_of_periods.get(row.entity)
            key = (contract_entity_subject_key(block.contract, row.entity), period or "")
            label = f"{block.contract}@{row.entity} {period or '?'}"
            columns = present.get(key)
            if period is None or columns is None:
                missing.append(label)
                continue
            for name in BalanceAmounts.model_fields:
                if getattr(row, name) is not None and f"{name}_txn" not in columns:
                    missing.append(f"{label} {name}")
                functional = row.functional
                if (
                    functional is not None
                    and getattr(functional, name) is not None
                    and f"{name}_functional" not in columns
                ):
                    missing.append(f"{label} functional.{name}")
    return missing


def report_parameters(block: ReportBlock) -> dict[str, Any]:
    """The key's parameters of a report block in the JSON types the report's own schema declares
    (``catalogue.DEFINITIONS_BY_CODE[code].parameters_schema``): a key carries ``time_bands:
    ["12", "24"]``, and the run is refused unless they are whole numbers. A parameter the schema
    does not declare goes as the key states it, and the product's validation answers for it."""
    from erev_api.domain.reports import catalogue
    from support.answer_keys import request_models  # local: import cycles

    declared = catalogue.DEFINITIONS_BY_CODE[block.report_code].parameters_schema
    properties: Mapping[str, Any] = declared.get("properties") or {}
    return {
        name: request_models.schema_value(properties.get(name) or {}, value)
        for name, value in dict(block.parameters).items()
    }


class JobRunner(Protocol):
    """READ-6: a report run created through its command and calculated by its deferred job;
    answers the run id. The database platform's is ``WorkspaceJobs``. A journals block's run is
    no longer made here: it is a step of the plan (``real_invoker``; item
    AK-JOURNAL-RUN-PLAN-1)."""

    def report_run(self, block: ReportBlock, known_at: datetime) -> UUID: ...


# D-98 candidate 107a: journal runs need ``journal.run`` (revenue_accountant → ak-preparer); report
# runs need ``report.run`` (the controller holds it → ak-approver).
JOURNAL_PERSONA: Final = "ak-preparer"
REPORT_PERSONA: Final = "ak-approver"


class WorkspaceJobs:
    """``JobRunner`` over the runner workspace (``database_platform.RunnerWorkspace``: ``clock``,
    ``scalar`` and ``uow(principal, clock=)``): the command inside a unit of work under
    ``principal`` (never the workspace default, rule ACT-1), then ``jobs.registry.run_job`` with
    the workspace's key ring and file store and the run's clock — the record-time clock for a
    checkpoint report run (F-RPS-CUTOFF-R1, record §43). Runs only where the lane's databases
    exist."""

    def __init__(self, workspace: Any, principals: Mapping[str, Any]) -> None:
        self.workspace = workspace
        self.principals = principals  # persona → principal, read when a run starts (ACT-1)

    def _principal(self, where: str, persona: str) -> Any:
        principal = self.principals.get(persona)
        if principal is None:
            raise NotProvisioned(
                f"{where}: no principal mapped for {persona!r}; Workspace.uow(None) is never "
                "used (rule ACT-1)",
                H["journal_create"] if persona == JOURNAL_PERSONA else H["report_create"],
            )
        return principal

    @staticmethod
    def _permitted(handler: str, where: str, principal: Any, persona: str) -> None:
        """Rule ACT-2 for the runs this collaborator starts: the run route's permission, checked
        against the job persona's principal before the unit of work."""
        from support.answer_keys import step_permissions  # local: import cycle

        step = Step("CHECKPOINT", persona, handler, where)
        step_permissions.check(Call(handler, persona, {}, step), principal, [])

    def _run(self, job_id: UUID, *, clock: Any = None) -> None:
        from erev_api.jobs.context import JobRuntime
        from erev_api.jobs.registry import run_job

        runtime = JobRuntime(
            clock=self.workspace.clock if clock is None else clock,
            keyring=self.workspace.keyring,
            files=self.workspace.files,
        )
        run_job(job_id, self.workspace.tenant_id, attempt=1, runtime=runtime)

    def report_run(self, block: ReportBlock, known_at: datetime) -> UUID:
        from erev_api.domain.reports.framework import create_run
        from erev_api.domain.reports.outputs import utc_text
        from erev_api.schemas.reports import ReportRunCreateIn

        where = f"reports {block.report_code}"
        principal = self._principal(where, REPORT_PERSONA)
        self._permitted(H["report_create"], where, principal, REPORT_PERSONA)  # report.run
        body = ReportRunCreateIn(
            report_code=block.report_code,
            parameters={**report_parameters(block), "known_at": utc_text(known_at)},
            output_format="JSON",
        )
        # F-RPS-CUTOFF-R1 (record §43; Codex 1845): ``known_at`` is the checkpoint's record-time
        # stamp (``clock_timestamp()`` after the last commit) while the workspace clock is still
        # the last item's business time (DG-AK-41), and ``framework._resolve`` refuses a
        # ``known_at`` later than ``uow.now``. The run's unit of work and its job therefore take
        # a clock fixed at one server read: the cutoff is not replaced by the business date, not
        # advanced, and the check is not bypassed; the workspace clock stays where the plan put it.
        from erev_api.clock import FrozenClock

        record_clock = FrozenClock(_server_clock(self.workspace))
        with self.workspace.uow(principal, clock=record_clock) as uow:
            run_id, job = create_run(uow, body)
            uow.commit()
        self._run(job.id, clock=record_clock)
        return run_id


def real_invoker(
    workspace: Any,
    key: AnswerKey,
    ledger: Sequence[LedgerEntry],
    principals: Mapping[str, Any] | None = None,
    reads: PersistedReads | None = None,
) -> Invoker:
    """The database invoker: convert the call with ``request_models.adapt`` resolving ids through
    ``LedgerResolver(ledger)`` (the adapter's live ledger, rule RES-1), import the handler and run
    each keyword set inside ``workspace.uow(principal)`` for the call's actor (``principals``:
    persona → ``Principal``; the API derives ``is_manual`` and the approval route from it), then
    commit (``provision_tenant`` runs outside a unit of work with the workspace's clock and
    keyring, and so does ``accept_invitation``, which opens its own as the invited user:
    ``_accept``). Declared here so the wiring is visible; it runs only where the lane's databases
    exist."""
    from support.answer_keys import request_models, step_permissions  # local: import cycles
    from support.answer_keys.ledger_resolver import LedgerResolver

    def invoke(call: Call) -> object:
        handler = request_models.handler_of(call.handler)
        clock = getattr(workspace, "clock", None)
        if call.step.clock_at is not None and hasattr(clock, "set"):
            # DG-AK-41: the application FrozenClock is set to the item's recorded_at (the plan's
            # clock_at) before anything else happens; DB-08 stamps record time at commit.
            at = datetime.strptime(call.step.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            clock.set(at)
        if call.handler != H["provision"]:
            # ACT-1 (record §22): the principal is proven first — a pure selector over the
            # mapping — before the conversion, whose resolver may read the approval rows, and
            # before the unit of work.
            principal = _principal_for(call, principals)
            # ACT-2 (record §34): the step's declared API permission, checked against the proven
            # principal as the API's guard would — before the conversion and the unit of work.
            step_permissions.check(call, principal, ledger)
        kwargs_list = request_models.adapt(call, key, LedgerResolver(ledger, reads))
        if call.step.phase == JOURNAL:
            # AK-JOURNAL-RUN-PLAN-1: the journal run of a journals block — read as it stands,
            # or what stands cancelled and the block's own created and worked.
            (only,) = kwargs_list
            return _journal_block(workspace, principal, call, only["body"], reads, ledger)
        results: list[object] = []
        for kwargs in kwargs_list:
            if call.handler == H["provision"]:
                results.append(
                    handler(
                        kwargs["request"],
                        actor=_operator_actor(call),
                        clock=workspace.clock,
                        keyring=workspace.keyring,
                    )
                )
                continue
            if call.handler == H["accept"]:
                results.append(_accept(handler, workspace, call, kwargs))
                continue
            with workspace.uow(principal) as uow:
                results.append(handler(uow, **kwargs))
                uow.commit()
        if call.handler == H["policy_test"]:
            # `request_test` defers POLICY_SIMULATION and returns the job id; the runner is the
            # worker here (as WorkspaceJobs is for journal and report runs): the job's `run_test`
            # marks the version TESTED (DB-03) before the plan's submit step.
            from erev_api.jobs.context import JobRuntime
            from erev_api.jobs.registry import run_job

            runtime = JobRuntime(
                clock=workspace.clock, keyring=workspace.keyring, files=workspace.files
            )
            for job_id in results:
                run_job(UUID(str(job_id)), workspace.tenant_id, attempt=1, runtime=runtime)
        if call.handler == H["close_run"]:
            _work_close_run(workspace, call, results[-1])
        return results[-1] if len(results) == 1 else results

    return invoke


class CloseRunFailed(AssertionError):
    """A close run the plan ran did not end ``SUCCEEDED``: the key fails, by name — the run, its
    status, the step it stopped at and that step's problem. Never a refusal of the plan's: the
    product was asked for its close run and did not give it."""


def _work_close_run(workspace: Any, call: Call, started: object) -> None:
    """The runner is the worker (as for a policy test, a journal run and a report run): the
    ``CLOSE_RUN`` job that ``close_runs.start`` deferred is run to its end with the workspace's
    clock, key ring and file store. No lock, no approval, no export: the run's steps 1 to 13.
    A dirty group costs the job one poll of its child (05 RCP-19) before it computes it itself."""
    from erev_api.db.tables import close_run
    from erev_api.jobs.context import JobRuntime
    from erev_api.jobs.registry import run_job
    from sqlalchemy import select

    where = f"{call.step.phase} {call.step.subject}"
    job = getattr(started, "job", None)
    run_id = getattr(started, "run_id", None)
    if job is None or run_id is None:
        raise CloseRunFailed(
            f"{where}: the command answered a run that was already active and deferred no job"
        )
    runtime = JobRuntime(clock=workspace.clock, keyring=workspace.keyring, files=workspace.files)
    run_job(UUID(str(job.id)), workspace.tenant_id, attempt=1, runtime=runtime)
    (row,) = workspace.rows(select(close_run).where(close_run.c.id == run_id))
    if str(row["status"]) == "SUCCEEDED":
        return
    stopped = next(
        (step for step in row["steps"] if str(step.get("status")) not in ("SUCCEEDED", "PENDING")),
        None,
    )
    at = "no step" if stopped is None else f"{stopped.get('step_code')} ({stopped.get('status')})"
    problem = None if stopped is None else stopped.get("problem")
    raise CloseRunFailed(
        f"{where}: close run {row['close_run_no']} ended {row['status']} at {at}: {problem}"
    )


class JournalRunFailed(AssertionError):
    """A journal run the plan asked for was not given: the product refused a cancel or the
    create, or the calculation left no run. The key fails, by name — the block, the
    run, what the product answered — as for a close run that does not succeed
    (``CloseRunFailed``): the product was asked. Never a refusal of the plan's."""


CANCEL_REASON: Final = "Answer-key plan: the journal run of the next block of this period follows."
# The grains whose lines name their contract (``JournalLine.contract``; READ-6).
PER_CONTRACT_GRAINS: Final = frozenset({"LEGACY_CONTRACT_POB", "CONTRACT_ACCOUNT_DIMENSIONS"})
DELTA: Final = "DELTA"
LEGACY_BOOK: Final = "LEGACY"


def standing_answer(
    standing: Sequence[Mapping[str, Any]], *, mode: str, grain: str, sealed_to: int, legacy_to: int
) -> Mapping[str, Any] | None:
    """The standing run a block can read as it is, or None — then what stands is cancelled and
    the block's own run created (item AK-JOURNAL-RUN-PLAN-1).

    ``standing`` are the runs of the block's entity, book and period that are not cancelled,
    oldest first. One run answers the block when it is the only one, has the block's mode and
    grain, starts at the first seal and ends at the last one sealed (``sealed_to``; for a DELTA
    run its LEGACY range likewise, ``legacy_to``): the whole journal of the period as it is now,
    in the block's form. That is the close run's own draft run right after the close run, for a
    block of the mode and grain the policies resolved (POL-005, POL-006). A run that continues
    an earlier one, or that something was sealed after, is not the period's journal."""
    if len(standing) != 1:
        return None
    (run,) = standing
    if str(run["mode"]) != mode or str(run["grain"]) != grain:
        return None
    if int(run["from_chain_seq"]) != 0 or int(run["to_chain_seq"]) != sealed_to:
        return None
    if mode == DELTA and (
        int(run["delta_from_chain_seq"] or 0) != 0
        or int(run["delta_to_chain_seq"] or 0) != legacy_to
    ):
        return None
    return run


def _journal_block(
    workspace: Any,
    principal: Any,
    call: Call,
    body: Any,
    reads: PersistedReads | None,
    ledger: Sequence[LedgerEntry],
) -> JournalAnswer:
    """The step of a journals block (item AK-JOURNAL-RUN-PLAN-1; ``platform_plan
    .journal_run_steps``). ``body`` is the API-S-JournalRunCreate of the block's run, without a
    cutoff: the command takes the application clock, which the plan set to the latest instant of
    any step before this one, so the run covers exactly what is sealed now.

    Read: the run that stands for the block's entity, book and period when it is the period's
    whole journal in the block's mode and grain (``standing_answer``). Otherwise the standing
    runs are cancelled, latest first — the product refuses any other order (ruling R-52 (b)) —
    each through ``cancel_run`` as the preparer, and the block's run is created and its
    ``JOURNAL_RUN_CALCULATE`` job worked here, the runner being the worker. The lines are read
    at once and kept. What the product refuses fails the key by name (``JournalRunFailed``)."""
    from erev_api.db.tables import job as job_table
    from erev_api.domain.journals import commands
    from erev_api.jobs.context import JobRuntime
    from erev_api.jobs.registry import run_job
    from erev_api.problems import Problem
    from erev_api.schemas.journals import JournalRunCancelIn
    from sqlalchemy import select
    from support.answer_keys import step_permissions  # local: import cycle

    where = f"{call.step.phase} {call.step.subject}"
    if reads is None:
        raise NotProvisioned(
            f"{where}: no persisted reads to find the runs that stand (rule READ-6)",
            call.handler,
            unprovisioned=True,
        )
    entity, period_key, book = str(body.entity_code), str(body.period_key), str(body.book.value)
    mode, grain = str(body.mode.value), str(body.grain.value)

    def runs() -> list[dict[str, Any]]:
        return reads.journal_runs(entity, book, period_key)

    standing = [row for row in runs() if str(row["state"]) != "cancelled"]
    found = standing_answer(
        standing,
        mode=mode,
        grain=grain,
        sealed_to=reads.sealed_to(book),
        legacy_to=reads.sealed_to(LEGACY_BOOK),
    )
    cancelled: list[UUID] = []
    if found is not None:
        run_id, read = UUID(str(found["id"])), True
    else:
        for row in reversed(standing):
            cancel = Call(
                H["journal_cancel"], call.actor, {"run_no": str(row["run_no"])}, call.step
            )
            step_permissions.check(cancel, principal, ledger)  # ACT-2: journal.run, as the API
            try:
                with workspace.uow(principal) as uow:
                    commands.cancel_run(
                        uow, UUID(str(row["id"])), JournalRunCancelIn(reason=CANCEL_REASON)
                    )
                    uow.commit()
            except Problem as refused:
                raise JournalRunFailed(
                    f"{where}: the cancel of journal run {row['run_no']} ({row['state']}) was "
                    f"refused: {refused.slug}: {refused.detail}"
                ) from refused
            cancelled.append(UUID(str(row["id"])))
        try:
            with workspace.uow(principal) as uow:
                run_id, deferred = commands.create_run(uow, body)
                uow.commit()
        except Problem as refused:
            raise JournalRunFailed(
                f"{where}: the journal run was refused: {refused.slug}: {refused.detail}"
            ) from refused
        runtime = JobRuntime(
            clock=workspace.clock, keyring=workspace.keyring, files=workspace.files
        )
        run_job(UUID(str(deferred.id)), workspace.tenant_id, attempt=1, runtime=runtime)
        if not [row for row in runs() if UUID(str(row["id"])) == run_id]:
            (job_row,) = workspace.rows(
                select(job_table.c.state, job_table.c.problem).where(
                    job_table.c.id == UUID(str(deferred.id))
                )
            )
            raise JournalRunFailed(
                f"{where}: the calculation left no run; its job ended {job_row['state']}: "
                f"{job_row['problem']}"
            )
        read = False
    lines = reads.journal_lines(run_id, per_contract=grain in PER_CONTRACT_GRAINS)
    return JournalAnswer(run_id, read, tuple(cancelled), lines)


ACCEPT_REQUEST_ID: Final = "answer-keys-accept"
# One person, one password, for the life of the process. The keys of one run provision a tenant
# each and invite the same people by email (``request_models.PERSONA_DOMAIN``), and a person who
# already has a password accepts a further invitation with it
# (``auth.invitations.check_acceptance_password``). Generated on first use, kept in memory only,
# never written anywhere: the runner acts through principals built from the ledger (ACT-1) and
# never signs anyone in.
_PASSWORDS: dict[str, str] = {}


def _password_of(persona: str) -> str:
    return _PASSWORDS.setdefault(persona, secrets.token_urlsafe(32))


def _accept(
    handler: Callable[..., object], workspace: Any, call: Call, kwargs: Mapping[str, Any]
) -> None:
    """``POST /session/accept-invitation`` for the call's persona (04 T-PLT-07): the membership
    becomes ACTIVE, as the API requires of everyone it gives a session to and the database of
    every approver (DB-10). The command authenticates the token and opens its own unit of work as
    the invited user, so it runs outside ``workspace.uow``; the session it answers with is
    dropped here — its token is a credential nothing in the runner uses."""
    from erev_api.auth.sessions import RequestFacts

    clock = workspace.clock
    handler(
        token=kwargs["token"],
        password=_password_of(call.step.subject),
        facts=RequestFacts(
            request_id=ACCEPT_REQUEST_ID, source_ip=None, user_agent=None, now=clock.now()
        ),
        keyring=workspace.keyring,
        clock=clock,
        files=workspace.files,
        previous_token=None,
    )


def _principal_for(call: Call, principals: Mapping[str, Any] | None) -> Any:
    """Rule ACT-1: the principal of the call's actor, proven and never defaulted. Refuses by name
    when the mapping lacks the actor, the mapped principal does not hold the persona's roles
    (``ROLE_CODES``), or the mapped principals span tenants; the ``system`` actor is the tenant's
    SYSTEM principal (mapped as ``system`` with kind SYSTEM, or built from the one mapped
    tenant)."""
    from erev_api.auth.principal import system_principal
    from erev_api.enums import PrincipalKind
    from support.answer_keys.request_models import ROLE_CODES

    where = f"{call.step.phase} {call.step.subject}"
    mapped = dict(principals or {})
    tenants = {getattr(principal, "tenant_id", None) for principal in mapped.values()}
    if len(tenants) > 1:
        raise NotProvisioned(
            f"{where}: the mapped principals span {len(tenants)} tenants (rule ACT-1)",
            call.handler,
        )
    if call.actor == SYSTEM:
        if "system" in mapped:
            if getattr(mapped["system"], "kind", None) is not PrincipalKind.SYSTEM:
                raise NotProvisioned(
                    f"{where}: the principal mapped for 'system' is not of kind SYSTEM "
                    "(rule ACT-1)",
                    call.handler,
                )
            return mapped["system"]
        if len(tenants) != 1 or None in tenants:
            raise NotProvisioned(
                f"{where}: no principal mapped for actor 'system' and no mapped tenant to build "
                "the SYSTEM principal from (rule ACT-1)",
                call.handler,
            )
        return system_principal(next(iter(tenants)))
    principal = mapped.get(call.actor)
    if principal is None:
        raise NotProvisioned(
            f"{where}: no principal mapped for actor {call.actor!r}; Workspace.uow(None) is never "
            "used (rule ACT-1)",
            call.handler,
        )
    if call.actor == INTEGRATION and getattr(principal, "kind", None) is not (
        PrincipalKind.API_CLIENT
    ):
        # CTR-6 (PRD ACT-10): an integrated source's event is an API client's — a person's
        # principal here would turn it into a manual event that waits for approval.
        raise NotProvisioned(
            f"{where}: the principal mapped for actor {call.actor!r} is not an API client "
            "(rule ACT-1)",
            call.handler,
        )
    missing = set(ROLE_CODES.get(call.actor, ())) - set(getattr(principal, "roles", ()))
    if missing:
        raise NotProvisioned(
            f"{where}: principal {getattr(principal, 'display_name', '?')!r} mapped for actor "
            f"{call.actor!r} lacks roles {sorted(missing)} (rule ACT-1)",
            call.handler,
        )
    return principal


def _server_clock(workspace: Any) -> datetime:
    """``SELECT clock_timestamp()`` through the workspace (DB-08); a database read."""
    from sqlalchemy import func, select

    value = workspace.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime):
        raise NotProvisioned("SELECT clock_timestamp()", "workspace.scalar", unprovisioned=True)
    return value


def _server_horizon(workspace: Any) -> int | None:
    """The server's transaction horizon — the first transaction id not yet assigned — through
    the workspace; a read that assigns nothing. Rows written before it carry a smaller
    ``created_txid``, rows written after it a greater or equal one. A workspace that answers no
    integer keeps no horizon: the ledger records None, and the reads that need one refuse by
    name (``workspace_reads``), never guess."""
    from sqlalchemy import func, select

    value = workspace.scalar(select(func.txid_snapshot_xmax(func.txid_current_snapshot())))
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _operator_actor(call: Call) -> Any:
    from erev_api.domain.platform.provisioning import OperatorActor

    return OperatorActor(
        channel="CLI", operator_user_id=None, os_user="answer-keys", request_id=call.step.subject
    )

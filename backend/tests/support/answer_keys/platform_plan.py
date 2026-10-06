"""Command plans for the platform answer keys (dev-guide DG-AK-41; BUILD_SPEC PRP-1 to PRP-3 prep).

``platform_runner.run_platform`` (PRP-1) executes these plans — in memory as evidence, on the
database platform (``EREV_AK_PLATFORM=db``, PLAT-G4-1) for real; ``PLATFORM_RUNNER_MISSING`` keeps
platform keys off the engine runner (XR-12). This module plans, without a database, what the
runner does for one ``LoadedKey``: the tenant it
provisions, the personas ``ak-preparer`` and ``ak-approver``, the API client ``ak-integration``
that sends the events of an integrated source, the ``world`` configuration versions
published through their lifecycles, the contracts booked, every timeline item as a domain command
with the ``FrozenClock`` set to the item's record time and ``known_at[seq]`` captured after its
commit, and every checkpoint block as the domain query or run it reads. Each step names the domain
handler by dotted path (``erev_api.domain…``), the actor, and the BUILD_SPEC item that must land
before the step can run (``gap``); the first gap of every plan is the runner itself.

The record times are the engine runner's (``runners._Assembler.times``: explicit ``recorded_at``,
else local noon of the effective date in the contracting entity's time zone, at least one second
after the previous item), so the two runners agree on the order they preserve (DG-AK-41: the
platform cannot backdate DB-08 record times; it captures real server times).

A close run is a step of the plan (``close_run_steps``; DG-AK-41 rev 1.246; item
AK-CLOSE-RUN-STEP-1). The oracle computes the period-end passes with every checkpoint (D-85); the
product posts them in a close run. Where a checkpoint's blocks expect a pass, the plan starts the
product's close run of that entity, book and period right after the checkpoint's last item, and
the runner works its job to the end — no lock, no approval, no export.

A journals block is answered by a step of the plan too (``journal_run_steps``; item
AK-JOURNAL-RUN-PLAN-1): right after the checkpoint's last step — after its close run where the
plan has one — and before the next item, at the latest application instant of any step before
it. A journal run's cutoff is compared with the instant its seals were written at
(``summarise.covered_to``: ``sealed_at``, the application clock's), so a run made there, with no
cutoff of its own, holds exactly what is sealed then; a run made when the checkpoint is read,
after the whole plan, would hold whatever later items sealed with an earlier business time.

The five platform keys of PHASES §8.2.3 are pinned by SHA-256 (``ORACLES``); a plan over a changed
key is refused, so the evidence this module gives is over exactly those oracles.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from erev_api.domain.contracts import estimates as estimate_rules
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.platform.provisioning import LABEL_LENGTH, TENANT_CODE_LENGTH
from erev_api.domain.reports import framework
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.registry.presets import PRESET_CATEGORY
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.models import (
    Checkpoint,
    CommandItem,
    Contract,
    EventItem,
    Judgement,
    PeriodStateItem,
    PobTemplate,
    World,
)
from support.answer_keys.runners import PARITY_PRESET, _Assembler
from support.golden_streams import parity_templates

__all__ = [
    "APPROVER",
    "CLOSE",
    "INTEGRATION",
    "INTEGRATION_SCOPES",
    "JOURNAL",
    "ORACLES",
    "PLATFORM_KEY_IDS",
    "PREPARER",
    "SSP_ANALYST",
    "SSP_APPROVER",
    "RUNNER",
    "CommandPlan",
    "Step",
    "close_run_steps",
    "handler_exists",
    "journal_run_steps",
    "load_platform_key",
    "oracle_mismatches",
    "plan",
    "waits_for_approval",
]

# PHASES §8.2.3: the five platform keys, SHA-256 of the YAML at main eb5546a.
ORACLES: Final[Mapping[str, str]] = {
    "POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT": (
        "e492d5c35c5f29debfae959b8684db57b32e82fe82fcbba7fb231bedda833a57"
    ),
    "DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS": (
        "45088bdb1dffdee51593cb584f9e5035a6ded2f215fc32fc68e64ed3db5180b1"
    ),
    "DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING": (
        "09a9cace19fcd72f6464a8d20104c22f6b274e4c0f061f6643ab9f4d706cbf14"
    ),
    "DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT": (
        "1d9748411b1d922c489cbb8d33a8b73b55b55ecd2a359051089ac3984b947ffe"
    ),
    "POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS": (
        "62d4ad584393403441cb1432a7fdf1afb2fbf78ee35a4a6acf9b6e35bb6b71c2"
    ),
}
PLATFORM_KEY_IDS: Final = tuple(ORACLES)

OPERATOR: Final = "operator"  # the erev_test provisioning operator (DG-AK-41 committed_db)
PREPARER: Final = "ak-preparer"  # revenue accountant
APPROVER: Final = "ak-approver"  # the controller role (DG-AK-41 rev 1.38; no approver role exists)
SSP_ANALYST: Final = "ak-ssp-analyst"  # ssp_analyst: SSP books, versions, entries, submissions
SSP_APPROVER: Final = "ak-ssp-approver"  # ssp_approver: SSP approvals (DG-AK-41 rev 1.42, 107a)
SYSTEM: Final = "system"  # the SYSTEM principal (the compute job)
CLOSE: Final = "CLOSE"  # the phase of a close run the plan runs for a checkpoint
JOURNAL: Final = "JOURNAL"  # the phase of the journal run that answers a journals block
# BUILD_SPEC CTR-6 (PRD ACT-10; 04 §16.3 "Manual events"): a timeline event whose key item says
# ``is_manual: false`` comes from an integrated source, so it is sent by an API client of the
# world — appended directly, stored ``is_manual`` false. A signed-in person's delivery, progress,
# milestone, usage, cost or return event would wait for another user's approval; that is the road
# of an item with ``is_manual: true`` (the preparer's request, then the approver's decision).
INTEGRATION: Final = "ak-integration"
INTEGRATION_SCOPES: Final = ("contract.read", "event.record")

TENANT_CODE_PREFIX: Final = "ak-"
_TENANT_CODE_DIGEST: Final = 8  # hex digits of sha256(key id) that keep two long ids apart


def tenant_code(key_id: str) -> str:
    """The code of the tenant the plan provisions for ``key_id`` — test-side identity, never an
    expected value. ``ak-<id lower-cased>`` when that fits the kernel's [J] rule (DG-KRN-TEN-03:
    3 to 40 lowercase letters, digits and single hyphens; the length is the kernel's own
    ``TENANT_CODE_LENGTH``); a longer id keeps its hyphen-clean head and gains ``-<8 hex of
    sha256(id)>`` so two long ids sharing a head stay distinct. Deterministic; the request the
    database platform sends and the in-memory plan's provision step both name it."""
    slug = re.sub(r"-+", "-", key_id.lower()).strip("-")
    code = f"{TENANT_CODE_PREFIX}{slug}"
    longest = max(TENANT_CODE_LENGTH)
    if len(code) <= longest:
        return code
    digest = hashlib.sha256(key_id.encode("utf-8")).hexdigest()[:_TENANT_CODE_DIGEST]
    head = slug[: longest - len(TENANT_CODE_PREFIX) - 1 - _TENANT_CODE_DIGEST].rstrip("-")
    return f"{TENANT_CODE_PREFIX}{head}-{digest}"


def tenant_display_name(key_id: str, title: str) -> str:
    """The provisioned tenant's display name: the full key id, then the key's title, within the
    kernel's ``LABEL_LENGTH`` (TY-07). With the id here, a digest-suffixed ``tenant_code`` still
    maps unambiguously to its key from the tenant row alone (Codex production-20260921-0216)."""
    return f"{key_id}: {title}"[: max(LABEL_LENGTH)]


RUNNER: Final = "support.answer_keys.platform_runner.run_platform"  # built and wired (PLAT-G4-1)
# A key's own ``close_run`` command item: §9.5.3 names the command and no parameters for it, so
# the plan cannot say which entity, book and period it closes. The close run a checkpoint's blocks
# expect is planned without the item (``close_run_steps``).
CLOSE_RUN_GAP: Final = (
    "AK-CLOSE-RUN-STEP-1: a key's own close_run command names no entity, book and period "
    "(dev-guide §9.5.3); the plan runs the close run a checkpoint's blocks expect"
)
# A period that locks or reopens. The product has the commands (BUILD_SPEC CLO-6 and CLO-7 are
# built): a lock, a permanent lock and a reopen are each requested and decided by an approval.
# What the plan lacks differs by the item (the supervisor's ruling of 2026-10-02, point 4). A
# period state — a world's or a timeline item's — names its entity, book and period, and the plan
# builds no sequence for it: the request, the close gates it meets, the approval. For a key's
# own ``lock_period`` or ``reopen_period`` command the guide names no parameters either
# (dev-guide §9.5.3, as for ``close_run``), whatever a key writes under ``params``. No platform
# key holds either kind.
LOCK_COMMANDS: Final = (
    "erev_api.domain.close.commands.request_lock",
    "erev_api.domain.close.commands.request_permanent_lock",
)
REOPEN_COMMAND: Final = "erev_api.domain.close.commands.request_reopen"
LOCK_GAP: Final = (
    "a period's lock is not planned: the product locks by a request, the close gates it meets "
    "and its approval (close.commands.request_lock, request_permanent_lock), and the plan builds "
    "no such sequence"
)
REOPEN_GAP: Final = (
    "a period's reopen is not planned: the product reopens by a request and its approval "
    "(close.commands.request_reopen), and the plan builds no such sequence"
)
LOCK_COMMAND_GAP: Final = (
    "a key's own lock_period command is not planned: dev-guide §9.5.3 names no parameters for "
    "it, and the product locks by a request, the close gates it meets and its approval "
    "(close.commands.request_lock), a sequence the plan does not build"
)
REOPEN_COMMAND_GAP: Final = (
    "a key's own reopen_period command is not planned: dev-guide §9.5.3 names no parameters "
    "for it, and the product reopens by a request and its approval "
    "(close.commands.request_reopen), a sequence the plan does not build"
)
PORTFOLIO_GAP: Final = "PRP-1: portfolio commands (T-CON-21) are not identified on main"
EXCEPTIONS_GAP: Final = "PRP-2: the exceptions block reads the exception register (not planned)"
# Report codes the catalogue defines without a builder on main, by the item that builds them. A
# code leaves this table when its builder is registered (``framework.BUILDERS``):
# ``revenue_from_prior_period_obligations`` with EDS-4 / RPS-3 (lane ENG-C4) and
# ``contract_cost_rollforward`` with RPS-12 (lane F-RPS-REG) have left it.
REPORT_GAPS: Final[Mapping[str, str]] = {
    "balance_aging": (
        "RPS-12: balance_aging builder is not registered; "
        "CTR-14: fx_layer_movement is not persisted"
    ),
}

# --- handlers (dotted paths; ``handler_exists`` resolves each) ----------------------------------
H: Final[Mapping[str, str]] = {
    "provision": "erev_api.domain.platform.provisioning.provision_tenant",
    "invite": "erev_api.domain.platform.users.invite_user",
    "accept": "erev_api.domain.platform.memberships.accept_invitation",
    "api_client": "erev_api.auth.api_clients.create_api_client",
    "assign_role": "erev_api.domain.platform.roles.assign_role",
    "decide": "erev_api.approvals.engine.decide",
    "currencies": "erev_api.domain.reference.commands.put_tenant_currencies",
    "calendar": "erev_api.domain.reference.commands.create_calendar",
    "fiscal_year": "erev_api.domain.reference.commands.ensure_fiscal_year",
    "entity": "erev_api.domain.reference.commands.create_entity",
    "entity_book": "erev_api.domain.reference.commands.put_entity_book",
    "open_period": "erev_api.domain.reference.commands.open_period",
    "gl_account": "erev_api.domain.reference.commands.create_gl_account",
    "mapping": "erev_api.domain.reference.commands.create_account_mapping_version",
    "mapping_rule": "erev_api.domain.reference.commands.add_account_mapping_rule",
    "mapping_test": "erev_api.domain.reference.commands.run_account_mapping_tests",
    "mapping_submit": "erev_api.domain.reference.commands.submit_account_mapping_version",
    "mapping_publish": "erev_api.domain.reference.commands.publish_account_mapping_version",
    "customer": "erev_api.domain.reference.commands.create_customer",
    "template": "erev_api.domain.policies.commands.create_pob_template",
    "template_version": "erev_api.domain.policies.commands.create_pob_template_version",
    # The example case of a template version is the same T-REF-27 command as a rule set's
    # (`POST /config-test-cases`); the step subject tells the conversion which kind it serves.
    "template_case": "erev_api.domain.policies.commands.create_config_test_case",
    "template_test": "erev_api.domain.policies.commands.run_pob_template_version_tests",
    "template_submit": "erev_api.domain.policies.commands.submit_pob_template_version",
    "template_publish": "erev_api.domain.policies.commands.publish_pob_template_version",
    "product": "erev_api.domain.reference.commands.create_product",
    "product_template": "erev_api.domain.reference.commands.update_product",
    "ssp_book": "erev_api.domain.ssp.commands.create_ssp_book",
    "ssp_version": "erev_api.domain.ssp.commands.create_ssp_book_version",
    "ssp_entries": "erev_api.domain.ssp.commands.upsert_ssp_entries",
    # REQ-SSP-008: a version is submitted with its study attached — an upload, then the link.
    "ssp_study": "erev_api.domain.platform.attachments.upload_file",
    "ssp_study_attach": "erev_api.domain.platform.attachments.attach",
    "ssp_submit": "erev_api.domain.ssp.publication.submit_ssp_book_version",
    "fx_set": "erev_api.domain.reference.commands.create_fx_rate_set",
    "fx_version": "erev_api.domain.reference.commands.create_fx_rate_set_version",
    "fx_submit": "erev_api.domain.reference.commands.submit_fx_rate_set_version",
    "rule_set": "erev_api.domain.policies.commands.create_rule_set",
    "rule_set_version": "erev_api.domain.policies.commands.create_rule_set_version",
    "rule": "erev_api.domain.policies.commands.upsert_rule",
    "rule_case": "erev_api.domain.policies.commands.create_config_test_case",
    "rule_tests": "erev_api.domain.policies.commands.run_rule_set_version_tests",
    "rule_set_submit": "erev_api.domain.policies.commands.submit_rule_set_version",
    "rule_set_publish": "erev_api.domain.policies.commands.publish_rule_set_version",
    "policy": "erev_api.domain.policies.registry_versions.create_policy",
    "policy_test": "erev_api.domain.policies.registry_versions.request_test",
    "policy_effective": "erev_api.domain.policies.registry_versions.update_policy",
    "policy_submit": "erev_api.domain.policies.registry_versions.submit_policy",
    "policy_publish": "erev_api.domain.policies.registry_versions.publish_policy",
    "book": "erev_api.domain.contracts.commands.book_contract",
    "judgement": "erev_api.domain.policies.judgements.create_judgement",
    "judgement_submit": "erev_api.domain.policies.judgements.submit_judgement",
    "estimate": "erev_api.domain.contracts.estimates.create_estimate",
    "estimate_version": "erev_api.domain.contracts.estimates.create_version",
    # ``PATCH /estimate-versions/{id}``: the DRAFT version names its CONSTRAINT record.
    "estimate_version_update": "erev_api.domain.contracts.estimates.update_version",
    # 04 §16.14 rev 1.241 (item EST-EVIDENCE-AT-SUBMIT-1): a version is submitted with its
    # evidence attached — an upload, then the link. The two commands are the SSP study's own;
    # the step's marker (``ESTIMATE_MARKER``) tells the two uses apart.
    "estimate_evidence": "erev_api.domain.platform.attachments.upload_file",
    "estimate_evidence_attach": "erev_api.domain.platform.attachments.attach",
    "estimate_submit": "erev_api.domain.contracts.estimates.submit_version",
    "distinct_review": "erev_api.domain.contracts.activation.record_distinct_review",
    "submit_activation": "erev_api.domain.contracts.activation.submit_activation",
    "record_events": "erev_api.domain.contracts.events.record_events",
    "compute": "erev_api.domain.contracts.compute_job.compute_group",
    "start_close": "erev_api.domain.close.commands.start_close",
    # ``POST /close-runs``: the run is started by the command and worked by its CLOSE_RUN job.
    "close_run": "erev_api.domain.close.close_runs.start",
    "journal_create": "erev_api.domain.journals.commands.create_run",
    "journal_submit": "erev_api.domain.journals.commands.submit_run",
    # AK-JOURNAL-RUN-PLAN-1: the run that stands in the way of a block's run is cancelled first.
    "journal_cancel": "erev_api.domain.journals.commands.cancel_run",
    "import_create": "erev_api.domain.imports.upload.create_import",
    "import_submit": "erev_api.domain.imports.commit.submit_import",
    "report_create": "erev_api.domain.reports.framework.create_run",
    "report_run": "erev_api.domain.reports.framework.run_report",
    "compare_cells": "support.answer_keys.report_cells.compare_block",
    "read_version": "erev_api.domain.contracts.queries.get_version",
    "read_balances": "erev_api.domain.contracts.queries.balances",
    "read_subledger": "erev_api.domain.journals.subledger.list_lines",
    "read_journal": "erev_api.domain.journals.queries.line_outs",
    "read_period": "erev_api.domain.close.queries.period_view",
}
PERIOD_STATE_HANDLERS: Final[Mapping[str, tuple[str, str | None]]] = {
    "open": (H["open_period"], None),
    "closing": (H["start_close"], None),
    "closed": ("", LOCK_GAP),
    "reopened": ("", REOPEN_GAP),
    "permanently_locked": ("", LOCK_GAP),
}
COMMAND_HANDLERS: Final[Mapping[str, tuple[tuple[str, ...], str | None]]] = {
    "close_run": ((), CLOSE_RUN_GAP),
    "journal_run": ((H["journal_create"], H["journal_submit"]), None),
    "lock_period": ((), LOCK_COMMAND_GAP),
    "reopen_period": ((), REOPEN_COMMAND_GAP),
    "publish_fx_rate_set": ((H["fx_submit"], H["decide"]), None),
    "import_upload": ((H["import_create"], H["import_submit"]), None),
}


@dataclass(frozen=True, slots=True)
class Step:
    """One planned action: who runs which handler on what, under which clock, and what blocks it."""

    # RUNNER | PROVISION | PERSONAS | WORLD | CONTRACTS | TIMELINE | CLOSE | JOURNAL | CHECKPOINT
    phase: str
    actor: str  # OPERATOR | PREPARER | APPROVER | INTEGRATION | SYSTEM
    handler: str  # dotted path; "" when a gap leaves no handler to name
    subject: str
    detail: Mapping[str, str] = field(default_factory=dict)
    # the timeline item (TIMELINE), the item a close run or a block's journal run follows (CLOSE,
    # JOURNAL) or a checkpoint's after_seq (CHECKPOINT)
    seq: int | None = None
    clock_at: str | None = None  # FrozenClock before the step, UTC ISO (DG-AK-41)
    captures_known_at: bool = False  # SELECT clock_timestamp() after commit → known_at[seq]
    gap: str | None = None  # BUILD_SPEC item that must land before the step runs


@dataclass(frozen=True, slots=True)
class CommandPlan:
    key_id: str
    sha256: str
    steps: tuple[Step, ...]

    @property
    def gaps(self) -> tuple[str, ...]:
        """Every distinct gap in plan order; the first is where the runner stops next."""
        seen: list[str] = []
        for step in self.steps:
            if step.gap is not None and step.gap not in seen:
                seen.append(step.gap)
        return tuple(seen)

    @property
    def first_stop(self) -> str:
        return self.gaps[0] if self.gaps else "none"

    @property
    def handlers(self) -> tuple[str, ...]:
        seen: list[str] = []
        for step in self.steps:
            if step.handler and step.handler not in seen:
                seen.append(step.handler)
        return tuple(seen)

    def steps_of(self, phase: str) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.phase == phase)

    @property
    def known_at_captures(self) -> tuple[int, ...]:
        """The seqs whose commit the runner follows with ``known_at[seq]``: one per item, and
        one more for the item a close run follows — the later stamp is the checkpoint's."""
        return tuple(
            step.seq for step in self.steps if step.captures_known_at and step.seq is not None
        )


def handler_exists(path: str) -> bool:
    """Whether the dotted ``path`` resolves to an attribute of an importable module."""
    module, _, name = path.rpartition(".")
    if not module or not name:
        return False
    try:
        return hasattr(importlib.import_module(module), name)
    except ImportError:
        return False


def key_path(key_id: str, root: Path = ANSWER_KEY_ROOT) -> Path:
    family = key_id.split("-", 1)[0].lower()
    return root / family / f"{key_id}.yaml"


def load_platform_key(key_id: str, root: Path = ANSWER_KEY_ROOT) -> LoadedKey:
    """The loaded key, refused unless its SHA-256 is the pinned oracle."""
    expected = ORACLES.get(key_id)
    if expected is None:
        raise ValueError(f"{key_id} is not one of the five platform keys (PHASES §8.2.3)")
    loaded = load(key_path(key_id, root))
    if loaded.sha256 != expected:
        raise ValueError(f"{key_id}: sha256 {loaded.sha256} differs from the oracle {expected}")
    return loaded


def oracle_mismatches(root: Path = ANSWER_KEY_ROOT) -> list[str]:
    """The platform keys whose file hash no longer equals ``ORACLES`` (empty when unchanged)."""
    found: list[str] = []
    for key_id, expected in ORACLES.items():
        actual = load(key_path(key_id, root)).sha256
        if actual != expected:
            found.append(f"{key_id}: {actual}")
    return found


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lifecycle(
    phase: str, subject: str, handlers: Iterable[str], *, approve: bool, detail: Mapping[str, str]
) -> list[Step]:
    """Create, submit as the preparer, approve as the approver, publish as the preparer."""
    steps = [Step(phase, PREPARER, handler, subject, detail) for handler in handlers]
    if approve:
        steps.append(Step(phase, APPROVER, H["decide"], subject, {"decision": "APPROVE"}))
    return steps


PRESET_HANDLER: Final = "erev_api.domain.policies.registry_versions.create_legacy_parity_preset"


PRESETS: Final = ("DEFAULT", "LEGACY_PARITY")


def preset_overlay(world: World) -> dict[str, object]:
    """The tenant values of the key that belong to the preset's own version: under a preset other
    than ``DEFAULT``, those of the preset's registry category. The preset and these values are ONE
    version of one key — category, tenant scope — in force from one instant, the preset overlaid
    by the tenant values, as the oracle's own bundle resolves them (``_Assembler``: "the preset
    defaults overlaid by tenant"). Published as two versions, the second names the effective date
    of the first and is refused (04 DB-04)."""
    if world.tenant.preset == "DEFAULT":
        return {}
    return {
        code: value
        for code, value in world.policies.tenant.items()
        if code in POLICY_PARAMETERS and POLICY_PARAMETERS[code].category is PRESET_CATEGORY
    }


def plan_templates(world: World) -> tuple[PobTemplate, ...]:
    """The obligation templates the plan creates: the key's own and, under the ``LEGACY_PARITY``
    preset, the parity templates stage 03 assigns by line (ENGINE_SPEC S03-R-18; 04 T-MIG-01)
    that the key does not define — the four the oracle's own bundle holds (``_Assembler``: "the
    preset provides them unless the key defines the code"). In the product the migration
    import's prerequisites name them, bind the products they create to them and refuse a SKU
    whose parity template the workspace lacks (``migration.prerequisites``); nothing but the
    template lifecycle writes a template. So the plan takes each through that lifecycle, as it
    takes the key's own — its steps stand in for that authoring (dev-guide DG-AK-41 rev 1.219)."""
    templates = list(world.pob_templates)
    if world.tenant.preset == PARITY_PRESET:
        defined = {template.code for template in templates}
        templates.extend(
            PobTemplate(
                code=seeded.template_code,
                obligation_kind=seeded.obligation_kind,
                distinctness=seeded.distinctness,
                satisfaction_pattern=seeded.satisfaction_pattern,
                over_time_criterion=seeded.over_time_criterion,
                recognition_method=seeded.recognition_method,
            )
            for seeded in parity_templates(date.min)
            if seeded.template_code not in defined
        )
    return tuple(templates)


def preset_steps(preset: str, *, effective_from: str, overlay: Iterable[str] = ()) -> list[Step]:
    """The lifecycle steps that apply ``tenant.preset`` right after provisioning (rule CONV-3):
    ``DEFAULT`` needs none (provisioning seeds it); ``LEGACY_PARITY`` creates the DRAFT preset
    version of the tenant scope (DG-KRN-REG-05), submits it, the approver decides, the preparer
    publishes; any other preset is refused explicitly, never waived. ``overlay`` names the tenant
    values the draft takes over the preset's (``preset_overlay``), in the edit that dates it."""
    if preset not in PRESETS:
        raise ValueError(f"unsupported tenant preset {preset!r}; supported: {', '.join(PRESETS)}")
    if preset == "DEFAULT":
        return []
    subject = f"preset {preset}"
    detail = {
        "preset": preset,
        "scope": "TENANT",
        "rule": "DG-KRN-REG-05",
        "effective_from": effective_from,  # the first period start (04 §16.5 rule 3)
    }
    keys = ",".join(sorted(overlay))
    if keys:
        detail["keys"] = keys
    return [
        Step("WORLD", PREPARER, PRESET_HANDLER, subject, detail),
        # The preset is created without a date; its submit requires one (EFFECTIVE_REQUIRED). The
        # same edit overlays the key's tenant values of the preset's category.
        Step("WORLD", PREPARER, H["policy_effective"], subject, detail),
        Step("WORLD", PREPARER, H["policy_test"], subject, detail),  # DB-03: TESTED first
        Step("WORLD", PREPARER, H["policy_submit"], subject, detail),
        Step("WORLD", APPROVER, H["decide"], subject, {"decision": "APPROVE", **detail}),
        Step("WORLD", PREPARER, H["policy_publish"], subject, detail),
    ]


def _world_steps(
    world: World,
    books: tuple[str, ...],
    *,
    effective_from: str,
    calendar_years: tuple[int, int] | None = None,
) -> list[Step]:
    """The WORLD phase. ``calendar_years`` are the first and last fiscal year the entities'
    calendars hold: the engine needs a period for every date it places (CV-12), so the calendar
    reaches the month of the latest date a contract line, a modification, an estimate or a
    timeline item carries, as the oracle's own bundle has it (``_Assembler.calendar_end``). The
    periods of ``world.periods`` are opened; the years beyond stay ``future``, as generated."""
    overlay = preset_overlay(world)
    steps: list[Step] = preset_steps(
        world.tenant.preset, effective_from=effective_from, overlay=overlay
    )  # CONV-3: the preset comes first
    # Tenant settings are the operator's (DG-AK-41 rev 1.38; D-98 candidate 107, Q-14): the API
    # of ``PUT /tenant-currencies`` needs ``settings.manage``, which only ``tenant_admin`` holds.
    steps.append(
        Step(
            "WORLD",
            OPERATOR,
            H["currencies"],
            "tenant currencies",
            {"currency_codes": ",".join(world.currencies)},
        )
    )
    first_year, last_year = calendar_years or (
        int(world.periods.from_[:4]),
        int(world.periods.to[:4]),
    )
    for entity in world.entities:
        subject = f"entity {entity.code}"
        steps.append(
            Step(
                "WORLD",
                PREPARER,
                H["calendar"],
                subject,
                {
                    "pattern": entity.calendar.pattern,
                    "fy_start": str(entity.calendar.fiscal_year_start_month),
                },
            )
        )
        for year in range(first_year, last_year + 1):
            steps.append(
                Step("WORLD", PREPARER, H["fiscal_year"], subject, {"fiscal_year": str(year)})
            )
        steps.append(
            Step(
                "WORLD",
                PREPARER,
                H["entity"],
                subject,
                {"functional_currency": entity.functional_currency, "time_zone": entity.time_zone},
            )
        )
        for book in entity.books:
            steps.append(Step("WORLD", PREPARER, H["entity_book"], subject, {"book": book}))
        for book in entity.books:
            steps.append(
                Step(
                    "WORLD",
                    PREPARER,
                    H["open_period"],
                    subject,
                    {
                        "book": book,
                        "range": f"{world.periods.from_}..{world.periods.to}",
                        "state": "open",
                    },
                )
            )
    for state in world.period_states:
        handler, gap = PERIOD_STATE_HANDLERS.get(state.state, ("", LOCK_GAP))
        steps.append(
            Step(
                "WORLD",
                APPROVER,
                handler,
                f"period {state.entity} {state.book} {state.period_key}",
                {"state": state.state},
                gap=gap,
            )
        )
    for account in world.gl_accounts:
        steps.append(
            Step(
                "WORLD",
                PREPARER,
                H["gl_account"],
                f"gl_account {account.code}",
                {"type": account.account_type},
            )
        )
    for customer in world.customers:
        steps.append(Step("WORLD", PREPARER, H["customer"], f"customer {customer.code}"))
    # DB-03 (lifecycle.submit; REQ-POL-003): a configuration version is submitted only once TESTED.
    # A template version is tested over at least one example case whose line names an existing
    # product, while a product's default template must name a PUBLISHED template ([J], T-REF-20):
    # products are created first without a template, the templates are cased, tested, submitted,
    # approved and published, then each product is bound to its template (`update_product`).
    for product in world.products:
        steps.append(
            Step(
                "WORLD",
                PREPARER,
                H["product"],
                f"product {product.code}",
                {"pob_template": product.pob_template, "bound": "after publication"},
            )
        )
    for template in plan_templates(world):
        subject = f"pob_template {template.code}"
        steps.extend(
            _lifecycle(
                "WORLD",
                subject,
                (
                    H["template"],
                    H["template_version"],
                    H["template_case"],
                    H["template_test"],
                    H["template_submit"],
                ),
                approve=True,
                detail={
                    "pattern": template.satisfaction_pattern,
                    "method": template.recognition_method,
                },
            )
        )
        steps.append(Step("WORLD", PREPARER, H["template_publish"], subject))
    for product in world.products:
        steps.append(
            Step(
                "WORLD",
                PREPARER,
                H["product_template"],
                f"product {product.code}",
                {"pob_template": product.pob_template},
            )
        )
    # The account mapping follows the products its rules name (and the GL accounts and entities
    # above): on the database platform every call converts against the live ledger (rule RES-1),
    # so a rule's `product_id` resolves only from a committed create_product call. Its lint run
    # (`run_account_mapping_tests`) makes the version TESTED before the submit (DB-03). The version
    # is dated at creation — its submit refuses a version without `effective_from`
    # (`mapping.EFFECTIVE_REQUIRED`; DB-04 freezes the date at submission) — at the instant the
    # world's policy versions take effect, the first period start.
    if world.account_mapping:
        steps.extend(
            _lifecycle(
                "WORLD",
                "account mapping",
                (
                    H["mapping"],
                    *([H["mapping_rule"]] * len(world.account_mapping)),
                    H["mapping_test"],
                    H["mapping_submit"],
                ),
                approve=True,
                detail={
                    "rules": str(len(world.account_mapping)),
                    "effective_from": effective_from,
                },
            )
        )
        steps.append(Step("WORLD", PREPARER, H["mapping_publish"], "account mapping"))
    for ssp_book in world.ssp_books:
        for index, version in enumerate(ssp_book.versions):
            subject = f"ssp_book {ssp_book.code} version {index + 1}"
            handlers = (H["ssp_book"],) if index == 0 else ()
            # D-98 candidate 107a: SSP authoring is the analyst's (ssp.create), its approval the
            # SSP approver's (ssp.approve) — the only catalogue roles carrying those grants. A
            # version is submitted with its study attached (REQ-SSP-008: 409 ssp-study-required
            # without one), and its approval is a decision (``decide``), which publishes through
            # the engine's own hook: called by itself, with no decision recorded, that hook is
            # refused by the database (EREV-CFG-002).
            steps.extend(
                Step("WORLD", SSP_ANALYST, handler, subject)
                for handler in (
                    *handlers,
                    H["ssp_version"],
                    H["ssp_entries"],
                    H["ssp_study"],
                    H["ssp_study_attach"],
                    H["ssp_submit"],
                )
            )
            steps.append(
                Step(
                    "WORLD",
                    SSP_APPROVER,
                    H["decide"],
                    subject,
                    {"decision": "APPROVE", "entries": str(len(version.entries))},
                )
            )
    for rate_set in world.fx_rate_sets:
        steps.extend(
            _lifecycle(
                "WORLD",
                f"fx_rate_set {rate_set.code}",
                (H["fx_set"], H["fx_version"], H["fx_submit"]),
                approve=True,
                detail={"rates": str(len(rate_set.rates)), "rate_type": rate_set.rate_type},
            )
        )
    for rule_set in world.rule_sets:
        subject = f"rule_set {rule_set.code}"
        steps.extend(
            _lifecycle(
                "WORLD",
                subject,
                (
                    H["rule_set"],
                    H["rule_set_version"],
                    *([H["rule"]] * len(rule_set.rules)),
                    # Rev 1.26 example cases: created and run before the submission (TESTED).
                    *([H["rule_case"]] * len(rule_set.example_cases or ())),
                    *([H["rule_tests"]] if rule_set.example_cases else []),
                    H["rule_set_submit"],
                ),
                approve=True,
                detail={"kind": rule_set.kind},
            )
        )
        steps.append(Step("WORLD", PREPARER, H["rule_set_publish"], subject))
    scopes: list[tuple[str, str, Mapping[str, object]]] = [
        # the tenant values the preset's version did not take (``preset_overlay``)
        (
            "TENANT",
            "tenant",
            {k: v for k, v in world.policies.tenant.items() if k not in overlay},
        )
    ]
    scopes.extend(
        ("ENTITY", code, values) for code, values in sorted(world.policies.entities.items())
    )
    scopes.extend(("BOOK", code, values) for code, values in sorted(world.policies.books.items()))
    for scope, code, values in scopes:
        if not values:
            continue
        subject = f"policies {scope} {code}"
        steps.extend(
            _lifecycle(
                "WORLD",
                subject,
                (H["policy"], H["policy_test"], H["policy_submit"]),  # DB-03: TESTED first
                approve=True,
                detail={"keys": ",".join(sorted(values)), "effective_from": effective_from},
            )
        )
        steps.append(Step("WORLD", PREPARER, H["policy_publish"], subject))
    for portfolio in world.portfolios:
        steps.append(Step("WORLD", PREPARER, "", f"portfolio {portfolio.code}", gap=PORTFOLIO_GAP))
    return steps


def _contract_configuration(contract: Contract, booking_seq: int) -> list[Step]:
    """The contract-scoped configuration the plan creates for the key (judgements, estimates),
    placed right after the contract's ``CONTRACT_BOOKED`` step and before its activation (record
    §18 rule FOLL-1: the API needs the booked contract and its obligations). Judgements run
    create → submit → approve here; estimates create the element. A version is created when it
    is due, at the timeline's ``ESTIMATE_CHANGED`` item that submits it (rule FOLL-2;
    ``_estimate_prerequisites``): the product keeps at most one version of an element open (04
    T-CON-13 rev 1.241; PRD ERR-93), so the drafts of every version no longer follow the booking.

    A key's ``policy_overrides`` have NO step (register index 308, POLICY-OVERRIDE-WITHDRAW-1;
    supervisor ruling R-126 (c); dev-guide §9.5.4 rev 1.299). Release 1.0 offers no policy
    override at contract or obligation level — the product refuses the creation by name
    (``POLICY_OVERRIDE_NOT_OFFERED``) — so the plan creates none. It does not refuse the key
    either: every other step runs, and the key is judged with one finding beside its figures
    (``platform_runner.key_verdict``). Until that item the plan ran create → submit → approve
    for each override here, and no computation read the row."""
    steps: list[Step] = []
    subject = f"contract {contract.external_id}"
    after = {"after_booking": str(booking_seq)}

    def lifecycle(handlers: tuple[str, ...], detail: Mapping[str, str]) -> list[Step]:
        return [
            replace(step, detail={**step.detail, **after})
            for step in _lifecycle("CONTRACTS", subject, handlers, approve=True, detail=detail)
        ]

    for judgement in contract.judgements or ():
        steps.extend(
            lifecycle(
                (H["judgement"], H["judgement_submit"]),
                {"topic": judgement.topic, "handle": judgement.handle},
            )
        )
    for estimate in contract.estimates or ():
        detail = {"element": estimate.element_code, "kind": estimate.estimate_kind, **after}
        steps.append(Step("CONTRACTS", PREPARER, H["estimate"], subject, detail))
    return steps


# 04 E-03 "MANUAL_EVENT when manual": the types a signed-in person's request does not append.
MANUAL_EVENT_TYPES: Final = frozenset(member.value for member in contract_events.MANUAL_TYPES)


def _recorder(item: EventItem) -> str:
    """Who sends a timeline event through ``record_events`` (BUILD_SPEC CTR-6; PRD ACT-10): the
    preparer for an item the key marks manual, the world's API client for every other — an
    integrated source's event, which the product appends directly with ``is_manual`` false."""
    return PREPARER if item.is_manual else INTEGRATION


def waits_for_approval(item: EventItem) -> bool:
    """The product's rule (04 §16.3 "Manual events"): the preparer's request waits for the
    approver when it holds a delivery, progress, milestone, usage, cost or return event (the
    product's own list, ``events.MANUAL_TYPES``). A person's event of another type — a billing,
    a receipt — is appended directly, manual or not, so an item of such a type marked manual
    takes no decision."""
    return item.is_manual and item.event_type in MANUAL_EVENT_TYPES


# The runner's own Step 1 record of a contract whose key states none
# (``_activation_prerequisites``).
STEP1_HANDLE: Final = "ak-step1"
STEP1_TOPICS: Final = frozenset({"COLLECTIBILITY", "NOT_A_CONTRACT"})
STEP1_EVENT: Final = "COLLECTIBILITY_ASSESSED"
STEP1_CONCLUSION: Final = "Collection of the consideration is probable."
STEP1_RATIONALE: Final = (
    "Answer-key runner: the key activates this contract and states no Step 1 judgement of its "
    "own, so the criteria of 606-10-25-1 are taken as met."
)
DISTINCT_RATIONALE: Final = (
    "Answer-key runner: the review confirms the conclusion of the obligation's template."
)
# 04 table 15.4-I DISTINCT_REVIEW: the template conclusions a person reviews per obligation; a
# ``series`` template records its conclusion itself.
REVIEWED_DISTINCTNESS: Final = frozenset({"distinct", "nondistinct"})
# The bound of these statements (dev-guide DG-AK-41 rev 1.213): the runner states on a key's
# behalf only what the key's expected values already imply. A key that expects a contract that
# is not one, or an obligation that is not distinct, is refused by name where the statement
# would be converted (``request_models.adapt``) — never given the default statement.
STEP1_BOUND: Final = (
    "DG-AK-41: the key's contract has no commercial substance, so the key expects a contract "
    "that is not one (606-10-25-1 (d)); the runner states Step 1 only for a contract whose "
    "criteria the key's facts meet"
)
DISTINCT_BOUND: Final = (
    "DG-AK-41: the obligation's template concludes nondistinct; the runner's review confirms a "
    "distinct conclusion only, and a nondistinct review names the obligation it integrates "
    "into (DistinctReviewIn.integrates_into_obligation_key), which §9.5.4 lines do not state"
)


def states_step1(contract: Contract, timeline: Sequence[object]) -> bool:
    """Whether the key itself states Step 1 for the contract: a judgement of a Step 1 topic or an
    assessment event in its timeline. Such a key speaks for itself and the runner adds nothing."""
    if any(judgement.topic in STEP1_TOPICS for judgement in contract.judgements or ()):
        return True
    return any(
        isinstance(item, EventItem)
        and item.contract == contract.external_id
        and item.event_type == STEP1_EVENT
        for item in timeline
    )


def step1_judgement() -> Judgement:
    """The runner's own Step 1 record (``_activation_prerequisites``): topic COLLECTIBILITY, of
    the contract and of no book. Its five criteria are answered where every Step 1 record of a
    key is (``request_models.judgement_request``), and all five are Yes: a contract whose facts
    answer (d) with No is refused before the record is made (``STEP1_BOUND``)."""
    return Judgement(
        handle=STEP1_HANDLE,
        topic="COLLECTIBILITY",
        conclusion=STEP1_CONCLUSION,
        rationale=STEP1_RATIONALE,
    )


def _activation_prerequisites(assembler: _Assembler, contract: Contract, seq: int) -> list[Step]:
    """What a person records before an activation can be submitted, where the key is silent (04
    table 15.4-I; dev-guide DG-AK-41). A key states a contract's terms and events, not the
    workflow around them, and the activation checklist asks for the workflow:

    - ``DISTINCT_REVIEW``: in a contract of two or more obligations, a reviewed distinct review
      of every obligation whose template concludes ``distinct`` or ``nondistinct``. The runner
      records the template's own conclusion, so the review changes nothing the key computes.
    - ``STEP1_RECORD``: one reviewed ``COLLECTIBILITY`` record of the contract — of no book, and
      so of every book — and a probable assessment per enabled book of the contracting entity,
      effective at the contract's inception, where the activation is dated and reads the
      assessment in force (ruling R-77 (2)). A contract whose key states Step 1 itself gets none
      (``states_step1``).

    ``SOURCE_REFERENCE`` is the booking's own member (``request_models.booking_request``). The
    preparer records and the approver reviews — a person's Step 1 assessment is appended
    directly, it is none of the types that wait for a second person (BUILD_SPEC CTR-6) — and
    every step runs at the activation item's clock. All of it is test-side: never an input or an
    expected value of a key.

    The bound: these statements say only what the key's expected values already imply. The step
    of a nondistinct obligation, and the Step 1 record of a contract the key's facts make no
    contract, are planned like the others and refused by name at their conversion
    (``DISTINCT_BOUND``, ``STEP1_BOUND``): the database platform stops there and the key ends
    not run with that reason, not on a refusal of the product."""
    world = assembler.key.world
    at = _iso(assembler.times[seq])
    subject = f"contract {contract.external_id}"
    marker = {"before_activation": str(seq)}

    def step(actor: str, handler: str, detail: Mapping[str, str]) -> Step:
        return Step(
            "CONTRACTS", actor, handler, subject, {**detail, **marker}, seq=seq, clock_at=at
        )

    steps: list[Step] = []
    if len(contract.lines) >= 2:
        templates = {template.code: template for template in plan_templates(world)}
        products = {product.code: product for product in world.products}
        for line in contract.lines:
            template = templates[products[line.product_code].pob_template]
            if template.distinctness not in REVIEWED_DISTINCTNESS:
                continue
            review = {"obligation_key": line.obligation_key, "distinctness": template.distinctness}
            steps.append(step(PREPARER, H["distinct_review"], review))
            steps.append(step(APPROVER, H["decide"], {"decision": "APPROVE", **review}))
    if not states_step1(contract, assembler.timeline):
        record = {"topic": "COLLECTIBILITY", "handle": STEP1_HANDLE}
        steps.append(step(PREPARER, H["judgement"], record))
        steps.append(step(PREPARER, H["judgement_submit"], record))
        steps.append(step(APPROVER, H["decide"], {"decision": "APPROVE", **record}))
        entity = next(item for item in world.entities if item.code == contract.contracting_entity)
        assessed = {
            "step1": STEP1_HANDLE,
            "books": ",".join(sorted(entity.books)),
            "effective_date": contract.inception_date,
        }
        steps.append(step(PREPARER, H["record_events"], assessed))
    return steps


# What a person records before an estimate version can be submitted, where the key is silent
# (``_estimate_prerequisites``; 04 §16.14 rev 1.241, table 15.4-D).
ESTIMATE_MARKER: Final = "before_estimate"  # the detail member of every such step
CONSTRAINT_KIND: Final = "VARIABLE_CONSIDERATION"
CONSTRAINT_TOPIC: Final = "CONSTRAINT"
CONSTRAINT_HANDLE: Final = "ak-constraint"
CONSTRAINT_CONCLUSION: Final = "A significant reversal of the constrained amount is not probable."
CONSTRAINT_RATIONALE: Final = (
    "Answer-key runner: the key submits this estimate version and states no CONSTRAINT judgement "
    "of its own, so the constrained amount it states is taken as meeting 606-10-32-11."
)
# The kinds whose version is submitted with its evidence: the product's own set.
EVIDENCE_KINDS: Final = estimate_rules.EVIDENCE_KINDS


def constraint_handle(element_code: str, version_no: int) -> str:
    """The handle of the runner's own CONSTRAINT record of one estimate version."""
    return f"{CONSTRAINT_HANDLE}:{element_code}:v{version_no}"


def constraint_of(handle: str | None) -> tuple[str, int] | None:
    """The element and the version a handle of ``constraint_handle`` names, else None."""
    prefix = f"{CONSTRAINT_HANDLE}:"
    if handle is None or not handle.startswith(prefix):
        return None
    element, separator, number = handle[len(prefix) :].rpartition(":v")
    if not separator or not element or not number.isdigit():
        return None
    return element, int(number)


def stated_constraint(contract: Contract, element_code: str, version_no: int) -> Judgement | None:
    """The CONSTRAINT judgement the key itself states for the element, or None: one whose
    ``questionnaire.estimate_key`` names the element by its code, by the engine's estimate key or
    by that key and the version — the three names the product reads
    (``estimates._constraint_record``). Such a key speaks for itself: the record follows the
    booking as every judgement of a key does, and the version names it."""
    estimate_key = obligation_subject_key(contract.external_id, element_code)
    names = {element_code, estimate_key, f"{estimate_key}@v{version_no}"}
    for judgement in contract.judgements or ():
        named = (judgement.questionnaire or {}).get("estimate_key")
        if judgement.topic == CONSTRAINT_TOPIC and named in names:
            return judgement
    return None


def constraint_judgement(element_code: str, version_no: int) -> Judgement:
    """The runner's own CONSTRAINT record of an estimate version whose key states none: of the
    version itself and of no book, naming the element by its code. The version is the subject
    the product's screen sends (SCREENS §8.4), and the one that leaves the contract alone: a
    record that names a contract holds it, while it is active, from the record's submission
    to its review — two more events on its stream — unless the record's subject is a
    modification or an estimate version (REQ-POL-010; 04 T-CON-20 "Judgement holds" rev
    1.209). Its conclusion says what the key's expected values already imply — the key takes
    the version's constrained amount into the transaction price — and ``remote`` is No: no
    remoteness is attested, which the engine reads for breakage alone (ENGINE_SPEC_B
    S09-R-29)."""
    return Judgement(
        handle=constraint_handle(element_code, version_no),
        topic=CONSTRAINT_TOPIC,
        conclusion=CONSTRAINT_CONCLUSION,
        rationale=CONSTRAINT_RATIONALE,
        questionnaire={"estimate_key": element_code, "remote": False},
    )


def named_constraint(contract: Contract, element_code: str, version_no: int) -> str | None:
    """The handle of the CONSTRAINT record a version names: the key's own record of the
    element, else the runner's; None for a version of another kind."""
    estimate = next((e for e in contract.estimates or () if e.element_code == element_code), None)
    if estimate is None or estimate.estimate_kind != CONSTRAINT_KIND:
        return None
    stated = stated_constraint(contract, element_code, version_no)
    return constraint_handle(element_code, version_no) if stated is None else stated.handle


def _estimate_prerequisites(
    assembler: _Assembler, item: EventItem, *, expects_refusal: bool = False
) -> list[Step]:
    """What a person does before an estimate version can be submitted, where the key is silent
    (04 §16.14 rev 1.241, table 15.4-D; PRD ERR-93, ERR-94, IMP-138 to IMP-141; dev-guide
    DG-AK-41 rev 1.278). A key states an element, its versions and the ``ESTIMATE_CHANGED`` item
    of each; the product asks for the workflow around them:

    - the version is created when it is due — at its own item, after its predecessor was
      approved. At most one version of an element is open (ERR-93), so the plan no longer
      drafts every version at the booking;
    - a ``VARIABLE_CONSIDERATION`` version names the CONSTRAINT record of its element, which is
      reviewed before the version is approved (ERR-94). Where the key states one
      (``stated_constraint``) it was reviewed after the booking and the version is created
      with it. Else the runner prepares its own on the version (``constraint_judgement``):
      the preparer creates the version, prepares the record and sends it for review, the
      approver, who holds ``judgement.review``, reviews it, and the preparer names it on
      the version;
    - a ``VARIABLE_CONSIDERATION``, ``EAC`` or ``RETURN_RATE`` version is submitted with its
      evidence attached: a page of the runner's own, uploaded and attached by the preparer, as
      the study of an SSP version is.

    A variable-consideration version that repeats the approved values — an attestation of no
    change — owes neither by the product's rule (it owes a reason, the key's ``rationale``)
    and may carry both: the runner prepares them for every version alike and does not repeat
    the product's comparison of values.

    A key that expects the submission REFUSED (``expects_refusal``) gets the conversions — the
    version, created when due, and its evidence — and no record of the runner's: the record is
    a statement, and it would state what the expected values of such a key do not imply
    (DG-AK-41, the bound). The product asks the version's own values first, so a refusal on
    them is reached either way, and with the evidence attached so is a refusal that follows
    its questions (an EAC below the costs incurred). A variable-consideration version whose
    key states no record is answered for the missing record once its values are clean: a
    refusal the product would raise after that question is not reached, and the key ends with
    the product's answer, by name.

    The steps follow the booking's pattern (``_activation_prerequisites``): the preparer
    records, the approver reviews, every step runs at the item's clock, and all of it is
    test-side — never an input or an expected value of a key."""
    contract = assembler.contracts[item.contract]
    element = str(item.payload.get("estimate", ""))
    estimate = next((e for e in contract.estimates or () if e.element_code == element), None)
    if estimate is None:
        return []  # the submission's own conversion refuses the unknown element by name
    version_no = int(str(item.payload.get("version_no", 1)))
    at = _iso(assembler.times[item.seq])
    subject = f"contract {contract.external_id}"
    marker = {ESTIMATE_MARKER: str(item.seq)}

    def step(actor: str, handler: str, detail: Mapping[str, str]) -> Step:
        return Step(
            "CONTRACTS", actor, handler, subject, {**detail, **marker}, seq=item.seq, clock_at=at
        )

    version = {
        "element": element,
        "kind": estimate.estimate_kind,
        "version_no": str(version_no),
    }
    handle = named_constraint(contract, element, version_no)
    own = handle is not None and stated_constraint(contract, element, version_no) is None
    if handle is not None and not own:
        version["constraint"] = handle  # the key's record, reviewed after the booking
    steps = [step(PREPARER, H["estimate_version"], version)]
    if handle is not None and own and not expects_refusal:
        record = {
            "topic": CONSTRAINT_TOPIC,
            "handle": handle,
            "element": element,
            "version_no": str(version_no),
        }
        steps.append(step(PREPARER, H["judgement"], record))
        steps.append(step(PREPARER, H["judgement_submit"], record))
        steps.append(step(APPROVER, H["decide"], {"decision": "APPROVE", **record}))
        named = {**version, "constraint": handle}
        steps.append(step(PREPARER, H["estimate_version_update"], named))
    if estimate.estimate_kind in EVIDENCE_KINDS:
        steps.append(step(PREPARER, H["estimate_evidence"], version))
        steps.append(step(PREPARER, H["estimate_evidence_attach"], version))
    return steps


def _timeline_steps(assembler: _Assembler) -> list[Step]:
    steps: list[Step] = []
    for item in assembler.timeline:
        at = _iso(assembler.times[item.seq])
        if item.expect_problem is not None:
            refused: dict[str, str] = {
                "code": item.expect_problem.code,
                "effect": "refused; no row changes",
                "verification": "expected code + unchanged state (rule PLAT-1)",
            }
            handler = H["record_events"] if isinstance(item, EventItem) else ""
            if isinstance(item, EventItem) and item.event_type == "ESTIMATE_CHANGED":
                # FOLL-2: the refusal of an estimate change is submit_version's, never
                # record_events' (API-R-30). The version it refuses is created first, when due.
                handler = H["estimate_submit"]
                refused.update(
                    {
                        "element": str(item.payload.get("estimate", "")),
                        "version_no": str(item.payload.get("version_no", 1)),
                    }
                )
                steps.extend(_estimate_prerequisites(assembler, item, expects_refusal=True))
            steps.append(
                Step(
                    "TIMELINE",
                    _recorder(item) if handler == H["record_events"] else PREPARER,
                    handler,
                    f"seq {item.seq} expect_problem",
                    refused,
                    seq=item.seq,
                    clock_at=at,
                )
            )
            continue
        if isinstance(item, EventItem):
            subject = f"seq {item.seq} {item.contract} {item.event_type}"
            detail = {
                "effective_date": item.effective_date,
                "payload_keys": ",".join(sorted(item.payload)),
            }
            if item.event_type == "CONTRACT_BOOKED":
                steps.append(
                    Step(
                        "TIMELINE",
                        PREPARER,
                        H["book"],
                        subject,
                        detail,
                        seq=item.seq,
                        clock_at=at,
                        captures_known_at=True,
                    )
                )
                # FOLL-1: judgements and estimated elements follow the booking; a key's policy
                # overrides have no step (register index 308).
                steps.extend(_contract_configuration(assembler.contracts[item.contract], item.seq))
                continue
            if item.event_type == "ESTIMATE_CHANGED":
                # CONV-2 / FOLL-2 / API-R-30: the estimate lifecycle emits the event, never
                # record_events: the preparer submits the DRAFT version, the approver's decision
                # appends ESTIMATE_CHANGED as SYSTEM and computes; known_at is that commit.
                # Before the submission: the version itself, its CONSTRAINT record and its
                # evidence (04 §16.14 rev 1.241).
                steps.extend(_estimate_prerequisites(assembler, item))
                route = {
                    **detail,
                    "element": str(item.payload.get("estimate", "")),
                    "version_no": str(item.payload.get("version_no", 1)),
                    "route": "estimate lifecycle (API-R-30); record_events never carries "
                    "ESTIMATE_CHANGED",
                }
                steps.append(
                    Step(
                        "TIMELINE",
                        PREPARER,
                        H["estimate_submit"],
                        subject,
                        route,
                        seq=item.seq,
                        clock_at=at,
                    )
                )
                steps.append(
                    Step(
                        "TIMELINE",
                        APPROVER,
                        H["decide"],
                        subject,
                        {
                            "decision": "APPROVE",
                            "emits": "ESTIMATE_CHANGED",
                            "contract": item.contract,
                            **route,
                        },
                        seq=item.seq,
                        clock_at=at,
                        captures_known_at=True,
                    )
                )
                steps.append(
                    Step(
                        "TIMELINE",
                        SYSTEM,
                        H["compute"],
                        subject,
                        {
                            "cutoff": "version_cutoff = max(known_at, transaction_timestamp) "
                            "(L6-3-Q-19)"
                        },
                        seq=item.seq,
                        clock_at=at,
                    )
                )
                continue
            if item.event_type == "CONTRACT_ACTIVATED":
                steps.extend(
                    _activation_prerequisites(
                        assembler, assembler.contracts[item.contract], item.seq
                    )
                )
                steps.append(
                    Step(
                        "TIMELINE",
                        PREPARER,
                        H["submit_activation"],
                        subject,
                        detail,
                        seq=item.seq,
                        clock_at=at,
                    )
                )
                # The approval IS the activation: the decision's hook runs the gate again, appends
                # CONTRACT_ACTIVATED as SYSTEM on behalf of the preparer and computes, all in the
                # deciding transaction (04 §16.1; DG-CMD-09). A second call of the hook after the
                # decision is refused as stale, so the plan has none; known_at is this commit.
                steps.append(
                    Step(
                        "TIMELINE",
                        APPROVER,
                        H["decide"],
                        subject,
                        {
                            "decision": "APPROVE",
                            "emits": "CONTRACT_ACTIVATED",
                            "contract": item.contract,
                        },
                        seq=item.seq,
                        clock_at=at,
                        captures_known_at=True,
                    )
                )
                continue
            # CTR-6: an integration's event (``is_manual`` false) is appended by the API client
            # and ``known_at`` is that commit; a person's request (``is_manual`` true) appends
            # nothing — the approver's decision appends it, and ``known_at`` is that commit.
            steps.append(
                Step(
                    "TIMELINE",
                    _recorder(item),
                    H["record_events"],
                    subject,
                    {**detail, "is_manual": str(item.is_manual).lower()},
                    seq=item.seq,
                    clock_at=at,
                    captures_known_at=not waits_for_approval(item),
                )
            )
            if waits_for_approval(item):
                steps.append(
                    Step(
                        "TIMELINE",
                        APPROVER,
                        H["decide"],
                        subject,
                        {"decision": "APPROVE"},
                        seq=item.seq,
                        clock_at=at,
                        captures_known_at=True,
                    )
                )
            steps.append(
                Step(
                    "TIMELINE",
                    SYSTEM,
                    H["compute"],
                    subject,
                    {"cutoff": "version_cutoff = max(known_at, transaction_timestamp) (L6-3-Q-19)"},
                    seq=item.seq,
                    clock_at=at,
                )
            )
        elif isinstance(item, PeriodStateItem):
            handler, gap = PERIOD_STATE_HANDLERS.get(item.state, ("", LOCK_GAP))
            steps.append(
                Step(
                    "TIMELINE",
                    APPROVER,
                    handler,
                    f"seq {item.seq} period {item.entity} {item.book} {item.period_key}",
                    {"state": item.state},
                    seq=item.seq,
                    clock_at=at,
                    captures_known_at=True,
                    gap=gap,
                )
            )
        elif isinstance(item, CommandItem):
            handlers, gap = COMMAND_HANDLERS[item.command.name]
            subject = f"seq {item.seq} command {item.command.name}"
            params = {key: str(value) for key, value in sorted(item.command.params.items())}
            if not handlers:
                steps.append(
                    Step(
                        "TIMELINE",
                        APPROVER,
                        "",
                        subject,
                        params,
                        seq=item.seq,
                        clock_at=at,
                        captures_known_at=True,
                        gap=gap,
                    )
                )
            for index, handler in enumerate(handlers):
                steps.append(
                    Step(
                        "TIMELINE",
                        APPROVER if handler == H["decide"] else PREPARER,
                        handler,
                        subject,
                        params,
                        seq=item.seq,
                        clock_at=at,
                        captures_known_at=index == len(handlers) - 1,
                    )
                )
    return steps


def _checkpoint_steps(assembler: _Assembler, checkpoint: Checkpoint) -> list[Step]:
    known_at = _iso(assembler.times[checkpoint.after_seq])
    base = {"known_at": known_at, "as_of": checkpoint.as_of, "book": checkpoint.book}
    name = f"checkpoint {checkpoint.name}"
    steps: list[Step] = []

    def read(
        handler: str, block: str, extra: Mapping[str, str] | None = None, gap: str | None = None
    ) -> None:
        steps.append(
            Step(
                "CHECKPOINT",
                PREPARER,
                handler,
                f"{name} {block}",
                {**base, **(extra or {})},
                seq=checkpoint.after_seq,
                clock_at=known_at,
                gap=gap,
            )
        )

    if checkpoint.contracts:
        read(H["read_version"], "contracts", {"contracts": str(len(checkpoint.contracts))})
        if any(block.balances for block in checkpoint.contracts):
            read(H["read_balances"], "contracts.balances")
    if checkpoint.subledger:
        read(H["read_subledger"], "subledger", {"blocks": str(len(checkpoint.subledger))})
    for block in checkpoint.journals or ():
        run = block.run
        extra = {
            "entity": run.entity,
            "period_key": run.period_key,
            "mode": run.mode,
            "grain": run.grain,
            "lines": str(len(block.lines)),
        }
        # The run itself is a step of phase JOURNAL in the timeline (``journal_run_steps``); the
        # checkpoint reads the lines that step kept.
        read(H["read_journal"], f"journals {run.entity} {run.period_key} {run.mode}", extra)
    for block in checkpoint.reports or ():
        code = block.report_code
        gap = (
            None
            if code in framework.BUILDERS
            else REPORT_GAPS.get(code, f"builder {code} is not registered")
        )
        extra = {
            "report_code": code,
            "parameters": ",".join(
                f"{key}={value}" for key, value in sorted(block.parameters.items())
            ),
            "cells": str(len(block.cells)),
        }
        read(H["report_create"], f"reports {code}", extra, gap)
        read(H["report_run"], f"reports {code}", extra, gap)
        read(H["compare_cells"], f"reports {code}", extra, gap)
    if checkpoint.period_states:
        read(H["read_period"], "period_states", {"rows": str(len(checkpoint.period_states))})
    if checkpoint.groups:
        read(H["read_balances"], "groups", {"groups": str(len(checkpoint.groups))})
    if checkpoint.exceptions:
        read("", "exceptions", {"rows": str(len(checkpoint.exceptions))}, EXCEPTIONS_GAP)
    return steps


# The personas the operator invites, each with its catalogue role (DG-AK-41 rev 1.42).
INVITED: Final[tuple[tuple[str, str], ...]] = (
    (PREPARER, "revenue_accountant"),
    (APPROVER, "controller"),
    (SSP_ANALYST, "ssp_analyst"),
    (SSP_APPROVER, "ssp_approver"),
)


def _persona_steps() -> list[Step]:
    """The PERSONAS phase: who acts in the tenant is a member of it, as through the API.

    Provisioning and ``invite_user`` leave a membership INVITED (04 T-PLT-07); the API opens a
    session only for an ACTIVE one, and the database refuses the decision of an approver without
    one (DB-10, ``tg_approval_decision__sod``: EREV-TRN-001). So everyone accepts the invitation
    they were sent before they act — the provisioning admin, who is the plan's operator, before
    the first invite, and each persona right after its own.

    The invites carry the personas' catalogue roles: ``invite_user(roles=…)`` submits one
    ROLE_ASSIGNMENT request per role and rule AUTO-BOOTSTRAP approves it at submission (04 §14.3;
    BR-PLT-02 — the operator holds tenant_admin while setup is incomplete), so the grant is
    active; a second ``assign_role`` for the same grant is refused as already held (422
    ``validation-failed``; integrated batch #4, keys-platform)."""
    steps = [Step("PERSONAS", OPERATOR, H["accept"], OPERATOR)]
    for persona, role in INVITED:
        steps.append(Step("PERSONAS", OPERATOR, H["invite"], persona, {"roles": role}))
        steps.append(Step("PERSONAS", persona, H["accept"], persona))
    return steps


def close_run_steps(loaded: LoadedKey, assembler: _Assembler) -> dict[int, list[Step]]:
    """The close runs of the plan, by the timeline item each follows (DG-AK-41 rev 1.246; item
    AK-CLOSE-RUN-STEP-1; the supervisor's rulings of 2026-10-01 on the lane's measurement).

    Where a checkpoint's blocks expect a period-end pass (``platform_runner.close_runs``: the
    oracle's own books answer them differently with the passes than without) the plan starts the
    product's close run of that entity, the checkpoint's book and that period right after the
    checkpoint's last item: ``POST /close-runs`` as the preparer, who holds ``period.close``, and
    the runner works the CLOSE_RUN job to its end (``workspace_adapter.real_invoker``). The step
    stamps ``known_at[after_seq]`` again, so the checkpoint reads after its close run. Its
    application instant is local noon of the checkpoint's as-of date in the entity's time zone,
    at least one second after the item it follows. Two checkpoints after one item share a run."""
    from support.answer_keys.platform_runner import close_runs  # local: import cycle

    zones = {entity.code: ZoneInfo(entity.time_zone) for entity in loaded.key.world.entities}
    found: dict[int, list[Step]] = {}
    planned: set[tuple[int, str, str, str]] = set()
    for checkpoint in loaded.key.checkpoints:
        after = int(checkpoint.after_seq)
        for entity, period_key in close_runs(loaded, checkpoint):
            run = (after, entity, str(checkpoint.book), period_key)
            if run in planned:
                continue
            planned.add(run)
            as_of = date.fromisoformat(str(checkpoint.as_of))
            noon = datetime.combine(as_of, time(12), tzinfo=zones[entity]).astimezone(UTC)
            at = max(noon, assembler.times[after] + timedelta(seconds=1))
            found.setdefault(after, []).append(
                Step(
                    CLOSE,
                    PREPARER,
                    H["close_run"],
                    f"close run {entity} {checkpoint.book} {period_key}",
                    {
                        "entity": entity,
                        "book": str(checkpoint.book),
                        "period_key": period_key,
                        "checkpoint": checkpoint.name,
                    },
                    seq=after,
                    clock_at=_iso(at),
                    captures_known_at=True,
                )
            )
    return found


def journal_run_steps(loaded: LoadedKey) -> dict[int, list[Step]]:
    """The journal runs of the plan, by the timeline item each follows (DG-AK-41 rev 1.263; item
    AK-JOURNAL-RUN-PLAN-1): one step per journals block, the checkpoints in the key's order and
    each checkpoint's blocks in theirs.

    The step answers its block where the checkpoint stands in the timeline — after the
    checkpoint's last item and the close run the plan runs there, before the next item — as the
    preparer, who holds ``journal.run``: it reads the run that stands for the block's entity and
    period when that run has the block's mode and grain and nothing was sealed since, and else
    cancels what stands, latest first, and creates the block's own, which the runner works
    (``workspace_adapter._journal_block``). It stamps nothing: a journal run writes
    no posting, and the checkpoint keeps the stamp its last item or close run took. Its
    application instant is set where the plan is assembled (``_at_the_latest_instant``)."""
    found: dict[int, list[Step]] = {}
    for checkpoint in loaded.key.checkpoints:
        for block in checkpoint.journals or ():
            run = block.run
            found.setdefault(int(checkpoint.after_seq), []).append(
                Step(
                    JOURNAL,
                    PREPARER,
                    H["journal_create"],
                    f"journals {run.entity} {run.period_key} {run.mode}",
                    {
                        "entity": run.entity,
                        "period_key": run.period_key,
                        "mode": run.mode,
                        "grain": run.grain,
                        "checkpoint": checkpoint.name,
                    },
                    seq=int(checkpoint.after_seq),
                )
            )
    return found


def _with_following(
    timeline: Sequence[Step], *following: Mapping[int, Sequence[Step]]
) -> list[Step]:
    """``timeline`` with the steps that follow an item right after the item's last step, in the
    order given: its close runs, then its journal runs."""
    last = {step.seq: index for index, step in enumerate(timeline) if step.seq is not None}
    merged: list[Step] = []
    for index, step in enumerate(timeline):
        merged.append(step)
        if step.seq is not None and last[step.seq] == index:
            for steps in following:
                merged.extend(steps.get(step.seq, ()))
    return merged


def _at_the_latest_instant(steps: Sequence[Step]) -> list[Step]:
    """``steps`` with each journal run at the latest application instant of any step before it.

    A journal run covers the seals whose ``sealed_at`` — the application clock's — is at or
    before its cutoff, and the step gives no cutoff: the command takes the clock of the step. At
    the latest instant so far every seal that exists is covered, also when a close run's noon
    lies after the item that follows it; a seal a later item writes does not exist yet."""
    placed: list[Step] = []
    latest: str | None = None
    for step in steps:
        if step.phase == JOURNAL:
            step = replace(step, clock_at=latest)
        elif step.clock_at is not None and (latest is None or step.clock_at > latest):
            latest = step.clock_at  # one format, UTC to the second: text order is time order
        placed.append(step)
    return placed


def plan(loaded: LoadedKey) -> CommandPlan:
    """The command plan of one platform key (DG-AK-41), refused for engine keys."""
    key = loaded.key
    if key.runner != "platform":
        raise ValueError(f"{key.id}: runner {key.runner!r} is not planned here")
    assembler = _Assembler(loaded)
    steps: list[Step] = [
        Step("RUNNER", SYSTEM, RUNNER, key.id, {"keys": "PHASES §8.2.3"}),
        Step(
            "PROVISION",
            OPERATOR,
            H["provision"],
            f"tenant for {key.id}",
            {
                "reporting_currency": key.world.tenant.reporting_currency,
                "preset": key.world.tenant.preset,
                "database": "erev_test",
            },
            clock_at=_iso(assembler.setup_at),
        ),
        *_persona_steps(),
        # CTR-6: the API client that sends the events of an integrated source (PRD ACT-10).
        Step(
            "PERSONAS",
            OPERATOR,
            H["api_client"],
            INTEGRATION,
            {"scopes": ",".join(INTEGRATION_SCOPES)},
        ),
    ]
    steps.extend(
        _world_steps(
            key.world,
            key.books,
            effective_from=_iso(assembler.policy_effective_from),
            calendar_years=(
                min(int(key.world.periods.from_[:4]), assembler.world_start.year),
                max(int(key.world.periods.to[:4]), assembler.calendar_end.year),
            ),
        )
    )
    # FOLL-1: contract configuration follows its booking. A close run follows the last item of
    # the checkpoint whose blocks expect it, and the journal runs of a checkpoint's blocks follow
    # that.
    steps.extend(
        _with_following(
            _timeline_steps(assembler),
            close_run_steps(loaded, assembler),
            journal_run_steps(loaded),
        )
    )
    steps = _at_the_latest_instant(steps)
    for checkpoint in key.checkpoints:
        steps.extend(_checkpoint_steps(assembler, checkpoint))
    return CommandPlan(key.id, loaded.sha256, tuple(steps))

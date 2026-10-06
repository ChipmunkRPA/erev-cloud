"""DG-ARC-08 registry completeness (dev-guide §6.8, DG-KRN-APR-05, DG-KRN-JOB-01, DG-KRN-JOB-10;
PHASES §5.3, BS-D-07; BUILD_SPEC PLF-9, PLF-10, PLF-14).

``PENDING_JOB_HANDLERS`` names the E-14 kinds whose handlers later phases build,
``erev_api.approvals.subjects.PENDING_SUBJECTS`` the E-08 subject types whose specs later phases
build, and ``erev_api.events.outbox.PENDING_OUTBOX_HANDLERS`` the E-70 topics whose handlers later
phases build, each with its PHASES §5.3 phase code. An item that builds a handler or a spec removes
its entry in the same commit (BUILD_SPEC XR-13), and GATE-SOP requires every tuple to be empty.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import erev_api.worker  # noqa: F401  (imports every handler module)
from erev_api.approvals.subjects import PENDING_SUBJECTS, SUBJECTS
from erev_api.enums import ApprovalSubjectType, ContractEventType, JobKind, OutboxTopic
from erev_api.events import outbox, payloads
from erev_api.jobs import registry
from pydantic import BaseModel

ROOT: Final = Path(__file__).resolve().parents[3]
ARCHITECTURE: Final = ROOT / "docs" / "05-ARCHITECTURE.md"
PHASES: Final = ROOT / "docs" / "build-spec" / "PHASES.md"
_LITERAL: Final = re.compile(r"`([A-Z][A-Z0-9_]*)`")
# PHASES §5.3 columns: phase, E-08 subjects, E-14 job kinds, E-70 outbox topics.
_SUBJECT_COLUMN: Final = 1
_JOB_COLUMN: Final = 2
_OUTBOX_COLUMN: Final = 3

PENDING_JOB_HANDLERS: tuple[tuple[str, str], ...] = (
    ("AI_TASK", "AIX"),
    ("DEAL_PREVIEW", "FCS"),
    ("EVIDENCE_PACK", "RPS"),
    ("FORECAST_RUN", "FCS"),
    ("REPLAY_VERIFY", "SOP"),
)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def execution_profile_queues(text: str) -> dict[str, str]:
    """05 §5.6 "Execution profiles (E-14)": job kind → queue."""
    block = text.split("Execution profiles (E-14):", 1)[1].split("Queues are exactly", 1)[0]
    queues: dict[str, str] = {}
    for line in block.splitlines():
        cells = _cells(line)
        if len(cells) >= 2 and cells[0].startswith("`"):
            for kind in _LITERAL.findall(cells[0]):
                queues[kind] = cells[1].strip("`")
    return queues


def registry_phases(text: str, column: int) -> dict[str, str]:
    """PHASES §5.3: literal of ``column`` → the phase that builds it."""
    block = text.split("### 5.3 Registries and provisioning seed", 1)[1].split("### 5.4", 1)[0]
    phases: dict[str, str] = {}
    for line in block.splitlines():
        cells = _cells(line)
        if len(cells) > column and re.fullmatch(r"[A-Z]{3}", cells[0]):
            for literal in _LITERAL.findall(cells[column]):
                phases[literal] = cells[0]
    return phases


def job_kind_phases(text: str) -> dict[str, str]:
    """PHASES §5.3: job kind → the phase that builds its handler."""
    return registry_phases(text, _JOB_COLUMN)


def pending_findings(
    name: str,
    *,
    literals: set[str],
    built: set[str],
    pending: Sequence[tuple[str, str]],
    phases: Mapping[str, str],
) -> list[str]:
    """The findings shared by every ``PENDING_<REGISTRY>`` tuple (BS-D-07)."""
    waiting = [literal for literal, _ in pending]
    findings: list[str] = []
    if len(set(waiting)) != len(waiting):
        findings.append(f"{name} repeats a literal")
    findings += [
        f"{literal} is registered and pending" for literal in sorted(built.intersection(waiting))
    ]
    uncovered = literals - built - set(waiting)
    if uncovered:
        findings.append(
            f"literals without a registration or {name} entry: " + ", ".join(sorted(uncovered))
        )
    unknown = (built | set(waiting)) - literals
    if unknown:
        findings.append("unknown literals: " + ", ".join(sorted(unknown)))
    findings += [
        f"{literal} is built in {phases.get(literal)}, not {phase} (PHASES §5.3)"
        for literal, phase in pending
        if phases.get(literal) != phase
    ]
    return findings


def job_registry_findings(
    *,
    job_queue: Mapping[str, str],
    handlers: set[str],
    pending: Sequence[tuple[str, str]],
    profile: Mapping[str, str],
    phases: Mapping[str, str],
) -> list[str]:
    kinds = {kind.value for kind in JobKind}
    findings: list[str] = []
    if set(job_queue) != kinds:
        findings.append("JOB_QUEUE does not cover E-14 exactly")
    findings += [
        f"JOB_QUEUE[{kind}] differs from the 05 §5.6 execution profile"
        for kind in sorted(kinds)
        if job_queue.get(kind) != profile.get(kind)
    ]
    return findings + pending_findings(
        "PENDING_JOB_HANDLERS", literals=kinds, built=handlers, pending=pending, phases=phases
    )


def test_dg_arc_08_job_registries() -> None:
    profile = execution_profile_queues(ARCHITECTURE.read_text(encoding="utf-8"))
    phases = job_kind_phases(PHASES.read_text(encoding="utf-8"))
    # PERIOD_OPEN_REDIRTY (item CLO-LOCK-OPEN-REDIRTY-1; 04 rev 1.164; PHASES rev 1.5)
    assert len(profile) == len(phases) == 27
    job_queue = {kind.value: queue for kind, queue in registry.JOB_QUEUE.items()}
    handlers = {kind.value for kind in registry.HANDLERS}

    def findings(**changes: object) -> list[str]:
        values: dict[str, object] = {
            "job_queue": job_queue,
            "handlers": handlers,
            "pending": PENDING_JOB_HANDLERS,
            "profile": profile,
            "phases": phases,
        }
        values.update(changes)
        return job_registry_findings(**values)  # type: ignore[arg-type]

    assert findings() == []
    assert list(PENDING_JOB_HANDLERS) == sorted(PENDING_JOB_HANDLERS)

    # Every rule can fail.
    assert findings(job_queue={**job_queue, "AI_TASK": "compute"}) == [
        "JOB_QUEUE[AI_TASK] differs from the 05 §5.6 execution profile"
    ]
    without_sync = {kind: queue for kind, queue in job_queue.items() if kind != "SYNC_RUN"}
    assert findings(job_queue=without_sync) == [
        "JOB_QUEUE does not cover E-14 exactly",
        "JOB_QUEUE[SYNC_RUN] differs from the 05 §5.6 execution profile",
    ]
    assert findings(pending=PENDING_JOB_HANDLERS[1:]) == [
        "literals without a registration or PENDING_JOB_HANDLERS entry: AI_TASK"
    ]
    assert findings(handlers={*handlers, "AI_TASK"}) == ["AI_TASK is registered and pending"]
    assert findings(pending=(*PENDING_JOB_HANDLERS, ("AI_TASK", "AIX"))) == [
        "PENDING_JOB_HANDLERS repeats a literal"
    ]
    assert findings(pending=(("AI_TASK", "PLF"), *PENDING_JOB_HANDLERS[1:])) == [
        "AI_TASK is built in AIX, not PLF (PHASES §5.3)"
    ]


def test_dg_arc_08_subjects() -> None:
    phases = registry_phases(PHASES.read_text(encoding="utf-8"), _SUBJECT_COLUMN)
    literals = {subject.value for subject in ApprovalSubjectType}
    # 04 rev 1.72: MIGRATION_SSP_REPLAY; rev 1.142: EVIDENCE_SHRED (PHASES rev 1.4, SOP row)
    assert len(literals) == 32
    assert set(phases) == literals
    registered = {subject.value for subject in SUBJECTS}

    def findings(**changes: object) -> list[str]:
        values: dict[str, object] = {
            "literals": literals,
            "built": registered,
            "pending": PENDING_SUBJECTS,
            "phases": phases,
        }
        values.update(changes)
        return pending_findings("PENDING_SUBJECTS", **values)  # type: ignore[arg-type]

    # SUBJECTS and PENDING_SUBJECTS are disjoint and together equal E-08.
    assert findings() == []
    assert registered.isdisjoint(subject for subject, _ in PENDING_SUBJECTS)
    assert registered | {subject for subject, _ in PENDING_SUBJECTS} == literals
    assert list(PENDING_SUBJECTS) == sorted(PENDING_SUBJECTS)

    # Every rule can fail.
    first, phase = PENDING_SUBJECTS[0]
    assert findings(pending=PENDING_SUBJECTS[1:]) == [
        f"literals without a registration or PENDING_SUBJECTS entry: {first}"
    ]
    assert findings(built=registered | {first}) == [f"{first} is registered and pending"]
    assert findings(pending=(*PENDING_SUBJECTS, (first, phase))) == [
        "PENDING_SUBJECTS repeats a literal"
    ]
    assert findings(pending=((first, "SOP"), *PENDING_SUBJECTS[1:])) == [
        f"{first} is built in {phase}, not SOP (PHASES §5.3)"
    ]
    assert findings(built=registered | {"PAYMENT_RUN"}) == ["unknown literals: PAYMENT_RUN"]


def test_dg_arc_08_outbox_handlers() -> None:
    phases = registry_phases(PHASES.read_text(encoding="utf-8"), _OUTBOX_COLUMN)
    literals = {topic.value for topic in OutboxTopic}
    assert len(literals) == 4
    assert set(phases) == literals
    registered = {topic.value for topic in outbox.HANDLERS}

    def findings(**changes: object) -> list[str]:
        values: dict[str, object] = {
            "literals": literals,
            "built": registered,
            "pending": outbox.PENDING_OUTBOX_HANDLERS,
            "phases": phases,
        }
        values.update(changes)
        return pending_findings("PENDING_OUTBOX_HANDLERS", **values)  # type: ignore[arg-type]

    # HANDLERS and PENDING_OUTBOX_HANDLERS are disjoint and together equal E-70.
    assert findings() == []
    pending = dict(outbox.PENDING_OUTBOX_HANDLERS)
    assert registered.isdisjoint(pending)
    assert registered | set(pending) == literals
    # DIN-12 registered the last handler (``domain.integrations.outbox``): nothing is pending.
    assert pending == {}
    assert registered == {"EMAIL", "JOURNAL_EXPORT", "SYNC_REQUEST", "WEBHOOK"}
    assert list(outbox.PENDING_OUTBOX_HANDLERS) == sorted(outbox.PENDING_OUTBOX_HANDLERS)

    # Every rule can fail.
    assert findings(built={"EMAIL", "JOURNAL_EXPORT", "WEBHOOK"}) == [
        "literals without a registration or PENDING_OUTBOX_HANDLERS entry: SYNC_REQUEST"
    ]
    assert findings(pending=(("SYNC_REQUEST", "DIN"),)) == [
        "SYNC_REQUEST is registered and pending"
    ]
    assert findings(built={"EMAIL", "JOURNAL_EXPORT"}) == [
        "literals without a registration or PENDING_OUTBOX_HANDLERS entry: SYNC_REQUEST, WEBHOOK"
    ]
    assert findings(
        built={"EMAIL", "JOURNAL_EXPORT", "WEBHOOK"}, pending=(("SYNC_REQUEST", "PLF"),)
    ) == ["SYNC_REQUEST is built in DIN, not PLF (PHASES §5.3)"]


# BUILD_SPEC PLF-30: FND and PLF are complete, so no pending entry may name them.
BUILT_PHASES: Final = frozenset({"FND", "PLF"})


def early_phase_findings(
    registries: Mapping[str, Sequence[tuple[str, str]]], plf_literals: Mapping[str, set[str]]
) -> list[str]:
    """Pending entries naming a built phase, and PLF literals of PHASES §5.3 still pending."""
    findings: list[str] = []
    for name, pending in registries.items():
        findings += [
            f"{name} entry {literal} names phase {phase}"
            for literal, phase in pending
            if phase in BUILT_PHASES
        ]
        waiting = sorted(plf_literals[name].intersection(literal for literal, _ in pending))
        if waiting:
            findings.append(f"{name} still holds PLF literals: " + ", ".join(waiting))
    return findings


def test_dg_arc_08_pending_entries_name_later_phases() -> None:
    text = PHASES.read_text(encoding="utf-8")
    columns = {
        "PENDING_SUBJECTS": _SUBJECT_COLUMN,
        "PENDING_JOB_HANDLERS": _JOB_COLUMN,
        "PENDING_OUTBOX_HANDLERS": _OUTBOX_COLUMN,
    }
    registries: dict[str, Sequence[tuple[str, str]]] = {
        "PENDING_SUBJECTS": PENDING_SUBJECTS,
        "PENDING_JOB_HANDLERS": PENDING_JOB_HANDLERS,
        "PENDING_OUTBOX_HANDLERS": outbox.PENDING_OUTBOX_HANDLERS,
    }
    plf = {
        name: {
            literal for literal, phase in registry_phases(text, column).items() if phase == "PLF"
        }
        for name, column in columns.items()
    }
    assert plf == {
        "PENDING_SUBJECTS": {"ROLE_CHANGE", "ROLE_ASSIGNMENT", "SOD_EXCEPTION", "SUPPORT_GRANT"},
        "PENDING_JOB_HANDLERS": {
            "AUDIT_CHAIN_VERIFY",
            "OUTBOX_RELAY",
            "WEBHOOK_DELIVERY",
            "EMAIL_DELIVERY",
            "RETENTION_SWEEP",
        },
        "PENDING_OUTBOX_HANDLERS": {"WEBHOOK", "EMAIL"},
    }
    assert early_phase_findings(registries, plf) == []

    # Every rule can fail.
    job_plf = {**registries, "PENDING_JOB_HANDLERS": (("AUDIT_CHAIN_VERIFY", "PLF"),)}
    assert early_phase_findings(job_plf, plf) == [
        "PENDING_JOB_HANDLERS entry AUDIT_CHAIN_VERIFY names phase PLF",
        "PENDING_JOB_HANDLERS still holds PLF literals: AUDIT_CHAIN_VERIFY",
    ]
    topic_relabelled = {**registries, "PENDING_OUTBOX_HANDLERS": (("EMAIL", "CLO"),)}
    assert early_phase_findings(topic_relabelled, plf) == [
        "PENDING_OUTBOX_HANDLERS still holds PLF literals: EMAIL"
    ]
    subject_fnd = {**registries, "PENDING_SUBJECTS": (("PERIOD_LOCK", "FND"),)}
    assert early_phase_findings(subject_fnd, plf) == [
        "PENDING_SUBJECTS entry PERIOD_LOCK names phase FND"
    ]


def payload_findings(
    registry_map: Mapping[tuple[ContractEventType, int], type[BaseModel]],
    latest: Mapping[ContractEventType, int],
) -> list[str]:
    """DG-ARC-08 for ``PAYLOADS`` (DG-KRN-EVT-03): versions 1 to latest of every E-03 value, each
    model named ``<PascalCase>V<n>``, and nothing else (BS-D-07: complete when created)."""
    findings: list[str] = []
    expected = {
        (event_type, version)
        for event_type in ContractEventType
        for version in range(1, latest.get(event_type, 0) + 1)
    }
    missing = sorted(
        f"{event_type.value} V{version}" for event_type, version in expected - set(registry_map)
    )
    if missing or set(latest) != set(ContractEventType):
        findings.append("PAYLOADS misses: " + ", ".join(missing or ["a LATEST_SCHEMA_VERSION"]))
    extra = sorted(
        f"{event_type.value} V{version}" for event_type, version in set(registry_map) - expected
    )
    if extra:
        findings.append(
            "PAYLOADS holds versions without LATEST_SCHEMA_VERSION: " + ", ".join(extra)
        )
    misnamed = sorted(
        model.__name__
        for (event_type, version), model in registry_map.items()
        if model.__name__ != payloads.model_name(event_type, version)
    )
    if misnamed:
        findings.append("payload models misnamed: " + ", ".join(misnamed))
    return findings


def test_payloads_cover_every_event_type() -> None:
    # BUILD_SPEC CTR-1: PAYLOADS holds version 1 of each of the 30 E-03 values, from CONTRACT_BOOKED
    # to REGROUPED — and, since 04 rev 1.61 (D-98 candidate 127; DG-KRN-EVT-03), version 2 of
    # OPENING_BALANCE_ESTABLISHED, the only later version.
    event_types = list(ContractEventType)
    assert len(event_types) == 30
    assert (event_types[0], event_types[-1]) == (
        ContractEventType.CONTRACT_BOOKED,
        ContractEventType.REGROUPED,
    )
    opening = ContractEventType.OPENING_BALANCE_ESTABLISHED
    assert set(payloads.PAYLOADS) == {(event_type, 1) for event_type in event_types} | {
        (opening, 2)
    }
    assert dict(payloads.LATEST_SCHEMA_VERSION) == {**dict.fromkeys(event_types, 1), opening: 2}
    assert payloads.PAYLOADS[(opening, 2)].__name__ == "OpeningBalanceEstablishedV2"
    assert set(payloads.UPCASTS) == {(opening, 1)}
    assert payloads.PAYLOADS[(ContractEventType.CONTRACT_BOOKED, 1)].__name__ == "ContractBookedV1"
    assert payloads.PAYLOADS[(ContractEventType.REGROUPED, 1)].__name__ == "RegroupedV1"
    assert payload_findings(payloads.PAYLOADS, payloads.LATEST_SCHEMA_VERSION) == []

    # Every rule can fail.
    without_regrouped = {
        key: model
        for key, model in payloads.PAYLOADS.items()
        if key[0] is not ContractEventType.REGROUPED
    }
    assert payload_findings(without_regrouped, payloads.LATEST_SCHEMA_VERSION) == [
        "PAYLOADS misses: REGROUPED V1"
    ]
    raised = {**payloads.LATEST_SCHEMA_VERSION, ContractEventType.REGROUPED: 2}
    assert payload_findings(payloads.PAYLOADS, raised) == ["PAYLOADS misses: REGROUPED V2"]
    lowered = {**payloads.LATEST_SCHEMA_VERSION, ContractEventType.REGROUPED: 0}
    assert payload_findings(payloads.PAYLOADS, lowered) == [
        "PAYLOADS holds versions without LATEST_SCHEMA_VERSION: REGROUPED V1"
    ]
    swapped = {
        **payloads.PAYLOADS,
        (ContractEventType.DELIVERY_RECORDED, 1): payloads.ReturnRecordedV1,
    }
    assert payload_findings(swapped, payloads.LATEST_SCHEMA_VERSION) == [
        "payload models misnamed: ReturnRecordedV1"
    ]

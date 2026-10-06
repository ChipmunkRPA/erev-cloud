"""The month-24 close window (dev-guide DG-PERF-02 (2); 05 PERF-01, PERF-50; 04 API-R-38 to
API-R-40). Pure parts (unit-tested): step seconds from ``close_run.steps``, terminal statuses, the
window's wall time. The orchestration drives the documented routes and is NOT RUN in the lane.

Dependency (recorded in the lane record): ``POST /close-runs`` (API-R-39), ``POST
/journal-batches/{id}/acknowledge`` (API-R-38, CLO-14 / CLO-15) and ``POST
/reconciliations/{id}/attach-trial-balance`` (API-R-40) are documented in 04 §15.3 and not yet on
main at this revision; the paths are constants below so the harness re-binds without edits
elsewhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Final

from perf.support.client import PerfClient

CLOSE_RUNS: Final = "/close-runs"
JOURNAL_RUNS: Final = "/journal-runs"
JOURNAL_BATCHES: Final = "/journal-batches"
RECONCILIATIONS: Final = "/reconciliations"
APPROVALS: Final = "/approvals"
PERIOD_KEY: Final = "FY2026-P12"
BOOK: Final = "ASC606"
ENTITIES: Final = ("VOL-DE", "VOL-UK", "VOL-US")  # entity-code order (DG-PERF-02)
CLOSE_LIMIT_SECONDS: Final = 600.0
POLL_EVERY: Final = 2.0
TERMINAL_OK: Final = frozenset({"COMPLETED", "SUCCEEDED", "DONE"})
TERMINAL_FAILED: Final = frozenset({"FAILED", "CANCELLED", "PROBLEM"})
FREEZE_STEP: Final = "DATASET_FREEZE"


@dataclass(frozen=True, slots=True)
class RouteBinding:
    """A route the harness drives: BOUND to a governed request schema (cited), or BLOCKED on the
    owning close item, in which case the harness refuses by name before posting anything (Q5
    ruling: no guessed bodies)."""

    method: str
    path: str
    status: str  # "bound" | "blocked"
    clause: str
    blocked_on: str | None = None


ROUTES: Final[Mapping[str, RouteBinding]] = {
    "close_runs_multi_entity": RouteBinding(
        "POST",
        f"{CLOSE_RUNS}/multi-entity",
        "bound",
        "04 §16.8 Close run commands (API-R-39; CLO-21): entity_codes (R; 1 to 50), book (O), "
        "period_key (R), cutoff_known_at (O) → 200 {results: [{entity_code, close_run_id, job_id, "
        "problem}]}; each entity starts in entity_codes order as POST /close-runs would",
    ),
    "close_run_read": RouteBinding(
        "GET",
        f"{CLOSE_RUNS}/{{id}}",
        "bound",
        "04 API-R-39 (CLO-19): the close run's T-CLS-01 status and steps (started_at, finished_at; "
        "05 PERF-50) are read, nothing is posted",
    ),
    "journal_run_submit": RouteBinding(
        "POST", f"{JOURNAL_RUNS}/{{id}}/submit", "bound", "04 §16.7: comment (O) (API-R-38; CLO-11)"
    ),
    "journal_run_export": RouteBinding(
        "POST",
        f"{JOURNAL_RUNS}/{{id}}/export",
        "bound",
        "04 §16.7: adapter (O; default the tenant's GL connection or CSV) (API-R-38; CLO-13)",
    ),
    "journal_batch_acknowledge": RouteBinding(
        "POST",
        f"{JOURNAL_BATCHES}/{{id}}/acknowledge",
        "bound",
        "04 §16.7 API-S-PostingAck: gl_document_id (R), gl_posted_date (O), message (O) → 201 "
        "(API-R-38; route lands with CLO-14)",
    ),
    "close_run_single": RouteBinding(
        "POST",
        CLOSE_RUNS,
        "blocked",
        "04 API-R-39 names the route; §16.8 defines the multi-entity command's request only",
        blocked_on="F-CLO CLO-19 (close run orchestration)",
    ),
    "attach_trial_balance": RouteBinding(
        "POST",
        f"{RECONCILIATIONS}/{{id}}/attach-trial-balance",
        "blocked",
        "04 API-R-40 names the route; no request schema in 04 §16 (BUILD_SPEC CLO-17 describes an "
        "uploaded CSV of account, currency and amount without members)",
        blocked_on="F-CLO CLO-17 (subledger-to-GL reconciliation, attach_trial_balance)",
    ),
}


class BlockedRoute(RuntimeError):
    """The harness refuses a route whose request schema is not governed text (Q5 ruling)."""


# Every route run_close_window drives, in first-use order; preflight() refuses the window by name
# before its first request when any of them is BLOCKED (Codex 2353 §4: a preflight, not a
# refusal after earlier supported operations).
WINDOW_ROUTES: Final[tuple[str, ...]] = (
    "close_runs_multi_entity",
    "close_run_read",
    "journal_run_submit",
    "journal_run_export",
    "journal_batch_acknowledge",
    "attach_trial_balance",
)


def preflight(names: Sequence[str] = WINDOW_ROUTES) -> tuple[RouteBinding, ...]:
    """``require_bound`` for every route of the window before anything is posted."""
    return tuple(require_bound(name) for name in names)


def require_bound(name: str) -> RouteBinding:
    binding = ROUTES[name]
    if binding.status != "bound":
        raise BlockedRoute(
            f"{binding.method} {binding.path} is BLOCKED on {binding.blocked_on}: {binding.clause}"
        )
    return binding


def multi_entity_body(entities: Sequence[str]) -> dict[str, Any]:
    """The 04 §16.8 request, exactly its members (required and the optional book)."""
    return {"entity_codes": list(entities), "book": BOOK, "period_key": PERIOD_KEY}


def acknowledge_body(batch_id: str) -> dict[str, Any]:
    """API-S-PostingAck (04 §16.7): gl_document_id (R), message (O); gl_posted_date left to the
    server default."""
    return {"gl_document_id": f"PERF-{batch_id[:8]}", "message": "perf harness acknowledgement"}


def parse_instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def step_seconds(steps: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Seconds per step from ``close_run.steps`` (T-CLS-01 ``started_at`` / ``finished_at``; 05
    PERF-50); a step without both instants is skipped."""
    out: dict[str, float] = {}
    for step in steps:
        started, finished = (
            parse_instant(step.get("started_at")),
            parse_instant(step.get("finished_at")),
        )
        name = str(step.get("step") or step.get("name") or "")
        if name and started is not None and finished is not None:
            out[name] = round((finished - started).total_seconds(), 3)
    return out


def is_terminal(status: str) -> bool:
    return status.upper() in TERMINAL_OK | TERMINAL_FAILED


def step_problem(steps: Sequence[Mapping[str, Any]]) -> str | None:
    """The first step that ended with a problem (its ``status_code`` / ``problem``), else None."""
    for step in steps:
        if step.get("problem") or str(step.get("state", "")).upper() in {"FAILED", "PROBLEM"}:
            return str(step.get("step") or step.get("name") or "?")
    return None


@dataclass
class EntityWindow:
    entity: str
    first_run_id: str = ""
    second_run_id: str = ""
    first_pass_seconds: float = 0.0
    second_pass_seconds: float = 0.0
    steps_first: dict[str, float] = field(default_factory=dict)
    steps_second: dict[str, float] = field(default_factory=dict)
    groups_recomputed: int = 0
    journal_runs: list[str] = field(default_factory=list)
    batches_acknowledged: int = 0
    tie_out_difference: str | None = None
    trial_balance_csv: str = ""


@dataclass
class CloseWindow:
    started_at: str
    finished_at: str = ""
    seconds: float = 0.0
    entities: dict[str, EntityWindow] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def within_limit(self) -> bool:
        return self.seconds <= CLOSE_LIMIT_SECONDS and not self.problems


def _start_close_runs(client: PerfClient, entities: Sequence[str]) -> dict[str, str]:
    """``POST /close-runs/multi-entity`` (bound): entity code → close run id; a per-entity
    ``problem`` is a refusal the window records."""
    require_bound("close_runs_multi_entity")
    body = client.post(
        f"{CLOSE_RUNS}/multi-entity",
        multi_entity_body(entities),
        idempotency_key=f"perf-close-{PERIOD_KEY}-{perf_counter_ns_hex()}",
    )
    started: dict[str, str] = {}
    for result in body.get("results", []):
        if result.get("problem"):
            raise RuntimeError(f"{result.get('entity_code')}: {result['problem']}")
        started[str(result["entity_code"])] = str(result["close_run_id"])
    return started


def perf_counter_ns_hex() -> str:
    return format(int(perf_counter() * 1e9), "x")


def _wait_close_run(client: PerfClient, run_id: str) -> Mapping[str, Any]:
    require_bound("close_run_read")
    return client.poll(
        f"{CLOSE_RUNS}/{run_id}",
        lambda body: is_terminal(str(body.get("status", ""))),
        every=POLL_EVERY,
    )


def _approve_pending(
    controller: PerfClient, reviewer: PerfClient, subject_type: str, subject_id: str
) -> None:
    """Approve every pending request of the subject as the reviewer (REQ-PLT-014 hashes)."""
    pending = reviewer.get(
        APPROVALS, {"status": "PENDING", "subject_type": subject_type, "subject_id": subject_id}
    )
    for item in pending.get("items", []):
        reviewer.post(
            f"{APPROVALS}/{item['id']}/approve",
            {
                "subject_content_sha256": item["subject_content_sha256"],
                "impact_preview_sha256": item.get("impact_preview_sha256"),
                "comment": "perf harness",
            },
        )


def without_lines(run: Mapping[str, Any]) -> bool:
    """A journal run that states no line (API-S-JournalRun ``totals.line_count`` 0): the run of
    an entity without activity in the period. It is the period's run as it stands — there is
    nothing in it to approve or export, its submission is refused (409; item JRN-EMPTY-RUN-1) —
    so the harness leaves it. A run that does not state its count is not taken for one. Pure."""
    totals = run.get("totals")
    return isinstance(totals, Mapping) and totals.get("line_count") == 0


def _finish_journal_runs(
    accountant: PerfClient,
    controller: PerfClient,
    reviewer: PerfClient,
    window: EntityWindow,
    close_run_id: str,
) -> None:
    """DG-PERF-02 (2) between the passes: the accountant submits every journal run of the close
    run (journal.run), the reviewer approves it, the controller exports its batches through the
    CSV adapter and acknowledges every exported batch (journal.export); the trial balance CSV is
    built from the batches and attached to the GL tie-out reconciliation. A run without lines is
    named among the window's runs and left as the close run calculated it (``without_lines``)."""
    runs = controller.get(
        JOURNAL_RUNS, {"entity": window.entity, "period": PERIOD_KEY, "book": BOOK}
    )
    batches_csv: list[str] = []
    for run in runs.get("items", []):
        run_id = str(run["id"])
        window.journal_runs.append(run_id)
        if without_lines(run):
            continue
        if str(run.get("state", "")).upper() in {"CALCULATED", "DRAFT"}:
            require_bound("journal_run_submit")
            accountant.post(
                f"{JOURNAL_RUNS}/{run_id}/submit", {"comment": "perf harness month-24 close"}
            )
        _approve_pending(controller, reviewer, "JOURNAL_RUN", run_id)
        require_bound("journal_run_export")
        controller.post(f"{JOURNAL_RUNS}/{run_id}/export", {"adapter": "CSV"})
        for batch in controller.get(f"{JOURNAL_RUNS}/{run_id}/batches").get("items", []):
            batch_id = str(batch["id"])
            download = controller.get_response(f"{JOURNAL_BATCHES}/{batch_id}/download")
            if download.status_code < 400:
                batches_csv.append(download.text)
            require_bound("journal_batch_acknowledge")
            controller.post(f"{JOURNAL_BATCHES}/{batch_id}/acknowledge", acknowledge_body(batch_id))
            window.batches_acknowledged += 1
    # The trial balance CSV is built (pure, unit-tested) but its attach route has no governed
    # request schema yet: the harness refuses by name here rather than posting a guessed body
    # (Q5 ruling).
    window.trial_balance_csv = trial_balance_csv(batches_csv)
    require_bound("attach_trial_balance")


def trial_balance_csv(batches: Sequence[str]) -> str:
    """The trial balance built from the exported batch CSVs: one row per account with the summed
    debit and credit columns (a pure aggregation over the batch lines; unit-tested)."""
    totals: dict[str, tuple[float, float]] = {}
    for text in batches:
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        header = [cell.strip().lower() for cell in lines[0].split(",")]
        try:
            account, debit, credit = (
                header.index("account"),
                header.index("debit"),
                header.index("credit"),
            )
        except ValueError:
            continue
        for line in lines[1:]:
            cells = line.split(",")
            if len(cells) <= max(account, debit, credit):
                continue
            d, c = totals.get(cells[account].strip(), (0.0, 0.0))
            totals[cells[account].strip()] = (
                d + float(cells[debit] or 0),
                c + float(cells[credit] or 0),
            )
    rows = ["account,debit,credit"] + [
        f"{acct},{d:.2f},{c:.2f}" for acct, (d, c) in sorted(totals.items())
    ]
    return "\n".join(rows) + "\n"


def run_close_window(
    accountant: PerfClient,
    controller: PerfClient,
    reviewer: PerfClient,
    *,
    entities: Sequence[str] = ENTITIES,
) -> CloseWindow:
    """The measured window (DG-PERF-02 (2)): first close run per entity (the controller,
    period.close), journal runs finished (accountant submits, reviewer approves, controller
    exports and acknowledges), second close run per entity; wall time from the first 202 to the
    last second-pass ``DATASET_FREEZE`` completion."""
    from perf.support.client import utc_now

    preflight()  # a BLOCKED route refuses the whole window before its first request
    window = CloseWindow(started_at=utc_now())
    t0 = perf_counter()
    for entity in entities:
        window.entities[entity] = EntityWindow(entity)
    # First pass: one command starts every entity in entity-code order (04 §16.8), executed
    # concurrently by the perf workers.
    for entity, run_id in _start_close_runs(controller, entities).items():
        window.entities[entity].first_run_id = run_id
    for entity in entities:
        ew = window.entities[entity]
        t_pass = perf_counter()
        body = _wait_close_run(controller, ew.first_run_id)
        ew.first_pass_seconds = round(perf_counter() - t_pass, 3)
        ew.steps_first = step_seconds(body.get("steps", []))
        ew.groups_recomputed = int(body.get("counts", {}).get("groups_recomputed", 0))
        problem = step_problem(body.get("steps", []))
        if problem or str(body.get("status", "")).upper() in TERMINAL_FAILED:
            window.problems.append(f"{entity} first pass: {problem or body.get('status')}")
    for entity in entities:
        _finish_journal_runs(
            accountant,
            controller,
            reviewer,
            window.entities[entity],
            window.entities[entity].first_run_id,
        )
    # Second pass: the observation steps record the export, acknowledgement and tie-out.
    for entity, run_id in _start_close_runs(controller, entities).items():
        window.entities[entity].second_run_id = run_id
    for entity in entities:
        ew = window.entities[entity]
        t_pass = perf_counter()
        body = _wait_close_run(controller, ew.second_run_id)
        ew.second_pass_seconds = round(perf_counter() - t_pass, 3)
        ew.steps_second = step_seconds(body.get("steps", []))
        problem = step_problem(body.get("steps", []))
        if problem or str(body.get("status", "")).upper() in TERMINAL_FAILED:
            window.problems.append(f"{entity} second pass: {problem or body.get('status')}")
        if FREEZE_STEP not in ew.steps_second:
            window.problems.append(f"{entity} second pass: {FREEZE_STEP} not completed")
    window.seconds = round(perf_counter() - t0, 3)
    window.finished_at = utc_now()
    return window

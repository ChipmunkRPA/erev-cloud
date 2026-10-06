"""The perf report accumulator (dev-guide DG-PERF-05, DG-MK-perf step 3; 05 PERF-05): close seconds
per entity and step, p95 per DG-PERF-03 endpoint, the PERF-30 mix results, the sandbox code and the
snapshot id, written to ``.run/reports/perf/report.json``. PRF-6 adds the host facts, the manifest
hash comparison and the baseline warning."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from perf.support.client import utc_now


@dataclass
class PerfReport:
    command: str
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    manifest_sha256: str = ""
    sandbox_tenant_id: str = ""
    snapshot_id: str = ""
    close: dict[str, Any] = field(default_factory=dict)
    latency: dict[str, Any] = field(default_factory=dict)
    mix: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def document(self) -> dict[str, Any]:
        body = asdict(self)
        body["finished_at"] = self.finished_at or utc_now()
        return body

    def with_sandbox(self, restored: Any) -> None:
        """The restored sandbox's identity AND its notes (the SANDBOX_RESET wait, …) — the notes
        reach the report (Codex 2353 §3)."""
        self.sandbox_tenant_id = str(restored.sandbox_tenant_id)
        self.snapshot_id = str(restored.snapshot_id)
        self.notes.extend(str(note) for note in restored.notes)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.document(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return path


def close_section(window: Any) -> dict[str, Any]:
    """The close part of the report from a ``close.CloseWindow``."""
    return {
        "seconds": window.seconds,
        "within_limit": window.within_limit,
        "started_at": window.started_at,
        "finished_at": window.finished_at,
        "problems": list(window.problems),
        "entities": {
            code: {
                "first_run_id": ew.first_run_id,
                "second_run_id": ew.second_run_id,
                "first_pass_seconds": ew.first_pass_seconds,
                "second_pass_seconds": ew.second_pass_seconds,
                "steps_first": dict(ew.steps_first),
                "steps_second": dict(ew.steps_second),
                "groups_recomputed": ew.groups_recomputed,
                "journal_runs": list(ew.journal_runs),
                "batches_acknowledged": ew.batches_acknowledged,
                "tie_out_difference": ew.tie_out_difference,
            }
            for code, ew in window.entities.items()
        },
    }


def latency_section(measurements: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: {"p95_ms": round(m.p95_ms, 3), "samples": len(m.samples_ms), "failures": m.failures}
        for name, m in measurements.items()
    }

"""The report builder contract (BUILD_SPEC RPS-2 ``Builder = Callable[[UnitOfWork, ReportParams],
ReportData]``; 04 T-RPT-01 rule 1, T-RPT-02; SCREENS_B RPT-R-01, RPT-R-09; 03 REQ-RPT-002,
REQ-SEC-006).

``ReportParams`` is what the framework resolved for one run: every parameter including defaults, the
entity scope, ``known_at``, the book, the as-of date and the lock. ``filters`` are grid filters on
the definition's "Filter" columns (SCREENS_B RPT-R-09) and the ``filters`` parameter of the reports
that declare it: a builder compares each value as a bound parameter and answers an unknown field
with 422 ``validation-failed``. A builder reads through the unit of work it is given, restricts the
population to ``entity_ids`` itself (the job principal sees every entity) and orders its rows
deterministically, so that a rerun reproduces the output.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from erev_api.domain.reports.outputs import ReportData, utc_text
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

FILTER_RULE: Final = "RPT-R-09"


BINDING_VERSION: Final = 1
ADAPTER: Final = "adapter"  # the builder re-executes against the bound sources
# Codex 2225: retained evidence must SUPPLY INPUTS to the real builder logic — a same-source rerun
# REBUILDS from the retained input rows (never a replay of the saved output).
RETAINED: Final = "retained_inputs"
# No same-source support yet: a rerun is a NEW live evaluation, labelled as such; never a
# reproduction claim (Codex 2202 / 2225; frps3c).
OPEN: Final = "open"


def _utc_text(moment: datetime) -> str:
    # Codex 2216 (A): the exact timezone-aware instant, microseconds included — a truncated cutoff
    # would exclude a version stamped inside the same second on the bound read.
    return utc_text(moment)


@dataclass(frozen=True, slots=True)
class SourceBinding:
    """The sources a LIVE run's build actually consumed (04 T-RPT-02 ``source_binding`` rev 1.55;
    ENGINE_SPEC_B S15-R-24; frps3b): the effective record cutoff it applied, the contract-version
    ids per book, the material grouping / label values its rows used (``kind → {id → value}``:
    customer segment and name per customer, product family / name / revenue category per product),
    the non-version memberships it consumed (``kind → ids``: subledger lines, journal runs, api
    clients), the input facts a retained-inputs builder consumed (``evidence``), its output row
    keys, the builder's strategy (``ADAPTER``: a rerun or explanation re-executes against these
    sources; ``RETAINED`` = ``retained_inputs``: no contract version binds the builder — a
    same-source rerun REBUILDS through the same logic from the retained evidence, never a replay
    of saved output; ``OPEN``: no source adapter yet — only the cutoff is recorded and a rerun is a
    NEW live evaluation labelled open), the source dimensions the builder's contract leaves OPEN
    (declared, never silently narrowed), the report definition version the build ran and the
    build's dataset reference (hash / format — informational: CTL-029 compares hash and totals
    and is not source-identity proof). A rerun and a cell explanation of a bound run resolve
    against this — never against today's rows (Codex 2131 / 2154 / 2202 / 2225 / 2315)."""

    cutoff: datetime
    versions: Mapping[str, tuple[UUID, ...]]
    labels: Mapping[str, Mapping[str, str | None]]
    row_keys: frozenset[str]
    strategy: str = ADAPTER
    members: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    open: tuple[str, ...] = ()
    report_version: int | None = None
    dataset: Mapping[str, Any] | None = None
    # Retained input evidence (``kind → JSON-safe value``): the pre-aggregation facts a
    # retained-inputs builder consumed, fed back to its real logic on a same-source rebuild.
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_stored(self) -> dict[str, Any]:
        return {
            "binding_version": BINDING_VERSION,
            "strategy": self.strategy,
            "report_version": self.report_version,
            "cutoff": _utc_text(self.cutoff),
            "versions": {
                book: [str(v) for v in ids] for book, ids in sorted(self.versions.items())
            },
            "labels": {
                kind: dict(sorted(values.items())) for kind, values in sorted(self.labels.items())
            },
            "members": {kind: sorted(ids) for kind, ids in sorted(self.members.items())},
            "open": list(self.open),
            "dataset": None if self.dataset is None else dict(self.dataset),
            "evidence": {kind: value for kind, value in sorted(self.evidence.items())},
            "row_keys": sorted(self.row_keys),
        }

    @classmethod
    def from_stored(cls, stored: Mapping[str, Any] | None) -> SourceBinding | None:
        if stored is None:
            return None
        if int(stored.get("binding_version", 0)) != BINDING_VERSION:
            raise ValueError(
                f"unsupported source binding_version {stored.get('binding_version')!r}"
            )
        cutoff = datetime.fromisoformat(str(stored["cutoff"]).replace("Z", "+00:00"))
        return cls(
            cutoff=cutoff,
            versions={
                str(book): tuple(UUID(str(v)) for v in ids)
                for book, ids in dict(stored.get("versions") or {}).items()
            },
            labels={
                str(kind): {
                    str(k): (None if v is None else str(v)) for k, v in dict(values).items()
                }
                for kind, values in dict(stored.get("labels") or {}).items()
            },
            row_keys=frozenset(str(k) for k in stored.get("row_keys") or ()),
            strategy=str(stored.get("strategy") or ADAPTER),
            members={
                str(kind): tuple(str(v) for v in ids)
                for kind, ids in dict(stored.get("members") or {}).items()
            },
            open=tuple(str(item) for item in stored.get("open") or ()),
            report_version=None
            if stored.get("report_version") is None
            else int(stored["report_version"]),
            dataset=None if stored.get("dataset") is None else dict(stored["dataset"]),
            evidence=dict(stored.get("evidence") or {}),
        )

    def version_ids(self, book_code: str) -> tuple[UUID, ...]:
        return tuple(self.versions.get(book_code, ()))

    def member_ids(self, kind: str) -> tuple[str, ...]:
        return tuple(self.members.get(kind, ()))

    def label(self, kind: str, key: str) -> tuple[bool, str | None]:
        """(bound?, value): whether the binding holds ``kind``/``key`` and the value it holds."""
        values = self.labels.get(kind)
        if values is None or key not in values:
            return False, None
        return True, values[key]

    def summary(self) -> dict[str, Any]:
        kind = {ADAPTER: "bound", RETAINED: "retained", OPEN: OPEN}.get(
            self.strategy, self.strategy
        )
        return {
            "bound": self.strategy != OPEN,
            "kind": kind,
            "strategy": self.strategy,
            "cutoff": self.cutoff,
            "versions": sum(len(ids) for ids in self.versions.values()),
            "labels": sum(len(values) for values in self.labels.values()),
            "members": sum(len(ids) for ids in self.members.values()),
            "rows": len(self.row_keys),
            "open": list(self.open),
        }


class SourceCollector:
    """Records the sources a LIVE build consumes — through ``tie_outs.cutoff_for`` /
    ``versions_for`` / ``label_for`` / ``record_members`` — so the framework can bind them with
    the run (S15-R-24)."""

    def __init__(self) -> None:
        self.cutoff: datetime | None = None
        self.versions: dict[str, set[UUID]] = {}
        self.labels: dict[str, dict[str, str | None]] = {}
        self.members: dict[str, set[str]] = {}
        self.evidence: dict[str, Any] = {}

    def record_cutoff(self, cutoff: datetime) -> None:
        self.cutoff = cutoff

    def record_versions(self, book_code: str, ids: Iterable[UUID]) -> None:
        self.versions.setdefault(book_code, set()).update(ids)

    def record_label(self, kind: str, key: str, value: str | None) -> None:
        self.labels.setdefault(kind, {})[key] = value

    def record_members(self, kind: str, ids: Iterable[object]) -> None:
        self.members.setdefault(kind, set()).update(str(item) for item in ids)

    def record_evidence(self, kind: str, value: Any) -> None:
        """JSON-safe retained inputs of a retained-inputs builder (Codex 2225)."""
        self.evidence[kind] = value

    def binding(
        self,
        *,
        row_keys: Sequence[str],
        strategy: str = ADAPTER,
        open: Sequence[str] = (),
        report_version: int | None = None,
        dataset: Mapping[str, Any] | None = None,
    ) -> SourceBinding:
        if self.cutoff is None:
            raise ValueError("the build consumed no cutoff: nothing to bind")
        return SourceBinding(
            cutoff=self.cutoff,
            versions={book: tuple(sorted(ids, key=str)) for book, ids in self.versions.items()},
            labels={kind: dict(values) for kind, values in self.labels.items()},
            row_keys=frozenset(str(key) for key in row_keys),
            strategy=strategy,
            members={kind: tuple(sorted(ids)) for kind, ids in self.members.items()},
            open=tuple(open),
            report_version=report_version,
            dataset=dataset,
            evidence=dict(self.evidence),
        )


@dataclass(frozen=True, slots=True)
class ReportParams:
    report_code: str
    report_version: int
    parameters: Mapping[str, Any]
    entity_ids: tuple[UUID, ...]
    known_at: datetime
    book_code: str | None = None
    as_of_date: date | None = None
    period_lock_id: UUID | None = None
    filters: Mapping[str, str] = field(default_factory=dict)
    # The run's output format: an on-screen JSON run omits sections a nonpublic election suppresses
    # (SCREENS_B RV-12; BUILD_SPEC RPS-4).
    output_format: str | None = None
    # F-RPS-CUTOFF-R1 (record §43): True for an explicit as-of read (a run created with a
    # ``known_at`` parameter) — the builders then keep the supplied cutoff (READ-1) instead of
    # L6-3-Q-19's widening to the transaction timestamp.
    historical: bool = False
    # frps3b (S15-R-24): the sources a bound run's build consumed — a rerun or a cell explanation
    # resolves against them (``tie_outs.cutoff_for`` / ``versions_for`` / ``label_for``); None for
    # a live build, which records what it consumes into ``sources`` for the framework to bind.
    binding: SourceBinding | None = None
    sources: SourceCollector | None = field(default=None, compare=False)


type Builder = Callable[[UnitOfWork, ReportParams], ReportData]


def filter_problem(name: str, message: str) -> Problem:
    """422 ``validation-failed`` on one grid filter."""
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field=f"filters.{name}", rule_id=FILTER_RULE, message=message)],
    )


def unknown_filter(name: str, allowed: Iterable[str]) -> Problem:
    return filter_problem(name, f"Filter by {', '.join(sorted(allowed))}.")

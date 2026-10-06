"""Producers other lanes own, resolved by name at the moment the close path needs them (F-CLO
preparation record ``docs/reviews/loop/prod/F-CLO-prep.md`` §16.3, §17).

The lock path of CLO-6 consumes three interfaces agreed with their owners: P4's control-execution
registry (``erev_api.controls.evidence``: ``RunRefType`` with ``PERIOD_LOCK`` and
``RECONCILIATION_RUN``, ``record_execution``; SOP-1 1b/1c, pending P2 + C1b on main), F-RPS's
snapshot dataset registry (``erev_api.domain.reports.snapshots``: ``SNAPSHOT_DATASETS`` keyed by the
E-64 literal and ``SnapshotScope``) and the EDS-6 engine module
(``erev_engine.stages.s15_disclosures.snapshots``: ``SNAPSHOT_KINDS``, ``Encoded``,
``manifest_sha256``; GATE-EDS). Where a producer is absent on the tree the path **refuses by name**
with ``ProducerMissing`` before any write: never a stub, never a fake result. The refusal is a
``RuntimeError`` (ERR-34 at the API: nothing saved), so a lock cannot complete on a tree that lacks
its producers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Final

CONTROL_EVIDENCE: Final = "erev_api.controls.evidence"
SNAPSHOT_ENGINE: Final = "erev_engine.stages.s15_disclosures.snapshots"
SNAPSHOT_REGISTRY: Final = "erev_api.domain.reports.snapshots"
OWNER_P4: Final = "SOP-1 1b/1c, lane P4; pending P2 + C1b on main"
OWNER_EDS: Final = "EDS-6, lane F-RPS; GATE-EDS prerequisite"
OWNER_RPS: Final = (
    "lane F-RPS dataset registry (twelve of twelve builders registered — RPS-SNAP SNAP-2 adopted "
    "F-CTR's modification_register at CTR-17 slice 1 and F-CLO's manual_adjustment_register at "
    "RPS-8 RPT-18; no named dependency remains — a kind absent from the registry is still refused "
    "by name; D-98 candidate 139)"
)


class ProducerMissing(RuntimeError):
    """A producer another lane owns is not on this tree: the close path refuses by name."""

    def __init__(self, module: str, names: tuple[str, ...], owner: str, *, note: str = "") -> None:
        self.module = module
        self.names = names
        self.owner = owner
        joined = " / ".join(f"{module}.{name}" for name in names)
        tail = f"; {note}" if note else ""
        super().__init__(
            f"{joined} is not on this tree ({owner}); "
            f"the close path refuses rather than stub it{tail}"
        )


def resolve(module: str, names: tuple[str, ...], owner: str) -> tuple[Any, ...]:
    """The named symbols of ``module``; ``ProducerMissing`` naming the module or the first absent
    symbol."""
    try:
        loaded = import_module(module)
    except ImportError as exc:
        raise ProducerMissing(module, names, owner) from exc
    values: list[Any] = []
    for name in names:
        value = getattr(loaded, name, None)
        if value is None:
            raise ProducerMissing(module, (name,), owner)
        values.append(value)
    return tuple(values)


@dataclass(frozen=True, slots=True)
class ControlEvidence:
    """P4's registry: the run-reference enum and ``record_execution`` (agreed shape, record §2)."""

    run_ref_type: Any
    record_execution: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class SnapshotEngine:
    """EDS-6: the twelve E-64 kinds in order, the ``Encoded`` type and the S15-R-19 manifest."""

    kinds: tuple[str, ...]
    encoded: Any
    manifest_sha256: Callable[[Mapping[str, str]], str]


@dataclass(frozen=True, slots=True)
class SnapshotRegistry:
    """F-RPS: ``SNAPSHOT_DATASETS`` (kind → ``(uow, SnapshotScope) -> Encoded``), the scope type
    and ``SnapshotRefusal`` — the registry's refusal of one kind's freeze, carrying ``kind`` and
    ``reason``, which the lock decision answers by name (supervisor ruling R-19 (c))."""

    datasets: Mapping[str, Callable[..., Any]]
    scope: Callable[..., Any]
    refusal: type[Exception]


def control_evidence() -> ControlEvidence:
    run_ref_type, record_execution = resolve(
        CONTROL_EVIDENCE, ("RunRefType", "record_execution"), OWNER_P4
    )
    return ControlEvidence(run_ref_type=run_ref_type, record_execution=record_execution)


def snapshot_engine() -> SnapshotEngine:
    kinds, encoded, manifest = resolve(
        SNAPSHOT_ENGINE, ("SNAPSHOT_KINDS", "Encoded", "manifest_sha256"), OWNER_EDS
    )
    return SnapshotEngine(
        kinds=tuple(str(kind) for kind in kinds), encoded=encoded, manifest_sha256=manifest
    )


def snapshot_registry() -> SnapshotRegistry:
    datasets, scope, refusal = resolve(
        SNAPSHOT_REGISTRY, ("SNAPSHOT_DATASETS", "SnapshotScope", "SnapshotRefusal"), OWNER_RPS
    )
    return SnapshotRegistry(datasets=datasets, scope=scope, refusal=refusal)

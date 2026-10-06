"""``GLAdapter`` at the BUILD_SPEC DIN-14 path (05 §5.2, ADP-10 to ADP-14): the protocol, its typed
results and the ADP-12 error classes are defined in the domain port
``erev_api.domain.journals.ports`` (DG-LAY-03: adapters implement protocols of kernel or domain
modules) and re-exported here, with the chart-of-accounts reading of a ``COA_SYNC`` run
(``erev_api.domain.integrations.ports.ChartSource``; 03 REQ-INT-008) and the trial-balance
members of the port (BUILD_SPEC CLO-15, CLO-17)."""

from __future__ import annotations

from erev_api.domain.integrations.ports import ChartAccount, ChartSource, ChartValue
from erev_api.domain.journals.ports import (
    Accepted,
    AccountRef,
    AdapterCode,
    ChunkLine,
    DimensionRef,
    Duplicate,
    EntityRef,
    GLAdapter,
    GLAdapterFactory,
    GLContext,
    JournalChunk,
    PeriodRef,
    Permanent,
    PostingResult,
    Transient,
    TrialBalance,
    TrialBalanceDetail,
    TrialBalanceLine,
    ValidationResult,
)

__all__ = [
    "Accepted",
    "AccountRef",
    "AdapterCode",
    "ChartAccount",
    "ChartSource",
    "ChartValue",
    "ChunkLine",
    "DimensionRef",
    "Duplicate",
    "EntityRef",
    "GLAdapter",
    "GLAdapterFactory",
    "GLContext",
    "JournalChunk",
    "PeriodRef",
    "Permanent",
    "PostingResult",
    "Transient",
    "TrialBalance",
    "TrialBalanceDetail",
    "TrialBalanceLine",
    "ValidationResult",
]

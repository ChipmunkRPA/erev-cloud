"""``InboundAdapter`` at the BUILD_SPEC DIN-12 path: the protocol and its typed results are defined
in the domain port ``erev_api.domain.integrations.ports`` (DG-LAY-03: adapters implement protocols
of kernel or domain modules) and re-exported here."""

from __future__ import annotations

from erev_api.domain.integrations.ports import (
    ChangePage,
    Checkpoint,
    ControlTotals,
    Duplicate,
    InboundAdapter,
    InboundContext,
    NormalisedLine,
    NormalisedOrderDraft,
    NormalisedRecords,
    Notification,
    Permanent,
    SourceObject,
    Transient,
    Undeliverable,
    WebhookNotice,
)

__all__ = [
    "ChangePage",
    "Checkpoint",
    "ControlTotals",
    "Duplicate",
    "InboundAdapter",
    "InboundContext",
    "NormalisedLine",
    "NormalisedOrderDraft",
    "NormalisedRecords",
    "Notification",
    "Permanent",
    "SourceObject",
    "Transient",
    "Undeliverable",
    "WebhookNotice",
]

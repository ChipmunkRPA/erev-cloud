"""``CSV_GL``: the file general ledger adapter (05 §5.2, ADP-10, ADP-11, ADP-13, ADP-33; 03
REQ-JE-011, REQ-JE-012; BUILD_SPEC CLO-13).

A CSV export has no ERP behind it. ``post_chunk`` validates the chunk's accounts against the
workspace's chart of accounts and answers ``EXPORTED`` with the zipped CSV and JSON manifest, which
a person imports into the ledger and confirms later with its document reference (ADP-33). Chunks
are unlimited (ADP-11), nothing posted is deleted or changed (ADP-13), and a repeated external id
answers the first result (ADP-10); the file of a chunk is the same bytes on every render.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Final, Literal

from erev_api.domain.journals import export, ports

UNKNOWN_ACCOUNT: Final = "Account {code} is not in the chart of accounts."
NO_TRIAL_BALANCE: Final = "A CSV export has no general ledger to read a trial balance from."


class CsvGl:
    """One adapter per dispatch, built from the workspace's chart of accounts."""

    def __init__(self, context: ports.GLContext) -> None:
        self._chart = {account.code: account for account in context.accounts}
        self._posted: dict[str, ports.PostingResult] = {}

    @property
    def code(self) -> Literal["CSV_GL"]:
        return "CSV_GL"

    def validate_accounts(
        self, accounts: Sequence[ports.AccountRef], dimensions: Sequence[ports.DimensionRef]
    ) -> ports.ValidationResult:
        """Every account must be in the chart; a file export checks no dimension values."""
        unknown = sorted({account.code for account in accounts} - self._chart.keys())
        return ports.ValidationResult(
            errors=tuple(UNKNOWN_ACCOUNT.format(code=code) for code in unknown)
        )

    def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
        posted = self._posted.get(chunk.external_id)
        if posted is not None:
            return posted
        checked = self.validate_accounts(chunk.accounts, chunk.dimensions)
        if not checked.ok:
            raise ports.Permanent(" ".join(checked.errors))
        artifact = export.render_export(chunk)
        result = ports.PostingResult(
            external_id=chunk.external_id,
            status="EXPORTED",
            response_sha256=hashlib.sha256(artifact).hexdigest(),
            message=f"{len(chunk.lines)} lines written to the CSV export.",
            artifact=artifact,
            artifact_name=f"{export.export_name(chunk)}.zip",
        )
        self._posted[chunk.external_id] = result
        return result

    def get_posting(self, external_id: str) -> ports.PostingResult | None:
        return self._posted.get(external_id)

    def pull_chart_of_accounts(self) -> Sequence[ports.AccountRef]:
        return tuple(self._chart[code] for code in sorted(self._chart))

    def pull_trial_balance(
        self, entity: ports.EntityRef, period: ports.PeriodRef, accounts: Sequence[str]
    ) -> ports.TrialBalance:
        raise ports.Permanent(NO_TRIAL_BALANCE)

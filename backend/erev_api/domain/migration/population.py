"""The comparison population of a migration reconciliation (BUILD_SPEC LMG-3
``MIGRATION_RECONCILE``; 04 T-MIG-01 mode note — the import "computes, in a dry run, the
per-contract events and the reconciliation lines without creating contracts"; PRD WLD-X-27 — the
comparison at the cutover 2023-01-31; Codex ``PRODUCTION-LMG3-EXTRACTOR-REVIEW-a2aad104.md`` F1).

The eRev side of the reconciliation is a BOUND population: the batch's own mode and cutover, the
book, and the contract / contract-version / calc-trace identities of the computation the migration
compares against — mode (a) the dry-run computation of the staged contracts at the cutover date
that the import produces (job ``MIGRATION_IMPORT``); mode (b) the contract versions the replay
committed in the sandbox tenant from ``import_upload_ids`` (LMG-4). The reconcile reads exactly
those versions and each version's own calc trace. It never selects "the latest version as of now":
a later live computation of a linked contract must not change the comparison while the imported
legacy snapshot and the migration are unchanged. Until the import / replay slices capture the
population, the reconcile refuses and names the missing source of the batch's mode
(``not_captured_copy``); it does not substitute live values.

Capture is DURABLE (supervisor ruling D-98 candidate 122): the reconciliation lines are migration
evidence citing ``contract_version_id`` / ``calc_trace_id`` / ``trace_sha256``, and the readers
refuse a missing row or a hash mismatch, so identities that existed only until a savepoint
rollback could not be re-verified later — mode (a) keeps its dry-run results accessible (the
shape — a T-MIG-01 field or a batch-keyed population table — is decided with the
``MIGRATION_IMPORT`` slice); mode (b) is durable already (the sandbox tenant).

Membership (Codex C2 on d093acee): a ``contract_version`` is group / book level (04 T-CON-04
``combination_group`` and ``combination_group_member``) and the computation persists every member
contract's obligation rows in the one version, so a bound version carries its member contract SET
(``VersionRef.contract_ids``) and, SEPARATELY, its captured EXPECTED output
(``VersionRef.obligation_version_ids``: the obligation-version row ids the computation produced —
possibly EMPTY, because the engine admits a ``contract_version`` with no ``obligation_version``
rows: D-98-78, ``tests/engine/s05_allocation/test_s05_voided_member.py``; ``computation.py``
persists the version and inserts obligation rows only when there are any). ``bind`` requires
every row's contract to be a member and the loaded rows to equal the captured output EXACTLY: an
expected row that did not load is refused by name (``MISSING_OUTPUT_COPY``), an unexpected extra
row is refused by name (``UNEXPECTED_OUTPUT_COPY``), a captured-empty version binds with zero rows
— membership never implies output, output is never fabricated or trimmed to what loaded, absent
evidence never becomes zero. A version whose membership is not bound (an empty set) is refused BY
NAME (``UNBOUND_MEMBERSHIP_COPY``) — membership and expected output are captured with the
population, never inferred from the rows. This is the representation's contract (Codex C2 on
d093acee, C2-R1 on 0440b923); the shipped legacy fixture's versions are singletons and are NO
evidence for combined groups — the capability is incomplete until the capture slices supply real
memberships and outputs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID

from erev_api.enums import MigrationMode

__all__ = [
    "BOOK",
    "FOREIGN_COPY",
    "MISSING_OUTPUT_COPY",
    "NOT_CAPTURED_COPY",
    "OUTPUT_NOT_CAPTURED_COPY",
    "SOURCE_BY_MODE",
    "UNBOUND_MEMBERSHIP_COPY",
    "UNEXPECTED_OUTPUT_COPY",
    "ComparisonPopulation",
    "PopulationError",
    "VersionRef",
    "not_captured_copy",
]

# The legacy database is an ASC 606 book; the migration compares that book (present business
# scope — no broader book feature).
BOOK: Final = "ASC606"
SOURCE_BY_MODE: Final[Mapping[MigrationMode, str]] = {
    MigrationMode.OPENING_BALANCES: (
        "the dry-run computation of the staged contracts at the cutover date, produced by the "
        "import (04 T-MIG-01; job MIGRATION_IMPORT)"
    ),
    MigrationMode.REPLAY: (
        "the contract versions the replay committed in the sandbox tenant from import_upload_ids "
        "(BUILD_SPEC LMG-4)"
    ),
}
NOT_CAPTURED_COPY: Final = (
    "The eRev side of this {mode} migration — {source} — has not been captured; the reconcile "
    "does not read the latest live computation in its place."
)
FOREIGN_COPY: Final = "The captured comparison population is not this migration's own: {what}."
UNBOUND_MEMBERSHIP_COPY: Final = (
    "The member contracts of contract version {version} are not bound; the capture must name the "
    "version's combination-group membership (04 T-CON-04) — it is not inferred from the rows."
)
MISSING_OUTPUT_COPY: Final = (
    "Expected obligation version row(s) of contract version {version} did not load: {ids}; the "
    "captured output is neither fabricated nor trimmed to what loaded."
)
UNEXPECTED_OUTPUT_COPY: Final = (
    "Obligation version row {row} of contract version {version} is not in the captured output."
)
OUTPUT_NOT_CAPTURED_COPY: Final = (
    "The expected output of contract version {version} was not captured; an empty set of "
    "obligation versions is admitted only as a captured, observed result (D-98-78) — never as "
    "omitted evidence."
)


class PopulationError(ValueError):
    """The captured population is not the batch's own, or the rows read are not exactly its
    bound versions. The reconcile refuses; nothing is written."""


def not_captured_copy(mode: MigrationMode) -> str:
    """The refusal that names the missing eRev source of ``mode``."""
    return NOT_CAPTURED_COPY.format(mode=mode.value, source=SOURCE_BY_MODE[mode])


@dataclass(frozen=True, slots=True)
class VersionRef:
    """The identities bound before any value is extracted: the contract version, its admitted
    member contracts (the combination group's members for that version — one for a stand-alone
    contract, several for a combined group), that version's own calc trace
    (``contract_version.calc_trace_id``), the book, and the captured EXPECTED output — the
    ``obligation_version`` row ids the computation produced for the version, an EMPTY set for an
    admitted empty result (D-98-78). Membership and output are separate facts: a member may have
    produced no row. An empty membership is refused by name; an empty output is legitimate."""

    contract_ids: frozenset[UUID]
    contract_version_id: UUID
    calc_trace_id: UUID | None
    book_code: str
    obligation_version_ids: frozenset[UUID]
    # Provenance of the producing computation (04 T-MIG-04 rev 1.60): the cutover date and the
    # migration id read back from its ``OPENING_BALANCE_ESTABLISHED`` INPUT — the proof that the
    # computation used THIS batch and cutover (Codex 0247: "matching declared IDs / cutover alone
    # does not prove that producing computation used that batch / cutover"). None until captured.
    cutover_date: date | None = None
    payload_migration_batch_id: UUID | None = None
    # The CAPTURED trace hash (T-MIG-04 ``trace_sha256``): the reader validates the trace it reads
    # against this bound hash, not only against a stored row (Codex 0408). None until captured.
    trace_sha256: str | None = None
    # Whether the capture READ the version's obligation versions: an empty
    # ``obligation_version_ids`` is an admitted empty result only when True (Codex 0422 (d) —
    # omitted evidence is never observed emptiness). None until captured; False is refused by name.
    expected_output_captured: bool | None = None
    # The parent's retained member map (T-MIG-04 ``members``: contract id → external id) — the
    # authoritative label of every comparison row (Codex 0533 R2a); None until captured.
    members: Mapping[UUID, str] | None = None
    # The batch whose capture bound this version (T-MIG-04 ``migration_batch_id``): trace and
    # child retrieval are scoped to the same capture (Codex 0533 R2b); None until captured.
    capture_batch_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.contract_ids:
            raise PopulationError(UNBOUND_MEMBERSHIP_COPY.format(version=self.contract_version_id))
        if self.expected_output_captured is False:
            raise PopulationError(OUTPUT_NOT_CAPTURED_COPY.format(version=self.contract_version_id))
        if self.members is not None and set(self.members) != set(self.contract_ids):
            raise PopulationError(
                f"contract version {self.contract_version_id}: the retained member map does not "
                "name exactly the bound member contracts"
            )


@dataclass(frozen=True, slots=True)
class ComparisonPopulation:
    """What the reconcile compares the legacy snapshot against."""

    batch_id: UUID
    mode: MigrationMode
    cutover_date: date | None
    book_code: str
    versions: tuple[VersionRef, ...]

    def __post_init__(self) -> None:
        if (self.mode is MigrationMode.OPENING_BALANCES) != (self.cutover_date is not None):
            raise PopulationError(
                "an opening-balance population carries the cutover date; a replay population none"
            )
        if not self.versions:
            raise PopulationError("the captured population names no contract version")
        ids = [ref.contract_version_id for ref in self.versions]
        if len(set(ids)) != len(ids):
            raise PopulationError("the captured population names a contract version twice")
        for ref in self.versions:
            if ref.book_code != self.book_code:
                raise PopulationError(
                    f"contract version {ref.contract_version_id} is bound in book "
                    f"{ref.book_code}, the population in {self.book_code}"
                )

    @property
    def refs(self) -> Mapping[UUID, VersionRef]:
        return {ref.contract_version_id: ref for ref in self.versions}

    def check_batch(self, batch: Mapping[str, Any]) -> None:
        """The population must be the batch's own (id, mode, cutover) in the migration book."""
        what: list[str] = []
        if UUID(str(batch["id"])) != self.batch_id:
            what.append(f"migration {self.batch_id} is not {batch['id']}")
        mode = MigrationMode(str(batch["mode"]))
        if mode is not self.mode:
            what.append(f"mode {self.mode.value} is not the migration's {mode.value}")
        cutover = batch.get("cutover_date")
        if cutover != self.cutover_date:
            what.append(f"cutover {self.cutover_date} is not the migration's {cutover}")
        if self.book_code != BOOK:
            what.append(f"book {self.book_code} is not {BOOK}")
        for ref in self.versions:
            # the producing computation's own input names the batch and cutover it used
            if ref.payload_migration_batch_id is not None and ref.payload_migration_batch_id != (
                self.batch_id
            ):
                what.append(
                    f"contract version {ref.contract_version_id} was computed for migration "
                    f"{ref.payload_migration_batch_id}, not {self.batch_id}"
                )
            if ref.cutover_date is not None and ref.cutover_date != self.cutover_date:
                what.append(
                    f"contract version {ref.contract_version_id} was computed at cutover "
                    f"{ref.cutover_date}, not {self.cutover_date}"
                )
        if what:
            raise PopulationError(FOREIGN_COPY.format(what="; ".join(what)))

    def bind(self, rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        """The obligation-version rows of exactly the bound versions' captured output: every row
        belongs to a bound version, in its bound book, for a bound member contract, and is one of
        the version's expected rows; every expected row is present. A captured-empty version
        binds with no rows. Anything else is refused by name — a missing expected row is never a
        silent zero, an extra row is never adopted, membership is never trimmed to what loaded."""
        refs = self.refs
        bound: list[Mapping[str, Any]] = []
        loaded: dict[UUID, set[UUID]] = {version_id: set() for version_id in refs}
        for row in rows:
            version_id = UUID(str(row["contract_version_id"]))
            ref = refs.get(version_id)
            if ref is None:
                raise PopulationError(
                    f"an obligation version row of contract version {version_id} is not bound "
                    "by the population"
                )
            book = row.get("book_code")
            if book != ref.book_code:
                raise PopulationError(
                    f"contract version {version_id}: book_code {book!r} is not the bound "
                    f"{ref.book_code!r}"
                )
            contract = row.get("contract_id")
            if contract is None or UUID(str(contract)) not in ref.contract_ids:
                raise PopulationError(
                    f"contract version {version_id}: contract_id {contract} is not a bound member "
                    "of the version"
                )
            if ref.members is not None:
                # the typed label that keys every comparison row must be the retained one (R2a)
                expected_label = ref.members[UUID(str(contract))]
                if str(row.get("contract_external_id")) != expected_label:
                    raise PopulationError(
                        f"contract version {version_id}: contract_external_id "
                        f"{row.get('contract_external_id')!r} is not the retained "
                        f"{expected_label!r} of member {contract}"
                    )
            row_id = row.get("id")
            if row_id is None or UUID(str(row_id)) not in ref.obligation_version_ids:
                raise PopulationError(UNEXPECTED_OUTPUT_COPY.format(row=row_id, version=version_id))
            loaded[version_id].add(UUID(str(row_id)))
            bound.append(row)
        for version_id, ref in refs.items():
            missing = sorted(str(i) for i in ref.obligation_version_ids - loaded[version_id])
            if missing:
                raise PopulationError(
                    MISSING_OUTPUT_COPY.format(version=version_id, ids=", ".join(missing))
                )
        return bound

"""The preparation artifact and ``erev release prepare`` (05 REL-06; 04 T-PLT-43 BASELINE; RB-16;
D-96 (7), (C), v4 C/E; owner lane P5, ruled 2026-09-19).

Pure plan, decision and summary functions; the CLI command, the session reads (group heads,
T-CON-25 presence, bundle assembly) and the evidence writes are wired after P1's merge. The rules:

- the **preparation artifact** carries the enabled version's calculation code and ``ENGINE_VERSION``
  unchanged (a PATCH by DG-ENG-10: byte-identical outputs) plus the new capture/backfill/SOP-3 code;
  it is stamped as its own ``engine_release`` row (same ``engine_version``, new ``build_sha``) and
  writes the tenant's ``BASELINE`` row for **that** row, so its own recomputations pass the
  per-process-release gate;
- **prepare** walks every group head without T-CON-25 evidence: a verified backfill attaches
  evidence only when the current bundle's CV-25 hash equals the head's ``input_sha256`` **and** the
  engine reproduces the stored ``output_sha256`` (logical identity, labelled ``BACKFILL_VERIFIED``);
  anything else is drift and the group is recomputed under the baseline by the normal command path;
- the run is **complete** only when zero heads lack evidence; the CLI exits non-zero otherwise, so
  the candidate release is never deployed over an unprepared tenant (RB-16 step 2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

from erev_engine import upgrade
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError

from erev_api.controls.validation_level import PreparationRow, check_declaration
from erev_api.domain.contracts.release_validation import ValidationCreation, baseline_row

__all__ = [
    "ArtifactFacts",
    "BackfillOutcome",
    "HeadFacts",
    "PreparePlan",
    "PrepareSummary",
    "PrepareSummaryError",
    "backfill_decision",
    "baseline_for_artifact",
    "format_summary",
    "is_preparation_artifact",
    "plan_prepare",
    "prepare_release_baseline",
    "prepare_summary",
]

Engine = Callable[[InputBundle], OutputBundle]
BackfillKind = Literal[
    "BACKFILL_VERIFIED",
    "INPUT_DRIFTED",
    "OUTPUT_DRIFTED",
    "ENGINE_ERROR",
    "BACKFILL_BOOK_POPULATION_MISMATCH",
]
EXIT_COMPLETE: Final = 0
EXIT_INCOMPLETE: Final = 1


# --- the artifact ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArtifactFacts:
    process_engine_version: str
    process_build_sha: str
    enabled_engine_version: str  # the tenant's enabled release (its historical build)
    enabled_build_sha: str


def is_preparation_artifact(facts: ArtifactFacts) -> bool:
    """Same ``engine_version`` as the enabled release, a different ``build_sha`` (D-96 (7))."""
    return (
        facts.process_engine_version == facts.enabled_engine_version
        and facts.process_build_sha != facts.enabled_build_sha
    )


def baseline_for_artifact(
    facts: ArtifactFacts, *, preparation_release_id: UUID, historical_release_id: UUID
) -> ValidationCreation:
    """The BASELINE row the artifact writes for its **own** release; refused for a process that is
    not the preparation artifact (a candidate must never write a baseline for itself)."""
    if not is_preparation_artifact(facts):
        raise ValueError(
            "only the preparation artifact (same engine_version, new build_sha) writes a BASELINE "
            "row"
        )
    return baseline_row(
        preparation_release_id=preparation_release_id, historical_release_id=historical_release_id
    )


# --- the plan -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeadFacts:
    group_id: UUID
    head_computation_id: UUID | None
    has_evidence: bool
    input_sha256: str | None
    output_sha256_by_book: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class PreparePlan:
    evidenced: tuple[UUID, ...]  # heads that already carry T-CON-25 evidence
    to_backfill: tuple[HeadFacts, ...]  # heads without evidence: try the verified backfill
    no_head: tuple[UUID, ...]  # never computed successfully: nothing to prepare


def plan_prepare(heads: Iterable[HeadFacts]) -> PreparePlan:
    evidenced: list[UUID] = []
    backfill: list[HeadFacts] = []
    no_head: list[UUID] = []
    for head in sorted(heads, key=lambda item: str(item.group_id)):
        if head.head_computation_id is None:
            no_head.append(head.group_id)
        elif head.has_evidence:
            evidenced.append(head.group_id)
        else:
            backfill.append(head)
    return PreparePlan(tuple(evidenced), tuple(backfill), tuple(no_head))


# --- the backfill decision ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BackfillOutcome:
    """What ``prepare`` may write for one head: a ``BACKFILL_VERIFIED`` T-CON-25 row (bytes and
    digests) or a T-CON-26 ``UNVERIFIABLE`` row with the drift reason and a recompute
    instruction."""

    group_id: UUID
    head_computation_id: UUID
    kind: BackfillKind
    input_bytes: bytes | None
    input_file_sha256: str | None
    output_bytes: bytes | None
    output_file_sha256: str | None
    recompute: bool

    @property
    def verified(self) -> bool:
        return self.kind == "BACKFILL_VERIFIED"


def backfill_decision(head: HeadFacts, current: InputBundle, engine: Engine) -> BackfillOutcome:
    """The verified backfill (D-96 (2)): evidence is attached only when the hashes prove logical
    identity; a drift leaves the group to a normal recomputation under the baseline."""
    if head.head_computation_id is None:
        raise ValueError("a head without a successful computation has nothing to back-fill")
    stored_outputs = set(head.output_sha256_by_book.values())

    def drift(kind: BackfillKind) -> BackfillOutcome:
        assert head.head_computation_id is not None
        return BackfillOutcome(
            head.group_id, head.head_computation_id, kind, None, None, None, None, True
        )

    if head.input_sha256 is None or current.sha256() != head.input_sha256:
        return drift("INPUT_DRIFTED")
    try:
        output = engine(current)
    except EngineError:
        return drift("ENGINE_ERROR")
    # P5-PREP-R3: the stored book map's KEY set must equal the contract-version book population of
    # the recomputed output (04 T-CON-25 ``book_codes`` = books with a contract version); an
    # unknown key, a missing book or an extra book is refused before any hash is compared —
    # agreement among hash values never proves the map's keys.
    present = {book.book_code for book in output.books if book.contract_version is not None}
    if set(head.output_sha256_by_book) != present:
        assert head.head_computation_id is not None
        return BackfillOutcome(
            head.group_id,
            head.head_computation_id,
            "BACKFILL_BOOK_POPULATION_MISMATCH",
            None,
            None,
            None,
            None,
            False,
        )
    if len(stored_outputs) != 1 or output.sha256() not in stored_outputs:
        return drift("OUTPUT_DRIFTED")
    input_bytes = upgrade.encode_input(current)
    output_bytes = upgrade.encode_output(output)
    return BackfillOutcome(
        head.group_id,
        head.head_computation_id,
        "BACKFILL_VERIFIED",
        input_bytes,
        upgrade.raw_digest(input_bytes),
        output_bytes,
        upgrade.raw_digest(output_bytes),
        False,
    )


# --- the summary (CLI) ----------------------------------------------------------------------------


Identity = tuple[UUID, UUID]  # (group_id, head_computation_id)
SummaryRefusal = Literal["SUMMARY_OUTCOME_DUPLICATE", "SUMMARY_OUTCOME_UNPLANNED"]


class PrepareSummaryError(ValueError):
    """P5-PREP-R1: the supplied outcomes cannot be reconciled to the plan — a duplicate outcome
    identity or an outcome for an identity the plan never named (wrong group, wrong head, extra).
    Neither may substitute for a missing planned head, so the summary is refused, not computed."""

    def __init__(self, reason: SummaryRefusal, identities: Sequence[Identity]) -> None:
        self.reason: SummaryRefusal = reason
        self.identities: tuple[Identity, ...] = tuple(identities)
        listed = ", ".join(f"{group}/{head}" for group, head in self.identities)
        super().__init__(f"{reason}: {listed}")


@dataclass(frozen=True, slots=True)
class PrepareSummary:
    evidenced: int
    backfilled: int
    drifted: tuple[UUID, ...]  # groups that need a normal recomputation under the baseline
    engine_errors: tuple[UUID, ...]
    refused: tuple[UUID, ...]  # BACKFILL_BOOK_POPULATION_MISMATCH: stored book map ≠ output
    missing: tuple[Identity, ...]  # planned (group, head) identities with no outcome at all
    no_head: int

    @property
    def complete(self) -> bool:
        """Zero heads lack evidence after the run (RB-16 step 2's exit condition): every planned
        identity has exactly one verified outcome — nothing drifted, errored, refused or missing."""
        return not (self.drifted or self.engine_errors or self.refused or self.missing)

    @property
    def exit_code(self) -> int:
        return EXIT_COMPLETE if self.complete else EXIT_INCOMPLETE


def prepare_summary(plan: PreparePlan, outcomes: Sequence[BackfillOutcome]) -> PrepareSummary:
    """P5-PREP-R1: completion needs a one-to-one match between the planned
    ``(group_id, head_computation_id)`` identities and the outcome identities. A duplicate identity
    is refused (``SUMMARY_OUTCOME_DUPLICATE``); an identity outside the plan — wrong group, wrong
    head, extra — is refused (``SUMMARY_OUTCOME_UNPLANNED``); a planned identity without an outcome
    stays incomplete and is listed. Drift, error and the explicit no-head case are reported as
    before."""
    planned: set[Identity] = {
        (head.group_id, head.head_computation_id)
        for head in plan.to_backfill
        if head.head_computation_id is not None
    }
    seen: set[Identity] = set()
    duplicates: list[Identity] = []
    unplanned: list[Identity] = []
    for item in outcomes:
        identity: Identity = (item.group_id, item.head_computation_id)
        if identity in seen:
            duplicates.append(identity)
        seen.add(identity)
        if identity not in planned:
            unplanned.append(identity)
    if duplicates:
        raise PrepareSummaryError("SUMMARY_OUTCOME_DUPLICATE", sorted(set(duplicates), key=str))
    if unplanned:
        raise PrepareSummaryError("SUMMARY_OUTCOME_UNPLANNED", sorted(set(unplanned), key=str))
    missing = tuple(sorted(planned - seen, key=str))
    return PrepareSummary(
        evidenced=len(plan.evidenced),
        backfilled=sum(1 for item in outcomes if item.verified),
        drifted=tuple(
            item.group_id for item in outcomes if item.kind in ("INPUT_DRIFTED", "OUTPUT_DRIFTED")
        ),
        engine_errors=tuple(item.group_id for item in outcomes if item.kind == "ENGINE_ERROR"),
        refused=tuple(
            item.group_id for item in outcomes if item.kind == "BACKFILL_BOOK_POPULATION_MISMATCH"
        ),
        missing=missing,
        no_head=len(plan.no_head),
    )


def format_summary(summary: PrepareSummary) -> str:
    """Operator lines: counts and group ids only — no connection strings, no values (common terms,
    diagnostic-output amendment)."""
    lines = [
        f"evidenced heads: {summary.evidenced}",
        f"backfilled (BACKFILL_VERIFIED): {summary.backfilled}",
        f"drifted (recompute under the baseline): {len(summary.drifted)}",
        f"engine errors: {len(summary.engine_errors)}",
        f"refused (stored book map does not match the output): {len(summary.refused)}",
        f"planned heads without a result: {len(summary.missing)}",
        f"groups without a head: {summary.no_head}",
        "prepare complete"
        if summary.complete
        else "prepare INCOMPLETE — do not deploy the candidate",
    ]
    lines += [f"  recompute {group_id}" for group_id in summary.drifted]
    lines += [f"  engine error {group_id}" for group_id in summary.engine_errors]
    lines += [f"  book population mismatch {group_id}" for group_id in summary.refused]
    lines += [f"  missing result for group {group} head {head}" for group, head in summary.missing]
    return "\n".join(lines)


# --- the preparation path (P5-PREP-R2) ------------------------------------------------------------


def prepare_release_baseline(
    facts: ArtifactFacts,
    *,
    preparation_release_id: UUID,
    historical_release_id: UUID,
    authorization_ref: str,
) -> tuple[ValidationCreation, PreparationRow]:
    """The explicit same-version / new-build preparation path (REL-06; 11 SOP-3 prerequisites;
    D-98 candidate REL-06-SAME-VERSION-REBUILD, supervisor): accepts an artifact whose engine
    version equals the enabled release's when the build differs, requires the typed authorization
    reference, binds the artifact's own BASELINE row and returns the ``PreparationRow`` the
    stamping hook passes to ``check_declaration`` — the only way a same-version new build is
    accepted. Build facts never infer calculation-code identity; that is the author's DG-ENG-10
    declaration, checked by the gates."""
    baseline = baseline_for_artifact(
        facts,
        preparation_release_id=preparation_release_id,
        historical_release_id=historical_release_id,
    )
    row = PreparationRow(
        engine_version=facts.process_engine_version,
        build_sha=facts.process_build_sha,
        preparation_release_id=preparation_release_id,
        baseline_release_id=baseline.engine_release_id,
        authorization_ref=authorization_ref,
    )
    check_declaration(
        "PATCH",
        previous_version=facts.enabled_engine_version,
        candidate_version=facts.process_engine_version,
        previous_build=facts.enabled_build_sha,
        candidate_build=facts.process_build_sha,
        preparation=row,
    )
    return baseline, row

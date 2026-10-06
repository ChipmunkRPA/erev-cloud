"""Replay verification decision (05 RCP-28, RCP-28a; 04 T-CON-26; D-96 (1), (2), (A), (B)).

Pure: the caller (the ``REPLAY_VERIFY`` job handler of the integration slice) loads the source
facts (T-CON-07/08), the evidence bytes (T-CON-25 files) and the process release, hands them to
``verify`` together with the engine callable, and persists the returned ``VerificationRow``
through ``release_validation.verification_write``. Nothing here reads a database, and nothing
here ever writes T-CON-07/08, postings or heads — the row is the only output.

Order of checks (RCP-28a "Evidence verification order"):

1. runtime — an integrity replay needs ``source.engine_version == process.engine_version``
   (raw hashes exclude ``build_sha``); otherwise ``UNVERIFIABLE`` / ``SOURCE_RUNTIME_UNAVAILABLE``
   with ``engine_executed = false``, NULL executed identity, NULL actual output, ``compute`` not
   invoked and the source never retagged (A);
2. evidence present — else ``UNVERIFIABLE`` / ``INPUT_EVIDENCE_MISSING`` (never a rebuild);
3. raw input digest — ``MISMATCH`` / ``INPUT_EVIDENCE_HASH_MISMATCH``;
4. logical CV-25 hash of the decoded bundle against T-CON-07 — ``LOGICAL_HASH_MISMATCH``;
5. output evidence: raw digest, CV-26 logical hash and the book set against the T-CON-08 rows —
   ``OUTPUT_EVIDENCE_HASH_MISMATCH``; disagreeing stored copies (T-CON-08 rows among themselves,
   or T-CON-08 against T-CON-25) — ``EXPECTED_HASH_DISAGREEMENT``;
6. candidate path only — the registered transform chain, else ``UNVERIFIABLE`` /
   ``NO_INPUT_TRANSFORM``;
7. execution — ``EngineError`` → ``ERROR`` with the executed identity and NULL actual output;
   integrity → L0 ``MATCH``/``MISMATCH``; candidate → L1 ``MATCH`` else ``DIFFERENCES`` with the
   L2 summary.

Every ``MISMATCH`` is an integrity incident: it blocks the attempt and is never approvable (B).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

from erev_engine import upgrade
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError

from erev_api.domain.contracts.release_validation import ExecutionToken
from erev_api.enums import ComputationTrigger, VerificationOutcome

__all__ = [
    "REASONS",
    "EvidenceFacts",
    "ProcessFacts",
    "SourceFacts",
    "VerificationRow",
    "verify",
]

Trigger = Literal["REPLAY_VERIFY", "UPGRADE_VALIDATE"]
Engine = Callable[[InputBundle], OutputBundle]

REASONS: Final = (
    "SOURCE_RUNTIME_UNAVAILABLE",
    "INPUT_EVIDENCE_MISSING",
    "INPUT_EVIDENCE_HASH_MISMATCH",
    "LOGICAL_HASH_MISMATCH",
    "OUTPUT_EVIDENCE_HASH_MISMATCH",
    "EXPECTED_HASH_DISAGREEMENT",
    "NO_INPUT_TRANSFORM",
    "ENGINE_ERROR",
    "L0_MISMATCH",
    "L1_DIFFERENCES",
)
_INTEGRITY_REASONS: Final = frozenset(
    {
        "INPUT_EVIDENCE_HASH_MISMATCH",
        "LOGICAL_HASH_MISMATCH",
        "OUTPUT_EVIDENCE_HASH_MISMATCH",
        "EXPECTED_HASH_DISAGREEMENT",
        "L0_MISMATCH",
    }
)


@dataclass(frozen=True, slots=True)
class SourceFacts:
    """T-CON-07 and its T-CON-08 rows (the specified oracle)."""

    computation_id: UUID
    combination_group_id: UUID
    engine_release_id: UUID
    engine_version: str
    input_sha256: str
    output_sha256_by_book: Mapping[str, str]  # T-CON-08 rows of the computation


@dataclass(frozen=True, slots=True)
class EvidenceFacts:
    """T-CON-25 row and its two files, as loaded (digests recomputed here, never trusted)."""

    input_bytes: bytes
    input_file_sha256: str  # the stored trusted digest
    output_bytes: bytes
    output_file_sha256: str
    output_sha256: str  # the T-CON-25 copy of the logical output hash
    book_codes: tuple[str, ...]
    codec: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProcessFacts:
    """The orchestrating process (T-PLT-38 row of the running api/worker)."""

    engine_release_id: UUID
    engine_version: str


@dataclass(frozen=True, slots=True)
class VerificationRow:
    """The T-CON-26 row. ``__post_init__`` enforces the four named CHECKs in Python as well, so a
    malformed row is refused before it reaches the database (A)."""

    source_computation_id: UUID | None
    combination_group_id: UUID
    trigger: Trigger
    source_engine_release_id: UUID | None
    source_engine_version: str | None
    source_codec: Mapping[str, object] | None
    process_engine_release_id: UUID
    process_engine_version: str
    engine_executed: bool
    executed_engine_release_id: UUID | None
    executed_engine_version: str | None
    input_transform_id: str | None
    candidate_input_sha256: str | None
    input_sha256: str | None
    input_file_sha256_expected: str | None
    input_file_sha256_observed: str | None
    expected_output_sha256: str | None
    evidence_output_sha256: str | None
    expected_book_codes: tuple[str, ...] | None
    actual_output_sha256: str | None
    normalised_expected_sha256: str | None
    normalised_actual_sha256: str | None
    normalised_input_match: bool | None
    outcome: VerificationOutcome
    reason: str | None
    difference_summary: Mapping[str, object] | None
    release_validation_attempt_id: UUID | None
    token: ExecutionToken

    def __post_init__(self) -> None:
        if self.trigger not in ("REPLAY_VERIFY", "UPGRADE_VALIDATE"):
            raise ValueError("trigger is REPLAY_VERIFY or UPGRADE_VALIDATE")
        # ck_cv__executed_identity: both executed columns present iff executed, else both NULL.
        both_present = (
            self.executed_engine_release_id is not None and self.executed_engine_version is not None
        )
        both_null = self.executed_engine_release_id is None and self.executed_engine_version is None
        if not (
            (self.engine_executed and both_present) or (not self.engine_executed and both_null)
        ):
            raise ValueError("ck_cv__executed_identity")
        # ck_cv__no_output_without_execution
        if not self.engine_executed and self.actual_output_sha256 is not None:
            raise ValueError("ck_cv__no_output_without_execution")
        # ck_cv__integrity_source
        if self.engine_executed and self.trigger == "REPLAY_VERIFY":
            if (
                self.source_computation_id is None
                or self.source_engine_version is None
                or self.executed_engine_version != self.source_engine_version
            ):
                raise ValueError("ck_cv__integrity_source")
        # ck_cv__candidate_release
        if self.engine_executed and self.trigger == "UPGRADE_VALIDATE":
            if self.executed_engine_release_id != self.process_engine_release_id:
                raise ValueError("ck_cv__candidate_release")
        if self.outcome is not VerificationOutcome.MATCH and self.reason is None:
            raise ValueError("reason is required unless the outcome is MATCH")
        if self.reason is not None and self.reason not in REASONS:
            raise ValueError(f"unknown reason {self.reason!r}")

    @property
    def integrity_incident(self) -> bool:
        """RB-09: a MISMATCH under either trigger (SEV-1); never an approvable difference."""
        return self.outcome is VerificationOutcome.MISMATCH


def verify(
    *,
    trigger: Trigger,
    source: SourceFacts,
    evidence: EvidenceFacts | None,
    process: ProcessFacts,
    engine: Engine,
    token: ExecutionToken,
    attempt_id: UUID | None,
    registry: Mapping[tuple[str, str], upgrade.InputTransform] = upgrade.INPUT_TRANSFORMS,
) -> VerificationRow:
    """One verification attempt of ``source`` under ``process`` (RCP-28a)."""
    # The not-executed template: every outcome below is a typed ``dataclasses.replace`` of it, so
    # the four CHECKs run on each constructed row.
    template = VerificationRow(
        source_computation_id=source.computation_id,
        combination_group_id=source.combination_group_id,
        trigger=trigger,
        source_engine_release_id=source.engine_release_id,
        source_engine_version=source.engine_version,
        source_codec=None if evidence is None else dict(evidence.codec),
        process_engine_release_id=process.engine_release_id,
        process_engine_version=process.engine_version,
        engine_executed=False,
        executed_engine_release_id=None,
        executed_engine_version=None,
        input_transform_id=None,
        candidate_input_sha256=None,
        input_sha256=source.input_sha256,
        input_file_sha256_expected=None if evidence is None else evidence.input_file_sha256,
        input_file_sha256_observed=None
        if evidence is None
        else upgrade.raw_digest(evidence.input_bytes),
        expected_output_sha256=_expected_output(source),
        evidence_output_sha256=None if evidence is None else evidence.output_sha256,
        expected_book_codes=tuple(sorted(source.output_sha256_by_book)),
        actual_output_sha256=None,
        normalised_expected_sha256=None,
        normalised_actual_sha256=None,
        normalised_input_match=None,
        outcome=VerificationOutcome.UNVERIFIABLE,
        reason="INPUT_EVIDENCE_MISSING",
        difference_summary=None,
        release_validation_attempt_id=attempt_id,
        token=token,
    )

    def not_executed(outcome: VerificationOutcome, reason: str) -> VerificationRow:
        return dataclasses.replace(template, outcome=outcome, reason=reason)

    unverifiable, mismatch = VerificationOutcome.UNVERIFIABLE, VerificationOutcome.MISMATCH
    # 1. runtime (A): the integrity path runs the source's own version only.
    if trigger == "REPLAY_VERIFY" and source.engine_version != process.engine_version:
        return not_executed(unverifiable, "SOURCE_RUNTIME_UNAVAILABLE")
    # 2. evidence present.
    if evidence is None:
        return not_executed(unverifiable, "INPUT_EVIDENCE_MISSING")
    # 3. raw input digest.
    observed = upgrade.raw_digest(evidence.input_bytes)
    if observed != evidence.input_file_sha256:
        return not_executed(mismatch, "INPUT_EVIDENCE_HASH_MISMATCH")
    # 4. logical CV-25 hash of the decoded bundle against T-CON-07.
    try:
        bundle = upgrade.decode_input(evidence.input_bytes)
    except (ValueError, TypeError):
        return not_executed(mismatch, "INPUT_EVIDENCE_HASH_MISMATCH")
    if bundle.sha256() != source.input_sha256:
        return not_executed(mismatch, "LOGICAL_HASH_MISMATCH")
    # 5. output evidence and the stored copies.
    expected = _expected_output(source)
    if expected is None:
        return not_executed(mismatch, "EXPECTED_HASH_DISAGREEMENT")
    if (
        upgrade.raw_digest(evidence.output_bytes) != evidence.output_file_sha256
        or evidence.output_file_sha256 != evidence.output_sha256
    ):
        return not_executed(mismatch, "OUTPUT_EVIDENCE_HASH_MISMATCH")
    if evidence.output_sha256 != expected or tuple(sorted(evidence.book_codes)) != tuple(
        sorted(source.output_sha256_by_book)
    ):
        return not_executed(mismatch, "EXPECTED_HASH_DISAGREEMENT")
    expected_mapping = upgrade.output_mapping(evidence.output_bytes)
    # 6. candidate input.
    transform_id: str | None = None
    candidate_sha: str | None = None
    to_run = bundle
    if trigger == "UPGRADE_VALIDATE":
        try:
            to_run, transform_id = upgrade.candidate_input(bundle, process.engine_version, registry)
        except upgrade.TransformUnavailable:
            return not_executed(unverifiable, "NO_INPUT_TRANSFORM")
        candidate_sha = to_run.sha256()
    # 7. execution: the executed identity is the process release (ck_cv__integrity_source and
    # ck_cv__candidate_release are re-checked by every replace below).
    try:
        output = engine(to_run)
    except EngineError:
        return dataclasses.replace(
            template,
            engine_executed=True,
            executed_engine_release_id=process.engine_release_id,
            executed_engine_version=process.engine_version,
            input_transform_id=transform_id,
            candidate_input_sha256=candidate_sha,
            outcome=VerificationOutcome.ERROR,
            reason="ENGINE_ERROR",
        )
    actual = output.sha256()
    if trigger == "REPLAY_VERIFY":
        matched = actual == expected
        return dataclasses.replace(
            template,
            engine_executed=True,
            executed_engine_release_id=process.engine_release_id,
            executed_engine_version=process.engine_version,
            actual_output_sha256=actual,
            outcome=VerificationOutcome.MATCH if matched else mismatch,
            reason=None if matched else "L0_MISMATCH",
        )
    actual_mapping = upgrade.output_mapping(output)
    l1_expected = upgrade.l1_sha256(expected_mapping)
    l1_actual = upgrade.l1_sha256(actual_mapping)
    input_match = upgrade.normalised_input_sha256(bundle) == upgrade.normalised_input_sha256(to_run)
    summary = upgrade.representation_diff(expected_mapping, actual_mapping)
    l1_match = l1_expected == l1_actual
    return dataclasses.replace(
        template,
        engine_executed=True,
        executed_engine_release_id=process.engine_release_id,
        executed_engine_version=process.engine_version,
        input_transform_id=transform_id,
        candidate_input_sha256=candidate_sha,
        actual_output_sha256=actual,
        normalised_expected_sha256=l1_expected,
        normalised_actual_sha256=l1_actual,
        normalised_input_match=input_match,
        outcome=VerificationOutcome.MATCH if l1_match else VerificationOutcome.DIFFERENCES,
        reason=None if l1_match else "L1_DIFFERENCES",
        difference_summary=summary.as_json(),
    )


def _expected_output(source: SourceFacts) -> str | None:
    """The T-CON-08 ``output_sha256`` shared by every book row; None when the rows disagree or
    the computation has no version row (an ``EXPECTED_HASH_DISAGREEMENT`` for the caller)."""
    values: Sequence[str] = tuple(source.output_sha256_by_book.values())
    if not values or len(set(values)) != 1:
        return None
    return values[0]


# The E-87 literals this module writes into T-CON-26 ``trigger`` (never into a bundle).
TRIGGERS: Final = (
    ComputationTrigger.REPLAY_VERIFY.value,
    ComputationTrigger.UPGRADE_VALIDATE.value,
)

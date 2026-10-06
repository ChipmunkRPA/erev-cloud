"""``domain.contracts.release_prepare``: preparation-artifact identity, the prepare plan, the
verified backfill decision and the CLI summary (05 REL-06; RB-16; D-96 (2), (7), C; lane P5).
DB-free: the head facts are injected and the engine is the real ``erev_engine.compute``."""

from __future__ import annotations

import dataclasses
from uuid import UUID, uuid4

import pytest
from erev_api.controls.validation_level import (
    SAME_VERSION_REBUILD,
    PreparationRow,
    check_declaration,
)
from erev_api.domain.contracts.release_prepare import (
    EXIT_COMPLETE,
    EXIT_INCOMPLETE,
    ArtifactFacts,
    HeadFacts,
    PrepareSummaryError,
    backfill_decision,
    baseline_for_artifact,
    format_summary,
    is_preparation_artifact,
    plan_prepare,
    prepare_release_baseline,
    prepare_summary,
)
from erev_api.enums import ReleaseValidationStatus
from erev_engine import ENGINE_VERSION, compute, upgrade
from erev_engine.errors import EngineError
from support.billing_lines import checkpoint_bundle

COMPUTABLE = ("mod", "MOD-LEGACY-PROS-GT12", "end-june-after-prospective")


def test_preparation_artifact_identity_and_its_own_baseline_row() -> None:
    artifact = ArtifactFacts(ENGINE_VERSION, "b" * 40, ENGINE_VERSION, "a" * 40)
    assert is_preparation_artifact(artifact)
    assert not is_preparation_artifact(
        ArtifactFacts(ENGINE_VERSION, "a" * 40, ENGINE_VERSION, "a" * 40)
    )
    assert not is_preparation_artifact(ArtifactFacts("0.4.0", "b" * 40, ENGINE_VERSION, "a" * 40))
    preparation, historical = uuid4(), uuid4()
    row = baseline_for_artifact(
        artifact, preparation_release_id=preparation, historical_release_id=historical
    )
    assert row.engine_release_id == preparation and row.source_engine_release_id == historical
    assert row.effective_level == "BASELINE" and row.status is ReleaseValidationStatus.PASSED
    assert row.enabled_at_creation
    candidate = ArtifactFacts("0.4.0", "c" * 40, ENGINE_VERSION, "a" * 40)
    with pytest.raises(ValueError, match="only the preparation artifact"):
        baseline_for_artifact(
            candidate, preparation_release_id=uuid4(), historical_release_id=historical
        )


def test_plan_partitions_heads() -> None:
    evidenced = HeadFacts(UUID(int=1), UUID(int=11), True, "a" * 64, {"ASC606": "b" * 64})
    missing = HeadFacts(UUID(int=2), UUID(int=12), False, "a" * 64, {"ASC606": "b" * 64})
    never = HeadFacts(UUID(int=3), None, False, None, {})
    plan = plan_prepare([never, missing, evidenced])
    assert plan.evidenced == (UUID(int=1),)
    assert [h.group_id for h in plan.to_backfill] == [UUID(int=2)]
    assert plan.no_head == (UUID(int=3),)


def _head(bundle_hash: str, output_hash: str) -> HeadFacts:
    return HeadFacts(uuid4(), uuid4(), False, bundle_hash, {"ASC606": output_hash})


def test_backfill_verified_only_when_both_hashes_prove_identity() -> None:
    bundle = checkpoint_bundle(*COMPUTABLE)
    output = compute(bundle)
    head = _head(bundle.sha256(), output.sha256())
    verified = backfill_decision(head, bundle, compute)
    assert verified.verified and not verified.recompute and verified.kind == "BACKFILL_VERIFIED"
    assert verified.input_bytes is not None and verified.output_bytes is not None
    assert verified.input_file_sha256 == upgrade.raw_digest(verified.input_bytes)
    assert verified.output_file_sha256 == output.sha256()  # output digest == CV-26 hash
    assert upgrade.decode_input(verified.input_bytes).sha256() == head.input_sha256
    # Input drift: the current bundle no longer hashes to the head's input (the checkpoint runs
    # under the parity preset, so the other preset is the changed input).
    other_preset = "DEFAULT" if bundle.tenant_preset == "LEGACY_PARITY" else "LEGACY_PARITY"
    drifted = dataclasses.replace(bundle, tenant_preset=other_preset)
    assert drifted.sha256() != head.input_sha256
    assert backfill_decision(head, drifted, compute).kind == "INPUT_DRIFTED"
    # Output drift: the stored T-CON-08 hash is not what the engine reproduces.
    other = _head(bundle.sha256(), "0" * 64)
    assert backfill_decision(other, bundle, compute).kind == "OUTPUT_DRIFTED"
    # A stored map naming a book the output does not carry is refused BEFORE any hash comparison
    # (P5-PREP-R3: population first, values second) — never verified, never mere drift.
    two = HeadFacts(
        uuid4(), uuid4(), False, bundle.sha256(), {"ASC606": output.sha256(), "IFRS15": "1" * 64}
    )
    assert backfill_decision(two, bundle, compute).kind == "BACKFILL_BOOK_POPULATION_MISMATCH"

    def failing(_: object) -> object:
        raise EngineError("ENGINE_INVARIANT_VIOLATED", "probe")

    assert backfill_decision(head, bundle, failing).kind == "ENGINE_ERROR"  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        backfill_decision(HeadFacts(uuid4(), None, False, None, {}), bundle, compute)


def test_p5_prep_r1_completion_requires_one_to_one_match_with_the_plan() -> None:
    """Codex P5-PREP-R1 probe shapes (PRODUCTION-P5-PREP-REVIEW-934c55d.md): native head, empty
    outcomes; one of two omitted; a duplicate masking the omission; an outcome for a different
    group; an outcome for a different head; a complete two-head set."""
    bundle = checkpoint_bundle(*COMPUTABLE)
    sha = compute(bundle).sha256()
    native = HeadFacts(UUID(int=1), UUID(int=2), False, bundle.sha256(), {"ASC606": sha})
    plan = plan_prepare([native])
    # 1. one planned head, empty outcomes → incomplete, non-zero exit, the identity listed.
    empty = prepare_summary(plan, [])
    assert not empty.complete and empty.exit_code == EXIT_INCOMPLETE
    assert empty.missing == ((UUID(int=1), UUID(int=2)),)
    text = format_summary(empty)
    assert "prepare INCOMPLETE" in text and "prepare complete" not in text
    assert f"missing result for group {UUID(int=1)} head {UUID(int=2)}" in text
    # positive control: the matching native verified result completes.
    verified = backfill_decision(native, bundle, compute)
    assert verified.verified
    assert prepare_summary(plan, [verified]).complete
    # 2. one of two planned heads omitted → the other identity is missing, never complete.
    second = HeadFacts(UUID(int=3), UUID(int=4), False, bundle.sha256(), {"ASC606": sha})
    two = plan_prepare([native, second])
    second_verified = backfill_decision(second, bundle, compute)
    partial = prepare_summary(two, [verified])
    assert not partial.complete and partial.missing == ((UUID(int=3), UUID(int=4)),)
    assert partial.exit_code == EXIT_INCOMPLETE
    # 3. the same result duplicated to mask the omission → refused, never a substitute.
    with pytest.raises(PrepareSummaryError) as duplicated:
        prepare_summary(two, [verified, verified])
    assert duplicated.value.reason == "SUMMARY_OUTCOME_DUPLICATE"
    assert duplicated.value.identities == ((UUID(int=1), UUID(int=2)),)
    # 4. an outcome for a different group → refused as unplanned.
    wrong_group = dataclasses.replace(second_verified, group_id=UUID(int=99))
    with pytest.raises(PrepareSummaryError) as other_group:
        prepare_summary(two, [verified, wrong_group])
    assert other_group.value.reason == "SUMMARY_OUTCOME_UNPLANNED"
    assert other_group.value.identities == ((UUID(int=99), UUID(int=4)),)
    # 5. an outcome for a different head of a planned group → refused as unplanned.
    wrong_head = dataclasses.replace(second_verified, head_computation_id=UUID(int=44))
    with pytest.raises(PrepareSummaryError) as other_head:
        prepare_summary(two, [verified, wrong_head])
    assert other_head.value.reason == "SUMMARY_OUTCOME_UNPLANNED"
    # 6. a complete two-head result set stays complete (order-insensitive).
    full = prepare_summary(two, [second_verified, verified])
    assert full.complete and full.exit_code == EXIT_COMPLETE and full.missing == ()
    # Controls: drift stays reported and blocks completion; the no-head case is explicit and never
    # counts as a missing result.
    drifted_head = HeadFacts(UUID(int=5), UUID(int=6), False, "f" * 64, {"ASC606": sha})
    with_drift = plan_prepare([native, drifted_head, HeadFacts(UUID(int=7), None, False, None, {})])
    outcomes = [backfill_decision(head, bundle, compute) for head in with_drift.to_backfill]
    summary = prepare_summary(with_drift, outcomes)
    assert summary.drifted == (UUID(int=5),) and summary.missing == () and summary.no_head == 1
    assert not summary.complete


def test_p5_prep_r2_same_version_new_build_only_through_the_preparation_path() -> None:
    """Codex P5-PREP-R2 probe: 0.3.0 / new build / PATCH passes through the preparation path and
    binds the artifact's own BASELINE row; the same pair through the bare declaration path (no
    preparation row) still fails; downgrade and under-declaration controls are unchanged."""
    enabled_build, new_build = "a" * 40, "b" * 40
    facts = ArtifactFacts(ENGINE_VERSION, new_build, ENGINE_VERSION, enabled_build)
    preparation_release, historical = uuid4(), uuid4()
    baseline, row = prepare_release_baseline(
        facts,
        preparation_release_id=preparation_release,
        historical_release_id=historical,
        authorization_ref="CHG-2026-0919-P5",
    )
    assert baseline.engine_release_id == preparation_release and baseline.enabled_at_creation
    assert row.baseline_release_id == preparation_release and row.authorization_ref
    assert row.covers(ENGINE_VERSION, new_build) and not row.covers(ENGINE_VERSION, enabled_build)
    # The stamping hook accepts the pair with the row …
    check_declaration(
        "PATCH",
        previous_version=ENGINE_VERSION,
        candidate_version=ENGINE_VERSION,
        previous_build=enabled_build,
        candidate_build=new_build,
        preparation=row,
    )
    # … and refuses the same pair through the bare declaration path (no preparation row), with the
    # named reason instead of "does not follow".
    with pytest.raises(ValueError, match=SAME_VERSION_REBUILD):
        check_declaration(
            "PATCH",
            previous_version=ENGINE_VERSION,
            candidate_version=ENGINE_VERSION,
            previous_build=enabled_build,
            candidate_build=new_build,
        )
    # A row for another build does not cover this pair.
    with pytest.raises(ValueError, match=SAME_VERSION_REBUILD):
        check_declaration(
            "PATCH",
            previous_version=ENGINE_VERSION,
            candidate_version=ENGINE_VERSION,
            previous_build=enabled_build,
            candidate_build="c" * 40,
            preparation=row,
        )
    # An equal pair is the same release restarting: accepted without a row.
    check_declaration(
        "PATCH",
        previous_version=ENGINE_VERSION,
        candidate_version=ENGINE_VERSION,
        previous_build=enabled_build,
        candidate_build=enabled_build,
    )
    # Unchanged controls: downgrade still "does not follow"; under-declaration still refused.
    with pytest.raises(ValueError, match="does not follow"):
        check_declaration("PATCH", previous_version="0.3.0", candidate_version="0.2.0")
    with pytest.raises(ValueError, match="below the semver floor"):
        check_declaration("PATCH", previous_version="0.2.0", candidate_version="0.3.0")
    # The row itself is typed: an empty authorization reference or a foreign baseline is refused,
    # and a candidate (different version) cannot take the preparation path.
    with pytest.raises(ValueError, match="authorization reference"):
        PreparationRow(ENGINE_VERSION, new_build, preparation_release, preparation_release, "  ")
    with pytest.raises(ValueError, match="own release"):
        PreparationRow(ENGINE_VERSION, new_build, preparation_release, uuid4(), "CHG-1")
    with pytest.raises(ValueError, match="only the preparation artifact"):
        prepare_release_baseline(
            ArtifactFacts("0.4.0", new_build, ENGINE_VERSION, enabled_build),
            preparation_release_id=uuid4(),
            historical_release_id=historical,
            authorization_ref="CHG-2",
        )


def test_p5_prep_r3_backfill_reconciles_the_book_population() -> None:
    """Codex P5-PREP-R3 probe shapes: the native output has only ASC606; a stored map keyed
    {'NOT_A_BOOK': sha} or {'ASC606': sha, 'IFRS15': sha} must be refused even though every hash
    value is the unchanged native CV-26; the correct single-book map still verifies; a wrong hash
    still drifts."""
    bundle = checkpoint_bundle(*COMPUTABLE)
    output = compute(bundle)
    sha = output.sha256()
    assert {b.book_code for b in output.books if b.contract_version is not None} == {"ASC606"}
    unknown_key = HeadFacts(uuid4(), uuid4(), False, bundle.sha256(), {"NOT_A_BOOK": sha})
    assert backfill_decision(unknown_key, bundle, compute).kind == (
        "BACKFILL_BOOK_POPULATION_MISMATCH"
    )
    extra_book = HeadFacts(uuid4(), uuid4(), False, bundle.sha256(), {"ASC606": sha, "IFRS15": sha})
    refused = backfill_decision(extra_book, bundle, compute)
    assert refused.kind == "BACKFILL_BOOK_POPULATION_MISMATCH"
    assert not refused.verified and refused.input_bytes is None and not refused.recompute
    missing_book = HeadFacts(uuid4(), uuid4(), False, bundle.sha256(), {})
    assert backfill_decision(missing_book, bundle, compute).kind == (
        "BACKFILL_BOOK_POPULATION_MISMATCH"
    )
    correct = HeadFacts(uuid4(), uuid4(), False, bundle.sha256(), {"ASC606": sha})
    assert backfill_decision(correct, bundle, compute).kind == "BACKFILL_VERIFIED"
    wrong_hash = HeadFacts(uuid4(), uuid4(), False, bundle.sha256(), {"ASC606": "0" * 64})
    assert backfill_decision(wrong_hash, bundle, compute).kind == "OUTPUT_DRIFTED"
    # The refusal blocks completion and is listed by the summary.
    plan = plan_prepare([extra_book])
    summary = prepare_summary(plan, [refused])
    assert summary.refused == (extra_book.group_id,) and not summary.complete
    assert "book population mismatch" in format_summary(summary)


def test_summary_is_complete_only_when_no_head_lacks_evidence() -> None:
    bundle = checkpoint_bundle(*COMPUTABLE)
    output = compute(bundle)
    good = _head(bundle.sha256(), output.sha256())
    bad = _head("f" * 64, output.sha256())
    plan = plan_prepare(
        [
            good,
            bad,
            HeadFacts(UUID(int=5), UUID(int=55), True, "a" * 64, {}),
            HeadFacts(UUID(int=6), None, False, None, {}),
        ]
    )
    outcomes = [backfill_decision(head, bundle, compute) for head in plan.to_backfill]
    summary = prepare_summary(plan, outcomes)
    assert (summary.evidenced, summary.backfilled, summary.no_head) == (1, 1, 1)
    assert summary.drifted == (bad.group_id,) and not summary.complete
    assert summary.exit_code == EXIT_INCOMPLETE
    text = format_summary(summary)
    assert "prepare INCOMPLETE" in text and str(bad.group_id) in text and "postgres" not in text
    complete = prepare_summary(plan_prepare([good]), [backfill_decision(good, bundle, compute)])
    assert complete.complete and complete.exit_code == EXIT_COMPLETE
    assert "prepare complete" in format_summary(complete)

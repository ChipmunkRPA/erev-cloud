"""``erev_api.domain.contracts.replay_verify.verify``: the RCP-28a decision over injected source,
evidence and process facts (05 RCP-28, RCP-28a; 04 T-CON-26; D-96 (1), (2), (A), (B); lane P5
preparation slice). DB-free: the engine is the real ``erev_engine.compute`` behind a spy.

The four SOP-3 named integration tests (``backend/tests/domain/contracts/test_replay_verify.py``,
CTR factories + database) remain the integration slice; these scenarios exercise the same
decision without a stored computation.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from erev_api.domain.contracts.release_validation import ExecutionToken
from erev_api.domain.contracts.replay_verify import (
    EvidenceFacts,
    ProcessFacts,
    SourceFacts,
    VerificationRow,
    verify,
)
from erev_api.enums import VerificationOutcome
from erev_engine import ENGINE_VERSION, compute, upgrade
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError
from support.billing_lines import checkpoint_bundle

V = VerificationOutcome
TOKEN = ExecutionToken(UUID(int=1), 11, 1)
COMPUTABLE = ("mod", "MOD-LEGACY-PROS-GT12", "end-june-after-prospective")


class _Spy:
    """Counts engine invocations; optionally raises."""

    def __init__(self, error: EngineError | None = None) -> None:
        self.calls = 0
        self.error = error

    def __call__(self, bundle: InputBundle) -> OutputBundle:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return compute(bundle)


def _stored() -> tuple[InputBundle, OutputBundle, SourceFacts, EvidenceFacts, ProcessFacts]:
    """A stored computation and its evidence, as the integration slice would load them."""
    bundle = checkpoint_bundle(*COMPUTABLE)
    output = compute(bundle)
    input_bytes = upgrade.encode_input(bundle)
    output_bytes = upgrade.encode_output(output)
    release = uuid4()
    source = SourceFacts(
        computation_id=uuid4(),
        combination_group_id=uuid4(),
        engine_release_id=release,
        engine_version=ENGINE_VERSION,
        input_sha256=bundle.sha256(),
        output_sha256_by_book={"ASC606": output.sha256()},
    )
    evidence = EvidenceFacts(
        input_bytes=input_bytes,
        input_file_sha256=upgrade.raw_digest(input_bytes),
        output_bytes=output_bytes,
        output_file_sha256=upgrade.raw_digest(output_bytes),
        output_sha256=output.sha256(),
        book_codes=("ASC606",),
        codec={"format_version": 1, "engine_version": ENGINE_VERSION},
    )
    process = ProcessFacts(engine_release_id=release, engine_version=ENGINE_VERSION)
    return bundle, output, source, evidence, process


def _verify(
    trigger: str,
    source: SourceFacts,
    evidence: EvidenceFacts | None,
    process: ProcessFacts,
    engine: Callable[[InputBundle], OutputBundle],
) -> VerificationRow:
    return verify(
        trigger=trigger,  # type: ignore[arg-type]
        source=source,
        evidence=evidence,
        process=process,
        engine=engine,
        token=TOKEN,
        attempt_id=uuid4(),
    )


# --- integrity (S01, S02) -------------------------------------------------------------------------


def test_same_version_integrity_replay_matches_on_l0() -> None:
    _, output, source, evidence, process = _stored()
    spy = _Spy()
    row = _verify("REPLAY_VERIFY", source, evidence, process, spy)
    assert row.outcome is V.MATCH and row.reason is None and spy.calls == 1
    assert row.engine_executed and row.executed_engine_version == ENGINE_VERSION
    assert row.actual_output_sha256 == output.sha256() == row.expected_output_sha256
    assert row.input_file_sha256_observed == row.input_file_sha256_expected
    assert row.input_transform_id is None and row.candidate_input_sha256 is None
    assert not row.integrity_incident


def test_altered_t_con_08_hash_is_a_mismatch_that_names_the_moved_copy() -> None:
    _, _, source, evidence, process = _stored()
    altered = dataclasses.replace(source, output_sha256_by_book={"ASC606": "0" * 64})
    row = _verify("REPLAY_VERIFY", altered, evidence, process, _Spy())
    # T-CON-08 disagrees with the T-CON-25 copy: the incident is raised before any execution and
    # the report can show which stored copy moved (S02 preserved).
    assert row.outcome is V.MISMATCH and row.reason == "EXPECTED_HASH_DISAGREEMENT"
    assert not row.engine_executed and row.actual_output_sha256 is None
    assert row.integrity_incident
    disagreeing = dataclasses.replace(
        source,
        output_sha256_by_book={
            "ASC606": source.output_sha256_by_book["ASC606"],
            "IFRS15": "1" * 64,
        },
    )
    assert _verify("REPLAY_VERIFY", disagreeing, evidence, process, _Spy()).reason == (
        "EXPECTED_HASH_DISAGREEMENT"
    )


def test_l0_mismatch_when_the_engine_output_differs() -> None:
    _, output, source, evidence, process = _stored()
    other = dataclasses.replace(output, diagnostics=(*output.diagnostics,))  # same
    assert other.sha256() == output.sha256()

    def different(bundle: InputBundle) -> OutputBundle:
        real = compute(bundle)
        return dataclasses.replace(real, input_sha256="e" * 64)  # a tampered output

    row = _verify("REPLAY_VERIFY", source, evidence, process, different)
    assert row.outcome is V.MISMATCH and row.reason == "L0_MISMATCH" and row.engine_executed
    assert row.actual_output_sha256 != row.expected_output_sha256


# --- A: unavailable runtime is stored without an execution ----------------------------------------


def test_source_runtime_unavailable_is_stored_and_compute_is_not_invoked() -> None:
    _, _, source, evidence, _ = _stored()
    other_process = ProcessFacts(engine_release_id=uuid4(), engine_version="9.9.9")
    spy = _Spy()
    row = _verify("REPLAY_VERIFY", source, evidence, other_process, spy)
    assert spy.calls == 0
    assert row.outcome is V.UNVERIFIABLE and row.reason == "SOURCE_RUNTIME_UNAVAILABLE"
    assert row.engine_executed is False
    assert row.executed_engine_release_id is None and row.executed_engine_version is None
    assert row.actual_output_sha256 is None
    # The source identity is preserved, never retagged; the process identity is recorded apart.
    assert row.source_engine_version == ENGINE_VERSION and row.process_engine_version == "9.9.9"
    assert row.source_engine_release_id == source.engine_release_id


def test_executed_identity_checks_refuse_malformed_rows() -> None:
    _, _, source, evidence, process = _stored()
    good = _verify("REPLAY_VERIFY", source, evidence, process, _Spy())
    with pytest.raises(ValueError, match="ck_cv__executed_identity"):
        dataclasses.replace(good, executed_engine_release_id=None)  # executed with a NULL id
    with pytest.raises(ValueError, match="ck_cv__executed_identity"):
        dataclasses.replace(good, engine_executed=False, actual_output_sha256=None)  # ids kept
    with pytest.raises(ValueError, match="ck_cv__no_output_without_execution"):
        dataclasses.replace(
            good,
            engine_executed=False,
            executed_engine_release_id=None,
            executed_engine_version=None,
            outcome=V.UNVERIFIABLE,
            reason="SOURCE_RUNTIME_UNAVAILABLE",
        )  # not executed but an actual output remains
    with pytest.raises(ValueError, match="ck_cv__integrity_source"):
        dataclasses.replace(
            good, source_computation_id=None, outcome=V.NO_SOURCE, reason="ENGINE_ERROR"
        )
    with pytest.raises(ValueError, match="ck_cv__candidate_release"):
        dataclasses.replace(good, trigger="UPGRADE_VALIDATE", executed_engine_release_id=uuid4())
    with pytest.raises(ValueError, match="reason is required"):
        dataclasses.replace(good, outcome=V.DIFFERENCES)
    # A started-but-failed execution keeps engine_executed = true with a NULL actual output.
    failed = dataclasses.replace(
        good, actual_output_sha256=None, outcome=V.ERROR, reason="ENGINE_ERROR"
    )
    assert failed.engine_executed and failed.actual_output_sha256 is None


# --- evidence order (R1) --------------------------------------------------------------------------


def test_missing_evidence_is_unverifiable_never_a_rebuild() -> None:
    _, _, source, _, process = _stored()
    spy = _Spy()
    row = _verify("REPLAY_VERIFY", source, None, process, spy)
    assert row.outcome is V.UNVERIFIABLE and row.reason == "INPUT_EVIDENCE_MISSING"
    assert spy.calls == 0 and not row.engine_executed


def test_known_at_only_byte_change_fails_the_raw_digest_while_the_logical_hash_holds() -> None:
    bundle, _, source, evidence, process = _stored()
    moved = dataclasses.replace(bundle, known_at=bundle.known_at.replace(minute=59))
    tampered = dataclasses.replace(evidence, input_bytes=upgrade.encode_input(moved))
    assert upgrade.decode_input(tampered.input_bytes).sha256() == source.input_sha256  # CV-25
    spy = _Spy()
    row = _verify("REPLAY_VERIFY", source, tampered, process, spy)
    assert row.outcome is V.MISMATCH and row.reason == "INPUT_EVIDENCE_HASH_MISMATCH"
    assert row.input_file_sha256_observed != row.input_file_sha256_expected and spy.calls == 0


def test_hashed_field_change_with_a_refreshed_digest_fails_the_logical_hash() -> None:
    bundle, _, source, evidence, process = _stored()
    changed = dataclasses.replace(
        bundle, tenant_preset="LEGACY_PARITY" if bundle.tenant_preset == "DEFAULT" else "DEFAULT"
    )
    new_bytes = upgrade.encode_input(changed)
    tampered = dataclasses.replace(
        evidence, input_bytes=new_bytes, input_file_sha256=upgrade.raw_digest(new_bytes)
    )
    row = _verify("REPLAY_VERIFY", source, tampered, process, _Spy())
    assert row.outcome is V.MISMATCH and row.reason == "LOGICAL_HASH_MISMATCH"


def test_output_evidence_digest_and_book_set_are_checked() -> None:
    _, _, source, evidence, process = _stored()
    bad_output = dataclasses.replace(evidence, output_bytes=evidence.output_bytes + b" ")
    assert _verify("REPLAY_VERIFY", source, bad_output, process, _Spy()).reason == (
        "OUTPUT_EVIDENCE_HASH_MISMATCH"
    )
    other_books = dataclasses.replace(evidence, book_codes=("ASC606", "IFRS15"))
    assert _verify("REPLAY_VERIFY", source, other_books, process, _Spy()).reason == (
        "EXPECTED_HASH_DISAGREEMENT"
    )


# --- candidate validation (S04, S06) --------------------------------------------------------------


def test_candidate_stamp_only_release_matches_on_l1_with_r_count_3() -> None:
    _, _, source, evidence, _ = _stored()
    old_source = dataclasses.replace(source, engine_version="0.2.0")
    # The stored bundle carries the 0.2.0 stamp; the candidate process runs ENGINE_VERSION.
    bundle = upgrade.decode_input(evidence.input_bytes)
    old_bundle = dataclasses.replace(bundle, engine_version="0.2.0")
    old_bytes = upgrade.encode_input(old_bundle)
    old_output = compute(dataclasses.replace(old_bundle, engine_version=ENGINE_VERSION))
    # An output "stored under 0.2.0": the same computation with the older stamp fields.
    old_mapping = upgrade.output_mapping(old_output)
    old_mapping["engine_version"] = "0.2.0"
    old_mapping["input_sha256"] = old_bundle.sha256()
    for book in old_mapping["books"]:
        book["trace"]["engine_version"] = "0.2.0"
    from erev_engine.canonical import canonical_bytes, sha256_hex

    old_output_bytes = canonical_bytes(old_mapping)
    old_hash = sha256_hex(old_mapping)
    old_evidence = EvidenceFacts(
        input_bytes=old_bytes,
        input_file_sha256=upgrade.raw_digest(old_bytes),
        output_bytes=old_output_bytes,
        output_file_sha256=upgrade.raw_digest(old_output_bytes),
        output_sha256=old_hash,
        book_codes=("ASC606",),
        codec={"format_version": 1, "engine_version": "0.2.0"},
    )
    old_source = dataclasses.replace(
        old_source, input_sha256=old_bundle.sha256(), output_sha256_by_book={"ASC606": old_hash}
    )
    process = ProcessFacts(engine_release_id=uuid4(), engine_version=ENGINE_VERSION)
    spy = _Spy()
    row = _verify("UPGRADE_VALIDATE", old_source, old_evidence, process, spy)
    assert spy.calls == 1 and row.engine_executed
    assert row.executed_engine_release_id == process.engine_release_id  # ck_cv__candidate_release
    assert row.input_transform_id == f"0.2.0->{ENGINE_VERSION}:0.2.0->0.3.0"
    assert row.candidate_input_sha256 != old_source.input_sha256  # the stamp is hashed
    assert row.normalised_input_match is True
    assert row.outcome is V.MATCH and row.reason is None  # L1 equal
    assert row.actual_output_sha256 != old_hash  # L0 unequal across versions by construction
    assert row.difference_summary == {
        "M": 0,
        "P": 0,
        "T": 0,
        "R": 3,
        "changed_r_paths": row.difference_summary["changed_r_paths"],
    }  # type: ignore[index]
    # The integrity path for the same source under the new process: unavailable runtime.
    assert _verify("REPLAY_VERIFY", old_source, old_evidence, process, _Spy()).reason == (
        "SOURCE_RUNTIME_UNAVAILABLE"
    )


def test_candidate_with_a_money_difference_is_differences_never_mismatch() -> None:
    _, _, source, evidence, process = _stored()

    def changed(bundle: InputBundle) -> OutputBundle:
        real = compute(bundle)
        book = real.books[0]
        version = book.contract_version
        assert version is not None
        columns = dict(version.columns)
        key = next(k for k in sorted(columns) if k == "transaction_price")
        columns[key] = columns[key] + 1  # type: ignore[operator]
        return dataclasses.replace(
            real,
            books=(
                dataclasses.replace(
                    book, contract_version=dataclasses.replace(version, columns=columns)
                ),
            ),
        )

    row = _verify("UPGRADE_VALIDATE", source, evidence, process, changed)
    assert row.outcome is V.DIFFERENCES and row.reason == "L1_DIFFERENCES"
    assert row.difference_summary is not None and row.difference_summary["M"] >= 1  # type: ignore[index, operator]
    assert not row.integrity_incident


def test_no_input_transform_is_unverifiable_and_not_executed() -> None:
    _, _, source, evidence, _ = _stored()
    unreachable = dataclasses.replace(source, engine_version="0.0.1")
    bundle = upgrade.decode_input(evidence.input_bytes)
    older = dataclasses.replace(bundle, engine_version="0.0.1")
    older_bytes = upgrade.encode_input(older)
    ev = dataclasses.replace(
        evidence, input_bytes=older_bytes, input_file_sha256=upgrade.raw_digest(older_bytes)
    )
    unreachable = dataclasses.replace(unreachable, input_sha256=older.sha256())
    process = ProcessFacts(engine_release_id=uuid4(), engine_version=ENGINE_VERSION)
    spy = _Spy()
    row = _verify("UPGRADE_VALIDATE", unreachable, ev, process, spy)
    assert row.outcome is V.UNVERIFIABLE and row.reason == "NO_INPUT_TRANSFORM"
    assert spy.calls == 0 and not row.engine_executed


def test_engine_error_is_error_with_executed_identity_and_null_output() -> None:
    _, _, source, evidence, process = _stored()
    spy = _Spy(EngineError("ENGINE_INVARIANT_VIOLATED", "probe"))
    row = _verify("REPLAY_VERIFY", source, evidence, process, spy)
    assert row.outcome is V.ERROR and row.reason == "ENGINE_ERROR"
    assert row.engine_executed and row.executed_engine_version == ENGINE_VERSION
    assert row.actual_output_sha256 is None and spy.calls == 1

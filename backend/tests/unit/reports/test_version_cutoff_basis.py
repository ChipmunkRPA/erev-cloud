"""F-RPS-CUTOFF-R1 (record §43; Codex packet production-20260920-1826): the record cutoff of report
reads has two bases. L6-3-Q-19's *record* basis widens a run's ``known_at`` to the later of it and
the transaction timestamp — right for a run whose ``known_at`` defaulted to the application clock
(a FrozenClock test world stamps versions with the later server time). An explicit as-of read —
the platform runner's checkpoint reads (READ-1: ``contract_version.known_at <= known_at`` of the
ledger stamp) or any run created with a ``known_at`` parameter — must keep the supplied cutoff, or
a report requested as of an earlier checkpoint selects a LATER contract version (the witness:
``v10.known_at <= k < v11.known_at <= r`` → the widened reader picks v11, READ-1 picks v10, and
March money can be identical, so amounts alone prove nothing about version provenance).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.domain.reports import framework, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.catalogue import HISTORICAL_BASIS, KNOWN_AT_BASIS_KEY, RECORD_BASIS

K = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)  # the checkpoint's captured server stamp
R = datetime(2026, 4, 9, 9, 30, tzinfo=UTC)  # the report job's transaction timestamp
V10, V11 = datetime(2026, 3, 30, 8, tzinfo=UTC), datetime(2026, 4, 2, 8, tzinfo=UTC)


def _selected(cutoff: datetime) -> str:
    """What ``latest_versions`` selects for one group: the greatest version recorded by cutoff."""
    return "v11" if V11 <= cutoff else "v10"


def test_the_witness_a_historical_read_keeps_its_supplied_cutoff() -> None:
    """READ-1: with the checkpoint stamp k as the cutoff the reader selects v10; the record basis
    (L6-3-Q-19) widens k to the transaction time r and selects v11 — the defect Codex measured."""
    assert V10 <= K < V11 <= R
    assert tie_outs.effective_cutoff(K, R, historical=False) == R  # L6-3-Q-19, unchanged
    assert _selected(tie_outs.effective_cutoff(K, R, historical=False)) == "v11"
    assert tie_outs.effective_cutoff(K, R, historical=True) == K  # READ-1
    assert _selected(tie_outs.effective_cutoff(K, R, historical=True)) == "v10"


def test_the_record_basis_is_unchanged_for_default_runs() -> None:
    """A default run's ``known_at`` is the application clock and may lag the server: the record
    basis still reads what the job's transaction can see; a known_at after the transaction time
    (a clock ahead of the server) stays as supplied under both bases."""
    later = datetime(2026, 4, 9, 9, 31, tzinfo=UTC)
    assert tie_outs.effective_cutoff(K, R) == R
    assert tie_outs.effective_cutoff(later, R) == later
    assert tie_outs.effective_cutoff(later, R, historical=True) == later
    with pytest.raises(TypeError):
        tie_outs.effective_cutoff(K, None, historical=False)  # type: ignore[arg-type]


def _stored_run(parameters: dict[str, object]) -> dict[str, object]:
    """A stored ``report_run`` row as ``run_report``, ``rerun`` and ``explain_cell`` read it."""
    return {
        "report_code": "balance_aging",
        "report_version": 1,
        "parameters": parameters,
        "entity_ids": [str(uuid5(NAMESPACE_URL, "erev://tests/entity/US01"))],
        "known_at": K,
        "book_code": "ASC606",
        "as_of_date": None,
        "period_lock_id": None,
        "output_format": "json",
    }


def test_the_stored_basis_decides_the_cutoff_for_run_rerun_and_explain_alike() -> None:
    """The real framework path: ``report_params`` over a stored run derives ``historical`` from the
    stored ``known_at_basis`` parameter — never from the presence or value of ``known_at`` (both
    are normalised into every stored run) — so the job, a rerun and the explain route read the
    same version cutoff."""
    base = {"entity_codes": ["US01"], "book": "ASC606", "period_key": "FY2026-P03", "known_at": "x"}
    assert framework.report_params(
        _stored_run({**base, KNOWN_AT_BASIS_KEY: HISTORICAL_BASIS})
    ).historical
    assert not framework.report_params(
        _stored_run({**base, KNOWN_AT_BASIS_KEY: RECORD_BASIS})
    ).historical
    assert not framework.report_params(_stored_run(base)).historical  # a run stored before the key
    assert ReportParams("balance_aging", 1, {}, (), K).historical is False


def test_resolve_basis_from_the_callers_parameters_before_normalisation() -> None:
    """``_resolve`` decides the basis from what the caller supplied: historical when ``known_at``
    was supplied, record when it defaulted; a supplied basis is honoured — ``historical`` without
    a ``known_at`` is refused (no cutoff to hold), ``record`` with a ``known_at`` is an explicit
    compatibility read."""
    assert framework.resolve_basis({}, known_at_given=False) == (RECORD_BASIS, [])
    assert framework.resolve_basis({"known_at": "…"}, known_at_given=True) == (HISTORICAL_BASIS, [])
    basis, errors = framework.resolve_basis(
        {KNOWN_AT_BASIS_KEY: HISTORICAL_BASIS}, known_at_given=False
    )
    assert basis == HISTORICAL_BASIS and len(errors) == 1
    assert errors[0].field == f"parameters.{KNOWN_AT_BASIS_KEY}"
    assert errors[0].message == framework.BASIS_NEEDS_KNOWN_AT
    assert framework.resolve_basis(
        {"known_at": "…", KNOWN_AT_BASIS_KEY: RECORD_BASIS}, known_at_given=True
    ) == (RECORD_BASIS, [])
    assert framework.resolve_basis(
        {"known_at": "…", KNOWN_AT_BASIS_KEY: HISTORICAL_BASIS}, known_at_given=True
    ) == (HISTORICAL_BASIS, [])


def test_a_run_stored_before_the_parameter_reads_on_the_record_basis() -> None:
    """Codex 1845: a stored run without ``known_at_basis`` — created before the parameter existed —
    is the record basis; the basis is read from the stored row, never inferred from its stored
    ``known_at``. ``rerun`` copies the stored parameters without re-resolving them and
    ``explain_cell`` reads the run row, so both stay on the record basis too."""
    legacy = _stored_run({framework.KNOWN_AT: "2026-03-31T12:00:00Z"})
    assert framework.KNOWN_AT_BASIS not in legacy["parameters"]
    params = framework.report_params(legacy)
    assert params.historical is False
    assert params.known_at == legacy["known_at"]

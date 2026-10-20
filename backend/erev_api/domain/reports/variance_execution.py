"""Execute retained close-variance inputs after the authorized read transaction ends.

Original computations must reproduce their retained output hashes and frozen money
before counterfactual replay. Replay uses a common earlier posting basis, so posting
an earlier computation is not counted a second time as a business event. The final
counterfactual must still reproduce the later frozen money exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import BookInput, InputBundle, OutputBundle
from erev_engine.stages.s15_disclosures.variance import Evaluation, decompose

from erev_api.problems import Problem

from .computation_sources import VerifiedComputation
from .variance_projection import Projection
from .variance_replay import (
    Engine,
    Execution,
    Metrics,
    Replay,
    replay_period_money,
    validate_reporting_pair,
)
from .variance_reporting import Basis


@dataclass(frozen=True)
class SourceExecution:
    computation_id: UUID
    input_sha256: str
    output_sha256: str


@dataclass(frozen=True)
class RetainedReplay:
    earlier: SourceExecution
    later: SourceExecution
    normalized_fields: tuple[str, ...]
    replay_input_sha256: str
    replay: Replay


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Retained close variance: {detail}")


def _readback_books(
    earlier: InputBundle, later: InputBundle, reproduced: OutputBundle
) -> tuple[tuple[BookInput, ...], tuple[str, ...]]:
    """Remove only new SSP readbacks proven by the earlier original output.

    First pricing selects a version; the next input records that choice. This is
    persistence of the same decision, not a new SSP election. Modification weight
    readbacks and changes to an existing choice require their own replay phase.
    """
    old_books = {book.book_code: book for book in earlier.books}
    outputs = {book.book_code: book for book in reproduced.books}
    books = []
    normalized = []
    for book in later.books:
        old = old_books.get(book.book_code)
        output = outputs.get(book.book_code)
        if old is None or output is None:
            books.append(book)
            continue
        identities = {(p.code, p.scope, p.subject_key) for p in old.policies}
        priced = {
            row.subject_key: row.columns.get("ssp_book_version_key")
            for row in output.obligation_versions
        }
        kept = []
        for policy in book.policies:
            if (
                (policy.code, policy.scope, policy.subject_key) not in identities
                and policy.code == "ssp.version_basis"
                and policy.scope == "OBLIGATION"
                and policy.level == "O"
                and policy.source_ref == "RECORDED"
                and policy.pin == "K"
                and isinstance(priced.get(policy.subject_key), str)
                and policy.value == {"recorded": priced[policy.subject_key]}
            ):
                normalized.append(f"books.{book.book_code}.ssp_readback.{policy.subject_key}")
            else:
                kept.append(policy)
        books.append(replace(book, policies=tuple(kept)))
    return tuple(books), tuple(normalized)


def verify_source(
    source: VerifiedComputation,
    expected: Metrics,
    *,
    entity_code: str,
    book_code: str,
    period_key: str,
    currency_view: Literal["transaction", "functional", "reporting"] = "transaction",
    engine: Engine = compute,
    reporting_basis: Basis | None = None,
) -> tuple[SourceExecution, OutputBundle]:
    if source.bundle.engine_version != ENGINE_VERSION:
        raise _refuse("the retained engine runtime is unavailable.")
    if any(not isinstance(value, Fraction) for value in expected.values()):
        raise _refuse("frozen amounts must be exact fractions.")
    output = engine(source.bundle)
    if (
        output.engine_version != source.bundle.engine_version
        or output.input_sha256 != source.bundle.sha256()
        or output.sha256() != source.output_sha256
    ):
        raise _refuse("the original computation does not reproduce its retained output.")
    actual = Projection(
        source.bundle, entity_code, book_code, period_key, currency_view, reporting_basis
    )(output)
    if any(
        actual.get(key, Fraction(0)) != expected.get(key, Fraction(0))
        for key in actual.keys() | expected.keys()
    ):
        raise _refuse("the original computation does not reproduce its frozen endpoint.")
    return SourceExecution(source.computation_id, source.bundle.sha256(), output.sha256()), output


def execute(
    earlier: VerifiedComputation,
    later: VerifiedComputation,
    *,
    entity_code: str,
    book_code: str,
    period_key: str,
    earlier_metrics: Metrics,
    later_metrics: Metrics,
    currency_view: Literal["transaction", "functional", "reporting"] = "transaction",
    earlier_reporting_basis: Basis | None = None,
    later_reporting_basis: Basis | None = None,
    engine: Engine = compute,
) -> RetainedReplay:
    """Pure calculation phase; accepts no session and never persists engine output.

    The caller supplies authorized sources and frozen endpoints for this group.
    References and FX use explicit replay phases; calendar/membership changes
    still require population replay.
    Normalization is explicit evidence, not an alteration of the retained source.
    """
    validate_reporting_pair(currency_view, earlier_reporting_basis, later_reporting_basis)
    if earlier.group_id != later.group_id:
        raise _refuse("group membership changes require a separate replay phase.")
    for source in (earlier, later):
        if source.bundle.engine_version != ENGINE_VERSION:
            raise _refuse("the retained engine runtime is unavailable.")
    for expected in (earlier_metrics, later_metrics):
        if any(not isinstance(value, Fraction) for value in expected.values()):
            raise _refuse("frozen amounts must be exact fractions.")

    before, earlier_output = verify_source(
        earlier,
        earlier_metrics,
        entity_code=entity_code,
        book_code=book_code,
        period_key=period_key,
        currency_view=currency_view,
        reporting_basis=earlier_reporting_basis,
        engine=engine,
    )
    after, _ = verify_source(
        later,
        later_metrics,
        entity_code=entity_code,
        book_code=book_code,
        period_key=period_key,
        currency_view=currency_view,
        reporting_basis=later_reporting_basis,
        engine=engine,
    )
    if earlier.computation_id == later.computation_id:
        if earlier.bundle != later.bundle or before != after:
            raise _refuse("one computation identity has inconsistent retained sources.")
        # Two closes may select the same last computation. Do not invent a later
        # input cutoff just to satisfy the event replay's chronological contract.
        measures = {
            key: decompose(
                earlier_metrics.get(key, Fraction(0)),
                [
                    Evaluation(
                        "FX" if currency_view == "reporting" else "PROGRESS",
                        later_metrics.get(key, Fraction(0)),
                    )
                ],
            )
            for key in sorted(earlier_metrics.keys() | later_metrics.keys())
        }
        replay = Replay(ENGINE_VERSION, (), MappingProxyType(measures))
        if earlier_reporting_basis is not None and later_reporting_basis is not None:
            replay = replace(
                replay,
                executions=(
                    Execution(
                        "FX", (), before.input_sha256, before.output_sha256, ("reporting_rates",)
                    ),
                ),
                reporting_basis_sha256=(
                    earlier_reporting_basis.evidence_sha256,
                    later_reporting_basis.evidence_sha256,
                ),
            )
        return RetainedReplay(before, after, (), later.bundle.sha256(), replay)

    normalized = []
    if earlier.bundle.posted != later.bundle.posted:
        normalized.append("posted")
    if earlier.bundle.group.previous_stream_heads != later.bundle.group.previous_stream_heads:
        normalized.append("group.previous_stream_heads")
    books, readbacks = _readback_books(earlier.bundle, later.bundle, earlier_output)
    normalized.extend(readbacks)
    counterfactual = replace(
        later.bundle,
        books=books,
        posted=earlier.bundle.posted,
        group=replace(
            later.bundle.group,
            previous_stream_heads=earlier.bundle.group.previous_stream_heads,
        ),
    )
    replay = replay_period_money(
        earlier.bundle,
        counterfactual,
        entity_code=entity_code,
        book_code=book_code,
        period_key=period_key,
        earlier_metrics=earlier_metrics,
        later_metrics=later_metrics,
        currency_view=currency_view,
        earlier_reporting_basis=earlier_reporting_basis,
        later_reporting_basis=later_reporting_basis,
        engine=engine,
    )
    return RetainedReplay(before, after, tuple(normalized), counterfactual.sha256(), replay)

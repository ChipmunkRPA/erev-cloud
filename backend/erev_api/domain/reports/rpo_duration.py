"""Original contract terms from the retained engine input, never current end dates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import localcontext
from uuid import UUID

from erev_engine import ENGINE_VERSION, fold_book, guards, money
from erev_engine.bundle import InputBundle
from erev_engine.stages import s01_canonicalize, s13_books
from erev_engine.stages.state import SegmentCause
from erev_engine.trace import TraceBuilder
from sqlalchemy import select

from erev_api.db.tables import contract_version
from erev_api.domain.reports import computation_sources
from erev_api.domain.reports.builders import ReportParams
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def original_ends(bundle: InputBundle, book_code: str) -> dict[str, date]:
    """Use the same inception segments as stage 15's POL-197 predicate.

    Folding retained input reads templates, voids and combination membership as originally
    admitted. It does not execute posting, rebuild inputs, mutate state or change output hashes.
    """
    if bundle.engine_version != ENGINE_VERSION:
        raise Problem("validation-failed", "Original RPO terms require a supported engine version.")
    guards.no_floats(bundle)
    book = next((book for book in bundle.books if book.book_code == book_code), None)
    if book is None:
        raise Problem("validation-failed", "The retained RPO source does not contain this book.")
    with localcontext(money.DECIMAL_CONTEXT):
        trace = TraceBuilder(engine_version=ENGINE_VERSION)
        canonical = s01_canonicalize.run(bundle, trace)
        allocated = fold_book(s13_books.book_context(canonical, book), canonical, trace)
    result = {view.header.external_id: view.header.inception_date for view in allocated.contracts}
    for ob in allocated.obligations:
        if ob.segments and ob.segments[0].cause == SegmentCause.INCEPTION:
            end = ob.segments[0].totals.end_date
            if end is not None:
                result[ob.contract_key] = max(result[ob.contract_key], end)
    return result


def read(
    uow: UnitOfWork | None,
    version_ids: Sequence[UUID],
    *,
    book_code: str,
    permission: str = "report.run",
    params: ReportParams | None = None,
) -> dict[UUID, Mapping[str, date]]:
    evidence_key = "original_rpo_terms_v1"
    if params is not None and params.binding is not None:
        try:
            evidence = params.binding.evidence[evidence_key]
            if evidence["book"] != book_code:
                raise ValueError("book differs")
            return {
                version: {
                    key: date.fromisoformat(value)
                    for key, value in evidence["versions"][str(version)].items()
                }
                for version in version_ids
            }
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            raise Problem(
                "validation-failed", "Retained original RPO terms are missing."
            ) from error
    if uow is None:
        raise Problem("validation-failed", "Original RPO terms require retained source access.")
    if params is not None and params.requester is not None:
        uow = UnitOfWork(
            ctx=params.requester,
            session=uow.session,
            clock=uow.clock,
            keyring=uow.keyring,
            files=uow.files,
        )
    references: dict[UUID, UUID | None] = {
        row.id: row.contract_computation_id
        for row in uow.session.execute(
            select(contract_version.c.id, contract_version.c.contract_computation_id).where(
                contract_version.c.id.in_(version_ids),
                contract_version.c.book_code == book_code,
            )
        )
    }
    if set(references) != set(version_ids) or any(value is None for value in references.values()):
        raise Problem("validation-failed", "Original RPO terms lack retained computation evidence.")
    cached = {}
    for computation_id in set(references.values()):
        assert computation_id is not None
        source = computation_sources.read_for_report(
            uow,
            computation_id,
            permission=permission,
            system_snapshot=(
                params is not None
                and params.snapshot_read
                and uow.principal.kind == PrincipalKind.SYSTEM
            ),
        )
        cached[computation_id] = original_ends(source.bundle, book_code)
    result: dict[UUID, Mapping[str, date]] = {
        version: cached[computation]
        for version, computation in references.items()
        if computation is not None
    }
    if params is not None and params.sources is not None:
        params.sources.record_evidence(
            evidence_key,
            {
                "book": book_code,
                "versions": {
                    str(version): {key: value.isoformat() for key, value in ends.items()}
                    for version, ends in result.items()
                },
            },
        )
    return result

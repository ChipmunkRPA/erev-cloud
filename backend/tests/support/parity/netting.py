"""The ``NETTING_RECLASS`` step of a close run in the golden parity worlds (05 RCP-06, RCP-08(b);
ENGINE_SPEC_B S14-R-05, Table 14-A; POLICIES JET-06, CHK-022; DEVIATIONS PJR-3; BUILD_SPEC GPB-1;
L7-1-Q-6).

The release candidate posts no time-driven amount through the platform: the close-run steps that
post JET-06 are CLO-19 and CLO-20, both post-rc. The legacy journal views of the parity cases book
the period-end reclass of a debit position (Contract 2 in January 2023: Dr 15002 58.85 / Cr 21002,
CHK-022; PJR-3), so after each committed upload the parity world stands in for that step:

1. for each combination group with a head computation, the platform bundle at the unit of work's
   instant with trigger ``CLOSE_RELEASE`` (``bundles.build``), which carries the sealed subledger
   lines as ``posted`` (RCP-05);
2. the engine's ``NETTING_RECLASS`` pass over the framework books: stages 01 to 14 with stage 14
   bound to the pass (S14-R-05), as the answer-key runner runs its close pass (D-85a). An ``ERROR``
   finding refuses the pass;
3. the pass's ``TIME`` intents per (entity, period of ``horizon``), sealed through
   ``computation._post_book``, the platform's own line builder, under a ``SUCCEEDED`` close run of
   that entity, book and period (T-CLS-01; T-SL-01 requires a close run for ``CLOSE_RELEASE``).

Nothing else is written: no computation, contract version or obligation version, so the probe
version counts and the GPA readers see what the import pipeline wrote. Every path posts "cumulative
target minus posted" (RCP-06), so a pass with nothing new posts nothing. Intents of periods outside
``horizon`` (the FY2024 reversal of the December reclass) are not posted, as in
``support.worlds.uat_ledger_world``.

[J] RCP-08(b) keys the reclass posting ``reclass:<close_run_id>:<entity_id>``, while
``_post_book`` posts one ``CLOSE_RELEASE`` posting ``release:<close_run_id>:<group_id>`` per group.
The legacy views sum lines whatever their posting, so the journal figures do not depend on it.
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_api.db import new_id
from erev_api.db.tables import close_run, combination_group
from erev_api.domain.contracts import bundles, computation
from erev_api.enums import BookCode, CloseRunStatus, ComputationTrigger
from erev_engine import ENGINE_VERSION, assemble_output, money
from erev_engine.bundle import InputBundle, OutputBundle, PostingIntent
from erev_engine.stages import STAGES, StageSpec, s01_canonicalize, s13_books
from erev_engine.trace import TraceBuilder
from sqlalchemy import insert, select

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork
    from support.factories import Workspace

__all__ = ["PASS_NAME", "netting_pass", "post_netting_reclass"]

PASS_NAME: Final = "NETTING_RECLASS"  # S14-R-05 pass and T-CLS-01 step code
TIME_CLASS: Final = "TIME"
ERROR: Final = "ERROR"


def _bound(spec: StageSpec) -> StageSpec:
    """Stage 14 bound to the pass (S14-R-05)."""
    entry: Callable[..., object] = spec.entry

    def run(ctx: object, state: object, tb: object, **bound: object) -> object:
        return entry(ctx, state, tb, **bound, pass_name=PASS_NAME)

    return dataclasses.replace(spec, entry=run)


def netting_pass(bundle: InputBundle) -> OutputBundle:
    """The ``NETTING_RECLASS`` pass over the framework books of a ``CLOSE_RELEASE`` bundle."""
    framework = tuple(book for book in bundle.books if book.book_code != BookCode.LEGACY.value)
    value = dataclasses.replace(bundle, books=framework)
    specs = tuple(_bound(spec) if spec.stage == "14" else spec for spec in STAGES)
    errors: list[str] = []

    def check(book: str | None, state: object) -> None:
        errors.extend(
            f"{book}:{finding.code}:{finding.subject_key}"
            for finding in getattr(state, "findings", ())
            if finding.severity == ERROR
        )

    with decimal.localcontext(money.DECIMAL_CONTEXT):
        canonical = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
        results = s13_books.run_books(canonical, specs, check=check)
        if errors:
            raise AssertionError(f"the netting pass collected blocking findings {sorted(errors)}")
        return assemble_output(value, canonical, results)


def _close_run(
    uow: UnitOfWork,
    *,
    book_code: str,
    entity: tuple[UUID, str],
    period: tuple[UUID, str],
) -> UUID:
    """A ``SUCCEEDED`` close run of one entity, book and period that ran only this step."""
    principal = uow.principal
    run_id = new_id()
    stamps: dict[str, Any] = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    uow.session.execute(
        insert(close_run).values(
            tenant_id=principal.tenant_id,
            id=run_id,
            close_run_no=f"PARITY-{entity[1]}-{period[1]}-{run_id.hex[:12]}",
            entity_id=entity[0],
            book_code=book_code,
            period_id=period[0],
            status=CloseRunStatus.SUCCEEDED.value,
            cutoff_known_at=uow.now,
            current_step_code=None,
            steps=[{"code": PASS_NAME, "status": CloseRunStatus.SUCCEEDED.value}],
            counts={},
            started_at=uow.now,
            finished_at=uow.now,
            **stamps,
        )
    )
    return run_id


def post_netting_reclass(place: Workspace, horizon: frozenset[str]) -> int:
    """Steps 1 to 3 of the module docstring in one unit of work; the number of lines sealed."""
    sealed = 0
    with place.uow() as uow:
        session = uow.session
        groups = session.execute(
            select(combination_group.c.id, combination_group.c.head_computation_id)
            .where(combination_group.c.head_computation_id.is_not(None))
            .order_by(combination_group.c.code)
        ).all()
        for group_id, head_computation_id in groups:
            bundle = bundles.build(
                session, UUID(str(group_id)), uow.now, (), ComputationTrigger.CLOSE_RELEASE
            )
            output = netting_pass(bundle)
            found = bundles.index(session, bundle)
            for book_output in output.books:
                split: dict[tuple[str, str], list[PostingIntent]] = {}
                for intent in book_output.posting_intents:
                    if intent.posting_class == TIME_CLASS and intent.posting_period_key in horizon:
                        key = (intent.entity, intent.posting_period_key)
                        split.setdefault(key, []).append(intent)
                for (entity_code, period_key), intents in sorted(split.items()):
                    period_id, _ = found.periods[(entity_code, period_key)]
                    run_id = _close_run(
                        uow,
                        book_code=book_output.book_code,
                        entity=(UUID(str(found.entities[entity_code]["id"])), entity_code),
                        period=(UUID(str(period_id)), period_key),
                    )
                    posted = computation._post_book(
                        uow,
                        bundle,
                        found,
                        dataclasses.replace(book_output, posting_intents=tuple(intents)),
                        computation_id=UUID(str(head_computation_id)),
                        stored=None,
                        close_run_id=run_id,
                    )
                    sealed += 0 if posted is None else len(posted.line_ids)
        uow.commit()
    return sealed

"""The seeded close of the demo world, a stage ``erev seed demo`` runs only when asked (PRD §2.1
WLD-R-02, §2.2 WLD-P-02, WLD-P-04; BUILD_SPEC CLO-22; dev-guide DG-MK-seed ``--with-close``;
supervisor ruling of 2026-10-01 on lane F-ADM-WEB's design line, item 12).

Why a stage and not a part of every seed. A lock costs what the product's close costs: the close
run reads every computed contract group of the entity in each of its three period-end passes,
which is minutes for eight months of the demo world, and the seed runs before every end-to-end
stack and in every test module of the demo world. The default seed therefore leaves every period
of 2026 ``open``, as before; ``--with-close`` adds the close.

What the stage closes: ``CLOSED`` — AVM-US, book ``ASC606``, January to August 2026 — one period
after the other through ``closing.close_period``, with ``maya`` preparing, ``priya`` approving the
journal run and reviewing the reconciliations, and ``marcus`` deciding each lock (WLD-P-02). The
other entities and books stay ``open``; AVM-JP cannot be closed as it is seeded, because the engine
finds no SSP for three of its licences and a close run ends ``BLOCKED`` on them.

Where the stage stands (WLD-P-04: the seed executes periods in order). A pending request, an open
hold and a submitted judgement record hold every period of their entity (``close.gates``), and so
does an import's exception item. The seeded open-period items WLD-B-01, WLD-B-03 and WLD-B-05 sit on
AVM-US contracts and WLD-B-04 is an import of AVM-US contracts, so the close comes after the
contracts and before those items: the background builder books its contracts and leaves the three
items, ``build`` closes the months and then makes them (``background.open_period_items``), and the
imports builder follows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from erev_api.domain.demo import closing
from erev_api.domain.demo.avenmoor import ACCOUNTANT, CONTROLLER, SSP_APPROVER, background
from erev_api.enums import BookCode

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

CAST: Final = closing.ClosingCast(preparer=ACCOUNTANT, reviewer=SSP_APPROVER, controller=CONTROLLER)
# PRD WLD-P-02: January to August 2026 in the calendar of the January entities.
PERIOD_KEYS: Final = tuple(f"FY2026-P{month:02d}" for month in range(1, 9))
# (entity, book) the stage closes, each over ``PERIOD_KEYS`` in order.
CLOSED: Final[tuple[tuple[str, BookCode], ...]] = (("AVM-US", BookCode.ASC606),)


def closed_scopes() -> list[dict[str, str]]:
    """What a seed with the stage records in ``demo_seed.complete``: the closed entity-books with
    their first and last period."""
    return [
        {
            "entity_code": entity_code,
            "book": book.value,
            "from_period_key": PERIOD_KEYS[0],
            "to_period_key": PERIOD_KEYS[-1],
        }
        for entity_code, book in CLOSED
    ]


def seed_close_history(ctx: BuildContext) -> None:
    """Close ``CLOSED`` over ``PERIOD_KEYS``, earliest period first (BR-CLS-08)."""
    for entity_code, book in CLOSED:
        for period_key in PERIOD_KEYS:
            closing.close_period(
                ctx, CAST, entity_code=entity_code, book=book, period_key=period_key
            )


def build(ctx: BuildContext) -> None:
    """The builder of the stage: nothing unless the seed was asked for the close; then the close,
    and after it the open-period items the background builder left for it."""
    if not ctx.with_close:
        return
    seed_close_history(ctx)
    background.open_period_items(ctx)

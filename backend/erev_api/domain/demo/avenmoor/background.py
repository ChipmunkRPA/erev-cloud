"""Avenmoor background contracts and the seeded open-period items on them (docs/02-PRD.md §2.1
WLD-R-01, WLD-R-06; §2.9 WLD-B-01, WLD-B-03, WLD-B-05, WLD-B-08; BUILD_SPEC CTR-20, XR-09).

``specs`` generates the 180 background contracts ``BG-AVM-0001`` to ``BG-AVM-0180`` with
``random.Random(20260912)``: AVM-US 100, AVM-UK 30, AVM-DE 40 and AVM-JP 10, each a single
obligation of the entity's subscription, support or licence product with inception on the first of
a month from Jan to Sep 2026, for a customer of its own that the booking creates. ``build`` books,
records Step 1 and activates each through the key-contract commands of ``contracts``, as ``maya``
with ``priya`` approving (WLD-R-02), except:

- ``BG-AVM-0020`` (TP USD 146,000.00): submitted by ``maya`` and left pending (WLD-B-01);
- ``BG-AVM-0021``: a ``journal_export`` hold "Customer dispute on invoice INV-US-3988" (WLD-B-05);
- ``BG-AVM-0023``: a ``PRINCIPAL_AGENT`` judgement record submitted by ``maya``, unreviewed
  (WLD-B-03);
- ``BG-AVM-0030``: a duplicate of ``BG-AVM-0029`` created in error, active (WLD-B-08); the
  combination suggestion the duplicate raises is dismissed first.

The first three are the open-period items of AVM-US. Each holds every period of its entity until it
is cleared — a pending request, an open hold and a submitted judgement record carry no period
(``close.gates``) — so a seed that closes months first (``--with-close``; ``demo.close_history``)
has ``build`` book the contracts and leave the three items, and makes them after its locks with
``open_period_items``. A seed without the close makes them where it always did, in the order of
the contracts.

[J] L5-4-Q-7: WLD-B-02 (manual adjustment), WLD-B-04 (invalid import), WLD-B-06 (VC element without
estimate) and WLD-B-07 (NetSuite mock entry) need capabilities outside CTR-20 and are not seeded.
Background contracts carry no billing; tests assert only their counts (WLD-R-06).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract
from erev_api.domain.contracts import holds
from erev_api.domain.demo.avenmoor import contracts as key_contracts
from erev_api.domain.demo.avenmoor.contracts import ContractSpec, LineSpec
from erev_api.domain.policies import judgements
from erev_api.enums import HoldType, JudgementTopic
from erev_api.schemas.events import HoldApplyIn
from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

SEED: Final = 20260912  # WLD-R-01
PREFIX: Final = "BG-AVM-"
COUNTS: Final = (("AVM-US", 100), ("AVM-UK", 30), ("AVM-DE", 40), ("AVM-JP", 10))  # WLD-R-06
PENDING_ACTIVATION: Final = "BG-AVM-0020"  # WLD-B-01
HELD: Final = "BG-AVM-0021"  # WLD-B-05
JUDGED: Final = "BG-AVM-0023"  # WLD-B-03
DUPLICATED: Final = "BG-AVM-0029"
DUPLICATE: Final = "BG-AVM-0030"  # WLD-B-08
PENDING_SEAT_MONTHS: Final = 1460  # TP USD 146,000.00 at 100.00 per seat-month
HOLD_REASON: Final = "Customer dispute on invoice INV-US-3988"
DUPLICATE_RATIONALE: Final = "Duplicate of BG-AVM-0029 entered in error; it will be voided."
PRINCIPAL_CONCLUSION: Final = "Avenmoor controls the platform service before it transfers."
PRINCIPAL_RATIONALE: Final = (
    "Avenmoor is primarily responsible for fulfilment, carries the service risk and sets the price."
)


@dataclass(frozen=True, slots=True)
class Family:
    """The background product of an entity."""

    currency: str
    product: str
    legal_suffix: str
    years: int
    prices: tuple[str, ...]  # stated prices of a single-unit line; empty for seat-months
    activates: bool = True


FAMILIES: Final = {
    "AVM-US": Family("USD", "AVM-SEAT-MO", "Inc.", 1, ()),
    "AVM-UK": Family("GBP", "AVM-PLAT-UK", "Ltd", 1, ("54000.00", "57000.00", "60000.00")),
    "AVM-DE": Family(
        "EUR", "AVM-SUP-12", "GmbH", 1, ("19000.00", "19500.00", "20000.00", "21000.00")
    ),
    # [J] L5-4-Q-12: AVM-JP contracts cannot activate until the bundle stops carrying the April
    # calendar's stateless periods before AVM-JP's first period; they stay drafts with Step 1.
    "AVM-JP": Family(
        "JPY", "AVM-LIB-LIC", "KK", 3, ("20000000", "30000000", "50000000"), activates=False
    ),
}
# [J] WLD-R-03: fictitious names ending with "(Demo)".
FIRST_WORDS: Final = (
    "Ashcombe",
    "Brightwater",
    "Calderwick",
    "Dunmore",
    "Elmstead",
    "Fairhollow",
    "Greyhaven",
    "Hartwell",
    "Ironbridge",
    "Larkspur",
    "Millbrook",
    "Northcote",
    "Oakhurst",
    "Pennant",
    "Ravensworth",
    "Stonebury",
    "Thornfield",
    "Wexmoor",
)
SECOND_WORDS: Final = (
    "Analytics",
    "Clinics",
    "Foods",
    "Freight",
    "Hotels",
    "Instruments",
    "Logistics",
    "Media",
    "Retail",
    "Systems",
)


def _last_day(start: date, years: int) -> date:
    return date(start.year + years, start.month, start.day) - timedelta(days=1)


def _line(rng: random.Random, family: Family, start: date) -> LineSpec:
    end = _last_day(start, family.years)
    if not family.prices:
        seat_months = rng.randint(5, 120) * 12
        return LineSpec(
            "O1", family.product, str(seat_months), f"{seat_months * 100}.00", start, end
        )
    return LineSpec("O1", family.product, "1", rng.choice(family.prices), start, end)


def specs() -> tuple[ContractSpec, ...]:
    """The 180 background contracts in number order (WLD-R-01, WLD-R-06)."""
    rng = random.Random(SEED)
    found: list[ContractSpec] = []
    number = 0
    for entity, count in COUNTS:
        family = FAMILIES[entity]
        for _ in range(count):
            number += 1
            external_id = f"{PREFIX}{number:04d}"
            name = f"{rng.choice(FIRST_WORDS)} {rng.choice(SECOND_WORDS)} {family.legal_suffix}"
            start = date(2026, rng.randint(1, 9), 1)
            line = _line(rng, family, start)
            if external_id == PENDING_ACTIVATION:
                months = str(PENDING_SEAT_MONTHS)
                line = replace(line, quantity=months, price=f"{PENDING_SEAT_MONTHS * 100}.00")
            found.append(
                ContractSpec(
                    external_id=external_id,
                    customer_code=f"BG-C-{number:04d}",
                    customer_name=f"{name} (Demo)",
                    entity=entity,
                    currency=family.currency,
                    inception=start,
                    lines=(line,),
                    activates=family.activates,
                )
            )
    by_id = {spec.external_id: spec for spec in found}
    original = by_id[DUPLICATED]
    duplicate = replace(original, external_id=DUPLICATE)
    return tuple(duplicate if spec.external_id == DUPLICATE else spec for spec in found)


def _hold(ctx: BuildContext, contract_id: UUID) -> None:
    """``POST /contracts/{id}/apply-hold`` as ``maya`` (WLD-B-05)."""
    current = key_contracts.head(ctx, contract_id)
    with ctx.command(key_contracts.PREPARER, key_contracts.CREATE) as uow:
        holds.apply_hold(
            uow,
            contract_id=contract_id,
            expected_stream_version=current,
            body=HoldApplyIn(hold_type=HoldType.JOURNAL_EXPORT, reason=HOLD_REASON),
        )


def _principal_agent(ctx: BuildContext, contract_id: UUID) -> None:
    """``POST /judgements`` and ``/submit`` as ``maya``; nobody has reviewed it yet (WLD-B-03)."""
    with ctx.command(key_contracts.PREPARER, key_contracts.JUDGEMENT_CREATE) as uow:
        record = judgements.create_judgement(
            uow,
            body=JudgementCreateIn(
                topic=JudgementTopic.PRINCIPAL_AGENT,
                subject_type="contract",
                subject_id=contract_id,
                conclusion=PRINCIPAL_CONCLUSION,
                rationale=PRINCIPAL_RATIONALE,
                questionnaire={"obligation_key": "O1", "conclusion": "PRINCIPAL"},
            ),
        )
    with ctx.command(key_contracts.PREPARER, key_contracts.JUDGEMENT_CREATE) as uow:
        judgements.submit_judgement(
            uow,
            judgement_id=record.id,
            body=JudgementSubmitIn(comment=key_contracts.SUBMIT_COMMENT),
        )


def build(ctx: BuildContext, generated: Sequence[ContractSpec] | None = None) -> None:
    """Book and activate the background contracts with the WLD-B items, each in its place; for
    a seed that closes months first, without the three open-period items (module docstring)."""
    for spec in specs() if generated is None else generated:
        contract_id = key_contracts.book(ctx, spec, None)
        if spec.external_id == DUPLICATE:
            key_contracts.dismiss_suggestions(ctx, contract_id, DUPLICATE_RATIONALE)
        key_contracts.record_step1(ctx, contract_id, spec.inception)
        if not spec.activates:
            continue
        if spec.external_id == PENDING_ACTIVATION:
            if not ctx.with_close:
                key_contracts.submit(ctx, contract_id)
            continue
        key_contracts.activate(ctx, contract_id)
        if ctx.with_close:
            continue
        if spec.external_id == HELD:
            _hold(ctx, contract_id)
        elif spec.external_id == JUDGED:
            _principal_agent(ctx, contract_id)


def open_period_items(ctx: BuildContext) -> None:
    """WLD-B-01, WLD-B-05 and WLD-B-03 on the contracts ``build`` booked without them, in the
    order of the contracts: the pending activation, the hold, the judgement record. A contract the
    seed did not book is passed over."""
    with ctx.read() as session:
        found = {
            str(external_id): UUID(str(contract_id))
            for external_id, contract_id in session.execute(
                select(contract.c.external_id, contract.c.id).where(
                    contract.c.external_id.in_((PENDING_ACTIVATION, HELD, JUDGED))
                )
            )
        }
    if PENDING_ACTIVATION in found:
        key_contracts.submit(ctx, found[PENDING_ACTIVATION])
    if HELD in found:
        _hold(ctx, found[HELD])
    if JUDGED in found:
        _principal_agent(ctx, found[JUDGED])

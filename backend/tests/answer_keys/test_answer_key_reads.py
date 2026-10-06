"""The product's to-date reader across the answer-key corpus (04 API-C-10 rev 1.132, 1.174 and
1.179; ENGINE_SPEC_B S15-R-01 and S15-R-08 rev 1.127; items CTR-ASOF-KPI-1, CTR-TODATE-AWAITING-1
and RPT-ASOF-FIGURES-1; supervisor rulings R-76, R-85, R-106 (c), R-114 (f), R-116 (c) and R-118
(a)).

The contract reads serve a version's to-date measures at the cut of ``as_of``, from the period
nodes of the version's trace (``erev_api.domain.contracts.to_date``). This module holds that
reader against the whole corpus, without a database: for every selected key, checkpoint and group
with a contract version in the checkpoint's book, the reader's figures at the checkpoint's
``as_of`` are computed on the engine's own trace — once as a reader of every member contract and
once as a reader who sees none (a member contract of another entity: the subject is found from a
bound node) — and set beside two oracles the reader does not produce:

1. the key's expected version members, where the key states them (``transaction_price``,
   ``revenue_cum``, ``billed_cum``, ``scheduled_amount``, ``awaiting_trigger_amount``,
   ``rpo_amount``), and the two parts of an obligation's remainder (``scheduled_amount``,
   ``awaiting_trigger_amount``), where the key states them for the obligation;
2. the ledger: the revenue the same computation posts through the period of ``as_of`` (posting
   intents, account role ``REVENUE``, credits less debits), when ``as_of`` is a period end of
   every entity of the group.

And two properties of every obligation at every checkpoint. The reader's (04 DB-17 at the cut):
its reported allocation is its revenue, its scheduled and its awaiting-trigger amount, and neither
part of the remainder is below zero — revenue recognised since the version date leaves the
scheduled amount first and the awaiting-trigger amount after it (ENGINE_SPEC_B S09-R-45; ruling
R-118 (a)). The reports' (S15-R-01, S15-R-08;
``erev_api.domain.reports.cuts.scheduled_after``): the schedule lines the waterfall and the RPO
state as scheduled — the ``REVENUE`` lines of the periods after the cut, for an obligation whose
remainder has a scheduled part — are that part and are never refused, so the waterfall's
recognised + scheduled + awaiting trigger is the allocation and the RPO is the remainder at every
checkpoint.

And one of the read itself (``to_date.nodes_at``): a report states a population at one or two
dates and keeps of each period series only the nodes those dates reach. At every checkpoint's
date and the day before the first period — and, at a key's last checkpoint, at every period end of
the group's entities and a week before each — the obligations and the balance rows read from the
kept nodes are those read from the whole trace, or both reads refuse with one message.

Nothing is refused, both readers agree, every balance row of the latest period reads, and the
figures tie — except the differences of ``POSTED_DIFFERS``, each pinned by key, checkpoint, amounts
and reason. A pinned difference that no longer occurs fails as a new one does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, Final
from uuid import NAMESPACE_URL, uuid5

import erev_engine
import pytest
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import cuts, tie_outs
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import encode_key
from support.answer_keys.loader import LoadedKey, active_selection
from support.answer_keys.runners import _build_checkpoint_bundles

pytestmark = pytest.mark.answer_key

ZERO: Final = Decimal(0)

MEMBERS: Final = (
    "transaction_price",
    "revenue_cum",
    "billed_cum",
    "scheduled_amount",
    "awaiting_trigger_amount",
    "rpo_amount",
)
# The two parts of an obligation's remainder (04 DB-17), which a key may state per obligation.
REMAINDER: Final = ("scheduled_amount", "awaiting_trigger_amount")
# The cutover of a business combination brings the revenue recognised before it into the version
# (``revenue_cum``) as an opening baseline and posts none of it: this ledger starts at the cutover.
OPENING_BASELINE: Final = (
    "the version's revenue holds the 120,000.00 recognised before the cutover, which the cutover "
    "emits as an opening baseline and does not post"
)
# A contract that failed Step 1 releases its non-refundable deposit to revenue (606-10-25-7): the
# ledger's REVENUE role holds the amount and no obligation does. What the header shows for such a
# contract is item CTR-KPI-25-7-1 (candidate AD-57).
DEPOSIT_RELEASE: Final = (
    "a deposit released to revenue under 606-10-25-7 is posted to the REVENUE role and is no "
    "obligation's revenue (trace: deposit_to_revenue_cum); item CTR-KPI-25-7-1"
)
ONB_121: Final = "ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION"
# (key id, checkpoint) → (the reader's revenue, the revenue posted, why they differ).
POSTED_DIFFERS: Final = {
    (ONB_121, "cutover-no-postings"): ("120000.00", "0.00", OPENING_BASELINE),
    (ONB_121, "january-2026-asc606"): ("130000.00", "10000.00", OPENING_BASELINE),
    (ONB_121, "year-end-2026-asc606"): ("240000.00", "120000.00", OPENING_BASELINE),
    ("STP1-S1-25-7A-DELIVERY-RELEASE", "december-delivery-release"): (
        "0.00",
        "1200.00",
        DEPOSIT_RELEASE,
    ),
    ("STP1-S1-25-7A-THEN-CRITERIA-MET", "december-delivery-release"): (
        "0.00",
        "1200.00",
        DEPOSIT_RELEASE,
    ),
    ("STP1-S1-25-7A-THEN-CRITERIA-MET", "january-criteria-met-netted"): (
        "0.00",
        "1200.00",
        DEPOSIT_RELEASE,
    ),
    ("STP1-S1-25-7B-TERMINATION-REFUND-RELEASE", "april-termination"): (
        "0.00",
        "1000.00",
        DEPOSIT_RELEASE,
    ),
}


def _major(value: object, unit: int) -> Decimal:
    return Decimal(int(value)).scaleb(-unit) if isinstance(value, int) else Decimal(0)


def _ratio(value: Any) -> Decimal:
    if hasattr(value, "numerator"):
        return Decimal(value.numerator) / Decimal(value.denominator)
    return Decimal(str(value or 0))


def _remainders(
    where: str,
    rows: list[dict[str, Any]],
    at: to_date.VersionAt,
    blocks: dict[str, Any],
    members: tuple[str, ...],
    lines: dict[str, list[cuts.Line]],
    as_of: date,
) -> list[str]:
    """The remainder of every obligation at the cut (item CTR-TODATE-AWAITING-1; supervisor
    ruling R-114 (f)): its reported allocation is its revenue, its scheduled and its
    awaiting-trigger amount (04 DB-17, held at the cut), neither part is below zero, and each part
    is what the key states for the obligation, where it states one."""
    findings: list[str] = []
    stated = {
        (encode_key(member), str(row["obligation_key"])): row
        for member in members
        for row in (getattr(blocks.get(member), "obligations", None) or ())
    }
    for row in rows:
        found = at.obligations[row["id"]]
        subject = f"{where}: obligation {row['subject_key']}"
        parts = {"scheduled_amount": found.scheduled, "awaiting_trigger_amount": found.awaiting}
        for name, value in parts.items():
            if value < 0:
                findings.append(f"{subject}: {name} {value} at the cut is below zero")
        allocated = row["allocated_amount"] - found.shift
        if allocated != found.revenue + found.scheduled + found.awaiting:
            findings.append(
                f"{subject}: allocated {allocated} is not revenue {found.revenue} + scheduled "
                f"{found.scheduled} + awaiting trigger {found.awaiting}"
            )
        # the reports' rule: what they state as scheduled is the scheduled part, so the waterfall
        # total is the allocation and the RPO is the remainder (S15-R-01, S15-R-08)
        try:
            later = cuts.scheduled_after(
                lines.get(row["subject_key"], []),
                found,
                as_of,
                contract=row["subject_key"].split("/")[0],
                obligation=str(row["obligation_key"]),
            )
        except cuts.ScheduleUnreadable as refused:
            findings.append(f"{subject}: {refused.errors[0].message}")
        else:
            scheduled = sum((amount for _, _, amount in later), Decimal(0))
            if found.revenue + scheduled + found.awaiting != allocated:
                findings.append(
                    f"{subject}: the waterfall states {found.revenue} + {scheduled} + "
                    f"{found.awaiting} for an allocation of {allocated}"
                )
            if scheduled + found.awaiting != allocated - found.revenue:
                findings.append(
                    f"{subject}: the RPO states {scheduled + found.awaiting} for a remainder of "
                    f"{allocated - found.revenue}"
                )
        expected = stated.get((row["subject_key"].split("/")[0], str(row["obligation_key"])), {})
        for name in REMAINDER:
            if expected.get(name) is not None and Decimal(str(expected[name])) != parts[name]:
                findings.append(
                    f"{subject}: {name} expected {expected[name]}, the reader shows {parts[name]} "
                    f"(the version holds {row[name]})"
                )
    return findings


def _answer(read: Callable[[], Any]) -> tuple[str, Any]:
    """What a read answers: its result, or the message it refuses with."""
    try:
        return "read", read()
    except (to_date.Unreadable, tie_outs.BalanceUnreadable) as refused:
        return "refused", refused.errors[0].message


def _obligations_at(
    version: dict[str, Any],
    rows: list[dict[str, Any]],
    readers: dict[Any, str],
    day: date,
    nodes: to_date.Nodes,
) -> Any:
    found = to_date.version_at(version, rows, nodes=nodes, external_ids=readers, as_of=day)
    return found.obligations


def _balance_row_at(
    version: dict[str, Any], key: str, stored: dict[str, Any], day: date, nodes: to_date.Nodes
) -> Any:
    balance = to_date.balance_at(
        stored, version=version, nodes=nodes, external_id=key, moved=ZERO, as_of=day
    )
    measured = to_date.measured_at(
        version, nodes=nodes, external_id=key, entity_code=str(stored["entity_code"]), as_of=day
    )
    return balance, measured


def _kept_nodes(
    where: str,
    trace_nodes: Sequence[Any],
    whole: to_date.Nodes,
    days: Sequence[date],
    version: dict[str, Any],
    rows: list[dict[str, Any]],
    visible: dict[Any, str],
    balance_rows: Sequence[tuple[str, dict[str, Any]]],
) -> list[str]:
    """The reports' read (``to_date.nodes_at``; module docstring): at each of ``days`` the
    obligations and the balance rows read from the nodes kept for that date equal those read
    from the whole trace, or both refuse alike."""
    findings: list[str] = []
    for day in days:
        kept = to_date.nodes_of(to_date.nodes_at(trace_nodes, [day]), whole.starts)
        reads: list[tuple[str, Callable[[to_date.Nodes], Any]]] = [
            ("the reader of every member", partial(_obligations_at, version, rows, visible, day)),
            ("the reader of no member", partial(_obligations_at, version, rows, {}, day)),
        ]
        reads += [
            (
                f"the balance row {key}@{stored['entity_code']}",
                partial(_balance_row_at, version, key, stored, day),
            )
            for key, stored in balance_rows
        ]
        for name, read in reads:
            full = _answer(partial(read, whole))
            lean = _answer(partial(read, kept))
            if full != lean:
                findings.append(
                    f"{where}: at {day} {name} answers differently from the kept nodes: "
                    f"{lean} for {full}"
                )
    return findings


def _read(loaded: LoadedKey) -> tuple[list[str], dict[tuple[str, str], tuple[str, str]]]:
    """Every finding of the key but a difference from the posted revenue, and those differences by
    (key id, checkpoint)."""
    findings: list[str] = []
    posted_differs: dict[tuple[str, str], tuple[str, str]] = {}
    expected = {item.name: item for item in loaded.key.checkpoints}
    checkpoints = _build_checkpoint_bundles(loaded)
    for checkpoint in checkpoints:
        blocks = {item.contract: item for item in (expected[checkpoint.name].contracts or ())}
        for bundle in checkpoint.bundles:
            try:
                output = erev_engine.compute(bundle)
            except EngineError:
                continue  # a checkpoint whose expectation is the engine's refusal
            book = next((b for b in output.books if b.book_code == checkpoint.book), None)
            if book is None or book.contract_version is None:
                continue
            where = f"{checkpoint.name} as_of {checkpoint.as_of}"
            currency = bundle.group.transaction_currency
            unit = ISO_4217[currency].minor_unit
            starts: dict[tuple[str, date], set[date]] = {}
            period_end_everywhere = True
            cut_keys: dict[str, str] = {}
            for entity in bundle.entities:
                for period in entity.periods:
                    starts.setdefault((period.period_key, period.end_date), set()).add(
                        period.start_date
                    )
                    if period.start_date <= checkpoint.as_of <= period.end_date:
                        cut_keys[entity.code] = period.period_key
                        if period.end_date != checkpoint.as_of:
                            period_end_everywhere = False
            nodes = to_date.nodes_of(
                book.trace.nodes, {pair: tuple(sorted(found)) for pair, found in starts.items()}
            )
            columns = book.contract_version.columns
            version: dict[str, Any] = {name: _major(columns.get(name), unit) for name in MEMBERS}
            version |= {"version_no": 1, "id": uuid5(NAMESPACE_URL, "v")}
            rows = [
                {
                    "id": uuid5(NAMESPACE_URL, item.subject_key),
                    "contract_id": uuid5(NAMESPACE_URL, item.subject_key.split("/")[0]),
                    "obligation_key": item.columns.get("obligation_key"),
                    "txn_currency": currency,
                    "effective_date": item.columns.get("effective_date"),
                    "revenue_cum": _major(item.columns.get("revenue_cum"), unit),
                    "billed_cum": _major(item.columns.get("billed_cum"), unit),
                    "progress_ratio": _ratio(item.columns.get("progress_ratio")),
                    "satisfaction_status": item.columns.get("satisfaction_status"),
                    "recognition_method": item.columns.get("recognition_method"),
                    "hold_types": tuple(item.columns.get("hold_types") or ()),
                    "allocated_amount": _major(item.columns.get("allocated_amount"), unit),
                    "scheduled_amount": _major(item.columns.get("scheduled_amount"), unit),
                    "awaiting_trigger_amount": _major(
                        item.columns.get("awaiting_trigger_amount"), unit
                    ),
                    "trace_nodes": dict(item.trace_nodes),
                    "subject_key": item.subject_key,
                }
                for item in book.obligation_versions
            ]
            members = bundle.group.member_contract_keys
            visible = {uuid5(NAMESPACE_URL, encode_key(key)): key for key in members}
            try:
                seen = to_date.version_at(
                    version, rows, nodes=nodes, external_ids=visible, as_of=checkpoint.as_of
                )
                at = to_date.version_at(
                    version, rows, nodes=nodes, external_ids={}, as_of=checkpoint.as_of
                )
            except to_date.Unreadable as refused:
                error = refused.errors[0]
                findings.append(f"{where}: refused {error.field}: {error.message}")
                continue
            if seen != at:
                findings.append(
                    f"{where}: the reader of every member and the reader of none differ"
                )
            # the balance rows of the latest period, as the header reads them
            latest: dict[str, Any] = {}
            for item in book.balances:
                held = latest.get(item.subject_key)
                if held is None or item.period_key > held.period_key:
                    latest[item.subject_key] = item
            balance_rows: list[tuple[str, dict[str, Any]]] = []
            for key in members:
                for subject, item in latest.items():
                    contract_part, _, entity_part = subject.partition("@")
                    if contract_part != encode_key(key):
                        continue
                    stored = {
                        "contract_id": uuid5(NAMESPACE_URL, contract_part),
                        "entity_id": entity_part,
                        "entity_code": entity_part,
                        "txn_currency": currency,
                        "net_position_txn": _major(item.columns.get("net_position_txn"), unit),
                        **{
                            f"{name}_txn": _major(item.columns.get(f"{name}_txn"), unit)
                            for name in tie_outs.BALANCE_MEASURES
                        },
                    }
                    balance_rows.append((key, stored))
                    try:
                        to_date.measured_at(
                            version,
                            nodes=nodes,
                            external_id=key,
                            entity_code=entity_part,
                            as_of=checkpoint.as_of,
                        )
                        to_date.balance_at(
                            stored,
                            version=version,
                            nodes=nodes,
                            external_id=key,
                            moved=Decimal(0),
                            as_of=checkpoint.as_of,
                        )
                    except (to_date.Unreadable, tie_outs.BalanceUnreadable) as refused:
                        error = refused.errors[0]
                        findings.append(f"{where}: balance row {subject} refused: {error.message}")
            ends_of = sorted(
                {period.end_date for entity in bundle.entities for period in entity.periods}
            )
            first_start = min(
                (period.start_date for entity in bundle.entities for period in entity.periods),
                default=checkpoint.as_of,
            )
            days = {checkpoint.as_of, first_start - timedelta(days=1)}
            if checkpoint is checkpoints[-1]:
                days |= {*ends_of, *(day - timedelta(days=7) for day in ends_of)}
            findings += _kept_nodes(
                where, book.trace.nodes, nodes, sorted(days), version, rows, visible, balance_rows
            )
            shown = {
                "transaction_price": version["transaction_price"] - at.returns_moved,
                "revenue_cum": version["revenue_cum"] + at.revenue_moved - at.release_moved,
                "billed_cum": version["billed_cum"] + at.billed_moved,
                "scheduled_amount": version["scheduled_amount"] - at.scheduled_moved,
                "awaiting_trigger_amount": version["awaiting_trigger_amount"] - at.awaiting_moved,
                "rpo_amount": version["rpo_amount"] - at.rpo_moved,
            }
            ends = {
                (entity.code, item.period_key): item.end_date
                for entity in bundle.entities
                for item in entity.periods
            }
            lines: dict[str, list[cuts.Line]] = {}
            for line in book.schedules:
                kind = str(getattr(line.schedule_kind, "value", line.schedule_kind))
                if kind == "REVENUE" and line.subject_type == "obligation":
                    lines.setdefault(line.subject_key, []).append(
                        (
                            uuid5(NAMESPACE_URL, f"{line.subject_key}:{line.period_key}:{kind}"),
                            ends[line.entity, line.period_key],
                            _major(line.amount, unit),
                        )
                    )
            findings += _remainders(where, rows, at, blocks, members, lines, checkpoint.as_of)
            # (1) the key's expected version members
            for member in members:
                found = blocks.get(member)
                if found is None or found.version is None or len(members) != 1:
                    continue
                for name in MEMBERS:
                    stated = getattr(found.version, name, None)
                    if stated is not None and Decimal(str(stated)) != shown[name]:
                        findings.append(
                            f"{where}: {name} expected {stated}, the reader shows {shown[name]} "
                            f"(the version holds {version[name]})"
                        )
            # (2) the revenue posted through the period of as_of
            if not period_end_everywhere or not cut_keys:
                continue
            posted = 0
            for intent in book.posting_intents:
                cut = cut_keys.get(intent.entity)
                if cut is None or intent.posting_period_key > cut:
                    continue
                for line in intent.lines:
                    if line.account_role == "REVENUE":
                        posted += line.amount_txn if line.side == "C" else -line.amount_txn
            if _major(posted, unit) != shown["revenue_cum"]:
                posted_differs[(loaded.key.id, checkpoint.name)] = (
                    str(shown["revenue_cum"]),
                    str(_major(posted, unit)),
                )
    return findings, posted_differs


@pytest.mark.parametrize("loaded", active_selection(), ids=lambda k: k.key.id)
def test_the_to_date_reader_ties_to_the_key_and_to_the_ledger(loaded: LoadedKey) -> None:
    findings, posted_differs = _read(loaded)
    assert findings == [], "\n".join(findings)
    pinned = {
        pair: (shown, posted)
        for pair, (shown, posted, _) in POSTED_DIFFERS.items()
        if pair[0] == loaded.key.id
    }
    assert posted_differs == pinned, (
        "the revenue the reader shows and the revenue posted through the period of as_of: "
        f"found {posted_differs}, pinned {pinned}"
    )


def test_every_pinned_difference_names_a_key_of_the_corpus() -> None:
    """A pin is by name and reason: its key exists (in an unfiltered run) and its reason is one
    of the two the supervisor ruled on (R-106 (c))."""
    selected = {item.key.id for item in active_selection()}
    assert {reason for _, _, reason in POSTED_DIFFERS.values()} == {
        OPENING_BASELINE,
        DEPOSIT_RELEASE,
    }
    pinned = {key for key, _ in POSTED_DIFFERS}
    assert len(POSTED_DIFFERS) == 7 and len(pinned) == 4
    if pinned & selected:  # a filtered run may select none of them
        missing = sorted(key for key in pinned if key not in selected)
        assert missing == [] or len(selected) < 50, missing

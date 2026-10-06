"""Provenance nodes of the CURRENT original allocation (ENGINE_SPEC CV-50 links of
``original_allocated_exact`` / ``original_allocated_amount``, CV-47 (b); D-98 candidates 117 and
121; lane ENG-T1F).

The two columns publish ``ObligationState.original_allocation`` (the S05-R-10 total: the relative
share of the remainder plus the targeted shares; after an S06-R-26 repin the repin's share; for an
obligation a boundary creates the quota installed at creation). CV-50 requires a summed column to
link the sum node the producing stage emits and a re-measured column its ``<column>@<event>`` node,
never the partial or stale version-state node. ``emit_original_allocation`` emits that pair —
``original_allocated_exact@<event key>:<ob>:-`` (``alloc.original_total.v1``, exact inputs, its
``exact`` param bound to the producers' exact values within the CV-51 limit) and
``original_allocated_amount@<event key>:<ob>:-`` (``alloc.original_total_amount.v1``, Σ of the
posted components counted once, the exact total in the residue) — over the producing node(s):
stage 05 at inception under the booking event when targeted shares exist, stage 06 at a repin and
at each creating boundary over the creation producer. The assembler links the latest such node
that holds the stored value (``_snapshot_links``). Standard library only.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from fractions import Fraction
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.formulas import binds_encoded, rational_param
from erev_engine.money import round_half_up, to_fraction
from erev_engine.stages.state import BookContext, EventView, ObligationState, Quota, Quota1
from erev_engine.trace import ABSENT_PREFIX, ABSENT_ZERO_TOTAL, TraceBuilder

TOTAL_EXACT_FORMULA: Final = "alloc.original_total.v1"
TOTAL_AMOUNT_FORMULA: Final = "alloc.original_total_amount.v1"
ECHO_FORMULA: Final = "input.echo.v1"
RELATIVE_FORMULA: Final = "alloc.relative_ssp.v1"
WEIGHT_FORMULA: Final = "alloc.original_weight.v1"
UNIT_SSP_FORMULA: Final = "alloc.unit_ssp.v1"
# CV-50 rev 1.29: a contract-permitted absence of a snapshot producer is stamped in place of a node
# id as one of the stable identifiers declared once in ``erev_engine.trace`` (``ABSENT_ZERO_TOTAL``,
# ``ABSENT_NO_RESOLUTION``; ``ABSENCE_COLUMNS`` = the reason admitted per column), asserted by the
# assembler by identity — distinct from a missing REQUIRED producer (which refuses).


def booking_event_key(events: Iterable[EventView], contract_key: str) -> str | None:
    """The ``CONTRACT_BOOKED`` event key of ``contract_key`` (the inception "boundary")."""
    return next(
        (
            event.event_key
            for event in events
            if event.contract_key == contract_key and event.event_type == "CONTRACT_BOOKED"
        ),
        None,
    )


def emit_original_allocation(
    ctx: BookContext,
    tb: TraceBuilder,
    event_key: str,
    subject: str,
    quota: Quota,
    *,
    exact_inputs: Sequence[str],
    amount_inputs: Sequence[str],
    rule: str,
) -> tuple[str, str]:
    """The ``<column>@<event key>:<ob>:-`` pair of the current original allocation (see module).

    Invariants before emission (never a silent substitution): the exact quota lies within the
    CV-51 limit of the sum of the cited inputs' exact values (half a unit at 18 places per
    independently encoded component — the whole contract, no equality claim beyond it), and the
    posted quota equals the sum of the cited POSTED contributions exactly (the column's actual
    computation, Codex 0312: S05-R-10 sums posted shares separately; a repin or creation preserves
    the apportioned posted share; nothing re-rounds the raw total).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    cited = [tb.exact(node_id) for node_id in exact_inputs]
    held = [item for item in cited if item is not None]
    if len(held) != len(cited) or not binds_encoded(quota.x_exact, held):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the current original allocation is not the exact value of its cited producing "
            "node(s) within the CV-51 encoding limit",
            subject_key=subject,
            detail={
                "rule": rule,
                "node_id": ",".join(exact_inputs),
                "operand": rational_param(quota.x_exact),
                "cited": rational_param(sum(held, Fraction(0))),
            },
        )
    posted = [tb.value(node_id) for node_id in amount_inputs]
    summed = sum((to_fraction(item) for item in posted if item is not None), Fraction(0))
    if any(item is None for item in posted) or summed * 10**minor_unit != quota.a_posted:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the posted current original allocation is not the sum of its cited posted components",
            subject_key=subject,
            detail={
                "rule": rule,
                "node_id": ",".join(amount_inputs),
                "operand": str(quota.a_posted),
                "cited": rational_param(summed * 10**minor_unit),
            },
        )
    exact_id = tb.node(
        measure=f"original_allocated_exact@{event_key}",
        subject_key=subject,
        period_key=None,
        value=quota.x_exact,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=TOTAL_EXACT_FORMULA,
        inputs=list(exact_inputs),
        params={"exact": rational_param(quota.x_exact), "role": "exact", "rule": rule},
        narrative_key=TOTAL_EXACT_FORMULA.rsplit(".v", 1)[0],
    )
    amount_id = tb.node(
        measure=f"original_allocated_amount@{event_key}",
        subject_key=subject,
        period_key=None,
        value=quota.a_posted,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=TOTAL_AMOUNT_FORMULA,
        inputs=list(amount_inputs),
        params={"role": "amount", "rule": rule},
        exact=quota.x_exact,
        narrative_key=TOTAL_AMOUNT_FORMULA.rsplit(".v", 1)[0],
    )
    return exact_id, amount_id


def emit_snapshot_columns(
    ctx: BookContext,
    tb: TraceBuilder,
    event_key: str,
    subject: str,
    *,
    selected_node: str | None,
    selected: Fraction | None,
    quantity: Fraction,
    stated_price: Fraction | None,
    price: Quota1 | None,
    rule: str,
    total_inputs: Sequence[str] = (),
    total_value: Fraction | None = None,
    weight_input: str | None = None,
    weight_value: Fraction | None = None,
    total_node: str | None = None,
    allocation_weight_node: str | None = None,
) -> dict[str, str]:
    """The ``<column>@<event key>:<ob>:-`` producers of the six snapshot columns for an obligation
    a boundary re-measures or creates (ENGINE_SPEC CV-50 rev 1.29; D-98 candidates 123 and 124),
    returned as column → node id for the state's ``snapshot_producer_links``:

    - ``original_ssp_selected``: ``selected_node`` (stage 05's own ``original_ssp_selected@<event
      key>`` node emitted by ``resolve_ssp`` / ``points.emit``), when present in the trace;
    - ``original_unit_ssp``: ``alloc.unit_ssp.v1`` over that node and ``original_quantity`` (no
      node when Q = 0 — the column is NULL);
    - ``original_stated_price``: the reserved id ``original_stated_price@<event key>:<ob>:-`` — an
      ``input.echo.v1`` over the boundary state's ``stated_price@<event key>:<ob>:-`` node, which
      ``emit_stated_price_echoes`` emits once the boundary state exists (the stage 03 draft's own
      ``stated_price`` node is NOT re-emitted: the boundary state derives its node from it);
    - ``original_total_contract_price``: the reserved id ``original_total_contract_price@<event
      key>:<ob>:-`` — an ``input.echo.v1`` over the boundary's ``transaction_price@<event key>``
      build-up, which stage 13 traces after the handler; ``emit_price_echoes`` emits it then;
    - ``original_total_contract_ssp``: ``total_node`` when the constructor produced it (the legacy
      template's ``role total_ssp``), else ``alloc.original_total.v1`` (exact inputs) over
      ``total_inputs`` (the boundary's ``mod_weight@`` weight nodes) with the raw ``total_value``
      as its bound ``exact`` param (within the CV-51 limit of the cited values);
    - ``allocation_weight``: ``allocation_weight_node`` when the constructor produced it, else
      ``alloc.original_weight.v1`` over ``weight_input`` and the total node with the raw operands
      as bound params — the governed ratio w ÷ Σw, so it replays exactly; never the assembler's
      0 default. When Σw = 0 (DEV-054) there is NO ratio: the contract-permitted absence
      ``trace.ABSENT_ZERO_TOTAL`` (``absent:zero-total``) is stamped in place of a node id (no
      0 ÷ 0 is manufactured), as a constructor may pass it in ``allocation_weight_node``; a
      LEGACY-VC created line (no SSP resolution by construction) stamps
      ``trace.ABSENT_NO_RESOLUTION`` (``absent:no-ssp-resolution``) for ``original_ssp_selected``
      (no node fabricated). The identifiers are the closed enumeration of ``erev_engine.trace``;
      the assembler admits each by identity for its column only, over the column's existing 0
      display, publishes it as the column's link, and refuses a genuinely missing REQUIRED
      producer (CV-50 rev 1.29).
    Other absent producers emit nothing (the column stays NULL or unlinked; never fabricated)."""
    links: dict[str, str] = {}
    quantity_node = f"original_quantity:{subject}:-"
    if selected_node is not None and selected_node.startswith(ABSENT_PREFIX):
        links["original_ssp_selected"] = selected_node  # the named absence, not a node
    elif selected_node is not None and tb.value(selected_node) is not None:
        links["original_ssp_selected"] = selected_node
        if selected is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a selected-SSP producer is cited without its raw selected SSP",
                subject_key=subject,
                detail={"rule": rule, "node_id": selected_node},
            )
        cited = tb.exact(selected_node)
        if cited is None or not binds_encoded(selected, [cited]):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the raw selected SSP is not the value of its cited producer within the CV-51 "
                "encoding limit",
                subject_key=subject,
                detail={
                    "rule": rule,
                    "node_id": selected_node,
                    "operand": rational_param(selected),
                    "cited": rational_param(cited if cited is not None else Fraction(0)),
                },
            )
        if quantity != 0 and tb.value(quantity_node) is not None:
            # The RAW quotient the column publishes; the raw operands travel as params bound to
            # the cited producers (one emission / replay contract; Codex 0954 §1a). BOTH operands
            # are bound at emission under the CV-51 rule the replay applies (Codex 1025 §1: the
            # quantity was taken on the node's mere existence).
            cited_quantity = tb.exact(quantity_node)
            if cited_quantity is None or not binds_encoded(quantity, [cited_quantity]):
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "the raw quantity is not the value of its cited original_quantity node within "
                    "the CV-51 encoding limit",
                    subject_key=subject,
                    detail={
                        "rule": rule,
                        "node_id": quantity_node,
                        "operand": rational_param(quantity),
                        "cited": rational_param(
                            cited_quantity if cited_quantity is not None else Fraction(0)
                        ),
                    },
                )
            links["original_unit_ssp"] = tb.node(
                measure=f"original_unit_ssp@{event_key}",
                subject_key=subject,
                period_key=None,
                value=selected / quantity,
                currency=ctx.txn_currency,
                minor_unit=None,
                formula_id=UNIT_SSP_FORMULA,
                inputs=[selected_node, quantity_node],
                params={
                    "ssp": rational_param(selected),
                    "quantity": rational_param(quantity),
                    "rule": rule,
                },
                narrative_key=UNIT_SSP_FORMULA.rsplit(".v", 1)[0],
            )
    if stated_price is not None:
        # The created line's stated price is produced by the boundary state's
        # ``stated_price@<event key>:<ob>:-`` node, emitted after the obligations are built
        # (``boundary_state.emit``); the echo over it is emitted then (``emit_stated_price_echoes``)
        # under this reserved id, which the assembler links by identity.
        links["original_stated_price"] = f"original_stated_price@{event_key}:{subject}:-"
    if price is not None:
        # The boundary's ``transaction_price@<event key>:<group>:-`` build-up is traced by stage 13
        # after the handler returns (``_trace_boundary_price``); the echo over it is emitted then
        # (``emit_price_echoes``) under this reserved id, which the assembler links by identity.
        links["original_total_contract_price"] = (
            f"original_total_contract_price@{event_key}:{subject}:-"
        )
    total_id = total_node
    if total_id is None and total_inputs and total_value is not None:
        cited_totals = [tb.exact(node_id) for node_id in total_inputs]
        held = [item for item in cited_totals if item is not None]
        if len(held) != len(cited_totals) or not binds_encoded(total_value, held):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the boundary's total SSP is not the sum of its cited weight nodes within the "
                "CV-51 encoding limit",
                subject_key=subject,
                detail={
                    "rule": rule,
                    "node_id": ",".join(total_inputs),
                    "operand": rational_param(total_value),
                    "cited": rational_param(sum(held, Fraction(0))),
                },
            )
        # The RAW total as the bound param (``alloc.original_total.v1``, exact inputs): the stored
        # value and the replay are the same raw rational (Codex 0954 §1b).
        total_id = tb.node(
            measure=f"original_total_contract_ssp@{event_key}",
            subject_key=subject,
            period_key=None,
            value=total_value,
            currency=ctx.txn_currency,
            minor_unit=None,
            formula_id=TOTAL_EXACT_FORMULA,
            inputs=list(total_inputs),
            params={"exact": rational_param(total_value), "role": "total", "rule": rule},
            narrative_key=TOTAL_EXACT_FORMULA.rsplit(".v", 1)[0],
        )
    if total_id is not None:
        links["original_total_contract_ssp"] = total_id
    weight_id = allocation_weight_node
    if weight_id is None and weight_input is not None and total_value == 0:
        # DEV-054 (Σw = 0): the governed ratio is undefined — no 0 ÷ 0 is manufactured; the
        # absence is stamped by name so the assembler distinguishes it from a missing producer.
        weight_id = ABSENT_ZERO_TOTAL
    if (
        weight_id is None
        and weight_input is not None
        and total_id is not None
        and weight_value is not None
        and total_value not in (None, 0)
    ):
        assert total_value is not None
        own_cited, total_cited = tb.exact(weight_input), tb.exact(total_id)
        if (
            own_cited is None
            or total_cited is None
            or not binds_encoded(weight_value, [own_cited])
            or not binds_encoded(total_value, [total_cited])
        ):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the raw weight operands are not the values of their cited producers within the "
                "CV-51 encoding limit",
                subject_key=subject,
                detail={
                    "rule": rule,
                    "node_id": f"{weight_input},{total_id}",
                    "operand": f"{rational_param(weight_value)}/{rational_param(total_value)}",
                },
            )
        # The RAW governed ratio w ÷ Σw; the raw operands travel as params bound to the cited
        # weight and total nodes (``alloc.original_weight.v1``; Codex 0954 §1b).
        weight_id = tb.node(
            measure=f"allocation_weight@{event_key}",
            subject_key=subject,
            period_key=None,
            value=weight_value / total_value,
            currency=None,
            minor_unit=None,
            formula_id=WEIGHT_FORMULA,
            inputs=[weight_input, total_id],
            params={
                "weight": rational_param(weight_value),
                "total": rational_param(total_value),
                "rule": rule,
            },
            narrative_key=WEIGHT_FORMULA.rsplit(".v", 1)[0],
        )
    if weight_id is not None:
        links["allocation_weight"] = weight_id
    return links


def emit_stated_price_echoes(
    ctx: BookContext, tb: TraceBuilder, ev: EventView, created: Iterable[ObligationState]
) -> None:
    """After ``boundary_state.emit``: for every obligation the boundary created, the reserved
    ``original_stated_price@<event key>:<ob>:-`` echo over the boundary's
    ``stated_price@<event key>:<ob>:-`` node (CV-50 rev 1.29; D-98 candidate 124). Fails closed when
    the boundary node is absent: a reserved link is never left dangling."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    for ob in created:
        subject = ob.subject_key
        links = ob.snapshot_producer_links
        reserved = links.get("original_stated_price")
        if reserved is None:
            continue
        source = f"stated_price@{ev.event_key}:{subject}:-"
        if tb.value(source) is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the boundary state emitted no stated_price node for an obligation it created",
                subject_key=subject,
                detail={"rule": "CV-50", "node_id": source},
            )
        stated: Fraction = ob.original_stated_price
        node_id = tb.node(
            measure=f"original_stated_price@{ev.event_key}",
            subject_key=subject,
            period_key=None,
            value=round_half_up(stated, minor_unit),
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=ECHO_FORMULA,
            inputs=[source],
            params={"member": "stated_price", "rule": "S06-R-14"},
            exact=stated,
            narrative_key=ECHO_FORMULA.rsplit(".v", 1)[0],
        )
        if node_id != reserved:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the stated-price echo id differs from the reserved link",
                subject_key=subject,
                detail={"rule": "CV-50", "node_id": node_id, "reserved": reserved},
            )


def emit_price_echoes(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    obligations: Iterable[ObligationState],
    *,
    total: Quota1,
    price_node: str,
) -> None:
    """After stage 13 traced the boundary price (``_trace_boundary_price``): for every obligation
    the boundary created, the reserved ``original_total_contract_price@<event key>:<ob>:-`` echo
    over the boundary's ``transaction_price@<event key>:<group>:-`` build-up (CV-50 rev 1.29; D-98
    candidate 124). A reserved link whose build-up stage 13 did not trace is REFUSED (the price
    basis the column consumed has no producer) — never left unresolved, never another node."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    for ob in obligations:
        subject = ob.subject_key
        reserved = ob.snapshot_producer_links.get("original_total_contract_price")
        expected = f"original_total_contract_price@{ev.event_key}:{subject}:-"
        if reserved != expected or tb.value(expected) is not None:
            continue
        if tb.value(price_node) is None:
            # The price basis this obligation's column consumed was not traced: a required
            # producer is missing — refuse; never leave the reserved link unresolved (Codex 0954).
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "stage 13 traced no transaction_price build-up for the event that created an "
                "obligation whose original_total_contract_price link it must produce",
                subject_key=subject,
                detail={"rule": "CV-50", "node_id": price_node, "reserved": reserved},
            )
        node_id = tb.node(
            measure=f"original_total_contract_price@{ev.event_key}",
            subject_key=subject,
            period_key=None,
            value=total.posted,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=ECHO_FORMULA,
            inputs=[price_node],
            params={"member": "transaction_price", "rule": "CV-50"},
            exact=total.exact,
            narrative_key=ECHO_FORMULA.rsplit(".v", 1)[0],
        )
        assert node_id == expected

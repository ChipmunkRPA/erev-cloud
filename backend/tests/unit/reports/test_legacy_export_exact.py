"""D-98 candidate 89 (04 §17.1 rules 4 and 4a rev 1.75; SCREENS_B §5.6.2 RPT-10 rev 1.24;
dev-guide DG-PAR-05 and DG-KRN-EXP-08; Codex production-20260921-1155 §1 and -2215 §3 / §4; lane
F-LMG record §27, §27.9): the legacy exports write the EXACT trace-sourced value of the six
posted-cents columns (rule 4) and the exact revenue ACTIVITY of ``Current Rev Rec`` (LM-CL-55)
through the posted node's OWN companion (rule 4a) — never ``value + rounding_residue`` of the
posted node, the literal ``unavailable`` where the producer names an adjusted endpoint, a named
run-level refusal for a legacy trace and for a missing / redirected / posted / invalid companion.
Fakes only — trace objects built with the engine's own ``Trace`` / ``TraceNode`` types and
formulas that REPLAY under ``erev_engine.trace.reevaluate`` (rule 4a step (4) replays the whole
trace: ``input.echo.v1`` over a value-bearing ``SourceRef`` for the stored-column nodes, the
production exact-activity chain ``rec.exact_endpoint.v1`` / ``rec.exact_difference.v1`` /
``rec.exact_activity.v1`` for the companion), rows as ``obligation_version`` dicts, a recording
loader in place of ``explain.store.load_trace``; no database. The shipped-world measurement is
``tests/engine/s13_books/test_s13_legacy_export_exact_columns.py``.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports import exact_sources, legacy_columns
from erev_api.explain import store
from erev_api.explain.store import TraceIntegrityError
from erev_api.problems import Problem
from erev_engine.formulas import rational_param
from erev_engine.money import format_exact
from erev_engine.trace import SourceRef, Trace, TraceNode

V1 = UUID(int=0x51)
V2 = UUID(int=0x52)
SUBJECT = "Contract 1/POB %231"
OTHER = "Contract 1/POB %232"
ENTITY = "Contract 1@AVM-US"
AS_OF = "2023-01-31"
# the golden world's Contract 1 POB #1 rank-3 activity: posted 128.84, exact 128.84043607532210109
ACTIVITY_EXACT = Fraction(Decimal("128.84043607532210109"))
ACTIVITY_POSTED = "128.84"
ACTIVITY_TEXT = "128.84043607532210109"


def _source(value: str) -> SourceRef:
    return SourceRef("source_record", "fake", {"value": value})


def _node(
    measure: str, value: str, residue: str | None, subject: str = SUBJECT, currency: str = "USD"
) -> TraceNode:
    """A stored-column node that replays to its own value (``input.echo.v1`` over a source)."""
    return TraceNode(
        id=f"{measure}:{subject}:-",
        measure=measure,
        value=value,
        currency=currency,
        formula_id="input.echo.v1",
        inputs=(_source(value),),
        params={"minor_unit": "2"},
        rounding_residue=residue,
        narrative_key="input.echo",
    )


def _exact_node(
    measure: str,
    subject: str,
    value: Fraction,
    formula_id: str,
    inputs: tuple[str | SourceRef, ...],
    params: dict[str, str],
    *,
    currency: str = "USD",
    stored: str | None = None,
) -> TraceNode:
    return TraceNode(
        id=f"{measure}:{subject}:-",
        measure=measure,
        value=format_exact(value) if stored is None else stored,
        currency=currency,
        formula_id=formula_id,
        inputs=inputs,
        params=params,
        rounding_residue=None,
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )


def _activity_chain(
    subject: str = SUBJECT,
    exact: Fraction = ACTIVITY_EXACT,
    posted: str = ACTIVITY_POSTED,
    *,
    events: int = 1,
    currency: str = "USD",
    companion_value: str | None = None,
    companion_id: str | None = None,
    companion_residue: str | None = None,
) -> tuple[TraceNode, ...]:
    """The producer's shape (CV-64 rev 1.30): guarded ``before`` endpoint, ``after`` endpoint over a
    money source, one delta, the companion Σ, and the posted ``revenue_amount`` node naming it."""
    event = "E1"
    before = _exact_node(
        f"revenue_exact_before@{event}",
        subject,
        Fraction(0),
        "rec.exact_endpoint.v1",
        (),
        {"as_of": AS_OF, "event": event, "side": "before", "guard": "S02-R-03"},
        currency=currency,
    )
    after = _exact_node(
        f"revenue_exact_after@{event}",
        subject,
        exact,
        "rec.exact_endpoint.v1",
        (_source(format_exact(exact)),),
        {"as_of": AS_OF, "event": event, "side": "after", "exact": rational_param(exact)},
        currency=currency,
    )
    delta = _exact_node(
        f"revenue_exact_delta@{event}",
        subject,
        exact,
        "rec.exact_difference.v1",
        (after.id, before.id),
        {"event": event, "after": rational_param(exact), "before": "0"},
        currency=currency,
    )
    chain: tuple[TraceNode, ...] = (before, after, delta) if events else ()
    companion = TraceNode(
        id=f"revenue_amount_exact:{subject}:-",
        measure="revenue_amount_exact",
        value=format_exact(exact) if companion_value is None else companion_value,
        currency=currency,
        formula_id="rec.exact_activity.v1",
        inputs=(delta.id,) if events else (),
        params={"as_of": AS_OF, "exact": rational_param(exact), "events": str(events)},
        rounding_residue=companion_residue,
        narrative_key="rec.exact_activity",
    )
    posted_node = TraceNode(
        id=f"revenue_amount:{subject}:-",
        measure="revenue_amount",
        value=posted,
        currency=currency,
        formula_id="input.echo.v1",
        inputs=(_source(posted),),
        params={
            "minor_unit": "2",
            "exact_node": companion.id if companion_id is None else companion_id,
        },
        rounding_residue=format_exact(exact - Fraction(Decimal(posted))),
        narrative_key="input.echo",
    )
    return (*chain, companion, posted_node)


def _posted_activity(params: dict[str, str], posted: str = ACTIVITY_POSTED) -> TraceNode:
    """A posted ``revenue_amount`` node without a companion: ``exact_basis`` (UNAVAILABLE) or
    neither param (LEGACY); the residue is the producer's ``0``."""
    return TraceNode(
        id=f"revenue_amount:{SUBJECT}:-",
        measure="revenue_amount",
        value=posted,
        currency="USD",
        formula_id="input.echo.v1",
        inputs=(_source(posted),),
        params={"minor_unit": "2", **params},
        rounding_residue="0",
        narrative_key="input.echo",
    )


UNAVAILABLE_PARAMS = {"exact_basis": "unavailable: adjusted:manual-adjustment E1 after"}


def _trace(*nodes: TraceNode) -> Trace:
    return Trace(format_version=1, engine_version="test", nodes=nodes, root_measures={})


def _row(version: UUID, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": UUID(int=0x100 + version.int),
        "contract_version_id": version,
        "obligation_key": "POB #1",
        "txn_currency": "USD",  # the version's transaction currency — every node must carry it
        "trace_nodes": {
            column: f"{column}:{SUBJECT}:-" for column in legacy_columns.EXACT_TEXT_COLUMNS
        },
        "remaining_allocation": Decimal("322.10"),
        "revenue_cum": Decimal("128.84"),
        "revenue_amount": Decimal("128.84"),
        "position_obligation": Decimal("-28.84"),
        "position_contract_entity": Decimal("4.31"),
        "netting_reclass_amount": Decimal("0.00"),
        "original_allocated_exact": Decimal("322.101090188305250000"),
    }
    row.update(over)
    row["trace_nodes"]["position_contract_entity"] = f"position_contract_entity:{ENTITY}:-"
    return row


def _six(residue_remaining: str | None) -> tuple[TraceNode, ...]:
    return (
        _node("remaining_allocation", "322.10", residue_remaining),
        _node("revenue_cum", "128.84", "0.0004360753221"),
        _node("position_obligation", "-28.84", "-0.0004360753221"),
        _node("position_contract_entity", "4.31", "0.001199207135786", subject=ENTITY),
        _node("netting_reclass_amount", "0.00", "0"),
    )


def _full_trace(
    residue_remaining: str | None, activity: tuple[TraceNode, ...] | None = None
) -> Trace:
    return _trace(*_six(residue_remaining), *(_activity_chain() if activity is None else activity))


def _column(name: str) -> legacy_columns.LegacyColumn:
    return next(column for column in legacy_columns.CONTRACT_LIVE if column.name == name)


def _fields(refused: Problem) -> list[str]:
    return [error.field for error in refused.errors]


def test_attach_reads_each_rows_own_version_trace_once_and_renders_the_exact_text() -> None:
    # two rows of V1 and one of V2: the SAME node ids in both traces with different residues; each
    # row carries the text of ITS version's node; the loader runs once per distinct version
    traces = {V1: _full_trace("0.00109018830525"), V2: _full_trace(None)}
    loaded: list[UUID] = []

    def loader(_session: Any, version_id: UUID) -> Trace | None:
        loaded.append(version_id)
        return traces.get(version_id)

    rows = [_row(V1), _row(V1, obligation_key="POB #2"), _row(V2)]
    assert exact_sources.attach_exact_texts(None, rows, loader=loader) == 2
    assert loaded == [V1, V2]
    first = rows[0][legacy_columns.EXACT_TEXT_KEY]
    assert first == {
        "remaining_allocation": "322.10109018830525",  # value + residue, no re-scaling
        "revenue_cum": "128.8404360753221",
        "position_obligation": "-28.8404360753221",
        "position_contract_entity": "4.311199207135786",
        "netting_reclass_amount": "0",
        "revenue_amount": ACTIVITY_TEXT,  # rule 4a: the companion's own value, not 128.84
    }
    assert rows[1][legacy_columns.EXACT_TEXT_KEY] == first
    # V2's remaining_allocation node has no residue (an exact node or an adjusted evaluation): the
    # node value is the exact text — the producer's representation, consumed as-is
    assert rows[2][legacy_columns.EXACT_TEXT_KEY]["remaining_allocation"] == "322.1"


def test_attach_renders_a_negative_residue_exactly() -> None:
    # the largest batch-#5 Δ: Contract 1 POB #2 rank 3 — node 118.54, residue
    # −0.006798810703666997; its activity (batch #5's named cell): posted 118.53, companion
    # 118.533201189296333003
    trace = _trace(
        _node("remaining_allocation", "118.54", "-0.006798810703666997"),
        _node("revenue_cum", "118.53", "0.00320118929634"),
        _node("position_obligation", "-18.53", "-0.00320118929634"),
        _node("position_contract_entity", "4.31", "0.001199207135786", subject=ENTITY),
        _node("netting_reclass_amount", "0.00", None),
        *_activity_chain(SUBJECT, Fraction(Decimal("118.533201189296333003")), "118.53"),
    )
    row = _row(V1)
    exact_sources.attach_exact_texts(None, [row], loader=lambda _s, _v: trace)
    texts = row[legacy_columns.EXACT_TEXT_KEY]
    assert texts["remaining_allocation"] == "118.533201189296333003"
    assert abs(Decimal(texts["remaining_allocation"]) - Decimal("118.53320118929634")) < Decimal(
        "0.0001"
    )
    assert texts["position_obligation"] == "-18.53320118929634"
    assert texts["revenue_amount"] == "118.533201189296333003"


def test_activity_supported_negative_zero_and_empty_activities() -> None:
    # rule 4a SUPPORTED: a negative activity (Contract 2 POB #1's shape with the sign flipped), a
    # zero activity over one event, and the defined 0 of a version without admitted events
    negative = Fraction(Decimal("-58.846153846153846154"))
    cases = {
        UUID(int=0x61): (_activity_chain(SUBJECT, negative, "-58.85"), "-58.846153846153846154"),
        UUID(int=0x62): (_activity_chain(SUBJECT, Fraction(0), "0.00"), "0"),
        UUID(int=0x63): (_activity_chain(SUBJECT, Fraction(0), "0.00", events=0), "0"),
    }
    traces = {version: _full_trace("0", chain) for version, (chain, _text) in cases.items()}
    rows = [_row(version) for version in cases]
    assert exact_sources.attach_exact_texts(None, rows, loader=lambda _s, v: traces[v]) == 3
    assert [row[legacy_columns.EXACT_TEXT_KEY]["revenue_amount"] for row in rows] == [
        text for _chain, text in cases.values()
    ]
    assert traces[UUID(int=0x63)].nodes[-2].inputs == ()  # the empty Σ, not a missing companion


def test_activity_is_the_companions_own_value_never_posted_plus_residue() -> None:
    # D-98 134 AMENDMENT 1 (Codex 2215 item 4): A = 1.0049999999999999995 and P = 1.01 sit on
    # opposite-signed ties — Q18(A) = 1.005 while P + Q18(A − P) = 1.004999999999999999; the
    # consumer writes the companion's serialized 1.005, and the checker validates both encodings
    exact = Fraction(Decimal("1.0049999999999999995"))
    chain = _activity_chain(SUBJECT, exact, "1.01")
    posted = chain[-1]
    assert posted.rounding_residue == format_exact(exact - Fraction(Decimal("1.01")))
    assert Decimal(posted.value) + Decimal(posted.rounding_residue) != Decimal("1.005")
    row = _row(V1)
    exact_sources.attach_exact_texts(None, [row], loader=lambda _s, _v: _full_trace("0", chain))
    assert row[legacy_columns.EXACT_TEXT_KEY]["revenue_amount"] == "1.005"


def test_activity_unavailable_writes_the_literal_never_the_posted_cents() -> None:
    # rule 4a UNAVAILABLE (D-98 candidate 149 (i)): the producer names an adjusted endpoint in
    # exact_basis — the cell is the literal, the other columns attach as before, and the column
    # Value passes the literal through (a text cell in a decimal column; SCREENS_B rev 1.24)
    trace = _full_trace("0", (_posted_activity(UNAVAILABLE_PARAMS),))
    row = _row(V1)
    assert exact_sources.attach_exact_texts(None, [row], loader=lambda _s, _v: trace) == 1
    texts = row[legacy_columns.EXACT_TEXT_KEY]
    assert texts["revenue_amount"] == legacy_columns.UNAVAILABLE_TEXT == "unavailable"
    assert texts["revenue_cum"] == "128.8404360753221"
    assert _column("Current Rev Rec").value(row, None) == "unavailable"


def test_activity_legacy_trace_refuses_the_run_by_name() -> None:
    # rule 4a LEGACY: a posted node naming neither exact_node nor exact_basis is a trace without
    # exact-activity provenance — refused like an absent node, never posted-as-exact
    trace = _full_trace("0", (_posted_activity({}),))
    row = _row(V1)
    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(None, [row], loader=lambda _s, _v: trace)
    assert _fields(refused.value) == [f"rows[{row['id']}].revenue_amount"]
    message = refused.value.errors[0].message
    assert exact_sources.REASON_NODE_ABSENT in message
    assert "names no exact companion and no exact_basis" in message
    assert refused.value.errors[0].rule_id == "DG-PAR-05"
    assert legacy_columns.EXACT_TEXT_KEY not in row


def test_activity_companion_defects_refuse_the_run_naming_every_row_and_reason() -> None:
    # rule 4a MISSING / REDIRECTED / posted-class / INVALID companions and a node naming both
    # params: one refusal, in row order, every reason distinct and named (RULING 1's shape)
    missing = _activity_chain(companion_id=f"revenue_amount_exact:{SUBJECT}:2023-02")
    redirected = (
        *_activity_chain(OTHER),
        *_activity_chain(companion_id=f"revenue_amount_exact:{OTHER}:-"),
    )
    posted_class = _activity_chain(companion_residue="0")
    tampered = _activity_chain(companion_value="128.85")
    both = _activity_chain()
    both_posted = TraceNode(
        **{
            **{f.name: getattr(both[-1], f.name) for f in both[-1].__dataclass_fields__.values()},
            "params": {**both[-1].params, **UNAVAILABLE_PARAMS},
        }
    )
    both = (*both[:-1], both_posted)
    versions = {
        UUID(int=0x71): missing,
        UUID(int=0x72): redirected,
        UUID(int=0x73): posted_class,
        UUID(int=0x74): tampered,
        UUID(int=0x75): both,
    }
    traces = {version: _full_trace("0", chain) for version, chain in versions.items()}
    rows = [_row(version) for version in versions]
    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(None, rows, loader=lambda _s, v: traces[v])
    assert _fields(refused.value) == [f"rows[{row['id']}].revenue_amount" for row in rows]
    messages = [error.message for error in refused.value.errors]
    assert (
        f"{exact_sources.REASON_COMPANION_MISSING}: revenue_amount_exact:{SUBJECT}:2023-02"
        in (messages[0])
    )
    assert exact_sources.REASON_COMPANION_REDIRECTED in messages[1]
    assert f"not its own exact measure 'revenue_amount_exact:{SUBJECT}:-'" in messages[1]
    posted_reason = f"{exact_sources.REASON_COMPANION_INVALID}: revenue_amount_exact:{SUBJECT}:-"
    assert f"{posted_reason} is a posted node" in messages[2]
    assert exact_sources.REASON_COMPANION_INVALID in messages[3]
    assert "value 128.85 != Q18(A_replayed) 128.84043607532210109" in messages[3]
    assert "names both exact_node" in messages[4]
    assert {error.rule_id for error in refused.value.errors} == {"DG-PAR-05"}
    assert refused.value.detail == "5 fields need attention."
    for row in rows:
        assert legacy_columns.EXACT_TEXT_KEY not in row


def _clone(node: TraceNode, **over: Any) -> TraceNode:
    return TraceNode(
        **{**{f.name: getattr(node, f.name) for f in node.__dataclass_fields__.values()}, **over}
    )


def test_activity_binding_checks_precede_availability_and_acceptance() -> None:
    # CONSUMER witnesses over decoder-admissible shapes (Trace objects + a lambda loader; no
    # serialization, hash check or trace_from_row here — the retained-ROW decode is the next test).
    # CL55-BINDING-1 (Codex production-20260922-0233 §2–§3): the store admits a retained trace under
    # its canonical hash and the numerical replay never validates measure / currency metadata, so
    # the consumer checks the BINDING before availability — (i) the bound posted node's measure,
    # (ii) its populated, matching currency — and, for SUPPORTED, (iii) the companion's measure and
    # (iv) its populated, matching currency; each a distinct named reason inside the ONE refusal
    chain = _activity_chain()
    companion, posted = chain[-2], chain[-1]
    # (a) a retained trace binding `revenue_amount` to the `revenue_cum` posted node, which carries
    # exact_basis: measure mismatch — never the `unavailable` cell
    six = _six("0")
    cum_with_basis = _clone(six[1], params={"minor_unit": "2", **UNAVAILABLE_PARAMS})
    retained = _row(UUID(int=0x81))
    retained["trace_nodes"]["revenue_amount"] = cum_with_basis.id
    cases: dict[UUID, tuple[dict[str, Any], Trace, str]] = {
        UUID(int=0x81): (
            retained,
            _trace(six[0], cum_with_basis, *six[2:], *chain),
            f"{exact_sources.REASON_MEASURE_MISMATCH}: node revenue_cum:{SUBJECT}:- measures "
            "'revenue_cum', the bound column is 'revenue_amount'",
        ),
        UUID(int=0x82): (  # (b) null posted currency
            _row(UUID(int=0x82)),
            _full_trace("0", (*chain[:-1], _clone(posted, currency=None))),
            f"{exact_sources.REASON_CURRENCY_MISSING}: node revenue_amount:{SUBJECT}:- carries "
            "None, the version's transaction currency is 'USD'",
        ),
        UUID(int=0x83): (  # (c) mismatched posted currency
            _row(UUID(int=0x83)),
            _full_trace("0", (*chain[:-1], _clone(posted, currency="EUR"))),
            f"{exact_sources.REASON_CURRENCY_MISMATCH}: node revenue_amount:{SUBJECT}:- carries "
            "EUR, the version's transaction currency is USD",
        ),
        UUID(int=0x84): (  # (d) wrong companion measure under the expected id
            _row(UUID(int=0x84)),
            _full_trace("0", (*chain[:-2], _clone(companion, measure="revenue_cum_exact"), posted)),
            f"{exact_sources.REASON_MEASURE_MISMATCH}: companion revenue_amount_exact:{SUBJECT}:- "
            "measures 'revenue_cum_exact', not 'revenue_amount_exact'",
        ),
        UUID(int=0x85): (  # (e) null companion currency
            _row(UUID(int=0x85)),
            _full_trace("0", (*chain[:-2], _clone(companion, currency=None), posted)),
            f"{exact_sources.REASON_CURRENCY_MISSING}: companion revenue_amount_exact:{SUBJECT}:- "
            "carries no currency; the version's transaction currency is USD",
        ),
        UUID(int=0x86): (  # (f) the version's own currency unknown: nothing to bind the node to
            _row(UUID(int=0x86), txn_currency=None),
            _full_trace("0"),
            f"{exact_sources.REASON_CURRENCY_MISSING}: node revenue_amount:{SUBJECT}:- carries "
            "'USD', the version's transaction currency is None",
        ),
    }
    rows = [row for row, _t, _r in cases.values()]
    traces = {version: trace for version, (_w, trace, _r) in cases.items()}
    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(None, rows, loader=lambda _s, v: traces[v])
    # (a)–(e) name the activity column; (f) — CL55-RULE4-CURRENCY-1 (04 §17.1 rule 4 rev 1.87) —
    # names EVERY exact column of the currency-less version too (rule 4 now requires a populated
    # version currency, as rule 4a does), the activity last, in EXACT_TEXT_COLUMNS order
    assert _fields(refused.value) == [
        *[f"rows[{row['id']}].revenue_amount" for row in rows[:-1]],
        *[f"rows[{rows[-1]['id']}].{column}" for column in legacy_columns.EXACT_TEXT_COLUMNS],
    ]
    errors = refused.value.errors
    expected = [reason for _w, _t, reason in cases.values()]
    for error, reason in zip((*errors[:5], errors[-1]), expected, strict=True):
        assert reason in error.message, (reason, error.message)
    for error in errors[5:-1]:  # (f)'s five exact columns: rule 4's own `currency missing`
        assert f"{exact_sources.REASON_CURRENCY_MISSING}: node " in error.message
        assert "the version's transaction currency is None" in error.message
        assert "(04 §17.1 rule 4)" in error.message
    for error in errors:
        assert "unavailable" not in error.message  # a binding refusal, never the UNAVAILABLE cell
    assert {error.rule_id for error in errors} == {"DG-PAR-05"}
    assert refused.value.detail == "11 fields need attention."
    for row in rows:
        assert legacy_columns.EXACT_TEXT_KEY not in row  # no `unavailable` cell, no partial attach
    # the same nodes with the binding intact still SUPPORT — the checks add refusals, never values
    good = _row(UUID(int=0x87))
    exact_sources.attach_exact_texts(None, [good], loader=lambda _s, _v: _full_trace("0"))
    assert good[legacy_columns.EXACT_TEXT_KEY]["revenue_amount"] == ACTIVITY_TEXT


def _stored_row(version: UUID, trace: Trace) -> dict[str, Any]:
    """A ``calc_trace`` ROW exactly as ``explain.store.insert_trace`` writes it (the members
    ``trace_from_row`` reads): the store's own document and the canonical hash."""
    return {
        "id": UUID(int=0x7000 + version.int),
        "contract_version_id": version,
        "format_version": trace.format_version,
        "engine_version": trace.engine_version,
        "trace_sha256": trace.sha256(),
        "node_count": len(trace.nodes),
        "root_measures": dict(trace.root_measures),
        "trace": store.trace_document(trace),
    }


def test_activity_binding_refusal_on_a_retained_row_decoded_through_trace_from_row() -> None:
    # Codex 0306 §4 (2): the retained-ROW path — a stored calc_trace row in the store's own shape,
    # decoded through explain.store.trace_from_row with its hash VERIFIED, then refused at the
    # binding check: the retained trace binds `revenue_amount` to the `revenue_cum` USD posted node
    # carrying exact_basis → `measure mismatch`, never the `unavailable` cell; the same decode path
    # SUPPORTS the intact binding (measure and currency, None included, survive the round trip)
    six = _six("0")
    cum_with_basis = _clone(six[1], params={"minor_unit": "2", **UNAVAILABLE_PARAMS})
    retained_trace = _trace(six[0], cum_with_basis, *six[2:], *_activity_chain())
    stored = {V1: _stored_row(V1, retained_trace), V2: _stored_row(V2, _full_trace("0"))}
    decoded: list[UUID] = []

    def loader(_session: Any, version_id: UUID) -> Trace:
        decoded.append(version_id)
        return store.trace_from_row(stored[version_id])  # the hash check runs here

    tampered = {**stored[V1], "trace_sha256": "0" * 64}
    with pytest.raises(TraceIntegrityError):
        store.trace_from_row(tampered)  # the decode path verifies the hash — exercised, not assumed
    retained = _row(V1)
    retained["trace_nodes"]["revenue_amount"] = cum_with_basis.id
    good = _row(V2)
    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(None, [retained, good], loader=loader)
    assert decoded == [V1, V2]
    assert _fields(refused.value) == [f"rows[{retained['id']}].revenue_amount"]
    message = refused.value.errors[0].message
    assert (
        f"{exact_sources.REASON_MEASURE_MISMATCH}: node revenue_cum:{SUBJECT}:- measures "
        "'revenue_cum', the bound column is 'revenue_amount'"
    ) in message
    assert "unavailable" not in message
    assert legacy_columns.EXACT_TEXT_KEY not in retained
    # the export refuses on findings — the good row's text is not relied on (no partial file)
    assert exact_sources.attach_exact_texts(None, [good], loader=loader) == 1
    assert good[legacy_columns.EXACT_TEXT_KEY]["revenue_amount"] == ACTIVITY_TEXT
    round_trip = store.trace_from_row(stored[V2])
    nodes = {node.id: node for node in round_trip.nodes}
    posted = nodes[f"revenue_amount:{SUBJECT}:-"]
    assert (posted.measure, posted.currency) == ("revenue_amount", "USD")
    assert nodes[posted.params["exact_node"]].measure == "revenue_amount_exact"


def test_activity_non_replaying_trace_refuses_by_name_and_replays_once_per_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # rule 4a step (4) replays the WHOLE trace once per loaded trace (two rows, one version → one
    # reevaluate); a trace with an unregistered formula in the companion chain does not replay and
    # the activity is refused by name — never treated as validated by the checker's silence
    calls: list[int] = []
    real = exact_sources.reevaluate

    def counting(trace: Trace) -> Any:
        calls.append(len(trace.nodes))
        return real(trace)

    monkeypatch.setattr(exact_sources, "reevaluate", counting)
    rows = [_row(V1), _row(V1, obligation_key="POB #2")]
    exact_sources.attach_exact_texts(None, rows, loader=lambda _s, _v: _full_trace("0"))
    assert len(calls) == 1
    broken = list(_activity_chain())
    delta = broken[2]
    broken[2] = TraceNode(
        **{
            **{f.name: getattr(delta, f.name) for f in delta.__dataclass_fields__.values()},
            "formula_id": "rec.bogus.v1",
            "narrative_key": "rec.bogus",
        }
    )
    row = _row(V2)
    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(
            None, [row], loader=lambda _s, _v: _full_trace("0", tuple(broken))
        )
    assert _fields(refused.value) == [f"rows[{row['id']}].revenue_amount"]
    assert "the calc trace does not replay" in refused.value.errors[0].message
    assert "rec.bogus.v1" in refused.value.errors[0].message


def test_attach_refuses_the_whole_run_naming_every_offending_row_and_reason() -> None:
    # RULING 1 Q-89-2: ONE refusal listing every (contract version, obligation version, column) —
    # a version without a stored trace, a row whose trace_nodes binds no node, a bound node the
    # trace lacks, and a version whose trace fails its hash check — with the three named reasons
    V3, V4 = UUID(int=0x53), UUID(int=0x54)
    no_trace = _row(V3)
    unbound = _row(V1)
    del unbound["trace_nodes"]["revenue_cum"]
    missing = _row(V1, id=UUID(int=0x999))  # bound to a node the trace does not hold
    missing["trace_nodes"]["netting_reclass_amount"] = "netting_reclass_amount:Other/POB %239:-"
    tampered = _row(V4)
    good = _row(V2)

    def loader(_session: Any, version_id: UUID) -> Trace | None:
        if version_id == V3:
            return None
        if version_id == V4:
            raise TraceIntegrityError("calc trace of contract version does not hash to its record")
        trace = _full_trace("0")
        return trace

    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(
            None, [no_trace, unbound, missing, tampered, good], loader=loader
        )
    errors = refused.value.errors
    # LMG89-FINDINGS-1 (Codex 1535): a wholly unusable trace names EVERY requested column of its row
    # — 6 + 1 + 1 + 6 = 14 findings, in row order, fields rows[<obligation version>].<column>
    columns = list(legacy_columns.EXACT_TEXT_COLUMNS)
    assert [(e.field, e.rule_id) for e in errors] == [
        *[(f"rows[{no_trace['id']}].{column}", "DG-PAR-05") for column in columns],
        (f"rows[{unbound['id']}].revenue_cum", "DG-PAR-05"),
        (f"rows[{missing['id']}].netting_reclass_amount", "DG-PAR-05"),
        *[(f"rows[{tampered['id']}].{column}", "DG-PAR-05") for column in columns],
    ]
    for error in errors[:6]:
        assert str(V3) in error.message and error.message.count("trace missing") == 1
    assert "node absent (pre-provenance trace): trace_nodes binds no node for revenue_cum" in (
        errors[6].message
    )
    assert (
        "node absent (pre-provenance trace): netting_reclass_amount:Other/POB %239:- is not in"
        in errors[7].message
    )
    for error in errors[8:]:
        assert str(V4) in error.message and "hash mismatch" in error.message
    assert len(errors) == 14 and refused.value.detail == "14 fields need attention."
    assert legacy_columns.EXACT_TEXT_KEY not in no_trace  # nothing attached to an offending row
    assert legacy_columns.EXACT_TEXT_KEY not in unbound


def test_export_builders_refuse_the_whole_run_and_write_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the run-level refusal witness (RULING 1): the RPT-10 builder over two versions, one without
    # a stored trace → ONE Problem naming every row of that version; nothing returned; with the
    # traces present the rows carry the exact texts and the activity — the companion's own value
    # for V1, the `unavailable` literal for V2 (the positive builder composition, both branches)
    from datetime import UTC, date, datetime
    from types import SimpleNamespace
    from typing import cast

    from erev_api.db.tables import obligation_version
    from erev_api.domain.reports.builders import ReportParams, contract_history
    from erev_api.domain.reports.builders import legacy_contract_history_export as export

    def full_row(version: UUID, key: str) -> dict[str, Any]:
        # every obligation_version column (None unless the export needs a value) + the population's
        # extras (contract_history.population): the 71 legacy Values then all render
        row: dict[str, Any] = {column.name: None for column in obligation_version.c}
        row.update(_row(version, obligation_key=key))
        row.update(
            contract_external_id="Contract 1",
            entity_code="AVM-US",
            version_no=1,
            chain_version_no=1,  # the number along the contract's chain (never changed its group)
            previous_obligation_version_id=None,
            distinctness="distinct",
            legacy_record_key=f"Contract 1 {key}",
            processed_at=datetime(2026, 9, 21, 14, 0, tzinfo=UTC),
            line_sequence=1,
        )
        return row

    rows = [full_row(V1, "POB #1"), full_row(V1, "POB #2"), full_row(V2, "POB #1")]
    monkeypatch.setattr(
        contract_history, "date_range", lambda *_a, **_k: (date(2023, 1, 1), date(2023, 12, 31))
    )
    monkeypatch.setattr(contract_history, "population", lambda *_a, **_k: [dict(r) for r in rows])
    monkeypatch.setattr(contract_history, "previous_versions", lambda *_a, **_k: {})
    uow = cast(Any, SimpleNamespace(session=object()))
    params = cast(ReportParams, SimpleNamespace(entity_ids=(UUID(int=1),)))
    traces = {V1: _full_trace("0.00109018830525")}  # V2 has no stored trace
    monkeypatch.setattr(export.exact_sources.store, "load_trace", lambda _s, v: traces.get(v))
    with pytest.raises(Problem) as refused:
        export.build(uow, params)
    assert [e.field for e in refused.value.errors] == [
        f"rows[{rows[2]['id']}].{column}" for column in legacy_columns.EXACT_TEXT_COLUMNS
    ]  # LMG89-FINDINGS-1: one finding per column of the unusable version, never a wildcard
    assert "trace missing" in refused.value.errors[0].message
    traces[V2] = _full_trace(None, (_posted_activity(UNAVAILABLE_PARAMS),))
    data = export.build(uow, params)
    assert len(data.rows) == 3
    assert [r["Current Remaining Allocation"] for r in data.rows] == [
        "322.10109018830525",
        "322.10109018830525",
        "322.1",
    ]
    assert [r["Current Rev Rec"] for r in data.rows] == [
        ACTIVITY_TEXT,
        ACTIVITY_TEXT,
        "unavailable",
    ]


def test_attach_refuses_a_node_whose_currency_is_not_the_versions() -> None:
    # Codex 1521 §3 (a): the linkage is actual — the node bound by the row's own trace_nodes in
    # the row's own version's trace, carrying the version's transaction currency; a same-named node
    # in another currency is refused by name, never rendered as a matching value — for the
    # activity's posted node AND its companion alike
    trace = _trace(
        _node("remaining_allocation", "322.10", "0.00109018830525", currency="EUR"),
        *_six("0")[1:],
        *_activity_chain(),
    )
    row = _row(V1)
    loaded: list[UUID] = []

    def loader(_session: Any, version_id: UUID) -> Trace:
        loaded.append(version_id)
        return trace

    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(None, [row], loader=loader)
    assert loaded == [V1]  # the row's OWN contract version, nothing else
    assert _fields(refused.value) == [f"rows[{row['id']}].remaining_allocation"]
    assert "currency mismatch" in refused.value.errors[0].message
    assert "carries EUR" in refused.value.errors[0].message and "is USD" in (
        refused.value.errors[0].message
    )
    assert legacy_columns.EXACT_TEXT_KEY not in row
    foreign = _activity_chain(currency="EUR")
    trace = _full_trace("0", (*foreign[:-1], _activity_chain()[-1]))  # USD posted, EUR companion
    row = _row(V2)
    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(None, [row], loader=lambda _s, _v: trace)
    assert _fields(refused.value) == [f"rows[{row['id']}].revenue_amount"]
    assert "currency mismatch: companion" in refused.value.errors[0].message


def test_attach_refuses_a_null_currency_on_an_exact_column_or_on_the_version() -> None:
    # CL55-RULE4-CURRENCY-1 (Codex production-20260922-0431 §4; 04 §17.1 rule 4 rev 1.87): the five
    # exact columns require a POPULATED node currency equal to the version's, as rule 4a does — a
    # node carrying no currency, or a version without a transaction currency, refuses by name
    # (`currency missing`) inside the ONE run-level refusal, in row order; the golden population
    # carries none (the s13 witness), so only a malformed retained trace reaches this branch
    null_node_trace = _trace(
        _clone(_six("0")[0], currency=None), *_six("0")[1:], *_activity_chain()
    )
    null_node = _row(V1)
    null_version = _row(V2, txn_currency=None)  # the version's own currency unknown
    good = _row(UUID(int=0x53))
    traces = {V1: null_node_trace, V2: _full_trace("0"), UUID(int=0x53): _full_trace("0")}

    with pytest.raises(Problem) as refused:
        exact_sources.attach_exact_texts(
            None, [null_node, null_version, good], loader=lambda _s, version_id: traces[version_id]
        )
    errors = refused.value.errors
    # row order: the null-currency node names its one column; the currency-less version names every
    # exact column (rule 4) AND the activity (rule 4a) — 1 + 6 findings; the intact row is not named
    assert [(e.field, e.rule_id) for e in errors] == [
        (f"rows[{null_node['id']}].remaining_allocation", "DG-PAR-05"),
        *[
            (f"rows[{null_version['id']}].{column}", "DG-PAR-05")
            for column in legacy_columns.EXACT_TEXT_COLUMNS
        ],
    ]
    assert "currency missing: node remaining_allocation:" in errors[0].message
    assert "carries None, the version's transaction currency is 'USD'" in errors[0].message
    assert "(04 §17.1 rule 4)" in errors[0].message
    for error in errors[1:6]:
        assert "currency missing: node " in error.message
        assert "the version's transaction currency is None" in error.message
        assert "(04 §17.1 rule 4)" in error.message
    assert "currency missing: node revenue_amount:" in errors[6].message
    assert "(04 §17.1 rule 4a)" in errors[6].message
    assert len(errors) == 7 and refused.value.detail == "7 fields need attention."
    for row in (null_node, null_version):  # nothing attached to an offending row
        assert legacy_columns.EXACT_TEXT_KEY not in row


def test_legacy_columns_write_the_exact_texts_the_previous_rows_text_and_the_activity() -> None:
    row = _row(V2)
    row[legacy_columns.EXACT_TEXT_KEY] = {
        "remaining_allocation": "118.533201189296333003",
        "revenue_cum": "118.53320118929634",
        "position_obligation": "-18.53320118929634",
        "position_contract_entity": "4.311199207135786",
        "netting_reclass_amount": "0",
        "revenue_amount": "118.533201189296333003",
    }
    previous = _row(V1)
    previous[legacy_columns.EXACT_TEXT_KEY] = {
        "remaining_allocation": "237.06640237859267",
        "revenue_cum": "0",
        "position_obligation": "0",
        "position_contract_entity": "0",
        "netting_reclass_amount": "0",
        "revenue_amount": "0",
    }
    rendered = {
        name: _column(name).value(row, previous)
        for name in (
            "Previous Remaining Allocation",
            "Current Remaining Allocation",
            "Current Rev Rec",
            "Current Rev Rec - Cumulative",
            "Current Contract Position - POB",
            "Current Contract Position - Contract Level",
            "Current Reclass to UAR",
        )
    }
    assert rendered == {
        "Previous Remaining Allocation": "237.06640237859267",  # the previous version's OWN node
        "Current Remaining Allocation": "118.533201189296333003",
        "Current Rev Rec": "118.533201189296333003",  # rule 4a: the companion's value, not 118.53
        "Current Rev Rec - Cumulative": "118.53320118929634",
        "Current Contract Position - POB": "-18.53320118929634",
        "Current Contract Position - Contract Level": "4.311199207135786",
        "Current Reclass to UAR": "0",
    }
    # a first version: the RAW exact original allocation, as before (rule 2)
    assert _column("Previous Remaining Allocation").value(row, None) == "322.10109018830525"
    row[legacy_columns.EXACT_TEXT_KEY]["revenue_amount"] = legacy_columns.UNAVAILABLE_TEXT
    assert _column("Current Rev Rec").value(row, previous) == "unavailable"


def test_legacy_columns_fail_closed_without_the_attached_exact_text() -> None:
    row = _row(V1)  # no exact_text attached
    for name in (
        "Current Remaining Allocation",
        "Current Rev Rec",
        "Current Rev Rec - Cumulative",
        "Current Contract Position - POB",
        "Current Contract Position - Contract Level",
        "Current Reclass to UAR",
    ):
        with pytest.raises(ValueError, match="never the posted cents"):
            _column(name).value(row, None)
    with pytest.raises(ValueError, match="remaining_allocation"):
        _column("Previous Remaining Allocation").value(_row(V2), row)
    assert set(legacy_columns.EXACT_COLUMNS) == {
        "remaining_allocation",
        "revenue_cum",
        "position_obligation",
        "position_contract_entity",
        "netting_reclass_amount",
    }
    assert legacy_columns.ACTIVITY_COLUMNS == ("revenue_amount",)
    assert legacy_columns.EXACT_TEXT_COLUMNS == (*legacy_columns.EXACT_COLUMNS, "revenue_amount")

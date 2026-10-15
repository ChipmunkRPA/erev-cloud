"""Unsupported model explanations never replace the deterministic narrative."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.adapters.ai.provider import FakeProvider
from erev_api.domain.ai.narratives import PreparedNarrative, prepare_narrative
from erev_api.domain.ai.ports import AIResponse
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.explain.service import ExplainNode, Explanation

TRACE = UUID(int=71)


def explanation() -> Explanation:
    return Explanation(
        "0.4",
        "revenue:root",
        "revenue",
        "9764.38",
        "USD",
        (
            ExplainNode(
                "revenue:root",
                "revenue",
                "9764.38",
                "USD",
                "sched.period_difference",
                {"private_note": "do not send this"},
                None,
                (),
            ),
            ExplainNode(
                "allocation:root", "allocation", "10000.00", "USD", "allocate", {}, None, ()
            ),
        ),
        ("Deterministic explanation remains available.",),
    )


def prepared() -> PreparedNarrative:
    return prepare_narrative(
        explanation=explanation(),
        trace_id=TRACE,
        minor_unit=2,
        model="fixture-model",
        max_tokens=1000,
    )


def response(
    narrative: str = "Revenue was USD 9,764.38.", ids: list[str] | None = None
) -> AIResponse:
    raw = json.dumps(
        {"narrative": narrative, "node_ids": ids if ids is not None else ["revenue:root"]}
    )
    return AIResponse(raw, sha256(raw.encode()).hexdigest(), 20, 10, 1, "fixture-model", "end_turn")


def test_traced_narrative_proposed() -> None:
    value = prepared()
    selected = value.select(response())
    assert selected.proposed
    assert selected.narrative == ("Revenue was USD 9,764.38.",)
    assert selected.node_ids == ("revenue:root",)
    assert selected.problem_code is None
    assert value.trace_id == TRACE
    assert value.request.template_id == "explain-narrative"
    assert "private_note" not in value.request.messages[0]["content"]
    assert "Deterministic" not in value.request.messages[0]["content"]


def test_uncited_figure_is_not_supported_by_other_visible_nodes() -> None:
    value = prepared()
    selected = value.select(response("Revenue was USD 10,000.00."))
    assert not selected.proposed
    assert selected.narrative == explanation().narrative
    assert selected.node_ids == ()
    assert selected.problem_code == "AI_UNTRACED_FIGURE"
    assert value.select(response("Allocation was USD 10,000.00.", ["allocation:root"])).proposed


@pytest.mark.parametrize("ids", [[], ["unknown"], ["revenue:root", "revenue:root"]])
def test_invalid_citations_return_only_deterministic_text(ids: list[str]) -> None:
    selected = prepared().select(response(ids=ids))
    assert not selected.proposed
    assert selected.narrative == explanation().narrative
    assert selected.node_ids == ()


@pytest.mark.parametrize(
    "raw",
    [
        '{"narrative":"good","narrative":"bad","node_ids":["revenue:root"]}',
        '{"narrative":NaN,"node_ids":["revenue:root"]}',
        '{"narrative":"good","node_ids":[3]}',
        '{"narrative":"good","node_ids":["revenue:root"],"extra":true}',
        "[]",
        "{",
        "[" * 2000,
        '{"narrative":"","node_ids":[]}',
    ],
)
def test_malformed_output_never_replaces_fallback(raw: str) -> None:
    candidate = replace(response(), text=raw, response_sha256=sha256(raw.encode()).hexdigest())
    selected = prepared().select(candidate)
    assert not selected.proposed
    assert selected.narrative == explanation().narrative


@pytest.mark.parametrize(
    "change",
    [
        {"stop_reason": "refusal"},
        {"stop_reason": "max_tokens"},
        {"response_sha256": "0" * 64},
        {"text": "\ud800"},
        {"text": "x" * (2 * 1024 * 1024 + 1)},
    ],
)
def test_failed_response_keeps_fallback(change: dict[str, str]) -> None:
    original = response()
    selected = prepared().select(
        replace(
            original,
            text=change.get("text", original.text),
            stop_reason=change.get("stop_reason", original.stop_reason),
            response_sha256=change.get("response_sha256", original.response_sha256),
        )
    )
    assert not selected.proposed
    assert selected.narrative == explanation().narrative
    assert selected.node_ids == ()


def test_trace_snapshot_excludes_different_currency() -> None:
    source = explanation()
    other = replace(source.nodes[1], currency="EUR")
    value = prepare_narrative(
        explanation=replace(source, nodes=(source.nodes[0], other)),
        trace_id=TRACE,
        minor_unit=2,
        model="fixture-model",
        max_tokens=1000,
    )
    assert "allocation:root" not in value.values
    assert not value.select(response("Allocation 10,000.00.", ["allocation:root"])).proposed


@pytest.mark.parametrize("value", ["NaN", "1e9999999", "1/3", "9" * 129])
def test_invalid_trace_values_refuse_before_provider(value: str) -> None:
    source = explanation()
    source = replace(source, nodes=(replace(source.nodes[0], value=value),))
    with pytest.raises(PreparationRefused, match="AI_INVALID_TRACE_EVIDENCE"):
        prepare_narrative(
            explanation=source, trace_id=TRACE, minor_unit=2, model="fixture-model", max_tokens=1000
        )


@pytest.mark.parametrize("supported", [True, False])
def test_fake_provider_response_selects_proposal_or_exact_fallback(
    tmp_path: Path, supported: bool
) -> None:
    value = prepared()
    directory = tmp_path / "explain-narrative" / "v1"
    directory.mkdir(parents=True)
    reply = response("Revenue was USD 9,764.38." if supported else "Revenue was USD 10,000.00.")
    (directory / f"{value.request.input_sha256}.json").write_text(
        json.dumps(
            {
                "text": reply.text,
                "input_tokens": 20,
                "output_tokens": 10,
                "latency_ms": 0,
                "stop_reason": "end_turn",
            }
        )
    )
    returned = FakeProvider(tmp_path).complete(value.request)
    selected = value.select(returned)
    assert selected.proposed is supported
    assert selected.narrative == (
        ("Revenue was USD 9,764.38.",) if supported else explanation().narrative
    )
    assert value.deterministic == explanation().narrative


def test_redaction_cannot_silently_change_evidence_ids() -> None:
    source = explanation()
    node = replace(source.nodes[0], id="someone@example.com")
    source = replace(source, nodes=(node,), root_node_id=node.id)
    with pytest.raises(PreparationRefused, match="AI_NARRATIVE_PREPARATION_MISMATCH"):
        prepare_narrative(
            explanation=source, trace_id=TRACE, minor_unit=2, model="fixture-model", max_tokens=1000
        )


def test_evidence_mapping_is_immutable() -> None:
    value = prepared()
    with pytest.raises(TypeError):
        value.values["revenue:root"] = value.values["allocation:root"]  # type: ignore[index]


@pytest.mark.parametrize("currency,minor_unit", [("JPY", 0), ("BHD", 3)])
def test_supplied_currency_precision_reaches_numeric_validation(
    currency: str, minor_unit: int
) -> None:
    source = explanation()
    node = replace(source.nodes[0], currency=currency, value="123.0004")
    value = prepare_narrative(
        explanation=replace(source, currency=currency, nodes=(node,)),
        trace_id=TRACE,
        minor_unit=minor_unit,
        model="fixture-model",
        max_tokens=1000,
    )
    assert value.select(response("Revenue was 123.")).proposed
    assert not value.select(response("Revenue was 124.")).proposed

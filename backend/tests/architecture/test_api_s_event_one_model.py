"""API-S-Event is ONE model (04 §16.3 API-S-Event, rev 1.273; the supervisor's ruling of
2026-10-02 on lane F-CTR-WEB's reading of the Events panel; BUILD_SPEC CTR-5, CTR-15).

Three routes read an event of a contract's stream: ``GET /contracts/{id}/events``, ``GET
/events/{id}`` and ``GET /obligations/{id}/events`` — the route the Events panel of an obligation
and its drawer read. Until rev 1.273 the third answered a model of its own, built by a function of
its own, and the two had drifted apart. Measured on that route: an applied manual event named
neither the person who prepared it nor the one who approved it (``prepared_by``, ``approved_by``;
PRD J-08-AC-3, control CTL-009) — its row is the SYSTEM principal's — and an imported event never
its source row.

This test reads the OpenAPI document of the application: the three reads answer ``EventOut``, and
no other response schema has the shape of a stream event. A member API-S-Event gains is then
answered by every read of an event, and a second model of an event fails here until it is the
first.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from erev_api.config import Settings
from erev_api.main import create_app

EVENT: Final = "EventOut"
LIST: Final = f"ListOut_{EVENT}_"
# The reads of an event and the schema of their 200.
READS: Final = {
    "/api/v1/contracts/{contract_id}/events": LIST,
    "/api/v1/events/{event_id}": EVENT,
    "/api/v1/obligations/{obligation_id}/events": LIST,
}
# What makes a schema an event of a stream: its place in the stream and the hash of its payload.
SHAPE: Final = frozenset({"stream_version", "payload_sha256"})
# The members the obligation's own model lacked or left empty, and the member of rev 1.273.
WHOLE: Final = frozenset({"prepared_by", "approved_by", "source_row", "void_refusal"})


def _name(node: Mapping[str, Any]) -> str:
    return str(node.get("$ref", "")).rsplit("/", 1)[-1]


def answered(document: Mapping[str, Any], path: str) -> str:
    """The schema of the 200 of ``GET path``."""
    ok = document["paths"][path]["get"]["responses"]["200"]
    return _name(ok["content"]["application/json"]["schema"])


def event_models(document: Mapping[str, Any]) -> set[str]:
    """The schemas of ``document`` that have the shape of a stream event."""
    return {
        name
        for name, schema in document["components"]["schemas"].items()
        if set(schema.get("properties") or {}) >= SHAPE
    }


def test_api_s_event_is_one_model_for_every_read_of_an_event(app_settings: Settings) -> None:
    document = create_app(app_settings).openapi()
    schemas = document["components"]["schemas"]

    assert {path: answered(document, path) for path in READS} == READS
    assert _name(schemas[LIST]["properties"]["items"]["items"]) == EVENT
    # one model: a second schema of an event is a second list of members to keep
    assert event_models(document) == {EVENT}
    assert set(schemas[EVENT]["properties"]) >= WHOLE
    assert set(schemas[EVENT]["required"]) == set(schemas[EVENT]["properties"])


def test_api_s_event_the_reader_tells_a_second_model_of_an_event() -> None:
    event = {"properties": {"id": {}, "stream_version": {}, "payload_sha256": {}, "payload": {}}}
    document = {
        "paths": {
            "/api/v1/obligations/{obligation_id}/events": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ListOut_Other_"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "EventOut": event,
                "ObligationEventOut": event,
                # neither: a submission stores items, and a version of a stream is not an event
                "EventSubmissionOut": {"properties": {"id": {}, "items": {}}},
                "ContractOut": {"properties": {"head_stream_version": {}}},
            }
        },
    }
    assert event_models(document) == {"EventOut", "ObligationEventOut"}
    assert answered(document, "/api/v1/obligations/{obligation_id}/events") == "ListOut_Other_"

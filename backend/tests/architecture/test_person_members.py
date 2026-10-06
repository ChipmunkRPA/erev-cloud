"""DG-API-11: a response member that names a person is API-S-Actor (dev-guide §6.4, rev 1.122;
04 §16.0 API-S-Actor, rev 1.139).

A response member that carries a bare principal id leaves the screen without a name: only
``GET /users`` turns the id into one, and that route needs ``user.manage`` — the Policies grids
showed raw ids under "Author" and "Approver" (browser QA, item API-ACTOR-MEMBERS-1). This test
reads the OpenAPI document of the application: every property of a response schema (``…Out``)
whose name says it holds a principal is either an ``ActorOut`` or one of ``NOT_CONVERTED``, the
members that reach no screen as a person today. The list is closed: a new by-person member is an
Actor from its first commit, and a member leaves the list when it is converted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from erev_api.config import Settings
from erev_api.main import create_app

ACTOR: Final = "ActorOut"
# A property that holds a principal: a stamp (`created_by`, `published_by`, `resolved_by_id`) or a
# role of the row (`approver_id`, `on_behalf_of_id`).
BY_PERSON: Final = re.compile(
    r"(_by|_by_id)$|^(on_behalf_of|actor|approver|preparer|reviewer|signer)_id$"
)
# DG-API-11: the by-person members that still carry a bare id. Shorten it; never extend it.
NOT_CONVERTED: Final = frozenset(
    {
        ("AttachmentOut", "created_by"),
        ("AttachmentOut", "voided_by"),
        ("FileOut", "created_by"),
        ("FxRateSetVersionDetailOut", "created_by"),
        ("FxRateSetVersionDetailOut", "published_by"),
        ("FxRateSetVersionOut", "created_by"),
        ("FxRateSetVersionOut", "published_by"),
        ("MappingProfileOut", "published_by"),
        ("PobTemplateVersionOut", "created_by"),
        ("PobTemplateVersionOut", "published_by"),
        ("RuleSetVersionOut", "published_by"),
        ("SodRuleOut", "published_by"),
        ("TenantOut", "ai_disabled_by"),
        ("TenantOut", "created_by"),
        ("TenantOut", "updated_by"),
    }
)
# The members item API-ACTOR-MEMBERS-1 converted: each is an Actor, under this name.
CONVERTED: Final = frozenset(
    {
        ("PolicyOut", "published_by"),
        ("AccountMappingOut", "created_by"),
        ("AccountMappingOut", "published_by"),
        ("ExceptionItemOut", "resolved_by"),
        ("AuditEventOut", "on_behalf_of"),
        ("PeriodLockOut", "created_by"),
        ("PeriodLockRowOut", "created_by"),
        ("TenantSnapshotOut", "created_by"),
    }
)

type Member = tuple[str, str]


def _alternatives(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The schemas a property may hold: itself, or the members of its ``anyOf`` / ``oneOf``."""
    found = [*node.get("anyOf", ()), *node.get("oneOf", ())]
    return found or [node]


def _is_uuid(node: Mapping[str, Any]) -> bool:
    return any(option.get("format") == "uuid" for option in _alternatives(node))


def _is_actor(node: Mapping[str, Any]) -> bool:
    return any(str(option.get("$ref", "")).endswith(f"/{ACTOR}") for option in _alternatives(node))


def person_members(document: Mapping[str, Any]) -> tuple[set[Member], set[Member]]:
    """``(actors, bare)`` of the response schemas of ``document``: the properties that are an
    ``ActorOut``, and the properties named as a principal that are a bare uuid."""
    actors: set[Member] = set()
    bare: set[Member] = set()
    for name, schema in document["components"]["schemas"].items():
        if not name.endswith("Out"):
            continue
        for member, node in (schema.get("properties") or {}).items():
            if _is_actor(node):
                actors.add((name, member))
            elif BY_PERSON.search(member) and _is_uuid(node):
                bare.add((name, member))
    return actors, bare


def test_dg_api_11_a_member_that_names_a_person_is_an_actor(app_settings: Settings) -> None:
    actors, bare = person_members(create_app(app_settings).openapi())
    added = sorted(bare - NOT_CONVERTED)
    assert added == [], (
        "DG-API-11: a response member that names a person is ActorOut, read with its row "
        f"(erev_api.domain.platform.actors), not a bare id: {added}"
    )
    converted = sorted(NOT_CONVERTED - bare)
    assert converted == [], (
        f"DG-API-11: no longer a bare id — remove from NOT_CONVERTED: {converted}"
    )
    assert CONVERTED <= actors, sorted(CONVERTED - actors)


def test_dg_api_11_the_reader_tells_an_actor_from_a_bare_id() -> None:
    document = {
        "components": {
            "schemas": {
                "ProbeOut": {
                    "properties": {
                        "created_by": {"$ref": "#/components/schemas/ActorOut"},
                        "published_by": {
                            "anyOf": [{"$ref": "#/components/schemas/ActorOut"}, {"type": "null"}]
                        },
                        "resolved_by": {
                            "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]
                        },
                        "on_behalf_of_id": {"type": "string", "format": "uuid"},
                        "approver_id": {"type": "string", "format": "uuid"},
                        # neither a principal by name nor an id of one
                        "sorted_by": {"type": "string"},
                        "entity_id": {"type": "string", "format": "uuid"},
                        "owner_membership_id": {"type": "string", "format": "uuid"},
                    }
                },
                # a request body names a principal by id: that is what a client sends
                "ProbeIn": {"properties": {"approver_id": {"type": "string", "format": "uuid"}}},
            }
        }
    }
    assert person_members(document) == (
        {("ProbeOut", "created_by"), ("ProbeOut", "published_by")},
        {
            ("ProbeOut", "resolved_by"),
            ("ProbeOut", "on_behalf_of_id"),
            ("ProbeOut", "approver_id"),
        },
    )

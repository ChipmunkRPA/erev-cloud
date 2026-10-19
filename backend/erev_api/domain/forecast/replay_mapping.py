"""Verify the retained mapping of a forecast import without publishing target configuration."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.imports import mapping_profiles
from erev_api.problems import Problem

_CONTENT = frozenset({"code", "name", "template_code", "version_no", "effective_from", "mappings"})


def profile(snapshot: Mapping[str, Any], *, template_code: str) -> mapping_profiles.Profile:
    """Validate a source-reader snapshot each time its retained mapping is consumed."""
    if set(snapshot) != _CONTENT | {"id", "content_sha256"}:
        raise Problem("precondition-failed", "The retained forecast mapping is malformed.")
    content = {key: snapshot[key] for key in _CONTENT}
    if (
        snapshot["template_code"] != template_code
        or sha256_hex(content) != snapshot["content_sha256"]
    ):
        raise Problem(
            "precondition-failed",
            "The retained forecast mapping does not match its hash or template.",
        )
    try:
        identity = UUID(str(snapshot["id"]))
        mappings = mapping_profiles.normalised_mappings(snapshot["mappings"])
    except (ValueError, TypeError, AttributeError) as error:
        raise Problem(
            "precondition-failed", "The retained forecast mapping is malformed."
        ) from error
    return mapping_profiles.Profile(
        id=identity,
        code=str(snapshot["code"]),
        template_code=template_code,
        aliases=mappings["aliases"],
        constants=mappings["constants"],
        custom_attributes=tuple(mappings["custom_attributes"]),
    )

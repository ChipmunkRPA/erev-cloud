"""Load versioned prompt files and verify their exact bytes before preparation."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from erev_api.domain.ai.preparation import PreparationRefused, PromptTemplate
from erev_api.domain.ai.prompt_manifest import TEMPLATE_SHA256

MAX_TEMPLATE_BYTES = 64 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreparationRefused("AI_INVALID_TEMPLATE_METADATA")
        result[key] = value
    return result


def load_template(template_id: str, version: int, *, root: Path | None = None) -> PromptTemplate:
    """The full UTF-8 file, including metadata, is the system message and hash input.

    Front matter uses JSON, a strict subset of YAML, to avoid aliases, implicit
    scalar conversions and executable tags. Paths are selected only by trusted
    registered identifiers. ``root`` supports packaged-file verification in tests.
    """
    if (
        re.fullmatch(r"[a-z][a-z0-9-]*", template_id) is None
        or type(version) is not int
        or version < 1
    ):
        raise PreparationRefused("AI_INVALID_TEMPLATE")
    expected = TEMPLATE_SHA256.get((template_id, version))
    if expected is None:
        raise PreparationRefused("AI_TEMPLATE_NOT_REGISTERED")
    directory = root if root is not None else Path(__file__).parent / "prompts"
    try:
        with (directory / template_id / f"v{version}.md").open("rb") as handle:
            raw = handle.read(MAX_TEMPLATE_BYTES + 1)
    except OSError:
        raise PreparationRefused("AI_TEMPLATE_UNAVAILABLE") from None
    if len(raw) > MAX_TEMPLATE_BYTES:
        raise PreparationRefused("AI_TEMPLATE_TOO_LARGE")
    if sha256(raw).hexdigest() != expected:
        raise PreparationRefused("AI_TEMPLATE_HASH_MISMATCH")
    try:
        text = raw.decode("utf-8")
        marker, front_matter, body = text.split("---\n", 2)
        if marker or not body.strip():
            raise ValueError("Missing front matter or body")
        metadata = json.loads(front_matter, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError):
        raise PreparationRefused("AI_INVALID_TEMPLATE_METADATA") from None
    if (
        not isinstance(metadata, dict)
        or set(metadata) != {"id", "version", "purpose", "output_schema"}
        or metadata["id"] != template_id
        or type(metadata["version"]) is not int
        or metadata["version"] != version
        or not isinstance(metadata["purpose"], str)
        or not metadata["purpose"].strip()
        or not isinstance(metadata["output_schema"], dict)
        or not metadata["output_schema"]
    ):
        raise PreparationRefused("AI_INVALID_TEMPLATE_METADATA")
    return PromptTemplate(template_id, version, text, expected)

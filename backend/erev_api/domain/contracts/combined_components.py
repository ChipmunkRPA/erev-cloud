"""Original lessor component identities retained by a selected calculation version."""

import json

from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.trace import Trace


def keys(trace: Trace | None, external_id: str, obligation_key: str) -> list[str]:
    if trace is None:
        return []
    subject = obligation_subject_key(external_id, obligation_key)
    node = next((node for node in trace.nodes if node.id == f"stated_price:{subject}:-"), None)
    if node is None or "lessor_judgement_keys" not in node.params:
        return []
    encoded = node.params.get("lessor_component_keys")
    if encoded is None:
        return []  # Historical traces without structured identities cannot supply choices.
    value = json.loads(encoded)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError("Invalid retained lessor component membership")
    return sorted(set(value))

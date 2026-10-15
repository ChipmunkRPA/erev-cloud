"""Prepare minimised, redacted provider input and bind the exact outgoing request.

The gateway must supply only authorised, minimised facts; raw source-document text
has its own argument and is refused when the tenant has not permitted its use.
This pure boundary performs no provider calls, writes, permission checks or budget
reservations. Those remain the job gateway's responsibilities.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.ai.ports import AIRequest
from erev_api.privacy.patterns import redact_text, redact_value


class PreparationRefused(ValueError):
    """A safe, fixed error code without input text."""


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    template_id: str
    version: int
    system: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.template_id or type(self.version) is not int or self.version < 1:
            raise PreparationRefused("AI_INVALID_TEMPLATE")
        if sha256(self.system.encode("utf-8")).hexdigest() != self.sha256:
            raise PreparationRefused("AI_TEMPLATE_HASH_MISMATCH")


def _safe_keys(value: Any) -> None:
    # Redaction replaces values, never JSON field names (PRV-08). Refuse a
    # contact-bearing key rather than leaking it or collapsing distinct keys.
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or redact_text(key) != key:
                raise PreparationRefused("AI_UNSAFE_FIELD_NAME")
            _safe_keys(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _safe_keys(item)


def prepare_request(
    *,
    template: PromptTemplate,
    model: str,
    max_tokens: int,
    inputs: Mapping[str, Any],
    contract_text: str | None = None,
    send_contract_text: bool = False,
    redact_contact_details: bool = True,
) -> AIRequest:
    """Freeze input bytes before their digest is calculated; caller mutation cannot
    change the outgoing messages after review or between budgeting and a call."""
    if not model or type(max_tokens) is not int or max_tokens < 1:
        raise PreparationRefused("AI_INVALID_REQUEST_CONFIGURATION")
    if contract_text is not None and not send_contract_text:
        raise PreparationRefused("AI_CONTRACT_TEXT_DISABLED")
    payload: dict[str, Any] = {"facts": inputs}
    if contract_text is not None:
        payload["contract_text"] = contract_text
    system = template.system
    if redact_contact_details:
        _safe_keys(payload)
        payload = redact_value(payload)
        system = redact_text(system)
    message = MappingProxyType(
        {"role": "user", "content": canonical_bytes(payload).decode("utf-8")}
    )
    parameters = MappingProxyType(
        {
            "template_sha256": template.sha256,
            "send_contract_text": send_contract_text,
            "redact_contact_details": redact_contact_details,
            "max_tokens": max_tokens,
        }
    )
    messages = (message,)
    evidence = {
        "template_id": template.template_id,
        "template_version": template.version,
        "model": model,
        "parameters": parameters,
        "system": system,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    return AIRequest(
        template_id=template.template_id,
        template_version=template.version,
        model=model,
        parameters=parameters,
        system=system,
        messages=messages,
        input_sha256=sha256_hex(evidence),
        max_tokens=max_tokens,
    )

"""Bind the known WLD-F-29 document fixture to a real upload, never arbitrary text."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from erev_api.adapters.documents.pdf import extract_pdf_pages
from erev_api.domain.ai.document_preparation import prepare_extraction
from erev_api.domain.ai.extraction_fields import require_contract_paths
from erev_api.domain.ai.ports import AIRequest

_DOCUMENT = "Kinsley-Marrow-Order-Form-2026-10.pdf"
_RESPONSE = "f95d321bcf24be4c43ac22f435e0a8c99ad7e9c0d2d8afe430873684c432f70c.json"
_ORIGINAL_ID = str(UUID(int=41))


def known_contract_response(request: AIRequest, root: Path) -> str:
    """An explicit known-document fallback after exact/default fixture lookup fails.

    Reconstruct the entire request from the bundled PDF, including the prompt, redacted pages,
    schema, model, token limit and digest. Upload identity, model, token limit and allowed
    field selection may vary; prompt content and redacted source pages must still match.
    No request bytes become a filename, and no response is supplied for other documents.
    """
    if (
        request.template_id != "contract-review"
        or request.template_version != 1
        or request.parameters.get("redact_contact_details") is not True
    ):
        raise FileNotFoundError("No matching AI document fixture")
    try:
        facts = json.loads(request.messages[0]["content"])["facts"]
        document_id = UUID(facts["document_id"])
        raw_paths = facts["allowed_paths"]
        if not isinstance(raw_paths, list) or any(not isinstance(path, str) for path in raw_paths):
            raise ValueError("Invalid paths")
        paths = require_contract_paths(frozenset(raw_paths))
    except (IndexError, KeyError, TypeError, ValueError, AttributeError):
        raise FileNotFoundError("No matching AI document fixture") from None
    expected = prepare_extraction(
        document_id=document_id,
        pages=extract_pdf_pages(
            (root / "documents" / _DOCUMENT).read_bytes(), send_contract_text=True
        ),
        allowed_paths=paths,
        model=request.model,
        max_tokens=request.max_tokens,
        send_contract_text=True,
    )
    if request != expected.request:
        raise FileNotFoundError("No matching AI document fixture")
    value = json.loads((root / "contract-review" / "v1" / _RESPONSE).read_text(encoding="utf-8"))
    fields = json.loads(value["text"])
    selected = []
    for field in fields:
        if field["citation"]["ref_id"] != _ORIGINAL_ID:
            raise ValueError("Invalid known document fixture citation")
        if field["path"] in paths:
            field["citation"]["ref_id"] = str(document_id)
            selected.append(field)
    if not selected:
        raise FileNotFoundError("No matching AI document fields")
    value["text"] = json.dumps(selected, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)

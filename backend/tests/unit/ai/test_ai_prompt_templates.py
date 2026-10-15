"""Retained prompt bytes, version identity and prepared evidence stay bound."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from erev_api.domain.ai import templates
from erev_api.domain.ai.preparation import PreparationRefused, prepare_request
from erev_api.domain.ai.prompt_manifest import TEMPLATE_SHA256
from erev_api.domain.ai.templates import load_template

ROOT = Path(templates.__file__).parent / "prompts"


def test_prompt_manifest_covers_exactly_retained_versions() -> None:
    paths = {f"{name}/v{version}.md" for name, version in TEMPLATE_SHA256}
    assert {str(path.relative_to(ROOT)) for path in ROOT.rglob("*.md")} == paths
    for (name, version), digest in TEMPLATE_SHA256.items():
        raw = (ROOT / name / f"v{version}.md").read_bytes()
        assert sha256(raw).hexdigest() == digest
        template = load_template(name, version)
        assert template.system.encode() == raw
        assert template.sha256 == digest


def test_file_hash_flows_into_prepared_call_evidence() -> None:
    template = load_template("contract-review", 1)
    request = prepare_request(
        template=template, model="configured-model", max_tokens=1000, inputs={}
    )
    assert (
        request.parameters["template_sha256"]
        == sha256((ROOT / "contract-review/v1.md").read_bytes()).hexdigest()
    )
    assert request.system == template.system
    assert request.template_id == "contract-review"
    assert request.template_version == 1


@pytest.mark.parametrize("change", [b" ", b"\r\n", b"Changed instruction"])
def test_changed_version_bytes_refused(tmp_path: Path, change: bytes) -> None:
    target = tmp_path / "contract-review/v1.md"
    target.parent.mkdir()
    target.write_bytes((ROOT / "contract-review/v1.md").read_bytes() + change)
    with pytest.raises(PreparationRefused, match="AI_TEMPLATE_HASH_MISMATCH"):
        load_template("contract-review", 1, root=tmp_path)


@pytest.mark.parametrize(
    "name,version",
    [
        ("../contract-review", 1),
        ("/outside/prompt", 1),
        ("contract-review", True),
        ("contract-review", 0),
    ],
)
def test_path_and_version_refused_before_file_access(name: str, version: int) -> None:
    with pytest.raises(PreparationRefused, match="AI_INVALID_TEMPLATE"):
        load_template(name, version)


def test_unregistered_version_has_no_latest_fallback() -> None:
    with pytest.raises(PreparationRefused, match="AI_TEMPLATE_NOT_REGISTERED"):
        load_template("contract-review", 2)


def test_missing_and_oversized_template_refused(tmp_path: Path) -> None:
    with pytest.raises(PreparationRefused, match="AI_TEMPLATE_UNAVAILABLE"):
        load_template("contract-review", 1, root=tmp_path)
    target = tmp_path / "contract-review/v1.md"
    target.parent.mkdir()
    target.write_bytes(b"x" * (templates.MAX_TEMPLATE_BYTES + 1))
    with pytest.raises(PreparationRefused, match="AI_TEMPLATE_TOO_LARGE"):
        load_template("contract-review", 1, root=tmp_path)


@pytest.mark.parametrize(
    "metadata",
    [
        "{}",
        '{"id":"contract-review","version":true,"purpose":"test","output_schema":{}}',
        '{"id":"contract-review","id":"other","version":1,"purpose":"test","output_schema":{"type":"array"}}',
        "!!python/object:os.system {}",
    ],
)
def test_new_manifest_entry_still_requires_valid_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, metadata: str
) -> None:
    raw = f"---\n{metadata}\n---\nTask body\n".encode()
    target = tmp_path / "contract-review/v1.md"
    target.parent.mkdir()
    target.write_bytes(raw)
    monkeypatch.setattr(
        templates, "TEMPLATE_SHA256", {("contract-review", 1): sha256(raw).hexdigest()}
    )
    with pytest.raises(PreparationRefused, match="AI_INVALID_TEMPLATE_METADATA"):
        load_template("contract-review", 1, root=tmp_path)

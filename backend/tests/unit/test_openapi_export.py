"""OpenAPI document export and staleness check (dev-guide DG-API-10, §1.3; 04 API-C-01; D-72)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from erev_api.api.deps import problem_responses
from erev_api.config import Settings
from erev_api.main import create_app, openapi_document
from fastapi import FastAPI
from support.http import call

ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = ROOT / "docs" / "api" / "openapi.json"
CHECK_SCRIPT = ROOT / "scripts" / "openapi_check.sh"
TAG = "API-R-53 Health, OpenAPI and metrics"


def test_dg_api_10_openapi_31_document(app_settings: Settings) -> None:
    app = create_app(app_settings)
    committed = DOCUMENT.read_text(encoding="utf-8")
    document = json.loads(committed)
    assert document["openapi"] == "3.1.0"
    assert document["info"]["version"] == "1.0.0"
    assert TAG in [tag["name"] for tag in document["tags"]]
    assert document["paths"]["/api/v1/healthz"]["get"]["tags"] == [TAG]
    assert committed == json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert openapi_document(app) == committed

    served = call(app, "GET", "/api/v1/openapi.json")
    assert served.status_code == 200
    assert served.json() == document
    assert [path for path in document["paths"] if path.startswith("/api/v1/__mocks__/")] == []


def test_problem_responses_declare_problem_documents() -> None:
    app = FastAPI()

    @app.get("/probe", responses=problem_responses("forbidden", "mfa-required", "not-found"))
    def probe() -> None: ...

    document = app.openapi()
    responses = document["paths"]["/probe"]["get"]["responses"]
    assert responses["403"]["description"] == "Problem: forbidden, mfa-required"
    assert responses["404"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ProblemOut"
    }
    assert "ProblemOut" in document["components"]["schemas"]


def run_check(*arguments: Path) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("MAKE")}
    return subprocess.run(
        [str(CHECK_SCRIPT), *map(str, arguments)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_openapi_check_detects_stale_document(tmp_path: Path) -> None:
    stale = tmp_path / "openapi.json"
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    document["info"]["title"] = "Stale title"
    stale.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    result = run_check(stale)
    assert result.returncode == 1
    assert "is stale; run make openapi" in result.stdout

    current = run_check()
    assert current.returncode == 0, current.stdout


def test_snapshot_routes_declare_header_schemas() -> None:
    """Codex I4 follow-up 1 (lane record §13.2.16): the shared header components and the four
    snapshot routes' header schemas are in the committed document."""
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    components = document["components"]
    key = components["parameters"]["IdempotencyKey"]
    assert (key["name"], key["in"], key["required"]) == ("Idempotency-Key", "header", True)
    assert key["schema"] == {"type": "string", "minLength": 8, "maxLength": 255}
    assert {"Location", "ETag", "X-Erev-Tenant-Snapshot-Id", "X-Erev-Sandbox-Tenant-Id"} <= set(
        components["headers"]
    )
    request = document["paths"]["/api/v1/tenant/snapshots"]["post"]
    assert {"$ref": "#/components/parameters/IdempotencyKey"} in request["parameters"]
    accepted = request["responses"]["202"]["headers"]
    assert accepted["Location"] == {"$ref": "#/components/headers/Location"}
    assert accepted["X-Erev-Tenant-Snapshot-Id"] == {
        "$ref": "#/components/headers/X-Erev-Tenant-Snapshot-Id"
    }
    manifest = document["paths"]["/api/v1/tenant/snapshots/{tenant_snapshot_id}/manifest"]["get"]
    assert manifest["responses"]["200"]["headers"]["ETag"] == {"$ref": "#/components/headers/ETag"}
    settings = document["paths"]["/api/v1/tenant"]
    assert settings["get"]["responses"]["200"]["headers"]["ETag"]["$ref"].endswith("/ETag")
    assert {"$ref": "#/components/parameters/IdempotencyKey"} in settings["patch"]["parameters"]
    # every command operation declares the header once, from the one shared definition
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if method in {"post", "put", "patch", "delete"} and "parameters" in operation:
                refs = [
                    p
                    for p in operation["parameters"]
                    if p.get("$ref", "").endswith("IdempotencyKey")
                ]
                assert len(refs) <= 1, (path, method)


def test_operator_tenants_declares_its_idempotency_header_without_a_replay_promise() -> None:
    """Codex F-SNP-I51-DOC1 (lane record §13.2.22): the operator route validates the header
    directly (DG-KRN-TEN-05) and must declare it — through a shared component whose description
    states the no-record / no-replay exception and promises no stored-response replay."""
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    operation = document["paths"]["/api/v1/operator/tenants"]["post"]
    ref = {"$ref": "#/components/parameters/IdempotencyKeyOperator"}
    assert operation["parameters"].count(ref) == 1
    assert {"$ref": "#/components/parameters/IdempotencyKey"} not in operation["parameters"]
    component = document["components"]["parameters"]["IdempotencyKeyOperator"]
    assert (component["name"], component["in"], component["required"]) == (
        "Idempotency-Key",
        "header",
        True,
    )
    assert component["schema"] == {"type": "string", "minLength": 8, "maxLength": 255}
    description = component["description"].lower()
    assert "no stored response" in description and "replays the stored response" not in description

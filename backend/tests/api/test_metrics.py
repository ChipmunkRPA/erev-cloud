"""``GET /metrics`` (BUILD_SPEC SOP-4; 04 API-R-53; 05 MET-01 to MET-11; REQ-OPS-012).

These tests build the application without a database: the metrics route reads no tenant data,
and the pool gauge is taken from the api engine object without connecting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.metrics import METRICS
from erev_api.main import create_app
from pydantic import SecretStr
from support.http import call

ROOT: Final = Path(__file__).resolve().parents[3]
TOKEN: Final = "metrics-probe-token-0f9a"  # synthetic; the settings carry it as a SecretStr
LABEL: Final = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
UUID: Final = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
AMOUNT: Final = re.compile(r"^-?[0-9]+\.[0-9]{2,}$")
NAMES: Final = (
    "erev_http_requests_total",
    "erev_http_request_duration_seconds",
    "erev_jobs_total",
    "erev_job_duration_seconds",
    "erev_job_queue_depth",
    "erev_computation_duration_seconds",
    "erev_close_step_duration_seconds",
    "erev_outbox_messages",
    "erev_export_failures_total",
    "erev_audit_chain_verification_failures_total",
    "erev_db_pool_in_use",
)


def _enabled(app_settings: Settings) -> Settings:
    return app_settings.model_copy(
        update={"metrics_enabled": True, "metrics_token": SecretStr(TOKEN)}
    )


def _slug(body: dict[str, object]) -> str:
    return str(body["type"]).rsplit("/", 1)[-1]


def test_req_ops_012_metrics_disabled_by_default(
    app_settings: Settings, clock: FrozenClock
) -> None:
    disabled = app_settings.model_copy(update={"metrics_enabled": False})
    app = create_app(disabled, clock=clock)
    response = call(app, "GET", "/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 404, response.text
    assert _slug(response.json()) == "not-found"


def test_metrics_bearer_and_format(app_settings: Settings, clock: FrozenClock) -> None:
    app = create_app(_enabled(app_settings), clock=clock)
    missing = call(app, "GET", "/metrics")
    assert (missing.status_code, _slug(missing.json())) == (401, "unauthenticated"), missing.text
    wrong = call(app, "GET", "/metrics", headers={"Authorization": "Bearer not-the-token"})
    assert (wrong.status_code, _slug(wrong.json())) == (401, "unauthenticated"), wrong.text
    # A request through the middleware first, so MET-01 / MET-02 carry at least one sample.
    assert call(app, "GET", "/api/v1/healthz").status_code == 200

    response = call(app, "GET", "/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = response.text
    for name in NAMES:
        assert f"# TYPE {name} " in body, name
    assert {item.name for item in METRICS} == set(NAMES)
    assert (
        'erev_http_requests_total{method="GET",route="/api/v1/healthz",status_class="2xx"}' in body
    )
    assert "erev_http_request_duration_seconds_bucket{" in body
    assert 'erev_db_pool_in_use{component="api"}' in body
    # Labels never hold tenant ids, user ids or amounts (05 MET; SOP-4).
    for line in body.splitlines():
        if line.startswith("#") or "{" not in line:
            continue
        for key, value in LABEL.findall(line[line.index("{") : line.rindex("}") + 1]):
            assert not UUID.match(value), line
            # `le` is a histogram bucket bound (seconds), not an amount.
            assert key == "le" or not AMOUNT.match(value), line


def test_metrics_route_not_in_openapi_under_api_v1(
    app_settings: Settings, clock: FrozenClock
) -> None:
    committed = json.loads((ROOT / "docs" / "api" / "openapi.json").read_text("utf-8"))
    assert "/api/v1/metrics" not in committed["paths"]
    assert "/metrics" not in committed["paths"]
    app = create_app(_enabled(app_settings), clock=clock)
    assert app.openapi()["paths"].keys() == committed["paths"].keys()
    under_api = call(app, "GET", "/api/v1/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert under_api.status_code == 404, under_api.text
    # No cookie, no tenant, no Idempotency-Key: the bearer alone serves the exposition.
    served = call(app, "GET", "/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert served.status_code == 200, served.text
    assert "X-Erev-Tenant-Kind" not in served.headers


def test_metrics_malformed_bearer_is_401_never_500(
    app_settings: Settings, clock: FrozenClock
) -> None:
    """R-34 SD-4: a bearer that is not ASCII answered 500 (``compare_digest`` refuses such a
    str); every bearer that is not the token is 401 ``unauthenticated``, and the token still
    passes. The comparison is over the bytes the client sent."""
    app = create_app(_enabled(app_settings), clock=clock)
    refused: list[list[tuple[bytes, bytes]] | dict[str, str]] = [
        [(b"Authorization", b"Bearer caf\xc3\xa9")],  # the review's probe: UTF-8 bytes
        [(b"Authorization", b"Bearer \xff\xfe")],  # bytes that are no UTF-8 at all
        [(b"Authorization", TOKEN.encode() + b"\xc3\xa9")],  # no scheme
        [(b"Authorization", b"Bearer " + TOKEN.encode() + b"\xc3\xa9")],  # the token and more
        {"Authorization": "Bearer "},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": f"Bearer {TOKEN[:-1]}"},
    ]
    for headers in refused:
        response = call(app, "GET", "/metrics", headers=headers)
        assert (response.status_code, _slug(response.json())) == (401, "unauthenticated"), headers
    ok = call(app, "GET", "/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200, ok.text

    # A token that is itself not ASCII is compared by its UTF-8 bytes, as the client sends it.
    accented = app_settings.model_copy(
        update={"metrics_enabled": True, "metrics_token": SecretStr("clé-métrique-0f9a")}
    )
    accented_app = create_app(accented, clock=clock)
    sent = [(b"Authorization", "Bearer clé-métrique-0f9a".encode())]
    assert call(accented_app, "GET", "/metrics", headers=sent).status_code == 200
    near = [(b"Authorization", b"Bearer cle-metrique-0f9a")]
    assert call(accented_app, "GET", "/metrics", headers=near).status_code == 401

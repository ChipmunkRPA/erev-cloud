"""Application factory (docs/dev-guide.md §1.1; 05 §2.5; a DG-KRN-CFG-01 composition root)."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

from erev_api.adapters import mocks
from erev_api.adapters.billing import stripe
from erev_api.adapters.crm import salesforce
from erev_api.adapters.gl import netsuite
from erev_api.adapters.http.adapter_client import client_factory
from erev_api.adapters.idp.oidc_http import HttpxOidcHttp
from erev_api.api.deps import (
    API_PREFIX,
    GuardedRoute,
    install_command_handlers,
    install_openapi_components,
)
from erev_api.api.metrics import metrics_endpoint
from erev_api.api.middleware import RequestLifecycleMiddleware
from erev_api.api.router import api_router, openapi_tags
from erev_api.auth.keyring import build_keyring, build_tenant_key_provisioner
from erev_api.auth.ratelimit import (
    OPENAPI_RATE_LIMIT_LINE,
    LoginRateLimiter,
    PasswordResetRateLimiter,
    RequestRateLimiter,
)
from erev_api.clock import Clock, SystemClock
from erev_api.config import Settings, SettingsError, get_settings
from erev_api.controls.release import log_release, stamp_release
from erev_api.controls.startup import refuse_unsafe_production
from erev_api.domain.integrations import sync as integrations_sync
from erev_api.files.store import build_file_store
from erev_api.logging import configure_logging
from erev_api.problems import install_handlers

TITLE: Final = "eRev Cloud API"
# DG-API-10: the published contract version, independent of the package version.
API_VERSION: Final = "1.0.0"
# 05 SAR-12: the allow-list applies only when EREV_CORS_ORIGINS is non-empty.
CORS_METHODS: Final = ("GET", "POST", "PUT", "PATCH", "DELETE")
CORS_HEADERS: Final = (
    "Content-Type",
    "Idempotency-Key",
    "If-Match",
    "X-CSRF-Token",
    "X-Request-Id",
)
_CORS_ORIGIN: Final = re.compile(r"^https?://[^/?#]+$")
STARTUP_REQUEST_ID: Final = "startup-api"


def cors_allow_list(settings: Settings) -> tuple[str, ...]:
    """The SAR-12 origins; a wildcard or a malformed origin refuses app creation (D-78).

    ``Settings`` still accepts such values, so the production doctor check can report them.
    """
    for origin in settings.cors_origins:
        if "*" in origin or not _CORS_ORIGIN.fullmatch(origin):
            raise SettingsError(
                "EREV_CORS_ORIGINS must list origins matching ^https?://[^/?#]+$ and no "
                "wildcard (05 SAR-12)"
            )
    return settings.cors_origins


def create_app(settings: Settings | None = None, *, clock: Clock | None = None) -> FastAPI:
    """Build the api; ``uvicorn erev_api.main:create_app --factory`` calls it without arguments.

    Without ``settings`` this is the process composition root: it reads the settings and installs
    the logging pipeline. Tests pass their own settings and keep their own logging capture.
    """
    if settings is None:
        settings = get_settings()
        configure_logging(level=settings.log_level, fmt=settings.log_format)
    origins = cors_allow_list(settings)
    env = settings.env

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # 05 SAR-40 startup subset (rev 1.53): a production process refuses fake email and
        # placeholder or repeated master keys before it stamps, connects or serves.
        refuse_unsafe_production(settings)
        # 05 REL-03: the process stamps its release when it starts serving, not when an app is
        # only built (`erev openapi` and the ASGI tests build apps without running startup).
        application.state.engine_release = await run_in_threadpool(
            stamp_release, env, request_id=STARTUP_REQUEST_ID
        )
        log_release(application.state.engine_release)
        yield

    app = FastAPI(
        title=TITLE,
        version=API_VERSION,
        description=OPENAPI_RATE_LIMIT_LINE,
        openapi_url=f"{API_PREFIX}/openapi.json",
        openapi_tags=openapi_tags(),
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    # Routes declared on the application itself record their permission too (DG-KRN-AUTH-03).
    app.router.route_class = GuardedRoute
    app.state.settings = settings
    app.state.clock = clock if clock is not None else SystemClock()
    app.state.keyring = build_keyring(settings)
    # CFG-05: LocalFileStore locally and under compose, GcsFileStore hosted (CMP-05, OPR-09).
    app.state.file_store = build_file_store(settings)
    # KEY-05 provisioning authority for POST /api/v1/operator/tenants; hosted, the api identity is
    # accessor-only and the call fails closed unless the process runs as the provisioning identity.
    app.state.key_provisioner = build_tenant_key_provisioner(settings, app.state.keyring)
    app.state.login_rate_limiter = LoginRateLimiter()
    app.state.password_reset_rate_limiter = PasswordResetRateLimiter()
    # DG-KRN-TEN-05: operator provisioning is limited per source address, as sign-in is.
    app.state.operator_rate_limiter = LoginRateLimiter()
    # SOP-4 (05 SAR-13; API-C-16): one sliding-window limiter per api process (DG-API-07).
    app.state.request_rate_limiter = RequestRateLimiter()
    app.state.oidc_http = HttpxOidcHttp(env=settings.env)
    # DG-LAY-03: the inbound CRM and billing adapters and the guarded client the test-connection
    # probe and the webhook receiver build (05 ADP-14, ADP-16, ADP-17, SAR-15; BUILD_SPEC DIN-12,
    # DIN-13).
    salesforce.register()
    stripe.register()
    netsuite.register()  # the NETSUITE chart source of a COA_SYNC run (BUILD_SPEC DIN-14)
    integrations_sync.register_http_client_factory(client_factory(settings.env))
    install_handlers(app)
    install_command_handlers(app)
    if origins:
        # Added first, so it runs inside the lifecycle middleware and preflight responses carry
        # the SAR-20 headers and the request id.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=CORS_METHODS,
            allow_headers=CORS_HEADERS,
        )
    app.add_middleware(RequestLifecycleMiddleware)
    app.include_router(api_router)
    # 04 API-R-53: GET /metrics outside /api/v1, api process only (BS1-D-36), bearer
    # EREV_METRICS_TOKEN, never in the OpenAPI document (SOP-4).
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    install_openapi_components(app)  # shared header components (record §13.2.16)
    # D-72: the mock adapter servers mount only under dev, test and e2e.
    mocks.mount(app, settings)
    return app


def openapi_document(app: FastAPI) -> str:
    """The committed form of the document: sorted keys, 2-space indent, trailing newline."""
    return json.dumps(app.openapi(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"

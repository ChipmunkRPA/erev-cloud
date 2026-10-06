"""In-process mock adapter servers (05 ADP-20; dev-guide DG-API-09, DG-ARC-04; D-72).

``mount`` includes the mock routers under ``/api/v1/__mocks__`` only when ``EREV_ENV`` is ``dev``,
``test`` or ``e2e``. The routes are unauthenticated, absent from the OpenAPI document and bind no
port of their own; their state lives on the application (ADP-22).
"""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts

from erev_api.adapters.mocks import admin, netsuite, oidc, qbo, salesforce, stripe
from erev_api.config import Environment, Settings

MOCKS_PREFIX: Final = "/api/v1/__mocks__"
MOCK_ENVIRONMENTS: Final = frozenset({Environment.DEV, Environment.TEST, Environment.E2E})


def mount(app: FastAPI, settings: Settings) -> None:
    """Seed the mock state and include the mock routers; never under ``production``."""
    if settings.env not in MOCK_ENVIRONMENTS:
        return
    app.state.mocks = admin.MockWorld(
        adapters={
            oidc.CODE: oidc.OidcMock(issuer=oidc.issuer_for(settings)),
            salesforce.CODE: salesforce.SalesforceMock(),
            stripe.CODE: stripe.StripeMock(),
            netsuite.CODE: netsuite.NetSuiteMock(),
            qbo.CODE: qbo.QboMock(),
        },
        faults=admin.Faults(),
    )
    for router in (
        admin.router,
        oidc.router,
        salesforce.router,
        stripe.router,
        netsuite.router,
        qbo.router,
    ):
        app.include_router(router, prefix=MOCKS_PREFIX, include_in_schema=False)


def mounted_mock_routes(app: FastAPI) -> list[str]:
    """The mock route paths ``app`` mounts (DG-API-09, D-72): empty for a production-profile app.
    A predicate for the architecture test and for the P4 doctor's production check."""
    found: list[str] = []
    for route in iter_route_contexts(app.routes):  # included routers expanded (FastAPI ≥ 0.141)
        path = route.path or ""
        if path.startswith(MOCKS_PREFIX):
            found.append(path)
    return sorted(found)

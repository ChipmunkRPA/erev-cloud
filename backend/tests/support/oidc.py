"""The mock OIDC provider for api and CLI tests (05 ADP-24; BUILD_SPEC PLF-27, BS1-D-25).

``oidc_app`` builds an app whose OIDC client reaches that app's own in-process mock IdP.
``create_mock_oidc`` runs ``erev idp create`` for provider ``mock-oidc`` after ``remove_provider``
has deleted an earlier copy as ``erev_owner``, so every test starts from one unlinked provider and
``GET /session`` lists only what the test created. The provider is bound to ``acme.test``, the
domain of the fixture users Maya and Omar (REQ-PLT-006); ``invite`` runs ``erev idp invite``,
without which no identity signs in through the provider.
"""

from __future__ import annotations

import json
from uuid import UUID

from click.testing import Result
from erev_api import cli
from erev_api.adapters.idp.oidc_http import HttpxOidcHttp
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import owner_engine
from erev_api.db.tables.platform import app_user, identity_provider
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import delete, select, text, update
from support.http import asgi_sync_transport, recording_transport
from support.operators import invoke

PROVIDER_CODE = "mock-oidc"
PROVIDER_NAME = "Mock OIDC"
CLIENT_ID = "erev-local"
ISSUER_URL = "http://127.0.0.1:8190/api/v1/__mocks__/oidc"
# The domain the mock provider is authoritative for: the fixture users Maya and Omar.
EMAIL_DOMAINS: tuple[str, ...] = ("acme.test",)


def idp_create_args(
    *,
    code: str = PROVIDER_CODE,
    kind: str = "oidc",
    issuer_url: str = ISSUER_URL,
    email_domains: tuple[str, ...] = EMAIL_DOMAINS,
) -> list[str]:
    args = [
        "idp",
        "create",
        "--code",
        code,
        "--kind",
        kind,
        "--name",
        PROVIDER_NAME,
        "--issuer-url",
        issuer_url,
        "--client-id",
        CLIENT_ID,
    ]
    for domain in email_domains:
        args += ["--email-domain", domain]
    return args


def oidc_app(
    settings: Settings, clock: FrozenClock, *, requested: list[str] | None = None
) -> FastAPI:
    """The app with its OIDC client over its own mock IdP; ``requested`` collects each URL the
    client sends."""
    app = create_app(settings, clock=clock)
    transport = asgi_sync_transport(app)
    if requested is not None:
        transport = recording_transport(transport, requested)
    app.state.oidc_http = HttpxOidcHttp(env=settings.env, transport=transport)
    return app


# DB-20 (04 §14.1 rev 1.189): the guard that keeps an identity on the provider it was invited for.
GUARD_OFF = text("ALTER TABLE erev.app_user DISABLE TRIGGER tg_app_user__identity_provider")
GUARD_ON = text("ALTER TABLE erev.app_user ENABLE TRIGGER tg_app_user__identity_provider")


def remove_provider(code: str = PROVIDER_CODE) -> None:
    """Unlink the provider's users and delete the provider as ``erev_owner`` (BS1-D-25).

    The product never takes an identity off its provider: DB-20 refuses the unlinking for every
    role (ruling R-111 (7)), and 1.0 has no command that retires a provider. A test world does
    retire one, between tests, because the fixture identities outlive it. Only the owner of the
    table can, with the guard off for that one statement and on again before the transaction
    commits; nothing outside this transaction ever sees it off."""
    with owner_engine().begin() as connection:
        provider_id = connection.execute(
            select(identity_provider.c.id).where(identity_provider.c.code == code)
        ).scalar_one_or_none()
        if provider_id is None:
            return
        connection.execute(GUARD_OFF)
        connection.execute(
            update(app_user)
            .where(app_user.c.identity_provider_id == provider_id)
            .values(
                identity_provider_id=None,
                identity_provider_subject=None,
                updated_by_kind="SYSTEM",
            )
        )
        connection.execute(GUARD_ON)
        connection.execute(delete(identity_provider).where(identity_provider.c.id == provider_id))


def create_mock_oidc(
    services: cli.CliServices, issuer_url: str, *, email_domains: tuple[str, ...] = EMAIL_DOMAINS
) -> UUID:
    remove_provider()
    result = invoke(services, idp_create_args(issuer_url=issuer_url, email_domains=email_domains))
    assert result.exit_code == 0, result.output
    return UUID(json.loads(result.stdout.splitlines()[-1])["id"])


def invite_args(email: str, *, code: str = PROVIDER_CODE) -> list[str]:
    return ["idp", "invite", "--code", code, "--email", email]


def domains_args(
    *, code: str = PROVIDER_CODE, add: tuple[str, ...] = (), remove: tuple[str, ...] = ()
) -> list[str]:
    args = ["idp", "domains", "--code", code]
    for domain in add:
        args += ["--add", domain]
    for domain in remove:
        args += ["--remove", domain]
    return args


def change_domains(
    services: cli.CliServices,
    *,
    code: str = PROVIDER_CODE,
    add: tuple[str, ...] = (),
    remove: tuple[str, ...] = (),
) -> Result:
    """``erev idp domains``: the provider's email domains gain ``add`` and lose ``remove``."""
    return invoke(services, domains_args(code=code, add=add, remove=remove))


def invite(services: cli.CliServices, email: str, *, code: str = PROVIDER_CODE) -> Result:
    """``erev idp invite``: the existing identity with ``email`` is invited for the provider."""
    return invoke(services, invite_args(email, code=code))


def disable(services: cli.CliServices, *, code: str = PROVIDER_CODE) -> Result:
    """``erev idp disable``: the provider is taken out of sign-in."""
    return invoke(services, ["idp", "disable", "--code", code])


def enable(services: cli.CliServices, *, code: str = PROVIDER_CODE) -> Result:
    """``erev idp enable``: the provider is put back into sign-in."""
    return invoke(services, ["idp", "enable", "--code", code])


def end_sessions(services: cli.CliServices, *, code: str = PROVIDER_CODE) -> Result:
    """``erev idp end-sessions``: the sessions opened through a disabled provider end."""
    return invoke(services, ["idp", "end-sessions", "--code", code])


def list_providers(services: cli.CliServices) -> Result:
    """``erev idp list``: the providers with their codes and whether each is enabled."""
    return invoke(services, ["idp", "list"])

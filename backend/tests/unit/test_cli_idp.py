"""``erev idp create``, ``erev idp invite``, ``erev idp domains``, ``erev idp disable``,
``erev idp enable`` and ``erev idp end-sessions`` (04 T-PLT-02, T-PLT-03, T-PLT-06, T-PLT-08; 03
REQ-PLT-006; BUILD_SPEC PLF-27, BS1-D-25; supervisor rulings R-48 (d) and R-108 (b) (5); item
OPS-IDP-SESSIONS-1)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from erev_api.auth import oidc
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Environment
from erev_api.db.session import identity_session
from erev_api.db.tables.platform import app_user, identity_provider, security_event
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import tenant_factory
from support.oidc import (
    ISSUER_URL,
    PROVIDER_CODE,
    PROVIDER_NAME,
    change_domains,
    disable,
    enable,
    end_sessions,
    idp_create_args,
    invite,
    list_providers,
    remove_provider,
)
from support.operators import create_operator, invoke, operator_services

PROBLEM_BASE = "https://erev.dev/problems/"


@pytest.fixture
def no_mock_provider(committed_db: TestDatabase) -> Iterator[None]:
    remove_provider()
    yield
    remove_provider()


def chain_mark() -> int:
    with identity_session(request_id="tests-cli-idp-mark") as db:
        return int(
            db.execute(select(func.coalesce(func.max(security_event.c.chain_seq), 0))).scalar_one()
        )


def test_idp_create_writes_platform_security_event(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    services = operator_services(keyring, clock, tmp_path)
    mark = chain_mark()
    result = invoke(services, idp_create_args())
    assert result.exit_code == 0, result.output
    created = json.loads(result.stdout.splitlines()[-1])
    assert {name: value for name, value in created.items() if name != "id"} == {
        "code": PROVIDER_CODE,
        "kind": "oidc",
        "display_name": "Mock OIDC",
        "issuer_url": ISSUER_URL,
        "client_id": "erev-local",
        "client_secret_ref": None,
        # 04 T-PLT-03 rev 1.108: the domains the provider was bound to.
        "email_domains": ["acme.test"],
        "is_enabled": True,
    }
    with identity_session(request_id="tests-cli-idp") as db:
        rows = db.execute(
            select(
                identity_provider.c.id,
                identity_provider.c.kind,
                identity_provider.c.display_name,
                identity_provider.c.issuer_url,
                identity_provider.c.client_id,
                identity_provider.c.is_enabled,
            ).where(identity_provider.c.code == PROVIDER_CODE)
        ).all()
        events = db.execute(
            select(security_event.c.kind, security_event.c.user_id, security_event.c.detail).where(
                security_event.c.chain_seq > mark
            )
        ).all()
    assert [tuple(row) for row in rows] == [
        (UUID(created["id"]), "oidc", "Mock OIDC", ISSUER_URL, "erev-local", True)
    ]
    assert [tuple(event) for event in events] == [
        ("PLATFORM_SCOPE_USED", None, {"command": "idp.create"})
    ]

    saml = invoke(services, idp_create_args(code="mock-saml", kind="saml"))
    assert saml.exit_code == 1
    problem = json.loads(saml.stderr)
    assert problem["type"] == PROBLEM_BASE + "validation-failed"
    assert [(error["field"], error["rule_id"]) for error in problem["errors"]] == [
        ("kind", "T-PLT-03")
    ]
    duplicate = invoke(services, idp_create_args())
    assert duplicate.exit_code == 1
    assert [
        (error["field"], error["rule_id"]) for error in json.loads(duplicate.stderr)["errors"]
    ] == [("code", "T-PLT-03")]
    with identity_session(request_id="tests-cli-idp-after") as db:
        providers = db.execute(select(func.count()).select_from(identity_provider)).scalar_one()
        written = db.execute(
            select(func.count())
            .select_from(security_event)
            .where(security_event.c.chain_seq > mark)
        ).scalar_one()
    assert (providers, written) == (1, 1)


def test_idp_create_refuses_loopback_http_issuer_in_production(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """PR-A-04 (D-80): loopback or http issuers only under dev, test and e2e (05 SAR-15)."""
    issuer = "http://127.0.0.1:9000/realms/x"
    services = operator_services(keyring, clock, tmp_path, env=Environment.PRODUCTION)
    mark = chain_mark()
    result = invoke(services, idp_create_args(issuer_url=issuer))
    assert result.exit_code == 1, result.output
    problem = json.loads(result.stderr)
    assert problem["type"] == PROBLEM_BASE + "validation-failed"
    assert [(error["field"], error["rule_id"]) for error in problem["errors"]] == [
        ("issuer_url", "T-PLT-03")
    ]
    with identity_session(request_id="tests-cli-idp-production") as db:
        providers = db.execute(
            select(func.count())
            .select_from(identity_provider)
            .where(identity_provider.c.code == PROVIDER_CODE)
        ).scalar_one()
    assert (providers, chain_mark()) == (0, mark)

    assert oidc._issuer_valid(issuer, env=Environment.PRODUCTION) is False
    assert oidc._issuer_valid(issuer, env=Environment.TEST) is True
    assert oidc._issuer_valid("https://127.0.0.1/realms/x", env=Environment.PRODUCTION) is False
    assert oidc._issuer_valid("https://[::1]/realms/x", env=Environment.PRODUCTION) is False
    assert oidc._issuer_valid("https://idp.corp.example/realms/x", env=Environment.PRODUCTION)


def problem_fields(result: object) -> list[tuple[str, str]]:
    problem = json.loads(result.stderr)  # type: ignore[attr-defined]
    assert problem["type"] == PROBLEM_BASE + "validation-failed"
    return [(error["field"], error["rule_id"]) for error in problem["errors"]]


def stored_domains(code: str = PROVIDER_CODE) -> list[str] | None:
    with identity_session(request_id="tests-cli-idp-domains") as db:
        return db.execute(
            select(identity_provider.c.email_domains).where(identity_provider.c.code == code)
        ).scalar_one_or_none()


def test_req_plt_006_a_provider_is_bound_to_its_email_domains_at_creation(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """Ruling R-48 (d): a provider is created for the email domains it is authoritative for,
    1 to 20 distinct host names, stored in lower case. Without one the command creates nothing."""
    services = operator_services(keyring, clock, tmp_path)
    mark = chain_mark()

    unbound = invoke(services, idp_create_args(email_domains=()))
    assert unbound.exit_code == 2, unbound.output  # the option is required
    refused = {
        "a bare label": ("acme",),
        "an address": ("maya@acme.test",),
        "a space": ("acme .test",),
        "a repeated domain": ("acme.test", "ACME.test"),
        "more than twenty": tuple(f"d{number}.acme.test" for number in range(21)),
    }
    for case, domains in refused.items():
        result = invoke(services, idp_create_args(email_domains=domains))
        assert result.exit_code == 1, (case, result.output)
        assert problem_fields(result) == [("email_domains", "T-PLT-03")], case
    assert (stored_domains(), chain_mark()) == (None, mark)

    created = invoke(services, idp_create_args(email_domains=(" Acme.Test", "eu.acme.test")))
    assert created.exit_code == 0, created.output
    assert json.loads(created.stdout.splitlines()[-1])["email_domains"] == [
        "acme.test",
        "eu.acme.test",
    ]
    assert stored_domains() == ["acme.test", "eu.acme.test"]


def identity(email: str) -> tuple[UUID, UUID | None, str | None]:
    """(id, provider, provider subject) of the identity with ``email``."""
    with identity_session(request_id="tests-cli-idp-identity") as db:
        row = db.execute(
            select(
                app_user.c.id,
                app_user.c.identity_provider_id,
                app_user.c.identity_provider_subject,
            ).where(app_user.c.email == email)
        ).one()
    return row.id, row.identity_provider_id, row.identity_provider_subject


def test_req_plt_006_idp_invite_names_the_provider_on_an_existing_identity(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """Ruling R-48 (d): only an identity invited for a provider signs in through it. The operator
    invites an existing identity of the provider's domain; nothing else is admitted, and the
    invitation is a platform security event on the identity."""
    services = operator_services(keyring, clock, tmp_path)
    created = invoke(services, idp_create_args())
    assert created.exit_code == 0, created.output
    provider_id = UUID(json.loads(created.stdout.splitlines()[-1])["id"])
    token = uuid4().hex[:8]
    maya, ines = f"maya-{token}@acme.test", f"ines-{token}@contoso.test"
    for email in (maya, ines):
        tenant_factory(keyring=keyring, clock=clock, admin_email=email)
    operator = create_operator(services, email=f"ops-{token}@acme.test")
    maya_id, _, _ = identity(maya)
    mark = chain_mark()

    refusals = {
        ("no-such-idp", maya): ("code", "T-PLT-03"),  # an unknown provider
        (PROVIDER_CODE, ines): ("email", "T-PLT-03"),  # a domain the provider is not bound to
        (PROVIDER_CODE, f"nobody-{token}@acme.test"): ("email", "T-PLT-03"),  # no such identity
        (PROVIDER_CODE, operator["email"]): ("email", "T-PLT-03"),  # a platform operator
    }
    for (code, email), expected in refusals.items():
        result = invite(services, email, code=code)
        assert result.exit_code == 1, (code, email, result.output)
        assert problem_fields(result) == [expected], (code, email)
    assert chain_mark() == mark
    assert identity(maya) == (maya_id, None, None)

    first = invite(services, f" {maya.upper()} ")  # the address is normalised
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout.splitlines()[-1]) == {
        "provider": PROVIDER_CODE,
        "email": maya,
        "user_id": str(maya_id),
        "invited": True,
        "linked": False,
    }
    assert identity(maya) == (maya_id, provider_id, None)
    again = invite(services, maya)  # a second invitation changes nothing
    assert again.exit_code == 0, again.output
    assert json.loads(again.stdout.splitlines()[-1])["invited"] is False
    with identity_session(request_id="tests-cli-idp-invite") as db:
        events = db.execute(
            select(security_event.c.kind, security_event.c.user_id, security_event.c.detail)
            .where(security_event.c.chain_seq > mark)
            .order_by(security_event.c.chain_seq)
        ).all()
    assert [tuple(event) for event in events] == [
        (
            "PLATFORM_SCOPE_USED",
            maya_id,
            {"command": "idp.invite", "provider": PROVIDER_CODE, "invited": invited},
        )
        for invited in (True, False)
    ]

    # An identity of one provider is not invited for another.
    second = invoke(services, idp_create_args(code="second-idp"))
    assert second.exit_code == 0, second.output
    try:
        elsewhere = invite(services, maya, code="second-idp")
        assert elsewhere.exit_code == 1, elsewhere.output
        assert problem_fields(elsewhere) == [("email", "T-PLT-03")]
        assert identity(maya) == (maya_id, provider_id, None)
    finally:
        remove_provider("second-idp")


def provider_row(code: str = PROVIDER_CODE) -> tuple[list[str], str, int]:
    """(email domains, who last changed the row, its version) of the provider: the version
    counts the writes of the row (04 SC-M, DB-02)."""
    with identity_session(request_id="tests-cli-idp-row") as db:
        row = db.execute(
            select(
                identity_provider.c.email_domains,
                identity_provider.c.updated_by_kind,
                identity_provider.c.row_version,
            ).where(identity_provider.c.code == code)
        ).one()
    return list(row.email_domains), str(row.updated_by_kind), int(row.row_version)


def events_after(mark: int) -> list[tuple[str, UUID | None, dict[str, object]]]:
    with identity_session(request_id="tests-cli-idp-events") as db:
        rows = db.execute(
            select(security_event.c.kind, security_event.c.user_id, security_event.c.detail)
            .where(security_event.c.chain_seq > mark)
            .order_by(security_event.c.chain_seq)
        ).all()
    return [(row.kind, row.user_id, row.detail) for row in rows]


def test_ops_idp_domains_1_the_operator_changes_the_domains_of_a_provider(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """OPS-IDP-DOMAINS-1 (supervisor ruling R-108 (b) (5); 04 T-PLT-03 rev 1.217; REQ-PLT-006
    rev 1.132): a provider had its email domains from ``erev idp create`` and from nothing
    else, so a provider whose organisation gained or gave up a domain could only be changed by
    SQL as ``erev_owner``. ``erev idp domains`` adds and removes domains in one transaction with
    its platform security event; the provider keeps 1 to 20."""
    services = operator_services(keyring, clock, tmp_path)
    created = invoke(services, idp_create_args())
    assert created.exit_code == 0, created.output
    provider_id = UUID(json.loads(created.stdout.splitlines()[-1])["id"])
    mark = chain_mark()

    refused = {
        "no domain named": ({}, "email_domains"),
        "an unknown provider": ({"code": "no-such-idp", "add": ("eu.acme.test",)}, "code"),
        "a bare label to add": ({"add": ("acme",)}, "add"),
        "an address to add": ({"add": ("maya@acme.test",)}, "add"),
        "a domain added twice": ({"add": ("eu.acme.test", "EU.acme.test")}, "add"),
        "a bare label to remove": ({"remove": ("acme",)}, "remove"),
        "one domain added and removed": (
            {"add": ("eu.acme.test",), "remove": ("eu.acme.test",)},
            "email_domains",
        ),
        "the last domain removed": ({"remove": ("acme.test",)}, "email_domains"),
        "more than twenty": (
            {"add": tuple(f"d{number}.acme.test" for number in range(20))},
            "email_domains",
        ),
    }
    for case, (arguments, field) in refused.items():
        result = change_domains(services, **arguments)  # type: ignore[arg-type]
        assert result.exit_code == 1, (case, result.output)
        assert problem_fields(result) == [(field, "T-PLT-03")], case
    assert (provider_row(), chain_mark()) == ((["acme.test"], "SYSTEM", 1), mark)

    added = change_domains(services, add=(" EU.Acme.Test", "contoso.test"))
    assert added.exit_code == 0, added.output
    assert json.loads(added.stdout.splitlines()[-1]) == {
        "provider": PROVIDER_CODE,
        "email_domains": ["acme.test", "eu.acme.test", "contoso.test"],
        "added": ["eu.acme.test", "contoso.test"],
        "removed": [],
        "identities_outside": 0,
    }
    assert provider_row() == (["acme.test", "eu.acme.test", "contoso.test"], "SYSTEM", 2)
    # Adding a domain that is bound and removing one that is not change nothing - the row is not
    # written; the command is answered as done and leaves its event, as a second invitation does.
    again = change_domains(services, add=("contoso.test",), remove=("fabrikam.test",))
    assert again.exit_code == 0, again.output
    unchanged = json.loads(again.stdout.splitlines()[-1])
    assert (unchanged["added"], unchanged["removed"]) == ([], [])
    assert unchanged["email_domains"] == ["acme.test", "eu.acme.test", "contoso.test"]
    assert provider_row() == (["acme.test", "eu.acme.test", "contoso.test"], "SYSTEM", 2)

    # An identity invited for the provider whose domain is taken from it is counted, not moved:
    # it stays invited, and the callback will refuse its domain.
    token = uuid4().hex[:8]
    maya = f"maya-{token}@acme.test"
    tenant_factory(keyring=keyring, clock=clock, admin_email=maya)
    assert invite(services, maya).exit_code == 0
    maya_id, _, _ = identity(maya)
    removed = change_domains(services, add=("fabrikam.test",), remove=("acme.test", "eu.acme.test"))
    assert removed.exit_code == 0, removed.output
    assert json.loads(removed.stdout.splitlines()[-1]) == {
        "provider": PROVIDER_CODE,
        "email_domains": ["contoso.test", "fabrikam.test"],
        "added": ["fabrikam.test"],
        "removed": ["acme.test", "eu.acme.test"],
        "identities_outside": 1,
    }
    assert provider_row() == (["contoso.test", "fabrikam.test"], "SYSTEM", 3)
    assert identity(maya) == (maya_id, provider_id, None)
    assert [event for event in events_after(mark) if event[2].get("command") == "idp.domains"] == [
        (
            "PLATFORM_SCOPE_USED",
            None,
            {
                "command": "idp.domains",
                "provider": PROVIDER_CODE,
                "added": added_domains,
                "removed": removed_domains,
                "identities_outside": outside,
            },
        )
        for added_domains, removed_domains, outside in (
            (["eu.acme.test", "contoso.test"], [], 0),
            ([], [], 0),
            (["fabrikam.test"], ["acme.test", "eu.acme.test"], 1),
        )
    ]


def provider_state(code: str = PROVIDER_CODE) -> tuple[bool, int]:
    """(enabled, row version) of the provider: the version counts the writes of the row."""
    with identity_session(request_id="tests-cli-idp-state") as db:
        row = db.execute(
            select(identity_provider.c.is_enabled, identity_provider.c.row_version).where(
                identity_provider.c.code == code
            )
        ).one()
    return bool(row.is_enabled), int(row.row_version)


def test_ops_idp_domains_1_the_operator_takes_a_provider_out_of_sign_in_and_puts_it_back(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """OPS-IDP-DOMAINS-1 with the supervisor's ruling of 2026-10-01 (04 T-PLT-03 rev 1.217; 05
    SAR-27 rev 1.156): ``identity_provider.is_enabled`` was read by the sign-in and written by
    no command, so a provider could be taken out of sign-in only by SQL as ``erev_owner``.
    ``erev idp disable`` and ``erev idp enable`` write it in one transaction with their platform
    security event; a command that changes nothing does not write the row and still leaves its
    event. The provider's other commands work while it is disabled."""
    services = operator_services(keyring, clock, tmp_path)
    created = invoke(services, idp_create_args())
    assert created.exit_code == 0, created.output
    assert provider_state() == (True, 1)
    mark = chain_mark()

    for command in (disable, enable):
        unknown = command(services, code="no-such-idp")
        assert unknown.exit_code == 1, unknown.output
        assert problem_fields(unknown) == [("code", "T-PLT-03")]
    assert (provider_state(), chain_mark()) == ((True, 1), mark)

    answers = []
    for command, state in (
        (disable, (False, 2)),
        (disable, (False, 2)),  # disabled already: answered as done, the row is not written
        (enable, (True, 3)),
        (enable, (True, 3)),
    ):
        result = command(services)
        assert result.exit_code == 0, result.output
        answers.append(json.loads(result.stdout.splitlines()[-1]))
        assert provider_state() == state
    assert answers == [
        {"provider": PROVIDER_CODE, "is_enabled": False, "changed": True},
        {"provider": PROVIDER_CODE, "is_enabled": False, "changed": False},
        {"provider": PROVIDER_CODE, "is_enabled": True, "changed": True},
        {"provider": PROVIDER_CODE, "is_enabled": True, "changed": False},
    ]
    assert events_after(mark) == [
        (
            "PLATFORM_SCOPE_USED",
            None,
            {"command": command, "provider": PROVIDER_CODE, "changed": changed},
        )
        for command, changed in (
            ("idp.disable", True),
            ("idp.disable", False),
            ("idp.enable", True),
            ("idp.enable", False),
        )
    ]

    # A disabled provider is still the operator's to prepare: its domains change as before.
    assert disable(services).exit_code == 0
    prepared = change_domains(services, add=("eu.acme.test",))
    assert prepared.exit_code == 0, prepared.output
    assert provider_row()[0] == ["acme.test", "eu.acme.test"]
    assert provider_state()[0] is False


def test_ops_idp_sessions_1_the_operator_ends_the_sessions_of_a_disabled_provider(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """Item OPS-IDP-SESSIONS-1 (05 SAR-27 rev 1.178; 04 T-PLT-08 rev 1.249): the command's own
    contract, without a session - ``tests/api/test_oidc.py`` holds what it ends. An unknown
    provider and a provider that is enabled are refused with rule ``T-PLT-03`` and nothing is
    written; on a disabled provider the command answers with its two counts and leaves its
    platform security event, every time it is run; it does not write the provider's row."""
    services = operator_services(keyring, clock, tmp_path)
    created = invoke(services, idp_create_args())
    assert created.exit_code == 0, created.output
    mark = chain_mark()

    unknown = end_sessions(services, code="no-such-idp")
    assert unknown.exit_code == 1, unknown.output
    assert problem_fields(unknown) == [("code", "T-PLT-03")]
    enabled = end_sessions(services)
    assert enabled.exit_code == 1, enabled.output
    assert problem_fields(enabled) == [("code", "T-PLT-03")]
    assert [error["message"] for error in json.loads(enabled.stderr)["errors"]] == [
        oidc.PROVIDER_ENABLED
    ]
    assert (provider_state(), chain_mark()) == ((True, 1), mark)

    assert disable(services).exit_code == 0
    mark = chain_mark()
    nothing = {"provider": PROVIDER_CODE, "identities": 0, "sessions_ended": 0}
    for _ in range(2):
        result = end_sessions(services)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout.splitlines()[-1]) == nothing
    assert (
        events_after(mark)
        == [("PLATFORM_SCOPE_USED", None, {"command": "idp.end-sessions", **nothing})] * 2
    )
    assert provider_state() == (False, 2)


def listed(result: object) -> list[dict[str, object]]:
    lines = result.stdout.splitlines()  # type: ignore[attr-defined]
    providers = json.loads(lines[-1])["providers"]
    assert isinstance(providers, list)
    return providers


def test_erev_idp_list_names_the_providers_and_whether_each_is_enabled(
    no_mock_provider: None, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """05 SAR-27 rev 1.201 (a rider of item INVITE-ACCEPT-SESSION-1). The other ``erev idp``
    commands take a provider's code and refuse an unknown one without naming any; an operator
    had the code only from the line ``erev idp create`` printed. ``erev idp list`` prints every
    provider with its code, kind, name, issuer, email domains and whether it is enabled, ordered
    by code. It reads: the security chain gains no event and the provider's row no write."""
    services = operator_services(keyring, clock, tmp_path)
    before = list_providers(services)
    assert before.exit_code == 0, before.output
    others = listed(before)
    assert PROVIDER_CODE not in [provider["code"] for provider in others]

    created = invoke(services, idp_create_args(email_domains=("zeta.test", "acme.test")))
    assert created.exit_code == 0, created.output
    mark = chain_mark()
    result = list_providers(services)
    assert result.exit_code == 0, result.output
    providers = listed(result)
    codes = [str(provider["code"]) for provider in providers]
    assert codes == sorted(codes)
    (mock,) = [provider for provider in providers if provider["code"] == PROVIDER_CODE]
    assert mock == {
        "code": PROVIDER_CODE,
        "kind": "oidc",
        "display_name": PROVIDER_NAME,
        "issuer_url": ISSUER_URL,
        "email_domains": ["acme.test", "zeta.test"],
        "is_enabled": True,
    }
    assert [provider for provider in providers if provider["code"] != PROVIDER_CODE] == others
    assert (provider_state(), chain_mark()) == ((True, 1), mark)

    assert disable(services).exit_code == 0
    mark = chain_mark()
    (mock,) = [
        provider
        for provider in listed(list_providers(services))
        if provider["code"] == PROVIDER_CODE
    ]
    assert mock["is_enabled"] is False
    assert (provider_state(), chain_mark()) == ((False, 2), mark)

    # A provider created later whose code sorts earlier stands before it: the order is the
    # code's, not the order of creation.
    earlier = "a-later-oidc"
    try:
        second = invoke(
            services,
            idp_create_args(
                code=earlier, issuer_url=f"{ISSUER_URL}-later", email_domains=("later.test",)
            ),
        )
        assert second.exit_code == 0, second.output
        ours = [
            (str(provider["code"]), provider["is_enabled"])
            for provider in listed(list_providers(services))
            if provider["code"] in (earlier, PROVIDER_CODE)
        ]
        assert ours == [(earlier, True), (PROVIDER_CODE, False)]
    finally:
        remove_provider(earlier)

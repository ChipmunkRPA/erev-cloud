"""The link of an email is composed when it is sent (05 NTR-04, KEY-03 rev 1.90; 04 T-INT-03
``payload``, T-PLT-07, T-PLT-42 rev 1.151; security review 2026-09-29 P3-17; supervisor rulings
R-48 (g), R-53 (h)).

No database: the key ring derives from synthetic master keys, and the two message builders are
called as their commands call them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.adapters.keys.provider import LocalKeyProvider
from erev_api.adapters.secrets.store import EnvSecretStore
from erev_api.auth import credentials
from erev_api.auth.keyring import LINK_TOKEN_LABEL, KeyRing, LinkToken
from erev_api.config import Settings
from erev_api.domain.platform import provisioning
from erev_api.enums import OutboxTopic, PrincipalKind
from erev_api.events import outbox
from support.links import emailed_link, emailed_token

TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
ROW = UUID("0191e0a0-0000-7000-8000-0000000000aa")
OTHER = UUID("0191e0a0-0000-7000-8000-0000000000bb")
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


@pytest.fixture
def keyring(app_settings: Settings) -> KeyRing:
    return KeyRing(LocalKeyProvider(EnvSecretStore(app_settings)))


def test_key_03_the_token_of_a_link_is_derived_from_the_platform_security_key(
    keyring: KeyRing,
) -> None:
    issued = keyring.link_token("password-reset", ROW)
    assert issued.key_id == keyring.current_security_key_id() == "security-hmac:1"
    # The construction 05 KEY-03 states: HMAC-SHA256 over the label, the purpose and the
    # reference's 16 bytes, as 43 URL-safe characters.
    expected = hmac.new(
        keyring.security_event_key("security-hmac:1"),
        b"\x00".join((LINK_TOKEN_LABEL, b"password-reset", ROW.bytes)),
        hashlib.sha256,
    ).digest()
    assert issued.token == base64.urlsafe_b64encode(expected).rstrip(b"=").decode("ascii")
    assert len(issued.token) == 43
    # The same link gives the same token, when it is issued and when it is sent; another
    # reference, another purpose or another key gives another.
    assert keyring.link_token("password-reset", ROW, key_id=issued.key_id) == issued
    others = {
        keyring.link_token("password-reset", OTHER).token,
        keyring.link_token("invitation", ROW).token,
    }
    assert len(others | {issued.token}) == 3
    # A token never shows in a representation (it would reach a log).
    assert issued.token not in repr(issued)
    assert repr(issued) == "LinkToken(key_id='security-hmac:1')"
    assert isinstance(issued, LinkToken)


def test_p3_17_the_reset_message_names_its_token_and_never_holds_it(keyring: KeyRing) -> None:
    """Security review P3-17 (ruling R-48 (g)): the reset link stood in clear, token included, in
    ``outbox_message.payload`` of the workspace. The message names the token by reference; the
    dispatcher composes the link."""
    issued = keyring.link_token(credentials.RESET_PURPOSE, ROW)
    values = credentials.reset_message(
        tenant_id=TENANT, token_id=ROW, email="lena@acme.test", key_id=issued.key_id, now=NOW
    )
    payload = values["payload"]
    assert payload["link_path"] == "/password/reset/confirm#token={token}"
    assert payload[outbox.LINK_TOKEN] == {
        "purpose": "password-reset",
        "reference": str(ROW),
        "key_id": "security-hmac:1",
    }
    assert issued.token not in json.dumps(values, default=str)
    # The email carries the link with the token whose SHA-256 the T-PLT-42 row stores.
    assert emailed_link(payload, keyring) == f"/password/reset/confirm#token={issued.token}"
    assert emailed_token(payload, keyring, prefix="/password/reset/confirm#token=") == issued.token


def test_p3_17_the_invitation_message_names_its_token_and_never_holds_it(keyring: KeyRing) -> None:
    """Ruling R-53 (h): the invitation link joins P3-17. Every invitation email has a reference of
    its own, so a re-sent invitation has another token."""
    first = provisioning.invitation_token(keyring)
    again = provisioning.invitation_token(keyring)
    assert first.reference != again.reference and first.token != again.token
    assert first.token not in repr(first)
    values = provisioning.invitation_message(
        tenant_id=TENANT,
        membership_id=ROW,
        email="ines@acme.test",
        workspace_name="Avenmoor",
        link_reference=first.reference,
        key_id=first.key_id,
        expires_at=NOW + timedelta(days=7),
        created_by=None,
        created_by_kind=PrincipalKind.SYSTEM,
        now=NOW,
    )
    payload = values["payload"]
    assert payload["link_path"] == "/accept-invitation#token={token}"
    assert payload[outbox.LINK_TOKEN] == {
        "purpose": "invitation",
        "reference": str(first.reference),
        "key_id": first.key_id,
    }
    assert first.token not in json.dumps(values, default=str)
    assert emailed_token(payload, keyring, prefix="/accept-invitation#token=") == first.token


def _email(**payload: object) -> dict[str, object]:
    return outbox.message_values(
        tenant_id=TENANT,
        topic=OutboxTopic.EMAIL,
        aggregate_type="probe",
        aggregate_id=ROW,
        dedupe_key="probe",
        payload={
            "to": "a@acme.test",
            "subject": "s",
            "text": "t",
            "reference": str(ROW),
            **payload,
        },
        now=NOW,
        created_by=None,
        created_by_kind=PrincipalKind.SYSTEM,
    )


def test_t_int_03_an_email_payload_is_refused_when_it_would_hold_a_token(keyring: KeyRing) -> None:
    named = outbox.link_token_reference("invitation", ROW, "security-hmac:1")
    token = keyring.link_token("invitation", ROW).token
    # A token formatted into the path, as both builders did before.
    with pytest.raises(ValueError, match="never holds the token"):
        _email(link_path=f"/accept-invitation#token={token}")
    with pytest.raises(ValueError, match="never holds the token"):
        _email(link_path=f"/accept-invitation#token={token}", link_token=named)
    # The place and the reference come together.
    with pytest.raises(ValueError, match="names its token"):
        _email(link_path="/accept-invitation#token={token}")
    with pytest.raises(ValueError, match="names its token"):
        _email(link_path="/approvals", link_token=named)
    # Positive controls: a link without a secret, no link, and a named token.
    assert (
        _email(link_path="/approvals/requests/1")["payload"]["link_path"] == "/approvals/requests/1"
    )
    assert "link_path" not in _email()["payload"]
    accepted = _email(link_path="/accept-invitation#token={token}", link_token=named)["payload"]
    assert outbox.email_link_path(accepted, keyring) == f"/accept-invitation#token={token}"
    # Other topics carry their own payloads, unchecked here.
    other = outbox.message_values(
        tenant_id=TENANT,
        topic=OutboxTopic.WEBHOOK,
        aggregate_type="probe",
        aggregate_id=ROW,
        dedupe_key="probe",
        payload={"token=": "x"},
        now=NOW,
        created_by=None,
        created_by_kind=PrincipalKind.SYSTEM,
    )
    assert other["payload"] == {"token=": "x"}


def test_ntr_04_the_dispatcher_composes_the_link_and_fails_closed(keyring: KeyRing) -> None:
    assert outbox.email_link_path({"text": "t"}, keyring) is None
    assert outbox.email_link_path({"link_path": "/approvals"}, None) == "/approvals"
    named = outbox.link_token_reference("password-reset", ROW, "security-hmac:1")
    payload = {"link_path": "/password/reset/confirm#token={token}", "link_token": named}
    link = outbox.email_link_path(payload, keyring)
    assert link is not None and link.startswith("/password/reset/confirm#token=")
    assert "{token}" not in link
    # A place without a named token is never sent as it stands, and a named token needs a ring.
    with pytest.raises(ValueError, match="names its token"):
        outbox.email_link_path({"link_path": "/password/reset/confirm#token={token}"}, keyring)
    with pytest.raises(RuntimeError, match="no key ring"):
        outbox.email_link_path(payload, None)

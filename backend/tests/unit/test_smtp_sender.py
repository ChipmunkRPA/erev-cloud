"""The SMTP email adapter against a real TLS peer (05 NTR-05, CFG-18, SAR-15; D-80; R-34 SD-7).

``SmtpEmailSender`` connects to the address the SAR-15 guard checked and verifies the relay's
certificate against the configured host name. The security review of 2026-09-29 found that the
two never met: the client kept an empty host name, so STARTTLS raised ``check_hostname requires
server_hostname`` and no mail could be delivered under ``EREV_EMAIL_BACKEND=smtp``. These tests
deliver through ``support.smtp_sink.TlsSmtpSink`` on loopback with a certificate authority created
for the test: no network, and no socket of the sender is replaced except where a test says so
(the network pieces live in the support module, DG-ARC-12).
"""

from __future__ import annotations

import ssl
from collections.abc import Iterator
from datetime import UTC, datetime
from email import message_from_bytes
from pathlib import Path
from uuid import uuid4

import pytest
from erev_api.adapters.email.smtp import SmtpEmailSender, _CheckedSMTP
from erev_api.adapters.http.guard import DestinationRefused
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.events.outbox import EmailMessage
from pydantic import SecretStr
from support.production import production_settings
from support.smtp_sink import (
    Authority,
    SmtpNotSupported,
    TlsSmtpSink,
    authority,
    carry_connections_to,
)

HOST = "relay.erev.test"
# What the relay is asked to authenticate; a fixture value, no credential of any system.
RELAY_CREDENTIAL = "relay-credential"
PUBLIC_ADDRESS = "93.184.216.34"  # a global-unicast literal; the production test connects nowhere
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def trusted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Authority:
    """A certificate authority the default TLS context trusts for this test (OpenSSL reads
    ``SSL_CERT_FILE`` when the context loads its default certificates)."""
    found = authority(tmp_path / "pki")
    monkeypatch.setenv("SSL_CERT_FILE", str(found.ca_file))
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    return found


@pytest.fixture
def sink(trusted: Authority, tmp_path: Path) -> Iterator[TlsSmtpSink]:
    cert_file, key_file = trusted.issue(HOST, tmp_path / "pki")
    with TlsSmtpSink(cert_file, key_file) as running:
        yield running


def _message() -> EmailMessage:
    return EmailMessage(
        tenant_code="acme",
        reference=uuid4(),
        to="controller@acme.test",
        subject="You are invited to eRev Cloud",
        text="Accept the invitation: https://erev.example/invitations/accept#token=probe",
    )


def _sender(
    port: int,
    *,
    env: Environment = Environment.TEST,
    address: str = "127.0.0.1",
    host: str = HOST,
    username: str | None = None,
    password: str | None = None,
    private_relay: bool = False,
    ca_file: Path | None = None,
) -> SmtpEmailSender:
    return SmtpEmailSender(
        host=host,
        port=port,
        username=username,
        password=None if password is None else SecretStr(password),
        sender="erev@acme.test",
        clock=FrozenClock(AT),
        env=env,
        resolve=lambda name, _port: [address],
        private_relay=private_relay,
        ca_file=ca_file,
    )


def _verbs(sink: TlsSmtpSink, *, encrypted: bool) -> list[str]:
    return [line.split(" ", 1)[0].upper() for secure, line in sink.commands if secure is encrypted]


def test_smtp_sender_delivers_over_starttls_with_the_host_verified(sink: TlsSmtpSink) -> None:
    """The message is delivered; the handshake names the configured host (SNI) and verifies the
    certificate against it; nothing but EHLO and STARTTLS travels before the handshake."""
    message = _message()
    message_id = _sender(sink.port).send(message)

    assert sink.handshake_errors == []
    assert sink.server_names == [HOST]
    (delivery,) = sink.deliveries
    assert (delivery.mail_from, delivery.recipients) == ("erev@acme.test", [message.to])
    received = message_from_bytes(delivery.data)
    assert received["Message-ID"] == message_id == f"<{message.reference}@erev.invalid>"
    assert (received["From"], received["To"]) == ("erev@acme.test", message.to)
    assert received["Subject"] == message.subject
    assert message.text in received.get_payload(decode=True).decode("utf-8")
    assert _verbs(sink, encrypted=False) == ["EHLO", "STARTTLS"]
    assert _verbs(sink, encrypted=True) == ["EHLO", "MAIL", "RCPT", "DATA", "QUIT"]
    # The client keeps the host name for the certificate check while its socket goes to the
    # checked address (the defect: it kept "").
    assert _CheckedSMTP("127.0.0.1", host=HOST, timeout=1.0)._host == HOST


def test_smtp_sender_logs_in_only_inside_the_tls_session(sink: TlsSmtpSink) -> None:
    _sender(sink.port, username="erev", password=RELAY_CREDENTIAL).send(_message())
    assert sink.credentials == [(True, "erev", RELAY_CREDENTIAL)]
    assert "AUTH" not in _verbs(sink, encrypted=False)
    assert len(sink.deliveries) == 1


def test_smtp_sender_refuses_a_certificate_for_another_name(
    trusted: Authority, tmp_path: Path
) -> None:
    """A relay that presents a trusted certificate for another host is refused in the handshake;
    no envelope and no message follow."""
    cert_file, key_file = trusted.issue("other.erev.test", tmp_path / "pki")
    with TlsSmtpSink(cert_file, key_file) as sink:
        with pytest.raises(ssl.SSLCertVerificationError) as refused:
            _sender(sink.port).send(_message())
        assert "Hostname mismatch" in str(refused.value)
    assert sink.deliveries == [] and _verbs(sink, encrypted=True) == []


def test_smtp_sender_refuses_a_certificate_of_an_untrusted_authority(
    trusted: Authority, tmp_path: Path
) -> None:
    stranger = authority(tmp_path / "stranger", name="another authority")
    cert_file, key_file = stranger.issue(HOST, tmp_path / "stranger")
    with TlsSmtpSink(cert_file, key_file) as sink:
        with pytest.raises(ssl.SSLCertVerificationError):
            _sender(sink.port).send(_message())
    assert sink.deliveries == [] and _verbs(sink, encrypted=True) == []


def test_smtp_sender_sends_nothing_to_a_relay_without_starttls(
    trusted: Authority, tmp_path: Path
) -> None:
    """STARTTLS is mandatory (SAR-15: SMTP with STARTTLS): a relay that does not offer it gets
    the greeting exchange and nothing else — no credentials, no envelope, no message."""
    cert_file, key_file = trusted.issue(HOST, tmp_path / "pki")
    with TlsSmtpSink(cert_file, key_file, offer_starttls=False) as sink:
        with pytest.raises(SmtpNotSupported):
            _sender(sink.port, username="erev", password=RELAY_CREDENTIAL).send(_message())
    assert sink.deliveries == [] and sink.credentials == []
    assert set(_verbs(sink, encrypted=False)) <= {"EHLO", "QUIT"}


def test_smtp_sender_under_production_connects_to_the_checked_address(
    sink: TlsSmtpSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The security review's probe, inverted (R-34 SD-7). Under production the host must resolve
    to a global address and the socket goes to exactly that address, never to the name; here that
    one connection is carried to the loopback sink, and the delivery completes with the
    certificate verified against the host name."""
    connected = carry_connections_to(sink, monkeypatch)
    sender = _sender(
        587,
        env=Environment.PRODUCTION,
        address=PUBLIC_ADDRESS,
        username="erev",
        password=RELAY_CREDENTIAL,
    )
    sender.send(_message())
    assert connected == [(PUBLIC_ADDRESS, 587)]
    assert sink.server_names == [HOST] and len(sink.deliveries) == 1
    assert sink.credentials == [(True, "erev", RELAY_CREDENTIAL)]

    # Control: production still refuses a relay on a private or loopback address before any
    # socket opens (SAR-15; D-80).
    connected.clear()
    for address in ("10.0.0.5", "127.0.0.1", "169.254.169.254"):
        with pytest.raises(DestinationRefused):
            _sender(587, env=Environment.PRODUCTION, address=address).send(_message())
    assert connected == [] and len(sink.deliveries) == 1


# --- 05 SAR-15, CFG-18 rev 1.53 (supervisor ruling R-39): the operator's private relay ---------


@pytest.fixture
def operator_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Authority:
    """A certificate authority that no trust store of the test knows: the default TLS context
    trusts an unrelated authority, so only ``EREV_SMTP_CA_FILE`` can make the relay's certificate
    valid."""
    unrelated = authority(tmp_path / "unrelated", name="an unrelated authority")
    monkeypatch.setenv("SSL_CERT_FILE", str(unrelated.ca_file))
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    return authority(tmp_path / "operator", name="the operator authority")


def test_private_relay_opt_in_delivers_to_a_loopback_relay_under_production(
    operator_authority: Authority, tmp_path: Path
) -> None:
    """With the opt-in a production sender reaches a relay on a loopback address — no connection
    of the test is carried anywhere — and verifies its certificate against the bundle
    ``EREV_SMTP_CA_FILE`` names. Without the opt-in the relay is refused before any socket opens;
    with the opt-in and without the bundle the handshake fails and nothing is sent."""
    cert_file, key_file = operator_authority.issue(HOST, tmp_path / "operator")
    bundle = operator_authority.ca_file
    with TlsSmtpSink(cert_file, key_file) as sink:
        with pytest.raises(DestinationRefused):
            _sender(sink.port, env=Environment.PRODUCTION, ca_file=bundle).send(_message())
        assert sink.commands == []

        with pytest.raises(ssl.SSLCertVerificationError):
            _sender(sink.port, env=Environment.PRODUCTION, private_relay=True).send(_message())
        assert sink.deliveries == [] and _verbs(sink, encrypted=True) == []

        _sender(
            sink.port,
            env=Environment.PRODUCTION,
            private_relay=True,
            ca_file=bundle,
            username="erev",
            password=RELAY_CREDENTIAL,
        ).send(_message())
    assert len(sink.deliveries) == 1 and sink.server_names[-1] == HOST
    assert sink.credentials == [(True, "erev", RELAY_CREDENTIAL)]
    assert "AUTH" not in _verbs(sink, encrypted=False)


def test_smtp_ca_file_is_the_trust_of_the_relay_in_place_of_the_system_store(
    trusted: Authority, tmp_path: Path
) -> None:
    """A certificate the system store accepts is refused when ``EREV_SMTP_CA_FILE`` names another
    authority: the bundle replaces the store for the relay, it does not add to it."""
    other = authority(tmp_path / "other", name="another authority")
    cert_file, key_file = trusted.issue(HOST, tmp_path / "pki")
    with TlsSmtpSink(cert_file, key_file) as sink:
        with pytest.raises(ssl.SSLCertVerificationError):
            _sender(sink.port, ca_file=other.ca_file).send(_message())
        assert sink.deliveries == []
        _sender(sink.port, ca_file=trusted.ca_file).send(_message())
    assert len(sink.deliveries) == 1


@pytest.mark.parametrize("address", ["169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1"])
def test_private_relay_opt_in_still_refuses_link_local_and_reserved_relays(
    address: str, sink: TlsSmtpSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    connected = carry_connections_to(sink, monkeypatch)
    sender = _sender(587, env=Environment.PRODUCTION, address=address, private_relay=True)
    with pytest.raises(DestinationRefused):
        sender.send(_message())
    assert connected == [] and sink.commands == []


def test_smtp_sender_takes_the_opt_in_and_the_bundle_from_the_settings(
    app_settings: Settings, tmp_path: Path
) -> None:
    clock = FrozenClock(AT)
    default = SmtpEmailSender.from_settings(production_settings(app_settings), clock)
    assert (default.private_relay, default.ca_file) == (False, None)
    bundle = tmp_path / "relay-ca.pem"
    opted = SmtpEmailSender.from_settings(
        production_settings(app_settings, smtp_private_relay=True, smtp_ca_file=bundle), clock
    )
    assert (opted.private_relay, opted.ca_file) == (True, bundle)

"""A loopback SMTP sink with STARTTLS, and the certificates it needs (05 NTR-05, CFG-18, SAR-15).

``SmtpEmailSender`` is witnessed against a real TLS peer without any network: ``authority``
creates a throwaway certificate authority and ``TlsSmtpSink`` serves one SMTP conversation at a time
on ``127.0.0.1`` with a certificate that authority signed. Nothing here is a fixture credential:
the keys are generated per test and written under the test's temporary directory only.
"""

from __future__ import annotations

import base64
import smtplib
import socket
import ssl
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

TIMEOUT_SECONDS = 10.0
# What ``smtplib`` raises when a relay does not offer STARTTLS; named here because tests import no
# network library themselves (DG-ARC-12).
SmtpNotSupported = smtplib.SMTPNotSupportedError


@dataclass(frozen=True, slots=True)
class Authority:
    """A certificate authority that exists for one test."""

    key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate
    ca_file: Path  # PEM of the authority certificate: what a client trusts

    def issue(self, host: str, directory: Path) -> tuple[Path, Path]:
        """A server certificate for ``host`` (subject alternative name) and its key, as PEM
        files under ``directory``."""
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
            .issuer_name(self.certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
            )
            .sign(self.key, hashes.SHA256())
        )
        directory.mkdir(parents=True, exist_ok=True)
        cert_file = directory / f"{host}.pem"
        key_file = directory / f"{host}.key"
        cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        return cert_file, key_file


def authority(directory: Path, name: str = "eRev test authority") -> Authority:
    """A new self-signed certificate authority whose certificate is written to ``directory``."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    directory.mkdir(parents=True, exist_ok=True)
    ca_file = directory / f"{name.replace(' ', '-')}.ca.pem"
    ca_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return Authority(key=key, certificate=certificate, ca_file=ca_file)


@dataclass(slots=True)
class Delivery:
    """One accepted message: the envelope and the DATA bytes as received."""

    mail_from: str
    recipients: list[str]
    data: bytes


@dataclass(slots=True)
class TlsSmtpSink:
    """An SMTP server on ``127.0.0.1`` for tests: EHLO, STARTTLS, AUTH PLAIN, MAIL, RCPT, DATA,
    QUIT. ``offer_starttls=False`` plays a relay without TLS. ``commands`` records every command
    line as ``(encrypted, line)``, so a test can show what travelled before and after the
    handshake; ``server_names`` records the SNI name of each handshake."""

    cert_file: Path
    key_file: Path
    offer_starttls: bool = True
    port: int = 0
    commands: list[tuple[bool, str]] = field(default_factory=list)
    deliveries: list[Delivery] = field(default_factory=list)
    credentials: list[tuple[bool, str, str]] = field(default_factory=list)
    server_names: list[str | None] = field(default_factory=list)
    handshake_errors: list[str] = field(default_factory=list)
    _listener: socket.socket | None = None
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def __enter__(self) -> TlsSmtpSink:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        listener.settimeout(0.2)
        self._listener = listener
        self.port = int(listener.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, name="smtp-sink", daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=TIMEOUT_SECONDS)
        if self._listener is not None:
            self._listener.close()

    def _serve(self) -> None:
        assert self._listener is not None
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(TIMEOUT_SECONDS)
                try:
                    self._converse(connection)
                except (OSError, ssl.SSLError) as error:
                    self.handshake_errors.append(type(error).__name__)

    def _tls_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.cert_file, self.key_file)

        def remember(sock: ssl.SSLObject, name: str | None, _context: ssl.SSLContext) -> None:
            self.server_names.append(name)

        context.sni_callback = remember
        return context

    def _converse(self, connection: socket.socket) -> None:
        stream: socket.socket = connection
        encrypted = False
        reader = stream.makefile("rb")

        def say(text: str) -> None:
            stream.sendall(text.encode("ascii") + b"\r\n")

        def capabilities() -> None:
            lines = ["sink.erev.test"]
            if self.offer_starttls and not encrypted:
                lines.append("STARTTLS")
            if encrypted:
                lines.append("AUTH PLAIN")
            lines.append("8BITMIME")
            for line in lines[:-1]:
                say(f"250-{line}")
            say(f"250 {lines[-1]}")

        say("220 sink.erev.test ESMTP")
        mail_from, recipients = "", []
        while True:
            raw = reader.readline()
            if not raw:
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            verb = line.split(" ", 1)[0].upper()
            self.commands.append(
                (encrypted, "AUTH PLAIN <credentials>" if verb == "AUTH" else line)
            )
            if verb in ("EHLO", "HELO"):
                capabilities()
            elif verb == "STARTTLS" and self.offer_starttls and not encrypted:
                say("220 2.0.0 Ready to start TLS")
                stream = self._tls_context().wrap_socket(connection, server_side=True)
                encrypted = True
                reader = stream.makefile("rb")
            elif verb == "AUTH":
                parts = line.split(" ")
                decoded = base64.b64decode(parts[2]).split(b"\0") if len(parts) == 3 else []
                if len(decoded) == 3:
                    self.credentials.append((encrypted, decoded[1].decode(), decoded[2].decode()))
                    say("235 2.7.0 Authentication successful")
                else:
                    say("501 5.5.2 Cannot decode the response")
            elif verb == "MAIL":
                mail_from, recipients = line.split(":", 1)[1].split(" ")[0].strip("<>"), []
                say("250 2.1.0 Ok")
            elif verb == "RCPT":
                recipients.append(line.split(":", 1)[1].strip().strip("<>"))
                say("250 2.1.5 Ok")
            elif verb == "DATA":
                say("354 End data with <CR><LF>.<CR><LF>")
                body = bytearray()
                while True:
                    chunk = reader.readline()
                    if not chunk or chunk == b".\r\n":
                        break
                    body += chunk[1:] if chunk.startswith(b"..") else chunk
                self.deliveries.append(Delivery(mail_from, list(recipients), bytes(body)))
                say("250 2.0.0 Ok: queued")
            elif verb == "RSET":
                say("250 2.0.0 Ok")
            elif verb == "QUIT":
                say("221 2.0.0 Bye")
                return
            else:
                say("502 5.5.2 Command not recognised")


def carry_connections_to(sink: TlsSmtpSink, monkeypatch: Any) -> list[Any]:
    """Every ``socket.create_connection`` of the test is recorded and carried to ``sink`` on
    loopback; returns the list of addresses that were asked for. It stands in for the route to a
    global address, which a test must not take (DG-TST-15), so that the address a production
    sender connects to can be observed while the TLS conversation stays real."""
    real_create_connection = socket.create_connection
    asked: list[Any] = []

    def to_the_sink(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        asked.append(address)
        return real_create_connection(("127.0.0.1", sink.port), *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", to_the_sink)
    return asked

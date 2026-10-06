"""SMTP email adapter (05 NTR-05, CFG-18, SAR-15; D-80): ``smtplib.SMTP`` with STARTTLS required
and the server certificate verified. ``EREV_SMTP_HOST`` passes the SAR-15 address rule before any
socket opens, and the connection goes to the checked address while the certificate is verified
against the host name. Tests send nothing through it (BUILD_SPEC PLF-14): only the refusal of a
destination is exercised (WEB-3b). Failures raise, and the outbox retry schedule applies
(DG-KRN-EVT-05).

Rev 1.53 (supervisor ruling R-39): the relay is the operator's configuration. With
``EREV_SMTP_PRIVATE_RELAY`` the address rule also admits a relay on a private-use or loopback
address, and ``EREV_SMTP_CA_FILE`` names the bundle its certificate is verified against in place
of the system trust store. Neither relaxes STARTTLS or the verification.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Final

from pydantic import SecretStr

from erev_api.adapters.email.render import mime_message
from erev_api.adapters.http.guard import Resolver, check_host, system_resolver
from erev_api.clock import Clock
from erev_api.config import Environment, Settings
from erev_api.events.outbox import EmailMessage

TIMEOUT_SECONDS: Final = 30.0


class _CheckedSMTP(smtplib.SMTP):
    """An SMTP client whose socket connects to the checked address, while ``_host``, which
    STARTTLS verifies the certificate against and sends as the server name, is the configured
    host name.

    ``smtplib.SMTP`` records ``_host`` in its constructor only, and only when it is given a host,
    which makes it connect at once; ``connect()`` never sets it. The client is built without a
    host so that the connection is opened by ``connect()`` through ``_get_socket``, and the host
    name is therefore set here (R-34 SD-7: left empty, STARTTLS raised ``check_hostname requires
    server_hostname`` and no mail was ever delivered).
    """

    def __init__(self, address: str, *, host: str, timeout: float) -> None:
        self._address = address
        super().__init__(timeout=timeout)
        self._host = host

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        # CPython's connection hook; no source address is configured.
        return socket.create_connection((self._address, port), timeout)


@dataclass(frozen=True, slots=True)
class SmtpEmailSender:
    host: str
    port: int
    username: str | None
    password: SecretStr | None
    sender: str
    clock: Clock
    env: Environment
    resolve: Resolver = system_resolver
    # 05 CFG-18 rev 1.53: the operator's opt-in for a relay on a private-use or loopback address,
    # and the PEM bundle the relay's certificate is verified against (None: the system store).
    private_relay: bool = False
    ca_file: Path | None = None

    @classmethod
    def from_settings(cls, settings: Settings, clock: Clock) -> SmtpEmailSender:
        if settings.smtp_host is None or settings.smtp_from is None:
            raise ValueError(
                "EREV_SMTP_HOST and EREV_SMTP_FROM are required when EREV_EMAIL_BACKEND is smtp"
            )
        return cls(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            sender=settings.smtp_from,
            clock=clock,
            env=settings.env,
            private_relay=settings.smtp_private_relay,
            ca_file=settings.smtp_ca_file,
        )

    def send(self, message: EmailMessage) -> str:
        """Send over STARTTLS; returns the Message-ID. A refused host raises
        ``DestinationRefused`` before connecting."""
        address = check_host(
            self.host, self.port, env=self.env, resolve=self.resolve, private=self.private_relay
        )
        mime = mime_message(message, sender=self.sender, at=self.clock.now().astimezone(UTC))
        context = ssl.create_default_context(
            cafile=None if self.ca_file is None else str(self.ca_file)
        )
        with _CheckedSMTP(address, host=self.host, timeout=TIMEOUT_SECONDS) as client:
            client.connect(self.host, self.port)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
            if self.username is not None and self.password is not None:
                client.login(self.username, self.password.get_secret_value())
            client.send_message(mime)
        return str(mime["Message-ID"])

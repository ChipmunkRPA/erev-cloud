"""SAR-15 outbound destination guard (05 SAR-15, SAR-42; BUILD_SPEC SOP-8;
``adapters/http/guard.py``). CPU only: the resolver is injected, nothing is connected."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Sequence
from ipaddress import ip_address
from pathlib import Path

import pytest
from erev_api.adapters.http.guard import (
    ADDRESS_REFUSED,
    CREDENTIALS_REFUSED,
    SCHEME_REFUSED,
    UNRESOLVED,
    Destination,
    DestinationRefused,
    check_destination,
    check_host,
)
from erev_api.config import Environment

BLOCKED = (
    "127.0.0.1",  # loopback
    "10.0.0.1",  # private
    "172.16.0.1",  # private
    "192.168.1.1",  # private
    "169.254.169.254",  # link-local, the metadata address
    "100.64.0.1",  # CGNAT
    "::1",  # IPv6 loopback
    "fe80::1",  # IPv6 link-local
    "::ffff:10.0.0.1",  # IPv4-mapped private
    "64:ff9b::7f00:1",  # NAT64 loopback
    "fc00::1",  # IPv6 unique local
    "0.0.0.0",  # unspecified
    "224.0.0.1",  # multicast
)
PUBLIC = "93.184.216.34"
URL = "https://hooks.example.test/erev"


def resolver(*addresses: str) -> object:
    def resolve(host: str, port: int) -> Sequence[str]:
        return addresses

    return resolve


@pytest.mark.parametrize("address", BLOCKED)
def test_sar_15_blocked_ranges(address: str) -> None:
    """Under ``EREV_ENV=production`` the guard refuses every address of the SAR-15 ranges, whether
    the host resolves to it or names it literally, and its message never repeats the address."""
    with pytest.raises(DestinationRefused) as resolved:
        check_destination(URL, env=Environment.PRODUCTION, resolve=resolver(address))
    assert str(resolved.value) == ADDRESS_REFUSED and address not in str(resolved.value)
    literal = URL.replace("hooks.example.test", f"[{address}]" if ":" in address else address)
    with pytest.raises(DestinationRefused):
        check_destination(literal, env=Environment.PRODUCTION)
    # One refused address among several refuses the whole host (no first-address escape).
    with pytest.raises(DestinationRefused):
        check_host(
            "hooks.example.test", 443, env=Environment.PRODUCTION, resolve=resolver(PUBLIC, address)
        )


def test_sar_15_scheme_credentials_and_resolution() -> None:
    with pytest.raises(DestinationRefused) as plain:
        check_destination(
            URL.replace("https", "http"), env=Environment.PRODUCTION, resolve=resolver(PUBLIC)
        )
    assert str(plain.value) == SCHEME_REFUSED
    with pytest.raises(DestinationRefused) as creds:
        check_destination(
            "https://user:pw@hooks.example.test/x",
            env=Environment.PRODUCTION,
            resolve=resolver(PUBLIC),
        )
    assert str(creds.value) == CREDENTIALS_REFUSED
    with pytest.raises(DestinationRefused) as unresolved:
        check_destination(URL, env=Environment.PRODUCTION, resolve=resolver())
    assert str(unresolved.value) == UNRESOLVED


def test_sar_15_connects_to_the_resolved_address() -> None:
    """The caller connects to the address that was checked, with SNI and Host from the URL."""
    destination = check_destination(
        "https://hooks.example.test:8443/x", env=Environment.PRODUCTION, resolve=resolver(PUBLIC)
    )
    assert destination == Destination(
        scheme="https", host="hooks.example.test", netloc="hooks.example.test:8443", address=PUBLIC
    )
    assert (
        check_host("hooks.example.test", 443, env=Environment.PRODUCTION, resolve=resolver(PUBLIC))
        == PUBLIC
    )


def test_sar_15_local_environments_allow_loopback_and_http_only() -> None:
    """DG-ENV-10: dev, test and e2e reach the in-process mocks on loopback over http; private and
    link-local ranges stay refused even there."""
    for env in (Environment.DEV, Environment.TEST, Environment.E2E):
        local = check_destination("http://127.0.0.1:8190/mock", env=env)
        assert local.address == "127.0.0.1" and local.scheme == "http"
        with pytest.raises(DestinationRefused):
            check_destination("http://10.0.0.1/", env=env)
        with pytest.raises(DestinationRefused):
            check_destination("http://169.254.169.254/", env=env)
    with pytest.raises(DestinationRefused):
        check_destination("http://127.0.0.1:8190/mock", env=Environment.PRODUCTION)


# 05 SAR-15 rev 1.53 (supervisor ruling R-39): what the operator's SMTP opt-in admits, and what it
# never does.
PRIVATE_RELAY_ADMITTED = (
    "127.0.0.1",
    "127.8.9.10",  # the whole loopback range
    "::1",
    "10.0.0.5",
    "172.16.0.1",
    "172.31.255.254",
    "192.168.65.254",
    "fd12:3456:789a::1",  # IPv6 unique local
    "fc00::1",
    "::ffff:10.0.0.1",  # judged by its embedded IPv4 address
)
PRIVATE_RELAY_REFUSED = (
    "169.254.169.254",  # link-local: the metadata address
    "169.254.0.1",
    "fe80::1",
    "fec0::1",  # IPv6 site-local, outside fc00::/7
    "100.64.0.1",  # CGNAT
    "0.0.0.0",
    "::",
    "224.0.0.1",
    "ff02::1",
    "240.0.0.1",  # reserved
    "192.0.2.1",  # documentation range
    "::ffff:169.254.169.254",
    "64:ff9b::a9fe:a9fe",  # NAT64 of the metadata address
)


@pytest.mark.parametrize("address", PRIVATE_RELAY_ADMITTED)
def test_sar_15_private_relay_opt_in_admits_loopback_and_private_use(address: str) -> None:
    """``check_host(..., private=True)`` — the SMTP relay under the operator's opt-in — admits a
    loopback or private-use address, literal or resolved, and returns it as the address to connect
    to; the same address stays refused without the opt-in."""
    # Literal hosts are normalized; DNS results retain the checked resolver spelling.
    expected = str(ip_address(address))
    assert check_host(address, 587, env=Environment.PRODUCTION, private=True) == expected
    resolved = check_host(
        "relay.internal.test",
        587,
        env=Environment.PRODUCTION,
        resolve=resolver(address),
        private=True,
    )
    assert resolved == address
    with pytest.raises(DestinationRefused):
        check_host(
            "relay.internal.test", 587, env=Environment.PRODUCTION, resolve=resolver(address)
        )
    with pytest.raises(DestinationRefused):
        check_host(address, 587, env=Environment.PRODUCTION)


@pytest.mark.parametrize("address", PRIVATE_RELAY_REFUSED)
def test_sar_15_private_relay_opt_in_refuses_everything_else(address: str) -> None:
    """Link-local addresses with the metadata address, CGNAT, multicast, reserved and unspecified
    addresses are refused whatever the opt-in, alone or beside an admitted address."""
    with pytest.raises(DestinationRefused) as refused:
        check_host(address, 587, env=Environment.PRODUCTION, private=True)
    assert str(refused.value) == ADDRESS_REFUSED
    with pytest.raises(DestinationRefused):
        check_host(
            "relay.internal.test",
            587,
            env=Environment.PRODUCTION,
            resolve=resolver("10.0.0.5", address),
            private=True,
        )


def test_sar_15_the_opt_in_exists_for_the_smtp_relay_alone() -> None:
    """Tenant-supplied destinations cannot take the opt-in: ``check_destination`` has no such
    parameter, and the one call in the product that passes ``private`` is the SMTP sender's."""
    assert list(inspect.signature(check_destination).parameters) == ["url", "env", "resolve"]
    assert inspect.signature(check_host).parameters["private"].default is False
    package = Path(__file__).resolve().parents[2] / "erev_api"
    callers = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if any(
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) == "check_host"
            and any(keyword.arg == "private" for keyword in node.keywords)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    )
    assert callers == ["adapters/email/smtp.py"]
    # A public relay is unaffected by the opt-in.
    assert check_host(PUBLIC, 587, env=Environment.PRODUCTION, private=True) == PUBLIC

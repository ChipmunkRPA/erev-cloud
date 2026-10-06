"""Outbound destination guard (05 SAR-15, THR-15, NTR-13; 01-DECISIONS D-80; BUILD_SPEC PLF-24,
WEB-3b).

``check_destination`` accepts an https URL whose host resolves only to global unicast addresses and
returns the first resolved address, so the caller connects to the address it checked, with SNI and
the ``Host`` header set to the host (DNS rebinding between check and connect is thereby excluded).
``check_host`` applies the same address rule to a host and port without a URL (SMTP).

An address is refused unless it is global unicast: ``is_global`` false (loopback, private,
link-local including the metadata address 169.254.169.254, CGNAT, benchmarking, IETF protocol
assignments), multicast, reserved, unspecified or IPv6 site-local. NAT64 (``64:ff9b::/96``), 6to4
(``2002::/16``), IPv4-mapped and IPv4-compatible addresses are judged by their embedded IPv4
address. When ``EREV_ENV`` is ``dev``, ``test`` or ``e2e`` loopback addresses and plain ``http``
are allowed, so that adapters reach the in-process mock routers.

``check_host(..., private=True)`` is the operator's opt-in for the SMTP relay alone (05 SAR-15
rev 1.53, CFG-18 ``EREV_SMTP_PRIVATE_RELAY``; supervisor ruling R-39): loopback and the
private-use networks are then admitted as well. ``check_destination`` takes no such argument:
adapter base URLs, webhook endpoints and OIDC issuers are tenant data.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from erev_api.config import LOCAL_ENVIRONMENTS, Environment

type Address = ipaddress.IPv4Address | ipaddress.IPv6Address
type Resolver = Callable[[str, int], Sequence[str]]

NAT64: Final = ipaddress.ip_network("64:ff9b::/96")
IPV4_COMPATIBLE: Final = ipaddress.ip_network("::/96")
# 05 SAR-15 rev 1.53: what ``private=True`` admits beside loopback — the RFC 1918 networks and
# the IPv6 unique local range. Link-local addresses (the metadata address among them), CGNAT,
# multicast, reserved and unspecified addresses are refused whatever the opt-in.
PRIVATE_USE: Final = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
DEFAULT_PORTS: Final = {"https": 443, "http": 80}
NO_HOST: Final = "The destination URL has no host."
SCHEME_REFUSED: Final = "The destination must use https."
CREDENTIALS_REFUSED: Final = "The destination URL must not carry credentials."
PORT_INVALID: Final = "The destination URL has an invalid port."
UNRESOLVED: Final = "The destination host does not resolve."
ADDRESS_REFUSED: Final = (
    "The destination resolves to a loopback, private, link-local, shared, multicast or reserved"
    " address."
)


class DestinationRefused(ValueError):
    """The destination breaks SAR-15; the message names the rule, never the address."""


@dataclass(frozen=True, slots=True)
class Destination:
    scheme: str
    host: str  # the URL host, for SNI
    netloc: str  # host and optional port, for the Host header
    address: str  # the checked address to connect to


def system_resolver(host: str, port: int) -> list[str]:
    """The host's addresses from the operating system resolver, in resolver order."""
    addresses: list[str] = []
    for *_, sockaddr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        address = str(sockaddr[0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def _literal(host: str) -> Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _judged(address: Address) -> Address:
    """The address the rule judges: an IPv6 address that embeds an IPv4 address is judged by it."""
    if not isinstance(address, ipaddress.IPv6Address):
        return address
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    # ``::`` and ``::1`` sit in ::/96 but are the IPv6 unspecified and loopback addresses.
    if address in NAT64 or (address in IPV4_COMPATIBLE and int(address) > 1):
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return address


def _refused(address: Address, *, local: bool, private: bool = False) -> bool:
    judged = _judged(address)
    if local and judged.is_loopback:
        return False
    if private and (judged.is_loopback or any(judged in network for network in PRIVATE_USE)):
        return False
    return (
        not judged.is_global
        or judged.is_multicast
        or judged.is_reserved
        or judged.is_unspecified
        or (isinstance(judged, ipaddress.IPv6Address) and judged.is_site_local)
    )


def check_host(
    host: str,
    port: int,
    *,
    env: Environment,
    resolve: Resolver = system_resolver,
    private: bool = False,
) -> str:
    """The first checked address of ``host``, or ``DestinationRefused`` when the host does not
    resolve or any address it resolves to is refused (SAR-15). ``private`` also admits loopback
    and private-use addresses: the SMTP relay under the operator's opt-in, nothing else."""
    local = env in LOCAL_ENVIRONMENTS
    literal = _literal(host)
    if literal is not None:
        addresses: Sequence[str] = [str(literal)]
    else:
        try:
            addresses = resolve(host, port)
        except OSError as error:
            raise DestinationRefused(UNRESOLVED) from error
    if not addresses:
        raise DestinationRefused(UNRESOLVED)
    for address in addresses:
        parsed = _literal(address)
        if parsed is None or _refused(parsed, local=local, private=private):
            raise DestinationRefused(ADDRESS_REFUSED)
    return addresses[0]


def check_destination(
    url: str, *, env: Environment, resolve: Resolver = system_resolver
) -> Destination:
    """The checked destination of ``url``, or ``DestinationRefused`` (SAR-15)."""
    local = env in LOCAL_ENVIRONMENTS
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme != "https" and not (local and scheme == "http"):
        raise DestinationRefused(SCHEME_REFUSED)
    host = parts.hostname
    if not host:
        raise DestinationRefused(NO_HOST)
    if parts.username is not None or parts.password is not None:
        raise DestinationRefused(CREDENTIALS_REFUSED)
    try:
        port = parts.port or DEFAULT_PORTS[scheme]
    except ValueError as error:
        raise DestinationRefused(PORT_INVALID) from error
    address = check_host(host, port, env=env, resolve=resolve)
    return Destination(scheme=scheme, host=host, netloc=parts.netloc, address=address)

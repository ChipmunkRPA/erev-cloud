"""Socket guard: tests reach only loopback and Unix sockets (docs/dev-guide.md DG-TST-15)."""

from __future__ import annotations

import socket
from typing import Any, Final

import pytest

LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1"})


class NetworkBlocked(RuntimeError):
    """A test tried to open a connection to a non-loopback address (REQ-SEC-008)."""


def _require_loopback(family: int, address: Any) -> None:
    if family == getattr(socket, "AF_UNIX", object()):
        return
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host not in LOOPBACK_HOSTS:
        raise NetworkBlocked(f"network access is blocked in tests (host {host})")


def unused_loopback_port() -> int:
    """A loopback TCP port nothing listens on, so a connection to it is refused."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def record_connections(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The address of every connection attempt, recorded before the installed guard judges it."""
    attempts: list[Any] = []
    guarded_connect = socket.socket.connect
    guarded_create_connection = socket.create_connection

    def connect(self: socket.socket, address: Any) -> None:
        attempts.append(address)
        guarded_connect(self, address)

    def create_connection(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
        attempts.append(address)
        return guarded_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    return attempts


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create_connection = socket.create_connection

    def connect(self: socket.socket, address: Any) -> None:
        _require_loopback(self.family, address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        _require_loopback(self.family, address)
        return real_connect_ex(self, address)

    def create_connection(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
        # Checked before name resolution, so a blocked host never reaches DNS.
        _require_loopback(socket.AF_INET, address)
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)

"""No-network guard (docs/dev-guide.md DG-TST-15; REQ-SEC-008; BUILD_SPEC FND-2)."""

from __future__ import annotations

import socket

import pytest
from support.markers import FIRST_AREAS, area_of, collection_rank
from support.network import NetworkBlocked


def _unused_loopback_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def test_dg_tst_15_non_loopback_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("192.0.2.1", 80), timeout=1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw:
        with pytest.raises(NetworkBlocked):
            raw.connect(("192.0.2.1", 80))
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", _unused_loopback_port()), timeout=1)


def test_collection_orders_engine_and_architecture_first(request: pytest.FixtureRequest) -> None:
    ranks = [collection_rank(item.path) for item in request.session.items]
    assert ranks == sorted(ranks)
    assert area_of(request.path) == "unit"
    assert FIRST_AREAS == ("engine", "architecture")

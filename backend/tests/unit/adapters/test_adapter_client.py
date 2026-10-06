"""The inbound adapters' outbound HTTP client (05 SAR-15, ADP-12, ADP-20; DG-ARC-12, DG-LAY-03;
BUILD_SPEC DIN-12): the factory refuses a ``base_url`` the guard refuses as ``ports.Permanent``
(never retried), the transport pins every request to the checked address with the name in ``Host``
(and SNI under https), and the local environments admit loopback and plain http for the in-process
mocks while production does not. No socket: the network transport is a recording mock transport
from ``support.http``.
"""

from __future__ import annotations

from typing import Any

import pytest
from erev_api.adapters.http import adapter_client
from erev_api.config import Environment
from erev_api.domain.integrations import ports
from support.http import json_transport


def _resolver(*addresses: str) -> Any:
    def resolve(host: str, port: int) -> list[str]:
        return list(addresses)

    return resolve


def test_factory_refuses_a_base_url_the_guard_refuses_as_permanent() -> None:
    build = adapter_client.client_factory(
        Environment.PRODUCTION, transport=json_transport(lambda r: {})
    )
    with pytest.raises(ports.Permanent, match="base_url refused"):
        build("http://127.0.0.1:5270/api/v1/__mocks__/salesforce")  # plain http, loopback
    with pytest.raises(ports.Permanent, match="base_url refused"):
        build("https://user:pw@crm.example.test/")  # credentials in the URL


def test_local_environments_admit_loopback_http_and_pin_the_host() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def respond(request: Any) -> dict[str, Any]:
        seen.append(
            (str(request.url.host), request.headers["Host"], request.extensions.get("sni_hostname"))
        )
        return {"events": [], "latestReplayId": 0}

    build = adapter_client.client_factory(Environment.TEST, transport=json_transport(respond))
    with build("http://127.0.0.1:5270/api/v1/__mocks__/salesforce") as client:
        response = client.get("http://127.0.0.1:5270/api/v1/__mocks__/salesforce/events?replayId=0")
    assert response.status_code == 200 and response.json() == {"events": [], "latestReplayId": 0}
    assert seen == [("127.0.0.1", "127.0.0.1:5270", None)]  # no SNI under http


def test_https_requests_connect_to_the_resolved_address_with_name_in_host_and_sni() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def respond(request: Any) -> dict[str, Any]:
        seen.append(
            (str(request.url.host), request.headers["Host"], request.extensions.get("sni_hostname"))
        )
        return {}

    build = adapter_client.client_factory(
        Environment.PRODUCTION,
        transport=json_transport(respond),
        resolve=_resolver("93.184.216.34"),
    )
    with build("https://crm.example.test") as client:
        client.get("https://crm.example.test/services/data/v60.0/sobjects/Order/1")
    assert seen == [("93.184.216.34", "crm.example.test", "crm.example.test")]


def test_a_request_to_a_refused_address_is_permanent_inside_the_transport() -> None:
    build = adapter_client.client_factory(
        Environment.PRODUCTION,
        transport=json_transport(lambda r: {}),
        resolve=_resolver("93.184.216.34"),
    )
    client = build("https://crm.example.test")
    with pytest.raises(ports.Permanent):
        client.get("https://169.254.169.254/latest/meta-data/")  # the metadata address (SAR-15)
    client.close()


def test_client_defaults_no_redirects_no_environment_and_a_bounded_timeout() -> None:
    build = adapter_client.client_factory(Environment.TEST, transport=json_transport(lambda r: {}))
    with build("http://127.0.0.1:1/") as client:
        assert client.follow_redirects is False
        assert client.trust_env is False
        assert client.timeout.read == adapter_client.REQUEST_TIMEOUT_SECONDS

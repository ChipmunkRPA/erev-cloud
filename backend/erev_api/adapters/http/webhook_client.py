"""Webhook HTTP client (05 NTR-12, NTR-13, SAR-15; BUILD_SPEC PLF-24).

``WebhookClient.post`` checks the destination through the SAR-15 guard, then POSTs the body to the
checked address with the ``Host`` header and SNI set to the URL host, a 10-second timeout, no
redirects and no proxies from the environment. Tests pass an ``httpx.MockTransport`` and a resolver,
so no request leaves the process.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import httpx

from erev_api.adapters.http.guard import (
    DestinationRefused,
    Resolver,
    check_destination,
    system_resolver,
)
from erev_api.config import Environment
from erev_api.events.webhooks import WebhookDeliveryError

REQUEST_TIMEOUT_SECONDS: Final = 10.0


class WebhookClient:
    """The ``WebhookSender`` of the worker (DG-KRN-EVT-07)."""

    def __init__(
        self,
        *,
        env: Environment,
        transport: httpx.BaseTransport | None = None,
        resolve: Resolver = system_resolver,
    ) -> None:
        self._env = env
        self._transport = transport
        self._resolve = resolve

    def post(self, url: str, *, body: bytes, headers: Mapping[str, str]) -> int:
        try:
            destination = check_destination(url, env=self._env, resolve=self._resolve)
        except DestinationRefused as refused:
            raise WebhookDeliveryError(str(refused)) from refused
        target = httpx.URL(url).copy_with(host=destination.address)
        extensions = {"sni_hostname": destination.host} if destination.scheme == "https" else {}
        with httpx.Client(
            transport=self._transport,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.post(
                target,
                content=body,
                headers={**headers, "Host": destination.netloc},
                extensions=extensions,
            )
        return response.status_code

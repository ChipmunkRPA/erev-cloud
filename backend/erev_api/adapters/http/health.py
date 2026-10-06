"""Container health probe (05 DPL-01 HEALTHCHECK; BUILD_SPEC DEP-1).

``probe_status`` GETs a URL of the container itself and returns the HTTP status. It ignores proxy
variables, follows no destination guard (the address is the image's own loopback listener, never a
tenant destination) and raises ``HealthProbeFailed`` when no answer arrives. It lives under
``adapters/`` because DG-ARC-12 confines ``urllib.request`` to adapters.
"""

from __future__ import annotations

from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

HTTP_SCHEMES: Final = frozenset({"http", "https"})


class HealthProbeFailed(Exception):
    """No HTTP answer: the connection was refused, timed out or failed."""


def is_http_url(url: str) -> bool:
    return urlsplit(url).scheme in HTTP_SCHEMES


def probe_status(url: str, *, timeout_seconds: float) -> int:
    """The HTTP status that a GET of ``url`` answers within ``timeout_seconds``."""
    if not is_http_url(url):
        raise ValueError(f"not an http or https URL: {url}")
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout_seconds) as response:
            return int(response.status)
    except HTTPError as error:
        return int(error.code)
    except (URLError, OSError) as error:
        raise HealthProbeFailed(str(error)) from error

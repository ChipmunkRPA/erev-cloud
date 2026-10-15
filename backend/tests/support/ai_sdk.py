"""Synthetic HTTP objects for AI SDK exception tests; never opens a connection."""

import httpx2


def request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=request())

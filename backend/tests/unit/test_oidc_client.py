"""OIDC relying-party helpers without a provider (05 SAR-15, SAR-27, KEY-09; BUILD_SPEC PLF-27,
WEB-3b)."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from erev_api.adapters.http.guard import DestinationRefused
from erev_api.adapters.idp.oidc_http import HttpxOidcHttp
from erev_api.auth import oidc
from erev_api.config import Environment
from joserfc import jwt
from joserfc.jwk import KeySet, OctKey, RSAKey
from support.http import HttpRequest, json_transport

PROVIDER = oidc.Provider(
    id=uuid4(),
    code="corp-idp",
    display_name="Corp IdP",
    issuer_url="https://idp.corp.test",
    client_id="erev",
    client_secret_ref=None,
    scopes=oidc.DEFAULT_SCOPES,
)
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


class Secrets:
    def secret(self, ref: str) -> str:
        return f"value-of-{ref}"


def test_token_form_sends_verifier_and_referenced_secret() -> None:
    form = oidc.token_form(
        PROVIDER,
        code="c-1",
        verifier="v-1",
        public_origin="https://erev.corp.test",
        secrets=Secrets(),
    )
    assert form == {
        "grant_type": "authorization_code",
        "code": "c-1",
        "redirect_uri": "https://erev.corp.test/api/v1/session/oidc/corp-idp/callback",
        "client_id": "erev",
        "code_verifier": "v-1",
    }
    confidential = replace(PROVIDER, client_secret_ref="idp-corp-client")
    assert (
        oidc.token_form(
            confidential,
            code="c-1",
            verifier="v-1",
            public_origin="https://erev.corp.test",
            secrets=Secrets(),
        )["client_secret"]
        == "value-of-idp-corp-client"
    )


RESOLVED = {
    "idp.example": "93.184.216.34",
    "internal.example": "10.0.0.5",
    "meta.example": "169.254.169.254",
}
DISCOVERY = {"issuer": "https://idp.example"}


def resolve(host: str, port: int) -> list[str]:
    return [RESOLVED[host]]


def test_sar_15_provider_urls_guarded() -> None:
    """PR-A-04 (D-80): provider requests pass the SAR-15 guard and go to the checked address."""
    sent: list[HttpRequest] = []

    def respond(request: HttpRequest) -> dict[str, str]:
        sent.append(request)
        return DISCOVERY

    client = HttpxOidcHttp(
        env=Environment.PRODUCTION, transport=json_transport(respond), resolve=resolve
    )
    assert client.get_json("https://idp.example/.well-known/openid-configuration") == DISCOVERY
    [request] = sent
    assert (request.url.scheme, request.url.host, request.url.path) == (
        "https",
        "93.184.216.34",
        "/.well-known/openid-configuration",
    )
    assert (request.headers["Host"], request.extensions["sni_hostname"]) == (
        "idp.example",
        "idp.example",
    )

    for refused in ("https://internal.example/token", "https://meta.example/jwks"):
        with pytest.raises(DestinationRefused) as excinfo:
            client.get_json(refused)
        assert isinstance(excinfo.value, oidc.OidcHttpError)
    with pytest.raises(DestinationRefused):
        client.post_form("https://internal.example/token", {"code": "c-1"})
    with pytest.raises(DestinationRefused, match="https"):
        client.get_json("http://idp.example/x")
    assert len(sent) == 1

    local = HttpxOidcHttp(env=Environment.TEST, transport=json_transport(respond), resolve=resolve)
    mock = "http://127.0.0.1:8190/api/v1/__mocks__/oidc/.well-known/openid-configuration"
    assert local.get_json(mock) == DISCOVERY
    assert (sent[-1].url.host, sent[-1].url.port, sent[-1].headers["Host"]) == (
        "127.0.0.1",
        8190,
        "127.0.0.1:8190",
    )
    assert "sni_hostname" not in sent[-1].extensions


def test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce() -> None:
    key = RSAKey.generate_key(2048, parameters={"kid": "k1"}, private=True)
    jwks = {"keys": [key.as_dict(private=False)]}
    now = int(NOW.timestamp())
    good = {
        "iss": PROVIDER.issuer_url,
        "aud": "erev",
        "sub": "s-1",
        "exp": now + 300,
        "nonce": "n-1",
    }

    def claims(payload: dict[str, object], signer: RSAKey = key, alg: str = "RS256") -> object:
        token = jwt.encode({"alg": alg, "kid": "k1"}, payload, signer)
        return oidc.validated_claims(token, provider=PROVIDER, jwks=jwks, nonce="n-1", now=NOW)

    assert claims(good) == good
    assert claims({**good, "iss": "https://other.test"}) is None
    assert claims({**good, "aud": "someone-else"}) is None
    assert claims({**good, "exp": now - 120}) is None
    assert claims({**good, "nonce": "n-2"}) is None
    impostor = RSAKey.generate_key(2048, parameters={"kid": "k1"}, private=True)
    assert claims(good, signer=impostor) is None
    assert oidc.validated_claims(None, provider=PROVIDER, jwks=jwks, nonce="n-1", now=NOW) is None
    assert KeySet.import_key_set(jwks).keys[0].kid == "k1"


def _rs256_fixture() -> tuple[RSAKey, dict[str, object], dict[str, object], int]:
    key = RSAKey.generate_key(2048, parameters={"kid": "k1"}, private=True)
    jwks: dict[str, object] = {"keys": [key.as_dict(private=False)]}
    now = int(NOW.timestamp())
    good: dict[str, object] = {
        "iss": PROVIDER.issuer_url,
        "aud": "erev",
        "sub": "s-1",
        "exp": now + 300,
        "nonce": "n-1",
    }
    return key, jwks, good, now


def test_validated_claims_rejects_future_nbf_and_iat_within_leeway() -> None:
    """ASVS V9.2.1 from the relying party's side (Codex production-20260922-0133 §6): the admissible
    time window is ``exp`` AND ``nbf`` AND ``iat`` under ``CLOCK_LEEWAY_SECONDS`` — a not-before or
    an issued-at more than the leeway in the future is refused; a not-before inside the leeway or in
    the past is admitted with the claims intact."""
    key, jwks, good, now = _rs256_fixture()

    def claims(payload: dict[str, object]) -> object:
        token = jwt.encode({"alg": "RS256", "kid": "k1"}, payload, key)
        return oidc.validated_claims(token, provider=PROVIDER, jwks=jwks, nonce="n-1", now=NOW)

    assert claims(good) == good
    assert claims({**good, "nbf": now + 3600}) is None, "a future not-before is refused"
    assert claims({**good, "iat": now + 3600}) is None, "a future issued-at is refused"
    within = {**good, "nbf": now + oidc.CLOCK_LEEWAY_SECONDS - 30}
    assert claims(within) == within, "a not-before inside the leeway is admitted"
    past = {**good, "nbf": now - 10, "iat": now - 10}
    assert claims(past) == past


def test_validated_claims_refuses_non_rs256_tokens() -> None:
    """ASVS V9.1.2 from the relying party's side (Codex production-20260922-0133 §6; supervisor's
    conditions): the verification allowlist ``ID_TOKEN_ALGORITHMS == ("RS256",)`` refuses BOTH an
    HS256-signed token and a hand-built unsigned ``alg: none`` compact token (raw base64url header
    and payload with an EMPTY signature — joserfc will not encode one), while the RS256 token of
    the same claims is admitted (control)."""
    key, jwks, good, _now = _rs256_fixture()
    assert oidc.ID_TOKEN_ALGORITHMS == ("RS256",)

    def verify(token: object) -> object:
        return oidc.validated_claims(token, provider=PROVIDER, jwks=jwks, nonce="n-1", now=NOW)

    secret = OctKey.import_key("a-shared-secret-of-at-least-thirty-two-bytes!")
    hs256 = jwt.encode({"alg": "HS256", "kid": "k1"}, good, secret)
    assert verify(hs256) is None, "an HS256-signed token is refused"

    def segment(obj: dict[str, object]) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    unsigned = f"{segment({'alg': 'none', 'kid': 'k1'})}.{segment(good)}."
    assert unsigned.endswith(".") and unsigned.count(".") == 2, "compact form, empty signature"
    assert verify(unsigned) is None, "an unsigned alg:none token is refused"
    assert verify(jwt.encode({"alg": "RS256", "kid": "k1"}, good, key)) == good

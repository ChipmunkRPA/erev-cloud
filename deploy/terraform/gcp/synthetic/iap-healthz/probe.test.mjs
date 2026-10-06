// Offline unit tests for the strict-IAP health probe core (lane P3c). Run with `node --test` (the
// pytest module backend/tests/unit/deploy/test_terraform_policy.py invokes this file). Every network
// call is a recorded fake; no Google SDK, no credentials, no network.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const probe = require('./probe.js');

const TARGET = 'https://erev.example.com/api/v1/healthz';
const SIGNER = 'erev-iap-probe@placeholder-project.iam.gserviceaccount.com';
const ACCESS_TOKEN = 'ya29.placeholder-access-token-value';
const FAKE_JWT = 'eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJodHRwczovL2VyZXYiLCJpc3MiOiJwcm9iZSJ9.c2lnbmF0dXJlLXBsYWNlaG9sZGVy';
const ENV = {
  EREV_PROBE_TARGET_URL: TARGET,
  EREV_PROBE_SIGNER_EMAIL: SIGNER,
  EREV_PROBE_JWT_TTL_SECONDS: '300',
  EREV_PROBE_TIMEOUT_MS: '5000',
};
const T0_MS = 1_800_000_000_000;

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

// A fake fetch that answers the metadata server, IAM Credentials signJwt and the target, records
// every call, and lets a test replace the target answer (a Response or a thrown error).
function fakeFetch({ target, signJwt } = {}) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url) === probe.METADATA_TOKEN_URL) {
      return jsonResponse({ access_token: ACCESS_TOKEN, expires_in: 3599, token_type: 'Bearer' });
    }
    if (String(url).startsWith(probe.IAM_CREDENTIALS_BASE)) {
      if (signJwt) {
        return signJwt(url, options);
      }
      return jsonResponse({ keyId: 'placeholder-key-id', signedJwt: FAKE_JWT });
    }
    if (String(url) === TARGET) {
      if (typeof target === 'function') {
        return target(url, options);
      }
      return target ?? jsonResponse({ status: 'ok' });
    }
    throw new Error(`unexpected url ${url}`);
  };
  return { fetch, calls };
}

function clock(...secondsSequence) {
  // Returns epoch milliseconds; each call advances through the sequence and holds the last value.
  let index = 0;
  return () => {
    const seconds = secondsSequence[Math.min(index, secondsSequence.length - 1)];
    index += 1;
    return T0_MS + seconds * 1000;
  };
}

function targetCall(calls) {
  const found = calls.filter((call) => call.url === TARGET);
  assert.equal(found.length, 1, 'exactly one request to the target');
  return found[0];
}

function signedClaims(calls) {
  const call = calls.find((c) => c.url.startsWith(probe.IAM_CREDENTIALS_BASE));
  assert.ok(call, 'signJwt was called');
  const body = JSON.parse(call.options.body);
  return { claims: JSON.parse(body.payload), call };
}

test('healthy: signed JWT for the exact audience, redirects disabled, TLS verification untouched, 200 status ok', async () => {
  const { fetch, calls } = fakeFetch();
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, true);
  assert.equal(result.class, 'healthy');
  assert.equal(result.status, 200);

  const { claims, call } = signedClaims(calls);
  assert.equal(claims.aud, TARGET, 'audience is exactly the target URL');
  assert.equal(claims.iss, SIGNER);
  assert.equal(claims.sub, SIGNER);
  assert.equal(claims.exp - claims.iat, 300);
  assert.ok(claims.exp - claims.iat <= probe.MAX_JWT_TTL_SECONDS);
  assert.equal(call.url, `${probe.IAM_CREDENTIALS_BASE}${encodeURIComponent(SIGNER)}:signJwt`);
  assert.equal(call.options.headers.Authorization, `Bearer ${ACCESS_TOKEN}`);

  const request = targetCall(calls);
  assert.equal(request.options.redirect, 'manual', 'redirects are never followed');
  assert.equal(request.options.headers.Authorization, `Bearer ${FAKE_JWT}`);
  assert.equal(request.options.method, 'GET');
  assert.ok(request.options.signal instanceof AbortSignal, 'bounded timeout');
  assert.equal('rejectUnauthorized' in request.options, false, 'TLS verification is the default');
  assert.equal(request.options.dispatcher, undefined, 'no custom TLS agent');
  assert.equal(process.env.NODE_TLS_REJECT_UNAUTHORIZED, undefined);
});

test('expired JWT: IAP 401 is an auth failure that names expiry, never a success', async () => {
  const { fetch, calls } = fakeFetch({ target: jsonResponse({ error: 'unauthorized' }, 401) });
  // Signed at t=0 with a 300 s ttl; the response is classified at t=400 (past exp).
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 400, 401) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'auth');
  assert.equal(result.status, 401);
  assert.match(result.message, /expired/);
  targetCall(calls);
});

test('rejected JWT (wrong audience, signature or ungranted signer): 403 is an auth failure', async () => {
  const { fetch } = fakeFetch({ target: new Response('', { status: 403 }) });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'auth');
  assert.match(result.message, /rejected/);
});

test('302 to the sign-in page is a failure, never a success, and is not followed', async () => {
  const { fetch, calls } = fakeFetch({
    target: new Response('', {
      status: 302,
      headers: { location: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=x&redirect_uri=y' },
    }),
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'iap-challenge');
  assert.equal(result.status, 302);
  assert.match(result.message, /accounts\.google\.com/);
  assert.doesNotMatch(result.message, /client_id|redirect_uri/, 'redirect query is not echoed');
  assert.equal(targetCall(calls).options.redirect, 'manual');
  assert.equal(calls.filter((c) => c.url.includes('accounts.google.com')).length, 0, 'no follow-up request');
});

test('200 with an HTML sign-in page body is a body failure', async () => {
  const { fetch } = fakeFetch({
    target: new Response('<html><body>Sign in</body></html>', {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    }),
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'body');
  assert.match(result.message, /text\/html/);
});

test('200 with the wrong JSON status is a body failure', async () => {
  const { fetch } = fakeFetch({ target: jsonResponse({ status: 'degraded' }) });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'body');
  assert.match(result.message, /"degraded"/);
});

test('200 with a non-JSON body is a body failure', async () => {
  const { fetch } = fakeFetch({ target: jsonResponse('not json', 200) });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'body');
});

for (const code of ['CERT_HAS_EXPIRED', 'ERR_TLS_CERT_ALTNAME_INVALID', 'SELF_SIGNED_CERT_IN_CHAIN']) {
  test(`TLS error ${code} is a transport failure`, async () => {
    const { fetch } = fakeFetch({
      target: () => {
        throw new TypeError('fetch failed', { cause: { code } });
      },
    });
    const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
    assert.equal(result.ok, false);
    assert.equal(result.class, 'transport');
    assert.equal(result.message, `tls: ${code}`);
  });
}

test('DNS failure is a transport failure', async () => {
  const { fetch } = fakeFetch({
    target: () => {
      throw new TypeError('fetch failed', { cause: { code: 'ENOTFOUND' } });
    },
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.class, 'transport');
  assert.equal(result.message, 'dns: ENOTFOUND');
});

test('timeout is a transport failure', async () => {
  const { fetch } = fakeFetch({
    target: () => {
      const error = new Error('The operation was aborted due to timeout');
      error.name = 'TimeoutError';
      throw error;
    },
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.class, 'transport');
  assert.equal(result.message, 'timeout');
});

test('backend 503 is a backend failure', async () => {
  const { fetch } = fakeFetch({ target: jsonResponse({ status: 'unavailable' }, 503) });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.class, 'backend');
  assert.equal(result.status, 503);
});

test('signJwt denied (signer lacks iam.serviceAccounts.signJwt) is a signing failure and the target is never called', async () => {
  const { fetch, calls } = fakeFetch({ signJwt: () => jsonResponse({ error: { code: 403 } }, 403) });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'signing');
  assert.equal(result.message, 'signJwt returned 403');
  assert.equal(calls.filter((c) => c.url === TARGET).length, 0);
});

test('no token value ever reaches a message', async () => {
  const { fetch } = fakeFetch({
    target: () => {
      throw new Error(`upstream said Bearer ${FAKE_JWT} was invalid; token ${FAKE_JWT}`);
    },
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.class, 'transport');
  assert.doesNotMatch(result.message, new RegExp(FAKE_JWT.slice(0, 20)));
  assert.doesNotMatch(result.message, /ya29\./);
  assert.match(result.message, /\[redacted/);
  assert.equal(probe.redact(`Authorization: Bearer ${ACCESS_TOKEN}`), 'Authorization: Bearer [redacted]');
  assert.equal(probe.redact(FAKE_JWT), '[redacted-token]');
});

test('configuration rejects http, other paths, oversized ttl and a missing signer', () => {
  assert.throws(
    () => probe.configFromEnv({ ...ENV, EREV_PROBE_TARGET_URL: 'http://erev.example.com/api/v1/healthz' }),
    /https/
  );
  assert.throws(
    () => probe.configFromEnv({ ...ENV, EREV_PROBE_TARGET_URL: 'https://erev.example.com/api/v1/readyz' }),
    /healthz/
  );
  assert.throws(
    () => probe.configFromEnv({ ...ENV, EREV_PROBE_TARGET_URL: `${TARGET}?x=1` }),
    /healthz/
  );
  assert.throws(() => probe.configFromEnv({ ...ENV, EREV_PROBE_JWT_TTL_SECONDS: '3601' }), /3600/);
  assert.throws(() => probe.configFromEnv({ ...ENV, EREV_PROBE_SIGNER_EMAIL: '' }), /required/);
  const config = probe.configFromEnv(ENV);
  assert.equal(config.audience, config.targetUrl);
  assert.equal(config.expectedStatus, 200);
  assert.equal(config.expectedBodyStatus, 'ok');
});

// A response whose headers arrived but whose body read fails (P3c-R3).
function bodyFailingResponse(error) {
  return {
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => {
      throw error;
    },
  };
}

test('body timeout after the 200 headers is one classified transport failure, not a throw', async () => {
  const error = new Error('The operation was aborted due to timeout');
  error.name = 'TimeoutError';
  const { fetch } = fakeFetch({ target: bodyFailingResponse(error) });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'transport');
  assert.equal(result.status, 200);
  assert.equal(result.message, 'body read failed after status 200: timeout');
  assert.equal(typeof result.latencyMs, 'number');
});

test('connection reset while reading the body is one classified transport failure, not a throw', async () => {
  const { fetch } = fakeFetch({
    target: bodyFailingResponse(new TypeError('terminated', { cause: { code: 'ECONNRESET' } })),
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.ok, false);
  assert.equal(result.class, 'transport');
  assert.equal(result.message, 'body read failed after status 200: connection: ECONNRESET');
});

test('a body read error carrying a token is redacted', async () => {
  const { fetch } = fakeFetch({
    target: bodyFailingResponse(new Error(`stream closed; Bearer ${FAKE_JWT}`)),
  });
  const result = await probe.runProbe(probe.configFromEnv(ENV), { fetch, now: clock(0, 1, 1) });
  assert.equal(result.class, 'transport');
  assert.doesNotMatch(result.message, new RegExp(FAKE_JWT.slice(0, 20)));
  assert.match(result.message, /\[redacted/);
});

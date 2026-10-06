'use strict';
// eRev strict-IAP health probe, core module (lane P3c; 05 DPL-37 external /api/v1/healthz coverage
// while IAP is on without the healthz exemption). Pure: no Google SDK and no I/O of its own. Every
// network call goes through the injected `fetch` and every clock read through `now`, so the runner
// is unit-tested offline (probe.test.mjs, `node --test`) and index.js only wires it to the Cloud
// Monitoring Synthetics SDK.
//
// Contract (README "Strict-IAP health probe"): mint a short-lived JWT for the probe's own service
// account through the IAM Credentials signJwt API (no exported key), with iss = sub = the signer,
// aud = EXACTLY the target URL and exp within the IAP bound; GET the target over HTTPS with normal
// certificate verification, a bounded timeout and redirects DISABLED; succeed only on status 200
// with a JSON body whose status is "ok". Everything else is a classified failure: transport (DNS,
// TLS, connection, timeout), iap-challenge (any redirect, e.g. to the sign-in page), auth (401/403:
// expired, wrong audience, wrong signature or ungranted identity), backend (other statuses), body
// (200 without the health body), signing (token or signJwt failure). No token or Authorization
// header value ever reaches a message or a log line.

const METADATA_TOKEN_URL =
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token';
const IAM_CREDENTIALS_BASE = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/';
const HEALTHZ_PATH = '/api/v1/healthz';
const MAX_JWT_TTL_SECONDS = 3600; // IAP: exp within 3600 seconds of iat
const TLS_ERROR_CODES = new Set([
  'CERT_HAS_EXPIRED',
  'CERT_NOT_YET_VALID',
  'DEPTH_ZERO_SELF_SIGNED_CERT',
  'SELF_SIGNED_CERT_IN_CHAIN',
  'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
  'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
  'ERR_TLS_CERT_ALTNAME_INVALID',
  'HOSTNAME_MISMATCH',
]);
const DNS_ERROR_CODES = new Set(['ENOTFOUND', 'EAI_AGAIN']);
const CONNECTION_ERROR_CODES = new Set(['ECONNREFUSED', 'ECONNRESET', 'EHOSTUNREACH', 'ETIMEDOUT']);
// Three base64url segments: the shape of a JWT (or an OAuth access token embedded in a message).
const JWT_PATTERN = /[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g;
const BEARER_PATTERN = /Bearer\s+[A-Za-z0-9._~+/=-]+/g;

class ProbeError extends Error {
  constructor(failureClass, message) {
    super(message);
    this.failureClass = failureClass;
  }
}

function required(env, name) {
  const value = env[name];
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${name} is required`);
  }
  return value.trim();
}

function positiveInt(value, name) {
  if (!/^[0-9]+$/.test(value) || Number(value) <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return Number(value);
}

// The runner's configuration comes from the Cloud Run function environment (cloud_run.tf sets it).
function configFromEnv(env) {
  const targetUrl = required(env, 'EREV_PROBE_TARGET_URL');
  let url;
  try {
    url = new URL(targetUrl);
  } catch {
    throw new Error('EREV_PROBE_TARGET_URL must be an absolute URL');
  }
  if (url.protocol !== 'https:') {
    throw new Error('EREV_PROBE_TARGET_URL must be https');
  }
  if (url.pathname !== HEALTHZ_PATH || url.search !== '' || url.hash !== '') {
    throw new Error(`EREV_PROBE_TARGET_URL must be the bare ${HEALTHZ_PATH} path`);
  }
  const signerEmail = required(env, 'EREV_PROBE_SIGNER_EMAIL');
  const jwtTtlSeconds = positiveInt(env.EREV_PROBE_JWT_TTL_SECONDS ?? '300', 'EREV_PROBE_JWT_TTL_SECONDS');
  if (jwtTtlSeconds > MAX_JWT_TTL_SECONDS) {
    throw new Error(`EREV_PROBE_JWT_TTL_SECONDS must be at most ${MAX_JWT_TTL_SECONDS}`);
  }
  const timeoutMs = positiveInt(env.EREV_PROBE_TIMEOUT_MS ?? '10000', 'EREV_PROBE_TIMEOUT_MS');
  return {
    targetUrl: url.toString(),
    // IAP: the audience is the exact protected URL; never a client id, never a wildcard here.
    audience: url.toString(),
    signerEmail,
    jwtTtlSeconds,
    timeoutMs,
    expectedStatus: 200,
    expectedBodyStatus: 'ok',
  };
}

// Strip anything token-shaped before a message can reach a result or a log line.
function redact(text) {
  return String(text ?? '')
    .replace(BEARER_PATTERN, 'Bearer [redacted]')
    .replace(JWT_PATTERN, '[redacted-token]');
}

function buildClaims(config, nowSeconds) {
  return {
    iss: config.signerEmail,
    sub: config.signerEmail,
    aud: config.audience,
    iat: nowSeconds,
    exp: nowSeconds + config.jwtTtlSeconds,
  };
}

async function fetchAccessToken(fetch, timeoutMs) {
  const response = await fetch(METADATA_TOKEN_URL, {
    method: 'GET',
    headers: { 'Metadata-Flavor': 'Google' },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new ProbeError('signing', `metadata token request returned ${response.status}`);
  }
  const body = await response.json();
  if (typeof body.access_token !== 'string' || body.access_token === '') {
    throw new ProbeError('signing', 'metadata token response carried no access token');
  }
  return body.access_token;
}

// IAM Credentials signJwt: the function's own identity signs a JWT for the configured signer (the
// same account, granted iam.serviceAccounts.signJwt on itself only). No private key is exported.
async function signJwt(fetch, accessToken, config, claims) {
  const url = `${IAM_CREDENTIALS_BASE}${encodeURIComponent(config.signerEmail)}:signJwt`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ payload: JSON.stringify(claims) }),
    signal: AbortSignal.timeout(config.timeoutMs),
  });
  if (!response.ok) {
    // The body may echo request details; only the status is reported.
    throw new ProbeError('signing', `signJwt returned ${response.status}`);
  }
  const body = await response.json();
  if (typeof body.signedJwt !== 'string' || body.signedJwt === '') {
    throw new ProbeError('signing', 'signJwt response carried no signedJwt');
  }
  return body.signedJwt;
}

function describeTransportError(error) {
  const name = error && error.name;
  if (name === 'TimeoutError' || name === 'AbortError') {
    return 'timeout';
  }
  const code = (error && error.cause && error.cause.code) || (error && error.code) || '';
  if (TLS_ERROR_CODES.has(code)) {
    return `tls: ${code}`;
  }
  if (DNS_ERROR_CODES.has(code)) {
    return `dns: ${code}`;
  }
  if (CONNECTION_ERROR_CODES.has(code)) {
    return `connection: ${code}`;
  }
  return `transport error${code ? ` ${code}` : ''}: ${redact(error && error.message)}`;
}

function redirectTarget(location) {
  if (!location) {
    return 'an unknown location';
  }
  try {
    return new URL(location).origin;
  } catch {
    return 'a relative location';
  }
}

function failure(failureClass, message, status) {
  return { ok: false, class: failureClass, status: status ?? null, message: redact(message) };
}

async function probeHealth(fetch, config, jwt, claims, nowSeconds) {
  let response;
  try {
    response = await fetch(config.targetUrl, {
      method: 'GET',
      // Never follow: a redirect is the IAP sign-in challenge (or a misroute), not health.
      redirect: 'manual',
      headers: { Authorization: `Bearer ${jwt}`, Accept: 'application/json' },
      signal: AbortSignal.timeout(config.timeoutMs),
    });
  } catch (error) {
    return failure('transport', describeTransportError(error));
  }
  const status = response.status;
  if (status >= 300 && status < 400) {
    return failure(
      'iap-challenge',
      `redirect ${status} to ${redirectTarget(response.headers.get('location'))}: ` +
        'an IAP sign-in challenge is never a healthy response',
      status
    );
  }
  if (status === 401 || status === 403) {
    const detail =
      claims.exp <= nowSeconds
        ? 'the probe JWT expired before the request (clock or latency)'
        : 'the probe JWT was rejected (audience, signature, issuer or IAP access for the signer)';
    return failure('auth', `IAP returned ${status}: ${detail}`, status);
  }
  if (status !== config.expectedStatus) {
    return failure('backend', `status ${status}, expected ${config.expectedStatus}`, status);
  }
  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  // The body arrives after the headers: a timeout or reset while reading it is a transport
  // failure too, reported as one classified record (never an unhandled throw; P3c-R3).
  let text;
  try {
    text = await response.text();
  } catch (error) {
    return failure(
      'transport',
      `body read failed after status ${status}: ${describeTransportError(error)}`,
      status
    );
  }
  if (!contentType.includes('application/json')) {
    return failure(
      'body',
      `status 200 but content-type ${contentType || 'missing'}: a sign-in or error page is not health`,
      status
    );
  }
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return failure('body', 'status 200 but the body is not JSON', status);
  }
  if (!body || body.status !== config.expectedBodyStatus) {
    return failure(
      'body',
      `status 200 but body.status is ${JSON.stringify(body ? body.status : body)}, ` +
        `expected ${JSON.stringify(config.expectedBodyStatus)}`,
      status
    );
  }
  return { ok: true, class: 'healthy', status, message: 'healthz ok' };
}

// deps: { fetch, now } — `now` returns epoch milliseconds and is read once before signing and once
// before classifying the response, so an expired token is reported as such.
async function runProbe(config, deps) {
  const startedMs = deps.now();
  const nowSeconds = Math.floor(startedMs / 1000);
  const claims = buildClaims(config, nowSeconds);
  let jwt;
  try {
    const accessToken = await fetchAccessToken(deps.fetch, config.timeoutMs);
    jwt = await signJwt(deps.fetch, accessToken, config, claims);
  } catch (error) {
    const failureClass = error instanceof ProbeError ? error.failureClass : 'signing';
    const result = failure(failureClass, error && error.message ? error.message : 'signing failed');
    result.latencyMs = deps.now() - startedMs;
    return result;
  }
  const responseNowSeconds = Math.floor(deps.now() / 1000);
  const result = await probeHealth(deps.fetch, config, jwt, claims, responseNowSeconds);
  result.latencyMs = deps.now() - startedMs;
  result.audience = config.audience;
  return result;
}

module.exports = {
  HEALTHZ_PATH,
  MAX_JWT_TTL_SECONDS,
  METADATA_TOKEN_URL,
  IAM_CREDENTIALS_BASE,
  TLS_ERROR_CODES,
  ProbeError,
  buildClaims,
  configFromEnv,
  redact,
  runProbe,
};

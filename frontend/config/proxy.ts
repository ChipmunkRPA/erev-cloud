// API proxy target for the Vite dev and preview servers (docs/dev-guide.md DG-RUN-20).
// There is no default target: a silent default would point the browser at the wrong API.

const PROXY_TARGET_PATTERN = /^http:\/\/127\.0\.0\.1:\d{2,5}$/;

export const PROXY_TARGET_ERROR =
  "EREV_API_PROXY_TARGET must be set, for example http://127.0.0.1:8190";

export function resolveProxyTarget(value: string | undefined): string {
  if (value === undefined || !PROXY_TARGET_PATTERN.test(value)) {
    throw new Error(PROXY_TARGET_ERROR);
  }
  return value;
}

// Synchronizer token of `GET /session` (docs/dev-guide.md DG-FE-05; 04 API-C-02). It lives in module
// memory only, never in localStorage or sessionStorage, so script that reads storage cannot lift it.
let token: string | null = null;

export function getCsrfToken(): string | null {
  return token;
}

export function setCsrfToken(value: string | null): void {
  token = value;
}

// OAuth2 client-credentials API clients (04 API-R-08 `GET, POST /api-clients`, `POST
// /api-clients/{id}/rotate-secret`, `/revoke`; API-R-06 `GET /permissions`; API-R-53 `GET /openapi.json`;
// T-PLT-15; E-103; REQ-PLT-033, REQ-PLT-034; CTL-037; SCREENS_B §9.15; BUILD_SPEC WEB-23). A client
// holds non-approval scopes only (ERR-24 `scope-not-allowed`); its secret is returned once by the create
// and rotate commands and never again. Commands go through `useCommand` from the screen.
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import type { Permission } from "./roles";
import { dayStartInstant, utcDateOf } from "../../format";

export type ApiClient = components["schemas"]["ApiClientOut"];
export type ApiClientCreate = components["schemas"]["ApiClientIn"];
export type ApiClientSecret = components["schemas"]["ApiClientSecretOut"];
export type ApiClientRevoke = components["schemas"]["ApiClientRevokeIn"];
export type ApiClientStatus = components["schemas"]["ApiClientStatus"];

export const API_CLIENTS_PATH = "/api/v1/api-clients";
export const OPENAPI_PATH = "/api/v1/openapi.json";
export const TOKEN_PATH = "/api/v1/oauth/token";
export const API_BASE_PATH = "/api/v1";
/** SCREENS RT-93 SF-16:developer, `pane=api-clients|webhooks|openapi`. */
export const DEVELOPER_ROUTE = "/settings/developer";
/** SCREENS_B §9.15 read permissions per tab. */
export const API_CLIENT_MANAGE_PERMISSION = "api_client.manage";
export const WEBHOOK_MANAGE_PERMISSION = "webhook.manage";
/** SCREENS_B §9.15 defaults of "New API client". */
export const DEFAULT_RATE_LIMIT = 600;
export const DEFAULT_EXPIRY_DAYS = 365;
/** PRD ERR-24 problem slug (CTL-037). */
export const SCOPE_NOT_ALLOWED_SLUG = "scope-not-allowed";
/** SCR-PERM-05: the step-up the create and rotate commands ask for. */
export const STEP_UP_REQUIRED_SLUG = "mfa-step-up-required";

export type DeveloperPane = "api-clients" | "webhooks" | "openapi";
export const DEVELOPER_PANES: readonly DeveloperPane[] = ["api-clients", "webhooks", "openapi"];

export function developerPaneOf(value: string | null): DeveloperPane {
  return DEVELOPER_PANES.find((pane) => pane === value) ?? "api-clients";
}

export const EVERY_API_CLIENT: QueryKey = queryKey("api-clients", "tenant");

export function apiClientsGridKey(): QueryKey {
  return queryKey("api-clients", "tenant", { view: "grid" });
}

export function fetchApiClientsPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ApiClient>> {
  return fetchListPage<ApiClient>(API_CLIENTS_PATH, { sort: sort ?? "name" }, cursor);
}

export function apiClientCommandPath(
  clientId: string,
  command: "rotate-secret" | "revoke",
): string {
  return `${API_CLIENTS_PATH}/${clientId}/${command}`;
}

export interface ScopeGroup {
  readonly area: string;
  readonly permissions: readonly Permission[];
}

/** SCREENS_B §9.15 "Scopes": non-approval permissions grouped by area, areas in catalogue order. */
export function scopeGroups(permissions: readonly Permission[]): readonly ScopeGroup[] {
  const groups: ScopeGroup[] = [];
  for (const permission of permissions) {
    if (permission.is_approval) {
      continue;
    }
    const group = groups.find((candidate) => candidate.area === permission.area);
    if (group === undefined) {
      groups.push({ area: permission.area, permissions: [permission] });
    } else {
      groups.splice(groups.indexOf(group), 1, {
        area: group.area,
        permissions: [...group.permissions, permission],
      });
    }
  }
  return groups;
}

/** The default expiry: today plus 365 days, as an RFC 3339 instant at midnight UTC. */
export function defaultExpiry(nowMs: number): string {
  return utcDateOf(nowMs + DEFAULT_EXPIRY_DAYS * 86_400_000);
}

/** The picked expiry date as the instant the API takes: the start of that day, UTC (DS-I18N-08). */
export function expiryInstant(date: string): string {
  return dayStartInstant(date);
}

/** The masked rendering of a secret: one bullet per character, capped for very long values. */
export function maskSecret(secret: string): string {
  return "•".repeat(Math.min(secret.length, 32));
}

/** SCREENS_B §9.15 `SF-16-row-<name normalised>`: `svc-salesforce`. */
export function clientTestKey(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** SCREENS_B §9.15 client id cell: "erevc_3f09…_Xq2…", the prefix and suffix of a long id. */
export function shortClientId(clientId: string): string {
  return clientId.length <= 24 ? clientId : `${clientId.slice(0, 10)}…${clientId.slice(-6)}`;
}

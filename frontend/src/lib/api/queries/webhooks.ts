// Signed webhook endpoints and their deliveries (04 API-R-15 `GET, POST /webhook-endpoints`, `PATCH
// /webhook-endpoints/{id}`, `GET /webhook-deliveries?status`; T-PLT-35, T-PLT-36; E-97; REQ-PLT-037,
// REQ-OPS-016; SB-R-08; SCREENS_B §9.15; BUILD_SPEC WEB-23). Endpoints receive signed notifications with
// resource ids only; the signing secret is returned once by the create command. Commands go through
// `useCommand` from the screen.
import { useQuery } from "@tanstack/react-query";

import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type WebhookEndpoint = components["schemas"]["WebhookEndpointOut"];
export type WebhookEndpointCreate = components["schemas"]["WebhookEndpointIn"];
export type WebhookEndpointCreated = components["schemas"]["WebhookEndpointCreatedOut"];
export type WebhookEndpointUpdate = components["schemas"]["WebhookEndpointUpdateIn"];
export type WebhookDelivery = components["schemas"]["WebhookDeliveryOut"];
export type WebhookDeliveryStatus = components["schemas"]["WebhookDeliveryStatus"];

export const WEBHOOK_ENDPOINTS_PATH = "/api/v1/webhook-endpoints";
export const WEBHOOK_DELIVERIES_PATH = "/api/v1/webhook-deliveries";
/** SCREENS_B §9.15 "Events" codes (T-PLT-35 `event_kinds`). */
export const WEBHOOK_EVENT_KINDS: readonly string[] = [
  "run.completed",
  "import.committed",
  "period.locked",
  "journal_batch.exported",
  "journal_batch.acknowledged",
  "exception.raised",
];
/** E-97 literals in 04 order. */
export const DELIVERY_STATUSES: readonly WebhookDeliveryStatus[] = [
  "PENDING",
  "SUCCEEDED",
  "FAILED",
  "ABANDONED",
];

export const EVERY_WEBHOOK: QueryKey = queryKey("webhook-endpoints", "tenant");
export const EVERY_DELIVERY: QueryKey = queryKey("webhook-deliveries", "tenant");

export function endpointsGridKey(): QueryKey {
  return queryKey("webhook-endpoints", "tenant", { view: "grid" });
}

export function fetchEndpointsPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<WebhookEndpoint>> {
  return fetchListPage<WebhookEndpoint>(WEBHOOK_ENDPOINTS_PATH, { sort: sort ?? "url" }, cursor);
}

/** Every endpoint, for the "Endpoint" column of the deliveries grid. */
export function allEndpointsKey(): QueryKey {
  return queryKey("webhook-endpoints", "tenant", { view: "all" });
}

export async function fetchAllEndpoints(): Promise<readonly WebhookEndpoint[]> {
  const page = await fetchListPage<WebhookEndpoint>(WEBHOOK_ENDPOINTS_PATH, { sort: "url" }, null, {
    limit: 500,
    count: false,
  });
  return page.items;
}

export function useAllEndpoints(enabled = true) {
  return useQuery({ queryKey: allEndpointsKey(), queryFn: fetchAllEndpoints, enabled });
}

export function endpointPath(endpointId: string): string {
  return `${WEBHOOK_ENDPOINTS_PATH}/${endpointId}`;
}

export function deliveriesGridKey(status: readonly string[]): QueryKey {
  return queryKey("webhook-deliveries", "tenant", { view: "grid", status: status.join(",") });
}

export function fetchDeliveriesPage(
  status: readonly string[],
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<WebhookDelivery>> {
  return fetchListPage<WebhookDelivery>(
    WEBHOOK_DELIVERIES_PATH,
    { status: status.length === 1 ? status[0] : null, sort: sort ?? "-created_at" },
    cursor,
  );
}

/** SCREENS_B §9.15 "Use an https URL." except the loopback hosts allowed in dev and e2e. */
export function acceptableWebhookUrl(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    if (parsed.protocol === "https:") {
      return true;
    }
    return (
      parsed.protocol === "http:" &&
      (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost")
    );
  } catch {
    return false;
  }
}

/** The endpoint URL without its path, for the deliveries grid ("Endpoint"). */
export function urlPrefix(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return url;
  }
}

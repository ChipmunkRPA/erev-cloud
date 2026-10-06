// Customer, related-party group and API fixtures shared by the SF-15 customer tests (SCREENS §9.8
// sample world: C-05 Hollenbrand Klinikbedarf, C-11 Hollenbrand Medizintechnik, C-01 Pellworth).
import { http, HttpResponse } from "msw";

import type { Customer, RelatedPartyGroup } from "../lib/api/queries/customers";
import { apiUrl, problemResponse, server } from "./msw";

export const HOLLENBRAND: RelatedPartyGroup = {
  id: "9a9a9a9a-9a9a-4a9a-8a9a-9a9a9a9a9a9a",
  code: "HOLLENBRAND",
  name: "Hollenbrand group",
  description: "Hollenbrand Klinikbedarf and Hollenbrand Medizintechnik under common control.",
  member_count: 2,
  row_version: 2,
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

export function customer(
  overrides: Partial<Customer> & Pick<Customer, "id" | "code" | "name">,
): Customer {
  return {
    country_code: "DE",
    credit_grade: null,
    external_id: null,
    is_active: true,
    parent_customer_id: null,
    related_party_group: null,
    related_party_group_id: null,
    row_version: 3,
    segment: null,
    source_system: "NETSUITE",
    created_at: "2026-08-15T08:00:00Z",
    updated_at: "2026-09-10T08:00:00Z",
    ...overrides,
  };
}

export const KLINIKBEDARF = customer({
  id: "c5c5c5c5-c5c5-4c5c-8c5c-c5c5c5c5c5c5",
  code: "CUST-0005",
  name: "Hollenbrand Klinikbedarf GmbH (Demo)",
  external_id: "C-DE-3001",
  related_party_group: { id: HOLLENBRAND.id, code: HOLLENBRAND.code, name: HOLLENBRAND.name },
  related_party_group_id: HOLLENBRAND.id,
  segment: "Healthcare",
});
export const MEDIZINTECHNIK = customer({
  id: "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1",
  code: "CUST-0011",
  name: "Hollenbrand Medizintechnik GmbH (Demo)",
  external_id: "C-DE-3004",
  related_party_group: { id: HOLLENBRAND.id, code: HOLLENBRAND.code, name: HOLLENBRAND.name },
  related_party_group_id: HOLLENBRAND.id,
});
export const PELLWORTH = customer({
  id: "c0c0c0c0-c0c0-4c0c-8c0c-c0c0c0c0c0c0",
  code: "CUST-0001",
  name: "Pellworth Logistics Inc. (Demo)",
  country_code: "US",
  external_id: "001DEMO0001",
  source_system: "SALESFORCE",
  credit_grade: "A",
});

export function serveCustomers(
  customers: readonly Customer[],
  groups: readonly RelatedPartyGroup[],
) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/customers"), ({ request }) => {
      const url = new URL(request.url);
      const group = url.searchParams.get("related_party_group_id");
      const q = url.searchParams.get("q");
      const items = customers.filter(
        (item) =>
          (group === null || item.related_party_group_id === group) &&
          (q === null || item.name.toLowerCase().includes(q.toLowerCase())),
      );
      return HttpResponse.json(
        { items, next_cursor: null },
        {
          headers:
            url.searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(items.length) }
              : {},
        },
      );
    }),
    http.get(apiUrl("/api/v1/customers/:customerId"), ({ params }) => {
      const found = customers.find((item) => item.id === params.customerId);
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/related-party-groups"), () =>
      HttpResponse.json({ items: groups, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/contracts"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
  );
}

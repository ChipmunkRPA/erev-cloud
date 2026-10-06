// Customers and related-party groups (04 API-R-22 `GET, POST /customers`, `GET, PATCH /customers/{id}`
// with `If-Match`, `GET, POST /related-party-groups`, `PATCH /related-party-groups/{id}`; T-REF-18,
// T-REF-19; E-38 `source_system`; REQ-REF-010, REQ-REF-011, REQ-CON-010; SCREENS §9; BUILD_SPEC RFD-20).
// The customer master holds business identity only (no personal contact details); a customer belongs
// to at most one related-party group, which combination detection and disclosure use. Commands go
// through `useCommand` from the screens.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { STRUCTURE_LIMIT } from "./tenant";

export type Customer = components["schemas"]["CustomerOut"];
export type CustomerCreate = components["schemas"]["CustomerIn"];
export type CustomerUpdate = components["schemas"]["CustomerUpdateIn"];
export type RelatedPartyGroup = components["schemas"]["RelatedPartyGroupOut"];
export type RelatedPartyGroupCreate = components["schemas"]["RelatedPartyGroupIn"];
export type RelatedPartyGroupUpdate = components["schemas"]["RelatedPartyGroupUpdateIn"];
export type SourceSystem = components["schemas"]["SourceSystem"];

export const CUSTOMERS_PATH = "/api/v1/customers";
export const RELATED_PARTY_GROUPS_PATH = "/api/v1/related-party-groups";
/** SCREENS RT-79 to RT-81. */
export const CUSTOMERS_ROUTE = "/settings/customers";
export const CUSTOMER_ROUTE = "/settings/customers/:customerId";
export const RELATED_PARTY_GROUPS_ROUTE = "/settings/related-party-groups";
/** SCREENS §9.1: read `contract.read`; create and edit `masterdata.maintain`; import `import.upload`. */
export const CUSTOMER_READ_PERMISSION = "contract.read";
export const MASTERDATA_MAINTAIN_PERMISSION = "masterdata.maintain";
export const IMPORT_UPLOAD_PERMISSION = "import.upload";
/** SF-10:new with the customers template (SCREENS §9.3). */
export const IMPORT_CUSTOMERS_ROUTE = "/data/imports/new?template=customers";
/** 04 API-R-22 sorts: `code`, `name`, `updated_at`; the grid opens on the name. */
export const DEFAULT_CUSTOMER_SORT = "name";
/** E-38 literals in 04 order. */
export const SOURCE_SYSTEMS: readonly SourceSystem[] = [
  "LEGACY_TEMPLATE_V1",
  "CSV_V2",
  "API",
  "MANUAL_UI",
  "SALESFORCE",
  "STRIPE",
  "NETSUITE",
  "QUICKBOOKS_ONLINE",
  "LEGACY_DB",
];
/** SCREENS §3.5 column 15 label keys of E-38 (`contracts.list.source.<key>`). */
export const SOURCE_LABEL_KEYS: Readonly<Record<SourceSystem, string>> = {
  LEGACY_TEMPLATE_V1: "legacyTemplate",
  CSV_V2: "csv",
  API: "api",
  MANUAL_UI: "manual",
  SALESFORCE: "salesforce",
  STRIPE: "stripe",
  NETSUITE: "netsuite",
  QUICKBOOKS_ONLINE: "quickbooks",
  LEGACY_DB: "legacyDatabase",
};
/** Customers a person enters here carry this source; the others come from imports and integrations. */
export const MANUAL_SOURCE: SourceSystem = "MANUAL_UI";

export interface CustomerQuery {
  readonly q: string;
  readonly groupId: string | null;
  readonly source: readonly string[];
  readonly externalId: string | null;
  readonly isActive: boolean | null;
}

export const EMPTY_CUSTOMER_QUERY: CustomerQuery = {
  q: "",
  groupId: null,
  source: [],
  externalId: null,
  isActive: null,
};

/** Every customer read, for invalidation after a command (includes the contracts filter list). */
export const EVERY_CUSTOMER: QueryKey = queryKey("customers", "tenant");
export const EVERY_RELATED_PARTY_GROUP: QueryKey = queryKey("related-party-groups", "tenant");

export function customersGridKey(query: CustomerQuery): QueryKey {
  return queryKey("customers", "tenant", {
    view: "grid",
    q: query.q,
    group: query.groupId,
    source: query.source.join(","),
    external_id: query.externalId,
    is_active: query.isActive,
  });
}

export function fetchCustomersPage(
  query: CustomerQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Customer>> {
  const source = query.source[0] ?? null;
  return fetchListPage<Customer>(
    CUSTOMERS_PATH,
    {
      q: query.q === "" ? null : query.q,
      related_party_group_id: query.groupId,
      // API-R-22 filters one source system; a multi-value filter narrows client-side.
      source_system: query.source.length === 1 ? source : null,
      external_id: query.externalId,
      is_active: query.isActive,
      sort: sort ?? DEFAULT_CUSTOMER_SORT,
    },
    cursor,
  );
}

export function customerKey(customerId: string): QueryKey {
  return queryKey("customers", "tenant", { view: "record", id: customerId });
}

export function fetchCustomer(customerId: string): Promise<Customer> {
  return unwrap(
    api.GET("/api/v1/customers/{customer_id}", { params: { path: { customer_id: customerId } } }),
  );
}

export function useCustomer(customerId: string) {
  return useQuery({ queryKey: customerKey(customerId), queryFn: () => fetchCustomer(customerId) });
}

export function customerPath(customerId: string): string {
  return `${CUSTOMERS_PATH}/${customerId}`;
}

export function customerRoute(customerId: string): string {
  return `${CUSTOMERS_ROUTE}/${customerId}`;
}

export function groupMembersKey(groupId: string): QueryKey {
  return queryKey("customers", "tenant", { view: "members", group: groupId });
}

/** The customers of one related-party group, in code order (SCREENS §9.3 related customers). */
export async function fetchGroupMembers(groupId: string): Promise<readonly Customer[]> {
  const page = await fetchListPage<Customer>(
    CUSTOMERS_PATH,
    { related_party_group_id: groupId, sort: "code" },
    null,
    { limit: STRUCTURE_LIMIT, count: false },
  );
  return page.items;
}

export function allCustomersKey(): QueryKey {
  return queryKey("customers", "tenant", { view: "all" });
}

/** Every customer in scope, in name order, for the "Parent customer" combobox. */
export async function fetchAllCustomers(): Promise<readonly Customer[]> {
  const customers: Customer[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Customer> = await fetchListPage<Customer>(
      CUSTOMERS_PATH,
      { sort: DEFAULT_CUSTOMER_SORT },
      cursor,
      { limit: STRUCTURE_LIMIT, count: false },
    );
    customers.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return customers;
}

export function groupsKey(): QueryKey {
  return queryKey("related-party-groups", "tenant", { view: "all" });
}

/** Every related-party group in code order (the API default sort). */
export async function fetchAllGroups(): Promise<readonly RelatedPartyGroup[]> {
  const page = await fetchListPage<RelatedPartyGroup>(RELATED_PARTY_GROUPS_PATH, {}, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function useGroups(enabled = true) {
  return useQuery({ queryKey: groupsKey(), queryFn: fetchAllGroups, enabled });
}

export function groupsGridKey(query: string): QueryKey {
  return queryKey("related-party-groups", "tenant", { view: "grid", q: query });
}

export function fetchGroupsPage(
  query: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<RelatedPartyGroup>> {
  return fetchListPage<RelatedPartyGroup>(
    RELATED_PARTY_GROUPS_PATH,
    { q: query === "" ? null : query, sort: sort ?? "code" },
    cursor,
  );
}

export function groupPath(groupId: string): string {
  return `${RELATED_PARTY_GROUPS_PATH}/${groupId}`;
}

/** SCREENS §9.4 column 3: "<code> · <name>" of a customer's group. */
export function groupLabel(group: Pick<RelatedPartyGroup, "code" | "name">): string {
  return `${group.code} · ${group.name}`;
}

/** The route of the groups page with one group's drawer open. */
export function groupDrawerRoute(groupId: string): string {
  return `${RELATED_PARTY_GROUPS_ROUTE}?drawer=group&row=${groupId}`;
}

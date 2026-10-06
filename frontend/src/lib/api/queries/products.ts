// Products and bundles (04 API-R-23 `GET, POST /products`, `GET, PATCH /products/{id}` with `If-Match`,
// `GET, PUT /products/{id}/bundle-components`, `POST /products/{id}/propose-principal-agent-change`;
// API-R-24 `GET /pob-templates`, `GET /pob-template-versions/{id}`; API-R-26 SSP entries of a product;
// API-R-13 `GET /policies/resolve` for the mandatory disaggregation attributes; T-REF-20, T-REF-21;
// REQ-REF-012 to REQ-REF-014, REQ-POB-009; SCREENS §10; BUILD_SPEC RFD-21). The product master: default
// obligation template, revenue category, disaggregation attributes, principal or agent conclusion,
// bundles and the SSP entries that price the product. Commands go through `useCommand` from the screens.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { ApiProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { POB_TEMPLATES_PATH, type PobTemplate, type PobTemplateVersion } from "./rule-sets";
import { STRUCTURE_LIMIT } from "./tenant";

export type Product = components["schemas"]["ProductOut"];
export type ProductCreate = components["schemas"]["ProductIn"];
export type ProductUpdate = components["schemas"]["ProductUpdateIn"];
export type BundleComponent = components["schemas"]["BundleComponentOut"];
export type BundleComponentInput = components["schemas"]["BundleComponentIn"];
export type BundleComponents = components["schemas"]["BundleComponentsOut"];
export type PrincipalAgentChange = components["schemas"]["PrincipalAgentChangeIn"];
export type PrincipalAgentChangeResult = components["schemas"]["PrincipalAgentChangeOut"];
export type Distinctness = components["schemas"]["Distinctness"];
export type PrincipalAgent = components["schemas"]["PrincipalAgent"];
export type SplitBasis = BundleComponent["split_basis"];

export const PRODUCTS_PATH = "/api/v1/products";
/** SCREENS RT-82 and RT-83. */
export const PRODUCTS_ROUTE = "/settings/products";
export const PRODUCT_ROUTE = "/settings/products/:productId";
/** SCREENS RT-61 SF-13:template-version, the "Default template" drill (built by RFD-23). */
export const TEMPLATE_VERSION_ROUTE = "/policies/templates/:templateId/versions/:versionId";
/** SCREENS §10.1: read `contract.read`; edit and bundles `masterdata.maintain`; import `import.upload`. */
export const PRODUCT_READ_PERMISSION = "contract.read";
export const MASTERDATA_MAINTAIN_PERMISSION = "masterdata.maintain";
export const IMPORT_UPLOAD_PERMISSION = "import.upload";
export const IMPORT_PRODUCTS_ROUTE = "/data/imports/new?template=products";
/** 04 API-R-23 sorts `code` and `name`. */
export const DEFAULT_PRODUCT_SORT = "code";
/** E-13 and T-REF-20 literals in 04 order. */
export const DISTINCTNESS_VALUES: readonly Distinctness[] = ["distinct", "nondistinct", "series"];
export const PRINCIPAL_AGENT_VALUES: readonly PrincipalAgent[] = [
  "PRINCIPAL",
  "AGENT",
  "NOT_ASSESSED",
];
export const SPLIT_BASES: readonly SplitBasis[] = ["relative_ssp", "fixed_percentage"];
/** SCREENS §10.6: the customer-option product whose SSP comes from the option record. */
export const OPTION_REVENUE_CATEGORY = "MATERIAL_RIGHT";
/** The registry parameter naming the tenant's required disaggregation attributes (SCREENS §10.4). */
export const MANDATORY_ATTRIBUTES_KEY = "disclosure.mandatory_disaggregation_attributes";

export type ProductPane = "attributes" | "bundle" | "ssp" | "policy-values";
export const PRODUCT_PANES: readonly ProductPane[] = [
  "attributes",
  "bundle",
  "ssp",
  "policy-values",
];

/** SCREENS §10.1 `pane=attributes|bundle|ssp|policy-values`; anything else is Attributes. */
export function productPaneOf(value: string | null): ProductPane {
  return PRODUCT_PANES.find((pane) => pane === value) ?? "attributes";
}

export interface ProductQuery {
  readonly q: string;
  readonly family: string | null;
  readonly isActive: boolean | null;
}

export const EVERY_PRODUCT: QueryKey = queryKey("products", "tenant");

export function productsGridKey(query: ProductQuery): QueryKey {
  return queryKey("products", "tenant", {
    view: "grid",
    q: query.q,
    family: query.family,
    is_active: query.isActive,
  });
}

export function fetchProductsPage(
  query: ProductQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Product>> {
  return fetchListPage<Product>(
    PRODUCTS_PATH,
    {
      q: query.q === "" ? null : query.q,
      product_family: query.family,
      is_active: query.isActive,
      sort: sort ?? DEFAULT_PRODUCT_SORT,
    },
    cursor,
  );
}

export function productKey(productId: string): QueryKey {
  return queryKey("products", "tenant", { view: "record", id: productId });
}

export function fetchProduct(productId: string): Promise<Product> {
  return unwrap(
    api.GET("/api/v1/products/{product_id}", { params: { path: { product_id: productId } } }),
  );
}

export function useProduct(productId: string) {
  return useQuery({ queryKey: productKey(productId), queryFn: () => fetchProduct(productId) });
}

export function productPath(productId: string): string {
  return `${PRODUCTS_PATH}/${productId}`;
}

export function productRoute(productId: string): string {
  return `${PRODUCTS_ROUTE}/${productId}`;
}

export function bundleComponentsPath(productId: string): string {
  return `${productPath(productId)}/bundle-components`;
}

export function bundleComponentsKey(productId: string): QueryKey {
  return queryKey("products", "tenant", { view: "bundle", id: productId });
}

export function fetchBundleComponents(productId: string): Promise<BundleComponents> {
  return unwrap(
    api.GET("/api/v1/products/{product_id}/bundle-components", {
      params: { path: { product_id: productId } },
    }),
  );
}

export function proposePrincipalAgentPath(productId: string): string {
  return `${productPath(productId)}/propose-principal-agent-change`;
}

export function allProductsKey(): QueryKey {
  return queryKey("products", "tenant", { view: "all" });
}

/** Every product in code order (bundle component choices, up to the structure limit). */
export async function fetchAllProducts(): Promise<readonly Product[]> {
  const page = await fetchListPage<Product>(PRODUCTS_PATH, { sort: DEFAULT_PRODUCT_SORT }, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function allTemplatesKey(): QueryKey {
  return queryKey("pob-templates", "tenant", { view: "all" });
}

/** Every obligation template with its version summaries, in code order. */
export async function fetchAllTemplates(): Promise<readonly PobTemplate[]> {
  const page = await fetchListPage<PobTemplate>(POB_TEMPLATES_PATH, { sort: "code" }, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function useTemplates(enabled = true) {
  return useQuery({ queryKey: allTemplatesKey(), queryFn: fetchAllTemplates, enabled });
}

/** SCREENS §10.4 "Default obligation template": templates with a published (current) version. */
export function publishedTemplates(templates: readonly PobTemplate[]): readonly PobTemplate[] {
  return templates.filter((template) => template.current_version !== null);
}

export function templateVersionKey(versionId: string): QueryKey {
  return queryKey("pob-template-versions", "tenant", { id: versionId, view: "product" });
}

export function fetchTemplateVersion(versionId: string): Promise<PobTemplateVersion> {
  return unwrap(
    api.GET("/api/v1/pob-template-versions/{version_id}", {
      params: { path: { version_id: versionId } },
    }),
  );
}

export function templateVersionRoute(templateId: string, versionId: string): string {
  return `/policies/templates/${templateId}/versions/${versionId}`;
}

export function mandatoryAttributesKey(): QueryKey {
  return queryKey("policies", "tenant", { view: "mandatory-disaggregation" });
}

/** The tenant's required disaggregation attribute keys; a reader without the registry read sees none. */
export async function fetchMandatoryAttributes(): Promise<readonly string[]> {
  try {
    const resolution = await unwrap(
      api.GET("/api/v1/policies/resolve", {
        params: { query: { key: MANDATORY_ATTRIBUTES_KEY } },
      }),
    );
    const value: unknown = resolution.value;
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch (error) {
    if (error instanceof ApiProblem && (error.status === 403 || error.status === 404)) {
      return [];
    }
    throw error;
  }
}

/** The required attributes the product has not set (REQ-REF-012), from usability first. */
export function missingAttributes(
  product: Pick<Product, "usability" | "disaggregation">,
  mandatory: readonly string[],
): readonly string[] {
  if (product.usability.missing.length > 0) {
    return product.usability.missing;
  }
  return mandatory.filter((key) => {
    const value = product.disaggregation[key];
    return value === undefined || value === null || value === "";
  });
}

export interface PolicyValueRow {
  readonly key: string;
  readonly value: string;
  readonly level: "product" | "template";
}

/** SCREENS §10.4 policy values: product values, then the template version's, which take precedence. */
export function policyValueRows(
  product: Pick<Product, "policy_values">,
  templateVersion: Pick<PobTemplateVersion, "policy_values"> | null,
): readonly PolicyValueRow[] {
  const render = (value: unknown) => (typeof value === "string" ? value : JSON.stringify(value));
  const rows: PolicyValueRow[] = Object.entries(product.policy_values).map(([key, value]) => ({
    key,
    value: render(value),
    level: "product",
  }));
  for (const [key, value] of Object.entries(templateVersion?.policy_values ?? {})) {
    rows.push({ key, value: render(value), level: "template" });
  }
  return rows.sort((a, b) => a.key.localeCompare(b.key) || a.level.localeCompare(b.level));
}

/** The `BundleComponentIn` bodies of stored rows, for a whole-list `PUT`. */
export function bundleInputs(rows: readonly BundleComponent[]): readonly BundleComponentInput[] {
  return rows.map((row) => ({
    component_product_id: row.component_product_id,
    quantity_per_bundle: row.quantity_per_bundle,
    sequence: row.sequence,
    split_basis: row.split_basis,
    split_ratio: row.split_ratio,
    valid_from: row.valid_from,
    valid_to: row.valid_to,
  }));
}

/** SCREENS §10.4: the indicator answers travel inside the rationale (API-R-23 takes none). */
export function composeRationale(
  indicators: readonly {
    readonly label: string;
    readonly answer: "yes" | "no" | null;
    readonly note: string;
  }[],
  rationale: string,
): string {
  const lines = indicators
    .filter((indicator) => indicator.answer !== null)
    .map(
      (indicator) =>
        `${indicator.label}: ${indicator.answer === "yes" ? "Yes" : "No"}${
          indicator.note.trim() === "" ? "" : ` (${indicator.note.trim()})`
        }`,
    );
  return [...lines, rationale.trim()].filter((line) => line !== "").join("\n");
}

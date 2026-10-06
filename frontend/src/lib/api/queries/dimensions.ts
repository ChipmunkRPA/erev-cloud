// Dimensions and their values (04 API-R-21 `GET, POST /dimensions`, `GET, POST /dimensions/{code}/values`,
// `PATCH /dimensions/{code}/values/{id}`; T-REF-14, T-REF-15; SCREENS_B §9.5; BUILD_SPEC RFD-19).
// Commands need `masterdata.maintain`; a workspace defines at most five custom dimensions.
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type Dimension = components["schemas"]["DimensionOut"];
export type DimensionCreate = components["schemas"]["DimensionIn"];
export type DimensionValue = components["schemas"]["DimensionValueOut"];
export type DimensionValueCreate = components["schemas"]["DimensionValueIn"];

export const DIMENSIONS_PATH = "/api/v1/dimensions";
export const DIMENSION_MAINTAIN_PERMISSION = "masterdata.maintain";
/** SCREENS_B §9.5: "A workspace can define at most five custom dimensions." */
export const CUSTOM_DIMENSION_LIMIT = 5;

export function dimensionsKey(): QueryKey {
  return queryKey("dimensions", "tenant");
}

/** One DataGrid page of `GET /dimensions` (DG-FE-07). */
export function fetchDimensionsPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Dimension>> {
  return fetchListPage<Dimension>(DIMENSIONS_PATH, { sort }, cursor);
}

/** Every dimension of the workspace (at most the built-in five plus five custom ones). */
export async function fetchAllDimensions(): Promise<readonly Dimension[]> {
  const page = await fetchListPage<Dimension>(DIMENSIONS_PATH, {}, null, {
    limit: 200,
    count: false,
  });
  return page.items;
}

export function dimensionValuesPath(code: string): string {
  return `${DIMENSIONS_PATH}/${encodeURIComponent(code)}/values`;
}

export function dimensionValuesKey(code: string): QueryKey {
  return queryKey("dimension-values", "tenant", { code });
}

/** The values of one dimension, following cursors. */
export async function fetchDimensionValues(code: string): Promise<readonly DimensionValue[]> {
  const items: DimensionValue[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<DimensionValue> = await fetchListPage<DimensionValue>(
      dimensionValuesPath(code),
      {},
      cursor,
      { count: false },
    );
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items;
}

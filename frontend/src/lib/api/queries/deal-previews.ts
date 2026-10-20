import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import type { components } from "../schema";

export type DealPreview = components["schemas"]["DealPreviewOut"];
export type DealInput = components["schemas"]["DealInputIn"];
export function fetchDealPreview(id: string): Promise<DealPreview> {
  return unwrap(
    api.GET("/api/v1/deal-previews/{preview_id}", { params: { path: { preview_id: id } } }),
  );
}

export type DealProduct = Pick<components["schemas"]["ProductOut"], "id" | "code" | "name">;
/** Page the active catalogue completely; a selector must not silently stop at page one. */
export async function fetchDealProducts(): Promise<readonly DealProduct[]> {
  const products: DealProduct[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<components["schemas"]["ProductOut"]> = await fetchListPage(
      "/api/v1/products",
      { is_active: true, sort: "code" },
      cursor,
      { limit: 200, count: false },
    );
    products.push(
      ...page.items
        .filter((product) => product.is_active)
        .map(({ id, code, name }) => ({ id, code, name })),
    );
    cursor = page.nextCursor;
  } while (cursor !== null);
  return products;
}

import { api, unwrap } from "../client";
import type { components } from "../schema";

export type DealPreview = components["schemas"]["DealPreviewOut"];
export type DealInput = components["schemas"]["DealInputIn"];
export function fetchDealPreview(id: string): Promise<DealPreview> {
  return unwrap(
    api.GET("/api/v1/deal-previews/{preview_id}", { params: { path: { preview_id: id } } }),
  );
}

// Saved views (04 API-R-16, T-PLT-37; SCREENS SCR-IA-07; DESIGN_SYSTEM DS-CMP-10 saved views). The
// caller's views and the views other members share, per screen code. Only the owner renames, changes,
// shares or deletes a view.
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { useCommand } from "../commands";
import { fetchListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type SavedView = components["schemas"]["SavedViewOut"];
export type SavedViewCreate = components["schemas"]["SavedViewIn"];
export type SavedViewUpdate = components["schemas"]["SavedViewUpdateIn"];

export const SAVED_VIEWS_PATH = "/api/v1/saved-views";
const PAGE_LIMIT = 500;

export function savedViewsKey(screenCode: string): QueryKey {
  return queryKey("saved-views", "tenant", { screen_code: screenCode });
}

const EVERY_SAVED_VIEW = queryKey("saved-views", "tenant");

/** Every grid view of a screen (favourites excluded), in name order. */
export async function fetchSavedViews(screenCode: string): Promise<readonly SavedView[]> {
  const views: SavedView[] = [];
  let cursor: string | null = null;
  do {
    const page: Awaited<ReturnType<typeof fetchListPage<SavedView>>> = await fetchListPage(
      SAVED_VIEWS_PATH,
      { screen_code: screenCode, is_favourite: false, sort: "name" },
      cursor,
      { limit: PAGE_LIMIT, count: false },
    );
    views.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return views;
}

export function useSavedViews(screenCode: string) {
  return useQuery({
    queryKey: savedViewsKey(screenCode),
    queryFn: () => fetchSavedViews(screenCode),
  });
}

export function useCreateSavedView() {
  return useCommand<SavedView>({
    method: "POST",
    path: SAVED_VIEWS_PATH,
    invalidates: [EVERY_SAVED_VIEW],
  });
}

// A command keeps its Idempotency-Key while the same body is retried, so a command whose target view
// changes starts a new intent.
function useSavedViewCommand<T>(method: "PATCH" | "DELETE", viewId: string | null) {
  const command = useCommand<T>({
    method,
    path: `${SAVED_VIEWS_PATH}/${viewId ?? ""}`,
    invalidates: [EVERY_SAVED_VIEW],
  });
  const { reset } = command;
  useEffect(() => reset(), [reset, viewId]);
  return command;
}

export function useUpdateSavedView(viewId: string | null) {
  return useSavedViewCommand<SavedView>("PATCH", viewId);
}

export function useDeleteSavedView(viewId: string | null) {
  return useSavedViewCommand<null>("DELETE", viewId);
}

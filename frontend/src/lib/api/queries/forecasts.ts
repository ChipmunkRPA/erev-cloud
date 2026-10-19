import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey } from "../query-keys";
import type { components } from "../schema";

export type ForecastRun = components["schemas"]["ForecastRunOut"];
export type ForecastInput = components["schemas"]["EventSetOut"];
export type ForecastRequest = components["schemas"]["ForecastRunCreateIn"];
export const forecastRunsKey = queryKey("forecast-runs", "tenant");
export const forecastInputsKey = queryKey("forecast-event-sets", "tenant", { status: "PUBLISHED" });

export async function fetchForecastInputs(): Promise<readonly ForecastInput[]> {
  const inputs: ForecastInput[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<ForecastInput> = await fetchListPage<ForecastInput>(
      "/api/v1/forecast-event-sets",
      { status: "PUBLISHED" },
      cursor,
      { limit: 200, count: false },
    );
    inputs.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return inputs;
}

export function fetchForecastRuns(cursor: string | null = null) {
  return fetchListPage<ForecastRun>("/api/v1/forecast-runs", {}, cursor, {
    limit: 50,
    count: false,
  });
}

export function fetchForecastRun(id: string): Promise<ForecastRun> {
  return unwrap(api.GET("/api/v1/forecast-runs/{run_id}", { params: { path: { run_id: id } } }));
}

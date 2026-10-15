// SF-15:ai-call-log: server applies current tenant and actor visibility on every read.
import { api, unwrap } from "../client";
import { fetchListPage } from "../lists";
import { queryKey } from "../query-keys";
import type { components } from "../schema";

export type AIModelLog = components["schemas"]["AIModelLogOut"];
export const aiModelLogsKey = () => queryKey("ai-model-logs", "tenant");
export const aiModelLogKey = (id: string) => queryKey("ai-model-log", "tenant", { id });
export function fetchAIModelLogs(cursor: string | null, sort: string | null) {
  return fetchListPage<AIModelLog>("/api/v1/ai/model-logs", { sort }, cursor, { limit: 50 });
}
export function fetchAIModelLog(id: string): Promise<AIModelLog> {
  return unwrap(api.GET("/api/v1/ai/model-logs/{id}", { params: { path: { id } } }));
}

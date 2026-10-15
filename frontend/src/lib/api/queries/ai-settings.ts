// Administrator AI settings reads never enable AI or bypass independent approval.
import { api, unwrap } from "../client";
import { fetchListPage, type ListQuery } from "../lists";
import { queryKey, type QueryParams } from "../query-keys";
import type { components } from "../schema";

export type AISettingsStatus = components["schemas"]["AISettingsStatusOut"];
export type AISettingsVersion = components["schemas"]["PolicyOut"];
export const AI_SETTINGS_PATH = "/api/v1/ai/settings";
export const AI_SETTINGS_VERSIONS_PATH = `${AI_SETTINGS_PATH}/versions`;

export function aiSettingsKey() {
  return queryKey("ai-settings", "tenant");
}

export function aiSettingsVersionsKey(query: QueryParams = {}) {
  return queryKey("ai-settings-versions", "tenant", query);
}

export function fetchAISettings(): Promise<AISettingsStatus> {
  return unwrap(api.GET("/api/v1/ai/settings"));
}

export function fetchAISettingsVersions(query: ListQuery = {}, cursor: string | null = null) {
  return fetchListPage<AISettingsVersion>(AI_SETTINGS_VERSIONS_PATH, query, cursor);
}

export function fetchAISettingsValues(): Promise<components["schemas"]["AISettingsValuesOut"]> {
  return unwrap(api.GET("/api/v1/ai/settings/values"));
}

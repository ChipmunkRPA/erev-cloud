// Import mapping profiles (04 T-IMP-06; API-R-43 `GET, POST /import-mapping-profiles`,
// `POST /import-mapping-profiles/{id}/test`, `/submit`; PRD ACT-22; SCREENS §12.4, §11.0 header
// commands; BUILD_SPEC DIN-10, DIN-15). Integration after merge (D-81): DIN-10 builds these routes in
// the same level, so the types below follow its contract (MappingProfileOut, MappingProfileIn,
// MappingProfileSubmitIn) until `make openapi` regenerates `schema.d.ts` at the merge.
import type { CommandKeys } from "../commands";
import { fetchListPage, type ListPage } from "../lists";
import { type ApiProblem, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type MappingProfileStatus = components["schemas"]["ConfigStatus"];

/** T-IMP-06 `mappings`. */
export interface MappingProfileMappings {
  /** Source column → template column. */
  readonly aliases: Readonly<Record<string, string>>;
  /** Template column → value. */
  readonly constants: Readonly<Record<string, unknown>>;
  /** Source columns stored under `custom_attributes`. */
  readonly custom_attributes: readonly string[];
}

/** One mapping profile version (DIN-10 MappingProfileOut). */
export interface MappingProfile {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly template_code: string;
  readonly mappings: MappingProfileMappings;
  readonly version_no: number;
  readonly status: MappingProfileStatus;
  readonly effective_from: string | null;
  readonly effective_to: string | null;
  readonly content_sha256: string | null;
  readonly approval_request_id: string | null;
  readonly published_at: string | null;
  readonly published_by: string | null;
  readonly supersedes_version_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly row_version: number;
}

/** `POST /import-mapping-profiles`: the next version of a profile code, as DRAFT. */
export interface MappingProfileInput {
  readonly code: string;
  readonly name: string;
  readonly template_code: string;
  readonly mappings: MappingProfileMappings;
}

export const MAPPING_PROFILES_PATH = "/api/v1/import-mapping-profiles";
/** PRD ACT-22: mapping profiles are authored with `config.author` (approved in SF-12). */
export const CONFIG_AUTHOR_PERMISSION = "config.author";
/** DIN-10 `MappingProfileIn.code`. */
export const PROFILE_CODE_PATTERN = /^[A-Z0-9][A-Z0-9_.-]{0,63}$/;

export type ProfileAction = "test" | "submit";

export type ProfileOutcome =
  | { readonly ok: true; readonly profile: MappingProfile }
  | { readonly ok: false; readonly problem: ApiProblem };

export function mappingProfilesKey(): QueryKey {
  return queryKey("import-mapping-profiles", "tenant", { view: "list" });
}

/** Every mapping profile read, for invalidation after a command. */
export const EVERY_MAPPING_PROFILE: QueryKey = queryKey("import-mapping-profiles", "tenant");

/** One DataGrid page of `GET /import-mapping-profiles` (DG-FE-07), by code without a URL sort. */
export function fetchMappingProfilesPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<MappingProfile>> {
  return fetchListPage<MappingProfile>(MAPPING_PROFILES_PATH, { sort: sort ?? "code" }, cursor);
}

export function publishedProfilesKey(templateCode: string): QueryKey {
  return queryKey("import-mapping-profiles", "tenant", {
    view: "published",
    template_code: templateCode,
  });
}

/**
 * SCREENS §12.2 Step 1 "Mapping profile": the published profiles of a CSV v2 template (DIN-10 list
 * filters `template_code` and `status`), by code.
 */
export async function fetchPublishedProfiles(
  templateCode: string,
): Promise<readonly MappingProfile[]> {
  const page = await fetchListPage<MappingProfile>(
    MAPPING_PROFILES_PATH,
    { template_code: templateCode, status: "PUBLISHED", sort: "code" },
    null,
    { limit: 200, count: false },
  );
  return page.items;
}

/** SCREENS §11.0 header commands: DRAFT runs tests; TESTED submits or runs the tests again. */
export function profileActions(status: MappingProfileStatus): readonly ProfileAction[] {
  if (status === "DRAFT") {
    return ["test"];
  }
  if (status === "TESTED") {
    return ["submit", "test"];
  }
  return [];
}

/** One command under the key `keys` holds for it (DG-FE-05 rev 1.156); a network failure rejects. */
async function post(keys: CommandKeys, path: string, body?: unknown): Promise<ProfileOutcome> {
  const response = await keys.send("POST", path, body === undefined ? {} : { body });
  if (!response.ok) {
    return { ok: false, problem: await readProblem(response) };
  }
  return { ok: true, profile: (await response.json()) as MappingProfile };
}

export function createMappingProfile(
  keys: CommandKeys,
  input: MappingProfileInput,
): Promise<ProfileOutcome> {
  return post(keys, MAPPING_PROFILES_PATH, input);
}

export function testMappingProfile(keys: CommandKeys, profileId: string): Promise<ProfileOutcome> {
  return post(keys, `${MAPPING_PROFILES_PATH}/${profileId}/test`);
}

export function submitMappingProfile(
  keys: CommandKeys,
  profileId: string,
  comment: string | null,
): Promise<ProfileOutcome> {
  return post(keys, `${MAPPING_PROFILES_PATH}/${profileId}/submit`, { comment });
}

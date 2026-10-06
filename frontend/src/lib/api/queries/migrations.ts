// Legacy migrations (04 T-MIG-01, E-76 `migration_status`, §17.2 LM-CL-03 / LM-CL-09 rev 1.64;
// API `GET /migrations/{id}`, `POST /migrations/{id}/import`; SCREENS_B §10.3 SF-19:detail rev 1.20;
// BUILD_SPEC LMG-2). The mapping step's pure model lives here so the screen stays a thin view: which
// "Entity mapping" row is "Matched" or "Will be created", how the "Entity defaults" and the workspace's
// only calendar resolve a row's calendar and time zone (the row's own value wins), the named refusals
// of "Confirm mapping", and the `/import` body.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import type { Calendar } from "./calendars";
import type { Entity } from "./tenant";

export type Migration = components["schemas"]["MigrationOut"];
export type MigrationStatus = components["schemas"]["MigrationStatus"];
export type MigrationMode = components["schemas"]["MigrationMode"];
export type MigrationProfile = components["schemas"]["MigrationProfileOut"];
export type EntityMappingRow = components["schemas"]["EntityMappingIn"];
export type EntityDefaults = components["schemas"]["EntityDefaultsIn"];
export type OpeningBalancesImport = components["schemas"]["OpeningBalancesImportIn"];
export type SourceFile = components["schemas"]["FileOut"];

export const MIGRATIONS_PATH = "/api/v1/migrations";
/** SCREENS_B RT-52 SF-19, the Migrations tab of the Data frame. */
export const MIGRATIONS_ROUTE = "/data/migrations";
/** SCREENS_B RT-53 SF-19:detail; the screen parameter `step` selects the step (SCREENS SCR-URL-15). */
export const MIGRATION_DETAIL_ROUTE = "/data/migrations/:migrationId";
export const STEP_PARAM = "step";
/** SCREENS_B §10.3 "Roles and permissions": read and run `migration.run`; promotion `migration.approve`. */
export const MIGRATION_RUN_PERMISSION = "migration.run";
export const MIGRATION_APPROVE_PERMISSION = "migration.approve";
/** While the profile or the import job runs, the screen reads the migration again at this interval. */
export const MIGRATION_POLL_INTERVAL_MS = 2_000;

/** E-76 literals in 04 order. */
export const MIGRATION_STATUSES: readonly MigrationStatus[] = [
  "UPLOADED",
  "PROFILING",
  "PROFILED",
  "IMPORTING",
  "IMPORTED",
  "RECONCILED",
  "SUBMITTED",
  "PROMOTED",
  "FAILED",
  "CANCELLED",
];
export const RUNNING_MIGRATION_STATUSES: ReadonlySet<MigrationStatus> = new Set([
  "PROFILING",
  "IMPORTING",
]);

/** SCREENS_B §10.3 "Route": the step slugs per mode, in stepper order. */
export type OpeningBalancesStep = "profile" | "mapping" | "import" | "reconciliation" | "promotion";
export type ReplayStep = "profile" | "plan" | "replay" | "reconciliation" | "promotion";
export type MigrationStep = OpeningBalancesStep | ReplayStep;
export const OPENING_BALANCES_STEPS: readonly OpeningBalancesStep[] = [
  "profile",
  "mapping",
  "import",
  "reconciliation",
  "promotion",
];
export const REPLAY_STEPS: readonly ReplayStep[] = [
  "profile",
  "plan",
  "replay",
  "reconciliation",
  "promotion",
];

/** The steps this build renders (F-ADM, SCREENS_B 1.20 WEB item, option A): J-20.2 and J-20.3 only. */
export const BUILT_STEPS: ReadonlySet<MigrationStep> = new Set<MigrationStep>([
  "mapping",
  "import",
]);

export function isBuiltStep(mode: MigrationMode, step: MigrationStep): boolean {
  return mode === "OPENING_BALANCES" && BUILT_STEPS.has(step);
}

export function stepsOf(mode: MigrationMode): readonly MigrationStep[] {
  return mode === "REPLAY" ? REPLAY_STEPS : OPENING_BALANCES_STEPS;
}

export function isMigrationStep(mode: MigrationMode, value: string | null): value is MigrationStep {
  return value !== null && (stepsOf(mode) as readonly string[]).includes(value);
}

/**
 * The step a status opens on (the stepper's current step): the profile while profiling, the mapping
 * (or the replay plan) once profiled, the import (or replay) while it runs and once imported, the
 * reconciliation once reconciled, the promotion once submitted or promoted. A FAILED batch is told apart
 * by its profile (F-LMG, 2026-09-21; SCREENS_B row 1.22): the profile is written only when profiling
 * completes, so a FAILED batch WITHOUT a profile failed while profiling and opens on the Profile step
 * with its SCR-ST-12 banner; a FAILED batch WITH a profile failed in the import phase and opens on the
 * import (or replay) step. The reconcile job never fails the batch. A CANCELLED batch opens on the
 * import (or replay) step.
 */
export function stepOfStatus(
  mode: MigrationMode,
  status: MigrationStatus,
  profile: MigrationProfile | null = null,
): MigrationStep {
  const replay = mode === "REPLAY";
  switch (status) {
    case "UPLOADED":
    case "PROFILING":
      return "profile";
    case "PROFILED":
      return replay ? "plan" : "mapping";
    case "RECONCILED":
      return "reconciliation";
    case "SUBMITTED":
    case "PROMOTED":
      return "promotion";
    case "FAILED":
      if (profile === null) {
        return "profile";
      }
      return replay ? "replay" : "import";
    default:
      return replay ? "replay" : "import";
  }
}

export function migrationRoute(migrationId: string): string {
  return `${MIGRATIONS_ROUTE}/${encodeURIComponent(migrationId)}`;
}

export function migrationStepRoute(migrationId: string, step: MigrationStep): string {
  return `${migrationRoute(migrationId)}?${STEP_PARAM}=${step}`;
}

export function migrationImportPath(migrationId: string): string {
  return `${MIGRATIONS_PATH}/${encodeURIComponent(migrationId)}/import`;
}

/** Every migration read, for invalidation after a command. */
export const EVERY_MIGRATION: QueryKey = queryKey("migrations", "tenant");

export function migrationKey(migrationId: string): QueryKey {
  return queryKey("migrations", "tenant", { id: migrationId });
}

export function fetchMigration(migrationId: string): Promise<Migration> {
  return unwrap(
    api.GET("/api/v1/migrations/{migration_id}", {
      params: { path: { migration_id: migrationId } },
    }),
  );
}

/** The migration, read again at the poll interval while its profile or import job runs. */
export function useMigration(migrationId: string) {
  return useQuery({
    queryKey: migrationKey(migrationId),
    queryFn: () => fetchMigration(migrationId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data !== undefined && RUNNING_MIGRATION_STATUSES.has(query.state.data.status)
        ? MIGRATION_POLL_INTERVAL_MS
        : false,
  });
}

export function sourceFileKey(fileId: string): QueryKey {
  return queryKey("files", "tenant", { id: fileId });
}

/** The T-PLT file row of the migration's source (`original_filename` for the header meta). */
export function fetchSourceFile(fileId: string): Promise<SourceFile> {
  return unwrap(api.GET("/api/v1/files/{file_id}", { params: { path: { file_id: fileId } } }));
}

export function useSourceFile(fileId: string | null) {
  return useQuery({
    queryKey: sourceFileKey(fileId ?? ""),
    queryFn: () => fetchSourceFile(fileId ?? ""),
    enabled: fileId !== null,
    retry: false,
  });
}

// ---- the read-only "Field mapping" table (§10.3; 04 API-R-48 rev 1.66; D-98 133 AMENDMENT 1 (b)) -----

/**
 * One row of `GET /migrations/field-mapping` (operation `migrations_field_mapping`, F-LMG-API-2 on main
 * 7064160c): the 71 rows of 04 §17.2 as data — `id` "LM-CL-nn", `legacy_column` (the exact legacy
 * text), `target` (the §17.2 target), `rule` (the transformation / export rule). The screen renders the
 * rows verbatim — the legacy names are API data, not product copy (REQ-UX-010 untouched).
 */
export type FieldMappingRow = components["schemas"]["FieldMappingRowOut"];
export type FieldMapping = components["schemas"]["FieldMappingOut"];

export const FIELD_MAPPING_PATH = `${MIGRATIONS_PATH}/field-mapping`;

export function fieldMappingKey(): QueryKey {
  return queryKey("migrations", "tenant", { view: "field-mapping" });
}

function isFieldMappingRow(value: unknown): value is FieldMappingRow {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const row = value as Record<string, unknown>;
  return (
    typeof row.id === "string" &&
    typeof row.legacy_column === "string" &&
    typeof row.target === "string" &&
    typeof row.rule === "string"
  );
}

/**
 * The 71 rows in legacy order through the typed client; the body is still checked structurally — the
 * generated types describe the contract, they do not validate a response — so a malformed body is an
 * error by name, never a guess.
 */
export async function fetchFieldMapping(): Promise<readonly FieldMappingRow[]> {
  const body: unknown = await unwrap(api.GET("/api/v1/migrations/field-mapping"));
  const rows = typeof body === "object" && body !== null ? (body as { rows?: unknown }).rows : null;
  if (!Array.isArray(rows) || !rows.every(isFieldMappingRow)) {
    throw new Error(`Unexpected field-mapping body from ${FIELD_MAPPING_PATH}`);
  }
  return rows;
}

export function useFieldMapping(enabled = true) {
  return useQuery({
    queryKey: fieldMappingKey(),
    queryFn: fetchFieldMapping,
    enabled,
    retry: false,
  });
}

// ---- the mapping step (J-20.2) model ------------------------------------------------------------

/** SCREENS_B §10.3 "Entity mapping" → "Status": "Matched" or "Will be created". */
export type MappingStatus = "MATCHED" | "WILL_BE_CREATED";

/** One "Entity mapping" row as the user edits it; `null` inputs fall back to the defaults. */
export interface MappingRow {
  /** "Legacy Selling Entity", exact text (LM-CL-09). */
  readonly legacyName: string;
  /** "Entity": the target code; the identity mapping (legacy text = code) until edited. */
  readonly entityCode: string;
  readonly calendarId: string | null;
  readonly timeZone: string | null;
}

/** The DS-CMP-21 field group "Entity defaults" above the table (rev 1.20). */
export interface EntityDefaultsState {
  readonly calendarId: string | null;
  readonly timeZone: string | null;
}

/** "Batch parameters" (POL-211, POL-212 editable; POL-213, POL-214 forced) and the rev 1.20 toggle. */
export interface BatchParametersState {
  readonly nondistinctMapping: string;
  readonly materialRightConvention: string;
  readonly createMissingProducts: boolean;
}

/** A refusal of "Confirm mapping" by name (Codex 1106 R2): the row, the field and the §10.3 copy. */
export interface MappingRefusal {
  readonly legacyName: string;
  readonly field: "calendar_id" | "time_zone";
}

export const NONDISTINCT_MAPPING_KEY = "migration.nondistinct_mapping";
export const MATERIAL_RIGHT_CONVENTION_KEY = "migration.material_right_convention";
export const LEGACY_VC_ROWS_KEY = "migration.legacy_vc_rows";
export const SPLIT_UPLOAD_ALLOCATION_KEY = "migration.split_upload_allocation";
/** §10.3 preset values: POL-211 `SINGLE_POB`, POL-212 `KEEP_QUANTITY_CONVENTION`. */
export const NONDISTINCT_MAPPING_PRESET = "SINGLE_POB";
export const MATERIAL_RIGHT_CONVENTION_PRESET = "KEEP_QUANTITY_CONVENTION";
/** §10.3 forced, read-only values of POL-213 and POL-214. */
export const LEGACY_VC_ROWS_FORCED = "VC_ELEMENT_PLUS_CREDIT_EVENTS";
export const SPLIT_UPLOAD_ALLOCATION_FORCED = "ALLOCATE_ACROSS_ALL_POBS";

/** The identity rows of the profile's selling entities, in profile order (every entity is listed). */
export function identityRows(profile: Pick<MigrationProfile, "selling_entities">): MappingRow[] {
  return profile.selling_entities.map((name) => ({
    legacyName: name,
    entityCode: name,
    calendarId: null,
    timeZone: null,
  }));
}

/** The workspace's only calendar when exactly one exists, else null (§10.3 "Calendar" default). */
export function onlyCalendarId(calendars: readonly Calendar[]): string | null {
  return calendars.length === 1 ? (calendars[0]?.id ?? null) : null;
}

/** The workspace entity a row targets, by exact code, or null for a "Will be created" row. */
export function matchedEntity(row: MappingRow, entities: readonly Entity[]): Entity | null {
  return entities.find((entity) => entity.code === row.entityCode) ?? null;
}

export function mappingStatus(row: MappingRow, entities: readonly Entity[]): MappingStatus {
  return matchedEntity(row, entities) === null ? "WILL_BE_CREATED" : "MATCHED";
}

/**
 * The calendar a "Will be created" row resolves to: its own value, else the "Entity defaults" value,
 * else the workspace's only calendar (04 §17.2 LM-CL-09 rev 1.64); null when none resolves.
 */
export function resolvedCalendarId(
  row: MappingRow,
  defaults: EntityDefaultsState,
  calendars: readonly Calendar[],
): string | null {
  return row.calendarId ?? defaults.calendarId ?? onlyCalendarId(calendars);
}

/** The time zone a "Will be created" row resolves to: its own value, else the "Entity defaults" value. */
export function resolvedTimeZone(row: MappingRow, defaults: EntityDefaultsState): string | null {
  return row.timeZone ?? defaults.timeZone;
}

/**
 * "Confirm mapping" is refused by name while a "Will be created" row has no calendar or time zone
 * (§10.3, Codex 1106 R2): one refusal per missing field per row, in row order. "Matched" rows carry the
 * entity's own values and are never refused here.
 */
export function mappingRefusals(
  rows: readonly MappingRow[],
  defaults: EntityDefaultsState,
  calendars: readonly Calendar[],
  entities: readonly Entity[],
): readonly MappingRefusal[] {
  const refusals: MappingRefusal[] = [];
  for (const row of rows) {
    if (mappingStatus(row, entities) === "MATCHED") {
      continue;
    }
    if (resolvedCalendarId(row, defaults, calendars) === null) {
      refusals.push({ legacyName: row.legacyName, field: "calendar_id" });
    }
    if (resolvedTimeZone(row, defaults) === null) {
      refusals.push({ legacyName: row.legacyName, field: "time_zone" });
    }
  }
  return refusals;
}

/** The distinct target codes of the rows, in first-seen order (rows sharing a target are ONE entity). */
export function targetCodes(rows: readonly MappingRow[]): readonly string[] {
  return [...new Set(rows.map((row) => row.entityCode))];
}

/**
 * The `POST /migrations/{id}/import` body of D-31 mode (a) (§10.3 data binding rev 1.20): every row of
 * the table with the values the user set on it (a row's own value wins over the defaults; an unset value
 * is omitted so the API applies `entity_defaults`), the defaults as entered, the two editable batch
 * parameters and the toggles. `create_missing_entities` has no control on the screen and keeps the API
 * default (true).
 */
export function importBody(
  cutoverDate: string,
  rows: readonly MappingRow[],
  defaults: EntityDefaultsState,
  parameters: BatchParametersState,
): OpeningBalancesImport {
  const entityMapping: EntityMappingRow[] = rows.map((row) => ({
    legacy_name: row.legacyName,
    entity_code: row.entityCode,
    ...(row.calendarId === null ? {} : { calendar_id: row.calendarId }),
    ...(row.timeZone === null ? {} : { time_zone: row.timeZone }),
  }));
  const entityDefaults: EntityDefaults = {
    ...(defaults.calendarId === null ? {} : { calendar_id: defaults.calendarId }),
    ...(defaults.timeZone === null ? {} : { time_zone: defaults.timeZone }),
  };
  return {
    mode: "OPENING_BALANCES",
    cutover_date: cutoverDate,
    entity_mapping: entityMapping,
    entity_defaults: Object.keys(entityDefaults).length === 0 ? null : entityDefaults,
    batch_parameters: {
      [NONDISTINCT_MAPPING_KEY]: parameters.nondistinctMapping,
      [MATERIAL_RIGHT_CONVENTION_KEY]: parameters.materialRightConvention,
    },
    create_missing_entities: true,
    create_missing_products: parameters.createMissingProducts,
  };
}

/** The `entity_mapping[<index>]` row index of a 422 field name, or null for a batch-level finding. */
export function findingRowIndex(field: string | null): number | null {
  const match = field === null ? null : /^entity_mapping\[(\d+)\]/.exec(field);
  return match?.[1] === undefined ? null : Number(match[1]);
}

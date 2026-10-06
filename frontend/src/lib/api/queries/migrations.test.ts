// @vitest-environment jsdom
// The mapping step model of SF-19:detail (SCREENS_B §10.3 rev 1.20; 04 §17.2 LM-CL-09 / LM-CL-03 rev
// 1.64): defaults resolve in the documented order, "Confirm mapping" is refused by name, and the
// `/import` body carries what the user set and nothing invented.
import { describe, expect, it } from "vitest";

import type { Calendar } from "./calendars";
import {
  type BatchParametersState,
  findingRowIndex,
  identityRows,
  importBody,
  isMigrationStep,
  mappingRefusals,
  mappingStatus,
  migrationImportPath,
  migrationStepRoute,
  onlyCalendarId,
  resolvedCalendarId,
  resolvedTimeZone,
  stepOfStatus,
  targetCodes,
} from "./migrations";
import type { Entity } from "./tenant";

const MONTHLY: Calendar = {
  id: "ca1ca1ca-ca1c-4ca1-8ca1-ca1ca1ca1ca1",
  code: "MONTHLY",
  name: "Monthly, fiscal year starts January",
  pattern: "MONTHLY",
  fiscal_year_start_month: 1,
  week_end_day: null,
  year_end_anchor: null,
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const MONTHLY_AP: Calendar = {
  ...MONTHLY,
  id: "ca2ca2ca-ca2c-4ca2-8ca2-ca2ca2ca2ca2",
  code: "MONTHLY-AP",
};

const PEMBREY = {
  id: "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1",
  code: "Mock Entity 1",
  name: "Mock Entity 1",
  functional_currency: "USD",
  calendar_id: MONTHLY.id,
  time_zone: "America/New_York",
  is_active: true,
  country_code: null,
  tax_id: null,
  parent_entity_id: null,
  books: [],
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as unknown as Entity;

const PARAMETERS: BatchParametersState = {
  nondistinctMapping: "SINGLE_POB",
  materialRightConvention: "KEEP_QUANTITY_CONVENTION",
  createMissingProducts: true,
};

const NO_DEFAULTS = { calendarId: null, timeZone: null };
const MATCHED_ROW = {
  legacyName: "Mock Entity 1",
  entityCode: "Mock Entity 1",
  calendarId: null,
  timeZone: null,
};
const CREATED_ROW = { ...MATCHED_ROW, legacyName: "Mock Entity 2", entityCode: "Mock Entity 2" };

describe("SF-19:detail mapping step model (SCREENS_B §10.3 rev 1.20)", () => {
  it("lists every selling entity of the profile as its identity mapping", () => {
    expect(identityRows({ selling_entities: ["Mock Entity 1", "Mock Entity 2"] })).toEqual([
      MATCHED_ROW,
      CREATED_ROW,
    ]);
  });

  it("defaults the calendar to the workspace's only calendar and to nothing otherwise", () => {
    expect(onlyCalendarId([MONTHLY])).toBe(MONTHLY.id);
    expect(onlyCalendarId([MONTHLY, MONTHLY_AP])).toBeNull();
    expect(onlyCalendarId([])).toBeNull();
  });

  it("marks a row Matched by exact entity code and Will be created otherwise", () => {
    expect(mappingStatus(MATCHED_ROW, [PEMBREY])).toBe("MATCHED");
    expect(mappingStatus(CREATED_ROW, [PEMBREY])).toBe("WILL_BE_CREATED");
    // Exact text: a case difference is another code (LM-CL-09 maps by exact text).
    expect(mappingStatus({ ...CREATED_ROW, entityCode: "mock entity 1" }, [PEMBREY])).toBe(
      "WILL_BE_CREATED",
    );
  });

  it("resolves a row's calendar and time zone: own value, else defaults, else the only calendar", () => {
    expect(resolvedCalendarId(CREATED_ROW, NO_DEFAULTS, [MONTHLY])).toBe(MONTHLY.id);
    expect(resolvedCalendarId(CREATED_ROW, NO_DEFAULTS, [MONTHLY, MONTHLY_AP])).toBeNull();
    const defaults = { calendarId: MONTHLY_AP.id, timeZone: "Europe/London" };
    expect(resolvedCalendarId(CREATED_ROW, defaults, [MONTHLY, MONTHLY_AP])).toBe(MONTHLY_AP.id);
    expect(
      resolvedCalendarId({ ...CREATED_ROW, calendarId: MONTHLY.id }, defaults, [
        MONTHLY,
        MONTHLY_AP,
      ]),
    ).toBe(MONTHLY.id);
    expect(resolvedTimeZone(CREATED_ROW, NO_DEFAULTS)).toBeNull();
    expect(resolvedTimeZone(CREATED_ROW, defaults)).toBe("Europe/London");
    expect(resolvedTimeZone({ ...CREATED_ROW, timeZone: "Asia/Tokyo" }, defaults)).toBe(
      "Asia/Tokyo",
    );
  });

  it("refuses Confirm mapping by name for every Will be created row lacking a calendar or time zone", () => {
    const rows = identityRows({
      selling_entities: ["Mock Entity 1", "Mock Entity 2", "Mock Entity 3"],
    });
    // Two calendars: nothing defaults; Mock Entity 1 is Matched and never refused.
    expect(mappingRefusals(rows, NO_DEFAULTS, [MONTHLY, MONTHLY_AP], [PEMBREY])).toEqual([
      { legacyName: "Mock Entity 2", field: "calendar_id" },
      { legacyName: "Mock Entity 2", field: "time_zone" },
      { legacyName: "Mock Entity 3", field: "calendar_id" },
      { legacyName: "Mock Entity 3", field: "time_zone" },
    ]);
    // The defaults resolve both fields for every created row.
    const defaults = { calendarId: MONTHLY.id, timeZone: "Europe/London" };
    expect(mappingRefusals(rows, defaults, [MONTHLY, MONTHLY_AP], [PEMBREY])).toEqual([]);
    // One calendar and a row-level time zone on one row: the other created row still lacks its zone.
    const withZone = rows.map((row) =>
      row.legacyName === "Mock Entity 2" ? { ...row, timeZone: "Asia/Tokyo" } : row,
    );
    expect(mappingRefusals(withZone, NO_DEFAULTS, [MONTHLY], [PEMBREY])).toEqual([
      { legacyName: "Mock Entity 3", field: "time_zone" },
    ]);
  });

  it("consolidates rows sharing a target into one code, in first-seen order", () => {
    const rows = identityRows({ selling_entities: ["Mock Entity 1", "Mock Entity 2"] }).map(
      (row) => ({ ...row, entityCode: "GROUP" }),
    );
    expect(targetCodes(rows)).toEqual(["GROUP"]);
    expect(targetCodes(identityRows({ selling_entities: ["A", "B", "A"] }))).toEqual(["A", "B"]);
  });

  it("builds the /import body from what the user set and invents no value", () => {
    const rows = identityRows({ selling_entities: ["Mock Entity 1", "Mock Entity 2"] }).map(
      (row) => (row.legacyName === "Mock Entity 2" ? { ...row, timeZone: "Asia/Tokyo" } : row),
    );
    const defaults = { calendarId: MONTHLY.id, timeZone: null };
    expect(importBody("2023-01-31", rows, defaults, PARAMETERS)).toEqual({
      mode: "OPENING_BALANCES",
      cutover_date: "2023-01-31",
      entity_mapping: [
        { legacy_name: "Mock Entity 1", entity_code: "Mock Entity 1" },
        { legacy_name: "Mock Entity 2", entity_code: "Mock Entity 2", time_zone: "Asia/Tokyo" },
      ],
      entity_defaults: { calendar_id: MONTHLY.id },
      batch_parameters: {
        "migration.nondistinct_mapping": "SINGLE_POB",
        "migration.material_right_convention": "KEEP_QUANTITY_CONVENTION",
      },
      create_missing_entities: true,
      create_missing_products: true,
    });
    const body = importBody("2023-01-31", rows, NO_DEFAULTS, {
      ...PARAMETERS,
      createMissingProducts: false,
    });
    expect(body.entity_defaults).toBeNull();
    expect(body.create_missing_products).toBe(false);
  });

  it("maps a 422 field name to its Entity mapping row", () => {
    expect(findingRowIndex("entity_mapping[0].calendar_id")).toBe(0);
    expect(findingRowIndex("entity_mapping[12].time_zone")).toBe(12);
    expect(findingRowIndex("entity_defaults.calendar_id")).toBeNull();
    expect(findingRowIndex("migration_id")).toBeNull();
    expect(findingRowIndex(null)).toBeNull();
  });

  it("names the steps of each mode and opens a status on its step", () => {
    expect(isMigrationStep("OPENING_BALANCES", "mapping")).toBe(true);
    expect(isMigrationStep("OPENING_BALANCES", "plan")).toBe(false);
    expect(isMigrationStep("REPLAY", "plan")).toBe(true);
    expect(isMigrationStep("REPLAY", null)).toBe(false);
    expect(stepOfStatus("OPENING_BALANCES", "PROFILED")).toBe("mapping");
    expect(stepOfStatus("REPLAY", "PROFILED")).toBe("plan");
    expect(stepOfStatus("OPENING_BALANCES", "IMPORTING")).toBe("import");
    expect(stepOfStatus("OPENING_BALANCES", "RECONCILED")).toBe("reconciliation");
    expect(stepOfStatus("OPENING_BALANCES", "PROMOTED")).toBe("promotion");
    // A FAILED batch: without a profile it failed while profiling; with one, in the import phase.
    expect(stepOfStatus("OPENING_BALANCES", "FAILED")).toBe("profile");
    expect(stepOfStatus("OPENING_BALANCES", "FAILED", null)).toBe("profile");
    expect(stepOfStatus("REPLAY", "FAILED", null)).toBe("profile");
    const profile = {
      source_sha256: "",
      tables: {},
      contract_live_rows: 24,
      contracts: 4,
      legacy_pob_rows: 16,
      sku_ssp_rows: 7,
      ssp_versions: [],
      version_tokens: [],
      selling_entities: ["Mock Entity 1"],
      latest_current_period: "2023-01-31",
    };
    expect(stepOfStatus("OPENING_BALANCES", "FAILED", profile)).toBe("import");
    expect(stepOfStatus("REPLAY", "FAILED", profile)).toBe("replay");
    expect(stepOfStatus("OPENING_BALANCES", "CANCELLED", null)).toBe("import");
    expect(migrationStepRoute("m1", "mapping")).toBe("/data/migrations/m1?step=mapping");
    expect(migrationImportPath("m1")).toBe("/api/v1/migrations/m1/import");
  });
});

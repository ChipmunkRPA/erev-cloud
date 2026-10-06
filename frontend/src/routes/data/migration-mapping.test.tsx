// @vitest-environment jsdom
// SF-19:detail step "Mapping (opening balances)" (SCREENS_B §10.3 rev 1.20; J-20.2): every selling entity
// is listed; a "Matched" row shows the entity's calendar and time zone read-only; a "Will be created"
// row takes the rev 1.20 inputs; "Confirm mapping" is refused by name while such a row has no calendar
// or time zone; the toggle "Create missing products" is on by default with its helper text; a refused
// `/import` shows each finding verbatim.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiProblem } from "../../lib/api/problems";
import type { Calendar } from "../../lib/api/queries/calendars";
import { importBody, type Migration } from "../../lib/api/queries/migrations";
import type { Entity } from "../../lib/api/queries/tenant";
import { installMemoryStorage, renderWithApp } from "../../test/app";
import {
  type FieldMappingState,
  type MappingConfirmation,
  MigrationMappingStep,
} from "./migration-mapping";

installMemoryStorage();

afterEach(() => {
  cleanup();
});

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
  name: "Monthly, fiscal year starts April",
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

const MIGRATION = {
  id: "m1m1m1m1-m1m1-4m1m-8m1m-m1m1m1m1m1m1",
  migration_no: "MIG-000001",
  mode: "OPENING_BALANCES",
  status: "PROFILED",
  source_file_id: "f1f1f1f1-f1f1-4f1f-8f1f-f1f1f1f1f1f1",
  source_sha256: "1f09c2aa000000000000000000000000000000000000000000000000000009ce2",
  cutover_date: null,
  import_upload_ids: [],
  job_id: null,
  problem: null,
  profile: {
    source_sha256: "1f09c2aa000000000000000000000000000000000000000000000000000009ce2",
    tables: { Contract_Live: 24, SKU_SSP: 7 },
    contract_live_rows: 24,
    contracts: 4,
    legacy_pob_rows: 16,
    sku_ssp_rows: 7,
    ssp_versions: ["2023-01-01"],
    version_tokens: [],
    selling_entities: ["Mock Entity 1", "Mock Entity 2"],
    latest_current_period: "2023-01-31",
  },
  registry_version_id: null,
  reconciliation_report_run_id: null,
  approval_request_id: null,
  sandbox_tenant_id: null,
  unexplained_count: null,
  row_version: 1,
  created_by: { id: "u1", display_name: "Maya Chen" },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  started_at: null,
  finished_at: null,
} as unknown as Migration;

// Synthetic legacy column names: the real ones are API data the frontend never holds (REQ-UX-010).
const FIELD_MAPPING = [
  {
    id: "LM-CL-01",
    legacy_column: "Legacy column 1",
    target: "contract.external_id",
    rule: "Exact text.",
  },
  { id: "LM-CL-02", legacy_column: "Legacy column 2", target: "customer.code", rule: "Trimmed." },
];

function renderStep(options: {
  readonly fieldMapping?: FieldMappingState;
  readonly calendars?: readonly Calendar[];
  readonly problem?: ApiProblem | null;
  readonly initial?: MappingConfirmation | null;
  readonly onConfirm?: (confirmation: MappingConfirmation) => void;
}) {
  const onConfirm = options.onConfirm ?? vi.fn();
  renderWithApp(
    <MigrationMappingStep
      migration={MIGRATION}
      calendars={options.calendars ?? [MONTHLY, MONTHLY_AP]}
      entities={[PEMBREY]}
      nondistinctOptions={["SINGLE_POB", "SERIES", "REVIEW_QUEUE"]}
      materialRightOptions={["CONVERT_TO_OPTION_RECORD", "KEEP_QUANTITY_CONVENTION"]}
      fieldMapping={options.fieldMapping ?? { kind: "ready", rows: FIELD_MAPPING }}
      problem={options.problem ?? null}
      initial={options.initial ?? null}
      onConfirm={onConfirm}
    />,
  );
  return onConfirm;
}

describe("SF-19:detail mapping step (SCREENS_B §10.3 rev 1.20)", () => {
  it("lists every selling entity with the rev 1.20 columns, the notice, the defaults and the toggle", async () => {
    renderStep({});
    // §10.3 locator: status "The legacy-parity preset will apply …", hook SF-19-banner-preset (a live
    // banner: the region is inserted after load; its role carries no name from content).
    const notice = await within(screen.getByTestId("SF-19-banner-preset")).findByRole("status");
    expect(
      within(notice).getByText(
        "The legacy-parity preset will apply to this workspace when the migration is promoted.",
      ),
    ).toBeTruthy();
    const group = screen.getByRole("group", { name: "Entity defaults" });
    expect(within(group).getByText("Calendar")).toBeTruthy();
    expect(within(group).getByText("Time zone")).toBeTruthy();

    const table = screen.getByTestId("SF-19-grid-entity-mapping");
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual(["Legacy Selling Entity", "Entity", "Calendar", "Time zone", "Status"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    // The Matched row shows the entity's own calendar and time zone read-only.
    const matched = rows[0] as HTMLElement;
    expect(within(matched).getByText("Matched")).toBeTruthy();
    expect(within(matched).getByText("MONTHLY · Monthly, fiscal year starts January")).toBeTruthy();
    expect(within(matched).getByText("America/New_York")).toBeTruthy();
    expect(within(matched).queryByRole("combobox")).toBeNull();
    // The Will be created row takes a calendar (select) and a time zone (combobox).
    const created = rows[1] as HTMLElement;
    expect(within(created).getByText("Will be created")).toBeTruthy();
    expect(
      within(created).getByRole("combobox", { name: "Calendar for Mock Entity 2" }),
    ).toBeTruthy();
    expect(
      within(created).getByRole("combobox", { name: "Time zone for Mock Entity 2" }),
    ).toBeTruthy();

    const toggle = screen.getByRole("switch", { name: "Create missing products" });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect(
      screen.getByText(
        "Products absent from this workspace are created from the legacy SKU name with the parity template of their rows; a SKU mapped to two templates is refused.",
      ),
    ).toBeTruthy();
    // The cutover date defaults to the latest Current Period.
    expect((screen.getByLabelText("Cutover date") as HTMLInputElement).value).toBe("31 Jan 2023");
  });

  it("refuses Confirm mapping by name while a Will be created row has no calendar or time zone", () => {
    const onConfirm = renderStep({});
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getAllByText("Choose a calendar for Mock Entity 2.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Choose a time zone for Mock Entity 2.").length).toBeGreaterThan(0);
  });

  it("defaults the calendar to the workspace's only calendar, so only the time zone is refused", () => {
    const onConfirm = renderStep({ calendars: [MONTHLY] });
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByText("Choose a calendar for Mock Entity 2.")).toBeNull();
    expect(screen.getAllByText("Choose a time zone for Mock Entity 2.").length).toBeGreaterThan(0);
  });

  it("confirms with the Entity defaults applied and hands the host an /import-ready confirmation", () => {
    const onConfirm = vi.fn();
    renderStep({
      onConfirm,
      initial: {
        migrationId: MIGRATION.id,
        cutoverDate: "2023-01-31",
        rows: [
          {
            legacyName: "Mock Entity 1",
            entityCode: "Mock Entity 1",
            calendarId: null,
            timeZone: null,
          },
          {
            legacyName: "Mock Entity 2",
            entityCode: "Mock Entity 2",
            calendarId: null,
            timeZone: null,
          },
        ],
        defaults: { calendarId: MONTHLY_AP.id, timeZone: "Europe/London" },
        parameters: {
          nondistinctMapping: "SINGLE_POB",
          materialRightConvention: "KEEP_QUANTITY_CONVENTION",
          createMissingProducts: true,
        },
      },
    });
    fireEvent.click(screen.getByRole("switch", { name: "Create missing products" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    const confirmation = onConfirm.mock.calls[0]?.[0] as MappingConfirmation;
    expect(
      importBody(
        confirmation.cutoverDate,
        confirmation.rows,
        confirmation.defaults,
        confirmation.parameters,
      ),
    ).toEqual({
      mode: "OPENING_BALANCES",
      cutover_date: "2023-01-31",
      entity_mapping: [
        { legacy_name: "Mock Entity 1", entity_code: "Mock Entity 1" },
        { legacy_name: "Mock Entity 2", entity_code: "Mock Entity 2" },
      ],
      entity_defaults: { calendar_id: MONTHLY_AP.id, time_zone: "Europe/London" },
      batch_parameters: {
        "migration.nondistinct_mapping": "SINGLE_POB",
        "migration.material_right_convention": "KEEP_QUANTITY_CONVENTION",
      },
      create_missing_entities: true,
      create_missing_products: false,
    });
  });

  it("applies a picked Entity defaults calendar to every Will be created row without its own", () => {
    renderStep({});
    const group = screen.getByRole("group", { name: "Entity defaults" });
    fireEvent.click(within(group).getByRole("combobox", { name: /^Calendar/ }));
    fireEvent.mouseDown(
      screen.getByRole("option", { name: "MONTHLY-AP · Monthly, fiscal year starts April" }),
    );
    const table = screen.getByTestId("SF-19-grid-entity-mapping");
    const rowSelect = within(table).getByRole("combobox", { name: "Calendar for Mock Entity 2" });
    expect(rowSelect.textContent).toContain("MONTHLY-AP · Monthly, fiscal year starts April");
    // The Matched row keeps the entity's own calendar.
    expect(within(table).getByText("MONTHLY · Monthly, fiscal year starts January")).toBeTruthy();
  });

  it("retargets a row to an existing entity code, which makes it Matched", () => {
    renderStep({});
    const input = screen.getByRole("textbox", { name: "Entity for Mock Entity 2" });
    fireEvent.change(input, { target: { value: "Mock Entity 1" } });
    const table = screen.getByTestId("SF-19-grid-entity-mapping");
    expect(within(table).getAllByText("Matched")).toHaveLength(2);
    expect(within(table).queryByText("Will be created")).toBeNull();
  });

  it("refuses a cutover date after the latest legacy period, by name", () => {
    const onConfirm = renderStep({ calendars: [MONTHLY] });
    const cutover = screen.getByLabelText("Cutover date");
    fireEvent.change(cutover, { target: { value: "15 Feb 2023" } });
    fireEvent.blur(cutover);
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(
      screen.getAllByText("Choose a cutover date on or before the latest legacy period.").length,
    ).toBeGreaterThan(0);
  });

  it("keeps every finding (Codex 1546 R1): legacy_name-only, several on one field, mixed mapped and unmapped", () => {
    const finding = (field: string | null, message: string, rule = "LM-CL-09") => ({
      field,
      sheet: null,
      row: null,
      rule_id: rule,
      message,
    });
    const problemOf = (errors: ReturnType<typeof finding>[]) =>
      new ApiProblem({
        type: "https://erev.dev/problems/validation-failed",
        slug: "validation-failed",
        title: "Validation failed",
        status: 422,
        detail: null,
        code: null,
        requestId: null,
        errors,
      });
    // (1) ONE finding on a field this step renders no control for: it must not disappear.
    renderStep({
      problem: problemOf([
        finding(
          "entity_mapping[1].legacy_name",
          "Entity mapping names 'Mock Entity 9', which is not a selling entity of the legacy database.",
        ),
      ]),
    });
    let banner = screen.getByTestId("SF-19-banner-import-refused");
    expect(within(banner).getAllByTestId("SF-19-import-finding")).toHaveLength(1);
    expect(
      within(banner).getByText(
        "Entity mapping names 'Mock Entity 9', which is not a selling entity of the legacy database.",
      ),
    ).toBeTruthy();
    expect(within(banner).getByText("entity_mapping[1].legacy_name")).toBeTruthy();
    cleanup();
    // (2) Several findings on the same field: every one shows inline, in order.
    renderStep({
      problem: problemOf([
        finding("entity_mapping[1].time_zone", "Choose a time zone for Mock Entity 2."),
        finding(
          "entity_mapping[1].time_zone",
          "Rows mapped to entity code 'Mock Entity 2' disagree on the time zone ('A' vs 'B'); confirm one time zone for that entity.",
        ),
      ]),
    });
    let table = screen.getByTestId("SF-19-grid-entity-mapping");
    expect(within(table).getByText("Choose a time zone for Mock Entity 2.")).toBeTruthy();
    expect(
      within(table).getByText(
        "Rows mapped to entity code 'Mock Entity 2' disagree on the time zone ('A' vs 'B'); confirm one time zone for that entity.",
      ),
    ).toBeTruthy();
    expect(screen.queryAllByTestId("SF-19-import-finding")).toHaveLength(0);
    cleanup();
    // (3) Mixed: the mapped finding inline, the unmapped ones (a row outside the table, the batch) in the banner.
    renderStep({
      problem: problemOf([
        finding("entity_mapping[1].calendar_id", "Choose a calendar for Mock Entity 2."),
        finding("entity_mapping[7].calendar_id", "Choose a calendar for Mock Entity 8."),
        finding("entity_mapping", "Entity mapping is incomplete."),
        finding(
          "migration_id",
          "SKU Widget maps to two templates (LEGACY-DISTINCT, LEGACY-NONDISTINCT); resolve it in the legacy database before importing.",
          "LM-CL-03",
        ),
      ]),
    });
    table = screen.getByTestId("SF-19-grid-entity-mapping");
    expect(within(table).getByText("Choose a calendar for Mock Entity 2.")).toBeTruthy();
    banner = screen.getByTestId("SF-19-banner-import-refused");
    const shown = within(banner)
      .getAllByTestId("SF-19-import-finding")
      .map((node) => node.textContent ?? "");
    expect(shown).toHaveLength(3);
    expect(shown[0]).toContain("entity_mapping[7].calendar_id");
    expect(shown[0]).toContain("Choose a calendar for Mock Entity 8.");
    expect(shown[1]).toContain("Entity mapping is incomplete.");
    expect(shown[2]).toContain("SKU Widget maps to two templates");
  });

  it("shows a lone POL-211 / POL-212 refusal on its own field (Codex 1614 R1 residual), and several", () => {
    const problemOf = (errors: { field: string; message: string }[]) =>
      new ApiProblem({
        type: "https://erev.dev/problems/validation-failed",
        slug: "validation-failed",
        title: "Validation failed",
        status: 422,
        detail: null,
        code: null,
        requestId: null,
        errors: errors.map((error) => ({ ...error, sheet: null, row: null, rule_id: "POL-211" })),
      });
    // (1) ONE finding on a batch parameter: inline on the parameter's Field, not lost behind the title.
    renderStep({
      problem: problemOf([
        {
          field: "batch_parameters.migration.nondistinct_mapping",
          message: "migration.nondistinct_mapping must be one of SINGLE_POB, SERIES, REVIEW_QUEUE.",
        },
      ]),
    });
    const parameters = screen.getByTestId("SF-19-batch-parameters");
    expect(
      within(parameters).getByText(
        "migration.nondistinct_mapping must be one of SINGLE_POB, SERIES, REVIEW_QUEUE.",
      ),
    ).toBeTruthy();
    expect(
      within(parameters)
        .getByRole("combobox", { name: /^migration\.nondistinct_mapping/ })
        .getAttribute("aria-invalid"),
    ).toBe("true");
    expect(screen.queryAllByTestId("SF-19-import-finding")).toHaveLength(0);
    cleanup();
    // (2) Several on the two parameter fields: each shows on its Field.
    renderStep({
      problem: problemOf([
        {
          field: "batch_parameters.migration.material_right_convention",
          message:
            "migration.material_right_convention must be CONVERT_TO_OPTION_RECORD or KEEP_QUANTITY_CONVENTION.",
        },
        {
          field: "batch_parameters.migration.material_right_convention",
          message: "The legacy-parity preset fixes migration.material_right_convention.",
        },
        {
          field: "batch_parameters.migration.legacy_vc_rows",
          message: "migration.legacy_vc_rows is FORCED to VC_ELEMENT_PLUS_CREDIT_EVENTS.",
        },
      ]),
    });
    const again = screen.getByTestId("SF-19-batch-parameters");
    expect(
      within(again).getByText(
        /migration\.material_right_convention must be CONVERT_TO_OPTION_RECORD or KEEP_QUANTITY_CONVENTION\./,
      ),
    ).toBeTruthy();
    expect(
      within(again).getByText(
        /The legacy-parity preset fixes migration\.material_right_convention\./,
      ),
    ).toBeTruthy();
    // The FORCED parameter has no control: its finding goes to the named banner, verbatim.
    const banner = screen.getByTestId("SF-19-banner-import-refused");
    expect(
      within(banner).getByText(
        "migration.legacy_vc_rows is FORCED to VC_ELEMENT_PLUS_CREDIT_EVENTS.",
      ),
    ).toBeTruthy();
  });

  it("renders the read-only Field mapping rows verbatim from the API, with its loading and failed states", () => {
    renderStep({});
    const table = screen.getByTestId("SF-19-grid-field-mapping");
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual(["Legacy column", "eRev field", "Rule"]);
    // Rows are found by their "Legacy column" text: 1.22 carries only the table hook.
    const row = within(table).getByText("Legacy column 2").closest("tr");
    expect(row).not.toBeNull();
    if (row === null) {
      throw new Error("row");
    }
    expect(within(row).getByText("Legacy column 2")).toBeTruthy();
    expect(within(row).getByText("customer.code")).toBeTruthy();
    expect(within(row).getByText("Trimmed.")).toBeTruthy();
    cleanup();
    renderStep({ fieldMapping: { kind: "loading" } });
    expect(screen.queryByTestId("SF-19-grid-field-mapping")).toBeNull();
    cleanup();
    const onRetry = vi.fn();
    renderStep({ fieldMapping: { kind: "failed", message: "Gateway timeout", onRetry } });
    // DS-CMP-29: a negative banner inserted after load is an alert (Codex 1954, D-98 145 (B)).
    const alert = screen
      .getAllByRole("alert")
      .find((node) => within(node).queryByText("Could not load the field mapping") !== null);
    expect(alert).toBeTruthy();
    if (alert === undefined) {
      throw new Error("alert");
    }
    expect(within(alert).getByText("Gateway timeout")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    // The mapping itself is never blocked by the table's read.
    expect(screen.getByTestId("SF-19-grid-entity-mapping")).toBeTruthy();
  });

  it("shows every finding of a refused /import verbatim: the row's field and the batch banner", () => {
    const problem = new ApiProblem({
      type: "https://erev.dev/problems/validation-failed",
      slug: "validation-failed",
      title: "Validation failed",
      status: 422,
      detail: null,
      code: null,
      requestId: null,
      errors: [
        {
          field: "entity_mapping[1].calendar_id",
          sheet: null,
          row: null,
          rule_id: "LM-CL-09",
          message: "Choose a calendar for Mock Entity 2.",
        },
        {
          field: "migration_id",
          sheet: null,
          row: null,
          rule_id: "LM-CL-03",
          message:
            "SKU Widget maps to two templates (LEGACY-DISTINCT, LEGACY-NONDISTINCT); resolve it in the legacy database before importing.",
        },
      ],
    });
    renderStep({ problem });
    const table = screen.getByTestId("SF-19-grid-entity-mapping");
    expect(within(table).getByText("Choose a calendar for Mock Entity 2.")).toBeTruthy();
    const banner = screen.getByTestId("SF-19-banner-import-refused");
    expect(within(banner).getByText("Validation failed")).toBeTruthy();
    expect(
      within(banner).getByText(
        "SKU Widget maps to two templates (LEGACY-DISTINCT, LEGACY-NONDISTINCT); resolve it in the legacy database before importing.",
      ),
    ).toBeTruthy();
  });
});

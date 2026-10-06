// SF-19:detail, step "Mapping (opening balances)" (SCREENS_B §10.3 rev 1.20; PRD J-20.2; 04 §17.2
// LM-CL-09 / LM-CL-03 rev 1.64; DESIGN_SYSTEM DS-CMP-10, DS-CMP-21, DS-CMP-29; BUILD_SPEC LMG-2).
//
// The step lists EVERY selling entity of the profile in the table "Entity mapping" (identity mapping
// until edited) with, per rev 1.20, a "Calendar" and a "Time zone" column: a "Matched" row shows the
// entity's own values read-only; a "Will be created" row takes a value, else the field group "Entity
// defaults" above the table, else the workspace's only calendar (the row's own value wins). "Batch
// parameters" hold POL-211 / POL-212 (editable), POL-213 / POL-214 (forced, read-only) and the rev 1.20
// toggle "Create missing products". "Confirm mapping" is refused by name while a "Will be created" row
// has no calendar or time zone (Codex 1106 R2) or the cutover date is after the latest legacy period;
// the host posts the confirmation with "Run import" and hands any 422 back here, where every finding
// shows by name (the row's field, or the batch banner). The read-only "Field mapping" table of §10.3 is
// not rendered by this component: its legacy column names are REQ-UX-010 vocabulary the frontend may
// not hold until the API supplies them (lane record F-ADM).
import { useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { Combobox } from "../../components/form/Combobox";
import { DateInput } from "../../components/form/DateInput";
import { ErrorSummary, type FormErrorEntry } from "../../components/form/ErrorSummary";
import {
  controlClass,
  Field,
  type FieldControlProps,
  fieldId,
  fieldLabelId,
} from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Switch } from "../../components/form/Switch";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/feedback/Skeleton";
import type { ApiProblem, ProblemFieldError } from "../../lib/api/problems";
import type { Calendar } from "../../lib/api/queries/calendars";
import {
  type BatchParametersState,
  type EntityDefaultsState,
  type FieldMappingRow,
  identityRows,
  LEGACY_VC_ROWS_FORCED,
  LEGACY_VC_ROWS_KEY,
  type MappingRow,
  mappingRefusals,
  mappingStatus,
  MATERIAL_RIGHT_CONVENTION_KEY,
  MATERIAL_RIGHT_CONVENTION_PRESET,
  matchedEntity,
  type Migration,
  NONDISTINCT_MAPPING_KEY,
  NONDISTINCT_MAPPING_PRESET,
  resolvedCalendarId,
  resolvedTimeZone,
  SPLIT_UPLOAD_ALLOCATION_FORCED,
  SPLIT_UPLOAD_ALLOCATION_KEY,
} from "../../lib/api/queries/migrations";
import type { Entity } from "../../lib/api/queries/tenant";
import { formatDate, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { timeZoneOptions } from "../../lib/reference/countries";

/** The read-only "Field mapping" table's data, as the host reads it (`GET /migrations/field-mapping`). */
export type FieldMappingState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly rows: readonly FieldMappingRow[] }
  | { readonly kind: "failed"; readonly message: string | null; readonly onRetry: () => void };

/** What "Confirm mapping" hands the host; "Run import" posts `importBody(...)` of it (J-20.3). */
export interface MappingConfirmation {
  /** The migration the confirmation belongs to (Codex 1546 R2): "Run import" posts it to this id only. */
  readonly migrationId: string;
  readonly cutoverDate: string;
  readonly rows: readonly MappingRow[];
  readonly defaults: EntityDefaultsState;
  readonly parameters: BatchParametersState;
}

export interface MigrationMappingStepProps {
  readonly migration: Migration;
  readonly calendars: readonly Calendar[];
  readonly entities: readonly Entity[];
  /** POL-211 allowed values from the registry parameter catalogue (API-R-13), in catalogue order. */
  readonly nondistinctOptions: readonly string[];
  /** POL-212 allowed values from the registry parameter catalogue (API-R-13), in catalogue order. */
  readonly materialRightOptions: readonly string[];
  /** The "Field mapping" rows (04 §17.2 as data), or their loading / failed state. */
  readonly fieldMapping: FieldMappingState;
  /** The refused `/import` (422) to show by name, or null. */
  readonly problem: ApiProblem | null;
  /** The confirmation of an earlier visit, kept when the user comes back from the import step. */
  readonly initial?: MappingConfirmation | null;
  readonly onConfirm: (confirmation: MappingConfirmation) => void;
  readonly onBack?: (() => void) | undefined;
}

const PRESET_PARAMETERS: BatchParametersState = {
  nondistinctMapping: NONDISTINCT_MAPPING_PRESET,
  materialRightConvention: MATERIAL_RIGHT_CONVENTION_PRESET,
  createMissingProducts: true,
};

const NO_DEFAULTS: EntityDefaultsState = { calendarId: null, timeZone: null };

function rowFieldName(index: number, member: "entity_code" | "calendar_id" | "time_zone"): string {
  return `entity_mapping[${String(index)}].${member}`;
}

/** The control props of an in-table field; its `sr-only` `<label>` carries `fieldLabelId(name)`. */
function cellControl(name: string, invalid: boolean): FieldControlProps {
  return {
    id: fieldId(name),
    name,
    ...(invalid
      ? { "aria-invalid": true as const, "aria-describedby": `${fieldId(name)}-error` }
      : {}),
  };
}

function calendarLabel(calendar: Calendar): string {
  return `${calendar.code} · ${calendar.name}`;
}

const HEAD = "py-2 pe-4 text-start font-medium";
const CELL = "py-2 pe-4 align-top";

export function MigrationMappingStep({
  migration,
  calendars,
  entities,
  nondistinctOptions,
  materialRightOptions,
  fieldMapping,
  problem,
  initial = null,
  onConfirm,
  onBack,
}: MigrationMappingStepProps) {
  const profile = migration.profile;
  const latestPeriod = profile?.latest_current_period ?? null;
  const [rows, setRows] = useState<readonly MappingRow[]>(
    () => initial?.rows ?? identityRows(profile ?? { selling_entities: [] }),
  );
  const [defaults, setDefaults] = useState<EntityDefaultsState>(initial?.defaults ?? NO_DEFAULTS);
  const [parameters, setParameters] = useState<BatchParametersState>(
    initial?.parameters ?? PRESET_PARAMETERS,
  );
  const [cutoverText, setCutoverText] = useState(() =>
    initial === null ? formatDate(latestPeriod) : formatDate(initial.cutoverDate),
  );
  const [cutoverDate, setCutoverDate] = useState<string | null>(
    initial?.cutoverDate ?? latestPeriod,
  );
  const [cutoverFormatError, setCutoverFormatError] = useState<string | null>(null);
  const [submitCount, setSubmitCount] = useState(0);
  const [clientErrors, setClientErrors] = useState<Readonly<Record<string, string>>>({});

  const calendarOptions = calendars.map((calendar) => ({
    value: calendar.id,
    label: calendarLabel(calendar),
  }));
  const zones = timeZoneOptions(null);

  // Every 422 finding is kept (Codex 1546 R1). A finding whose field has a rendered control shows inline
  // on that control, one line per finding (multiplicity kept); every other finding — a field this step
  // renders no control for (`entity_mapping[i].legacy_name`), a row index outside the table, the batch
  // (`migration_id`, `entity_mapping`) or any unknown field — shows verbatim in the named banner below.
  const renderedFields = new Set<string>([
    "entity_defaults.calendar_id",
    "entity_defaults.time_zone",
    "cutover_date",
    NONDISTINCT_MAPPING_KEY,
    MATERIAL_RIGHT_CONVENTION_KEY,
  ]);
  rows.forEach((_row, index) => {
    for (const member of ["entity_code", "calendar_id", "time_zone"] as const) {
      renderedFields.add(rowFieldName(index, member));
    }
  });
  const serverErrors = new Map<string, string[]>();
  const unmapped: ProblemFieldError[] = [];
  for (const error of problem?.errors ?? []) {
    const field = error.field?.replace(/^batch_parameters\./, "") ?? null;
    if (field !== null && renderedFields.has(field)) {
      serverErrors.set(field, [...(serverErrors.get(field) ?? []), error.message]);
    } else {
      unmapped.push(error);
    }
  }
  const messagesOf = (name: string): readonly string[] => {
    const client = clientErrors[name];
    return [...(serverErrors.get(name) ?? []), ...(client === undefined ? [] : [client])];
  };
  const errorText = (name: string): string | null => {
    const messages = messagesOf(name);
    return messages.length === 0 ? null : messages.join(" ");
  };
  const errorNames = [...new Set([...serverErrors.keys(), ...Object.keys(clientErrors)])];
  const summary: FormErrorEntry[] = errorNames.map((name) => ({
    name,
    message: messagesOf(name).join(" "),
  }));

  const updateRow = (index: number, patch: Partial<MappingRow>) => {
    setRows((current) => current.map((row, at) => (at === index ? { ...row, ...patch } : row)));
    setClientErrors({});
  };

  const confirm = () => {
    const found: Record<string, string> = {};
    rows.forEach((row, index) => {
      for (const refusal of mappingRefusals([row], defaults, calendars, entities)) {
        found[rowFieldName(index, refusal.field)] = t(
          refusal.field === "calendar_id"
            ? "data.migrations.mapping.chooseCalendar"
            : "data.migrations.mapping.chooseTimeZone",
          { entity: refusal.legacyName },
        );
      }
    });
    if (cutoverFormatError !== null) {
      found["cutover_date"] = cutoverFormatError;
    } else if (cutoverDate === null || (latestPeriod !== null && cutoverDate > latestPeriod)) {
      found["cutover_date"] = t("data.migrations.mapping.cutoverDateRule");
    }
    setClientErrors(found);
    setSubmitCount((count) => count + 1);
    if (Object.keys(found).length === 0 && cutoverDate !== null) {
      onConfirm({ migrationId: migration.id, cutoverDate, rows, defaults, parameters });
    }
  };

  return (
    <section
      aria-label={t("data.migrations.step.mapping")}
      data-testid="SF-19-step-mapping"
      className="flex flex-col gap-6"
    >
      {/* §10.3 test hook `SF-19-banner-preset`: the DS-CMP-29 notice of J-20.2 (REQ-MIG-005), a status
          region per the §10.3 locator ("status" + the notice text). */}
      <div data-testid="SF-19-banner-preset">
        <Banner
          tone="info"
          announce="live"
          headingLevel={2}
          title={t("data.migrations.mapping.presetNotice")}
        />
      </div>
      {problem === null ? null : (
        <div data-testid="SF-19-banner-import-refused">
          <Banner tone="negative" announce="live" headingLevel={2} title={problem.title}>
            {problem.detail === null ? null : <p>{problem.detail}</p>}
            {unmapped.map((finding, index) => (
              <p key={`${finding.field ?? ""}:${String(index)}`} data-testid="SF-19-import-finding">
                {finding.field === null ? null : (
                  <span className="me-2 font-mono text-mono-sm text-fg-2">{finding.field}</span>
                )}
                {finding.message}
              </p>
            ))}
          </Banner>
        </div>
      )}
      <ErrorSummary errors={summary} submitCount={submitCount} />

      <fieldset className="flex flex-col gap-2">
        <legend className="text-body-sm font-medium text-fg-1">
          {t("data.migrations.mapping.entityDefaults")}
        </legend>
        <div className="flex flex-wrap gap-4">
          <Field
            name="entity_defaults.calendar_id"
            label={t("data.migrations.mapping.calendar")}
            width="text"
            error={errorText("entity_defaults.calendar_id")}
          >
            {(control) => (
              <Select<string>
                control={control}
                options={calendarOptions}
                value={defaults.calendarId}
                invalid={messagesOf("entity_defaults.calendar_id").length > 0}
                onChange={(next) => {
                  setDefaults((current) => ({ ...current, calendarId: next }));
                  setClientErrors({});
                }}
              />
            )}
          </Field>
          <Field
            name="entity_defaults.time_zone"
            label={t("data.migrations.mapping.timeZone")}
            width="text"
            error={errorText("entity_defaults.time_zone")}
          >
            {(control) => (
              <Combobox
                control={control}
                options={zones}
                value={defaults.timeZone}
                invalid={messagesOf("entity_defaults.time_zone").length > 0}
                onChange={(next) => {
                  setDefaults((current) => ({ ...current, timeZone: next }));
                  setClientErrors({});
                }}
              />
            )}
          </Field>
        </div>
      </fieldset>

      <table
        data-testid="SF-19-grid-entity-mapping"
        className="w-full border-collapse text-body-sm"
      >
        <caption className="mb-2 text-start text-title-sm text-fg-1">
          {t("data.migrations.mapping.entityMapping")}
        </caption>
        <thead>
          <tr className="border-b border-default text-fg-2">
            <th scope="col" className={HEAD}>
              {t("data.migrations.mapping.legacyEntity")}
            </th>
            <th scope="col" className={HEAD}>
              {t("data.migrations.mapping.entity")}
            </th>
            <th scope="col" className={HEAD}>
              {t("data.migrations.mapping.calendar")}
            </th>
            <th scope="col" className={HEAD}>
              {t("data.migrations.mapping.timeZone")}
            </th>
            <th scope="col" className="py-2 text-start font-medium">
              {t("data.migrations.mapping.status")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const entity = matchedEntity(row, entities);
            const status = mappingStatus(row, entities);
            const codeName = rowFieldName(index, "entity_code");
            const calendarName = rowFieldName(index, "calendar_id");
            const zoneName = rowFieldName(index, "time_zone");
            const calendarErrors = messagesOf(calendarName);
            const zoneErrors = messagesOf(zoneName);
            const codeErrors = messagesOf(codeName);
            const entityCalendar =
              entity === null
                ? null
                : (calendars.find((calendar) => calendar.id === entity.calendar_id) ?? null);
            return (
              <tr key={row.legacyName} className="border-b border-hairline">
                <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                  {row.legacyName}
                </th>
                <td className={CELL}>
                  <input
                    id={fieldId(codeName)}
                    name={codeName}
                    type="text"
                    className={controlClass(codeErrors.length > 0)}
                    aria-label={t("data.migrations.mapping.rowField", {
                      field: t("data.migrations.mapping.entity"),
                      entity: row.legacyName,
                    })}
                    aria-invalid={codeErrors.length === 0 ? undefined : true}
                    value={row.entityCode}
                    onChange={(event) => updateRow(index, { entityCode: event.target.value })}
                  />
                  {codeErrors.map((message) => (
                    <p key={message} className="mt-1 text-body-sm text-negative-fg">
                      {message}
                    </p>
                  ))}
                </td>
                <td className={CELL}>
                  {entity !== null ? (
                    <>
                      <span className="text-fg-1">
                        {entityCalendar === null ? NO_VALUE : calendarLabel(entityCalendar)}
                      </span>
                      {calendarErrors.map((message) => (
                        <p key={message} className="mt-1 text-body-sm text-negative-fg">
                          {message}
                        </p>
                      ))}
                    </>
                  ) : (
                    <>
                      <label
                        htmlFor={fieldId(calendarName)}
                        id={fieldLabelId(calendarName)}
                        className="sr-only"
                      >
                        {t("data.migrations.mapping.rowField", {
                          field: t("data.migrations.mapping.calendar"),
                          entity: row.legacyName,
                        })}
                      </label>
                      <Select<string>
                        control={cellControl(calendarName, calendarErrors.length > 0)}
                        options={calendarOptions}
                        value={resolvedCalendarId(row, defaults, calendars)}
                        invalid={calendarErrors.length > 0}
                        onChange={(next) => updateRow(index, { calendarId: next })}
                      />
                      {calendarErrors.length === 0 ? null : (
                        <div id={`${fieldId(calendarName)}-error`}>
                          {calendarErrors.map((message) => (
                            <p key={message} className="mt-1 text-body-sm text-negative-fg">
                              {message}
                            </p>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </td>
                <td className={CELL}>
                  {entity !== null ? (
                    <>
                      <span className="text-fg-1">{entity.time_zone}</span>
                      {zoneErrors.map((message) => (
                        <p key={message} className="mt-1 text-body-sm text-negative-fg">
                          {message}
                        </p>
                      ))}
                    </>
                  ) : (
                    <>
                      <label
                        htmlFor={fieldId(zoneName)}
                        id={fieldLabelId(zoneName)}
                        className="sr-only"
                      >
                        {t("data.migrations.mapping.rowField", {
                          field: t("data.migrations.mapping.timeZone"),
                          entity: row.legacyName,
                        })}
                      </label>
                      <Combobox
                        control={cellControl(zoneName, zoneErrors.length > 0)}
                        options={zones}
                        value={resolvedTimeZone(row, defaults)}
                        invalid={zoneErrors.length > 0}
                        onChange={(next) => updateRow(index, { timeZone: next })}
                      />
                      {zoneErrors.length === 0 ? null : (
                        <div id={`${fieldId(zoneName)}-error`}>
                          {zoneErrors.map((message) => (
                            <p key={message} className="mt-1 text-body-sm text-negative-fg">
                              {message}
                            </p>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </td>
                <td className="py-2 align-top text-fg-1">
                  {t(`data.migrations.mapping.status.${status}`)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <FieldMappingTable state={fieldMapping} />

      <section
        aria-labelledby="SF-19-batch-parameters"
        data-testid="SF-19-batch-parameters"
        className="flex flex-col gap-3"
      >
        <h2 id="SF-19-batch-parameters" className="text-title-sm text-fg-1">
          {t("data.migrations.mapping.batchParameters")}
        </h2>
        <div className="flex flex-wrap gap-4">
          <Field
            name={NONDISTINCT_MAPPING_KEY}
            label={NONDISTINCT_MAPPING_KEY}
            width="text"
            error={errorText(NONDISTINCT_MAPPING_KEY)}
          >
            {(control) => (
              <Select<string>
                control={control}
                options={nondistinctOptions.map((value) => ({ value, label: value }))}
                value={parameters.nondistinctMapping}
                invalid={messagesOf(NONDISTINCT_MAPPING_KEY).length > 0}
                onChange={(next) =>
                  setParameters((current) => ({ ...current, nondistinctMapping: next }))
                }
              />
            )}
          </Field>
          <Field
            name={MATERIAL_RIGHT_CONVENTION_KEY}
            label={MATERIAL_RIGHT_CONVENTION_KEY}
            width="text"
            error={errorText(MATERIAL_RIGHT_CONVENTION_KEY)}
          >
            {(control) => (
              <Select<string>
                control={control}
                options={materialRightOptions.map((value) => ({ value, label: value }))}
                value={parameters.materialRightConvention}
                invalid={messagesOf(MATERIAL_RIGHT_CONVENTION_KEY).length > 0}
                onChange={(next) =>
                  setParameters((current) => ({ ...current, materialRightConvention: next }))
                }
              />
            )}
          </Field>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body-sm">
          <dt className="font-mono text-mono-sm text-fg-2">{LEGACY_VC_ROWS_KEY}</dt>
          <dd className="font-mono text-mono-sm text-fg-1">{LEGACY_VC_ROWS_FORCED}</dd>
          <dt className="font-mono text-mono-sm text-fg-2">{SPLIT_UPLOAD_ALLOCATION_KEY}</dt>
          <dd className="font-mono text-mono-sm text-fg-1">{SPLIT_UPLOAD_ALLOCATION_FORCED}</dd>
        </dl>
        <div className="flex flex-col gap-1">
          <Switch
            label={t("data.migrations.mapping.createMissingProducts")}
            checked={parameters.createMissingProducts}
            onChange={(checked) =>
              setParameters((current) => ({ ...current, createMissingProducts: checked }))
            }
          />
          <p className="text-body-sm text-fg-3">
            {t("data.migrations.mapping.createMissingProductsHelp")}
          </p>
        </div>
      </section>

      <Field
        name="cutover_date"
        label={t("data.migrations.mapping.cutoverDate")}
        required
        width="date"
        error={errorText("cutover_date")}
      >
        {(control) => (
          <DateInput
            control={control}
            value={cutoverText}
            onChange={(text) => {
              setCutoverText(text);
              setClientErrors({});
            }}
            onValue={setCutoverDate}
            onFormatError={setCutoverFormatError}
            invalid={messagesOf("cutover_date").length > 0}
          />
        )}
      </Field>

      <div className="flex items-center gap-3 border-t border-hairline pt-3">
        {onBack === undefined ? null : (
          <Button variant="secondary" onClick={onBack}>
            {t("data.migrations.back")}
          </Button>
        )}
        <span className="flex-1" />
        <Button variant="primary" onClick={confirm}>
          {t("data.migrations.mapping.confirm")}
        </Button>
      </div>
    </section>
  );
}

/**
 * §10.3 "Field mapping" (read-only, REQ-MIG-006): "Legacy column" (legacy names allowed, D-33), "eRev
 * field", "Rule" — every row of `GET /migrations/field-mapping` verbatim, in the API's (legacy) order.
 */
function FieldMappingTable({ state }: { readonly state: FieldMappingState }) {
  if (state.kind === "loading") {
    return <Skeleton region={t("data.migrations.mapping.fieldMapping")} shape="text" count={3} />;
  }
  if (state.kind === "failed") {
    // Inserted after the page and the form have loaded (the read fails later than they render), so it
    // carries DS-CMP-29's live semantics — role "alert" for a negative banner (Codex 1954, D-98 145 (B)).
    return (
      <Banner
        tone="negative"
        announce="live"
        headingLevel={2}
        title={t("data.migrations.fieldMapping.loadError")}
        actions={
          <Button variant="secondary" size="sm" onClick={state.onRetry}>
            {t("common.job.retry")}
          </Button>
        }
      >
        {state.message}
      </Banner>
    );
  }
  return (
    <table data-testid="SF-19-grid-field-mapping" className="w-full border-collapse text-body-sm">
      <caption className="mb-2 text-start text-title-sm text-fg-1">
        {t("data.migrations.mapping.fieldMapping")}
      </caption>
      <thead>
        <tr className="border-b border-default text-fg-2">
          <th scope="col" className={HEAD}>
            {t("data.migrations.fieldMapping.legacyColumn")}
          </th>
          <th scope="col" className={HEAD}>
            {t("data.migrations.fieldMapping.erevField")}
          </th>
          <th scope="col" className="py-2 text-start font-medium">
            {t("data.migrations.fieldMapping.rule")}
          </th>
        </tr>
      </thead>
      <tbody>
        {state.rows.map((row) => (
          <tr key={row.id} className="border-b border-hairline">
            <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
              {row.legacy_column}
            </th>
            <td className={`${CELL} font-mono text-mono-sm text-fg-1`}>{row.target}</td>
            <td className="py-2 align-top text-fg-2">{row.rule}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

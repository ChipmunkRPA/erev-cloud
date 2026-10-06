// SF-10:new New import, step 1 Upload (SCREENS §12.2; §0.4 RT-43; §0.5 SCR-URL-28, SCR-URL-29; §0.10
// SCR-LTH-O5; §0.7 SCR-PERM-01; DESIGN_SYSTEM DS-CMP-18, DS-CMP-21, DS-CMP-29; 04 API-R-12 `POST /files`
// (purpose IMPORT_SOURCE, T-PLT-29), API-R-43 `GET /import-templates`, `GET /import-mapping-profiles`,
// `POST /imports` (API-S-ImportCreate); PRD SM-05, ERR-37, IMP-05; BUILD_SPEC DIN-16).
//
// The Data frame and the stepper "Import steps" at Upload; the template select grouped by family and
// preselected by `?template=`; the effective date and the mode (preselected by `?mode=`) when the
// template requires them; the read-only progress mode of the legacy progress tracking template; the
// published mapping profiles of a CSV v2 template; and the dropzone. "Upload and validate" stores the
// file, creates the import and opens its `validate` step while the validation job runs. A refused
// file names the reason on the dropzone (ERR-37, IMP-05).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type DragEvent, type FormEvent, type ReactNode, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { UploadSimple } from "../../components/icons/registry";
import { type Step, Stepper } from "../../components/record/Stepper";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { useAccess } from "../../lib/access";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import type { Job } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import {
  fetchImportTemplates,
  type ImportTemplate,
  importTemplatesKey,
  templateName,
} from "../../lib/api/queries/import-templates";
import {
  EVERY_IMPORT,
  type ImportCreateBody,
  IMPORT_FILE_PURPOSE,
  IMPORT_UPLOAD_PERMISSION,
  importJobsKey,
  IMPORTS_PATH,
  IMPORTS_ROUTE,
  importStepRoute,
  TEMPLATES_ROUTE,
} from "../../lib/api/queries/imports";
import {
  fetchPublishedProfiles,
  publishedProfilesKey,
} from "../../lib/api/queries/mapping-profiles";
import { useMe } from "../../lib/api/queries/me";
import { uploadFile } from "../../lib/api/queries/ssp-books";
import { formatDate, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import type { CorrectedFileState, UploadedState } from "./import-detail";
import { DataPageHeader } from "./imports";

/** SCREENS SCR-URL-28 `mode` literals (REQ-DAT-003). */
export const IMPORT_MODES = ["prospective", "retrospective", "pob_price_change"] as const;
/** PRD J-01.10; LTM-03: the legacy progress tracking template records delivery and billing. */
const PROGRESS_TRACKING = "legacy_progress_tracking";
const EFFECTIVE_DATE = "effective_date";
const MODE = "mode";
const NO_PROFILE = "none";
/** 04 T-PLT-29 `IMPORT_SOURCE`: `.xlsx` and `.csv`. */
const ACCEPTED_FILES =
  ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const IMPORT_ID_HEADER = "X-Erev-Import-Id";
const EVENT_SET_PARAM = "event_set";

function isCorrectedState(value: unknown): value is CorrectedFileState {
  return typeof value === "object" && value !== null && "parameters" in value;
}

function problemText(problem: unknown): string {
  if (problem instanceof ApiProblem) {
    const message = problem.errors.find((error) => error.field === null)?.message;
    const text = problem.detail ?? message ?? problem.title;
    return problem.requestId === null
      ? text
      : `${text} ${t("approvals.reference", { reference: problem.requestId })}`;
  }
  return problem instanceof Error ? problem.message : String(problem);
}

/** DS-CMP-18 stepper at Upload: every later step waits for the file. */
export function uploadSteps(): Step[] {
  return (["upload", "map", "validate", "review", "approval", "committed"] as const).map((id) => ({
    id,
    label: t(`data.imports.step.${id}`),
    state: id === "upload" ? "current" : "pending",
  }));
}

export function ImportNew() {
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.imports.new.title")} shape="text" count={6} />;
  } else if (!access.holdsAnywhere(IMPORT_UPLOAD_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("data.access.newImport") })}
        description={t("settings.access.description", {
          permission: t("data.imports.new.permission"),
        })}
      />
    );
  } else {
    return <NewImportPage />;
  }
  return (
    <div data-testid="SF-10-new-page" className="relative flex flex-col gap-4">
      <DataPageHeader
        title={t("data.imports.new.title")}
        crumbs={[{ label: t("data.imports.title"), to: IMPORTS_ROUTE }]}
      />
      {body}
    </div>
  );
}

interface DropzoneProps {
  readonly file: File | null;
  readonly error: string | null;
  readonly onFile: (file: File) => void;
}

/** DS-CMP-18 dropzone: a button backed by a native file input; drag and drop is optional. */
function Dropzone({ file, error, onFile }: DropzoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const labelId = useId();
  const limitId = useId();
  const errorId = useId();
  const built = useBuiltPaths();
  const drop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped !== undefined) {
      onFile(dropped);
    }
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span id={labelId} className="text-body-sm font-medium text-fg-1">
        {t("data.imports.new.file")}
      </span>
      <button
        type="button"
        data-testid="SF-10-dropzone"
        aria-describedby={error === null ? limitId : `${limitId} ${errorId}`}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        className={cn(
          "flex h-40 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-surface px-4 text-body-sm text-fg-2 hover:bg-hover",
          error === null ? "border-control" : "border-negative-fg",
          over ? "bg-hover" : null,
        )}
      >
        <UploadSimple aria-hidden="true" size={24} className="text-fg-3" />
        <span>{t("data.imports.upload.dropzone")}</span>
        <span className="inline-flex h-8 items-center rounded-md border border-control bg-surface px-3 font-medium text-fg-1">
          {t("data.imports.upload.choose")}
        </span>
      </button>
      <input
        ref={input}
        type="file"
        hidden
        accept={ACCEPTED_FILES}
        data-testid="SF-10-file-input"
        aria-labelledby={labelId}
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          if (chosen !== undefined) {
            onFile(chosen);
          }
          event.target.value = "";
        }}
      />
      {file === null ? null : (
        <p data-testid="SF-10-file-selected" className="text-body-sm text-fg-1">
          {t("data.imports.upload.selected", {
            name: file.name,
            size: formatNumber(file.size, { kind: "count" }),
          })}
        </p>
      )}
      <p id={limitId} className="text-body-sm text-fg-3">
        {t("data.imports.upload.limit")}
        {built.has(TEMPLATES_ROUTE) ? (
          <>
            {" "}
            <Link to={TEMPLATES_ROUTE} className="text-accent-fg underline">
              {t("data.imports.downloadTemplates")}
            </Link>
          </>
        ) : null}
      </p>
      {error === null ? null : (
        <p id={errorId} className="text-body-sm text-negative-fg">
          {error}
        </p>
      )}
    </div>
  );
}

function requiredParameter(template: ImportTemplate | undefined, name: string) {
  return template?.required_parameters.find((parameter) => parameter.name === name);
}

function NewImportPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const search = new URLSearchParams(location.search);
  const corrected = isCorrectedState(location.state) ? location.state.parameters : {};
  const templates = useQuery({ queryKey: importTemplatesKey(), queryFn: fetchImportTemplates });
  const [templateCode, setTemplateCode] = useState<string | null>(search.get("template"));
  const template = templates.data?.find((candidate) => candidate.code === templateCode);
  const initialEffective =
    typeof corrected.effective_date === "string" ? corrected.effective_date : null;
  const [effective, setEffective] = useState<string | null>(initialEffective);
  const [effectiveTyped, setEffectiveTyped] = useState(
    initialEffective === null ? "" : formatDate(initialEffective),
  );
  const [effectiveFormat, setEffectiveFormat] = useState<string | null>(null);
  const modeParam =
    search.get("mode") ?? (typeof corrected.mode === "string" ? corrected.mode : null);
  const [mode, setMode] = useState<string | null>(
    modeParam !== null && (IMPORT_MODES as readonly string[]).includes(modeParam)
      ? modeParam
      : null,
  );
  const [profileId, setProfileId] = useState<string>(NO_PROFILE);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const command = useCommand<Job>({
    method: "POST",
    path: IMPORTS_PATH,
    invalidates: [EVERY_IMPORT],
  });
  // The key of the file upload that precedes the import command (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();

  const csv = template?.family === "CSV_V2";
  const effectiveParameter = requiredParameter(template, EFFECTIVE_DATE);
  const modeParameter = requiredParameter(template, MODE);
  const modes = modeParameter?.allowed_values ?? IMPORT_MODES;
  const profiles = useQuery({
    queryKey: publishedProfilesKey(template?.code ?? ""),
    queryFn: () => fetchPublishedProfiles(template?.code ?? ""),
    enabled: csv,
    retry: false,
  });
  const templateOptions = (templates.data ?? []).map((candidate) => ({
    value: candidate.code,
    label: templateName(candidate),
    group: t(`data.imports.new.group.${candidate.family}`),
  }));
  const profileOptions = [
    { value: NO_PROFILE, label: t("data.imports.new.profile.none") },
    ...(profiles.data ?? []).map((profile) => ({
      value: profile.id,
      label: t("data.imports.new.profile.option", { code: profile.code, name: profile.name }),
    })),
  ];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (template === undefined) {
      found.template = t("data.imports.new.required.template");
    }
    if (effectiveParameter !== undefined && effective === null) {
      found.effective_date = effectiveFormat ?? t("data.imports.new.required.effectiveDate");
    }
    if (modeParameter !== undefined && mode === null) {
      found.mode = t("data.imports.new.required.mode");
    }
    setErrors(found);
    setBanner(null);
    setFileError(file === null ? t("data.imports.new.required.file") : null);
    if (Object.keys(found).length > 0 || template === undefined || file === null) {
      return;
    }
    setUploading(true);
    let stored: { readonly id: string };
    try {
      stored = await uploadFile(keys, IMPORT_FILE_PURPOSE, file);
    } catch (error) {
      setUploading(false);
      setFileError(problemText(error));
      return;
    }
    const parameters: Record<string, string> = {};
    if (effectiveParameter !== undefined && effective !== null) {
      parameters[EFFECTIVE_DATE] = effective;
    }
    if (modeParameter !== undefined && mode !== null) {
      parameters[MODE] = mode;
    }
    const eventSet = search.get(EVENT_SET_PARAM);
    const body: ImportCreateBody = {
      file_id: stored.id,
      template_code: template.code,
      parameters,
      mapping_profile_id: csv && profileId !== NO_PROFILE ? profileId : null,
      ...(eventSet === null ? {} : { forecast_event_set_id: eventSet }),
    };
    const outcome = await command.submit(body);
    setUploading(false);
    if (outcome.kind === "accepted") {
      const importId = outcome.response.headers.get(IMPORT_ID_HEADER);
      if (importId === null) {
        setBanner(t("data.imports.new.noImport"));
        return;
      }
      const job = (await outcome.response.json()) as Job;
      // The validate step shows the job at once, before its first poll (DS-CMP-24).
      queryClient.setQueryData(importJobsKey(importId), [job]);
      void navigate(importStepRoute(importId, "validate"), {
        state: { uploaded: true } satisfies UploadedState,
      });
      return;
    }
    if (outcome.kind === "network-error") {
      setBanner(problemText(outcome.error));
      return;
    }
    if (outcome.kind === "succeeded") {
      // `POST /imports` answers 202 with the validation job; any other success names no import.
      setBanner(t("data.imports.new.noImport"));
      return;
    }
    const problem = outcome.problem;
    if (problem.slug === "duplicate-import" || problem.slug === "upload-type-not-allowed") {
      setFileError(problemText(problem));
      return;
    }
    const fields: Record<string, string> = {};
    let unplaced: string | null = null;
    for (const error of problem.errors) {
      const field = error.field ?? "";
      if (field.endsWith(EFFECTIVE_DATE)) {
        fields.effective_date = error.message;
      } else if (field.endsWith(MODE)) {
        fields.mode = error.message;
      } else if (field.endsWith("template_code")) {
        fields.template = error.message;
      } else if (field.endsWith("mapping_profile_id")) {
        fields.profile = error.message;
      } else if (field.endsWith("file_id")) {
        setFileError(error.message);
      } else {
        unplaced ??= error.message;
      }
    }
    setErrors(fields);
    const onFile = problem.errors.some((error) => error.field?.endsWith("file_id") === true);
    if (Object.keys(fields).length === 0 && !onFile) {
      setBanner(unplaced ?? problemText(problem));
    }
  };

  return (
    <div data-testid="SF-10-new-page" className="relative flex flex-col gap-4">
      <DataPageHeader
        title={t("data.imports.new.title")}
        crumbs={[{ label: t("data.imports.title"), to: IMPORTS_ROUTE }]}
      />
      <div data-testid="SF-10-stepper">
        <Stepper label={t("data.imports.stepper")} steps={uploadSteps()} currentId="upload" />
      </div>
      <form
        noValidate
        aria-label={t("data.imports.new.form")}
        className="flex max-w-160 flex-col gap-4"
        onSubmit={(event) => void submit(event)}
      >
        {banner === null ? null : (
          <Banner tone="negative" announce="live" headingLevel={2} title={banner} />
        )}
        {templates.isError ? (
          <Banner
            tone="negative"
            headingLevel={2}
            title={t("data.templates.loadError")}
            actions={
              <Button variant="secondary" size="sm" onClick={() => void templates.refetch()}>
                {t("data.imports.retry")}
              </Button>
            }
          >
            {problemText(templates.error)}
          </Banner>
        ) : null}
        <Field
          name="import-template"
          label={t("data.imports.new.template")}
          required
          error={errors.template ?? null}
          width="text"
        >
          {(control) => (
            <Select
              control={control}
              options={templateOptions}
              value={template === undefined ? null : template.code}
              onChange={(value) => {
                setTemplateCode(value);
                setProfileId(NO_PROFILE);
              }}
              placeholder={
                templates.data === undefined
                  ? t("data.imports.new.templatesLoading")
                  : t("data.imports.new.templatePlaceholder")
              }
              invalid={errors.template !== undefined}
            />
          )}
        </Field>
        {effectiveParameter === undefined ? null : (
          <Field
            name="import-effective-date"
            label={t("data.templates.parameter.effectiveDate")}
            required
            error={errors.effective_date ?? null}
            width="date"
          >
            {(control) => (
              <DateInput
                control={control}
                value={effectiveTyped}
                onChange={setEffectiveTyped}
                onValue={setEffective}
                onFormatError={setEffectiveFormat}
                invalid={errors.effective_date !== undefined}
              />
            )}
          </Field>
        )}
        {modeParameter === undefined ? null : (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-body-sm font-medium text-fg-1">
              {t("data.imports.new.mode")}
            </legend>
            {modes.map((value) => (
              <label key={value} className="flex items-center gap-2 text-body-sm text-fg-1">
                <input
                  type="radio"
                  name="import_mode"
                  value={value}
                  checked={mode === value}
                  onChange={() => setMode(value)}
                  className="size-4"
                />
                {t(`data.imports.mode.${value}`)}
              </label>
            ))}
            {errors.mode === undefined ? null : (
              <span className="text-body-sm text-negative-fg">{errors.mode}</span>
            )}
          </fieldset>
        )}
        {template?.code === PROGRESS_TRACKING ? (
          <Field
            name="import-progress-mode"
            label={t("data.imports.new.progressMode")}
            width="text"
          >
            {(control) => (
              <input
                {...control}
                readOnly
                className={controlClass(false)}
                value={t("data.imports.new.progressModeValue")}
              />
            )}
          </Field>
        ) : null}
        {csv ? (
          <Field
            name="import-mapping-profile"
            label={t("data.imports.new.profile.label")}
            help={profiles.isError ? t("data.imports.new.profile.loadError") : undefined}
            error={errors.profile ?? null}
            width="text"
          >
            {(control) => (
              <Select
                control={control}
                options={profileOptions}
                value={profileId}
                onChange={setProfileId}
                invalid={errors.profile !== undefined}
              />
            )}
          </Field>
        ) : null}
        <Dropzone
          file={file}
          error={fileError}
          onFile={(chosen) => {
            setFile(chosen);
            setFileError(null);
          }}
        />
        <div>
          <Button variant="primary" type="submit" loading={uploading || command.pending}>
            {t("data.imports.upload.submit")}
          </Button>
        </div>
      </form>
    </div>
  );
}

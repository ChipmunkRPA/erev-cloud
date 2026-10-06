// SF-19:detail Migration (SCREENS_B §10.3 rev 1.20; §0.4 RT-53; SCREENS SCR-URL-15 screen parameter
// `step`; §0.7 SCR-PERM-01, SCR-ST-05, SCR-ST-07, SCR-ST-12; DESIGN_SYSTEM DS-CMP-06, DS-CMP-18,
// DS-CMP-24, DS-CMP-29; 04 T-MIG-01, E-76, §17.2 LM-CL-09 / LM-CL-03 rev 1.64; API `GET /migrations/{id}`,
// `POST /migrations/{id}/import`; PRD J-20.2, J-20.3; BUILD_SPEC LMG-2).
//
// The minimal host of the opening-balances journey J-20.2 → J-20.3 (supervisor ruling, option A): the
// Data frame, the five-step stepper "Migration steps", the Mapping step (`MigrationMappingStep`) and the
// Import step (summary "Cutover <date> · <n> entities · <n> contracts", "Run import" → `POST /import`,
// the DS-CMP-24 job while `MIGRATION_IMPORT` runs). The Profile, Reconciliation and Promotion steps, the
// replay journey, SF-19 (list) and SF-19:new are separate WEB items: their steps are in the stepper but
// not navigable, and a `step` naming one shows the frame and the stepper with no region.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router";

import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { type Step, Stepper } from "../../components/record/Stepper";
import { Button } from "../../components/ui/Button";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, useJob } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { fetchAllCalendars, calendarsKey } from "../../lib/api/queries/calendars";
import { allEntitiesKey, fetchAllEntities } from "../../lib/api/queries/entities";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  EVERY_MIGRATION,
  importBody,
  isBuiltStep,
  isMigrationStep,
  MATERIAL_RIGHT_CONVENTION_KEY,
  type Migration,
  MIGRATION_RUN_PERMISSION,
  type MigrationStep,
  migrationImportPath,
  migrationKey,
  migrationStepRoute,
  NONDISTINCT_MAPPING_KEY,
  STEP_PARAM,
  stepOfStatus,
  stepsOf,
  targetCodes,
  useFieldMapping,
  useMigration,
  useSourceFile,
} from "../../lib/api/queries/migrations";
import { fetchAllParameters, parametersKey, valueControl } from "../../lib/api/queries/policies";
import { formatDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams } from "../../lib/url/params";
import { DataPageHeader, digestText } from "./imports";
import {
  type FieldMappingState,
  type MappingConfirmation,
  MigrationMappingStep,
} from "./migration-mapping";

// The DS-CMP-24 progress label "Importing legacy database <no>" is the job region's accessible name and
// the SCR-ST-12 banner's subject; the progress renders what API-S-Job reports (done / total) and names
// no unit noun (F-LMG confirmation (3) of 2026-09-21).
const RAIL_STATUSES_AFTER_MAPPING = new Set([
  "IMPORTING",
  "IMPORTED",
  "RECONCILED",
  "SUBMITTED",
  "PROMOTED",
]);

function Frame({
  title,
  current,
  meta,
  children,
}: {
  readonly title: string;
  readonly current?: string | undefined;
  readonly meta?: ReactNode;
  readonly children: ReactNode;
}) {
  // The "Migrations" crumb links once SF-19 (list) is built (XR-14: linked only once built).
  return (
    <div data-testid="SF-19-page" className="flex flex-col gap-4">
      <DataPageHeader title={title} current={current ?? title} meta={meta} />
      {children}
    </div>
  );
}

function LoadingFrame() {
  return (
    <Frame title={t("data.migrations.detail.documentTitle")}>
      <Skeleton region={t("data.migrations.stepper")} shape="text" count={2} />
    </Frame>
  );
}

export function MigrationDetail() {
  const { migrationId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  if (me.isError) {
    return (
      <Frame title={t("data.migrations.detail.documentTitle")}>
        <Banner tone="negative" title={me.error.message} />
      </Frame>
    );
  }
  if (me.data === undefined) {
    return <LoadingFrame />;
  }
  // A legacy migration is the workspace's: every route of it asks `migration.run` for all
  // entities (04 API-R-48; SCREENS §0.6 SCR-PERM-02 (c)).
  if (!access.holdsForAll(MIGRATION_RUN_PERMISSION)) {
    return (
      <Frame title={t("data.migrations.detail.documentTitle")}>
        <AccessLimited
          area={t("data.access.migrations")}
          permissions={[MIGRATION_RUN_PERMISSION]}
          allEntities={
            access.holdsAnywhere(MIGRATION_RUN_PERMISSION)
              ? {
                  message: "data.migrations.access.allEntities",
                  permission: MIGRATION_RUN_PERMISSION,
                }
              : undefined
          }
        />
      </Frame>
    );
  }
  return <DetailPage me={me.data} migrationId={migrationId} />;
}

function stepParam(search: string): string | null {
  const raw = rawParams(search).find((param) => param.name === STEP_PARAM);
  return raw === undefined ? null : decodeValue(raw.value);
}

function DetailPage({ me, migrationId }: { readonly me: Me; readonly migrationId: string }) {
  const location = useLocation();
  const found = useMigration(migrationId);
  if (found.isError) {
    const error: unknown = found.error;
    if (error instanceof ApiProblem && error.status === 404) {
      return (
        <Frame title={t("data.migrations.detail.documentTitle")}>
          <EmptyState
            title={t("data.migrations.detail.notFound")}
            description={t("data.migrations.detail.notFoundDescription")}
          />
        </Frame>
      );
    }
    return (
      <Frame title={t("data.migrations.detail.documentTitle")}>
        <Banner
          tone="negative"
          title={t("data.migrations.detail.loadError")}
          actions={
            <Button variant="secondary" size="sm" onClick={() => void found.refetch()}>
              {t("common.job.retry")}
            </Button>
          }
        >
          {error instanceof Error ? error.message : null}
        </Banner>
      </Frame>
    );
  }
  if (found.data === undefined) {
    return <LoadingFrame />;
  }
  const migration = found.data;
  const requested = stepParam(location.search);
  if (!isMigrationStep(migration.mode, requested)) {
    return (
      <Navigate
        replace
        to={migrationStepRoute(
          migration.id,
          stepOfStatus(migration.mode, migration.status, migration.profile),
        )}
        state={location.state}
      />
    );
  }
  // Keyed by the migration (Codex 1546 R2): a cached migration B never inherits A's confirmation or findings.
  return <StepPage key={migration.id} me={me} migration={migration} step={requested} />;
}

/** The stepper: every step of the mode; only the built steps of the journey are navigable. */
function migrationSteps(migration: Migration, page: MigrationStep): readonly Step[] {
  const steps = stepsOf(migration.mode);
  const current = stepOfStatus(migration.mode, migration.status, migration.profile);
  const currentIndex = steps.indexOf(current);
  const profile = migration.profile;
  return steps.map((step, index) => {
    let state: Step["state"] = "pending";
    if (index < currentIndex) {
      state = "complete";
    } else if (index === currentIndex) {
      state = migration.status === "FAILED" ? "error" : "current";
    }
    let caption: string | undefined;
    if (step === "profile" && profile !== null) {
      caption = t("data.migrations.caption.rows", { count: profile.contract_live_rows });
    } else if (step === "mapping" && RAIL_STATUSES_AFTER_MAPPING.has(migration.status)) {
      caption = t("data.migrations.caption.confirmed");
    } else if (step === "import" && migration.status !== "PROFILED" && index < currentIndex) {
      caption = t("data.migrations.caption.imported");
    } else if (
      step === "reconciliation" &&
      migration.unexplained_count !== null &&
      migration.unexplained_count !== undefined
    ) {
      caption = t("data.migrations.caption.unexplained", { count: migration.unexplained_count });
    } else if (step === "promotion" && index >= currentIndex && migration.status !== "PROMOTED") {
      caption = t("data.migrations.caption.notSubmitted");
    }
    // A built step links while the migration is still PROFILED (the mapping is editable until
    // `/import` captures it); an unbuilt step never links (separate WEB items).
    const navigable =
      isBuiltStep(migration.mode, step) && migration.status === "PROFILED" && step !== page;
    return {
      id: step,
      label: t(`data.migrations.step.${step}`),
      state,
      caption,
      ...(navigable ? { to: migrationStepRoute(migration.id, step) } : {}),
    };
  });
}

function MigrationMeta({ migration }: { readonly migration: Migration }) {
  const file = useSourceFile(migration.source_file_id);
  const chip = chipFor("E-76", migration.status);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-sm text-fg-2">
      <OutlineChip label={t(`data.migrations.mode.${migration.mode}`)} />
      {chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />}
      {file.data?.original_filename === undefined || file.data.original_filename === null ? null : (
        <span className="text-fg-1">{file.data.original_filename}</span>
      )}
      <span>
        {t("data.migrations.meta.sha256")}{" "}
        <span className="font-mono text-mono-sm" title={migration.source_sha256}>
          {digestText(migration.source_sha256)}
        </span>
      </span>
      {migration.cutover_date === null ? null : (
        <span>
          {t("data.migrations.meta.cutover", { date: formatDate(migration.cutover_date) })}
        </span>
      )}
      <span>{t("data.migrations.meta.runBy", { name: migration.created_by.display_name })}</span>
    </div>
  );
}

function StepPage({
  me,
  migration,
  step,
}: {
  readonly me: Me;
  readonly migration: Migration;
  readonly step: MigrationStep;
}) {
  // The confirmation of "Confirm mapping" lives on the page until "Run import" posts it (J-20.3); a
  // refused `/import` comes back to the mapping step with its findings.
  const [confirmation, setConfirmation] = useState<MappingConfirmation | null>(null);
  const [refused, setRefused] = useState<ApiProblem | null>(null);
  // Belt and braces with the key above: state of another migration is never applied to this one.
  const own =
    confirmation !== null && confirmation.migrationId === migration.id ? confirmation : null;
  const navigate = useNavigate();
  const built = isBuiltStep(migration.mode, step);
  const title = t("data.migrations.detail.title", { no: migration.migration_no });

  let content: ReactNode = null;
  if (step === "profile" && migration.status === "FAILED" && migration.profile === null) {
    // The only Profile-step region this build renders: §10.3 "any | Failed" SCR-ST-12 for a batch that
    // failed while profiling (no profile written — F-LMG's rule, SCREENS_B row 1.22).
    content = <ProfilingFailed migration={migration} />;
  } else if (built && step === "mapping") {
    content = (
      <MappingStepPage
        key={migration.id}
        migration={migration}
        problem={own === null ? null : refused}
        initial={own}
        onConfirm={(next) => {
          setConfirmation(next);
          setRefused(null);
          void navigate(migrationStepRoute(migration.id, "import"));
        }}
      />
    );
  } else if (built && step === "import") {
    content = (
      <ImportStepPage
        me={me}
        migration={migration}
        confirmation={own}
        onRefused={(problem) => {
          setRefused(problem);
          void navigate(migrationStepRoute(migration.id, "mapping"));
        }}
        onBack={() => void navigate(migrationStepRoute(migration.id, "mapping"))}
      />
    );
  }

  return (
    <Frame
      title={title}
      current={migration.migration_no}
      meta={<MigrationMeta migration={migration} />}
    >
      <div data-testid="SF-19-stepper">
        <Stepper
          label={t("data.migrations.stepper")}
          steps={migrationSteps(migration, step)}
          currentId={step}
        />
      </div>
      {content === null ? null : <div className="flex flex-col gap-4">{content}</div>}
    </Frame>
  );
}

/** SCR-ST-12 for the PROFILE phase: "Profiling <file name> failed. Nothing was committed." */
function ProfilingFailed({ migration }: { readonly migration: Migration }) {
  const file = useSourceFile(migration.source_file_id);
  if (file.data === undefined && !file.isError) {
    return <Skeleton region={t("data.migrations.step.profile")} shape="text" count={1} />;
  }
  // The source's name; the SHA-256 prefix stands in when the file row cannot be read.
  const name = file.data?.original_filename ?? digestText(migration.source_sha256);
  return (
    <section
      aria-label={t("data.migrations.step.profile")}
      data-testid="SF-19-step-profile"
      className="flex flex-col gap-4"
    >
      <Banner
        tone="negative"
        announce="static"
        headingLevel={2}
        title={t("common.job.failed", { label: t("data.migrations.profile.running", { name }) })}
      >
        {migration.problem?.detail ?? null}
      </Banner>
    </section>
  );
}

function MappingStepPage({
  migration,
  problem,
  initial,
  onConfirm,
}: {
  readonly migration: Migration;
  readonly problem: ApiProblem | null;
  readonly initial: MappingConfirmation | null;
  readonly onConfirm: (confirmation: MappingConfirmation) => void;
}) {
  const calendars = useQuery({ queryKey: calendarsKey(), queryFn: fetchAllCalendars });
  const entities = useQuery({ queryKey: allEntitiesKey(), queryFn: fetchAllEntities });
  const parameters = useQuery({ queryKey: parametersKey(), queryFn: fetchAllParameters });
  const fieldMapping = useFieldMapping();
  const failed = [calendars, entities, parameters].find((query) => query.isError);
  if (failed !== undefined) {
    return (
      <Banner tone="negative" title={t("data.migrations.detail.loadError")}>
        {failed.error instanceof Error ? failed.error.message : null}
      </Banner>
    );
  }
  if (
    calendars.data === undefined ||
    entities.data === undefined ||
    parameters.data === undefined
  ) {
    return <Skeleton region={t("data.migrations.step.mapping")} shape="text" count={4} />;
  }
  // The table's own states: it never blocks the mapping (SCR-ST-05 for its read, with Retry).
  let fieldMappingState: FieldMappingState;
  if (fieldMapping.isError) {
    const error: unknown = fieldMapping.error;
    fieldMappingState = {
      kind: "failed",
      message: error instanceof Error ? error.message : null,
      onRetry: () => void fieldMapping.refetch(),
    };
  } else if (fieldMapping.data === undefined) {
    fieldMappingState = { kind: "loading" };
  } else {
    fieldMappingState = { kind: "ready", rows: fieldMapping.data };
  }
  const literals = (code: string): readonly string[] => {
    const parameter = parameters.data.find((candidate) => candidate.code === code);
    return parameter === undefined ? [] : valueControl(parameter.value_schema).options;
  };
  return (
    <MigrationMappingStep
      migration={migration}
      calendars={calendars.data}
      entities={entities.data}
      nondistinctOptions={literals(NONDISTINCT_MAPPING_KEY)}
      materialRightOptions={literals(MATERIAL_RIGHT_CONVENTION_KEY)}
      fieldMapping={fieldMappingState}
      problem={problem}
      initial={initial}
      onConfirm={onConfirm}
    />
  );
}

function ImportStepPage({
  migration,
  confirmation,
  onRefused,
  onBack,
}: {
  readonly me: Me;
  readonly migration: Migration;
  readonly confirmation: MappingConfirmation | null;
  readonly onRefused: (problem: ApiProblem) => void;
  readonly onBack: () => void;
}) {
  const command = useCommand({
    method: "POST",
    path: migrationImportPath(migration.id),
    invalidates: [EVERY_MIGRATION, migrationKey(migration.id)],
  });
  const jobId = migration.job_id ?? command.jobId;
  const job = useJob(migration.status === "PROFILED" ? null : jobId);
  const label = t("data.migrations.import.running", { no: migration.migration_no });
  const announced = useRef(false);
  useEffect(() => {
    if (!announced.current && job.data !== undefined && isTerminal(job.data)) {
      announced.current = true;
    }
  }, [job.data]);

  if (migration.status === "PROFILED") {
    if (confirmation === null || confirmation.migrationId !== migration.id) {
      // Nothing confirmed for THIS migration on this visit (a reload, a direct link, or another
      // migration's confirmation — Codex 1546 R2): the mapping comes first.
      return <Navigate replace to={migrationStepRoute(migration.id, "mapping")} />;
    }
    const run = async () => {
      const outcome = await command.submit(
        importBody(
          confirmation.cutoverDate,
          confirmation.rows,
          confirmation.defaults,
          confirmation.parameters,
        ),
      );
      if (outcome.kind === "failed") {
        onRefused(outcome.problem);
      }
    };
    return (
      <section
        aria-label={t("data.migrations.step.import")}
        data-testid="SF-19-step-import"
        className="flex flex-col gap-4"
      >
        <p data-testid="SF-19-import-summary" className="text-body-md text-fg-1">
          {t("data.migrations.import.summary", {
            date: formatDate(confirmation.cutoverDate),
            entities: targetCodes(confirmation.rows).length,
            contracts: migration.profile?.contracts ?? 0,
          })}
        </p>
        {command.pending || command.jobId !== null ? (
          <section
            aria-label={label}
            data-testid="SF-19-job"
            className="rounded-lg border border-default bg-surface p-4"
          >
            <JobProgress
              label={label}
              job={
                command.job ?? {
                  id: command.jobId ?? migration.id,
                  state: "RUNNING",
                  progress: { done: 0, total: null },
                  started_at: null,
                  problem: null,
                }
              }
              unit=""
            />
          </section>
        ) : null}
        <div className="flex items-center gap-3 border-t border-hairline pt-3">
          <Button variant="secondary" onClick={onBack}>
            {t("data.migrations.back")}
          </Button>
          <span className="flex-1" />
          <Button
            variant="primary"
            loading={command.pending || command.jobId !== null}
            onClick={() => void run()}
          >
            {t("data.migrations.import.run")}
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label={t("data.migrations.step.import")}
      data-testid="SF-19-step-import"
      className="flex flex-col gap-4"
    >
      {migration.status === "FAILED" && job.data === undefined ? (
        <Banner
          tone="negative"
          announce="static"
          headingLevel={2}
          title={t("common.job.failed", { label })}
        >
          {migration.problem?.detail ?? null}
        </Banner>
      ) : null}
      {jobId === null ? null : (
        <section
          aria-label={label}
          data-testid="SF-19-job"
          className="rounded-lg border border-default bg-surface p-4"
        >
          <JobProgress
            label={label}
            job={
              job.data ?? {
                id: jobId,
                state: migration.status === "IMPORTING" ? "RUNNING" : "SUCCEEDED",
                progress: { done: 0, total: null },
                started_at: migration.started_at,
                problem: null,
              }
            }
            unit=""
          />
        </section>
      )}
    </section>
  );
}

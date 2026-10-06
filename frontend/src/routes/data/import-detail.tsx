// SF-10:detail Import wizard steps (SCREENS §12.2, §12.3; §0.4 RT-44; §0.5 SCR-URL-15, SCR-URL-32; §0.7
// SCR-PERM-01, SCR-ST-05, SCR-ST-07, SCR-ST-12; §0.8 E-40, E-41; DESIGN_SYSTEM DS-CMP-06, DS-CMP-09,
// DS-CMP-10, DS-CMP-13, DS-CMP-16, DS-CMP-18, DS-CMP-19, DS-CMP-24, DS-CMP-29; 04 API-R-43, API-R-11
// `GET /jobs`, API-R-09 `GET /approvals/{id}`; PRD SM-05; BUILD_SPEC DIN-16).
//
// `/data/imports/:importId` redirects to the step of the import's status. Each step page holds the Data
// frame (breadcrumb "Data / Imports / <file name>", `h1` the template name, the meta row and the status
// chip), the stepper "Import steps", the step's regions and the sticky footer "Back" / "Next". While a job
// of the import runs, the page reads the import and its jobs every 2 seconds and shows the DS-CMP-24
// indicator in place, so the user can leave and come back (REQ-UX-021). When the job of the page's step
// has finished and the import has moved on, the page moves to the step of the new status.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress, type JobProgressJob } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field } from "../../components/form/Field";
import { DownloadSimple, PencilSimple, Plus, X, XCircle } from "../../components/icons/registry";
import { type Step, Stepper } from "../../components/record/Stepper";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip, ToneChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, type Job } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { queryKey } from "../../lib/api/query-keys";
import {
  type Approval,
  approvalKey,
  fetchApproval,
  requestRoute,
} from "../../lib/api/queries/approvals";
import {
  fetchImportTemplates,
  type ImportTemplate,
  importTemplatesKey,
  templateName,
} from "../../lib/api/queries/import-templates";
import {
  CANCELLABLE_STATUSES,
  controlTotalsOf,
  type ControlTotals,
  diffSummaryOf,
  downloadErrorReport,
  EVERY_IMPORT,
  EXCEPTIONS_ROUTE,
  fetchFileFindings,
  fetchImport,
  fetchImportDiff,
  fetchImportJobs,
  fetchImportRowsPage,
  fileFindingsKey,
  findImportRow,
  IMPORT_POLL_INTERVAL_MS,
  IMPORT_READ_PERMISSION,
  IMPORT_STEPS,
  IMPORT_UPLOAD_PERMISSION,
  type ImportDiffItem,
  importDiffKey,
  type ImportItem,
  importJobsKey,
  importKey,
  importName,
  type ImportRow,
  type ImportRowQuery,
  importRowsKey,
  IMPORTS_PATH,
  IMPORTS_ROUTE,
  type ImportStatus,
  type ImportStep,
  importStepRoute,
  isImportStep,
  NEW_IMPORT_ROUTE,
  RUNNING_STATUSES,
  stepOfStatus,
  totalsMismatch,
} from "../../lib/api/queries/imports";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  formatDate,
  formatNumber,
  formatPeriod,
  formatTimestamp,
  joinParts,
  NO_VALUE,
  numberParts,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import messages from "../../messages/en.json";
import { useBuiltPaths } from "../settings/index";
import {
  cellText,
  ImportRowDrawer,
  messageText,
  targetLabel,
  targetRoute,
} from "./import-row-drawer";
import { DataAccessLimited, DataPageHeader, digestText, ImportStatusCell } from "./imports";

/** SCREENS RT-57 SF-12:request. */
const APPROVAL_REQUEST_ROUTE = "/approvals/requests/:requestId";
/** 04 §15.4 IMP-01. */
const HEADER_MISMATCH = "TEMPLATE_HEADER_MISMATCH";
const LEGACY_PREFIX = "legacy_";
const CODE_PARAM = "f.code";
const ROW_PARAM = "row";
const SHEET_PARAM = "sheet";

type JobKind = Job["kind"];

/** The job each step page follows (05 §5.6). */
const STEP_JOB: Readonly<Partial<Record<ImportStep, JobKind>>> = {
  validate: "IMPORT_VALIDATE",
  review: "IMPORT_DIFF",
  committed: "IMPORT_COMMIT",
};

/** The statuses whose job a step page shows in place. */
const STEP_RUNNING: Readonly<Partial<Record<ImportStep, ReadonlySet<ImportStatus>>>> = {
  validate: new Set<ImportStatus>(["UPLOADED", "VALIDATING"]),
  review: new Set<ImportStatus>(["VALIDATED", "DIFFING"]),
  committed: new Set<ImportStatus>(["APPROVED", "COMMITTING"]),
};

const AFTER_SUBMIT: ReadonlySet<ImportStatus> = new Set<ImportStatus>([
  "SUBMITTED",
  "APPROVED",
  "REJECTED",
  "COMMITTING",
  "COMMITTED",
  "FAILED",
]);

/** The navigation state SF-10:new leaves: the import started on this visit. */
export interface UploadedState {
  readonly uploaded: true;
}

function isUploadedState(value: unknown): value is UploadedState {
  return typeof value === "object" && value !== null && "uploaded" in value;
}

/** A count as DS-FMT-21 text. */
function countText(value: number | null): string {
  return value === null ? NO_VALUE : formatNumber(value, { kind: "count" });
}

/** A diff amount (a decimal string of the contract currency's minor unit) with its decimals kept. */
export function amountText(value: string | null, delta = false): string {
  if (value === null) {
    return NO_VALUE;
  }
  const match = /^[-+]?(\d+)(?:\.(\d+))?$/.exec(value);
  if (match === null) {
    return value;
  }
  const [, integer = "0", fraction = ""] = match;
  const parts = numberParts(value, { delta });
  const grouped = numberParts(integer, { kind: "count" }).body;
  const separator = formatNumber("1.5").charAt(1);
  return joinParts({
    ...parts,
    body: fraction === "" ? grouped : `${grouped}${separator}${fraction}`,
  });
}

function dateOf(timestamp: string): string {
  try {
    return formatDate(timestampDate(timestamp));
  } catch {
    return formatTimestamp(timestamp);
  }
}

function isLegacy(item: ImportItem, template: ImportTemplate | undefined): boolean {
  return template === undefined
    ? item.template.code.startsWith(LEGACY_PREFIX)
    : template.family === "LEGACY_V1";
}

/** "2 errors in 2 rows": ERROR messages over the rows that carry one (file-level findings count 1). */
export function errorsInRows(item: ImportItem): string {
  const errors = item.finding_counts
    .filter((finding) => finding.severity === "ERROR")
    .reduce((sum, finding) => sum + Math.max(finding.rows, 1), 0);
  const rows = item.counts.errors ?? 0;
  return t("data.imports.validate.errorsInRows", {
    errors: t("data.imports.validate.errors", { count: errors, formatted: countText(errors) }),
    rows: t("data.imports.validate.rows", { count: rows, formatted: countText(rows) }),
  });
}

function validated(item: ImportItem): boolean {
  return item.counts.rows !== null;
}

/** Whether a step page shows for the import; a later step redirects to the step of the status. */
export function stepReachable(step: ImportStep, item: ImportItem, legacy: boolean): boolean {
  if (step === "map") {
    return legacy || validated(item);
  }
  if (step === "approval" && item.status === "DIFF_READY") {
    return true;
  }
  if (step === "committed" && (item.status === "APPROVED" || item.status === "COMMITTING")) {
    return true;
  }
  return IMPORT_STEPS.indexOf(step) <= IMPORT_STEPS.indexOf(stepOfStatus(item.status));
}

/** DS-CMP-18 stepper items: markers, captions and the links of completed steps. */
export function importSteps(
  item: ImportItem,
  legacy: boolean,
  page: ImportStep,
  search = "",
): Step[] {
  const status = item.status;
  const link = (step: ImportStep) => `${importStepRoute(item.id, step)}${search}`;
  const label = (key: string) => t(`data.imports.step.${key}`);
  const summary = diffSummaryOf(item);

  let map: Step;
  if (item.finding_counts.some((finding) => finding.code === HEADER_MISMATCH)) {
    map = { id: "map", label: label("map"), state: "error", caption: t("data.imports.map.error") };
  } else if (legacy) {
    map = {
      id: "map",
      label: label("map"),
      state: "skipped",
      caption: t("data.imports.map.skipped"),
    };
  } else if (!validated(item)) {
    map = { id: "map", label: label("map"), state: "pending" };
  } else if (item.header_match.some((header) => header.match === "ALIAS")) {
    map = {
      id: "map",
      label: label("map"),
      state: "complete",
      caption: t("data.imports.map.aliased"),
      to: link("map"),
    };
  } else {
    map = {
      id: "map",
      label: label("map"),
      state: "skipped",
      caption: t("data.imports.map.matched"),
    };
  }

  let validate: Step;
  if (status === "UPLOADED" || status === "VALIDATING") {
    validate = { id: "validate", label: label("validate"), state: "current" };
  } else if (status === "INVALID") {
    validate = {
      id: "validate",
      label: label("validate"),
      state: "error",
      caption: errorsInRows(item),
    };
  } else if (!validated(item)) {
    validate = {
      id: "validate",
      label: label("validate"),
      state: "current",
      caption: t("data.imports.step.cancelled"),
    };
  } else {
    const rows = item.counts.rows ?? 0;
    validate = {
      id: "validate",
      label: label("validate"),
      state: "complete",
      caption: t("data.imports.validate.rows", { count: rows, formatted: countText(rows) }),
      to: link("validate"),
    };
  }

  let review: Step;
  if (status === "VALIDATED" || status === "DIFFING") {
    review = { id: "review", label: label("review"), state: "current" };
  } else if (status === "DIFF_READY") {
    review =
      page === "approval"
        ? { id: "review", label: label("review"), state: "complete", to: link("review") }
        : { id: "review", label: label("review"), state: "current" };
  } else if (AFTER_SUBMIT.has(status)) {
    const affected = summary?.contractsAffected ?? 0;
    review = {
      id: "review",
      label: label("review"),
      state: "complete",
      caption: t("data.imports.review.affected", {
        count: affected,
        formatted: countText(affected),
      }),
      to: link("review"),
    };
  } else {
    review = { id: "review", label: label("review"), state: "pending" };
  }

  let approval: Step;
  if (status === "DIFF_READY" && page === "approval") {
    approval = { id: "approval", label: label("approval"), state: "current" };
  } else if (status === "SUBMITTED") {
    approval = {
      id: "approval",
      label: label("approval"),
      state: "current",
      caption: t("data.imports.approval.pending"),
    };
  } else if (status === "APPROVED" || status === "COMMITTING") {
    approval =
      page === "committed"
        ? {
            id: "approval",
            label: label("approval"),
            state: "complete",
            caption: t("data.imports.approval.approved"),
            to: link("approval"),
          }
        : {
            id: "approval",
            label: label("approval"),
            state: "current",
            caption: t("data.imports.approval.approved"),
          };
  } else if (status === "REJECTED") {
    approval = {
      id: "approval",
      label: label("approval"),
      state: "error",
      caption: t("data.imports.approval.rejected"),
    };
  } else if (status === "COMMITTED" || status === "FAILED") {
    approval = {
      id: "approval",
      label: label("approval"),
      state: "complete",
      caption: t("data.imports.approval.approved"),
      to: link("approval"),
    };
  } else {
    approval = { id: "approval", label: label("approval"), state: "pending" };
  }

  let committed: Step;
  if ((status === "APPROVED" || status === "COMMITTING") && page === "committed") {
    committed = { id: "committed", label: label("committed"), state: "current" };
  } else if (status === "COMMITTED") {
    committed = {
      id: "committed",
      label: label("committed"),
      state: "complete",
      caption: item.committed_at === null ? undefined : dateOf(item.committed_at),
      to: link("committed"),
    };
  } else if (status === "FAILED") {
    committed = {
      id: "committed",
      label: label("committed"),
      state: "error",
      caption: t("data.imports.committed.failedCaption"),
    };
  } else {
    committed = { id: "committed", label: label("committed"), state: "pending" };
  }

  return [
    {
      id: "upload",
      label: label("upload"),
      state: "complete",
      caption: dateOf(item.created_at),
    },
    map,
    validate,
    review,
    approval,
    committed,
  ];
}

/** SF-10:new with the same template and mode (SCR-URL-28); the effective date rides on the state. */
export function correctedFileRoute(item: ImportItem): string {
  const search = new URLSearchParams({ template: item.template.code });
  const mode = item.parameters.mode;
  if (typeof mode === "string") {
    search.set("mode", mode);
  }
  return `${NEW_IMPORT_ROUTE}?${search.toString()}`;
}

/** The parameters SF-10:new keeps for a corrected file. */
export interface CorrectedFileState {
  readonly parameters: Readonly<Record<string, unknown>>;
}

function blockedReason(page: ImportStep, item: ImportItem): string | null {
  const status = item.status;
  if (status === "CANCELLED") {
    return t("data.imports.cancelled");
  }
  if (page === "validate") {
    if (status === "INVALID") {
      return t("data.imports.next.invalid", { errors: errorsInRows(item) });
    }
    return status === "UPLOADED" || status === "VALIDATING"
      ? t("data.imports.next.validating")
      : null;
  }
  if (page === "review") {
    return status === "VALIDATED" || status === "DIFFING" ? t("data.imports.next.diffing") : null;
  }
  if (page === "approval") {
    if (status === "DIFF_READY") {
      return t("data.imports.next.submit");
    }
    if (status === "SUBMITTED") {
      return t("data.imports.next.waiting");
    }
    return status === "REJECTED" ? t("data.imports.next.rejected") : null;
  }
  return null;
}

function Frame({
  title,
  crumb,
  meta,
  children,
}: {
  readonly title: string;
  readonly crumb?: string | undefined;
  readonly meta?: ReactNode;
  readonly children: ReactNode;
}) {
  return (
    <div data-testid="SF-10-detail-page" className="flex flex-col gap-4">
      <DataPageHeader
        title={title}
        crumbs={[{ label: t("data.imports.title"), to: IMPORTS_ROUTE }]}
        current={crumb ?? title}
        meta={meta}
      />
      {children}
    </div>
  );
}

function problemText(problem: unknown): string {
  if (problem instanceof ApiProblem) {
    return problem.requestId === null
      ? problem.title
      : `${problem.title} ${t("approvals.reference", { reference: problem.requestId })}`;
  }
  return problem instanceof Error ? problem.message : String(problem);
}

/** SCREENS §0.7 SCR-ST-07 and SCR-ST-05 for the import read. */
function ImportLoadFailure({
  error,
  onRetry,
}: {
  readonly error: unknown;
  readonly onRetry: () => void;
}) {
  const navigate = useNavigate();
  if (error instanceof ApiProblem && error.status === 404) {
    return (
      <Frame title={t("data.imports.detail.notFound")}>
        <EmptyState
          title={t("data.imports.detail.notFound")}
          description={t("data.imports.detail.notFoundDescription")}
          action={{
            label: t("data.imports.detail.goToImports"),
            onAction: () => void navigate(IMPORTS_ROUTE),
          }}
        />
      </Frame>
    );
  }
  return (
    <Frame title={t("data.imports.detail.documentTitle")}>
      <Banner
        tone="negative"
        title={t("data.imports.detail.loadError")}
        actions={
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {t("data.imports.retry")}
          </Button>
        }
      >
        {problemText(error)}
      </Banner>
    </Frame>
  );
}

function LoadingFrame() {
  return (
    <Frame title={t("data.imports.detail.documentTitle")}>
      <Skeleton region={t("data.imports.stepper")} shape="text" count={2} />
      <Skeleton region={t("data.imports.figures.label")} shape="kpi" count={5} />
    </Frame>
  );
}

function useImport(importId: string) {
  return useQuery({
    queryKey: importKey(importId),
    queryFn: () => fetchImport(importId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data !== undefined && RUNNING_STATUSES.has(query.state.data.status)
        ? IMPORT_POLL_INTERVAL_MS
        : false,
  });
}

/** RT-44 `/data/imports/:importId`: the step of the import's status, keeping the search string. */
export function ImportRedirect() {
  const { importId = "" } = useParams();
  const location = useLocation();
  const me = useMe();
  const access = useAccess();
  const found = useImport(importId);
  if (me.data !== undefined && !access.holdsAnywhere(IMPORT_READ_PERMISSION)) {
    return (
      <Frame title={t("data.imports.detail.documentTitle")}>
        <DataAccessLimited area={t("data.access.imports")} />
      </Frame>
    );
  }
  if (found.data !== undefined) {
    return (
      <Navigate
        replace
        to={`${importStepRoute(importId, stepOfStatus(found.data.status))}${location.search}`}
        state={location.state}
      />
    );
  }
  if (found.isError) {
    return <ImportLoadFailure error={found.error} onRetry={() => void found.refetch()} />;
  }
  return <LoadingFrame />;
}

/** RT-44 SF-10:detail. */
export function ImportDetail() {
  const { importId = "", step } = useParams();
  const me = useMe();
  const access = useAccess();
  if (me.isError) {
    return (
      <Frame title={t("data.imports.detail.documentTitle")}>
        <Banner tone="negative" title={me.error.message} />
      </Frame>
    );
  }
  if (me.data === undefined) {
    return <LoadingFrame />;
  }
  if (!access.holdsAnywhere(IMPORT_READ_PERMISSION)) {
    return (
      <Frame title={t("data.imports.detail.documentTitle")}>
        <DataAccessLimited area={t("data.access.imports")} />
      </Frame>
    );
  }
  return <DetailPage me={me.data} importId={importId} step={step} />;
}

function DetailPage({
  me,
  importId,
  step,
}: {
  readonly me: Me;
  readonly importId: string;
  readonly step: string | undefined;
}) {
  const location = useLocation();
  const found = useImport(importId);
  const templates = useQuery({ queryKey: importTemplatesKey(), queryFn: fetchImportTemplates });
  if (found.isError) {
    return <ImportLoadFailure error={found.error} onRetry={() => void found.refetch()} />;
  }
  if (found.data === undefined) {
    return <LoadingFrame />;
  }
  const item = found.data;
  const template =
    templates.data?.find(
      (candidate) =>
        candidate.code === item.template.code && candidate.version === item.template.version,
    ) ?? templates.data?.find((candidate) => candidate.code === item.template.code);
  const legacy = isLegacy(item, template);
  if (!isImportStep(step) || !stepReachable(step, item, legacy)) {
    return (
      <Navigate
        replace
        to={`${importStepRoute(importId, stepOfStatus(item.status))}${location.search}`}
        state={location.state}
      />
    );
  }
  return <StepPage me={me} item={item} template={template} legacy={legacy} page={step} />;
}

interface StepPageProps {
  readonly me: Me;
  readonly item: ImportItem;
  readonly template: ImportTemplate | undefined;
  readonly legacy: boolean;
  readonly page: ImportStep;
}

/**
 * The jobs of the import, read again while the import or one of its jobs still runs. A read the API
 * refuses (null) is not repeated: the stand-in shows instead (SCREENS §0.6 SCR-PERM-02).
 */
function useImportJobs(item: ImportItem) {
  const running = RUNNING_STATUSES.has(item.status);
  return useQuery({
    queryKey: importJobsKey(item.id),
    queryFn: () => fetchImportJobs(item.id),
    retry: false,
    refetchInterval: (query) =>
      query.state.data !== null &&
      (running || query.state.data?.some((job) => !isTerminal(job)) === true)
        ? IMPORT_POLL_INTERVAL_MS
        : false,
  });
}

/** A stand-in while the job itself is not readable (the caller may read only its own jobs). */
function pendingJob(item: ImportItem): JobProgressJob {
  return {
    id: item.id,
    state: "RUNNING",
    progress: { done: 0, total: null },
    started_at: null,
    problem: null,
  };
}

function StepPage({ me, item, template, legacy, page }: StepPageProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const jobs = useImportJobs(item);
  const csv = template === undefined ? !legacy : template.file_format === "CSV";
  const pageJobKind = STEP_JOB[page];
  const pageJob =
    pageJobKind === undefined ? undefined : jobs.data?.find((job) => job.kind === pageJobKind);
  const pageRunning = STEP_RUNNING[page]?.has(item.status) === true;
  const showJob = pageRunning || (pageJob !== undefined && !isTerminal(pageJob));

  // The page moves on once its own job has finished and the import has reached a later step, when
  // the import was still moving on while the page showed; a step the user opens stays put.
  const sawRunning = useRef(isUploadedState(location.state) || RUNNING_STATUSES.has(item.status));
  const shownPage = useRef(page);
  if (shownPage.current !== page) {
    shownPage.current = page;
    sawRunning.current = RUNNING_STATUSES.has(item.status);
  }
  if (RUNNING_STATUSES.has(item.status)) {
    sawRunning.current = true;
  }
  const target = stepOfStatus(item.status);
  const later = page !== "map" && IMPORT_STEPS.indexOf(target) > IMPORT_STEPS.indexOf(page);
  const pageJobDone = pageJob === undefined || isTerminal(pageJob);
  useEffect(() => {
    if (sawRunning.current && later && pageJobDone && !showJob) {
      void navigate(`${importStepRoute(item.id, target)}${location.search}`, {
        replace: true,
        state: location.state,
      });
    }
  }, [later, pageJobDone, showJob, target, item.id, location.search, location.state, navigate]);

  // DS-CMP-18: validation completion is announced politely.
  const previous = useRef<ImportStatus>(item.status);
  useEffect(() => {
    const before = previous.current;
    previous.current = item.status;
    if (before === item.status || (before !== "UPLOADED" && before !== "VALIDATING")) {
      return;
    }
    if (item.status === "INVALID") {
      announce(t("data.imports.validate.finishedErrors", { errors: errorsInRows(item) }), "polite");
    } else if (item.status !== "VALIDATING") {
      const warnings = item.counts.warnings ?? 0;
      announce(
        t("data.imports.validate.finished", { count: warnings, formatted: countText(warnings) }),
        "polite",
      );
    }
  }, [item]);

  const params = rawParams(location.search);
  const rowValue = params.find((param) => param.name === ROW_PARAM);
  const sheetValue = params.find((param) => param.name === SHEET_PARAM);
  const rowNumber = rowValue === undefined ? Number.NaN : Number(decodeValue(rowValue.value));
  const drawerOpen =
    (page === "validate" || page === "committed") &&
    Number.isSafeInteger(rowNumber) &&
    rowNumber >= 1;
  const closeDrawer = () => {
    void navigate(
      { search: withParams(location.search, { [ROW_PARAM]: null, [SHEET_PARAM]: null }) },
      { replace: true, state: location.state },
    );
  };

  // Step links keep the context parameters and drop the page's own `row`, `sheet` and `f.code`.
  const stepSearch = withParams(location.search, {
    [ROW_PARAM]: null,
    [SHEET_PARAM]: null,
    [CODE_PARAM]: null,
  });
  const index = IMPORT_STEPS.indexOf(page);
  const previousStep = IMPORT_STEPS[index - 1];
  const nextStep = IMPORT_STEPS[index + 1];
  const back =
    previousStep !== undefined && stepReachable(previousStep, item, legacy)
      ? previousStep
      : undefined;
  const blocked =
    nextStep === undefined
      ? null
      : (blockedReason(page, item) ??
        (stepReachable(nextStep, item, legacy) ? null : t("data.imports.next.notYet")));

  const job = pageJob ?? pendingJob(item);
  const fileName = importName(item);
  const name = templateName(item.template);

  let content: ReactNode;
  if (page === "map") {
    content = <MapStep item={item} legacy={legacy} />;
  } else if (page === "validate") {
    content = (
      <ValidateStep
        item={item}
        template={template}
        csv={csv}
        built={built}
        job={showJob ? job : null}
      />
    );
  } else if (page === "review") {
    content = <ReviewStep me={me} item={item} job={showJob ? job : null} />;
  } else if (page === "approval") {
    content = <ApprovalStep me={me} item={item} built={built} />;
  } else {
    content = <CommittedStep item={item} built={built} job={showJob ? job : null} />;
  }

  return (
    <Frame title={name} crumb={fileName} meta={<ImportMeta item={item} />}>
      <div data-testid="SF-10-stepper">
        <Stepper
          label={t("data.imports.stepper")}
          steps={importSteps(item, legacy, page, stepSearch)}
          currentId={page}
        />
      </div>
      <div className="flex flex-col gap-4">{content}</div>
      <div className="sticky -bottom-[var(--gutter)] -mb-[var(--gutter)] flex items-center gap-3 border-t border-hairline bg-surface py-3">
        {back === undefined ? null : (
          <Button
            variant="secondary"
            onClick={() => void navigate(`${importStepRoute(item.id, back)}${stepSearch}`)}
          >
            {t("data.imports.back")}
          </Button>
        )}
        <span className="flex-1" />
        {/* DS-CMP-18: "Next" reports what blocks it. */}
        {nextStep === undefined || blocked === null ? null : (
          <span data-testid="SF-10-next-blocked" className="text-body-sm text-fg-2">
            {blocked}
          </span>
        )}
        {nextStep === undefined ? null : (
          <Button
            variant="primary"
            disabledReason={blocked ?? undefined}
            onClick={() => void navigate(`${importStepRoute(item.id, nextStep)}${stepSearch}`)}
          >
            {t("data.imports.next")}
          </Button>
        )}
      </div>
      {drawerOpen ? (
        <ImportRowDrawer
          item={item}
          rowNumber={rowNumber}
          sheetName={sheetValue === undefined || csv ? null : decodeValue(sheetValue.value)}
          csv={csv}
          onClose={closeDrawer}
        />
      ) : null}
    </Frame>
  );
}

/** The meta row: file name, SHA-256, parameters, uploader, upload time and the status chip. */
function ImportMeta({ item }: { readonly item: ImportItem }) {
  const effective = item.parameters.effective_date;
  const mode = item.parameters.mode;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-sm text-fg-2">
      <span className="text-fg-1">{importName(item)}</span>
      <span>
        {t("data.imports.meta.sha256")}{" "}
        <span className="font-mono text-mono-sm" title={item.file.sha256}>
          {digestText(item.file.sha256)}
        </span>
      </span>
      {typeof effective === "string" ? (
        <span>{t("data.imports.meta.effectiveDate", { date: formatDate(effective) })}</span>
      ) : null}
      {typeof mode === "string" ? (
        <span>{t("data.imports.meta.mode", { mode: t(`data.imports.mode.${mode}`) })}</span>
      ) : null}
      <span>{t("data.imports.meta.uploadedBy", { name: item.created_by.display_name })}</span>
      <span>{formatTimestamp(item.created_at)}</span>
      <ImportStatusCell status={item.status} />
    </div>
  );
}

// --- Step 2 Map columns ------------------------------------------------------------------------------

function MapStep({ item, legacy }: { readonly item: ImportItem; readonly legacy: boolean }) {
  const navigate = useNavigate();
  const mismatch = item.finding_counts.some((finding) => finding.code === HEADER_MISMATCH);
  const findings = useQuery({
    queryKey: fileFindingsKey(item.id),
    queryFn: () => fetchFileFindings(item.id),
    enabled: mismatch,
    retry: false,
  });
  if (mismatch) {
    const message = findings.data?.find((finding) => finding.ruleId === HEADER_MISMATCH)?.message;
    return (
      <Banner
        tone="negative"
        announce="static"
        headingLevel={2}
        title={t("data.imports.map.mismatchTitle")}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void navigate(correctedFileRoute(item))}
          >
            {t("data.imports.map.chooseProfile")}
          </Button>
        }
      >
        {message === undefined ? null : messageText({ message, rule_id: HEADER_MISMATCH })}
      </Banner>
    );
  }
  if (legacy) {
    return <p className="text-body-sm text-fg-2">{t("data.imports.map.skipped")}</p>;
  }
  if (item.header_match.length === 0) {
    return <p className="text-body-sm text-fg-2">{t("data.imports.map.matchedDescription")}</p>;
  }
  return (
    <table data-testid="SF-10-grid-header-match" className="w-full border-collapse text-body-sm">
      <caption className="mb-2 text-start text-title-sm text-fg-1">
        {t("data.imports.map.caption")}
      </caption>
      <thead>
        <tr className="border-b border-default text-fg-2">
          <th scope="col" className="py-2 pe-4 text-start font-medium">
            {t("data.imports.map.source")}
          </th>
          <th scope="col" className="py-2 pe-4 text-start font-medium">
            {t("data.imports.map.samples")}
          </th>
          <th scope="col" className="py-2 pe-4 text-start font-medium">
            {t("data.imports.map.field")}
          </th>
          <th scope="col" className="py-2 text-start font-medium">
            {t("data.imports.map.match")}
          </th>
        </tr>
      </thead>
      <tbody>
        {item.header_match.map((header) => (
          <tr key={header.source_column} className="border-b border-hairline">
            <th scope="row" className="py-2 pe-4 text-start font-normal text-fg-1">
              {header.source_column}
            </th>
            <td className="py-2 pe-4 font-mono text-mono-sm text-fg-2">
              {header.samples.slice(0, 3).join(", ") || NO_VALUE}
            </td>
            <td className="py-2 pe-4 font-mono text-mono-sm text-fg-1">
              {header.template_field ?? NO_VALUE}
            </td>
            <td className="py-2 text-fg-1">
              {header.match === "ALIAS"
                ? t("data.imports.map.alias", { profile: header.alias_profile_code ?? NO_VALUE })
                : t(`data.imports.map.kind.${header.match}`)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// --- Step 3 Validate --------------------------------------------------------------------------------

interface Figure {
  readonly id: string;
  readonly label: string;
  readonly value: number | null;
}

/** DS-CMP-06 import batch variant: a region "Import figures" of counts. */
function ImportFigures({ figures }: { readonly figures: readonly Figure[] }) {
  return (
    <section
      aria-label={t("data.imports.figures.label")}
      data-testid="SF-10-kpi-strip"
      className="rounded-lg border border-default bg-surface"
    >
      <dl className="grid auto-cols-fr grid-flow-col divide-x divide-hairline">
        {figures.map((figure) => (
          <div key={figure.id} className="flex flex-col gap-1 px-4 py-3">
            <dt className="text-caption text-fg-3">{figure.label}</dt>
            <dd data-testid={`SF-10-kpi-${figure.id}`} className="num text-kpi text-fg-1">
              {countText(figure.value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function selectedCodes(search: string): readonly string[] {
  const param = rawParams(search).find((item) => item.name === CODE_PARAM);
  const colon = param?.value.indexOf(":") ?? -1;
  if (param === undefined || colon < 0) {
    return [];
  }
  return param.value
    .slice(colon + 1)
    .split(",")
    .map((value) => decodeValue(value))
    .filter((value) => value !== "");
}

function codeSearch(search: string, codes: readonly string[]): string {
  const value =
    codes.length === 0
      ? null
      : `${codes.length === 1 ? "is" : "in"}:${codes.map((code) => encodeURIComponent(code)).join(",")}`;
  return withParams(search, { [CODE_PARAM]: value });
}

/** "Download error report" (04 §16.6), in the rows grid toolbar. */
function DownloadErrorReport({ item }: { readonly item: ImportItem }) {
  const toast = useToast();
  const download = () => {
    void downloadErrorReport(item).catch((error: unknown) => {
      toast.show({ tone: "negative", message: problemText(error) });
    });
  };
  return (
    <Button variant="secondary" size="sm" icon={DownloadSimple} onClick={download}>
      {t("data.imports.validate.downloadErrors")}
    </Button>
  );
}

/** DS-CMP-13 finding chips: "<code> · <rows> rows"; selecting one sets `f.code`. */
function FindingChips({ item }: { readonly item: ImportItem }) {
  const location = useLocation();
  const navigate = useNavigate();
  const codes = selectedCodes(location.search);
  const toggle = (code: string) => {
    const next = codes.includes(code) ? codes.filter((value) => value !== code) : [...codes, code];
    void navigate(
      { search: codeSearch(location.search, next) },
      { replace: true, state: location.state },
    );
  };
  if (item.finding_counts.length === 0) {
    return null;
  }
  return (
    <div
      role="group"
      aria-label={t("data.imports.findings.label")}
      className="flex flex-wrap gap-2"
    >
      {item.finding_counts.map((finding) => {
        const pressed = codes.includes(finding.code);
        return (
          <button
            key={finding.code}
            type="button"
            aria-pressed={pressed}
            onClick={() => toggle(finding.code)}
            className={
              pressed
                ? "inline-flex h-7 items-center gap-1.5 rounded-full border border-accent-solid bg-accent-subtle px-2.5 text-body-sm text-fg-1"
                : "inline-flex h-7 items-center gap-1.5 rounded-full border border-control bg-surface px-2.5 text-body-sm text-fg-1 hover:bg-hover"
            }
          >
            <span className="font-mono text-mono-sm">{finding.code}</span>{" "}
            <span className="text-fg-2">
              {t("data.imports.findings.rows", {
                count: finding.rows,
                formatted: countText(finding.rows),
              })}
            </span>
            {pressed ? <X aria-hidden="true" size={14} className="text-fg-3" /> : null}
          </button>
        );
      })}
    </div>
  );
}

function rowSearch(search: string, row: ImportRow, csv: boolean): string {
  return withParams(search, {
    [ROW_PARAM]: String(row.row_number),
    [SHEET_PARAM]: csv ? null : encodeURIComponent(row.sheet_name),
  });
}

/** SCREENS §12.2: an aggregated row's chip with the link to the row it was combined into. */
function AggregatedCell({
  item,
  row,
  csv,
}: {
  readonly item: ImportItem;
  readonly row: ImportRow;
  readonly csv: boolean;
}) {
  const location = useLocation();
  const targetId = row.aggregated_into_row_id;
  const target = useQuery({
    queryKey: queryKey("imports", "tenant", { id: item.id, row_id: targetId }),
    queryFn: () => findImportRow(item.id, targetId ?? ""),
    enabled: targetId !== null,
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const chip = chipFor("E-41", row.status);
  return (
    <span className="flex items-center gap-2">
      {chip === null ? null : <StatusChip status={chip.status} />}
      {target.data === undefined || target.data === null ? null : (
        <Link
          to={{ search: rowSearch(location.search, target.data, csv) }}
          state={location.state}
          className="text-body-sm text-accent-fg underline"
        >
          {t("data.imports.rows.aggregatedInto", { row: formatNumber(target.data.row_number) })}
        </Link>
      )}
    </span>
  );
}

function MessagesCell({ row, csv }: { readonly row: ImportRow; readonly csv: boolean }) {
  const location = useLocation();
  const [first, ...rest] = row.messages;
  if (first === undefined) {
    return null;
  }
  const text = messageText(first);
  const code = `(${first.rule_id})`;
  const prose = text.endsWith(` ${code}`) ? text.slice(0, -code.length - 1) : text;
  return (
    <span className="flex min-w-0 items-center gap-1" title={text}>
      <span className="truncate">{prose}</span>
      {prose === text ? null : (
        <>
          {" "}
          <span className="shrink-0 font-mono text-mono-sm text-fg-2">{code}</span>
        </>
      )}
      {rest.length === 0 ? null : (
        <Link
          to={{ search: rowSearch(location.search, row, csv) }}
          state={location.state}
          className="ms-1 shrink-0 text-accent-fg underline"
        >
          {t("data.imports.rows.more", { count: rest.length, formatted: countText(rest.length) })}
        </Link>
      )}
    </span>
  );
}

/** SCREENS §12.2 rows grid columns: Row, Sheet, Status, Messages, Business key, then the raw columns. */
export function rowColumns(
  item: ImportItem,
  headers: readonly string[],
  csv: boolean,
): readonly GridColumn<ImportRow>[] {
  const columns: GridColumn<ImportRow>[] = [
    {
      id: "row_number",
      header: t("data.imports.rows.column.row"),
      kind: "number",
      numberKind: "count",
      value: (row) => String(row.row_number),
      sortKey: "row_number",
      width: 88,
    },
    {
      id: "sheet",
      header: t("data.imports.rows.column.sheet"),
      kind: "text",
      value: (row) => row.sheet_name,
      width: 160,
    },
    {
      id: "status",
      header: t("data.imports.rows.column.status"),
      kind: "status",
      value: (row) => row.status,
      render: (row) => <AggregatedCell item={item} row={row} csv={csv} />,
      sortKey: "status",
      width: 200,
    },
    {
      id: "messages",
      header: t("data.imports.rows.column.messages"),
      kind: "text",
      value: (row) => (row.messages[0] === undefined ? null : messageText(row.messages[0])),
      render: (row) => <MessagesCell row={row} csv={csv} />,
      width: 720,
    },
    {
      id: "business_key",
      header: t("data.imports.rows.column.businessKey"),
      kind: "text",
      value: (row) => row.business_key,
      render: (row) =>
        row.business_key === null ? null : (
          <span className="font-mono text-mono-sm">{row.business_key}</span>
        ),
      width: 200,
    },
  ];
  for (const header of headers) {
    columns.push({
      id: `raw:${header}`,
      header,
      kind: "text",
      value: (row) => cellText(row.raw[header]),
      render: (row) => {
        const invalid = row.messages.some(
          (message) => message.severity === "ERROR" && message.field === header,
        );
        return invalid ? (
          <span className="flex items-center gap-1 font-mono text-mono-sm text-negative-fg">
            <XCircle aria-hidden="true" size={12} className="shrink-0" />
            {cellText(row.raw[header])}
            <span className="sr-only">{t("data.imports.rows.invalidCell")}</span>
          </span>
        ) : (
          <span className="font-mono text-mono-sm">{cellText(row.raw[header])}</span>
        );
      },
      width: 160,
    });
  }
  return columns;
}

function RowsGrid({
  item,
  template,
  csv,
}: {
  readonly item: ImportItem;
  readonly template: ImportTemplate | undefined;
  readonly csv: boolean;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const codes = selectedCodes(location.search);
  const query: ImportRowQuery = { status: null, codes };
  const source: GridSource<ImportRow> = {
    queryKey: importRowsKey(item.id, query),
    fetchPage: (cursor, sort) => fetchImportRowsPage(item.id, query, cursor, sort),
  };
  const headers = useMemo(() => (template?.headers ?? []).map((header) => header.name), [template]);
  const columns = useMemo(() => rowColumns(item, headers, csv), [item, headers, csv]);
  const defaultColumns = useMemo(
    () => initialColumnState(columns, csv ? ["sheet"] : []),
    [columns, csv],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  useEffect(() => {
    setColumnState(defaultColumns);
  }, [defaultColumns]);
  return (
    <div className="flex h-120 min-h-0 flex-col">
      <DataGrid<ImportRow>
        name="rows"
        title={t("data.imports.rows.title")}
        titleVisible={false}
        errorTitle={t("data.imports.rows.loadError")}
        countLabel={(value, formatted) => t("data.imports.rows.count", { count: value, formatted })}
        columns={columns}
        source={source}
        rowKey={(row) => row.id}
        rowLabel={(row) => t("data.imports.rows.rowLabel", { row: formatNumber(row.row_number) })}
        testIdPrefix="SF-10"
        rowTestKey={(row) => String(row.row_number)}
        rowHref={(row) => `${location.pathname}${rowSearch(location.search, row, csv)}`}
        toolbarActions={<DownloadErrorReport item={item} />}
        filterBar={<FindingChips item={item} />}
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        emptyState={
          <EmptyState
            title={t("data.imports.rows.empty")}
            description={t("data.imports.rows.emptyDescription")}
          />
        }
        noResults={
          <EmptyState
            title={t("data.imports.rows.noResults")}
            description=""
            action={{
              label: t("data.imports.clearFilters"),
              onAction: () =>
                void navigate(
                  { search: codeSearch(location.search, []) },
                  {
                    replace: true,
                    state: location.state,
                  },
                ),
            }}
          />
        }
      />
    </div>
  );
}

function ValidateStep({
  item,
  template,
  csv,
  built,
  job,
}: {
  readonly item: ImportItem;
  readonly template: ImportTemplate | undefined;
  readonly csv: boolean;
  readonly built: ReadonlySet<string>;
  readonly job: JobProgressJob | null;
}) {
  const navigate = useNavigate();
  // An upload is not of one entity: its rows name their entities, so `import.upload` asks any entity.
  const uploader = useAccess().holdsAnywhere(IMPORT_UPLOAD_PERMISSION);
  const fileName = importName(item);
  const rows = item.counts.rows;
  return (
    <>
      {job === null ? null : (
        <section
          aria-label={t("data.imports.validate.jobRegion")}
          className="rounded-lg border border-default bg-surface p-4"
        >
          <JobProgress
            label={t("data.imports.validate.job", { name: fileName })}
            job={job}
            unit={t("data.imports.validate.jobUnit")}
          />
        </section>
      )}
      {item.status === "CANCELLED" ? (
        <Banner
          tone="info"
          announce="static"
          headingLevel={2}
          title={t("data.imports.cancelled")}
        />
      ) : null}
      {item.status === "INVALID" ? (
        <div data-testid="SF-10-banner-rejected">
          <Banner
            tone="negative"
            announce="static"
            headingLevel={2}
            title={t("data.imports.validate.rejected.title")}
            actions={
              uploader ? (
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() =>
                      void navigate(correctedFileRoute(item), {
                        state: { parameters: item.parameters } satisfies CorrectedFileState,
                      })
                    }
                  >
                    {t("data.imports.validate.uploadCorrected")}
                  </Button>
                  {built.has(EXCEPTIONS_ROUTE) ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void navigate(`${EXCEPTIONS_ROUTE}?f.import=is:${item.id}`)}
                    >
                      {t("data.imports.validate.viewExceptions")}
                    </Button>
                  ) : null}
                </>
              ) : undefined
            }
          >
            {t("data.imports.validate.rejected.message", { errors: errorsInRows(item) })}
          </Banner>
        </div>
      ) : null}
      {rows === null ? null : (
        <>
          <ImportFigures
            figures={[
              { id: "rows", label: t("data.imports.figures.rows"), value: rows },
              { id: "valid", label: t("data.imports.figures.valid"), value: item.counts.valid },
              {
                id: "warnings",
                label: t("data.imports.figures.warnings"),
                value: item.counts.warnings,
              },
              { id: "errors", label: t("data.imports.figures.errors"), value: item.counts.errors },
              {
                id: "aggregated",
                label: t("data.imports.figures.aggregated"),
                value: item.counts.aggregated,
              },
            ]}
          />
          <RowsGrid item={item} template={template} csv={csv} />
        </>
      )}
    </>
  );
}

// --- Step 4 Review changes --------------------------------------------------------------------------

const HEAD = "py-2 pe-4 text-start font-medium";
const HEAD_END = "py-2 pe-4 text-end font-medium";
const CELL = "py-2 pe-4";
const CELL_END = "num py-2 pe-4 text-end";

function StaticTable({
  caption,
  testId,
  head,
  children,
}: {
  readonly caption: string;
  readonly testId?: string | undefined;
  readonly head: ReactNode;
  readonly children: ReactNode;
}) {
  return (
    <table data-testid={testId} className="w-full border-collapse text-body-sm">
      <caption className="mb-2 text-start text-title-sm text-fg-1">{caption}</caption>
      <thead>
        <tr className="border-b border-default text-fg-2">{head}</tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

const CATALOGUE: Readonly<Record<string, string>> = messages;

/** The label of a diff measure ("Allocated amount"); an unknown measure shows as is. */
export function measureLabel(measure: string): string {
  const key = `data.imports.measure.${measure}`;
  return CATALOGUE[key] === undefined ? measure : t(key);
}

function ChangeChip({ change }: { readonly change: ImportDiffItem["change"] }) {
  return change === "ADDED" ? (
    <ToneChip tone="info" icon={Plus} label={t("data.imports.diff.change.ADDED")} />
  ) : (
    <ToneChip tone="neutral" icon={PencilSimple} label={t("data.imports.diff.change.CHANGED")} />
  );
}

function diffColumns(): readonly GridColumn<ImportDiffItem>[] {
  return [
    {
      id: "change",
      header: t("data.imports.diff.column.change"),
      kind: "status",
      value: (entry) => entry.change,
      render: (entry) => <ChangeChip change={entry.change} />,
      width: 120,
    },
    {
      id: "contract",
      header: t("data.imports.diff.column.contract"),
      kind: "text",
      value: (entry) => entry.contract_external_id,
      render: (entry) => (
        <span className="font-mono text-mono-sm">{entry.contract_external_id}</span>
      ),
      width: 200,
    },
    {
      id: "obligation",
      header: t("data.imports.diff.column.obligation"),
      kind: "text",
      value: (entry) => entry.obligation_key,
      render: (entry) =>
        entry.obligation_key === null ? null : (
          <span className="font-mono text-mono-sm">{entry.obligation_key}</span>
        ),
      width: 120,
    },
    {
      id: "measure",
      header: t("data.imports.diff.column.measure"),
      kind: "text",
      value: (entry) => measureLabel(entry.measure),
      width: 200,
    },
    {
      id: "before",
      header: t("data.imports.diff.column.before"),
      kind: "number",
      value: (entry) => entry.before,
      render: (entry) => <span className="num">{amountText(entry.before)}</span>,
      width: 160,
    },
    {
      id: "after",
      header: t("data.imports.diff.column.after"),
      kind: "number",
      value: (entry) => entry.after,
      render: (entry) => <span className="num">{amountText(entry.after)}</span>,
      width: 160,
    },
  ];
}

function AffectedRecords({ item }: { readonly item: ImportItem }) {
  const columns = useMemo(() => diffColumns(), []);
  const defaultColumns = useMemo(() => initialColumnState(columns), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const source: GridSource<ImportDiffItem> = {
    queryKey: importDiffKey(item.id),
    fetchPage: async () => {
      const diff = await fetchImportDiff(item.id);
      return {
        items: diff.items,
        nextCursor: null,
        total: { count: diff.items.length, capped: false },
      };
    },
  };
  return (
    <div data-testid="SF-10-diff" className="flex h-96 min-h-0 flex-col">
      <DataGrid<ImportDiffItem>
        name="diff"
        title={t("data.imports.diff.title")}
        headingLevel={2}
        errorTitle={t("data.imports.diff.loadError")}
        countLabel={(value, formatted) => t("data.imports.diff.count", { count: value, formatted })}
        columns={columns}
        source={source}
        rowKey={(entry) =>
          `${entry.contract_external_id}:${entry.obligation_key ?? ""}:${entry.measure}`
        }
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        emptyState={
          <EmptyState
            title={t("data.imports.diff.empty")}
            description={t("data.imports.diff.emptyDescription")}
          />
        }
      />
    </div>
  );
}

function Warnings({ item }: { readonly item: ImportItem }) {
  const warnings = useQuery({
    queryKey: importRowsKey(item.id, { status: "WARNING", codes: [] }),
    queryFn: () =>
      fetchImportRowsPage(item.id, { status: "WARNING", codes: [] }, null, "row_number"),
    enabled: (item.counts.warnings ?? 0) > 0,
    retry: false,
  });
  const messages = (warnings.data?.items ?? []).flatMap((row) =>
    row.messages.filter((message) => message.severity === "WARNING"),
  );
  if (messages.length === 0) {
    return null;
  }
  return (
    <section className="flex flex-col gap-1.5">
      <h2 className="text-title-sm text-fg-1">{t("data.imports.review.warnings")}</h2>
      <ul className="flex flex-col gap-1 text-body-sm text-fg-1">
        {messages.map((message, index) => (
          <li key={`${message.rule_id}:${String(index)}`}>{messageText(message)}</li>
        ))}
      </ul>
    </section>
  );
}

function CancelImport({ item }: { readonly item: ImportItem }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const command = useCommand<ImportItem>({
    method: "POST",
    path: `${IMPORTS_PATH}/${item.id}/cancel`,
    invalidates: [EVERY_IMPORT],
  });
  const cancel = async () => {
    const outcome = await command.submit();
    if (outcome.kind === "succeeded") {
      setConfirming(false);
      toast.show({
        tone: "positive",
        message: t("data.imports.cancelledToast", { name: importName(item) }),
      });
      await queryClient.invalidateQueries({ queryKey: importKey(item.id) });
    } else if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: problemText(outcome.problem) });
    }
  };
  return (
    <>
      <div>
        <Button variant="secondary" onClick={() => setConfirming(true)}>
          {t("data.imports.cancel")}
        </Button>
      </div>
      <Modal
        open={confirming}
        variant="confirmation"
        title={t("data.imports.cancelConfirm.title")}
        primaryAction={{
          label: t("data.imports.cancel"),
          destructive: true,
          onAction: () => void cancel(),
        }}
        cancelLabel={t("data.imports.cancelConfirm.keep")}
        submitting={command.pending}
        onClose={() => setConfirming(false)}
      />
    </>
  );
}

function ReviewStep({
  me,
  item,
  job,
}: {
  readonly me: Me;
  readonly item: ImportItem;
  readonly job: JobProgressJob | null;
}) {
  const summary = diffSummaryOf(item);
  const ready = item.status === "DIFF_READY" || AFTER_SUBMIT.has(item.status);
  const access = useAccess();
  const uploader =
    me.user.id === item.created_by.id && access.holdsAnywhere(IMPORT_UPLOAD_PERMISSION);
  return (
    <>
      <h2 className="text-title-md text-fg-1">{t("data.imports.review.title")}</h2>
      {job === null ? null : (
        <section
          aria-label={t("data.imports.review.jobRegion")}
          className="rounded-lg border border-default bg-surface p-4"
        >
          <JobProgress
            label={t("data.imports.review.job")}
            job={job}
            unit={t("data.imports.review.jobUnit")}
          />
        </section>
      )}
      {item.status === "CANCELLED" ? (
        <Banner
          tone="info"
          announce="static"
          headingLevel={2}
          title={t("data.imports.cancelled")}
        />
      ) : null}
      {!ready || summary === null ? null : (
        <>
          <ImportFigures
            figures={[
              {
                id: "contracts-affected",
                label: t("data.imports.review.contractsAffected"),
                value: summary.contractsAffected,
              },
              {
                id: "contracts-created",
                label: t("data.imports.review.contractsCreated"),
                value: summary.contractsCreated,
              },
              {
                id: "allocation-changes",
                label: t("data.imports.review.allocationChanges"),
                value: summary.allocationChanges.length,
              },
              {
                id: "journal-lines",
                label: t("data.imports.review.journalLines"),
                value: summary.journalPreview.length,
              },
            ]}
          />
          {summary.allocationChanges.length === 0 ? null : (
            <StaticTable
              caption={t("data.imports.review.allocation.caption")}
              head={
                <>
                  <th scope="col" className={HEAD}>
                    {t("data.imports.review.allocation.contract")}
                  </th>
                  <th scope="col" className={HEAD_END}>
                    {t("data.imports.review.allocation.before")}
                  </th>
                  <th scope="col" className={HEAD_END}>
                    {t("data.imports.review.allocation.after")}
                  </th>
                </>
              }
            >
              {summary.allocationChanges.map((change, index) => (
                <tr
                  key={`${change.contract}:${String(index)}`}
                  className="border-b border-hairline"
                >
                  <th
                    scope="row"
                    className={`${CELL} text-start font-mono text-mono-sm font-normal text-fg-1`}
                  >
                    {change.contract}
                  </th>
                  <td className={CELL_END}>{amountText(change.before)}</td>
                  <td className={CELL_END}>{amountText(change.after)}</td>
                </tr>
              ))}
            </StaticTable>
          )}
          {summary.revenueByPeriod.length === 0 ? null : (
            <StaticTable
              caption={t("data.imports.review.revenue.caption")}
              testId="SF-10-grid-revenue-delta"
              head={
                <>
                  <th scope="col" className={HEAD}>
                    {t("data.imports.review.revenue.period")}
                  </th>
                  <th scope="col" className={HEAD_END}>
                    {t("data.imports.review.revenue.change")}
                  </th>
                </>
              }
            >
              {summary.revenueByPeriod.map((entry) => (
                <tr key={entry.periodKey} className="border-b border-hairline">
                  <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                    {formatPeriod(entry.periodKey)}
                  </th>
                  <td className={CELL_END}>{amountText(entry.amount, true)}</td>
                </tr>
              ))}
            </StaticTable>
          )}
          {summary.journalPreview.length === 0 ? null : (
            <StaticTable
              caption={t("data.imports.review.journal.caption")}
              head={
                <>
                  <th scope="col" className={HEAD}>
                    {t("data.imports.review.journal.role")}
                  </th>
                  <th scope="col" className={HEAD_END}>
                    {t("data.imports.review.journal.debit")}
                  </th>
                  <th scope="col" className={HEAD_END}>
                    {t("data.imports.review.journal.credit")}
                  </th>
                </>
              }
            >
              {summary.journalPreview.map((line, index) => (
                <tr
                  key={`${line.accountRole}:${String(index)}`}
                  className="border-b border-hairline"
                >
                  <th
                    scope="row"
                    className={`${CELL} text-start font-mono text-mono-sm font-normal text-fg-1`}
                  >
                    {line.accountRole}
                  </th>
                  <td className={CELL_END}>{amountText(line.debit)}</td>
                  <td className={CELL_END}>{amountText(line.credit)}</td>
                </tr>
              ))}
            </StaticTable>
          )}
          <Warnings item={item} />
          <AffectedRecords item={item} />
        </>
      )}
      {uploader && CANCELLABLE_STATUSES.has(item.status) ? <CancelImport item={item} /> : null}
    </>
  );
}

// --- Step 5 Approval --------------------------------------------------------------------------------

function SubmitForImportApproval({ item }: { readonly item: ImportItem }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [missing, setMissing] = useState(false);
  const command = useCommand<ImportItem>({
    method: "POST",
    path: `${IMPORTS_PATH}/${item.id}/submit`,
    invalidates: [EVERY_IMPORT],
  });
  const submit = async () => {
    if (comment.trim() === "") {
      setMissing(true);
      return;
    }
    setMissing(false);
    const outcome = await command.submit({ comment: comment.trim() });
    if (outcome.kind !== "succeeded") {
      return;
    }
    const requestId = outcome.data?.approval_request_id ?? null;
    let number = requestId ?? "";
    if (requestId !== null) {
      try {
        number = (await fetchApproval(requestId)).request_no;
      } catch {
        number = requestId.slice(0, 8);
      }
    }
    toast.show({
      tone: "positive",
      message: t("data.imports.approval.submitted", { request: number }),
    });
    await queryClient.invalidateQueries({ queryKey: importKey(item.id) });
  };
  const error = missing
    ? t("data.imports.approval.commentRequired")
    : (command.fieldErrors.comment ?? null);
  return (
    <form
      noValidate
      className="flex max-w-120 flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {command.problem !== null && command.fieldErrors.comment === undefined ? (
        <Banner
          tone="negative"
          announce="live"
          headingLevel={2}
          title={problemText(command.problem)}
        />
      ) : null}
      <Field
        name="import-submit-comment"
        label={t("data.imports.approval.comment")}
        required
        error={error}
        width="full"
      >
        {(control) => (
          <textarea
            {...control}
            rows={3}
            className={controlClass(error !== null, true)}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        )}
      </Field>
      <div>
        <Button variant="primary" type="submit" loading={command.pending}>
          {t("data.imports.approval.submit")}
        </Button>
      </div>
    </form>
  );
}

function ApprovalStatusChip({ status }: { readonly status: Approval["status"] }) {
  const chip = chipFor("E-05", status);
  return chip === null ? null : <StatusChip status={chip.status} />;
}

function stepStatusChip(status: Approval["steps"][number]["status"]): ReactNode {
  if (status === "APPROVED") {
    return <StatusChip status="Approved" />;
  }
  if (status === "REJECTED") {
    return <StatusChip status="Rejected" />;
  }
  if (status === "ACTIVE") {
    return <StatusChip status="Pending approval" />;
  }
  return (
    <span className="text-body-sm text-fg-3">
      {t(`data.imports.approval.stepStatus.${status}`)}
    </span>
  );
}

function RoutingPanel({
  item,
  requestId,
  built,
  uploader,
}: {
  readonly item: ImportItem;
  readonly requestId: string;
  readonly built: ReadonlySet<string>;
  readonly uploader: boolean;
}) {
  const navigate = useNavigate();
  const approval = useQuery({
    queryKey: approvalKey(requestId),
    queryFn: () => fetchApproval(requestId),
    retry: false,
  });
  if (approval.isError) {
    return (
      <Banner
        tone="negative"
        title={t("data.imports.approval.loadError")}
        actions={
          <Button variant="secondary" size="sm" onClick={() => void approval.refetch()}>
            {t("data.imports.retry")}
          </Button>
        }
      >
        {problemText(approval.error)}
      </Banner>
    );
  }
  if (approval.data === undefined) {
    return <Skeleton region={t("data.imports.approval.routing")} shape="text" count={3} />;
  }
  const request = approval.data;
  const decisions = request.steps.flatMap((step) => step.decisions);
  const automatic = decisions.find((decision) => decision.decision === "AUTO_APPROVE");
  const rejection = decisions.find((decision) => decision.decision === "REJECT");
  return (
    <section className="flex flex-col gap-3">
      {item.status === "REJECTED" && rejection !== undefined ? (
        <Banner
          tone="negative"
          announce="static"
          headingLevel={2}
          title={t("data.imports.approval.rejectedBy", {
            name: rejection.approver.display_name,
            comment: rejection.comment ?? NO_VALUE,
          })}
          actions={
            uploader ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  void navigate(correctedFileRoute(item), {
                    state: { parameters: item.parameters } satisfies CorrectedFileState,
                  })
                }
              >
                {t("data.imports.validate.uploadCorrected")}
              </Button>
            ) : undefined
          }
        />
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-title-md text-fg-1">
          {t("data.imports.approval.request", { request: request.request_no })}
        </h2>
        <ApprovalStatusChip status={request.status} />
        <span className="flex-1" />
        {built.has(APPROVAL_REQUEST_ROUTE) ? (
          <Link
            to={requestRoute(request.id)}
            className="text-body-sm text-accent-fg hover:underline"
          >
            {t("data.imports.approval.viewRequest")}
          </Link>
        ) : null}
      </div>
      {automatic === undefined ? null : (
        <p className="text-body-sm text-fg-1">
          {t("data.imports.approval.automatic", {
            rule: automatic.auto_rule_key ?? request.routing.rule_key ?? NO_VALUE,
          })}
        </p>
      )}
      <ol
        aria-label={t("data.imports.approval.routing")}
        className="flex flex-col gap-2 text-body-sm"
      >
        {request.steps.map((step) => (
          <li
            key={step.step_no}
            className="flex flex-col gap-1 rounded-md border border-hairline px-3 py-2"
          >
            <span className="flex flex-wrap items-center gap-3">
              <span className="font-medium text-fg-1">{step.name}</span>
              <span className="font-mono text-mono-sm text-fg-2">{step.required_permission}</span>
              {stepStatusChip(step.status)}
            </span>
            {step.decisions.map((decision) => (
              <span key={decision.id} className="flex flex-wrap gap-x-2 text-fg-2">
                <span className="text-fg-1">{decision.approver.display_name}</span>
                <span>{t(`data.imports.approval.decision.${decision.decision}`)}</span>
                <span>{formatTimestamp(decision.decided_at)}</span>
                {decision.comment === null ? null : <q>{decision.comment}</q>}
              </span>
            ))}
          </li>
        ))}
      </ol>
    </section>
  );
}

function ApprovalStep({
  me,
  item,
  built,
}: {
  readonly me: Me;
  readonly item: ImportItem;
  readonly built: ReadonlySet<string>;
}) {
  const access = useAccess();
  const uploader =
    me.user.id === item.created_by.id && access.holdsAnywhere(IMPORT_UPLOAD_PERMISSION);
  if (item.status === "DIFF_READY") {
    return uploader ? (
      <SubmitForImportApproval item={item} />
    ) : (
      <p className="text-body-sm text-fg-2">
        {t("data.imports.approval.notSubmitted", { name: item.created_by.display_name })}
      </p>
    );
  }
  if (item.approval_request_id === null) {
    return <p className="text-body-sm text-fg-2">{t("data.imports.approval.none")}</p>;
  }
  return (
    <RoutingPanel
      item={item}
      requestId={item.approval_request_id}
      built={built}
      uploader={uploader}
    />
  );
}

// --- Step 6 Committed -------------------------------------------------------------------------------

interface CreatedRecord {
  readonly key: string;
  readonly row: number;
  readonly targetType: string;
  readonly targetId: string;
}

function createdColumns(): readonly GridColumn<CreatedRecord>[] {
  return [
    {
      id: "row",
      header: t("data.imports.created.column.row"),
      kind: "number",
      numberKind: "count",
      value: (record) => String(record.row),
      width: 88,
    },
    {
      id: "target",
      header: t("data.imports.created.column.target"),
      kind: "text",
      value: (record) => targetLabel(record.targetType),
      width: 200,
    },
    {
      id: "record",
      header: t("data.imports.created.column.record"),
      kind: "text",
      value: (record) => record.targetId,
      render: (record) => {
        const route = targetRoute(record.targetType, record.targetId);
        const text = <span className="font-mono text-mono-sm">{record.targetId.slice(0, 8)}</span>;
        return route === null ? (
          text
        ) : (
          <Link to={route} className="text-accent-fg hover:underline">
            {text}
          </Link>
        );
      },
      width: 200,
    },
  ];
}

function CreatedRecords({ item }: { readonly item: ImportItem }) {
  const columns = useMemo(() => createdColumns(), []);
  const defaultColumns = useMemo(() => initialColumnState(columns), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const source: GridSource<CreatedRecord> = {
    queryKey: queryKey("imports", "tenant", { id: item.id, view: "created" }),
    fetchPage: async (cursor) => {
      const page = await fetchImportRowsPage(
        item.id,
        { status: null, codes: [] },
        cursor,
        "row_number",
      );
      return {
        items: page.items.flatMap((row) =>
          row.lineage.map((target) => ({
            key: `${row.id}:${target.target_type}:${target.target_id}`,
            row: row.row_number,
            targetType: target.target_type,
            targetId: target.target_id,
          })),
        ),
        nextCursor: page.nextCursor,
        total: null,
      };
    },
  };
  return (
    <div className="flex h-96 min-h-0 flex-col">
      <DataGrid<CreatedRecord>
        name="created"
        title={t("data.imports.created.title")}
        headingLevel={2}
        errorTitle={t("data.imports.created.loadError")}
        countLabel={(value, formatted) =>
          t("data.imports.created.count", { count: value, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(record) => record.key}
        testIdPrefix="SF-10"
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        emptyState={
          <EmptyState
            title={t("data.imports.created.empty")}
            description={t("data.imports.created.emptyDescription")}
          />
        }
      />
    </div>
  );
}

function ControlTotalsTable({ totals }: { readonly totals: ControlTotals }) {
  const source = totals.source;
  const loaded = totals.loaded;
  const names = [
    ...new Set([
      ...Object.keys(source?.amountSums ?? {}),
      ...Object.keys(loaded?.amountSums ?? {}),
    ]),
  ].sort();
  const lines = [
    {
      measure: t("data.imports.committed.totals.rows"),
      source: source === null ? null : String(source.rows),
      loaded: loaded === null ? null : String(loaded.rows),
      amount: false,
    },
    ...names.map((name) => ({
      measure: name,
      source: source?.amountSums[name] ?? null,
      loaded: loaded?.amountSums[name] ?? null,
      amount: true,
    })),
  ];
  return (
    <StaticTable
      caption={t("data.imports.committed.totals.caption")}
      testId="SF-10-grid-control-totals"
      head={
        <>
          <th scope="col" className={HEAD}>
            {t("data.imports.committed.totals.measure")}
          </th>
          <th scope="col" className={HEAD_END}>
            {t("data.imports.committed.totals.source")}
          </th>
          <th scope="col" className={HEAD_END}>
            {t("data.imports.committed.totals.loaded")}
          </th>
          <th scope="col" className={HEAD}>
            {t("data.imports.committed.totals.result")}
          </th>
        </>
      }
    >
      {lines.map((line) => (
        <tr key={line.measure} className="border-b border-hairline">
          <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
            {line.measure}
          </th>
          <td className={CELL_END}>
            {line.amount
              ? amountText(line.source)
              : countText(line.source === null ? null : Number(line.source))}
          </td>
          <td className={CELL_END}>
            {line.amount
              ? amountText(line.loaded)
              : countText(line.loaded === null ? null : Number(line.loaded))}
          </td>
          <td className={CELL}>
            <StatusChip status={line.source === line.loaded ? "Reconciled" : "Difference"} />
          </td>
        </tr>
      ))}
    </StaticTable>
  );
}

function FailedBanner({ item }: { readonly item: ImportItem }) {
  const findings = useQuery({
    queryKey: fileFindingsKey(item.id),
    queryFn: () => fetchFileFindings(item.id),
    retry: false,
  });
  const message = findings.data?.find(
    (finding) =>
      finding.ruleId === "CONTROL_TOTALS_MISMATCH" || finding.ruleId === "IMPORT_PROCESSING_FAILED",
  );
  return (
    <Banner
      tone="negative"
      announce="static"
      headingLevel={2}
      title={t("common.job.failed", {
        label: t("data.imports.committed.job", {
          rows: countText(item.counts.rows),
        }),
      })}
    >
      {message === undefined
        ? totalsMismatch(controlTotalsOf(item))
          ? t("data.imports.committed.mismatch")
          : null
        : messageText({ message: message.message, rule_id: message.ruleId })}
    </Banner>
  );
}

function CommittedStep({
  item,
  built,
  job,
}: {
  readonly item: ImportItem;
  readonly built: ReadonlySet<string>;
  readonly job: JobProgressJob | null;
}) {
  const totals = controlTotalsOf(item);
  return (
    <>
      {job === null ? null : (
        <section
          aria-label={t("data.imports.committed.jobRegion")}
          className="rounded-lg border border-default bg-surface p-4"
        >
          <JobProgress
            label={t("data.imports.committed.job", { rows: countText(item.counts.rows) })}
            job={job}
            unit={t("data.imports.validate.jobUnit")}
          />
        </section>
      )}
      {item.status === "FAILED" ? <FailedBanner item={item} /> : null}
      {item.status !== "COMMITTED" ? null : (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-body-sm">
            <dt className="text-fg-3">{t("data.imports.committed.at")}</dt>
            <dd className="text-fg-1">
              {item.committed_at === null ? NO_VALUE : formatTimestamp(item.committed_at)}
            </dd>
          </dl>
          {totals === null ? null : <ControlTotalsTable totals={totals} />}
          <CreatedRecords item={item} />
          {item.finding_counts.length > 0 && built.has(EXCEPTIONS_ROUTE) ? (
            <div>
              <Link
                to={`${EXCEPTIONS_ROUTE}?f.import=is:${item.id}`}
                className="text-body-sm text-accent-fg hover:underline"
              >
                {t("data.imports.validate.viewExceptions")}
              </Link>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}

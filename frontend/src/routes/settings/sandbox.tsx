// SF-15:sandbox Sandbox copies (SCREENS_B §9.7; SCREENS §0.4 RT-84, §0.5 SCR-LTH-10 to SCR-LTH-12,
// §0.7 SCR-ST-03, SCR-ST-11, SCR-ST-12, SCR-PERM-05; SCREENS_B §0.3 SB-R-05, SB-R-06; DESIGN_SYSTEM
// DS-CMP-10 static table, DS-CMP-11, DS-CMP-24, DS-CMP-29, DS-FMT-17; 04 API-R-04 `GET, POST
// /tenant/snapshots`, `POST /tenant/sandboxes`, `POST /tenant/reset`, API-R-03 `GET /me`, API-R-01
// `POST /session/tenant`; 05 SBX-02 to SBX-07; 03 REQ-PLT-022 to REQ-PLT-025; PRD J-25, ACT-50, ACT-51;
// BUILD_SPEC SNP-5). In a production workspace: "Create sandbox copy", the table "Sandboxes" — the
// user's workspaces copied from this one (`GET /me`), each opened with `POST /session/tenant` — and the
// table "Stored snapshots" with "Restore into a new sandbox". A copy or a restore answers 202 with a
// job, whose progress shows above the tables until the toast "Sandbox <name> is ready." In a sandbox
// the page says what the workspace was copied from and offers "Reset sandbox" (`sandbox.reset`), a
// confirmation with a reason; production renders no reset control at all. A reset moves the session
// to the successor sandbox, so its progress watches the session as well as the job.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { fetchSession } from "../../app/auth/RequireSession";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { SESSION_TENANT_PATH } from "../../app/shell/TenantSwitcher";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { accessOf } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, type Job, JOB_POLL_INTERVAL_MS, useJob } from "../../lib/api/jobs";
import { fetchListPage } from "../../lib/api/lists";
import { STEP_UP_REQUIRED_SLUG } from "../../lib/api/queries/api-clients";
import { type Me, type MeMembership, useMe } from "../../lib/api/queries/me";
import { queryKey, type QueryKey, queryKeys } from "../../lib/api/query-keys";
import { placeProblem } from "../../lib/api/refusals";
import type { components } from "../../lib/api/schema";
import { formatTimestamp, instantOf, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { RadioGroup, TextField } from "../contracts/drawers/common";
import { parseCutoff } from "../journals/journal-runs";
import { testIdKey } from "../onboarding/select-workspace";
import { SettingsPageHeader } from "./index";
import { StepUpModal } from "./profile";

export type Snapshot = components["schemas"]["TenantSnapshotOut"];
type SessionLoginOut = components["schemas"]["SessionLoginOut"];

/** SCREENS RT-84. */
export const SANDBOX_PATH = "/settings/sandbox";
export const SNAPSHOTS_PATH = "/api/v1/tenant/snapshots";
export const SANDBOXES_PATH = "/api/v1/tenant/sandboxes";
export const RESET_PATH = "/api/v1/tenant/reset";
/** SCREENS RT-84: read and create copies (PRD ACT-50). */
export const SNAPSHOT_PERMISSION = "tenant.snapshot";
/** PRD ACT-51: reset, in a sandbox only. */
export const RESET_PERMISSION = "sandbox.reset";
/** The header of a 202 that pre-allocates a sandbox tenant (04 API-R-04). */
export const SANDBOX_ID_HEADER = "X-Erev-Sandbox-Tenant-Id";
/** 04 T-PLT-34 `name`: the sandbox's display name. */
export const NAME_LENGTH = 400;

export function snapshotsKey(): QueryKey {
  return queryKey("tenant-snapshots", "tenant");
}

/** The stored snapshots of the workspace, newest first. */
export async function fetchSnapshots(): Promise<readonly Snapshot[]> {
  const page = await fetchListPage<Snapshot>(SNAPSHOTS_PATH, { sort: "-created_at" }, null, {
    count: false,
  });
  return page.items;
}

/**
 * The user's workspaces copied from `tenantId` that are workspaces: a sandbox still loading
 * (`SUSPENDED`, 05 SBX-04) is shown by its copy's progress, not as a row.
 */
export function sandboxesOf(
  memberships: readonly MeMembership[],
  tenantId: string,
): readonly MeMembership[] {
  return memberships.filter(
    (membership) =>
      membership.tenant.kind === "sandbox" &&
      membership.tenant.source_tenant_id === tenantId &&
      membership.tenant.status !== "SUSPENDED",
  );
}

/** `5b1e…09ac`: the first and the last four characters of an id. */
export function idPrefix(id: string): string {
  return `${id.slice(0, 4)}…${id.slice(-4)}`;
}

/** `a0c4e9d1…7e22`: the first eight and the last four characters of a digest. */
export function digestPrefix(digest: string | null): string {
  return digest === null ? NO_VALUE : `${digest.slice(0, 8)}…${digest.slice(-4)}`;
}

/**
 * "A specific time": an instant that has passed, typed as the cut-off of a journal run is typed
 * (`YYYY-MM-DD HH:mm`, UTC unless an offset is named); an empty field is an error here.
 */
export function specificTime(text: string, nowMs: number): ReturnType<typeof parseCutoff> {
  const parsed = parseCutoff(text, nowMs);
  return parsed.value === null && parsed.error === null
    ? { value: null, error: t("journals.runForm.cutoffFormat") }
    : parsed;
}

interface Started {
  readonly jobId: string;
  /** The name the new sandbox was given. */
  readonly name: string;
}

interface ResetStarted {
  readonly jobId: string;
  /** The pre-allocated successor the session moves to. */
  readonly successorId: string;
}

export function SandboxCopies() {
  const me = useMe();
  const session = useShellSession();
  const title = t("settings.sandbox.title");
  const active = session?.authenticated === true ? session.active_tenant : null;

  let body: ReactNode;
  let header: ReactNode = <SettingsPageHeader title={title} group="sandbox" />;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined || active === null) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (active.kind === "sandbox") {
    header = null;
    body = <SandboxView me={me.data} tenantId={active.id} tenantName={active.display_name} />;
  } else if (!accessOf(me.data).holdsForAll(SNAPSHOT_PERMISSION)) {
    // A copy is a copy of the whole workspace: its snapshots are read and made by a holder for all
    // entities alone.
    body = (
      <AccessLimited
        area={title}
        permissions={[SNAPSHOT_PERMISSION]}
        allEntities={
          accessOf(me.data).holdsAnywhere(SNAPSHOT_PERMISSION)
            ? { message: "settings.sandbox.access.allEntities", permission: SNAPSHOT_PERMISSION }
            : undefined
        }
      />
    );
  } else {
    header = null;
    body = <ProductionView me={me.data} tenantId={active.id} tenantName={active.display_name} />;
  }

  return (
    <div data-testid="SF-15-page" className="flex w-full flex-col gap-6 px-[var(--gutter)] py-6">
      {header}
      {body}
    </div>
  );
}

interface ViewProps {
  readonly me: Me;
  readonly tenantId: string;
  readonly tenantName: string;
}

// ---------------------------------------------------------------------------------------------------
// Production: copies, stored snapshots
// ---------------------------------------------------------------------------------------------------

function ProductionView({ me, tenantId, tenantName }: ViewProps) {
  const title = t("settings.sandbox.title");
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState<Snapshot | null>(null);
  const [copies, setCopies] = useState<readonly Started[]>([]);
  // The copies of this visit that ended without a sandbox: each keeps its banner, and none of them
  // is "copying" any more, so the empty state returns under the banner.
  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set());
  const snapshots = useQuery({ queryKey: snapshotsKey(), queryFn: fetchSnapshots });
  const sandboxes = sandboxesOf(me.memberships, tenantId);
  const open = useOpenWorkspace();
  const create = {
    label: t("settings.sandbox.create.action"),
    onAction: () => {
      setCreating(true);
    },
  };
  const started = (copy: Started) => {
    setCopies((current) => [...current, copy]);
  };
  const fail = (jobId: string) => {
    setFailed((current) => new Set(current).add(jobId));
  };

  return (
    <>
      <SettingsPageHeader
        title={title}
        group="sandbox"
        actions={
          <Button variant="primary" onClick={create.onAction}>
            {create.label}
          </Button>
        }
      >
        <p className="text-body-sm text-fg-2">{t("settings.sandbox.description")}</p>
      </SettingsPageHeader>
      {copies.map((copy) => (
        <CopyProgress
          key={copy.jobId}
          copy={copy}
          tenantName={tenantName}
          onOpen={open.open}
          onFailed={fail}
        />
      ))}
      {open.problem === null ? null : <Banner tone="negative" title={open.problem} />}
      <SandboxesTable
        sandboxes={sandboxes}
        snapshots={snapshots.data ?? []}
        copying={copies.some((copy) => !failed.has(copy.jobId))}
        create={create}
        opening={open.pending}
        onOpen={open.open}
      />
      <SnapshotsTable
        snapshots={snapshots.data}
        error={snapshots.isError ? snapshots.error.message : null}
        onRetry={() => void snapshots.refetch()}
        memberships={me.memberships}
        onRestore={setRestoring}
      />
      {creating ? (
        <CreateCopyDialog
          onClose={() => {
            setCreating(false);
          }}
          onStarted={started}
        />
      ) : null}
      {restoring === null ? null : (
        <RestoreDialog
          snapshot={restoring}
          onClose={() => {
            setRestoring(null);
          }}
          onStarted={started}
        />
      )}
    </>
  );
}

/** `POST /session/tenant`, then the landing route of the opened workspace (the switcher's steps). */
function useOpenWorkspace() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { submit, pending, problem } = useCommand<SessionLoginOut>({
    method: "POST",
    path: SESSION_TENANT_PATH,
  });
  const open = async (tenantId: string, tenantName: string) => {
    if (pending) {
      return;
    }
    const outcome = await submit({ tenant_id: tenantId });
    if (outcome.kind !== "succeeded") {
      return;
    }
    // Every cached read belongs to the workspace that was left (DG-FE-04 scopes).
    queryClient.clear();
    if (outcome.data !== null) {
      queryClient.setQueryData(queryKeys.session(), outcome.data);
    }
    void navigate("/");
    announce(t("shell.tenantSwitcher.switched", { tenant: tenantName }), "polite");
  };
  return {
    open: (tenantId: string, tenantName: string) => void open(tenantId, tenantName),
    pending,
    problem: problem === null ? null : (problem.detail ?? problem.title),
  };
}

interface CopyProgressProps {
  readonly copy: Started;
  readonly tenantName: string;
  readonly onOpen: (tenantId: string, tenantName: string) => void;
  /** The job ended without a sandbox (`FAILED` or `CANCELLED`). */
  readonly onFailed: (jobId: string) => void;
}

/** DS-CMP-24 progress of one copy or restore (SB-R-06), then its toast, warning or failure. */
function CopyProgress({ copy, tenantName, onOpen, onFailed }: CopyProgressProps) {
  const job = useJob(copy.jobId);
  const toast = useToast();
  const queryClient = useQueryClient();
  const announced = useRef(false);
  const data = job.data;
  const label = t("settings.sandbox.job.copying", { tenant: tenantName });
  const succeeded = data?.state === "SUCCEEDED" || data?.state === "SUCCEEDED_WITH_EXCEPTIONS";
  useEffect(() => {
    if (data === undefined || !isTerminal(data) || announced.current) {
      return;
    }
    announced.current = true;
    void queryClient.invalidateQueries({ queryKey: snapshotsKey() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.me() });
    if (!succeeded) {
      onFailed(copy.jobId);
      return;
    }
    const sandboxId = data.result?.sandbox_tenant_id;
    toast.show({
      tone: "positive",
      message: t("settings.sandbox.ready", { name: copy.name }),
      action:
        typeof sandboxId === "string"
          ? {
              label: t("settings.sandbox.openSandbox"),
              onAction: () => {
                onOpen(sandboxId, copy.name);
              },
            }
          : undefined,
    });
  });
  if (data === undefined) {
    return null;
  }
  const mismatches = Number(data.result?.counts?.derived_mismatches ?? 0);
  if (succeeded) {
    return mismatches > 0 ? (
      <div data-testid="SF-15-banner-determinism">
        <Banner tone="warning" title={t("settings.sandbox.mismatch", { count: mismatches })} />
      </div>
    ) : null;
  }
  return <JobProgress label={label} job={explained(data)} unit={t("settings.sandbox.job.unit")} />;
}

/**
 * A failed copy, restore or reset as its SCR-ST-12 banner tells it. A load refusal rides a general
 * problem type (04 API-R-04; PRD ERR-77 on `precondition-failed`), whose title — "Record changed" —
 * says nothing of it: the banner carries the refusal's own sentence, its detail or its first finding.
 */
export function explained(job: Job): Job {
  const problem = job.state === "FAILED" ? job.problem : null;
  const reason = problem?.detail ?? problem?.errors?.[0]?.message;
  if (problem === null || reason === null || reason === undefined) {
    return job;
  }
  return { ...job, problem: { ...problem, title: reason } };
}

interface SandboxesTableProps {
  readonly sandboxes: readonly MeMembership[];
  readonly snapshots: readonly Snapshot[];
  /** A copy of this session is running: the empty state gives way to its progress. */
  readonly copying: boolean;
  readonly create: { readonly label: string; readonly onAction: () => void };
  readonly opening: boolean;
  readonly onOpen: (tenantId: string, tenantName: string) => void;
}

const HEADER = "px-3 py-2 text-start font-medium text-fg-2";
const CELL = "px-3 py-3 align-top";
/** SCREENS_B §9.7: at 1280 px the tables hide "Created by" and "Manifest SHA-256". */
const WIDE_ONLY = "hidden xl:table-cell";

/** SCREENS_B §9.7 "Sandboxes": the user's workspaces copied from this one. */
function SandboxesTable({
  sandboxes,
  snapshots,
  copying,
  create,
  opening,
  onOpen,
}: SandboxesTableProps) {
  const headingId = useId();
  const name = t("settings.sandbox.sandboxes.title");
  if (sandboxes.length === 0) {
    return copying ? null : (
      <div data-testid="SF-15-empty-sandboxes">
        <EmptyState
          title={t("settings.sandbox.empty.title")}
          description={t("settings.sandbox.empty.description")}
          action={create}
        />
      </div>
    );
  }
  // The copy a sandbox was loaded from names who asked for it.
  const creator = new Map(
    snapshots
      .filter((snapshot) => snapshot.target_tenant_id !== null)
      .map((snapshot) => [snapshot.target_tenant_id, snapshot.created_by.display_name]),
  );
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("settings.sandbox.sandboxes.heading", { count: sandboxes.length })}
      </h2>
      <table
        aria-label={name}
        data-testid="SF-15-grid-sandboxes"
        className="w-full border-collapse text-body-sm"
      >
        <thead>
          <tr className="border-b border-default bg-subtle">
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.sandboxes.column.name")}
            </th>
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.column.knownAt")}
            </th>
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.column.status")}
            </th>
            <th scope="col" className={`${HEADER} ${WIDE_ONLY}`}>
              {t("settings.sandbox.column.createdBy")}
            </th>
            <th scope="col" className={HEADER}>
              <span className="sr-only">{t("settings.sandbox.column.actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sandboxes.map(({ tenant }) => {
            // SCREENS_B §0.4 E-101 gives `ARCHIVED` its chip; every other row here is "Active".
            const archived = tenant.status === "ARCHIVED" ? chipFor("E-101", "ARCHIVED") : null;
            return (
              <tr
                key={tenant.id}
                data-testid={`SF-15-row-${testIdKey(tenant.code)}`}
                className="border-b border-hairline"
              >
                <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                  {tenant.display_name}
                </th>
                <td className={`${CELL} num`}>{formatTimestamp(tenant.source_known_at)}</td>
                <td className={CELL}>
                  <StatusChip status={archived?.status ?? "Active"} />
                </td>
                <td className={`${CELL} ${WIDE_ONLY}`}>{creator.get(tenant.id) ?? NO_VALUE}</td>
                <td className={`${CELL} text-end`}>
                  {tenant.status === "ACTIVE" ? (
                    <Button
                      variant="link"
                      size="sm"
                      loading={opening}
                      aria-label={t("settings.sandbox.sandboxes.openNamed", {
                        name: tenant.display_name,
                      })}
                      onClick={() => {
                        onOpen(tenant.id, tenant.display_name);
                      }}
                    >
                      {t("settings.sandbox.sandboxes.open")}
                    </Button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

interface SnapshotsTableProps {
  readonly snapshots: readonly Snapshot[] | undefined;
  readonly error: string | null;
  readonly onRetry: () => void;
  readonly memberships: readonly MeMembership[];
  readonly onRestore: (snapshot: Snapshot) => void;
}

/** A snapshot that can be restored: `SUCCEEDED` with its manifest (04 `SNAPSHOT_NOT_LOADABLE`). */
export function restorable(snapshot: Snapshot): boolean {
  return snapshot.status === "SUCCEEDED" && snapshot.manifest_sha256 !== null;
}

/** SCREENS_B §9.7 "Stored snapshots". */
function SnapshotsTable({
  snapshots,
  error,
  onRetry,
  memberships,
  onRestore,
}: SnapshotsTableProps) {
  const headingId = useId();
  const name = t("settings.sandbox.snapshots.title");
  if (error !== null) {
    return (
      <Banner
        tone="negative"
        title={t("settings.sandbox.snapshots.loadError")}
        actions={
          <Button variant="link" onClick={onRetry}>
            {t("settings.sandbox.retry")}
          </Button>
        }
      >
        {error}
      </Banner>
    );
  }
  if (snapshots === undefined) {
    return <Skeleton region={name} shape="rows" count={3} />;
  }
  if (snapshots.length === 0) {
    return null;
  }
  const names = new Map(memberships.map(({ tenant }) => [tenant.id, tenant.display_name]));
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("settings.sandbox.snapshots.heading", { count: snapshots.length })}
      </h2>
      <table
        aria-label={name}
        data-testid="SF-15-grid-snapshots"
        className="w-full border-collapse text-body-sm"
      >
        <thead>
          <tr className="border-b border-default bg-subtle">
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.snapshots.column.snapshot")}
            </th>
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.snapshots.column.purpose")}
            </th>
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.column.knownAt")}
            </th>
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.column.status")}
            </th>
            <th scope="col" className={HEADER}>
              {t("settings.sandbox.snapshots.column.target")}
            </th>
            <th scope="col" className={`${HEADER} ${WIDE_ONLY}`}>
              {t("settings.sandbox.snapshots.column.manifest")}
            </th>
            <th scope="col" className={`${HEADER} ${WIDE_ONLY}`}>
              {t("settings.sandbox.column.createdBy")}
            </th>
            <th scope="col" className={HEADER}>
              <span className="sr-only">{t("settings.sandbox.column.actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((snapshot) => {
            const chip = chipFor("E-67", snapshot.status);
            const prefix = idPrefix(snapshot.id);
            return (
              <tr
                key={snapshot.id}
                data-testid={`SF-15-row-snapshot-${snapshot.id}`}
                className="border-b border-hairline"
              >
                <th scope="row" className={`${CELL} text-start font-mono font-normal text-fg-1`}>
                  {prefix}
                </th>
                <td className={CELL}>{t(`settings.sandbox.purpose.${snapshot.purpose}`)}</td>
                <td className={`${CELL} num`}>{formatTimestamp(snapshot.known_at)}</td>
                <td className={CELL}>
                  {chip === null ? null : <StatusChip status={chip.status} />}
                </td>
                <td className={CELL}>
                  {snapshot.target_tenant_id === null
                    ? NO_VALUE
                    : (names.get(snapshot.target_tenant_id) ?? NO_VALUE)}
                </td>
                <td
                  className={`${CELL} ${WIDE_ONLY}${snapshot.manifest_sha256 === null ? "" : " font-mono"}`}
                >
                  {digestPrefix(snapshot.manifest_sha256)}
                </td>
                <td className={`${CELL} ${WIDE_ONLY}`}>{snapshot.created_by.display_name}</td>
                <td className={`${CELL} text-end`}>
                  {restorable(snapshot) ? (
                    <Button
                      variant="link"
                      size="sm"
                      aria-label={t("settings.sandbox.restore.actionNamed", { snapshot: prefix })}
                      onClick={() => {
                        onRestore(snapshot);
                      }}
                    >
                      {t("settings.sandbox.restore.action")}
                    </Button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

type KnownAt = "now" | "specific";

interface StartDialogProps {
  readonly onClose: () => void;
  readonly onStarted: (copy: Started) => void;
}

/** A name of 1 to 400 characters after trimming, or its field error. */
function nameError(name: string): string | null {
  const text = name.trim();
  if (text === "") {
    return t("settings.sandbox.name.required");
  }
  return text.length > NAME_LENGTH ? t("settings.sandbox.name.tooLong") : null;
}

/** §9.7 "Create sandbox copy" (SCR-LTH-10; DS-CMP-11 form; ACT-50 step-up). */
// docs/dev-guide.md DG-FE-06: the fields of the three dialogs and the members each sends. The time of
// a copy is on screen only for "a specific time"; the snapshot of a restore and the mode of a reset
// show no message. An error on a member without a field on screen is the banner's.
const COPY_MEMBERS = { name: ["name"], knownAt: ["known_at"] } as const;
const COPY_MEMBERS_OF_NOW = { ...COPY_MEMBERS, knownAt: [] } as const;
const RESTORE_MEMBERS = { name: ["name"] } as const;
const RESET_MEMBERS = { reason: ["reason"] } as const;

function CreateCopyDialog({ onClose, onStarted }: StartDialogProps) {
  const formId = useId();
  const [name, setName] = useState("");
  const [knownAt, setKnownAt] = useState<KnownAt>("now");
  const [timeText, setTimeText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const create = useCommand({ method: "POST", path: SNAPSHOTS_PATH });
  const time = specificTime(timeText, Date.now());
  const stepUpAsked = create.problem?.slug === STEP_UP_REQUIRED_SLUG;
  const placed = useMemo(
    () =>
      placeProblem<keyof typeof COPY_MEMBERS>(
        create.problem,
        knownAt === "specific" ? COPY_MEMBERS : COPY_MEMBERS_OF_NOW,
      ),
    [create.problem, knownAt],
  );
  // "Now" is the instant of the first request of this intent: the request after a step-up, and a
  // retry after a lost answer, send the same body, so they carry the same Idempotency-Key and
  // can never ask for a second copy (DG-FE-05).
  const askedAt = useRef<string | null>(null);

  const send = async () => {
    const copyName = name.trim();
    askedAt.current ??= instantOf(Date.now());
    const outcome = await create.submit({
      known_at: knownAt === "now" ? askedAt.current : time.value,
      purpose: "SANDBOX_COPY",
      name: copyName,
    });
    if (outcome.kind === "accepted") {
      onStarted({ jobId: outcome.jobId, name: copyName });
      onClose();
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (create.pending || nameError(name) !== null) {
      return;
    }
    if (knownAt === "specific" && time.value === null) {
      return;
    }
    void send();
  };

  return (
    <>
      <Modal
        open={!stepUp}
        variant="form"
        title={t("settings.sandbox.create.title")}
        description={t("settings.sandbox.create.consequence")}
        primaryAction={{ label: t("settings.sandbox.create.action"), form: formId }}
        submitting={create.pending}
        onClose={onClose}
        testId="SF-15-dialog-create-sandbox-copy"
      >
        <form id={formId} noValidate className="flex flex-col gap-4" onSubmit={submit}>
          {stepUpAsked ? null : <RefusalBanner problem={create.problem} placed={placed} />}
          <TextField
            name="sandbox-name"
            label={t("settings.sandbox.name.label")}
            required
            value={name}
            onChange={(value) => {
              askedAt.current = null;
              setName(value);
            }}
            error={(attempted ? nameError(name) : null) ?? placed.fields.name}
          />
          <div className="flex flex-col gap-1">
            <span className="text-body-sm font-medium text-fg-1">
              {t("settings.sandbox.create.knownAt.label")}
            </span>
            <div>
              <SegmentedControl<KnownAt>
                label={t("settings.sandbox.create.knownAt.label")}
                options={[
                  { value: "now", label: t("settings.sandbox.create.knownAt.now") },
                  { value: "specific", label: t("settings.sandbox.create.knownAt.specific") },
                ]}
                value={knownAt}
                onChange={(value) => {
                  askedAt.current = null;
                  setKnownAt(value);
                }}
              />
            </div>
          </div>
          {knownAt === "now" ? null : (
            <TextField
              name="sandbox-known-at"
              label={t("settings.sandbox.create.knownAt.time")}
              required
              help={t("settings.sandbox.create.knownAt.timeHelp")}
              value={timeText}
              onChange={setTimeText}
              error={(attempted ? time.error : null) ?? placed.fields.knownAt}
            />
          )}
        </form>
      </Modal>
      {stepUp ? (
        <StepUpModal
          onCancel={onClose}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

interface RestoreDialogProps extends StartDialogProps {
  readonly snapshot: Snapshot;
}

/** §9.7 "Restore into a new sandbox" (SCR-LTH-11; DS-CMP-11 form). */
function RestoreDialog({ snapshot, onClose, onStarted }: RestoreDialogProps) {
  const formId = useId();
  const [name, setName] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const restore = useCommand({ method: "POST", path: SANDBOXES_PATH });
  const placed = useMemo(() => placeProblem(restore.problem, RESTORE_MEMBERS), [restore.problem]);
  const error = (attempted ? nameError(name) : null) ?? placed.fields.name;

  const send = async () => {
    const copyName = name.trim();
    const outcome = await restore.submit({ tenant_snapshot_id: snapshot.id, name: copyName });
    if (outcome.kind === "accepted") {
      onStarted({ jobId: outcome.jobId, name: copyName });
      onClose();
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (restore.pending || nameError(name) !== null) {
      return;
    }
    void send();
  };
  const stepUpAsked = restore.problem?.slug === STEP_UP_REQUIRED_SLUG;

  return (
    <>
      <Modal
        open={!stepUp}
        variant="form"
        title={t("settings.sandbox.restore.action")}
        description={t("settings.sandbox.restore.consequence")}
        primaryAction={{ label: t("settings.sandbox.restore.action"), form: formId }}
        submitting={restore.pending}
        onClose={onClose}
        testId="SF-15-dialog-restore-sandbox"
      >
        <form id={formId} noValidate className="flex flex-col gap-4" onSubmit={submit}>
          {stepUpAsked ? null : <RefusalBanner problem={restore.problem} placed={placed} />}
          <TextField
            name="sandbox-name"
            label={t("settings.sandbox.name.label")}
            required
            value={name}
            onChange={setName}
            error={error}
          />
        </form>
      </Modal>
      {stepUp ? (
        <StepUpModal
          onCancel={onClose}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------------------------------------------
// Sandbox: what it was copied from, and its reset
// ---------------------------------------------------------------------------------------------------

function SandboxView({ me, tenantId, tenantName }: ViewProps) {
  const title = t("settings.sandbox.title");
  const [confirming, setConfirming] = useState(false);
  const [reset, setReset] = useState<ResetStarted | null>(null);
  const [resetFailed, setResetFailed] = useState(false);
  const own = me.memberships.find((membership) => membership.tenant.id === tenantId)?.tenant;
  const source = me.memberships.find(
    (membership) => membership.tenant.id === own?.source_tenant_id,
  )?.tenant;
  const knownAt = own?.source_known_at ?? null;
  const canReset = accessOf(me).holdsForAll(RESET_PERMISSION);

  let origin: string;
  if (knownAt === null) {
    origin =
      source === undefined
        ? t("settings.sandbox.origin.empty")
        : t("settings.sandbox.origin.emptyOf", { source: source.display_name });
  } else {
    origin =
      source === undefined
        ? t("settings.sandbox.origin.copied", { knownAt: formatTimestamp(knownAt) })
        : t("settings.sandbox.origin.copiedFrom", {
            source: source.display_name,
            knownAt: formatTimestamp(knownAt),
          });
  }

  return (
    <>
      <SettingsPageHeader
        title={title}
        group="sandbox"
        actions={
          canReset && (reset === null || resetFailed) ? (
            <Button
              onClick={() => {
                setConfirming(true);
              }}
            >
              {t("settings.sandbox.reset.action")}
            </Button>
          ) : undefined
        }
      >
        <p data-testid="SF-15-sandbox-origin" className="text-body-sm text-fg-2">
          {origin}
        </p>
      </SettingsPageHeader>
      {reset === null ? null : (
        <ResetProgress
          key={reset.jobId}
          reset={reset}
          tenantName={tenantName}
          onMoved={() => {
            setReset(null);
          }}
          onFailed={() => {
            setResetFailed(true);
          }}
        />
      )}
      {confirming ? (
        <ResetDialog
          knownAt={knownAt}
          onClose={() => {
            setConfirming(false);
          }}
          onStarted={(started) => {
            setResetFailed(false);
            setReset(started);
          }}
        />
      ) : null}
    </>
  );
}

type ResetMode = "SNAPSHOT" | "EMPTY";

interface ResetDialogProps {
  /** `source_known_at` of the sandbox: the copy a reset can go back to, null in an empty sandbox. */
  readonly knownAt: string | null;
  readonly onClose: () => void;
  readonly onStarted: (reset: ResetStarted) => void;
}

/** §9.7 "Reset sandbox" (SCR-LTH-12; SB-R-05): a confirmation with a reason; ACT-51 step-up. */
function ResetDialog({ knownAt, onClose, onStarted }: ResetDialogProps) {
  const formId = useId();
  const [mode, setMode] = useState<ResetMode>(knownAt === null ? "EMPTY" : "SNAPSHOT");
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const reset = useCommand({ method: "POST", path: RESET_PATH });
  const placed = useMemo(() => placeProblem(reset.problem, RESET_MEMBERS), [reset.problem]);

  const send = async () => {
    const outcome = await reset.submit({ mode, reason: reason.trim() });
    if (outcome.kind === "accepted") {
      const successorId = outcome.response.headers.get(SANDBOX_ID_HEADER);
      if (successorId !== null) {
        onStarted({ jobId: outcome.jobId, successorId });
      }
      onClose();
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (reset.pending || reasonError(reason) !== null) {
      return;
    }
    void send();
  };
  const stepUpAsked = reset.problem?.slug === STEP_UP_REQUIRED_SLUG;

  return (
    <>
      <Modal
        open={!stepUp}
        variant="confirmation"
        title={t("settings.sandbox.reset.action")}
        description={t("settings.sandbox.reset.consequence")}
        primaryAction={{
          label: t("settings.sandbox.reset.action"),
          destructive: true,
          form: formId,
        }}
        submitting={reset.pending}
        onClose={onClose}
        testId="SF-15-dialog-reset-sandbox"
      >
        <form id={formId} noValidate className="flex flex-col gap-4" onSubmit={submit}>
          {stepUpAsked ? null : <RefusalBanner problem={reset.problem} placed={placed} />}
          <RadioGroup<ResetMode>
            legend={t("settings.sandbox.reset.mode.label")}
            options={[
              ...(knownAt === null
                ? []
                : [
                    {
                      value: "SNAPSHOT" as const,
                      label: t("settings.sandbox.reset.mode.snapshot", {
                        knownAt: formatTimestamp(knownAt),
                      }),
                    },
                  ]),
              { value: "EMPTY" as const, label: t("settings.sandbox.reset.mode.empty") },
            ]}
            value={mode}
            onChange={setMode}
          />
          <ReasonField
            label={t("settings.sandbox.reset.reason")}
            value={reason}
            onChange={setReason}
            showError={attempted}
            error={placed.fields.reason}
          />
        </form>
      </Modal>
      {stepUp ? (
        <StepUpModal
          onCancel={onClose}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

/**
 * DS-CMP-24 progress of a reset (SB-R-06). The job lives in the sandbox it supersedes and the
 * session is moved to the successor before the job ends (05 SBX-07), so this session stops seeing
 * the job: the reset is complete when the session's workspace is the successor. Every cached read
 * belongs to the archived sandbox then. The route stays, so nothing remounts: the session is set
 * and every other read is reset, which its mounted readers answer by reading the successor — a
 * removed query would leave them showing the archived sandbox (an empty successor as a copy).
 */
function ResetProgress({
  reset,
  tenantName,
  onMoved,
  onFailed,
}: {
  readonly reset: ResetStarted;
  readonly tenantName: string;
  readonly onMoved: () => void;
  readonly onFailed: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const job = useJob(reset.jobId);
  const failed = job.data?.state === "FAILED" || job.data?.state === "CANCELLED";
  const moved = useQuery({
    queryKey: queryKey("sandbox-reset-session", "public", { id: reset.successorId }),
    queryFn: fetchSession,
    enabled: !failed,
    refetchInterval: JOB_POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
  }).data;
  const label = t("settings.sandbox.job.resetting", { tenant: tenantName });
  const done =
    moved?.authenticated === true && moved.active_tenant?.id === reset.successorId ? moved : null;
  const settled = useRef(false);
  useEffect(() => {
    if (settled.current) {
      return;
    }
    if (failed) {
      settled.current = true;
      onFailed();
      return;
    }
    if (done === null) {
      return;
    }
    settled.current = true;
    queryClient.setQueryData(queryKeys.session(), done);
    void queryClient.resetQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    toast.show({ tone: "positive", message: t("common.job.succeeded", { label }) });
    onMoved();
  });
  if (job.data === undefined || done !== null) {
    return null;
  }
  return (
    <JobProgress label={label} job={explained(job.data)} unit={t("settings.sandbox.job.unit")} />
  );
}

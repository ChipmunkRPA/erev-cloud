// SF-15:workspace Workspace settings (SCREENS_B §9.6; SCREENS §0.4 RT-110, SCR-PERM-01, SCR-PERM-02;
// DESIGN_SYSTEM DS-CMP-06, DS-CMP-21, DS-CMP-29, DS-FMT-06; 04 API-R-17 `GET, PATCH /tenant`, API-R-13
// `GET /policies/resolve`, `POST /policies`, `/test`, `/submit`; T-PLT-31; D-75; BUILD_SPEC RFD-19).
// The workspace identity, and the platform, close and integration registry values that are not
// accounting policies. "Save name" applies at once (`PATCH /tenant`, `settings.manage`). "Submit for
// approval" creates one TENANT registry version per changed category with the changed values only, runs
// its test job and submits it with the comment; the versions are approved in SF-12. The form is
// editable for a holder of `config.author` for ALL entities: it states TENANT versions, and the API
// lets a member author one only with the permission for all entities (04 §16.5 rev 1.309; SCREENS_B
// §9.6 rev 1.102). Other readers — a holder for named entities among them — see the values
// read-only without a submit control (L4-5-Q-18). One version of a category is open at a time (PRD
// SM-04) and the form creates a new one: where a DRAFT or TESTED version is open — a withdrawn request,
// a submission that stopped half-way — it names that version with a link to its page and does not
// submit the category (rev 1.94).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ErrorSummary, type FormErrorEntry } from "../../components/form/ErrorSummary";
import { controlClass, Field, fieldId } from "../../components/form/Field";
import { WarningCircle } from "../../components/icons/registry";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { useAccess } from "../../lib/access";
import { api, send, unwrap } from "../../lib/api/client";
import { type CommandKeys, useCommand, useCommandKeys } from "../../lib/api/commands";
import { fetchJob, isTerminal, JOB_POLL_INTERVAL_MS, type Job } from "../../lib/api/jobs";
import { ApiProblem, readProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import { accountingVersionRoute, fetchAllPolicies } from "../../lib/api/queries/policies";
import {
  rowIfMatch,
  type Tenant,
  TENANT_PATH,
  tenantKey,
  useTenant,
} from "../../lib/api/queries/tenant";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import { useFieldRefusals } from "../../lib/api/refusals";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { SETUP_PERMISSION, SettingsPageHeader } from "./index";

type RegistryCategory = components["schemas"]["RegistryCategory"];
type Policy = components["schemas"]["PolicyOut"];

export const POLICIES_PATH = "/api/v1/policies";
/** 04 API-R-13: lifecycle commands need `config.author` — at TENANT scope for all entities. */
export const AUTHOR_PERMISSION = "config.author";
export const READ_PERMISSION = "config.read";
export const NEGATIVE_STYLES = ["PARENTHESES", "MINUS"] as const;
export type NegativeStyle = (typeof NEGATIVE_STYLES)[number];
/** SCREENS_B §9.6 radio labels: the two DS-FMT-06 styles of the figure −4,000.00 (U+2212 minus). */
export const NEGATIVE_EXAMPLES: Readonly<Record<NegativeStyle, string>> = {
  PARENTHESES: "(4,000.00)",
  MINUS: "\u22124,000.00",
};

type Control =
  | { readonly kind: "negative" }
  | { readonly kind: "checkbox"; readonly help?: boolean }
  | {
      readonly kind: "integer";
      readonly min: number;
      readonly max: number;
      readonly unit?: "days" | "years";
    }
  | { readonly kind: "percent" }
  | { readonly kind: "list" };

export type FieldsetId = "formats" | "close" | "platform";

export interface WorkspaceField {
  /** The registry key (T-PLT-31). */
  readonly key: string;
  readonly category: RegistryCategory;
  readonly fieldset: FieldsetId;
  /** The message key under `settings.workspace.fields`. */
  readonly id: string;
  readonly control: Control;
}

/** SCREENS_B §9.6 field table in wireframe order. */
export const WORKSPACE_FIELDS: readonly WorkspaceField[] = [
  {
    key: "ui.negative_number_style",
    category: "PLATFORM",
    fieldset: "formats",
    id: "negative",
    control: { kind: "negative" },
  },
  {
    key: "close.require_reconciliations_for_lock",
    category: "CLOSE",
    fieldset: "close",
    id: "requireReconciliations",
    control: { kind: "checkbox" },
  },
  {
    key: "close.unacknowledged_export_block_days",
    category: "CLOSE",
    fieldset: "close",
    id: "exportBlock",
    control: { kind: "integer", min: 0, max: 30, unit: "days" },
  },
  {
    key: "close.late_entry_window_days",
    category: "CLOSE",
    fieldset: "close",
    id: "lateEntry",
    control: { kind: "integer", min: 0, max: 31, unit: "days" },
  },
  {
    key: "close.rollforward_other_threshold_ratio",
    category: "CLOSE",
    fieldset: "close",
    id: "otherThreshold",
    control: { kind: "percent" },
  },
  {
    key: "close.dq_revenue_without_billing_days",
    category: "CLOSE",
    fieldset: "close",
    id: "revenueWithoutBilling",
    control: { kind: "integer", min: 1, max: 365, unit: "days" },
  },
  {
    key: "close.dq_inactive_contract_days",
    category: "CLOSE",
    fieldset: "close",
    id: "inactiveContract",
    control: { kind: "integer", min: 1, max: 730, unit: "days" },
  },
  {
    key: "platform.job_concurrency",
    category: "PLATFORM",
    fieldset: "platform",
    id: "jobConcurrency",
    control: { kind: "integer", min: 1, max: 16 },
  },
  {
    key: "platform.audit_retention_years",
    category: "PLATFORM",
    fieldset: "platform",
    id: "auditRetention",
    control: { kind: "integer", min: 7, max: 30, unit: "years" },
  },
  {
    key: "approval.ssp_second_approver_threshold_ratio",
    category: "PLATFORM",
    fieldset: "platform",
    id: "sspThreshold",
    control: { kind: "percent" },
  },
  {
    key: "data.quarantine_failed_rows",
    category: "INTEGRATION",
    fieldset: "platform",
    id: "quarantine",
    control: { kind: "checkbox", help: true },
  },
  {
    key: "integration.grouping_fields",
    category: "INTEGRATION",
    fieldset: "platform",
    id: "groupingFields",
    control: { kind: "list" },
  },
  {
    key: "disclosure.mandatory_disaggregation_attributes",
    category: "DISCLOSURE_ELECTION",
    fieldset: "platform",
    id: "disaggregation",
    control: { kind: "list" },
  },
];

const FIELDSETS: readonly FieldsetId[] = ["formats", "close", "platform"];
/** One label column and one control column, as the SF-15:profile rows (SCREENS_B §9.6 wireframe). */
const ROW = "grid grid-cols-[minmax(0,16rem)_minmax(0,1fr)] items-start gap-4";
const CATEGORIES: readonly RegistryCategory[] = [
  "PLATFORM",
  "CLOSE",
  "INTEGRATION",
  "DISCLOSURE_ELECTION",
];

export type FormValue = string | boolean | readonly string[];
export type FormValues = Readonly<Record<string, FormValue>>;

/** A registry ratio as a percentage text by moving the decimal point, never through a number: 0.10 → 10. */
export function ratioToPercent(ratio: string): string {
  const [whole = "0", fraction = ""] = ratio.split(".");
  const padded = fraction.padEnd(2, "0");
  const integer = `${whole}${padded.slice(0, 2)}`.replace(/^0+(?=\d)/, "");
  const rest = padded.slice(2).replace(/0+$/, "");
  return rest === "" ? integer : `${integer}.${rest}`;
}

/** A percentage text from 0 to 100 as a registry ratio (10.5 → 0.105); null when invalid. */
export function percentToRatio(percent: string): string | null {
  const text = percent.trim();
  if (!/^\d+(\.\d+)?$/.test(text)) {
    return null;
  }
  const [whole = "0", fraction = ""] = text.split(".");
  const integer = whole.replace(/^0+(?=\d)/, "");
  if (
    integer.length > 3 ||
    (integer.length === 3 && !(integer === "100" && /^0*$/.test(fraction)))
  ) {
    return null;
  }
  const digits = integer.padStart(3, "0");
  const head = digits.slice(0, -2).replace(/^0+(?=\d)/, "");
  const tail = `${digits.slice(-2)}${fraction}`.replace(/0+$/, "");
  return tail === "" ? head : `${head}.${tail}`;
}

function normaliseRatio(ratio: string): string {
  return percentToRatio(ratioToPercent(ratio)) ?? ratio;
}

/** The form text of a resolved registry value. */
export function toFormValue(field: WorkspaceField, value: unknown): FormValue {
  switch (field.control.kind) {
    case "checkbox":
      return value === true;
    case "integer":
      return typeof value === "number" ? String(value) : String(value ?? "");
    case "percent":
      return ratioToPercent(typeof value === "string" ? value : String(value ?? "0"));
    case "list":
      return Array.isArray(value) ? value.map(String) : [];
    case "negative":
      return value === "MINUS" ? "MINUS" : "PARENTHESES";
  }
}

/** The registry value of a form value, or an error message. */
export function toRegistryValue(
  field: WorkspaceField,
  value: FormValue,
): { readonly value: unknown } | { readonly error: string } {
  const control = field.control;
  switch (control.kind) {
    case "checkbox":
      return { value: value === true };
    case "integer": {
      const text = typeof value === "string" ? value.trim() : "";
      const number = /^\d+$/.test(text) ? Number(text) : Number.NaN;
      if (!(number >= control.min && number <= control.max)) {
        return { error: t(`settings.workspace.fields.${field.id}.invalid`) };
      }
      return { value: number };
    }
    case "percent": {
      const ratio = percentToRatio(typeof value === "string" ? value : "");
      return ratio === null ? { error: t("settings.workspace.percentInvalid") } : { value: ratio };
    }
    case "list":
      return { value: Array.isArray(value) ? [...(value as readonly string[])] : [] };
    case "negative":
      return { value };
  }
}

function sameValue(field: WorkspaceField, current: unknown, stored: unknown): boolean {
  if (
    field.control.kind === "percent" &&
    typeof current === "string" &&
    typeof stored === "string"
  ) {
    return normaliseRatio(current) === normaliseRatio(stored);
  }
  return JSON.stringify(current) === JSON.stringify(stored);
}

export interface CategoryChange {
  readonly category: RegistryCategory;
  readonly values: Readonly<Record<string, unknown>>;
}

/** The changed values grouped by category in SCREENS_B §9.6 order, or the field errors. */
export function workspaceChanges(
  stored: Readonly<Record<string, unknown>>,
  values: FormValues,
): {
  readonly changes: readonly CategoryChange[];
  readonly errors: Readonly<Record<string, string>>;
} {
  const errors: Record<string, string> = {};
  const grouped = new Map<RegistryCategory, Record<string, unknown>>();
  for (const field of WORKSPACE_FIELDS) {
    const current = values[field.key];
    if (current === undefined || field.control.kind === "list") {
      continue;
    }
    const converted = toRegistryValue(field, current);
    if ("error" in converted) {
      errors[field.key] = converted.error;
      continue;
    }
    if (!sameValue(field, converted.value, stored[field.key])) {
      const group = grouped.get(field.category) ?? {};
      group[field.key] = converted.value;
      grouped.set(field.category, group);
    }
  }
  const changes = CATEGORIES.filter((category) => grouped.has(category)).map((category) => ({
    category,
    values: grouped.get(category) ?? {},
  }));
  return { changes, errors };
}

export function resolvedKey(): QueryKey {
  return queryKey("policies", "tenant", { view: "workspace-resolved" });
}

async function fetchResolved(): Promise<Readonly<Record<string, unknown>>> {
  const entries = await Promise.all(
    WORKSPACE_FIELDS.map(async (field) => {
      const resolution = await unwrap(
        api.GET("/api/v1/policies/resolve", { params: { query: { key: field.key } } }),
      );
      return [field.key, resolution.value as unknown] as const;
    }),
  );
  return Object.fromEntries(entries);
}

function pendingKey(): QueryKey {
  return queryKey("policies", "tenant", { view: "workspace-pending" });
}

/** A DRAFT or TESTED tenant version of a category of this form: open, and no request yet. */
export interface OpenVersion {
  readonly category: RegistryCategory;
  readonly id: string;
  readonly versionNo: number;
}

interface Pending {
  readonly categories: readonly RegistryCategory[];
  readonly requestNo: string | null;
  /** At most one per category (PRD SM-04), in the order of the form's categories. */
  readonly open: readonly OpenVersion[];
}

async function fetchPending(): Promise<Pending> {
  const listed = await fetchAllPolicies();
  const tenant = listed.filter(
    (version: Policy) => version.scope === "TENANT" && CATEGORIES.includes(version.category),
  );
  const submitted = tenant.filter((version) => version.status === "SUBMITTED");
  const categories = CATEGORIES.filter((category) =>
    submitted.some((version) => version.category === category),
  );
  const open = CATEGORIES.flatMap((category): OpenVersion[] => {
    const found = tenant.find(
      (version) =>
        version.category === category &&
        (version.status === "DRAFT" || version.status === "TESTED"),
    );
    return found === undefined ? [] : [{ category, id: found.id, versionNo: found.version_no }];
  });
  const requestId = submitted.find(
    (version) => version.pending_approval_request_id !== null,
  )?.pending_approval_request_id;
  if (requestId === undefined || requestId === null) {
    return { categories, requestNo: null, open };
  }
  const response = await send("GET", `/api/v1/approvals/${requestId}`);
  if (!response.ok) {
    return { categories, requestNo: null, open };
  }
  const approval = (await response.json()) as { readonly request_no?: string };
  return { categories, requestNo: approval.request_no ?? null, open };
}

/** SCREENS_B §9.6 rev 1.94: what the form says of an open version of one of its categories. */
function openVersionSentence(version: OpenVersion): string {
  return t("settings.workspace.openVersion", {
    version: String(version.versionNo),
    category: t(`settings.workspace.category.${version.category}`),
  });
}

type Step<T> =
  { readonly ok: true; readonly data: T } | { readonly ok: false; readonly problem: ApiProblem };

/**
 * One command of the submission sequence. It keeps its key after it succeeded, until the whole
 * submission is through (DG-FE-05 rev 1.156): when a later command fails, the second press sends
 * this one again under its key and the API replays the version it created instead of creating another.
 */
async function commandStep<T>(keys: CommandKeys, path: string, body: unknown): Promise<Step<T>> {
  const response = await keys.send("POST", path, { body, keep: true });
  if (!response.ok) {
    return { ok: false, problem: await readProblem(response) };
  }
  return { ok: true, data: (await response.json()) as T };
}

/** Polls `GET /jobs/{id}` every 2 seconds until the job is terminal (DG-FE-05). */
export async function waitForJob(
  jobId: string,
  pause: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): Promise<Job> {
  for (;;) {
    const job = await fetchJob(jobId);
    if (isTerminal(job)) {
      return job;
    }
    await pause(JOB_POLL_INTERVAL_MS);
  }
}

export function WorkspaceSettings() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.workspace.title");
  // The workspace is one for all entities: its name is read and saved by a holder of
  // `settings.manage` for all of them (SCREENS §0.6 SCR-PERM-02 (c)).
  const manage = access.holdsForAll(SETUP_PERMISSION);
  const read = manage || access.holdsAnywhere(READ_PERMISSION);

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!read) {
    body = (
      <AccessLimited
        area={title}
        permissions={[SETUP_PERMISSION]}
        allEntities={
          access.holdsAnywhere(SETUP_PERMISSION)
            ? { message: "settings.workspace.access.allEntities", permission: SETUP_PERMISSION }
            : undefined
        }
      />
    );
  } else {
    body = <WorkspaceSections manage={manage} author={access.holdsForAll(AUTHOR_PERMISSION)} />;
  }

  return (
    <div className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={title} group="workspace" />
      {body}
    </div>
  );
}

function WorkspaceSections({
  manage,
  author,
}: {
  readonly manage: boolean;
  readonly author: boolean;
}) {
  const tenant = useTenant(manage);
  const resolved = useQuery({ queryKey: resolvedKey(), queryFn: fetchResolved });
  const pending = useQuery({ queryKey: pendingKey(), queryFn: fetchPending });

  if (resolved.isError || tenant.isError) {
    const problem = resolved.error ?? tenant.error;
    return (
      <Banner
        tone="negative"
        title={t("settings.workspace.loadError")}
        actions={
          <Button
            variant="link"
            onClick={() => {
              void resolved.refetch();
              if (manage) {
                void tenant.refetch();
              }
            }}
          >
            {t("settings.workspace.retry")}
          </Button>
        }
      >
        {problem?.message}
      </Banner>
    );
  }
  if (resolved.data === undefined || (manage && tenant.data === undefined)) {
    return <Skeleton region={t("settings.workspace.title")} shape="rows" count={8} />;
  }
  const pendingData = pending.data;
  return (
    <>
      {pendingData !== undefined && pendingData.categories.length > 0 ? (
        <Banner
          tone="info"
          title={
            pendingData.requestNo === null
              ? t("settings.workspace.pendingNoNumber", {
                  categories: pendingData.categories
                    .map((category) => t(`settings.workspace.category.${category}`))
                    .join(", "),
                })
              : t("settings.workspace.pending", {
                  categories: pendingData.categories
                    .map((category) => t(`settings.workspace.category.${category}`))
                    .join(", "),
                  request: pendingData.requestNo,
                })
          }
        />
      ) : null}
      {(pendingData?.open ?? []).map((version) => (
        <Banner
          key={version.category}
          tone="info"
          title={openVersionSentence(version)}
          actions={
            <Link
              to={accountingVersionRoute(version.id)}
              className="text-body-sm font-medium text-accent-fg hover:underline"
            >
              {t("policies.accountingVersion.openVersion", { version: String(version.versionNo) })}
            </Link>
          }
        />
      ))}
      {tenant.data === undefined ? null : <WorkspaceIdentity tenant={tenant.data} />}
      <WorkspaceForm stored={resolved.data} author={author} />
    </>
  );
}

/** The API member the one field of "Workspace" sends (DG-FE-06 rev 1.228). */
const IDENTITY_MEMBERS = { display_name: ["display_name"] } as const;

function WorkspaceIdentity({ tenant }: { readonly tenant: Tenant }) {
  const headingId = useId();
  const toast = useToast();
  const [name, setName] = useState(tenant.display_name);
  const rename = useCommand<Tenant>({
    method: "PATCH",
    path: TENANT_PATH,
    invalidates: [tenantKey()],
  });
  const refusals = useFieldRefusals(rename.problem, IDENTITY_MEMBERS);
  const nameError = refusals.fields.display_name;
  const row = "grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)] gap-4 py-2";

  const save = async () => {
    const outcome = await rename.submit(
      { display_name: name },
      { ifMatch: rowIfMatch(tenant.row_version) },
    );
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("settings.workspace.nameSaved") });
    }
  };

  return (
    <section aria-labelledby={headingId} className="flex flex-col">
      <h2 id={headingId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
        {t("settings.workspace.identity.title")}
      </h2>
      <RefusalBanner
        problem={refusals.banner}
        placed={refusals.placed}
        conflict={rename.banner}
        headingLevel={3}
      />
      <dl className="flex flex-col text-body-sm">
        <div className={row}>
          <dt className="font-medium text-fg-1">{t("settings.workspace.identity.code")}</dt>
          <dd className="font-mono text-fg-1">{tenant.code}</dd>
        </div>
        <div className={row}>
          <dt className="font-medium text-fg-1">{t("settings.workspace.identity.kind")}</dt>
          <dd className="text-fg-1">{t(`settings.workspace.identity.kinds.${tenant.kind}`)}</dd>
        </div>
        <div className={row}>
          <dt className="font-medium text-fg-1">{t("settings.workspace.identity.currency")}</dt>
          <dd className="font-mono text-fg-1">{tenant.reporting_currency}</dd>
        </div>
        <div className={row}>
          <dt className="font-medium text-fg-1">{t("settings.workspace.identity.demo")}</dt>
          <dd className="text-fg-1">
            {t(tenant.is_demo ? "settings.workspace.yes" : "settings.workspace.no")}
          </dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-end gap-3 pt-2">
        <div className="w-80">
          <Field
            name="display_name"
            label={t("settings.workspace.identity.name")}
            error={nameError}
          >
            {(control) => (
              <input
                {...control}
                type="text"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  refusals.edited("display_name");
                }}
                className={controlClass(nameError !== null)}
              />
            )}
          </Field>
        </div>
        <Button variant="secondary" loading={rename.pending} onClick={() => void save()}>
          {t("settings.workspace.identity.saveName")}
        </Button>
      </div>
    </section>
  );
}

interface WorkspaceFormProps {
  readonly stored: Readonly<Record<string, unknown>>;
  readonly author: boolean;
}

function initialValues(stored: Readonly<Record<string, unknown>>): FormValues {
  return Object.fromEntries(
    WORKSPACE_FIELDS.map((field) => [field.key, toFormValue(field, stored[field.key])]),
  );
}

function WorkspaceForm({ stored, author }: WorkspaceFormProps) {
  const toast = useToast();
  // One press creates, tests and submits a version per changed category (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<FormValues>(() => initialValues(stored));
  const [comment, setComment] = useState("");
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const [submitCount, setSubmitCount] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // A step the API refused: the banner says every sentence of the refusal (DG-FE-06 rev 1.228).
  const [refusal, setRefusal] = useState<ApiProblem | null>(null);
  // The versions a press of this form has started and not brought to their request yet, by
  // category: the id once the create was answered, null while its answer is not known. Such a
  // version is open, and it is this form's: when a command got no answer, the next press continues
  // it under the keys it had (DG-FE-05 rev 1.156). Once the API has refused a command the
  // submission is over: a version it created stays open — the form cannot change what was refused
  // — and is no longer the form's, and its keys are forgotten.
  const started = useRef(new Map<RegistryCategory, string | null>());
  const stopped = async (category: RegistryCategory, problem: ApiProblem | string) => {
    started.current.delete(category);
    keys.clear();
    if (typeof problem === "string") {
      setProblem(problem);
    } else {
      setRefusal(problem);
    }
    // What is open now is named at once, with the way to its page.
    await queryClient.invalidateQueries({ queryKey: pendingKey() });
  };

  const update = (key: string, value: FormValue) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setSubmitCount((count) => count + 1);
    setProblem(null);
    setRefusal(null);
    const { changes, errors: fieldErrors } = workspaceChanges(stored, values);
    const found: Record<string, string> = { ...fieldErrors };
    const commentError = reasonError(comment);
    if (commentError !== null) {
      found.comment = commentError;
    }
    if (changes.length === 0 && Object.keys(fieldErrors).length === 0) {
      found.form = t("settings.workspace.noChanges");
    }
    setErrors(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setSubmitting(true);
    try {
      // Before anything is sent the versions are read again: a category of which a DRAFT or TESTED
      // version is open is not submitted — the API would refuse the new version (PRD SM-04) — and
      // the form says which version stands in its way. The other categories go through.
      const { open } = await queryClient.fetchQuery({
        queryKey: pendingKey(),
        queryFn: fetchPending,
        staleTime: 0,
      });
      const held = open.filter((version) => {
        const mine = started.current.get(version.category);
        return (
          changes.some((change) => change.category === version.category) &&
          (mine === undefined || (mine !== null && mine !== version.id))
        );
      });
      const free = changes.filter(
        (change) => !held.some((version) => version.category === change.category),
      );
      if (held.length > 0) {
        setErrors({ form: held.map(openVersionSentence).join(" ") });
      }
      if (free.length === 0) {
        return;
      }
      for (const change of free) {
        if (!started.current.has(change.category)) {
          started.current.set(change.category, null);
        }
        const created = await commandStep<Policy>(keys, POLICIES_PATH, {
          category: change.category,
          scope: "TENANT",
          values: change.values,
        });
        if (!created.ok) {
          await stopped(change.category, created.problem);
          return;
        }
        started.current.set(change.category, created.data.id);
        const versionPath = `${POLICIES_PATH}/${created.data.id}`;
        const test = await commandStep<Job>(keys, `${versionPath}/test`, {
          run_simulation: false,
        });
        if (!test.ok) {
          await stopped(change.category, test.problem);
          return;
        }
        const job = await waitForJob(test.data.id);
        if (job.state === "FAILED" || job.state === "CANCELLED") {
          await stopped(
            change.category,
            job.problem?.detail ?? job.problem?.title ?? t("settings.workspace.testFailed"),
          );
          return;
        }
        const submitted = await commandStep<Policy>(keys, `${versionPath}/submit`, {
          comment: comment.trim(),
        });
        if (!submitted.ok) {
          await stopped(change.category, submitted.problem);
          return;
        }
        started.current.delete(change.category);
      }
      keys.clear();
      started.current.clear();
      setComment("");
      toast.show({ tone: "positive", message: t("settings.workspace.submitted") });
      await queryClient.invalidateQueries({ queryKey: ["policies"] });
    } catch (error) {
      // A command or the job's read got no answer: the form keeps its input, and the next press
      // sends the same keys.
      if (error instanceof ApiProblem) {
        setRefusal(error);
      } else {
        setProblem(t("common.command.noAnswer"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const summary: FormErrorEntry[] = Object.entries(errors)
    .filter(([name]) => name !== "form")
    .map(([name, message]) => ({ name: name === "comment" ? "comment" : name, message }));

  return (
    <form
      aria-label={t("settings.workspace.form")}
      data-testid="SF-15-workspace-form"
      noValidate
      onSubmit={(event) => void submit(event)}
      className="flex flex-col gap-6"
    >
      {summary.length > 0 ? <ErrorSummary errors={summary} submitCount={submitCount} /> : null}
      {problem === null ? null : <Banner tone="negative" announce="live" title={problem} />}
      <RefusalBanner problem={refusal} />
      {FIELDSETS.map((fieldset) => (
        <fieldset key={fieldset} className="flex flex-col gap-4">
          <legend className="mb-2 w-full border-b border-hairline pb-2 text-title-sm text-fg-1">
            {t(`settings.workspace.fieldset.${fieldset}`)}
          </legend>
          {WORKSPACE_FIELDS.filter((field) => field.fieldset === fieldset).map((field) => (
            <WorkspaceControl
              key={field.key}
              field={field}
              value={values[field.key] ?? ""}
              error={errors[field.key] ?? null}
              readOnly={!author}
              onChange={(value) => {
                update(field.key, value);
              }}
            />
          ))}
          {fieldset === "platform" ? (
            <p className="text-body-sm text-fg-2">{t("settings.workspace.accountingPolicies")}</p>
          ) : null}
        </fieldset>
      ))}
      {author ? (
        <div className="flex flex-col gap-3">
          <ReasonField
            name="comment"
            label={t("settings.workspace.comment")}
            value={comment}
            onChange={setComment}
            showError={submitCount > 0}
            error={errors.comment ?? null}
          />
          <div className="flex flex-wrap items-center justify-end gap-3">
            {errors.form === undefined ? null : (
              <p className="text-body-sm text-fg-2">{errors.form}</p>
            )}
            <Button type="submit" variant="primary" loading={submitting}>
              {t("settings.workspace.submit")}
            </Button>
          </div>
        </div>
      ) : null}
    </form>
  );
}

interface WorkspaceControlProps {
  readonly field: WorkspaceField;
  readonly value: FormValue;
  readonly error: string | null;
  readonly readOnly: boolean;
  readonly onChange: (value: FormValue) => void;
}

function WorkspaceControl({ field, value, error, readOnly, onChange }: WorkspaceControlProps) {
  const labelId = useId();
  const control = field.control;
  const label = t(`settings.workspace.fields.${field.id}.label`);
  switch (control.kind) {
    case "negative":
      return (
        <div
          role="radiogroup"
          aria-labelledby={labelId}
          aria-readonly={readOnly ? true : undefined}
          data-testid="SF-15-workspace-negative-style"
          className={ROW}
        >
          <span id={labelId} className="text-body-sm font-medium text-fg-1">
            {label}
          </span>
          <div className="flex flex-wrap items-center gap-6">
            {NEGATIVE_STYLES.map((style) => (
              <label key={style} className="flex items-center gap-2 text-body-sm text-fg-1">
                <input
                  type="radio"
                  name={field.key}
                  value={style}
                  checked={value === style}
                  aria-label={t(`settings.workspace.negative.${style}.name`)}
                  onChange={() => {
                    if (!readOnly) {
                      onChange(style);
                    }
                  }}
                  className="size-4"
                />
                <span aria-hidden="true" className="num tabular-nums">
                  {NEGATIVE_EXAMPLES[style]}
                </span>
              </label>
            ))}
          </div>
        </div>
      );
    case "checkbox": {
      const id = fieldId(field.key);
      const helpId = `${id}-help`;
      const help = control.help === true ? t(`settings.workspace.fields.${field.id}.help`) : null;
      return (
        <div className={ROW}>
          <label htmlFor={id} className="text-body-sm font-medium text-fg-1">
            {label}
          </label>
          <div className="flex flex-col gap-1">
            <input
              id={id}
              name={field.key}
              type="checkbox"
              checked={value === true}
              aria-readonly={readOnly ? true : undefined}
              aria-describedby={help === null ? undefined : helpId}
              onChange={(event) => {
                if (!readOnly) {
                  onChange(event.target.checked);
                }
              }}
              className="mt-0.5 size-4"
            />
            {help === null ? null : (
              <p id={helpId} className="text-body-sm text-fg-3">
                {help}
              </p>
            )}
          </div>
        </div>
      );
    }
    case "integer":
    case "percent": {
      const id = fieldId(field.key);
      const unitId = `${id}-unit`;
      const errorId = `${id}-error`;
      const unit =
        control.kind === "percent"
          ? t("settings.workspace.unit.percent")
          : control.unit === undefined
            ? null
            : t(`settings.workspace.unit.${control.unit}`);
      const describedBy = cn(unit !== null && unitId, error !== null && errorId);
      return (
        <div className={ROW}>
          <label htmlFor={id} className="pt-1.5 text-body-sm font-medium text-fg-1">
            {label}
          </label>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <div className="w-24">
                <input
                  id={id}
                  name={field.key}
                  type="text"
                  inputMode={control.kind === "integer" ? "numeric" : "decimal"}
                  readOnly={readOnly}
                  value={typeof value === "string" ? value : ""}
                  aria-invalid={error === null ? undefined : true}
                  aria-describedby={describedBy === "" ? undefined : describedBy}
                  onChange={(event) => {
                    onChange(event.target.value);
                  }}
                  className={cn(controlClass(error !== null), "num text-end")}
                />
              </div>
              {unit === null ? null : (
                <span id={unitId} className="text-body-sm text-fg-2">
                  {unit}
                </span>
              )}
            </div>
            {error === null ? null : (
              <p id={errorId} className="flex items-start gap-1 text-body-sm text-negative-fg">
                <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
                {error}
              </p>
            )}
          </div>
        </div>
      );
    }
    case "list": {
      const items = Array.isArray(value) ? (value as readonly string[]) : [];
      return (
        <div className={ROW}>
          <span className="text-body-sm font-medium text-fg-1">{label}</span>
          <span className="font-mono text-body-sm text-fg-1">
            {items.length === 0 ? "—" : items.join(", ")}
          </span>
        </div>
      );
    }
  }
}

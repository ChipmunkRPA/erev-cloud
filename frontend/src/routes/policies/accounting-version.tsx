// SF-13:accounting-version Accounting policy version editor (SCREENS §11.0 lifecycle pattern, §11.3
// version editor; §0.4 RT-64; §0.7 SCR-ST-05, SCR-ST-07, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-06, DS-CMP-10,
// DS-CMP-11, DS-CMP-16, DS-CMP-19, DS-CMP-21, DS-CMP-29; 04 API-R-13 `GET, PATCH /policies/{id}`
// (`If-Match`), `POST /policies/{id}/test` (202 job), `/submit`, `/withdraw`, `GET /registry/parameters`;
// REQ-POL-004 to REQ-POL-007, REQ-POL-011; BUILD_SPEC RFD-23). Header "<category> · <scope>" with the
// status, version and preset chips; the lifecycle stepper; "Effective from"; the parameter filters
// (quick search, Section, "Changed only"); the DataGrid "Policy parameters" joined from the registry
// parameters, the version's values and the published version of the same scope ("Current value");
// forced parameters show the lock "Forced by the framework" and no control; "Save values" patches the
// draft; "Run tests and simulation" starts the test job and the results panel reads the evidence and
// the impact simulation. Values change only while the version is DRAFT or TESTED (DB-04); the approval
// publishes (D-76). "Withdraw" is the policy's own route, so its author is back on a DRAFT (PRD SM-01,
// SM-04). A REJECTED or WITHDRAWN version offers "Edit" — the `PATCH` that reopens it — while its basis
// is still the published version of its scope, and PRD ERR-92's sentence with "New policy version"
// once a later version was published (SCREENS §11.3 rev 1.56).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field, fieldId } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Switch } from "../../components/form/Switch";
import { LockSimple } from "../../components/icons/registry";
import { RecordHeader } from "../../components/record/RecordHeader";
import { type Step, Stepper } from "../../components/record/Stepper";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { type Approval, fetchApproval } from "../../lib/api/queries/approvals";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  ACCOUNTING_ROUTE,
  accountingVersionRoute,
  allPoliciesKey,
  currentPublished,
  EVERY_POLICY,
  fetchAllPolicies,
  filterRows,
  formatLiteral,
  INSTANT_CATEGORIES,
  isPolicyEditable,
  openVersion,
  type ParameterFilter,
  type ParameterRow,
  parameterRows,
  parseLiteral,
  type Policy,
  policyCommandPath,
  policyKey,
  policyPath,
  type PolicyUpdate,
  proposedValue,
  sectionsOf,
  SETTINGS_CATEGORIES,
  SETTINGS_CATEGORY_ROUTES,
  usePolicy,
  useParameters,
  valueControl,
} from "../../lib/api/queries/policies";
import { CONFIG_AUTHOR_PERMISSION, CONFIG_READ_PERMISSION } from "../../lib/api/queries/rule-sets";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import {
  effectiveInstant,
  formatDate,
  formatNumber,
  NO_VALUE,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { categoryLabel, NewVersionDrawer, presetLabel, scopeLabel } from "./accounting";
import { POLICY_TABS } from "./revenue";
import {
  approverNames,
  EFFECTIVE_FIELD,
  focusEffectiveFrom,
  refusesEffectiveDate,
  useLifecycleRefusal,
  useSubmissionOrder,
} from "./version-meta";

// The help of "Effective from" stands under the filter row, and the control names it as the help of
// its field is named (`Field`: "<field id>-help").
const EFFECTIVE_HELP_ID = `${fieldId(EFFECTIVE_FIELD)}-help`;

/**
 * A literal in mono. One longer than its column shortens under its full text as the title, as a grid
 * text cell does: the cell would otherwise cut it at its edge, and a cut literal reads as another
 * one (SCREENS §11.3 rev 1.56).
 */
function mono(text: string): ReactNode {
  return text === "" ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="truncate font-mono text-mono" title={text}>
      {text}
    </span>
  );
}

/**
 * A value beside the level it comes from (SCREENS §11.3 "Current value" and "Proposed value":
 * "Tenant", "Framework default"). The value shortens, so that the level stays whole in a narrow
 * column.
 */
function levelled(text: string, level: string): ReactNode {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {mono(text)}
      <span className="shrink-0 whitespace-nowrap text-caption text-fg-3">{level}</span>
    </span>
  );
}

/** SCREENS §11.0 lifecycle steps of a registry version. */
export function policyLifecycle(
  policy: Policy,
  approval: Approval | undefined,
): { readonly steps: readonly Step[]; readonly currentId: string } {
  const approvers = approverNames(approval);
  const decided =
    policy.status === "APPROVED" || policy.status === "PUBLISHED" || policy.status === "SUPERSEDED";
  let approvalCaption: string | undefined;
  if (policy.status === "SUBMITTED") {
    approvalCaption = t("policies.lifecycle.pending");
  } else if (decided && approvers.length > 0) {
    approvalCaption = t("policies.lifecycle.approvedBy", { name: approvers.join(", ") });
  } else if (policy.status === "REJECTED") {
    approvalCaption = t("policies.lifecycle.rejected");
  } else if (policy.status === "WITHDRAWN") {
    approvalCaption = t("policies.lifecycle.withdrawn");
  }
  const order: Readonly<Record<Policy["status"], number>> = {
    DRAFT: 0,
    TESTED: 1,
    SUBMITTED: 2,
    REJECTED: 2,
    WITHDRAWN: 2,
    APPROVED: 3,
    PUBLISHED: 4,
    SUPERSEDED: 4,
    // E-12 VOIDED is a discarded estimate version only (04 rev 1.210); no version shown here takes it.
    VOIDED: 0,
  };
  const reached = order[policy.status];
  const state = (index: number): Step["state"] => {
    if (index < reached) {
      return "complete";
    }
    if (index === reached) {
      if (policy.status === "REJECTED") {
        return "error";
      }
      if (policy.status === "WITHDRAWN") {
        return "skipped";
      }
      return "current";
    }
    return index === 3 && reached === 4 ? "complete" : "pending";
  };
  const evidence = testEvidence(policy);
  const steps: Step[] = [
    {
      id: "draft",
      label: t("policies.lifecycle.draft"),
      state: state(0),
      caption: t("policies.lifecycle.edited", {
        date: formatDate(timestampDate(policy.updated_at)),
      }),
    },
    {
      id: "tested",
      label: t("policies.lifecycle.tested"),
      state: state(1),
      caption:
        evidence === null
          ? undefined
          : t("policies.lifecycle.tests", {
              passed: formatNumber(evidence.passed, { kind: "count" }),
              total: formatNumber(evidence.total, { kind: "count" }),
            }),
    },
    {
      id: "approval",
      label: t("policies.lifecycle.approval"),
      state: state(2),
      caption: approvalCaption,
    },
    {
      id: "published",
      label: t("policies.lifecycle.published"),
      state: reached === 4 ? "complete" : state(3),
      caption:
        policy.effective_from === null
          ? undefined
          : t("policies.lifecycle.effective", {
              date: formatDate(timestampDate(policy.effective_from)),
            }),
    },
  ];
  const currentId = (["draft", "tested", "approval", "published"] as const)[Math.min(reached, 3)];
  return { steps, currentId: currentId ?? "draft" };
}

/** API-S-Policy `test_evidence` is free-form; the example-case counts are read when present. */
export function testEvidence(
  policy: Pick<Policy, "test_evidence">,
): { readonly passed: number; readonly total: number } | null {
  const evidence = policy.test_evidence;
  if (evidence === null) {
    return null;
  }
  const passed = evidence.passed;
  const total = evidence.total;
  return typeof passed === "number" && typeof total === "number" ? { passed, total } : null;
}

export function AccountingVersionEditor() {
  const { policyId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const policy = usePolicy(policyId);
  const title = t("policies.accountingVersion.documentTitle");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(CONFIG_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else if (policy.isError) {
    body =
      policy.error instanceof ApiProblem && policy.error.status === 404 ? (
        <div data-testid="SF-13-accounting-version-not-found">
          <EmptyState
            title={t("policies.accountingVersion.notFound.title")}
            description={t("policies.version.notFound.description")}
            link={{ label: t("policies.tabs.accounting"), href: ACCOUNTING_ROUTE }}
          />
        </div>
      ) : (
        <Banner tone="negative" title={t("policies.accountingVersion.loadError")} />
      );
  } else if (policy.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else {
    // One view per version: the route stays when the author goes from one version to another — the
    // link of a version whose basis was superseded, and Back — and what was chosen on one page and
    // not saved (proposed values, the date, the filters) is no part of the other.
    return (
      <VersionView
        key={policy.data.id}
        policy={policy.data}
        me={me.data}
        author={access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION)}
      />
    );
  }
  return (
    <div
      data-testid="SF-13-accounting-version-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

function VersionNav({ policy }: { readonly policy: Policy }) {
  const built = useBuiltPaths();
  const access = useAccess();
  const location = useLocation();
  const tabs: RouteTab[] = POLICY_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`policies.tabs.${tab.key}`),
    to: tab.key === "accounting" ? `${location.pathname}${location.search}` : tab.path,
    end: true,
  }));
  return (
    <div className="flex flex-col gap-3">
      <nav aria-label={t("common.record.breadcrumb")}>
        <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
          <li className="flex items-center gap-1.5">
            <Link to="/policies" className="hover:text-fg-1 hover:underline">
              {t("policies.title")}
            </Link>
            <span aria-hidden="true">/</span>
          </li>
          <li className="flex items-center gap-1.5">
            <Link to={ACCOUNTING_ROUTE} className="hover:text-fg-1 hover:underline">
              {t("policies.tabs.accounting")}
            </Link>
            <span aria-hidden="true">/</span>
          </li>
          <li aria-current="page">
            {`${scopeLabel(policy)} ${t("policies.version.number", { version: String(policy.version_no) })}`}
          </li>
        </ol>
      </nav>
      {tabs.length === 0 ? null : <RouteTabs label={t("policies.tabs.label")} tabs={tabs} />}
    </div>
  );
}

function VersionView({
  policy,
  me,
  author,
}: {
  readonly policy: Policy;
  readonly me: Me;
  readonly author: boolean;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const searchId = useId();
  const sectionId = useId();
  // Where focus goes when the control that was pressed leaves the page with the status it changed.
  const heading = useRef<HTMLHeadingElement>(null);
  const noticeTitle = useRef<HTMLHeadingElement>(null);
  const editable = author && isPolicyEditable(policy);
  // E-12: an edit returns a REJECTED or WITHDRAWN version to DRAFT (PRD SM-04).
  const reopenable = author && (policy.status === "REJECTED" || policy.status === "WITHDRAWN");
  // A settings version needs no effective date: it takes effect when it is approved (04 §16.5).
  const instant = INSTANT_CATEGORIES.has(policy.category);
  const approvalId = policy.pending_approval_request_id ?? policy.approval_request_id;
  const approval = useQuery({
    queryKey: queryKey("approvals", "tenant", { id: approvalId ?? "" }),
    queryFn: () => fetchApproval(approvalId ?? ""),
    enabled: approvalId !== null,
    retry: false,
  });
  const parameters = useParameters();
  const all = useQuery({ queryKey: allPoliciesKey(), queryFn: fetchAllPolicies });
  const published = currentPublished(all.data ?? [], policy);
  const open = openVersion(all.data ?? [], policy);
  // The way out of a version that came back (SCREENS §11.3 rev 1.56). The edit is refused once another
  // version of the scope was published since the submit (PRD ERR-92), and while another version of
  // the scope is open (PRD SM-04), which a new version is refused for as well. The page knows both
  // from the versions it lists: it offers no exit until they are read.
  let exit: "edit" | "superseded" | "blocked" | null = null;
  if (reopenable && all.data !== undefined) {
    if (open !== null) {
      exit = "blocked";
    } else {
      exit =
        published === null || published.id === policy.supersedes_version_id ? "edit" : "superseded";
    }
  }
  const rows = useMemo(
    () => parameterRows(parameters.data ?? [], policy, published),
    [parameters.data, policy, published],
  );
  const [filter, setFilter] = useState<ParameterFilter>({
    q: "",
    section: null,
    changedOnly: false,
  });
  const [draft, setDraft] = useState<Readonly<Record<string, string>>>({});
  // 04 SC-V `effective_from` is an instant; the field shows and edits its UTC date (DS-FMT-17).
  const initialEffective =
    policy.effective_from === null ? null : timestampDate(policy.effective_from);
  const [effectiveText, setEffectiveText] = useState(
    initialEffective === null ? "" : formatDate(initialEffective),
  );
  const [effective, setEffective] = useState<string | null>(initialEffective);
  // An edit refused for the effective date opens the field, so that the date goes with the next one.
  const [dateOpen, setDateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const dateEditable = editable || (exit === "edit" && dateOpen);
  useEffect(() => {
    if (dateOpen) {
      focusEffectiveFrom();
    }
  }, [dateOpen]);
  const invalidates = [policyKey(policy.id), EVERY_POLICY, queryKey("approvals", "tenant")];
  const save = useCommand<Policy>({ method: "PATCH", path: policyPath(policy.id), invalidates });
  const reopen = useCommand<Policy>({ method: "PATCH", path: policyPath(policy.id), invalidates });
  const runTests = useCommand({
    method: "POST",
    path: policyCommandPath(policy.id, "test"),
    invalidates,
  });
  const submitVersion = useCommand<Policy>({
    method: "POST",
    path: policyCommandPath(policy.id, "submit"),
    invalidates,
  });
  // The policy's own route withdraws the request and reopens the version in one transaction (04
  // §16.5): the answer is the DRAFT. `POST /approvals/{id}/withdraw` would leave it WITHDRAWN.
  const withdraw = useCommand<Policy>({
    method: "POST",
    path: policyCommandPath(policy.id, "withdraw"),
    invalidates,
  });
  // SCREENS §11.0 "Refused command" (rev 1.31): "Submit for approval", a save and the edit that
  // reopens check the effective date, so their message on it stands at the field; what no field shows
  // is listed in the banner of the command — the header's for a lifecycle command, the one above the
  // grid for a save.
  // A refusal of the edit is about the version that came back: once that version is a draft again
  // — through this edit or through another author's — it has nothing left to say.
  const reopenRefused = reopenable ? reopen.problem : null;
  const refusal = useLifecycleRefusal(
    submitVersion.problem ?? reopenRefused,
    runTests.problem ?? withdraw.problem,
  );
  // Refused all the same (PRD ERR-92, SM-04): when the versions have been read again the notice
  // stands in the refusal's place. It was not on the page when it loaded, so focus goes to its
  // sentence; the link follows it.
  const leadsOn = exit === "superseded" || exit === "blocked";
  const noticeAfterRefusal = leadsOn && reopenRefused !== null;
  useEffect(() => {
    if (noticeAfterRefusal) {
      noticeTitle.current?.focus();
    }
  }, [noticeAfterRefusal]);
  const saved = useLifecycleRefusal(save.problem, null);
  const submissions = useSubmissionOrder(submitVersion.reset);
  const failed = refusal.banner;
  const effectiveError = refusal.effective ?? saved.effective;
  const running = runTests.jobId !== null && !isTerminal(runTests.job);
  const visible = useMemo(() => filterRows(rows, filter), [rows, filter]);
  const sections = useMemo(() => sectionsOf(rows), [rows]);
  const dirtyValues = Object.keys(draft).length > 0;
  const dirtyEffective = effective !== initialEffective;
  const { steps, currentId } = policyLifecycle(policy, approval.data);
  const evidence = testEvidence(policy);
  const identity = { scope: scopeLabel(policy), version: String(policy.version_no) };

  const columns = useMemo(() => parameterColumns(editable, draft, setDraft), [editable, draft]);
  const source: GridSource<ParameterRow> = useMemo(
    () => ({
      queryKey: queryKey("registry-parameters", "public", {
        view: "version",
        id: policy.id,
        q: filter.q,
        section: filter.section,
        changed: filter.changedOnly,
        rows: visible.length,
        values: JSON.stringify(policy.values),
      }),
      fetchPage: () =>
        Promise.resolve({
          items: visible,
          nextCursor: null,
          total: { count: visible.length, capped: false },
        }),
    }),
    [visible, policy.id, policy.values, filter],
  );

  const saveValues = async () => {
    const values: Record<string, unknown> = { ...policy.values };
    const returned = new Set<string>();
    for (const [code, text] of Object.entries(draft)) {
      const row = rows.find((candidate) => candidate.parameter.code === code);
      if (row === undefined) {
        continue;
      }
      const parsed = parseLiteral(
        valueControl(row.parameter.value_schema),
        row.parameter.value_schema,
        text,
      );
      if (parsed === null) {
        // An emptied proposed value returns the key to the default. It leaves the stated values,
        // and where the published version holds the key — which a version keeps unless it says
        // otherwise (04 §16.5) — the request names it in `unset`.
        for (const key of Object.keys(values)) {
          if (key === code) {
            values[key] = undefined;
          }
        }
        if (row.currentLevel === "published") {
          returned.add(code);
        }
      } else {
        values[code] = parsed;
      }
    }
    const stated = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== undefined),
    );
    const body: PolicyUpdate = {
      values: stated,
      // `unset` replaces the stored list, so it carries the codes the draft already returns.
      ...(returned.size > 0
        ? {
            unset: [...new Set([...policy.unset, ...returned])]
              .filter((code) => !(code in stated))
              .sort(),
          }
        : {}),
      ...(dirtyEffective
        ? { effective_from: effective === null ? null : effectiveInstant(effective) }
        : {}),
    };
    const clearEarlier = submissions.changing();
    const outcome = await save.submit(body, { ifMatch: rowIfMatch(policy.row_version) });
    if (outcome.kind === "succeeded") {
      setDraft({});
      // What an earlier submission was refused for was about the version before this save.
      clearEarlier();
      toast.show({ tone: "positive", message: t("policies.accountingVersion.saved", identity) });
    } else if (outcome.kind === "failed" && refusesEffectiveDate(outcome.problem)) {
      focusEffectiveFrom();
    }
  };
  const doTests = async () => {
    const outcome = await runTests.submit({ run_simulation: true });
    if (outcome.kind === "accepted") {
      toast.show({ tone: "neutral", message: t("policies.accountingVersion.testsStarted") });
    } else if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.accountingVersion.testsCompleted") });
    }
  };
  const doSubmit = async () => {
    submissions.submitted();
    const outcome = await submitVersion.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.accountingVersion.submitted", identity),
      });
    } else if (outcome.kind === "failed" && refusesEffectiveDate(outcome.problem)) {
      focusEffectiveFrom();
    }
  };
  const doWithdraw = async () => {
    const outcome = await withdraw.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.accountingVersion.withdrawn", identity),
      });
      // "Withdraw" leaves the page with the status it ended.
      heading.current?.focus();
    }
  };
  const doEdit = async () => {
    // The `PATCH` that reopens names nothing. Once a refusal for the date has opened the field it
    // carries what the author chose there: a date, or none where the field was emptied. A text
    // that is no date is not sent as "no date" — the refusal of the stored date then stands — and
    // nothing typed while the field was not this edit's is sent at all.
    const chosen =
      dateOpen && dirtyEffective && (effective !== null || effectiveText.trim() === "");
    const body: PolicyUpdate = chosen
      ? { effective_from: effective === null ? null : effectiveInstant(effective) }
      : {};
    const outcome = await reopen.submit(body, { ifMatch: rowIfMatch(policy.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.accountingVersion.reopened", identity) });
      setDateOpen(false);
      // "Edit" leaves the page with the status it ended.
      heading.current?.focus();
    } else if (outcome.kind === "failed") {
      if (refusesEffectiveDate(outcome.problem)) {
        setDateOpen(true);
        focusEffectiveFrom();
      } else {
        // Refused all the same (PRD ERR-92): the versions this page listed are no longer the latest.
        await queryClient.invalidateQueries({ queryKey: EVERY_POLICY });
      }
    }
  };
  // The preparer of the pending request is the one "Withdraw" is offered to.
  const withdrawable =
    policy.status === "SUBMITTED" &&
    approvalId !== null &&
    approval.data?.preparer.id === me.user.id;
  const actions = author ? (
    <>
      {editable ? (
        <>
          <Button
            variant="secondary"
            onClick={() => void saveValues()}
            disabledReason={
              dirtyValues || dirtyEffective
                ? undefined
                : t("policies.templateVersion.outputs.noChanges")
            }
          >
            {t("policies.accountingVersion.saveValues")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => void doTests()}
            disabledReason={running ? t("policies.accountingVersion.testsRunning") : undefined}
          >
            {t("policies.accountingVersion.runTests")}
          </Button>
          <Button
            variant="primary"
            onClick={() => void doSubmit()}
            disabledReason={
              !instant && policy.effective_from === null && effective === null
                ? t("policies.version.effectiveRequired")
                : undefined
            }
          >
            {t("policies.accountingVersion.submit")}
          </Button>
        </>
      ) : null}
      {withdrawable ? (
        <Button variant="secondary" loading={withdraw.pending} onClick={() => void doWithdraw()}>
          {t("policies.version.withdraw")}
        </Button>
      ) : null}
      {exit === "edit" ? (
        <Button variant="primary" loading={reopen.pending} onClick={() => void doEdit()}>
          {t("policies.accountingVersion.edit")}
        </Button>
      ) : null}
    </>
  ) : undefined;
  const preset = presetLabel(policy.preset_code);
  // What the header says of a version its author cannot change as it is.
  let notice: ReactNode;
  if (exit === "blocked" && open !== null) {
    // PRD SM-04's sentence, as the API words the refusal, with the way to the version it names.
    notice = (
      <Banner
        tone="info"
        announce="static"
        titleRef={noticeTitle}
        title={t("policies.accountingVersion.versionOpen")}
        actions={
          <Link
            to={accountingVersionRoute(open.id)}
            className="text-body-sm font-medium text-accent-fg hover:underline"
          >
            {t("policies.accountingVersion.openVersion", { version: String(open.version_no) })}
          </Link>
        }
      />
    );
  } else if (exit === "edit") {
    notice = (
      <Banner
        tone="info"
        announce="static"
        title={t(
          policy.status === "REJECTED"
            ? "policies.accountingVersion.rejected"
            : "policies.accountingVersion.wasWithdrawn",
          { version: String(policy.version_no) },
        )}
      />
    );
  } else if (exit === "superseded" && published !== null) {
    const settings = SETTINGS_CATEGORIES.has(policy.category);
    notice = (
      <Banner
        tone="info"
        announce="static"
        titleRef={noticeTitle}
        title={t("policies.accountingVersion.basisSuperseded", {
          version: String(published.version_no),
        })}
        actions={
          settings ? (
            <Link
              to={SETTINGS_CATEGORY_ROUTES[policy.category] ?? "/settings"}
              className="text-body-sm font-medium text-accent-fg hover:underline"
            >
              {t("policies.accounting.openInSettings")}
            </Link>
          ) : (
            <Button variant="link" onClick={() => setCreating(true)}>
              {t("policies.accounting.new")}
            </Button>
          )
        }
      />
    );
  } else if (author && !editable && !reopenable) {
    // PRD ERR-09 on a policy version (rev 1.190): no control copies one, so the banner names the
    // control that does change values — "Withdraw" where this author is offered it, a new version
    // once the version is approved, published or superseded.
    let frozen = "policies.accountingVersion.frozen";
    if (policy.status === "SUBMITTED") {
      frozen = withdrawable
        ? "policies.accountingVersion.frozenPending"
        : "policies.accountingVersion.frozenPendingOther";
    }
    notice = <Banner tone="info" announce="static" title={t(frozen)} />;
  }
  // The notice that leads on says the refusal's own sentence, whole, and holds the way.
  const headerBanner =
    failed !== null && !leadsOn ? (
      <RefusalBanner problem={failed} placed={refusal.placed} />
    ) : (
      notice
    );

  return (
    <div
      data-testid="SF-13-accounting-version-page"
      // At least the height of the main region: the grid takes what the other blocks leave, and
      // below its floor of eight rows the page scrolls (SCREENS §11.3 rev 1.56).
      className="flex min-h-full w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <VersionNav policy={policy} />
      <RecordHeader
        title={`${categoryLabel(policy.category)} · ${scopeLabel(policy)}`}
        chips={
          <>
            <StatusChip status={chipFor("E-12", policy.status)?.status ?? policy.status} />
            <OutlineChip
              label={t("policies.version.number", { version: String(policy.version_no) })}
            />
            {policy.preset_code === null ? null : <OutlineChip label={preset} />}
          </>
        }
        actions={actions}
        banner={headerBanner}
        headingRef={heading}
      />
      <Stepper label={t("policies.lifecycle.label")} steps={steps} currentId={currentId} />
      {/* One row, as SCREENS §11.3 draws it; the help of the date stands under the row at full
          width — inside its 160 px field it wrapped to six lines and took the grid's room. */}
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
          <Field
            name={EFFECTIVE_FIELD}
            label={t("policies.accountingVersion.effectiveFrom")}
            error={effectiveError}
            width="date"
          >
            {(control) => {
              const described = {
                ...control,
                "aria-describedby": cn(control["aria-describedby"], EFFECTIVE_HELP_ID),
              };
              return dateEditable ? (
                <DateInput
                  control={described}
                  value={effectiveText}
                  onChange={(text) => {
                    // A blur echoes the date as it reads; only another text is an edit.
                    if (text !== effectiveText) {
                      refusal.effectiveEdited();
                      saved.effectiveEdited();
                    }
                    setEffectiveText(text);
                  }}
                  onValue={setEffective}
                  invalid={effectiveError !== null}
                />
              ) : (
                <output {...described} className="num block py-1.5 text-body-sm text-fg-1">
                  {formatDate(initialEffective)}
                </output>
              );
            }}
          </Field>
          <div className="w-72 max-w-full">
            <Field name={`search-${searchId}`} label={t("policies.accountingVersion.search")}>
              {(control) => (
                <input
                  {...control}
                  type="search"
                  value={filter.q}
                  onChange={(event) => setFilter({ ...filter, q: event.target.value })}
                  className={controlClass(false)}
                />
              )}
            </Field>
          </div>
          <div className="w-64 max-w-full">
            <Field name={`section-${sectionId}`} label={t("policies.accountingVersion.section")}>
              {(control) => (
                <Select<string>
                  control={control}
                  options={[
                    { value: "", label: t("policies.accountingVersion.allSections") },
                    ...sections.map((section) => ({ value: section, label: section })),
                  ]}
                  value={filter.section ?? ""}
                  onChange={(value) =>
                    setFilter({ ...filter, section: value === "" ? null : value })
                  }
                />
              )}
            </Field>
          </div>
          {/* The switch has no label above it: an empty label line puts it on the line of the
              controls, whatever a field beside it shows under its own control. */}
          <div className="flex flex-col gap-1">
            <span aria-hidden="true" className="text-body-sm">
              {"\u00a0"}
            </span>
            <div className="flex h-[var(--control-h)] items-center">
              <Switch
                label={t("policies.accountingVersion.changedOnly")}
                checked={filter.changedOnly}
                onChange={(checked) => setFilter({ ...filter, changedOnly: checked })}
              />
            </div>
          </div>
        </div>
        <p id={EFFECTIVE_HELP_ID} className="text-body-sm text-fg-3">
          {t(effectiveHelpKey(instant, dateEditable))}
        </p>
      </div>
      <RefusalBanner problem={saved.banner} placed={saved.placed} />
      {/* A floor of eight rows — the grid's bar, its header row, 8 x 36 px and the room a
          horizontal scrollbar takes where it takes any — stated as the minimum: left to its content
          the block would be as tall as the grid's own limit. */}
      <div className="flex min-h-100 shrink-0 grow basis-0 flex-col">
        {parameters.isError || all.isError ? (
          <Banner tone="negative" title={t("policies.accountingVersion.loadError")} />
        ) : parameters.data === undefined || all.data === undefined ? (
          <Skeleton region={t("policies.accountingVersion.grid")} shape="rows" count={8} />
        ) : (
          <DataGrid<ParameterRow>
            name="parameters"
            title={t("policies.accountingVersion.grid")}
            errorTitle={t("policies.accountingVersion.loadError")}
            countLabel={(value, formatted) =>
              t("policies.accountingVersion.count", { count: value, formatted })
            }
            columns={columns}
            source={source}
            rowKey={(row) => row.parameter.code}
            rowLabel={(row) => row.parameter.code}
            testIdPrefix="SF-13"
            rowTestKey={(row) => row.parameter.code}
            emptyState={
              <EmptyState
                title={t("policies.accountingVersion.empty.title")}
                description={t("policies.accountingVersion.empty.description")}
              />
            }
            noResults={
              <EmptyState
                title={t("policies.accountingVersion.empty.title")}
                description={t("policies.accountingVersion.empty.description")}
              />
            }
          />
        )}
      </div>
      <section
        aria-label={t("policies.panes.simulation")}
        data-testid="SF-13-pane-simulation"
        className="flex flex-col gap-1"
      >
        <h2 className="text-body-sm font-medium text-fg-1">{t("policies.panes.simulation")}</h2>
        <p className="text-body-sm text-fg-1">
          {evidence === null
            ? t("policies.accountingVersion.results.noTests")
            : t("policies.accountingVersion.results.cases", {
                passed: formatNumber(evidence.passed, { kind: "count" }),
                total: formatNumber(evidence.total, { kind: "count" }),
              })}
        </p>
        <p className="text-body-sm text-fg-2">
          {policy.impact_simulation === null
            ? t("policies.simulation.none")
            : policy.impact_simulation.summary.contracts_affected === 0
              ? t("policies.simulation.noContracts")
              : t("policies.accountingVersion.results.affected", {
                  formatted: formatNumber(policy.impact_simulation.summary.contracts_affected, {
                    kind: "count",
                  }),
                })}
        </p>
      </section>
      {creating ? (
        <NewVersionDrawer
          initial={{
            category: policy.category,
            scope: policy.scope,
            entityCode: policy.entity_code,
            book: policy.book,
          }}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </div>
  );
}

/**
 * The help of "Effective from" (SCREENS §11.3). A settings version needs no date; where the field
 * cannot be edited its help says when the version takes effect and gives no instruction.
 */
function effectiveHelpKey(instant: boolean, editable: boolean): string {
  if (!instant) {
    return "policies.accountingVersion.effectiveHelp";
  }
  return editable
    ? "policies.accountingVersion.effectiveHelpInstant"
    : "policies.accountingVersion.effectiveHelpInstantReadOnly";
}

/**
 * The Key cell: the key shortens as every literal of the grid does (`mono`), and the "Changed" chip
 * beside it stays whole (SCREENS §11.3 rev 1.56).
 */
function keyCell(row: ParameterRow): ReactNode {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {mono(row.parameter.code)}
      {row.changed ? (
        <span className="shrink-0">
          <OutlineChip label={t("policies.accountingVersion.changed")} />
        </span>
      ) : null}
    </span>
  );
}

/** SCREENS §11.3 parameter grid columns; the Proposed value cell edits the draft while editable. */
export function parameterColumns(
  editable: boolean,
  draft: Readonly<Record<string, string>>,
  onDraft: (next: Readonly<Record<string, string>>) => void,
): readonly GridColumn<ParameterRow>[] {
  return [
    {
      id: "pol_id",
      header: t("policies.accountingVersion.column.pol"),
      kind: "identifier",
      value: (row) => row.parameter.pol_id ?? row.parameter.code,
      render: (row) => mono(row.parameter.pol_id ?? ""),
      width: 96,
    },
    {
      id: "code",
      header: t("policies.accountingVersion.column.key"),
      kind: "text",
      value: (row) => row.parameter.code,
      render: keyCell,
      width: 240,
    },
    {
      id: "description",
      header: t("policies.accountingVersion.column.question"),
      kind: "text",
      value: (row) => row.parameter.description,
      width: 320,
    },
    {
      id: "current",
      header: t("policies.accountingVersion.column.current"),
      kind: "text",
      value: (row) => formatLiteral(row.current),
      render: (row) =>
        levelled(
          formatLiteral(row.current),
          t(
            row.currentLevel === "published"
              ? "policies.accountingVersion.level.tenant"
              : "policies.accountingVersion.level.default",
          ),
        ),
      width: 200,
    },
    {
      id: "proposed",
      header: t("policies.accountingVersion.column.proposed"),
      kind: "text",
      value: (row) => draft[row.parameter.code] ?? formatLiteral(proposedValue(row)),
      render: (row) => (
        <ProposedCell row={row} editable={editable} draft={draft} onDraft={onDraft} />
      ),
      width: 220,
    },
    {
      id: "default_asc606",
      header: t("policies.accountingVersion.column.asc606"),
      kind: "text",
      value: (row) => formatLiteral(row.parameter.default_asc606),
      render: (row) => mono(formatLiteral(row.parameter.default_asc606)),
      width: 144,
    },
    {
      id: "default_ifrs15",
      header: t("policies.accountingVersion.column.ifrs15"),
      kind: "text",
      value: (row) => formatLiteral(row.parameter.default_ifrs15),
      render: (row) => mono(formatLiteral(row.parameter.default_ifrs15)),
      width: 144,
    },
    {
      id: "legacy_parity_value",
      header: t("policies.accountingVersion.column.parity"),
      kind: "text",
      value: (row) =>
        row.parameter.legacy_parity_value === null
          ? t("policies.accountingVersion.notApplicable")
          : formatLiteral(row.parameter.legacy_parity_value),
      render: (row) =>
        row.parameter.legacy_parity_value === null
          ? t("policies.accountingVersion.notApplicable")
          : mono(formatLiteral(row.parameter.legacy_parity_value)),
      width: 144,
    },
    {
      id: "allowed_levels",
      header: t("policies.accountingVersion.column.levels"),
      kind: "text",
      value: (row) =>
        row.parameter.allowed_levels
          .map((level) => t(`policies.accounting.scope.${level}`))
          .join(", "),
      width: 200,
    },
    {
      id: "pin",
      header: t("policies.accountingVersion.column.pin"),
      kind: "text",
      value: (row) => t(`policies.accountingVersion.pin.${row.parameter.pin}`),
      width: 144,
    },
    {
      id: "approval_code",
      header: t("policies.accountingVersion.column.approval"),
      kind: "text",
      value: (row) => t(`policies.accountingVersion.approvalCode.${row.parameter.approval_code}`),
      width: 128,
    },
    {
      id: "source_ref",
      header: t("policies.accountingVersion.column.source"),
      kind: "text",
      value: (row) => row.parameter.source_ref,
      render: (row) => mono(row.parameter.source_ref),
      width: 160,
    },
  ];
}

function ProposedCell({
  row,
  editable,
  draft,
  onDraft,
}: {
  readonly row: ParameterRow;
  readonly editable: boolean;
  readonly draft: Readonly<Record<string, string>>;
  readonly onDraft: (next: Readonly<Record<string, string>>) => void;
}) {
  const code = row.parameter.code;
  const shown = draft[code] ?? formatLiteral(proposedValue(row));
  if (row.forced) {
    return (
      <span className="flex min-w-0 items-center gap-2">
        <LockSimple
          role="img"
          aria-label={t("policies.accountingVersion.forced")}
          className="shrink-0 text-fg-3"
        />
        {mono(shown)}
      </span>
    );
  }
  if (!editable) {
    // A key the version returns to the default reads its default, named as the Current column
    // names a level.
    return row.returned
      ? levelled(shown, t("policies.accountingVersion.level.default"))
      : mono(shown);
  }
  const control = valueControl(row.parameter.value_schema);
  const label = t("policies.accountingVersion.proposedOf", { key: code });
  const set = (text: string) => onDraft({ ...draft, [code]: text });
  if (control.kind === "enum" || control.kind === "boolean") {
    return (
      <select
        aria-label={label}
        value={shown}
        onChange={(event) => set(event.target.value)}
        className={`${controlClass(false)} truncate font-mono`}
      >
        {control.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      type="text"
      aria-label={label}
      value={shown}
      inputMode={control.kind === "number" ? "decimal" : undefined}
      onChange={(event) => set(event.target.value)}
      className={`${controlClass(false)} truncate font-mono`}
    />
  );
}

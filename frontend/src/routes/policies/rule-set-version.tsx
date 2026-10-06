// SF-13:rule-set-version Rule set version, the decision-table editor (SCREENS §11.0 lifecycle pattern;
// §11.1 "Decision-table editor", rules grid, rule drawer, lint copy, test cases, simulation, "Try a line",
// states, sample world and test hooks; §0.4 RT-62; §0.5 SCR-URL-13 `pane`, `drawer`, `row`; §0.7
// SCR-ST-01 to SCR-ST-09, SCR-PERM-01 to SCR-PERM-03; DESIGN_SYSTEM DS-CMP-06, DS-CMP-07, DS-CMP-09,
// DS-CMP-10, DS-CMP-11, DS-CMP-16, DS-CMP-18, DS-CMP-19, DS-CMP-20, DS-CMP-29; 04 API-R-25, API-R-57, API-R-09
// `POST /approvals/{id}/withdraw`; BUILD_SPEC RFD-22).
//
// Breadcrumb "Policies / <tab label> / <code>", the Policies route tabs, the record header (rule set
// name, code, status, version and kind chips, the §11.0 commands for `config.author`), the lifecycle
// stepper "Draft · Tested · Approval · Published", the version details, and panel tabs Rules, Test cases,
// Lint, Simulation and Changes. Rules, example cases and the effective date change only while the version
// is DRAFT or TESTED (DB-04); outside those states the grid shows no edit actions. The approval executes
// publication, so no Publish button renders (D-76).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type {
  EditOutcome,
  GridColumn,
  GridColumnState,
  GridSource,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field, fieldId, fieldLabelId } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Money } from "../../components/money/Money";
import { RecordHeader } from "../../components/record/RecordHeader";
import { type Step, Stepper } from "../../components/record/Stepper";
import { withPane } from "../../components/record/pane-params";
import { PanelTabs, type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { type CommandKeys, useCommand, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem, fieldErrorsOf, readProblem } from "../../lib/api/problems";
import {
  type Approval,
  APPROVAL_PERMISSIONS,
  APPROVALS_PATH,
  currencyRegistered,
  fetchApproval,
  FILE_CONTENT_PATH,
} from "../../lib/api/queries/approvals";
import {
  caseResultWord,
  CONFIG_TEST_CASES_PATH,
  type ConfigTestCase,
  configTestCasesKey,
  fetchConfigTestCasesPage,
  jsonSummary,
  parseJsonObject,
} from "../../lib/api/queries/config-test-cases";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  asCondition,
  compareRules,
  CONFIG_AUTHOR_PERMISSION,
  CONFIG_READ_PERMISSION,
  conditionSummary,
  conditionValueText,
  EVERY_RULE_SET,
  fetchAllRules,
  fetchRuleSet,
  fetchRulesPage,
  fetchRuleSetVersion,
  fetchSspBookCodes,
  fetchTemplateCodes,
  fieldLabel,
  isBooleanField,
  isEditableStatus,
  LIST_FIELDS,
  lintMessage,
  operatorLabel,
  outputSummary,
  parseConditionValue,
  REVENUE_KINDS,
  type Rule,
  RULE_FIELDS,
  RULE_OPERATORS,
  RULE_SETS_PATH,
  type RuleChange,
  type RuleOperator,
  type RuleSet,
  type RuleSetEvaluation,
  type RuleSetKind,
  ruleSetKey,
  ruleSetKindLabel,
  type RuleSetVersion,
  ruleSetVersionKey,
  ruleSetVersionPath,
  ruleSetVersionRoute,
  routingSteps,
  rulesKey,
} from "../../lib/api/queries/rule-sets";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { formatDate, formatNumber, NO_VALUE, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { POLICY_TABS } from "./revenue";
import {
  approverNames,
  effectiveCaption,
  focusEffectiveFrom,
  refusesEffectiveDate,
  ruleSetForm,
  useLifecycleRefusal,
  useSubmissionOrder,
  VersionMeta,
} from "./version-meta";

/** SCREENS §11.1 panel tabs, `pane=rules|tests|lint|simulation|changes`; the default omits `pane`. */
export const PANES = ["rules", "tests", "lint", "simulation", "changes"] as const;
export type Pane = (typeof PANES)[number];

export const DRAWER_RULE = "rule";
export const DRAWER_NEW_RULE = "new-rule";
export const DRAWER_NEW_TEST_CASE = "new-test-case";
export const DRAWER_TRY_LINE = "try-line";

/** 04 API-C-13: the problem of a command on a version that is no longer DRAFT or TESTED (ERR-09). */
export const FROZEN_SLUG = "configuration-frozen";

export function paneOf(value: string | null): Pane {
  return PANES.find((pane) => pane === value) ?? "rules";
}

/** SCREENS §11.0 lifecycle stepper for rule sets: "Draft · Tested · Approval · Published". */
export function lifecycleSteps(
  version: RuleSetVersion,
  approval: Approval | undefined,
): { readonly steps: readonly Step[]; readonly currentId: string } {
  const evidence = version.test_evidence;
  const approvers = approverNames(approval);
  const decided =
    version.status === "APPROVED" ||
    version.status === "PUBLISHED" ||
    version.status === "SUPERSEDED";
  let approvalCaption: string | undefined;
  if (version.status === "SUBMITTED") {
    approvalCaption = t("policies.lifecycle.pending");
  } else if (decided && approvers.length > 0) {
    approvalCaption = t("policies.lifecycle.approvedBy", { name: approvers.join(", ") });
  } else if (version.status === "REJECTED") {
    approvalCaption = t("policies.lifecycle.rejected");
  } else if (version.status === "WITHDRAWN") {
    approvalCaption = t("policies.lifecycle.withdrawn");
  }
  const order: Readonly<Record<RuleSetVersion["status"], number>> = {
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
  const reached = order[version.status];
  const state = (index: number): Step["state"] => {
    if (index < reached) {
      return "complete";
    }
    if (index === reached) {
      if (version.status === "REJECTED") {
        return "error";
      }
      if (version.status === "WITHDRAWN") {
        return "skipped";
      }
      return "current";
    }
    return index === 3 && reached === 4 ? "complete" : "pending";
  };
  const steps: Step[] = [
    {
      id: "draft",
      label: t("policies.lifecycle.draft"),
      state: state(0),
      caption: t("policies.lifecycle.edited", {
        date: formatDate(timestampDate(version.updated_at)),
      }),
    },
    {
      id: "tested",
      label: t("policies.lifecycle.tested"),
      state: state(1),
      caption:
        evidence.total === 0
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
      caption: effectiveCaption(version, ruleSetForm(version.kind)),
    },
  ];
  const currentId = (["draft", "tested", "approval", "published"] as const)[Math.min(reached, 3)];
  return { steps, currentId: currentId ?? "draft" };
}

export function RuleSetVersionEditor() {
  const { ruleSetId = "", versionId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const navigate = useNavigate();
  const read = access.holdsAnywhere(CONFIG_READ_PERMISSION);
  const version = useQuery({
    queryKey: ruleSetVersionKey(versionId),
    queryFn: () => fetchRuleSetVersion(versionId),
    enabled: read,
  });
  const ruleSet = useQuery({
    queryKey: ruleSetKey(ruleSetId),
    queryFn: () => fetchRuleSet(ruleSetId),
    enabled: read,
  });
  const region = t("policies.version.region");

  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  if (!read) {
    return (
      <EmptyState
        title={t("settings.access.title", { area: t("policies.title") })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  }
  const failure = version.error ?? ruleSet.error;
  const notFound = (
    <EmptyState
      title={t("policies.version.notFound.title")}
      description={t("policies.version.notFound.description")}
      action={{
        label: t("policies.version.notFound.action"),
        onAction: () => void navigate("/policies"),
      }}
    />
  );
  if (failure !== null) {
    if (failure instanceof ApiProblem && failure.status === 404) {
      return notFound;
    }
    return (
      <Banner
        tone="negative"
        title={t("policies.version.loadError")}
        headingLevel={2}
        actions={
          <Button
            variant="link"
            onClick={() => {
              void version.refetch();
              void ruleSet.refetch();
            }}
          >
            {t("policies.retry")}
          </Button>
        }
      >
        {problemText(failure)}
      </Banner>
    );
  }
  if (version.data === undefined || ruleSet.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  if (version.data.rule_set_id !== ruleSet.data.id) {
    return notFound;
  }
  return (
    <VersionView
      key={version.data.id}
      ruleSet={ruleSet.data}
      version={version.data}
      me={me.data}
      author={access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION)}
    />
  );
}

/** SCREENS §0.7 SCR-ST-05 message: the problem title, then "Reference <request id>." (CPY-05). */
function problemText(error: unknown): string {
  if (error instanceof ApiProblem) {
    return error.requestId === null
      ? error.title
      : `${error.title} ${t("approvals.reference", { reference: error.requestId })}`;
  }
  return error instanceof Error ? error.message : String(error);
}

function tabKeyOf(kind: RuleSetKind): string {
  return REVENUE_KINDS.includes(kind) ? "revenue" : "controlRules";
}

function VersionNav({ ruleSet }: { readonly ruleSet: RuleSet }) {
  const built = useBuiltPaths();
  const access = useAccess();
  const location = useLocation();
  const tabKey = tabKeyOf(ruleSet.kind);
  const home = POLICY_TABS.find((tab) => tab.key === tabKey);
  const tabs: RouteTab[] = POLICY_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`policies.tabs.${tab.key}`),
    // SCREENS §11.1 wireframe: the tab of the rule set's list stays current on its version pages.
    to: tab.key === tabKey ? `${location.pathname}${location.search}` : tab.path,
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
          {home === undefined || !built.has(home.path) ? null : (
            <li className="flex items-center gap-1.5">
              <Link to={home.path} className="hover:text-fg-1 hover:underline">
                {t(`policies.tabs.${home.key}`)}
              </Link>
              <span aria-hidden="true">/</span>
            </li>
          )}
          <li aria-current="page" className="font-mono text-mono-sm">
            {ruleSet.code}
          </li>
        </ol>
      </nav>
      {tabs.length === 0 ? null : <RouteTabs label={t("policies.tabs.label")} tabs={tabs} />}
    </div>
  );
}

interface VersionViewProps {
  readonly ruleSet: RuleSet;
  readonly version: RuleSetVersion;
  readonly me: Me;
  readonly author: boolean;
}

function versionQueries(version: RuleSetVersion, ruleSet: RuleSet): readonly QueryKey[] {
  return [
    queryKey("rule-set-versions", "tenant", { id: version.id }),
    ruleSetKey(ruleSet.id),
    EVERY_RULE_SET,
    configTestCasesKey("rule_set_version", version.id),
    queryKey("approvals", "tenant"),
  ];
}

function VersionView({ ruleSet, version, me, author }: VersionViewProps) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const pane = paneOf(params.get("pane"));
  const drawer = params.get("drawer");
  const row = params.get("row");
  const editable = author && isEditableStatus(version.status);
  const approvalId = version.pending_approval_request_id ?? version.approval_request_id;
  const approval = useQuery({
    queryKey: queryKey("approvals", "tenant", { id: approvalId ?? "" }),
    queryFn: () => fetchApproval(approvalId ?? ""),
    enabled: approvalId !== null,
    retry: false,
  });
  const rules = useQuery({
    queryKey: rulesKey(version.id),
    queryFn: () => fetchAllRules(version.id),
  });
  const invalidates = versionQueries(version, ruleSet);
  const versionPath = ruleSetVersionPath(version.id);
  const lint = useCommand<RuleSetVersion>({
    method: "POST",
    path: `${versionPath}/lint`,
    invalidates,
  });
  const runTests = useCommand<RuleSetVersion>({
    method: "POST",
    path: `${versionPath}/test`,
    invalidates,
  });
  const submitVersion = useCommand<RuleSetVersion>({
    method: "POST",
    path: `${versionPath}/submit`,
    invalidates,
  });
  const withdraw = useCommand({
    method: "POST",
    path: `${APPROVALS_PATH}/${approvalId ?? ""}/withdraw`,
    invalidates,
  });
  const newDraft = useCommand<RuleSetVersion>({
    method: "POST",
    path: `${RULE_SETS_PATH}/${ruleSet.id}/versions`,
    invalidates: [EVERY_RULE_SET, ruleSetKey(ruleSet.id)],
  });
  // SCREENS §11.0 "Refused command" (rev 1.31): "Submit for approval" checks the effective date.
  const form = ruleSetForm(ruleSet.kind);
  const supersedes = ruleSet.current_version !== null && ruleSet.current_version.id !== version.id;
  const refusal = useLifecycleRefusal(
    submitVersion.problem,
    [lint, runTests, withdraw, newDraft].find((command) => command.problem !== null)?.problem ??
      null,
  );
  const submissions = useSubmissionOrder(submitVersion.reset);
  const failed = refusal.banner;
  const lintFailed = version.lint_result?.status === "FAIL";
  const authoredByViewer = approval.data !== undefined && approval.data.preparer.id === me.user.id;
  const kindLabel = ruleSetKindLabel(ruleSet.kind);
  const identity = { code: ruleSet.code, version: version.version_no };

  const setPane = (next: string) => {
    setParams(
      (current) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const copy = withPane(current, next === "rules" ? null : next);
        copy.delete("drawer");
        copy.delete("row");
        return copy;
      },
      { replace: true },
    );
  };
  const openDrawer = (name: string, id: string | null = null) => {
    setParams((current) => {
      const copy = new URLSearchParams(current);
      copy.set("drawer", name);
      if (id === null) {
        copy.delete("row");
      } else {
        copy.set("row", id);
      }
      return copy;
    });
  };
  const closeDrawer = () => {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        copy.delete("drawer");
        copy.delete("row");
        return copy;
      },
      { replace: true },
    );
  };

  const doLint = async () => {
    const outcome = await lint.submit({});
    if (outcome.kind === "succeeded") {
      setPane("lint");
    }
  };
  const doTests = async () => {
    const clearEarlier = submissions.changing();
    const outcome = await runTests.submit({});
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      const evidence = outcome.data.test_evidence;
      const message = t("policies.tests.completed", {
        passed: formatNumber(evidence.passed, { kind: "count" }),
        total: formatNumber(evidence.total, { kind: "count" }),
      });
      announce(message, "polite");
      toast.show({ tone: evidence.failed > 0 ? "warning" : "positive", message });
      // What an earlier submission was refused for was about the content before this run.
      clearEarlier();
    }
  };
  const doSubmit = async () => {
    submissions.submitted();
    const outcome = await submitVersion.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.version.submitted", identity) });
    } else if (outcome.kind === "failed" && refusesEffectiveDate(outcome.problem)) {
      focusEffectiveFrom();
    }
  };
  const doWithdraw = async () => {
    const outcome = await withdraw.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.version.withdrawn", identity) });
    }
  };
  const doNewDraft = async () => {
    const outcome = await newDraft.submit({ source_version_id: version.id });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("policies.version.draftCreated", {
          code: ruleSet.code,
          version: outcome.data.version_no,
        }),
      });
      void navigate(ruleSetVersionRoute(ruleSet.id, outcome.data.id));
    }
  };

  let actions: ReactNode = null;
  if (author) {
    switch (version.status) {
      case "DRAFT":
        actions = (
          <>
            <Button variant="secondary" loading={lint.pending} onClick={() => void doLint()}>
              {t("policies.version.runLint")}
            </Button>
            <Button variant="primary" loading={runTests.pending} onClick={() => void doTests()}>
              {t("policies.version.runTests")}
            </Button>
          </>
        );
        break;
      case "TESTED":
        actions = (
          <>
            <Button variant="secondary" loading={runTests.pending} onClick={() => void doTests()}>
              {t("policies.version.runTests")}
            </Button>
            {lintFailed ? null : (
              <Button
                variant="primary"
                loading={submitVersion.pending}
                disabledReason={
                  // A version read at an instant may go without a date: it takes effect on approval.
                  form === "date" && version.effective_from === null
                    ? t("policies.version.effectiveRequired")
                    : undefined
                }
                onClick={() => void doSubmit()}
              >
                {t("policies.version.submit")}
              </Button>
            )}
          </>
        );
        break;
      case "SUBMITTED":
        actions = authoredByViewer ? (
          <Button variant="secondary" loading={withdraw.pending} onClick={() => void doWithdraw()}>
            {t("policies.version.withdraw")}
          </Button>
        ) : null;
        break;
      default:
        actions = (
          <Button variant="primary" loading={newDraft.pending} onClick={() => void doNewDraft()}>
            {t("policies.version.newDraft")}
          </Button>
        );
    }
  }

  const statusSpec = chipFor("E-12", version.status);
  const lifecycle = lifecycleSteps(version, approval.data);
  const banners: ReactNode[] = [];
  if (version.status === "SUBMITTED" && authoredByViewer) {
    banners.push(<Banner key="author" tone="info" title={t("policies.version.authorNotice")} />);
  }
  if (failed !== null) {
    banners.push(
      failed.slug === FROZEN_SLUG ? (
        <Banner key="frozen" tone="warning" announce="live" title={t("policies.version.frozen")} />
      ) : (
        <RefusalBanner key="problem" problem={failed} placed={refusal.placed} />
      ),
    );
  }
  const evidence = version.test_evidence;
  const tabs = [
    { id: "rules", label: t("policies.panes.rules"), count: version.rule_count },
    { id: "tests", label: t("policies.panes.tests"), count: evidence.total },
    {
      id: "lint",
      label: t("policies.panes.lint"),
      blockerLabel: lintFailed ? t("policies.lint.blocker") : undefined,
    },
    { id: "simulation", label: t("policies.panes.simulation") },
    { id: "changes", label: t("policies.panes.changes") },
  ];
  const allRules = rules.data ?? [];

  let panel: ReactNode;
  switch (pane) {
    case "rules":
      panel = (
        <RulesPane
          ruleSet={ruleSet}
          version={version}
          editable={editable}
          rules={allRules}
          onOpen={openDrawer}
        />
      );
      break;
    case "tests":
      panel = <TestCasesPane version={version} editable={editable} onOpen={openDrawer} />;
      break;
    case "lint":
      panel = <LintPane version={version} rules={allRules} />;
      break;
    case "simulation":
      panel = <SimulationPane version={version} />;
      break;
    case "changes":
      panel = <ChangesPane ruleSet={ruleSet} version={version} rules={rules.data} />;
      break;
  }

  const selectedRule = row === null ? undefined : allRules.find((rule) => rule.id === row);

  return (
    <div className="flex w-full flex-col gap-4">
      <VersionNav ruleSet={ruleSet} />
      <RecordHeader
        title={ruleSet.name}
        identifier={{
          value: ruleSet.code,
          copyLabel: t("policies.version.copyCode"),
          copiedMessage: t("policies.version.copied", { code: ruleSet.code }),
        }}
        chips={
          <>
            {statusSpec === null ? null : <StatusChip status={statusSpec.status} />}
            <OutlineChip label={t("policies.version.number", { version: version.version_no })} />
            <OutlineChip label={kindLabel} />
          </>
        }
        actions={
          <>
            {runTests.pending ? (
              <span role="status" className="text-body-sm text-fg-2">
                {t("policies.tests.running", {
                  count: evidence.total,
                  formatted: formatNumber(evidence.total, { kind: "count" }),
                })}
              </span>
            ) : null}
            {actions}
          </>
        }
        banner={
          banners.length === 0 ? undefined : <div className="flex flex-col gap-2">{banners}</div>
        }
        tracker={
          <Stepper
            label={t("policies.lifecycle.label")}
            steps={lifecycle.steps}
            currentId={lifecycle.currentId}
          />
        }
      />
      <VersionMeta
        // A new version row is a new form: its fields show what is stored.
        key={version.id}
        version={version}
        path={versionPath}
        form={form}
        supersedes={supersedes}
        required={form === "date"}
        approval={approval.data}
        editable={editable}
        invalidates={invalidates}
        refusal={refusal.effective}
        onEdited={refusal.effectiveEdited}
        onSave={submissions.changing}
        className="px-[var(--gutter)]"
      />
      <PanelTabs label={t("policies.panes.label")} tabs={tabs} selectedId={pane} onChange={setPane}>
        {panel}
      </PanelTabs>
      {drawer === DRAWER_RULE && selectedRule !== undefined ? (
        <RuleDrawer
          key={`${selectedRule.id}:${String(editable)}`}
          kind={ruleSet.kind}
          version={version}
          rule={selectedRule}
          source={null}
          editable={editable}
          invalidates={invalidates}
          onClose={closeDrawer}
        />
      ) : null}
      {drawer === DRAWER_NEW_RULE && editable ? (
        <RuleDrawer
          key={`new:${row ?? ""}`}
          kind={ruleSet.kind}
          version={version}
          rule={null}
          source={selectedRule ?? null}
          editable
          invalidates={invalidates}
          onClose={closeDrawer}
        />
      ) : null}
      {drawer === DRAWER_NEW_TEST_CASE && editable ? (
        <TestCaseDrawer version={version} invalidates={invalidates} onClose={closeDrawer} />
      ) : null}
      {drawer === DRAWER_TRY_LINE && RULE_FIELDS[ruleSet.kind].length > 0 ? (
        <TryLineDrawer ruleSet={ruleSet} version={version} onClose={closeDrawer} />
      ) : null}
    </div>
  );
}

/**
 * One upsert of a rule from a grid cell, under the key `keys` holds for that body (DG-FE-05 rev
 * 1.156). A save that got no answer is an outcome: the cell says so, and the same value saved again
 * carries the same key.
 */
async function saveRuleCell(
  keys: CommandKeys,
  versionId: string,
  rule: Rule,
  changes: { readonly priority?: number; readonly description?: string | null },
): Promise<EditOutcome> {
  let response: Response;
  try {
    response = await keys.send("POST", `${ruleSetVersionPath(versionId)}/rules`, {
      body: {
        rule_key: rule.rule_key,
        priority: rule.priority,
        conditions: rule.conditions,
        outputs: rule.outputs,
        description: rule.description,
        ...changes,
      },
    });
  } catch {
    return { ok: false, message: t("common.command.noAnswer") };
  }
  if (response.ok) {
    return { ok: true };
  }
  const problem = await readProblem(response);
  const [first] = Object.values(fieldErrorsOf(problem));
  return { ok: false, message: first ?? problem.detail ?? problem.title };
}

interface RulesPaneProps {
  readonly ruleSet: RuleSet;
  readonly version: RuleSetVersion;
  readonly editable: boolean;
  readonly rules: readonly Rule[];
  readonly onOpen: (drawer: string, id?: string | null) => void;
}

function RulesPane({ ruleSet, version, editable, rules, onOpen }: RulesPaneProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const keys = useCommandKeys();
  const [removing, setRemoving] = useState<Rule | null>(null);
  const invalidates = versionQueries(version, ruleSet);
  const remove = useCommand({
    method: "DELETE",
    path: `${ruleSetVersionPath(version.id)}/rules/${removing?.id ?? ""}`,
    invalidates,
  });
  const refresh = async () => {
    await Promise.all(invalidates.map((key) => queryClient.invalidateQueries({ queryKey: key })));
  };
  const source: GridSource<Rule> = {
    queryKey: queryKey("rule-set-versions", "tenant", { id: version.id, view: "rules-grid" }),
    fetchPage: (cursor, sort) => fetchRulesPage(version.id, cursor, sort),
  };
  const byId = new Map(rules.map((rule) => [rule.id, rule]));
  const tryable = RULE_FIELDS[ruleSet.kind].length > 0;

  // API-C-09 sort keys: GET /api/v1/rule-set-versions/{version_id}/rules
  const columns: readonly GridColumn<Rule>[] = [
    {
      id: "priority",
      header: t("policies.rules.column.priority"),
      kind: "number",
      numberKind: "count",
      value: (rule) => String(rule.priority),
      sortKey: "priority",
      width: 104,
      edit: editable
        ? {
            kind: "text",
            save: async (rule, typed) => {
              if (!/^-?[0-9]+$/.test(typed.trim())) {
                return { ok: false, message: t("policies.rules.priorityInvalid") };
              }
              const outcome = await saveRuleCell(keys, version.id, rule, {
                priority: Number(typed.trim()),
              });
              if (outcome.ok) {
                await refresh();
              }
              return outcome;
            },
          }
        : undefined,
    },
    {
      id: "rule_key",
      header: t("policies.rules.column.key"),
      kind: "identifier",
      value: (rule) => rule.rule_key,
      href: (rule) => `?drawer=${DRAWER_RULE}&row=${rule.id}`,
      sortKey: "rule_key",
      width: 176,
    },
    {
      id: "conditions",
      header: t("policies.rules.column.conditions"),
      kind: "text",
      value: (rule) => conditionSummary(rule.conditions),
      width: 360,
    },
    {
      id: "outputs",
      header: t("policies.rules.column.outputs"),
      kind: "text",
      value: (rule) => outputSummary(ruleSet.kind, rule.outputs),
      width: 280,
    },
    {
      id: "specificity",
      header: t("policies.rules.column.specificity"),
      kind: "number",
      numberKind: "count",
      value: (rule) => String(rule.specificity),
      render: (rule) => (
        <span className="num text-fg-2">{formatNumber(rule.specificity, { kind: "count" })}</span>
      ),
      width: 112,
    },
    {
      id: "description",
      header: t("policies.rules.column.description"),
      kind: "text",
      value: (rule) => rule.description ?? null,
      width: 320,
      edit: editable
        ? {
            kind: "text",
            save: async (rule, typed) => {
              const outcome = await saveRuleCell(keys, version.id, rule, {
                description: typed.trim() === "" ? null : typed.trim(),
              });
              if (outcome.ok) {
                await refresh();
              }
              return outcome;
            },
          }
        : undefined,
    },
  ];
  const columnState: GridColumnState = {
    order: columns.map((column) => column.id),
    hidden: [],
    widths: {},
    pinned: { start: ["priority"], end: [] },
  };

  const confirmRemove = async () => {
    if (removing === null) {
      return;
    }
    const key = removing.rule_key;
    const outcome = await remove.submit();
    if (outcome.kind === "succeeded") {
      setRemoving(null);
      toast.show({ tone: "positive", message: t("policies.rules.removed", { key }) });
    }
  };

  return (
    <div className="flex h-120 min-h-0 flex-col pt-3">
      <DataGrid<Rule>
        name="rules"
        title={t("policies.rules.title")}
        headingLevel={3}
        countLabel={(count, formatted) => t("policies.rules.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(rule) => rule.id}
        rowLabel={(rule) => rule.rule_key}
        testIdPrefix="SF-13"
        rowTestKey={(rule) => `rule-${rule.rule_key}`}
        editable={editable}
        selectable={editable}
        defaultColumnState={columnState}
        bulkActions={
          editable
            ? (selection) => {
                const [id] = [...selection.ids];
                const rule = id === undefined ? undefined : byId.get(id);
                if (selection.ids.size !== 1 || rule === undefined) {
                  return null;
                }
                return (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onOpen(DRAWER_NEW_RULE, rule.id)}
                    >
                      {t("policies.rules.duplicate")}
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setRemoving(rule)}>
                      {t("policies.rules.remove")}
                    </Button>
                  </>
                );
              }
            : undefined
        }
        toolbarActions={
          <>
            {tryable ? (
              <Button variant="secondary" size="sm" onClick={() => onOpen(DRAWER_TRY_LINE)}>
                {t("policies.rules.tryLine")}
              </Button>
            ) : null}
            {editable ? (
              <Button variant="primary" size="sm" onClick={() => onOpen(DRAWER_NEW_RULE)}>
                {t("policies.rules.add")}
              </Button>
            ) : null}
          </>
        }
        emptyState={
          <EmptyState
            title={t("policies.rules.empty.title")}
            description={t("policies.rules.empty.description", {
              kind: ruleSetKindLabel(ruleSet.kind),
            })}
            action={
              editable
                ? { label: t("policies.rules.add"), onAction: () => onOpen(DRAWER_NEW_RULE) }
                : undefined
            }
            headingLevel={3}
          />
        }
      />
      <Modal
        open={removing !== null}
        variant="confirmation"
        title={t("policies.rules.removeConfirm.title", { key: removing?.rule_key ?? "" })}
        description={t("policies.rules.removeConfirm.description")}
        primaryAction={{
          label: t("policies.rules.remove"),
          destructive: true,
          onAction: () => void confirmRemove(),
        }}
        onClose={() => setRemoving(null)}
      />
    </div>
  );
}

interface ConditionDraft {
  readonly id: string;
  readonly field: string | null;
  readonly op: RuleOperator | null;
  readonly text: string;
}

interface StepDraft {
  readonly id: string;
  readonly name: string;
  readonly permission: string | null;
  readonly approvers: string;
}

interface OutputDraft {
  readonly templateCode: string | null;
  readonly bookCode: string | null;
  readonly steps: readonly StepDraft[];
  readonly windowDays: string;
  readonly match: string | null;
  readonly holdType: string;
  readonly level: string | null;
  readonly severity: string | null;
  readonly message: string;
}

function stringOf(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function outputDraftOf(outputs: Readonly<Record<string, unknown>>): OutputDraft {
  return {
    templateCode: stringOf(outputs.pob_template_code),
    bookCode: stringOf(outputs.ssp_book_code),
    steps: routingSteps(outputs).map((step) => ({
      id: crypto.randomUUID(),
      name: step.name,
      permission: step.permission === "" ? null : step.permission,
      approvers: String(step.min_approvers),
    })),
    windowDays: typeof outputs.window_days === "number" ? String(outputs.window_days) : "",
    match: stringOf(outputs.match),
    holdType: stringOf(outputs.hold_type) ?? "",
    level: stringOf(outputs.level),
    severity: stringOf(outputs.severity),
    message: stringOf(outputs.message) ?? "",
  };
}

/** The T-REF-26 `outputs` object of a kind from the drawer fields. */
export function outputsOf(kind: RuleSetKind, draft: OutputDraft): Record<string, unknown> {
  switch (kind) {
    case "POB_ASSIGNMENT":
      return { pob_template_code: draft.templateCode };
    case "SSP_ASSIGNMENT":
      return { ssp_book_code: draft.bookCode };
    case "APPROVAL_ROUTING":
      return {
        steps: draft.steps.map((step) => ({
          name: step.name.trim(),
          permission: step.permission,
          min_approvers: /^[0-9]+$/.test(step.approvers.trim()) ? Number(step.approvers.trim()) : 0,
        })),
      };
    case "AUTO_APPROVAL":
      return { auto_approve: true };
    case "COMBINATION_DETECTION":
      return {
        window_days: /^[0-9]+$/.test(draft.windowDays.trim())
          ? Number(draft.windowDays.trim())
          : -1,
        match: draft.match,
      };
    case "HOLD":
      return { hold_type: draft.holdType.trim(), level: draft.level };
    case "DATA_QUALITY":
      return { severity: draft.severity, message: draft.message.trim() };
  }
}

interface RuleDrawerProps {
  readonly kind: RuleSetKind;
  readonly version: RuleSetVersion;
  /** The rule to show or edit; null for a new rule. */
  readonly rule: Rule | null;
  /** "Duplicate rule": the rule a new rule copies. */
  readonly source: Rule | null;
  readonly editable: boolean;
  readonly invalidates: readonly QueryKey[];
  readonly onClose: () => void;
}

/** SCREENS §11.1 rule drawer "Rule <rule key>" (DS-CMP-09 wide): conditions builder and outputs by kind. */
function RuleDrawer({
  kind,
  version,
  rule,
  source,
  editable,
  invalidates,
  onClose,
}: RuleDrawerProps) {
  const toast = useToast();
  const formId = useId();
  const origin = rule ?? source;
  const [ruleKey, setRuleKey] = useState(rule?.rule_key ?? "");
  const [priority, setPriority] = useState(origin === null ? "0" : String(origin.priority));
  const [description, setDescription] = useState(origin?.description ?? "");
  const [conditions, setConditions] = useState<readonly ConditionDraft[]>(
    (origin?.conditions ?? []).map((raw) => {
      const condition = asCondition(raw);
      return {
        id: crypto.randomUUID(),
        field: condition.field === "" ? null : condition.field,
        op: RULE_OPERATORS.find((op) => op === condition.op) ?? null,
        text: conditionValueText(condition.value),
      };
    }),
  );
  const [outputs, setOutputs] = useState<OutputDraft>(outputDraftOf(origin?.outputs ?? {}));
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const upsert = useCommand<Rule>({
    method: "POST",
    path: `${ruleSetVersionPath(version.id)}/rules`,
    invalidates,
  });
  const templates = useQuery({
    queryKey: queryKey("pob-templates", "tenant", { view: "codes" }),
    queryFn: fetchTemplateCodes,
    enabled: editable && kind === "POB_ASSIGNMENT",
  });
  const books = useQuery({
    queryKey: queryKey("ssp-books", "tenant", { view: "codes" }),
    queryFn: fetchSspBookCodes,
    enabled: editable && kind === "SSP_ASSIGNMENT",
  });
  const title =
    rule === null ? t("policies.rule.newTitle") : t("policies.rule.title", { key: rule.rule_key });

  if (!editable) {
    return (
      <Drawer open wide title={title} initialFocus="title" onClose={onClose}>
        {rule === null ? null : <RuleDetails kind={kind} rule={rule} />}
      </Drawer>
    );
  }

  const fields = RULE_FIELDS[kind];
  const serverErrors = upsert.fieldErrors;
  const errors = { ...serverErrors, ...local };
  const otherErrors = Object.entries(serverErrors).filter(
    ([name]) => !["rule_key", "priority", "description"].includes(name),
  );
  const updateCondition = (id: string, changes: Partial<Omit<ConditionDraft, "id">>) => {
    setConditions((current) =>
      current.map((condition) => (condition.id === id ? { ...condition, ...changes } : condition)),
    );
  };
  const updateStep = (id: string, changes: Partial<Omit<StepDraft, "id">>) => {
    setOutputs((current) => ({
      ...current,
      steps: current.steps.map((step) => (step.id === id ? { ...step, ...changes } : step)),
    }));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (upsert.pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (ruleKey.trim() === "") {
      found.rule_key = t("policies.rule.keyRequired");
    }
    if (!/^-?[0-9]+$/.test(priority.trim())) {
      found.priority = t("policies.rules.priorityInvalid");
    }
    conditions.forEach((condition, index) => {
      if (condition.field === null || condition.op === null) {
        found[`condition-${String(index)}`] = t("policies.rule.conditionRequired");
      }
    });
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const key = ruleKey.trim();
    const outcome = await upsert.submit({
      rule_key: key,
      priority: Number(priority.trim()),
      conditions: conditions.map((condition) => ({
        field: condition.field,
        op: condition.op,
        value: parseConditionValue(condition.field ?? "", condition.op ?? "eq", condition.text),
      })),
      outputs: outputsOf(kind, outputs),
      description: description.trim() === "" ? null : description.trim(),
    });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.rule.saved", { key }) });
      onClose();
    }
  };

  const banner =
    upsert.problem === null ? undefined : (
      <Banner tone="negative" title={upsert.problem.detail ?? upsert.problem.title}>
        {otherErrors.length === 0 ? null : (
          <ul className="list-disc ps-4">
            {otherErrors.map(([name, message]) => (
              <li key={name}>
                <span className="font-mono text-mono-sm">{name}</span> {message}
              </li>
            ))}
          </ul>
        )}
      </Banner>
    );

  return (
    <Drawer
      open
      wide
      title={title}
      dirty
      submitting={upsert.pending}
      banner={banner}
      primaryAction={{ label: t("policies.rule.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-13-drawer-rule"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="rule_key"
          label={t("policies.rule.key")}
          required
          error={errors.rule_key ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={rule !== null}
              value={ruleKey}
              onChange={(event) => {
                setRuleKey(event.target.value);
              }}
              className={`${controlClass(errors.rule_key !== undefined)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="rule_priority"
          label={t("policies.rules.column.priority")}
          required
          help={t("policies.rule.priorityHelp")}
          error={errors.priority ?? null}
          width="money"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              inputMode="numeric"
              value={priority}
              onChange={(event) => {
                setPriority(event.target.value);
              }}
              className={`${controlClass(errors.priority !== undefined)} num`}
            />
          )}
        </Field>
        <Field
          name="rule_description"
          label={t("policies.rules.column.description")}
          optional
          error={errors.description ?? null}
          width="text"
        >
          {(control) => (
            <textarea
              {...control}
              rows={2}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              className={controlClass(errors.description !== undefined, true)}
            />
          )}
        </Field>
        <section aria-labelledby={`${formId}-conditions`} className="flex flex-col gap-3">
          <h3 id={`${formId}-conditions`} className="text-title-sm text-fg-1">
            {t("policies.rule.conditions")}
          </h3>
          {fields.length === 0 ? (
            <p className="text-body-sm text-fg-2">{t("policies.rule.noFields")}</p>
          ) : null}
          {conditions.map((condition, index) => (
            <fieldset
              key={condition.id}
              className="flex flex-col gap-2 rounded-md border border-hairline p-3"
            >
              <legend className="px-1 text-body-sm font-medium text-fg-1">
                {t("policies.rule.condition", {
                  position: formatNumber(index + 1, { kind: "count" }),
                })}
              </legend>
              <div className="flex flex-wrap items-start gap-3">
                <Field
                  name={`condition_${String(index)}_field`}
                  label={t("policies.rule.field")}
                  error={errors[`condition-${String(index)}`] ?? null}
                  width="text"
                >
                  {(control) => (
                    <Select<string>
                      control={control}
                      options={fields.map((value) => ({ value, label: fieldLabel(value) }))}
                      value={condition.field}
                      invalid={errors[`condition-${String(index)}`] !== undefined}
                      onChange={(value) => updateCondition(condition.id, { field: value })}
                    />
                  )}
                </Field>
                <Field
                  name={`condition_${String(index)}_op`}
                  label={t("policies.rule.operator")}
                  width="date"
                >
                  {(control) => (
                    <Select<RuleOperator>
                      control={control}
                      options={RULE_OPERATORS.map((value) => ({
                        value,
                        label: operatorLabel(value, condition.field ?? ""),
                      }))}
                      value={condition.op}
                      onChange={(value) => updateCondition(condition.id, { op: value })}
                    />
                  )}
                </Field>
                <Field
                  name={`condition_${String(index)}_value`}
                  label={t("policies.rule.value")}
                  help={
                    condition.op === "in" || condition.op === "range"
                      ? t(
                          condition.op === "in"
                            ? "policies.rule.valueListHelp"
                            : "policies.rule.valueRangeHelp",
                        )
                      : undefined
                  }
                  width="text"
                >
                  {(control) => (
                    <input
                      {...control}
                      type="text"
                      value={condition.text}
                      onChange={(event) =>
                        updateCondition(condition.id, { text: event.target.value })
                      }
                      className={`${controlClass(false)} font-mono`}
                    />
                  )}
                </Field>
              </div>
              <div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setConditions((current) =>
                      current.filter((candidate) => candidate.id !== condition.id),
                    )
                  }
                >
                  {t("policies.rule.removeCondition")}
                </Button>
              </div>
            </fieldset>
          ))}
          {fields.length === 0 ? null : (
            <div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  setConditions((current) => [
                    ...current,
                    { id: crypto.randomUUID(), field: null, op: "eq", text: "" },
                  ])
                }
              >
                {t("policies.rule.addCondition")}
              </Button>
            </div>
          )}
        </section>
        <section aria-labelledby={`${formId}-outputs`} className="flex flex-col gap-3">
          <h3 id={`${formId}-outputs`} className="text-title-sm text-fg-1">
            {t("policies.rule.outputs")}
          </h3>
          <OutputFields
            kind={kind}
            outputs={outputs}
            templateCodes={templates.data ?? []}
            bookCodes={books.data ?? []}
            onChange={(changes) => setOutputs((current) => ({ ...current, ...changes }))}
            onStep={updateStep}
          />
        </section>
      </form>
    </Drawer>
  );
}

interface OutputFieldsProps {
  readonly kind: RuleSetKind;
  readonly outputs: OutputDraft;
  readonly templateCodes: readonly string[];
  readonly bookCodes: readonly string[];
  readonly onChange: (changes: Partial<OutputDraft>) => void;
  readonly onStep: (id: string, changes: Partial<Omit<StepDraft, "id">>) => void;
}

function OutputFields({
  kind,
  outputs,
  templateCodes,
  bookCodes,
  onChange,
  onStep,
}: OutputFieldsProps) {
  const header = "px-2 py-1.5 text-start text-body-sm font-medium text-fg-2";
  switch (kind) {
    case "POB_ASSIGNMENT":
      return (
        <Field
          name="output_template"
          label={t("policies.rule.output.template")}
          required
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={templateCodes.map((value) => ({ value, label: value }))}
              value={outputs.templateCode}
              onChange={(value) => onChange({ templateCode: value })}
            />
          )}
        </Field>
      );
    case "SSP_ASSIGNMENT":
      return (
        <Field name="output_book" label={t("policies.rule.output.book")} required width="text">
          {(control) => (
            <Select<string>
              control={control}
              options={bookCodes.map((value) => ({ value, label: value }))}
              value={outputs.bookCode}
              onChange={(value) => onChange({ bookCode: value })}
            />
          )}
        </Field>
      );
    case "APPROVAL_ROUTING":
      return (
        <div className="flex flex-col gap-2">
          <table className="w-full border-collapse text-body-sm">
            <caption className="pb-2 text-start text-body-sm font-medium text-fg-1">
              {t("policies.rule.output.steps")}
            </caption>
            <thead>
              <tr className="border-b border-default bg-subtle">
                <th scope="col" className={header}>
                  {t("policies.rule.output.stepName")}
                </th>
                <th scope="col" className={header}>
                  {t("policies.rule.output.permission")}
                </th>
                <th scope="col" className={header}>
                  {t("policies.rule.output.minApprovers")}
                </th>
                <th scope="col" className={header}>
                  <span className="sr-only">{t("policies.rule.output.removeStep")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {outputs.steps.map((step, index) => {
                const position = formatNumber(index + 1, { kind: "count" });
                return (
                  <tr key={step.id} className="border-b border-hairline align-top">
                    <td className="px-2 py-1.5">
                      <input
                        type="text"
                        aria-label={t("policies.rule.output.stepNameOf", { position })}
                        value={step.name}
                        onChange={(event) => onStep(step.id, { name: event.target.value })}
                        className={controlClass(false)}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      {/* Select names itself by the field label id; the column header is the visible label. */}
                      <span
                        id={fieldLabelId(`step_${String(index)}_permission`)}
                        className="sr-only"
                      >
                        {t("policies.rule.output.permissionOf", { position })}
                      </span>
                      <Select<string>
                        control={{
                          id: fieldId(`step_${String(index)}_permission`),
                          name: `step_${String(index)}_permission`,
                        }}
                        options={[...APPROVAL_PERMISSIONS].map((value) => ({
                          value,
                          label: value,
                        }))}
                        value={step.permission}
                        onChange={(value) => onStep(step.id, { permission: value })}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        type="text"
                        inputMode="numeric"
                        aria-label={t("policies.rule.output.minApproversOf", { position })}
                        value={step.approvers}
                        onChange={(event) => onStep(step.id, { approvers: event.target.value })}
                        className={`${controlClass(false)} num w-20`}
                      />
                    </td>
                    <td className="px-2 py-1.5 text-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          onChange({
                            steps: outputs.steps.filter((candidate) => candidate.id !== step.id),
                          })
                        }
                      >
                        {t("policies.rule.output.removeStep")}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                onChange({
                  steps: [
                    ...outputs.steps,
                    { id: crypto.randomUUID(), name: "", permission: null, approvers: "1" },
                  ],
                })
              }
            >
              {t("policies.rule.output.addStep")}
            </Button>
          </div>
        </div>
      );
    case "AUTO_APPROVAL":
      return (
        <label className="flex items-center gap-2 text-body-sm text-fg-1">
          <input type="checkbox" checked readOnly aria-readonly="true" className="size-4" />
          {t("policies.rule.output.autoApprove")}
        </label>
      );
    case "COMBINATION_DETECTION":
      return (
        <div className="flex flex-wrap gap-3">
          <Field
            name="output_window"
            label={t("policies.rule.output.windowDays")}
            required
            width="money"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                inputMode="numeric"
                value={outputs.windowDays}
                onChange={(event) => onChange({ windowDays: event.target.value })}
                className={`${controlClass(false)} num`}
              />
            )}
          </Field>
          <Field name="output_match" label={t("policies.rule.output.match")} required width="text">
            {(control) => (
              <Select<string>
                control={control}
                options={["same_customer", "related_party"].map((value) => ({
                  value,
                  label: t(`policies.rule.output.match.${value}`),
                }))}
                value={outputs.match}
                onChange={(value) => onChange({ match: value })}
              />
            )}
          </Field>
        </div>
      );
    case "HOLD":
      return (
        <div className="flex flex-wrap gap-3">
          <Field
            name="output_hold_type"
            label={t("policies.rule.output.holdType")}
            required
            width="text"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                value={outputs.holdType}
                onChange={(event) => onChange({ holdType: event.target.value })}
                className={`${controlClass(false)} font-mono`}
              />
            )}
          </Field>
          <Field name="output_level" label={t("policies.rule.output.level")} required width="date">
            {(control) => (
              <Select<string>
                control={control}
                options={["contract", "obligation"].map((value) => ({
                  value,
                  label: t(`policies.rule.output.level.${value}`),
                }))}
                value={outputs.level}
                onChange={(value) => onChange({ level: value })}
              />
            )}
          </Field>
        </div>
      );
    case "DATA_QUALITY":
      return (
        <div className="flex flex-col gap-3">
          <Field
            name="output_severity"
            label={t("policies.rule.output.severity")}
            required
            width="date"
          >
            {(control) => (
              <Select<string>
                control={control}
                options={["ERROR", "WARNING"].map((value) => ({
                  value,
                  label: t(`policies.rule.output.severity.${value}`),
                }))}
                value={outputs.severity}
                onChange={(value) => onChange({ severity: value })}
              />
            )}
          </Field>
          <Field
            name="output_message"
            label={t("policies.rule.output.message")}
            required
            width="text"
          >
            {(control) => (
              <textarea
                {...control}
                rows={3}
                value={outputs.message}
                onChange={(event) => onChange({ message: event.target.value })}
                className={controlClass(false, true)}
              />
            )}
          </Field>
        </div>
      );
  }
}

/** The read-only rule drawer body: definition list, condition fieldsets and outputs. */
function RuleDetails({ kind, rule }: { readonly kind: RuleSetKind; readonly rule: Rule }) {
  const header = "px-2 py-1.5 text-start text-body-sm font-medium text-fg-2";
  const steps = routingSteps(rule.outputs);
  return (
    <div data-testid="SF-13-drawer-rule" className="flex flex-col gap-4">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-body-sm">
        <dt className="text-fg-3">{t("policies.rule.key")}</dt>
        <dd className="font-mono text-mono-sm text-fg-1">{rule.rule_key}</dd>
        <dt className="text-fg-3">{t("policies.rules.column.priority")}</dt>
        <dd className="num text-fg-1">{formatNumber(rule.priority)}</dd>
        <dt className="text-fg-3">{t("policies.rules.column.specificity")}</dt>
        <dd className="num text-fg-2">{formatNumber(rule.specificity, { kind: "count" })}</dd>
        <dt className="text-fg-3">{t("policies.rules.column.description")}</dt>
        <dd className="text-fg-1">{rule.description ?? NO_VALUE}</dd>
      </dl>
      <section className="flex flex-col gap-3">
        <h3 className="text-title-sm text-fg-1">{t("policies.rule.conditions")}</h3>
        {rule.conditions.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("policies.rule.noConditions")}</p>
        ) : null}
        {rule.conditions.map(asCondition).map((condition, index) => (
          <fieldset
            key={`${condition.field}:${String(index)}`}
            className="rounded-md border border-hairline p-3"
          >
            <legend className="px-1 text-body-sm font-medium text-fg-1">
              {t("policies.rule.condition", {
                position: formatNumber(index + 1, { kind: "count" }),
              })}
            </legend>
            <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-body-sm">
              <dt className="text-fg-3">{t("policies.rule.field")}</dt>
              <dd className="text-fg-1">{fieldLabel(condition.field)}</dd>
              <dt className="text-fg-3">{t("policies.rule.operator")}</dt>
              <dd className="text-fg-1">{operatorLabel(condition.op, condition.field)}</dd>
              <dt className="text-fg-3">{t("policies.rule.value")}</dt>
              <dd className="font-mono text-mono-sm text-fg-1">
                {conditionValueText(condition.value)}
              </dd>
            </dl>
          </fieldset>
        ))}
      </section>
      <section className="flex flex-col gap-3">
        <h3 className="text-title-sm text-fg-1">{t("policies.rule.outputs")}</h3>
        {kind === "APPROVAL_ROUTING" ? (
          <table className="w-full border-collapse text-body-sm">
            <caption className="pb-2 text-start text-body-sm font-medium text-fg-1">
              {t("policies.rule.output.steps")}
            </caption>
            <thead>
              <tr className="border-b border-default bg-subtle">
                <th scope="col" className={header}>
                  {t("policies.rule.output.stepName")}
                </th>
                <th scope="col" className={header}>
                  {t("policies.rule.output.permission")}
                </th>
                <th scope="col" className={`${header} text-end`}>
                  {t("policies.rule.output.minApprovers")}
                </th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step, index) => (
                <tr key={`${step.name}:${String(index)}`} className="border-b border-hairline">
                  <th scope="row" className="px-2 py-1.5 text-start font-normal text-fg-1">
                    {step.name}
                  </th>
                  <td className="px-2 py-1.5 font-mono text-mono-sm">{step.permission}</td>
                  <td className="num px-2 py-1.5 text-end">
                    {formatNumber(step.min_approvers, { kind: "count" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-body-sm text-fg-1">{outputSummary(kind, rule.outputs)}</p>
        )}
      </section>
    </div>
  );
}

interface TestCasesPaneProps {
  readonly version: RuleSetVersion;
  readonly editable: boolean;
  readonly onOpen: (drawer: string, id?: string | null) => void;
}

function mono(text: string): ReactNode {
  return (
    <span className="truncate font-mono text-mono-sm" title={text}>
      {text}
    </span>
  );
}

function TestCasesPane({ version, editable, onOpen }: TestCasesPaneProps) {
  const source: GridSource<ConfigTestCase> = {
    queryKey: configTestCasesKey("rule_set_version", version.id),
    fetchPage: (cursor, sort) =>
      fetchConfigTestCasesPage("rule_set_version", version.id, cursor, sort),
  };
  // API-C-09 sort keys: GET /api/v1/config-test-cases
  const columns: readonly GridColumn<ConfigTestCase>[] = [
    {
      id: "name",
      header: t("policies.tests.column.name"),
      kind: "text",
      value: (item) => item.name,
      sortKey: "name",
      width: 280,
    },
    {
      id: "input",
      header: t("policies.tests.column.input"),
      kind: "text",
      value: (item) => jsonSummary(item.input),
      render: (item) => mono(jsonSummary(item.input)),
      width: 320,
    },
    {
      id: "expected",
      header: t("policies.tests.column.expected"),
      kind: "text",
      value: (item) => jsonSummary(item.expected_output),
      render: (item) => mono(jsonSummary(item.expected_output)),
      width: 240,
    },
    {
      id: "result",
      header: t("policies.tests.column.result"),
      kind: "status",
      value: (item) => item.last_result,
      render: (item) => {
        const word = caseResultWord(item.last_result);
        return word === null ? NO_VALUE : <StatusChip status={word} />;
      },
      width: 136,
    },
    {
      id: "last_run",
      header: t("policies.tests.column.lastRun"),
      kind: "timestamp",
      value: (item) => item.last_run_at,
      width: 184,
    },
  ];
  return (
    <div className="flex h-120 min-h-0 flex-col pt-3">
      <DataGrid<ConfigTestCase>
        name="test-cases"
        title={t("policies.tests.title")}
        headingLevel={3}
        countLabel={(count, formatted) => t("policies.tests.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        rowLabel={(item) => item.name}
        testIdPrefix="SF-13"
        rowTestKey={(item) => `test-case-${item.name}`}
        toolbarActions={
          editable ? (
            <Button variant="primary" size="sm" onClick={() => onOpen(DRAWER_NEW_TEST_CASE)}>
              {t("policies.tests.add")}
            </Button>
          ) : undefined
        }
        emptyState={
          <EmptyState
            title={t("policies.tests.empty.title")}
            description={t("policies.tests.empty.description")}
            action={
              editable
                ? { label: t("policies.tests.add"), onAction: () => onOpen(DRAWER_NEW_TEST_CASE) }
                : undefined
            }
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

interface TestCaseDrawerProps {
  readonly version: RuleSetVersion;
  readonly invalidates: readonly QueryKey[];
  readonly onClose: () => void;
}

/** The API members the fields of "Add test case" send (DG-FE-06 rev 1.228). */
const TEST_CASE_MEMBERS = {
  name: ["name"],
  input: ["input"],
  expected_output: ["expected_output"],
} as const;

/** SCREENS §11.1 "Add test case": Name; Input and Expected output as JSON objects (API-R-57). */
function TestCaseDrawer({ version, invalidates, onClose }: TestCaseDrawerProps) {
  const toast = useToast();
  const formId = useId();
  const [name, setName] = useState("");
  const [input, setInput] = useState("{}");
  const [expected, setExpected] = useState("{}");
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const create = useCommand<ConfigTestCase>({
    method: "POST",
    path: CONFIG_TEST_CASES_PATH,
    invalidates,
  });
  const refusals = useFieldRefusals(create.problem, TEST_CASE_MEMBERS);
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (create.pending) {
      return;
    }
    const found: Record<string, string> = {};
    const parsedInput = parseJsonObject(input);
    const parsedExpected = parseJsonObject(expected);
    if (name.trim() === "") {
      found.name = t("policies.tests.drawer.nameRequired");
    }
    if (!parsedInput.ok) {
      found.input = t("policies.tests.drawer.jsonInvalid");
    }
    if (!parsedExpected.ok) {
      found.expected_output = t("policies.tests.drawer.jsonInvalid");
    }
    setLocal(found);
    if (Object.keys(found).length > 0 || !parsedInput.ok || !parsedExpected.ok) {
      return;
    }
    const outcome = await create.submit({
      subject_type: "rule_set_version",
      subject_id: version.id,
      name: name.trim(),
      input: parsedInput.value,
      expected_output: parsedExpected.value,
    });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.tests.drawer.added", { name: name.trim() }),
      });
      onClose();
    }
  };

  return (
    <Drawer
      open
      title={t("policies.tests.add")}
      dirty={name !== "" || input !== "{}" || expected !== "{}"}
      submitting={create.pending}
      banner={
        refusals.banner === null ? undefined : (
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        )
      }
      primaryAction={{ label: t("policies.tests.add"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="case_name"
          label={t("policies.tests.column.name")}
          required
          error={errors.name ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                refusals.edited("name");
              }}
              className={controlClass(errors.name !== undefined)}
            />
          )}
        </Field>
        <Field
          name="case_input"
          label={t("policies.tests.column.input")}
          required
          error={errors.input ?? null}
          width="full"
        >
          {(control) => (
            <textarea
              {...control}
              rows={5}
              value={input}
              onChange={(event) => {
                setInput(event.target.value);
                refusals.edited("input");
              }}
              className={`${controlClass(errors.input !== undefined, true)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="case_expected"
          label={t("policies.tests.column.expected")}
          required
          help={t("policies.tests.drawer.expectedHelp")}
          error={errors.expected_output ?? null}
          width="full"
        >
          {(control) => (
            <textarea
              {...control}
              rows={3}
              value={expected}
              onChange={(event) => {
                setExpected(event.target.value);
                refusals.edited("expected_output");
              }}
              className={`${controlClass(errors.expected_output !== undefined, true)} font-mono`}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}

/** SCREENS §11.1 lint panel: the static list "Lint findings", error rows with the negative chip only. */
function LintPane({
  version,
  rules,
}: {
  readonly version: RuleSetVersion;
  readonly rules: readonly Rule[];
}) {
  const result = version.lint_result;
  if (result === null) {
    return <p className="pt-3 text-body-sm text-fg-2">{t("policies.lint.notRun")}</p>;
  }
  if (result.findings.length === 0) {
    return <p className="pt-3 text-body-sm text-fg-2">{t("policies.lint.empty")}</p>;
  }
  return (
    <ul
      aria-label={t("policies.lint.label")}
      data-testid="SF-13-pane-lint"
      className="mt-3 flex flex-col border-t border-hairline"
    >
      {result.findings.map((finding) => (
        <li
          key={`${finding.rule_id}:${finding.rule_keys.join(",")}`}
          className="flex items-start gap-3 border-b border-hairline py-2 text-body-sm text-fg-1"
        >
          <StatusChip status="Error" />
          <span>{lintMessage(finding, rules)}</span>
        </li>
      ))}
    </ul>
  );
}

function moneyOf(value: unknown): ReactNode {
  if (typeof value === "object" && value !== null) {
    const money = value as { readonly amount?: unknown; readonly currency?: unknown };
    if (
      typeof money.amount === "string" &&
      typeof money.currency === "string" &&
      currencyRegistered(money.currency)
    ) {
      return <Money value={money.amount} currency={money.currency} variant="cell" />;
    }
  }
  return NO_VALUE;
}

function textOf(value: unknown): string {
  return typeof value === "string" && value !== "" ? value : NO_VALUE;
}

interface StaticTableProps {
  readonly caption: string;
  readonly headers: readonly { readonly label: string; readonly end?: boolean }[];
  readonly rows: readonly (readonly ReactNode[])[];
}

function StaticTable({ caption, headers, rows }: StaticTableProps) {
  return (
    <table className="w-full border-collapse text-body-sm">
      <caption className="pb-2 text-start text-title-sm text-fg-1">{caption}</caption>
      <thead>
        <tr className="border-b border-default bg-subtle">
          {headers.map((header) => (
            <th
              key={header.label}
              scope="col"
              className={`px-3 py-2 font-medium text-fg-2 ${header.end === true ? "text-end" : "text-start"}`}
            >
              {header.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((cells, index) => (
          <tr key={String(index)} className="border-b border-hairline">
            {cells.map((cell, column) => (
              <td
                key={String(column)}
                className={`px-3 py-2 ${headers[column]?.end === true ? "text-end" : "text-start"}`}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** SCREENS §11.1 simulation panel (04 API-S-SimulationSummary; PRD BR-POL-01). */
function SimulationPane({ version }: { readonly version: RuleSetVersion }) {
  const simulation = version.impact_simulation;
  let body: ReactNode;
  if (simulation === null) {
    body = <p className="text-body-sm text-fg-2">{t("policies.simulation.none")}</p>;
  } else if (simulation.summary.contracts_affected === 0) {
    body = <p className="text-body-sm text-fg-1">{t("policies.simulation.noContracts")}</p>;
  } else {
    const summary = simulation.summary;
    body = (
      <>
        <p className="text-body-sm text-fg-1">{summary.statement}</p>
        <StaticTable
          caption={t("policies.simulation.revenue")}
          headers={[
            { label: t("policies.simulation.column.period") },
            { label: t("policies.simulation.column.entity") },
            { label: t("policies.simulation.column.change"), end: true },
          ]}
          rows={summary.revenue_delta_by_period.map((item) => [
            textOf(item.period_key),
            textOf(item.entity_code),
            moneyOf(item.amount),
          ])}
        />
        <StaticTable
          caption={t("policies.simulation.balance")}
          headers={[
            { label: t("policies.simulation.column.balance") },
            { label: t("policies.simulation.column.entity") },
            { label: t("policies.simulation.column.change"), end: true },
          ]}
          rows={summary.balance_delta.map((item) => [
            textOf(item.balance),
            textOf(item.entity_code),
            moneyOf(item.amount),
          ])}
        />
        <StaticTable
          caption={t("policies.simulation.journal")}
          headers={[
            { label: t("policies.simulation.column.role") },
            { label: t("policies.simulation.column.debit"), end: true },
            { label: t("policies.simulation.column.credit"), end: true },
          ]}
          rows={summary.journal_delta.map((item) => [
            textOf(item.account_role),
            moneyOf(item.debit),
            moneyOf(item.credit),
          ])}
        />
      </>
    );
  }
  return (
    <div data-testid="SF-13-pane-simulation" className="flex flex-col gap-4 pt-3">
      {body}
      {simulation === null ? null : (
        <a
          href={`${FILE_CONTENT_PATH}/${simulation.file_id}/content`}
          className="self-start text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
        >
          {t("policies.simulation.download")}
        </a>
      )}
    </div>
  );
}

interface ChangesPaneProps {
  readonly ruleSet: RuleSet;
  readonly version: RuleSetVersion;
  readonly rules: readonly Rule[] | undefined;
}

/**
 * SCREENS §11.1 changes panel, DS-CMP-16 grid diff: against the set's published version, or, on the
 * published version itself, against the version it superseded; version 1 adds every rule (L4-5-Q-37).
 */
function ChangesPane({ ruleSet, version, rules }: ChangesPaneProps) {
  const current = ruleSet.current_version;
  const baselineId =
    current !== null && current.id !== version.id ? current.id : version.supersedes_version_id;
  const baseline = useQuery({
    queryKey: rulesKey(baselineId ?? "none"),
    queryFn: () => fetchAllRules(baselineId ?? ""),
    enabled: baselineId !== null,
  });
  if (rules === undefined || (baselineId !== null && baseline.data === undefined)) {
    return <Skeleton region={t("policies.changes.title")} shape="rows" count={4} />;
  }
  const changes = compareRules(rules, baseline.data ?? []);
  const source: GridSource<RuleChange> = {
    queryKey: queryKey("rule-set-versions", "tenant", {
      id: version.id,
      view: "changes",
      against: baselineId ?? "",
      digest: changes.map((change) => `${change.kind}:${change.rule.rule_key}`).join(","),
    }),
    fetchPage: () =>
      Promise.resolve({
        items: changes,
        nextCursor: null,
        total: { count: changes.length, capped: false },
      }),
  };
  const cell = (change: RuleChange, column: string, text: string | null): ReactNode => {
    if (change.kind !== "changed" || !change.changed.has(column) || change.previous === null) {
      return text ?? NO_VALUE;
    }
    const previous = previousText(ruleSet.kind, change.previous, column);
    return (
      <span
        className="truncate rounded-sm px-1 ring-1 ring-inset ring-warning-border"
        title={t("policies.changes.was", { value: previous })}
      >
        {text ?? NO_VALUE}
      </span>
    );
  };
  const columns: readonly GridColumn<RuleChange>[] = [
    {
      id: "change",
      header: t("policies.changes.column.change"),
      kind: "status",
      value: (change) => change.kind,
      render: (change) => (
        <>
          <span className="sr-only">{t(`common.diff.prefix.${change.kind}`)}</span>
          <OutlineChip label={t(`policies.changes.kind.${change.kind}`)} />
        </>
      ),
      width: 120,
    },
    {
      id: "rule_key",
      header: t("policies.rules.column.key"),
      kind: "identifier",
      value: (change) => change.rule.rule_key,
      width: 176,
    },
    {
      id: "priority",
      header: t("policies.rules.column.priority"),
      kind: "number",
      value: (change) => String(change.rule.priority),
      render: (change) => cell(change, "priority", formatNumber(change.rule.priority)),
      width: 104,
    },
    {
      id: "conditions",
      header: t("policies.rules.column.conditions"),
      kind: "text",
      value: (change) => conditionSummary(change.rule.conditions),
      render: (change) => cell(change, "conditions", conditionSummary(change.rule.conditions)),
      width: 360,
    },
    {
      id: "outputs",
      header: t("policies.rules.column.outputs"),
      kind: "text",
      value: (change) => outputSummary(ruleSet.kind, change.rule.outputs),
      render: (change) => cell(change, "outputs", outputSummary(ruleSet.kind, change.rule.outputs)),
      width: 280,
    },
    {
      id: "description",
      header: t("policies.rules.column.description"),
      kind: "text",
      value: (change) => change.rule.description ?? null,
      render: (change) => cell(change, "description", change.rule.description ?? null),
      width: 280,
    },
  ];
  return (
    <div className="flex h-120 min-h-0 flex-col pt-3">
      <DataGrid<RuleChange>
        name="changes"
        title={t("policies.changes.title")}
        headingLevel={3}
        countLabel={(count, formatted) => t("policies.changes.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(change) => `${change.kind}:${change.rule.rule_key}`}
        rowLabel={(change) => change.rule.rule_key}
        testIdPrefix="SF-13"
        rowTestKey={(change) => `change-${change.rule.rule_key}`}
        emptyState={
          <EmptyState
            title={t("policies.changes.empty.title")}
            description={t("policies.changes.empty.description")}
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

function previousText(kind: RuleSetKind, rule: Rule, column: string): string {
  switch (column) {
    case "priority":
      return formatNumber(rule.priority);
    case "conditions":
      return conditionSummary(rule.conditions);
    case "outputs":
      return outputSummary(kind, rule.outputs);
    default:
      return rule.description ?? NO_VALUE;
  }
}

interface TryLineDrawerProps {
  readonly ruleSet: RuleSet;
  readonly version: RuleSetVersion;
  readonly onClose: () => void;
}

/** The facts of "Try a line": collection fields split on commas; empty inputs are left out. */
export function factsOf(values: Readonly<Record<string, string>>): Record<string, unknown> {
  const facts: Record<string, unknown> = {};
  for (const [field, typed] of Object.entries(values)) {
    const text = typed.trim();
    if (text === "") {
      continue;
    }
    if (LIST_FIELDS.has(field)) {
      facts[field] = text
        .split(",")
        .map((part) => part.trim())
        .filter((part) => part !== "");
    } else if (isBooleanField(field)) {
      facts[field] = text === "true";
    } else {
      facts[field] = text;
    }
  }
  return facts;
}

/** SCREENS §11.1 "Try a line": the kind's condition fields, evaluated against this version. */
function TryLineDrawer({ ruleSet, version, onClose }: TryLineDrawerProps) {
  const formId = useId();
  const [values, setValues] = useState<Readonly<Record<string, string>>>({});
  const [result, setResult] = useState<RuleSetEvaluation | null>(null);
  const evaluate = useCommand<RuleSetEvaluation>({
    method: "POST",
    path: `${RULE_SETS_PATH}/${ruleSet.id}/evaluate`,
  });
  const fields = RULE_FIELDS[ruleSet.kind];

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (evaluate.pending) {
      return;
    }
    setResult(null);
    const outcome = await evaluate.submit({ facts: factsOf(values), version_id: version.id });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      setResult(outcome.data);
    }
  };
  let message: string | null = null;
  if (result !== null) {
    message =
      result.matched && result.rule_key !== null
        ? t("policies.try.matched", {
            key: result.rule_key,
            specificity: formatNumber(result.specificity ?? 0, { kind: "count" }),
            priority: formatNumber(result.priority ?? 0),
            output: outputSummary(ruleSet.kind, result.outputs ?? {}),
          })
        : t("policies.try.noMatch");
  }

  return (
    <Drawer
      open
      title={t("policies.rules.tryLine")}
      subtitle={`${ruleSet.code} ${t("policies.version.number", { version: version.version_no })}`}
      submitting={evaluate.pending}
      banner={
        evaluate.problem === null ? undefined : (
          <Banner tone="negative" title={evaluate.problem.detail ?? evaluate.problem.title} />
        )
      }
      primaryAction={{ label: t("policies.try.run"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        {fields.map((field) => (
          <Field
            key={field}
            name={`try_${field.replace(/[^a-z0-9]+/g, "_")}`}
            label={fieldLabel(field)}
            optional
            help={LIST_FIELDS.has(field) ? t("policies.rule.valueListHelp") : undefined}
            error={evaluate.fieldErrors[`facts.${field}`] ?? null}
            width="text"
          >
            {(control) =>
              isBooleanField(field) ? (
                <Select<string>
                  control={control}
                  options={[
                    { value: "true", label: t("common.grid.yes") },
                    { value: "false", label: t("common.grid.no") },
                  ]}
                  value={values[field] ?? null}
                  onChange={(value) => setValues((current) => ({ ...current, [field]: value }))}
                />
              ) : (
                <input
                  {...control}
                  type="text"
                  value={values[field] ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [field]: event.target.value }))
                  }
                  className={`${controlClass(false)} font-mono`}
                />
              )
            }
          </Field>
        ))}
      </form>
      <div role="status" className="text-body-sm text-fg-1">
        {message}
      </div>
    </Drawer>
  );
}

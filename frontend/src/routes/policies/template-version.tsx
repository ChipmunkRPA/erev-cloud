// SF-13:template-version Obligation template version editor (SCREENS §11.0 lifecycle pattern, §11.2;
// §0.4 RT-61; §0.5 `pane=outputs|policy-values|tests|simulation|changes`; §0.7 SCR-ST-05, SCR-ST-07,
// SCR-PERM-01; DESIGN_SYSTEM DS-CMP-06, DS-CMP-07, DS-CMP-10, DS-CMP-16, DS-CMP-19, DS-CMP-21, DS-CMP-29;
// 04 API-R-24 `GET /pob-templates/{id}`, `POST /pob-templates/{id}/versions`, `GET, PATCH
// /pob-template-versions/{id}` (`If-Match`), `POST …/test`, `/submit`, API-R-57 `GET /config-test-cases`,
// API-R-09 `POST /approvals/{id}/withdraw`; REQ-POL-001; BUILD_SPEC RFD-23). Breadcrumb "Policies /
// Revenue policies / <code>", the Policies route tabs, the record header (name, code, status and version
// chips, the §11.0 commands for `config.author`), the lifecycle stepper and the panel tabs Outputs
// (the T-REF-23 form, saved as one `PATCH` of the changed fields), Policy values (product-level
// registry parameters), Test cases (read-only list; cases are authored on SF-13:rule-set-version's
// pattern in a later item), Simulation (the example-case evidence; template versions carry no impact
// simulation) and Changes (the outputs that differ from the superseded version). Outputs change only
// while the version is DRAFT or TESTED (DB-04); the approval publishes, so no Publish button renders
// (D-76). Rev 1.31 (item TPL-EFFECTIVE-FROM-UI-1; PRD ERR-75): the Meta of §11.1 stands between the
// stepper and the panes — a version that replaces the published one cannot be submitted without an
// effective date later than today — and a refused command shows its messages (§11.0).
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Combobox } from "../../components/form/Combobox";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { RecordHeader } from "../../components/record/RecordHeader";
import { type Step, Stepper } from "../../components/record/Stepper";
import { withPane } from "../../components/record/pane-params";
import { PanelTabs, type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { type Approval, APPROVALS_PATH, fetchApproval } from "../../lib/api/queries/approvals";
import {
  type ConfigTestCase,
  caseResultWord,
  configTestCasesKey,
  fetchConfigTestCasesPage,
  jsonSummary,
} from "../../lib/api/queries/config-test-cases";
import { useMe } from "../../lib/api/queries/me";
import {
  DISTINCTNESS_VALUES,
  type Distinctness,
  END_DATE_RULES,
  type EndDateRule,
  EVERY_TEMPLATE,
  EVERY_TEMPLATE_VERSION,
  fetchTemplateVersion,
  isTemplateEditable,
  LICENCE_NATURES,
  type LicenceNature,
  OBLIGATION_KINDS,
  type ObligationKind,
  type OutputField,
  outputChanges,
  OVER_TIME_CRITERIA,
  type OverTimeCriterion,
  type PobTemplate,
  type PobTemplateVersion,
  type PobTemplateVersionUpdate,
  POINT_IN_TIME_METHODS,
  PRINCIPAL_AGENT_VALUES,
  type PrincipalAgent,
  productLevelParameters,
  RATABLE_CONVENTIONS,
  type RatableConvention,
  RECOGNITION_METHODS,
  type RecognitionMethod,
  SATISFACTION_PATTERNS,
  type SatisfactionPattern,
  SERIES_UNITS,
  type SeriesIncrementUnit,
  START_DATE_RULES,
  type StartDateRule,
  templateKey,
  templatePaneOf,
  templateVersionKey,
  templateVersionPath,
  templateVersionRoute,
  templateVersionsPath,
  useTemplate,
  useTemplateVersion,
  WARRANTY_TYPES,
  type WarrantyType,
} from "../../lib/api/queries/pob-templates";
import { useParameters } from "../../lib/api/queries/policies";
import { CONFIG_AUTHOR_PERMISSION, CONFIG_READ_PERMISSION } from "../../lib/api/queries/rule-sets";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { placeProblem } from "../../lib/api/refusals";
import {
  formatDate,
  formatNumber,
  formatTimestamp,
  NO_VALUE,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { POLICY_TABS } from "./revenue";
import {
  approverNames,
  effectiveCaption,
  focusEffectiveFrom,
  refusesEffectiveDate,
  useLifecycleRefusal,
  useSubmissionOrder,
  VersionMeta,
} from "./version-meta";

function mono(text: string | null): ReactNode {
  return text === null || text === "" ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="font-mono text-mono">{text}</span>
  );
}

export function kindLabel(kind: ObligationKind): string {
  return t(`policies.template.kind.${kind}`);
}

export function methodLabel(method: RecognitionMethod): string {
  return t(`policies.template.method.${method}`);
}

/** SCREENS §11.2 "Distinctness" cell: "Series (increment: day)" for a series template. */
export function distinctnessText(
  version: Pick<PobTemplateVersion, "distinctness" | "series_increment_unit">,
): string {
  if (version.distinctness === "series") {
    return t("policies.template.series", {
      unit: t(`policies.template.seriesUnit.${version.series_increment_unit ?? "day"}`),
    });
  }
  return t(`policies.template.distinctness.${version.distinctness}`);
}

function outputText(field: OutputField, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return NO_VALUE;
  }
  if (typeof value === "boolean") {
    return t(value ? "policies.template.yes" : "policies.template.no");
  }
  const literal = String(value);
  switch (field) {
    case "obligation_kind":
      return kindLabel(literal as ObligationKind);
    case "distinctness":
      return t(`policies.template.distinctness.${literal}`);
    case "series_increment_unit":
      return t(`policies.template.seriesUnit.${literal}`);
    case "satisfaction_pattern":
      return t(`policies.template.satisfaction.${literal}`);
    case "over_time_criterion":
      return t(`policies.template.criterion.${literal}`);
    case "recognition_method":
      return methodLabel(literal as RecognitionMethod);
    case "ratable_convention":
      return t(`policies.template.convention.${literal}`);
    case "start_date_rule":
      return t(`policies.template.startRule.${literal}`);
    case "end_date_rule":
      return t(`policies.template.endRule.${literal}`);
    case "principal_agent":
      return t(`policies.template.principalAgent.${literal}`);
    case "warranty_type":
      return t(`policies.template.warranty.${literal}`);
    case "licence_nature":
      return t(`policies.template.licence.${literal}`);
    default:
      return literal;
  }
}

/** The §11.0 lifecycle steps of a template version (mirrors the rule-set version editor). */
export function templateLifecycle(
  version: PobTemplateVersion,
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
  const order: Readonly<Record<PobTemplateVersion["status"], number>> = {
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
      caption: effectiveCaption(version, "date"),
    },
  ];
  const currentId = (["draft", "tested", "approval", "published"] as const)[Math.min(reached, 3)];
  return { steps, currentId: currentId ?? "draft" };
}

export function TemplateVersionEditor() {
  const { templateId = "", versionId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const template = useTemplate(templateId);
  const version = useTemplateVersion(versionId);
  const title = t("policies.templateVersion.documentTitle");

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
  } else if (template.isError || version.isError) {
    const error = template.error ?? version.error;
    body =
      error instanceof ApiProblem && error.status === 404 ? (
        <div data-testid="SF-13-template-version-not-found">
          <EmptyState
            title={t("policies.templateVersion.notFound.title")}
            description={t("policies.version.notFound.description")}
            link={{ label: t("policies.version.notFound.action"), href: "/policies" }}
          />
        </div>
      ) : (
        <Banner tone="negative" title={t("policies.templateVersion.loadError")} />
      );
  } else if (template.data === undefined || version.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else {
    return (
      <VersionView
        template={template.data}
        version={version.data}
        author={access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION)}
      />
    );
  }
  return (
    <div
      data-testid="SF-13-template-version-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

function VersionNav({ template }: { readonly template: PobTemplate }) {
  const built = useBuiltPaths();
  const access = useAccess();
  const location = useLocation();
  const home = POLICY_TABS.find((tab) => tab.key === "revenue");
  const tabs: RouteTab[] = POLICY_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`policies.tabs.${tab.key}`),
    to: tab.key === "revenue" ? `${location.pathname}${location.search}` : tab.path,
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
                {t("policies.tabs.revenue")}
              </Link>
              <span aria-hidden="true">/</span>
            </li>
          )}
          <li aria-current="page" className="font-mono text-mono-sm">
            {template.code}
          </li>
        </ol>
      </nav>
      {tabs.length === 0 ? null : <RouteTabs label={t("policies.tabs.label")} tabs={tabs} />}
    </div>
  );
}

function VersionView({
  template,
  version,
  author,
}: {
  readonly template: PobTemplate;
  readonly version: PobTemplateVersion;
  readonly author: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const pane = templatePaneOf(params.get("pane"));
  const editable = author && isTemplateEditable(version);
  const approvalId = version.pending_approval_request_id ?? version.approval_request_id;
  const approval = useQuery({
    queryKey: queryKey("approvals", "tenant", { id: approvalId ?? "" }),
    queryFn: () => fetchApproval(approvalId ?? ""),
    enabled: approvalId !== null,
    retry: false,
  });
  const invalidates = [
    templateVersionKey(version.id),
    templateKey(template.id),
    EVERY_TEMPLATE,
    EVERY_TEMPLATE_VERSION,
    configTestCasesKey("pob_template_version", version.id),
    queryKey("approvals", "tenant"),
  ];
  const versionPath = templateVersionPath(version.id);
  const runTests = useCommand<PobTemplateVersion>({
    method: "POST",
    path: `${versionPath}/test`,
    invalidates,
  });
  const submitVersion = useCommand<PobTemplateVersion>({
    method: "POST",
    path: `${versionPath}/submit`,
    invalidates,
  });
  const withdraw = useCommand({
    method: "POST",
    path: `${APPROVALS_PATH}/${approvalId ?? ""}/withdraw`,
    invalidates,
  });
  const newDraft = useCommand<PobTemplateVersion>({
    method: "POST",
    path: templateVersionsPath(template.id),
    invalidates,
  });
  // SCREENS §11.0 "Refused command" (rev 1.31): "Submit for approval" checks the effective date.
  const refusal = useLifecycleRefusal(
    submitVersion.problem,
    [runTests, withdraw, newDraft].find((command) => command.problem !== null)?.problem ?? null,
  );
  const submissions = useSubmissionOrder(submitVersion.reset);
  const failed = refusal.banner;
  // PRD ERR-75: the engine chooses a template version by a contract date, so a version that replaces
  // the published one needs a date; the first version of a template keeps a free one.
  const supersedes =
    template.current_version !== null && template.current_version.id !== version.id;
  const identity = { code: template.code, version: String(version.version_no) };
  const { steps, currentId } = templateLifecycle(version, approval.data);
  const statusChip = chipFor("E-12", version.status);

  const setPane = (next: string) =>
    setParams(
      (current) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const copy = withPane(current, next === "outputs" ? null : next);
        return copy;
      },
      { replace: true },
    );
  const doTests = async () => {
    const clearEarlier = submissions.changing();
    const outcome = await runTests.submit({});
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      const evidence = outcome.data.test_evidence;
      toast.show({
        tone: evidence.failed > 0 ? "warning" : "positive",
        message: t("policies.tests.completed", {
          passed: formatNumber(evidence.passed, { kind: "count" }),
          total: formatNumber(evidence.total, { kind: "count" }),
        }),
      });
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
          code: template.code,
          version: String(outcome.data.version_no),
        }),
      });
      void navigate(templateVersionRoute(template.id, outcome.data.id));
    }
  };
  const actions = author ? (
    <>
      {editable ? (
        <>
          <Button variant="secondary" onClick={() => void doTests()}>
            {t("policies.version.runTests")}
          </Button>
          <Button variant="primary" onClick={() => void doSubmit()}>
            {t("policies.version.submit")}
          </Button>
        </>
      ) : null}
      {version.status === "SUBMITTED" && approvalId !== null ? (
        <Button variant="secondary" onClick={() => void doWithdraw()}>
          {t("policies.version.withdraw")}
        </Button>
      ) : null}
      {editable ? null : (
        <Button variant="primary" onClick={() => void doNewDraft()}>
          {t("policies.version.newDraft")}
        </Button>
      )}
    </>
  ) : undefined;

  return (
    <div
      data-testid="SF-13-template-version-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <VersionNav template={template} />
      <RecordHeader
        title={template.name}
        identifier={{
          value: template.code,
          copyLabel: t("policies.templateVersion.copyCode"),
          copiedMessage: t("policies.version.copied", { code: template.code }),
          testId: "SF-13-identifier",
        }}
        chips={
          <>
            <StatusChip status={statusChip?.status ?? version.status} />
            <OutlineChip
              label={t("policies.version.number", { version: String(version.version_no) })}
            />
          </>
        }
        actions={actions}
        banner={
          failed !== null ? (
            <RefusalBanner problem={failed} placed={refusal.placed} />
          ) : editable || !author ? undefined : (
            <Banner tone="info" announce="static" title={t("policies.version.frozen")} />
          )
        }
      />
      <Stepper label={t("policies.lifecycle.label")} steps={steps} currentId={currentId} />
      <VersionMeta
        // A new version row is a new form: its fields show what is stored.
        key={version.id}
        version={version}
        path={versionPath}
        form="date"
        supersedes={supersedes}
        required={supersedes}
        approval={approval.data}
        editable={editable}
        invalidates={invalidates}
        refusal={refusal.effective}
        onEdited={refusal.effectiveEdited}
        onSave={submissions.changing}
      />
      <PanelTabs
        label={t("policies.panes.label")}
        tabs={[
          { id: "outputs", label: t("policies.templateVersion.panes.outputs") },
          { id: "policy-values", label: t("policies.templateVersion.panes.policyValues") },
          { id: "tests", label: t("policies.panes.tests") },
          { id: "simulation", label: t("policies.panes.simulation") },
          { id: "changes", label: t("policies.panes.changes") },
        ]}
        selectedId={pane}
        onChange={setPane}
      >
        {pane === "policy-values" ? (
          <PolicyValuesPane version={version} editable={editable} invalidates={invalidates} />
        ) : pane === "tests" ? (
          <TestCasesPane version={version} />
        ) : pane === "simulation" ? (
          <SimulationPane version={version} />
        ) : pane === "changes" ? (
          <ChangesPane template={template} version={version} />
        ) : (
          <OutputsPane
            template={template}
            version={version}
            editable={editable}
            invalidates={invalidates}
          />
        )}
      </PanelTabs>
    </div>
  );
}

interface OutputsDraft {
  readonly obligation_kind: ObligationKind;
  readonly distinctness: Distinctness;
  readonly series_increment_unit: SeriesIncrementUnit | null;
  readonly satisfaction_pattern: SatisfactionPattern;
  readonly over_time_criterion: OverTimeCriterion;
  readonly recognition_method: RecognitionMethod;
  readonly ratable_convention: RatableConvention | null;
  readonly start_date_rule: StartDateRule;
  readonly end_date_rule: EndDateRule;
  readonly term_months: string;
  readonly principal_agent: PrincipalAgent;
  readonly warranty_type: WarrantyType;
  readonly licence_nature: LicenceNature;
  readonly sfc_assessment_required: boolean;
  readonly revenue_category: string;
  readonly stratification_label: string;
  readonly is_excluded_from_netting_attribution: boolean;
}

function draftOf(version: PobTemplateVersion): OutputsDraft {
  return {
    obligation_kind: version.obligation_kind,
    distinctness: version.distinctness,
    series_increment_unit: version.series_increment_unit,
    satisfaction_pattern: version.satisfaction_pattern,
    over_time_criterion: version.over_time_criterion,
    recognition_method: version.recognition_method,
    ratable_convention: version.ratable_convention,
    start_date_rule: version.start_date_rule,
    end_date_rule: version.end_date_rule,
    term_months: version.term_months === null ? "" : String(version.term_months),
    principal_agent: version.principal_agent,
    warranty_type: version.warranty_type,
    licence_nature: version.licence_nature,
    sfc_assessment_required: version.sfc_assessment_required,
    revenue_category: version.revenue_category ?? "",
    stratification_label: version.stratification_label ?? "",
    is_excluded_from_netting_attribution: version.is_excluded_from_netting_attribution,
  };
}

/** The `PATCH` body of the fields the draft changed (SCREENS §11.2 outputs form). */
export function outputsPatch(
  version: PobTemplateVersion,
  draft: OutputsDraft,
): PobTemplateVersionUpdate {
  const series = draft.distinctness === "series";
  const overTime = draft.satisfaction_pattern === "OVER_TIME";
  const timeElapsed = draft.recognition_method === "TIME_ELAPSED";
  const startPlusTerm = draft.end_date_rule === "START_PLUS_TERM";
  const next = {
    obligation_kind: draft.obligation_kind,
    distinctness: draft.distinctness,
    series_increment_unit: series ? (draft.series_increment_unit ?? "day") : null,
    satisfaction_pattern: draft.satisfaction_pattern,
    over_time_criterion: overTime
      ? draft.over_time_criterion
      : ("NOT_APPLICABLE" as OverTimeCriterion),
    recognition_method: draft.recognition_method,
    ratable_convention: timeElapsed ? (draft.ratable_convention ?? "DAILY") : null,
    start_date_rule: draft.start_date_rule,
    end_date_rule: draft.end_date_rule,
    term_months:
      startPlusTerm && draft.term_months.trim() !== "" ? Number(draft.term_months) : null,
    principal_agent: draft.principal_agent,
    warranty_type: draft.warranty_type,
    licence_nature: draft.licence_nature,
    sfc_assessment_required: draft.sfc_assessment_required,
    revenue_category: draft.revenue_category.trim() === "" ? null : draft.revenue_category.trim(),
    stratification_label:
      draft.stratification_label.trim() === "" ? null : draft.stratification_label.trim(),
    is_excluded_from_netting_attribution: draft.is_excluded_from_netting_attribution,
  };
  const patch: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(next)) {
    if (version[field as OutputField] !== value) {
      patch[field] = value;
    }
  }
  return patch as PobTemplateVersionUpdate;
}

/** The output fields that show a message of the API: every one but the two switches. */
type OutputControl = Exclude<
  OutputField,
  "sfc_assessment_required" | "is_excluded_from_netting_attribution"
>;

/**
 * docs/dev-guide.md DG-FE-06: the fields of the outputs form, each named as the member it sends. Four
 * are on screen only for the choice they belong to, and a field that is not on screen takes no member:
 * an error there is the banner's, as is one on a switch or on the account role overrides.
 */
function outputMembers(shown: {
  readonly series: boolean;
  readonly overTime: boolean;
  readonly timeElapsed: boolean;
  readonly startPlusTerm: boolean;
}): Readonly<Record<OutputControl, readonly string[]>> {
  return {
    obligation_kind: ["obligation_kind"],
    distinctness: ["distinctness"],
    series_increment_unit: shown.series ? ["series_increment_unit"] : [],
    satisfaction_pattern: ["satisfaction_pattern"],
    over_time_criterion: shown.overTime ? ["over_time_criterion"] : [],
    recognition_method: ["recognition_method"],
    ratable_convention: shown.timeElapsed ? ["ratable_convention"] : [],
    start_date_rule: ["start_date_rule"],
    end_date_rule: ["end_date_rule"],
    term_months: shown.startPlusTerm ? ["term_months"] : [],
    principal_agent: ["principal_agent"],
    warranty_type: ["warranty_type"],
    licence_nature: ["licence_nature"],
    revenue_category: ["revenue_category"],
    stratification_label: ["stratification_label"],
  };
}

function OutputsPane({
  template,
  version,
  editable,
  invalidates,
}: {
  readonly template: PobTemplate;
  readonly version: PobTemplateVersion;
  readonly editable: boolean;
  readonly invalidates: readonly ReturnType<typeof queryKey>[];
}) {
  const toast = useToast();
  const formId = useId();
  const radioId = useId();
  const [draft, setDraft] = useState<OutputsDraft>(() => draftOf(version));
  const [attempted, setAttempted] = useState(false);
  const save = useCommand<PobTemplateVersion>({
    method: "PATCH",
    path: templateVersionPath(version.id),
    invalidates,
  });
  const patch = outputsPatch(version, draft);
  const dirty = Object.keys(patch).length > 0;
  const series = draft.distinctness === "series";
  const overTime = draft.satisfaction_pattern === "OVER_TIME";
  const timeElapsed = draft.recognition_method === "TIME_ELAPSED";
  const startPlusTerm = draft.end_date_rule === "START_PLUS_TERM";
  const placed = useMemo(
    () =>
      placeProblem(save.problem, outputMembers({ series, overTime, timeElapsed, startPlusTerm })),
    [save.problem, series, overTime, timeElapsed, startPlusTerm],
  );
  const termError =
    attempted && startPlusTerm && !/^\d+$/.test(draft.term_months.trim())
      ? t("policies.templateVersion.outputs.termRequired")
      : placed.fields.term_months;
  const methods = overTime ? RECOGNITION_METHODS : POINT_IN_TIME_METHODS;
  const update = (change: Partial<OutputsDraft>) =>
    setDraft((previous) => ({ ...previous, ...change }));
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (!editable || !dirty || (startPlusTerm && !/^\d+$/.test(draft.term_months.trim()))) {
      return;
    }
    const outcome = await save.submit(patch, { ifMatch: rowIfMatch(version.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.templateVersion.outputs.saved", {
          code: template.code,
          version: String(version.version_no),
        }),
      });
    }
  };
  const select = <T extends string>(
    field: OutputControl,
    label: string,
    options: readonly T[],
    value: T | null,
    labelOf: (value: T) => string,
    onChange: (value: T) => void,
    help?: string,
  ) => (
    <Field name={field} label={label} error={placed.fields[field]} help={help} width="text">
      {(control) =>
        editable ? (
          <Select<T>
            control={control}
            options={options.map((option) => ({ value: option, label: labelOf(option) }))}
            value={value}
            onChange={onChange}
          />
        ) : (
          <output {...control} className="block py-1.5 text-body-sm text-fg-1">
            {value === null ? NO_VALUE : labelOf(value)}
          </output>
        )
      }
    </Field>
  );
  const radios = <T extends string>(
    name: string,
    label: string,
    options: readonly T[],
    value: T,
    labelOf: (value: T) => string,
    onChange: (value: T) => void,
  ) => (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-body-sm font-medium text-fg-1">{label}</legend>
      <div className="flex flex-wrap items-center gap-6">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              type="radio"
              name={`${name}-${radioId}`}
              value={option}
              checked={value === option}
              disabled={!editable}
              onChange={() => onChange(option)}
              className="size-4"
            />
            {labelOf(option)}
          </label>
        ))}
      </div>
    </fieldset>
  );
  const checkbox = (field: keyof OutputsDraft & string, label: string, value: boolean) => (
    <label className="flex items-center gap-2 text-body-sm text-fg-1">
      <input
        type="checkbox"
        checked={value}
        disabled={!editable}
        onChange={(event) => update({ [field]: event.target.checked } as Partial<OutputsDraft>)}
        className="size-4"
      />
      {label}
    </label>
  );
  return (
    <form
      id={formId}
      noValidate
      aria-label={t("policies.templateVersion.outputs.form")}
      data-testid="SF-13-pane-template-outputs"
      onSubmit={(event) => void submit(event)}
      className="flex flex-col gap-4 pt-3"
    >
      <RefusalBanner problem={save.problem} placed={placed} />
      <div className="grid gap-4 md:grid-cols-2">
        {select(
          "obligation_kind",
          t("policies.templateVersion.outputs.kind"),
          OBLIGATION_KINDS,
          draft.obligation_kind,
          kindLabel,
          (value) => update({ obligation_kind: value }),
        )}
        {radios(
          "distinctness",
          t("policies.templateVersion.outputs.distinctness"),
          DISTINCTNESS_VALUES,
          draft.distinctness,
          (value) => t(`policies.template.distinctness.${value}`),
          (value) => update({ distinctness: value }),
        )}
        {series
          ? select(
              "series_increment_unit",
              t("policies.templateVersion.outputs.seriesUnit"),
              SERIES_UNITS,
              draft.series_increment_unit ?? "day",
              (value) => t(`policies.template.seriesUnit.${value}`),
              (value) => update({ series_increment_unit: value }),
              t("policies.templateVersion.outputs.seriesUnitHelp"),
            )
          : null}
        {radios(
          "satisfaction_pattern",
          t("policies.templateVersion.outputs.pattern"),
          SATISFACTION_PATTERNS,
          draft.satisfaction_pattern,
          (value) => t(`policies.template.satisfaction.${value}`),
          (value) =>
            update({
              satisfaction_pattern: value,
              recognition_method:
                value === "OVER_TIME" || POINT_IN_TIME_METHODS.includes(draft.recognition_method)
                  ? draft.recognition_method
                  : "POINT_IN_TIME",
            }),
        )}
        {overTime
          ? select(
              "over_time_criterion",
              t("policies.templateVersion.outputs.criterion"),
              OVER_TIME_CRITERIA,
              draft.over_time_criterion === "NOT_APPLICABLE" ? "OT_A" : draft.over_time_criterion,
              (value) => t(`policies.template.criterion.${value}`),
              (value) => update({ over_time_criterion: value }),
              t("policies.templateVersion.outputs.criterionHelp"),
            )
          : null}
        {select(
          "recognition_method",
          t("policies.templateVersion.outputs.method"),
          methods,
          draft.recognition_method,
          methodLabel,
          (value) => update({ recognition_method: value }),
        )}
        {timeElapsed
          ? select(
              "ratable_convention",
              t("policies.templateVersion.outputs.convention"),
              RATABLE_CONVENTIONS,
              draft.ratable_convention ?? "DAILY",
              (value) => t(`policies.template.convention.${value}`),
              (value) => update({ ratable_convention: value }),
              t("policies.templateVersion.outputs.conventionHelp"),
            )
          : null}
        {select(
          "start_date_rule",
          t("policies.templateVersion.outputs.startRule"),
          START_DATE_RULES,
          draft.start_date_rule,
          (value) => t(`policies.template.startRule.${value}`),
          (value) => update({ start_date_rule: value }),
        )}
        {select(
          "end_date_rule",
          t("policies.templateVersion.outputs.endRule"),
          END_DATE_RULES,
          draft.end_date_rule,
          (value) => t(`policies.template.endRule.${value}`),
          (value) => update({ end_date_rule: value }),
        )}
        {startPlusTerm ? (
          <Field
            name="term_months"
            label={t("policies.templateVersion.outputs.termMonths")}
            required
            error={termError}
            width="money"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                inputMode="numeric"
                readOnly={!editable}
                value={draft.term_months}
                onChange={(event) => update({ term_months: event.target.value })}
                className={`${controlClass(termError !== null)} num`}
              />
            )}
          </Field>
        ) : null}
        {select(
          "principal_agent",
          t("policies.templateVersion.outputs.principalAgent"),
          PRINCIPAL_AGENT_VALUES,
          draft.principal_agent,
          (value) => t(`policies.template.principalAgent.${value}`),
          (value) => update({ principal_agent: value }),
        )}
        {select(
          "warranty_type",
          t("policies.templateVersion.outputs.warranty"),
          WARRANTY_TYPES,
          draft.warranty_type,
          (value) => t(`policies.template.warranty.${value}`),
          (value) => update({ warranty_type: value }),
        )}
        {select(
          "licence_nature",
          t("policies.templateVersion.outputs.licence"),
          LICENCE_NATURES,
          draft.licence_nature,
          (value) => t(`policies.template.licence.${value}`),
          (value) => update({ licence_nature: value }),
        )}
        <Field
          name="revenue_category"
          label={t("policies.templateVersion.outputs.revenueCategory")}
          optional
          error={placed.fields.revenue_category}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={!editable}
              value={draft.revenue_category}
              onChange={(event) => update({ revenue_category: event.target.value })}
              className={`${controlClass(false)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="stratification_label"
          label={t("policies.templateVersion.outputs.stratification")}
          optional
          error={placed.fields.stratification_label}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={!editable}
              value={draft.stratification_label}
              onChange={(event) => update({ stratification_label: event.target.value })}
              className={controlClass(false)}
            />
          )}
        </Field>
      </div>
      {checkbox(
        "sfc_assessment_required",
        t("policies.templateVersion.outputs.sfc"),
        draft.sfc_assessment_required,
      )}
      {checkbox(
        "is_excluded_from_netting_attribution",
        t("policies.templateVersion.outputs.nettingExcluded"),
        draft.is_excluded_from_netting_attribution,
      )}
      <section
        aria-label={t("policies.templateVersion.outputs.overrides")}
        className="flex flex-col gap-1"
      >
        <h3 className="text-body-sm font-medium text-fg-1">
          {t("policies.templateVersion.outputs.overrides")}
        </h3>
        {Object.keys(version.account_role_overrides).length === 0 ? (
          <p className="text-body-sm text-fg-3">
            {t("policies.templateVersion.outputs.overridesNone")}
          </p>
        ) : (
          <ul className="flex flex-col gap-1 text-body-sm">
            {Object.entries(version.account_role_overrides).map(([role, account]) => (
              <li key={role} className="flex items-center gap-2">
                {mono(role)}
                <span className="text-fg-3">→</span>
                {mono(account)}
              </li>
            ))}
          </ul>
        )}
      </section>
      {editable ? (
        <div>
          <Button
            variant="primary"
            type="submit"
            form={formId}
            disabledReason={dirty ? undefined : t("policies.templateVersion.outputs.noChanges")}
          >
            {t("policies.templateVersion.outputs.save")}
          </Button>
        </div>
      ) : null}
    </form>
  );
}

function PolicyValuesPane({
  version,
  editable,
  invalidates,
}: {
  readonly version: PobTemplateVersion;
  readonly editable: boolean;
  readonly invalidates: readonly ReturnType<typeof queryKey>[];
}) {
  const toast = useToast();
  const keyId = useId();
  const parameters = useParameters();
  const [values, setValues] = useState<Readonly<Record<string, string>>>(() =>
    Object.fromEntries(
      Object.entries(version.policy_values).map(([key, value]) => [
        key,
        typeof value === "string" ? value : JSON.stringify(value),
      ]),
    ),
  );
  const [newKey, setNewKey] = useState<string | null>(null);
  const save = useCommand<PobTemplateVersion>({
    method: "PATCH",
    path: templateVersionPath(version.id),
    invalidates,
  });
  const candidates = productLevelParameters(parameters.data ?? []).filter(
    (parameter) => !(parameter.code in values),
  );
  const approvalCode = (key: string) =>
    parameters.data?.find((parameter) => parameter.code === key)?.approval_code ?? NO_VALUE;
  const stored = JSON.stringify(
    Object.fromEntries(
      Object.entries(version.policy_values).map(([key, value]) => [
        key,
        typeof value === "string" ? value : JSON.stringify(value),
      ]),
    ),
  );
  const dirty = JSON.stringify(values) !== stored;
  const submit = async () => {
    const body: PobTemplateVersionUpdate = {
      policy_values: Object.fromEntries(
        Object.entries(values).map(([key, text]) => {
          try {
            return [key, JSON.parse(text) as unknown];
          } catch {
            return [key, text];
          }
        }),
      ),
    };
    const outcome = await save.submit(body, { ifMatch: rowIfMatch(version.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.templateVersion.values.saved") });
    }
  };
  return (
    <div className="flex flex-col gap-3 pt-3" data-testid="SF-13-pane-template-policy-values">
      <RefusalBanner problem={save.problem} />
      {Object.keys(values).length === 0 ? (
        <p className="text-body-sm text-fg-3">{t("policies.templateVersion.values.empty")}</p>
      ) : (
        <table
          aria-label={t("policies.templateVersion.panes.policyValues")}
          className="w-full text-body-sm"
        >
          <thead>
            <tr className="border-b border-hairline text-caption text-fg-3">
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("policies.templateVersion.values.key")}
              </th>
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("policies.templateVersion.values.value")}
              </th>
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("policies.templateVersion.values.approval")}
              </th>
              {editable ? (
                <th scope="col" className="py-2 text-start font-medium">
                  {t("policies.templateVersion.values.actions")}
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {Object.entries(values).map(([key, text]) => (
              <tr key={key} className="border-b border-hairline last:border-b-0">
                <th scope="row" className="py-2 pe-4 text-start font-normal">
                  {mono(key)}
                </th>
                <td className="py-2 pe-4">
                  {editable ? (
                    <input
                      type="text"
                      aria-label={t("policies.templateVersion.values.valueOf", { key })}
                      value={text}
                      onChange={(event) => setValues({ ...values, [key]: event.target.value })}
                      className={`${controlClass(false)} font-mono`}
                    />
                  ) : (
                    mono(text)
                  )}
                </td>
                <td className="py-2 pe-4">{mono(approvalCode(key))}</td>
                {editable ? (
                  <td className="py-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setValues(
                          Object.fromEntries(
                            Object.entries(values).filter(([candidate]) => candidate !== key),
                          ),
                        )
                      }
                    >
                      {t("policies.templateVersion.values.remove")}
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editable ? (
        <div className="flex flex-wrap items-end gap-3">
          <Field
            name={`policy-key-${keyId}`}
            label={t("policies.templateVersion.values.key")}
            width="text"
          >
            {(control) => (
              <Combobox
                control={control}
                options={candidates.map((parameter) => ({
                  value: parameter.code,
                  label: `${parameter.code} · ${parameter.description}`,
                }))}
                value={newKey}
                onChange={setNewKey}
              />
            )}
          </Field>
          <Button
            variant="secondary"
            size="sm"
            disabledReason={
              newKey === null ? t("policies.templateVersion.values.chooseKey") : undefined
            }
            onClick={() => {
              if (newKey !== null) {
                setValues({ ...values, [newKey]: "" });
                setNewKey(null);
              }
            }}
          >
            {t("policies.templateVersion.values.add")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabledReason={dirty ? undefined : t("policies.templateVersion.outputs.noChanges")}
            onClick={() => void submit()}
          >
            {t("policies.templateVersion.values.save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function TestCasesPane({ version }: { readonly version: PobTemplateVersion }) {
  const source: GridSource<ConfigTestCase> = {
    queryKey: configTestCasesKey("pob_template_version", version.id),
    fetchPage: (cursor, sort) =>
      fetchConfigTestCasesPage("pob_template_version", version.id, cursor, sort),
  };
  const columns: readonly GridColumn<ConfigTestCase>[] = [
    {
      id: "name",
      header: t("policies.tests.column.name"),
      kind: "identifier",
      value: (item) => item.name,
      width: 200,
    },
    {
      id: "input",
      header: t("policies.tests.column.input"),
      kind: "text",
      value: (item) => jsonSummary(item.input),
      width: 280,
    },
    {
      id: "expected",
      header: t("policies.tests.column.expected"),
      kind: "text",
      value: (item) => jsonSummary(item.expected_output),
      width: 280,
    },
    {
      id: "result",
      header: t("policies.tests.column.result"),
      kind: "status",
      value: (item) => caseResultWord(item.last_result),
      width: 120,
    },
    {
      id: "last_run",
      header: t("policies.tests.column.lastRun"),
      kind: "timestamp",
      value: (item) => item.last_run_at,
    },
  ];
  return (
    <div className="flex min-h-0 flex-col gap-3 pt-3" data-testid="SF-13-pane-template-tests">
      <p className="text-body-sm text-fg-3">{t("policies.templateVersion.tests.readOnly")}</p>
      <DataGrid<ConfigTestCase>
        name="template-test-cases"
        title={t("policies.tests.title")}
        countLabel={(count, formatted) => t("policies.tests.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        testIdPrefix="SF-13"
        rowTestKey={(item) => item.name}
        emptyState={
          <EmptyState
            title={t("policies.tests.empty.title")}
            description={t("policies.tests.empty.description")}
          />
        }
      />
    </div>
  );
}

function SimulationPane({ version }: { readonly version: PobTemplateVersion }) {
  const evidence = version.test_evidence;
  return (
    <div className="flex flex-col gap-2 pt-3" data-testid="SF-13-pane-simulation">
      <p className="text-body-sm text-fg-1">
        {evidence.total === 0
          ? t("policies.templateVersion.simulation.noTests")
          : t("policies.templateVersion.simulation.cases", {
              passed: formatNumber(evidence.passed, { kind: "count" }),
              total: formatNumber(evidence.total, { kind: "count" }),
            })}
      </p>
      {evidence.last_run_at === null ? null : (
        <p className="text-body-sm text-fg-3">
          {t("policies.templateVersion.simulation.lastRun", {
            timestamp: formatTimestamp(evidence.last_run_at),
          })}
        </p>
      )}
      <p className="text-body-sm text-fg-3">{t("policies.templateVersion.simulation.none")}</p>
    </div>
  );
}

function ChangesPane({
  template,
  version,
}: {
  readonly template: PobTemplate;
  readonly version: PobTemplateVersion;
}) {
  const previousId = version.supersedes_version_id;
  const previous = useQuery({
    queryKey: templateVersionKey(previousId ?? ""),
    queryFn: () => fetchTemplateVersion(previousId ?? ""),
    enabled: previousId !== null,
  });
  let body: ReactNode;
  if (previousId === null) {
    body = <p className="text-body-sm text-fg-3">{t("policies.templateVersion.changes.first")}</p>;
  } else if (previous.isError) {
    body = <Banner tone="negative" title={t("policies.templateVersion.loadError")} />;
  } else if (previous.data === undefined) {
    body = <Skeleton region={t("policies.panes.changes")} shape="rows" count={3} />;
  } else {
    const changes = outputChanges(version, previous.data);
    body =
      changes.length === 0 ? (
        <p className="text-body-sm text-fg-3">{t("policies.templateVersion.changes.none")}</p>
      ) : (
        <table aria-label={t("policies.panes.changes")} className="w-full text-body-sm">
          <thead>
            <tr className="border-b border-hairline text-caption text-fg-3">
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("policies.templateVersion.changes.field")}
              </th>
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("policies.templateVersion.changes.before")}
              </th>
              <th scope="col" className="py-2 text-start font-medium">
                {t("policies.templateVersion.changes.after")}
              </th>
            </tr>
          </thead>
          <tbody>
            {changes.map((change) => (
              <tr key={change.field} className="border-b border-hairline last:border-b-0">
                <th scope="row" className="py-2 pe-4 text-start font-normal">
                  {mono(change.field)}
                </th>
                <td className="py-2 pe-4 text-fg-2">{outputText(change.field, change.before)}</td>
                <td className="py-2 text-fg-1">{outputText(change.field, change.after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      );
  }
  return (
    <div className="flex flex-col gap-2 pt-3" data-testid="SF-13-pane-changes">
      {previousId === null || previous.data === undefined ? null : (
        <p className="text-body-sm text-fg-2">
          {t("policies.templateVersion.changes.supersedes", {
            version: String(previous.data.version_no),
          })}{" "}
          <Link
            to={templateVersionRoute(template.id, previousId)}
            className="text-accent-fg hover:underline"
          >
            {t("policies.version.number", { version: String(previous.data.version_no) })}
          </Link>
        </p>
      )}
      {body}
    </div>
  );
}

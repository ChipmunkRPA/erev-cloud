// SF-13:account-mapping-version Account mapping version editor (SCREENS §11.0 lifecycle pattern, §11.6;
// §0.4 RT-70; §0.5 `pane=rules|coverage|resolve|simulation|changes`; §0.7 SCR-ST-05, SCR-ST-07,
// SCR-PERM-01; DESIGN_SYSTEM DS-CMP-06, DS-CMP-09, DS-CMP-10, DS-CMP-16, DS-CMP-19, DS-CMP-21; 04
// API-R-20 `GET, PATCH /account-mappings/{id}` (`If-Match`), `POST …/test`, `/submit`, `GET, POST
// …/rules`, `DELETE …/rules/{rule_id}`, `GET /account-mappings/resolve`, API-R-12 `GET
// /files/{id}/content`, API-R-09 `POST /approvals/{id}/withdraw`; REQ-REF-008, REQ-JE-022; BUILD_SPEC
// RFD-25). Breadcrumb "Policies / Account mapping / <name>", the Policies route tabs, the record header
// (name, status, version and effective chips, the §11.0 commands for `config.author`), the lifecycle
// stepper and the panes Rules (DataGrid "Mapping rules"; "Add rule" drawer and "Remove rule" while DRAFT
// or TESTED — the API creates and deletes rules, so a change is a remove and an add), Coverage (table
// "Role coverage", 38 rows computed from the loaded rules), Test resolution (`GET /account-mappings
// /resolve`), Simulation (the impact file of the last test) and Changes (rules added and removed
// against the superseded version). The approval publishes (D-76).
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
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { RecordHeader } from "../../components/record/RecordHeader";
import { type Step, Stepper } from "../../components/record/Stepper";
import { withPane } from "../../components/record/pane-params";
import { PanelTabs, type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  type AccountMapping,
  type AccountMappingRule,
  type AccountMappingUpdate,
  ACCOUNT_MAPPING_ROUTE,
  ACCOUNT_MAPPINGS_PATH,
  type AccountResolution,
  type AccountRole,
  BILLING_CLEARING,
  CLEARING_PURPOSES,
  type ClearingPurpose,
  coverageRows,
  EMPTY_RULE_DRAFT,
  EVERY_ACCOUNT_MAPPING,
  fetchAllRules,
  fetchMapping,
  isMappingEditable,
  MAPPABLE_ROLES,
  mappingCommandPath,
  mappingKey,
  mappingPaneOf,
  mappingPath,
  mappingVersionRoute,
  resolveAccount,
  type ResolveQuery,
  ruleChanges,
  type RuleDraft,
  ruleDraftErrors,
  ruleInput,
  rulePath,
  rulesKey,
  rulesPath,
  useMapping,
} from "../../lib/api/queries/account-mappings";
import { fetchAllAccounts, type GlAccount } from "../../lib/api/queries/accounts";
import { fileContentPath } from "../../lib/api/queries/access-reviews";
import { type Approval, APPROVALS_PATH, fetchApproval } from "../../lib/api/queries/approvals";
import { BOOK_CODES, bookLabel } from "../../lib/api/queries/entities";
import { useMe } from "../../lib/api/queries/me";
import { allProductsKey, fetchAllProducts } from "../../lib/api/queries/products";
import { CONFIG_AUTHOR_PERMISSION, CONFIG_READ_PERMISSION } from "../../lib/api/queries/rule-sets";
import {
  type BookCode,
  entitiesKey,
  fetchActiveEntities,
  rowIfMatch,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { placeProblem } from "../../lib/api/refusals";
import {
  effectiveInstant,
  formatDate,
  formatNumber,
  NO_VALUE,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { POLICY_TABS } from "./revenue";
import { approverNames } from "./version-meta";

function mono(text: string | null): ReactNode {
  return text === null || text === "" ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="font-mono text-mono">{text}</span>
  );
}

export function roleLabel(role: AccountRole): string {
  return t(`accountRole.${role}`);
}

export function purposeLabel(purpose: ClearingPurpose): string {
  return t(`policies.mapping.clearingPurpose.${purpose}`);
}

/** SCREENS §11.0 lifecycle steps of a mapping version (no example-case evidence on API-S-AccountMapping). */
export function mappingLifecycle(
  mapping: AccountMapping,
  approval: Approval | undefined,
): { readonly steps: readonly Step[]; readonly currentId: string } {
  const approvers = approverNames(approval);
  const decided =
    mapping.status === "APPROVED" ||
    mapping.status === "PUBLISHED" ||
    mapping.status === "SUPERSEDED";
  let approvalCaption: string | undefined;
  if (mapping.status === "SUBMITTED") {
    approvalCaption = t("policies.lifecycle.pending");
  } else if (decided && approvers.length > 0) {
    approvalCaption = t("policies.lifecycle.approvedBy", { name: approvers.join(", ") });
  } else if (mapping.status === "REJECTED") {
    approvalCaption = t("policies.lifecycle.rejected");
  } else if (mapping.status === "WITHDRAWN") {
    approvalCaption = t("policies.lifecycle.withdrawn");
  }
  const order: Readonly<Record<AccountMapping["status"], number>> = {
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
  const reached = order[mapping.status];
  const state = (index: number): Step["state"] => {
    if (index < reached) {
      return "complete";
    }
    if (index === reached) {
      if (mapping.status === "REJECTED") {
        return "error";
      }
      if (mapping.status === "WITHDRAWN") {
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
        date: formatDate(timestampDate(mapping.updated_at)),
      }),
    },
    { id: "tested", label: t("policies.lifecycle.tested"), state: state(1) },
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
        mapping.effective_from === null
          ? undefined
          : t("policies.lifecycle.effective", {
              date: formatDate(timestampDate(mapping.effective_from)),
            }),
    },
  ];
  const currentId = (["draft", "tested", "approval", "published"] as const)[Math.min(reached, 3)];
  return { steps, currentId: currentId ?? "draft" };
}

export function AccountMappingVersionEditor() {
  const { mappingVersionId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const mapping = useMapping(mappingVersionId);
  const title = t("policies.mappingVersion.documentTitle");

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
  } else if (mapping.isError) {
    body =
      mapping.error instanceof ApiProblem && mapping.error.status === 404 ? (
        <div data-testid="SF-13-account-mapping-version-not-found">
          <EmptyState
            title={t("policies.mappingVersion.notFound.title")}
            description={t("policies.version.notFound.description")}
            link={{ label: t("policies.tabs.accountMapping"), href: ACCOUNT_MAPPING_ROUTE }}
          />
        </div>
      ) : (
        <Banner tone="negative" title={t("policies.mappingVersion.loadError")} />
      );
  } else if (mapping.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else {
    return (
      <VersionView mapping={mapping.data} author={access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION)} />
    );
  }
  return (
    <div
      data-testid="SF-13-account-mapping-version-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

function VersionNav({ mapping }: { readonly mapping: AccountMapping }) {
  const built = useBuiltPaths();
  const access = useAccess();
  const location = useLocation();
  const tabs: RouteTab[] = POLICY_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`policies.tabs.${tab.key}`),
    to: tab.key === "accountMapping" ? `${location.pathname}${location.search}` : tab.path,
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
            <Link to={ACCOUNT_MAPPING_ROUTE} className="hover:text-fg-1 hover:underline">
              {t("policies.tabs.accountMapping")}
            </Link>
            <span aria-hidden="true">/</span>
          </li>
          <li aria-current="page" className="font-mono text-mono-sm">
            {mapping.name}
          </li>
        </ol>
      </nav>
      {tabs.length === 0 ? null : <RouteTabs label={t("policies.tabs.label")} tabs={tabs} />}
    </div>
  );
}

function VersionView({
  mapping,
  author,
}: {
  readonly mapping: AccountMapping;
  readonly author: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const pane = mappingPaneOf(params.get("pane"));
  const editable = author && isMappingEditable(mapping);
  const approvalId = mapping.pending_approval_request_id ?? mapping.approval_request_id;
  const approval = useQuery({
    queryKey: queryKey("approvals", "tenant", { id: approvalId ?? "" }),
    queryFn: () => fetchApproval(approvalId ?? ""),
    enabled: approvalId !== null,
    retry: false,
  });
  const rules = useQuery({
    queryKey: rulesKey(mapping.id),
    queryFn: () => fetchAllRules(mapping.id),
  });
  const invalidates = [
    mappingKey(mapping.id),
    rulesKey(mapping.id),
    EVERY_ACCOUNT_MAPPING,
    queryKey("approvals", "tenant"),
  ];
  const runTests = useCommand<AccountMapping>({
    method: "POST",
    path: mappingCommandPath(mapping.id, "test"),
    invalidates,
  });
  const submitVersion = useCommand<AccountMapping>({
    method: "POST",
    path: mappingCommandPath(mapping.id, "submit"),
    invalidates,
  });
  const withdraw = useCommand({
    method: "POST",
    path: `${APPROVALS_PATH}/${approvalId ?? ""}/withdraw`,
    invalidates,
  });
  const newDraft = useCommand<AccountMapping>({
    method: "POST",
    path: ACCOUNT_MAPPINGS_PATH,
    invalidates: [EVERY_ACCOUNT_MAPPING],
  });
  const failed =
    [runTests, submitVersion, withdraw, newDraft].find((command) => command.problem !== null)
      ?.problem ?? null;
  const identity = { name: mapping.name, version: String(mapping.version_no) };
  const { steps, currentId } = mappingLifecycle(mapping, approval.data);
  const [adding, setAdding] = useState(false);

  const setPane = (next: string) =>
    setParams(
      (current) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const copy = withPane(current, next === "rules" ? null : next);
        return copy;
      },
      { replace: true },
    );
  const doTests = async () => {
    const outcome = await runTests.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.mappingVersion.tested", identity) });
    }
  };
  const doSubmit = async () => {
    const outcome = await submitVersion.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.mappingVersion.submitted", identity) });
    }
  };
  const doWithdraw = async () => {
    const outcome = await withdraw.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.mappingVersion.withdrawn", identity) });
    }
  };
  const doNewDraft = async () => {
    const outcome = await newDraft.submit({ name: mapping.name, source_version_id: mapping.id });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("policies.mapping.newDialog.created", {
          name: outcome.data.name,
          version: String(outcome.data.version_no),
        }),
      });
      void navigate(mappingVersionRoute(outcome.data.id));
    }
  };
  const actions = author ? (
    <>
      {editable ? (
        <>
          <Button variant="secondary" onClick={() => void doTests()}>
            {t("policies.version.runTests")}
          </Button>
          <Button
            variant="primary"
            onClick={() => void doSubmit()}
            disabledReason={
              mapping.effective_from === null ? t("policies.version.effectiveRequired") : undefined
            }
          >
            {t("policies.version.submit")}
          </Button>
        </>
      ) : null}
      {mapping.status === "SUBMITTED" && approvalId !== null ? (
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
      data-testid="SF-13-account-mapping-version-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <VersionNav mapping={mapping} />
      <RecordHeader
        title={mapping.name}
        chips={
          <>
            <StatusChip status={chipFor("E-12", mapping.status)?.status ?? mapping.status} />
            <OutlineChip
              label={t("policies.version.number", { version: String(mapping.version_no) })}
            />
            {mapping.effective_from === null ? null : (
              <OutlineChip
                label={t("policies.lifecycle.effective", {
                  date: formatDate(timestampDate(mapping.effective_from)),
                })}
              />
            )}
          </>
        }
        actions={actions}
        banner={
          failed !== null ? (
            <Banner tone="negative" title={failed.detail ?? failed.title} />
          ) : editable || !author ? undefined : (
            <Banner tone="info" announce="static" title={t("policies.version.frozen")} />
          )
        }
      />
      <Stepper label={t("policies.lifecycle.label")} steps={steps} currentId={currentId} />
      {editable ? <EffectiveDate mapping={mapping} invalidates={invalidates} /> : null}
      <PanelTabs
        label={t("policies.panes.label")}
        tabs={[
          {
            id: "rules",
            label: t("policies.mappingVersion.panes.rules"),
            count: rules.data?.length,
          },
          { id: "coverage", label: t("policies.mappingVersion.panes.coverage") },
          { id: "resolve", label: t("policies.mappingVersion.panes.resolve") },
          { id: "simulation", label: t("policies.panes.simulation") },
          { id: "changes", label: t("policies.panes.changes") },
        ]}
        selectedId={pane}
        onChange={setPane}
      >
        {pane === "coverage" ? (
          <CoveragePane rules={rules.data} />
        ) : pane === "resolve" ? (
          <ResolvePane />
        ) : pane === "simulation" ? (
          <SimulationPane mapping={mapping} />
        ) : pane === "changes" ? (
          <ChangesPane mapping={mapping} rules={rules.data} />
        ) : (
          <RulesPane
            mapping={mapping}
            editable={editable}
            invalidates={invalidates}
            onAdd={() => setAdding(true)}
          />
        )}
      </PanelTabs>
      {adding ? (
        <RuleDrawer mapping={mapping} invalidates={invalidates} onClose={() => setAdding(false)} />
      ) : null}
    </div>
  );
}

// docs/dev-guide.md DG-FE-06: the field of "Save effective date" and the fields of "Add rule" that show
// a message of the API, each with the member it sends. The entity, the book, the product and the
// revenue category of a rule show none: an error there is the banner's.
const EFFECTIVE_MEMBERS = { effective: ["effective_from"] } as const;
const MAPPING_RULE_MEMBERS = {
  role: ["account_role"],
  purpose: ["clearing_purpose"],
  account: ["gl_account_id"],
  priority: ["priority"],
} as const;

function EffectiveDate({
  mapping,
  invalidates,
}: {
  readonly mapping: AccountMapping;
  readonly invalidates: readonly ReturnType<typeof queryKey>[];
}) {
  const toast = useToast();
  // 04 SC-V `effective_from` is an instant; the field edits its UTC date (DS-FMT-17).
  const initial = mapping.effective_from === null ? null : timestampDate(mapping.effective_from);
  const [text, setText] = useState(initial === null ? "" : formatDate(initial));
  const [date, setDate] = useState<string | null>(initial);
  const save = useCommand<AccountMapping>({
    method: "PATCH",
    path: mappingPath(mapping.id),
    invalidates,
  });
  const placed = useMemo(() => placeProblem(save.problem, EFFECTIVE_MEMBERS), [save.problem]);
  const dirty = date !== initial;
  return (
    <div className="flex flex-col gap-3">
      {/* The save had no banner: a refusal that named no date was shown nowhere. */}
      <RefusalBanner problem={save.problem} placed={placed} conflict={save.banner} />
      <div className="flex flex-wrap items-end gap-3">
        <Field
          name="effective_from"
          label={t("policies.mapping.newDialog.effectiveFrom")}
          error={placed.fields.effective}
          width="date"
        >
          {(control) => (
            <DateInput control={control} value={text} onChange={setText} onValue={setDate} />
          )}
        </Field>
        <Button
          variant="secondary"
          size="sm"
          disabledReason={dirty ? undefined : t("policies.templateVersion.outputs.noChanges")}
          onClick={() =>
            void (async () => {
              const outcome = await save.submit(
                {
                  effective_from: date === null ? null : effectiveInstant(date),
                } satisfies AccountMappingUpdate,
                { ifMatch: rowIfMatch(mapping.row_version) },
              );
              if (outcome.kind === "succeeded") {
                toast.show({
                  tone: "positive",
                  message: t("policies.mappingVersion.effectiveSaved"),
                });
              }
            })()
          }
        >
          {t("policies.mappingVersion.saveEffective")}
        </Button>
      </div>
    </div>
  );
}

/** SCREENS §11.6 rules grid columns; "Remove rule" only while editable. */
export function ruleColumns(
  entities: ReadonlyMap<string, string>,
  products: ReadonlyMap<string, string>,
  editable: boolean,
  onRemove: (rule: AccountMappingRule) => void,
): readonly GridColumn<AccountMappingRule>[] {
  const any = t("policies.mappingVersion.any");
  const columns: GridColumn<AccountMappingRule>[] = [
    {
      id: "account_role",
      header: t("policies.mappingVersion.column.role"),
      kind: "identifier",
      value: (rule) => roleLabel(rule.account_role),
      render: (rule) => (
        <span className="inline-flex flex-col">
          <span>{roleLabel(rule.account_role)}</span>
          <span className="font-mono text-mono-sm text-fg-3">{rule.account_role}</span>
        </span>
      ),
      width: 220,
    },
    {
      id: "clearing_purpose",
      header: t("policies.mappingVersion.column.clearingPurpose"),
      kind: "text",
      value: (rule) =>
        rule.clearing_purpose === null ? null : purposeLabel(rule.clearing_purpose),
      width: 144,
    },
    {
      id: "entity_id",
      header: t("policies.mappingVersion.column.entity"),
      kind: "text",
      value: (rule) =>
        rule.entity_id === null ? any : (entities.get(rule.entity_id) ?? rule.entity_id),
      width: 112,
    },
    {
      id: "book_code",
      header: t("policies.mappingVersion.column.book"),
      kind: "text",
      value: (rule) => (rule.book_code === null ? any : bookLabel(rule.book_code)),
      width: 112,
    },
    {
      id: "product_id",
      header: t("policies.mappingVersion.column.product"),
      kind: "text",
      value: (rule) =>
        rule.product_id === null ? any : (products.get(rule.product_id) ?? rule.product_id),
      width: 160,
    },
    {
      id: "revenue_category",
      header: t("policies.mappingVersion.column.revenueCategory"),
      kind: "text",
      value: (rule) => rule.revenue_category ?? any,
      render: (rule) =>
        rule.revenue_category === null ? <span>{any}</span> : mono(rule.revenue_category),
      width: 160,
    },
    {
      id: "gl_account",
      header: t("policies.mappingVersion.column.glAccount"),
      kind: "text",
      value: (rule) => `${rule.gl_account.code} ${rule.gl_account.name}`,
      render: (rule) => (
        <span className="inline-flex items-center gap-2">
          {mono(rule.gl_account.code)}
          <span>{rule.gl_account.name}</span>
        </span>
      ),
      width: 260,
    },
    {
      id: "priority",
      header: t("policies.mappingVersion.column.priority"),
      kind: "number",
      numberKind: "count",
      value: (rule) => String(rule.priority),
      width: 96,
    },
    {
      id: "specificity",
      header: t("policies.mappingVersion.column.specificity"),
      kind: "number",
      numberKind: "count",
      value: (rule) => String(rule.specificity),
      width: 104,
    },
  ];
  if (editable) {
    columns.push({
      id: "actions",
      header: t("policies.mappingVersion.column.actions"),
      kind: "actions",
      value: () => null,
      render: (rule) => (
        <Button variant="link" size="sm" onClick={() => onRemove(rule)}>
          {t("policies.mappingVersion.removeRule")}
        </Button>
      ),
      width: 128,
    });
  }
  return columns;
}

function RulesPane({
  mapping,
  editable,
  invalidates,
  onAdd,
}: {
  readonly mapping: AccountMapping;
  readonly editable: boolean;
  readonly invalidates: readonly ReturnType<typeof queryKey>[];
  readonly onAdd: () => void;
}) {
  const toast = useToast();
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const products = useQuery({ queryKey: allProductsKey(), queryFn: fetchAllProducts });
  const [removing, setRemoving] = useState<AccountMappingRule | null>(null);
  const remove = useCommand({
    method: "DELETE",
    path: removing === null ? rulesPath(mapping.id) : rulePath(mapping.id, removing.id),
    invalidates,
  });
  const entityMap = useMemo(
    () => new Map((entities.data ?? []).map((entity) => [entity.id, entity.code])),
    [entities.data],
  );
  const productMap = useMemo(
    () => new Map((products.data ?? []).map((product) => [product.id, product.code])),
    [products.data],
  );
  const columns = useMemo(
    () => ruleColumns(entityMap, productMap, editable, setRemoving),
    [entityMap, productMap, editable],
  );
  const source: GridSource<AccountMappingRule> = useMemo(
    () => ({
      queryKey: rulesKey(mapping.id),
      fetchPage: async () => {
        const items = await fetchAllRules(mapping.id);
        return { items, nextCursor: null, total: { count: items.length, capped: false } };
      },
    }),
    [mapping.id],
  );
  const doRemove = async () => {
    if (removing === null) {
      return;
    }
    const outcome = await remove.submit();
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.mappingVersion.ruleRemoved", {
          role: roleLabel(removing.account_role),
        }),
      });
      setRemoving(null);
    }
  };
  return (
    <div className="flex min-h-0 flex-col gap-3 pt-3" data-testid="SF-13-pane-rules">
      <RefusalBanner problem={remove.problem} />
      {removing === null ? null : (
        <Banner
          tone="warning"
          announce="static"
          title={t("policies.mappingVersion.removeConfirm", {
            role: roleLabel(removing.account_role),
            account: removing.gl_account.code,
          })}
          actions={
            <>
              <Button variant="danger" size="sm" onClick={() => void doRemove()}>
                {t("policies.mappingVersion.removeRule")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setRemoving(null)}>
                {t("policies.mappingVersion.keepRule")}
              </Button>
            </>
          }
        />
      )}
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<AccountMappingRule>
          name="mapping-rules"
          title={t("policies.mappingVersion.rules")}
          errorTitle={t("policies.mappingVersion.rulesLoadError")}
          countLabel={(count, formatted) =>
            t("policies.mappingVersion.ruleCount", { count, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(rule) => rule.id}
          rowLabel={(rule) => `${roleLabel(rule.account_role)} ${rule.gl_account.code}`}
          testIdPrefix="SF-13"
          rowTestKey={(rule) => rule.id}
          toolbarActions={
            editable ? (
              <Button variant="primary" size="sm" onClick={onAdd}>
                {t("policies.mappingVersion.addRule")}
              </Button>
            ) : undefined
          }
          emptyState={
            <EmptyState
              title={t("policies.mappingVersion.rulesEmpty.title")}
              description={t("policies.mappingVersion.rulesEmpty.description")}
              action={
                editable
                  ? { label: t("policies.mappingVersion.addRule"), onAction: onAdd }
                  : undefined
              }
            />
          }
        />
      </div>
    </div>
  );
}

/** SCREENS §11.6 "Add rule" drawer: the role, clearing purpose, key and GL account of one rule. */
function RuleDrawer({
  mapping,
  invalidates,
  onClose,
}: {
  readonly mapping: AccountMapping;
  readonly invalidates: readonly ReturnType<typeof queryKey>[];
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const [draft, setDraft] = useState<RuleDraft>(EMPTY_RULE_DRAFT);
  const [attempted, setAttempted] = useState(false);
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const products = useQuery({ queryKey: allProductsKey(), queryFn: fetchAllProducts });
  const accounts = useQuery({
    queryKey: queryKey("gl-accounts", "tenant", { view: "all" }),
    queryFn: fetchAllAccounts,
  });
  const create = useCommand<AccountMappingRule>({
    method: "POST",
    path: rulesPath(mapping.id),
    invalidates,
  });
  const placed = useMemo(
    () => placeProblem(create.problem, MAPPING_RULE_MEMBERS),
    [create.problem],
  );
  const errors = attempted ? ruleDraftErrors(draft) : [];
  const update = (change: Partial<RuleDraft>) =>
    setDraft((previous) => ({ ...previous, ...change }));
  const billing = draft.role === BILLING_CLEARING;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (ruleDraftErrors(draft).length > 0) {
      return;
    }
    const outcome = await create.submit(ruleInput(draft));
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.mappingVersion.ruleAdded", {
          role: roleLabel(draft.role ?? "REVENUE"),
        }),
      });
      onClose();
    }
  };
  const anyOption = { value: "", label: t("policies.mappingVersion.any") };
  return (
    <Drawer
      open
      title={t("policies.mappingVersion.addRule")}
      subtitle={`${mapping.name} v${String(mapping.version_no)}`}
      dirty={draft.role !== null || draft.glAccountId !== null}
      submitting={create.pending}
      primaryAction={{ label: t("policies.mappingVersion.saveRule"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-13-drawer-mapping-rule"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="account_role"
          label={t("policies.mappingVersion.column.role")}
          required
          error={
            errors.includes("role") ? t("policies.mappingVersion.error.role") : placed.fields.role
          }
          width="text"
        >
          {(control) => (
            <Select<AccountRole>
              control={control}
              options={MAPPABLE_ROLES.map((role) => ({ value: role, label: roleLabel(role) }))}
              value={draft.role}
              invalid={errors.includes("role")}
              onChange={(role) =>
                update({
                  role,
                  clearingPurpose: role === BILLING_CLEARING ? draft.clearingPurpose : null,
                })
              }
              renderExtra={(option) => (
                <span className="font-mono text-mono-sm text-fg-3">{option.value}</span>
              )}
            />
          )}
        </Field>
        <Field
          name="clearing_purpose"
          label={t("policies.mappingVersion.column.clearingPurpose")}
          required={billing}
          optional={!billing}
          help={billing ? undefined : t("policies.mappingVersion.clearingPurposeOnly")}
          error={
            errors.includes("clearingPurposeRequired")
              ? t("policies.mappingVersion.error.clearingPurposeRequired")
              : errors.includes("clearingPurposeForbidden")
                ? t("policies.mappingVersion.error.clearingPurposeForbidden")
                : placed.fields.purpose
          }
          width="text"
        >
          {(control) =>
            billing ? (
              <Select<ClearingPurpose>
                control={control}
                options={CLEARING_PURPOSES.map((purpose) => ({
                  value: purpose,
                  label: purposeLabel(purpose),
                }))}
                value={draft.clearingPurpose}
                invalid={errors.includes("clearingPurposeRequired")}
                onChange={(purpose) => update({ clearingPurpose: purpose })}
              />
            ) : (
              // SCREENS §11.6: disabled with the reason in the field help ("Only billing clearing has a
              // clearing purpose."), which the control's aria-describedby references.
              <select
                {...control}
                disabled
                aria-disabled="true"
                value=""
                className={`${controlClass(false)} text-fg-3`}
              >
                <option value="">{NO_VALUE}</option>
              </select>
            )
          }
        </Field>
        <Field
          name="entity_id"
          label={t("policies.mappingVersion.column.entity")}
          optional
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                anyOption,
                ...(entities.data ?? []).map((entity) => ({
                  value: entity.id,
                  label: entity.code,
                })),
              ]}
              value={draft.entityId ?? ""}
              onChange={(value) => update({ entityId: value === "" ? null : value })}
            />
          )}
        </Field>
        <Field
          name="book_code"
          label={t("policies.mappingVersion.column.book")}
          optional
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                anyOption,
                ...BOOK_CODES.map((code) => ({ value: code, label: bookLabel(code) })),
              ]}
              value={draft.book ?? ""}
              onChange={(value) => update({ book: value === "" ? null : (value as BookCode) })}
            />
          )}
        </Field>
        <Field
          name="product_id"
          label={t("policies.mappingVersion.column.product")}
          optional
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={(products.data ?? []).map((product) => ({
                value: product.id,
                label: `${product.code} · ${product.name}`,
              }))}
              value={draft.productId}
              onChange={(value) =>
                update({
                  productId: value,
                  revenueCategory: value === null ? draft.revenueCategory : "",
                })
              }
            />
          )}
        </Field>
        <Field
          name="revenue_category"
          label={t("policies.mappingVersion.column.revenueCategory")}
          optional
          help={
            draft.productId === null ? undefined : t("policies.mappingVersion.categoryDisabled")
          }
          error={
            errors.includes("productOrCategory")
              ? t("policies.mappingVersion.error.productOrCategory")
              : null
          }
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              disabled={draft.productId !== null}
              value={draft.revenueCategory}
              onChange={(event) => update({ revenueCategory: event.target.value })}
              className={`${controlClass(errors.includes("productOrCategory"))} font-mono`}
            />
          )}
        </Field>
        <Field
          name="gl_account_id"
          label={t("policies.mappingVersion.column.glAccount")}
          required
          error={
            errors.includes("glAccount")
              ? t("policies.mappingVersion.error.glAccount")
              : placed.fields.account
          }
          width="full"
        >
          {(control) => (
            <Combobox
              control={control}
              options={(accounts.data ?? []).map((account: GlAccount) => ({
                value: account.id,
                label: `${account.code} ${account.name}`,
              }))}
              value={draft.glAccountId}
              invalid={errors.includes("glAccount")}
              onChange={(value) => update({ glAccountId: value })}
            />
          )}
        </Field>
        <Field
          name="priority"
          label={t("policies.mappingVersion.column.priority")}
          required
          error={
            errors.includes("priority")
              ? t("policies.mappingVersion.error.priority")
              : placed.fields.priority
          }
          width="money"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              inputMode="numeric"
              value={draft.priority}
              onChange={(event) => update({ priority: event.target.value })}
              className={`${controlClass(errors.includes("priority"))} num`}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}

function CoveragePane({ rules }: { readonly rules: readonly AccountMappingRule[] | undefined }) {
  if (rules === undefined) {
    return <Skeleton region={t("policies.mappingVersion.coverage")} shape="rows" count={6} />;
  }
  const rows = coverageRows(rules);
  return (
    <div className="flex flex-col gap-2 pt-3" data-testid="SF-13-pane-coverage">
      <table
        aria-label={t("policies.mappingVersion.coverage")}
        data-testid="SF-13-grid-coverage"
        className="w-full text-body-sm"
      >
        <thead>
          <tr className="border-b border-hairline text-caption text-fg-3">
            <th scope="col" className="py-2 pe-4 text-start font-medium">
              {t("policies.mappingVersion.column.role")}
            </th>
            <th scope="col" className="py-2 pe-4 text-start font-medium">
              {t("policies.mappingVersion.column.clearingPurpose")}
            </th>
            <th scope="col" className="py-2 text-start font-medium">
              {t("policies.mappingVersion.column.status")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.role}-${row.clearingPurpose ?? ""}`}
              data-testid={`SF-13-coverage-${row.role}${row.clearingPurpose === null ? "" : `-${row.clearingPurpose}`}`}
              data-status={row.status}
              className={`border-b border-hairline last:border-b-0 ${row.status === "reserved" ? "text-fg-3" : "text-fg-1"}`}
            >
              <th scope="row" className="py-2 pe-4 text-start font-normal">
                {roleLabel(row.role)}
              </th>
              <td className="py-2 pe-4">
                {row.clearingPurpose === null ? NO_VALUE : purposeLabel(row.clearingPurpose)}
              </td>
              <td className="py-2">
                {row.status === "mapped" ? (
                  t("policies.mappingVersion.coverageMapped", {
                    formatted: formatNumber(row.ruleCount, { kind: "count" }),
                    count: row.ruleCount,
                  })
                ) : row.status === "reserved" ? (
                  t("policies.mappingVersion.coverageReserved")
                ) : (
                  <span className="inline-flex flex-wrap items-center gap-2">
                    <StatusChip status="Not mapped" />
                    <span className="text-caption text-fg-3">
                      {t("policies.mappingVersion.coverageMissingNote")}
                    </span>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResolvePane() {
  const formId = useId();
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const products = useQuery({ queryKey: allProductsKey(), queryFn: fetchAllProducts });
  const [draft, setDraft] = useState<RuleDraft>(EMPTY_RULE_DRAFT);
  const [knownAtText, setKnownAtText] = useState("");
  const [knownAt, setKnownAt] = useState<string | null>(null);
  const [result, setResult] = useState<AccountResolution | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false);
  const update = (change: Partial<RuleDraft>) =>
    setDraft((previous) => ({ ...previous, ...change }));
  const entityCode = (id: string | null) =>
    entities.data?.find((entity) => entity.id === id)?.code ?? null;
  const productCode = (id: string | null) =>
    products.data?.find((product) => product.id === id)?.code ?? null;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (draft.role === null) {
      return;
    }
    const query: ResolveQuery = {
      role: draft.role,
      clearingPurpose: draft.role === BILLING_CLEARING ? draft.clearingPurpose : null,
      entity: entityCode(draft.entityId),
      book: draft.book,
      product: productCode(draft.productId),
      revenueCategory: draft.revenueCategory.trim() === "" ? null : draft.revenueCategory.trim(),
      knownAt,
    };
    setPending(true);
    setProblem(null);
    setResult(null);
    try {
      setResult(await resolveAccount(query));
    } catch (error) {
      if (error instanceof ApiProblem) {
        setProblem(error);
      } else {
        throw error;
      }
    } finally {
      setPending(false);
    }
  };
  const anyOption = { value: "", label: t("policies.mappingVersion.any") };
  const roleName = draft.role === null ? "" : roleLabel(draft.role);
  return (
    <div className="flex flex-col gap-3 pt-3" data-testid="SF-13-pane-resolve">
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-wrap items-end gap-3"
        aria-label={t("policies.mappingVersion.panes.resolve")}
      >
        <Field
          name="resolve-role"
          label={t("policies.mappingVersion.column.role")}
          required
          error={attempted && draft.role === null ? t("policies.mappingVersion.error.role") : null}
          width="text"
        >
          {(control) => (
            <Select<AccountRole>
              control={control}
              options={MAPPABLE_ROLES.map((role) => ({ value: role, label: roleLabel(role) }))}
              value={draft.role}
              onChange={(role) => update({ role })}
            />
          )}
        </Field>
        {draft.role === BILLING_CLEARING ? (
          <Field
            name="resolve-purpose"
            label={t("policies.mappingVersion.column.clearingPurpose")}
            width="text"
          >
            {(control) => (
              <Select<ClearingPurpose>
                control={control}
                options={CLEARING_PURPOSES.map((purpose) => ({
                  value: purpose,
                  label: purposeLabel(purpose),
                }))}
                value={draft.clearingPurpose}
                onChange={(purpose) => update({ clearingPurpose: purpose })}
              />
            )}
          </Field>
        ) : null}
        <Field
          name="resolve-entity"
          label={t("policies.mappingVersion.column.entity")}
          optional
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                anyOption,
                ...(entities.data ?? []).map((entity) => ({
                  value: entity.id,
                  label: entity.code,
                })),
              ]}
              value={draft.entityId ?? ""}
              onChange={(value) => update({ entityId: value === "" ? null : value })}
            />
          )}
        </Field>
        <Field
          name="resolve-book"
          label={t("policies.mappingVersion.column.book")}
          optional
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                anyOption,
                ...BOOK_CODES.map((code) => ({ value: code, label: bookLabel(code) })),
              ]}
              value={draft.book ?? ""}
              onChange={(value) => update({ book: value === "" ? null : (value as BookCode) })}
            />
          )}
        </Field>
        <Field
          name="resolve-product"
          label={t("policies.mappingVersion.column.product")}
          optional
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={(products.data ?? []).map((product) => ({
                value: product.id,
                label: `${product.code} · ${product.name}`,
              }))}
              value={draft.productId}
              onChange={(value) => update({ productId: value })}
            />
          )}
        </Field>
        <Field
          name="resolve-category"
          label={t("policies.mappingVersion.column.revenueCategory")}
          optional
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={draft.revenueCategory}
              onChange={(event) => update({ revenueCategory: event.target.value })}
              className={`${controlClass(false)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="resolve-known-at"
          label={t("policies.mappingVersion.knownAt")}
          optional
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={knownAtText}
              onChange={setKnownAtText}
              onValue={setKnownAt}
            />
          )}
        </Field>
        <Button
          variant="primary"
          type="submit"
          form={formId}
          disabledReason={pending ? t("policies.mappingVersion.resolving") : undefined}
        >
          {t("policies.mappingVersion.resolve")}
        </Button>
      </form>
      {result === null ? null : (
        <p className="text-body-sm text-fg-1" data-testid="SF-13-resolve-result">
          {t("policies.mappingVersion.resolved", {
            code: result.gl_account.code,
            name: result.gl_account.name,
            priority: result.source.priority === null ? NO_VALUE : String(result.source.priority),
            specificity:
              result.source.specificity === null ? NO_VALUE : String(result.source.specificity),
          })}
        </p>
      )}
      {problem === null ? null : (
        <Banner
          tone="negative"
          title={
            problem.status === 404 || problem.status === 409
              ? t("policies.mappingVersion.unmapped", {
                  role: roleName,
                  entity: entityCode(draft.entityId) ?? t("policies.mappingVersion.any"),
                })
              : (problem.detail ?? problem.title)
          }
        />
      )}
    </div>
  );
}

function SimulationPane({ mapping }: { readonly mapping: AccountMapping }) {
  return (
    <div className="flex flex-col gap-2 pt-3" data-testid="SF-13-pane-simulation">
      {mapping.impact_simulation_file_id === null ? (
        <p className="text-body-sm text-fg-2">{t("policies.simulation.none")}</p>
      ) : (
        <a
          href={fileContentPath(mapping.impact_simulation_file_id)}
          className="text-body-sm font-medium text-accent-fg hover:underline"
          download
        >
          {t("policies.mappingVersion.downloadSimulation")}
        </a>
      )}
    </div>
  );
}

function ChangesPane({
  mapping,
  rules,
}: {
  readonly mapping: AccountMapping;
  readonly rules: readonly AccountMappingRule[] | undefined;
}) {
  const previousId = mapping.supersedes_version_id;
  const previous = useQuery({
    queryKey: mappingKey(previousId ?? ""),
    queryFn: () => fetchMapping(previousId ?? ""),
    enabled: previousId !== null,
  });
  const previousRules = useQuery({
    queryKey: rulesKey(previousId ?? ""),
    queryFn: () => fetchAllRules(previousId ?? ""),
    enabled: previousId !== null,
  });
  if (previousId === null) {
    return (
      <p className="pt-3 text-body-sm text-fg-3">{t("policies.mappingVersion.changes.first")}</p>
    );
  }
  if (rules === undefined || previousRules.data === undefined || previous.data === undefined) {
    return <Skeleton region={t("policies.panes.changes")} shape="rows" count={3} />;
  }
  const changes = ruleChanges(rules, previousRules.data);
  const list = (title: string, items: readonly AccountMappingRule[]) => (
    <section aria-label={title} className="flex flex-col gap-1">
      <h3 className="text-body-sm font-medium text-fg-1">{title}</h3>
      {items.length === 0 ? (
        <p className="text-body-sm text-fg-3">{t("policies.mappingVersion.changes.none")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-body-sm">
          {items.map((rule) => (
            <li key={rule.id} className="flex flex-wrap items-center gap-2">
              <span>{roleLabel(rule.account_role)}</span>
              {rule.clearing_purpose === null ? null : (
                <span className="text-fg-2">{purposeLabel(rule.clearing_purpose)}</span>
              )}
              {mono(rule.gl_account.code)}
              <span className="text-fg-2">{rule.gl_account.name}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
  return (
    <div className="flex flex-col gap-3 pt-3" data-testid="SF-13-pane-changes">
      <p className="text-body-sm text-fg-2">
        {t("policies.mappingVersion.changes.supersedes", {
          version: String(previous.data.version_no),
        })}{" "}
        <Link to={mappingVersionRoute(previousId)} className="text-accent-fg hover:underline">
          {t("policies.version.number", { version: String(previous.data.version_no) })}
        </Link>
      </p>
      {list(t("policies.mappingVersion.changes.added"), changes.added)}
      {list(t("policies.mappingVersion.changes.removed"), changes.removed)}
    </div>
  );
}

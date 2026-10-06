// SF-13:revenue Revenue policies (SCREENS §11.0 frame, §11.1 "Revenue policies page" and the "New rule set"
// drawer; §0.3 SCR-IA-01, SCR-IA-02; §0.4 RT-59; §0.7 SCR-ST-03, SCR-PERM-01, SCR-PERM-02; DESIGN_SYSTEM
// DS-CMP-07, DS-CMP-09, DS-CMP-10, DS-CMP-19; 04 API-R-24 `GET /pob-templates`, API-R-25 `GET, POST
// /rule-sets`, `POST /rule-sets/{id}/versions`; BUILD_SPEC RFD-22). The `h1` "Policies", the route tabs of
// the built Policies pages, the DataGrid "Obligation templates" and the DataGrid "Assignment rules" of
// the obligation and SSP assignment rule sets. A rule set code opens its current version, else its latest
// (SF-13:rule-set-version). "New rule set" (`config.author`) creates the set and its draft version 1 and
// opens that version. Template codes link and "New template" renders once SF-13:template-version is
// built (XR-14; L4-5-Q-30).
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { type CommandKeys, useCommandKeys } from "../../lib/api/commands";
import { type ApiProblem, readProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import {
  CONFIG_AUTHOR_PERMISSION,
  CONFIG_READ_PERMISSION,
  distinctnessLabel,
  EVERY_RULE_SET,
  fetchRuleSetsPage,
  fetchTemplatesPage,
  lintStatusWord,
  REVENUE_KINDS,
  type RuleSet,
  type RuleSetKind,
  ruleSetKindLabel,
  ruleSetsKey,
  RULE_SETS_PATH,
  ruleSetVersionRoute,
  type RuleSetVersion,
  type TemplateRow,
  templatesKey,
} from "../../lib/api/queries/rule-sets";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";

/** SCREENS §0.4 RT-61 SF-13:template-version, built by RFD-23. */
export const TEMPLATE_VERSION_PATTERN = "/policies/templates/:templateId/versions/:versionId";

export interface PolicyTab {
  readonly screen: string;
  readonly path: string;
  /** The message key under `policies.tabs`. */
  readonly key: string;
  /** Any-of read permissions (SCREENS §0.4). */
  readonly permissions: readonly string[];
}

/** SCREENS §0.3 SCR-IA-02 Policies route tabs, in order, with the RT-59 to RT-69 read permissions. */
export const POLICY_TABS: readonly PolicyTab[] = [
  {
    screen: "SF-13:revenue",
    path: "/policies/revenue",
    key: "revenue",
    permissions: ["config.read"],
  },
  {
    screen: "SF-13:control-rules",
    path: "/policies/control-rules",
    key: "controlRules",
    permissions: ["config.read"],
  },
  {
    screen: "SF-13:accounting",
    path: "/policies/accounting",
    key: "accounting",
    permissions: ["config.read"],
  },
  {
    screen: "SF-13:ssp-books",
    path: "/policies/ssp-books",
    key: "sspBooks",
    permissions: ["ssp.read"],
  },
  {
    screen: "SF-13:ssp-calculator",
    path: "/policies/ssp-calculator",
    key: "sspCalculator",
    permissions: ["ssp.read"],
  },
  {
    screen: "SF-13:account-mapping",
    path: "/policies/account-mapping",
    key: "accountMapping",
    permissions: ["config.read"],
  },
];

/** SCR-IA-02: the `h1` "Policies" and the route tabs of built pages the user may read (XR-14). */
export function PoliciesPageHeader() {
  const built = useBuiltPaths();
  const access = useAccess();
  const tabs: RouteTab[] = POLICY_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`policies.tabs.${tab.key}`),
    to: tab.path,
    end: true,
  }));
  return (
    <header className="flex flex-col gap-3">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {t("policies.title")}
      </h1>
      {tabs.length === 0 ? null : <RouteTabs label={t("policies.tabs.label")} tabs={tabs} />}
    </header>
  );
}

export interface PoliciesPageProps {
  /** The page body for a `config.read` holder; `author` holds `config.author` (SCR-PERM-02). */
  readonly children: (author: boolean) => ReactNode;
}

/** SCREENS §11.0 list page frame with the SCR-PERM-01 access-limited state. */
export function PoliciesPage({ children }: PoliciesPageProps) {
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("policies.title")} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(CONFIG_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("policies.title") })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    body = children(access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION));
  }
  return (
    <div className="flex w-full flex-col gap-6">
      <PoliciesPageHeader />
      {body}
    </div>
  );
}

function versionChip(status: RuleSetVersion["status"] | undefined): ReactNode {
  if (status === undefined) {
    return null;
  }
  const spec = chipFor("E-12", status);
  return spec === null ? null : <StatusChip status={spec.status} />;
}

function versionNumber(summary: { readonly version_no: number } | null): string | null {
  return summary === null ? null : t("policies.version.number", { version: summary.version_no });
}

function effectiveDate(summary: { readonly effective_from: string | null } | null): string | null {
  return summary?.effective_from === null || summary === null
    ? null
    : timestampDate(summary.effective_from);
}

/** SCREENS §11.1 rule-set columns, shared by the revenue policies and control rules pages. */
// API-C-09 sort keys: GET /api/v1/rule-sets
export function ruleSetColumns(): readonly GridColumn<RuleSet>[] {
  // A set always starts with version 1; one whose first version failed to start opens its list page.
  const route = (set: RuleSet): string => {
    const summary = set.current_version ?? set.latest_version;
    if (summary !== null) {
      return ruleSetVersionRoute(set.id, summary.id);
    }
    return REVENUE_KINDS.includes(set.kind) ? "/policies/revenue" : "/policies/control-rules";
  };
  return [
    {
      id: "code",
      header: t("policies.ruleSets.column.code"),
      kind: "identifier",
      value: (set) => set.code,
      href: route,
      sortKey: "code",
      width: 176,
    },
    {
      id: "name",
      header: t("policies.ruleSets.column.name"),
      kind: "text",
      value: (set) => set.name,
      sortKey: "name",
      width: 240,
    },
    {
      id: "kind",
      header: t("policies.ruleSets.column.kind"),
      kind: "text",
      value: (set) => ruleSetKindLabel(set.kind),
      width: 192,
    },
    {
      id: "current",
      header: t("policies.ruleSets.column.currentVersion"),
      kind: "text",
      value: (set) => versionNumber(set.current_version),
      width: 160,
    },
    {
      id: "status",
      header: t("policies.ruleSets.column.latestStatus"),
      kind: "status",
      value: (set) => set.latest_version?.status ?? null,
      render: (set) => versionChip(set.latest_version?.status) ?? "—",
      width: 160,
    },
    {
      id: "rules",
      header: t("policies.ruleSets.column.rules"),
      kind: "number",
      numberKind: "count",
      value: (set) =>
        set.latest_version?.rule_count === null || set.latest_version === null
          ? null
          : String(set.latest_version.rule_count),
      width: 96,
    },
    {
      id: "lint",
      header: t("policies.ruleSets.column.lint"),
      kind: "status",
      value: (set) => set.latest_version?.lint_status ?? null,
      render: (set) => {
        const word = lintStatusWord(set.latest_version?.lint_status ?? null);
        return word === null ? "—" : <StatusChip status={word} />;
      },
      width: 112,
    },
    {
      id: "effective",
      header: t("policies.ruleSets.column.effectiveFrom"),
      kind: "date",
      value: (set) => effectiveDate(set.current_version),
      width: 128,
    },
  ];
}

const TEMPLATES_SOURCE: GridSource<TemplateRow> = {
  queryKey: templatesKey(),
  fetchPage: fetchTemplatesPage,
};

const REVENUE_RULE_SETS: GridSource<RuleSet> = {
  queryKey: ruleSetsKey(REVENUE_KINDS),
  fetchPage: (cursor, sort) => fetchRuleSetsPage(REVENUE_KINDS, cursor, sort),
};

export function RevenuePolicies() {
  return <PoliciesPage>{(author) => <RevenueGrids author={author} />}</PoliciesPage>;
}

function RevenueGrids({ author }: { readonly author: boolean }) {
  const built = useBuiltPaths();
  const [creating, setCreating] = useState(false);
  const templateEditor = built.has(TEMPLATE_VERSION_PATTERN);

  // API-C-09 sort keys: GET /api/v1/pob-templates
  const templateColumns: readonly GridColumn<TemplateRow>[] = [
    {
      id: "code",
      header: t("policies.revenue.templates.column.template"),
      kind: "identifier",
      value: (row) => row.template.code,
      href: templateEditor
        ? (row) => {
            const summary = row.template.current_version ?? row.template.latest_version;
            return summary === null
              ? `/policies/templates/${row.template.id}`
              : `/policies/templates/${row.template.id}/versions/${summary.id}`;
          }
        : undefined,
      sortKey: "code",
      width: 176,
    },
    {
      id: "name",
      header: t("policies.revenue.templates.column.name"),
      kind: "text",
      value: (row) => row.template.name,
      sortKey: "name",
      width: 240,
    },
    {
      id: "current",
      header: t("policies.revenue.templates.column.currentVersion"),
      kind: "text",
      value: (row) => versionNumber(row.template.current_version),
      width: 160,
    },
    {
      id: "status",
      header: t("policies.revenue.templates.column.latestStatus"),
      kind: "status",
      value: (row) => row.template.latest_version?.status ?? null,
      render: (row) => versionChip(row.template.latest_version?.status) ?? "—",
      width: 160,
    },
    {
      id: "pattern",
      header: t("policies.revenue.templates.column.satisfaction"),
      kind: "text",
      value: (row) =>
        row.version === null
          ? null
          : t(`policies.template.satisfaction.${row.version.satisfaction_pattern}`),
      width: 192,
    },
    {
      id: "method",
      header: t("policies.revenue.templates.column.method"),
      kind: "text",
      value: (row) =>
        row.version === null
          ? null
          : t(`policies.template.method.${row.version.recognition_method}`),
      width: 192,
    },
    {
      id: "convention",
      header: t("policies.revenue.templates.column.convention"),
      kind: "text",
      value: (row) =>
        row.version?.ratable_convention === null || row.version === null
          ? null
          : t(`policies.template.convention.${row.version.ratable_convention}`),
      width: 136,
    },
    {
      id: "distinctness",
      header: t("policies.revenue.templates.column.distinctness"),
      kind: "text",
      value: (row) => (row.version === null ? null : distinctnessLabel(row.version)),
      width: 176,
    },
    {
      id: "effective",
      header: t("policies.revenue.templates.column.effectiveFrom"),
      kind: "date",
      value: (row) => effectiveDate(row.template.current_version),
      width: 128,
    },
  ];

  return (
    <>
      <div className="flex h-120 min-h-0 flex-col">
        <DataGrid<TemplateRow>
          name="templates"
          title={t("policies.revenue.templates.title")}
          countLabel={(count, formatted) =>
            t("policies.revenue.templates.count", { count, formatted })
          }
          columns={templateColumns}
          source={TEMPLATES_SOURCE}
          rowKey={(row) => row.template.id}
          rowLabel={(row) => row.template.code}
          testIdPrefix="SF-13"
          rowTestKey={(row) => `template-${row.template.code}`}
          emptyState={
            <EmptyState
              title={t("policies.revenue.templates.empty.title")}
              description={t("policies.revenue.templates.empty.description")}
            />
          }
        />
      </div>
      <div className="flex h-80 min-h-0 flex-col">
        <DataGrid<RuleSet>
          name="rule-sets"
          title={t("policies.revenue.ruleSets.title")}
          countLabel={(count, formatted) => t("policies.ruleSets.count", { count, formatted })}
          columns={ruleSetColumns()}
          source={REVENUE_RULE_SETS}
          rowKey={(set) => set.id}
          rowLabel={(set) => set.code}
          testIdPrefix="SF-13"
          rowTestKey={(set) => `rule-set-${set.code}`}
          toolbarActions={
            author ? (
              <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
                {t("policies.ruleSets.new")}
              </Button>
            ) : undefined
          }
          emptyState={
            <EmptyState
              title={t("policies.revenue.ruleSets.empty.title")}
              description={t("policies.revenue.ruleSets.empty.description")}
            />
          }
        />
      </div>
      {creating ? (
        <NewRuleSetDrawer kinds={REVENUE_KINDS} onClose={() => setCreating(false)} />
      ) : null}
    </>
  );
}

type Created<T> =
  { readonly ok: true; readonly data: T } | { readonly ok: false; readonly problem: ApiProblem };

/**
 * One command of the create sequence. It keeps its key after it succeeded, until the sequence is
 * through (DG-FE-05 rev 1.156): when the version cannot be created, the second press sends the rule
 * set again under its key and the API replays the rule set it created.
 */
async function createStep<T>(keys: CommandKeys, path: string, body: unknown): Promise<Created<T>> {
  const response = await keys.send("POST", path, { body, keep: true });
  if (!response.ok) {
    return { ok: false, problem: await readProblem(response) };
  }
  return { ok: true, data: (await response.json()) as T };
}

/**
 * The API members the fields of "New rule set" send (DG-FE-06 rev 1.228). The first draft version is
 * a command of its own without members, so what it is refused for is the banner's.
 */
const RULE_SET_MEMBERS = {
  code: ["code"],
  name: ["name"],
  kind: ["kind"],
  description: ["description"],
} as const;

export interface NewRuleSetDrawerProps {
  /** The kinds the page lists; the drawer offers only these. */
  readonly kinds: readonly RuleSetKind[];
  readonly onClose: () => void;
}

/**
 * SCREENS §11.1 "New rule set": Code, Name, Kind (immutable after creation), Description; "Create rule
 * set" posts `POST /rule-sets`, then `POST /rule-sets/{id}/versions`, and opens the draft version.
 */
export function NewRuleSetDrawer({ kinds, onClose }: NewRuleSetDrawerProps) {
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const formId = useId();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState<RuleSetKind | null>(
    kinds.length === 1 ? (kinds[0] ?? null) : null,
  );
  const [description, setDescription] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const refusals = useFieldRefusals(problem, RULE_SET_MEMBERS);
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (code.trim() === "") {
      found.code = t("policies.ruleSets.drawer.codeRequired");
    }
    if (kind === null) {
      found.kind = t("policies.ruleSets.drawer.kindRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0 || kind === null) {
      return;
    }
    setPending(true);
    setProblem(null);
    let created: Created<RuleSet>;
    let version: Created<RuleSetVersion>;
    try {
      created = await createStep<RuleSet>(keys, RULE_SETS_PATH, {
        code: code.trim(),
        kind,
        ...(name.trim() === "" ? {} : { name: name.trim() }),
        ...(description.trim() === "" ? {} : { description: description.trim() }),
      });
      if (!created.ok) {
        setPending(false);
        setProblem(created.problem);
        return;
      }
      version = await createStep<RuleSetVersion>(
        keys,
        `${RULE_SETS_PATH}/${created.data.id}/versions`,
        {},
      );
    } catch {
      // No answer: the drawer keeps its input, and the next press sends the same keys.
      setPending(false);
      noAnswer();
      return;
    }
    await queryClient.invalidateQueries({ queryKey: EVERY_RULE_SET });
    setPending(false);
    if (!version.ok) {
      setProblem(version.problem);
      return;
    }
    keys.clear();
    toast.show({
      tone: "positive",
      message: t("policies.ruleSets.drawer.created", { code: created.data.code }),
    });
    onClose();
    void navigate(ruleSetVersionRoute(created.data.id, version.data.id));
  };

  return (
    <Drawer
      open
      title={t("policies.ruleSets.new")}
      dirty={code !== "" || name !== "" || description !== ""}
      submitting={pending}
      banner={
        refusals.banner === null ? undefined : (
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        )
      }
      primaryAction={{ label: t("policies.ruleSets.drawer.create"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="rule_set_code"
          label={t("policies.ruleSets.drawer.code")}
          required
          error={errors.code ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
                refusals.edited("code");
              }}
              className={`${controlClass(errors.code !== undefined)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="rule_set_name"
          label={t("policies.ruleSets.drawer.name")}
          optional
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
          name="rule_set_kind"
          label={t("policies.ruleSets.drawer.kind")}
          required
          help={t("policies.ruleSets.drawer.kindHelp")}
          error={errors.kind ?? null}
          width="text"
        >
          {(control) => (
            <Select<RuleSetKind>
              control={control}
              options={kinds.map((value) => ({ value, label: ruleSetKindLabel(value) }))}
              value={kind}
              invalid={errors.kind !== undefined}
              onChange={(next) => {
                setKind(next);
                refusals.edited("kind");
              }}
            />
          )}
        </Field>
        <Field
          name="rule_set_description"
          label={t("policies.ruleSets.drawer.description")}
          optional
          error={errors.description ?? null}
          width="text"
        >
          {(control) => (
            <textarea
              {...control}
              rows={3}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                refusals.edited("description");
              }}
              className={controlClass(errors.description !== undefined, true)}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}

// SF-13:accounting Accounting policies (SCREENS §11.3 list; §0.4 RT-63; §0.5 SCR-URL `q`; §0.7 SCR-ST-03,
// SCR-ST-05, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-11, DS-CMP-19; 04 API-R-13 `GET, POST
// /policies`, `POST /policies/presets/legacy-parity`; E-53; REQ-POL-003 to REQ-POL-005; BUILD_SPEC
// RFD-23). The Policies frame and the DataGrid of registry versions (category, scope, version, status,
// preset, effective dates, author, approver); "New policy version" (drawer: category, scope, entity or
// book, "Start from the current published values") and "Apply legacy-parity preset" (modal: scope,
// entity, book) for `config.author`. The security, AI and platform categories are edited on their
// Settings pages and show "Open in Settings" instead of a version link.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { Combobox } from "../../components/form/Combobox";
import { Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { BOOK_CODES, bookLabel } from "../../lib/api/queries/entities";
import { useMe } from "../../lib/api/queries/me";
import {
  accountingVersionRoute,
  allPoliciesKey,
  currentPublished,
  EVERY_POLICY,
  fetchAllPolicies,
  fetchPoliciesPage,
  LEGACY_PARITY_PATH,
  type LegacyParityPreset,
  POLICIES_PATH,
  policiesGridKey,
  type Policy,
  type PolicyCreate,
  PRESET_LEGACY_PARITY,
  REGISTRY_CATEGORIES,
  type RegistryCategory,
  type RegistryScope,
  SETTINGS_CATEGORIES,
  SETTINGS_CATEGORY_ROUTES,
  VERSION_SCOPES,
} from "../../lib/api/queries/policies";
import { CONFIG_AUTHOR_PERMISSION, CONFIG_READ_PERMISSION } from "../../lib/api/queries/rule-sets";
import { type BookCode, entitiesKey, fetchActiveEntities } from "../../lib/api/queries/tenant";
import { fieldMessages, placeProblem } from "../../lib/api/refusals";
import { formatNumber, NO_VALUE, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { PoliciesPageHeader } from "./revenue";

export function categoryLabel(category: RegistryCategory): string {
  return t(`policies.accounting.category.${category}`);
}

/** SCREENS §11.3 "Preset": `DEFAULT`, `LEGACY_PARITY` or `INDUSTRY_<cluster>`. */
export function presetLabel(preset: string | null): string {
  if (preset === null) {
    return NO_VALUE;
  }
  if (preset === "DEFAULT") {
    return t("policies.accounting.preset.default");
  }
  if (preset === PRESET_LEGACY_PARITY) {
    return t("policies.accounting.preset.legacyParity");
  }
  if (preset.startsWith("INDUSTRY_")) {
    return t("policies.accounting.preset.industry", { cluster: preset.slice("INDUSTRY_".length) });
  }
  return preset;
}

/** SCREENS §11.3 scope: "Tenant", "Entity <code>" or "Book <label>". */
export function scopeLabel(policy: Pick<Policy, "scope" | "entity_code" | "book">): string {
  if (policy.scope === "ENTITY") {
    return `${t("policies.accounting.scope.ENTITY")} ${policy.entity_code ?? ""}`.trim();
  }
  if (policy.scope === "BOOK") {
    return `${t("policies.accounting.scope.BOOK")} ${policy.book === null ? "" : bookLabel(policy.book)}`.trim();
  }
  return t("policies.accounting.scope.TENANT");
}

/** SCREENS §11.3 list grid columns. */
export function policyColumns(): readonly GridColumn<Policy>[] {
  return [
    {
      id: "category",
      header: t("policies.accounting.column.category"),
      kind: "identifier",
      value: (policy) => categoryLabel(policy.category),
      // Settings-owned categories link their Settings page instead of a version editor (SCREENS §11.3).
      href: (policy) =>
        SETTINGS_CATEGORIES.has(policy.category)
          ? (SETTINGS_CATEGORY_ROUTES[policy.category] ?? "/settings")
          : accountingVersionRoute(policy.id),
      width: 200,
    },
    {
      id: "scope",
      header: t("policies.accounting.column.scope"),
      kind: "text",
      value: (policy) => scopeLabel(policy),
      width: 160,
    },
    {
      id: "version",
      header: t("policies.accounting.column.version"),
      kind: "text",
      value: (policy) => t("policies.version.number", { version: String(policy.version_no) }),
      render: (policy) =>
        SETTINGS_CATEGORIES.has(policy.category) ? (
          <Link
            to={SETTINGS_CATEGORY_ROUTES[policy.category] ?? "/settings"}
            className="text-accent-fg hover:underline"
          >
            {t("policies.accounting.openInSettings")}
          </Link>
        ) : (
          <span className="num">
            {t("policies.version.number", { version: String(policy.version_no) })}
          </span>
        ),
      width: 144,
    },
    {
      id: "status",
      header: t("policies.accounting.column.status"),
      kind: "status",
      value: (policy) => policy.status,
      render: (policy) => (
        <StatusChip status={chipFor("E-12", policy.status)?.status ?? policy.status} />
      ),
    },
    {
      id: "preset",
      header: t("policies.accounting.column.preset"),
      kind: "text",
      value: (policy) => presetLabel(policy.preset_code),
      width: 176,
    },
    // 04 SC-V `effective_from` and `effective_to` are instants; the grid shows their UTC date (DS-FMT-17).
    {
      id: "effective_from",
      header: t("policies.accounting.column.effectiveFrom"),
      kind: "date",
      value: (policy) =>
        policy.effective_from === null ? null : timestampDate(policy.effective_from),
    },
    {
      id: "effective_to",
      header: t("policies.accounting.column.effectiveTo"),
      kind: "date",
      value: (policy) => (policy.effective_to === null ? null : timestampDate(policy.effective_to)),
    },
    {
      id: "author",
      header: t("policies.accounting.column.author"),
      kind: "text",
      value: (policy) => policy.created_by.display_name,
      width: 160,
    },
    {
      id: "approver",
      header: t("policies.accounting.column.approver"),
      kind: "text",
      value: (policy) => policy.published_by?.display_name ?? null,
      width: 160,
    },
  ];
}

export function AccountingPolicies() {
  const me = useMe();
  const access = useAccess();
  const title = t("policies.tabs.accounting");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(CONFIG_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    return <AccountingList access={access} />;
  }
  return (
    <div
      data-testid="SF-13-accounting-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <PoliciesPageHeader />
      {body}
    </div>
  );
}

type Dialog = { readonly kind: "none" } | { readonly kind: "new" } | { readonly kind: "preset" };

function AccountingList({ access }: { readonly access: Access }) {
  const [total, setTotal] = useState<number | undefined>(undefined);
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const author = access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION);
  const columns = useMemo(() => policyColumns(), []);
  const source: GridSource<Policy> = {
    queryKey: policiesGridKey(),
    fetchPage: fetchPoliciesPage,
  };
  const countLabel = (value: number) =>
    t("policies.accounting.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  const close = () => setDialog({ kind: "none" });
  const newVersion = author
    ? { label: t("policies.accounting.new"), onAction: () => setDialog({ kind: "new" }) }
    : undefined;

  return (
    <div
      data-testid="SF-13-accounting-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <PoliciesPageHeader />
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<Policy>
          name="policy-versions"
          title={t("policies.accounting.grid")}
          errorTitle={t("policies.accounting.loadError")}
          countLabel={(value, formatted) =>
            t("policies.accounting.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(policy) => policy.id}
          rowLabel={(policy) =>
            `${categoryLabel(policy.category)} ${scopeLabel(policy)} v${String(policy.version_no)}`
          }
          testIdPrefix="SF-13"
          rowTestKey={(policy) =>
            `${policy.category}-${policy.scope}-${policy.entity_code ?? ""}-${policy.book ?? ""}-${String(policy.version_no)}`
          }
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            author ? (
              <>
                <Button variant="secondary" onClick={() => setDialog({ kind: "preset" })}>
                  {t("policies.accounting.applyPreset")}
                </Button>
                <Button variant="primary" onClick={() => setDialog({ kind: "new" })}>
                  {t("policies.accounting.new")}
                </Button>
              </>
            ) : undefined
          }
          filterBar={
            <FilterBar
              fields={[]}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-13-filter-bar-policies"
            />
          }
          emptyState={
            <div data-testid="SF-13-empty-policies">
              <EmptyState
                title={t("policies.accounting.empty.title")}
                description={t("policies.accounting.empty.description")}
                action={newVersion}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("policies.accounting.noResults.title")}
              description={t("policies.accounting.noResults.description")}
            />
          }
        />
      </div>
      {dialog.kind === "new" ? <NewVersionDrawer onClose={close} /> : null}
      {dialog.kind === "preset" ? <PresetModal onClose={close} /> : null}
    </div>
  );
}

/** The categories a policy version is authored for here (the others live on Settings pages). */
const AUTHORED_CATEGORIES: readonly RegistryCategory[] = REGISTRY_CATEGORIES.filter(
  (category) => !SETTINGS_CATEGORIES.has(category),
);

/**
 * docs/dev-guide.md DG-FE-06: the scope fields of the two forms and the members each sends. The entity
 * and the book are on screen for their scope only, and a field that is not on screen takes no member:
 * an error there is the banner's.
 */
function scopeMembers(scope: RegistryScope) {
  return {
    scope: ["scope"],
    entity_code: scope === "ENTITY" ? ["entity_code"] : [],
    book: scope === "BOOK" ? ["book"] : [],
  } as const;
}

function ScopeFields({
  scope,
  entityCode,
  book,
  onScope,
  onEntity,
  onBook,
  errors,
}: {
  readonly scope: RegistryScope;
  readonly entityCode: string | null;
  readonly book: BookCode | null;
  readonly onScope: (scope: RegistryScope) => void;
  readonly onEntity: (code: string | null) => void;
  readonly onBook: (book: BookCode) => void;
  readonly errors: Readonly<Record<string, string>>;
}) {
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  return (
    <>
      <Field
        name="scope"
        label={t("policies.accounting.form.scope")}
        required
        error={errors.scope ?? null}
        width="text"
      >
        {(control) => (
          <Select<RegistryScope>
            control={control}
            options={VERSION_SCOPES.map((value) => ({
              value,
              label: t(`policies.accounting.scope.${value}`),
            }))}
            value={scope}
            onChange={onScope}
          />
        )}
      </Field>
      {scope === "ENTITY" ? (
        <Field
          name="entity_code"
          label={t("policies.accounting.form.entity")}
          required
          error={errors.entity_code ?? null}
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={(entities.data ?? []).map((entity) => ({
                value: entity.code,
                label: `${entity.code} · ${entity.name}`,
              }))}
              value={entityCode}
              invalid={errors.entity_code !== undefined}
              onChange={onEntity}
            />
          )}
        </Field>
      ) : null}
      {scope === "BOOK" ? (
        <Field
          name="book"
          label={t("policies.accounting.form.book")}
          required
          error={errors.book ?? null}
          width="text"
        >
          {(control) => (
            <Select<BookCode>
              control={control}
              options={BOOK_CODES.map((value) => ({ value, label: bookLabel(value) }))}
              value={book}
              invalid={errors.book !== undefined}
              onChange={onBook}
            />
          )}
        </Field>
      ) : null}
    </>
  );
}

/** The category and scope a "New policy version" drawer opens on. */
export interface NewVersionTarget {
  readonly category: RegistryCategory;
  readonly scope: RegistryScope;
  readonly entityCode: string | null;
  readonly book: BookCode | null;
}

/**
 * SCREENS §11.3 "New policy version" drawer. The version editor opens it on the category and scope
 * of a version that can no longer be edited (`initial`; rev 1.56).
 */
export function NewVersionDrawer({
  onClose,
  initial,
}: {
  readonly onClose: () => void;
  readonly initial?: NewVersionTarget;
}) {
  const toast = useToast();
  const navigate = useNavigate();
  const formId = useId();
  const startId = useId();
  const [category, setCategory] = useState<RegistryCategory | null>(initial?.category ?? null);
  const [scope, setScope] = useState<RegistryScope>(initial?.scope ?? "TENANT");
  const [entityCode, setEntityCode] = useState<string | null>(initial?.entityCode ?? null);
  const [book, setBook] = useState<BookCode | null>(initial?.book ?? "ASC606");
  const [startFromCurrent, setStartFromCurrent] = useState(true);
  const [attempted, setAttempted] = useState(false);
  const all = useQuery({
    queryKey: allPoliciesKey(),
    queryFn: fetchAllPolicies,
    enabled: startFromCurrent,
  });
  const create = useCommand<Policy>({
    method: "POST",
    path: POLICIES_PATH,
    invalidates: [EVERY_POLICY],
  });
  const placed = useMemo(
    () => placeProblem(create.problem, { category: ["category"], ...scopeMembers(scope) }),
    [create.problem, scope],
  );
  const errors: Record<string, string> = { ...fieldMessages(placed.fields) };
  if (attempted) {
    if (category === null) {
      errors.category ??= t("policies.accounting.form.categoryRequired");
    }
    if (scope === "ENTITY" && entityCode === null) {
      errors.entity_code ??= t("policies.accounting.form.entityRequired");
    }
    if (scope === "BOOK" && book === null) {
      errors.book ??= t("policies.accounting.form.bookRequired");
    }
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (
      category === null ||
      (scope === "ENTITY" && entityCode === null) ||
      (scope === "BOOK" && book === null)
    ) {
      return;
    }
    const target = {
      id: "",
      category,
      scope,
      entity_code: scope === "ENTITY" ? entityCode : null,
      book: scope === "BOOK" ? book : null,
    };
    const published = startFromCurrent ? currentPublished(all.data ?? [], target) : null;
    // Unticked, the draft starts from the framework defaults: the values sent are the whole set,
    // so the version returns every published value to its default (04 §16.5 `basis`).
    const body: PolicyCreate = {
      category,
      scope,
      entity_code: target.entity_code,
      book: target.book,
      values: published?.values ?? {},
      ...(startFromCurrent ? {} : { basis: "DEFAULTS" as const }),
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("policies.accounting.created", { version: String(outcome.data.version_no) }),
      });
      onClose();
      void navigate(accountingVersionRoute(outcome.data.id));
    }
  };
  return (
    <Drawer
      open
      title={t("policies.accounting.new")}
      dirty={category !== (initial?.category ?? null)}
      submitting={create.pending}
      primaryAction={{ label: t("policies.accounting.form.create"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-13-drawer-new-policy"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="category"
          label={t("policies.accounting.form.category")}
          required
          error={errors.category ?? null}
          width="text"
        >
          {(control) => (
            <Select<RegistryCategory>
              control={control}
              options={AUTHORED_CATEGORIES.map((value) => ({ value, label: categoryLabel(value) }))}
              value={category}
              invalid={errors.category !== undefined}
              onChange={setCategory}
            />
          )}
        </Field>
        <ScopeFields
          scope={scope}
          entityCode={entityCode}
          book={book}
          onScope={setScope}
          onEntity={setEntityCode}
          onBook={setBook}
          errors={errors}
        />
        <label htmlFor={startId} className="flex items-center gap-2 text-body-sm text-fg-1">
          <input
            id={startId}
            type="checkbox"
            checked={startFromCurrent}
            onChange={(event) => setStartFromCurrent(event.target.checked)}
            className="size-4"
          />
          {t("policies.accounting.form.startFromCurrent")}
        </label>
      </form>
    </Drawer>
  );
}

/** SCREENS §11.3 "Apply legacy-parity preset" modal. */
function PresetModal({ onClose }: { readonly onClose: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const formId = useId();
  const [scope, setScope] = useState<RegistryScope>("TENANT");
  const [entityCode, setEntityCode] = useState<string | null>(null);
  const [book, setBook] = useState<BookCode | null>("ASC606");
  const [attempted, setAttempted] = useState(false);
  const preset = useCommand<Policy>({
    method: "POST",
    path: LEGACY_PARITY_PATH,
    invalidates: [EVERY_POLICY],
  });
  const placed = useMemo(
    () => placeProblem(preset.problem, scopeMembers(scope)),
    [preset.problem, scope],
  );
  const errors: Record<string, string> = { ...fieldMessages(placed.fields) };
  if (attempted && scope === "ENTITY" && entityCode === null) {
    errors.entity_code ??= t("policies.accounting.form.entityRequired");
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (scope === "ENTITY" && entityCode === null) {
      return;
    }
    const body: LegacyParityPreset = {
      scope,
      ...(scope === "ENTITY" ? { entity_code: entityCode } : {}),
      ...(scope === "BOOK" ? { book } : {}),
    };
    const outcome = await preset.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({ tone: "positive", message: t("policies.accounting.presetCreated") });
      onClose();
      void navigate(accountingVersionRoute(outcome.data.id));
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("policies.accounting.applyPreset")}
      description={t("policies.accounting.presetDescription")}
      primaryAction={{ label: t("policies.accounting.presetCreate"), form: formId }}
      submitting={preset.pending}
      onClose={onClose}
      testId="SF-13-dialog-legacy-parity"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <RefusalBanner problem={preset.problem} placed={placed} />
        <ScopeFields
          scope={scope}
          entityCode={entityCode}
          book={book}
          onScope={setScope}
          onEntity={setEntityCode}
          onBook={setBook}
          errors={errors}
        />
      </form>
    </Modal>
  );
}

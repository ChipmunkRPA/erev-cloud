// SF-15:chart-of-accounts Chart of accounts (SCREENS_B §9.5; SCREENS §0.4 RT-78, §0.5 SCR-URL `drawer`,
// `row`, §0.7 SCR-ST-03, SCR-PERM-01, SCR-PERM-02; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-21, DS-CMP-23;
// 04 API-R-20 `GET, POST /gl-accounts`, `PATCH /gl-accounts/{id}`, `GET /account-mappings`, API-R-21
// `GET, POST /dimensions`, `GET, POST /dimensions/{code}/values`; BUILD_SPEC RFD-19). The DataGrids
// "Accounts" and "Dimensions". An account code opens "Edit <code>" and "New account" the create drawer
// (`config.author`); a dimension code opens "Dimension values" and "New dimension" the create drawer
// (`masterdata.maintain`). The drawers are URL state (`drawer`, `row`). Deactivating an account the
// published mapping uses shows the SCREENS_B §9.5 warning and waits for "I have reviewed this warning".
// "Import accounts" renders once SF-10:new is built (XR-14).
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field, fieldId } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Select } from "../../components/form/Select";
import { Switch } from "../../components/form/Switch";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  ACCOUNT_AUTHOR_PERMISSION,
  ACCOUNT_TYPES,
  accountPath,
  accountRoleLabel,
  accountsKey,
  type AccountType,
  fetchAccountsPage,
  fetchAllAccounts,
  fetchMappedRoles,
  type GlAccount,
  GL_ACCOUNTS_PATH,
  mappedRolesKey,
  type SourceSystem,
} from "../../lib/api/queries/accounts";
import {
  CUSTOM_DIMENSION_LIMIT,
  type Dimension,
  DIMENSION_MAINTAIN_PERMISSION,
  DIMENSIONS_PATH,
  dimensionsKey,
  dimensionValuesKey,
  dimensionValuesPath,
  fetchAllDimensions,
  fetchDimensionsPage,
  fetchDimensionValues,
} from "../../lib/api/queries/dimensions";
import { useMe } from "../../lib/api/queries/me";
import {
  entitiesKey,
  fetchActiveEntities,
  rowIfMatch,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "./index";

export const DRAWER_ACCOUNT = "account";
export const DRAWER_NEW_ACCOUNT = "new-account";
export const DRAWER_DIMENSION_VALUES = "dimension-values";
export const DRAWER_NEW_DIMENSION = "new-dimension";

/** SCREENS_B §9.5 "Source" words; the other E-38 literals keep their product names. */
export const SOURCE_LABEL_KEYS: Readonly<Record<SourceSystem, string>> = {
  MANUAL_UI: "manual",
  NETSUITE: "netsuite",
  QUICKBOOKS_ONLINE: "quickbooks",
  LEGACY_TEMPLATE_V1: "legacy",
  LEGACY_DB: "legacy",
  CSV_V2: "csv",
  API: "api",
  SALESFORCE: "salesforce",
  STRIPE: "stripe",
};

const ACCOUNTS_SOURCE: GridSource<GlAccount> = {
  queryKey: accountsKey(),
  fetchPage: (cursor, sort) => fetchAccountsPage({}, cursor, sort),
};

const DIMENSIONS_SOURCE: GridSource<Dimension> = {
  queryKey: dimensionsKey(),
  fetchPage: fetchDimensionsPage,
};

export function ChartOfAccounts() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.chartOfAccounts.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(STRUCTURE_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    body = (
      <ChartSections
        author={access.holdsAnywhere(ACCOUNT_AUTHOR_PERMISSION)}
        maintain={access.holdsAnywhere(DIMENSION_MAINTAIN_PERMISSION)}
      />
    );
  }

  return (
    <div className="flex w-full flex-col gap-6 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={title} group="workspace" />
      {body}
    </div>
  );
}

function ChartSections({
  author,
  maintain,
}: {
  readonly author: boolean;
  readonly maintain: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const mapped = useQuery({ queryKey: mappedRolesKey(), queryFn: fetchMappedRoles });
  const drawer = params.get("drawer");
  const row = params.get("row");

  const openDrawer = (name: string, id: string | null = null) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set("drawer", name);
      if (id === null) {
        next.delete("row");
      } else {
        next.set("row", id);
      }
      return next;
    });
  };
  const closeDrawer = () => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete("drawer");
        next.delete("row");
        return next;
      },
      { replace: true },
    );
  };

  const codes = new Map((entities.data ?? []).map((item) => [item.id, item.code]));
  const roles = mapped.data ?? new Map<string, readonly string[]>();

  // API-C-09 sort keys: GET /api/v1/gl-accounts
  const accountColumns: readonly GridColumn<GlAccount>[] = [
    {
      id: "code",
      header: t("settings.chartOfAccounts.column.code"),
      kind: "identifier",
      value: (account) => account.code,
      href: (account) => `?drawer=${DRAWER_ACCOUNT}&row=${account.id}`,
      sortKey: "code",
    },
    {
      id: "name",
      header: t("settings.chartOfAccounts.column.name"),
      kind: "text",
      value: (account) => account.name,
      sortKey: "name",
      width: 280,
    },
    {
      id: "type",
      header: t("settings.chartOfAccounts.column.type"),
      kind: "text",
      value: (account) => t(`settings.chartOfAccounts.type.${account.account_type}`),
      width: 112,
    },
    {
      id: "normal",
      header: t("settings.chartOfAccounts.column.normal"),
      kind: "text",
      value: (account) => t(`settings.chartOfAccounts.normal.${account.normal_balance}`),
      width: 144,
    },
    {
      id: "entities",
      header: t("settings.chartOfAccounts.column.entities"),
      kind: "text",
      value: (account) =>
        account.entity_ids.length === 0
          ? t("settings.chartOfAccounts.allEntities")
          : account.entity_ids.map((id) => codes.get(id) ?? id).join(", "),
    },
    {
      id: "dimensions",
      header: t("settings.chartOfAccounts.column.dimensions"),
      kind: "text",
      width: 192,
      value: (account) =>
        account.required_dimensions.length === 0 ? null : account.required_dimensions.join(", "),
      render: (account) =>
        account.required_dimensions.length === 0 ? (
          "—"
        ) : (
          <span className="font-mono text-mono-sm">{account.required_dimensions.join(", ")}</span>
        ),
    },
    {
      id: "source",
      header: t("settings.chartOfAccounts.column.source"),
      kind: "text",
      value: (account) =>
        t(`settings.chartOfAccounts.source.${SOURCE_LABEL_KEYS[account.source_system]}`),
      width: 136,
    },
    {
      id: "active",
      header: t("settings.chartOfAccounts.column.active"),
      kind: "boolean",
      value: (account) => String(account.is_active),
      width: 96,
    },
    {
      id: "roles",
      header: t("settings.chartOfAccounts.column.roles"),
      kind: "text",
      value: (account) => {
        const held = roles.get(account.code) ?? [];
        return held.length === 0 ? null : held.map(accountRoleLabel).join(", ");
      },
      width: 240,
    },
  ];

  // API-C-09 sort keys: GET /api/v1/dimensions
  const dimensionColumns: readonly GridColumn<Dimension>[] = [
    {
      id: "code",
      header: t("settings.chartOfAccounts.dimensions.column.code"),
      kind: "identifier",
      value: (dimension) => dimension.code,
      href: (dimension) =>
        `?drawer=${DRAWER_DIMENSION_VALUES}&row=${encodeURIComponent(dimension.code)}`,
      sortKey: "code",
    },
    {
      id: "name",
      header: t("settings.chartOfAccounts.dimensions.column.name"),
      kind: "text",
      value: (dimension) => dimension.name,
      sortKey: "name",
      width: 240,
    },
    {
      id: "builtin",
      header: t("settings.chartOfAccounts.dimensions.column.builtin"),
      kind: "boolean",
      value: (dimension) => String(dimension.is_builtin),
      width: 96,
    },
    {
      id: "active",
      header: t("settings.chartOfAccounts.dimensions.column.active"),
      kind: "boolean",
      value: (dimension) => String(dimension.is_active),
      width: 96,
    },
  ];

  return (
    <>
      <div className="flex h-120 min-h-0 flex-col">
        <DataGrid<GlAccount>
          name="accounts"
          title={t("settings.chartOfAccounts.accounts.title")}
          countLabel={(count, formatted) =>
            t("settings.chartOfAccounts.accounts.count", { count, formatted })
          }
          columns={accountColumns}
          source={ACCOUNTS_SOURCE}
          rowKey={(account) => account.id}
          rowLabel={(account) => account.code}
          rowHref={(account) => `?drawer=${DRAWER_ACCOUNT}&row=${account.id}`}
          testIdPrefix="SF-15"
          rowTestKey={(account) => account.code}
          toolbarActions={
            author ? (
              <Button variant="primary" size="sm" onClick={() => openDrawer(DRAWER_NEW_ACCOUNT)}>
                {t("settings.chartOfAccounts.accounts.new")}
              </Button>
            ) : undefined
          }
          emptyState={
            <EmptyState
              title={t("settings.chartOfAccounts.accounts.empty.title")}
              description={t("settings.chartOfAccounts.accounts.empty.description")}
              action={
                author
                  ? {
                      label: t("settings.chartOfAccounts.accounts.new"),
                      onAction: () => openDrawer(DRAWER_NEW_ACCOUNT),
                    }
                  : undefined
              }
            />
          }
        />
      </div>
      <div className="flex h-80 min-h-0 flex-col">
        <DataGrid<Dimension>
          name="dimensions"
          title={t("settings.chartOfAccounts.dimensions.title")}
          countLabel={(count, formatted) =>
            t("settings.chartOfAccounts.dimensions.count", { count, formatted })
          }
          columns={dimensionColumns}
          source={DIMENSIONS_SOURCE}
          rowKey={(dimension) => dimension.id}
          rowLabel={(dimension) => dimension.code}
          rowHref={(dimension) =>
            `?drawer=${DRAWER_DIMENSION_VALUES}&row=${encodeURIComponent(dimension.code)}`
          }
          testIdPrefix="SF-15"
          rowTestKey={(dimension) => `dimension-${dimension.code}`}
          toolbarActions={
            maintain ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => openDrawer(DRAWER_NEW_DIMENSION)}
              >
                {t("settings.chartOfAccounts.dimensions.new")}
              </Button>
            ) : undefined
          }
        />
      </div>
      {drawer === DRAWER_NEW_ACCOUNT && author ? (
        <AccountDrawer account={null} mappedRoles={[]} onClose={closeDrawer} />
      ) : null}
      {drawer === DRAWER_ACCOUNT && row !== null ? (
        <AccountLoader accountId={row} author={author} roles={roles} onClose={closeDrawer} />
      ) : null}
      {drawer === DRAWER_DIMENSION_VALUES && row !== null ? (
        <DimensionValuesDrawer code={row} maintain={maintain} onClose={closeDrawer} />
      ) : null}
      {drawer === DRAWER_NEW_DIMENSION && maintain ? (
        <DimensionDrawer onClose={closeDrawer} />
      ) : null}
    </>
  );
}

interface AccountLoaderProps {
  readonly accountId: string;
  readonly author: boolean;
  readonly roles: ReadonlyMap<string, readonly string[]>;
  readonly onClose: () => void;
}

/** The edit drawer of the `row` account; readers without `config.author` see the fields read-only. */
function AccountLoader({ accountId, author, roles, onClose }: AccountLoaderProps) {
  const accounts = useQuery({
    queryKey: queryKey("gl-accounts", "tenant", { view: "all" }),
    queryFn: fetchAllAccounts,
  });
  const account = accounts.data?.find((candidate) => candidate.id === accountId);
  if (account === undefined) {
    return null;
  }
  return (
    <AccountDrawer
      key={`${account.id}:${String(account.row_version)}`}
      account={account}
      readOnly={!author}
      mappedRoles={roles.get(account.code) ?? []}
      onClose={onClose}
    />
  );
}

interface AccountDrawerProps {
  readonly account: GlAccount | null;
  readonly readOnly?: boolean;
  readonly mappedRoles: readonly string[];
  readonly onClose: () => void;
}

type Balance = "D" | "C";

/**
 * The API members the fields of the account drawer send (DG-FE-06 rev 1.228): a refusal that names
 * another member, `is_active` for one, is the banner's. "Entities" is a field only while the account
 * is not one of all entities.
 */
const ACCOUNT_MEMBERS = {
  code: ["code"],
  name: ["name"],
  account_type: ["account_type"],
  normal_balance: ["normal_balance"],
  entity_ids: ["entity_ids"],
  required_dimensions: ["required_dimensions"],
} as const;
const ACCOUNT_MEMBERS_OF_ALL_ENTITIES = { ...ACCOUNT_MEMBERS, entity_ids: [] } as const;

function AccountDrawer({ account, readOnly = false, mappedRoles, onClose }: AccountDrawerProps) {
  const toast = useToast();
  const formId = useId();
  const reviewId = useId();
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const dimensions = useQuery({
    queryKey: queryKey("dimensions", "tenant", { view: "all" }),
    queryFn: fetchAllDimensions,
  });
  const [code, setCode] = useState(account?.code ?? "");
  const [name, setName] = useState(account?.name ?? "");
  const [type, setType] = useState<AccountType | null>(account?.account_type ?? null);
  const [balance, setBalance] = useState<Balance | null>(account?.normal_balance ?? null);
  const [allEntities, setAllEntities] = useState(
    account === null || account.entity_ids.length === 0,
  );
  const [entityIds, setEntityIds] = useState<readonly string[]>(account?.entity_ids ?? []);
  const [required, setRequired] = useState<readonly string[]>(account?.required_dimensions ?? []);
  const [active, setActive] = useState(account?.is_active ?? true);
  const [reviewed, setReviewed] = useState(false);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const invalidates = [accountsKey(), queryKey("gl-accounts", "tenant", { view: "all" })];
  const create = useCommand<GlAccount>({ method: "POST", path: GL_ACCOUNTS_PATH, invalidates });
  const edit = useCommand<GlAccount>({
    method: "PATCH",
    path: account === null ? GL_ACCOUNTS_PATH : accountPath(account.id),
    invalidates,
  });
  const command = account === null ? create : edit;
  const refusals = useFieldRefusals<keyof typeof ACCOUNT_MEMBERS>(
    command.problem,
    allEntities ? ACCOUNT_MEMBERS_OF_ALL_ENTITIES : ACCOUNT_MEMBERS,
  );
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };
  const deactivating = account !== null && account.is_active && !active && mappedRoles.length > 0;
  const entityValues = allEntities ? [] : entityIds;
  const dirty =
    account === null
      ? code !== "" || name !== ""
      : name !== account.name ||
        type !== account.account_type ||
        balance !== account.normal_balance ||
        active !== account.is_active ||
        JSON.stringify(entityValues) !== JSON.stringify(account.entity_ids) ||
        JSON.stringify(required) !== JSON.stringify(account.required_dimensions);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (readOnly || command.pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (account === null && code.trim() === "") {
      found.code = t("settings.chartOfAccounts.drawer.codeRequired");
    }
    if (name.trim() === "") {
      found.name = t("settings.chartOfAccounts.drawer.nameRequired");
    }
    if (type === null) {
      found.account_type = t("settings.chartOfAccounts.drawer.typeRequired");
    }
    if (balance === null) {
      found.normal_balance = t("settings.chartOfAccounts.drawer.balanceRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0 || type === null || balance === null) {
      return;
    }
    const outcome =
      account === null
        ? await create.submit({
            code: code.trim(),
            name: name.trim(),
            account_type: type,
            normal_balance: balance,
            entity_ids: entityValues,
            required_dimensions: required,
            is_active: active,
          })
        : await edit.submit(
            {
              ...(name !== account.name ? { name: name.trim() } : {}),
              ...(type !== account.account_type ? { account_type: type } : {}),
              ...(balance !== account.normal_balance ? { normal_balance: balance } : {}),
              ...(JSON.stringify(entityValues) !== JSON.stringify(account.entity_ids)
                ? { entity_ids: entityValues }
                : {}),
              ...(JSON.stringify(required) !== JSON.stringify(account.required_dimensions)
                ? { required_dimensions: required }
                : {}),
              ...(active !== account.is_active ? { is_active: active } : {}),
            },
            { ifMatch: rowIfMatch(account.row_version) },
          );
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("settings.chartOfAccounts.drawer.saved", { code: account?.code ?? code.trim() }),
      });
      onClose();
    }
  };

  const problemBanner =
    command.banner !== null || refusals.banner !== null ? (
      <RefusalBanner problem={refusals.banner} placed={refusals.placed} conflict={command.banner} />
    ) : undefined;

  return (
    <Drawer
      open
      title={
        account === null
          ? t("settings.chartOfAccounts.drawer.newTitle")
          : t("settings.chartOfAccounts.drawer.editTitle", { code: account.code })
      }
      subtitle={account?.name}
      dirty={dirty && !readOnly}
      submitting={command.pending}
      banner={problemBanner}
      primaryAction={
        readOnly
          ? undefined
          : {
              label: t("settings.chartOfAccounts.drawer.save"),
              form: formId,
              disabledReason:
                deactivating && !reviewed
                  ? t("settings.chartOfAccounts.drawer.reviewReason")
                  : undefined,
            }
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="code"
          label={t("settings.chartOfAccounts.drawer.code")}
          required={account === null}
          error={errors.code ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={account !== null || readOnly}
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
          name="name"
          label={t("settings.chartOfAccounts.drawer.name")}
          required
          error={errors.name ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
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
          name="account_type"
          label={t("settings.chartOfAccounts.drawer.type")}
          required
          error={errors.account_type ?? null}
          width="text"
        >
          {(control) => (
            <Select<AccountType>
              control={control}
              options={ACCOUNT_TYPES.map((value) => ({
                value,
                label: t(`settings.chartOfAccounts.type.${value}`),
              }))}
              value={type}
              invalid={errors.account_type !== undefined}
              onChange={(value) => {
                if (!readOnly) {
                  setType(value);
                  refusals.edited("account_type");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="normal_balance"
          label={t("settings.chartOfAccounts.drawer.balance")}
          required
          error={errors.normal_balance ?? null}
          width="text"
        >
          {(control) => (
            <Select<Balance>
              control={control}
              options={(["D", "C"] as const).map((value) => ({
                value,
                label: t(`settings.chartOfAccounts.normal.${value}`),
              }))}
              value={balance}
              invalid={errors.normal_balance !== undefined}
              onChange={(value) => {
                if (!readOnly) {
                  setBalance(value);
                  refusals.edited("normal_balance");
                }
              }}
            />
          )}
        </Field>
        <Switch
          label={t("settings.chartOfAccounts.allEntities")}
          checked={allEntities}
          disabledReason={readOnly ? t("settings.chartOfAccounts.drawer.readOnly") : undefined}
          onChange={setAllEntities}
        />
        {allEntities ? null : (
          <Field
            name="entity_ids"
            label={t("settings.chartOfAccounts.drawer.entities")}
            error={errors.entity_ids ?? null}
            width="text"
          >
            {(control) => (
              <MultiSelect<string>
                control={control}
                options={(entities.data ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.code} · ${item.name}`,
                }))}
                values={entityIds}
                onChange={(values) => {
                  if (!readOnly) {
                    setEntityIds(values);
                    refusals.edited("entity_ids");
                  }
                }}
              />
            )}
          </Field>
        )}
        <Field
          name="required_dimensions"
          label={t("settings.chartOfAccounts.drawer.dimensions")}
          optional
          error={errors.required_dimensions ?? null}
          width="text"
        >
          {(control) => (
            <MultiSelect<string>
              control={control}
              options={(dimensions.data ?? []).map((item) => ({
                value: item.code,
                label: `${item.code} · ${item.name}`,
              }))}
              values={required}
              onChange={(values) => {
                if (!readOnly) {
                  setRequired(values);
                  refusals.edited("required_dimensions");
                }
              }}
            />
          )}
        </Field>
        <Switch
          label={t("settings.chartOfAccounts.drawer.active")}
          checked={active}
          disabledReason={readOnly ? t("settings.chartOfAccounts.drawer.readOnly") : undefined}
          onChange={setActive}
        />
        {deactivating ? (
          <div className="flex flex-col gap-2">
            <Banner
              tone="warning"
              announce="live"
              title={t("settings.chartOfAccounts.drawer.mappedWarning", {
                code: account.code,
                roles: mappedRoles.map(accountRoleLabel).join(", "),
              })}
            />
            <label htmlFor={reviewId} className="flex items-center gap-2 text-body-sm text-fg-1">
              <input
                id={reviewId}
                type="checkbox"
                checked={reviewed}
                onChange={(event) => {
                  setReviewed(event.target.checked);
                }}
                className="size-4"
              />
              {t("settings.chartOfAccounts.drawer.reviewed")}
            </label>
          </div>
        ) : null}
      </form>
    </Drawer>
  );
}

/** The API members the two fields of "Add value" send (DG-FE-06 rev 1.228). */
const VALUE_MEMBERS = { code: ["code"], name: ["name"] } as const;

interface DimensionValuesDrawerProps {
  readonly code: string;
  readonly maintain: boolean;
  readonly onClose: () => void;
}

function DimensionValuesDrawer({ code, maintain, onClose }: DimensionValuesDrawerProps) {
  const toast = useToast();
  const formId = useId();
  const values = useQuery({
    queryKey: dimensionValuesKey(code),
    queryFn: () => fetchDimensionValues(code),
  });
  const [valueCode, setValueCode] = useState("");
  const [valueName, setValueName] = useState("");
  const create = useCommand({
    method: "POST",
    path: dimensionValuesPath(code),
    invalidates: [dimensionValuesKey(code)],
  });
  const refusals = useFieldRefusals(create.problem, VALUE_MEMBERS);
  const errors = refusals.fields;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (create.pending) {
      return;
    }
    const outcome = await create.submit({ code: valueCode.trim(), name: valueName.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("settings.chartOfAccounts.values.added", { code: valueCode.trim() }),
      });
      setValueCode("");
      setValueName("");
    }
  };

  const header = "px-3 py-2 text-start font-medium text-fg-2";
  const cell = "px-3 py-2 align-top";
  let list: ReactNode;
  if (values.isError) {
    list = <Banner tone="negative" title={values.error.message} />;
  } else if (values.data === undefined) {
    list = <Skeleton region={t("settings.chartOfAccounts.values.title")} shape="rows" count={4} />;
  } else {
    list = (
      <table
        aria-label={t("settings.chartOfAccounts.values.table")}
        data-testid="SF-15-grid-dimension-values"
        className="w-full border-collapse text-body-sm"
      >
        <thead>
          <tr className="border-b border-default bg-subtle">
            <th scope="col" className={header}>
              {t("settings.chartOfAccounts.values.column.code")}
            </th>
            <th scope="col" className={header}>
              {t("settings.chartOfAccounts.values.column.name")}
            </th>
            <th scope="col" className={header}>
              {t("settings.chartOfAccounts.values.column.active")}
            </th>
          </tr>
        </thead>
        <tbody>
          {values.data.length === 0 ? (
            <tr>
              <td colSpan={3} className={`${cell} text-fg-2`}>
                {t("settings.chartOfAccounts.values.empty")}
              </td>
            </tr>
          ) : (
            values.data.map((value) => (
              <tr key={value.id} className="border-b border-hairline">
                <th scope="row" className={`${cell} text-start font-mono font-normal`}>
                  {value.code}
                </th>
                <td className={cell}>{value.name}</td>
                <td className={cell}>
                  {t(value.is_active ? "common.grid.yes" : "common.grid.no")}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    );
  }

  return (
    <Drawer
      open
      title={t("settings.chartOfAccounts.values.title")}
      subtitle={code}
      initialFocus="title"
      submitting={create.pending}
      banner={
        refusals.banner === null ? undefined : (
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        )
      }
      primaryAction={
        maintain ? { label: t("settings.chartOfAccounts.values.add"), form: formId } : undefined
      }
      onClose={onClose}
    >
      <div className="flex flex-col gap-4">
        {list}
        {maintain ? (
          <form
            id={formId}
            noValidate
            onSubmit={(event) => void submit(event)}
            className="flex flex-col gap-3"
          >
            <Field
              name="value_code"
              label={t("settings.chartOfAccounts.values.code")}
              required
              error={errors.code}
              width="text"
            >
              {(control) => (
                <input
                  {...control}
                  type="text"
                  value={valueCode}
                  onChange={(event) => {
                    setValueCode(event.target.value);
                    refusals.edited("code");
                  }}
                  className={`${controlClass(errors.code !== null)} font-mono`}
                />
              )}
            </Field>
            <Field
              name="value_name"
              label={t("settings.chartOfAccounts.values.name")}
              required
              error={errors.name}
              width="text"
            >
              {(control) => (
                <input
                  {...control}
                  type="text"
                  value={valueName}
                  onChange={(event) => {
                    setValueName(event.target.value);
                    refusals.edited("name");
                  }}
                  className={controlClass(errors.name !== null)}
                />
              )}
            </Field>
          </form>
        ) : null}
      </div>
    </Drawer>
  );
}

/** The API members the two fields of "New dimension" send (DG-FE-06 rev 1.228). */
const DIMENSION_MEMBERS = { code: ["code"], name: ["name"] } as const;

function DimensionDrawer({ onClose }: { readonly onClose: () => void }) {
  const toast = useToast();
  const formId = useId();
  const dimensions = useQuery({
    queryKey: queryKey("dimensions", "tenant", { view: "all" }),
    queryFn: fetchAllDimensions,
  });
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [limitReached, setLimitReached] = useState(false);
  const create = useCommand({
    method: "POST",
    path: DIMENSIONS_PATH,
    invalidates: [dimensionsKey(), queryKey("dimensions", "tenant", { view: "all" })],
  });
  const refusals = useFieldRefusals(create.problem, DIMENSION_MEMBERS);
  const errors = refusals.fields;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (create.pending) {
      return;
    }
    const custom = (dimensions.data ?? []).filter((item) => !item.is_builtin).length;
    setLimitReached(custom >= CUSTOM_DIMENSION_LIMIT);
    if (custom >= CUSTOM_DIMENSION_LIMIT) {
      return;
    }
    const outcome = await create.submit({ code: code.trim(), name: name.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("settings.chartOfAccounts.dimensionDrawer.saved", { code: code.trim() }),
      });
      onClose();
    }
  };

  return (
    <Drawer
      open
      title={t("settings.chartOfAccounts.dimensions.new")}
      dirty={code !== "" || name !== ""}
      submitting={create.pending}
      banner={
        limitReached ? (
          <Banner tone="negative" title={t("settings.chartOfAccounts.dimensionDrawer.limit")} />
        ) : refusals.banner === null ? undefined : (
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        )
      }
      primaryAction={{ label: t("settings.chartOfAccounts.dimensionDrawer.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="dimension_code"
          label={t("settings.chartOfAccounts.dimensionDrawer.code")}
          required
          help={t("settings.chartOfAccounts.dimensionDrawer.codeHelp")}
          error={errors.code}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              id={fieldId("dimension_code")}
              type="text"
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
                refusals.edited("code");
              }}
              className={`${controlClass(errors.code !== null)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="dimension_name"
          label={t("settings.chartOfAccounts.dimensionDrawer.name")}
          required
          error={errors.name}
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
              className={controlClass(errors.name !== null)}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}

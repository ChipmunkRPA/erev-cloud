// SF-15:customers Customers (SCREENS §9; §0.4 RT-79, §0.5 SCR-URL `drawer`, `row`, `q`, `f.*`, §0.7
// SCR-ST-03, SCR-ST-04, SCR-ST-05, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-13, DS-CMP-21,
// DS-FMT-17, DS-FMT-22; 04 API-R-22 `GET, POST /customers`, `PATCH /customers/{id}` (`If-Match`), `GET
// /related-party-groups`; T-REF-19; REQ-REF-010, REQ-REF-011; BUILD_SPEC RFD-20). The Settings frame with
// the Reference data route tabs, the quick search "Search customers" with the Related-party group, Source,
// External id and Active filters, and the DataGrid "Customers" (§9.4 columns; the name links
// SF-15:customer, the group opens the group drawer of SF-15:related-party-groups). "New customer" and
// "Edit customer" (`masterdata.maintain`) share the drawer of §9.5, whose Name carries the identity-only
// help; a `validation-failed` naming a field renders under that field (the duplicate code reads
// "Customer code <code> is already used."). "Import customers" (`import.upload`) links SF-10:new once
// built. Column visibility defaults (Credit grade and Updated hidden) follow the grid's column controls.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { Combobox } from "../../components/form/Combobox";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  allCustomersKey,
  type Customer,
  type CustomerCreate,
  CUSTOMER_READ_PERMISSION,
  type CustomerQuery,
  type CustomerUpdate,
  customerPath,
  customerRoute,
  CUSTOMERS_PATH,
  customersGridKey,
  EVERY_CUSTOMER,
  fetchAllCustomers,
  fetchCustomersPage,
  groupDrawerRoute,
  groupLabel,
  IMPORT_CUSTOMERS_ROUTE,
  IMPORT_UPLOAD_PERMISSION,
  MANUAL_SOURCE,
  MASTERDATA_MAINTAIN_PERMISSION,
  RELATED_PARTY_GROUPS_ROUTE,
  type RelatedPartyGroup,
  SOURCE_LABEL_KEYS,
  SOURCE_SYSTEMS,
  type SourceSystem,
  useCustomer,
  useGroups,
} from "../../lib/api/queries/customers";
import { useMe } from "../../lib/api/queries/me";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { countryOptions } from "../../lib/reference/countries";
import { SettingsPageHeader, useBuiltPaths } from "./index";

const DRAWER_CUSTOMER = "customer";
const IMPORT_NEW_PATH = "/data/imports/new";

function mono(text: string | null) {
  return text === null ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="font-mono text-mono text-fg-2">{text}</span>
  );
}

function yesNo(value: boolean): string {
  return t(value ? "settings.customers.yes" : "settings.customers.no");
}

export function sourceLabel(source: SourceSystem): string {
  return t(`contracts.list.source.${SOURCE_LABEL_KEYS[source]}`);
}

/** SCREENS §9.4 filters: Related-party group, Source, External id (equals) and Active. */
export function customerFilterFields(
  groups: readonly RelatedPartyGroup[],
  groupsLoading: boolean,
): readonly FilterField[] {
  return [
    {
      name: "group",
      label: t("settings.customers.filter.group"),
      kind: "enum",
      operators: ["is"],
      options: groups.map((group) => ({ value: group.id, label: groupLabel(group) })),
      optionsLoading: groupsLoading,
    },
    {
      name: "source",
      label: t("settings.customers.filter.source"),
      kind: "enum",
      operators: ["is", "in"],
      options: SOURCE_SYSTEMS.map((source) => ({ value: source, label: sourceLabel(source) })),
    },
    {
      name: "external_id",
      label: t("settings.customers.filter.externalId"),
      kind: "text",
      operators: ["is"],
    },
    {
      name: "active",
      label: t("settings.customers.filter.active"),
      kind: "boolean",
      operators: ["is"],
    },
  ];
}

export function customerQuery(search: string, fields: readonly FilterField[]): CustomerQuery {
  const parsed = parseFilters(search, fields);
  const value = (name: string) => parsed.filters.find((filter) => filter.field === name)?.values;
  const active = value("active")?.[0];
  return {
    q: parsed.query,
    groupId: value("group")?.[0] ?? null,
    source: value("source") ?? [],
    externalId: value("external_id")?.[0] ?? null,
    isActive: active === undefined ? null : active === "true" || active === "yes",
  };
}

/** SCREENS §9.4 customers grid columns. */
export function customerColumns(
  groups: ReadonlyMap<string, RelatedPartyGroup>,
  groupsBuilt: boolean,
): readonly GridColumn<Customer>[] {
  return [
    {
      id: "name",
      header: t("settings.customers.column.customer"),
      kind: "identifier",
      value: (customer) => customer.name,
      href: (customer) => customerRoute(customer.id),
      sortKey: "name",
      width: 280,
    },
    {
      id: "code",
      header: t("settings.customers.column.code"),
      kind: "text",
      value: (customer) => customer.code,
      render: (customer) => mono(customer.code),
      sortKey: "code",
      width: 128,
    },
    {
      id: "group",
      header: t("settings.customers.column.group"),
      kind: "text",
      value: (customer) => {
        const group = customer.related_party_group;
        return group === null ? null : groupLabel(groups.get(group.id) ?? group);
      },
      render: (customer) => {
        const group = customer.related_party_group;
        if (group === null) {
          return mono(null);
        }
        const label = groupLabel(groups.get(group.id) ?? group);
        return groupsBuilt ? (
          <Link to={groupDrawerRoute(group.id)} className="text-accent-fg hover:underline">
            {label}
          </Link>
        ) : (
          <span>{label}</span>
        );
      },
      width: 220,
    },
    {
      id: "country_code",
      header: t("settings.customers.column.country"),
      kind: "text",
      value: (customer) => customer.country_code,
      render: (customer) => mono(customer.country_code),
      width: 96,
    },
    {
      id: "segment",
      header: t("settings.customers.column.segment"),
      kind: "text",
      value: (customer) => customer.segment,
      width: 144,
    },
    {
      id: "credit_grade",
      header: t("settings.customers.column.creditGrade"),
      kind: "text",
      value: (customer) => customer.credit_grade,
      width: 120,
    },
    {
      id: "source_system",
      header: t("settings.customers.column.source"),
      kind: "text",
      value: (customer) => sourceLabel(customer.source_system),
      width: 144,
    },
    {
      id: "external_id",
      header: t("settings.customers.column.externalId"),
      kind: "text",
      value: (customer) => customer.external_id,
      render: (customer) => mono(customer.external_id),
      width: 144,
    },
    {
      id: "is_active",
      header: t("settings.customers.column.active"),
      kind: "text",
      value: (customer) => yesNo(customer.is_active),
      width: 88,
    },
    {
      id: "updated_at",
      header: t("settings.customers.column.updated"),
      kind: "timestamp",
      value: (customer) => customer.updated_at,
      sortKey: "updated_at",
    },
  ];
}

export function CustomersScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.customers.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(CUSTOMER_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.contractRead"),
        })}
      />
    );
  } else {
    return <CustomersPage access={access} />;
  }
  return (
    <div
      data-testid="SF-15-customers-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="reference" />
      {body}
    </div>
  );
}

function CustomersPage({ access }: { readonly access: Access }) {
  const { search } = useLocation();
  const [params, setParams] = useSearchParams();
  const built = useBuiltPaths();
  const [total, setTotal] = useState<number | undefined>(undefined);
  const title = t("settings.customers.title");
  const maintain = access.holdsAnywhere(MASTERDATA_MAINTAIN_PERMISSION);
  const importable = access.holdsAnywhere(IMPORT_UPLOAD_PERMISSION) && built.has(IMPORT_NEW_PATH);
  const groups = useGroups();
  const groupMap = useMemo(
    () => new Map((groups.data ?? []).map((group) => [group.id, group])),
    [groups.data],
  );
  const fields = useMemo(
    () => customerFilterFields(groups.data ?? [], groups.data === undefined),
    [groups.data],
  );
  const query = customerQuery(search, fields);
  const columns = useMemo(
    () => customerColumns(groupMap, built.has(RELATED_PARTY_GROUPS_ROUTE)),
    [groupMap, built],
  );
  const source: GridSource<Customer> = {
    queryKey: customersGridKey(query),
    fetchPage: (cursor, sort) => fetchCustomersPage(query, cursor, sort),
  };
  const drawer = params.get("drawer");
  const row = params.get("row");
  const openDrawer = (id: string | null) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("drawer", DRAWER_CUSTOMER);
        if (id === null) {
          next.delete("row");
        } else {
          next.set("row", id);
        }
        return next;
      },
      { replace: true },
    );
  };
  const closeDrawer = () => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("drawer");
        next.delete("row");
        return next;
      },
      { replace: true },
    );
  };
  const newCustomer = maintain
    ? { label: t("settings.customers.new"), onAction: () => openDrawer(null) }
    : undefined;
  const importLink = importable
    ? { label: t("settings.customers.import"), href: IMPORT_CUSTOMERS_ROUTE }
    : undefined;
  const countLabel = (value: number) =>
    t("settings.customers.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });

  return (
    <div
      data-testid="SF-15-customers-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="reference">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">{countLabel(total)}</p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<Customer>
          name="customers"
          title={t("settings.customers.grid")}
          errorTitle={t("settings.customers.loadError")}
          countLabel={(value, formatted) =>
            t("settings.customers.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(customer) => customer.id}
          rowLabel={(customer) => customer.name}
          testIdPrefix="SF-15"
          rowTestKey={(customer) => customer.external_id ?? customer.code}
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            <>
              {importLink === undefined ? null : (
                <Link
                  to={importLink.href}
                  className="text-body-sm font-medium text-accent-fg hover:underline"
                >
                  {importLink.label}
                </Link>
              )}
              {newCustomer === undefined ? null : (
                <Button variant="primary" onClick={newCustomer.onAction}>
                  {newCustomer.label}
                </Button>
              )}
            </>
          }
          filterBar={
            <FilterBar
              fields={fields}
              searchLabel={t("settings.customers.search")}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-15-filter-bar-customers"
            />
          }
          emptyState={
            <div data-testid="SF-15-empty-customers">
              <EmptyState
                title={t("settings.customers.empty.title")}
                description={t("settings.customers.empty.description")}
                action={newCustomer}
                link={importLink}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("settings.customers.noResults.title")}
              description={t("settings.customers.noResults.description")}
            />
          }
        />
      </div>
      {drawer === DRAWER_CUSTOMER && row === null ? (
        <CustomerDrawer customer={null} readOnly={!maintain} onClose={closeDrawer} />
      ) : null}
      {drawer === DRAWER_CUSTOMER && row !== null ? (
        <CustomerDrawerLoader customerId={row} readOnly={!maintain} onClose={closeDrawer} />
      ) : null}
    </div>
  );
}

/** Loads the customer of `?row=` for the edit drawer. */
export function CustomerDrawerLoader({
  customerId,
  readOnly,
  onClose,
}: {
  readonly customerId: string;
  readonly readOnly: boolean;
  readonly onClose: () => void;
}) {
  const customer = useCustomer(customerId);
  if (customer.data === undefined) {
    return null;
  }
  return <CustomerDrawer customer={customer.data} readOnly={readOnly} onClose={onClose} />;
}

/**
 * The API members the fields of the customer drawer send (DG-FE-06 rev 1.228): a refusal that names
 * another member, `is_active` for one, is the banner's. "External id" is a field of a new customer
 * and of an imported one only.
 */
const CUSTOMER_MEMBERS = {
  code: ["code"],
  name: ["name"],
  related_party_group_id: ["related_party_group_id"],
  parent_customer_id: ["parent_customer_id"],
  credit_grade: ["credit_grade"],
  segment: ["segment"],
  country_code: ["country_code"],
  external_id: ["external_id"],
} as const;
const CUSTOMER_MEMBERS_WITHOUT_EXTERNAL_ID = { ...CUSTOMER_MEMBERS, external_id: [] } as const;

/** SCREENS §9.5 "New customer" / "Edit customer" drawer. */
export function CustomerDrawer({
  customer,
  readOnly,
  onClose,
}: {
  /** null creates. */
  readonly customer: Customer | null;
  readonly readOnly: boolean;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const activeId = useId();
  const groups = useGroups();
  const customers = useQueryAllCustomers();
  const [code, setCode] = useState(customer?.code ?? "");
  const [name, setName] = useState(customer?.name ?? "");
  const [groupId, setGroupId] = useState<string | null>(customer?.related_party_group_id ?? null);
  const [parentId, setParentId] = useState<string | null>(customer?.parent_customer_id ?? null);
  const [creditGrade, setCreditGrade] = useState(customer?.credit_grade ?? "");
  const [segment, setSegment] = useState(customer?.segment ?? "");
  const [country, setCountry] = useState<string | null>(customer?.country_code ?? null);
  const [externalId, setExternalId] = useState(customer?.external_id ?? "");
  const [active, setActive] = useState(customer?.is_active ?? true);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const invalidates = [EVERY_CUSTOMER];
  const create = useCommand<Customer>({ method: "POST", path: CUSTOMERS_PATH, invalidates });
  const edit = useCommand<Customer>({
    method: "PATCH",
    path: customer === null ? CUSTOMERS_PATH : customerPath(customer.id),
    invalidates,
  });
  const command = customer === null ? create : edit;
  // Customers from an integration or template show Source and External id read-only (SCREENS §9.5).
  const imported = customer !== null && customer.source_system !== MANUAL_SOURCE;
  const refusals = useFieldRefusals<keyof typeof CUSTOMER_MEMBERS>(
    command.problem,
    customer === null || imported ? CUSTOMER_MEMBERS : CUSTOMER_MEMBERS_WITHOUT_EXTERNAL_ID,
  );
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };
  if (errors.code !== undefined && /already|duplicate|exists|used/i.test(errors.code)) {
    errors.code = t("settings.customers.drawer.codeUsed", { code: code.trim() });
  }
  const countries = useMemo(() => countryOptions(), []);
  const optional = (value: string) => (value.trim() === "" ? null : value.trim());
  const dirty =
    customer === null
      ? code !== "" || name !== ""
      : code.trim() !== customer.code ||
        name.trim() !== customer.name ||
        groupId !== customer.related_party_group_id ||
        parentId !== customer.parent_customer_id ||
        optional(creditGrade) !== customer.credit_grade ||
        optional(segment) !== customer.segment ||
        country !== customer.country_code ||
        active !== customer.is_active;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (readOnly || command.pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (code.trim() === "") {
      found.code = t("settings.customers.drawer.codeRequired");
    }
    if (name.trim() === "") {
      found.name = t("settings.customers.drawer.nameRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    if (customer === null) {
      const body: CustomerCreate = {
        code: code.trim(),
        name: name.trim(),
        related_party_group_id: groupId,
        parent_customer_id: parentId,
        credit_grade: optional(creditGrade),
        segment: optional(segment),
        country_code: country,
        external_id: optional(externalId),
        source_system: MANUAL_SOURCE,
        is_active: active,
      };
      const outcome = await create.submit(body);
      if (outcome.kind === "succeeded" && outcome.data !== null) {
        toast.show({
          tone: "positive",
          message: t("settings.customers.drawer.saved", { code: outcome.data.code }),
        });
        onClose();
      }
      return;
    }
    const patch: CustomerUpdate = {
      ...(code.trim() !== customer.code ? { code: code.trim() } : {}),
      ...(name.trim() !== customer.name ? { name: name.trim() } : {}),
      ...(groupId !== customer.related_party_group_id ? { related_party_group_id: groupId } : {}),
      ...(parentId !== customer.parent_customer_id ? { parent_customer_id: parentId } : {}),
      ...(optional(creditGrade) !== customer.credit_grade
        ? { credit_grade: optional(creditGrade) }
        : {}),
      ...(optional(segment) !== customer.segment ? { segment: optional(segment) } : {}),
      ...(country !== customer.country_code ? { country_code: country } : {}),
      ...(active !== customer.is_active ? { is_active: active } : {}),
    };
    const outcome = await edit.submit(patch, { ifMatch: rowIfMatch(customer.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("settings.customers.drawer.saved", { code: code.trim() }),
      });
      onClose();
    }
  };

  const problemBanner =
    command.banner !== null || refusals.banner !== null ? (
      <RefusalBanner problem={refusals.banner} placed={refusals.placed} conflict={command.banner} />
    ) : undefined;
  const parents = (customers.data ?? []).filter((candidate) => candidate.id !== customer?.id);

  return (
    <Drawer
      open
      title={
        customer === null
          ? t("settings.customers.drawer.newTitle")
          : t("settings.customers.drawer.editTitle")
      }
      subtitle={customer?.name}
      dirty={dirty && !readOnly}
      submitting={command.pending}
      banner={problemBanner}
      primaryAction={
        readOnly ? undefined : { label: t("settings.customers.drawer.save"), form: formId }
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-15-drawer-customer"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="code"
          label={t("settings.customers.drawer.code")}
          required
          error={errors.code ?? null}
          help={customer === null ? undefined : t("settings.customers.drawer.codeLocked")}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
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
          label={t("settings.customers.drawer.name")}
          required
          error={errors.name ?? null}
          help={t("settings.customers.help.identityOnly")}
          width="full"
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
          name="related_party_group_id"
          label={t("settings.customers.drawer.group")}
          optional
          error={errors.related_party_group_id ?? null}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                { value: "", label: t("settings.customers.drawer.groupNone") },
                ...(groups.data ?? []).map((group) => ({
                  value: group.id,
                  label: groupLabel(group),
                })),
              ]}
              value={groupId ?? ""}
              invalid={errors.related_party_group_id !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setGroupId(next === "" ? null : next);
                  refusals.edited("related_party_group_id");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="parent_customer_id"
          label={t("settings.customers.drawer.parent")}
          optional
          error={errors.parent_customer_id ?? null}
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={parents.map((candidate) => ({
                value: candidate.id,
                label: `${candidate.code} · ${candidate.name}`,
              }))}
              value={parentId}
              invalid={errors.parent_customer_id !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setParentId(next);
                  refusals.edited("parent_customer_id");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="credit_grade"
          label={t("settings.customers.drawer.creditGrade")}
          optional
          error={errors.credit_grade ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={creditGrade}
              onChange={(event) => {
                setCreditGrade(event.target.value);
                refusals.edited("credit_grade");
              }}
              className={controlClass(errors.credit_grade !== undefined)}
            />
          )}
        </Field>
        <Field
          name="segment"
          label={t("settings.customers.drawer.segment")}
          optional
          error={errors.segment ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={segment}
              onChange={(event) => {
                setSegment(event.target.value);
                refusals.edited("segment");
              }}
              className={controlClass(errors.segment !== undefined)}
            />
          )}
        </Field>
        <Field
          name="country_code"
          label={t("settings.customers.drawer.country")}
          optional
          error={errors.country_code ?? null}
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={countries}
              value={country}
              invalid={errors.country_code !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setCountry(next);
                  refusals.edited("country_code");
                }
              }}
            />
          )}
        </Field>
        {customer === null || imported ? (
          <>
            {imported ? (
              <Field
                name="source_system"
                label={t("settings.customers.drawer.source")}
                width="text"
              >
                {(control) => (
                  <input
                    {...control}
                    type="text"
                    readOnly
                    value={sourceLabel(customer.source_system)}
                    className={controlClass(false)}
                  />
                )}
              </Field>
            ) : null}
            <Field
              name="external_id"
              label={t("settings.customers.drawer.externalId")}
              optional={!imported}
              error={errors.external_id ?? null}
              help={t("settings.customers.drawer.externalIdHelp")}
              width="text"
            >
              {(control) => (
                <input
                  {...control}
                  type="text"
                  readOnly={readOnly || imported}
                  value={externalId}
                  onChange={(event) => {
                    setExternalId(event.target.value);
                    refusals.edited("external_id");
                  }}
                  className={`${controlClass(errors.external_id !== undefined)} font-mono`}
                />
              )}
            </Field>
          </>
        ) : null}
        <label htmlFor={activeId} className="flex items-center gap-2 text-body-sm text-fg-1">
          <input
            id={activeId}
            type="checkbox"
            checked={active}
            disabled={readOnly}
            onChange={(event) => setActive(event.target.checked)}
            className="size-4"
          />
          {t("settings.customers.drawer.active")}
        </label>
      </form>
    </Drawer>
  );
}

/** Every customer in scope for the "Parent customer" combobox. */
function useQueryAllCustomers() {
  return useQuery({ queryKey: allCustomersKey(), queryFn: fetchAllCustomers });
}

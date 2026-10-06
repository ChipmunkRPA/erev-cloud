// SF-15:customer Customer (SCREENS §9; §0.4 RT-80, §0.7 SCR-ST-07, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-06
// customer variant, DS-CMP-09, DS-CMP-10; 04 API-R-22 `GET /customers/{id}`, `PATCH /customers/{id}`,
// `GET /contracts?customer=<id>`, `GET /customers?related_party_group_id=<id>`; BUILD_SPEC RFD-20). The
// record header (name, code with copy, Active or the outline Inactive, the meta row of group, country,
// segment, credit grade, source and external id; primary "Edit customer" for `masterdata.maintain`),
// the "Contracts" panel (SCREENS §3.5 columns 1, 3 to 8 of the customer's contracts, "No contracts for
// this customer yet.") and the "Related customers in <group>" table. An unknown id shows SCR-ST-07
// "Customer not found".
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { ApiProblem } from "../../lib/api/problems";
import {
  type ContractListItem,
  contractsKey,
  EMPTY_CONTRACT_QUERY,
  fetchContractsPage,
} from "../../lib/api/queries/contracts";
import {
  type Customer,
  CUSTOMER_READ_PERMISSION,
  customerRoute,
  CUSTOMERS_ROUTE,
  fetchGroupMembers,
  groupDrawerRoute,
  groupMembersKey,
  MASTERDATA_MAINTAIN_PERMISSION,
  RELATED_PARTY_GROUPS_ROUTE,
  useCustomer,
} from "../../lib/api/queries/customers";
import { useMe } from "../../lib/api/queries/me";
import { formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { contractColumns } from "../contracts/list";
import { SETTINGS_PATH, useBuiltPaths } from "./index";
import { CustomerDrawer, sourceLabel } from "./customers";

/** SCREENS §9.3: columns 1, 3, 4, 5, 6, 7, 8 of §3.5. */
const CONTRACT_COLUMN_IDS: ReadonlySet<string> = new Set([
  "contract",
  "status",
  "entity",
  "inception_date",
  "currency",
  "transaction_price",
  "revenue_to_date",
]);

function mono(text: string | null): ReactNode {
  return text === null ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="font-mono text-mono">{text}</span>
  );
}

function plain(text: string | null): ReactNode {
  return text === null ? <span className="text-fg-3">{NO_VALUE}</span> : text;
}

export function CustomerPage() {
  const { customerId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const customer = useCustomer(customerId);
  const title = t("settings.customer.title");

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
  } else if (customer.isError) {
    body =
      customer.error instanceof ApiProblem && customer.error.status === 404 ? (
        <div data-testid="SF-15-customer-not-found">
          <EmptyState
            title={t("settings.customer.notFound.title")}
            description={t("settings.customer.notFound.description")}
            link={{ label: t("settings.customers.title"), href: CUSTOMERS_ROUTE }}
          />
        </div>
      ) : (
        <Banner tone="negative" title={t("settings.customer.loadError")} />
      );
  } else if (customer.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else {
    return (
      <CustomerRecord
        customer={customer.data}
        maintain={access.holdsAnywhere(MASTERDATA_MAINTAIN_PERMISSION)}
      />
    );
  }
  return (
    <div
      data-testid="SF-15-customer-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

function CustomerRecord({
  customer,
  maintain,
}: {
  readonly customer: Customer;
  readonly maintain: boolean;
}) {
  const built = useBuiltPaths();
  const [editing, setEditing] = useState(false);
  const group = customer.related_party_group;
  const editAction = maintain ? (
    <Button variant="primary" onClick={() => setEditing(true)}>
      {t("settings.customers.edit")}
    </Button>
  ) : undefined;
  const groupsBuilt = built.has(RELATED_PARTY_GROUPS_ROUTE);
  const meta = [
    {
      label: t("settings.customer.meta.group"),
      value:
        group === null ? (
          plain(null)
        ) : groupsBuilt ? (
          <Link to={groupDrawerRoute(group.id)} className="text-accent-fg hover:underline">
            {group.code}
          </Link>
        ) : (
          mono(group.code)
        ),
    },
    { label: t("settings.customer.meta.country"), value: mono(customer.country_code) },
    { label: t("settings.customer.meta.segment"), value: plain(customer.segment) },
    { label: t("settings.customer.meta.creditGrade"), value: plain(customer.credit_grade) },
    { label: t("settings.customer.meta.source"), value: sourceLabel(customer.source_system) },
    { label: t("settings.customer.meta.externalId"), value: mono(customer.external_id) },
  ];
  return (
    <div
      data-testid="SF-15-customer-page"
      className="flex h-full min-h-0 w-full flex-col gap-6 px-[var(--gutter)] py-6"
    >
      <RecordHeader
        title={customer.name}
        breadcrumb={[
          { label: t("settings.index.title"), to: SETTINGS_PATH },
          { label: t("settings.customers.title"), to: CUSTOMERS_ROUTE },
        ]}
        identifier={{
          value: customer.code,
          copyLabel: t("settings.customer.copyCode"),
          copiedMessage: t("settings.customer.copied", { code: customer.code }),
          testId: "SF-15-identifier",
        }}
        chips={
          customer.is_active ? (
            <StatusChip status={t("settings.customers.active")} />
          ) : (
            <OutlineChip label={t("settings.customers.inactive")} />
          )
        }
        meta={meta}
        // The header shows the primary action in its action row and repeats it in the condensed bar.
        actions={editAction}
        primaryAction={editAction}
      />
      <ContractsPanel customer={customer} />
      {group === null ? null : <RelatedCustomers customer={customer} groupCode={group.code} />}
      {editing ? (
        <CustomerDrawer
          customer={customer}
          readOnly={!maintain}
          onClose={() => setEditing(false)}
        />
      ) : null}
    </div>
  );
}

/** SCREENS §9.3 contracts panel: `GET /contracts?customer=<id>` with the §3.5 columns 1, 3 to 8. */
function ContractsPanel({ customer }: { readonly customer: Customer }) {
  const built = useBuiltPaths();
  const [total, setTotal] = useState<number | undefined>(undefined);
  const query = { ...EMPTY_CONTRACT_QUERY, customer: customer.id };
  const columns = useMemo(
    () => contractColumns({ built }).filter((column) => CONTRACT_COLUMN_IDS.has(column.id)),
    [built],
  );
  const source: GridSource<ContractListItem> = {
    queryKey: contractsKey(query),
    fetchPage: (cursor, sort) => fetchContractsPage(query, cursor, sort),
  };
  return (
    <section
      aria-label={t("settings.customer.contracts.title")}
      data-testid="SF-15-customer-contracts"
      className="flex min-h-0 flex-col gap-2"
    >
      <h2 className="text-title-sm text-fg-1">
        {total === undefined
          ? t("settings.customer.contracts.title")
          : t("settings.customer.contracts.titleCount", {
              formatted: formatNumber(total, { kind: "count" }),
            })}
      </h2>
      <DataGrid<ContractListItem>
        name="customer-contracts"
        title={t("settings.customer.contracts.title")}
        errorTitle={t("settings.customer.contracts.loadError")}
        countLabel={(value, formatted) =>
          t("settings.customer.contracts.count", { count: value, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(contract) => contract.id}
        rowLabel={(contract) => contract.external_id}
        testIdPrefix="SF-15"
        rowTestKey={(contract) => contract.external_id}
        onTotalChange={(next) => setTotal(next?.count)}
        emptyState={
          <p data-testid="SF-15-empty-customer-contracts" className="text-body-sm text-fg-3">
            {t("settings.customer.contracts.empty")}
          </p>
        }
      />
    </section>
  );
}

/** SCREENS §9.3 related customers panel: the other members of the customer's group. */
function RelatedCustomers({
  customer,
  groupCode,
}: {
  readonly customer: Customer;
  readonly groupCode: string;
}) {
  const groupId = customer.related_party_group_id ?? "";
  const members = useQuery({
    queryKey: groupMembersKey(groupId),
    queryFn: () => fetchGroupMembers(groupId),
    enabled: groupId !== "",
  });
  const others = (members.data ?? []).filter((member) => member.id !== customer.id);
  const title = t("settings.customer.related.title", { group: groupCode });
  let body: ReactNode;
  if (members.isError) {
    body = <Banner tone="negative" title={t("settings.customer.related.loadError")} />;
  } else if (members.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={2} />;
  } else if (others.length === 0) {
    body = <p className="text-body-sm text-fg-3">{t("settings.customer.related.empty")}</p>;
  } else {
    body = (
      <table
        aria-label={title}
        data-testid="SF-15-customer-related"
        className="w-full text-body-sm"
      >
        <thead>
          <tr className="border-b border-hairline text-caption text-fg-3">
            <th scope="col" className="py-2 pe-4 text-start font-medium">
              {t("settings.customer.related.column.customer")}
            </th>
            <th scope="col" className="py-2 pe-4 text-start font-medium">
              {t("settings.customer.related.column.code")}
            </th>
            <th scope="col" className="py-2 text-start font-medium">
              {t("settings.customer.related.column.country")}
            </th>
          </tr>
        </thead>
        <tbody>
          {others.map((member) => (
            <tr key={member.id} className="border-b border-hairline last:border-b-0">
              <th scope="row" className="py-2 pe-4 text-start font-normal">
                <Link to={customerRoute(member.id)} className="text-accent-fg hover:underline">
                  {member.name}
                </Link>
              </th>
              <td className="py-2 pe-4">{mono(member.code)}</td>
              <td className="py-2">{mono(member.country_code)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <h2 className="text-title-sm text-fg-1">{title}</h2>
      {body}
    </section>
  );
}

// SF-15:product Product (SCREENS §10; §0.4 RT-83, §0.5 `pane=attributes|bundle|ssp|policy-values`,
// §0.7 SCR-ST-07, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-06, DS-CMP-09, DS-CMP-10, DS-CMP-19, DS-CMP-29,
// DS-FMT-09, DS-FMT-11, DS-FMT-13, DS-FMT-16, DS-FMT-20; 04 API-R-23 `GET, PATCH /products/{id}`, `GET, PUT
// /products/{id}/bundle-components`, `POST /products/{id}/propose-principal-agent-change`, API-R-24
// `GET /pob-template-versions/{id}`, API-R-26 `GET /ssp-books`, `GET /ssp-book-versions/{id}`,
// `GET /ssp-book-versions/{id}/entries?product=<code>`; REQ-REF-012 to REQ-REF-014; BUILD_SPEC RFD-21).
// The record header (code with copy, name, Active or outline Inactive, "Edit product"), the pending
// principal-or-agent banner, and the panel tabs "Product sections": Attributes (definition list, the
// disaggregation table with "Required" chips, "Propose principal or agent change"), Bundle components
// (a bundle's rows with "Add component row" and "Save components" — components change by adding rows
// with a later valid-from date, so the grid itself is read-only), SSP (the entries pricing the product
// in each book's current and draft versions; option products read "SSP comes from the option record")
// and Policy values (product values and the default template version's). The proposal drawer sends
// the conclusion and a rationale that carries the control-indicator answers (API-R-23 takes no
// indicator fields).
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

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
import { withPane } from "../../components/record/pane-params";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import {
  allProductsKey,
  type BundleComponent,
  type BundleComponentInput,
  bundleComponentsKey,
  bundleComponentsPath,
  bundleInputs,
  composeRationale,
  EVERY_PRODUCT,
  fetchAllProducts,
  fetchBundleComponents,
  fetchMandatoryAttributes,
  fetchTemplateVersion,
  mandatoryAttributesKey,
  MASTERDATA_MAINTAIN_PERMISSION,
  OPTION_REVENUE_CATEGORY,
  PRINCIPAL_AGENT_VALUES,
  type PrincipalAgent,
  type PrincipalAgentChange,
  type PrincipalAgentChangeResult,
  type Product,
  PRODUCT_READ_PERMISSION,
  type ProductPane,
  productPaneOf,
  PRODUCTS_ROUTE,
  proposePrincipalAgentPath,
  SPLIT_BASES,
  type SplitBasis,
  TEMPLATE_VERSION_ROUTE,
  templateVersionKey,
  templateVersionRoute,
  useProduct,
  useTemplates,
  policyValueRows,
} from "../../lib/api/queries/products";
import {
  fetchAllSspBooks,
  fetchSspBookVersion,
  type SspBook,
  type SspBookVersion,
  type SspEntry,
  sspBookRoute,
  sspBookVersionPath,
} from "../../lib/api/queries/ssp-books";
import { fetchListPage } from "../../lib/api/lists";
import { CURRENCIES_PATH, currencyRegistered } from "../../lib/api/queries/approvals";
import type { components } from "../../lib/api/schema";
import { queryKey } from "../../lib/api/query-keys";
import { placeProblem } from "../../lib/api/refusals";
import {
  formatDate,
  formatMoney,
  formatPercent,
  NO_VALUE,
  registerCurrencies,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { APPROVAL_REQUEST_ROUTE } from "../access/user";
import { SETTINGS_PATH, useBuiltPaths } from "./index";
import { distinctnessLabel, principalAgentLabel, ProductDrawer, yesNo } from "./products";

const SSP_BOOKS_ROUTE = "/policies/ssp-books";

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

export function ProductPage() {
  const { productId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const product = useProduct(productId);
  const title = t("settings.product.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(PRODUCT_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.contractRead"),
        })}
      />
    );
  } else if (product.isError) {
    body =
      product.error instanceof ApiProblem && product.error.status === 404 ? (
        <div data-testid="SF-15-product-not-found">
          <EmptyState
            title={t("settings.product.notFound.title")}
            description={t("settings.product.notFound.description")}
            link={{ label: t("settings.products.title"), href: PRODUCTS_ROUTE }}
          />
        </div>
      ) : (
        <Banner tone="negative" title={t("settings.product.loadError")} />
      );
  } else if (product.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else {
    return (
      <ProductRecord
        product={product.data}
        maintain={access.holdsAnywhere(MASTERDATA_MAINTAIN_PERMISSION)}
      />
    );
  }
  return (
    <div
      data-testid="SF-15-product-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

type Dialog = { readonly kind: "none" } | { readonly kind: "edit" } | { readonly kind: "propose" };

function ProductRecord({
  product,
  maintain,
}: {
  readonly product: Product;
  readonly maintain: boolean;
}) {
  const built = useBuiltPaths();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const pane = productPaneOf(params.get("pane"));
  const panes: readonly ProductPane[] = product.is_bundle
    ? ["attributes", "bundle", "ssp", "policy-values"]
    : ["attributes", "ssp", "policy-values"];
  const paneLabel = (candidate: ProductPane) =>
    t(
      candidate === "policy-values"
        ? "settings.product.pane.policyValues"
        : `settings.product.pane.${candidate}`,
    );
  const setPane = (next: string) =>
    setParams(
      (previous) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const nextParams = withPane(previous, next === "attributes" ? null : next);
        return nextParams;
      },
      { replace: true },
    );
  const editAction = maintain ? (
    <Button variant="primary" onClick={() => setDialog({ kind: "edit" })}>
      {t("settings.products.edit")}
    </Button>
  ) : undefined;
  const pending = product.pending_approval_request_id;
  const close = () => setDialog({ kind: "none" });

  return (
    <div
      data-testid="SF-15-product-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <RecordHeader
        title={product.name}
        breadcrumb={[
          { label: t("settings.index.title"), to: SETTINGS_PATH },
          { label: t("settings.products.title"), to: PRODUCTS_ROUTE },
        ]}
        identifier={{
          value: product.code,
          copyLabel: t("settings.product.copyCode"),
          copiedMessage: t("settings.product.copied", { code: product.code }),
          testId: "SF-15-identifier",
        }}
        chips={
          product.is_active ? (
            <StatusChip status={t("settings.customers.active")} />
          ) : (
            <OutlineChip label={t("settings.customers.inactive")} />
          )
        }
        meta={[
          {
            label: t("settings.product.attributes.revenueCategory"),
            value: mono(product.revenue_category),
          },
          { label: t("settings.product.attributes.unit"), value: mono(product.unit_of_measure) },
          {
            label: t("settings.product.attributes.principalAgent"),
            value: principalAgentLabel(product.principal_agent),
          },
        ]}
        actions={editAction}
        primaryAction={editAction}
        banner={
          pending === null ? undefined : (
            <div data-testid="SF-15-banner-principal-agent">
              <Banner
                tone="info"
                title={t("settings.product.pending")}
                actions={
                  built.has(APPROVAL_REQUEST_ROUTE) ? (
                    <Link
                      to={`/approvals/requests/${pending}`}
                      className="text-body-sm font-medium text-accent-fg hover:underline"
                    >
                      {t("settings.product.viewRequest")}
                    </Link>
                  ) : undefined
                }
              />
            </div>
          )
        }
      />
      <PanelTabs
        label={t("settings.product.sections")}
        tabs={panes.map((candidate) => ({ id: candidate, label: paneLabel(candidate) }))}
        selectedId={panes.includes(pane) ? pane : "attributes"}
        onChange={setPane}
      >
        {pane === "bundle" && product.is_bundle ? (
          <BundlePane product={product} maintain={maintain} />
        ) : pane === "ssp" ? (
          <SspPane product={product} />
        ) : pane === "policy-values" ? (
          <PolicyValuesPane product={product} />
        ) : (
          <AttributesPane
            product={product}
            maintain={maintain}
            onPropose={() => setDialog({ kind: "propose" })}
          />
        )}
      </PanelTabs>
      {dialog.kind === "edit" ? (
        <ProductDrawer product={product} readOnly={!maintain} onClose={close} />
      ) : null}
      {dialog.kind === "propose" ? <ProposeDrawer product={product} onClose={close} /> : null}
    </div>
  );
}

/** SCREENS §10.4 Attributes definition list. */
function AttributesPane({
  product,
  maintain,
  onPropose,
}: {
  readonly product: Product;
  readonly maintain: boolean;
  readonly onPropose: () => void;
}) {
  const built = useBuiltPaths();
  const templates = useTemplates();
  const mandatory = useQuery({
    queryKey: mandatoryAttributesKey(),
    queryFn: fetchMandatoryAttributes,
  });
  const template =
    product.default_pob_template_id === null
      ? null
      : (templates.data?.find((candidate) => candidate.id === product.default_pob_template_id) ??
        null);
  const current = template?.current_version ?? null;
  const required = new Set(mandatory.data ?? []);
  const attributes = Object.entries(product.disaggregation);
  const rows: readonly { readonly label: string; readonly value: ReactNode }[] = [
    { label: t("settings.product.attributes.code"), value: mono(product.code) },
    { label: t("settings.product.attributes.sku"), value: mono(product.sku_number) },
    { label: t("settings.product.attributes.name"), value: product.name },
    { label: t("settings.product.attributes.family"), value: plain(product.product_family) },
    {
      label: t("settings.product.attributes.revenueCategory"),
      value: mono(product.revenue_category),
    },
    {
      label: t("settings.product.attributes.template"),
      value:
        template === null ? (
          plain(null)
        ) : built.has(TEMPLATE_VERSION_ROUTE) && current !== null ? (
          <Link
            to={templateVersionRoute(template.id, current.id)}
            className="font-mono text-mono text-accent-fg hover:underline"
          >
            {`${template.code} v${String(current.version_no)}`}
          </Link>
        ) : (
          mono(current === null ? template.code : `${template.code} v${String(current.version_no)}`)
        ),
    },
    {
      label: t("settings.product.attributes.distinctness"),
      value: distinctnessLabel(product.distinctness_default),
    },
    { label: t("settings.product.attributes.unit"), value: mono(product.unit_of_measure) },
    { label: t("settings.product.attributes.bundle"), value: yesNo(product.is_bundle) },
    { label: t("settings.product.attributes.active"), value: yesNo(product.is_active) },
  ];
  return (
    <div className="flex flex-col gap-4 pt-3" data-testid="SF-15-pane-attributes">
      <dl className="grid grid-cols-[minmax(0,14rem)_minmax(0,1fr)] gap-x-4 gap-y-2 text-body-sm">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <dt className="text-fg-3">{row.label}</dt>
            <dd className="text-fg-1">{row.value}</dd>
          </div>
        ))}
        <dt className="text-fg-3">{t("settings.product.attributes.principalAgent")}</dt>
        <dd className="flex flex-wrap items-center gap-3 text-fg-1">
          {principalAgentLabel(product.principal_agent)}
          {maintain ? (
            <Button variant="secondary" size="sm" onClick={onPropose}>
              {t("settings.products.proposePrincipalAgent")}
            </Button>
          ) : null}
        </dd>
      </dl>
      <section
        aria-label={t("settings.product.attributes.disaggregation")}
        className="flex flex-col gap-2"
      >
        <h3 className="text-body-sm font-medium text-fg-1">
          {t("settings.product.attributes.disaggregation")}
        </h3>
        {attributes.length === 0 ? (
          <p className="text-body-sm text-fg-3">
            {required.size === 0
              ? t("settings.product.attributes.disaggregationNoneRequired")
              : t("settings.product.attributes.disaggregationEmpty")}
          </p>
        ) : (
          <table
            aria-label={t("settings.product.attributes.disaggregation")}
            data-testid="SF-15-product-disaggregation"
            className="w-full text-body-sm"
          >
            <thead>
              <tr className="border-b border-hairline text-caption text-fg-3">
                <th scope="col" className="py-2 pe-4 text-start font-medium">
                  {t("settings.product.attributes.attribute")}
                </th>
                <th scope="col" className="py-2 text-start font-medium">
                  {t("settings.product.attributes.value")}
                </th>
              </tr>
            </thead>
            <tbody>
              {attributes.map(([key, value]) => (
                <tr key={key} className="border-b border-hairline last:border-b-0">
                  <th scope="row" className="py-2 pe-4 text-start font-normal">
                    <span className="inline-flex items-center gap-2">
                      {mono(key)}
                      {required.has(key) ? (
                        <OutlineChip label={t("settings.product.attributes.required")} />
                      ) : null}
                    </span>
                  </th>
                  <td className="py-2 text-fg-1">
                    {typeof value === "string" ? value : JSON.stringify(value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

/** A component row typed in the "Add component row" form. */
interface ComponentDraft {
  readonly productId: string | null;
  readonly quantity: string;
  readonly splitBasis: SplitBasis;
  readonly splitRatio: string;
  readonly sequence: string;
  readonly validFromText: string;
  readonly validFrom: string | null;
  readonly validToText: string;
  readonly validTo: string | null;
}

const EMPTY_DRAFT: ComponentDraft = {
  productId: null,
  quantity: "1",
  splitBasis: "relative_ssp",
  splitRatio: "",
  sequence: "1",
  validFromText: "",
  validFrom: null,
  validToText: "",
  validTo: null,
};

function splitBasisLabel(basis: SplitBasis): string {
  return t(`settings.products.splitBasis.${basis}`);
}

/** SCREENS §10.4 bundle components columns. */
export function bundleColumns(): readonly GridColumn<BundleComponent>[] {
  return [
    {
      id: "component",
      header: t("settings.product.bundle.column.component"),
      kind: "identifier",
      value: (row) => row.component_product.code,
      width: 160,
    },
    {
      id: "quantity_per_bundle",
      header: t("settings.product.bundle.column.quantity"),
      kind: "number",
      numberKind: "quantity",
      value: (row) => row.quantity_per_bundle,
      width: 144,
    },
    {
      id: "split_basis",
      header: t("settings.product.bundle.column.splitBasis"),
      kind: "text",
      value: (row) => splitBasisLabel(row.split_basis),
      width: 144,
    },
    {
      id: "split_ratio",
      header: t("settings.product.bundle.column.splitRatio"),
      kind: "text",
      value: (row) => row.split_ratio,
      render: (row) => (
        <span className="num">
          {row.split_ratio === null ? NO_VALUE : formatPercent(row.split_ratio, { kind: "share" })}
        </span>
      ),
      width: 128,
    },
    {
      id: "sequence",
      header: t("settings.product.bundle.column.sequence"),
      kind: "number",
      numberKind: "count",
      value: (row) => String(row.sequence),
      width: 96,
    },
    {
      id: "valid_from",
      header: t("settings.product.bundle.column.validFrom"),
      kind: "date",
      value: (row) => row.valid_from,
      render: (row) => <span className="num">{formatDate(row.valid_from)}</span>,
    },
    {
      id: "valid_to",
      header: t("settings.product.bundle.column.validTo"),
      kind: "date",
      value: (row) => row.valid_to,
      render: (row) => <span className="num">{formatDate(row.valid_to)}</span>,
    },
  ];
}

function BundlePane({
  product,
  maintain,
}: {
  readonly product: Product;
  readonly maintain: boolean;
}) {
  const toast = useToast();
  const formId = useId();
  const [drafts, setDrafts] = useState<readonly ComponentDraft[]>([]);
  const [attempted, setAttempted] = useState(false);
  const stored = useQuery({
    queryKey: bundleComponentsKey(product.id),
    queryFn: () => fetchBundleComponents(product.id),
  });
  const products = useQuery({ queryKey: allProductsKey(), queryFn: fetchAllProducts });
  const save = useCommand({
    method: "PUT",
    path: bundleComponentsPath(product.id),
    invalidates: [bundleComponentsKey(product.id), EVERY_PRODUCT],
  });
  const columns = useMemo(() => bundleColumns(), []);
  const source: GridSource<BundleComponent> = useMemo(
    () => ({
      queryKey: queryKey("products", "tenant", { view: "bundle-grid", id: product.id }),
      fetchPage: async () => {
        const loaded = await fetchBundleComponents(product.id);
        return {
          items: loaded.components,
          nextCursor: null,
          total: { count: loaded.components.length, capped: false },
        };
      },
    }),
    [product.id],
  );
  const draftError = (draft: ComponentDraft): string | null => {
    if (draft.productId === null) {
      return t("settings.product.bundle.row.componentRequired");
    }
    if (!/^\d+(\.\d+)?$/.test(draft.quantity.trim()) || Number(draft.quantity) <= 0) {
      return t("settings.product.bundle.row.quantityRequired");
    }
    if (draft.splitBasis === "fixed_percentage" && draft.splitRatio.trim() === "") {
      return t("settings.product.bundle.row.splitRatioRequired");
    }
    if (draft.validFrom === null) {
      return t("settings.product.bundle.row.validFromRequired");
    }
    return null;
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (drafts.length === 0 || drafts.some((draft) => draftError(draft) !== null)) {
      return;
    }
    const components: BundleComponentInput[] = [
      ...bundleInputs(stored.data?.components ?? []),
      ...drafts.map((draft) => ({
        component_product_id: draft.productId ?? "",
        quantity_per_bundle: draft.quantity.trim(),
        sequence: Number(draft.sequence) || 1,
        split_basis: draft.splitBasis,
        split_ratio: draft.splitBasis === "fixed_percentage" ? draft.splitRatio.trim() : null,
        valid_from: draft.validFrom ?? "",
        valid_to: draft.validTo,
      })),
    ];
    const outcome = await save.submit({ components });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("settings.product.bundle.saved") });
      setDrafts([]);
      setAttempted(false);
    }
  };
  const componentOptions = (products.data ?? [])
    .filter((candidate) => candidate.id !== product.id)
    .map((candidate) => ({ value: candidate.id, label: `${candidate.code} · ${candidate.name}` }));
  return (
    <div className="flex min-h-0 flex-col gap-3 pt-3" data-testid="SF-15-pane-bundle">
      <RefusalBanner problem={save.problem} />
      {(stored.data?.components.length ?? 0) > 0 ? (
        <p className="text-body-sm text-fg-3">{t("settings.product.bundle.laterRows")}</p>
      ) : null}
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<BundleComponent>
          name="bundle-components"
          title={t("settings.product.bundle.title")}
          errorTitle={t("settings.product.bundle.loadError")}
          countLabel={(value, formatted) =>
            t("settings.product.bundle.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(row) => row.id}
          rowLabel={(row) => row.component_product.code}
          testIdPrefix="SF-15"
          rowTestKey={(row) => `${row.component_product.code}-${row.valid_from}`}
          emptyState={
            <EmptyState
              title={t("settings.product.bundle.empty.title")}
              description={t("settings.product.bundle.empty.description")}
            />
          }
        />
      </div>
      {maintain ? (
        <form
          id={formId}
          noValidate
          onSubmit={(event) => void submit(event)}
          className="flex flex-col gap-3"
          aria-label={t("settings.product.bundle.addRow")}
        >
          {drafts.map((draft, index) => {
            const error = attempted ? draftError(draft) : null;
            const update = (patch: Partial<ComponentDraft>) =>
              setDrafts((previous) =>
                previous.map((row, at) => (at === index ? { ...row, ...patch } : row)),
              );
            return (
              <fieldset
                key={String(index)}
                className="flex flex-wrap items-end gap-3 rounded-md border border-hairline p-3"
              >
                <legend className="text-body-sm font-medium text-fg-1">
                  {t("settings.product.bundle.addRow")} {String(index + 1)}
                </legend>
                <Field
                  name={`component-${String(index)}`}
                  label={t("settings.product.bundle.row.component")}
                  required
                  error={error}
                  width="text"
                >
                  {(control) => (
                    <Combobox
                      control={control}
                      options={componentOptions}
                      value={draft.productId}
                      invalid={error !== null}
                      onChange={(next) => update({ productId: next })}
                    />
                  )}
                </Field>
                <Field
                  name={`quantity-${String(index)}`}
                  label={t("settings.product.bundle.row.quantity")}
                  required
                  width="money"
                >
                  {(control) => (
                    <input
                      {...control}
                      type="text"
                      inputMode="decimal"
                      value={draft.quantity}
                      onChange={(event) => update({ quantity: event.target.value })}
                      className={`${controlClass(false)} num`}
                    />
                  )}
                </Field>
                <Field
                  name={`split-basis-${String(index)}`}
                  label={t("settings.product.bundle.row.splitBasis")}
                  required
                  width="text"
                >
                  {(control) => (
                    <Select<SplitBasis>
                      control={control}
                      options={SPLIT_BASES.map((basis) => ({
                        value: basis,
                        label: splitBasisLabel(basis),
                      }))}
                      value={draft.splitBasis}
                      onChange={(next) => update({ splitBasis: next })}
                    />
                  )}
                </Field>
                {draft.splitBasis === "fixed_percentage" ? (
                  <Field
                    name={`split-ratio-${String(index)}`}
                    label={t("settings.product.bundle.row.splitRatio")}
                    required
                    width="money"
                  >
                    {(control) => (
                      <input
                        {...control}
                        type="text"
                        inputMode="decimal"
                        value={draft.splitRatio}
                        onChange={(event) => update({ splitRatio: event.target.value })}
                        className={`${controlClass(false)} num`}
                      />
                    )}
                  </Field>
                ) : null}
                <Field
                  name={`sequence-${String(index)}`}
                  label={t("settings.product.bundle.row.sequence")}
                  width="money"
                >
                  {(control) => (
                    <input
                      {...control}
                      type="text"
                      inputMode="numeric"
                      value={draft.sequence}
                      onChange={(event) => update({ sequence: event.target.value })}
                      className={`${controlClass(false)} num`}
                    />
                  )}
                </Field>
                <Field
                  name={`valid-from-${String(index)}`}
                  label={t("settings.product.bundle.row.validFrom")}
                  required
                  width="date"
                >
                  {(control) => (
                    <DateInput
                      control={control}
                      value={draft.validFromText}
                      onChange={(text) => update({ validFromText: text })}
                      onValue={(date) => update({ validFrom: date })}
                    />
                  )}
                </Field>
                <Field
                  name={`valid-to-${String(index)}`}
                  label={t("settings.product.bundle.row.validTo")}
                  optional
                  width="date"
                >
                  {(control) => (
                    <DateInput
                      control={control}
                      value={draft.validToText}
                      onChange={(text) => update({ validToText: text })}
                      onValue={(date) => update({ validTo: date })}
                    />
                  )}
                </Field>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDrafts((previous) => previous.filter((_, at) => at !== index))}
                >
                  {t("settings.product.bundle.row.remove")}
                </Button>
              </fieldset>
            );
          })}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setDrafts((previous) => [...previous, EMPTY_DRAFT])}
            >
              {t("settings.product.bundle.addRow")}
            </Button>
            {drafts.length === 0 ? null : (
              <Button variant="primary" size="sm" type="submit" form={formId}>
                {t("settings.product.bundle.save")}
              </Button>
            )}
          </div>
        </form>
      ) : null}
    </div>
  );
}

interface SspRow {
  readonly book: SspBook;
  readonly version: SspBookVersion;
  readonly entry: SspEntry;
}

/** SCREENS §10.3 SSP panel read: the product's entries in each book's current and draft versions. */
export async function fetchProductSsp(productCode: string): Promise<readonly SspRow[]> {
  const books = await fetchAllSspBooks();
  const rows: SspRow[] = [];
  for (const book of books) {
    const versionIds = [
      ...new Set([book.current_version?.id ?? null, book.draft_version_id]),
    ].filter((id): id is string => id !== null);
    for (const versionId of versionIds) {
      const [version, entries] = await Promise.all([
        fetchSspBookVersion(versionId),
        fetchListPage<SspEntry>(
          `${sspBookVersionPath(versionId)}/entries`,
          { product: productCode, sort: "product_code" },
          null,
          { limit: 200, count: false },
        ),
      ]);
      for (const entry of entries.items) {
        rows.push({ book, version, entry });
      }
    }
  }
  await ensureCurrencies(rows.map((row) => row.entry.currency));
  return rows;
}

/** Registers the minor units of the entries' currencies (DS-FMT-03); a reader without the catalogue
 *  read keeps the raw values unformatted rather than failing the pane. */
async function ensureCurrencies(codes: readonly string[]): Promise<void> {
  const missing = [...new Set(codes)].filter((code) => !currencyRegistered(code));
  if (missing.length === 0) {
    return;
  }
  try {
    const page = await fetchListPage<components["schemas"]["CurrencyOut"]>(
      CURRENCIES_PATH,
      { code: missing },
      null,
      { limit: 200, count: false },
    );
    registerCurrencies(page.items);
  } catch (error) {
    if (!(error instanceof ApiProblem && error.status === 403)) {
      throw error;
    }
  }
}

function versionLabel(version: SspBookVersion): string {
  return (
    version.legacy_version_label ??
    version.methodology_label ??
    t("settings.product.ssp.version", { version: String(version.version_no) })
  );
}

function effectiveLabel(version: SspBookVersion): string {
  if (version.effective_from_date === null) {
    return NO_VALUE;
  }
  // DS-FMT-20 date range: a join of two dates, so no catalogue template.
  const from = formatDate(version.effective_from_date);
  return version.effective_to_date === null
    ? `${from} –`
    : `${from} – ${formatDate(version.effective_to_date)}`;
}

function SspPane({ product }: { readonly product: Product }) {
  const built = useBuiltPaths();
  const ssp = useQuery({
    queryKey: queryKey("ssp-books", "tenant", { view: "product", product: product.code }),
    queryFn: () => fetchProductSsp(product.code),
  });
  const title = t("settings.product.ssp.title");
  // DS-FMT-13 unit prices in the book currency's minor unit.
  const money = (value: string | null, currency: string) =>
    value === null ? NO_VALUE : currencyRegistered(currency) ? formatMoney(value, currency) : value;
  let body: ReactNode;
  if (product.revenue_category === OPTION_REVENUE_CATEGORY) {
    body = (
      <p className="text-body-sm text-fg-2" data-testid="SF-15-product-ssp-option">
        {t("settings.product.ssp.option")}
      </p>
    );
  } else if (ssp.isError) {
    body = <Banner tone="negative" title={t("settings.product.ssp.loadError")} />;
  } else if (ssp.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={3} />;
  } else if (ssp.data.length === 0) {
    body = (
      <p className="flex flex-wrap items-center gap-3 text-body-sm text-fg-2">
        {t("settings.product.ssp.empty")}
        {built.has(SSP_BOOKS_ROUTE) ? (
          <Link to={SSP_BOOKS_ROUTE} className="font-medium text-accent-fg hover:underline">
            {t("settings.product.ssp.openBooks")}
          </Link>
        ) : null}
      </p>
    );
  } else {
    body = (
      <table
        aria-label={title}
        data-testid="SF-15-grid-product-ssp"
        className="w-full text-body-sm"
      >
        <thead>
          <tr className="border-b border-hairline text-caption text-fg-3">
            {[
              "book",
              "version",
              "status",
              "effective",
              "method",
              "low",
              "mid",
              "high",
              "point",
              "currency",
            ].map((column) => (
              <th
                key={column}
                scope="col"
                className={`py-2 pe-4 font-medium ${["low", "mid", "high", "point"].includes(column) ? "text-end" : "text-start"}`}
              >
                {t(`settings.product.ssp.column.${column}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ssp.data.map(({ book, version, entry }) => {
            const band = entry.ranges[0];
            const chip = chipFor("E-12", version.status);
            return (
              <tr
                key={entry.id}
                data-testid={`SF-15-ssp-${book.code}-${String(version.version_no)}`}
                className="border-b border-hairline last:border-b-0"
              >
                <th scope="row" className="py-2 pe-4 text-start font-normal">
                  {built.has(SSP_BOOKS_ROUTE) ? (
                    <Link
                      to={sspBookRoute(book.id)}
                      className="font-mono text-mono text-accent-fg hover:underline"
                    >
                      {book.code}
                    </Link>
                  ) : (
                    mono(book.code)
                  )}
                </th>
                <td className="py-2 pe-4">{versionLabel(version)}</td>
                <td className="py-2 pe-4">
                  <StatusChip status={chip?.status ?? version.status} />
                </td>
                <td className="num py-2 pe-4">{effectiveLabel(version)}</td>
                <td className="py-2 pe-4">{t(`policies.ssp.method.${entry.method}`)}</td>
                <td className="num py-2 pe-4 text-end">
                  {money(band?.low_value ?? null, entry.currency)}
                </td>
                <td className="num py-2 pe-4 text-end">
                  {money(band?.mid_value ?? null, entry.currency)}
                </td>
                <td className="num py-2 pe-4 text-end">
                  {money(band?.high_value ?? null, entry.currency)}
                </td>
                <td className="num py-2 pe-4 text-end">
                  {money(band?.point_value ?? entry.observable_point, entry.currency)}
                </td>
                <td className="py-2 pe-4">{mono(entry.currency)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }
  return (
    <section aria-label={title} className="flex flex-col gap-2 pt-3" data-testid="SF-15-pane-ssp">
      <h3 className="text-body-sm font-medium text-fg-1">{title}</h3>
      {body}
    </section>
  );
}

function PolicyValuesPane({ product }: { readonly product: Product }) {
  const templates = useTemplates();
  const template =
    product.default_pob_template_id === null
      ? null
      : (templates.data?.find((candidate) => candidate.id === product.default_pob_template_id) ??
        null);
  const currentId = template?.current_version?.id ?? null;
  const version = useQuery({
    queryKey: templateVersionKey(currentId ?? ""),
    queryFn: () => fetchTemplateVersion(currentId ?? ""),
    enabled: currentId !== null,
  });
  const title = t("settings.product.policyValues.title");
  const rows = policyValueRows(product, version.data ?? null);
  let body: ReactNode;
  if (version.isError) {
    body = <Banner tone="negative" title={t("settings.product.policyValues.loadError")} />;
  } else if (currentId !== null && version.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={3} />;
  } else if (rows.length === 0) {
    body = <p className="text-body-sm text-fg-3">{t("settings.product.policyValues.empty")}</p>;
  } else {
    body = (
      <table
        aria-label={title}
        data-testid="SF-15-product-policy-values"
        className="w-full text-body-sm"
      >
        <thead>
          <tr className="border-b border-hairline text-caption text-fg-3">
            <th scope="col" className="py-2 pe-4 text-start font-medium">
              {t("settings.product.policyValues.column.key")}
            </th>
            <th scope="col" className="py-2 pe-4 text-start font-medium">
              {t("settings.product.policyValues.column.value")}
            </th>
            <th scope="col" className="py-2 text-start font-medium">
              {t("settings.product.policyValues.column.level")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.level}:${row.key}`}
              className="border-b border-hairline last:border-b-0"
            >
              <th scope="row" className="py-2 pe-4 text-start font-normal">
                {mono(row.key)}
              </th>
              <td className="py-2 pe-4 text-fg-1">{row.value}</td>
              <td className="py-2 text-fg-2">
                {row.level === "product"
                  ? t("settings.product.policyValues.level.product")
                  : t("settings.product.policyValues.level.template", {
                      code: template?.code ?? "",
                      version: String(template?.current_version?.version_no ?? ""),
                    })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-2 pt-3"
      data-testid="SF-15-pane-policy-values"
    >
      <h3 className="text-body-sm font-medium text-fg-1">{title}</h3>
      {body}
      <p className="text-caption text-fg-3">{t("settings.product.policyValues.note")}</p>
    </section>
  );
}

type Answer = "yes" | "no" | null;
interface Indicator {
  readonly id: "responsible" | "inventory" | "pricing";
  readonly answer: Answer;
  readonly note: string;
}
const INDICATORS: readonly Indicator["id"][] = ["responsible", "inventory", "pricing"];

/** SCREENS §10.4 "Propose principal or agent change" drawer. */
// docs/dev-guide.md DG-FE-06: the two fields of the proposal that show a message of the API and the
// members each sends; the indicators and their notes are parts of the rationale.
const PROPOSAL_MEMBERS = { rationale: ["rationale"], conclusion: ["principal_agent"] } as const;

function ProposeDrawer({
  product,
  onClose,
}: {
  readonly product: Product;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const baseId = useId();
  const [conclusion, setConclusion] = useState<PrincipalAgent | null>(null);
  const [indicators, setIndicators] = useState<readonly Indicator[]>(
    INDICATORS.map((id) => ({ id, answer: null, note: "" })),
  );
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const propose = useCommand<PrincipalAgentChangeResult>({
    method: "POST",
    path: proposePrincipalAgentPath(product.id),
    invalidates: [EVERY_PRODUCT],
  });
  const placed = useMemo(() => placeProblem(propose.problem, PROPOSAL_MEMBERS), [propose.problem]);
  const rationaleError =
    placed.fields.rationale ??
    (attempted && rationale.trim().length < 10
      ? t("settings.product.propose.rationaleRequired")
      : null);
  // The API's message on the conclusion is about a conclusion that was sent, so it stands while one
  // is chosen; the line was drawn only while none was.
  const conclusionError =
    placed.fields.conclusion ??
    (attempted && conclusion === null ? t("settings.product.propose.conclusion") : null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (conclusion === null || rationale.trim().length < 10) {
      return;
    }
    const body: PrincipalAgentChange = {
      principal_agent: conclusion,
      rationale: composeRationale(
        indicators.map((indicator) => ({
          label: t(`settings.product.propose.indicator.${indicator.id}`),
          answer: indicator.answer,
          note: indicator.note,
        })),
        rationale,
      ),
    };
    const outcome = await propose.submit(body);
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("settings.product.propose.submitted") });
      onClose();
    }
  };
  const update = (id: Indicator["id"], patch: Partial<Indicator>) =>
    setIndicators((previous) =>
      previous.map((indicator) => (indicator.id === id ? { ...indicator, ...patch } : indicator)),
    );
  return (
    <Drawer
      open
      title={t("settings.product.propose.title")}
      subtitle={`${product.code} · ${product.name}`}
      dirty={conclusion !== null || rationale !== ""}
      submitting={propose.pending}
      primaryAction={{ label: t("settings.product.propose.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-15-drawer-principal-agent"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <RefusalBanner problem={propose.problem} placed={placed} />
        <fieldset className="flex flex-col gap-2">
          <legend className="text-body-sm font-medium text-fg-1">
            {t("settings.product.propose.conclusion")}
          </legend>
          <div className="flex flex-wrap items-center gap-6">
            {PRINCIPAL_AGENT_VALUES.map((value) => (
              <label key={value} className="flex items-center gap-2 text-body-sm text-fg-1">
                <input
                  type="radio"
                  name={`conclusion-${baseId}`}
                  value={value}
                  checked={conclusion === value}
                  onChange={() => setConclusion(value)}
                  className="size-4"
                />
                {principalAgentLabel(value)}
              </label>
            ))}
          </div>
          {conclusionError === null ? null : (
            <p className="text-caption text-negative-fg">{conclusionError}</p>
          )}
        </fieldset>
        <fieldset className="flex flex-col gap-3">
          <legend className="text-body-sm font-medium text-fg-1">
            {t("settings.product.propose.indicators")}
          </legend>
          {indicators.map((indicator) => (
            <fieldset key={indicator.id} className="flex flex-col gap-2">
              <legend className="text-body-sm text-fg-1">
                {t(`settings.product.propose.indicator.${indicator.id}`)}
              </legend>
              <div className="flex flex-wrap items-end gap-4">
                {(["yes", "no"] as const).map((answer) => (
                  <label key={answer} className="flex items-center gap-2 text-body-sm text-fg-1">
                    <input
                      type="radio"
                      name={`${indicator.id}-${baseId}`}
                      value={answer}
                      checked={indicator.answer === answer}
                      onChange={() => update(indicator.id, { answer })}
                      className="size-4"
                    />
                    {t(
                      answer === "yes"
                        ? "settings.product.propose.indicatorYes"
                        : "settings.product.propose.indicatorNo",
                    )}
                  </label>
                ))}
                <Field
                  name={`${indicator.id}-note`}
                  label={t("settings.product.propose.indicatorNote")}
                  optional
                  width="text"
                >
                  {(control) => (
                    <input
                      {...control}
                      type="text"
                      value={indicator.note}
                      onChange={(event) => update(indicator.id, { note: event.target.value })}
                      className={controlClass(false)}
                    />
                  )}
                </Field>
              </div>
            </fieldset>
          ))}
        </fieldset>
        <Field
          name="rationale"
          label={t("settings.product.propose.rationale")}
          required
          help={t("settings.product.propose.rationaleHelp")}
          error={rationaleError}
          width="full"
        >
          {(control) => (
            <textarea
              {...control}
              rows={4}
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              className={`${controlClass(rationaleError !== null)} h-auto py-2`}
            />
          )}
        </Field>
        <p className="text-body-sm text-fg-2">{t("settings.product.propose.info")}</p>
      </form>
    </Drawer>
  );
}

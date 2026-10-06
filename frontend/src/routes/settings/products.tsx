// SF-15:products Products (SCREENS §10; §0.4 RT-82, §0.5 SCR-URL `drawer`, `row`, `q`, `f.*`, §0.7
// SCR-ST-03, SCR-ST-04, SCR-ST-05, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-13, DS-CMP-21,
// DS-FMT-22; 04 API-R-23 `GET, POST /products`, `PATCH /products/{id}` (`If-Match`), API-R-24 `GET
// /pob-templates`; T-REF-20; REQ-REF-012, REQ-REF-013; BUILD_SPEC RFD-21). The Settings frame with the
// Reference data route tabs, the quick search "Search products" with the Product family and Active
// filters, and the DataGrid "Products" (§10.3 columns; the code links SF-15:product, the default
// template links SF-13:template-version once built). "New product" and "Edit product"
// (`masterdata.maintain`) share the drawer of §10.4: the warning "This product cannot be used on
// contracts until <attributes> are set." names the required disaggregation attributes still missing.
// "Import products" (`import.upload`) links SF-10:new once built. Revenue category is free text (the
// published account mapping's categories are not read here).
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
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { WarningCircle } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import type { ApiProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import {
  DISTINCTNESS_VALUES,
  type Distinctness,
  EVERY_PRODUCT,
  fetchMandatoryAttributes,
  fetchProductsPage,
  IMPORT_PRODUCTS_ROUTE,
  IMPORT_UPLOAD_PERMISSION,
  mandatoryAttributesKey,
  MASTERDATA_MAINTAIN_PERMISSION,
  missingAttributes,
  type PrincipalAgent,
  type Product,
  PRODUCT_READ_PERMISSION,
  type ProductCreate,
  productPath,
  type ProductQuery,
  productRoute,
  PRODUCTS_PATH,
  productsGridKey,
  type ProductUpdate,
  publishedTemplates,
  TEMPLATE_VERSION_ROUTE,
  templateVersionRoute,
  useProduct,
  useTemplates,
} from "../../lib/api/queries/products";
import type { PobTemplate } from "../../lib/api/queries/rule-sets";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { useFieldRefusals } from "../../lib/api/refusals";
import { formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader, useBuiltPaths } from "./index";

const DRAWER_PRODUCT = "product";
const IMPORT_NEW_PATH = "/data/imports/new";

function mono(text: string | null) {
  return text === null ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="font-mono text-mono text-fg-2">{text}</span>
  );
}

export function yesNo(value: boolean): string {
  return t(value ? "settings.products.yes" : "settings.products.no");
}

export function principalAgentLabel(value: PrincipalAgent): string {
  return t(`settings.products.principalAgent.${value}`);
}

export function distinctnessLabel(value: Distinctness): string {
  return t(`settings.products.distinctness.${value}`);
}

/** SCREENS §10.3 filters: Product family and Active. */
export function productFilterFields(): readonly FilterField[] {
  return [
    {
      name: "family",
      label: t("settings.products.filter.family"),
      kind: "text",
      operators: ["is"],
    },
    {
      name: "active",
      label: t("settings.products.filter.active"),
      kind: "boolean",
      operators: ["is"],
    },
  ];
}

export function productQuery(search: string, fields: readonly FilterField[]): ProductQuery {
  const parsed = parseFilters(search, fields);
  const value = (name: string) => parsed.filters.find((filter) => filter.field === name)?.values[0];
  const active = value("active");
  return {
    q: parsed.query,
    family: value("family") ?? null,
    isActive: active === undefined ? null : active === "true" || active === "yes",
  };
}

/** SCREENS §10.3 products grid columns. */
export function productColumns(
  templates: ReadonlyMap<string, PobTemplate>,
  templateRouteBuilt: boolean,
): readonly GridColumn<Product>[] {
  const templateOf = (product: Product) =>
    product.default_pob_template_id === null
      ? null
      : (templates.get(product.default_pob_template_id) ?? null);
  return [
    {
      id: "code",
      header: t("settings.products.column.product"),
      kind: "identifier",
      value: (product) => product.code,
      href: (product) => productRoute(product.id),
      sortKey: "code",
      width: 160,
    },
    {
      id: "name",
      header: t("settings.products.column.name"),
      kind: "text",
      value: (product) => product.name,
      sortKey: "name",
      width: 280,
    },
    {
      id: "sku_number",
      header: t("settings.products.column.sku"),
      kind: "text",
      value: (product) => product.sku_number,
      render: (product) => mono(product.sku_number),
      width: 128,
    },
    {
      id: "product_family",
      header: t("settings.products.column.family"),
      kind: "text",
      value: (product) => product.product_family,
      width: 160,
    },
    {
      id: "revenue_category",
      header: t("settings.products.column.revenueCategory"),
      kind: "text",
      value: (product) => product.revenue_category,
      render: (product) => mono(product.revenue_category),
      width: 160,
    },
    {
      id: "default_template",
      header: t("settings.products.column.template"),
      kind: "text",
      value: (product) => templateOf(product)?.code ?? null,
      render: (product) => {
        const template = templateOf(product);
        if (template === null) {
          return mono(null);
        }
        const current = template.current_version;
        return templateRouteBuilt && current !== null ? (
          <Link
            to={templateVersionRoute(template.id, current.id)}
            className="font-mono text-mono text-accent-fg hover:underline"
          >
            {template.code}
          </Link>
        ) : (
          mono(template.code)
        );
      },
      width: 160,
    },
    {
      id: "principal_agent",
      header: t("settings.products.column.principalAgent"),
      kind: "text",
      value: (product) => principalAgentLabel(product.principal_agent),
      width: 144,
    },
    {
      id: "distinctness_default",
      header: t("settings.products.column.distinctness"),
      kind: "text",
      value: (product) => distinctnessLabel(product.distinctness_default),
      width: 144,
    },
    {
      id: "unit_of_measure",
      header: t("settings.products.column.unit"),
      kind: "text",
      value: (product) => product.unit_of_measure,
      render: (product) => mono(product.unit_of_measure),
      width: 88,
    },
    {
      id: "is_bundle",
      header: t("settings.products.column.bundle"),
      kind: "text",
      value: (product) => yesNo(product.is_bundle),
      width: 88,
    },
    {
      id: "is_active",
      header: t("settings.products.column.active"),
      kind: "text",
      value: (product) => yesNo(product.is_active),
      width: 88,
    },
  ];
}

export function ProductsScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.products.title");

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
  } else {
    return <ProductsPage access={access} />;
  }
  return (
    <div
      data-testid="SF-15-products-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="reference" />
      {body}
    </div>
  );
}

function ProductsPage({ access }: { readonly access: Access }) {
  const { search } = useLocation();
  const [params, setParams] = useSearchParams();
  const built = useBuiltPaths();
  const [total, setTotal] = useState<number | undefined>(undefined);
  const title = t("settings.products.title");
  const maintain = access.holdsAnywhere(MASTERDATA_MAINTAIN_PERMISSION);
  const importable = access.holdsAnywhere(IMPORT_UPLOAD_PERMISSION) && built.has(IMPORT_NEW_PATH);
  const templates = useTemplates();
  const templateMap = useMemo(
    () => new Map((templates.data ?? []).map((template) => [template.id, template])),
    [templates.data],
  );
  const fields = useMemo(() => productFilterFields(), []);
  const query = productQuery(search, fields);
  const columns = useMemo(
    () => productColumns(templateMap, built.has(TEMPLATE_VERSION_ROUTE)),
    [templateMap, built],
  );
  const source: GridSource<Product> = {
    queryKey: productsGridKey(query),
    fetchPage: (cursor, sort) => fetchProductsPage(query, cursor, sort),
  };
  const drawer = params.get("drawer");
  const row = params.get("row");
  const openDrawer = (id: string | null) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("drawer", DRAWER_PRODUCT);
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
  const newProduct = maintain
    ? { label: t("settings.products.new"), onAction: () => openDrawer(null) }
    : undefined;
  const importLink = importable
    ? { label: t("settings.products.import"), href: IMPORT_PRODUCTS_ROUTE }
    : undefined;
  const countLabel = (value: number) =>
    t("settings.products.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });

  return (
    <div
      data-testid="SF-15-products-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="reference">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">{countLabel(total)}</p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<Product>
          name="products"
          title={t("settings.products.grid")}
          errorTitle={t("settings.products.loadError")}
          countLabel={(value, formatted) =>
            t("settings.products.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(product) => product.id}
          rowLabel={(product) => product.code}
          testIdPrefix="SF-15"
          rowTestKey={(product) => product.code}
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
              {newProduct === undefined ? null : (
                <Button variant="primary" onClick={newProduct.onAction}>
                  {newProduct.label}
                </Button>
              )}
            </>
          }
          filterBar={
            <FilterBar
              fields={fields}
              searchLabel={t("settings.products.search")}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-15-filter-bar-products"
            />
          }
          emptyState={
            <div data-testid="SF-15-empty-products">
              <EmptyState
                title={t("settings.products.empty.title")}
                description={t("settings.products.empty.description")}
                action={newProduct}
                link={importLink}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("settings.products.noResults.title")}
              description={t("settings.products.noResults.description")}
            />
          }
        />
      </div>
      {drawer === DRAWER_PRODUCT && row === null ? (
        <ProductDrawer product={null} readOnly={!maintain} onClose={closeDrawer} />
      ) : null}
      {drawer === DRAWER_PRODUCT && row !== null ? (
        <ProductDrawerLoader productId={row} readOnly={!maintain} onClose={closeDrawer} />
      ) : null}
    </div>
  );
}

function ProductDrawerLoader({
  productId,
  readOnly,
  onClose,
}: {
  readonly productId: string;
  readonly readOnly: boolean;
  readonly onClose: () => void;
}) {
  const product = useProduct(productId);
  if (product.data === undefined) {
    return null;
  }
  return <ProductDrawer product={product.data} readOnly={readOnly} onClose={onClose} />;
}

interface AttributeRow {
  readonly key: string;
  readonly value: string;
}

function attributeRows(product: Product | null): readonly AttributeRow[] {
  if (product === null) {
    return [];
  }
  return Object.entries(product.disaggregation).map(([key, value]) => ({
    key,
    value: typeof value === "string" ? value : JSON.stringify(value),
  }));
}

/** The controls of the drawer that show a message, by the API-S-Product member each one enters. */
type ProductControl =
  | "code"
  | "sku_number"
  | "name"
  | "product_family"
  | "revenue_category"
  | "default_pob_template_id"
  | "unit_of_measure"
  | "is_bundle"
  | "disaggregation";

const PRODUCT_MEMBERS: Readonly<Record<ProductControl, readonly string[]>> = {
  code: ["code"],
  sku_number: ["sku_number"],
  name: ["name"],
  product_family: ["product_family"],
  revenue_category: ["revenue_category"],
  default_pob_template_id: ["default_pob_template_id"],
  unit_of_measure: ["unit_of_measure"],
  is_bundle: ["is_bundle"],
  disaggregation: ["disaggregation"],
};

const ATTRIBUTES_MEMBER = "disaggregation";

interface AttributeRefusals {
  /** The first message of each attribute key that is a row of the drawer. */
  readonly byKey: ReadonlyMap<string, string>;
  /** The first message on the attributes that names no row; it stands under their heading. */
  readonly other: string | null;
}

/**
 * The messages a refusal holds for the attribute rows (SCREENS §10.4 rev 1.35): the API points at an
 * attribute as `disaggregation.<key>`.
 */
function attributeRefusals(
  problem: ApiProblem | null,
  rows: readonly AttributeRow[],
): AttributeRefusals {
  const keys = new Set(rows.map((row) => row.key.trim()));
  const byKey = new Map<string, string>();
  let other: string | null = null;
  for (const error of problem?.errors ?? []) {
    if (
      error.field !== ATTRIBUTES_MEMBER &&
      error.field?.startsWith(`${ATTRIBUTES_MEMBER}.`) !== true
    ) {
      continue;
    }
    const key = error.field.slice(ATTRIBUTES_MEMBER.length + 1);
    if (key !== "" && keys.has(key)) {
      if (!byKey.has(key)) {
        byKey.set(key, error.message);
      }
    } else {
      other ??= error.message;
    }
  }
  return { byKey, other };
}

/** SCREENS §10.4 "New product" / "Edit product" drawer. */
export function ProductDrawer({
  product,
  readOnly,
  onClose,
}: {
  /** null creates. */
  readonly product: Product | null;
  readonly readOnly: boolean;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const bundleId = useId();
  const bundleErrorId = useId();
  const activeId = useId();
  const distinctId = useId();
  const templates = useTemplates();
  const mandatory = useQuery({
    queryKey: mandatoryAttributesKey(),
    queryFn: fetchMandatoryAttributes,
  });
  const [code, setCode] = useState(product?.code ?? "");
  const [sku, setSku] = useState(product?.sku_number ?? "");
  const [name, setName] = useState(product?.name ?? "");
  const [family, setFamily] = useState(product?.product_family ?? "");
  const [category, setCategory] = useState(product?.revenue_category ?? "");
  const [templateId, setTemplateId] = useState<string | null>(
    product?.default_pob_template_id ?? null,
  );
  const [distinctness, setDistinctness] = useState<Distinctness>(
    product?.distinctness_default ?? "distinct",
  );
  const [unit, setUnit] = useState(product?.unit_of_measure ?? "EA");
  const [bundle, setBundle] = useState(product?.is_bundle ?? false);
  const [attributes, setAttributes] = useState<readonly AttributeRow[]>(() =>
    attributeRows(product),
  );
  const [active, setActive] = useState(product?.is_active ?? true);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const invalidates = [EVERY_PRODUCT];
  const create = useCommand<Product>({ method: "POST", path: PRODUCTS_PATH, invalidates });
  const edit = useCommand<Product>({
    method: "PATCH",
    path: product === null ? PRODUCTS_PATH : productPath(product.id),
    invalidates,
  });
  const command = product === null ? create : edit;
  // A refusal stands at the control whose member it names and leaves when that value is edited;
  // what names no control is the banner's (SCREENS §10.4 rev 1.35).
  const refusals = useFieldRefusals(command.problem, PRODUCT_MEMBERS);
  // The screen's own check first, then what the server said of the value it was sent.
  const errorOf = (control: ProductControl): string | null =>
    local[control] ?? refusals.fields[control];
  const bundleError = errorOf("is_bundle");
  const optional = (value: string) => (value.trim() === "" ? null : value.trim());
  const disaggregation = Object.fromEntries(
    attributes
      .filter((row) => row.key.trim() !== "")
      .map((row) => [row.key.trim(), row.value.trim()]),
  );
  const missing = missingAttributes(
    { usability: { usable: true, missing: [] }, disaggregation },
    mandatory.data ?? [],
  );
  const dirty =
    product === null
      ? code !== "" || name !== ""
      : code.trim() !== product.code ||
        optional(sku) !== product.sku_number ||
        name.trim() !== product.name ||
        optional(family) !== product.product_family ||
        optional(category) !== product.revenue_category ||
        templateId !== product.default_pob_template_id ||
        distinctness !== product.distinctness_default ||
        unit.trim() !== product.unit_of_measure ||
        bundle !== product.is_bundle ||
        JSON.stringify(disaggregation) !== JSON.stringify(product.disaggregation) ||
        active !== product.is_active;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (readOnly || command.pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (code.trim() === "") {
      found.code = t("settings.products.drawer.codeRequired");
    }
    if (name.trim() === "") {
      found.name = t("settings.products.drawer.nameRequired");
    }
    if (unit.trim() === "") {
      found.unit_of_measure = t("settings.products.drawer.unitRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    if (product === null) {
      const body: ProductCreate = {
        code: code.trim(),
        sku_number: optional(sku),
        name: name.trim(),
        product_family: optional(family),
        revenue_category: optional(category),
        default_pob_template_id: templateId,
        distinctness_default: distinctness,
        unit_of_measure: unit.trim(),
        is_bundle: bundle,
        is_franchisor_preopening_service: false,
        principal_agent: "NOT_ASSESSED",
        disaggregation,
        is_active: active,
      };
      const outcome = await create.submit(body);
      if (outcome.kind === "succeeded" && outcome.data !== null) {
        toast.show({
          tone: "positive",
          message: t("settings.products.drawer.saved", { code: outcome.data.code }),
        });
        onClose();
      }
      return;
    }
    const patch: ProductUpdate = {
      ...(code.trim() !== product.code ? { code: code.trim() } : {}),
      ...(optional(sku) !== product.sku_number ? { sku_number: optional(sku) } : {}),
      ...(name.trim() !== product.name ? { name: name.trim() } : {}),
      ...(optional(family) !== product.product_family ? { product_family: optional(family) } : {}),
      ...(optional(category) !== product.revenue_category
        ? { revenue_category: optional(category) }
        : {}),
      ...(templateId !== product.default_pob_template_id
        ? { default_pob_template_id: templateId }
        : {}),
      ...(distinctness !== product.distinctness_default
        ? { distinctness_default: distinctness }
        : {}),
      ...(unit.trim() !== product.unit_of_measure ? { unit_of_measure: unit.trim() } : {}),
      ...(bundle !== product.is_bundle ? { is_bundle: bundle } : {}),
      ...(JSON.stringify(disaggregation) !== JSON.stringify(product.disaggregation)
        ? { disaggregation }
        : {}),
      ...(active !== product.is_active ? { is_active: active } : {}),
    };
    const outcome = await edit.submit(patch, { ifMatch: rowIfMatch(product.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("settings.products.drawer.saved", { code: code.trim() }),
      });
      onClose();
    }
  };

  // The refusal first — SCR-ST-09 after a 412, else the problem as the controls leave it — then the
  // standing warning of a missing required attribute (REQ-REF-012).
  const banners = (
    <>
      <RefusalBanner problem={refusals.banner} placed={refusals.placed} conflict={command.banner} />
      {missing.length > 0 ? (
        <Banner
          tone="warning"
          announce="static"
          title={t("settings.products.drawer.missingAttributes", {
            attributes: missing.join(", "),
          })}
        />
      ) : null}
    </>
  );
  const templateOptions = [
    { value: "", label: t("settings.products.drawer.templateNone") },
    ...publishedTemplates(templates.data ?? []).map((template) => ({
      value: template.id,
      label: `${template.code} · ${template.name}`,
    })),
  ];
  const text = (
    field: ProductControl,
    label: string,
    value: string,
    onChange: (next: string) => void,
    options: {
      readonly required?: boolean;
      readonly mono?: boolean;
      readonly help?: string | undefined;
      /** The field alone is read-only, in a drawer that can be saved. */
      readonly fixed?: boolean;
    } = {},
  ) => (
    <Field
      name={field}
      label={label}
      required={options.required === true}
      optional={options.required !== true}
      error={errorOf(field)}
      help={options.help}
      width="text"
    >
      {(control) => (
        <input
          {...control}
          type="text"
          readOnly={readOnly || options.fixed === true}
          value={value}
          onChange={(event) => {
            refusals.edited(field);
            onChange(event.target.value);
          }}
          className={`${controlClass(errorOf(field) !== null)}${options.mono === true ? " font-mono" : ""}`}
        />
      )}
    </Field>
  );

  return (
    <Drawer
      open
      title={
        product === null
          ? t("settings.products.drawer.newTitle")
          : t("settings.products.drawer.editTitle")
      }
      subtitle={product?.name}
      dirty={dirty && !readOnly}
      submitting={command.pending}
      banner={banners}
      primaryAction={
        readOnly ? undefined : { label: t("settings.products.drawer.save"), form: formId }
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-15-drawer-product"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        {/* SCREENS §10.4 (rev 1.44): API-S-Product `code_frozen` is the predicate of 04 DB-05 — a
            contract line, an SSP entry or an account mapping rule references the product — so the
            field is read-only then; the help says why in both states. */}
        {text("code", t("settings.products.drawer.code"), code, setCode, {
          required: true,
          mono: true,
          help: product === null ? undefined : t("settings.products.drawer.codeLocked"),
          fixed: product?.code_frozen === true,
        })}
        {text("sku_number", t("settings.products.drawer.sku"), sku, setSku, { mono: true })}
        {text("name", t("settings.products.drawer.name"), name, setName, { required: true })}
        {text("product_family", t("settings.products.drawer.family"), family, setFamily)}
        {text(
          "revenue_category",
          t("settings.products.drawer.revenueCategory"),
          category,
          setCategory,
          {
            mono: true,
            help: t("settings.products.drawer.revenueCategoryHelp"),
          },
        )}
        <Field
          name="default_pob_template_id"
          label={t("settings.products.drawer.template")}
          optional
          error={errorOf("default_pob_template_id")}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={templateOptions}
              value={templateId ?? ""}
              invalid={errorOf("default_pob_template_id") !== null}
              onChange={(next) => {
                if (!readOnly) {
                  refusals.edited("default_pob_template_id");
                  setTemplateId(next === "" ? null : next);
                }
              }}
            />
          )}
        </Field>
        <fieldset className="flex flex-col gap-2" aria-describedby={`${distinctId}-help`}>
          <legend className="text-body-sm font-medium text-fg-1">
            {t("settings.products.drawer.distinctness")}
          </legend>
          <div className="flex flex-wrap items-center gap-6">
            {DISTINCTNESS_VALUES.map((value) => (
              <label key={value} className="flex items-center gap-2 text-body-sm text-fg-1">
                <input
                  type="radio"
                  name={`distinctness-${distinctId}`}
                  value={value}
                  checked={distinctness === value}
                  disabled={readOnly}
                  onChange={() => setDistinctness(value)}
                  className="size-4"
                />
                {distinctnessLabel(value)}
              </label>
            ))}
          </div>
          <p id={`${distinctId}-help`} className="text-caption text-fg-3">
            {t("settings.products.drawer.distinctnessHelp")}
          </p>
        </fieldset>
        {text("unit_of_measure", t("settings.products.drawer.unit"), unit, setUnit, {
          required: true,
          mono: true,
        })}
        <div className="flex flex-col gap-1">
          <label htmlFor={bundleId} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={bundleId}
              type="checkbox"
              checked={bundle}
              disabled={readOnly}
              aria-invalid={bundleError === null ? undefined : true}
              aria-describedby={bundleError === null ? undefined : bundleErrorId}
              onChange={(event) => {
                refusals.edited("is_bundle");
                setBundle(event.target.checked);
              }}
              className="size-4"
            />
            {t("settings.products.drawer.bundle")}
          </label>
          {bundleError === null ? null : (
            <p id={bundleErrorId} className="flex items-start gap-1 text-body-sm text-negative-fg">
              <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
              {bundleError}
            </p>
          )}
        </div>
        <AttributeRows
          rows={attributes}
          mandatory={mandatory.data ?? []}
          readOnly={readOnly}
          refused={errorOf("disaggregation") === null ? null : command.problem}
          onChange={(next) => {
            refusals.edited("disaggregation");
            setAttributes(next);
          }}
        />
        <label htmlFor={activeId} className="flex items-center gap-2 text-body-sm text-fg-1">
          <input
            id={activeId}
            type="checkbox"
            checked={active}
            disabled={readOnly}
            onChange={(event) => setActive(event.target.checked)}
            className="size-4"
          />
          {t("settings.products.drawer.active")}
        </label>
      </form>
    </Drawer>
  );
}

/** SCREENS §10.4 "Disaggregation attributes": key and value rows; required keys are marked. */
function AttributeRows({
  rows,
  mandatory,
  readOnly,
  refused,
  onChange,
}: {
  readonly rows: readonly AttributeRow[];
  readonly mandatory: readonly string[];
  readonly readOnly: boolean;
  /** The refusal whose messages on the attributes still stand: none once a row has been edited. */
  readonly refused: ApiProblem | null;
  readonly onChange: (rows: readonly AttributeRow[]) => void;
}) {
  const baseId = useId();
  const errorId = useId();
  const refusals = attributeRefusals(refused, rows);
  const update = (index: number, patch: Partial<AttributeRow>) =>
    onChange(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)));
  return (
    <fieldset
      className="flex flex-col gap-2"
      data-testid="SF-15-product-attributes"
      aria-describedby={refusals.other === null ? undefined : errorId}
    >
      <legend className="text-body-sm font-medium text-fg-1">
        {t("settings.products.drawer.attributes")}
      </legend>
      {refusals.other === null ? null : (
        <p id={errorId} className="flex items-start gap-1 text-body-sm text-negative-fg">
          <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
          {refusals.other}
        </p>
      )}
      {mandatory.length > 0 ? (
        <p className="text-caption text-fg-3">
          {t("settings.products.drawer.attributesRequired", { attributes: mandatory.join(", ") })}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="text-body-sm text-fg-3">{t("settings.products.drawer.attributesEmpty")}</p>
      ) : null}
      {rows.map((row, index) => (
        <div key={`${baseId}-${String(index)}`} className="flex flex-wrap items-end gap-3">
          <Field
            name={`attribute-key-${baseId}-${String(index)}`}
            label={t("settings.products.drawer.attributeKey")}
            width="text"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                readOnly={readOnly}
                value={row.key}
                onChange={(event) => update(index, { key: event.target.value })}
                className={`${controlClass(false)} font-mono`}
              />
            )}
          </Field>
          <Field
            name={`attribute-value-${baseId}-${String(index)}`}
            label={t("settings.products.drawer.attributeValue")}
            error={refusals.byKey.get(row.key.trim()) ?? null}
            width="text"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                readOnly={readOnly}
                value={row.value}
                onChange={(event) => update(index, { value: event.target.value })}
                className={controlClass(refusals.byKey.has(row.key.trim()))}
              />
            )}
          </Field>
          {readOnly ? null : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onChange(rows.filter((_, at) => at !== index))}
            >
              {t("settings.products.drawer.attributeRemove")}
            </Button>
          )}
        </div>
      ))}
      {readOnly ? null : (
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onChange([...rows, { key: "", value: "" }])}
          >
            {t("settings.products.drawer.attributeAdd")}
          </Button>
        </div>
      )}
    </fieldset>
  );
}

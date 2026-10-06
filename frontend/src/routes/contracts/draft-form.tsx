// SF-03:new and SF-03:edit Draft contract form (SCREENS §4.10; §0.4 RT-09, RT-19; §0.6 SCR-PERM-01; §0.7
// SCR-ST-05, SCR-ST-07, SCR-ST-09; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11, DS-CMP-21, DS-SP-05; 04 API-R-28 `POST
// /contracts`, `POST /contracts/{id}/replace-draft`, `POST /contracts/{id}/submit-activation`, §16.1
// API-S-ContractCreate; docs/dev-guide.md DG-FE-05, DG-FE-06; BUILD_SPEC CTR-24).
//
// The sections Contract, Termination and Classification at the form width, the lines grid full-bleed below
// them and a sticky footer. "Save draft" sends the API-S-ContractCreate body of `lib/forms/contract`:
// `POST /contracts`, or `replace-draft` with `If-Match` for a draft that exists, whose external id,
// contracting entity and currency stay as booked (04 §16.1). "Save and submit for activation" saves,
// then sends `submit-activation` with the saved head: the API refuses `submit_for_activation` in the
// booking (L3-1-Q-43); a refused activation opens SF-03 with a warning toast that says what comes
// first, and with step 1 open when the Step 1 review is among the failed items (rulings R-89, R-93). A
// `validation-failed` answer lands on the fields and the grid cells; a 412 keeps the typed input and
// offers "Reload". Leaving a changed form asks "Discard changes?".
//
// SF-03:edit opens behind a fail-closed guard (ruling R-93 (a)): no read answers a draft as it stands
// (item CTR-DRAFT-READ-1), so the form is seeded from the latest booking only while every event after it
// is a hold applied or released, a Step 1 assessment or the void of one; otherwise the screen says why
// the draft is not edited here. A Step 1 assessment does not close the form (rev 1.72; ruling R-102 (c)):
// the API takes the edit and voids every assessment that stands, and the form says so above its sections
// where one does. The contract and its stream are read once per opening and again only on "Reload", and
// the save sends the head the guard read, never a later read of the contract.
//
// The lines grid is the form's own state, saved in one body, so its cells hold the DS-CMP-21 controls
// themselves (the shared DataGrid reads server pages and saves cell by cell). Customers and products are
// read with `contract.read`; the entities and the enabled currencies need `config.read`.
import { useQuery } from "@tanstack/react-query";
import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useBlocker, useLocation, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { ErrorSummary, type FormErrorEntry } from "../../components/form/ErrorSummary";
import {
  controlClass,
  Field,
  type FieldControlProps,
  fieldId,
  fieldLabelId,
} from "../../components/form/Field";
import { type ListOption, Listbox, optionId } from "../../components/form/Listbox";
import { Select } from "../../components/form/Select";
import {
  type LineCellKind,
  type LineColumn,
  LineEditor,
} from "../../components/line-editor/LineEditor";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, statusMessageKey } from "../../components/ui/StatusChip";
import { StickyFooter } from "../../components/ui/StickyFooter";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import {
  APPROVAL_REQUEST_HEADER,
  type Contract,
  CONTRACT_CREATE_PERMISSION,
  CONTRACT_RECORD_KEYS,
  contractIfMatch,
  CONTRACTS_PATH,
  draftForEditKey,
  fetchDraftForEdit,
  fetchProductChoices,
  productChoicesKey,
  replaceDraftPath,
  sendCommand,
  submitActivationPath,
} from "../../lib/api/queries/contracts";
import {
  enabledCurrencyCodes,
  fetchTenantCurrencies,
  tenantCurrenciesKey,
} from "../../lib/api/queries/currencies";
import { allCustomersKey, fetchAllCustomers } from "../../lib/api/queries/customers";
import { useMe } from "../../lib/api/queries/me";
import {
  entitiesKey,
  fetchActiveEntities,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import type { components } from "../../lib/api/schema";
import {
  buildDraft,
  type DraftCustomer,
  type DraftForm,
  draftFromBooking,
  type DraftLine,
  emptyDraft,
  emptyLine,
  IN_SCOPE,
  LINE_COLUMNS,
  type DraftColumn,
  lineField,
  linePatch,
  lineValue,
  LINES_FIELD,
  MAX_LINES,
  nextObligationKey,
  placeProblem,
  SCOPE_FLAGS,
  TERMINATION_PARTIES,
  type TerminationParty,
  type YesNo,
} from "../../lib/forms/contract";
import { formatNumber, registerCurrencies } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { requestNumber, SelectField, TextField, useRefreshRecord } from "./drawers/common";
import { contextSearch, fixActionOf } from "./workbench";

type SubmitActivationBody = components["schemas"]["SubmitActivationIn"];

const CREATE_VALUE = "\u0000create";
/** The fix actions of a failed checklist item that open step 1 of the tracker (SCREENS §4.9.8). */
const STEP1_FIXES: ReadonlySet<ReturnType<typeof fixActionOf>> = new Set(["step1", "step1Review"]);

interface Choice {
  readonly value: string;
  readonly label: string;
}

/** What the form reads before it renders: the choices of its selects and comboboxes. */
interface DraftChoices {
  readonly customers: readonly Choice[];
  readonly products: readonly Choice[];
  readonly entities: readonly (Choice & { readonly functionalCurrency: string | null })[];
  readonly currencies: readonly Choice[];
}

function PageFrame({
  testId,
  crumbs,
  title,
  identifier,
  children,
}: {
  readonly testId: string;
  readonly crumbs: readonly { readonly label: string; readonly to: string }[];
  readonly title: string;
  readonly identifier?: string | undefined;
  readonly children: ReactNode;
}) {
  return (
    <div data-testid={testId} className="flex min-h-full flex-col gap-4">
      <header className="flex flex-col gap-3">
        <nav aria-label={t("common.record.breadcrumb")}>
          <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
            {crumbs.map((crumb) => (
              <li key={`${crumb.label}:${crumb.to}`} className="flex items-center gap-1.5">
                <Link to={crumb.to} className="hover:text-fg-1 hover:underline">
                  {crumb.label}
                </Link>
                <span aria-hidden="true">/</span>
              </li>
            ))}
            <li aria-current="page" className="min-w-0 truncate">
              {title}
            </li>
          </ol>
        </nav>
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 id="draft-form-title" tabIndex={-1} className="text-title-lg text-fg-1">
            {title}
          </h1>
          {identifier === undefined ? null : (
            <span className="font-mono text-mono text-fg-2">{identifier}</span>
          )}
        </div>
      </header>
      {children}
    </div>
  );
}

function AccessLimited({ permission }: { readonly permission: string }) {
  return (
    <EmptyState
      title={t("settings.access.title", { area: t("contracts.draft.access.area") })}
      description={t("settings.access.description", { permission })}
      headingLevel={2}
    />
  );
}

function LoadError({
  title,
  problem,
  onRetry,
}: {
  readonly title: string;
  readonly problem: unknown;
  readonly onRetry: () => void;
}) {
  return (
    <Banner
      tone="negative"
      title={title}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("common.grid.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{problem.title}</p> : null}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("contracts.drawer.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

/** The selects and comboboxes of the form; `enabled` is false until the user may open it. */
function useDraftChoices(enabled: boolean) {
  const customers = useQuery({
    queryKey: allCustomersKey(),
    queryFn: fetchAllCustomers,
    enabled,
  });
  const products = useQuery({
    queryKey: productChoicesKey(),
    queryFn: fetchProductChoices,
    enabled,
  });
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities, enabled });
  const currencies = useQuery({
    queryKey: tenantCurrenciesKey(),
    queryFn: async () => {
      const rows = await fetchTenantCurrencies();
      // DS-FMT-03: the money cells parse and echo with the minor unit of the chosen currency.
      registerCurrencies(
        rows.map((row) => ({ code: row.currency_code, minor_unit: row.minor_unit })),
      );
      return rows;
    },
    enabled,
  });
  const reads = [customers, products, entities, currencies];
  const failed = reads.find((read) => read.isError);
  const choices = useMemo((): DraftChoices | null => {
    if (
      customers.data === undefined ||
      products.data === undefined ||
      entities.data === undefined ||
      currencies.data === undefined
    ) {
      return null;
    }
    return {
      customers: customers.data.map((item) => ({
        value: item.id,
        label: `${item.name} · ${item.code}`,
      })),
      products: products.data.map((item) => ({
        value: item.code,
        label: `${item.code} · ${item.name}`,
      })),
      entities: entities.data.map((item) => ({
        value: item.code,
        label: `${item.code} · ${item.name}`,
        functionalCurrency: item.functional_currency,
      })),
      currencies: enabledCurrencyCodes(currencies.data).map((code) => ({
        value: code,
        label: code,
      })),
    };
  }, [customers.data, products.data, entities.data, currencies.data]);
  return {
    choices,
    error: failed?.error ?? null,
    retry: () => {
      for (const read of reads) {
        if (read.isError) {
          void read.refetch();
        }
      }
    },
  };
}

export function NewContract() {
  const me = useMe();
  const location = useLocation();
  const ctxSearch = contextSearch(location.search);
  const permissions = me.data?.permissions ?? [];
  const allowed =
    permissions.includes(CONTRACT_CREATE_PERMISSION) &&
    permissions.includes(STRUCTURE_READ_PERMISSION);
  const lookups = useDraftChoices(allowed);
  const [initial] = useState(() => emptyDraft("l1"));

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("contracts.draft.new.title")} shape="rows" count={8} />;
  } else if (!permissions.includes(CONTRACT_CREATE_PERMISSION)) {
    body = <AccessLimited permission={t("contracts.draft.access.permission")} />;
  } else if (!permissions.includes(STRUCTURE_READ_PERMISSION)) {
    body = <AccessLimited permission={t("settings.access.permission.configRead")} />;
  } else if (lookups.error !== null) {
    body = (
      <LoadError
        title={t("contracts.draft.loadError")}
        problem={lookups.error}
        onRetry={lookups.retry}
      />
    );
  } else if (lookups.choices === null) {
    body = <Skeleton region={t("contracts.draft.new.title")} shape="rows" count={8} />;
  } else {
    body = (
      <DraftFormView
        mode={{ kind: "new" }}
        initial={initial}
        choices={lookups.choices}
        ctxSearch={ctxSearch}
      />
    );
  }
  return (
    <PageFrame
      testId="SF-03-new-page"
      crumbs={[{ label: t("contracts.workbench.breadcrumb"), to: `/contracts${ctxSearch}` }]}
      title={t("contracts.draft.new.title")}
    >
      {body}
    </PageFrame>
  );
}

export function EditDraft() {
  const me = useMe();
  const params = useParams();
  const contractId = params.contractId ?? "";
  const location = useLocation();
  const navigate = useNavigate();
  const ctxSearch = contextSearch(location.search);
  const permissions = me.data?.permissions ?? [];
  const allowed =
    permissions.includes(CONTRACT_CREATE_PERMISSION) &&
    permissions.includes(STRUCTURE_READ_PERMISSION);
  const lookups = useDraftChoices(allowed);
  // The form is seeded once from what this read answers; "Reload" after a 412 reads and seeds it again.
  const [seed, setSeed] = useState(0);
  const draft = useQuery({
    queryKey: draftForEditKey(contractId, seed),
    queryFn: () => fetchDraftForEdit(contractId),
    enabled: allowed,
    // Read each time the screen opens and never behind the form's back (SCR-ST-09 keeps typed input).
    gcTime: 0,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnReconnect: false,
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 2,
  });
  const contract = draft.data?.contract;
  const edit = draft.data?.edit ?? null;
  const workbenchPath = `/contracts/${contractId}/obligations${ctxSearch}`;
  const contractsPath = `/contracts${ctxSearch}`;
  const title = t("contracts.draft.edit.title");
  const crumbs = [
    { label: t("contracts.workbench.breadcrumb"), to: contractsPath },
    ...(contract === undefined ? [] : [{ label: contract.external_id, to: workbenchPath }]),
  ];
  const backToContract = {
    label: t("contracts.draft.edit.backToContract"),
    onAction: () => void navigate(workbenchPath),
  };

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!permissions.includes(CONTRACT_CREATE_PERMISSION)) {
    body = <AccessLimited permission={t("contracts.draft.access.permission")} />;
  } else if (!permissions.includes(STRUCTURE_READ_PERMISSION)) {
    body = <AccessLimited permission={t("settings.access.permission.configRead")} />;
  } else if (draft.isError && draft.error instanceof ApiProblem && draft.error.status === 404) {
    body = (
      <EmptyState
        title={t("contracts.workbench.notFound")}
        description={t("errors.notFound.description")}
        headingLevel={2}
        action={{
          label: t("contracts.workbench.goToContracts"),
          onAction: () => void navigate(contractsPath),
        }}
      />
    );
  } else if (draft.isError) {
    body = (
      <LoadError
        title={t("contracts.workbench.loadError")}
        problem={draft.error}
        onRetry={() => void draft.refetch()}
      />
    );
  } else if (contract === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (edit === null) {
    const chip = chipFor("E-17", contract.status);
    body = (
      <EmptyState
        title={t("contracts.draft.edit.notDraftTitle")}
        description={t("contracts.draft.edit.notDraftDescription", {
          id: contract.external_id,
          status: chip === null ? contract.status : t(statusMessageKey(chip.status)),
        })}
        headingLevel={2}
        action={backToContract}
      />
    );
  } else if (edit.kind !== "open") {
    // Ruling R-93 (a): the booking is no longer the draft.
    body = (
      <EmptyState
        title={t("contracts.draft.edit.changedTitle")}
        description={t("contracts.draft.edit.changedDescription")}
        headingLevel={2}
        action={backToContract}
      />
    );
  } else if (lookups.error !== null) {
    body = (
      <LoadError
        title={t("contracts.draft.loadError")}
        problem={lookups.error}
        onRetry={lookups.retry}
      />
    );
  } else if (lookups.choices === null) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else {
    body = (
      <EditDraftForm
        key={seed}
        contract={contract}
        payload={edit.booking.payload}
        head={edit.head}
        assessed={edit.assessed}
        choices={lookups.choices}
        ctxSearch={ctxSearch}
        onReload={() => setSeed((current) => current + 1)}
      />
    );
  }
  return (
    <PageFrame
      testId="SF-03-edit-page"
      crumbs={crumbs}
      title={title}
      identifier={contract?.external_id}
    >
      {body}
    </PageFrame>
  );
}

function EditDraftForm({
  contract,
  payload,
  head,
  assessed,
  choices,
  ctxSearch,
  onReload,
}: {
  readonly contract: Contract;
  readonly payload: unknown;
  /** The stream version the guard read the booking at. */
  readonly head: number;
  /** A Step 1 assessment stands on the stream the guard read: the save voids it (ruling R-102 (c)). */
  readonly assessed: boolean;
  readonly choices: DraftChoices;
  readonly ctxSearch: string;
  readonly onReload: () => void;
}) {
  // Seeded once per opening: the form holds the typed input from here on.
  const [initial] = useState(() =>
    draftFromBooking(contract, payload, (index) => `l${String(index + 1)}`),
  );
  // The customer on the draft stays a choice even when it is no longer active.
  const customers = choices.customers.some((item) => item.value === contract.customer.id)
    ? choices.customers
    : [
        {
          value: contract.customer.id,
          label: `${contract.customer.name} · ${contract.customer.code}`,
        },
        ...choices.customers,
      ];
  return (
    <DraftFormView
      mode={{ kind: "edit", contract, head, assessed }}
      initial={initial}
      choices={{ ...choices, customers }}
      ctxSearch={ctxSearch}
      onReload={onReload}
    />
  );
}

type DraftMode =
  | { readonly kind: "new" }
  | {
      readonly kind: "edit";
      readonly contract: Contract;
      /** The stream version the form was seeded at: the `If-Match` of `replace-draft`. */
      readonly head: number;
      /** A Step 1 assessment stands on the draft: SCREENS §4.10 (rev 1.72), the warning above the form. */
      readonly assessed: boolean;
    };

interface CustomerComboboxProps {
  readonly control: FieldControlProps;
  readonly options: readonly Choice[];
  readonly value: DraftCustomer | null;
  readonly onChange: (value: DraftCustomer | null) => void;
  readonly invalid: boolean;
}

/**
 * The Customer combobox (APG Combobox with list autocomplete, as `components/form/Combobox`) with the
 * SCREENS §4.10 option "Create customer <name>" after the matches of the typed text.
 */
function CustomerCombobox({ control, options, value, onChange, invalid }: CustomerComboboxProps) {
  const { name, ...inputProps } = control;
  const listId = `${control.id}-listbox`;
  const selectedLabel =
    value === null
      ? ""
      : value.kind === "new"
        ? value.name
        : (options.find((option) => option.value === value.id)?.label ?? "");
  const [text, setText] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    setText(selectedLabel);
  }, [selectedLabel]);

  const typed = text.trim();
  const query = typed.toLocaleLowerCase();
  const matches: readonly ListOption<string>[] =
    text === selectedLabel || query === ""
      ? options
      : options.filter((option) => option.label.toLocaleLowerCase().includes(query));
  const exact = options.some((option) => option.label.toLocaleLowerCase() === query);
  const listed: readonly ListOption<string>[] =
    typed === "" || exact || text === selectedLabel
      ? matches
      : [
          ...matches,
          { value: CREATE_VALUE, label: t("contracts.draft.createCustomer", { name: typed }) },
        ];
  const pick = (index: number) => {
    const option = listed[index];
    if (option !== undefined) {
      if (option.value === CREATE_VALUE) {
        onChange({ kind: "new", name: typed });
        setText(typed);
      } else {
        onChange({ kind: "existing", id: option.value });
        setText(option.label);
      }
    }
    setOpen(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (open) {
          setActive((index) => Math.min(listed.length - 1, index + 1));
        } else {
          setActive(0);
          setOpen(true);
        }
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => Math.max(0, index - 1));
        return;
      case "Enter":
        if (open && listed.length > 0) {
          event.preventDefault();
          pick(active);
        }
        return;
      case "Escape":
        event.preventDefault();
        if (open) {
          setOpen(false);
        } else if (text !== "") {
          setText("");
          onChange(null);
        }
        return;
      default:
    }
  };
  return (
    <div className="relative">
      <input
        type="hidden"
        name={name}
        value={value === null ? "" : value.kind === "new" ? value.name : value.id}
      />
      <input
        {...inputProps}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && listed.length > 0 ? optionId(listId, active) : undefined}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => {
          setOpen(false);
          setText(selectedLabel);
        }}
        className={controlClass(invalid)}
      />
      {open && listed.length > 0 ? (
        <Listbox
          id={listId}
          labelledBy={fieldLabelId(name)}
          options={listed}
          active={active}
          selected={new Set(value !== null && value.kind === "existing" ? [value.id] : [])}
          onPick={pick}
        />
      ) : null}
      {open && listed.length === 0 ? (
        <div
          role="status"
          className="absolute start-0 top-full z-[var(--z-popover)] mt-1 min-w-full rounded-lg border border-hairline bg-raised px-3 py-2 text-body-sm text-fg-3 shadow-popover"
        >
          {t("common.form.combobox.noMatches")}
        </div>
      ) : null}
    </div>
  );
}

const COLUMN_KIND: Readonly<Record<DraftColumn, LineCellKind>> = {
  obligationKey: "text",
  product: "combobox",
  stratification: "text",
  quantity: "decimal",
  totalPrice: "money",
  unitPrice: "decimal",
  startDate: "date",
  endDate: "date",
  performingEntity: "select",
  sspVersion: "text",
  scope: "select",
  outOfScopeAmount: "money",
  memo1: "text",
  memo2: "text",
  memo3: "text",
};
const COLUMN_WIDTH: Readonly<Record<DraftColumn, string>> = {
  obligationKey: "w-32 min-w-32",
  product: "w-72 min-w-72",
  stratification: "w-40 min-w-40",
  quantity: "w-28 min-w-28",
  totalPrice: "w-48 min-w-48",
  unitPrice: "w-36 min-w-36",
  startDate: "w-36 min-w-36",
  endDate: "w-36 min-w-36",
  performingEntity: "w-64 min-w-64",
  sspVersion: "w-44 min-w-44",
  scope: "w-64 min-w-64",
  outOfScopeAmount: "w-48 min-w-48",
  memo1: "w-44 min-w-44",
  memo2: "w-44 min-w-44",
  memo3: "w-44 min-w-44",
};

/** SCREENS §4.10 lines grid: the columns of the line editor over the form's lines. */
function lineColumns(
  choices: Pick<DraftChoices, "products" | "entities">,
  currency: string | null,
  contractingEntity: string | null,
): readonly LineColumn<DraftLine>[] {
  // Amounts parse and echo once the chosen currency's minor unit is known (DS-FMT-03).
  const money = currency !== null && currencyRegistered(currency) ? currency : null;
  const options: Partial<Record<DraftColumn, readonly Choice[]>> = {
    product: choices.products,
    performingEntity: choices.entities,
    scope: SCOPE_FLAGS.map((flag) => ({
      value: flag,
      label: t(`contracts.obligation.scope.${flag}`),
    })),
  };
  return LINE_COLUMNS.map((column) => {
    const label = t(`contracts.draft.column.${column}`);
    const kind = COLUMN_KIND[column];
    return {
      id: column,
      header:
        kind === "money" && money !== null
          ? t(`contracts.draft.column.${column}In`, { currency: money })
          : label,
      label,
      kind,
      value: (line) => lineValue(line, column, contractingEntity),
      options: options[column],
      currency: kind === "money" ? money : undefined,
      // SCREENS §4.10: the out-of-scope amount belongs to a line whose scope differs.
      disabled: column === "outOfScopeAmount" ? (line) => line.scope === IN_SCOPE : undefined,
      rowHeader: column === "obligationKey",
      width: COLUMN_WIDTH[column],
    };
  });
}

/** The header fields in form order: the order of the error summary. */
const HEADER_FIELDS = [
  "externalId",
  "customer",
  "customerCode",
  "entity",
  "currency",
  "inceptionDate",
  "signatureDate",
  "documentRef",
  "paymentTerms",
  "terminationParty",
  "hasPenalty",
  "noticeDays",
  "region",
  "channel",
  "contractType",
  "memo1",
  "memo2",
  "memo3",
] as const;

function without(
  record: Readonly<Record<string, string>>,
  names: readonly string[],
): Readonly<Record<string, string>> {
  if (!names.some((name) => name in record)) {
    return record;
  }
  return Object.fromEntries(Object.entries(record).filter(([name]) => !names.includes(name)));
}

function Section({ title, children }: { readonly title: string; readonly children: ReactNode }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <h2 id={headingId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
        {title}
      </h2>
      {children}
    </section>
  );
}

interface ServerProblem {
  readonly problem: ApiProblem;
  readonly fields: Readonly<Record<string, string>>;
  readonly unplaced: readonly string[];
}

interface DraftFormViewProps {
  readonly mode: DraftMode;
  readonly initial: DraftForm;
  readonly choices: DraftChoices;
  readonly ctxSearch: string;
  /** SF-03:edit after a 412: read the draft again and seed the form from it. */
  readonly onReload?: (() => void) | undefined;
}

function DraftFormView({ mode, initial, choices, ctxSearch, onReload }: DraftFormViewProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const refresh = useRefreshRecord();
  const editing = mode.kind === "edit";
  const [form, setForm] = useState(initial);
  const [attempted, setAttempted] = useState(false);
  // Moves focus to the error summary (two or more errors) or to the one wrong field.
  const [focusTick, setFocusTick] = useState(0);
  const [formatErrors, setFormatErrors] = useState<Readonly<Record<string, string>>>({});
  const [server, setServer] = useState<ServerProblem | null>(null);
  const [unreached, setUnreached] = useState(false);
  const [saving, setSaving] = useState<"draft" | "submit" | null>(null);
  const lineIds = useRef(initial.lines.length);
  const pendingFocus = useRef<string | null>(null);
  const leaving = useRef(false);
  const command = useCommand<Contract>({
    method: "POST",
    path: editing ? replaceDraftPath(mode.contract.id) : CONTRACTS_PATH,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  // The key of the activation command that follows the save (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();

  const built = useMemo(() => buildDraft(form), [form]);
  const columns = useMemo(
    () => lineColumns(choices, form.currency, form.entity),
    [choices, form.currency, form.entity],
  );
  const errors: Readonly<Record<string, string>> = {
    ...formatErrors,
    ...(server?.fields ?? {}),
    ...(attempted ? built.errors : {}),
  };
  const entries: FormErrorEntry[] = [
    ...[...HEADER_FIELDS, LINES_FIELD].flatMap((name) =>
      name in errors ? [{ name, message: errors[name] ?? "" }] : [],
    ),
    ...form.lines.flatMap((line, index) =>
      LINE_COLUMNS.flatMap((column) => {
        const name = lineField(line.id, column);
        return name in errors
          ? [
              {
                name,
                message: t("contracts.draft.error.inLine", {
                  line: formatNumber(index + 1, { kind: "count" }),
                  message: errors[name] ?? "",
                }),
              },
            ]
          : [];
      }),
    ),
  ];
  const onlyError = entries.length === 1 ? (entries[0]?.name ?? null) : null;
  useEffect(() => {
    if (focusTick > 0 && onlyError !== null) {
      document.getElementById(fieldId(onlyError))?.focus();
    }
    // Focus follows a submit, not every change of the errors.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusTick]);
  useEffect(() => {
    if (pendingFocus.current !== null) {
      document.getElementById(pendingFocus.current)?.focus();
      pendingFocus.current = null;
    }
  });

  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname,
  );

  const clearServer = (names: readonly string[]) =>
    setServer((current) =>
      current === null ? null : { ...current, fields: without(current.fields, names) },
    );
  const set = <K extends keyof DraftForm>(name: K, value: DraftForm[K]) => {
    setForm((current) => ({ ...current, [name]: value }));
    clearServer([name]);
  };
  const setFormatError = (name: string, message: string | null) =>
    setFormatErrors((current) =>
      message === null ? without(current, [name]) : { ...current, [name]: message },
    );
  const changeLine = (lineId: string, columnId: string, value: string) => {
    const column = LINE_COLUMNS.find((candidate) => candidate === columnId);
    if (column === undefined) {
      return;
    }
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line) =>
        line.id === lineId ? { ...line, ...linePatch(column, value, current.entity) } : line,
      ),
    }));
    clearServer([
      lineField(lineId, column),
      // Choosing "In scope (ASC 606)" also clears the out-of-scope amount.
      ...(column === "scope" ? [lineField(lineId, "outOfScopeAmount")] : []),
    ]);
  };
  const addLine = () => {
    lineIds.current += 1;
    const id = `l${String(lineIds.current)}`;
    setForm((current) => ({
      ...current,
      lines: [...current.lines, emptyLine(id, nextObligationKey(current.lines))],
    }));
    pendingFocus.current = fieldId(lineField(id, "obligationKey"));
  };
  const removeLine = (lineId: string) => {
    const index = form.lines.findIndex((line) => line.id === lineId);
    const neighbour = form.lines[index + 1] ?? form.lines[index - 1];
    pendingFocus.current =
      neighbour === undefined
        ? fieldId(LINES_FIELD)
        : fieldId(lineField(neighbour.id, "obligationKey"));
    setForm((current) => ({
      ...current,
      lines: current.lines.filter((line) => line.id !== lineId),
    }));
    const names = LINE_COLUMNS.map((column) => lineField(lineId, column));
    setFormatErrors((current) => without(current, names));
    // The pointers of the server name rows by position, which a removal moves.
    setServer(null);
  };
  const chooseEntity = (code: string) => {
    const functional = choices.entities.find((item) => item.value === code)?.functionalCurrency;
    const offered = choices.currencies.some((item) => item.value === functional);
    setForm((current) => ({
      ...current,
      entity: code,
      currency: current.currency ?? (offered && functional !== undefined ? functional : null),
    }));
    clearServer(["entity", "currency"]);
  };

  const workbenchPath = (contractId: string) => `/contracts/${contractId}/obligations${ctxSearch}`;
  /** Opens SF-03; `step1` opens the Step 1 segment of its tracker (SCREENS §4.1.3 `?step=1`). */
  const leave = (contractId: string, step1 = false) => {
    leaving.current = true;
    void navigate(
      step1
        ? `/contracts/${contractId}/obligations${withParams(ctxSearch, { step: "1" })}`
        : workbenchPath(contractId),
    );
  };
  const cancel = () => {
    void navigate(editing ? workbenchPath(mode.contract.id) : `/contracts${ctxSearch}`);
  };

  const save = async (submitAfter: boolean) => {
    setAttempted(true);
    setUnreached(false);
    if (built.body === null) {
      setFocusTick((tick) => tick + 1);
      return;
    }
    setServer(null);
    setSaving(submitAfter ? "submit" : "draft");
    const outcome = await command.submit(
      built.body,
      editing ? { ifMatch: contractIfMatch(mode.head) } : {},
    );
    if (outcome.kind === "failed") {
      setServer({ problem: outcome.problem, ...placeProblem(outcome.problem, form) });
      setFocusTick((tick) => tick + 1);
      setSaving(null);
      return;
    }
    if (outcome.kind !== "succeeded" || outcome.data === null) {
      setUnreached(outcome.kind === "network-error");
      setSaving(null);
      return;
    }
    const saved = outcome.data;
    if (!submitAfter) {
      toast.show({ tone: "positive", message: t("contracts.draft.saved") });
      leave(saved.id);
      return;
    }
    // Activation is its own command on the saved draft (04 §16.1), with the head the save answered.
    let activation: Awaited<ReturnType<typeof sendCommand<Contract>>> | null = null;
    try {
      activation = await sendCommand<Contract>(
        keys,
        "POST",
        submitActivationPath(saved.id),
        { comment: null } satisfies SubmitActivationBody,
        contractIfMatch(saved.head_stream_version),
      );
    } catch {
      activation = null;
    }
    await refresh();
    let step1 = false;
    if (activation === null) {
      toast.show({ tone: "warning", message: t("contracts.draft.notSubmittedUnreached") });
    } else if (!activation.ok) {
      // 409 `activation-checklist-failed` names each failed item (04 table 15.4-I). A new manual draft
      // has no Step 1 review yet (ruling R-89), so that refusal leads to step 1 of the tracker.
      // A toast holds two lines (DS-CMP-22): it names the first thing to do, and "Submit for
      // activation" on SF-03 lists every failed item with its fix (SCREENS §4.9.8).
      const failed = activation.problem.errors.filter((error) => error.rule_id !== null);
      step1 = failed.some((item) => STEP1_FIXES.has(fixActionOf(item.rule_id)));
      const [only] = failed;
      toast.show({
        tone: "warning",
        message: step1
          ? t("contracts.draft.notSubmittedStep1")
          : failed.length > 1
            ? t("contracts.draft.notSubmittedItems", {
                count: failed.length,
                formatted: formatNumber(failed.length, { kind: "count" }),
              })
            : t("contracts.draft.notSubmitted", {
                reason: only?.message ?? activation.problem.title,
              }),
      });
    } else {
      const requestId = activation.response.headers.get(APPROVAL_REQUEST_HEADER);
      toast.show({
        tone: "positive",
        message:
          activation.data.status === "ACTIVE" || requestId === null
            ? t("contracts.workbench.activation.activated")
            : t("contracts.workbench.activation.submitted", {
                request: await requestNumber(requestId),
              }),
      });
    }
    leave(saved.id, step1);
  };

  const busy = saving !== null;
  const shown = (name: string) => errors[name] ?? null;
  const hasRight = form.terminationParty !== null && form.terminationParty !== "NONE";
  const parties = TERMINATION_PARTIES.map((party) => ({
    value: party,
    label: t(`contracts.drawer.step1.party.${party === "NONE" ? "none" : party.toLowerCase()}`),
  }));
  const yesNo: readonly { readonly value: YesNo; readonly label: string }[] = [
    { value: "YES", label: t("contracts.drawer.yes") },
    { value: "NO", label: t("contracts.drawer.no") },
  ];
  const problem = server?.problem ?? null;

  return (
    <form
      noValidate
      aria-labelledby="draft-form-title"
      aria-busy={busy ? true : undefined}
      className="flex flex-1 flex-col gap-6"
      onSubmit={(event) => event.preventDefault()}
    >
      <div inert={busy} className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6">
        {editing && mode.assessed ? (
          <Banner tone="warning" title={t("contracts.draft.edit.assessedTitle")} announce="static">
            <p>{t("contracts.draft.edit.assessedDescription")}</p>
          </Banner>
        ) : null}
        {command.banner !== null ? (
          <Banner
            tone="warning"
            title={command.banner}
            actions={
              onReload === undefined ? undefined : (
                <Button variant="link" onClick={onReload}>
                  {t("contracts.draft.reload")}
                </Button>
              )
            }
          />
        ) : problem !== null ? (
          <Banner tone="negative" title={problem.title} announce="live">
            {problem.detail === null ? null : <p>{problem.detail}</p>}
            {(server?.unplaced ?? []).map((message) => (
              <p key={message}>{message}</p>
            ))}
            {problem.requestId === null ? null : (
              <p>{t("contracts.drawer.reference", { reference: problem.requestId })}</p>
            )}
          </Banner>
        ) : unreached ? (
          <Banner tone="negative" title={t("contracts.draft.notReached")} announce="live" />
        ) : null}
        <ErrorSummary errors={entries} submitCount={focusTick} />
        <Section title={t("contracts.draft.section.contract")}>
          <TextField
            name="externalId"
            label={t("contracts.draft.field.externalId")}
            required
            readOnly={editing}
            help={editing ? undefined : t("contracts.draft.field.externalIdHelp")}
            value={form.externalId}
            onChange={(value) => set("externalId", value)}
            error={shown("externalId")}
          />
          <Field
            name="customer"
            label={t("contracts.draft.field.customer")}
            required
            error={shown("customer")}
            width="text"
          >
            {(control) => (
              <CustomerCombobox
                control={control}
                options={choices.customers}
                value={form.customer}
                onChange={(value) => set("customer", value)}
                invalid={shown("customer") !== null}
              />
            )}
          </Field>
          {form.customer?.kind === "new" ? (
            <TextField
              name="customerCode"
              label={t("contracts.draft.field.customerCode")}
              required
              help={t("contracts.draft.field.customerCodeHelp")}
              value={form.customerCode}
              onChange={(value) => set("customerCode", value)}
              error={shown("customerCode")}
            />
          ) : null}
          <div className="flex flex-wrap gap-4">
            {editing ? (
              <TextField
                name="entity"
                label={t("contracts.draft.field.entity")}
                readOnly
                value={
                  choices.entities.find((item) => item.value === form.entity)?.label ??
                  form.entity ??
                  ""
                }
                onChange={() => undefined}
              />
            ) : (
              <Field
                name="entity"
                label={t("contracts.draft.field.entity")}
                required
                error={shown("entity")}
                width="text"
              >
                {(control) => (
                  <Select<string>
                    control={control}
                    options={choices.entities}
                    value={form.entity}
                    onChange={chooseEntity}
                    invalid={shown("entity") !== null}
                  />
                )}
              </Field>
            )}
            {editing ? (
              <TextField
                name="currency"
                label={t("contracts.draft.field.currency")}
                readOnly
                width="period"
                value={form.currency ?? ""}
                onChange={() => undefined}
              />
            ) : (
              <Field
                name="currency"
                label={t("contracts.draft.field.currency")}
                required
                error={shown("currency")}
                width="date"
              >
                {(control) => (
                  <Select<string>
                    control={control}
                    options={choices.currencies}
                    value={form.currency}
                    onChange={(value) => set("currency", value)}
                    invalid={shown("currency") !== null}
                  />
                )}
              </Field>
            )}
          </div>
          <div className="flex flex-wrap gap-4">
            <Field
              name="inceptionDate"
              label={t("contracts.draft.field.inceptionDate")}
              required
              error={shown("inceptionDate")}
              width="date"
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={form.inceptionDate}
                  onChange={(text) => set("inceptionDate", text)}
                  onFormatError={(message) => setFormatError("inceptionDate", message)}
                  invalid={shown("inceptionDate") !== null}
                />
              )}
            </Field>
            <Field
              name="signatureDate"
              label={t("contracts.draft.field.signatureDate")}
              optional
              error={shown("signatureDate")}
              width="date"
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={form.signatureDate}
                  onChange={(text) => set("signatureDate", text)}
                  onFormatError={(message) => setFormatError("signatureDate", message)}
                  invalid={shown("signatureDate") !== null}
                />
              )}
            </Field>
          </div>
          <TextField
            name="documentRef"
            label={t("contracts.draft.field.documentRef")}
            optional
            help={t("contracts.draft.field.documentRefHelp")}
            value={form.documentRef}
            onChange={(value) => set("documentRef", value)}
            error={shown("documentRef")}
          />
          <TextField
            name="paymentTerms"
            label={t("contracts.draft.field.paymentTerms")}
            optional
            value={form.paymentTerms}
            onChange={(value) => set("paymentTerms", value)}
            error={shown("paymentTerms")}
          />
        </Section>
        <Section title={t("contracts.draft.section.termination")}>
          <SelectField<TerminationParty>
            name="terminationParty"
            label={t("contracts.draft.field.terminationParty")}
            optional
            options={parties}
            value={form.terminationParty}
            onChange={(value) => set("terminationParty", value)}
            error={shown("terminationParty")}
          />
          {hasRight ? (
            <div className="flex flex-wrap gap-4">
              <Field
                name="hasPenalty"
                label={t("contracts.draft.field.hasPenalty")}
                optional
                error={shown("hasPenalty")}
                width="date"
              >
                {(control) => (
                  <Select<YesNo>
                    control={control}
                    options={yesNo}
                    value={form.hasPenalty}
                    onChange={(value) => set("hasPenalty", value)}
                    invalid={shown("hasPenalty") !== null}
                  />
                )}
              </Field>
              <TextField
                name="noticeDays"
                label={t("contracts.draft.field.noticeDays")}
                optional
                width="date"
                inputMode="numeric"
                value={form.noticeDays}
                onChange={(value) => set("noticeDays", value)}
                error={shown("noticeDays")}
              />
            </div>
          ) : null}
        </Section>
        <Section title={t("contracts.draft.section.classification")}>
          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-2 text-body-sm font-medium text-fg-1">
              <input
                id={fieldId("hasCommercialSubstance")}
                type="checkbox"
                className="size-4"
                checked={form.hasCommercialSubstance}
                aria-describedby={`${fieldId("hasCommercialSubstance")}-help`}
                onChange={(event) => set("hasCommercialSubstance", event.target.checked)}
              />
              {t("contracts.draft.field.commercialSubstance")}
            </label>
            <p id={`${fieldId("hasCommercialSubstance")}-help`} className="text-body-sm text-fg-3">
              {t("contracts.draft.field.commercialSubstanceHelp")}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {(["region", "channel", "contractType"] as const).map((name) => (
              <TextField
                key={name}
                name={name}
                label={t(`contracts.draft.field.${name}`)}
                optional
                width="full"
                value={form[name]}
                onChange={(value) => set(name, value)}
                error={shown(name)}
              />
            ))}
          </div>
          <div className="grid grid-cols-3 gap-4">
            {(["memo1", "memo2", "memo3"] as const).map((name, index) => (
              <TextField
                key={name}
                name={name}
                label={t("contracts.draft.field.memo", {
                  number: formatNumber(index + 1, { kind: "count" }),
                })}
                optional
                width="full"
                value={form[name]}
                onChange={(value) => set(name, value)}
                error={shown(name)}
              />
            ))}
          </div>
        </Section>
      </div>
      <div inert={busy}>
        <LineEditor<DraftLine>
          title={t("contracts.draft.lines.title")}
          countLabel={(count, formatted) => t("contracts.draft.lines.count", { count, formatted })}
          columns={columns}
          rows={form.lines}
          rowId={(line) => line.id}
          name={LINES_FIELD}
          cellName={lineField}
          errors={errors}
          onChange={changeLine}
          onFormatError={setFormatError}
          addLabel={t("contracts.draft.lines.add")}
          addDisabledReason={
            form.lines.length >= MAX_LINES
              ? t("contracts.draft.lines.limit", {
                  limit: formatNumber(MAX_LINES, { kind: "count" }),
                })
              : undefined
          }
          onAdd={addLine}
          removeLabel={(line, index) =>
            t("contracts.draft.lines.remove", {
              key:
                line.obligationKey.trim() === ""
                  ? formatNumber(index + 1, { kind: "count" })
                  : line.obligationKey.trim(),
            })
          }
          onRemove={removeLine}
          emptyText={t("contracts.draft.lines.empty")}
          testId="SF-03-grid-lines"
        />
      </div>
      {/* Flush with the bottom edge of the scrolling region, whose padding is the gutter: nothing of
          the form shows below the footer. It says "More below" while lines lie beneath it
          (DESIGN_SYSTEM rev 1.9). */}
      <StickyFooter cueTestId="SF-03-more-below">
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={cancel}>
            {t("contracts.draft.cancel")}
          </Button>
          <Button
            variant="secondary"
            loading={saving === "draft"}
            disabledReason={saving === "submit" ? t("common.dialog.submitting") : undefined}
            onClick={() => void save(false)}
          >
            {t("contracts.draft.save")}
          </Button>
          <Button
            variant="primary"
            loading={saving === "submit"}
            disabledReason={saving === "draft" ? t("common.dialog.submitting") : undefined}
            onClick={() => void save(true)}
          >
            {t("contracts.draft.saveAndSubmit")}
          </Button>
        </div>
      </StickyFooter>
      <Modal
        open={blocker.state === "blocked"}
        variant="confirmation"
        title={t("common.dialog.discard.title")}
        description={t("common.dialog.discard.description")}
        primaryAction={{
          label: t("common.dialog.discard.confirm"),
          destructive: true,
          onAction: () => blocker.proceed?.(),
        }}
        onClose={() => blocker.reset?.()}
      />
    </form>
  );
}

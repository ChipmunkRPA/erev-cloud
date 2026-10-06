// SF-13:ssp-calculator Historical SSP calculator (SCREENS §11.0 frame, §11.5 "New run" form and "Runs"
// panel; §0.4 RT-67; §0.7 SCR-PERM-01, SCR-PERM-02; DESIGN_SYSTEM DS-CMP-19, DS-CMP-21; 04 API-R-27
// `GET, POST /ssp-calculator-runs`, API-R-12 `POST /files` purpose `IMPORT_SOURCE`, API-R-26 `GET
// /ssp-books`, API-R-23 `GET /products`, `GET /tenant-currencies`; BUILD_SPEC RFD-24). For `ssp.create`
// the panel "New run": Name, SSP book, Products, Source, Pool file (uploaded source; CSV, 50 MiB),
// Date from, Date to, Band around the median (default 15.00%), Currency; "Run calculator" uploads the
// pool, posts the run (202 job `SSP_CALCULATOR`) and opens the run. The panel "Runs" lists the newest
// runs and refreshes while one is queued or running.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { Link, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommandKeys } from "../../lib/api/commands";
import { ApiProblem, fieldErrorsOf, readProblem } from "../../lib/api/problems";
import {
  fetchAllSspBooks,
  percentTextToRatio,
  type SspBook,
  sspBookVersionRoute,
  uploadFile,
} from "../../lib/api/queries/ssp-books";
import {
  type CalculatorSource,
  EVERY_SSP_RUN,
  fetchActiveProducts,
  fetchSspRuns,
  fetchTenantCurrencies,
  isActiveRun,
  POOL_FILE_PURPOSE,
  POOL_MAX_BYTES,
  POOL_UPLOAD_PERMISSION,
  type Product,
  productsKey,
  RUN_ID_HEADER,
  RUN_POLL_INTERVAL_MS,
  SOURCES,
  SSP_CALCULATOR_RUNS_PATH,
  type SspCalculatorRun,
  sspRunRoute,
  sspRunsKey,
  tenantCurrenciesKey,
} from "../../lib/api/queries/ssp-calculator";
import { queryKey } from "../../lib/api/query-keys";
import { formatList, formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { problemText, SspPage } from "./ssp-books";

/** SCREENS §11.5 default band around the median. */
export const DEFAULT_BAND_TEXT = "15.00";

export function SspCalculator() {
  return <SspPage>{(create) => <CalculatorBody create={create} />}</SspPage>;
}

function CalculatorBody({ create }: { readonly create: boolean }) {
  const products = useQuery({ queryKey: productsKey(), queryFn: fetchActiveProducts });
  return (
    <div className="flex flex-col gap-8">
      {create ? <NewRunPanel products={products.data} /> : null}
      <RunsPanel products={products.data} />
    </div>
  );
}

/** The API field of a server error, mapped onto the form field it belongs to. */
const SERVER_FIELDS: Readonly<Record<string, string>> = {
  name: "name",
  "parameters.ssp_book_id": "book",
  "parameters.product_ids": "products",
  "parameters.source": "source",
  "parameters.pool_file_id": "pool",
  "parameters.date_from": "dateFrom",
  "parameters.date_to": "dateTo",
  "parameters.band_ratio": "band",
  "parameters.currency": "currency",
};

function serverErrors(problem: ApiProblem | null): Readonly<Record<string, string>> {
  const errors: Record<string, string> = {};
  if (problem === null) {
    return errors;
  }
  for (const [field, message] of Object.entries(fieldErrorsOf(problem))) {
    const local = SERVER_FIELDS[field];
    if (local !== undefined && errors[local] === undefined) {
      errors[local] = message;
    }
  }
  return errors;
}

function NewRunPanel({ products }: { readonly products: readonly Product[] | undefined }) {
  const navigate = useNavigate();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  // The keys of the pool upload and of the run's start (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const queryClient = useQueryClient();
  const access = useAccess();
  const canUpload = access.holdsAnywhere(POOL_UPLOAD_PERMISSION);
  const books = useQuery({
    queryKey: queryKey("ssp-books", "tenant", { view: "all" }),
    queryFn: fetchAllSspBooks,
  });
  const currencies = useQuery({ queryKey: tenantCurrenciesKey(), queryFn: fetchTenantCurrencies });
  const headingId = useId();
  const formId = useId();
  const [name, setName] = useState("");
  const [bookId, setBookId] = useState<string | null>(null);
  const [productIds, setProductIds] = useState<readonly string[]>([]);
  const [source, setSource] = useState<CalculatorSource>("source_order_lines");
  const [pool, setPool] = useState<File | null>(null);
  const [fromTyped, setFromTyped] = useState("");
  const [from, setFrom] = useState<string | null>(null);
  const [fromError, setFromError] = useState<string | null>(null);
  const [toTyped, setToTyped] = useState("");
  const [to, setTo] = useState<string | null>(null);
  const [toError, setToError] = useState<string | null>(null);
  const [band, setBand] = useState(DEFAULT_BAND_TEXT);
  const [currency, setCurrency] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const errors = { ...serverErrors(problem), ...local };

  const selectBook = (id: string) => {
    setBookId(id);
    const chosen = books.data?.find((item: SspBook) => item.id === id);
    if (currency === null && chosen?.currency !== null && chosen?.currency !== undefined) {
      setCurrency(chosen.currency);
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending || fromError !== null || toError !== null) {
      return;
    }
    const found: Record<string, string> = {};
    if (name.trim() === "") {
      found.name = t("policies.sspCalculator.form.nameRequired");
    }
    if (bookId === null) {
      found.book = t("policies.sspCalculator.form.bookRequired");
    }
    if (productIds.length === 0) {
      found.products = t("policies.sspCalculator.form.productsRequired");
    }
    if (source === "source_order_lines") {
      if (pool === null) {
        found.pool = t("policies.sspCalculator.form.poolRequired");
      } else if (pool.size > POOL_MAX_BYTES) {
        found.pool = t("policies.sspCalculator.form.poolTooLarge");
      }
    }
    if (from === null) {
      found.dateFrom = t("policies.sspCalculator.form.dateRequired");
    }
    if (to === null) {
      found.dateTo = t("policies.sspCalculator.form.dateRequired");
    }
    const ratio = percentTextToRatio(band);
    if (ratio === null) {
      found.band = t("policies.sspVersion.entry.percentInvalid");
    }
    if (currency === null) {
      found.currency = t("policies.sspCalculator.form.currencyRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setPending(true);
    setProblem(null);
    let poolId: string | null = null;
    if (source === "source_order_lines" && pool !== null) {
      try {
        poolId = (await uploadFile(keys, POOL_FILE_PURPOSE, pool)).id;
      } catch (error) {
        setPending(false);
        setProblem(
          error instanceof ApiProblem
            ? error
            : new ApiProblem({
                type: "about:blank",
                slug: null,
                // No answer: the same file is sent under the same key on the next press.
                title: t("common.command.noAnswer"),
                status: 0,
                detail: null,
                code: null,
                errors: [],
                requestId: null,
              }),
        );
        return;
      }
    }
    const response = await keys
      .send("POST", SSP_CALCULATOR_RUNS_PATH, {
        body: {
          name: name.trim(),
          parameters: {
            source,
            product_ids: productIds,
            date_from: from,
            date_to: to,
            band_ratio: ratio,
            currency,
            ssp_book_id: bookId,
            ...(poolId === null ? {} : { pool_file_id: poolId }),
          },
        },
      })
      .catch(() => null);
    if (response === null) {
      // No answer: the form keeps its input, and the next press starts the run under the same key,
      // so a run the API did start is not started twice.
      setPending(false);
      noAnswer();
      return;
    }
    if (!response.ok) {
      setPending(false);
      setProblem(await readProblem(response));
      return;
    }
    const runId = response.headers.get(RUN_ID_HEADER);
    await queryClient.invalidateQueries({ queryKey: EVERY_SSP_RUN });
    setPending(false);
    toast.show({
      tone: "positive",
      message: t("policies.sspCalculator.started", { name: name.trim() }),
    });
    if (runId !== null) {
      void navigate(sspRunRoute(runId));
    }
  };

  const dateField = (
    field: "dateFrom" | "dateTo",
    typed: string,
    setTyped: (text: string) => void,
    setValue: (date: string | null) => void,
    formatError: string | null,
    setFormatError: (message: string | null) => void,
  ) => (
    <Field
      name={`calculator_${field}`}
      label={t(`policies.sspCalculator.form.${field}`)}
      required
      error={formatError ?? errors[field] ?? null}
      width="date"
    >
      {(control) => (
        <DateInput
          control={control}
          value={typed}
          onChange={setTyped}
          onValue={setValue}
          onFormatError={setFormatError}
          invalid={formatError !== null || errors[field] !== undefined}
        />
      )}
    </Field>
  );

  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-4 rounded-md border border-hairline bg-surface p-4"
    >
      <h2 id={headingId} className="text-title-md text-fg-1">
        {t("policies.sspCalculator.form.title")}
      </h2>
      {problem !== null && Object.keys(serverErrors(problem)).length === 0 ? (
        <Banner tone="negative" announce="live" title={problem.detail ?? problem.title} />
      ) : null}
      <form
        id={formId}
        aria-labelledby={headingId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Field
            name="calculator_name"
            label={t("policies.sspCalculator.form.name")}
            required
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
                }}
                className={controlClass(errors.name !== undefined)}
              />
            )}
          </Field>
          <Field
            name="calculator_book"
            label={t("policies.sspCalculator.form.book")}
            required
            error={errors.book ?? null}
            width="text"
          >
            {(control) => (
              <Select<string>
                control={control}
                options={(books.data ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.code} · ${item.name}`,
                }))}
                value={bookId}
                onChange={selectBook}
                invalid={errors.book !== undefined}
              />
            )}
          </Field>
          <Field
            name="calculator_products"
            label={t("policies.sspCalculator.form.products")}
            required
            error={errors.products ?? null}
            width="text"
          >
            {(control) => (
              <MultiSelect<string>
                control={control}
                options={(products ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.code} · ${item.name}`,
                }))}
                values={productIds}
                onChange={setProductIds}
                invalid={errors.products !== undefined}
              />
            )}
          </Field>
          <Field
            name="calculator_currency"
            label={t("policies.sspCalculator.form.currency")}
            required
            error={errors.currency ?? null}
            width="period"
          >
            {(control) => (
              <Select<string>
                control={control}
                options={(currencies.data ?? []).map((item) => ({
                  value: item.currency_code,
                  label: item.currency_code,
                }))}
                value={currency}
                onChange={setCurrency}
                invalid={errors.currency !== undefined}
              />
            )}
          </Field>
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-1 text-body-sm font-medium text-fg-1">
            {t("policies.sspCalculator.form.source")}
          </legend>
          {SOURCES.map((value) => (
            <label key={value} className="flex items-center gap-2 text-body-sm text-fg-1">
              <input
                type="radio"
                name="calculator_source"
                value={value}
                checked={source === value}
                onChange={() => {
                  setSource(value);
                }}
                className="size-4"
              />
              {t(`policies.sspCalculator.source.${value}`)}
            </label>
          ))}
          {errors.source === undefined ? null : (
            <span className="text-body-sm text-negative-fg">{errors.source}</span>
          )}
        </fieldset>
        {source === "source_order_lines" ? (
          <Field
            name="calculator_pool"
            label={t("policies.sspCalculator.form.pool")}
            required
            help={
              canUpload
                ? t("policies.sspCalculator.form.poolHelp")
                : t("policies.sspCalculator.form.poolNoPermission")
            }
            error={errors.pool ?? null}
            width="text"
          >
            {(control) => (
              <input
                {...control}
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => {
                  setPool(event.target.files?.[0] ?? null);
                }}
                className="text-body-sm text-fg-2 file:me-3 file:h-[var(--control-h)] file:cursor-pointer file:rounded-md file:border file:border-control file:bg-surface file:px-3 file:text-body-sm file:font-medium file:text-fg-1 hover:file:bg-hover"
              />
            )}
          </Field>
        ) : null}
        <div className="flex flex-wrap items-start gap-4">
          {dateField("dateFrom", fromTyped, setFromTyped, setFrom, fromError, setFromError)}
          {dateField("dateTo", toTyped, setToTyped, setTo, toError, setToError)}
          <Field
            name="calculator_band"
            label={t("policies.sspCalculator.form.band")}
            required
            help={t("policies.sspCalculator.form.bandHelp")}
            error={errors.band ?? null}
            width="money"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                inputMode="decimal"
                value={band}
                onChange={(event) => {
                  setBand(event.target.value);
                }}
                className={`${controlClass(errors.band !== undefined)} num text-end`}
              />
            )}
          </Field>
        </div>
        <div>
          <Button variant="primary" type="submit" loading={pending}>
            {t("policies.sspCalculator.form.run")}
          </Button>
        </div>
      </form>
    </section>
  );
}

function RunsPanel({ products }: { readonly products: readonly Product[] | undefined }) {
  const headingId = useId();
  const runs = useQuery({
    queryKey: sspRunsKey(),
    queryFn: fetchSspRuns,
    refetchInterval: (query) =>
      query.state.data?.some((run) => isActiveRun(run.status)) === true
        ? RUN_POLL_INTERVAL_MS
        : false,
  });
  const codes = new Map((products ?? []).map((item) => [item.id, item.code]));
  const headers = [
    ["run", false],
    ["products", false],
    ["observations", true],
    ["status", false],
    ["created", false],
    ["draft", false],
  ] as const;

  let body: ReactNode;
  if (runs.error !== null) {
    body = (
      <Banner tone="negative" title={t("policies.sspCalculator.runs.loadError")} headingLevel={3}>
        {problemText(runs.error)}
      </Banner>
    );
  } else if (runs.data === undefined) {
    body = <Skeleton region={t("policies.sspCalculator.runs.title")} shape="rows" count={4} />;
  } else if (runs.data.length === 0) {
    body = (
      <EmptyState
        title={t("policies.sspCalculator.runs.empty.title")}
        description={t("policies.sspCalculator.runs.empty.description")}
        headingLevel={3}
      />
    );
  } else {
    body = (
      <table aria-labelledby={headingId} className="w-full border-collapse text-body-sm">
        <thead>
          <tr className="border-b border-default bg-subtle">
            {headers.map(([key, end]) => (
              <th
                key={key}
                scope="col"
                className={`px-3 py-2 font-medium text-fg-2 ${end ? "text-end" : "text-start"}`}
              >
                {t(`policies.sspCalculator.runs.column.${key}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.data.map((run: SspCalculatorRun) => {
            const spec = chipFor("E-67", run.status);
            const productCodes = run.parameters.product_ids.map((id) => codes.get(id) ?? NO_VALUE);
            return (
              <tr
                key={run.id}
                data-testid={`SF-13-row-run-${run.id}`}
                className="border-b border-hairline"
              >
                <th scope="row" className="px-3 py-2 text-start font-normal">
                  <Link to={sspRunRoute(run.id)} className="text-accent-fg hover:underline">
                    {run.name}
                  </Link>
                </th>
                <td className="px-3 py-2 font-mono text-mono-sm">
                  {formatList(productCodes, "unit")}
                </td>
                <td className="num px-3 py-2 text-end">
                  {run.observation_count === null
                    ? NO_VALUE
                    : formatNumber(run.observation_count, { kind: "count" })}
                </td>
                <td className="px-3 py-2">
                  {spec === null ? run.status : <StatusChip status={spec.status} />}
                </td>
                <td className="num px-3 py-2">{formatTimestamp(run.created_at)}</td>
                <td className="px-3 py-2">
                  {run.draft_ssp_book_version_id === null ? (
                    NO_VALUE
                  ) : (
                    <Link
                      to={sspBookVersionRoute(
                        run.parameters.ssp_book_id,
                        run.draft_ssp_book_version_id,
                      )}
                      className="text-accent-fg hover:underline"
                    >
                      {t("policies.sspCalculator.runs.openDraft")}
                    </Link>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="text-title-md text-fg-1">
        {t("policies.sspCalculator.runs.title")}
      </h2>
      {body}
    </section>
  );
}

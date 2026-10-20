import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { Combobox } from "../../components/form/Combobox";
import { Field } from "../../components/form/Field";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, useJob } from "../../lib/api/jobs";
import { customersKey, fetchCustomers } from "../../lib/api/queries/contracts";
import {
  type DealInput,
  fetchDealPreview,
  fetchDealProducts,
} from "../../lib/api/queries/deal-previews";
import { entitiesKey, fetchActiveEntities } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { DealResults } from "./DealResults";
import { SaveDealPreview } from "./SaveDealPreview";

const text = (key: string) => t(`deal.${key}`);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function DealPreviewPage() {
  const access = useAccess();
  return access.holdsAnywhere("scenario.use") ? (
    <Preview />
  ) : (
    <AccessLimited area={text("title")} permissions={["scenario.use"]} />
  );
}
function Preview() {
  const access = useAccess();
  const [search, setSearch] = useSearchParams();
  const jobParam = search.get("job");
  const savedId = search.get("preview");
  const job = useJob(jobParam && uuid.test(jobParam) ? jobParam : null);
  const resultId =
    job.data?.kind === "DEAL_PREVIEW" && job.data.state === "SUCCEEDED"
      ? job.data.result?.preview_id
      : null;
  const previewId = savedId ?? (typeof resultId === "string" ? resultId : null);
  const invalidLink =
    (jobParam !== null && !uuid.test(jobParam)) ||
    (savedId !== null && !uuid.test(savedId)) ||
    (job.data !== undefined && job.data.kind !== "DEAL_PREVIEW");
  const preview = useQuery({
    queryKey: queryKey("deal-preview", "tenant", { id: previewId }),
    queryFn: () => fetchDealPreview(previewId ?? ""),
    enabled: previewId !== null && uuid.test(previewId) && !invalidLink,
  });
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const customers = useQuery({ queryKey: customersKey(), queryFn: fetchCustomers });
  const choices = (entities.data ?? []).filter((entity) =>
    access.holdsForEvery("scenario.use", [entity]),
  );
  const [entityCode, setEntity] = useState("");
  const entity = choices.find((item) => item.code === entityCode);
  const [existing, setExisting] = useState(false);
  const [lines, setLines] = useState([0]);
  const [selectedProducts, setProducts] = useState<Record<number, string | null>>({});
  const products = useQuery({
    queryKey: queryKey("products", "tenant", { purpose: "deal-preview", active: true }),
    queryFn: fetchDealProducts,
    enabled: jobParam === null && savedId === null,
  });
  const productOptions = (products.data ?? []).map((product) => ({
    value: product.code,
    label: `${product.code} · ${product.name}`,
  }));
  const validProducts =
    !products.isError &&
    lines.every((id) => productOptions.some((option) => option.value === selectedProducts[id]));

  const nextLine = useRef(1);
  const [confirm, setConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({ method: "POST", path: "/api/v1/deal-previews" });
  const inFlight = useRef(false);
  const running =
    command.pending || (jobParam !== null && (job.data === undefined || !isTerminal(job.data)));
  const locked = command.pending || jobParam !== null || savedId !== null;
  async function submit(form: HTMLFormElement) {
    if (inFlight.current || locked || !entity || !validProducts) return;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const input: DealInput = {
      ...(existing ? { customer_id: value("customer") } : { customer_name: value("customer") }),
      entity_code: entity.code,
      start_date: value("start"),
      lines: lines.map((id) => ({
        product_code: selectedProducts[id] ?? "",
        quantity: value(`quantity-${id}`),
        term_months: value(`term-${id}`) === "" ? null : Number(value(`term-${id}`)),
        price: { amount: value(`price-${id}`), currency: entity.functional_currency },
        performing_entity_code: value(`performer-${id}`) || null,
      })),
    };
    inFlight.current = true;
    setNetworkError(false);
    try {
      const outcome = await command.submit({ input });
      if (outcome.kind === "accepted") setSearch({ job: outcome.jobId });
      setNetworkError(outcome.kind === "network-error");
    } finally {
      inFlight.current = false;
    }
  }
  return (
    <main className="flex flex-col gap-5 p-6">
      <h1 className="text-heading-lg">{text("title")}</h1>
      <Banner tone="info" title={text("notice")} />
      {invalidLink && <Banner tone="negative" title={text("invalidLink")} />}
      {(entities.isError || (existing && customers.isError)) && (
        <Banner
          tone="negative"
          title={text("loadError")}
          actions={
            <Button
              variant="link"
              onClick={() => {
                void entities.refetch();
                void customers.refetch();
              }}
            >
              {text("retry")}
            </Button>
          }
        />
      )}
      {!locked && products.isPending && <p role="status">{text("productsLoading")}</p>}
      {!locked && products.isError && (
        <Banner
          tone="negative"
          title={text("productsError")}
          actions={
            <Button
              variant="link"
              onClick={() => {
                void products.refetch();
              }}
            >
              {text("retry")}
            </Button>
          }
        />
      )}
      {!locked && products.data?.length === 0 && <p>{text("productsEmpty")}</p>}
      {jobParam === null && savedId === null && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit(event.currentTarget);
          }}
        >
          <fieldset disabled={command.pending} className="flex flex-col gap-3">
            <label>
              {text("existing")}{" "}
              <input
                type="checkbox"
                checked={existing}
                onChange={(e) => setExisting(e.target.checked)}
              />
            </label>
            <label>
              {text("customer")}
              {existing ? (
                <select name="customer" required className="ml-2 border p-2">
                  <option value="">{text("choose")}</option>
                  {customers.data?.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input name="customer" required maxLength={255} className="ml-2 border p-2" />
              )}
            </label>
            <label>
              {text("entity")}
              <select
                required
                className="ml-2 border p-2"
                value={entityCode}
                onChange={(e) => setEntity(e.target.value)}
              >
                <option value="">{text("choose")}</option>
                {choices.map((item) => (
                  <option key={item.id} value={item.code}>
                    {item.code} · {item.functional_currency}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {text("start")} <input name="start" type="date" required className="border p-2" />
            </label>
            {lines.map((id, index) => (
              <fieldset key={id} className="flex flex-wrap gap-3 rounded border p-3">
                <legend>{t("deal.line", { number: index + 1 })}</legend>
                <Field name={`product-${id}`} label={text("product")} required width="text">
                  {(control) => (
                    <Combobox
                      control={control}
                      options={productOptions}
                      value={selectedProducts[id] ?? null}
                      onChange={(value) => setProducts((current) => ({ ...current, [id]: value }))}
                    />
                  )}
                </Field>
                <label>
                  {text("quantity")}{" "}
                  <input
                    name={`quantity-${id}`}
                    required
                    defaultValue="1"
                    inputMode="decimal"
                    pattern="[0-9]+(\.[0-9]+)?"
                    className="border p-2"
                  />
                </label>
                <label>
                  {text("term")}{" "}
                  <input
                    name={`term-${id}`}
                    type="number"
                    min="1"
                    max="1200"
                    step="1"
                    className="border p-2"
                  />
                </label>
                <label>
                  {text("price")} {entity?.functional_currency}
                  <input
                    name={`price-${id}`}
                    required
                    inputMode="decimal"
                    pattern="[0-9]+(\.[0-9]{1,4})?"
                    className="border p-2"
                  />
                </label>
                <label>
                  {text("performer")}{" "}
                  <select name={`performer-${id}`} className="border p-2">
                    <option value="">{text("sameEntity")}</option>
                    {choices.map((item) => (
                      <option key={item.id} value={item.code}>
                        {item.code}
                      </option>
                    ))}
                  </select>
                </label>
                <Button
                  variant="secondary"
                  disabledReason={lines.length === 1 ? text("oneLine") : undefined}
                  onClick={() => setLines((current) => current.filter((line) => line !== id))}
                >
                  {text("remove")}
                </Button>
              </fieldset>
            ))}
            <Button
              variant="secondary"
              disabledReason={lines.length >= 500 ? text("lineLimit") : undefined}
              onClick={() => setLines((current) => [...current, nextLine.current++])}
            >
              {text("add")}
            </Button>
            <Button
              type="submit"
              loading={command.pending}
              disabledReason={
                !entity ? text("chooseEntity") : !validProducts ? text("chooseProducts") : undefined
              }
            >
              {text("run")}
            </Button>
          </fieldset>
        </form>
      )}
      <RefusalBanner problem={command.problem} />
      {networkError && <Banner tone="negative" title={text("networkError")} />}
      {job.isError && (
        <Banner
          tone="negative"
          title={text("jobError")}
          actions={
            <Button
              onClick={() => {
                void job.refetch();
              }}
            >
              {text("retry")}
            </Button>
          }
        />
      )}
      {job.data?.kind === "DEAL_PREVIEW" && (
        <JobProgress job={job.data} label={text("title")} unit={text("lines")} />
      )}
      {!invalidLink && previewId && preview.isPending && <p role="status">{text("loading")}</p>}
      {preview.isError && (
        <Banner
          tone="negative"
          title={text("loadError")}
          actions={
            <Button
              onClick={() => {
                void preview.refetch();
              }}
            >
              {text("retry")}
            </Button>
          }
        />
      )}
      {!invalidLink && preview.data && <DealResults preview={preview.data} />}
      {!invalidLink && preview.data && (
        <SaveDealPreview key={preview.data.id} preview={preview.data} onBusy={setSaving} />
      )}
      {locked && (
        <Button
          variant="secondary"
          disabledReason={saving || (running && !invalidLink) ? text("wait") : undefined}
          onClick={() => setConfirm(true)}
        >
          {text("restart")}
        </Button>
      )}
      <Modal
        open={confirm}
        variant="confirmation"
        title={text("restart")}
        description={text("discard")}
        onClose={() => setConfirm(false)}
        primaryAction={{
          label: text("restart"),
          onAction: () => {
            setSearch({});
            command.reset();
            setLines([0]);
            setProducts({});
            setConfirm(false);
            setNetworkError(false);
          },
        }}
      />
    </main>
  );
}

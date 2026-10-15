import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  type Contract,
  CONTRACT_RECORD_KEYS,
  contractIfMatch,
} from "../../lib/api/queries/contracts";
import { contractEstimatesKey, fetchEstimates } from "../../lib/api/queries/estimates";
import type { Obligation } from "../../lib/api/queries/obligations";
import type { components } from "../../lib/api/schema";
import { formatDate, formatMoney, NO_VALUE, parseDateInput } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { EvidenceField, SelectField, TextField, uploadEvidence } from "./drawers/common";

type Terms = components["schemas"]["MaterialRightCreateIn"];
type Mode = "create" | "expire";
const TYPES: readonly Terms["option_type"][] = [
  "DISCOUNT_VOUCHER",
  "LOYALTY_POINTS",
  "RENEWAL_OPTION",
  "TIERED_DISCOUNT",
  "OTHER",
];
const METHODS: readonly Terms["ssp_method"][] = [
  "ENTERED_AMOUNT",
  "DISCOUNT_X_LIKELIHOOD",
  "RENEWAL_ALTERNATIVE",
];
const message = (key: string) => t(`contracts.option.${key}`);

export function MaterialRightPanel({
  contract,
  obligation,
  canCreate,
  canExpire,
}: {
  readonly contract: Contract;
  readonly obligation: Obligation;
  readonly canCreate: boolean;
  readonly canExpire: boolean;
}) {
  const [mode, setMode] = useState<Mode | null>(null);
  const right = obligation.material_right;
  const creation = canCreate && contract.status === "DRAFT" && right === null;
  const expiry = canExpire && contract.status === "ACTIVE" && right?.status === "OPEN";
  if (obligation.obligation_kind !== "MATERIAL_RIGHT" && right === null) return null;
  const rows =
    right === null
      ? []
      : [
          [message("type"), message(`type.${right.option_type}`)],
          [
            message("method"),
            right.ssp_method === null ? NO_VALUE : message(`method.${right.ssp_method}`),
          ],
          [message("status"), message(`status.${right.status}`)],
          [
            message("statusDate"),
            right.status_date === null ? NO_VALUE : formatDate(right.status_date),
          ],
          [
            message("expiryDate"),
            right.expiry_date === null ? NO_VALUE : formatDate(right.expiry_date),
          ],
          [message("ratio"), right.incremental_discount_ratio ?? NO_VALUE],
          [
            message("enteredAmount"),
            right.entered_ssp_amount == null
              ? NO_VALUE
              : formatMoney(right.entered_ssp_amount, obligation.currency),
          ],
          [
            message("amount"),
            right.expected_purchase_amount === null
              ? NO_VALUE
              : formatMoney(right.expected_purchase_amount, obligation.currency),
          ],
        ];
  return (
    <section
      className="flex flex-col gap-3 border-b border-hairline py-3"
      aria-label={message("title")}
    >
      <h3 className="text-body font-medium">{message("title")}</h3>
      {right === null ? (
        <p className="text-body-sm text-fg-3">{message("missing")}</p>
      ) : (
        <dl>
          {rows.map(([label, value]) => (
            <div key={label} className="grid grid-cols-2 gap-3 text-body-sm">
              <dt className="text-fg-3">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {right?.likelihood_estimate_id ? (
        <Link
          className="text-body-sm underline"
          to={`/contracts/${contract.id}/estimates/${right.likelihood_estimate_id}`}
        >
          {message("openEstimate")}
        </Link>
      ) : null}
      {creation ? (
        <Button size="sm" onClick={() => setMode("create")}>
          {message("create")}
        </Button>
      ) : null}
      {expiry ? (
        <Button size="sm" onClick={() => setMode("expire")}>
          {message("expire")}
        </Button>
      ) : null}
      {mode !== null && ((mode === "create" && creation) || (mode === "expire" && expiry)) ? (
        <MaterialRightDrawer
          key={`${obligation.id}:${mode}`}
          contract={contract}
          obligation={obligation}
          mode={mode}
          onClose={() => setMode(null)}
        />
      ) : null}
    </section>
  );
}

export function MaterialRightDrawer({
  contract,
  obligation,
  mode,
  onClose,
}: {
  readonly contract: Contract;
  readonly obligation: Obligation;
  readonly mode: Mode;
  readonly onClose: () => void;
}) {
  const form = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const [type, setType] = useState<Terms["option_type"]>("DISCOUNT_VOUCHER");
  const [method, setMethod] = useState<Terms["ssp_method"]>("ENTERED_AMOUNT");
  const [ratio, setRatio] = useState("");
  const [amount, setAmount] = useState("");
  const [enteredAmount, setEnteredAmount] = useState("");
  const [estimate, setEstimate] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [comment, setComment] = useState("");
  const [available, setAvailable] = useState("false");
  const [files, setFiles] = useState<readonly File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProblem, setUploadProblem] = useState<ApiProblem | null>(null);
  const [attempted, setAttempted] = useState(false);
  const discount = mode === "create" && method === "DISCOUNT_X_LIKELIHOOD";
  const estimates = useQuery({
    queryKey: contractEstimatesKey(contract.id),
    queryFn: () => fetchEstimates(contract.id),
    enabled: discount,
  });
  const options = (estimates.data ?? [])
    .filter(
      (item) =>
        item.estimate_kind === "EXERCISE_LIKELIHOOD" &&
        item.current_version !== null &&
        (item.obligation_id === null || item.obligation_id === obligation.id),
    )
    .map((item) => ({ value: item.id, label: item.element_code }));
  const command = useCommand({
    method: "POST",
    path: `/api/v1/obligations/${obligation.id}/${mode === "create" ? "material-right" : "expire-material-right"}`,
    ifMatch: contractIfMatch(contract.head_stream_version),
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const parsed = parseDateInput(date);
  const invalidDate = date.trim() !== "" && !parsed.ok;
  const required = (value: string | null) =>
    attempted && (value === null || value.trim() === "") ? message("required") : null;
  async function submit() {
    if (command.pending || uploading || command.jobId !== null) return;
    setAttempted(true);
    if (
      invalidDate ||
      (mode === "expire" && (date.trim() === "" || comment.trim() === "")) ||
      (discount &&
        (ratio.trim() === "" ||
          amount.trim() === "" ||
          !options.some((item) => item.value === estimate)))
    )
      return;
    const effective = parsed.ok ? parsed.value : null;
    if (mode === "expire" && effective === null) return;
    setUploadProblem(null);
    setUploading(true);
    try {
      const body: Terms | components["schemas"]["MaterialRightExpireIn"] =
        mode === "create"
          ? {
              option_type: type,
              ssp_method: method,
              expiry_date: effective,
              is_discount_available_without_contract: available === "true",
              ...(method === "ENTERED_AMOUNT" && enteredAmount.trim() !== ""
                ? {
                    entered_ssp_amount: {
                      amount: enteredAmount.trim(),
                      currency: obligation.currency,
                    },
                  }
                : {}),
              ...(discount
                ? {
                    incremental_discount_ratio: ratio.trim(),
                    expected_purchase_amount: {
                      amount: amount.trim(),
                      currency: obligation.currency,
                    },
                    likelihood_estimate_id: estimate,
                  }
                : {}),
            }
          : {
              effective_date: effective ?? "",
              comment: comment.trim(),
              evidence_file_ids: await uploadEvidence(keys, files),
            };
      const result = await command.submit(body);
      if (result.kind === "succeeded" || result.kind === "accepted") {
        toast.show({
          tone: "positive",
          message: message(result.kind === "accepted" ? "queued" : "saved"),
        });
        if (result.kind === "succeeded") onClose();
      }
    } catch (error) {
      if (error instanceof ApiProblem) setUploadProblem(error);
      else noAnswer();
    } finally {
      setUploading(false);
    }
  }
  return (
    <Drawer
      open
      title={message(mode)}
      initialFocus="field"
      dirty={command.jobId === null}
      submitting={command.pending || uploading}
      banner={
        <RefusalBanner problem={uploadProblem ?? command.problem} conflict={command.banner} />
      }
      primaryAction={
        command.jobId === null
          ? { label: message(mode === "create" ? "save" : "expire"), form }
          : undefined
      }
      onClose={onClose}
    >
      {command.jobId !== null ? (
        command.job === undefined ? (
          <p>{message("queued")}</p>
        ) : ["FAILED", "CANCELLED", "SUCCEEDED_WITH_EXCEPTIONS"].includes(command.job.state) ? (
          <Banner tone="negative" title={message("computationFailed")}>
            <p>{message("recordedDespiteFailure")}</p>
            <p>{command.job.problem?.title}</p>
            <p>{command.job.id}</p>
          </Banner>
        ) : (
          <JobProgress
            label={message("computation")}
            unit={message("contracts")}
            job={command.job}
            summary={<p>{message("computed")}</p>}
          />
        )
      ) : (
        <form
          id={form}
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <p className="text-body-sm text-fg-3">
            {message(mode === "create" ? "entryHelp" : "expiryHelp")}
          </p>
          {mode === "create" ? (
            <>
              <SelectField
                name="option-type"
                label={message("type")}
                value={type}
                options={(method === "RENEWAL_ALTERNATIVE"
                  ? ["RENEWAL_OPTION" as const]
                  : TYPES
                ).map((value) => ({ value, label: message(`type.${value}`) }))}
                onChange={setType}
              />
              <SelectField
                name="option-method"
                label={message("method")}
                value={method}
                options={METHODS.map((value) => ({ value, label: message(`method.${value}`) }))}
                onChange={(value) => {
                  setMethod(value);
                  if (value === "RENEWAL_ALTERNATIVE") setType("RENEWAL_OPTION");
                }}
              />
              <SelectField
                name="option-available"
                label={message("available")}
                value={available}
                options={[
                  { value: "false", label: message("no") },
                  { value: "true", label: message("yes") },
                ]}
                onChange={setAvailable}
              />
              {method === "ENTERED_AMOUNT" ? (
                <TextField
                  name="option-entered-amount"
                  label={message("enteredAmount")}
                  help={`${message("enteredAmountHelp")} ${obligation.currency}`}
                  value={enteredAmount}
                  onChange={setEnteredAmount}
                  inputMode="decimal"
                />
              ) : null}
              {discount ? (
                <>
                  <TextField
                    name="option-ratio"
                    label={message("ratio")}
                    help={message("ratioHelp")}
                    value={ratio}
                    onChange={setRatio}
                    inputMode="decimal"
                    required
                    error={required(ratio)}
                  />
                  <TextField
                    name="option-amount"
                    label={message("amount")}
                    help={obligation.currency}
                    value={amount}
                    onChange={setAmount}
                    inputMode="decimal"
                    required
                    error={required(amount)}
                  />
                  <SelectField
                    name="option-estimate"
                    label={message("estimate")}
                    value={estimate}
                    options={options}
                    onChange={setEstimate}
                    error={required(estimate)}
                  />
                  <p className="text-body-sm text-fg-3">{message("estimateHelp")}</p>
                  {estimates.isError ? (
                    <Button variant="link" onClick={() => void estimates.refetch()}>
                      {message("retryEstimates")}
                    </Button>
                  ) : null}
                </>
              ) : null}
            </>
          ) : null}
          <Field
            name="option-date"
            label={message(mode === "create" ? "expiryDate" : "effectiveDate")}
            optional={mode === "create"}
            error={
              attempted && invalidDate
                ? message("invalidDate")
                : mode === "expire"
                  ? required(date)
                  : null
            }
          >
            {(control) => <DateInput control={control} value={date} onChange={setDate} />}
          </Field>
          {mode === "expire" ? (
            <>
              <TextField
                name="option-comment"
                label={message("comment")}
                value={comment}
                onChange={setComment}
                multiline
                required
                error={required(comment)}
              />
              <EvidenceField
                name="option-evidence"
                label={message("evidence")}
                files={files}
                onChange={setFiles}
              />
            </>
          ) : null}
        </form>
      )}
    </Drawer>
  );
}

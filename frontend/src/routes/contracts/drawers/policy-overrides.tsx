// Validated POL-122/POL-047 authoring. Saving and submission are separate durable intents.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { Skeleton } from "../../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../../components/feedback/Toast";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommand } from "../../../lib/api/commands";
import {
  type Contract,
  type PolicyOverride,
  CONTRACT_RECORD_KEYS,
  POLICY_OVERRIDES_PATH,
  contractOverridesKey,
  fetchContractOverrides,
} from "../../../lib/api/queries/contracts";
import { placeProblem } from "../../../lib/api/refusals";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { t } from "../../../lib/i18n/t";
import { SelectField, TextField } from "./common";

const RIGHT = "balance.right_to_consideration";
const RATE = "sfc.discount_rate_basis";
const MEMBERS = {
  policy: ["policy_key"],
  obligation: ["obligation_key"],
  value: ["value"],
  rationale: ["rationale"],
} as const;
const key = (name: string) => `contracts.policyOverrides.${name}`;

function overrideValue(row: PolicyOverride): string {
  if (row.policy_key === RIGHT && (row.value === "CONDITIONAL" || row.value === "UNCONDITIONAL")) {
    return t(key(row.value));
  }
  if (row.policy_key === RATE && row.value !== null && typeof row.value === "object") {
    const value = row.value as Record<string, unknown>;
    const basis =
      value.basis === "ENTITY_BORROWING_RATE" ? "ENTITY_BORROWING_RATE" : "CUSTOMER_CREDIT_RATE";
    const compounding = value.compounding === "ANNUAL" ? "ANNUAL" : "MONTHLY";
    return t(key("rateValue"), {
      rate: String(value.annual_rate),
      basis: t(key(basis)),
      compounding: t(key(compounding)),
    });
  }
  return JSON.stringify(row.value);
}

function OverrideRecord({
  row,
  canAuthor,
  onSubmitting,
}: {
  readonly onSubmitting: (pending: boolean) => void;
  readonly row: PolicyOverride;
  readonly canAuthor: boolean;
}) {
  const noAnswer = useNoAnswer();
  const command = useCommand({
    method: "POST",
    path: `${POLICY_OVERRIDES_PATH}/${row.id}/submit`,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const submit = async () => {
    onSubmitting(true);
    try {
      const outcome = await command.submit({});
      if (outcome.kind === "network-error") noAnswer();
    } finally {
      onSubmitting(false);
    }
  };
  const known = row.policy_key === RIGHT || row.policy_key === RATE;
  return (
    <li className="flex flex-col gap-2 rounded-md border border-subtle p-3">
      <p className="text-body font-medium text-fg-1">
        {known ? t(key(row.policy_key === RIGHT ? "right" : "rate")) : row.policy_key}
        {row.obligation_key === null ? "" : ` · ${row.obligation_key}`}
      </p>
      <p className="text-body-sm text-fg-2">{t(key(`status.${row.status}`))}</p>
      <p className="break-words text-body-sm text-fg-2">{overrideValue(row)}</p>
      <p className="text-body-sm text-fg-2">{row.rationale}</p>
      {row.approval_request_id === null ? null : (
        <Link
          className="text-body-sm text-accent-fg underline"
          to={`/approvals/requests/${row.approval_request_id}`}
        >
          {t(key("viewRequest"))}
        </Link>
      )}
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      {row.status === "DRAFT" && canAuthor && known ? (
        <Button loading={command.pending} onClick={() => void submit()}>
          {t(key("submit"))}
        </Button>
      ) : null}
    </li>
  );
}

export function PolicyOverridesDrawer({
  contract,
  obligations,
  canAuthor,
  onClose,
}: {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly canAuthor: boolean;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const [policy, setPolicy] = useState(RIGHT);
  const [obligation, setObligation] = useState<string | null>(null);
  const [right, setRight] = useState("CONDITIONAL");
  const [basis, setBasis] = useState("CUSTOMER_CREDIT_RATE");
  const [annualRate, setAnnualRate] = useState("");
  const [compounding, setCompounding] = useState("MONTHLY");
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [submissions, setSubmissions] = useState(0);
  const records = useQuery({
    queryKey: contractOverridesKey(contract.id),
    queryFn: () => fetchContractOverrides(contract.id),
  });
  const command = useCommand<PolicyOverride>({
    method: "POST",
    path: POLICY_OVERRIDES_PATH,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = placeProblem(command.problem, MEMBERS);
  const required = t(key("required"));
  const save = async () => {
    setAttempted(true);
    if (
      !rationale.trim() ||
      (policy === RIGHT && obligation === null) ||
      (policy === RATE && !annualRate.trim())
    )
      return;
    const outcome = await command.submit({
      contract_id: contract.id,
      policy_key: policy,
      obligation_key: policy === RIGHT ? obligation : null,
      value: policy === RIGHT ? right : { basis, annual_rate: annualRate.trim(), compounding },
      rationale: rationale.trim(),
    });
    if (outcome.kind === "succeeded") {
      setRationale("");
      setAnnualRate("");
      setObligation(null);
      setAttempted(false);
      toast.show({ tone: "positive", message: t(key("saved")) });
    } else if (outcome.kind === "network-error") noAnswer();
  };
  const options = (names: readonly string[]) =>
    names.map((value) => ({ value, label: t(key(value)) }));
  return (
    <Drawer
      open
      title={t(key("title"))}
      subtitle={contract.external_id}
      dirty={rationale !== "" || annualRate !== ""}
      submitting={command.pending || submissions > 0}
      onClose={onClose}
      initialFocus={canAuthor ? "field" : "title"}
      banner={<RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />}
      primaryAction={canAuthor ? { label: t(key("save")), form: formId } : undefined}
    >
      <div className="flex flex-col gap-4">
        <p className="text-body-sm text-fg-2">{t(key("help"))}</p>
        {canAuthor ? (
          <form
            id={formId}
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <SelectField
              name="override-policy"
              label={t(key("policy"))}
              value={policy}
              onChange={setPolicy}
              error={placed.fields.policy}
              options={[
                { value: RIGHT, label: t(key("right")) },
                { value: RATE, label: t(key("rate")) },
              ]}
            />
            {policy === RIGHT ? (
              <>
                <SelectField
                  name="override-obligation"
                  label={t("contracts.drawer.obligation")}
                  value={obligation}
                  onChange={setObligation}
                  options={obligations.map((item) => ({
                    value: item.obligation_key,
                    label: `${item.obligation_key} · ${item.product.name}`,
                  }))}
                  error={attempted && obligation === null ? required : placed.fields.obligation}
                />
                <SelectField
                  name="override-right"
                  label={t(key("right"))}
                  value={right}
                  onChange={setRight}
                  options={options(["CONDITIONAL", "UNCONDITIONAL"])}
                  error={placed.fields.value}
                />
              </>
            ) : (
              <>
                <SelectField
                  name="override-basis"
                  label={t(key("basis"))}
                  value={basis}
                  onChange={setBasis}
                  options={options(["CUSTOMER_CREDIT_RATE", "ENTITY_BORROWING_RATE"])}
                />
                <TextField
                  name="override-rate"
                  label={t(key("annualRate"))}
                  value={annualRate}
                  onChange={setAnnualRate}
                  inputMode="decimal"
                  required
                  help={t(key("rateHelp"))}
                  error={attempted && !annualRate.trim() ? required : placed.fields.value}
                />
                <SelectField
                  name="override-compounding"
                  label={t(key("compounding"))}
                  value={compounding}
                  onChange={setCompounding}
                  options={options(["MONTHLY", "ANNUAL"])}
                />
              </>
            )}
            <TextField
              name="override-rationale"
              label={t(key("rationale"))}
              value={rationale}
              onChange={setRationale}
              required
              multiline
              error={attempted && !rationale.trim() ? required : placed.fields.rationale}
            />
          </form>
        ) : null}
        <h3 className="text-body font-medium text-fg-1">{t(key("records"))}</h3>
        {records.isPending ? (
          <Skeleton region={t(key("records"))} />
        ) : records.isError ? (
          <div>
            <p className="text-body-sm text-negative-fg">{t(key("readFailed"))}</p>
            <Button onClick={() => void records.refetch()}>{t(key("retry"))}</Button>
          </div>
        ) : records.data.length === 0 ? (
          <p className="text-body-sm text-fg-3">{t(key("empty"))}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {records.data.map((row) => (
              <OverrideRecord
                key={row.id}
                row={row}
                canAuthor={canAuthor}
                onSubmitting={(pending) => setSubmissions((count) => count + (pending ? 1 : -1))}
              />
            ))}
          </ul>
        )}
      </div>
    </Drawer>
  );
}

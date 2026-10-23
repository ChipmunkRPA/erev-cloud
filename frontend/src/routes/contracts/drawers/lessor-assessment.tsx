import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";

import { Banner } from "../../../components/feedback/Banner";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useToast } from "../../../components/feedback/Toast";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommandKeys } from "../../../lib/api/commands";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  type Contract,
  contractJudgementsKey,
  fetchContractJudgements,
  JUDGEMENTS_PATH,
  sendCommand,
  sendStep,
} from "../../../lib/api/queries/contracts";
import { judgementStatusLabel } from "../../../lib/api/queries/judgements";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { t } from "../../../lib/i18n/t";
import { RadioGroup, SelectField, TextField, useRefreshRecord } from "./common";

type Answer = "yes" | "no";

export function LessorAssessmentDrawer({
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
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const toast = useToast();
  const history = useQuery({
    queryKey: contractJudgementsKey(contract.id),
    queryFn: () => fetchContractJudgements(contract.id),
  });
  const records = (history.data ?? []).filter(
    (record) =>
      record.topic === "OTHER" &&
      typeof record.questionnaire?.lessor_lease_obligation_key === "string",
  );
  const [component, setComponent] = useState<string | null>(null);
  const [lease, setLease] = useState<string | null>(null);
  const [assetClass, setAssetClass] = useState("");
  const [pattern, setPattern] = useState<Answer | null>(null);
  const [operating, setOperating] = useState<Answer | null>(null);
  const [predominant, setPredominant] = useState<Answer | null>(null);
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false);
  const [frozen, setFrozen] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [networkError, setNetworkError] = useState(false);
  // Retained assessments keep original keys selectable after their components have merged.
  const choices = (isLease: boolean) => {
    const values = new Set(
      obligations
        .filter((item) =>
          isLease ? item.scope_flag === "LEASE_842" : item.scope_flag === "IN_SCOPE_606",
        )
        .map((item) => item.obligation_key),
    );
    for (const record of records) {
      const value =
        record.questionnaire?.[isLease ? "lessor_lease_obligation_key" : "obligation_key"];
      if (typeof value === "string") values.add(value);
    }
    return [...values].sort().map((value) => ({ value, label: value }));
  };
  const required = t("contracts.drawer.choose");
  const options = [
    { value: "yes" as const, label: t("contracts.lessor.yes") },
    { value: "no" as const, label: t("contracts.lessor.no") },
  ];
  const submit = async () => {
    if (pending || !canAuthor) return;
    setAttempted(true);
    if (
      component === null ||
      lease === null ||
      component === lease ||
      assetClass.trim() === "" ||
      rationale.trim() === "" ||
      pattern === null ||
      operating === null ||
      predominant === null
    )
      return;
    setPending(true);
    setFrozen(true);
    setProblem(null);
    setNetworkError(false);
    try {
      let id = createdId;
      if (id === null) {
        const created = await sendStep<{ readonly id: string }>(keys, "POST", JUDGEMENTS_PATH, {
          topic: "OTHER",
          subject_type: "contract",
          subject_id: contract.id,
          book: "ASC606",
          conclusion: t(
            predominant === "yes"
              ? "contracts.lessor.nonleaseConclusion"
              : "contracts.lessor.leaseConclusion",
          ),
          rationale: rationale.trim(),
          codification_refs: ["842-10-15-42A", "842-10-15-42B"],
          questionnaire: {
            obligation_key: component,
            lessor_lease_obligation_key: lease,
            lessor_asset_class: assetClass.trim(),
            lessor_same_transfer_pattern: pattern === "yes",
            lessor_operating_lease: operating === "yes",
            lessor_nonlease_predominates: predominant === "yes",
          },
        });
        if (!created.ok) {
          setProblem(created.problem);
          if (created.problem.status < 500 && created.problem.status !== 409) setFrozen(false);
          return;
        }
        id = created.data.id;
        setCreatedId(id);
      }
      const submitted = await sendCommand(keys, "POST", `${JUDGEMENTS_PATH}/${id}/submit`, {});
      if (!submitted.ok) {
        setProblem(submitted.problem);
        return;
      }
      keys.clear();
      await refresh();
      toast.show({ tone: "positive", message: t("contracts.lessor.saved") });
      onClose();
    } catch {
      setNetworkError(true);
    } finally {
      setPending(false);
    }
  };
  return (
    <Drawer
      open
      title={t("contracts.lessor.title")}
      subtitle={contract.external_id}
      initialFocus={canAuthor ? "field" : "title"}
      dirty={component !== null || rationale !== ""}
      submitting={pending}
      onClose={onClose}
      primaryAction={canAuthor ? { label: t("contracts.lessor.submit"), form: formId } : undefined}
      banner={
        <>
          <RefusalBanner problem={problem} />
          {networkError ? <Banner tone="negative" title={t("contracts.lessor.network")} /> : null}
        </>
      }
    >
      <Banner tone="info" announce="static" title={t("contracts.lessor.info")} />
      <section className="my-4 flex flex-col gap-2" aria-label={t("contracts.lessor.history")}>
        <h3>{t("contracts.lessor.history")}</h3>
        {history.isError ? (
          <Banner tone="negative" title={t("contracts.lessor.historyError")} />
        ) : null}
        {!history.isPending && !history.isError && records.length === 0 ? (
          <p>{t("contracts.lessor.empty")}</p>
        ) : null}
        {records.map((record) => (
          <details key={record.id}>
            <summary>
              {record.judgement_no} · {judgementStatusLabel(record.status)}
            </summary>
            <p>
              {String(record.questionnaire?.obligation_key)} →{" "}
              {String(record.questionnaire?.lessor_lease_obligation_key)}
            </p>
            <p>{String(record.questionnaire?.lessor_asset_class ?? "")}</p>
            {(["pattern", "operating", "predominant"] as const).map((field) => {
              const member = {
                pattern: "lessor_same_transfer_pattern",
                operating: "lessor_operating_lease",
                predominant: "lessor_nonlease_predominates",
              }[field];
              const answer = record.questionnaire?.[member];
              return (
                <p key={field}>
                  {t(`contracts.lessor.${field}`)}:{" "}
                  {answer === true
                    ? t("contracts.lessor.yes")
                    : answer === false
                      ? t("contracts.lessor.no")
                      : "—"}
                </p>
              );
            })}
            <p>{record.conclusion}</p>
            <p>{record.rationale}</p>
          </details>
        ))}
      </section>
      {canAuthor ? (
        <form
          id={formId}
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {frozen ? <Banner tone="info" title={t("contracts.lessor.retry")} /> : null}
          <fieldset
            disabled={pending || frozen || history.isPending || history.isError}
            className="flex flex-col gap-4"
          >
            <SelectField
              name="lessor-component"
              label={t("contracts.lessor.component")}
              options={choices(false)}
              value={component}
              onChange={setComponent}
              error={attempted && component === null ? required : undefined}
            />
            <SelectField
              name="lessor-lease"
              label={t("contracts.lessor.lease")}
              options={choices(true)}
              value={lease}
              onChange={setLease}
              error={attempted && (lease === null || lease === component) ? required : undefined}
            />
            <TextField
              name="lessor-asset"
              label={t("contracts.lessor.assetClass")}
              required
              value={assetClass}
              onChange={setAssetClass}
              error={attempted && assetClass.trim() === "" ? required : undefined}
            />
            <RadioGroup
              legend={t("contracts.lessor.pattern")}
              options={options}
              value={pattern}
              onChange={setPattern}
              error={attempted && pattern === null ? required : undefined}
            />
            <RadioGroup
              legend={t("contracts.lessor.operating")}
              options={options}
              value={operating}
              onChange={setOperating}
              error={attempted && operating === null ? required : undefined}
            />
            <RadioGroup
              legend={t("contracts.lessor.predominant")}
              options={options}
              value={predominant}
              onChange={setPredominant}
              error={attempted && predominant === null ? required : undefined}
            />
            <TextField
              name="lessor-rationale"
              label={t("contracts.lessor.rationale")}
              required
              multiline
              value={rationale}
              onChange={setRationale}
              error={attempted && rationale.trim() === "" ? required : undefined}
            />
          </fieldset>
        </form>
      ) : null}
    </Drawer>
  );
}

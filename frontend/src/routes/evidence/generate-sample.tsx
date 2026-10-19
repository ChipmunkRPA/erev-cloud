import { useId, useState } from "react";
import { Link, useNavigate } from "react-router";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { DateInput } from "../../components/form/DateInput";
import { Field, controlClass } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  EVIDENCE_PACKS_PATH,
  EVIDENCE_PACKS_ROUTE,
  mayCreateSampleEvidence,
} from "../../lib/api/queries/evidence-packs";
import { useFieldRefusals } from "../../lib/api/refusals";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { parseDateInput, utcDateOf } from "../../lib/format";
import { t } from "../../lib/i18n/t";

const MEMBERS = { contracts: ["contract_external_ids"], date: ["as_of"] } as const;

export function GenerateSamplePack() {
  const access = useAccess();
  const navigate = useNavigate();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [contracts, setContracts] = useState("");
  const [date, setDate] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({
    method: "POST",
    path: EVIDENCE_PACKS_PATH,
    invalidates: [queryKey("evidence-packs", "tenant")],
  });
  const refusals = useFieldRefusals(command.problem, MEMBERS);
  const resultId = command.job?.result?.href?.match(
    /^\/api\/v1\/evidence-packs\/([0-9a-f-]{36})$/i,
  )?.[1];
  // Preserve exact external identifiers, including punctuation; never split on commas or
  // silently normalize identifiers. Blank lines are separators, not selected contracts.
  const selected = contracts.split(/\r?\n/).filter((line) => line !== "");
  const selectionError =
    selected.length < 1 || selected.length > 50
      ? t("evidence.sample.countError")
      : selected.some((line) => line.trim() === "")
        ? t("evidence.sample.whitespaceError")
        : new Set(selected).size !== selected.length
          ? t("evidence.sample.duplicateError")
          : null;
  const parsed = parseDateInput(date);
  const dateError = !parsed.ok
    ? t("evidence.sample.dateError")
    : parsed.value > utcDateOf(Date.now())
      ? t("evidence.sample.futureError")
      : null;
  const body: components["schemas"]["ContractSamplePackCreateIn"] | null =
    selectionError === null && dateError === null && parsed.ok
      ? { kind: "CONTRACT_SAMPLE", contract_external_ids: selected, as_of: parsed.value }
      : null;
  const busy = command.pending || accepted;
  async function submit() {
    setAttempted(true);
    if (body === null || busy || !mayCreateSampleEvidence(access)) return;
    setNetworkError(false);
    const outcome = await command.submit(body);
    if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      setAccepted(true);
      const id = outcome.response.headers.get("X-Erev-Evidence-Pack-Id");
      if (id) void navigate(`${EVIDENCE_PACKS_ROUTE}/${encodeURIComponent(id)}`);
    } else if (outcome.kind === "network-error") setNetworkError(true);
  }
  if (!mayCreateSampleEvidence(access)) return null;
  return (
    <>
      <Button onClick={() => setOpen(true)}>{t("evidence.sample.open")}</Button>
      <Modal
        open={open}
        variant="form"
        title={t("evidence.sample.title")}
        description={t("evidence.sample.description")}
        onClose={() => {
          if (!command.pending) setOpen(false);
        }}
        submitting={command.pending}
        testId="SF-09-dialog-generate-sample"
        primaryAction={{
          label: t("evidence.generate.submit"),
          form: formId,
          disabledReason: accepted ? t("evidence.sample.accepted") : undefined,
        }}
      >
        <form
          id={formId}
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
          {networkError ? (
            <Banner tone="negative" title={t("evidence.generate.networkError")} />
          ) : null}
          {accepted ? <Banner tone="info" title={t("evidence.sample.accepted")} /> : null}
          {accepted && command.job ? (
            <JobProgress
              label={t("evidence.sample.title")}
              job={command.job}
              unit={t("evidence.sample.files")}
              summary={
                resultId ? (
                  <Link className="underline" to={`${EVIDENCE_PACKS_ROUTE}/${resultId}`}>
                    {t("evidence.sample.openResult")}
                  </Link>
                ) : undefined
              }
              onRetry={() => {
                command.reset();
                setAccepted(false);
              }}
            />
          ) : null}
          <fieldset disabled={busy} className="space-y-4">
            <Field
              name="contract_external_ids"
              label={t("evidence.sample.contracts")}
              required
              help={t("evidence.sample.contractHelp")}
              error={attempted ? (selectionError ?? refusals.fields.contracts) : undefined}
            >
              {(control) => (
                <textarea
                  {...control}
                  value={contracts}
                  rows={6}
                  className={controlClass(attempted && selectionError !== null, true)}
                  onChange={(event) => {
                    refusals.edited("contracts");
                    setContracts(event.target.value);
                  }}
                />
              )}
            </Field>
            <Field
              name="as_of"
              label={t("evidence.packs.sampleAsOf")}
              required
              help={t("evidence.sample.dateHelp")}
              error={attempted ? (dateError ?? refusals.fields.date) : undefined}
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={date}
                  onChange={(value) => {
                    refusals.edited("date");
                    setDate(value);
                  }}
                  disabled={busy}
                />
              )}
            </Field>
          </fieldset>
        </form>
      </Modal>
    </>
  );
}

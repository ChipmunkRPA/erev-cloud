import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { DateInput } from "../../components/form/DateInput";
import { Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  EVIDENCE_PACKS_PATH,
  EVIDENCE_PACKS_ROUTE,
  mayCreateRegisterEvidence,
} from "../../lib/api/queries/evidence-packs";
import { queryKey } from "../../lib/api/query-keys";
import { parseDateInput, utcDateOf } from "../../lib/format";
import { t } from "../../lib/i18n/t";

export function GenerateRegisterPack({ kind }: { readonly kind: "CHANGE" | "ACCESS" }) {
  const access = useAccess();
  const navigate = useNavigate();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState("");
  const [through, setThrough] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [acceptedId, setAcceptedId] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({
    method: "POST",
    path: EVIDENCE_PACKS_PATH,
    invalidates: [queryKey("evidence-packs", "tenant")],
  });
  const start = parseDateInput(from);
  const end = parseDateInput(through);
  const valid =
    end.ok &&
    end.value <= utcDateOf(Date.now()) &&
    (kind === "ACCESS" || (start.ok && start.value <= end.value));
  const title = t(kind === "CHANGE" ? "evidence.register.change" : "evidence.register.access");
  const busy = command.pending || accepted;
  async function submit() {
    setAttempted(true);
    if (!valid || !end.ok || busy || !mayCreateRegisterEvidence(access, kind)) return;
    const body =
      kind === "ACCESS"
        ? { kind, as_of: end.value }
        : start.ok
          ? { kind, from_date: start.value, to_date: end.value }
          : null;
    if (body === null) return;
    setNetworkError(false);
    const outcome = await command.submit(body);
    if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      setAccepted(true);
      const id = outcome.response.headers.get("X-Erev-Evidence-Pack-Id");
      setAcceptedId(id);
      if (id) void navigate(`${EVIDENCE_PACKS_ROUTE}/${encodeURIComponent(id)}?kind=${kind}`);
    } else if (outcome.kind === "network-error") setNetworkError(true);
  }
  if (!mayCreateRegisterEvidence(access, kind)) return null;
  return (
    <>
      <Button onClick={() => setOpen(true)}>{title}</Button>
      <Modal
        open={open}
        variant="form"
        title={title}
        description={t("evidence.register.basis")}
        onClose={() => {
          if (!command.pending) setOpen(false);
        }}
        submitting={command.pending}
        primaryAction={{
          label: t("evidence.generate.submit"),
          form: formId,
          disabledReason: accepted ? t("evidence.register.accepted") : undefined,
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
          <RefusalBanner problem={command.problem} />
          {networkError ? (
            <Banner tone="negative" title={t("evidence.generate.networkError")} />
          ) : null}
          {attempted && !valid ? (
            <Banner tone="negative" title={t("evidence.register.dateError")} />
          ) : null}
          {accepted ? (
            <Banner tone="info" title={t("evidence.register.accepted")}>
              <a
                className="underline"
                href={
                  acceptedId
                    ? `${EVIDENCE_PACKS_ROUTE}/${acceptedId}?kind=${kind}`
                    : `${EVIDENCE_PACKS_ROUTE}?kind=${kind}`
                }
              >
                {t("evidence.register.openResult")}
              </a>
            </Banner>
          ) : null}
          <fieldset disabled={busy} className="space-y-4">
            {kind === "CHANGE" ? (
              <Field name="from_date" label={t("evidence.register.from")} required>
                {(control) => (
                  <DateInput control={control} value={from} onChange={setFrom} disabled={busy} />
                )}
              </Field>
            ) : null}
            <Field
              name={kind === "ACCESS" ? "as_of" : "to_date"}
              label={t(kind === "ACCESS" ? "evidence.packs.sampleAsOf" : "evidence.register.to")}
              required
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={through}
                  onChange={setThrough}
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

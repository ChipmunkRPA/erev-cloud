import { useRef, useState } from "react";
import { Link } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { useCommand } from "../../lib/api/commands";
import type { DealPreview } from "../../lib/api/queries/deal-previews";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";

export function SaveDealPreview({
  preview,
  onBusy,
}: {
  preview: Pick<DealPreview, "id" | "saved_contract_id" | "save_allowed">;
  onBusy: (busy: boolean) => void;
}) {
  const [externalId, setExternalId] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);
  const [networkError, setNetworkError] = useState(false);
  const inFlight = useRef(false);
  const command = useCommand<components["schemas"]["ContractOut"]>({
    method: "POST",
    path: `/api/v1/deal-previews/${preview.id}/save`,
    invalidates: [
      queryKey("deal-preview", "tenant", { id: preview.id }),
      queryKey("contracts", "tenant"),
    ],
  });
  const contractId = savedId ?? preview.saved_contract_id;
  if (contractId)
    return (
      <div className="flex flex-col gap-2">
        <p>{t("deal.saved")}</p>
        <Link className="underline" to={`/contracts/${contractId}/obligations`}>
          {t("deal.openDraft")}
        </Link>
      </div>
    );
  if (!preview.save_allowed) return null;
  async function save() {
    if (inFlight.current || !externalId.trim() || !preview.save_allowed) return;
    inFlight.current = true;
    onBusy(true);
    setNetworkError(false);
    try {
      const result = await command.submit({ contract_external_id: externalId.trim() });
      if (result.kind === "succeeded" && result.data) setSavedId(result.data.id);
      setNetworkError(result.kind === "network-error");
    } finally {
      inFlight.current = false;
      onBusy(false);
    }
  }
  return (
    <section className="flex flex-col gap-3 rounded border p-4">
      <h2 className="text-heading-sm">{t("deal.saveTitle")}</h2>
      <p>{t("deal.saveExplanation")}</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
        className="flex flex-col gap-3"
      >
        <label>
          {t("deal.externalId")}{" "}
          <input
            className="border p-2"
            required
            maxLength={128}
            value={externalId}
            disabled={command.pending}
            onChange={(event) => setExternalId(event.target.value)}
          />
        </label>
        <RefusalBanner problem={command.problem} />
        {networkError && <Banner tone="negative" title={t("deal.saveNetworkError")} />}
        <Button
          type="submit"
          loading={command.pending}
          disabledReason={!externalId.trim() ? t("deal.externalIdRequired") : undefined}
        >
          {t("deal.saveTitle")}
        </Button>
      </form>
    </section>
  );
}

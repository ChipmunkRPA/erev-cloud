import { useState } from "react";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { useCommand } from "../../lib/api/commands";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";

export function ArchiveScenario({
  id,
  name,
  version,
}: {
  readonly id: string;
  readonly name: string;
  readonly version: number;
}) {
  const [confirming, setConfirming] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const [finished, setFinished] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `/api/v1/scenarios/${encodeURIComponent(id)}/archive`,
    invalidates: [queryKey("scenarios", "tenant")],
  });
  const submit = async () => {
    if (command.pending || finished || !confirming) return;
    setNetworkError(false);
    const outcome = await command.submit(undefined, { ifMatch: rowIfMatch(version) });
    setNetworkError(outcome.kind === "network-error");
    if (outcome.kind === "succeeded") {
      setFinished(true);
      setConfirming(false);
    }
  };
  if (finished) return <p role="status">{t("reports.scenarios.archive.done")}</p>;
  return (
    <div className="flex flex-col gap-2">
      {!confirming ? (
        <Button variant="secondary" onClick={() => setConfirming(true)}>
          {t("reports.scenarios.archive.action")}
        </Button>
      ) : (
        <>
          <p>{t("reports.scenarios.archive.confirm", { name })}</p>
          <p>{t("reports.scenarios.archive.effect")}</p>
          <div className="flex gap-2">
            <Button variant="primary" loading={command.pending} onClick={() => void submit()}>
              {t("reports.scenarios.archive.confirmAction")}
            </Button>
            <Button
              variant="secondary"
              disabledReason={command.pending ? t("reports.scenarios.archive.pending") : undefined}
              onClick={() => setConfirming(false)}
            >
              {t("reports.scenarios.archive.cancel")}
            </Button>
          </div>
        </>
      )}
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      {networkError ? (
        <Banner tone="negative" title={t("reports.scenarios.archive.error")}>
          {t("reports.scenarios.networkError")}
        </Banner>
      ) : null}
    </div>
  );
}

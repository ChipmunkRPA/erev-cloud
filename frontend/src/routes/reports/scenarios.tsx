import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal } from "../../lib/api/jobs";
import { fetchListPage } from "../../lib/api/lists";
import { useMe } from "../../lib/api/queries/me";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { TextField } from "../contracts/drawers/common";
import { useOpenWorkspace } from "../settings/sandbox";
import { ReportsHeader } from "./frame";

type Scenario = components["schemas"]["ScenarioOut"];
const KEY = queryKey("scenarios", "tenant");
const label = (key: string) => t(`reports.scenarios.${key}`);
export function ScenarioPage() {
  const access = useAccess();
  const me = useMe();
  const tenant = me.data?.memberships.find(
    (m) => m.membership_id === me.data?.active_membership_id,
  )?.tenant;
  const allowed = tenant?.kind === "production" && access.holdsForAll("scenario.use");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [networkError, setNetworkError] = useState(false);
  const records = useInfiniteQuery({
    queryKey: KEY,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      fetchListPage<Scenario>("/api/v1/scenarios", { sort: "-created_at" }, pageParam, {
        limit: 50,
        count: false,
      }),
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: allowed,
    retry: false,
  });
  const command = useCommand({ method: "POST", path: "/api/v1/scenarios", invalidates: [KEY] });
  const workspace = useOpenWorkspace("/reports/forecasts");
  const busy = command.pending || (command.jobId !== null && !isTerminal(command.job));
  const valid = name.trim().length > 0 && name.trim().length <= 400 && purpose.length <= 4000;
  const submit = async () => {
    if (!allowed || busy || !valid) return;
    setNetworkError(false);
    const outcome = await command.submit({ name: name.trim(), purpose: purpose.trim() || null });
    setNetworkError(outcome.kind === "network-error");
    if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      setName("");
      setPurpose("");
    }
  };
  return (
    <div className="flex flex-col gap-4">
      <ReportsHeader />
      <section aria-label={label("title")} className="flex flex-col gap-4 px-[var(--gutter)]">
        <h2 className="text-title-md">{label("title")}</h2>
        {!allowed ? (
          <p>{label("sourceOnly")}</p>
        ) : (
          <>
            <p>{label("description")}</p>
            <form
              className="flex flex-col gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <TextField
                name="scenario-name"
                label={label("name")}
                value={name}
                onChange={setName}
                disabled={busy}
              />
              <TextField
                name="scenario-purpose"
                label={label("purpose")}
                value={purpose}
                onChange={setPurpose}
                disabled={busy}
              />
              <Button
                type="submit"
                variant="primary"
                loading={busy}
                disabledReason={
                  !valid ? label("nameRequired") : busy ? label("creating") : undefined
                }
              >
                {label("create")}
              </Button>
            </form>
            {networkError || command.jobError ? (
              <Banner tone="negative" title={label("createError")}>
                {command.jobError?.message ?? label("networkError")}
              </Banner>
            ) : null}
            <RefusalBanner problem={command.problem} />
            {command.job ? (
              <JobProgress label={label("creating")} job={command.job} unit="" />
            ) : null}
            {workspace.problem ? (
              <Banner tone="negative" title={label("openError")}>
                {workspace.problem}
              </Banner>
            ) : null}
            {records.isError ? (
              <Banner
                tone="negative"
                title={label("loadError")}
                actions={
                  <Button
                    onClick={() =>
                      void (records.isFetchNextPageError
                        ? records.fetchNextPage()
                        : records.refetch())
                    }
                  >
                    {t("common.job.retry")}
                  </Button>
                }
              />
            ) : null}
            {records.isPending ? <p role="status">{label("loading")}</p> : null}
            {records.isSuccess && records.data.pages.every((page) => page.items.length === 0) ? (
              <p>{label("empty")}</p>
            ) : null}
            {records.data?.pages
              .flatMap((page) => page.items)
              .map((scenario) => (
                <article
                  key={scenario.id}
                  className="flex flex-col gap-2 rounded border border-default p-3"
                >
                  <h3 className="text-title-sm">{scenario.name}</h3>
                  <p>{scenario.purpose}</p>
                  <p>
                    {label(scenario.status === "ACTIVE" ? "active" : "archived")} ·{" "}
                    {label("cutoff")}: {formatTimestamp(scenario.base_known_at)}
                  </p>
                  {scenario.last_refreshed_at ? (
                    <p>
                      {label("refreshed")}: {formatTimestamp(scenario.last_refreshed_at)}
                    </p>
                  ) : null}
                  <Button
                    variant="secondary"
                    loading={workspace.pending}
                    onClick={() => workspace.open(scenario.scenario_tenant_id, scenario.name)}
                  >
                    {label("open")}
                  </Button>
                </article>
              ))}
            {records.hasNextPage ? (
              <Button loading={records.isFetching} onClick={() => void records.fetchNextPage()}>
                {label("more")}
              </Button>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

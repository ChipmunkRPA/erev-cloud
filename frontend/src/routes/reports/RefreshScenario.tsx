import { useEffect, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Field } from "../../components/form/Field";
import { Combobox } from "../../components/form/Combobox";
import { JobProgress } from "../../components/feedback/JobProgress";
import { useJob } from "../../lib/api/jobs";
import { Button } from "../../components/ui/Button";
import { useCommand } from "../../lib/api/commands";
import { fetchListPage } from "../../lib/api/lists";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";

type Refresh = components["schemas"]["ScenarioRefreshOut"];
type Input = components["schemas"]["ScenarioInputSummaryOut"];
const label = (key: string) => t(`reports.scenarios.refresh.${key}`);
const live = (row: Refresh | undefined) => row?.status === "QUEUED" || row?.status === "RUNNING";

export function RefreshScenario({
  id,
  version,
}: {
  readonly id: string;
  readonly version: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState("");
  const [acceptedJob, setAcceptedJob] = useState<string | null>(null);
  const [networkError, setNetworkError] = useState(false);
  const client = useQueryClient();
  const path = `/api/v1/scenarios/${encodeURIComponent(id)}`;
  const command = useCommand({
    method: "POST",
    path: `${path}/refresh`,
    invalidates: [queryKey("scenarios", "tenant")],
  });
  const status = useQuery({
    queryKey: queryKey("scenario-refreshes", "tenant", { id }),
    queryFn: () =>
      fetchListPage<Refresh>(`${path}/refreshes`, { sort: "-created_at" }, null, {
        limit: 1,
        count: false,
      }),
    enabled: expanded,
    retry: false,
    refetchInterval: (query) => {
      const latest = query.state.data?.items[0];
      return live(latest) || (acceptedJob !== null && latest?.job_id !== acceptedJob)
        ? 2000
        : false;
    },
  });
  const latest = status.data?.items[0];
  const job = useJob(expanded ? (acceptedJob ?? latest?.job_id ?? null) : null);
  const awaiting = acceptedJob !== null && latest?.job_id !== acceptedJob;
  const busy = command.pending || awaiting || live(latest);
  const inputs = useInfiniteQuery({
    queryKey: queryKey("scenario-published-inputs", "tenant", { id, version }),
    queryFn: ({ pageParam }) =>
      fetchListPage<Input>(`${path}/published-inputs`, { sort: "-created_at" }, pageParam, {
        limit: 50,
        count: false,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: expanded && !busy,
    retry: false,
  });
  useEffect(() => {
    if (latest && !live(latest)) {
      void client.invalidateQueries({ queryKey: queryKey("scenarios", "tenant") });
      void client.invalidateQueries({
        queryKey: queryKey("scenario-published-inputs", "tenant", { id, version }),
      });
    }
  }, [client, id, version, latest]);
  const choices = inputs.data?.pages.flatMap((page) => page.items) ?? [];
  const valid = choices.some((item) => item.id === selected);
  const submit = async () => {
    if (busy || !valid || !status.isSuccess || status.isFetching) return;
    setNetworkError(false);
    const outcome = await command.submit(
      { forecast_event_set_id: selected },
      { ifMatch: rowIfMatch(version) },
    );
    setNetworkError(outcome.kind === "network-error");
    if (outcome.kind === "accepted") setAcceptedJob(outcome.jobId);
    await status.refetch();
  };
  return (
    <div className="flex flex-col gap-2">
      <Button variant="secondary" onClick={() => setExpanded(!expanded)}>
        {label(expanded ? "hide" : "action")}
      </Button>
      {expanded ? (
        <>
          <p>{label("effect")}</p>
          {status.isPending ? <p role="status">{label("loading")}</p> : null}
          {latest && !awaiting ? (
            <p role="status">
              {label(latest.status)} ·{" "}
              {formatTimestamp(latest.finished_at ?? latest.started_at ?? latest.created_at)}
            </p>
          ) : null}
          {job.data ? <JobProgress label={label("action")} job={job.data} unit="" /> : null}
          {awaiting ? <p role="status">{label("awaiting")}</p> : null}
          {status.isError ? (
            <Banner
              tone="negative"
              title={label("statusError")}
              actions={
                <Button onClick={() => void status.refetch()}>{t("common.job.retry")}</Button>
              }
            />
          ) : null}
          <Field name={`refresh-input-${id}`} label={label("input")}>
            {(control) => (
              <Combobox
                control={control}
                value={valid ? selected : ""}
                options={[
                  { value: "", label: label("choose") },
                  ...choices.map((item) => ({
                    value: item.id,
                    label: `${item.code} — ${item.name} (v${item.version_no})`,
                  })),
                ]}
                onChange={(value) => setSelected(value ?? "")}
              />
            )}
          </Field>
          {inputs.isSuccess && choices.length === 0 ? <p>{label("empty")}</p> : null}
          {inputs.isError ? (
            <Banner
              tone="negative"
              title={label("inputsError")}
              actions={
                <Button
                  onClick={() =>
                    void (inputs.isFetchNextPageError ? inputs.fetchNextPage() : inputs.refetch())
                  }
                >
                  {t("common.job.retry")}
                </Button>
              }
            />
          ) : null}
          {inputs.hasNextPage ? (
            <Button loading={inputs.isFetching} onClick={() => void inputs.fetchNextPage()}>
              {label("more")}
            </Button>
          ) : null}
          <Button
            variant="primary"
            loading={busy}
            disabledReason={
              busy
                ? label("awaiting")
                : !status.isSuccess || status.isFetching
                  ? label("loading")
                  : !valid
                    ? label("choose")
                    : undefined
            }
            onClick={() => void submit()}
          >
            {label("submit")}
          </Button>
          <RefusalBanner problem={command.problem} conflict={command.banner} />
          {networkError ? (
            <Banner tone="negative" title={label("error")}>
              {t("reports.scenarios.networkError")}
            </Banner>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

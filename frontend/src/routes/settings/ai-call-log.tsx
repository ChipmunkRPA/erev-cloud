// SF-15:ai-call-log. Retained evidence remains readable while AI is disabled.
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { SavedViewSelector } from "../../components/data-grid/SavedViewSelector";
import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Drawer } from "../../components/ui/Drawer";
import { StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import {
  aiModelLogKey,
  aiModelLogsKey,
  fetchAIModelLog,
  fetchAIModelLogs,
  type AIModelLog,
} from "../../lib/api/queries/ai-model-logs";
import { useMe } from "../../lib/api/queries/me";
import { formatTimestamp, formatDuration, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Button } from "../../components/ui/Button";
import { CopySimple } from "../../components/icons/registry";
import { announce } from "../../lib/a11y/announce";
import { fetchProposals, AI_REVIEW_ROUTE } from "../../lib/api/queries/ai";
import { queryKey } from "../../lib/api/query-keys";
import { SettingsPageHeader } from "./index";
import { CallLogExport } from "./ai-call-log-export";

const label = (key: string) => t("settings.aiCallLog." + key);
const outcomes = {
  SUCCESS: "Succeeded",
  ERROR: "Failed",
  TIMEOUT: "Timed out",
  BUDGET_EXCEEDED: "Budget exceeded",
  DISABLED: "Disabled",
} as const;
const path = "/settings/ai/call-log";
function callRoute(id: string, search: string) {
  const params = new URLSearchParams(search);
  params.set("drawer", "call");
  params.set("call", id);
  return `${path}?${params.toString()}`;
}
function CallLink({ row }: { readonly row: AIModelLog }) {
  const location = useLocation();
  return (
    <Link to={callRoute(row.id, location.search)} className="whitespace-nowrap" data-volatile="">
      {formatTimestamp(row.created_at)}
    </Link>
  );
}
const columns: readonly GridColumn<AIModelLog>[] = [
  {
    id: "created_at",
    header: label("called"),
    kind: "timestamp",
    value: (row) => row.created_at,
    sortKey: "created_at",
    render: (row) => <CallLink row={row} />,
  },
  {
    id: "created_by",
    header: label("user"),
    kind: "user",
    value: (row) => row.created_by.display_name,
  },
  {
    id: "template",
    header: label("template"),
    kind: "text",
    value: (row) => `${row.prompt_template_id} v${row.prompt_template_version}`,
  },
  {
    id: "provider",
    header: label("provider"),
    kind: "text",
    value: (row) => (row.provider === "fake" ? "Fake" : "Anthropic"),
  },
  { id: "model_id", header: label("model"), kind: "text", value: (row) => row.model_id },
  {
    id: "outcome",
    header: label("outcome"),
    kind: "status",
    value: (row) => outcomes[row.outcome],
    render: (row) => <StatusChip status={outcomes[row.outcome]} />,
  },
  {
    id: "input_tokens",
    header: label("input"),
    kind: "number",
    value: (row) => (row.usage_known ? String(row.input_tokens) : null),
    render: (row) => (row.usage_known ? formatNumber(row.input_tokens) : label("unknown")),
  },
  {
    id: "output_tokens",
    header: label("output"),
    kind: "number",
    value: (row) => (row.usage_known ? String(row.output_tokens) : null),
    render: (row) => (row.usage_known ? formatNumber(row.output_tokens) : label("unknown")),
  },
  {
    id: "latency_ms",
    header: label("latency"),
    kind: "text",
    value: (row) => formatDuration(row.latency_ms),
  },
];

const DEFAULT_COLUMNS = initialColumnState(columns);

export function AICallLog() {
  const me = useMe();
  const access = useAccess();
  const allowed = access.holdsForAll("settings.manage") || access.holdsAnywhere("ai.use");
  return (
    <div className="flex w-full flex-col gap-6 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={label("title")} group="ai" />
      {me.isError ? (
        <Banner tone="negative" title={me.error.message} />
      ) : me.data === undefined ? (
        <Skeleton region={label("title")} shape="rows" count={6} />
      ) : !allowed ? (
        <AccessLimited area={label("title")} permissions={["ai.use", "settings.manage"]} />
      ) : (
        <CallGrid />
      )}
    </div>
  );
}
function CallGrid() {
  const me = useMe().data;
  const [columnState, setColumnState] = useState(DEFAULT_COLUMNS);
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const selected = params.get("drawer") === "call" ? params.get("call") : null;
  const source = useMemo<GridSource<AIModelLog>>(
    () => ({ queryKey: aiModelLogsKey(), fetchPage: fetchAIModelLogs }),
    [],
  );
  const close = () => {
    const next = new URLSearchParams(location.search);
    next.delete("drawer");
    next.delete("call");
    void navigate({ pathname: location.pathname, search: next.toString() });
  };
  return (
    <div className="flex min-h-0 min-w-0 gap-4">
      <div className="min-w-0 flex-1">
        <DataGrid
          name="ai-calls"
          title={label("grid")}
          columns={columns}
          source={source}
          rowKey={(row) => row.id}
          rowLabel={(row) => formatTimestamp(row.created_at)}
          rowHref={(row) => callRoute(row.id, location.search)}
          rowTestKey={(row) => row.prompt_template_id}
          testIdPrefix="SF-15"
          selectable={false}
          columnState={columnState}
          defaultColumnState={DEFAULT_COLUMNS}
          onColumnStateChange={setColumnState}
          toolbarActions={<CallLogExport key={me?.active_membership_id ?? "none"} />}
          viewSelector={
            <SavedViewSelector
              screenCode="SF-15:ai-call-log"
              membershipId={me?.active_membership_id ?? null}
              defaultLabel={label("grid")}
              columnState={columnState}
              defaultColumnState={DEFAULT_COLUMNS}
              onApplyColumns={setColumnState}
              testId="SF-15-ai-call-log-saved-view"
            />
          }
          countLabel={(count, formatted) =>
            `${formatted} ${label(count === 1 ? "singular" : "calls")}`
          }
          errorTitle={label("error")}
          emptyState={<EmptyState title={label("empty")} description={label("description")} />}
        />
      </div>
      {selected !== null && <CallDetails id={selected} onClose={close} />}
    </div>
  );
}
function CallDetails({ id, onClose }: { readonly id: string; readonly onClose: () => void }) {
  const read = useQuery({ queryKey: aiModelLogKey(id), queryFn: () => fetchAIModelLog(id) });
  const row = read.data;
  const fields =
    row === undefined
      ? []
      : [
          ...columns.map((column) => [
            column.header,
            column.id === "created_at" ? formatTimestamp(row.created_at) : column.value(row),
          ]),
          [label("errorDetail"), row.error_detail],
        ];
  return (
    <Drawer
      open
      variant="docked"
      initialFocus="title"
      title={
        row === undefined ? label("call") : `${label("call")} · ${formatTimestamp(row.created_at)}`
      }
      onClose={onClose}
    >
      <div data-testid="SF-15-drawer-ai-call" className="flex flex-col gap-4">
        {read.isError ? (
          <Banner tone="negative" title={label("error")}>
            {read.error.message}
          </Banner>
        ) : row === undefined ? (
          <Skeleton region={label("call")} shape="rows" count={8} />
        ) : (
          <>
            {!row.usage_known && (
              <Banner tone="warning" title={label("usageUnknown")}>
                {label("usageExplanation")}
              </Banner>
            )}
            <dl className="grid grid-cols-1 gap-3">
              {fields.map(([name, value]) => (
                <div key={name}>
                  <dt className="text-muted">{name}</dt>
                  <dd className="break-all">{value ?? "—"}</dd>
                </div>
              ))}
              <HashField name={label("inputHash")} value={row.input_sha256} />
              <HashField name={label("responseHash")} value={row.response_sha256} />
            </dl>
            <CallProposals id={row.id} />
            <h3>{label("parameters")}</h3>
            <dl className="grid grid-cols-1 gap-3">
              {Object.entries(row.parameters).map(([name, value]) => (
                <div key={name}>
                  <dt className="font-mono break-all">{name}</dt>
                  <dd className="break-all">{JSON.stringify(value)}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </div>
    </Drawer>
  );
}

function HashField({ name, value }: { readonly name: string; readonly value: string | null }) {
  return (
    <div>
      <dt className="text-muted">{name}</dt>
      <dd className="flex items-center gap-2">
        <span className="break-all font-mono">{value ?? "—"}</span>
        {value !== null && (
          <Button
            variant="ghost"
            size="sm"
            icon={CopySimple}
            aria-label={t("settings.aiCallLog.copyHash", { name })}
            onClick={() => {
              void (async () => {
                try {
                  await navigator.clipboard.writeText(value);
                  announce(label("hashCopied"));
                } catch {
                  announce(label("hashCopyFailed"));
                }
              })();
            }}
          />
        )}
      </dd>
    </div>
  );
}
function CallProposals({ id }: { readonly id: string }) {
  const access = useAccess();
  const allowed = access.holdsAnywhere("ai.use");
  const read = useInfiniteQuery({
    queryKey: queryKey("ai-proposals", "tenant", { call: id }),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => fetchProposals({ ai_model_log_id: id }, pageParam),
    getNextPageParam: (page) => page.nextCursor,
    enabled: allowed,
    staleTime: 0,
    refetchOnMount: "always",
  });
  if (!allowed) return <p>{label("proposalsAccess")}</p>;
  if (read.isError)
    return (
      <Banner tone="negative" title={label("proposalsError")}>
        {read.error.message}
      </Banner>
    );
  if (read.data === undefined || (read.isFetching && !read.isFetchingNextPage))
    return <Skeleton region={label("proposals")} shape="rows" count={1} />;
  const items = read.data.pages.flatMap((page) => page.items);
  return (
    <section aria-label={label("proposals")} className="flex flex-col gap-2">
      <h3>{label("proposals")}</h3>
      {items.length === 0 ? (
        <p>{label("noProposals")}</p>
      ) : (
        <ul>
          {items.map((proposal) => (
            <li key={proposal.id}>
              <Link
                to={
                  proposal.kind === "CONTRACT_EXTRACTION"
                    ? `${AI_REVIEW_ROUTE}/${encodeURIComponent(proposal.id)}`
                    : `/trace/${encodeURIComponent(proposal.subject_id)}?proposal=${encodeURIComponent(proposal.id)}`
                }
              >
                {label(
                  proposal.kind === "CONTRACT_EXTRACTION" ? "contractProposal" : "numberProposal",
                )}{" "}
                · {formatTimestamp(proposal.created_at)}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {read.hasNextPage && (
        <Button
          loading={read.isFetchingNextPage}
          onClick={() => {
            void read.fetchNextPage();
          }}
        >
          {label("moreProposals")}
        </Button>
      )}
    </section>
  );
}

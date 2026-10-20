import { ForecastInputReview } from "./ForecastInputReview";
import { Link } from "react-router";
import { useAccess } from "../../lib/access";
import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { useCommand } from "../../lib/api/commands";
import { fetchListPage } from "../../lib/api/lists";
import type { ForecastInput } from "../../lib/api/queries/forecasts";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { TextField } from "../contracts/drawers/common";

const key = queryKey("forecast-event-sets", "tenant");
const label = (value: string) => t(`reports.inputs.${value}`);
function InputRecord({ row }: { readonly row: ForecastInput }) {
  const access = useAccess();
  const [name, setName] = useState(row.name);
  const [confirming, setConfirming] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const [finished, setFinished] = useState(false);
  const edit = useCommand({
    method: "PATCH",
    path: `/api/v1/forecast-event-sets/${row.id}`,
    invalidates: [key],
  });
  const publish = useCommand({
    method: "POST",
    path: `/api/v1/forecast-event-sets/${row.id}/publish`,
    invalidates: [key],
  });
  const busy = edit.pending || publish.pending || finished;
  const save = async (publication: boolean) => {
    if (busy || (publication && !confirming)) return;
    setNetworkError(false);
    const outcome = publication
      ? await publish.submit(undefined, { ifMatch: rowIfMatch(row.row_version) })
      : await edit.submit({ name: name.trim() }, { ifMatch: rowIfMatch(row.row_version) });
    setNetworkError(outcome.kind === "network-error");
    if (outcome.kind === "succeeded") setFinished(true);
  };
  return (
    <article className="flex flex-col gap-2 rounded border border-default p-3">
      <h4>
        {row.code} — {row.name} · v{row.version_no} · {row.status}
      </h4>
      <p>
        {label("commands")}: {row.api_commands.length} · {label("imports")}:{" "}
        {row.import_upload_ids.length}
      </p>
      <ForecastInputReview row={row} />
      {row.content_sha256 ? (
        <p className="break-all">
          {label("hash")}: {row.content_sha256}
        </p>
      ) : null}
      {row.status === "DRAFT" ? (
        <>
          {access.holdsAnywhere("import.upload") ? (
            <Link
              className="underline"
              to={`/data/imports/new?event_set=${encodeURIComponent(row.id)}`}
            >
              {label("import")}
            </Link>
          ) : null}
          <TextField
            name={`input-name-${row.id}`}
            label={label("name")}
            value={name}
            onChange={setName}
            disabled={busy || confirming}
          />
          <div className="flex gap-2">
            <Button
              loading={edit.pending}
              disabledReason={
                busy ||
                confirming ||
                !name.trim() ||
                name.trim().length > 400 ||
                name.trim() === row.name
                  ? label("noChanges")
                  : undefined
              }
              onClick={() => void save(false)}
            >
              {label("save")}
            </Button>
            <Button
              disabledReason={busy || name.trim() !== row.name ? label("saveFirst") : undefined}
              onClick={() => setConfirming(true)}
            >
              {label("publish")}
            </Button>
          </div>
          {confirming ? (
            <>
              <p>{label("confirm")}</p>
              {row.api_commands.length === 0 && row.import_upload_ids.length === 0 ? (
                <p>{label("baseline")}</p>
              ) : null}
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  loading={publish.pending}
                  disabledReason={busy ? label("pending") : undefined}
                  onClick={() => void save(true)}
                >
                  {label("confirmPublish")}
                </Button>
                <Button
                  disabledReason={busy ? label("pending") : undefined}
                  onClick={() => setConfirming(false)}
                >
                  {label("cancel")}
                </Button>
              </div>
            </>
          ) : null}
          <RefusalBanner problem={edit.problem} conflict={edit.banner} />
          <RefusalBanner problem={publish.problem} conflict={publish.banner} />
          {networkError ? <Banner tone="negative" title={label("error")} /> : null}
        </>
      ) : null}
    </article>
  );
}
export function ForecastInputs() {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [networkError, setNetworkError] = useState(false);
  const records = useInfiniteQuery({
    queryKey: [...key, "manage"],
    queryFn: ({ pageParam }) =>
      fetchListPage<ForecastInput>(
        "/api/v1/forecast-event-sets",
        { sort: "-created_at" },
        pageParam,
        { limit: 50, count: false },
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: open,
    retry: false,
  });
  const create = useCommand({
    method: "POST",
    path: "/api/v1/forecast-event-sets",
    invalidates: [key],
  });
  const valid =
    /^[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}$/.test(code.trim()) &&
    name.trim().length > 0 &&
    name.trim().length <= 400;
  const submit = async () => {
    if (!valid || create.pending) return;
    setNetworkError(false);
    const outcome = await create.submit({ code: code.trim(), name: name.trim() });
    setNetworkError(outcome.kind === "network-error");
    if (outcome.kind === "succeeded") {
      setCode("");
      setName("");
    }
  };
  return (
    <section className="flex flex-col gap-3">
      <Button variant="secondary" onClick={() => setOpen(!open)}>
        {label(open ? "hide" : "title")}
      </Button>
      {open ? (
        <>
          <p>{label("description")}</p>
          <form
            className="flex flex-col gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <TextField
              name="input-code"
              label={label("code")}
              value={code}
              onChange={setCode}
              disabled={create.pending}
            />
            <TextField
              name="input-name"
              label={label("name")}
              value={name}
              onChange={setName}
              disabled={create.pending}
            />
            <Button
              type="submit"
              variant="primary"
              loading={create.pending}
              disabledReason={!valid ? label("required") : undefined}
            >
              {label("create")}
            </Button>
          </form>
          <RefusalBanner problem={create.problem} />
          {networkError ? <Banner tone="negative" title={label("error")} /> : null}
          {records.isPending ? <p role="status">{label("loading")}</p> : null}
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
                  {label("retry")}
                </Button>
              }
            />
          ) : null}
          {records.data?.pages
            .flatMap((page) => page.items)
            .map((row) => (
              <InputRecord key={`${row.id}:${row.row_version}`} row={row} />
            ))}
          {records.isSuccess && records.data.pages.every((page) => page.items.length === 0) ? (
            <p>{label("empty")}</p>
          ) : null}
          {records.hasNextPage ? (
            <Button loading={records.isFetching} onClick={() => void records.fetchNextPage()}>
              {label("more")}
            </Button>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

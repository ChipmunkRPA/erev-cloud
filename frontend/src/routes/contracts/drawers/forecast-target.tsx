import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Banner } from "../../../components/feedback/Banner";
import { Field } from "../../../components/form/Field";
import { Combobox } from "../../../components/form/Combobox";
import { Button } from "../../../components/ui/Button";
import { useAccess } from "../../../lib/access";
import { fetchListPage } from "../../../lib/api/lists";
import type { ForecastInput } from "../../../lib/api/queries/forecasts";
import { useMe } from "../../../lib/api/queries/me";
import { queryKey } from "../../../lib/api/query-keys";
import { t } from "../../../lib/i18n/t";

const label = (key: string) => t(`contracts.drawer.forecast.${key}`);
export function useForecastEventTarget(locked: boolean) {
  const access = useAccess();
  const me = useMe();
  const tenant = me.data?.memberships.find(
    (m) => m.membership_id === me.data?.active_membership_id,
  )?.tenant;
  const allowed = tenant?.kind === "sandbox" && access.holdsForAll("scenario.use");
  const [id, setId] = useState<string | null>(null);
  const records = useInfiniteQuery({
    queryKey: queryKey("forecast-event-sets", "tenant", { status: "DRAFT" }),
    queryFn: ({ pageParam }) =>
      fetchListPage<ForecastInput>(
        "/api/v1/forecast-event-sets",
        { status: "DRAFT", sort: "-created_at" },
        pageParam,
        { limit: 50, count: false },
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: allowed,
    retry: false,
  });
  const rows = records.data?.pages.flatMap((page) => page.items) ?? [];
  const valid =
    id === null ||
    (allowed && records.isSuccess && rows.some((row) => row.id === id && row.status === "DRAFT"));
  const control = allowed ? (
    <fieldset disabled={locked} className="flex flex-col gap-2">
      <Field name="event-forecast-target" label={label("target")}>
        {(control) => (
          <Combobox
            control={control}
            value={id ?? ""}
            options={[
              { value: "", label: label("ordinary") },
              ...rows.map((row) => ({
                value: row.id,
                label: `${row.code} — ${row.name} (v${row.version_no})`,
              })),
            ]}
            onChange={(value) => {
              if (!locked) setId(value || null);
            }}
          />
        )}
      </Field>
      {id !== null ? <p>{label("effect")}</p> : <p>{label("optional")}</p>}
      {!valid ? <Banner tone="negative" title={label("unavailable")} /> : null}
      {records.isError ? (
        <Banner
          tone="negative"
          title={label("loadError")}
          actions={
            <Button
              onClick={() =>
                void (records.isFetchNextPageError ? records.fetchNextPage() : records.refetch())
              }
            >
              {label("retry")}
            </Button>
          }
        />
      ) : null}
      {records.hasNextPage ? (
        <Button loading={records.isFetching} onClick={() => void records.fetchNextPage()}>
          {label("more")}
        </Button>
      ) : null}
    </fieldset>
  ) : null;
  return { id, valid, control };
}

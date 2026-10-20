import { useInfiniteQuery } from "@tanstack/react-query";

import { Combobox } from "../../../components/form/Combobox";
import { Field } from "../../../components/form/Field";
import { chipFor } from "../../../components/ui/StatusChip";
import { formatDate } from "../../../lib/format";
import { Button } from "../../../components/ui/Button";
import { useAccess } from "../../../lib/access";
import { fetchListPage } from "../../../lib/api/lists";
import { queryKey } from "../../../lib/api/query-keys";
import {
  MIGRATIONS_PATH,
  MIGRATION_RUN_PERMISSION,
  type Migration,
} from "../../../lib/api/queries/migrations";
import { t } from "../../../lib/i18n/t";
import { TextField } from "../../contracts/drawers/common";

export function MigrationParameter({
  value,
  error,
  disabled,
  onChange,
}: {
  readonly value: string;
  readonly error: string | undefined;
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}) {
  const access = useAccess();
  const allowed = access.holdsForAll(MIGRATION_RUN_PERMISSION);
  const records = useInfiniteQuery({
    queryKey: queryKey("migrations", "tenant", { view: "report-parameter" }),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      fetchListPage<Migration>(MIGRATIONS_PATH, { sort: "-created_at" }, pageParam, {
        limit: 50,
        count: false,
      }),
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: allowed && !disabled,
    retry: false,
  });
  const options =
    records.data?.pages
      .flatMap((page) => page.items)
      .map((item) => ({
        value: item.id,
        label: `${item.migration_no} · ${t(`data.migrations.mode.${item.mode}`)} · ${chipFor("E-76", item.status)?.caption ?? item.status}${item.cutover_date ? ` · ${formatDate(item.cutover_date)}` : ""}`,
      })) ?? [];
  // A saved report may refer to an older batch outside the loaded pages. Never erase that ID.
  if (value && !options.some((option) => option.value === value))
    options.unshift({ value, label: value });
  if (!allowed || disabled)
    return (
      <TextField
        name="p-migration_id"
        label={t("reports.parameters.migration_id")}
        value={value}
        error={error}
        disabled={disabled}
        onChange={onChange}
      />
    );
  return (
    <div className="flex flex-col gap-1">
      <Field name="p-migration_id" label={t("reports.parameters.migration_id")} error={error}>
        {(control) => (
          <Combobox
            control={control}
            options={options}
            value={value || null}
            onChange={(next) => onChange(next ?? "")}
            invalid={error !== undefined}
          />
        )}
      </Field>
      {records.isPending ? <p role="status">{t("reports.parameters.migrations.loading")}</p> : null}
      {records.isError ? (
        <div role="alert">
          <p>{t("reports.parameters.migrations.error")}</p>
          <Button
            variant="link"
            onClick={() =>
              void (records.isFetchNextPageError ? records.fetchNextPage() : records.refetch())
            }
          >
            {t("common.job.retry")}
          </Button>
        </div>
      ) : null}
      {records.hasNextPage ? (
        <Button
          variant="link"
          loading={records.isFetching}
          onClick={() => void records.fetchNextPage()}
        >
          {t("reports.parameters.migrations.more")}
        </Button>
      ) : null}
      {records.isSuccess && options.length === 0 ? (
        <p>{t("reports.parameters.migrations.empty")}</p>
      ) : null}
    </div>
  );
}

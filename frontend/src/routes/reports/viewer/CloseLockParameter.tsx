import { useQuery } from "@tanstack/react-query";
import { Combobox } from "../../../components/form/Combobox";
import { Field } from "../../../components/form/Field";
import { Button } from "../../../components/ui/Button";
import { useAccess } from "../../../lib/access";
import { fetchPeriodLocks, locksKey } from "../../../lib/api/queries/periods";
import { formatTimestamp } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { TextField } from "../../contracts/drawers/common";
import type { ReportContext } from "./specs";

export function CloseLockParameter({
  name,
  context,
  value,
  error,
  disabled,
  onChange,
}: {
  readonly name: "from_period_lock_id" | "to_period_lock_id";
  readonly context: ReportContext;
  readonly value: string;
  readonly error: string | undefined;
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}) {
  const access = useAccess();
  const period = context.periods.find(
    (item) =>
      item.entity.code === context.entity &&
      item.book === context.book &&
      item.period.period_key === context.periodKey,
  );
  const allowed = period !== undefined && access.holds("config.read", period.entity);
  const locks = useQuery({
    queryKey: locksKey(period?.id ?? ""),
    queryFn: () => {
      if (period === undefined) throw new Error("No period selected");
      return fetchPeriodLocks(period.id);
    },
    enabled: allowed && !disabled,
    retry: false,
  });
  const label = t(`reports.parameters.${name}`);
  const options = (locks.data ?? [])
    .filter((lock) => lock.kind === "LOCK")
    .map((lock) => ({
      value: lock.id,
      label: `${formatTimestamp(lock.created_at)} · ${lock.created_by.display_name} · ${lock.approval_request_no ?? lock.id}`,
    }));
  if (value && !options.some((option) => option.value === value))
    options.unshift({ value, label: value });
  // Preserve explicit/saved references when context is missing; the backend validates the pair.
  if (!allowed || disabled)
    return (
      <TextField
        name={`p-${name}`}
        label={label}
        value={value}
        error={error}
        disabled={disabled}
        onChange={onChange}
        help={!period && !disabled ? t("reports.parameters.locks.context") : undefined}
      />
    );
  return (
    <div className="flex flex-col gap-1">
      <Field name={`p-${name}`} label={label} error={error}>
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
      {locks.isPending ? <p role="status">{t("reports.parameters.locks.loading")}</p> : null}
      {locks.isError ? (
        <div role="alert">
          <p>{t("reports.parameters.locks.error")}</p>
          <Button variant="link" onClick={() => void locks.refetch()}>
            {t("common.job.retry")}
          </Button>
        </div>
      ) : null}
      {locks.isSuccess && options.length === 0 ? (
        <p>{t("reports.parameters.locks.empty")}</p>
      ) : null}
    </div>
  );
}

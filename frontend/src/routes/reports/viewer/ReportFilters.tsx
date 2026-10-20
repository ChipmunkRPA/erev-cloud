import { Button } from "../../../components/ui/Button";
import { t } from "../../../lib/i18n/t";
import { TextField } from "../../contracts/drawers/common";
import { filterRows } from "./filterValues";

export function ReportFilters({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const rows = filterRows(value);
  if (rows === null)
    return (
      <div>
        <p role="alert">{t("reports.filters.invalid")}</p>
        <Button
          disabledReason={disabled ? t("reports.filters.locked") : undefined}
          onClick={() => onChange("")}
        >
          {t("reports.filters.clear")}
        </Button>
      </div>
    );
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="text-body-sm font-medium">{t("reports.filters.title")}</legend>
      {rows.map(([field, match], index) => (
        <div className="flex flex-wrap items-end gap-2" key={index}>
          <TextField
            name={`filter-${index}-field`}
            label={t("reports.filters.field", { number: index + 1 })}
            value={field}
            disabled={disabled}
            onChange={(next) =>
              onChange(JSON.stringify(rows.map((row, i) => (i === index ? [next, row[1]] : row))))
            }
          />
          <TextField
            name={`filter-${index}-value`}
            label={t("reports.filters.value", { number: index + 1 })}
            value={match}
            disabled={disabled}
            onChange={(next) =>
              onChange(JSON.stringify(rows.map((row, i) => (i === index ? [row[0], next] : row))))
            }
          />
          <Button
            variant="secondary"
            disabledReason={disabled ? t("reports.filters.locked") : undefined}
            onClick={() => {
              const next = rows.filter((_, i) => i !== index);
              onChange(next.length ? JSON.stringify(next) : "");
            }}
          >
            {t("reports.filters.remove", { number: index + 1 })}
          </Button>
        </div>
      ))}
      <Button
        variant="secondary"
        disabledReason={disabled ? t("reports.filters.locked") : undefined}
        onClick={() => onChange(JSON.stringify([...rows, ["", ""]]))}
      >
        {t("reports.filters.add")}
      </Button>
    </fieldset>
  );
}

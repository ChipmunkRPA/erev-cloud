import { Button } from "../../../components/ui/Button";
import { t } from "../../../lib/i18n/t";
import { TextField } from "../../contracts/drawers/common";

const fields = [
  "contract_external_id",
  "as_of",
  "currency",
  "contract_liability",
  "unbilled_receivable",
  "source_reference",
] as const;
type Position = Record<(typeof fields)[number], string>;
function read(raw: string): Position[] | null {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    return Array.isArray(value) &&
      value.every(
        (row) =>
          row && typeof row === "object" && fields.every((key) => typeof row[key] === "string"),
      )
      ? (value as Position[])
      : null;
  } catch {
    return null;
  }
}

export function LegacyPositions({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const rows = read(value);
  const save = (next: Position[]) => onChange(next.length ? JSON.stringify(next) : "");
  return (
    <fieldset disabled={disabled} className="flex flex-col gap-2">
      <legend className="text-body-sm font-medium">{t("reports.legacyPositions.title")}</legend>
      <p className="text-body-sm text-fg-2">{t("reports.legacyPositions.help")}</p>
      {rows === null ? (
        <>
          <p role="alert">{t("reports.legacyPositions.invalid")}</p>
          <Button
            onClick={() => onChange("")}
            disabledReason={disabled ? t("reports.filters.locked") : undefined}
          >
            {t("reports.filters.clear")}
          </Button>
        </>
      ) : (
        <>
          {rows.map((row, index) => (
            <div key={index} className="flex flex-wrap items-end gap-2">
              {fields.map((key) => (
                <TextField
                  key={key}
                  name={`legacy-position-${index}-${key}`}
                  label={t(`reports.legacyPositions.${key}`)}
                  value={row[key]}
                  disabled={disabled}
                  onChange={(next) =>
                    save(rows.map((item, i) => (i === index ? { ...item, [key]: next } : item)))
                  }
                />
              ))}
              <Button
                variant="secondary"
                disabledReason={disabled ? t("reports.filters.locked") : undefined}
                onClick={() => save(rows.filter((_, i) => i !== index))}
              >
                {t("reports.filters.remove", { number: index + 1 })}
              </Button>
            </div>
          ))}
          <Button
            variant="secondary"
            disabledReason={
              disabled
                ? t("reports.filters.locked")
                : rows.length >= 500
                  ? t("reports.legacyPositions.limit")
                  : undefined
            }
            onClick={() =>
              save([
                ...rows,
                {
                  contract_external_id: "",
                  as_of: "",
                  currency: "",
                  contract_liability: "0.00",
                  unbilled_receivable: "0.00",
                  source_reference: "",
                },
              ])
            }
          >
            {t("reports.legacyPositions.add")}
          </Button>
        </>
      )}
    </fieldset>
  );
}

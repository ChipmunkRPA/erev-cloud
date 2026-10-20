import { t } from "../../lib/i18n/t";

export function ForecastEffectiveDates({
  start,
  end,
  onStart,
  onEnd,
  disabled = false,
}: {
  start: string;
  end: string;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="flex flex-col gap-2">
      <legend>{t("reports.inputs.dates")}</legend>
      <p>{t("reports.inputs.dateHelp")}</p>
      <label>
        {t("reports.inputs.from")}{" "}
        <input
          className="border p-2"
          type="datetime-local"
          step="0.001"
          value={start}
          onChange={(event) => onStart(event.target.value)}
        />
      </label>
      <label>
        {t("reports.inputs.to")}{" "}
        <input
          className="border p-2"
          type="datetime-local"
          step="0.001"
          value={end}
          onChange={(event) => onEnd(event.target.value)}
        />
      </label>
    </fieldset>
  );
}

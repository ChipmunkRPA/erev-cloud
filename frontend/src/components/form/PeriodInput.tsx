// Period input (DESIGN_SYSTEM DS-CMP-21): a popover list of accounting periods grouped by fiscal year,
// each with its E-04 state chip (SCREENS_B §0.4). Keyboard behaviour is the Select's.
import { StatusChip, chipFor } from "../ui/StatusChip";
import type { FieldControlProps } from "./Field";
import { Select } from "./Select";

export interface PeriodOption {
  /** The period key, for example `FY2026-P09`. */
  readonly key: string;
  /** DS-FMT-19 label, for example `Sep 2026`. */
  readonly label: string;
  readonly fiscalYear: string;
  /** E-04 `period_state`. */
  readonly state: string;
}

export interface PeriodInputProps {
  readonly control: FieldControlProps;
  readonly periods: readonly PeriodOption[];
  readonly value: string | null;
  readonly onChange: (key: string) => void;
  readonly invalid?: boolean;
}

export function PeriodInput({
  control,
  periods,
  value,
  onChange,
  invalid = false,
}: PeriodInputProps) {
  const states = new Map(periods.map((period) => [period.key, period.state]));
  return (
    <Select
      control={control}
      value={value}
      onChange={onChange}
      invalid={invalid}
      options={periods.map((period) => ({
        value: period.key,
        label: period.label,
        group: period.fiscalYear,
      }))}
      renderExtra={(option) => {
        const chip = chipFor("E-04", states.get(option.value) ?? "");
        return chip === null ? null : <StatusChip status={chip.status} />;
      }}
    />
  );
}

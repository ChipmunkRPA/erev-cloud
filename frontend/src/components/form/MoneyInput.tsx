// Money input (DESIGN_SYSTEM DS-CMP-21, DS-I18N-04; docs/dev-guide.md DG-FE-06, DG-FE-08). The value
// stays a string: typed text is parsed with parseMoneyInput on blur, which accepts parentheses, U+2212,
// hyphen-minus and locale grouping and refuses more decimals than the currency minor unit; a valid
// amount is then re-formatted. The ISO code is a trailing adornment, and the API decimal goes to onValue.
import { formatMoney, minorUnitOf, parseMoneyInput } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { cn } from "../ui/cn";
import { controlClass, type FieldControlProps } from "./Field";

export interface MoneyInputProps {
  readonly control: FieldControlProps;
  readonly currency: string;
  /** The typed text. */
  readonly value: string;
  readonly onChange: (text: string) => void;
  /** The API decimal string after a valid blur, or null when the field is empty or invalid. */
  readonly onValue?: ((decimal: string | null) => void) | undefined;
  /** The format error of the last blur, or null. */
  readonly onFormatError?: ((message: string | null) => void) | undefined;
  readonly invalid?: boolean;
  readonly readOnly?: boolean;
}

export function moneyInputError(text: string, currency: string): string | null {
  if (text.trim() === "") {
    return null;
  }
  const result = parseMoneyInput(text, currency);
  if (result.ok) {
    return null;
  }
  if (result.error === "invalid") {
    return t("common.form.money.invalid");
  }
  const minorUnit = minorUnitOf(currency);
  return minorUnit === 0
    ? t("common.form.money.noDecimals")
    : t("common.form.money.tooManyDecimals", { count: minorUnit });
}

export function MoneyInput({
  control,
  currency,
  value,
  onChange,
  onValue,
  onFormatError,
  invalid = false,
  readOnly = false,
}: MoneyInputProps) {
  const codeId = `${control.id}-currency`;
  const onBlur = () => {
    if (value.trim() === "") {
      onValue?.(null);
      onFormatError?.(null);
      return;
    }
    const result = parseMoneyInput(value, currency);
    if (result.ok) {
      onChange(formatMoney(result.value, currency, { variant: "cell" }));
      onValue?.(result.value);
      onFormatError?.(null);
    } else {
      onValue?.(null);
      onFormatError?.(moneyInputError(value, currency));
    }
  };
  return (
    <div className="relative flex items-center">
      <input
        {...control}
        aria-describedby={cn(control["aria-describedby"], codeId)}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        readOnly={readOnly}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className={cn(controlClass(invalid), "num-money pe-12 text-end")}
      />
      <span id={codeId} className="pointer-events-none absolute end-2.5 text-body-sm text-fg-3">
        {currency}
      </span>
    </div>
  );
}

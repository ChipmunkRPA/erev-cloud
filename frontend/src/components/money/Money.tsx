// <Money> (DESIGN_SYSTEM DS-CMP-26, DS-FMT-04 to DS-FMT-08, DS-FMT-29). Grid cells show figures only;
// inline and KPI values carry the ISO code. Under the parentheses style a non-negative cell reserves
// the width of ")" with `num-pos`, so decimal points align.
import { moneyParts, type MoneyVariant } from "../../lib/format";
import { NoValue, SignedFigures } from "./Num";

export interface MoneyProps {
  readonly value: string | null;
  readonly currency: string;
  readonly variant?: MoneyVariant;
  /** DS-FMT-31: a positive delta carries `+`. */
  readonly delta?: boolean;
}

export function Money({ value, currency, variant = "cell", delta = false }: MoneyProps) {
  if (value === null) {
    return <NoValue />;
  }
  const parts = moneyParts(value, currency, { variant, delta });
  const reserve = variant === "cell" && parts.style === "PARENTHESES" && parts.sign !== "negative";
  return (
    <span className={reserve ? "num-money num-pos" : "num-money"}>
      <SignedFigures parts={parts} />
    </span>
  );
}

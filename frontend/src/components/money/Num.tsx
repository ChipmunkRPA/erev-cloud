// <Num> and the shared signed-figure renderer (DESIGN_SYSTEM DS-CMP-26, DS-FMT-09 to DS-FMT-15,
// DS-FMT-21, DS-FMT-29). Signs are spoken words; parentheses and signs are hidden from assistive
// technology.
import {
  compactParts,
  MINUS_SIGN,
  NBSP,
  NO_VALUE,
  numberParts,
  percentParts,
  rateParts,
  type SignedParts,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";

export function SignedFigures({ parts }: { readonly parts: SignedParts }) {
  const negative = parts.sign === "negative";
  const parentheses = negative && parts.style === "PARENTHESES";
  return (
    <>
      {parts.code === null ? null : `${parts.code}${NBSP}`}
      {parts.sign === null ? null : (
        <>
          <span className="sr-only">{`${t(negative ? "common.number.minus" : "common.number.plus")} `}</span>
          <span aria-hidden="true">{negative ? (parentheses ? "(" : MINUS_SIGN) : "+"}</span>
        </>
      )}
      {parts.body}
      {parentheses ? <span aria-hidden="true">)</span> : null}
      {parts.suffix}
    </>
  );
}

/** DS-FMT-08: an em dash in `--fg-3` whose accessible text is "No value". */
export function NoValue() {
  return (
    <span className="text-fg-3">
      <span aria-hidden="true">{NO_VALUE}</span>
      <span className="sr-only">{t("common.number.noValue")}</span>
    </span>
  );
}

export type NumKind = "quantity" | "count" | "percent" | "share" | "pp" | "rate" | "fx" | "compact";

export interface NumProps {
  readonly value: string | number | null;
  readonly kind: NumKind;
  /** The price currency of a `rate`. */
  readonly currency?: string;
}

function partsOf(value: string | number, kind: NumKind, currency: string | undefined): SignedParts {
  if (kind === "quantity" || kind === "count") {
    return numberParts(value, { kind });
  }
  if (typeof value !== "string") {
    throw new Error(`<Num kind="${kind}"> needs a decimal string`);
  }
  switch (kind) {
    case "percent":
    case "share":
    case "pp":
      return percentParts(value, { kind });
    case "rate":
      return rateParts(
        value,
        currency === undefined ? { kind: "unit" } : { kind: "unit", currency },
      );
    case "fx":
      return rateParts(value, { kind: "fx" });
    case "compact":
      return compactParts(value);
  }
}

export function Num({ value, kind, currency }: NumProps) {
  if (value === null) {
    return <NoValue />;
  }
  return (
    <span className="num">
      <SignedFigures parts={partsOf(value, kind, currency)} />
    </span>
  );
}

// KPI strip proportion bar (DESIGN_SYSTEM DS-CH-05; DS-CMP-06): a 4 px neutral track and fill whose width
// is the API ratio of the value to its reference, capped at 100%. Zero or a negative ratio shows an
// empty track; above 100% the bar is full and the warning chip "Over <reference label>" follows. The bar
// is aria-hidden because the KPI's secondary line states the proportion. Ratios are compared on their
// digits and never become JavaScript numbers (DG-FE-08).
import { WarningCircle } from "../icons/registry";
import { ToneChip } from "../ui/StatusChip";

export interface ProportionBarProps {
  /** The API ratio of the value to its reference, a decimal string such as "0.462". */
  readonly ratio: string;
  /** The warning chip above 100%, for example "Over transaction price". */
  readonly overLabel: string;
}

const RATIO = /^(-?)(\d+)(?:\.(\d+))?$/;

/** Whether a non-negative decimal ratio exceeds 1, decided on its digits without floats. */
export function ratioAboveOne(ratio: string): boolean {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(ratio);
  if (match === null) {
    throw new Error(`Not a non-negative ratio: ${ratio}`);
  }
  const integer = (match[1] ?? "").replace(/^0+(?=\d)/, "");
  if (integer !== "0" && integer !== "1") {
    return true;
  }
  return integer === "1" && /[1-9]/.test(match[2] ?? "");
}

export function ProportionBar({ ratio, overLabel }: ProportionBarProps) {
  const match = RATIO.exec(ratio);
  if (match === null) {
    throw new Error(`Not a ratio: ${ratio}`);
  }
  const magnitude = ratio.replace(/^-/, "");
  const empty = match[1] === "-" || !/[1-9]/.test(magnitude);
  const over = !empty && ratioAboveOne(magnitude);
  const inlineSize = empty ? "0%" : over ? "100%" : `calc(${magnitude} * 100%)`;
  return (
    <>
      <span
        aria-hidden="true"
        data-kpi-bar=""
        className="block h-1 w-full overflow-hidden rounded-full bg-active"
      >
        <span className="block h-full rounded-full bg-fg-2" style={{ inlineSize }} />
      </span>
      {over ? <ToneChip tone="warning" icon={WarningCircle} label={overLabel} /> : null}
    </>
  );
}

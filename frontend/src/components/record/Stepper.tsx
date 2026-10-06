// Stepper (DESIGN_SYSTEM DS-CMP-18 anatomy), for every multi-step flow: `nav` named "<flow> steps"
// around an `ol`. Each item has a 20 px marker, the label and a status caption. The current item carries
// aria-current="step", completed steps link back, and future steps are not interactive. The accessible
// name states position, label and the caption, or the state word when there is no caption
// ("Step 3 of 6, Validate, 12 errors in 9 rows").
import { Link } from "react-router";

import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { CheckCircle, Circle, type Icon, Minus, XCircle } from "../icons/registry";
import { cn } from "../ui/cn";

export type StepState = "complete" | "current" | "error" | "pending" | "skipped";

export interface Step {
  readonly id: string;
  readonly label: string;
  readonly state: StepState;
  /** The status caption, for example "1,204 rows" or "12 errors in 9 rows". */
  readonly caption?: string | undefined;
  /** The route of a completed step; a completed step with a route is a link back. */
  readonly to?: string | undefined;
}

export interface StepperProps {
  /** The `nav` name, for example "Import steps" or "Modification steps". */
  readonly label: string;
  readonly steps: readonly Step[];
  /** The step the page shows; its item carries aria-current="step". */
  readonly currentId: string;
}

const MARKER: Readonly<Partial<Record<StepState, { readonly icon: Icon; readonly tone: string }>>> =
  {
    complete: { icon: CheckCircle, tone: "text-positive-fg" },
    error: { icon: XCircle, tone: "text-negative-fg" },
    pending: { icon: Circle, tone: "text-fg-3" },
    skipped: { icon: Minus, tone: "text-fg-3" },
  };

function Marker({ state, position }: { readonly state: StepState; readonly position: number }) {
  const marker = MARKER[state];
  if (marker === undefined) {
    return (
      <span className="num flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-solid text-caption font-medium text-on-accent">
        {formatNumber(position)}
      </span>
    );
  }
  const MarkerIcon = marker.icon;
  return <MarkerIcon size={20} data-state={state} className={cn("shrink-0", marker.tone)} />;
}

export function Stepper({ label, steps, currentId }: StepperProps) {
  const total = formatNumber(steps.length);
  return (
    <nav aria-label={label}>
      <ol className="flex flex-wrap items-start gap-x-6 gap-y-3">
        {steps.map((step, index) => {
          const position = index + 1;
          const name = t("common.stepper.name", {
            position: formatNumber(position),
            total,
            label: step.label,
            status: step.caption ?? t(`common.stepper.state.${step.state}`),
          });
          const content = (
            <>
              <span className="sr-only">{name}</span>
              <span aria-hidden="true" className="flex items-start gap-2">
                <Marker state={step.state} position={position} />
                <span className="flex min-w-0 flex-col">
                  <span
                    className={cn(
                      "text-body-sm font-medium",
                      step.state === "pending" || step.state === "skipped"
                        ? "text-fg-3"
                        : "text-fg-1",
                    )}
                  >
                    {step.label}
                  </span>
                  {step.caption === undefined ? null : (
                    <span className="text-caption text-fg-3">{step.caption}</span>
                  )}
                </span>
              </span>
            </>
          );
          return (
            <li
              key={step.id}
              aria-current={step.id === currentId ? "step" : undefined}
              className="min-w-0"
            >
              {step.state === "complete" && step.to !== undefined ? (
                <Link to={step.to} className="block rounded-sm hover:underline">
                  {content}
                </Link>
              ) : (
                <span className="block">{content}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// Five-step contract tracker (DESIGN_SYSTEM DS-CMP-17; REQ-UX-015): `ol aria-label="ASC 606 steps"` of
// five segment buttons across the record header, joined by a 1 px line between icons. A segment toggles
// the single evidence region below the row; Esc collapses it and returns focus to its segment. The state
// word is always in the accessible name ("Step 3, Transaction price, complete, USD 1,200,000.00") and in
// the visible status line unless the step is complete. Figures in evidence panels are Explain triggers.
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import {
  CheckCircle,
  Circle,
  HourglassMedium,
  type Icon,
  WarningCircle,
  XCircle,
} from "../icons/registry";
import { cn } from "../ui/cn";

export type TrackerState = "complete" | "attention" | "blocked" | "review" | "notStarted";

export interface TrackerStep {
  readonly state: TrackerState;
  /** The status line, for example "USD 1,200,000.00" or "4 obligations · 1 material right". */
  readonly status: string;
  /**
   * A read the status line needs has not answered: the step shows no status and is marked busy, so
   * that nothing partial is read or captured (SCREENS §4.1.3 rev 1.29).
   */
  readonly busy?: boolean | undefined;
  /** The evidence panel of the step. */
  readonly evidence: ReactNode;
}

export interface FiveStepTrackerProps {
  /** Contract, Obligations, Transaction price, Allocation and Recognition, in that order. */
  readonly steps: readonly TrackerStep[];
  readonly loading?: boolean;
  /** The expanded step index when controlled (for example by `?step=<n>`); null for none. */
  readonly open?: number | null | undefined;
  readonly onOpenChange?: ((open: number | null) => void) | undefined;
  /** The screen id of SCR-TID-04 `tracker`, `tracker-step-<n>` and `evidence-<n>`, for example "SF-03". */
  readonly testIdScreen?: string | undefined;
}

export const TRACKER_STEPS = [
  "contract",
  "obligations",
  "transactionPrice",
  "allocation",
  "recognition",
] as const;

const STATE_ICON: Readonly<Record<TrackerState, { readonly icon: Icon; readonly tone: string }>> = {
  complete: { icon: CheckCircle, tone: "text-positive-fg" },
  attention: { icon: WarningCircle, tone: "text-warning-fg" },
  blocked: { icon: XCircle, tone: "text-negative-fg" },
  review: { icon: HourglassMedium, tone: "text-info-fg" },
  notStarted: { icon: Circle, tone: "text-fg-3" },
};

// Copy defects throw in development and tests; a production build still renders.
const STRICT = import.meta.env.DEV || import.meta.env.MODE === "test";

export function FiveStepTracker({
  steps,
  loading = false,
  open: controlled,
  onOpenChange,
  testIdScreen,
}: FiveStepTrackerProps) {
  const baseId = useId();
  const [uncontrolled, setUncontrolled] = useState<number | null>(null);
  const open = controlled === undefined ? uncontrolled : controlled;
  const setOpen = (next: number | null) => {
    if (controlled === undefined) {
      setUncontrolled(next);
    }
    onOpenChange?.(next);
  };
  const testId = (suffix: string) =>
    testIdScreen === undefined ? undefined : `${testIdScreen}-${suffix}`;
  const root = useRef<HTMLDivElement>(null);
  const segments = useRef<(HTMLButtonElement | null)[]>([]);

  if (STRICT && !loading && steps.length !== TRACKER_STEPS.length) {
    throw new Error("The five-step tracker needs exactly five steps (DS-CMP-17)");
  }

  useEffect(() => {
    const element = root.current;
    if (element === null || open === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        if (controlled === undefined) {
          setUncontrolled(null);
        }
        onOpenChange?.(null);
        segments.current[open]?.focus();
      }
    };
    element.addEventListener("keydown", onKeyDown);
    return () => element.removeEventListener("keydown", onKeyDown);
  }, [open, controlled, onOpenChange]);

  const label = t("common.tracker.label");
  if (loading) {
    return (
      <ol
        aria-label={label}
        aria-busy="true"
        data-testid={testId("tracker")}
        className="grid grid-cols-5 gap-3"
      >
        {TRACKER_STEPS.map((key) => (
          <li key={key}>
            <span aria-hidden="true" data-skeleton="" className="block h-12 rounded-sm bg-subtle" />
          </li>
        ))}
      </ol>
    );
  }

  const openStep = open === null ? undefined : steps[open];
  return (
    <div ref={root} data-testid={testId("tracker")} className="flex flex-col">
      <ol aria-label={label} className="grid grid-cols-5">
        {TRACKER_STEPS.map((key, index) => {
          const step = steps[index];
          if (step === undefined) {
            return null;
          }
          const stepLabel = t(`common.tracker.step.${key}`);
          const { icon: StateIcon, tone } = STATE_ICON[step.state];
          const expanded = open === index;
          const busy = step.busy === true;
          let statusLine = step.status;
          if (busy) {
            statusLine = "";
          } else if (step.state !== "complete") {
            const visible = t(`common.tracker.visible.${step.state}`);
            statusLine = step.status === "" ? visible : `${visible} · ${step.status}`;
          }
          const nameParams = {
            position: formatNumber(index + 1),
            label: stepLabel,
            state: t(`common.tracker.state.${step.state}`),
            status: step.status,
          };
          return (
            <li key={key} aria-busy={busy ? true : undefined} className="flex min-w-0">
              <button
                ref={(element) => {
                  segments.current[index] = element;
                }}
                type="button"
                data-testid={testId(`tracker-step-${String(index + 1)}`)}
                aria-expanded={expanded}
                aria-controls={`${baseId}-evidence`}
                aria-label={
                  busy || step.status === ""
                    ? t("common.tracker.nameNoStatus", nameParams)
                    : t("common.tracker.name", nameParams)
                }
                onClick={() => setOpen(expanded ? null : index)}
                className={cn(
                  "flex w-full min-w-0 flex-col items-start gap-1 border-b-2 px-3 py-2 text-start hover:bg-hover",
                  expanded ? "border-accent-solid" : "border-transparent",
                )}
              >
                <span aria-hidden="true" className="flex w-full items-center gap-2">
                  <StateIcon size={16} className={cn("shrink-0", tone)} />
                  {/* D-87 L6-4-Q-7: labels and figures wrap in a narrow column (beside the docked
                      Explain panel) instead of clipping. */}
                  <span className="break-words text-body-sm font-medium text-fg-1">
                    {`${formatNumber(index + 1)} ${stepLabel}`}
                  </span>
                  {index < TRACKER_STEPS.length - 1 ? (
                    <span className="h-px min-w-0 flex-1 bg-[var(--border-default)]" />
                  ) : null}
                </span>
                {busy ? (
                  <span
                    aria-hidden="true"
                    data-skeleton=""
                    className="block h-4 w-24 rounded-sm bg-subtle"
                  />
                ) : (
                  <span
                    aria-hidden="true"
                    className="max-w-full break-words text-caption text-fg-3"
                  >
                    {statusLine}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ol>
      {openStep === undefined || open === null ? null : (
        <div
          id={`${baseId}-evidence`}
          data-testid={testId(`evidence-${String(open + 1)}`)}
          role="region"
          aria-label={t(`common.tracker.step.${TRACKER_STEPS[open] ?? "contract"}`)}
          className="border-t border-hairline p-[var(--panel-pad)]"
        >
          {openStep.evidence}
        </div>
      )}
    </div>
  );
}

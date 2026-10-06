// Skeleton (DESIGN_SYSTEM DS-CMP-30; SCREENS SCR-ST-01; docs/dev-guide.md DG-FE-14). Static blocks
// shaped like the final content, shown only after 150 ms to avoid flashes; no shimmer (DS-MOT-02).
// The region is aria-busy at once and carries the visually hidden "Loading <region name>".
import { useEffect, useState } from "react";

import { t } from "../../lib/i18n/t";

export const SKELETON_DELAY_MS = 150;

export type SkeletonShape = "text" | "kpi" | "rows";

export interface SkeletonProps {
  /** The region name spoken as "Loading <region name>". */
  readonly region: string;
  readonly shape?: SkeletonShape;
  readonly count?: number;
}

// Text lines vary between 60% and 90% of the width.
const LINE_WIDTHS = ["w-9/10", "w-3/4", "w-4/5", "w-3/5"] as const;

function Block({ shape, index }: { readonly shape: SkeletonShape; readonly index: number }) {
  if (shape === "kpi") {
    return <span className="block h-6 w-16 rounded-sm bg-subtle" />;
  }
  if (shape === "rows") {
    return <span className="block h-[var(--row-h)] w-full rounded-sm bg-subtle" />;
  }
  return (
    <span
      className={`block h-3 rounded-sm bg-subtle ${LINE_WIDTHS[index % LINE_WIDTHS.length] ?? ""}`}
    />
  );
}

export function Skeleton({ region, shape = "text", count = 3 }: SkeletonProps) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), SKELETON_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div aria-busy="true" className="flex flex-col gap-2">
      <span className="sr-only">{t("common.loading.region", { region })}</span>
      {visible ? (
        <div
          aria-hidden="true"
          data-skeleton=""
          className={shape === "kpi" ? "flex gap-4" : "flex flex-col gap-2"}
        >
          {Array.from({ length: count }, (_, index) => (
            <Block key={index} shape={shape} index={index} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

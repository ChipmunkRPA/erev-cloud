// Narrow viewport notice (X:narrow-viewport; SCREENS §0.4 placement row; SCREENS_B §12.4; PRD NFR-32;
// DESIGN_SYSTEM DS-SP-04). Below 1024 px CSS width, every route except SF-01, SF-12 and the SF-22
// family renders this start-aligned notice inside `main` instead of the page, with links to Home and
// Approvals, which work on smaller screens.
import { type ReactNode, useSyncExternalStore } from "react";
import { Link } from "react-router";

import { t } from "../../lib/i18n/t";

export const NARROW_VIEWPORT_PX = 1024;

/** SCREENS_B §12.4 and NFR-32: the SF ids that stay usable below 1024 px. */
export const NARROW_EXEMPT_SF: ReadonlySet<string> = new Set(["SF-01", "SF-12", "SF-22"]);

function subscribe(onChange: () => void): () => void {
  window.addEventListener("resize", onChange);
  return () => {
    window.removeEventListener("resize", onChange);
  };
}

export function useNarrowViewport(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.innerWidth < NARROW_VIEWPORT_PX,
    () => false,
  );
}

export interface NarrowViewportProps {
  /** The SF id of the current route (`handle.sf`). */
  readonly sf: string | null;
  /** The landing route (BS-D-08). */
  readonly homePath: string;
  /** `/approvals` when that route is built, else null (BUILD_SPEC XR-14). */
  readonly approvalsPath: string | null;
  readonly children: ReactNode;
}

const LINK_CLASS = "text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline";

export function NarrowViewport({ sf, homePath, approvalsPath, children }: NarrowViewportProps) {
  const narrow = useNarrowViewport();
  if (!narrow || (sf !== null && NARROW_EXEMPT_SF.has(sf))) {
    return children;
  }
  return (
    <div
      data-testid="X-empty-narrow-viewport"
      className="flex max-w-120 flex-col items-start gap-2 pt-12"
    >
      <h1 tabIndex={-1} className="text-title-md text-fg-1">
        {t("errors.narrowViewport.title")}
      </h1>
      <p className="text-body-sm text-fg-2">{t("errors.narrowViewport.description")}</p>
      <div className="mt-2 flex flex-wrap items-center gap-4">
        <Link to={homePath} className={LINK_CLASS}>
          {t("errors.narrowViewport.goHome")}
        </Link>
        {approvalsPath === null ? null : (
          <Link to={approvalsPath} className={LINK_CLASS}>
            {t("errors.narrowViewport.goApprovals")}
          </Link>
        )}
      </div>
    </div>
  );
}

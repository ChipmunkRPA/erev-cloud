// App shell (DESIGN_SYSTEM DS-CMP-01; SCREENS §1.1; DS-A11Y-09; DS-BR-06). Two columns: the icon rail,
// then the top bar, the global banner region and `main`. The skip link is the first focusable
// element. The document title is `<page title> · eRev Cloud`; a route change moves focus to the page
// `h1` (waiting for a page that renders its heading later) and announces the title politely. The
// first render sets the title only. The shell also mounts the About dialog (SF-27, `dialog=about`)
// and the session expiry warning (X:session-expiring).
import { type MouseEvent, type ReactNode, useEffect, useRef } from "react";
import { Outlet, type UIMatch, useLocation, useMatches } from "react-router";

import { announce } from "../../lib/a11y/announce";
import { t } from "../../lib/i18n/t";
import { NarrowViewport } from "../errors/NarrowViewport";
import { paramsMatch } from "../errors/NotFound";
import { AboutDialog } from "./AboutDialog";
import { IconRail } from "./IconRail";
import { SandboxBanner } from "./SandboxBanner";
import { SessionExpiringModal } from "./SessionExpiringModal";
import { TopBar } from "./TopBar";

/** SCREENS SCR-IA-06: `sf` is the PRD SF id, or `X` for an extra screen (SCR-TID-02). */
export interface RouteHandle {
  readonly sf: string;
  readonly screen: string;
  readonly titleKey: string;
}

export function isRouteHandle(value: unknown): value is RouteHandle {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const fields = value as Record<string, unknown>;
  return (
    typeof fields.sf === "string" &&
    typeof fields.screen === "string" &&
    typeof fields.titleKey === "string"
  );
}

/** The handle of the deepest matched route that has one. */
export function currentHandle(matches: readonly UIMatch[]): RouteHandle | null {
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const handle = matches[index]?.handle;
    if (isRouteHandle(handle)) {
      return handle;
    }
  }
  return null;
}

const APPROVALS_PATH = "/approvals";

export interface AppShellProps {
  /** The built route paths (the rail and the narrow-viewport links show built routes only). */
  readonly built: ReadonlySet<string>;
  /** The landing route (BS-D-08). */
  readonly homePath: string;
  /** DS-CMP-01 top bar items; the default is the WEB-9 TopBar. */
  readonly topBar?: ReactNode;
  /** The global banner region: at most one banner (DS-CMP-29); the default is the sandbox banner. */
  readonly banner?: ReactNode;
  /** SCR-IA-01 Approvals badge. */
  readonly approvalsPending?: number | null;
}

export function AppShell({
  built,
  homePath,
  topBar,
  banner,
  approvalsPending = null,
}: AppShellProps) {
  const matches = useMatches();
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const shownPath = useRef<string | null>(null);

  const handle = currentHandle(matches);
  const params = matches.at(-1)?.params ?? {};
  const pageTitle = !paramsMatch(params)
    ? t("errors.notFound.documentTitle")
    : handle === null
      ? null
      : t(handle.titleKey);
  const documentTitle =
    pageTitle === null ? t("shell.productName") : t("shell.documentTitle", { title: pageTitle });

  useEffect(() => {
    document.title = documentTitle;
  }, [documentTitle]);

  useEffect(() => {
    if (shownPath.current === null || shownPath.current === pathname) {
      shownPath.current = pathname;
      return undefined;
    }
    shownPath.current = pathname;
    if (pageTitle !== null) {
      announce(pageTitle, "polite");
    }
    const region = main.current;
    if (region === null) {
      return undefined;
    }
    const focusHeading = (): boolean => {
      const heading = region.querySelector("h1");
      if (heading === null) {
        return false;
      }
      if (!heading.hasAttribute("tabindex")) {
        heading.setAttribute("tabindex", "-1");
      }
      heading.focus();
      return true;
    };
    if (focusHeading()) {
      return undefined;
    }
    const observer = new MutationObserver(() => {
      if (focusHeading()) {
        observer.disconnect();
      }
    });
    observer.observe(region, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
    };
  }, [pathname, pageTitle]);

  const skipToMain = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    main.current?.focus();
  };

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas text-fg-1">
      <a
        href="#main"
        onClick={skipToMain}
        className="sr-only rounded-md bg-surface px-3 py-2 text-body-sm font-medium text-fg-1 shadow-popover focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-[var(--z-popover)]"
      >
        {t("shell.skipLink")}
      </a>
      <IconRail
        built={built}
        activeScreen={handle?.screen ?? null}
        approvalsPending={approvalsPending}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative flex h-[var(--topbar-h)] shrink-0 items-center gap-3 border-b border-hairline bg-surface px-3">
          {topBar === undefined ? <TopBar built={built} homePath={homePath} /> : topBar}
        </header>
        {banner === null ? null : (
          <div className="shrink-0">{banner === undefined ? <SandboxBanner /> : banner}</div>
        )}
        <main
          id="main"
          ref={main}
          tabIndex={-1}
          // `relative` (D-87 L6-4-Q-13): `main` is the containing block, so visually hidden text of a
          // page stays inside the scrolling region instead of extending the document below the shell.
          className="relative min-h-0 flex-1 overflow-auto p-[var(--gutter)]"
        >
          <NarrowViewport
            sf={handle?.sf ?? null}
            homePath={homePath}
            approvalsPath={built.has(APPROVALS_PATH) ? APPROVALS_PATH : null}
          >
            <Outlet />
          </NarrowViewport>
        </main>
      </div>
      <AboutDialog />
      <SessionExpiringModal />
    </div>
  );
}

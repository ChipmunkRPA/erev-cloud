// Route table test support (docs/dev-guide.md DG-FE-18): the app route table in a memory router with
// the providers and a cached session, so suites exercise the real guards, shell and placements.
import type { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { type ReactNode, StrictMode } from "react";
import { createMemoryRouter, type RouteObject, RouterProvider } from "react-router";
import { beforeEach } from "vitest";

import type { Session, SessionState } from "../app/auth/RequireSession";
import { AppProviders, createQueryClient } from "../app/providers";
import { buildRoutes, guardLeavingPages, type RouteTableOptions } from "../app/router";
import type { Me } from "../lib/api/queries/me";
import { unreadBadgeKey, type UnreadBadge } from "../lib/api/queries/notifications";
import { queryKeys } from "../lib/api/query-keys";
import { t } from "../lib/i18n/t";

export type MemoryRouter = ReturnType<typeof createMemoryRouter>;

const NativeRequest = globalThis.Request;

/** True when Node's Request refuses the signal (a jsdom AbortSignal). */
function refusedSignal(signal: AbortSignal | null | undefined): boolean {
  if (signal === undefined || signal === null) {
    return false;
  }
  try {
    return new NativeRequest("http://localhost/", { signal }).signal === undefined;
  } catch {
    return true;
  }
}

// The jsdom environment replaces AbortController and AbortSignal, and Node's Request refuses a jsdom
// signal, which a data router passes for every navigation (vitest-dev/vitest#4043). The bridge builds
// the Request without that signal and exposes the jsdom signal on it, so aborts still reach loaders.
class JsdomSignalRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init: RequestInit = {}) {
    const { signal, ...rest } = init;
    const foreign = refusedSignal(signal);
    super(input, foreign ? rest : init);
    if (foreign) {
      Object.defineProperty(this, "signal", { configurable: true, value: signal });
    }
  }
}

/** Installs the Request bridge for suites that create a data router under jsdom. */
export function installRouterRequest(): void {
  globalThis.Request = JsdomSignalRequest;
}

installRouterRequest();

/**
 * Evaluates the lazily loaded modules of the named routes before a suite's first render (F-ADM Q21).
 *
 * A route object's `lazy` runs `import()` on first match, so the first test of a suite pays the
 * module evaluation of the whole screen graph inside its `findBy` window (about 300 ms alone, 400 to
 * 700 ms while other suites share the CPU, and over the 1,000 ms default under load). The import is
 * cached per worker, so the data router's own `lazy` call afterwards resolves at once. Call from
 * `beforeAll` with the ids of the routes the suite renders.
 */
export async function preloadScreens(
  routes: readonly RouteObject[],
  ids: readonly string[],
): Promise<void> {
  const missing = ids.filter((id) => !routes.some((route) => route.id === id));
  if (missing.length > 0) {
    throw new Error(`preloadScreens: unknown route ids ${missing.join(", ")}`);
  }
  // React Router types `lazy` as a function or a per-property loader object; the route table uses
  // the function form.
  await Promise.all(
    routes
      .filter((route) => ids.includes(route.id ?? ""))
      .map((route) => (typeof route.lazy === "function" ? route.lazy() : undefined)),
  );
}

/** An API-S-Session of a signed-in, MFA-verified user with an active workspace. */
export function signedInSession(overrides: Partial<Session> = {}): Session {
  return {
    authenticated: true,
    user: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      email: "maya@example.test",
      display_name: "Maya Chen",
    },
    active_tenant: {
      id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
      code: "avenmoor",
      display_name: "Avenmoor",
      kind: "production",
    },
    mfa_verified_at: "2026-09-13T08:00:00Z",
    mfa_required: false,
    mfa_enrolment_required: false,
    idle_expires_at: "2026-09-13T09:00:00Z",
    absolute_expires_at: "2026-09-13T20:00:00Z",
    capabilities: { identity_providers: [] },
    csrf_token: "csrf-test-token",
    ...overrides,
  };
}

export const MEMBERSHIP_ID = "3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d";

/**
 * An API-S-Me of the signed-in user of `signedInSession`, with one production workspace. Unless a
 * test states `permission_scopes` (04 §16.12: per permission, "*" or the entities it is held for),
 * every permission of the result is held for all entities.
 */
export function signedInMe(overrides: Partial<Me> = {}): Me {
  const me: Omit<Me, "permission_scopes"> = {
    user: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      email: "maya@example.test",
      display_name: "Maya Chen",
      status: "ACTIVE",
    },
    memberships: [
      {
        membership_id: MEMBERSHIP_ID,
        tenant: {
          id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
          code: "avenmoor",
          display_name: "Avenmoor",
          kind: "production",
          is_demo: false,
          status: "ACTIVE",
          source_tenant_id: null,
          source_known_at: null,
        },
        status: "ACTIVE",
        last_opened_at: "2026-09-13T08:00:00Z",
      },
    ],
    active_membership_id: MEMBERSHIP_ID,
    permissions: ["contract.read", "contract.create"],
    entity_scope: "*",
    mfa: { enrolled: true, verified_at: "2026-09-13T08:00:00Z" },
    preferences: {
      theme: "SYSTEM",
      density: "COMFORTABLE",
      format_locale: "en-US",
      shortcuts_enabled: true,
      tour_completed: null,
    },
    tenant_settings: {
      negative_number_style: "PARENTHESES",
      default_locale: "en-US",
      ai_enabled: false,
    },
    engine_release: {
      engine_version: "1.0.0",
      build_sha: "3f9a1c22e41b7d0c5a6f8e9d0b1c2a3f4e5d6c7b",
      schema_revision: "e41",
    },
    unread_notification_count: 0,
    ...overrides,
  };
  return {
    ...me,
    permission_scopes:
      overrides.permission_scopes ??
      Object.fromEntries(me.permissions.map((code): [string, "*"] => [code, "*"])),
  };
}

/** The notifications badge with nothing unread. */
export const NO_UNREAD: UnreadBadge = { count: 0, capped: false, newest: null };

/** A route object as a screen item adds it; its page `h1` is the text of the title key. */
export function probeRoute(id: string, path: string, titleKey: string): RouteObject {
  const sf = id.startsWith("X:") ? "X" : (id.split(":", 1)[0] ?? id);
  return {
    id,
    path,
    handle: { sf, screen: id, titleKey },
    element: <h1 tabIndex={-1}>{t(titleKey)}</h1>,
  };
}

export interface RenderAppOptions extends Omit<RouteTableOptions, "queryClient"> {
  /** The cached session; null leaves the cache empty, so the loader calls `GET /session`. */
  readonly session?: SessionState | null;
  /** The cached `GET /me` of the top bar; null leaves the cache empty. */
  readonly me?: Me | null;
  /** The cached notifications badge; null leaves the cache empty. */
  readonly badge?: UnreadBadge | null;
  readonly strict?: boolean;
}

export interface RenderedApp {
  readonly router: MemoryRouter;
  readonly queryClient: QueryClient;
}

export function renderApp(entry: string, options: RenderAppOptions = {}): RenderedApp {
  const { session, me, badge, strict = false, ...tables } = options;
  const queryClient = createQueryClient();
  seedCaches(queryClient, { session, me, badge });
  const router = guardLeavingPages(
    createMemoryRouter(buildRoutes({ ...tables, queryClient }), {
      initialEntries: [entry],
    }),
  );
  const app = (
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  );
  render(strict ? <StrictMode>{app}</StrictMode> : app);
  return { router, queryClient };
}

export interface CachedReads {
  readonly session?: SessionState | null | undefined;
  readonly me?: Me | null | undefined;
  readonly badge?: UnreadBadge | null | undefined;
}

/**
 * Seeds the reads of the shell: the session, `GET /me` and the notifications badge. Fresh cached data
 * issues no request; undefined seeds the signed-in default and null leaves the cache empty.
 */
export function seedCaches(queryClient: QueryClient, reads: CachedReads): void {
  if (reads.session !== null) {
    queryClient.setQueryData(queryKeys.session(), reads.session ?? signedInSession());
  }
  if (reads.me !== null) {
    queryClient.setQueryData(queryKeys.me(), reads.me ?? signedInMe());
  }
  if (reads.badge !== null) {
    queryClient.setQueryData(unreadBadgeKey(), reads.badge ?? NO_UNREAD);
  }
}

export interface RenderWithAppOptions extends CachedReads {
  /** The memory router entry; every path renders `ui`. */
  readonly entry?: string;
}

/** Renders one shell part inside the providers and a memory router whose every path renders it. */
export function renderWithApp(ui: ReactNode, options: RenderWithAppOptions = {}): RenderedApp {
  const { entry = "/home", ...reads } = options;
  const queryClient = createQueryClient();
  seedCaches(queryClient, reads);
  const router = createMemoryRouter([{ path: "*", element: ui }], { initialEntries: [entry] });
  render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { router, queryClient };
}

/** An in-memory Storage: Node's own `localStorage` global can shadow the jsdom one. */
export function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => {
      values.clear();
    },
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

/** Gives each test of the calling file a fresh in-memory `localStorage` and default theme attributes. */
export function installMemoryStorage(): void {
  beforeEach(() => {
    Object.defineProperty(window, "localStorage", { configurable: true, value: memoryStorage() });
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.setAttribute("data-density", "comfortable");
  });
}

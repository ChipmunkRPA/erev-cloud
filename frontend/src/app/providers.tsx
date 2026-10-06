// Application providers (docs/dev-guide.md §8.1; DG-FE-04, DG-FE-10, DG-FE-11, DG-FE-13).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  type RefObject,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ToastProvider } from "../components/feedback/Toast";
import { ICON_DEFAULTS, IconContext } from "../components/icons/registry";
import { registerLiveRegions } from "../lib/a11y/announce";
import { UI_LOCALE } from "../lib/i18n/t";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
    },
  });
}

interface ChildrenProps {
  readonly children: ReactNode;
}

// DS-I18N-02: `format_locale` comes from the user profile, else the browser language.
export interface I18nValue {
  readonly uiLocale: string;
  readonly formatLocale: string;
  readonly setProfileLocale: (locale: string | null) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: ChildrenProps) {
  const [profileLocale, setProfileLocale] = useState<string | null>(null);
  const value = useMemo<I18nValue>(
    () => ({
      uiLocale: UI_LOCALE,
      formatLocale: profileLocale ?? navigator.language,
      setProfileLocale,
    }),
    [profileLocale],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n needs I18nProvider");
  }
  return value;
}

// DG-FE-13: public/theme-init.js applies the stored choices before first paint; this provider only
// toggles the attributes and storage afterwards. Components never branch on the theme.
export type ThemePreference = "light" | "dark" | "system";
export type Density = "comfortable" | "compact";

export interface ThemeValue {
  readonly theme: ThemePreference;
  readonly density: Density;
  readonly setTheme: (theme: ThemePreference) => void;
  readonly setDensity: (density: Density) => void;
}

const THEME_KEY = "erev.theme";
const DENSITY_KEY = "erev.density";

const ThemeContext = createContext<ThemeValue | null>(null);

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // Storage can be unavailable (privacy mode); the choice then lasts for this page only.
  }
}

export function ThemeProvider({ children }: ChildrenProps) {
  const [theme, setThemeState] = useState<ThemePreference>(() => {
    const stored = readStorage(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  });
  const [density, setDensityState] = useState<Density>(() =>
    readStorage(DENSITY_KEY) === "compact" ? "compact" : "comfortable",
  );

  useLayoutEffect(() => {
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
  }, [theme]);

  useLayoutEffect(() => {
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  const value = useMemo<ThemeValue>(
    () => ({
      theme,
      density,
      setTheme: (next) => {
        writeStorage(THEME_KEY, next === "system" ? null : next);
        setThemeState(next);
      },
      setDensity: (next) => {
        writeStorage(DENSITY_KEY, next);
        setDensityState(next);
      },
    }),
    [theme, density],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (value === null) {
    throw new Error("useTheme needs ThemeProvider");
  }
  return value;
}

function speaker(ref: RefObject<HTMLDivElement | null>): (message: string) => void {
  return (message) => {
    const region = ref.current;
    if (region !== null) {
      // Clearing first makes assistive technology read a repeated message again.
      region.textContent = "";
      region.textContent = message;
    }
  };
}

// DS-A11Y-08: one polite and one assertive region at the shell root.
export function AnnouncerProvider({ children }: ChildrenProps) {
  const polite = useRef<HTMLDivElement>(null);
  const assertive = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => registerLiveRegions(speaker(polite), speaker(assertive)), []);
  return (
    <>
      {children}
      <div ref={polite} role="status" aria-live="polite" aria-atomic="true" className="sr-only" />
      <div
        ref={assertive}
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
      />
    </>
  );
}

export interface AppProvidersProps extends ChildrenProps {
  readonly queryClient?: QueryClient;
}

export function AppProviders({ children, queryClient }: AppProvidersProps) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <QueryClientProvider client={client}>
      <I18nProvider>
        <ThemeProvider>
          <AnnouncerProvider>
            {/* DS-ICO-04: 16 px regular icons by default; DS-CMP-22: one toast region at the root. */}
            <IconContext.Provider value={ICON_DEFAULTS}>
              <ToastProvider>{children}</ToastProvider>
            </IconContext.Provider>
          </AnnouncerProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

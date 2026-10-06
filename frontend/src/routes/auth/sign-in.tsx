// SF-22 Sign in (SCREENS_B §12.1; SCREENS §0.4 RT-01, §0.5 SCR-URL-30; DESIGN_SYSTEM DS-BR-03,
// DS-A11Y-17; 04 API-R-01). Password sign-in with lockout and rate-limit copy, OIDC sign-in buttons
// from the `GET /session` capabilities, and the session-expired notice. The page renders outside the
// shell: a header bar with the wordmark and a start-aligned 440 px column. A successful sign-in stores
// the answered session in the query cache; an authenticated session (after sign-in, or after the OIDC
// callback redirects here) leaves for the MFA challenge, SF-23:select while no workspace is open, the
// safe `next` path or the landing route.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useId, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { fetchSession, MFA_CHALLENGE_PATH, type SessionState } from "../../app/auth/RequireSession";
import { SELECT_WORKSPACE_PATH } from "../../app/shell/TenantSwitcher";
import { Banner } from "../../components/feedback/Banner";
import { controlClass, Field, type FieldControlProps, fieldId } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { send } from "../../lib/api/client";
import { type ApiProblem, fieldErrorsOf, readProblem } from "../../lib/api/problems";
import { queryKeys } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";

type SessionLoginOut = components["schemas"]["SessionLoginOut"];

export const LOGIN_PATH = "/api/v1/session/login";
export { MFA_CHALLENGE_PATH };
/** RT-111 SF-22:password-reset, the target of "Forgot password?" (SCREENS_B §12.1 wireframe; WEB-14). */
export const FORGOT_PASSWORD_PATH = "/password/reset";
/** SCR-URL-30: the only accepted `reason`. */
export const SESSION_EXPIRED_REASON = "session-expired";
/**
 * 04 `platform.session_idle_minutes` default (T-PLT-08). A signed-out page has no workspace, so the
 * notice states the default (L3-3-Q-1).
 */
export const SESSION_IDLE_MINUTES = 30;

/** SCREENS SCR-URL-30: a same-origin path that begins with "/" and not with "//"; else null. */
export function safeNext(next: string | null): string | null {
  if (next === null || !next.startsWith("/") || next.startsWith("//")) {
    return null;
  }
  const origin = globalThis.location.origin;
  // "/\host" resolves to another origin in browsers, so the resolved origin is checked as well.
  return new URL(next, origin).origin === origin ? next : null;
}

/** The OIDC start route of a provider (04 API-R-01 `GET /session/oidc/{provider}/start`). */
export function oidcStartPath(code: string): string {
  return `/api/v1/session/oidc/${encodeURIComponent(code)}/start`;
}

/**
 * Where an authenticated session goes: the MFA challenge first; SF-23:select while no workspace is
 * open, because sign-in opens only a user's single ACTIVE membership and every other screen acts in
 * a workspace (D-83); then `next`, else `/` (landing).
 */
export function destinationAfterSignIn(session: SessionState, next: string | null): string {
  if (session.authenticated && session.mfa_required) {
    const search = next === null ? "" : `?${new URLSearchParams({ next }).toString()}`;
    return `${MFA_CHALLENGE_PATH}${search}`;
  }
  if (session.authenticated && session.active_tenant === null) {
    return SELECT_WORKSPACE_PATH;
  }
  return next ?? "/";
}

/** SCREENS_B §12.1 states and copy for a refused sign-in. */
export function signInErrorCopy(problem: ApiProblem, retryAfter: string | null): string {
  switch (problem.status) {
    case 401:
      return t("auth.sign-in.error.incorrect");
    case 423:
      return t("auth.sign-in.error.locked");
    case 429: {
      const seconds = Number(retryAfter);
      if (retryAfter !== null && Number.isInteger(seconds) && seconds >= 0) {
        return t("auth.sign-in.error.rateLimited", { count: seconds });
      }
      return problem.detail ?? problem.title;
    }
    default:
      return problem.detail ?? problem.title;
  }
}

interface Refusal {
  readonly message: string;
  /** Wrong email or password marks both fields invalid, without saying which is wrong. */
  readonly credentials: boolean;
  readonly fields: Readonly<Record<string, string>>;
}

/** The control's own description ids plus the error banner's id when the banner describes it. */
export function describedBy(
  control: FieldControlProps,
  errorId: string | null,
): string | undefined {
  const ids = [control["aria-describedby"], errorId].filter(
    (id) => id !== undefined && id !== null,
  );
  return ids.length === 0 ? undefined : ids.join(" ");
}

export interface AuthFrameProps {
  readonly testId: string;
  /** DS-BR-03: the 28 px sign-in wordmark above the title (SF-22 only). */
  readonly wordmark?: boolean;
  /** Controls at the end of the header bar, for example "Sign out" on SF-22:mfa-enrol (SCREENS_B §12.2). */
  readonly actions?: ReactNode;
  readonly children: ReactNode;
}

/** The SF-22 family frame: a header bar with the wordmark and a start-aligned 440 px column. */
export function AuthFrame({ testId, wordmark = false, actions, children }: AuthFrameProps) {
  const name = t("shell.wordmark");
  return (
    <div className="min-h-dvh bg-canvas text-fg-1">
      <header className="flex h-[var(--topbar-h)] items-center justify-between border-b border-hairline px-[var(--gutter)]">
        <span role="img" aria-label={name} className="text-title-md text-fg-1">
          {name}
        </span>
        {actions === undefined ? null : <div className="flex items-center gap-2">{actions}</div>}
      </header>
      <main
        data-testid={testId}
        className="flex w-full max-w-110 flex-col gap-4 px-[var(--gutter)] pb-12"
        style={{ paddingBlockStart: "15vh" }}
      >
        {wordmark ? (
          /* DS-BR-02, DS-BR-03: the sign-in wordmark is 28 px, a size no type token holds. */
          <span
            role="img"
            aria-label={name}
            className="font-semibold text-fg-1"
            style={{ fontSize: "1.75rem", lineHeight: "2.25rem", letterSpacing: "-0.02em" }}
          >
            {name}
          </span>
        ) : null}
        {children}
      </main>
    </div>
  );
}

const OIDC_BUTTON_CLASS =
  "inline-flex h-[var(--control-h)] items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover active:bg-active";

export function SignIn() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { data: session } = useQuery({ queryKey: queryKeys.session(), queryFn: fetchSession });
  const titleId = useId();
  const errorId = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [pending, setPending] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const rawNext = params.get("next");
  const next = safeNext(rawNext);
  const reason = params.get("reason");
  const expired = reason === SESSION_EXPIRED_REASON;
  const title = t("auth.sign-in.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  // SCR-URL-30: any other `next` or `reason` value is dropped from the URL.
  const dropNext = rawNext !== null && next === null;
  const dropReason = reason !== null && !expired;
  useEffect(() => {
    if (!dropNext && !dropReason) {
      return;
    }
    setParams(
      (current) => {
        const kept = new URLSearchParams(current);
        if (dropNext) {
          kept.delete("next");
        }
        if (dropReason) {
          kept.delete("reason");
        }
        return kept;
      },
      { replace: true },
    );
  }, [dropNext, dropReason, setParams]);

  if (session?.authenticated === true) {
    return <Navigate replace to={destinationAfterSignIn(session, next)} />;
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      const response = await send("POST", LOGIN_PATH, { body: { email, password } });
      if (!response.ok) {
        const problem = await readProblem(response);
        setRefusal({
          message: signInErrorCopy(problem, response.headers.get("Retry-After")),
          credentials: problem.status === 401,
          fields: problem.status === 422 ? fieldErrorsOf(problem) : {},
        });
        return;
      }
      const data = (await response.json()) as SessionLoginOut;
      // A new sign-in replaces every read cached for an earlier session; the answered session is
      // the cached session, so this page and X:session read it without another request.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
      queryClient.setQueryData<SessionLoginOut>(queryKeys.session(), data);
    } finally {
      setPending(false);
    }
  };

  const providers = session?.capabilities.identity_providers ?? [];
  const invalid = refusal?.credentials === true;
  const bannerId = refusal === null ? null : errorId;

  return (
    <AuthFrame testId="SF-22-page" wordmark>
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {expired ? (
        <Banner
          tone="info"
          announce="static"
          title={t("auth.sign-in.sessionExpired", { minutes: SESSION_IDLE_MINUTES })}
        />
      ) : null}
      {refusal === null ? null : (
        <div id={errorId} data-testid="SF-22-banner-error">
          <Banner tone="negative" title={refusal.message} />
        </div>
      )}
      <form
        noValidate
        aria-labelledby={titleId}
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <Field name="email" label={t("auth.sign-in.email")} required error={refusal?.fields.email}>
          {(control) => (
            <input
              {...control}
              aria-describedby={describedBy(control, invalid ? bannerId : null)}
              aria-invalid={invalid || control["aria-invalid"] === true ? true : undefined}
              type="email"
              autoComplete="username"
              spellCheck={false}
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
              className={controlClass(invalid || control["aria-invalid"] === true)}
            />
          )}
        </Field>
        {/* SCREENS_B §12.1 wireframe: "Show" sits at the end of the Password label row. */}
        <div className="relative">
          <Field
            name="password"
            label={t("auth.sign-in.password")}
            required
            error={refusal?.fields.password}
          >
            {(control) => (
              <input
                {...control}
                aria-describedby={describedBy(control, invalid ? bannerId : null)}
                aria-invalid={invalid || control["aria-invalid"] === true ? true : undefined}
                type={shown ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
                className={controlClass(invalid || control["aria-invalid"] === true)}
              />
            )}
          </Field>
          <div className="absolute end-0 top-0">
            <Button
              variant="link"
              size="sm"
              aria-pressed={shown}
              aria-controls={fieldId("password")}
              onClick={() => {
                setShown((value) => !value);
              }}
            >
              {t("auth.sign-in.show")}
            </Button>
          </div>
        </div>
        <div>
          <Button variant="primary" type="submit" loading={pending}>
            {t("auth.sign-in.submit")}
          </Button>
        </div>
      </form>
      <Link to={FORGOT_PASSWORD_PATH} className="text-body-sm text-accent-fg hover:underline">
        {t("auth.sign-in.forgotPassword")}
      </Link>
      {providers.length === 0 ? null : (
        <div className="flex flex-col items-start gap-2 border-t border-hairline pt-4">
          {providers.map((provider) => (
            <a
              key={provider.code}
              href={oidcStartPath(provider.code)}
              className={OIDC_BUTTON_CLASS}
            >
              {t("auth.sign-in.oidc", { provider: provider.name })}
            </a>
          ))}
        </div>
      )}
    </AuthFrame>
  );
}

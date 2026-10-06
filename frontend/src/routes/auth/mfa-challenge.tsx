// SF-22:mfa-challenge Verify your sign-in (SCREENS_B §12.1; SCREENS §0.4 RT-02; 04 API-R-01
// `POST /session/mfa`, `POST /session/logout`; BS1-D-19, BS1-D-30). The second step of a password
// sign-in: a TOTP code, or a recovery code after "Use a recovery code instead". A wrong code shows the
// SCREENS_B copy in the error banner that describes the field; a recovery-code sign-in reports the
// codes that remain in an info toast; "Sign in as someone else" ends the pending session and returns
// to SF-22. The page renders in the SF-22 frame. A visitor without a session goes to sign-in, and a
// session that owes no challenge (`mfa_required` false, on the sign-in answer and on `GET /session`)
// leaves for its destination.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Navigate, useSearchParams } from "react-router";

import { fetchSession, SessionPending, type SessionState } from "../../app/auth/RequireSession";
import { useSignOut } from "../../app/shell/UserMenu";
import { Banner } from "../../components/feedback/Banner";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field, fieldId } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { SIGN_IN_PATH } from "../../lib/api/client";
import { useCommand } from "../../lib/api/commands";
import type { ApiProblem } from "../../lib/api/problems";
import { queryKeys } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import {
  AuthFrame,
  describedBy,
  destinationAfterSignIn,
  safeNext,
  signInErrorCopy,
} from "./sign-in";

type SessionMfaOut = components["schemas"]["SessionMfaOut"];

export const MFA_VERIFY_PATH = "/api/v1/session/mfa";

export type ChallengeMode = "code" | "recovery";

/** True while the password step is done and the session still owes its MFA challenge. */
export function challengePending(session: SessionState): boolean {
  return session.authenticated && session.mfa_required;
}

/** SCREENS_B §12.1 copy for a refused verification: 422 is a wrong, replayed or spent code (BS1-D-30). */
export function challengeErrorCopy(problem: ApiProblem): string {
  return problem.status === 422
    ? t("auth.mfa-challenge.error.wrongCode")
    : signInErrorCopy(problem, null);
}

const FIELD: Readonly<Record<ChallengeMode, { readonly name: string; readonly label: string }>> = {
  code: { name: "code", label: "auth.mfa-challenge.code" },
  recovery: { name: "recovery_code", label: "auth.mfa-challenge.recoveryCode" },
};

export function MfaChallenge() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const signOut = useSignOut();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const { data: session } = useQuery({ queryKey: queryKeys.session(), queryFn: fetchSession });
  const verify = useCommand<SessionMfaOut>({ method: "POST", path: MFA_VERIFY_PATH });
  const titleId = useId();
  const errorId = useId();
  const [mode, setMode] = useState<ChallengeMode>("code");
  const [value, setValue] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const swapped = useRef(false);
  const title = t("auth.mfa-challenge.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  // A swap between the code and the recovery code moves focus to the new field.
  useEffect(() => {
    if (swapped.current) {
      document.getElementById(fieldId(FIELD[mode].name))?.focus();
    }
  }, [mode]);

  if (session === undefined) {
    return <SessionPending />;
  }
  if (!session.authenticated) {
    const search = next === null ? "" : `?${new URLSearchParams({ next }).toString()}`;
    return <Navigate replace to={`${SIGN_IN_PATH}${search}`} />;
  }
  if (!challengePending(session)) {
    return <Navigate replace to={destinationAfterSignIn(session, next)} />;
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (verify.pending) {
      return;
    }
    setRefusal(null);
    const entered = value.trim();
    const outcome = await verify.submit(
      mode === "code" ? { code: entered } : { recovery_code: entered },
    );
    if (outcome.kind === "failed") {
      setRefusal(challengeErrorCopy(outcome.problem));
      return;
    }
    if (outcome.kind !== "succeeded" || outcome.data === null) {
      return;
    }
    const verified = outcome.data;
    // The rotated session replaces every read cached for the pending one (SAR-09).
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    queryClient.setQueryData<SessionMfaOut>(queryKeys.session(), verified);
    if (verified.recovery_codes_remaining !== null) {
      toast.show({
        tone: "neutral",
        message: t("auth.mfa-challenge.recoveryUsed", {
          count: verified.recovery_codes_remaining,
        }),
      });
    }
  };

  const swap = () => {
    swapped.current = true;
    setMode((current) => (current === "code" ? "recovery" : "code"));
    setValue("");
    setRefusal(null);
  };

  const field = FIELD[mode];
  const invalid = refusal !== null;

  return (
    <AuthFrame testId="SF-22-mfa-challenge-page">
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {mode === "code" ? (
        <p className="text-body text-fg-2">{t("auth.mfa-challenge.description")}</p>
      ) : null}
      {refusal === null ? null : (
        <div id={errorId} data-testid="SF-22-banner-error">
          <Banner tone="negative" title={refusal} />
        </div>
      )}
      <form
        noValidate
        aria-labelledby={titleId}
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <Field key={mode} name={field.name} label={t(field.label)} required width="text">
          {(control) => (
            <input
              {...control}
              aria-describedby={describedBy(control, invalid ? errorId : null)}
              aria-invalid={invalid ? true : undefined}
              type="text"
              inputMode={mode === "code" ? "numeric" : "text"}
              autoComplete={mode === "code" ? "one-time-code" : "off"}
              autoCapitalize="none"
              spellCheck={false}
              value={value}
              onChange={(event) => {
                setValue(event.target.value);
              }}
              className={controlClass(invalid)}
            />
          )}
        </Field>
        <div>
          <Button variant="primary" type="submit" loading={verify.pending}>
            {t("auth.mfa-challenge.submit")}
          </Button>
        </div>
      </form>
      <div className="flex flex-wrap items-center gap-2 text-body-sm text-fg-3">
        <Button variant="link" size="sm" onClick={swap}>
          {t(
            mode === "code"
              ? "auth.mfa-challenge.useRecoveryCode"
              : "auth.mfa-challenge.useAuthenticator",
          )}
        </Button>
        <span aria-hidden="true">·</span>
        <Button
          variant="link"
          size="sm"
          onClick={() => {
            void signOut();
          }}
        >
          {t("auth.mfa-challenge.signInAsSomeoneElse")}
        </Button>
      </div>
    </AuthFrame>
  );
}

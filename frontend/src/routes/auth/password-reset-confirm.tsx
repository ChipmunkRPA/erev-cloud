// SF-22:password-reset-confirm Choose a new password (SCREENS_B §12.3; SCREENS §0.4 RT-112; 04
// API-R-01 `POST /session/password-reset/confirm`, T-PLT-42; ERR-21; BUILD_SPEC WEB-14). Public with a
// token that rides only in the URL fragment `#token=<token>` and travels only in the request body.
// A mismatch is refused before any request; 404 shows the expired-link state with a link to request a
// new one; 422 `password-policy` shows the ERR-21 copy the API answers; 204 shows the success state
// with a link to sign in (every session of the user has ended).
import { type FormEvent, useEffect, useId, useState } from "react";
import { Link, useLocation } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { Button } from "../../components/ui/Button";
import { send, SIGN_IN_PATH } from "../../lib/api/client";
import { readProblem } from "../../lib/api/problems";
import { t } from "../../lib/i18n/t";
import { PASSWORD_RESET_ROUTE } from "./password-reset";
import {
  NewPasswordFields,
  type PasswordRefusal,
  passwordRefusal,
  tokenFromFragment,
} from "./password-shared";
import { AuthFrame } from "./sign-in";

export const PASSWORD_RESET_CONFIRM_PATH = "/api/v1/session/password-reset/confirm";

type Outcome = "form" | "expired" | "done";

export function PasswordResetConfirm() {
  const { hash } = useLocation();
  const token = tokenFromFragment(hash);
  const titleId = useId();
  const errorId = useId();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const [pending, setPending] = useState(false);
  const [refusal, setRefusal] = useState<PasswordRefusal | null>(null);
  const [outcome, setOutcome] = useState<Outcome>("form");
  const title = t("auth.password-reset-confirm.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending || token === null) {
      return;
    }
    setRefusal(null);
    if (password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setPending(true);
    try {
      const response = await send("POST", PASSWORD_RESET_CONFIRM_PATH, {
        body: { token, new_password: password },
      });
      if (response.ok) {
        setOutcome("done");
        return;
      }
      const problem = await readProblem(response);
      if (problem.status === 404) {
        setOutcome("expired");
        return;
      }
      setRefusal(passwordRefusal(problem, "new_password"));
    } finally {
      setPending(false);
    }
  };

  const bannerId = refusal === null ? null : errorId;

  return (
    <AuthFrame testId="SF-22-password-reset-confirm-page">
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {token === null ? (
        <Banner
          tone="negative"
          announce="static"
          title={t("auth.password-reset-confirm.error.missingToken")}
        />
      ) : null}
      {outcome === "expired" ? (
        <Banner
          tone="negative"
          announce="static"
          title={t("auth.password-reset-confirm.error.expired")}
          actions={
            <Link to={PASSWORD_RESET_ROUTE} className="text-body-sm text-accent-fg hover:underline">
              {t("auth.password-reset-confirm.requestNew")}
            </Link>
          }
        />
      ) : null}
      {outcome === "done" ? (
        <Banner
          tone="positive"
          title={t("auth.password-reset-confirm.success")}
          actions={
            <Link to={SIGN_IN_PATH} className="text-body-sm text-accent-fg hover:underline">
              {t("auth.password-reset-confirm.signIn")}
            </Link>
          }
        />
      ) : null}
      {token !== null && outcome === "form" ? (
        <>
          {refusal === null ? null : (
            <div
              id={errorId}
              data-testid={refusal.policy ? "SF-22-banner-password-policy" : "SF-22-banner-error"}
            >
              <Banner tone="negative" title={refusal.message} />
            </div>
          )}
          <form
            noValidate
            aria-labelledby={titleId}
            className="flex flex-col gap-3"
            onSubmit={(event) => void submit(event)}
          >
            <NewPasswordFields
              name="new_password"
              label={t("auth.password-reset-confirm.password")}
              confirmLabel={t("auth.password-reset-confirm.confirm")}
              help={t("auth.password-reset-confirm.help")}
              password={password}
              confirm={confirm}
              error={refusal?.fields.new_password}
              bannerId={bannerId}
              mismatch={mismatch}
              onPassword={setPassword}
              onConfirm={setConfirm}
            />
            <div>
              <Button variant="primary" type="submit" loading={pending}>
                {t("auth.password-reset-confirm.submit")}
              </Button>
            </div>
          </form>
        </>
      ) : null}
    </AuthFrame>
  );
}

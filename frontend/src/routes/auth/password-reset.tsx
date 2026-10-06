// SF-22:password-reset Reset password (SCREENS_B §12.3; SCREENS §0.4 RT-111; 04 API-R-01
// `POST /session/password-reset`, T-PLT-42; BUILD_SPEC WEB-14). Public. The request always answers
// 202 whether or not the account exists, so the page shows the same status for every email and never
// reveals account existence. The page renders in the SF-22 frame.
import { type FormEvent, useEffect, useId, useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { send, SIGN_IN_PATH } from "../../lib/api/client";
import { readProblem } from "../../lib/api/problems";
import { t } from "../../lib/i18n/t";
import { AuthFrame } from "./sign-in";

export const PASSWORD_RESET_PATH = "/api/v1/session/password-reset";
export const PASSWORD_RESET_ROUTE = "/password/reset";

export function PasswordReset() {
  const titleId = useId();
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const title = t("auth.password-reset.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      const address = email.trim();
      const response = await send("POST", PASSWORD_RESET_PATH, { body: { email: address } });
      if (!response.ok) {
        const problem = await readProblem(response);
        setRefusal(problem.detail ?? problem.title);
        return;
      }
      setSent(address);
    } finally {
      setPending(false);
    }
  };

  return (
    <AuthFrame testId="SF-22-password-reset-page">
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {sent === null ? (
        <>
          <p className="text-body text-fg-2">{t("auth.password-reset.description")}</p>
          {refusal === null ? null : (
            <div data-testid="SF-22-banner-error">
              <Banner tone="negative" title={refusal} />
            </div>
          )}
          <form
            noValidate
            aria-labelledby={titleId}
            className="flex flex-col gap-3"
            onSubmit={(event) => void submit(event)}
          >
            <Field name="email" label={t("auth.password-reset.email")} required>
              {(control) => (
                <input
                  {...control}
                  type="email"
                  autoComplete="username"
                  spellCheck={false}
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                  }}
                  className={controlClass(false)}
                />
              )}
            </Field>
            <div>
              <Button variant="primary" type="submit" loading={pending}>
                {t("auth.password-reset.submit")}
              </Button>
            </div>
          </form>
        </>
      ) : (
        <p
          role="status"
          data-testid="SF-22-banner-reset-sent"
          className="rounded-md border border-hairline p-3 text-body text-fg-1"
        >
          {t("auth.password-reset.sent", { email: sent })}
        </p>
      )}
      <Link to={SIGN_IN_PATH} className="text-body-sm text-accent-fg hover:underline">
        {t("auth.password-reset.backToSignIn")}
      </Link>
    </AuthFrame>
  );
}

// SF-22:password-change Change password (SCREENS_B §12.3; SCREENS §0.4 RT-04; 04 API-R-03
// `POST /me/password` (§16.12); SAR-09, SAR-10; BUILD_SPEC WEB-14). Authenticated, outside the shell.
// A wrong current password is 422 `validation-failed` on `current_password` ("The current password is
// incorrect."); a weak new one 422 `password-policy` with the ERR-21 copy; success shows the toast
// "Password changed. Your other sessions were signed out." — the presented session continues under a
// rotated cookie, so the cached session is refetched — and then opens the landing route `/` (SCREENS_B
// rev 1.8; D-98 candidate 24 Q5). SF-15:profile's "Change password" is the entry point (Q4).
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useId, useState } from "react";
import { Link, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { useCommand } from "../../lib/api/commands";
import { queryKeys } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { NewPasswordFields, type PasswordRefusal, passwordRefusal } from "./password-shared";
import { AuthFrame, describedBy } from "./sign-in";

export const PASSWORD_CHANGE_PATH = "/api/v1/me/password";
/** SCREENS RT-04. */
export const PASSWORD_CHANGE_ROUTE = "/password/change";

export function PasswordChange() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const change = useCommand<null>({ method: "POST", path: PASSWORD_CHANGE_PATH });
  const titleId = useId();
  const errorId = useId();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const [refusal, setRefusal] = useState<PasswordRefusal | null>(null);
  const title = t("auth.password-change.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (change.pending) {
      return;
    }
    setRefusal(null);
    if (password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    const outcome = await change.submit({ current_password: current, new_password: password });
    if (outcome.kind === "failed") {
      const refused = passwordRefusal(outcome.problem, "new_password");
      setRefusal(
        refused.fields.current_password === undefined
          ? refused
          : {
              ...refused,
              message: t("auth.password-change.error.current"),
              fields: {
                ...refused.fields,
                current_password: t("auth.password-change.error.current"),
              },
            },
      );
      return;
    }
    if (outcome.kind !== "succeeded") {
      return;
    }
    setCurrent("");
    setPassword("");
    setConfirm("");
    void queryClient.invalidateQueries({ queryKey: queryKeys.session() });
    toast.show({ tone: "positive", message: t("auth.password-change.success") });
    void navigate("/", { replace: true });
  };

  const currentError = refusal?.fields.current_password;
  const bannerId = refusal === null ? null : errorId;

  return (
    <AuthFrame testId="SF-22-password-change-page">
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
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
        <Field
          name="current_password"
          label={t("auth.password-change.current")}
          required
          error={currentError}
        >
          {(control) => (
            <input
              {...control}
              aria-describedby={describedBy(control, currentError === undefined ? null : bannerId)}
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => {
                setCurrent(event.target.value);
              }}
              className={controlClass(currentError !== undefined)}
            />
          )}
        </Field>
        <NewPasswordFields
          name="new_password"
          label={t("auth.password-change.new")}
          confirmLabel={t("auth.password-change.confirm")}
          help={t("auth.password-change.help")}
          password={password}
          confirm={confirm}
          error={refusal?.fields.new_password}
          bannerId={bannerId}
          mismatch={mismatch}
          onPassword={setPassword}
          onConfirm={setConfirm}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" type="submit" loading={change.pending}>
            {t("auth.password-change.submit")}
          </Button>
          <Link to="/" className="text-body-sm text-accent-fg hover:underline">
            {t("auth.password-change.back")}
          </Link>
        </div>
      </form>
    </AuthFrame>
  );
}

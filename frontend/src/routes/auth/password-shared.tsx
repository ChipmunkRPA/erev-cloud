// Shared pieces of the SF-22 password screens (SCREENS_B §12.3; ERR-21; BUILD_SPEC WEB-13, WEB-14):
// the token of a URL fragment, the refusal copy of a new-password request and the two new-password
// fields with the policy help text, the mismatch check and `autocomplete="new-password"`.
import { controlClass, Field } from "../../components/form/Field";
import type { ApiProblem } from "../../lib/api/problems";
import { fieldErrorsOf } from "../../lib/api/problems";
import { t } from "../../lib/i18n/t";
import { describedBy } from "./sign-in";

/** The token of the URL fragment `#token=<token>`, or null when absent (RT-05, RT-112); one definition. */
export { tokenFromFragment } from "../../lib/api/queries/credentials";

export interface PasswordRefusal {
  readonly message: string;
  /** 422 `password-policy`: the ERR-21 copy the API answers. */
  readonly policy: boolean;
  readonly fields: Readonly<Record<string, string>>;
}

/** The refusal of a request that sets a password: the API's ERR-21 copy on the password field. */
export function passwordRefusal(problem: ApiProblem, field: string): PasswordRefusal {
  const fields = fieldErrorsOf(problem);
  const policy = problem.slug === "password-policy";
  return {
    message: problem.detail ?? problem.title,
    policy,
    fields:
      policy && fields[field] === undefined
        ? { ...fields, [field]: problem.detail ?? problem.title }
        : fields,
  };
}

export interface NewPasswordFieldsProps {
  readonly name: string;
  readonly label: string;
  readonly confirmLabel: string;
  readonly help: string;
  readonly password: string;
  readonly confirm: string;
  readonly error: string | undefined;
  readonly bannerId: string | null;
  readonly mismatch: boolean;
  readonly onPassword: (value: string) => void;
  readonly onConfirm: (value: string) => void;
}

/** A new password and its confirmation (§12.3 test hooks: textbox "Choose a password" or "New password"). */
export function NewPasswordFields({
  name,
  label,
  confirmLabel,
  help,
  password,
  confirm,
  error,
  bannerId,
  mismatch,
  onPassword,
  onConfirm,
}: NewPasswordFieldsProps) {
  const invalid = error !== undefined;
  return (
    <>
      <Field name={name} label={label} required help={help} error={error}>
        {(control) => (
          <input
            {...control}
            aria-describedby={describedBy(control, invalid ? bannerId : null)}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => {
              onPassword(event.target.value);
            }}
            className={controlClass(invalid)}
          />
        )}
      </Field>
      <Field
        name={`${name}_confirm`}
        label={confirmLabel}
        required
        error={mismatch ? t("auth.password.error.mismatch") : undefined}
      >
        {(control) => (
          <input
            {...control}
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => {
              onConfirm(event.target.value);
            }}
            className={controlClass(mismatch)}
          />
        )}
      </Field>
    </>
  );
}

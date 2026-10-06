// SF-22:accept-invitation Accept invitation (SCREENS_B §12.3 rev 1.8; SCREENS §0.4 RT-05; 04 API-R-01
// `POST /session/invitations/lookup`, `POST /session/accept-invitation`, T-PLT-07, §16.12 rev 1.38; 05
// SAR-06, SAR-09; PRD J-01.1, J-22.3, J-22.4, ERR-21; DESIGN_SYSTEM DS-CMP-21, DS-CMP-29; BUILD_SPEC
// WEB-13). The token is read from the URL fragment (`#token=<token>`), which the browser never sends to
// the server, and travels only in request bodies; a link without a token explains that it is incomplete.
// The lookup fills the heading "<inviter> invited <email> to <workspace>." and selects the form from
// `has_password`: an invitee without a password chooses one twice (`autocomplete="new-password"`; a
// mismatch is refused on the page, the policy by the API as 422 `password-policy`, ERR-21, rendered under
// the field before its help text); an existing user enters "Your eRev password" once
// (`current-password`), and the API's 422 `validation-failed` on `password` is the field error; a lock
// (423) shows the sign-in copy. A 404 from either request shows the expired-link state. An accepted
// invitation stores the answered session and applies the §12.1 landing rules: MFA enrolment first when
// the roles require it. A session already open in this browser is left alone; the API ends it when the
// acceptance opens the new one.
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useId, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner, refusalLines } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { ApiProblem } from "../../lib/api/problems";
import {
  acceptInvitation,
  type InvitationLookup,
  lookupInvitation,
  passwordPolicyMessage,
  type SessionLoginOut,
  tokenFromFragment,
} from "../../lib/api/queries/credentials";
import { queryKeys } from "../../lib/api/query-keys";
import { useFieldRefusals } from "../../lib/api/refusals";
import { t } from "../../lib/i18n/t";
import { AuthFrame, destinationAfterSignIn } from "./sign-in";

export type LookupState =
  | { readonly kind: "checking" }
  | { readonly kind: "found"; readonly invitation: InvitationLookup }
  | { readonly kind: "missing" }
  | { readonly kind: "expired" }
  | { readonly kind: "failed"; readonly message: string };

/** SCREENS_B §12.3 heading; an invitation created by a non-user principal names no inviter. */
export function invitationHeading(invitation: InvitationLookup): string {
  const params = {
    email: invitation.email,
    workspace: invitation.workspace_display_name,
  };
  return invitation.inviter_display_name === null
    ? t("auth.accept-invitation.headingNoInviter", params)
    : t("auth.accept-invitation.heading", { ...params, inviter: invitation.inviter_display_name });
}

/** The API member the password field sends; the token has no field (DG-FE-06 rev 1.228). */
const ACCEPT_MEMBERS = { password: ["password"] } as const;

export function AcceptInvitation() {
  const { hash } = useLocation();
  const token = tokenFromFragment(hash);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const titleId = useId();
  const errorId = useId();
  const [lookup, setLookup] = useState<LookupState>({ kind: "checking" });
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [policy, setPolicy] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Readonly<Record<string, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  // A 422 of the acceptance: the password field shows what names the password, and the banner says
  // what no field took — a refusal that names the token was shown nowhere.
  const [refused, setRefused] = useState<ApiProblem | null>(null);
  const refusals = useFieldRefusals(refused, ACCEPT_MEMBERS);
  const title = t("auth.accept-invitation.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  useEffect(() => {
    if (token === null) {
      setLookup({ kind: "missing" });
      return undefined;
    }
    let cancelled = false;
    setLookup({ kind: "checking" });
    void (async () => {
      try {
        const invitation = await lookupInvitation(token);
        if (!cancelled) {
          setLookup({ kind: "found", invitation });
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiProblem && error.status === 404) {
          setLookup({ kind: "expired" });
        } else {
          setLookup({
            kind: "failed",
            message:
              error instanceof ApiProblem
                ? (error.detail ?? error.title)
                : t("auth.accept-invitation.error.lookup"),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const existing = lookup.kind === "found" && lookup.invitation.has_password;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending || token === null) {
      return;
    }
    setPolicy(null);
    setFieldErrors({});
    setRefusal(null);
    setRefused(null);
    if (!existing && password !== confirmation) {
      setFieldErrors({ confirm_password: t("auth.password.error.mismatch") });
      return;
    }
    setPending(true);
    try {
      const session = await acceptInvitation({ token, password });
      // The acceptance opens a new session: every read cached for an earlier one goes, and the answered
      // session is the cached session, so X:session reads it without another request.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
      queryClient.setQueryData<SessionLoginOut>(queryKeys.session(), session);
      void navigate(destinationAfterSignIn(session, null), { replace: true });
    } catch (error) {
      if (!(error instanceof ApiProblem)) {
        setRefusal(t("auth.accept-invitation.error.network"));
        return;
      }
      const policyMessage = passwordPolicyMessage(error);
      if (policyMessage !== null) {
        setPolicy(policyMessage);
      } else if (error.status === 404) {
        setLookup({ kind: "expired" });
      } else if (error.status === 422) {
        setRefused(error);
      } else if (error.status === 423) {
        setRefusal(t("auth.sign-in.error.locked"));
      } else {
        setRefusal(error.detail ?? error.title);
      }
    } finally {
      setPending(false);
    }
  };

  const passwordError = policy ?? refusals.fields.password;
  // SCREENS_B §12.3: a refusal the password field shows whole has no banner. The banner stands when
  // the field took nothing of it, or when something is left that no field shows.
  const leftOver = refusals.banner === null ? null : refusalLines(refusals.banner, refusals.placed);
  const refusedBanner =
    leftOver !== null &&
    (refusals.placed.fields.password === null ||
      leftOver.detail !== null ||
      leftOver.sentences.length > 0);

  return (
    <AuthFrame testId="SF-22-accept-invitation-page">
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {lookup.kind === "checking" ? <Skeleton region={title} shape="rows" count={2} /> : null}
      {lookup.kind === "missing" ? (
        <div data-testid="SF-22-banner-invitation-missing">
          <Banner
            tone="warning"
            announce="static"
            title={t("auth.accept-invitation.error.missingToken")}
          />
        </div>
      ) : null}
      {lookup.kind === "expired" ? (
        <div data-testid="SF-22-banner-invitation-expired">
          <Banner
            tone="warning"
            announce="static"
            title={t("auth.accept-invitation.error.expired")}
          />
        </div>
      ) : null}
      {lookup.kind === "failed" ? <Banner tone="negative" title={lookup.message} /> : null}
      {lookup.kind === "found" ? (
        <>
          <p data-testid="SF-22-invitation-heading" className="text-body text-fg-2">
            {invitationHeading(lookup.invitation)}
          </p>
          {refusal === null && !refusedBanner ? null : (
            <div id={errorId} data-testid="SF-22-banner-error">
              {refusal !== null ? (
                <Banner tone="negative" title={refusal} />
              ) : (
                <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
              )}
            </div>
          )}
          <form
            noValidate
            aria-labelledby={titleId}
            className="flex flex-col gap-3"
            onSubmit={(event) => void submit(event)}
          >
            {existing ? (
              <Field
                name="password"
                label={t("auth.accept-invitation.existingPassword")}
                required
                error={refusals.fields.password}
              >
                {(control) => (
                  <input
                    {...control}
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => {
                      setPassword(event.target.value);
                      refusals.edited("password");
                    }}
                    className={controlClass(control["aria-invalid"] === true)}
                  />
                )}
              </Field>
            ) : (
              <>
                {/* The policy error is the field's error, so it precedes the help text in the description. */}
                <div data-testid={policy === null ? undefined : "SF-22-banner-password-policy"}>
                  <Field
                    name="password"
                    label={t("auth.accept-invitation.password")}
                    required
                    help={t("auth.accept-invitation.help")}
                    error={passwordError}
                  >
                    {(control) => (
                      <input
                        {...control}
                        type="password"
                        autoComplete="new-password"
                        value={password}
                        onChange={(event) => {
                          setPassword(event.target.value);
                          refusals.edited("password");
                        }}
                        className={controlClass(control["aria-invalid"] === true)}
                      />
                    )}
                  </Field>
                </div>
                <Field
                  name="confirm_password"
                  label={t("auth.accept-invitation.confirm")}
                  required
                  error={fieldErrors.confirm_password}
                >
                  {(control) => (
                    <input
                      {...control}
                      type="password"
                      autoComplete="new-password"
                      value={confirmation}
                      onChange={(event) => {
                        setConfirmation(event.target.value);
                      }}
                      className={controlClass(control["aria-invalid"] === true)}
                    />
                  )}
                </Field>
              </>
            )}
            <div>
              <Button variant="primary" type="submit" loading={pending}>
                {t("auth.accept-invitation.submit")}
              </Button>
            </div>
          </form>
        </>
      ) : null}
    </AuthFrame>
  );
}

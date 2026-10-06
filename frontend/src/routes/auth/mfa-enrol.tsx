// SF-22:mfa-enrol Set up multi-factor authentication (SCREENS_B §12.2; SCREENS §0.4 RT-03; 03 REQ-PLT-005;
// 04 API-R-03 `POST /me/mfa/enroll`, `POST /me/mfa/confirm`; 05 SAR-09, SAR-26; PRD J-22.4, J-22-AC-2,
// ERR-27; DESIGN_SYSTEM DS-CMP-18, DS-CMP-21, DS-CMP-29; BUILD_SPEC WEB-13). Three steps in the SF-22
// frame. Scan: the page starts enrolment on mount and shows the otpauth URI as a QR image (lib/qr, no
// dependency; a PNG data URI) with the manual key always beside it, grouped in fours, and "Copy key"; a refused start
// shows the problem with "Retry". Verify: the first code confirms the factor and the API rotates the
// session. Recovery codes: the ten codes are shown once with "Copy codes" and "Download codes"
// (`erev-recovery-codes.txt`); "Continue" waits for the acknowledgement, re-reads the session, which no
// longer carries the enrolment step, and applies the §12.1 landing rules (J-22.4: Home). `MfaGate`
// (app/auth) keeps a member who must enrol on this route; the ERR-27 warning banner states the reason
// while that is the case. "Sign out" in the header ends the session.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { fetchSession, type SessionState } from "../../app/auth/RequireSession";
import { useSignOut } from "../../app/shell/UserMenu";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field } from "../../components/form/Field";
import { CopySimple, DownloadSimple } from "../../components/icons/registry";
import { type Step, Stepper } from "../../components/record/Stepper";
import { Button } from "../../components/ui/Button";
import { SIGN_IN_PATH } from "../../lib/api/client";
import type { ApiProblem } from "../../lib/api/problems";
import {
  groupedKey,
  type MfaConfirmIn,
  type MfaEnrolment,
  RECOVERY_CODES_FILE,
  recoveryCodesText,
  useMfaConfirm,
  useMfaEnrol,
} from "../../lib/api/queries/mfa";
import { queryKeys } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { encodeQr, PNG_SCALE, qrPngDataUri, QUIET_ZONE } from "../../lib/qr/qr";
import { AuthFrame, describedBy, destinationAfterSignIn } from "./sign-in";

export type EnrolStep = "scan" | "verify" | "recovery";

/** DS-CMP-18 stepper order (SCREENS_B §12.2 "(1 Scan)──(2 Verify)──(3 Recovery codes)"). */
export const ENROL_STEPS: readonly EnrolStep[] = ["scan", "verify", "recovery"];

/** The stepper items for the current step: earlier steps complete, later steps pending. */
export function enrolSteps(current: EnrolStep): Step[] {
  const position = ENROL_STEPS.indexOf(current);
  return ENROL_STEPS.map((id, index) => ({
    id,
    label: t(`auth.mfa-enrol.steps.${id}`),
    state: index < position ? "complete" : index === position ? "current" : "pending",
  }));
}

/** True while the session demands enrolment (`mfa_enrolment_required` of API-S-Session). */
export function enrolmentRequired(session: SessionState | undefined): boolean {
  return session?.authenticated === true && session.mfa_enrolment_required;
}

/** SCREENS_B §12.2 copy for a refused first code: 422 is a wrong code (04 `me_mfa_confirm`). */
export function confirmErrorCopy(problem: ApiProblem): string {
  return problem.status === 422
    ? t("auth.mfa-enrol.verify.error.wrongCode")
    : (problem.detail ?? problem.title);
}

export function MfaEnrol() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const signOut = useSignOut();
  const { data: session } = useQuery({ queryKey: queryKeys.session(), queryFn: fetchSession });
  const enrol = useMfaEnrol();
  const confirm = useMfaConfirm();
  const startEnrolment = enrol.submit;
  const titleId = useId();
  const errorId = useId();
  const reasonId = useId();
  const checkboxId = useId();
  const [step, setStep] = useState<EnrolStep>("scan");
  const [seed, setSeed] = useState<MfaEnrolment | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [codes, setCodes] = useState<readonly string[]>([]);
  const [stored, setStored] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const started = useRef(false);
  const title = t("auth.mfa-enrol.title");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  const start = useCallback(async () => {
    setFailure(null);
    const outcome = await startEnrolment();
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      setSeed(outcome.data);
    } else if (outcome.kind === "failed") {
      setFailure(outcome.problem.detail ?? outcome.problem.title);
    } else if (outcome.kind === "network-error") {
      setFailure(t("auth.mfa-enrol.error.start"));
    }
  }, [startEnrolment]);

  // The seed is requested once per page, also under StrictMode's doubled effects.
  useEffect(() => {
    if (started.current) {
      return;
    }
    started.current = true;
    void start();
  }, [start]);

  const qr = useMemo(() => {
    if (seed === null) {
      return null;
    }
    try {
      const matrix = encodeQr(seed.otpauth_uri);
      return {
        src: qrPngDataUri(matrix),
        size: (matrix.length + 2 * QUIET_ZONE) * PNG_SCALE,
      };
    } catch {
      // An accepted enrolment can exceed the encoder's capacity. Keep manual setup available.
      return null;
    }
  }, [seed]);

  const verify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (confirm.pending) {
      return;
    }
    setRefusal(null);
    const body: MfaConfirmIn = { code: code.trim() };
    const outcome = await confirm.submit(body);
    if (outcome.kind === "failed") {
      setRefusal(confirmErrorCopy(outcome.problem));
      return;
    }
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      setCodes(outcome.data.recovery_codes);
      setStep("recovery");
    }
  };

  const copy = async (text: string, message: string) => {
    if (typeof navigator.clipboard === "undefined") {
      return;
    }
    await navigator.clipboard.writeText(text);
    toast.show({ tone: "positive", message });
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([recoveryCodesText(codes)], { type: "text/plain" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = RECOVERY_CODES_FILE;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  // The confirmed factor rotated the session (SAR-09): the re-read session owes no step any more,
  // which lifts MfaGate; the landing rules of §12.1 then apply.
  const finish = async () => {
    if (!stored || finishing) {
      return;
    }
    setFinishing(true);
    try {
      const fresh = await queryClient.fetchQuery<SessionState>({
        queryKey: queryKeys.session(),
        queryFn: fetchSession,
        staleTime: 0,
      });
      if (!fresh.authenticated) {
        void navigate(SIGN_IN_PATH, { replace: true });
        return;
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.me() });
      void navigate(destinationAfterSignIn(fresh, null), { replace: true });
    } finally {
      setFinishing(false);
    }
  };

  const invalid = refusal !== null;
  const continueReason = t("auth.mfa-enrol.recovery.error.acknowledge");

  return (
    <AuthFrame
      testId="SF-22-mfa-enrol-page"
      actions={
        <Button
          variant="link"
          size="sm"
          onClick={() => {
            void signOut();
          }}
        >
          {t("auth.mfa-enrol.signOut")}
        </Button>
      }
    >
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {enrolmentRequired(session) ? (
        <div data-testid="SF-22-banner-mfa-required">
          <Banner tone="warning" announce="static" title={t("auth.mfa-enrol.banner")} />
        </div>
      ) : null}
      <Stepper label={t("auth.mfa-enrol.steps")} steps={enrolSteps(step)} currentId={step} />

      {step === "scan" ? (
        <section aria-labelledby={titleId} className="flex flex-col gap-3">
          <p className="text-body text-fg-2">{t("auth.mfa-enrol.scan.description")}</p>
          {failure === null ? null : (
            <div data-testid="SF-22-banner-error">
              <Banner
                tone="negative"
                title={t("auth.mfa-enrol.error.start")}
                actions={
                  <Button
                    variant="link"
                    size="sm"
                    onClick={() => {
                      void start();
                    }}
                  >
                    {t("auth.mfa-enrol.error.retry")}
                  </Button>
                }
              >
                {failure}
              </Banner>
            </div>
          )}
          {seed === null && failure === null ? (
            <Skeleton region={t("auth.mfa-enrol.scan.qrRegion")} shape="rows" count={3} />
          ) : null}
          {seed !== null ? (
            <>
              {qr === null ? (
                // F-ADM-R1 Q20: the encoder refused the otpauth URI; the key below stays the way in.
                <p
                  role="note"
                  data-testid="SF-22-mfa-qr-unavailable"
                  className="text-body-sm font-medium text-warning-fg"
                >
                  {t("auth.mfa-enrol.scan.qrUnavailable")}
                </p>
              ) : (
                <img
                  src={qr.src}
                  alt={t("auth.mfa-enrol.scan.qrAlt")}
                  width={qr.size}
                  height={qr.size}
                  data-testid="SF-22-mfa-qr"
                  data-volatile=""
                  className="rounded-md border border-hairline bg-surface"
                />
              )}
              <div className="flex flex-col gap-1">
                <span className="text-body-sm font-medium text-fg-1">
                  {t("auth.mfa-enrol.scan.key")}
                </span>
                <div className="flex flex-wrap items-center gap-3">
                  <code
                    data-testid="SF-22-mfa-key"
                    data-volatile=""
                    className="font-mono text-body text-fg-1"
                  >
                    {groupedKey(seed.secret_base32)}
                  </code>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={CopySimple}
                    onClick={() => {
                      void copy(seed.secret_base32, t("auth.mfa-enrol.scan.copied"));
                    }}
                  >
                    {t("auth.mfa-enrol.scan.copyKey")}
                  </Button>
                </div>
              </div>
              <div>
                <Button
                  variant="primary"
                  onClick={() => {
                    setStep("verify");
                  }}
                >
                  {t("auth.mfa-enrol.scan.next")}
                </Button>
              </div>
            </>
          ) : null}
        </section>
      ) : null}

      {step === "verify" ? (
        <form
          noValidate
          aria-labelledby={titleId}
          className="flex flex-col gap-3"
          onSubmit={(event) => void verify(event)}
        >
          <p className="text-body text-fg-2">{t("auth.mfa-enrol.verify.description")}</p>
          {refusal === null ? null : (
            <div id={errorId} data-testid="SF-22-banner-error">
              <Banner tone="negative" title={refusal} />
            </div>
          )}
          <Field name="code" label={t("auth.mfa-enrol.verify.code")} required width="text">
            {(control) => (
              <input
                {...control}
                aria-describedby={describedBy(control, invalid ? errorId : null)}
                aria-invalid={invalid ? true : undefined}
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoCapitalize="none"
                spellCheck={false}
                value={code}
                onChange={(event) => {
                  setCode(event.target.value);
                }}
                className={controlClass(invalid)}
              />
            )}
          </Field>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" type="submit" loading={confirm.pending}>
              {t("auth.mfa-enrol.verify.submit")}
            </Button>
            <Button
              variant="link"
              size="sm"
              onClick={() => {
                setRefusal(null);
                setStep("scan");
              }}
            >
              {t("auth.mfa-enrol.verify.back")}
            </Button>
          </div>
        </form>
      ) : null}

      {step === "recovery" ? (
        <section aria-labelledby={titleId} className="flex flex-col gap-3">
          <p className="text-body text-fg-2">{t("auth.mfa-enrol.recovery.description")}</p>
          <ol
            aria-label={t("auth.mfa-enrol.recovery.list")}
            data-testid="SF-22-mfa-recovery-codes"
            data-volatile=""
            className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-body text-fg-1"
          >
            {codes.map((recoveryCode) => (
              <li key={recoveryCode}>{recoveryCode}</li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={CopySimple}
              onClick={() => {
                void copy(recoveryCodesText(codes), t("auth.mfa-enrol.recovery.copied"));
              }}
            >
              {t("auth.mfa-enrol.recovery.copy")}
            </Button>
            <Button variant="secondary" size="sm" icon={DownloadSimple} onClick={download}>
              {t("auth.mfa-enrol.recovery.download")}
            </Button>
          </div>
          <label htmlFor={checkboxId} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={checkboxId}
              type="checkbox"
              checked={stored}
              onChange={(event) => {
                setStored(event.target.checked);
              }}
              className="size-4"
            />
            {t("auth.mfa-enrol.recovery.acknowledge")}
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              loading={finishing}
              aria-describedby={stored ? undefined : reasonId}
              disabledReason={stored ? undefined : continueReason}
              onClick={() => {
                void finish();
              }}
            >
              {t("auth.mfa-enrol.recovery.continue")}
            </Button>
            {stored ? null : (
              <p id={reasonId} className="text-body-sm text-fg-2">
                {continueReason}
              </p>
            )}
          </div>
        </section>
      ) : null}
    </AuthFrame>
  );
}

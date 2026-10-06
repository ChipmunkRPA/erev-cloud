// SF-15:profile Profile (SCREENS_B §9.9; SCREENS §0.4 RT-73, SCR-IA-03, SCR-PERM-05; DESIGN_SYSTEM
// DS-DEN-01, DS-I18N-02, DS-I18N-03, DS-CMP-11, DS-CMP-31; 04 API-R-03 `GET /me`,
// `PATCH /me/preferences`, `POST /me/recovery-codes`; 03 REQ-UX-008, REQ-UX-022). The signed-in
// user's security, formats and display preferences, and workspaces. Number format, theme, density and
// single-key shortcuts apply at once: theme and density through the shell's display preferences
// (mirrored to `erev.theme` and `erev.density`), each change stored with `PATCH /me/preferences`.
// "Regenerate recovery codes" confirms, sends the command (a stale MFA verification opens the step-up
// modal and resends with the same Idempotency-Key), then shows the ten codes once in the dialog
// "Recovery codes", whose "Done" waits for the acknowledgement checkbox. The Password row offers "Change
// password", which opens SF-22:password-change (SCREENS_B §9.9; rev 1.8 closes L3-3-Q-12 and L3-3-Q-13,
// D-98 candidate 24 Q4); it shows no "Last changed" date, which API-S-Me does not carry. Role names are
// not rendered. The breadcrumb and the "Your preferences" route tabs come from `SettingsPageHeader`
// (SCR-IA-03).
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";

import { MFA_ENROL_PATH } from "../../app/auth/MfaGate";
import { openTenantId } from "../../app/shell/open-workspace";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { DENSITIES, THEMES, useDisplayPreferences } from "../../app/shell/UserMenu";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field, fieldId, fieldLabelId } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Switch } from "../../components/form/Switch";
import { Button } from "../../components/ui/Button";
import { trapTab, useModalFocus } from "../../components/ui/dialog";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { type Me, useMe, useUpdatePreferences } from "../../lib/api/queries/me";
import { queryKeys } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { formatNumber } from "../../lib/format";
import { t, UI_LOCALE } from "../../lib/i18n/t";
import { PASSWORD_CHANGE_ROUTE } from "../auth/password-change";
import { SettingsPageHeader } from "./index";

type RecoveryCodesOut = components["schemas"]["RecoveryCodesOut"];
type SessionMfaOut = components["schemas"]["SessionMfaOut"];

export const RECOVERY_CODES_PATH = "/api/v1/me/recovery-codes";
export const STEP_UP_PATH = "/api/v1/session/mfa";
/** The file name of the downloaded codes, as SF-22:mfa-enrol names it (BUILD_SPEC WEB-13). */
export const RECOVERY_CODES_FILE = "erev-recovery-codes.txt";
/** DS-I18N-03 example figure. */
export const FORMAT_EXAMPLE = "1234567.89";
/**
 * The Number format choices (DS-I18N-02 `format_locale`, BCP 47). SCREENS_B §9.9 names no list; these
 * cover the DS-I18N-03 separators and stay within the DS-CMP-21 select limit (L3-3-Q-14).
 */
export const FORMAT_LOCALES: readonly string[] = [
  "en-US",
  "en-GB",
  "de-DE",
  "fr-FR",
  "es-ES",
  "it-IT",
  "nl-NL",
  "sv-SE",
  "ja-JP",
];

const LANGUAGE_NAMES = new Intl.DisplayNames([UI_LOCALE], {
  type: "language",
  languageDisplay: "standard",
});

/** The English name of a BCP 47 tag, for example "German (Germany)"; an unknown tag shows itself. */
export function localeLabel(tag: string): string {
  try {
    return LANGUAGE_NAMES.of(tag) ?? tag;
  } catch {
    return tag;
  }
}

/** The select's locales: the list, with a stored tag outside it first. */
export function formatLocaleChoices(current: string): readonly string[] {
  return FORMAT_LOCALES.includes(current) ? FORMAT_LOCALES : [current, ...FORMAT_LOCALES];
}

const ROW = "grid grid-cols-[minmax(0,14rem)_minmax(0,1fr)] items-center gap-4 py-3";
const LINK_BUTTON =
  "inline-flex h-[var(--control-h)] items-center justify-center whitespace-nowrap rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover active:bg-active";

export function Profile() {
  const me = useMe();
  const title = t("settings.profile.title");

  let body;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else {
    body = <ProfileSections me={me.data} />;
  }

  return (
    <div className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={title} group="preferences">
        {me.data === undefined ? null : (
          <p data-testid="SF-15-profile-identity" className="flex gap-1.5 text-body-sm text-fg-2">
            <span>{me.data.user.display_name}</span>
            <span aria-hidden="true">·</span>
            <span>{me.data.user.email}</span>
          </p>
        )}
      </SettingsPageHeader>
      {body}
    </div>
  );
}

function ProfileSections({ me }: { readonly me: Me }) {
  const securityId = useId();
  const formatsId = useId();
  const workspacesId = useId();
  const toast = useToast();
  const { update } = useUpdatePreferences();
  const { theme, density, chooseTheme, chooseDensity } = useDisplayPreferences();
  const locale = me.preferences.format_locale;
  const localeField = "format_locale";

  const save = useCallback(
    async (patch: Parameters<typeof update>[0]) => {
      const outcome = await update(patch);
      if (outcome.kind === "failed") {
        toast.show({ tone: "negative", message: outcome.problem.detail ?? outcome.problem.title });
      }
    },
    [toast, update],
  );

  const memberships = me.memberships.filter((membership) => membership.status === "ACTIVE");
  // The current workspace is the session's: a workspace and its copies hold one membership id.
  const openId = openTenantId(useShellSession());

  return (
    <>
      <section
        aria-labelledby={securityId}
        data-testid="SF-15-profile-security"
        className="flex flex-col"
      >
        <h2 id={securityId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
          {t("settings.profile.security.title")}
        </h2>
        <div className={ROW}>
          <span className="text-body-sm font-medium text-fg-1">
            {t("settings.profile.password.label")}
          </span>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <Link to={PASSWORD_CHANGE_ROUTE} className={LINK_BUTTON}>
              {t("settings.profile.password.change")}
            </Link>
          </div>
        </div>
        <div className={ROW}>
          <span className="text-body-sm font-medium text-fg-1">
            {t("settings.profile.mfa.label")}
          </span>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-body-sm text-fg-2">
              {t(
                me.mfa.enrolled
                  ? "settings.profile.mfa.enrolled"
                  : "settings.profile.mfa.notEnrolled",
              )}
            </span>
            {me.mfa.enrolled ? (
              <RegenerateRecoveryCodes />
            ) : (
              <Link to={MFA_ENROL_PATH} className={LINK_BUTTON}>
                {t("settings.profile.mfa.setUp")}
              </Link>
            )}
          </div>
        </div>
      </section>

      <section aria-labelledby={formatsId} className="flex flex-col">
        <h2 id={formatsId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
          {t("settings.profile.formats.title")}
        </h2>
        <div className={ROW}>
          <label
            id={fieldLabelId(localeField)}
            htmlFor={fieldId(localeField)}
            className="text-body-sm font-medium text-fg-1"
          >
            {t("settings.profile.formats.numberFormat")}
          </label>
          <div className="flex flex-wrap items-center gap-4">
            <div className="w-64">
              <Select
                control={{ id: fieldId(localeField), name: localeField }}
                options={formatLocaleChoices(locale).map((tag) => ({
                  value: tag,
                  label: localeLabel(tag),
                }))}
                value={locale}
                onChange={(tag) => {
                  if (tag !== locale) {
                    void save({ format_locale: tag });
                  }
                }}
              />
            </div>
            <span className="text-body-sm text-fg-2 tabular-nums">
              {t("settings.profile.formats.example", {
                value: formatNumber(FORMAT_EXAMPLE, { locale }),
              })}
            </span>
          </div>
        </div>
        <div className={ROW}>
          <span aria-hidden="true" className="text-body-sm font-medium text-fg-1">
            {t("settings.profile.formats.theme")}
          </span>
          <div>
            <SegmentedControl
              label={t("settings.profile.formats.theme")}
              options={THEMES.map((value) => ({
                value,
                label: t(`shell.userMenu.themes.${value}`),
              }))}
              value={theme}
              onChange={chooseTheme}
            />
          </div>
        </div>
        <div className={ROW}>
          <span aria-hidden="true" className="text-body-sm font-medium text-fg-1">
            {t("settings.profile.formats.density")}
          </span>
          <div>
            <SegmentedControl
              label={t("settings.profile.formats.density")}
              options={DENSITIES.map((value) => ({
                value,
                label: t(`shell.userMenu.densities.${value}`),
              }))}
              value={density}
              onChange={chooseDensity}
            />
          </div>
        </div>
        <div className={ROW}>
          <div className="col-span-2">
            <Switch
              label={t("settings.profile.formats.shortcuts")}
              checked={me.preferences.shortcuts_enabled}
              onChange={(checked) => {
                void save({ shortcuts_enabled: checked });
              }}
            />
          </div>
        </div>
      </section>

      <section aria-labelledby={workspacesId} className="flex flex-col">
        <h2 id={workspacesId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
          {t("settings.profile.workspaces.title")}
        </h2>
        <ul className="flex flex-col">
          {memberships.map((membership) => (
            <li
              key={membership.tenant.id}
              className="flex flex-wrap items-center gap-2 border-b border-hairline py-3 text-body-sm text-fg-1"
            >
              {membership.tenant.display_name}
              {membership.tenant.kind === "sandbox" ? <StatusChip status="Sandbox" /> : null}
              {membership.tenant.id === openId ? (
                <OutlineChip label={t("shell.tenantSwitcher.current")} />
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

type RecoveryStage = "idle" | "confirm" | "step-up" | "codes";

/** "Regenerate recovery codes": confirmation, SCR-PERM-05 step-up when needed, then the codes dialog. */
export function RegenerateRecoveryCodes() {
  const toast = useToast();
  const regenerate = useCommand<RecoveryCodesOut>({ method: "POST", path: RECOVERY_CODES_PATH });
  const [stage, setStage] = useState<RecoveryStage>("idle");
  const [codes, setCodes] = useState<readonly string[]>([]);
  const trigger = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setStage("idle");
    trigger.current?.focus();
  }, []);

  const send = async () => {
    const outcome = await regenerate.submit();
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      setCodes(outcome.data.recovery_codes);
      setStage("codes");
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === "mfa-step-up-required") {
      setStage("step-up");
      return;
    }
    if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: outcome.problem.detail ?? outcome.problem.title });
      close();
    }
  };

  return (
    <>
      <Button
        ref={trigger}
        variant="secondary"
        onClick={() => {
          setStage("confirm");
        }}
      >
        {t("settings.profile.recovery.regenerate")}
      </Button>
      <Modal
        open={stage === "confirm"}
        variant="confirmation"
        title={t("settings.profile.recovery.confirmTitle")}
        description={t("settings.profile.recovery.confirmDescription")}
        primaryAction={{
          label: t("settings.profile.recovery.confirmAction"),
          destructive: true,
          onAction: () => {
            void send();
          },
        }}
        submitting={regenerate.pending}
        onClose={close}
      />
      {stage === "step-up" ? (
        <StepUpModal
          onCancel={close}
          onVerified={() => {
            void send();
          }}
        />
      ) : null}
      {stage === "codes" ? <RecoveryCodesDialog codes={codes} onDone={close} /> : null}
    </>
  );
}

interface StepUpModalProps {
  readonly onCancel: () => void;
  readonly onVerified: () => void;
}

/** SCR-PERM-05 step-up: a fresh TOTP verification through `POST /session/mfa` (BS1-D-19). */
export function StepUpModal({ onCancel, onVerified }: StepUpModalProps) {
  const queryClient = useQueryClient();
  const verify = useCommand<SessionMfaOut>({ method: "POST", path: STEP_UP_PATH });
  const formId = useId();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (verify.pending) {
      return;
    }
    setError(null);
    const outcome = await verify.submit({ code: code.trim() });
    if (outcome.kind === "failed") {
      setError(
        outcome.problem.status === 422
          ? t("settings.profile.stepUp.wrongCode")
          : (outcome.problem.detail ?? outcome.problem.title),
      );
      return;
    }
    if (outcome.kind === "succeeded") {
      if (outcome.data !== null) {
        queryClient.setQueryData<SessionMfaOut>(queryKeys.session(), outcome.data);
      }
      onVerified();
    }
  };

  return (
    <Modal
      open
      variant="form"
      title={t("settings.profile.stepUp.title")}
      primaryAction={{ label: t("settings.profile.stepUp.confirm"), form: formId }}
      submitting={verify.pending}
      onClose={onCancel}
    >
      <form id={formId} noValidate onSubmit={(event) => void submit(event)}>
        <Field name="step_up_code" label={t("settings.profile.stepUp.code")} required error={error}>
          {(control) => (
            <input
              {...control}
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              spellCheck={false}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
              }}
              className={controlClass(error !== null)}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}

interface RecoveryCodesDialogProps {
  readonly codes: readonly string[];
  readonly onDone: () => void;
}

/**
 * DS-CMP-11 dialog "Recovery codes": the codes shown once, "Copy codes", "Download codes (TXT)" and the
 * required acknowledgement. There is no Cancel, and Esc does not close it before the acknowledgement.
 */
export function RecoveryCodesDialog({ codes, onDone }: RecoveryCodesDialogProps) {
  const toast = useToast();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const reasonId = useId();
  const checkboxId = useId();
  const [stored, setStored] = useState(false);
  useModalFocus({ panel });

  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (stored) {
          onDone();
        }
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => root.removeEventListener("keydown", onKeyDown);
  }, [stored, onDone]);

  const text = `${codes.join("\n")}\n`;
  const copy = async () => {
    if (typeof navigator.clipboard === "undefined") {
      return;
    }
    await navigator.clipboard.writeText(text);
    toast.show({ tone: "positive", message: t("settings.profile.recovery.copied") });
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = RECOVERY_CODES_FILE;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "15vh" }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="SF-15-drawer-recovery-codes"
        className="flex max-h-full w-[var(--modal-w-md)] max-w-full flex-col self-start rounded-xl border border-hairline bg-raised shadow-overlay"
      >
        <div className="px-5 pt-5">
          <h2 id={titleId} className="text-title-md text-fg-1">
            {t("settings.profile.recovery.title")}
          </h2>
        </div>
        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-5 pt-4">
          <ol
            aria-label={t("settings.profile.recovery.list")}
            className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-body-sm text-fg-1"
          >
            {codes.map((code) => (
              <li key={code}>{code}</li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => void copy()}>
              {t("settings.profile.recovery.copy")}
            </Button>
            <Button variant="secondary" size="sm" onClick={download}>
              {t("settings.profile.recovery.download")}
            </Button>
          </div>
          <label htmlFor={checkboxId} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={checkboxId}
              type="checkbox"
              required
              checked={stored}
              onChange={(event) => {
                setStored(event.target.checked);
              }}
              className="size-4"
            />
            {t("settings.profile.recovery.acknowledge")}
          </label>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3 px-5 py-4">
          {stored ? null : (
            <p id={reasonId} className="text-body-sm text-fg-2">
              {t("settings.profile.recovery.doneReason")}
            </p>
          )}
          <Button
            variant="primary"
            aria-describedby={stored ? undefined : reasonId}
            disabledReason={stored ? undefined : t("settings.profile.recovery.doneReason")}
            onClick={onDone}
          >
            {t("settings.profile.recovery.done")}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

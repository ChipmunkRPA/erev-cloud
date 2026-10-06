// SF-14:security Security (SCREENS_B §9.14; SCREENS §0.4 RT-91, §0.3 SCR-IA-03, §0.7 SCR-PERM-01;
// DESIGN_SYSTEM DS-CMP-19; 04 §16.12 API-S-Session `capabilities.identity_providers`; REQ-PLT-004 to
// REQ-PLT-007; J-22.10; BUILD_SPEC WEB-22). The Settings frame with the Access route tabs and three
// read-only regions: "Sign-in methods" (email and password, Active; the global identity providers of
// `GET /session`, else "OIDC none configured"), "Password rules" (a list: length, not the email, not a
// common password, the lockout rule) and "Multi-factor authentication". The "Sessions" form (idle
// timeout, role-assignment approval) binds API-R-13 and is added by the RFD item that builds it
// (BS1-D-15): nothing of it renders here.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";

import { fetchSession } from "../../app/auth/RequireSession";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useMe } from "../../lib/api/queries/me";
import { SETTINGS_MANAGE_PERMISSION } from "../../lib/api/queries/support-grants";
import { queryKeys } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "../settings/index";

const ROW =
  "flex items-center justify-between gap-4 border-b border-hairline py-2.5 last:border-b-0";

/** SCREENS_B §9.14 "Password rules", in the wireframe's order. */
export function passwordRuleKeys(): readonly string[] {
  return [
    "access.security.passwordRules.length",
    "access.security.passwordRules.notEmail",
    "access.security.passwordRules.notCommon",
    "access.security.passwordRules.lockout",
  ];
}

function activeChip(): string {
  return chipFor("E-78", "ACTIVE")?.status ?? "Active";
}

function Region({
  title,
  testId,
  children,
}: {
  readonly title: string;
  readonly testId: string;
  readonly children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col">
      <h2 id={headingId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
        {title}
      </h2>
      {children}
    </section>
  );
}

function SignInMethods() {
  const session = useQuery({ queryKey: queryKeys.session(), queryFn: fetchSession });
  const providers = session.data?.capabilities.identity_providers ?? [];
  return (
    <Region title={t("access.security.signIn.title")} testId="SF-14-security-sign-in">
      <ul className="flex flex-col">
        <li className={ROW}>
          <span className="text-body-sm font-medium text-fg-1">
            {t("access.security.signIn.password")}
          </span>
          <StatusChip status={activeChip()} />
        </li>
        {providers.length === 0 ? (
          <li className={ROW}>
            <span className="text-body-sm font-medium text-fg-1">
              {t("access.security.signIn.oidc")}
            </span>
            <span className="text-body-sm text-fg-3">
              {t("access.security.signIn.noneConfigured")}
            </span>
          </li>
        ) : (
          providers.map((provider) => (
            <li key={provider.code} className={ROW}>
              <span className="text-body-sm font-medium text-fg-1">{provider.name}</span>
              <StatusChip status={activeChip()} />
            </li>
          ))
        )}
      </ul>
    </Region>
  );
}

function SecurityPage() {
  return (
    <div className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6">
      <SignInMethods />
      <Region
        title={t("access.security.passwordRules.title")}
        testId="SF-14-security-password-rules"
      >
        <ul className="flex list-disc flex-col gap-1 py-2.5 ps-5 text-body-sm text-fg-1">
          {passwordRuleKeys().map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ul>
      </Region>
      <Region title={t("access.security.mfa.title")} testId="SF-14-security-mfa">
        <p className="py-2.5 text-body-sm text-fg-1">{t("access.security.mfa.text")}</p>
      </Region>
    </div>
  );
}

export function SecurityScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("access.security.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsForAll(SETTINGS_MANAGE_PERMISSION)) {
    // The sign-in rules are the workspace's, one for all entities: the page is read by a holder of
    // `settings.manage` for all of them (SCREENS §0.6 SCR-PERM-02 (c)).
    body = (
      <AccessLimited
        area={title}
        permissions={[SETTINGS_MANAGE_PERMISSION]}
        allEntities={
          access.holdsAnywhere(SETTINGS_MANAGE_PERMISSION)
            ? {
                message: "access.security.access.allEntities",
                permission: SETTINGS_MANAGE_PERMISSION,
              }
            : undefined
        }
      />
    );
  } else {
    body = <SecurityPage />;
  }
  return (
    <div
      data-testid="SF-14-security-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access" />
      {body}
    </div>
  );
}

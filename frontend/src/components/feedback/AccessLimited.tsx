// The access-limited state of a page (SCREENS §0.6 SCR-PERM-01 and SCR-PERM-02 (c), rev 1.71; §0.7
// SCR-ST-06; DESIGN_SYSTEM DS-CMP-23; docs/dev-guide.md DG-FE-16 rev 1.274). The title names the area;
// the description says what to ask a workspace administrator for and names the permission as
// src/lib/permission-words.ts builds it: the phrase and, in parentheses and in mono, the code.
import { t } from "../../lib/i18n/t";
import {
  PHRASED_PERMISSIONS,
  type PhrasedPermission,
  permissionWords,
} from "../../lib/permission-words";
import { EmptyState } from "./EmptyState";

export interface AccessLimitedProps {
  /** The area of the title, "You do not have access to <area>". */
  readonly area: string;
  /** The permission the page's gate asks; several when any of them opens the page. */
  readonly permissions: readonly [PhrasedPermission, ...PhrasedPermission[]];
  /**
   * A page of the whole workspace, for a member who holds its permission for named entities only
   * (SCR-PERM-02 (c)): the page's own sentence, a message with `{permission}` — "<Area> covers every
   * entity of the workspace. Ask a workspace administrator for a role that includes {permission} for
   * all entities." — and the permission it names. Absent, the member holds none of `permissions` and
   * reads the description of SCR-PERM-01.
   */
  readonly allEntities?:
    { readonly message: string; readonly permission: PhrasedPermission } | undefined;
}

export function AccessLimited({ area, permissions, allEntities }: AccessLimitedProps) {
  return (
    <EmptyState
      title={t("settings.access.title", { area })}
      description={
        allEntities === undefined
          ? t("settings.access.description", { permission: permissionWords(...permissions) })
          : t(allEntities.message, { permission: permissionWords(allEntities.permission) })
      }
      identifiers={PHRASED_PERMISSIONS}
    />
  );
}

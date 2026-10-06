// The words of a permission in a sentence (SCREENS §0.6 SCR-PERM-01, rev 1.71; docs/dev-guide.md
// DG-FE-16 rev 1.274; item W-12e). A sentence that names a permission has two readers. The member who
// meets it is no administrator and reads the phrase. The workspace administrator she asks looks for
// the code: the word the Roles screen prints in the header of the permission's row. So the naming is
// the phrase and, in parentheses, the code. It is built here and nowhere else, from the constant the
// gate asks: no sentence of the catalogue spells a phrase or a code of its own.
import { formatList } from "./format";
import { t } from "./i18n/t";

/**
 * The permissions a sentence can name: each has a phrase in the catalogue, `permission.phrase.<code>`.
 * `frontend/config/permission-phrases.test.ts` holds this list and those keys to one set, each code to
 * a permission the API's document names, and each to a sentence of the product that names it.
 */
export const PHRASED_PERMISSIONS = [
  "access.approve",
  "api_client.manage",
  "audit.read",
  "migration.run",
  "settings.manage",
  "support_grant.approve",
  "tenant.snapshot",
  "webhook.manage",
] as const;

/** A permission that has a phrase: a sentence for any other does not compile. */
export type PhrasedPermission = (typeof PHRASED_PERMISSIONS)[number];

/**
 * The phrase of the catalogue carries the place of the code, "managing workspace settings ({code})",
 * so that a translation orders the two and sets the brackets as its language does; the code itself
 * comes from the constant.
 */
function naming(code: PhrasedPermission): string {
  return t(`permission.phrase.${code}`, { code });
}

/**
 * The naming of the permission a gate asks, for a sentence: "managing workspace settings
 * (settings.manage)". A page that any of several permissions opens names them all, joined with "or".
 */
export function permissionWords(
  first: PhrasedPermission,
  ...others: readonly PhrasedPermission[]
): string {
  return formatList([first, ...others].map(naming), "or");
}

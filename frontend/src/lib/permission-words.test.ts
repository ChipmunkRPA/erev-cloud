// The words of a permission in a sentence (SCREENS §0.6 SCR-PERM-01 rev 1.71; docs/dev-guide.md
// DG-FE-16 rev 1.274): the phrase the member reads and, in parentheses, the code the Roles screen
// prints — built from the constant the gate asks.
import { describe, expect, it } from "vitest";

import { PHRASED_PERMISSIONS, permissionWords } from "./permission-words";

describe("the naming of a permission in a sentence", () => {
  it("is the phrase and, in parentheses, the code", () => {
    expect(permissionWords("settings.manage")).toBe(
      "managing workspace settings (settings.manage)",
    );
    expect(permissionWords("audit.read")).toBe("viewing the audit log (audit.read)");
  });

  it("joins the permissions any of which opens a page with or", () => {
    expect(permissionWords("api_client.manage", "webhook.manage")).toBe(
      "managing API clients (api_client.manage) or managing webhooks (webhook.manage)",
    );
  });

  it("names every permission of its list, each with its own code", () => {
    for (const code of PHRASED_PERMISSIONS) {
      expect(permissionWords(code).endsWith(` (${code})`)).toBe(true);
      expect(permissionWords(code).startsWith(code)).toBe(false);
    }
  });

  it("does not compile for a permission without a phrase", () => {
    // @ts-expect-error -- `journal.run` has no phrase: no sentence names it.
    expect(() => permissionWords("journal.run")).toThrow("permission.phrase.journal.run");
  });
});

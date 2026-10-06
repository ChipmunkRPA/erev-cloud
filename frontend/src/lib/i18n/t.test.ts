// DS-I18N-01 and DS-I18N-06 (DESIGN_SYSTEM §9; docs/dev-guide.md DG-FE-11): named placeholders,
// plural keys through Intl.PluralRules, strict missing keys and pseudo-localisation.
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { pluralCategory } from "./plural";
import { PLACEHOLDER } from "./pseudo";
import { configureI18n, t } from "./t";

afterEach(() => {
  configureI18n({ search: "" });
  vi.restoreAllMocks();
});

const PLURAL_SUFFIX = /\.(zero|one|two|few|many|other)$/;

describe("DS-I18N-01 and DS-I18N-06", () => {
  it("interpolates named placeholders into plural variants", () => {
    expect(t("approvals.approveN", { count: 2 })).toBe("Approve 2 items");
    expect(t("approvals.approveN", { count: 1 })).toBe("Approve 1 item");
    expect(t("approvals.approveN", { count: 0 })).toBe("Approve 0 items");
  });

  it("resolves plural keys through Intl.PluralRules", () => {
    const select = vi.spyOn(Intl.PluralRules.prototype, "select");

    t("approvals.approveN", { count: 5 });

    expect(select).toHaveBeenCalledWith(5);
    expect(pluralCategory("en", 1)).toBe("one");
    expect(pluralCategory("pl", 5)).toBe("many");
  });

  it("throws under test for a missing key or parameter", () => {
    expect(() => t("approvals.missingKey")).toThrow("Missing message key: approvals.missingKey");
    expect(() => t("approvals.approveN.other")).toThrow(
      "Message approvals.approveN.other needs the parameter count",
    );
  });

  it("renders every catalogue string accented and at least 35% longer with ?pseudo=1", () => {
    const catalogue: Record<string, string> = messages;
    for (const [key, text] of Object.entries(catalogue)) {
      const plural = PLURAL_SUFFIX.exec(key);
      const base = plural === null ? key : key.slice(0, plural.index);
      const params: Record<string, string | number> = {};
      for (const match of text.matchAll(PLACEHOLDER)) {
        params[match[1] ?? ""] = "Value";
      }
      if (plural !== null) {
        params.count = plural[1] === "one" ? 1 : 7;
      }

      configureI18n({ search: "" });
      const plain = t(base, params);
      configureI18n({ search: "?entity=AVM-US&pseudo=1" });
      const pseudo = t(base, params);

      expect(pseudo).not.toBe(plain);
      expect(pseudo).toMatch(/[À-ɏḀ-ỿ]/);
      expect(pseudo.length).toBeGreaterThanOrEqual(plain.length * 1.35);
    }
  });

  it("keeps interpolated values unaccented in pseudo mode", () => {
    configureI18n({ search: "?pseudo=1" });

    expect(t("approvals.approveN", { count: 12 })).toContain("12");
  });
});

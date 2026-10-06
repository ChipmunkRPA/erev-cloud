// @vitest-environment jsdom
// 04 E-08 as the API states it (`docs/api/openapi.json`) against the two hand-kept tables of the
// screens: `SUBJECT_TYPES`, the options of the Type filter (SCREENS §15.3), and the catalogue's
// `approvals.subjectType.<literal>` labels. The API hands the inbox, the bulk dialog, the request view,
// the home page and a contract's history a `subject.type`, and `t()` throws on a key the catalogue
// lacks (a production build prints the key), so a subject type the server gains reaches both tables in
// the same change (lane SECFIX-IMP part B, `EVIDENCE_SHRED`; SCREENS rev 1.15, which also names the
// label `MIGRATION_SSP_REPLAY` had lacked since 04 rev 1.72).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { hasMessage } from "../../i18n/t";
import { SUBJECT_TYPES } from "./approvals";

const HERE = dirname(fileURLToPath(import.meta.url));

interface OpenApi {
  readonly components: {
    readonly schemas: Readonly<Record<string, { readonly enum?: readonly string[] }>>;
  };
}

/** E-08 `approval_subject_type` in the order the API document lists it. */
function apiSubjectTypes(): readonly string[] {
  const file = resolve(HERE, "../../../../../docs/api/openapi.json");
  const document = JSON.parse(readFileSync(file, "utf8")) as OpenApi;
  return document.components.schemas.ApprovalSubjectType?.enum ?? [];
}

describe("the subject types of the Type filter and their labels", () => {
  it("are 04 E-08 as the API document states it, in its order", () => {
    const api = apiSubjectTypes();
    expect(api).toContain("EVIDENCE_SHRED");
    expect([...SUBJECT_TYPES]).toEqual([...api]);
  });

  it("each have a catalogue label", () => {
    for (const type of SUBJECT_TYPES) {
      expect(hasMessage(`approvals.subjectType.${type}`), type).toBe(true);
    }
  });
});

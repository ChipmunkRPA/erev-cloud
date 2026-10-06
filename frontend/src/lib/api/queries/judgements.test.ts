// @vitest-environment jsdom
// The word of a judgement record's status (SCREENS §0.8, rev 1.66; 04 E-57 rev 1.242) and the two
// questions the screens ask of a record. Three screens read the status through a catalogue key
// without a fallback: `t()` throws on a key the catalogue lacks (a production build prints the key),
// and E-57 gained `VOIDED` with the discard of a draft. One function reads the word now; it holds a
// word for every status the API document states, and a literal the document does not state reads as
// itself.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { hasMessage } from "../../i18n/t";
import {
  discardable,
  judgementDiscardPath,
  judgementStatusLabel,
  recordStands,
} from "./judgements";

const HERE = dirname(fileURLToPath(import.meta.url));

interface OpenApi {
  readonly components: {
    readonly schemas: Readonly<Record<string, { readonly enum?: readonly string[] }>>;
  };
}

/** E-57 `judgement_status` in the order the API document lists it. */
function apiStatuses(): readonly string[] {
  const file = resolve(HERE, "../../../../../docs/api/openapi.json");
  const document = JSON.parse(readFileSync(file, "utf8")) as OpenApi;
  return document.components.schemas.JudgementStatus?.enum ?? [];
}

describe("the status of a judgement record in words", () => {
  it("the status of a judgement record has a word for every status of 04 E-57 as the API document states it", () => {
    const api = apiStatuses();
    expect(api).toContain("VOIDED");
    expect(
      api.filter((status) => !hasMessage(`contracts.workbench.step1.status.${status}`)),
    ).toEqual([]);
    expect(api.map((status) => [status, judgementStatusLabel(status)])).toEqual([
      ["DRAFT", "Draft"],
      // "Submitted" names the preparer's act; the state is a wait.
      ["SUBMITTED", "Waiting for review"],
      ["REVIEWED", "Reviewed"],
      ["REJECTED", "Rejected"],
      ["SUPERSEDED", "Superseded"],
      // A discarded draft, as a discarded estimate version and modification read.
      ["VOIDED", "Void"],
    ]);
  });

  it("a status the catalogue does not name reads as itself", () => {
    expect(judgementStatusLabel("ESCALATED")).toBe("ESCALATED");
  });
});

describe("what a screen asks of a judgement record", () => {
  it("a record stands while it is sent for review or reviewed", () => {
    expect(
      ["DRAFT", "SUBMITTED", "REVIEWED", "REJECTED", "SUPERSEDED", "VOIDED", "ESCALATED"].filter(
        recordStands,
      ),
    ).toEqual(["SUBMITTED", "REVIEWED"]);
  });

  const record = (status: string, topic = "COLLECTIBILITY", subject = "contract") =>
    ({ status, topic, subject_type: subject }) as Parameters<typeof discardable>[0];

  it("a draft is discarded on a screen unless it is the proposal of a combination group", () => {
    expect(discardable(record("DRAFT"))).toBe(true);
    expect(discardable(record("DRAFT", "CONSTRAINT", "estimate_version"))).toBe(true);
    expect(discardable(record("DRAFT", "MODIFICATION_TREATMENT_OVERRIDE", "modification"))).toBe(
      true,
    );
    // The API answers 409 "This record is the proposal of a combination group. It is decided with
    // its group.": the screen knows the record by its topic and its subject and offers nothing.
    expect(discardable(record("DRAFT", "COMBINATION", "combination_group"))).toBe(false);
    // A COMBINATION record of another subject is a record like any other.
    expect(discardable(record("DRAFT", "COMBINATION", "contract"))).toBe(true);
    for (const status of ["SUBMITTED", "REVIEWED", "SUPERSEDED", "VOIDED"]) {
      expect(discardable(record(status))).toBe(false);
    }
  });

  // PRD SM-10 rev 1.199 (04 rev 1.296; item JDG-REJECTED-EXIT-1): the discard takes a rejected
  // record as it takes a draft — it failed the activation checklist with no exit on a screen.
  it("a rejected record is discarded on a screen as a draft is", () => {
    expect(discardable(record("REJECTED"))).toBe(true);
    expect(discardable(record("REJECTED", "POB_DISTINCT_OVERRIDE", "obligation"))).toBe(true);
    expect(discardable(record("REJECTED", "CONSTRAINT", "estimate_version"))).toBe(true);
    // The rejected proposal of a combination group stays the group's (the API answers 409).
    expect(discardable(record("REJECTED", "COMBINATION", "combination_group"))).toBe(false);
  });

  it("the discard is a POST on the record's path", () => {
    expect(judgementDiscardPath("1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f")).toBe(
      "/api/v1/judgements/1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f/discard",
    );
  });
});

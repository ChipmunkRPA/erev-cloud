// SF-06:run and SF-06:run-batches, the toasts (SCREENS_B §3.2 and §3.4 rev 1.77; DESIGN_SYSTEM DS-CMP-22;
// BUILD_SPEC CLO-26; item JRN-RETRY-FOLLOW-1). A toast holds two lines and the kit cuts the third, which
// no test of rendered text sees. Rev 1.71 had the hand-over's instruction in its toast — three lines,
// cut after "record the" — and the API's sentence of a refused download, cut before its differences.
// Each sentence the two screens say in a toast is measured here, with values as the seeded world has
// them; an ending that needs more room is a banner of the frame.
import { describe, expect, it } from "vitest";

import { t } from "../../../lib/i18n/t";
import { textLines, TOAST_LINES, TOAST_MESSAGE_BOX } from "../../../test/text-lines";

const RUN = "JR-000209";
// A two-digit batch and chunk: wider than any the seeded world holds.
const BATCHES = ["1 · 2", "12 · 34"];

function toasts(): readonly string[] {
  return [
    t("journals.run.submit.done", { run: RUN }),
    t("journals.run.export.done", { run: RUN, acknowledged: 12, total: 34 }),
    t("journals.run.export.repeated"),
    t("journals.run.exit.cancelled", { run: RUN }),
    t("journals.run.exit.handedOverRun", { run: RUN }),
    t("common.command.noAnswer"),
    ...BATCHES.flatMap((batch) => [
      t("journals.run.exit.handedOver", { batch }),
      t("journals.run.retry.sent", { batch }),
      // A NetSuite document number, as the ledger answers it.
      t("journals.batches.record.done", { batch, reference: "JE-88412" }),
    ]),
  ];
}

describe("SF-06 journal run: toasts", () => {
  it("the toasts of the journal run fit the two lines of a toast", () => {
    const sentences = toasts();
    expect(sentences).toHaveLength(12);
    for (const sentence of sentences) {
      const lines = textLines(sentence, TOAST_MESSAGE_BOX);
      expect(lines.length, lines.join(" / ")).toBeLessThanOrEqual(TOAST_LINES);
    }
  });
});

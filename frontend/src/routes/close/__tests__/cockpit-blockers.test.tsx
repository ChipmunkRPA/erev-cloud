// @vitest-environment jsdom
// SF-05 blocker rows (SCREENS_B §1.1; 04 §16.8 rev 1.199): API-S-Period `blockers` is null in a
// row of `GET /periods` alone. The cockpit reads its own `period`, which carries the counts; a
// cockpit without them fails rather than reading "No blockers".
import { describe, expect, it } from "vitest";

import type { PeriodCockpit } from "../../../lib/api/queries/periods";
import { blockerRows } from "../cockpit";

describe("blockerRows", () => {
  it("fails on a cockpit whose period carries no blocker counts", () => {
    const cockpit = {
      period: {
        blockers: null,
        entity: { code: "AVM-US" },
        period: { period_key: "FY2026-P09" },
        book: "ASC606",
      },
      checklist: [],
    } as unknown as PeriodCockpit;
    expect(() => blockerRows(cockpit, { vcReassessmentMissing: 0 }, new Set())).toThrow(
      "API-S-PeriodCockpit period.blockers is null",
    );
  });
});

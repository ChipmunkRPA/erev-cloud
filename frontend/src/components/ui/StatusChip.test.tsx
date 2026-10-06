// @vitest-environment jsdom
// DS-CMP-19 (DESIGN_SYSTEM §7.5; SCREENS §0.8; SCREENS_B §0.4): the fixed status vocabulary and the
// mapping from 04 literals to chips.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatusChip, VOCABULARY, chipFor } from "./StatusChip";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// The DS-CMP-19 table as published: status | tone | icon.
const TABLE = `
Draft | neutral | PencilSimpleLine
Pending approval | info | HourglassMedium
Approved | positive | CheckCircle
Rejected | negative | XCircle
Withdrawn | neutral | ArrowUUpLeft
Stale | warning | ClockCounterClockwise
Active | neutral | Circle
Void | neutral | Prohibit
On hold | warning | PauseCircle
Satisfied | positive | CheckCircle
Valid | positive | CheckCircle
Warning | warning | WarningCircle
Error | negative | XCircle
Period open | neutral | LockSimpleOpen
Soft close | warning | HourglassMedium
Locked | neutral | LockSimple
Reopened | warning | LockSimpleOpen
Queued | neutral | CircleDashed
Running | info | CircleHalf
Succeeded | positive | CheckCircle
Failed | negative | XCircle
Exported | info | ArrowSquareOut
Posted | positive | CheckCircle
Reconciled | positive | CheckCircle
Difference | negative | Equals
Sandbox | warning | WarningCircle
Proposed | neutral, dashed edge | Sparkle
Abandoned | neutral | Prohibit
Accepted | positive | CheckCircle
Account locked | warning | LockSimple
Aggregated | neutral | TreeStructure
Applied | positive | CheckCircle
Archived | neutral | Prohibit
Auto-certified | positive | CheckCircle
Balanced | positive | CheckCircle
Blank | neutral | Minus
Blocked | warning | PauseCircle
Blocking | negative | XCircle
Budget exceeded | warning | WarningCircle
Calculated | neutral | PencilSimpleLine
Cancelled | neutral | Prohibit
Certified | positive | CheckCircle
Committed | positive | CheckCircle
Completed | positive | CheckCircle
Denied | negative | XCircle
Disabled | neutral | Prohibit
Dismissed | neutral | Prohibit
Expired | neutral | ClockCounterClockwise
Future | neutral | CalendarBlank
Imported | info | CheckCircle
In progress | info | CircleHalf
In review | info | CircleHalf
Info | info | Info
Invited | info | HourglassMedium
Met | positive | CheckCircle
Not a contract | neutral | Prohibit
Not applicable | neutral | Minus
Not mapped | warning | WarningCircle
Not passed | negative | XCircle
Not started | neutral | Circle
Open | neutral | Circle
Pass | positive | CheckCircle
Passed | positive | CheckCircle
Pending review | info | HourglassMedium
Permanently locked | neutral | LockSimple
Prepared | info | HourglassMedium
Profiled | info | CheckCircle
Promoted | positive | CheckCircle
Published | positive | CheckCircle
Removed | neutral | Prohibit
Resolved | positive | CheckCircle
Revocation requested | warning | WarningCircle
Reviewed | positive | CheckCircle
Revoked | neutral | Prohibit
Shortfall | warning | WarningCircle
Superseded | neutral | ClockCounterClockwise
Suspended | warning | PauseCircle
Terminated | neutral | Prohibit
Tested | info | CheckCircle
Timed out | warning | ClockCounterClockwise
Verification failed | negative | XCircle
Verified | positive | ShieldCheck
Waived | neutral | CheckCircle
`;

const ROWS = TABLE.trim()
  .split("\n")
  .map((line) => {
    const [word = "", tone = "", icon = ""] = line.split("|").map((cell) => cell.trim());
    return { word, tone: tone.split(",")[0] ?? "", dashed: tone.includes("dashed"), icon };
  });

describe("DS-CMP-19 vocabulary", () => {
  it("every word of the DS-CMP-19 table renders with its tone and icon", () => {
    expect(Object.keys(VOCABULARY).sort()).toEqual(ROWS.map((row) => row.word).sort());
    for (const row of ROWS) {
      const { container, unmount } = render(<StatusChip status={row.word} />);
      const chip = container.querySelector("[data-tone]");
      expect(chip?.textContent).toBe(row.word);
      expect(chip?.getAttribute("data-tone")).toBe(row.tone);
      expect(chip?.classList.contains("border-dashed")).toBe(row.dashed);
      const icon = chip?.querySelector("svg");
      expect(icon?.getAttribute("data-icon")).toBe(row.icon);
      expect(icon?.getAttribute("aria-hidden")).toBe("true");
      expect(icon?.getAttribute("width")).toBe("12");
      unmount();
    }
  });

  it("an unknown word throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<StatusChip status="Planned" />)).toThrow(
      /not DS-CMP-19 status vocabulary/,
    );
  });

  it("chipFor maps E-05 VOIDED by its void reason", () => {
    expect(chipFor("E-05", "VOIDED", { void_reason: "STALE_SUBJECT" })?.status).toBe("Stale");
    expect(chipFor("E-05", "VOIDED", { void_reason: "SUBJECT_VOIDED" })?.status).toBe("Void");
  });

  it("chipFor maps E-78 INVITED to Invited with tone info", () => {
    expect(chipFor("E-78", "INVITED")).toEqual({
      status: "Invited",
      tone: "info",
      icon: "HourglassMedium",
      caption: null,
    });
  });

  it("chipFor applies SCREENS_B §0.4 captions and shows no chip where the screens show none", () => {
    expect(chipFor("E-34", "draft", { job_state: "RUNNING" })).toMatchObject({
      status: "Running",
      caption: "Calculating",
    });
    expect(chipFor("E-34", "draft", { request_status: "PENDING" })).toMatchObject({
      status: "Pending approval",
      caption: "Submitted",
    });
    expect(chipFor("E-34", "exported", { acknowledged_batches: 2, batch_count: 5 })?.caption).toBe(
      "Partially acknowledged: 2 of 5 batches",
    );
    expect(chipFor("E-60", "FAILED")?.status).toBe("Not passed");
    expect(chipFor("E-40", "INVALID")?.caption).toBe("Rejected: fix the file and upload again");
    expect(chipFor("E-22", "UNSATISFIED")).toBeNull();
  });

  it("chipFor maps E-12 VOIDED, the discarded estimate version of ruling R-119 (e)", () => {
    // SCREENS §0.8 E-12 (rev 1.29): the word E-17 and E-26 have for their VOIDED literal.
    expect(chipFor("E-12", "VOIDED")).toEqual({
      status: "Void",
      tone: "neutral",
      icon: "Prohibit",
      caption: null,
    });
    expect(chipFor("E-12", "WITHDRAWN")?.status).toBe("Withdrawn");
  });

  it("chipFor maps the four literals of E-103, the two of ruling R-113 (e) among them", () => {
    // SCREENS_B §0.4 E-103 (rev 1.59): an API client awaits approval, is active, was refused, is revoked.
    expect(chipFor("E-103", "PENDING_APPROVAL")).toEqual({
      status: "Pending approval",
      tone: "info",
      icon: "HourglassMedium",
      caption: null,
    });
    expect(chipFor("E-103", "ACTIVE")?.status).toBe("Active");
    expect(chipFor("E-103", "REJECTED")).toEqual({
      status: "Rejected",
      tone: "negative",
      icon: "XCircle",
      caption: null,
    });
    expect(chipFor("E-103", "REVOKED")?.status).toBe("Revoked");
  });

  it("chipFor refuses an unknown enumeration or literal", () => {
    expect(() => chipFor("E-78", "DELETED")).toThrow(/No status chip for E-78 DELETED/);
    expect(() => chipFor("E-999", "ACTIVE")).toThrow(/No status chip/);
  });
});

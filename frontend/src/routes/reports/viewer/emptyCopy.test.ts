// @vitest-environment jsdom
// The SCREENS_B §5.6 "Empty copy" of the registers and analysis reports (RPT-17, RPT-19, RPT-21 to RPT-23,
// RPT-25, RPT-26, RPT-28 to RPT-30, RPT-32 to RPT-35, RPT-43, RPT-44): the title and description of an
// empty run, with the range, date or instant the run resolved. `user_access_listing` ("not reachable") and
// `ssp_version_diff` (its copy names two version labels a run does not carry) keep the generic copy.
import { describe, expect, it } from "vitest";

import type { Period } from "../../../lib/api/queries/tenant";
import { registerEmptyCopy, type ReportContext, sectionEmptyCopy } from "./specs";

function period(key: string, name: string, start: string, end: string): Period {
  return {
    id: `1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e${key.slice(-2)}`,
    entity: { id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001", code: "AVM-DE", name: "AVM-DE" },
    book: "ASC606",
    period: {
      id: `2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e${key.slice(-2)}`,
      period_key: key,
      name,
      fiscal_year: 2026,
      period_no: Number.parseInt(key.slice(-2), 10),
      quarter_no: 3,
      start_date: start,
      end_date: end,
    },
    state: "open",
    is_first_open: false,
    row_version: 1,
    state_changed_at: "2026-09-03T09:14:00Z",
    close_run: null,
    current_lock: null,
    blockers: {},
  } as unknown as Period;
}

const CONTEXT: ReportContext = {
  entity: "AVM-DE",
  book: "ASC606",
  periodKey: "FY2026-P09",
  periods: [
    period("FY2026-P08", "Aug 2026", "2026-08-01", "2026-08-31"),
    period("FY2026-P09", "Sep 2026", "2026-09-01", "2026-09-30"),
  ],
  snapshot: null,
  knownAt: null,
  currencyView: null,
};

function run(
  parameters: Record<string, unknown>,
  controlTotals: Record<string, unknown> | null = {},
): Parameters<typeof registerEmptyCopy>[1] {
  return { parameters, control_totals: controlTotals } as Parameters<typeof registerEmptyCopy>[1];
}

const DATES = { from_date: "2026-01-01", to_date: "2026-09-30" };

describe("registerEmptyCopy", () => {
  it.each([
    [
      "ssp_change_log",
      "No SSP changes from 01 Jan 2026 to 30 Sep 2026",
      "SSP book versions appear here when they are created, submitted, approved or superseded.",
    ],
    [
      "allocations_by_ssp_version",
      "No allocations from 01 Jan 2026 to 30 Sep 2026",
      "Allocations appear here with the SSP book version, range check and selected SSP used.",
    ],
    [
      "ssp_override_listing",
      "No SSP overrides from 01 Jan 2026 to 30 Sep 2026",
      "Obligations allocated with an SSP version other than the effective one appear here with their justification and approval.",
    ],
    [
      "config_change_register",
      "No configuration changes from 01 Jan 2026 to 30 Sep 2026",
      "Approved and rejected configuration versions appear here with author, approver and diff.",
    ],
    [
      "approvals_register",
      "No approval requests from 01 Jan 2026 to 30 Sep 2026",
      "Every approval request, decision and auto-approval appears here with preparer and approver.",
    ],
    [
      "judgement_register",
      "No judgement records from 01 Jan 2026 to 30 Sep 2026",
      "Documented accounting judgements with preparer and reviewer appear here.",
    ],
    [
      "estimate_change_listing",
      "No estimate changes from 01 Jan 2026 to 30 Sep 2026",
      "Each approved estimate version appears here with its predecessor and effect.",
    ],
  ])("%s states its date range", (code, title, description) => {
    expect(registerEmptyCopy(code, run(DATES), CONTEXT)).toEqual({ title, description });
    // a range the builder resolved is read from the control totals it echoes
    expect(registerEmptyCopy(code, run({}, DATES), CONTEXT)).toEqual({ title, description });
  });

  it("chain_verification_report states its instants", () => {
    expect(
      registerEmptyCopy(
        "chain_verification_report",
        run({}, { from: "2026-09-01T00:00:00.000000Z", to: "2026-09-30T23:59:59.000000Z" }),
        CONTEXT,
      ),
    ).toEqual({
      title: "No verifications from 01 Sep 2026 00:00 UTC to 30 Sep 2026 23:59 UTC",
      description:
        "The audit chain is verified daily and on demand. Each verification records the events checked and a digest.",
    });
  });

  it("sod_conflict_report states the instant it read", () => {
    expect(
      registerEmptyCopy(
        "sod_conflict_report",
        run({}, { as_of: "2026-09-12T16:02:00.000000Z" }),
        CONTEXT,
      ),
    ).toEqual({
      title: "No conflicts",
      description: "No member holds conflicting permissions at 12 Sep 2026 16:02 UTC.",
    });
  });

  it("scope_exclusion_register states its date", () => {
    expect(
      registerEmptyCopy("scope_exclusion_register", run({}, { as_of: "2026-09-30" }), CONTEXT),
    ).toEqual({
      title: "No out-of-scope lines at 30 Sep 2026",
      description:
        "Lines routed out of Topic 606 appear here with their measured amounts. They produce no revenue or journal lines.",
    });
  });

  it("the period-range reports state one period or a range", () => {
    const september = { from_period_key: "FY2026-P09", to_period_key: "FY2026-P09" };
    const twoMonths = { from_period_key: "FY2026-P08", to_period_key: "FY2026-P09" };
    expect(registerEmptyCopy("contract_cost_rollforward", run(september), CONTEXT)).toEqual({
      title: "No capitalized contract costs in Sep 2026",
      description:
        "Incremental costs of obtaining a contract and qualifying fulfilment costs appear here once capitalized.",
    });
    expect(registerEmptyCopy("intercompany_pairs", run(twoMonths), CONTEXT)).toEqual({
      title: "No intercompany pairs in Aug 2026 to Sep 2026",
      description:
        "Pairs appear when an obligation is performed by an entity other than the contracting entity.",
    });
    expect(
      registerEmptyCopy("book_bridge", run({ ...twoMonths, entity_codes: ["AVM-UK"] }), CONTEXT),
    ).toEqual({
      title: "No differences between ASC 606 and IFRS 15 in Aug 2026 to Sep 2026",
      description:
        "Differences appear when a framework switch changes revenue or balances for AVM-UK.",
    });
    // without an entity parameter the context entity is named
    expect(registerEmptyCopy("book_bridge", run(september), CONTEXT)?.description).toBe(
      "Differences appear when a framework switch changes revenue or balances for AVM-DE.",
    );
  });

  it("adoption_bridge states the date of initial application", () => {
    expect(
      registerEmptyCopy(
        "adoption_bridge",
        run({ date_of_initial_application: "2026-01-01" }),
        CONTEXT,
      ),
    ).toEqual({
      title: "No contracts at the date of initial application",
      description: "Contracts with both Legacy and ASC 606 figures at 01 Jan 2026 appear here.",
    });
  });

  it("audit_log_export states its one sentence over the generic description", () => {
    expect(registerEmptyCopy("audit_log_export", run({}), CONTEXT)).toEqual({
      title: "No audit events match these filters.",
      description: "The run keeps its parameters, totals and output hash as evidence.",
    });
  });

  it("late_entry_report states both section sentences", () => {
    expect(
      registerEmptyCopy(
        "late_entry_report",
        run({ period_key: "FY2026-P08", window_days: 5 }),
        CONTEXT,
      ),
    ).toEqual({
      title: "No events entered after the lock of Aug 2026.",
      description: "No events within 5 days of 31 Aug 2026.",
    });
  });

  it.each(["user_access_listing", "ssp_version_diff", "revenue_waterfall", "rpo", "je_population"])(
    "%s keeps the view's own or the generic copy",
    (code) => {
      expect(registerEmptyCopy(code, run(DATES), CONTEXT)).toBeNull();
    },
  );
});

describe("sectionEmptyCopy", () => {
  const stored = run({ period_key: "FY2026-P09", window_days: 1 });

  it("names the period of section 1 and the window of section 2", () => {
    expect(sectionEmptyCopy("late_entry_report", 1, stored, CONTEXT)).toBe(
      "No events entered after the lock of Sep 2026.",
    );
    expect(sectionEmptyCopy("late_entry_report", 2, stored, CONTEXT)).toBe(
      "No events within 1 day of 30 Sep 2026.",
    );
    // the window the builder applied, when the run holds no parameter
    expect(
      sectionEmptyCopy(
        "late_entry_report",
        2,
        run({ period_key: "FY2026-P08" }, { window_days: 0 }),
        CONTEXT,
      ),
    ).toBe("No events within 0 days of 31 Aug 2026.");
  });

  it("is null for another section or report", () => {
    expect(sectionEmptyCopy("late_entry_report", 3, stored, CONTEXT)).toBeNull();
    expect(sectionEmptyCopy("rpo", 2, stored, CONTEXT)).toBeNull();
  });
});

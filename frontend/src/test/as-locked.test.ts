// The fake of an as-locked report run says what the API says (item RV-AS-LOCKED-DEFAULT-1;
// docs/dev-guide.md DG-FE-18): `asLockedFindings` against every row of the table that
// `scripts/as_locked_fixture.py` wrote from `locked.reconcile_selectors` — each parameter set of each
// report that takes a lock, with the function's own findings.
import { describe, expect, it } from "vitest";

import lockDatasets from "../routes/reports/viewer/lock-datasets.json";

import {
  AS_LOCKED,
  asLockedFindings,
  asLockedRefusal,
  definitionOf,
  notALock,
  takes,
} from "./as-locked";

const LOCK_KEY = "period_lock_id";

describe("the fake of an as-locked report run", () => {
  it("gives the API's findings for every parameter set of the table", () => {
    expect(AS_LOCKED.cases.length).toBeGreaterThan(100);
    for (const row of AS_LOCKED.cases) {
      expect(
        {
          report: row.report,
          case: row.case,
          findings: asLockedFindings(row.report, row.given, AS_LOCKED.lock),
        },
        `${row.report}: ${row.case}`,
      ).toEqual({ report: row.report, case: row.case, findings: row.findings });
    }
  });

  it("the table asks every report that takes a lock, and every key of the twelve with a dataset", () => {
    const taking = AS_LOCKED.definitions.filter((definition) => takes(definition, LOCK_KEY));
    expect(taking).toHaveLength(30);
    expect(new Set(AS_LOCKED.cases.map((row) => row.report))).toEqual(
      new Set(taking.map((definition) => definition.code)),
    );
    expect(Object.keys(AS_LOCKED.kinds)).toHaveLength(12);
    for (const code of Object.keys(AS_LOCKED.kinds)) {
      const properties = Object.keys(definitionOf(code).parameters_schema.properties as object);
      const asked = new Set(
        AS_LOCKED.cases
          .filter((row) => row.report === code)
          .flatMap((row) => Object.keys(row.given)),
      );
      expect([...asked].sort(), code).toEqual([...properties].sort());
    }
  });

  it("the screens' table of lock datasets is the fixture's", () => {
    // Two files of one script: what the product reads and what the tests are held to.
    expect(lockDatasets).toEqual(AS_LOCKED.kinds);
  });

  it("refuses with a 422 as the API words it, and lets an admitted creation through", async () => {
    const lock = AS_LOCKED.lock;
    const own = { [LOCK_KEY]: lock.id, entity_codes: [lock.entity_code], book: lock.book_code };
    expect(asLockedRefusal("rpo", { entity_codes: ["AVM-US"] }, [lock])).toBeNull();
    expect(asLockedRefusal("rpo", { ...own, period_key: lock.period_key }, [lock])).toBeNull();

    const one = asLockedRefusal("rpo", { ...own, row_dimension: "ENTITY" }, [lock]);
    expect(one?.status).toBe(422);
    expect(await one?.json()).toMatchObject({
      title: "Check the highlighted fields",
      detail: "1 field needs attention.",
      errors: [
        {
          field: "parameters.row_dimension",
          rule_id: "S15-R-19",
          message: `row_dimension cannot be applied to an as-locked run: the frozen RPO dataset of lock ${lock.id} carries no such selector. Run the report current to apply it.`,
        },
      ],
    });
    const two = asLockedRefusal("rpo", { ...own, period_key: "FY2026-P09", time_bands: [12] }, [
      lock,
    ]);
    expect(await two?.json()).toMatchObject({ detail: "2 fields need attention." });

    // A report without a lock dataset, and a lock that is none of the workspace's.
    const none = asLockedRefusal("extract_contracts", { [LOCK_KEY]: lock.id }, [lock]);
    expect(await none?.json()).toMatchObject({
      errors: [
        {
          field: "parameters.period_lock_id",
          rule_id: "S15-R-19",
          message:
            "extract_contracts has no lock dataset (E-64): an as-locked run of this report is not supported; run it current (known_at) instead.",
        },
      ],
    });
    const unknown = asLockedRefusal("rpo", { [LOCK_KEY]: "another" }, [lock]);
    expect(await unknown?.json()).toMatchObject({
      errors: [
        {
          field: "parameters.period_lock_id",
          rule_id: "REQ-PLT-012",
          message: "Choose a period lock of this workspace.",
        },
      ],
    });
  });

  // S15-R-19 rev 1.167 (register index 280): a run names a LOCK record or is refused.
  it("says of a record that is no LOCK what the API says, for every row of the records table", () => {
    expect(AS_LOCKED.records.map((row) => row.kind)).toEqual([
      "LOCK",
      "LOCK",
      "REOPEN",
      "REOPEN",
      "PERMANENT_LOCK",
      "PERMANENT_LOCK",
    ]);
    for (const row of AS_LOCKED.records) {
      const record = {
        ...AS_LOCKED.lock,
        id: row.id,
        period_key: row.period_key,
        kind: row.kind,
        dataset_lock_id: row.dataset_lock_id,
      };
      expect(
        notALock(record),
        `${row.kind}, ${row.dataset_lock_id === null ? "no lock stands" : "a lock stands"}`,
      ).toBe(row.refusal);
    }
    // A record that says no kind is the record of a close.
    expect(notALock(AS_LOCKED.lock)).toBeNull();
  });

  it("refuses a run that names the permanent lock's record before it reads a selector, and names the lock to pass", async () => {
    const lock = AS_LOCKED.lock;
    const permanent = {
      ...lock,
      id: "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4bff08",
      kind: "PERMANENT_LOCK",
      dataset_lock_id: lock.id,
    };
    // Its own selectors and one the lock would not admit: one finding, the record's, as
    // `framework._resolve` stops there.
    const refused = asLockedRefusal(
      "rpo",
      { [LOCK_KEY]: permanent.id, period_key: lock.period_key, row_dimension: "ENTITY" },
      [lock, permanent],
    );
    expect(refused?.status).toBe(422);
    expect(await refused?.json()).toMatchObject({
      detail: "1 field needs attention.",
      errors: [
        {
          field: "parameters.period_lock_id",
          rule_id: "S15-R-19",
          message:
            `Lock ${permanent.id} is the permanent lock of FY2026-P08: it froze no dataset ` +
            `(E-63 PERMANENT_LOCK). The datasets of FY2026-P08 are those of lock ${lock.id}; ` +
            "pass that lock.",
        },
      ],
    });
    // A report without a lock dataset says so first, whatever the record is.
    const none = asLockedRefusal("extract_contracts", { [LOCK_KEY]: permanent.id }, [permanent]);
    expect(await none?.json()).toMatchObject({
      errors: [{ message: expect.stringContaining("has no lock dataset (E-64)") as string }],
    });
    // Where no lock's datasets stand: what the caller can do instead, the route's braces as written.
    const reopen = { ...permanent, kind: "REOPEN", dataset_lock_id: null };
    expect(notALock(reopen)).toBe(
      `Lock ${permanent.id} is a reopen record of FY2026-P08: it froze no dataset (E-63 REOPEN). ` +
        "No lock's datasets stand for FY2026-P08: run the report current (known_at) instead, or " +
        "pass a LOCK record of the period (GET /periods/{id}/locks).",
    );
  });
});

// The fixtures of project `qa-rc` (release candidate QA; PROGRESS.md D-99 (7)): the record every
// check writes its row to, and the sessions of the members. The project's tests do not assert the
// product: a check that finds something writes it down and the pass goes on, so that one finding
// does not hide the next. What the committed fixtures assert — no request to another host, no CSP
// violation — still fails a test.
import { test as base } from "../fixtures";
import { QaRecord } from "./record";
import { Sessions } from "./sessions";

export interface Qa {
  readonly record: QaRecord;
  readonly sessions: Sessions;
}

interface QaFixtures {
  qa: Qa;
}

export const test = base.extend<QaFixtures>({
  qa: async ({ browser, personas }, provide, testInfo) => {
    const record = new QaRecord();
    const sessions = new Sessions(browser, personas, record, testInfo);
    await provide({ record, sessions });
    await sessions.close();
  },
});

export { expect } from "../fixtures";

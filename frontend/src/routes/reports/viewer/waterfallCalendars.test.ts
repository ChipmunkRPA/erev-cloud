// @vitest-environment jsdom
import { expect, it } from "vitest";
import { bucketLabel } from "./specs";

it("labels cross-calendar waterfall columns by their exact date interval", () => {
  expect(bucketLabel("date_2026-09-01_2026-09-30", [])).toBe("2026-09-01 – 2026-09-30");
  expect(bucketLabel("date_2026-08-31_2026-09-27", [])).toBe("2026-08-31 – 2026-09-27");
  expect(bucketLabel("FY2026", [])).toBe("FY2026");
});

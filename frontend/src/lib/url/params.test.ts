// SCR-URL-20 (SCREENS §0.5): canonical parameter order and removal of parameters a screen does not use.
import { describe, expect, it } from "vitest";

import { canonicalise } from "./params";

describe("SCR-URL-20", () => {
  it("orders parameters canonically", () => {
    expect(canonicalise("?q=x&entity=AVM-US&view=v1&period=FY2026-P09")).toBe(
      "?entity=AVM-US&period=FY2026-P09&view=v1&q=x",
    );
  });

  it("removes parameters the screen does not declare", () => {
    expect(
      canonicalise("?pane=ssp&q=x&utm_source=mail&entity=AVM-US&tour=demo", {
        declared: ["entity", "q", "pane"],
      }),
    ).toBe("?entity=AVM-US&q=x&pane=ssp");
    expect(canonicalise("?utm_source=mail&x.y=1")).toBe("");
  });

  it("orders filters by column and keeps encoded commas inside values", () => {
    expect(
      canonicalise("?f.customer=is:Acme%2C%20Inc.&sort=-contract_no&f.status=in:ACTIVE,DRAFT", {
        filterColumns: ["status", "customer"],
      }),
    ).toBe("?sort=-contract_no&f.status=in:ACTIVE,DRAFT&f.customer=is:Acme%2C%20Inc.");
  });

  it("places report, run and dialog families in their slots", () => {
    expect(canonicalise("?dialog=about&run.revenue=r2&p.as_of=2026-09-30&run=r1&book=ASC606")).toBe(
      "?book=ASC606&run=r1&p.as_of=2026-09-30&run.revenue=r2&dialog=about",
    );
  });

  it("fills missing parameters from defaults", () => {
    expect(
      canonicalise("?q=x&period=FY2026-P09", {
        defaults: { entity: "AVM-US", period: "FY2026-P01", book: "ASC606" },
      }),
    ).toBe("?entity=AVM-US&period=FY2026-P09&book=ASC606&q=x");
  });
});

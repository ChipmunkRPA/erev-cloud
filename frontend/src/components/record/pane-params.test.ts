// @vitest-environment jsdom
// SCREENS SCR-URL-13 (crawl finding F4): the search a panel tab writes when its panes hold their own lists.
import { describe, expect, it } from "vitest";

import { SORT_PARAM } from "../data-grid/DataGrid";
import { VIEW_PARAM } from "../data-grid/SavedViewSelector";
import { FILTER_PREFIX, QUERY_PARAM } from "../filter-bar/filters";
import { LIST_PARAM_PREFIX, LIST_PARAMS, withPane } from "./pane-params";

function after(search: string, pane: string | null): string {
  return withPane(new URLSearchParams(search), pane).toString();
}

describe("withPane", () => {
  it("sets pane, or removes it for the default tab, and keeps what is not a list parameter", () => {
    expect(after("entity=AVM-US&period=FY2026-P09&book=ASC606", "tests")).toBe(
      "entity=AVM-US&period=FY2026-P09&book=ASC606&pane=tests",
    );
    expect(after("entity=AVM-US&pane=tests&drawer=rule&row=7", null)).toBe(
      "entity=AVM-US&drawer=rule&row=7",
    );
  });

  it("takes sort, q, view and every f.* of the pane it leaves out of the URL", () => {
    expect(
      after(
        "entity=AVM-US&sort=-priority&q=audit&view=ON_HOLD&f.status=is:APPROVED&f.kind=in:HOLD",
        "tests",
      ),
    ).toBe("entity=AVM-US&pane=tests");
    expect(after("pane=exceptions&f.status=is:APPROVED&sort=code", null)).toBe("");
  });

  it("names the list parameters as the grid, the filter bar and the saved-view selector do", () => {
    expect([...LIST_PARAMS].sort()).toEqual([SORT_PARAM, QUERY_PARAM, VIEW_PARAM].sort());
    expect(LIST_PARAM_PREFIX).toBe(FILTER_PREFIX);
  });

  it("leaves its argument as it was", () => {
    const current = new URLSearchParams("sort=code&pane=rules");
    withPane(current, "exceptions");
    expect(current.toString()).toBe("sort=code&pane=rules");
  });
});

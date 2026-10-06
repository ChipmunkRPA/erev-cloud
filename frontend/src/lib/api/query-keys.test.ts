// DG-FE-04 (docs/dev-guide.md §8.2): query keys have the shape `[resource, scope, params]`.
import { describe, expect, it } from "vitest";

import { queryKey, queryKeys } from "./query-keys";

describe("query keys", () => {
  it("have the shape [resource, scope, params]", () => {
    expect(queryKey("contracts", "tenant", { entity: "AVM-US", period: "FY2026-P09" })).toEqual([
      "contracts",
      "tenant",
      { entity: "AVM-US", period: "FY2026-P09" },
    ]);
    expect(queryKey("roles", "tenant")).toEqual(["roles", "tenant", {}]);
    for (const key of [queryKeys.session(), queryKeys.me(), queryKeys.job("8d4f2e1c")]) {
      expect(key).toHaveLength(3);
      const [resource, scope, params] = key;
      expect(typeof resource).toBe("string");
      expect(["public", "session", "tenant"]).toContain(scope);
      expect(typeof params).toBe("object");
    }
    expect(queryKeys.job("8d4f2e1c")).toEqual(["jobs", "tenant", { id: "8d4f2e1c" }]);
  });
});

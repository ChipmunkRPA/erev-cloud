import { describe, expect, it } from "vitest";

import { resolveProxyTarget } from "./proxy";

const MESSAGE = "EREV_API_PROXY_TARGET must be set, for example http://127.0.0.1:8190";

describe("resolveProxyTarget", () => {
  it("throws when the target is unset", () => {
    expect(() => resolveProxyTarget(undefined)).toThrow(MESSAGE);
  });

  it("throws for a localhost target", () => {
    expect(() => resolveProxyTarget("http://localhost:8190")).toThrow(MESSAGE);
  });

  it("returns a 127.0.0.1 target unchanged", () => {
    expect(resolveProxyTarget("http://127.0.0.1:8190")).toBe("http://127.0.0.1:8190");
  });
});

// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAISettings, fetchAISettingsVersions } from "./ai-settings";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
afterEach(() => vi.unstubAllGlobals());

describe("administrator AI settings reads", () => {
  it("preserves effective disablement alongside an enabled published policy", async () => {
    const body = {
      provider: "fake",
      enabled: false,
      registry_enabled: true,
      tenant_disabled_at: "2026-10-15T12:00:00Z",
      platform_disabled: false,
      workspace_active: true,
      model: "reviewed-model",
      monthly_token_budget: 42,
      send_contract_text: false,
      redact_contact_details: true,
    };
    const fetch = vi.fn().mockResolvedValue(json(body));
    vi.stubGlobal("fetch", fetch);
    expect(await fetchAISettings()).toEqual(body);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("returns authorization refusals instead of displaying invented defaults", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json(
          {
            type: "https://erev.test/problems/forbidden",
            title: "Forbidden",
            status: 403,
            detail: "Access refused",
            errors: [],
          },
          403,
        ),
      ),
    );
    await expect(fetchAISettings()).rejects.toMatchObject({ status: 403 });
  });

  it("retains the server cursor for saved AI versions", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ items: [], next_cursor: "retained-cursor" }));
    vi.stubGlobal("fetch", fetch);
    const page = await fetchAISettingsVersions({ status: "SUBMITTED" });
    expect(page.nextCursor).toBe("retained-cursor");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

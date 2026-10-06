// @vitest-environment jsdom
// SCREENS §0.6 SCR-PERM-01, -02 (rev 1.30); dev-guide DG-FE-16 (rev 1.175); 04 §16.12 API-S-Me
// `permission_scopes`, T-PLT-10: a gate asks for which legal entities the member holds a permission,
// not whether the code is among `permissions`. Before, every gate asked the second question, and a
// member of named entities was offered commands the API refuses.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { createQueryClient } from "../app/providers";
import { signedInMe } from "../test/app";
import { apiUrl, installMswServer, server } from "../test/msw";
import { accessOf, useAccess } from "./access";

installMswServer();

afterEach(() => {
  cleanup();
});

const US = { id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001", code: "AVM-US", name: "Avenmoor US Inc." };
const DE = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000003",
  code: "AVM-DE",
  name: "Avenmoor Devices GmbH",
};

/** Lena of PRD J-22.1: a reader everywhere, a reviewer for AVM-DE only. */
const LENA = signedInMe({
  permissions: ["contract.read", "contract.review"],
  permission_scopes: { "contract.read": "*", "contract.review": [DE.id] },
});

describe("accessOf", () => {
  it("a member of all entities holds a permission for every entity, without the entities read", () => {
    const access = accessOf(signedInMe({ permissions: ["contract.create"] }));
    expect(access.holds("contract.create", { id: US.id })).toBe(true);
    expect(access.holds("contract.create", { code: "AVM-DE" })).toBe(true);
    expect(access.holdsAnywhere("contract.create")).toBe(true);
    expect(access.holdsForAll("contract.create")).toBe(true);
    expect(access.holdsForEvery("contract.create", [{ id: US.id }, { code: "AVM-DE" }])).toBe(true);
    expect(access.holdsForEvery("contract.create", "*")).toBe(true);
    expect(access.scope("contract.create")).toBe("*");
  });

  it("a member of named entities holds it for those entities alone", () => {
    const access = accessOf(LENA, [US, DE]);
    // A record of one legal entity: held for that entity.
    expect(access.holds("contract.review", { id: DE.id })).toBe(true);
    expect(access.holds("contract.review", { id: US.id })).toBe(false);
    // A record that states its entity by code is resolved through the entities of the workspace.
    expect(access.holds("contract.review", { code: "AVM-DE" })).toBe(true);
    expect(access.holds("contract.review", { code: "AVM-US" })).toBe(false);
    // A tenant-wide object: held for any entity (dev-guide DG-KRN-AUTH-04).
    expect(access.holdsAnywhere("contract.review")).toBe(true);
    expect(access.holds("contract.review", null)).toBe(true);
    // A tenant-wide act or list: held for all entities.
    expect(access.holdsForAll("contract.review")).toBe(false);
    // A membership or an assignment: held for every entity its grants name; all when one is for all.
    expect(access.holdsForEvery("contract.review", [{ id: DE.id }])).toBe(true);
    expect(access.holdsForEvery("contract.review", [{ id: DE.id }, { id: US.id }])).toBe(false);
    expect(access.holdsForEvery("contract.review", "*")).toBe(false);
    expect(access.holdsForEvery("contract.review", [])).toBe(true);
    expect(access.scope("contract.review")).toEqual([DE.id]);
    // The permission held everywhere is not narrowed by the other.
    expect(access.holds("contract.read", { id: US.id })).toBe(true);
    expect(access.holdsForAll("contract.read")).toBe(true);
  });

  it("without the entities read a code names no entity for a member of named entities", () => {
    const access = accessOf(LENA);
    expect(access.holds("contract.review", { code: "AVM-DE" })).toBe(false);
    // An id needs no read.
    expect(access.holds("contract.review", { id: DE.id })).toBe(true);
    // A record that states both is decided by its id.
    expect(access.holds("contract.review", { id: DE.id, code: "AVM-DE" })).toBe(true);
  });

  it("a permission that is not held is held nowhere, and neither is anything before /me has answered", () => {
    for (const access of [accessOf(LENA, [US, DE]), accessOf(undefined)]) {
      expect(access.holds("period.lock", { id: DE.id })).toBe(false);
      expect(access.holds("period.lock", null)).toBe(false);
      expect(access.holdsAnywhere("period.lock")).toBe(false);
      expect(access.holdsForAll("period.lock")).toBe(false);
      expect(access.holdsForEvery("period.lock", [])).toBe(false);
      expect(access.scope("period.lock")).toBeNull();
    }
  });

  it("a code among `permissions` without its scope is not held: the scopes are what the API enforces", () => {
    const access = accessOf({ permissions: ["contract.create"], permission_scopes: {} });
    expect(access.holdsAnywhere("contract.create")).toBe(false);
  });
});

describe("useAccess", () => {
  function wrapperFor(me: ReturnType<typeof signedInMe>, reads: string[]) {
    server.use(
      http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(me)),
      http.get(apiUrl("/api/v1/entities"), ({ request }) => {
        reads.push(new URL(request.url).search);
        return HttpResponse.json({ items: [US, DE], next_cursor: null });
      }),
    );
    const client = createQueryClient();
    return ({ children }: { readonly children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  }

  it("a member of all entities asks for no entity list", async () => {
    const reads: string[] = [];
    const { result } = renderHook(() => useAccess(), {
      wrapper: wrapperFor(signedInMe({ permissions: ["contract.create"] }), reads),
    });
    await waitFor(() => {
      expect(result.current.holds("contract.create", { code: "AVM-US" })).toBe(true);
    });
    expect(reads).toEqual([]);
  });

  it("a member of named entities resolves a code once the entities are read, and offers nothing by code before", async () => {
    const reads: string[] = [];
    const { result } = renderHook(() => useAccess(), { wrapper: wrapperFor(LENA, reads) });
    // By id as soon as /me has answered.
    await waitFor(() => {
      expect(result.current.holds("contract.review", { id: DE.id })).toBe(true);
    });
    await waitFor(() => {
      expect(result.current.holds("contract.review", { code: "AVM-DE" })).toBe(true);
    });
    expect(result.current.holds("contract.review", { code: "AVM-US" })).toBe(false);
    expect(reads).toHaveLength(1);
  });
});

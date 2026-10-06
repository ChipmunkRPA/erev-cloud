// @vitest-environment jsdom
// SF-13:ssp-books "New SSP book" and "New draft version" (SCREENS §11.4; §0.7 SCR-ST-13; 04 API-R-26
// `POST /ssp-books`, `POST /ssp-books/{id}/versions`; docs/dev-guide.md DG-FE-06 rev 1.228; item
// KIT-UNPLACED-ERRORS-1). A refusal that names a member the form has no field for was shown nowhere:
// each form showed its banner only while the problem carried no field errors at all.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SspBook } from "../../lib/api/queries/ssp-books";
import { installMemoryStorage, renderWithApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { NewDraftModal, NewSspBookDrawer } from "./ssp-books";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const BOOK_ID = "5d6e7f80-9a1b-4c2d-8e3f-4a5b6c7d8e9f";
const AUTHOR = signedInMe({ permissions: ["ssp.read", "ssp.create"] });

const BOOK: SspBook = {
  id: BOOK_ID,
  code: "US-LIST",
  name: "US list prices",
  description: null,
  entity_code: null,
  currency: "USD",
  channel: null,
  segment: null,
  resolution_mode: "EFFECTIVE_DATE",
  current_version: null,
  draft_version_id: null,
  row_version: 1,
  created_at: "2026-01-01T09:00:00Z",
  updated_at: "2026-09-01T09:00:00Z",
};

function error(field: string, message: string) {
  return { field, sheet: null, row: null, rule_id: null, message };
}

function serveReads() {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/tenant-currencies"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

describe("SF-13:ssp-books, a refusal that names a member the form has no field for", () => {
  it("a refusal of New SSP book says in the banner what no field of the drawer shows", async () => {
    serveReads();
    server.use(
      http.post(apiUrl("/api/v1/ssp-books"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            error("code", "Use letters, digits and hyphens."),
            error("price_list_id", "A book of this workspace names its price list."),
          ],
        }),
      ),
    );
    renderWithApp(<NewSspBookDrawer onClose={vi.fn()} />, {
      entry: "/policies/ssp-books",
      me: AUTHOR,
    });

    const dialog = await screen.findByRole("dialog", { name: "New SSP book" });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "US LIST" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "US list prices" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create SSP book" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("A book of this workspace names its price list.")).toBeTruthy();
    expect(within(banner).queryByText("Use letters, digits and hyphens.")).toBeNull();
    expect(within(dialog).getAllByText("Use letters, digits and hyphens.")).toHaveLength(1);
    expect(within(dialog).getByLabelText(/^Code/).getAttribute("aria-invalid")).toBe("true");
  });

  it("a refusal of New draft version says in the banner what no field of the form shows", async () => {
    serveReads();
    server.use(
      http.post(apiUrl(`/api/v1/ssp-books/${BOOK_ID}/versions`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            error("methodology_label", "Use at most 120 characters."),
            error("copy_from_version_id", "The version to copy belongs to another book."),
          ],
        }),
      ),
    );
    renderWithApp(<NewDraftModal book={BOOK} source={null} onClose={vi.fn()} />, {
      entry: `/policies/ssp-books/${BOOK_ID}`,
      me: AUTHOR,
    });

    const dialog = await screen.findByRole("dialog", { name: "New draft version" });
    fireEvent.change(within(dialog).getByLabelText(/^Methodology label/), {
      target: { value: "Observed standalone sales" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create draft version" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("The version to copy belongs to another book.")).toBeTruthy();
    expect(within(banner).queryByText("Use at most 120 characters.")).toBeNull();
    expect(within(dialog).getAllByText("Use at most 120 characters.")).toHaveLength(1);
  });
});

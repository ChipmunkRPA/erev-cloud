// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ForecastInputReview } from "./ForecastInputReview";
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => true }) }));
afterEach(cleanup);
const command = {
  method: "POST",
  path: "/contracts/12345678-1234-1234-1234-123456789abc/events",
  body: {
    events: [
      {
        event_type: "PROGRESS_RECORDED",
        effective_date: "2026-10-19",
        payload: {
          cumulative_progress_ratio: "0.400000000000000001",
          amount: "123456789012345.67",
          note: "<script>alert(1)</script>",
        },
      },
    ],
  },
};
it("shows captured values in interleaved application order without rounding or interpreting markup", () => {
  render(
    <MemoryRouter>
      <ForecastInputReview
        row={{
          api_commands: [command],
          import_upload_ids: ["upload"],
          input_sequence: [
            { kind: "IMPORT_UPLOAD", id: "upload" },
            { kind: "API_COMMAND", index: 0 },
          ],
        }}
      />
    </MemoryRouter>,
  );
  expect(screen.queryByText("0.400000000000000001")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Review captured assumptions" }));
  expect(screen.getByText("0.400000000000000001")).toBeTruthy();
  expect(screen.getByText("123456789012345.67")).toBeTruthy();
  expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
  expect(document.querySelector("script")).toBeNull();
  const links = screen.getAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/data/imports/upload",
    "/contracts/12345678-1234-1234-1234-123456789abc",
  ]);
});
it("does not invent an order for populated legacy sets", () => {
  render(
    <MemoryRouter>
      <ForecastInputReview
        row={{ api_commands: [command], import_upload_ids: [], input_sequence: null }}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Review captured assumptions" }));
  expect(screen.getByText(/Recorded input order is missing/)).toBeTruthy();
  expect(screen.queryByRole("link")).toBeNull();
});
it("distinguishes an empty baseline from missing evidence", () => {
  render(
    <MemoryRouter>
      <ForecastInputReview
        row={{ api_commands: [], import_upload_ids: [], input_sequence: null }}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Review captured assumptions" }));
  expect(screen.getByText(/This version uses the scenario baseline/)).toBeTruthy();
});

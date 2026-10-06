// @vitest-environment jsdom
// DS-CMP-06 record header (DESIGN_SYSTEM §7.2; SCREENS §4.1.9): the section is named by its h1, the
// breadcrumb ends at the identifier, and copying the identifier confirms with a toast.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../feedback/Toast";
import { RecordHeader } from "./RecordHeader";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DS-CMP-06 record header", () => {
  it("names the section by its h1, links the breadcrumb and copies the identifier", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(
      <MemoryRouter>
        <ToastProvider>
          <RecordHeader
            title="Northwind platform agreement"
            breadcrumb={[{ label: "Contracts", to: "/contracts" }]}
            identifier={{
              value: "NS-SO-DE-5004",
              copyLabel: "Copy contract id",
              copiedMessage: "Copied NS-SO-DE-5004.",
            }}
            meta={[
              { label: "Customer", value: "Northwind Traders" },
              { label: "Currency", value: "USD" },
            ]}
          />
        </ToastProvider>
      </MemoryRouter>,
    );
    const section = screen.getByRole("region", { name: "Northwind platform agreement" });
    expect(section.tagName).toBe("SECTION");
    expect(within(section).getByRole("heading", { level: 1 }).textContent).toBe(
      "Northwind platform agreement",
    );

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Contracts" }).getAttribute("href")).toBe(
      "/contracts",
    );
    expect(within(breadcrumb).getByText("NS-SO-DE-5004").getAttribute("aria-current")).toBe("page");

    expect(Array.from(section.querySelectorAll("dt"), (term) => term.textContent)).toEqual([
      "Customer",
      "Currency",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Copy contract id" }));
    expect(writeText).toHaveBeenCalledWith("NS-SO-DE-5004");
    expect(await screen.findByText("Copied NS-SO-DE-5004.")).toBeTruthy();
  });

  it("the compact variant has no breadcrumb and an h2 title", () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <RecordHeader
            variant="compact"
            title="Platform subscription"
            breadcrumb={[{ label: "Contracts", to: "/contracts" }]}
          />
        </ToastProvider>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "Platform subscription" })).toBeTruthy();
  });
});

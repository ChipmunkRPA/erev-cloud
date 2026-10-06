// @vitest-environment jsdom
// DS-CMP-29 (DESIGN_SYSTEM §7.5): live roles of inserted banners and the static banner of a page load.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Banner, type BannerTone } from "./Banner";

afterEach(() => {
  cleanup();
});

describe("DS-CMP-29", () => {
  it("a banner inserted after load has role status for info, positive and warning and alert for negative", () => {
    const expected: Readonly<Record<BannerTone, string>> = {
      info: "status",
      positive: "status",
      warning: "status",
      negative: "alert",
    };
    for (const [tone, role] of Object.entries(expected) as [BannerTone, string][]) {
      const { unmount } = render(<Banner tone={tone} title={`Tone ${tone}`} />);
      const banner = screen.getByRole(role);
      expect(banner.getAttribute("data-tone")).toBe(tone);
      expect(banner.textContent).toContain(`Tone ${tone}`);
      unmount();
    }
  });

  it("a banner present on load is a static element with a heading", () => {
    render(
      <Banner tone="info" announce="static" title="Sep 2026 is locked for US01.">
        Late events post to Oct 2026 with origin period Sep 2026.
      </Banner>,
    );
    expect(screen.queryByRole("status")).toBeNull();
    expect(
      screen.getByRole("heading", { level: 2, name: "Sep 2026 is locked for US01." }),
    ).toBeTruthy();
  });

  it("only info banners can be dismissed", () => {
    const onDismiss = vi.fn();
    const { rerender } = render(
      <Banner tone="info" title="Scheduled maintenance tonight." onDismiss={onDismiss} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    rerender(
      <Banner
        tone="negative"
        title="API unreachable. Changes are not being saved."
        onDismiss={onDismiss}
      />,
    );
    expect(screen.queryByRole("button", { name: "Dismiss" })).toBeNull();
  });
});

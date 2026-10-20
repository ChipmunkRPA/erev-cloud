// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import { fetchDealProducts } from "./deal-previews";
const page = vi.hoisted(() => vi.fn());
vi.mock("../lists", () => ({ fetchListPage: page }));
it("loads later pages and excludes inactive products from the selector", async () => {
  page
    .mockResolvedValueOnce({
      items: [{ id: "1", code: "A", name: "First", is_active: true }],
      nextCursor: "page2",
    })
    .mockResolvedValueOnce({
      items: [
        { id: "2", code: "B", name: "Second", is_active: true },
        { id: "3", code: "OLD", name: "Retired", is_active: false },
      ],
      nextCursor: null,
    });
  expect(await fetchDealProducts()).toEqual([
    { id: "1", code: "A", name: "First" },
    { id: "2", code: "B", name: "Second" },
  ]);
  expect(page).toHaveBeenNthCalledWith(
    2,
    "/api/v1/products",
    { is_active: true, sort: "code" },
    "page2",
    { limit: 200, count: false },
  );
});

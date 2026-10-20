import { expect, it } from "vitest";
import { barPercent, revenueGroups, sumAmounts } from "./deal-revenue";

it("sums large, signed amounts and mixed decimal scales without floating point loss", () => {
  expect(sumAmounts(["9007199254740993.01", "0.09", "-1.1"])).toBe("9007199254740992.00");
  expect(sumAmounts(["-0.001", "0.0009"])).toBe("-0.0001");
  expect(sumAmounts(["-0.00", "0"])).toBe("0.00");
  expect(barPercent("-0.001", ["0.002", "-0.001"])).toBe(50);
  expect(barPercent("0", ["0"])).toBe(0);
});
it("separates entities and currencies while combining obligations of the same product", () => {
  const row = (
    entity: string,
    currency: string,
    product: string | null,
    subject: string,
    period: string,
    amount: string,
  ) => ({
    entity_code: entity,
    period_key: period,
    product_code: product,
    subject_key: subject,
    amount: { amount, currency },
  });
  const groups = revenueGroups([
    row("US", "USD", "A", "L1", "FY2026-P02", "2.00"),
    row("US", "USD", "A", "L2", "FY2026-P02", "-0.01"),
    row("US", "USD", "B", "L3", "FY2026-P01", "1.02"),
    row("US", "EUR", "A", "L4", "FY2026-P01", "50.00"),
    row("DE", "USD", "A", "L5", "FY2026-P01", "70.00"),
    row("US", "USD", null, "contract", "FY2026-P02", "0.01"),
  ]);
  expect(groups).toHaveLength(3);
  const usd = groups.find((group) => group.entity === "US" && group.currency === "USD");
  expect(usd?.total).toBe("3.02");
  expect(usd?.periods.map((period) => [period.key, period.total])).toEqual([
    ["FY2026-P01", "1.02"],
    ["FY2026-P02", "2.00"],
  ]);
  expect(usd?.products.map((product) => product.label)).toEqual(["A", "B", "contract"]);
});

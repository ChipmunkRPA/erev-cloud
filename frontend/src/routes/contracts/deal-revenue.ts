import type { components } from "../../lib/api/schema";

type Revenue = components["schemas"]["DealRevenueOut"];

/** Money stays decimal strings; only bounded chart geometry is converted to a number. */
export function sumAmounts(amounts: readonly string[]): string {
  const scale = amounts.reduce((max, value) => Math.max(max, value.split(".")[1]?.length ?? 0), 0);
  const total = amounts.reduce((sum, value) => {
    if (!/^-?\d+(\.\d+)?$/.test(value)) throw new Error("Invalid revenue amount");
    const negative = value.startsWith("-");
    const [whole = "0", fraction = ""] = value.replace(/^-/, "").split(".");
    const units = BigInt(whole + fraction.padEnd(scale, "0"));
    return sum + (negative ? -units : units);
  }, 0n);
  const digits = (total < 0n ? -total : total).toString().padStart(scale + 1, "0");
  return `${total < 0n ? "-" : ""}${scale === 0 ? digits : `${digits.slice(0, -scale)}.${digits.slice(-scale)}`}`;
}

export interface RevenueGroup {
  key: string;
  entity: string;
  currency: string;
  products: { key: string; label: string }[];
  periods: { key: string; amounts: Record<string, string>; total: string }[];
  totals: Record<string, string>;
  total: string;
}

export function revenueGroups(rows: readonly Revenue[]): RevenueGroup[] {
  const groups = new Map<string, Revenue[]>();
  for (const row of rows) {
    const key = JSON.stringify([row.entity_code, row.amount.currency]);
    const lines = groups.get(key);
    if (lines) lines.push(row);
    else groups.set(key, [row]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, lines]) => {
      const first = lines[0];
      if (!first) throw new Error("Empty revenue group");
      const productKey = (row: Revenue) =>
        JSON.stringify([row.product_code, row.product_code === null ? row.subject_key : null]);
      const products = [
        ...new Map(
          lines.map((row) => [
            productKey(row),
            { key: productKey(row), label: row.product_code ?? row.subject_key },
          ]),
        ).values(),
      ].sort((a, b) => a.label.localeCompare(b.label));
      const byPeriod = new Map<string, Map<string, string[]>>();
      const byProduct = new Map<string, string[]>();
      for (const row of lines) {
        const product = productKey(row);
        let period = byPeriod.get(row.period_key);
        if (!period) {
          period = new Map();
          byPeriod.set(row.period_key, period);
        }
        const amounts = period.get(product);
        if (amounts) amounts.push(row.amount.amount);
        else period.set(product, [row.amount.amount]);
        const total = byProduct.get(product);
        if (total) total.push(row.amount.amount);
        else byProduct.set(product, [row.amount.amount]);
      }
      const periods = [...byPeriod.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([period, cells]) => {
          const amounts = Object.fromEntries(
            products.map((product) => [product.key, sumAmounts(cells.get(product.key) ?? [])]),
          );
          return { key: period, amounts, total: sumAmounts(Object.values(amounts)) };
        });
      return {
        key,
        entity: first.entity_code,
        currency: first.amount.currency,
        products,
        periods,
        totals: Object.fromEntries(
          products.map((product) => [product.key, sumAmounts(byProduct.get(product.key) ?? [])]),
        ),
        total: sumAmounts(periods.map((period) => period.total)),
      };
    });
}

/** Percentage of the largest magnitude, truncated at two decimal places. */
export function barPercent(amount: string, values: readonly string[]): number {
  const scale = Math.max(
    0,
    ...[amount, ...values].map((value) => value.split(".")[1]?.length ?? 0),
  );
  const magnitude = (value: string) => {
    const [whole = "0", fraction = ""] = value.replace(/^-/, "").split(".");
    return BigInt(whole + fraction.padEnd(scale, "0"));
  };
  const max = values.reduce(
    (largest, value) => (magnitude(value) > largest ? magnitude(value) : largest),
    0n,
  );
  return max === 0n ? 0 : Number((magnitude(amount) * 10000n) / max) / 100;
}

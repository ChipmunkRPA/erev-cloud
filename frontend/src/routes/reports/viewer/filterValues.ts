/** URL state preserves incomplete/duplicate rows until the user repairs them. */
export type FilterRow = readonly [string, string];
export function filterRows(raw: string): readonly FilterRow[] | null {
  if (raw === "") return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (Array.isArray(value)) {
      return value.every(
        (row) =>
          Array.isArray(row) && row.length === 2 && row.every((cell) => typeof cell === "string"),
      )
        ? (value as FilterRow[])
        : null;
    }
    if (
      typeof value === "object" &&
      value !== null &&
      Object.values(value).every((cell) => typeof cell === "string")
    ) {
      return Object.entries(value) as FilterRow[];
    }
  } catch {
    /* Invalid address state must be repaired, not silently discarded. */
  }
  return null;
}
export function validFilterRows(rows: readonly FilterRow[] | null): rows is readonly FilterRow[] {
  return (
    rows !== null &&
    rows.every(([key, value]) => key.trim() !== "" && value !== "") &&
    new Set(rows.map(([key]) => key.trim())).size === rows.length
  );
}
export function filterValue(raw: string): unknown {
  const rows = filterRows(raw);
  return validFilterRows(rows)
    ? Object.fromEntries(rows.map(([key, value]) => [key.trim(), value]))
    : (rows ?? raw);
}

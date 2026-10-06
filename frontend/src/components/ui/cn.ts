/** Joins class names and skips false, null and undefined entries (design-check reads the literals). */
export function cn(...classes: ReadonlyArray<string | false | null | undefined>): string {
  return classes
    .filter((value): value is string => typeof value === "string" && value !== "")
    .join(" ");
}

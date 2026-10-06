// design-check fixture DS-LINT-23: a business date turned into a Date.
export function periodEnd(line: { period: { end_date: string } }): number {
  return new Date(line.period.end_date).getTime();
}

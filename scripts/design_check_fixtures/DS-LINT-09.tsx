// design-check fixture DS-LINT-09: formatting outside the format module and a date literal.
export function Amount({ value }: { value: number }) {
  const cutoff = new Date("2026-01-31");
  return (
    <span data-cutoff={cutoff.getTime()}>{value.toFixed(2)}</span>
  );
}

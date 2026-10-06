// design-check fixture DS-LINT-16: an inline style colour.
export const Swatch = ({ tone }: { tone: string }) => (
  <div style={{ backgroundColor: tone }}>Swatch</div>
);

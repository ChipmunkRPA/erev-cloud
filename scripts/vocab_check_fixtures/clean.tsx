// Near misses that the vocabulary lint must not report.
const netPosition = "net_position";
const unplannedRevenue = "carved";
const revision = "Review the POBs";

export const Balances = () => (
  <dl data-values={[netPosition, unplannedRevenue, revision].join(" ")}>
    <dt>Contract liability</dt>
    <dd>Scheduled</dd>
    <dd>Awaiting trigger</dd>
    <dd>Allocation adjustment</dd>
    <dd>Unbilled receivable</dd>
    <dd>Planned position</dd>
  </dl>
);

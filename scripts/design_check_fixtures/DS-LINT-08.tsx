// design-check fixture DS-LINT-08: a pie chart outside the chart module.
import { Pie, PieChart } from "recharts";

export const Share = () => (
  <PieChart>
    <Pie data={[]} dataKey="value" />
  </PieChart>
);

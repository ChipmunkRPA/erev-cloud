// design-check fixture: a clean component that yields no rule id.
import { useState } from "react";

import { Icon } from "../components/icons/registry";
import { cn } from "../lib/cn";
import { formatMoney } from "../lib/format";

export function BalanceCell({ amount, currency }: { amount: string; currency: string }) {
  const [open, setOpen] = useState(false);
  const openedAt = Date.now();
  return (
    <button
      type="button"
      className={cn("ms-2 ps-3 text-start bg-surface text-fg-2 shadow-popover rounded-md", open && "bg-hover")}
      style={{ color: "var(--fg-1)" }}
      data-opened-at={openedAt}
      onClick={() => setOpen(!open)}
    >
      <Icon name="caret-down" />
      {formatMoney(amount, currency)}
    </button>
  );
}

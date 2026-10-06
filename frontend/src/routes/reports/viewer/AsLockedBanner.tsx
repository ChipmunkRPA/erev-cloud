// RV-04 As locked (SCREENS_B §0.5 rev 1.98 and 1.101; SCREENS SCR-URL-06, SCR-ST-10; BR-RPT-02). For a
// locked context period the source of a report that has a lock dataset defaults to the lock whose
// datasets stand (API-S-Period `dataset_lock`): the screen sets `snapshot` to its id and passes it as
// `period_lock_id`. While that lock is the source the info banner reads "Showing <period label> as
// locked on <timestamp>." with "Show current figures"; otherwise, on a locked period, "Showing current
// figures. <period label> was locked on <timestamp>." with "Show as locked". The time is that lock's —
// when the figures were frozen, on a permanently locked period too. A report the lock does not freeze
// has no other source to offer: the banner says the current sentence, "A period lock does not freeze
// this report." and offers nothing — it never says "as locked" over figures that are current. Where a
// locked period has no lock whose datasets stand, a report the lock froze has no other source to offer
// either: the current sentence alone, with the time of the record that locked the period.
import { Banner } from "../../../components/feedback/Banner";
import { Button } from "../../../components/ui/Button";
import { formatTimestamp } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

/** E-04 states whose reports default to the lock snapshot. */
export const LOCKED_STATES: ReadonlySet<string> = new Set(["closed", "permanently_locked"]);

export interface AsLockedBannerProps {
  /** DS-FMT-19 label of the context period, for example "Aug 2026". */
  readonly periodLabel: string;
  /** The `created_at` of the lock whose datasets stand; of the record that locked the period where none does. */
  readonly lockedAt: string;
  /** True while a lock is the source of the view: the address names one and the report takes it. */
  readonly asLocked: boolean;
  /** True for a report the lock freezes: the only kind that can have "As locked" to offer. */
  readonly frozen: boolean;
  /** True where a lock's datasets stand for the period (`datasetLock`). */
  readonly standing: boolean;
  readonly onShowCurrent: () => void;
  readonly onShowLocked: () => void;
}

export function AsLockedBanner({
  periodLabel,
  lockedAt,
  asLocked,
  frozen,
  standing,
  onShowCurrent,
  onShowLocked,
}: AsLockedBannerProps) {
  const at = formatTimestamp(lockedAt);
  if (asLocked) {
    return (
      <Banner
        tone="info"
        announce="static"
        title={t("reports.asLocked.locked", { period: periodLabel, at })}
        actions={
          <Button variant="link" onClick={onShowCurrent}>
            {t("reports.asLocked.showCurrent")}
          </Button>
        }
      />
    );
  }
  const current = t("reports.asLocked.current", { period: periodLabel, at });
  if (!frozen) {
    return (
      <Banner tone="info" announce="static" title={current}>
        <p>{t("reports.asLocked.notFrozen")}</p>
      </Banner>
    );
  }
  return (
    <Banner
      tone="info"
      announce="static"
      title={current}
      actions={
        standing ? (
          <Button variant="link" onClick={onShowLocked}>
            {t("reports.asLocked.showLocked")}
          </Button>
        ) : undefined
      }
    />
  );
}

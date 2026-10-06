// DS-FMT-24 durations and the DS-CMP-21 date input helpers: parsing typed dates and calendar arithmetic
// over business date strings, independent of the browser time zone (DG-FE-20).
import { afterEach, describe, expect, it } from "vitest";

import {
  addDays,
  addMonths,
  configureFormat,
  currentDateIn,
  dayEndInstant,
  daysInMonth,
  dayStartInstant,
  effectiveInstant,
  formatDuration,
  formatElapsed,
  formatRelative,
  instantMs,
  instantOf,
  parseDateInput,
  timestampDate,
  utcDateOf,
  weekdayNames,
  weekdayOf,
} from "./index";

afterEach(() => {
  configureFormat({ locale: "en-US" });
});

describe("DS-FMT-18 relative time and instants", () => {
  const at = instantMs("2026-09-13T09:30:00Z");

  it("reads just now, minutes, hours and days, then the DS-FMT-17 timestamp from 7 days", () => {
    expect(formatRelative("2026-09-13T09:29:31Z", at)).toBe("just now");
    expect(formatRelative("2026-09-13T09:26:00Z", at)).toBe("4 min ago");
    expect(formatRelative("2026-09-13T06:10:00Z", at)).toBe("3 h ago");
    expect(formatRelative("2026-09-11T09:30:00Z", at)).toBe("2 d ago");
    expect(formatRelative("2026-09-06T09:30:00Z", at)).toBe("06 Sep 2026 09:30 UTC");
    expect(formatRelative("2026-09-13T09:31:00Z", at)).toBe("just now");
  });

  it("instantOf is the RFC 3339 UTC instant of an epoch time, which instantMs reads back", () => {
    expect(instantOf(at)).toBe("2026-09-13T09:30:00.000Z");
    expect(instantMs(instantOf(at + 1))).toBe(at + 1);
  });

  it("instantMs accepts Z or an offset and refuses anything else", () => {
    expect(instantMs("2026-09-13T11:30:00+02:00")).toBe(at);
    expect(() => instantMs("2026-09-13 09:30")).toThrow(/RFC 3339/);
  });
});

describe("DS-FMT-24 durations", () => {
  it("uses the largest two units", () => {
    expect(formatDuration(134_000)).toBe("2 min 14 s");
    expect(formatDuration(3 * 3_600_000 + 5 * 60_000 + 59_000)).toBe("3 h 05 min");
    expect(formatDuration(2 * 86_400_000 + 3 * 3_600_000)).toBe("2 d 03 h");
    expect(formatDuration(14_900)).toBe("14 s");
    expect(formatDuration(0)).toBe("0 s");
    expect(() => formatDuration(-1)).toThrow(/Not a duration/);
  });

  it("measures elapsed time from a UTC timestamp", () => {
    expect(formatElapsed("2026-09-13T09:00:00Z", 1_789_290_134_000)).toBe("2 min 14 s");
    expect(() => formatElapsed("2026-09-13 09:00", 0)).toThrow(/RFC 3339/);
  });
});

describe("DS-CMP-21 date input", () => {
  it("accepts YYYY-MM-DD, DD MMM YYYY and the locale numeric short date", () => {
    expect(parseDateInput("2026-09-07")).toEqual({ ok: true, value: "2026-09-07" });
    expect(parseDateInput(" 07 Sep 2026 ")).toEqual({ ok: true, value: "2026-09-07" });
    expect(parseDateInput("7 sep 2026")).toEqual({ ok: true, value: "2026-09-07" });
    expect(parseDateInput("9/7/2026")).toEqual({ ok: true, value: "2026-09-07" });
    expect(parseDateInput("07/09/2026", { locale: "en-GB" })).toEqual({
      ok: true,
      value: "2026-09-07",
    });
    expect(parseDateInput("7.9.2026", { locale: "de-DE" })).toEqual({
      ok: true,
      value: "2026-09-07",
    });
  });

  it("refuses impossible dates, two-digit years and free text", () => {
    expect(parseDateInput("2026-02-29")).toEqual({ ok: false });
    expect(parseDateInput("31 Sep 2026")).toEqual({ ok: false });
    expect(parseDateInput("9/7/26")).toEqual({ ok: false });
    expect(parseDateInput("next Monday")).toEqual({ ok: false });
    expect(parseDateInput("")).toEqual({ ok: false });
  });
});

describe("calendar arithmetic", () => {
  it("counts days per month, including leap years", () => {
    expect(daysInMonth(2028, 2)).toBe(29);
    expect(daysInMonth(2100, 2)).toBe(28);
    expect(daysInMonth(2000, 2)).toBe(29);
    expect(daysInMonth(2026, 9)).toBe(30);
  });

  it("moves by days and months without shifting across time zones", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2027-01-01", -1)).toBe("2026-12-31");
    expect(addMonths("2026-01-31", 1)).toBe("2026-02-28");
    expect(addMonths("2026-11-15", 14)).toBe("2028-01-15");
    expect(addMonths("2026-01-15", -13)).toBe("2024-12-15");
  });

  it("orders weekdays from Monday", () => {
    expect(weekdayOf("2024-01-01")).toBe(0);
    expect(weekdayOf("1970-01-01")).toBe(3);
    expect(weekdayOf("2000-01-01")).toBe(5);
    expect(weekdayNames("short")).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    expect(utcDateOf(1_789_290_134_000)).toBe("2026-09-13");
  });

  it("takes the UTC calendar date of an instant for timeline headings", () => {
    expect(timestampDate("2026-09-07T23:59:59Z")).toBe("2026-09-07");
    expect(timestampDate("2026-09-08T00:00:00.000Z")).toBe("2026-09-08");
    expect(() => timestampDate("2026-09-07T14:05:00+02:00")).toThrow(
      "Not an RFC 3339 UTC timestamp",
    );
  });
});

describe("DS-I18N-08 picked dates for instant fields (supervisor ruling R-59)", () => {
  /** The calendar date of `instant` on the wall clock of an IANA zone. */
  function localDate(instant: string, timeZone: string): string {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date(instant));
    const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
    return `${part("year")}-${part("month")}-${part("day")}`;
  }

  it("sends an effective date as 12:00:00Z and reads the same date back", () => {
    expect(effectiveInstant("2026-11-01")).toBe("2026-11-01T12:00:00Z");
    for (const date of ["2026-01-01", "2026-11-01", "2028-02-29", "2026-12-31"]) {
      expect(timestampDate(effectiveInstant(date))).toBe(date);
    }
    expect(() => effectiveInstant("2026-11-01T00:00:00Z")).toThrow("Not a business date");
    expect(() => effectiveInstant("2026-02-30")).toThrow("Not a business date");
    expect(() => effectiveInstant("")).toThrow("Not a business date");
  });

  it("is the same calendar date in every zone from UTC-12 to UTC+11, across daylight saving", () => {
    const zones = [
      "Etc/GMT+12",
      "Pacific/Honolulu",
      "America/Los_Angeles",
      "America/New_York",
      "UTC",
      "Europe/Berlin",
      "Asia/Kolkata",
      "Asia/Tokyo",
      "Australia/Sydney",
      "Pacific/Noumea",
    ];
    for (const date of ["2026-01-01", "2026-03-29", "2026-07-01", "2026-11-01"]) {
      for (const zone of zones) {
        expect(`${zone} ${localDate(effectiveInstant(date), zone)}`).toBe(`${zone} ${date}`);
      }
    }
  });

  it("reads the next day beyond UTC+11 (known limitation CFG-EFFECTIVE-DATE-1)", () => {
    expect(localDate(effectiveInstant("2026-11-01"), "Pacific/Auckland")).toBe("2026-11-02");
    expect(localDate(effectiveInstant("2026-07-01"), "Pacific/Fiji")).toBe("2026-07-02");
  });

  it("bounds a validity window in platform time, its last day included", () => {
    expect(dayStartInstant("2026-09-19")).toBe("2026-09-19T00:00:00Z");
    expect(dayEndInstant("2027-09-19")).toBe("2027-09-19T23:59:59Z");
    expect(timestampDate(dayStartInstant("2026-09-19"))).toBe("2026-09-19");
    expect(timestampDate(dayEndInstant("2027-09-19"))).toBe("2027-09-19");
    expect(() => dayStartInstant("19 Sep 2026")).toThrow("Not a business date");
    expect(() => dayEndInstant("2027-09-31")).toThrow("Not a business date");
  });
});

describe("05 TZ-02 the current date of an entity", () => {
  it("currentDateIn reads the calendar date of an instant in the entity's zone, not in UTC or the browser's", () => {
    // 01:30 UTC on 1 Oct 2026: still 30 Sep in Los Angeles, already 1 Oct in Berlin and Tokyo.
    const at = instantMs("2026-10-01T01:30:00Z");
    expect(currentDateIn("America/Los_Angeles", at)).toBe("2026-09-30");
    expect(currentDateIn("Europe/Berlin", at)).toBe("2026-10-01");
    expect(currentDateIn("Asia/Tokyo", at)).toBe("2026-10-01");
    expect(currentDateIn("UTC", at)).toBe("2026-10-01");
    // 20:00 UTC on 31 Dec: the next year in Auckland (UTC+13 in summer).
    expect(currentDateIn("Pacific/Auckland", instantMs("2026-12-31T20:00:00Z"))).toBe("2027-01-01");
  });
});

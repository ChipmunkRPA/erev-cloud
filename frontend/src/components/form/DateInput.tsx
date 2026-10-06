// Date input (DESIGN_SYSTEM DS-CMP-21, DS-FMT-16; APG Date Picker Dialog; docs/dev-guide.md DG-FE-20).
// A text input that accepts `YYYY-MM-DD`, `DD MMM YYYY` and the locale's numeric short date and echoes
// `DD MMM YYYY` on blur, plus a calendar button opening a modal grid: arrows move by day and week, Home
// and End to the week edges, Page Up and Page Down by month (with Shift by year), Enter or Space picks,
// Esc closes and focus returns to the calendar button. Values stay `YYYY-MM-DD` strings.
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import {
  addDays,
  addMonths,
  businessDate,
  dateParts,
  daysInMonth,
  formatDate,
  formatPeriod,
  parseDateInput,
  utcDateOf,
  weekdayNames,
  weekdayOf,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { CalendarBlank, CaretLeft, CaretRight } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { controlClass, type FieldControlProps } from "./Field";

export interface DateInputProps {
  readonly control: FieldControlProps;
  /** The typed text. */
  readonly value: string;
  readonly onChange: (text: string) => void;
  /** The business date after a valid blur or pick, or null when the field is empty or invalid. */
  readonly onValue?: ((date: string | null) => void) | undefined;
  readonly onFormatError?: ((message: string | null) => void) | undefined;
  readonly invalid?: boolean;
  /** DS-CMP-21 "Disabled": the date is shown and cannot be changed; no calendar is offered. */
  readonly disabled?: boolean;
}

function monthWeeks(focus: string): (string | null)[][] {
  const { year, month } = dateParts(focus);
  const first = businessDate(year, month, 1);
  const cells: (string | null)[] = Array.from({ length: weekdayOf(first) }, () => null);
  for (let day = 1; day <= daysInMonth(year, month); day += 1) {
    cells.push(businessDate(year, month, day));
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  return Array.from({ length: cells.length / 7 }, (_, week) => cells.slice(week * 7, week * 7 + 7));
}

export function DateInput({
  control,
  value,
  onChange,
  onValue,
  onFormatError,
  invalid = false,
  disabled = false,
}: DateInputProps) {
  const headingId = useId();
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState(() => utcDateOf(Date.now()));
  const root = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const focusedDay = useRef<HTMLButtonElement>(null);
  const parsed = parseDateInput(value);
  const selected = parsed.ok ? parsed.value : null;

  useEffect(() => {
    if (open) {
      focusedDay.current?.focus();
    }
  }, [open, focus]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target) !== true) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  const choose = (date: string) => {
    onChange(formatDate(date));
    onValue?.(date);
    onFormatError?.(null);
    close();
  };
  const onBlur = () => {
    if (value.trim() === "") {
      onValue?.(null);
      onFormatError?.(null);
    } else if (parsed.ok) {
      onChange(formatDate(parsed.value));
      onValue?.(parsed.value);
      onFormatError?.(null);
    } else {
      onValue?.(null);
      onFormatError?.(t("common.form.date.invalid"));
    }
  };

  const onGridKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const moves: Readonly<Record<string, () => string>> = {
      ArrowRight: () => addDays(focus, 1),
      ArrowLeft: () => addDays(focus, -1),
      ArrowDown: () => addDays(focus, 7),
      ArrowUp: () => addDays(focus, -7),
      Home: () => addDays(focus, -weekdayOf(focus)),
      End: () => addDays(focus, 6 - weekdayOf(focus)),
      PageUp: () => addMonths(focus, event.shiftKey ? -12 : -1),
      PageDown: () => addMonths(focus, event.shiftKey ? 12 : 1),
    };
    const move = moves[event.key];
    if (move !== undefined) {
      event.preventDefault();
      setFocus(move());
    }
  };

  // Modal dialog keyboard (DS-A11Y-10): Esc closes and returns focus to the calendar button; Tab and
  // Shift+Tab cycle inside the dialog.
  useEffect(() => {
    const element = dialog.current;
    if (!open || element === null) {
      return undefined;
    }
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        button.current?.focus();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const focusables = Array.from(
        element.querySelectorAll<HTMLElement>("button[tabindex='0'], button:not([tabindex])"),
      );
      const first = focusables[0];
      const last = focusables.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    element.addEventListener("keydown", onKeyDown);
    return () => element.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const { year, month } = dateParts(focus);
  const firstOfMonth = businessDate(year, month, 1);
  const shortNames = weekdayNames("short");
  const longNames = weekdayNames("long");

  return (
    <div ref={root} className="relative flex items-center gap-1">
      <input
        {...control}
        type="text"
        autoComplete="off"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className={cn(controlClass(invalid), "num")}
      />
      {disabled ? null : (
        <Button
          ref={button}
          variant="ghost"
          icon={CalendarBlank}
          aria-label={t("common.form.date.choose")}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => {
            setFocus(selected ?? utcDateOf(Date.now()));
            setOpen(true);
          }}
        />
      )}
      {open && !disabled ? (
        <div
          ref={dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby={headingId}
          className="absolute start-0 top-full z-[var(--z-popover)] mt-1 rounded-lg border border-hairline bg-raised p-3 shadow-popover"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              icon={CaretLeft}
              aria-label={t("common.form.date.previousMonth")}
              onClick={() => setFocus(addMonths(focus, -1))}
            />
            <h2 id={headingId} aria-live="polite" className="text-title-sm text-fg-1">
              {formatPeriod(firstOfMonth, { startDate: firstOfMonth })}
            </h2>
            <Button
              variant="ghost"
              size="sm"
              icon={CaretRight}
              aria-label={t("common.form.date.nextMonth")}
              onClick={() => setFocus(addMonths(focus, 1))}
            />
          </div>
          <table role="grid" aria-labelledby={headingId} className="border-collapse">
            <thead>
              <tr>
                {shortNames.map((name, index) => (
                  <th
                    key={name}
                    scope="col"
                    abbr={longNames[index]}
                    className="size-8 text-caption font-medium text-fg-3"
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {monthWeeks(focus).map((week) => (
                <tr key={week.find((cell) => cell !== null) ?? "blank"}>
                  {week.map((cell, index) =>
                    cell === null ? (
                      <td key={`blank-${String(index)}`} role="gridcell" />
                    ) : (
                      <td key={cell} role="gridcell" aria-selected={cell === selected}>
                        <button
                          ref={cell === focus ? focusedDay : undefined}
                          type="button"
                          tabIndex={cell === focus ? 0 : -1}
                          aria-label={formatDate(cell)}
                          onClick={() => choose(cell)}
                          onKeyDown={onGridKeyDown}
                          className={cn(
                            "focus-inset num size-8 rounded-sm text-body-sm",
                            cell === selected
                              ? "bg-accent-solid text-on-accent"
                              : "text-fg-1 hover:bg-hover",
                          )}
                        >
                          {dateParts(cell).day}
                        </button>
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

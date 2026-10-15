import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import type { EditorProps } from "./fields";
import {
  DAYS,
  buildHours,
  exceptionsFromValue,
  rowsFromValue,
  type Day,
  type Exception,
  type Range,
  type Row,
} from "./hoursModel";

const CHIP =
  "min-h-11 min-w-12 rounded-full px-3 text-sm font-medium ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-indigo-600";
const TIME =
  "min-h-11 w-28 rounded-lg border border-slate-300 bg-white px-2 text-base focus-visible:outline-2 focus-visible:outline-indigo-600";

function RangeInputs({
  ranges,
  onChange,
  prefix,
}: {
  ranges: Range[];
  onChange: (next: Range[]) => void;
  prefix: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      {ranges.map(([open, close], index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <input
            type="time"
            aria-label={t("knowledge.fields.hours.opens", { row: prefix })}
            className={TIME}
            value={open}
            onChange={(e) => onChange(ranges.map((r, i) => (i === index ? [e.target.value, r[1]] : r)))}
          />
          <span aria-hidden="true">–</span>
          <input
            type="time"
            aria-label={t("knowledge.fields.hours.closes", { row: prefix })}
            className={TIME}
            value={close}
            onChange={(e) => onChange(ranges.map((r, i) => (i === index ? [r[0], e.target.value] : r)))}
          />
          <Button variant="ghost" onClick={() => onChange(ranges.filter((_, i) => i !== index))}>
            {t("knowledge.fields.hours.removeRange")}
          </Button>
        </div>
      ))}
      <div>
        <Button variant="secondary" onClick={() => onChange([...ranges, ["09:00", "18:00"]])}>
          {t("knowledge.fields.hours.addRange")}
        </Button>
      </div>
    </div>
  );
}

/** Weekday chips with time ranges, plus holiday exceptions. */
export function HoursEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>(() => rowsFromValue(value));
  const [exceptions, setExceptions] = useState<Exception[]>(() => exceptionsFromValue(value));

  const commit = (nextRows: Row[], nextExceptions: Exception[]) => {
    setRows(nextRows);
    setExceptions(nextExceptions);
    onChange(buildHours(nextRows, nextExceptions));
  };

  const toggleDay = (rowIndex: number, day: Day) => {
    const has = rows[rowIndex]?.days.includes(day);
    commit(
      rows.map((row, i) => {
        if (i === rowIndex) {
          return { ...row, days: has ? row.days.filter((d) => d !== day) : [...row.days, day] };
        }
        return has ? row : { ...row, days: row.days.filter((d) => d !== day) }; // a day is in one row only
      }),
      exceptions,
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">{t("knowledge.fields.hours.closedHint")}</p>
      {rows.map((row, rowIndex) => (
        <fieldset key={rowIndex} className="flex flex-col gap-3 rounded-xl p-3 ring-1 ring-slate-200">
          <legend className="px-1 text-sm font-medium">
            {t("knowledge.fields.hours.row", { n: rowIndex + 1 })}
          </legend>
          <div className="flex flex-wrap gap-2" role="group" aria-label={t("knowledge.fields.hours.days")}>
            {DAYS.map((day) => {
              const on = row.days.includes(day);
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleDay(rowIndex, day)}
                  className={`${CHIP} ${on ? "bg-indigo-700 text-white ring-indigo-700" : "bg-white text-slate-800 ring-slate-300"}`}
                >
                  {t(`knowledge.days.${day}`)}
                </button>
              );
            })}
          </div>
          <RangeInputs
            ranges={row.ranges}
            prefix={String(rowIndex + 1)}
            onChange={(ranges) => commit(rows.map((r, i) => (i === rowIndex ? { ...r, ranges } : r)), exceptions)}
          />
          <div>
            <Button variant="ghost" onClick={() => commit(rows.filter((_, i) => i !== rowIndex), exceptions)}>
              {t("knowledge.fields.hours.removeRow")}
            </Button>
          </div>
        </fieldset>
      ))}
      <div>
        <Button
          variant="secondary"
          onClick={() => commit([...rows, { days: [], ranges: [["09:00", "18:00"]] }], exceptions)}
        >
          {t("knowledge.fields.hours.addRow")}
        </Button>
      </div>

      <h3 className="text-base font-medium">{t("knowledge.fields.hours.exceptions")}</h3>
      {exceptions.map((exception, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl p-3 ring-1 ring-slate-200">
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="date"
              aria-label={t("knowledge.fields.hours.exceptionDate")}
              className={TIME + " w-44"}
              value={exception.date}
              onChange={(e) =>
                commit(rows, exceptions.map((x, i) => (i === index ? { ...x, date: e.target.value } : x)))
              }
            />
            <label className="flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                className="size-5"
                checked={exception.closed}
                onChange={(e) =>
                  commit(
                    rows,
                    exceptions.map((x, i) =>
                      i === index
                        ? { ...x, closed: e.target.checked, ranges: e.target.checked ? [] : [["09:00", "13:00"]] }
                        : x,
                    ),
                  )
                }
              />
              {t("knowledge.fields.hours.closedAllDay")}
            </label>
            <Button variant="ghost" onClick={() => commit(rows, exceptions.filter((_, i) => i !== index))}>
              {t("knowledge.fields.hours.removeException")}
            </Button>
          </div>
          {exception.closed ? null : (
            <RangeInputs
              ranges={exception.ranges}
              prefix={exception.date}
              onChange={(ranges) =>
                commit(rows, exceptions.map((x, i) => (i === index ? { ...x, ranges } : x)))
              }
            />
          )}
        </div>
      ))}
      <div>
        <Button
          variant="secondary"
          onClick={() => commit(rows, [...exceptions, { date: "", closed: true, ranges: [] }])}
        >
          {t("knowledge.fields.hours.addException")}
        </Button>
      </div>
    </div>
  );
}

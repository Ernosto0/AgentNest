import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TextField } from "@/components/TextField";
import { uiLocale } from "../labels";
import { formatMoneyAmount, parseMoneyInput, type Money, type MoneyParse } from "../money";
import { SelectField, TextAreaField, type EditorProps, type FactValue } from "./fields";
import { asString } from "./util";

const UNITS = ["", "month", "session", "package", "item", "hour", "person", "day", "year"] as const;

function initialText(value: FactValue | null): string {
  const amount = asString(value?.amount);
  return amount.endsWith(".00") ? amount.slice(0, -3) : amount;
}

function conditionsOf(value: FactValue | null): { tr: string; en: string } {
  const raw = value?.conditions;
  const conditions = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  return { tr: asString(conditions.tr), en: asString(conditions.en) };
}

/** Amount + unit + conditions. Shows the formatted amount and asks when the notation is unclear. */
export function MoneyEditor({ value, onChange, currency }: EditorProps) {
  const { t, i18n } = useTranslation();
  const locale = uiLocale(i18n.language);
  const [text, setText] = useState(initialText(value));
  const [unit, setUnit] = useState(asString(value?.unit));
  const [conditions, setConditions] = useState(conditionsOf(value));
  const [choice, setChoice] = useState<number | null>(null);

  const parsed: MoneyParse | null = text.trim() ? parseMoneyInput(text, locale, currency) : null;

  const emit = (next: {
    parsed: MoneyParse | null;
    choice: number | null;
    unit: string;
    conditions: { tr: string; en: string };
  }) => {
    let money: Money | null = null;
    if (next.parsed?.kind === "money") money = next.parsed.money;
    if (next.parsed?.kind === "ambiguous" && next.choice !== null) {
      money = next.parsed.alternatives[next.choice] ?? null;
    }
    if (money === null) return onChange(null);
    const out: FactValue = { amount: money.amount, currency: money.currency };
    if (next.unit) out.unit = next.unit;
    const tr = next.conditions.tr.trim();
    const en = next.conditions.en.trim();
    if (tr || en) out.conditions = { ...(tr ? { tr } : {}), ...(en ? { en } : {}) };
    onChange(out);
  };

  const update = (patch: Partial<{ text: string; choice: number | null; unit: string; conditions: { tr: string; en: string } }>) => {
    const nextText = patch.text ?? text;
    const nextChoice = "choice" in patch ? (patch.choice ?? null) : patch.text !== undefined ? null : choice;
    const nextUnit = patch.unit ?? unit;
    const nextConditions = patch.conditions ?? conditions;
    setText(nextText);
    setChoice(nextChoice);
    setUnit(nextUnit);
    setConditions(nextConditions);
    emit({
      parsed: nextText.trim() ? parseMoneyInput(nextText, locale, currency) : null,
      choice: nextChoice,
      unit: nextUnit,
      conditions: nextConditions,
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <TextField
        label={t("knowledge.fields.money.amount", { currency })}
        inputMode="decimal"
        autoComplete="off"
        value={text}
        onChange={(event) => update({ text: event.target.value })}
        error={parsed?.kind === "error" ? t(`knowledge.moneyError.${parsed.code}`) : undefined}
      />
      {parsed?.kind === "money" ? (
        <p className="text-sm text-slate-700" aria-live="polite">
          {t("knowledge.fields.money.preview", {
            amount: formatMoneyAmount(parsed.money.amount, parsed.money.currency, locale),
          })}
        </p>
      ) : null}
      {parsed?.kind === "ambiguous" ? (
        <fieldset className="flex flex-col gap-2 rounded-lg bg-amber-50 p-3 ring-1 ring-amber-400">
          <legend className="px-1 text-sm font-medium text-amber-900">
            {t("knowledge.fields.money.ambiguous")}
          </legend>
          {parsed.alternatives.map((alternative, index) => (
            <label key={alternative.amount} className="flex min-h-11 items-center gap-3 text-base">
              <input
                type="radio"
                name="money-reading"
                className="size-5"
                checked={choice === index}
                onChange={() => update({ choice: index })}
              />
              <span>{formatMoneyAmount(alternative.amount, alternative.currency, locale)}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
      <SelectField
        label={t("knowledge.fields.money.unit")}
        value={unit}
        onChange={(event) => update({ unit: event.target.value })}
      >
        {UNITS.map((u) => (
          <option key={u} value={u}>
            {u ? t(`knowledge.unit.${u}`) : t("knowledge.unit.none")}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        label={t("knowledge.fields.money.conditionsTr")}
        rows={2}
        value={conditions.tr}
        onChange={(event) => update({ conditions: { ...conditions, tr: event.target.value } })}
      />
      <TextAreaField
        label={t("knowledge.fields.money.conditionsEn")}
        rows={2}
        value={conditions.en}
        onChange={(event) => update({ conditions: { ...conditions, en: event.target.value } })}
      />
    </div>
  );
}

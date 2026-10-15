import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TextField } from "@/components/TextField";
import { parsePhone } from "../money";
import { SelectField, TextAreaField, type EditorProps, type FactValue } from "./fields";
import { asString } from "./util";

export function TextEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(asString(value?.text));
  return (
    <TextAreaField
      label={t("knowledge.fields.text")}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onChange(event.target.value.trim() ? { text: event.target.value } : null);
      }}
    />
  );
}

type LanguageTab = "tr" | "en";

export function LocalizedTextEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<LanguageTab>("tr");
  const [texts, setTexts] = useState<Record<LanguageTab, string>>({
    tr: asString(value?.tr),
    en: asString(value?.en),
  });

  const update = (next: Record<LanguageTab, string>) => {
    setTexts(next);
    const out: FactValue = {};
    if (next.tr.trim()) out.tr = next.tr;
    if (next.en.trim()) out.en = next.en;
    onChange(Object.keys(out).length > 0 ? out : null);
  };

  return (
    <div className="flex flex-col gap-2">
      <div role="tablist" aria-label={t("knowledge.fields.languages")} className="flex gap-2">
        {(["tr", "en"] as const).map((language) => (
          <button
            key={language}
            type="button"
            role="tab"
            id={`lt-tab-${language}`}
            aria-selected={tab === language}
            aria-controls="lt-panel"
            onClick={() => setTab(language)}
            className={`min-h-11 rounded-lg px-4 text-base font-medium ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              tab === language
                ? "bg-indigo-700 text-white ring-indigo-700"
                : "bg-white text-slate-800 ring-slate-300"
            }`}
          >
            {t(`knowledge.fields.language.${language}`)}
            {texts[language].trim() ? null : <span className="sr-only">{t("knowledge.fields.empty")}</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="lt-panel" aria-labelledby={`lt-tab-${tab}`}>
        <TextAreaField
          label={t(`knowledge.fields.language.${tab}`)}
          rows={5}
          value={texts[tab]}
          onChange={(event) => update({ ...texts, [tab]: event.target.value })}
        />
      </div>
    </div>
  );
}

export function PhoneEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(asString(value?.display) || asString(value?.e164));
  const e164 = parsePhone(text);
  return (
    <TextField
      label={t("knowledge.fields.phone")}
      type="tel"
      inputMode="tel"
      autoComplete="off"
      value={text}
      error={text.trim() && !e164 ? t("knowledge.fieldErrors.invalid_phone") : undefined}
      onChange={(event) => {
        setText(event.target.value);
        const parsed = parsePhone(event.target.value);
        onChange(parsed ? { e164: parsed } : null);
      }}
    />
  );
}

export function EmailEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(asString(value?.email));
  return (
    <TextField
      label={t("knowledge.fields.email")}
      type="email"
      autoComplete="off"
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onChange(/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(event.target.value.trim()) ? { email: event.target.value.trim() } : null);
      }}
    />
  );
}

export function UrlEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(asString(value?.url));
  return (
    <TextField
      label={t("knowledge.fields.url")}
      type="url"
      autoComplete="off"
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onChange(/^https?:\/\/\S+$/i.test(event.target.value.trim()) ? { url: event.target.value.trim() } : null);
      }}
    />
  );
}

export function AddressEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const initialLines = Array.isArray(value?.lines) ? (value.lines as unknown[]).map(asString) : [];
  const [state, setState] = useState({
    lines: initialLines.join("\n"),
    district: asString(value?.district),
    city: asString(value?.city),
    mapsUrl: asString(value?.maps_url),
  });

  const update = (next: typeof state) => {
    setState(next);
    const lines = next.lines.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0 || !next.city.trim()) return onChange(null);
    const out: FactValue = { lines, city: next.city.trim() };
    if (next.district.trim()) out.district = next.district.trim();
    if (next.mapsUrl.trim()) out.maps_url = next.mapsUrl.trim();
    onChange(out);
  };

  return (
    <div className="flex flex-col gap-3">
      <TextAreaField
        label={t("knowledge.fields.address.lines")}
        hint={t("knowledge.fields.address.linesHint")}
        value={state.lines}
        onChange={(event) => update({ ...state, lines: event.target.value })}
      />
      <TextField
        label={t("knowledge.fields.address.district")}
        value={state.district}
        onChange={(event) => update({ ...state, district: event.target.value })}
      />
      <TextField
        label={t("knowledge.fields.address.city")}
        value={state.city}
        onChange={(event) => update({ ...state, city: event.target.value })}
      />
      <TextField
        label={t("knowledge.fields.address.mapsUrl")}
        type="url"
        value={state.mapsUrl}
        onChange={(event) => update({ ...state, mapsUrl: event.target.value })}
      />
    </div>
  );
}

export function BooleanEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const [answer, setAnswer] = useState<boolean | null>(
    typeof value?.value === "boolean" ? value.value : null,
  );
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="text-sm font-medium text-slate-800">{t("knowledge.fields.boolean")}</legend>
      {([true, false] as const).map((option) => (
        <label key={String(option)} className="flex min-h-11 items-center gap-3 text-base">
          <input
            type="radio"
            name="boolean-answer"
            className="size-5"
            checked={answer === option}
            onChange={() => {
              setAnswer(option);
              onChange({ value: option });
            }}
          />
          {t(`knowledge.bool.${option}`)}
        </label>
      ))}
    </fieldset>
  );
}

export function EnumEditor({ value, onChange, allowedValues }: EditorProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState(asString(value?.value));
  return (
    <SelectField
      label={t("knowledge.fields.enum")}
      value={selected}
      onChange={(event) => {
        setSelected(event.target.value);
        onChange(event.target.value ? { value: event.target.value } : null);
      }}
    >
      <option value="">{t("knowledge.fields.choose")}</option>
      {allowedValues.map((option) => (
        <option key={option} value={option}>
          {t(`knowledge.enum.${option}`, { defaultValue: option })}
        </option>
      ))}
    </SelectField>
  );
}

export function StringListEditor({ value, onChange }: EditorProps) {
  const { t } = useTranslation();
  const initial = Array.isArray(value?.items) ? (value.items as unknown[]).map(asString) : [];
  const [text, setText] = useState(initial.join("\n"));
  return (
    <TextAreaField
      label={t("knowledge.fields.list")}
      hint={t("knowledge.fields.listHint")}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        const items = event.target.value.split("\n").map((i) => i.trim()).filter(Boolean);
        onChange(items.length > 0 ? { items } : null);
      }}
    />
  );
}

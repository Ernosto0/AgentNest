import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES, isLanguage, setLanguage, type Language } from "@/i18n";

interface LanguageSwitchProps {
  /** Called after the UI language changed, e.g. to save it on the user's account. */
  onChange?: (language: Language) => void;
}

/** Turkish / English segmented control. Each option is labelled in its own language. */
export function LanguageSwitch({ onChange }: LanguageSwitchProps) {
  const { t, i18n } = useTranslation();
  const current = isLanguage(i18n.language) ? i18n.language : "tr";

  async function choose(language: Language) {
    if (language === current) return;
    await setLanguage(language);
    onChange?.(language);
  }

  return (
    <div
      role="group"
      aria-label={t("common.language")}
      className="inline-flex overflow-hidden rounded-lg ring-1 ring-slate-300"
    >
      {SUPPORTED_LANGUAGES.map((language) => (
        <button
          key={language}
          type="button"
          lang={language}
          aria-pressed={language === current}
          onClick={() => void choose(language)}
          className={[
            "min-h-11 min-w-20 px-4 text-base font-medium",
            "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-indigo-600",
            language === current ? "bg-indigo-700 text-white" : "bg-white text-slate-800 hover:bg-slate-50",
          ].join(" ")}
        >
          {t(`settings.languages.${language}`, { lng: language })}
        </button>
      ))}
    </div>
  );
}

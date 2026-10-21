import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enActivity from "./locales/en/activity.json";
import enAi from "./locales/en/ai.json";
import en from "./locales/en/common.json";
import enContent from "./locales/en/content.json";
import enInbox from "./locales/en/inbox.json";
import enKnowledge from "./locales/en/knowledge.json";
import trActivity from "./locales/tr/activity.json";
import trAi from "./locales/tr/ai.json";
import tr from "./locales/tr/common.json";
import trContent from "./locales/tr/content.json";
import trInbox from "./locales/tr/inbox.json";
import trKnowledge from "./locales/tr/knowledge.json";

export const SUPPORTED_LANGUAGES = ["tr", "en"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];
export const DEFAULT_LANGUAGE: Language = "tr";

const STORAGE_KEY = "agentnest.language";

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** Stored choice, then the browser language, then Turkish (the primary market). */
export function detectLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // Storage can be blocked (private mode): fall through to the browser language.
  }
  const browser = typeof navigator === "undefined" ? "" : navigator.language.toLowerCase();
  return browser.startsWith("en") ? "en" : DEFAULT_LANGUAGE;
}

/** Switch the UI language now and remember it on this device. */
export async function setLanguage(language: Language): Promise<void> {
  try {
    window.localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Not persisting is acceptable: the account setting is the durable copy.
  }
  await i18n.changeLanguage(language);
}

i18n.on("languageChanged", (language) => {
  document.documentElement.lang = language;
});

void i18n.use(initReactI18next).init({
  // One namespace; the knowledge catalog is a separate file merged into it (top-level keys differ).
  resources: {
    tr: { common: { ...tr, ...trKnowledge, ...trAi, ...trInbox, ...trContent, ...trActivity } },
    en: { common: { ...en, ...enKnowledge, ...enAi, ...enInbox, ...enContent, ...enActivity } },
  },
  lng: detectLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: SUPPORTED_LANGUAGES,
  defaultNS: "common",
  ns: ["common"],
  interpolation: { escapeValue: false }, // React escapes
  returnNull: false,
});

export default i18n;

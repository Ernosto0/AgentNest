import { useEffect } from "react";
import { isLanguage, setLanguage } from "@/i18n";
import { useMe } from "@/features/auth/hooks";

/**
 * The account's saved language wins over the device default once the user is known
 * (ADR-016: users.ui_locale). Runs when the saved language changes, not on every render,
 * so a language picked in the UI is never reverted while it is being saved.
 */
export function LanguageSync() {
  const me = useMe();
  const saved = me.data?.user.ui_locale;
  useEffect(() => {
    if (isLanguage(saved)) void setLanguage(saved);
  }, [saved]);
  return null;
}

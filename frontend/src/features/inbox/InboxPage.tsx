import { useTranslation } from "react-i18next";
import { InboxIcon } from "@/components/icons";

export function InboxPage() {
  const { t } = useTranslation();
  return <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-panel bg-surface p-6 text-center">
    <InboxIcon className="text-3xl text-secondary" />
    <h2 className="type-section">{t("convo.selectConversation")}</h2>
    <p className="text-secondary">{t("convo.selectHint")}</p>
  </div>;
}

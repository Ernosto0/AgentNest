import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/EmptyState";

interface SectionPlaceholderPageProps {
  section: "inbox" | "content" | "approvals";
}

/** Phase 1 has no domain features: each tab explains that its section comes later. */
export function SectionPlaceholderPage({ section }: SectionPlaceholderPageProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold">{t(`${section}.title`)}</h1>
      <EmptyState title={t("empty.comingLater")} description={t("empty.comingLaterHint")} />
    </div>
  );
}

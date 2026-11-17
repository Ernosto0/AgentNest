import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";
import { useMeta } from "@/features/auth/hooks";

export function TermsPage() {
  const { t } = useTranslation();
  const meta = useMeta();
  return <PublicShell title={t("signup.terms")}>
    <div className="flex flex-col gap-5 rounded-panel border border-border bg-surface p-6">
      <p>{t("signup.version", { version: meta.data?.terms_version ?? "" })}</p>
      <p>{t("signup.termsBody")}</p>
      <p>{t("signup.termsResponsibility")}</p>
      <Link to="/privacy" className="inline-flex min-h-11 items-center text-action underline">{t("legal.privacyTitle")}</Link>
      <Link to="/signup" className="inline-flex min-h-11 items-center text-action underline">{t("signup.title")}</Link>
    </div>
  </PublicShell>;
}

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";

export function PrivacyPolicyPage() {
  const { t } = useTranslation();

  return (
    <PublicShell
      title={t("legal.privacyTitle")}
      description={t("legal.privacySubtitle")}
      action={
        <Link to="/login">
          <Button variant="secondary">{t("legal.backToLogin")}</Button>
        </Link>
      }
    >
      <div className="flex flex-col gap-6 rounded-panel border border-border bg-surface p-6 sm:p-8">
        <section className="flex flex-col gap-2">
          <p className="text-sm leading-relaxed text-secondary">{t("legal.privacySummary")}</p>
        </section>

        <section className="flex flex-col gap-2 border-t border-border pt-4">
          <h2 className="font-heading text-base font-semibold text-primary">
            {t("legal.privacyControllerSection")}
          </h2>
          <p className="text-sm leading-relaxed text-secondary">{t("legal.privacyControllerText")}</p>
        </section>

        <section className="flex flex-col gap-2 border-t border-border pt-4">
          <h2 className="font-heading text-base font-semibold text-primary">
            {t("legal.privacySecuritySection")}
          </h2>
          <p className="text-sm leading-relaxed text-secondary">{t("legal.privacySecurityText")}</p>
        </section>

        <section className="flex flex-col gap-2 border-t border-border pt-4">
          <h2 className="font-heading text-base font-semibold text-primary">
            {t("legal.privacyRetentionSection")}
          </h2>
          <p className="text-sm leading-relaxed text-secondary">{t("legal.privacyRetentionText")}</p>
        </section>

        <section className="flex flex-col gap-2 border-t border-border pt-4">
          <h2 className="font-heading text-base font-semibold text-primary">
            {t("legal.privacyContactSection")}
          </h2>
          <p className="text-sm leading-relaxed text-secondary">{t("legal.privacyContactText")}</p>
        </section>

        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4 text-xs text-secondary">
          <Link to="/data-deletion" className="hover:underline">
            {t("legal.dataDeletionTitle")}
          </Link>
          <Link to="/login" className="hover:underline">
            {t("legal.backToLogin")}
          </Link>
        </div>
      </div>
    </PublicShell>
  );
}

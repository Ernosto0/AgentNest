import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";

export function PrivacyPolicyPage() {
  const { t } = useTranslation();

  return (
    <PublicShell
      title={t("legal.privacyTitle")}
      description={t("legal.privacySubtitle")}
      action={
        <Link to="/login" className="inline-flex min-h-11 items-center rounded-control border border-border bg-surface px-4 text-body font-medium text-primary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t("legal.backToLogin")}</Link>
      }
    >
      <div className="flex flex-col gap-6 rounded-panel border border-border bg-surface p-6 sm:p-8 shadow-xs">
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
          <Link to="/data-deletion" className="inline-flex min-h-11 items-center rounded-control hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            {t("legal.dataDeletionTitle")}
          </Link>
          <Link to="/login" className="inline-flex min-h-11 items-center rounded-control hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            {t("legal.backToLogin")}
          </Link>
        </div>
      </div>
    </PublicShell>
  );
}


import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { useMeta } from "@/features/auth/hooks";
import type { Language } from "@/i18n";

/** Form-first on phones, with a quiet desktop brand region. No customer data lives here. */
export function PublicShell({ title, description, children, action, onLanguageChange }: {
  title: string; description?: string; children: ReactNode; action?: ReactNode;
  onLanguageChange?: (language: Language) => void;
}) {
  const { t } = useTranslation();
  const meta = useMeta();
  const name = meta.data?.product_name ?? t("app.name");
  return <div className="min-h-dvh bg-canvas text-primary lg:grid lg:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.2fr)]">
    <aside aria-label={t("entry.brandRegion")} className="hidden min-h-dvh flex-col justify-between bg-navigation p-12 text-navigation-text lg:flex xl:p-16">
      <p className="font-heading text-2xl font-bold tracking-tight">{name}</p>
      <div className="my-16 max-w-md"><p className="font-heading text-4xl leading-tight font-semibold tracking-tight xl:text-5xl">{t("entry.brandTitle")}</p><p className="mt-6 text-lg leading-relaxed">{t("entry.brandDetail")}</p></div>
      <p className="text-metadata">{t("entry.brandFooter")}</p>
    </aside>
    <main className="mx-auto flex min-h-dvh w-full min-w-0 max-w-2xl flex-col px-4 py-6 sm:px-8 lg:px-12 lg:py-10">
      <div className="flex flex-wrap items-center justify-between gap-4"><p className="font-heading text-xl font-bold tracking-tight text-primary lg:hidden">{name}</p><div className="ml-auto flex flex-wrap items-center gap-2"><LanguageSwitch onChange={onLanguageChange} />{action}</div></div>
      <div className="my-auto flex min-w-0 flex-col gap-6 py-10 lg:py-12"><header><h1 className="type-page break-words">{title}</h1>{description ? <p className="mt-3 max-w-prose text-form text-secondary">{description}</p> : null}</header>{children}</div>
    </main>
  </div>;
}

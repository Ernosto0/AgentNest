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
    <aside aria-label={t("entry.brandRegion")} className="relative hidden min-h-dvh flex-col justify-between bg-[#0e1814] border-r border-[#1a2b22] p-12 text-navigation-text lg:flex xl:p-16 overflow-hidden">
      <div className="absolute top-0 right-0 h-96 w-96 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 left-0 h-96 w-96 rounded-full bg-teal-500/10 blur-3xl pointer-events-none" />
      <div className="flex items-center gap-3 relative z-10">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-sm ring-1 ring-white/20">
          <span className="font-heading text-lg font-bold">A</span>
        </div>
        <p className="font-heading text-2xl font-bold tracking-tight text-white">{name}</p>
      </div>
      <div className="my-16 max-w-md relative z-10">
        <p className="font-heading text-4xl leading-tight font-extrabold tracking-tight xl:text-5xl text-white">{t("entry.brandTitle")}</p>
        <p className="mt-6 text-lg leading-relaxed text-[#b4c7bb]">{t("entry.brandDetail")}</p>
      </div>
      <p className="text-metadata text-[#738d7b] relative z-10">{t("entry.brandFooter")}</p>
    </aside>
    <main className="mx-auto flex min-h-dvh w-full min-w-0 max-w-2xl flex-col px-4 py-6 sm:px-8 lg:px-12 lg:py-10">
      <div className="flex flex-wrap items-center justify-between gap-4"><p className="font-heading text-xl font-bold tracking-tight text-primary lg:hidden">{name}</p><div className="ml-auto flex flex-wrap items-center gap-2"><LanguageSwitch onChange={onLanguageChange} />{action}</div></div>
      <div className="my-auto flex min-w-0 flex-col gap-6 py-10 lg:py-12"><header><h1 className="type-page break-words">{title}</h1>{description ? <p className="mt-3 max-w-prose text-form text-secondary">{description}</p> : null}</header>{children}</div>
    </main>
  </div>;
}

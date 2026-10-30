import { useEffect, useState } from "react";
import i18n from "@/i18n";
import { SharedReference } from "./SharedReference";
import { AlertIcon, CheckIcon, ClockIcon, HomeIcon, InfoIcon, ShieldCheckIcon } from "@/components/icons";

// Development fixture copy is deliberately separate from the production catalogs.
const COPY = {
  en: {
    title: "Workspace design reference", intro: "Local specimens · no business data or API calls",
    heading: "A clear view of your day", section: "Typography and Turkish glyphs",
    body: "Readable working text for decisions, messages and forms.", metadata: "Supporting details remain readable at 13 px.",
    metric: "Metric type specimen · fictional number", colors: "Surfaces, boundaries and focus", sample: "Example field",
    action: "Primary action", navigation: "Navigation specimen", current: "Today", statuses: "State specimens · labels remain explicit",
    success: "Verified success", attention: "Needs a decision", danger: "Failed", info: "Checking", simulation: "Simulated",
    focus: "Use Tab to inspect the focus ring", inverse: "Use Tab to inspect inverse focus", brand: "AgentNest",
  },
  tr: {
    title: "Çalışma alanı tasarım referansı", intro: "Yerel örnekler · işletme verisi veya API çağrısı yok",
    heading: "Gününüzü net bir şekilde görün", section: "Yazı stilleri ve Türkçe karakterler",
    body: "Kararlar, mesajlar ve formlar için okunaklı çalışma metni.", metadata: "Destekleyici ayrıntılar 13 pikselde okunabilir kalır.",
    metric: "Sayı stili örneği · kurgu değer", colors: "Yüzeyler, sınırlar ve odak", sample: "Örnek alan",
    action: "Birincil işlem", navigation: "Gezinme örneği", current: "Bugün", statuses: "Durum örnekleri · açık metin etiketleri",
    success: "Doğrulanmış başarı", attention: "Karar bekliyor", danger: "Başarısız", info: "Kontrol ediliyor", simulation: "Simülasyon",
    focus: "Odak halkasını incelemek için Tab kullanın", inverse: "Koyu yüzeyde odağı incelemek için Tab kullanın", brand: "AgentNest",
  },
} as const;

const GLYPHS = "İ ı Ğ ğ Ş ş Ö ö Ü ü Ç ç · ₺ € £ $ · 0123456789";
const SURFACES = ["surface", "canvas", "surface-subtle", "assistant"] as const;
const SURFACE_CLASSES = {
  surface: "bg-surface", canvas: "bg-canvas", "surface-subtle": "bg-surface-subtle", assistant: "bg-assistant",
};

/** Extend this development-only view when shared controls migrate in Session 03. */
export function DesignReference() {
  const [locale, setLocale] = useState<"en" | "tr">(() => new URLSearchParams(location.search).get("lang") === "en" ? "en" : "tr");
  const copy = COPY[locale];
  useEffect(() => { void i18n.changeLanguage(locale); }, [locale]);
  return (
    <main lang={locale} className="mx-auto grid min-h-dvh max-w-7xl gap-8 px-4 py-8 text-primary md:px-8" data-testid="design-reference">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-heading text-section font-bold">{copy.brand}</p>
          <h1 className="type-page mt-3">{copy.title}</h1>
          <p className="mt-2 text-secondary">{copy.intro}</p>
        </div>
        <div className="flex gap-2">
          {(["tr", "en"] as const).map(language => (
            <button key={language} type="button" onClick={() => setLocale(language)} aria-pressed={language === locale} className="min-h-11 min-w-11 rounded-control border border-control bg-surface px-3 uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{language}</button>
          ))}
        </div>
      </header>

      <section className="rounded-panel border border-border bg-surface p-6">
        <h2 className="type-section">{copy.section}</h2>
        <h3 className="type-page mt-4" data-testid="heading-specimen">{copy.heading}</h3>
        <p className="mt-4 text-form" data-testid="body-specimen">{copy.body}</p>
        <p className="mt-2 text-metadata text-secondary">{copy.metadata}</p>
        <p className="mt-4 font-heading text-section" data-testid="heading-glyphs">{GLYPHS}</p>
        <p className="mt-2 text-form" data-testid="body-glyphs">{GLYPHS}</p>
        <p className="type-metric mt-6">{new Intl.NumberFormat(locale).format(1234)}</p>
        <p className="text-metadata text-secondary">{copy.metric}</p>
      </section>

      <section>
        <h2 className="type-section mb-4">{copy.colors}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {SURFACES.map(surface => (
            <div key={surface} data-surface={surface} className={`grid gap-3 rounded-panel border border-border p-5 ${SURFACE_CLASSES[surface]}`}>
              <p className="font-semibold">{surface}</p>
              <p className="text-secondary">{copy.focus}</p>
              <label className="grid gap-2 text-body font-medium">
                {copy.sample}
                <input className="min-h-11 min-w-0 rounded-control border border-control bg-transparent px-3 text-form focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus" defaultValue={GLYPHS} />
              </label>
              <button type="button" className="min-h-11 rounded-control bg-action px-4 py-2 text-on-action transition-colors hover:bg-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{copy.action}</button>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 rounded-panel bg-navigation p-6 text-navigation-text" data-surface="navigation">
        <h2 className="type-section">{copy.navigation}</h2>
        <p>{copy.inverse}</p>
        <button type="button" className="flex min-h-11 items-center gap-3 rounded-control bg-navigation-selected px-4 py-2 text-left font-semibold text-navigation-selected-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-inverse"><HomeIcon />{copy.current}</button>
      </section>

      <section>
        <h2 className="type-section mb-4">{copy.statuses}</h2>
        <div className="flex flex-wrap gap-3">
          <span data-tone="success" className="inline-flex items-center gap-2 rounded-control bg-success-subtle px-3 py-2 text-body text-success"><CheckIcon />{copy.success}</span>
          <span data-tone="attention" className="inline-flex items-center gap-2 rounded-control bg-attention-subtle px-3 py-2 text-body text-attention"><AlertIcon />{copy.attention}</span>
          <span data-tone="danger" className="inline-flex items-center gap-2 rounded-control bg-danger-subtle px-3 py-2 text-body text-danger"><AlertIcon />{copy.danger}</span>
          <span data-tone="info" className="inline-flex items-center gap-2 rounded-control bg-info-subtle px-3 py-2 text-body text-info"><ClockIcon />{copy.info}</span>
          <span data-tone="simulation" className="inline-flex items-center gap-2 rounded-control bg-simulation-subtle px-3 py-2 text-body text-simulation"><ShieldCheckIcon />{copy.simulation}</span>
          <InfoIcon className="size-6 text-info" />
        </div>
      </section>
      <SharedReference locale={locale} />
    </main>
  );
}

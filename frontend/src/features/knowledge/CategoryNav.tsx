import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { FactCategory } from "@/api/types";
import { FOCUS } from "@/features/home/DashboardPanel";
import { CategoryCounts } from "./CategoryCounts";
import { CategoryGlyph } from "./CategoryGlyph";
import { CATEGORY_GROUPS, type CategorySummary } from "./model";

/**
 * Jump between categories without going back to the overview: a grouped rail beside the facts
 * from 1024 px, a horizontally scrolling strip (inside its own box) on smaller screens.
 */
export function CategoryNav({
  current,
  base,
  summaries,
}: {
  current: FactCategory;
  base: string;
  summaries: CategorySummary[] | null;
}) {
  const { t } = useTranslation();
  const strip = useRef<HTMLDivElement>(null);
  const byCategory = new Map(summaries?.map((s) => [s.category, s]));

  // Keep the open category visible in the phone strip without scrolling the page.
  useEffect(() => {
    const box = strip.current;
    const active = box?.querySelector<HTMLElement>("[aria-current='page']");
    if (!box || !active || box.scrollWidth <= box.clientWidth) return;
    box.scrollLeft = active.offsetLeft - box.clientWidth / 2 + active.offsetWidth / 2;
  }, [current]);

  return (
    <nav aria-label={t("knowledge.categories")} className="min-w-0 lg:sticky lg:top-24">
      <div
        ref={strip}
        className="-mx-4 flex min-w-0 gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:thin] md:-mx-6 md:px-6 lg:mx-0 lg:flex-col lg:gap-4 lg:overflow-visible lg:px-0 lg:pb-0"
      >
        {CATEGORY_GROUPS.map((group) => (
          <div key={group.id} className="contents lg:flex lg:flex-col lg:gap-0.5">
            <p className="hidden px-2.5 pb-1 text-[0.6875rem] font-semibold tracking-wide text-secondary uppercase lg:block">
              {t(`knowledge.group.${group.id}.title`)}
            </p>
            {group.categories.map((category) => {
              const selected = category === current;
              const summary = byCategory.get(category);
              const blocking = (summary?.needed.length ?? 0) > 0;
              return (
                <Link
                  key={category}
                  to={`${base}/${category}`}
                  aria-current={selected ? "page" : undefined}
                  className={`flex min-h-11 shrink-0 items-center gap-2.5 rounded-xl border px-2.5 py-1.5 text-metadata transition-colors lg:border-transparent ${FOCUS} ${
                    selected
                      ? "border-action bg-surface font-semibold text-primary lg:border-border lg:shadow-[inset_3px_0_0_var(--an-action)]"
                      : "border-border bg-surface/60 font-medium text-primary/85 hover:bg-surface hover:text-primary lg:bg-transparent lg:hover:bg-surface"
                  }`}
                >
                  <CategoryGlyph category={category} size="sm" tone={selected ? "selected" : blocking ? "attention" : "neutral"} />
                  <span className="whitespace-nowrap lg:min-w-0 lg:flex-1 lg:truncate">{t(`knowledge.category.${category}`)}</span>
                  {summary ? (
                    <span className="hidden lg:inline-flex">
                      <CategoryCounts summary={summary} variant="mark" />
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
}

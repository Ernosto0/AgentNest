import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Fact, TemplateItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ChevronRightIcon, MagnifierIcon, XIcon } from "@/components/icons";
import { FOCUS } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FactStatusChip } from "./FactStatusChip";
import { CategoryGlyph } from "./CategoryGlyph";
import { knowledgeBase } from "./useKnowledgeBase";
import { pickLabel } from "./labels";
import { CATEGORY_GROUPS, factAnchor, itemAnchor, searchKnowledge, type CategorySummary } from "./model";
import { CategoryCounts } from "./CategoryCounts";

/**
 * Every category, grouped the way an owner thinks about the business, as compact tiles with
 * real counts. A search over names and values replaces the tiles while it has a query.
 */
export function CategoryBrowser({
  summaries,
  facts,
  template,
  needed,
  className = "",
}: {
  summaries: CategorySummary[] | null;
  facts: Fact[];
  template: TemplateItem[];
  needed: Set<string> | null;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const base = knowledgeBase(workspace.id);
  const searchId = useId();
  const [query, setQuery] = useState("");
  const hits = query.trim() ? searchKnowledge(query, facts, template, needed, i18n.language, (c) => t(`knowledge.category.${c}`)) : null;
  const byCategory = new Map(summaries?.map((s) => [s.category, s]));

  return (
    <section aria-labelledby="knowledge-categories-title" className={`flex min-w-0 flex-col gap-4 ${className}`}>
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h2 id="knowledge-categories-title" className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {t("knowledge.categories")}
          </h2>
          <p className="text-metadata text-secondary">{t("knowledge.browse.hint")}</p>
        </div>
        <div role="search" className="relative min-w-0 sm:w-72">
          <label htmlFor={searchId} className="sr-only">
            {t("knowledge.browse.searchLabel")}
          </label>
          <MagnifierIcon aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-base text-secondary" />
          <input
            id={searchId}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setQuery("");
            }}
            placeholder={t("knowledge.browse.search")}
            className={`min-h-11 w-full rounded-xl border border-border bg-surface pr-3 pl-9 text-body text-primary placeholder:text-secondary/80 transition-colors hover:border-control/40 ${FOCUS}`}
          />
        </div>
      </div>

      {hits ? (
        <SearchResults query={query} hits={hits} base={base} onClear={() => setQuery("")} />
      ) : summaries === null ? (
        <div role="status" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-2">
          <span className="sr-only">{t("common.loading")}</span>
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} aria-hidden="true" className="h-[4.5rem] rounded-2xl border border-border bg-surface motion-safe:animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="flex min-w-0 flex-col gap-5">
          {CATEGORY_GROUPS.map((group) => (
            <section key={group.id} aria-labelledby={`knowledge-group-${group.id}`} className="flex min-w-0 flex-col gap-2">
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                <h3 id={`knowledge-group-${group.id}`} className="text-xs font-semibold tracking-wide text-secondary uppercase">
                  {t(`knowledge.group.${group.id}.title`)}
                </h3>
                <p className="text-xs text-secondary/80">{t(`knowledge.group.${group.id}.hint`)}</p>
              </div>
              <ul aria-label={t(`knowledge.group.${group.id}.title`)} className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-2">
                {group.categories.map((category) => {
                  const summary = byCategory.get(category);
                  if (!summary) return null;
                  return (
                    <li key={category} className="flex min-w-0">
                      <CategoryTile summary={summary} to={`${base}/${category}`} />
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

function CategoryTile({ summary, to }: { summary: CategorySummary; to: string }) {
  const { t } = useTranslation();
  const blocking = summary.needed.length > 0;
  return (
    <Link
      to={to}
      data-category={summary.category}
      className={`group flex min-h-[4.5rem] w-full min-w-0 items-center gap-3 rounded-2xl border bg-surface px-3.5 py-3 transition-colors duration-150 hover:bg-surface-subtle/50 ${FOCUS} ${
        blocking ? "border-attention/45 hover:border-attention/70" : "border-border hover:border-action/35"
      }`}
    >
      <CategoryGlyph category={summary.category} tone={blocking ? "attention" : "neutral"} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-body leading-5 font-semibold text-primary transition-colors group-hover:text-action">
          {t(`knowledge.category.${summary.category}`)}
        </span>
        <CategoryCounts summary={summary} />
      </span>
      <ChevronRightIcon aria-hidden="true" className="shrink-0 text-lg text-secondary/50 transition-all group-hover:translate-x-0.5 group-hover:text-primary" />
    </Link>
  );
}

function SearchResults({
  query,
  hits,
  base,
  onClear,
}: {
  query: string;
  hits: ReturnType<typeof searchKnowledge>;
  base: string;
  onClear: () => void;
}) {
  const { t, i18n } = useTranslation();
  if (hits.length === 0) {
    return (
      <div data-testid="knowledge-search-empty" className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border px-5 py-10 text-center">
        <p role="status" className="font-heading text-base font-semibold text-primary">
          {t("knowledge.browse.noResults", { query: query.trim() })}
        </p>
        <p className="max-w-sm text-metadata text-secondary">{t("knowledge.browse.noResultsHint")}</p>
        <Button variant="secondary" onClick={onClear}>
          <XIcon className="text-base" />
          {t("knowledge.browse.clear")}
        </Button>
      </div>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p role="status" className="text-xs text-secondary">
        {t("knowledge.browse.results", { count: hits.length })}
      </p>
      <ul data-testid="knowledge-search-results" className="min-w-0 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
        {hits.map((hit) => {
          const category = hit.kind === "fact" ? hit.fact.category : hit.item.category;
          const label = pickLabel(hit.kind === "fact" ? hit.fact.label : hit.item.label, i18n.language);
          const anchor = hit.kind === "fact" ? factAnchor(hit.fact.key) : itemAnchor(hit.item.identifier);
          return (
            <li key={hit.kind === "fact" ? hit.fact.id : hit.item.identifier}>
              <Link
                to={`${base}/${category}#${anchor}`}
                className={`group flex min-w-0 items-start gap-3 px-4 py-3 transition-colors hover:bg-surface-subtle/60 ${FOCUS} focus-visible:-outline-offset-2`}
              >
                <CategoryGlyph category={category} size="sm" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="min-w-0 text-body leading-5 font-semibold [overflow-wrap:anywhere] text-primary group-hover:text-action">{label}</span>
                    <FactStatusChip state={hit.kind === "fact" ? hit.fact.state : "not_added"} quiet={hit.kind === "fact" && hit.fact.state === "verified"} />
                  </span>
                  <span className="line-clamp-2 text-metadata [overflow-wrap:anywhere] whitespace-pre-line text-secondary">
                    {hit.kind === "fact" ? hit.fact.display : pickLabel(hit.item.description, i18n.language)}
                  </span>
                  <span className="text-xs text-secondary/80">{t(`knowledge.category.${category}`)}</span>
                </span>
                <ChevronRightIcon aria-hidden="true" className="mt-1 shrink-0 text-lg text-secondary/50 group-hover:text-primary" />
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

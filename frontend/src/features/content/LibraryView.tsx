import { useId, useState, type ComponentType, type KeyboardEvent, type ReactNode, type SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem, ContentTab, ContentType } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  AlertIcon,
  CalendarIcon,
  CheckIcon,
  MagnifierIcon,
  PencilIcon,
  SparkIcon,
  XIcon,
} from "@/components/icons";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { byScheduledTime, friendlyMoment } from "./agenda";
import { ContentCard, ContentCardSkeleton } from "./ContentCard";
import { LIST_LIMIT, useContentItems } from "./hooks";
import { tabItems, textPreview } from "./presentation";
import { CONTENT_TABS } from "./status";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;
const TAB_ICON: Record<ContentTab, Icon> = {
  drafts: PencilIcon,
  scheduled: CalendarIcon,
  published: CheckIcon,
  problems: AlertIcon,
};

/** One tab's list as the status tiles see it: the items, or why they are not there. */
export interface TabList {
  items: ContentItem[] | undefined;
  /** The server returned a full page: the tab may hold more than is listed. */
  capped: boolean;
  isError: boolean;
}

type Format = "all" | ContentType;

/**
 * The library: one tile per status tab (what there is, and what needs a look), then the open
 * tab's items as visual cards with a search and a format filter over the loaded page.
 */
export function LibraryView({
  tab,
  onTab,
  lists,
  onWrite,
}: {
  tab: ContentTab;
  onTab: (tab: ContentTab) => void;
  lists: Record<ContentTab, TabList>;
  /** Moves the owner to the composer (empty states point there instead of opening a second entry). */
  onWrite: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  // The open tab refreshes quickly; the others only feed the tiles.
  const active = useContentItems(workspace.id, tab);
  const visible = tabItems(active.data, tab);
  const accounts = useSocialAccounts(workspace.id);
  const panelId = useId();
  const searchId = useId();

  const [format, setFormat] = useState<Format>("all");
  const [query, setQuery] = useState("");
  const needle = query.trim().toLocaleLowerCase(i18n.language);
  const filtered = visible?.filter((item) => {
    if (format !== "all" && item.content_type !== format) return false;
    if (needle === "") return true;
    return `${item.title} ${textPreview(item)}`.toLocaleLowerCase(i18n.language).includes(needle);
  });
  const filtering = format !== "all" || needle !== "";
  const clearFilters = () => {
    setFormat("all");
    setQuery("");
  };

  // The account is only worth a line on each card when there is more than one to tell apart.
  const usernames = new Map((accounts.data ?? []).map((account) => [account.id, account.username ?? account.id]));
  const showAccounts = usernames.size > 1;
  const allEmpty = CONTENT_TABS.every((name) => lists[name].items?.length === 0);
  const capped = (active.data?.length ?? 0) >= LIST_LIMIT;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <StatusTiles tab={tab} onTab={onTab} lists={lists} panelId={panelId} />

      <section
        id={panelId}
        role="tabpanel"
        aria-labelledby={`content-tab-${tab}`}
        data-testid="content-library"
        className="flex min-w-0 flex-col gap-4"
      >
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <h2 className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
              {t(`content.tabs.${tab}`)}
            </h2>
            <p className="text-metadata text-secondary">{t(`content.tabHelp.${tab}`)}</p>
          </div>
          {visible && visible.length > 0 ? (
            <div role="group" aria-label={t("content.filters.label")} className="flex min-w-0 flex-wrap items-center gap-2">
              <div className="relative min-w-0 flex-1 basis-52 lg:w-64 lg:flex-none">
                <label htmlFor={searchId} className="sr-only">
                  {t("content.filters.searchLabel")}
                </label>
                <MagnifierIcon aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-base text-secondary" />
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t("content.filters.search")}
                  className={`min-h-11 w-full rounded-xl border border-border bg-surface pr-3 pl-9 text-body text-primary placeholder:text-secondary/80 transition-colors hover:border-control/40 ${FOCUS}`}
                />
              </div>
              <Segmented
                label={t("content.filters.format")}
                value={format}
                onChange={setFormat}
                options={[
                  { value: "all", label: t("content.filters.all") },
                  { value: "feed_image", label: t("content.filters.posts") },
                  { value: "story_image", label: t("content.filters.stories") },
                ]}
              />
            </div>
          ) : null}
        </div>

        {active.isError ? <ErrorMessage error={active.error} /> : null}

        {active.isPending ? (
          <div role="status" className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-[repeat(auto-fill,minmax(12rem,1fr))]">
            <span className="sr-only">{t("common.loading")}</span>
            {Array.from({ length: 4 }, (_, index) => (
              <ContentCardSkeleton key={index} />
            ))}
          </div>
        ) : null}

        {visible && visible.length === 0 ? (
          allEmpty && tab === "drafts" ? (
            <GettingStarted onWrite={onWrite} />
          ) : (
            <TabEmpty tab={tab} lists={lists} onTab={onTab} onWrite={onWrite} />
          )
        ) : null}

        {filtered && visible && visible.length > 0 && filtered.length === 0 ? (
          <div
            data-testid="content-filter-empty"
            className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border px-5 py-10 text-center"
          >
            <p className="font-heading text-base font-semibold text-primary">{t("content.filters.noMatch")}</p>
            <p className="max-w-sm text-metadata text-secondary">{t("content.filters.noMatchHint")}</p>
            <Button variant="secondary" onClick={clearFilters}>
              <XIcon className="text-base" />
              {t("content.filters.clear")}
            </Button>
          </div>
        ) : null}

        {filtered && filtered.length > 0 ? (
          <>
            {filtering ? (
              <p role="status" className="-mt-1 text-xs text-secondary">
                {t("content.filters.showing", { shown: filtered.length, total: visible?.length ?? 0 })}
              </p>
            ) : null}
            <ul
              aria-label={t(`content.tabs.${tab}`)}
              className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-[repeat(auto-fill,minmax(12rem,1fr))]"
            >
              {filtered.map((item) => (
                <li key={item.id} className="min-w-0">
                  <ContentCard
                    item={item}
                    showAccount={showAccounts && item.social_account_id ? usernames.get(item.social_account_id) : null}
                  />
                </li>
              ))}
            </ul>
            {capped ? (
              <p className="text-center text-xs text-secondary">
                {t(tab === "scheduled" ? "content.capped.earliest" : "content.capped.recent", { count: LIST_LIMIT })}
              </p>
            ) : null}
          </>
        ) : null}
      </section>
    </div>
  );
}

/** The four status tabs as tiles: a count and one line on what is there or what is next. */
function StatusTiles({
  tab,
  onTab,
  lists,
  panelId,
}: {
  tab: ContentTab;
  onTab: (tab: ContentTab) => void;
  lists: Record<ContentTab, TabList>;
  panelId: string;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const when = (at: string, withTime = true) => friendlyMoment(at, workspace.timezone, i18n.language, t, { withTime });

  const hint = (name: ContentTab): string => {
    const list = lists[name];
    if (list.isError && !list.items) return t("content.tiles.countUnknown");
    const items = list.items;
    if (!items) return "";
    if (name === "drafts") {
      const pending = items.filter((item) => item.status === "pending_approval").length;
      if (pending > 0) return t("content.tiles.draftsPending", { count: pending });
      return items.length > 0 ? t("content.tiles.draftsActive") : t("content.tiles.draftsNone");
    }
    if (name === "scheduled") {
      const next = byScheduledTime(items).find((item) => item.scheduled_at !== null);
      return next?.scheduled_at ? t("content.tiles.scheduledNext", { when: when(next.scheduled_at) }) : t("content.tiles.scheduledNone");
    }
    if (name === "published") {
      const latest = items.find((item) => item.published_at !== null);
      return latest?.published_at ? t("content.tiles.publishedLast", { when: when(latest.published_at, false) }) : t("content.tiles.publishedNone");
    }
    return items.length > 0 ? t("content.tiles.problemsSome") : t("content.tiles.problemsNone");
  };

  const focusTab = (name: ContentTab) => {
    onTab(name);
    document.getElementById(`content-tab-${name}`)?.focus();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = CONTENT_TABS.indexOf(tab);
    const target =
      event.key === "ArrowRight" || event.key === "ArrowDown"
        ? CONTENT_TABS[(index + 1) % CONTENT_TABS.length]
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? CONTENT_TABS[(index - 1 + CONTENT_TABS.length) % CONTENT_TABS.length]
          : event.key === "Home"
            ? CONTENT_TABS[0]
            : event.key === "End"
              ? CONTENT_TABS.at(-1)
              : undefined;
    if (!target) return;
    event.preventDefault();
    focusTab(target);
  };

  return (
    <div
      role="tablist"
      aria-label={t("content.tabsLabel")}
      onKeyDown={onKeyDown}
      className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4"
    >
      {CONTENT_TABS.map((name) => {
        const selected = tab === name;
        const list = lists[name];
        const count = list.items?.length;
        const shown = count === undefined ? "–" : list.capped ? `${LIST_LIMIT}+` : String(count);
        const alarming = name === "problems" && (count ?? 0) > 0;
        const Icon = TAB_ICON[name];
        return (
          <button
            key={name}
            id={`content-tab-${name}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={panelId}
            aria-describedby={`content-tab-${name}-count content-tab-${name}-hint`}
            tabIndex={selected ? 0 : -1}
            data-testid={`content-tile-${name}`}
            onClick={() => onTab(name)}
            className={`group relative flex min-h-[4.5rem] min-w-0 items-center gap-3 rounded-2xl border px-3 py-3 text-left transition-colors duration-150 sm:px-4 ${FOCUS} ${
              selected
                ? "border-action bg-surface shadow-[inset_0_0_0_1px_var(--an-action)]"
                : "border-border bg-surface/60 hover:border-action/30 hover:bg-surface"
            }`}
          >
            <span
              aria-hidden="true"
              className={`hidden size-9 shrink-0 items-center justify-center rounded-lg text-base transition-colors sm:flex ${
                alarming
                  ? "bg-attention-subtle text-attention"
                  : selected
                    ? "bg-action text-on-action"
                    : "bg-surface-subtle text-action"
              }`}
            >
              <Icon />
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className={`truncate text-body leading-5 font-semibold ${selected ? "text-primary" : "text-primary/90"}`}>
                {t(`content.tabs.${name}`)}
              </span>
              <span
                id={`content-tab-${name}-hint`}
                aria-hidden="true"
                className={`line-clamp-2 text-xs leading-4 sm:truncate sm:leading-5 ${alarming ? "font-medium text-attention" : "text-secondary"}`}
              >
                {hint(name)}
              </span>
            </span>
            <span
              id={`content-tab-${name}-count`}
              aria-hidden="true"
              className={`shrink-0 self-start font-heading text-xl leading-none font-bold tabular-nums sm:self-center ${
                alarming ? "text-attention" : count === 0 ? "text-secondary/60" : "text-primary"
              }`}
            >
              {shown}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** A small set of mutually exclusive choices; `aria-pressed` marks the chosen one. */
function Segmented<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-xl border border-border bg-surface-subtle/70 p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`min-h-11 rounded-lg px-3 text-metadata font-semibold transition-colors md:min-h-9 ${FOCUS} ${
            value === option.value ? "bg-surface text-primary shadow-xs ring-1 ring-border" : "text-secondary hover:text-primary"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

const EMPTY_ICON: Record<ContentTab, Icon> = {
  drafts: PencilIcon,
  scheduled: CalendarIcon,
  published: SparkIcon,
  problems: CheckIcon,
};

/** Each tab's own empty state, with the next step that actually exists from here. */
function TabEmpty({
  tab,
  lists,
  onTab,
  onWrite,
}: {
  tab: ContentTab;
  lists: Record<ContentTab, TabList>;
  onTab: (tab: ContentTab) => void;
  onWrite: () => void;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const has = (name: ContentTab) => (lists[name].items?.length ?? 0) > 0;
  const Icon = EMPTY_ICON[tab];
  const calm = tab === "problems";

  let action: ReactNode = null;
  if (tab === "drafts") {
    action = (
      <Button onClick={onWrite}>
        <SparkIcon className="text-base" />
        {t("content.emptyAction.write")}
      </Button>
    );
  } else if (tab === "scheduled") {
    action = has("drafts") ? (
      <Button variant="secondary" onClick={() => onTab("drafts")}>
        <PencilIcon className="text-base" />
        {t("content.emptyAction.drafts")}
      </Button>
    ) : (
      <Button onClick={onWrite}>
        <SparkIcon className="text-base" />
        {t("content.emptyAction.write")}
      </Button>
    );
  } else if (tab === "published" && has("scheduled")) {
    action = (
      <Link
        to={`/w/${workspace.id}/content?view=agenda`}
        className={`inline-flex min-h-11 items-center gap-2 rounded-control border border-border bg-surface px-4 text-body font-medium text-primary transition-colors hover:bg-surface-subtle ${FOCUS}`}
      >
        <CalendarIcon aria-hidden="true" className="text-base" />
        {t("content.emptyAction.agenda")}
      </Link>
    );
  }

  return (
    <div
      data-testid={`content-empty-${tab}`}
      className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-surface px-5 py-10 text-center sm:py-12"
    >
      <span
        aria-hidden="true"
        className={`flex size-12 items-center justify-center rounded-2xl text-xl ${
          calm ? "bg-success-subtle text-success" : "bg-assistant text-action"
        }`}
      >
        <Icon />
      </span>
      <div className="flex max-w-md flex-col gap-1">
        <p className="font-heading text-base font-semibold text-primary">{t(`content.empty.${tab}`)}</p>
        <p className="text-metadata text-secondary">{t(`content.emptyHint.${tab}`)}</p>
      </div>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

/** A library with nothing in it yet: how content moves here, and where to begin. */
function GettingStarted({ onWrite }: { onWrite: () => void }) {
  const { t } = useTranslation();
  const steps: { icon: Icon; title: string; text: string }[] = [
    { icon: SparkIcon, title: t("content.onboarding.step1Title"), text: t("content.onboarding.step1") },
    { icon: CalendarIcon, title: t("content.onboarding.step2Title"), text: t("content.onboarding.step2") },
    { icon: CheckIcon, title: t("content.onboarding.step3Title"), text: t("content.onboarding.step3") },
  ];
  return (
    <div data-testid="content-empty-drafts" className="flex flex-col gap-5 rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <div className="flex flex-col gap-1">
        <p className="font-heading text-lg leading-snug font-semibold tracking-tight text-primary">{t("content.onboarding.title")}</p>
        <p className="max-w-prose text-metadata text-secondary">{t("content.onboarding.intro")}</p>
      </div>
      <ol className="grid gap-3 sm:grid-cols-3">
        {steps.map((step, index) => (
          <li key={step.title} className="flex min-w-0 gap-3 rounded-xl bg-surface-subtle/70 p-4 sm:flex-col sm:gap-3">
            <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface text-base text-action ring-1 ring-border">
              <step.icon />
            </span>
            <div className="min-w-0">
              <p className="text-body font-semibold text-primary">
                <span className="text-secondary tabular-nums">{index + 1}. </span>
                {step.title}
              </p>
              <p className="text-metadata text-secondary">{step.text}</p>
            </div>
          </li>
        ))}
      </ol>
      <div>
        <Button onClick={onWrite}>
          <SparkIcon className="text-base" />
          {t("content.emptyAction.write")}
        </Button>
      </div>
    </div>
  );
}

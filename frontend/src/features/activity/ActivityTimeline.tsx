import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ActivityEntry, ActivityLevel } from "@/api/types";
import { ChevronDownIcon, LayersIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { FOCUS } from "@/features/home/DashboardPanel";
import { dayLabel, shiftDay } from "@/features/reports/dates";
import { ICONS, LEVEL_DOT, LEVEL_PILL, LEVEL_TILE, entryIconKey, fullTimeOf, timeOf } from "./presentation";
import type { DaySection, TimelineItem } from "./timeline";

interface Clock {
  timezone: string;
  today: string;
}

/** The feed: one section per local day, rows newest first, repeated runs folded into groups. */
export function ActivityTimeline({
  sections,
  clock,
  onShowFlow,
}: {
  sections: DaySection[];
  clock: Clock;
  onShowFlow: ((id: string) => void) | null;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-6" data-testid="activity-timeline">
      {sections.map((section) => (
        <DayBlock key={section.day} section={section} clock={clock} onShowFlow={onShowFlow} />
      ))}
    </div>
  );
}

function DayBlock({ section, clock, onShowFlow }: { section: DaySection; clock: Clock; onShowFlow: ((id: string) => void) | null }) {
  const { t, i18n } = useTranslation();
  const headingId = useId();
  const label =
    section.day === clock.today
      ? t("activity.today")
      : section.day === shiftDay(clock.today, -1)
        ? t("activity.yesterday")
        : dayLabel(section.day, i18n.language);
  const count = section.openEnded
    ? t("activity.dayCountMore", { count: section.count })
    : t("activity.dayCount", { count: section.count });
  return (
    <section aria-labelledby={headingId} className="grid min-w-0 gap-2.5 lg:grid-cols-[9.5rem_minmax(0,1fr)] lg:gap-6">
      <div className="flex items-baseline justify-between gap-3 lg:sticky lg:top-24 lg:flex-col lg:justify-start lg:gap-0.5 lg:self-start lg:pt-3.5">
        <h2 id={headingId} className="font-heading text-sm font-semibold tracking-tight text-primary">
          {label}
        </h2>
        <p className="text-xs text-secondary tabular-nums">{count}</p>
      </div>
      <ul className="min-w-0 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
        {section.items.map((item) => (
          <li key={item.kind === "entry" ? item.entry.id : item.key} className="min-w-0">
            <Item item={item} clock={clock} onShowFlow={onShowFlow} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Item({ item, clock, onShowFlow }: { item: TimelineItem; clock: Clock; onShowFlow: ((id: string) => void) | null }) {
  return item.kind === "entry" ? (
    <EntryRow entry={item.entry} clock={clock} onShowFlow={onShowFlow} />
  ) : (
    <GroupRow entries={item.entries} level={item.level} openEnded={item.openEnded} clock={clock} onShowFlow={onShowFlow} />
  );
}

function IconTile({ entry, level, stacked = false }: { entry: ActivityEntry; level: ActivityLevel; stacked?: boolean }) {
  const Icon = ICONS[entryIconKey(entry)];
  return (
    <span aria-hidden="true" className="relative mt-0.5 flex size-8 shrink-0">
      {stacked ? <span className={`absolute inset-0 translate-x-1 -translate-y-1 rounded-lg opacity-50 ${LEVEL_TILE[level]}`} /> : null}
      <span className={`relative flex size-8 items-center justify-center rounded-lg text-base ring-2 ring-surface ${LEVEL_TILE[level]}`}>
        <Icon />
      </span>
    </span>
  );
}

function LevelPill({ level }: { level: ActivityLevel }) {
  const { t } = useTranslation();
  const tone = LEVEL_PILL[level];
  if (!tone) return null;
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-px text-xs leading-5 font-semibold ring-1 ring-inset ${tone}`}>
      {t(`activity.level.${level}`)}
    </span>
  );
}

function ResourceLink({ entry }: { entry: ActivityEntry }) {
  const { resource } = entry;
  if (!resource) return null;
  return resource.link ? (
    <Link to={resource.link} className={`min-w-0 font-medium break-words text-action underline-offset-2 hover:text-action-hover hover:underline ${FOCUS}`}>
      {resource.label}
    </Link>
  ) : (
    <span className="min-w-0 break-words text-primary/80">{resource.label}</span>
  );
}

/** One audit entry: what happened, about what, by whom and when; details on request. */
function EntryRow({
  entry,
  clock,
  onShowFlow,
  nested = false,
}: {
  entry: ActivityEntry;
  clock: Clock;
  onShowFlow: ((id: string) => void) | null;
  nested?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div
      data-testid="activity-entry"
      data-level={entry.level}
      className={`flex min-w-0 gap-3 transition-colors ${nested ? "py-2.5 pr-3 pl-3" : "px-4 py-3 sm:px-5"} ${open ? "bg-surface-subtle/50" : "hover:bg-surface-subtle/40"}`}
    >
      {nested ? (
        <span aria-hidden="true" className={`mt-2 size-2 shrink-0 rounded-full ${LEVEL_DOT[entry.level]}`} />
      ) : (
        <IconTile entry={entry} level={entry.level} />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className={`group/row -mx-1 flex min-h-8 min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-1 rounded-control px-1 text-left ${FOCUS}`}
        >
          <span className={`min-w-0 flex-1 basis-40 break-words text-primary ${nested ? "text-metadata" : "text-body font-semibold"} ${entry.routine ? "font-medium text-primary/85" : ""}`}>
            {entry.text}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-2 pt-0.5">
            <LevelPill level={entry.level} />
            <time dateTime={entry.occurred_at} className="text-xs text-secondary tabular-nums">
              {timeOf(entry.occurred_at, i18n.language, clock.timezone)}
            </time>
            <ChevronDownIcon className={`text-base text-secondary transition-transform group-hover/row:text-primary motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
            <span className="sr-only">{open ? t("activity.hideDetails") : t("activity.showDetails")}</span>
          </span>
        </button>
        <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-metadata text-secondary">
          <ResourceLink entry={entry} />
          {entry.resource && entry.resource.label !== entry.actor.label ? (
            <>
              <span aria-hidden="true">·</span>
              <span className="min-w-0 break-words">{entry.actor.label}</span>
            </>
          ) : entry.resource ? null : (
            <span className="min-w-0 break-words">{entry.actor.label}</span>
          )}
          {entry.routine ? (
            <span className="rounded-full bg-surface-subtle px-1.5 text-[11px] leading-4 font-semibold text-secondary">{t("activity.routineTag")}</span>
          ) : null}
          {entry.is_simulated ? <SimulatedBadge compact /> : null}
        </div>
        {open ? <EntryDetails id={panelId} entry={entry} clock={clock} onShowFlow={onShowFlow} /> : <div id={panelId} hidden />}
      </div>
    </div>
  );
}

function Fact({ term, children, wide = false }: { term: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 ${wide ? "sm:col-span-2" : ""}`}>
      <dt className="text-xs font-semibold text-secondary">{term}</dt>
      <dd className="min-w-0 text-metadata break-words text-primary">{children}</dd>
    </div>
  );
}

function EntryDetails({ id, entry, clock, onShowFlow }: { id: string; entry: ActivityEntry; clock: Clock; onShowFlow: ((id: string) => void) | null }) {
  const { t, i18n } = useTranslation();
  const flow = entry.correlation_id;
  return (
    <div id={id} className="mt-2 rounded-xl border border-border bg-surface px-4 py-3" data-testid="activity-entry-details">
      <dl className="grid min-w-0 gap-x-6 gap-y-3 sm:grid-cols-2">
        <Fact term={t("activity.details.when")} wide>
          {fullTimeOf(entry.occurred_at, i18n.language, clock.timezone)}
          <span className="text-secondary"> · {clock.timezone}</span>
        </Fact>
        <Fact term={t("activity.details.by")}>
          {entry.actor.label}
          <span className="text-secondary"> · {t(`activity.actorType.${entry.actor.type}`)}</span>
        </Fact>
        <Fact term={t("activity.details.category")}>
          {t(`activity.groups.${entry.group}`, { defaultValue: t("activity.groups.system") })}
        </Fact>
        <Fact term={t("activity.details.outcome")}>{t(`activity.level.${entry.level}`)}</Fact>
        {entry.resource ? (
          <Fact term={t("activity.details.record")}>
            <ResourceLink entry={entry} />
          </Fact>
        ) : null}
        {entry.details.map((detail) => (
          <Fact key={detail.key} term={detail.label}>
            {detail.value}
          </Fact>
        ))}
        {entry.routine ? (
          <Fact term={t("activity.details.routine")} wide>
            {t("activity.details.routineHint")}
          </Fact>
        ) : null}
        {entry.is_simulated ? (
          <Fact term={t("activity.details.simulated")} wide>
            {t("activity.details.simulatedHint")}
          </Fact>
        ) : null}
        <Fact term={t("activity.details.reference")} wide>
          <code className="font-mono text-xs break-all text-secondary">{entry.id}</code>
          <span className="text-secondary"> · {entry.action}</span>
        </Fact>
      </dl>
      {flow && onShowFlow ? (
        <button
          type="button"
          onClick={() => onShowFlow(flow)}
          className={`mt-3 inline-flex min-h-10 items-center gap-1.5 rounded-control border border-border px-3 text-metadata font-semibold text-action hover:border-action/40 hover:bg-surface-subtle ${FOCUS}`}
        >
          <LayersIcon className="text-base" />
          {t("activity.details.showFlow")}
        </button>
      ) : null}
    </div>
  );
}

/** Adjacent entries the server marked as the same kind of thing, folded into one row. */
function GroupRow({
  entries,
  level,
  openEnded,
  clock,
  onShowFlow,
}: {
  entries: ActivityEntry[];
  level: ActivityLevel;
  openEnded: boolean;
  clock: Clock;
  onShowFlow: ((id: string) => void) | null;
}) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const newest = entries[0]!;
  const oldest = entries[entries.length - 1]!;
  const count = openEnded ? t("activity.group.countMore", { count: entries.length }) : t("activity.group.count", { count: entries.length });
  const problems = entries.filter((e) => e.level === "failure" || e.level === "warning").length;
  const simulated = entries.some((e) => e.is_simulated);
  return (
    <div data-testid="activity-group" data-level={level} className={`min-w-0 ${open ? "bg-surface-subtle/50" : ""}`}>
      <div className={`flex min-w-0 gap-3 px-4 py-3 sm:px-5 ${open ? "" : "hover:bg-surface-subtle/40"}`}>
        <IconTile entry={newest} level={level} stacked />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
            className={`group/row -mx-1 flex min-h-8 min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-1 rounded-control px-1 text-left ${FOCUS}`}
          >
            <span className="min-w-0 flex-1 basis-40 text-body font-semibold break-words text-primary">
              {newest.text}
              <span className="ml-2 inline-flex translate-y-[-1px] items-center rounded-full bg-surface-subtle px-2 align-middle text-xs leading-5 font-semibold text-secondary ring-1 ring-border ring-inset">
                {count}
              </span>
            </span>
            <span className="ml-auto flex shrink-0 items-center gap-2 pt-0.5">
              <LevelPill level={level} />
              <span className="text-xs text-secondary tabular-nums">
                {timeOf(oldest.occurred_at, i18n.language, clock.timezone)}–{timeOf(newest.occurred_at, i18n.language, clock.timezone)}
              </span>
              <ChevronDownIcon className={`text-base text-secondary transition-transform group-hover/row:text-primary motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
              <span className="sr-only">{open ? t("activity.group.hide") : t("activity.group.show")}</span>
            </span>
          </button>
          <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-metadata text-secondary">
            <span className="inline-flex items-center gap-1 font-medium">
              <LayersIcon className="text-sm" />
              {t("activity.group.grouped")}
            </span>
            {newest.resource ? (
              <>
                <span aria-hidden="true">·</span>
                <ResourceLink entry={newest} />
              </>
            ) : null}
            <span aria-hidden="true">·</span>
            <span>{newest.actor.label}</span>
            {problems > 0 && problems < entries.length ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-medium text-danger">{t("activity.group.problems", { count: problems })}</span>
              </>
            ) : null}
            {simulated ? <SimulatedBadge compact /> : null}
          </div>
        </div>
      </div>
      {open ? (
        <ul id={panelId} aria-label={count} className="mr-4 mb-3 ml-[3.25rem] divide-y divide-border rounded-xl border border-border bg-surface sm:mr-5 sm:ml-[3.75rem]">
          {entries.map((entry) => (
            <li key={entry.id} className="min-w-0">
              <EntryRow entry={entry} clock={clock} onShowFlow={onShowFlow} nested />
            </li>
          ))}
        </ul>
      ) : (
        <div id={panelId} hidden />
      )}
    </div>
  );
}

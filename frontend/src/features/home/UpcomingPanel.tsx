import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CalendarIcon, ImageIcon, PlusIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import type { NewContentMode } from "@/features/content/GenerateSheet";
import { useMediaPreview } from "@/features/content/hooks";
import { shiftDay, todayIn } from "@/features/reports/dates";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, Panel, PanelHeading, PanelLink, SkeletonRows } from "./DashboardPanel";
import { SCHEDULED_WEEK_LIMIT, useScheduledWeek } from "./hooks";
import { WeekCalendar } from "./WeekCalendar";

const NEXT_SHOWN = 4;

export type CreateContent = (mode: NewContentMode, type?: "feed_image" | "story_image") => void;

/**
 * Upcoming content: the week at a glance and the next scheduled items as visual cards.
 * The cards are a capped preview of the scheduled list, never a total.
 */
export function UpcomingPanel({ onCreate, className = "" }: { onCreate: CreateContent; className?: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const week = useScheduledWeek(workspace.id, workspace.timezone);
  const posts = week.days.reduce((sum, day) => sum + day.posts.length, 0);
  const stories = week.days.reduce((sum, day) => sum + day.stories.length, 0);
  // The scheduled list is fetched with a limit; a full page means the week may hold more.
  const capped = week.items.length >= SCHEDULED_WEEK_LIMIT;
  const next = week.items.slice(0, NEXT_SHOWN);
  const draftStory = () => onCreate("blank", "story_image");

  return (
    <Panel aria-labelledby="home-upcoming-title" data-testid="home-upcoming" className={`gap-5 ${className}`}>
      <PanelHeading
        id="home-upcoming-title"
        icon={<CalendarIcon />}
        title={t("home.upNext.title")}
        meta={
          week.isSuccess ? (
            <span data-testid="week-summary">
              {t("home.upNext.weekSummary", {
                posts: capped ? `${posts}+` : posts,
                stories: capped ? `${stories}+` : stories,
              })}
            </span>
          ) : undefined
        }
        action={<PanelLink to={`/w/${workspace.id}/content?view=agenda`}>{t("home.week.viewDay")}</PanelLink>}
      />

      {week.error ? <ErrorMessage error={week.error} /> : null}
      {week.isPending ? <SkeletonRows label={t("common.loading")} rows={2} /> : null}

      {week.isSuccess ? (
        <>
          <WeekCalendar days={week.days} onDraftStory={draftStory} />

          {next.length === 0 ? (
            <div
              data-testid="upcoming-empty"
              className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border border-dashed border-border px-4 py-4"
            >
              <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-subtle text-xl text-action">
                <ImageIcon />
              </span>
              <div className="min-w-0 flex-1 basis-52">
                <p className="font-semibold text-primary">{t("home.upNext.empty")}</p>
                <p className="text-metadata text-secondary">{t("home.upcoming.emptyHint")}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => onCreate("ai")} className="px-3.5">
                  <SparkIcon />
                  {t("home.quick.generate")}
                </Button>
                <Button variant="secondary" onClick={draftStory} className="px-3.5">
                  <PlusIcon />
                  {t("home.upNext.draftStory")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-secondary">{t("home.upNext.next")}</h3>
                  <p className="text-xs text-secondary">{t("core.previewOnly")}</p>
                </div>
                <PanelLink to={`/w/${workspace.id}/content?tab=scheduled`}>{t("home.upcoming.all")}</PanelLink>
              </div>
              {/* Phones scroll sideways with snap; wider screens show the preview in one row. */}
              <ul
                data-testid="upcoming-list"
                className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pt-0.5 pb-2 md:grid md:max-w-3xl md:grid-cols-4 md:overflow-visible md:pb-0"
              >
                {next.map((item) => (
                  <UpcomingCard key={item.id} item={item} />
                ))}
              </ul>
            </div>
          )}
        </>
      ) : null}
    </Panel>
  );
}

function UpcomingCard({ item }: { item: ContentItem }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const isStory = item.content_type === "story_image";
  const aspectWarning = isStory && item.validation?.warnings?.some((w) => w.code === "STORY_ASPECT_NOT_9_16");

  let when: string | null = null;
  if (item.scheduled_at) {
    const at = new Date(item.scheduled_at);
    const today = todayIn(workspace.timezone);
    const day = todayIn(workspace.timezone, at);
    const time = at.toLocaleTimeString(i18n.language, { hour: "2-digit", minute: "2-digit", timeZone: workspace.timezone });
    const dayText =
      day === today
        ? t("home.week.today")
        : day === shiftDay(today, 1)
          ? t("home.week.tomorrow")
          : at.toLocaleDateString(i18n.language, { weekday: "short", day: "numeric", month: "short", timeZone: workspace.timezone });
    when = `${dayText} · ${time}`;
  }

  return (
    <li className="flex w-36 shrink-0 snap-start md:w-auto">
      <Link
        to={`/w/${workspace.id}/content/${item.id}`}
        className={`group flex w-full flex-col gap-2 rounded-xl ${FOCUS}`}
      >
        <div className="relative">
          <Thumbnail mediaId={item.media_asset_id} deleted={item.media_deleted} />
          <span
            className={`absolute top-2 left-2 rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold ${
              isStory ? "bg-chart-2 text-primary" : "bg-action text-on-action"
            }`}
          >
            {isStory ? t("home.upNext.typeStory") : t("home.upNext.typePost")}
          </span>
          {aspectWarning ? (
            <span
              className="absolute top-2 right-2 flex size-6 items-center justify-center rounded-full bg-attention text-xs text-on-action"
              title={t("home.upNext.aspectWarning")}
              role="img"
              aria-label={t("home.upNext.aspectWarning")}
            >
              <AlertIcon aria-hidden="true" />
            </span>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-0.5 px-0.5">
          <span className="line-clamp-2 text-body leading-snug font-semibold text-primary transition-colors group-hover:text-action">
            {item.title}
          </span>
          {when ? <span className="text-xs text-secondary">{when}</span> : null}
          {item.is_simulated ? (
            <span className="pt-0.5">
              <SimulatedBadge compact />
            </span>
          ) : null}
        </div>
      </Link>
    </li>
  );
}

/** Real media when there is some; otherwise a placeholder that says there is no image. */
function Thumbnail({ mediaId, deleted }: { mediaId: string | null; deleted?: boolean }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const preview = useMediaPreview(workspace.id, deleted ? null : mediaId);
  if (!mediaId || deleted || !preview.url) {
    return (
      <div className="flex aspect-[4/5] w-full flex-col items-center justify-center gap-1.5 rounded-xl bg-surface-subtle text-secondary transition-colors group-hover:bg-assistant">
        <ImageIcon aria-hidden="true" className="text-2xl opacity-60" />
        <span className="text-[0.6875rem] font-medium">
          {preview.isPending ? t("common.loading") : t("home.upNext.noImage")}
        </span>
      </div>
    );
  }
  return (
    <img
      src={preview.url}
      alt=""
      className="aspect-[4/5] w-full rounded-xl object-cover ring-1 ring-border transition-[filter] group-hover:brightness-95"
    />
  );
}

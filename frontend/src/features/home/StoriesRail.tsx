import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { AlertIcon, ImageIcon, PlusIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMediaPreview } from "@/features/content/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

function StoryThumbnail({
  workspaceId,
  mediaId,
  deleted,
}: {
  workspaceId: string;
  mediaId: string | null;
  deleted?: boolean;
}) {
  const preview = useMediaPreview(workspaceId, deleted ? null : mediaId);
  if (!mediaId || deleted || !preview.url) {
    return (
      <div
        className="flex aspect-[9/16] w-24 shrink-0 items-center justify-center rounded-panel bg-surface-subtle text-secondary border border-border/80"
        aria-hidden="true"
      >
        <ImageIcon className="text-xl opacity-60" />
      </div>
    );
  }

  return (
    <img
      src={preview.url}
      alt=""
      className="aspect-[9/16] w-24 shrink-0 rounded-panel object-cover border border-border/80 shadow-2xs group-hover:border-action transition-colors"
    />
  );
}

export function StoriesRail({
  stories,
  onNewStory,
}: {
  stories: ContentItem[];
  onNewStory?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();

  if (stories.length === 0) {
    return (
      <div
        data-testid="stories-rail-empty"
        className="flex items-center justify-between gap-4 rounded-panel border border-dashed border-border p-4 bg-surface-subtle/30"
      >
        <div className="flex flex-col gap-0.5">
          <p className="text-sm font-semibold text-primary">{t("home.upNext.noStories")}</p>
          <p className="text-xs text-secondary">{t("home.upNext.noStoriesHint")}</p>
        </div>
        {onNewStory ? (
          <button
            type="button"
            onClick={onNewStory}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-control border border-control bg-surface px-3 py-1.5 text-xs font-semibold text-action hover:bg-surface-subtle shrink-0"
          >
            <PlusIcon className="text-sm" />
            <span>{t("home.upNext.draftStory")}</span>
          </button>
        ) : (
          <Link
            to={`/w/${workspace.id}/content?tab=drafts`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-control border border-control bg-surface px-3 py-1.5 text-xs font-semibold text-action hover:bg-surface-subtle shrink-0"
          >
            <PlusIcon className="text-sm" />
            <span>{t("home.upNext.draftStory")}</span>
          </Link>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5" data-testid="stories-rail">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-secondary">
          {t("home.upNext.stories")}
        </h3>
        <span className="text-xs font-semibold text-secondary">
          {stories.length}
        </span>
      </div>

      <div className="flex items-start gap-3 overflow-x-auto pb-2 pt-1 scrollbar-thin">
        {stories.map((story) => {
          const hasAspectWarning = story.validation?.warnings?.some(
            (w) => w.code === "STORY_ASPECT_NOT_9_16",
          );

          const timeLabel = story.scheduled_at
            ? new Date(story.scheduled_at).toLocaleString(i18n.language, {
                weekday: "short",
                hour: "2-digit",
                minute: "2-digit",
                timeZone: workspace.timezone,
              })
            : null;

          return (
            <Link
              key={story.id}
              to={`/w/${workspace.id}/content/${story.id}`}
              className="group flex flex-col gap-1.5 shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              title={story.title}
            >
              <div className="relative">
                <StoryThumbnail
                  workspaceId={workspace.id}
                  mediaId={story.media_asset_id}
                  deleted={story.media_deleted}
                />
                {hasAspectWarning ? (
                  <span
                    className="absolute top-1.5 right-1.5 rounded-full bg-attention p-1 text-white shadow-xs"
                    title={t("home.upNext.aspectWarning")}
                    aria-label={t("home.upNext.aspectWarning")}
                  >
                    <AlertIcon className="text-xs" />
                  </span>
                ) : null}
              </div>

              <div className="flex flex-col max-w-24">
                <span className="text-xs font-medium text-primary truncate group-hover:text-action transition-colors">
                  {story.title}
                </span>
                <span className="text-[11px] text-secondary truncate">
                  {timeLabel}
                </span>
                {story.is_simulated ? (
                  <div className="pt-0.5">
                    <SimulatedBadge />
                  </div>
                ) : null}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

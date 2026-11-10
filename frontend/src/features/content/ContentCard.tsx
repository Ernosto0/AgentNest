import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { AlertIcon, CalendarIcon, CheckIcon, PencilIcon, SparkIcon, SpinnerIcon } from "@/components/icons";
import { StatusBadge } from "@/components/StatusBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { friendlyMoment } from "./agenda";
import { ContentMedia } from "./ContentMedia";
import { isGenerating } from "./hooks";
import { problemReason, textPreview } from "./presentation";
import { contentBadge } from "./status";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

/** When the item goes out, went out, or last changed: whichever the status makes meaningful. */
function whenLine(item: ContentItem, t: TFunction, language: string, timezone: string) {
  if (item.status === "published" && item.published_at) {
    return { icon: CheckIcon, text: t("content.card.publishedAt", { time: friendlyMoment(item.published_at, timezone, language, t) }) };
  }
  if (item.status === "scheduled" || item.status === "publishing" || item.status === "retry_scheduled") {
    return item.scheduled_at
      ? { icon: CalendarIcon, text: t("content.card.scheduledFor", { time: friendlyMoment(item.scheduled_at, timezone, language, t) }) }
      : null;
  }
  return { icon: PencilIcon, text: t("content.card.updatedAt", { time: friendlyMoment(item.updated_at, timezone, language, t) }) };
}

/** Post or Story, on the image. Colours follow the Today calendar (posts green, stories amber). */
export function TypePill({ type, className = "" }: { type: ContentItem["content_type"]; className?: string }) {
  const { t } = useTranslation();
  const story = type === "story_image";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.6875rem] leading-4 font-semibold ${
        story ? "bg-chart-2 text-primary" : "bg-action text-on-action"
      } ${className}`}
    >
      {t(`content.type.${type}`)}
    </span>
  );
}

/**
 * One item of the library as a visual card. The status badge is the only statement of where the
 * item stands (INV-18); the time line and the reason only explain it.
 */
export function ContentCard({ item, showAccount }: { item: ContentItem; showAccount?: string | null }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const badge = contentBadge(item, t, i18n.language, workspace.timezone);
  const when = whenLine(item, t, i18n.language, workspace.timezone);
  const text = textPreview(item);
  const reason = problemReason(item, t);
  const generating = isGenerating(item);
  const aiDraft = item.generation?.status === "succeeded";
  const WhenIcon = when?.icon;

  return (
    <Link
      to={`/w/${workspace.id}/content/${item.id}`}
      data-content-id={item.id}
      data-testid="content-card"
      className={`group flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface transition-colors duration-150 hover:border-action/35 ${FOCUS}`}
    >
      <div className="relative">
        <ContentMedia item={item} className="aspect-[4/5] w-full" />
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-2.5">
          <TypePill type={item.content_type} className="shadow-sm" />
          {aiDraft ? (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-surface/90 px-2 py-0.5 text-[0.6875rem] leading-4 font-semibold text-action shadow-sm backdrop-blur-sm"
              title={t("content.card.aiDraftHint")}
            >
              <SparkIcon aria-hidden="true" className="text-xs" />
              {t("content.card.aiDraft")}
            </span>
          ) : null}
        </div>
        {generating ? (
          <div className="absolute inset-x-2.5 bottom-2.5">
            <span
              data-testid="card-generating"
              className="flex items-center justify-center gap-1.5 rounded-full bg-surface/95 px-3 py-1.5 text-xs font-semibold text-info shadow-sm backdrop-blur-sm"
            >
              <SpinnerIcon aria-hidden="true" className="motion-safe:animate-spin" />
              <span>{t("content.card.generating")}</span>
            </span>
          </div>
        ) : null}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2 p-3 sm:p-3.5">
        <div className="flex min-w-0 flex-col gap-1">
          <h3
            data-testid="content-card-title"
            className="line-clamp-2 font-heading text-body leading-snug font-semibold break-words text-primary transition-colors group-hover:text-action"
          >
            {item.title || t("content.card.untitled")}
          </h3>
          {reason ? (
            <p className="flex min-w-0 items-start gap-1.5 text-xs leading-5 text-attention">
              <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
              <span className="line-clamp-3 break-words">{reason}</span>
            </p>
          ) : (
            <p className={`line-clamp-2 text-xs leading-5 break-words ${text ? "text-secondary" : "text-secondary/70 italic"}`}>
              {text || t("content.card.noText")}
            </p>
          )}
        </div>

        <div className="mt-auto flex min-w-0 flex-col gap-1.5 pt-1">
          <StatusBadge compact status={badge.status} params={badge.params} simulated={item.is_simulated} />
          {when && WhenIcon ? (
            <p className="flex min-w-0 items-start gap-1.5 text-xs leading-5 text-secondary">
              <WhenIcon aria-hidden="true" className="mt-1 shrink-0 opacity-70" />
              <span className="min-w-0 break-words">{when.text}</span>
            </p>
          ) : null}
          {showAccount ? <p className="truncate text-xs text-secondary">@{showAccount}</p> : null}
        </div>
      </div>
    </Link>
  );
}

/** The card's shape while the list loads, so the grid does not jump when it arrives. */
export function ContentCardSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col overflow-hidden rounded-2xl border border-border bg-surface">
      <div className="aspect-[4/5] w-full bg-surface-subtle motion-safe:animate-pulse" />
      <div className="flex flex-col gap-2 p-3.5">
        <div className="h-3 w-4/5 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
        <div className="h-2.5 w-3/5 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
        <div className="mt-2 h-5 w-20 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
      </div>
    </div>
  );
}

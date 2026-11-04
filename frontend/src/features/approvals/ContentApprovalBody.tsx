import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Approval, ContentItem } from "@/api/types";
import { ContentPreview } from "@/features/content/ContentPreview";
import { timezoneLabel } from "@/features/content/messages";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { isStaleFor } from "./format";

const LABELS = {
  media: "content.approval.media",
  caption: "content.approval.caption",
  overlay: "content.approval.overlay",
  overlayNote: "content.approval.overlayNote",
  noMedia: "content.approval.noMedia",
  noCaption: "content.approval.noCaption",
};

/**
 * Exactly what a `content.publish` approval authorises: the image, the caption (feed) or the
 * overlay text (story) and the time, read from the item at the version the approval is bound to.
 * The approval carries only ids and a title, so the text comes from the item; if the item has
 * moved on since the request, the bound text can no longer be shown and nothing is presented as
 * if it were approved. Deciding stays with the explicit buttons of the sheet.
 */
export function ContentApprovalBody({
  approval,
  item,
  loading,
  failed,
}: {
  approval: Approval;
  item: ContentItem | undefined;
  loading: boolean;
  failed: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();

  if (loading) return <p className="text-sm text-secondary">{t("common.loading")}</p>;
  if (failed || !item) {
    return (
      <p role="alert" className="rounded-control border border-danger bg-danger-subtle p-3.5 text-sm text-danger shadow-xs">
        {t("content.approval.loadFailed")}
      </p>
    );
  }

  // The time the approval is bound to (its summary); the item's own only if the summary lacks it.
  const summary = approval.summary as { scheduled_at?: unknown };
  const boundAt = typeof summary.scheduled_at === "string" ? summary.scheduled_at : item.scheduled_at;
  const when = boundAt
    ? new Date(boundAt).toLocaleString(i18n.language, {
        dateStyle: "long",
        timeStyle: "short",
        timeZone: workspace.timezone,
      })
    : null;
  const stale = isStaleFor(approval, item);

  return (
    <div
      className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-4 shadow-xs"
      data-testid="content-approval-body"
      data-stale={stale}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-heading font-semibold text-primary">{t("content.approval.heading")}</p>
        <span className="rounded-control border border-border bg-surface-subtle px-2.5 py-0.5 text-xs font-medium text-secondary">
          {t(`content.type.${item.content_type}`)} · {t("content.approval.version", { version: approval.subject.version })}
        </span>
      </div>

      <p className="text-base font-semibold text-primary break-words">{item.title}</p>

      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 text-sm rounded-control border border-border bg-surface-subtle p-3.5">
        <dt className="text-secondary font-medium">{t("content.approval.type")}</dt>
        <dd className="text-primary font-medium">
          {t(`content.type.${item.content_type}`)} · {t("content.approval.version", { version: approval.subject.version })}
        </dd>
        {when ? (
          <>
            <dt className="text-secondary font-medium">{t("content.approval.when")}</dt>
            <dd data-testid="approval-when" className="text-primary font-medium">
              {when} ({timezoneLabel(workspace.timezone, t)})
            </dd>
          </>
        ) : null}
      </dl>

      {stale ? (
        <p
          role="alert"
          data-testid="approval-stale"
          className="rounded-control border border-attention bg-attention-subtle p-3.5 text-sm text-attention shadow-xs"
        >
          {t("content.approval.stale", { current: item.version, approved: approval.subject.version })}
        </p>
      ) : (
        <div className="overflow-hidden rounded-control border border-border bg-surface p-3.5 shadow-2xs">
          <ContentPreview
            contentType={item.content_type}
            caption={item.caption}
            overlay={item.overlay_text_suggestions}
            mediaId={item.media_asset_id}
            mediaDeleted={item.media_deleted}
            labels={LABELS}
          />
        </div>
      )}

      <div>
        <Link
          to={`/w/${workspace.id}/content/${item.id}`}
          className="inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          {t("content.approval.open")}
        </Link>
      </div>
    </div>
  );
}

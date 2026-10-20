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

  if (loading) return <p className="text-sm text-slate-600">{t("common.loading")}</p>;
  if (failed || !item) {
    return (
      <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
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
    <div className="flex flex-col gap-3 rounded-lg bg-slate-50 p-3" data-testid="content-approval-body" data-stale={stale}>
      <p className="font-medium">{t("content.approval.heading")}</p>
      <p className="text-lg font-semibold break-words">{item.title}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-600">{t("content.approval.type")}</dt>
        <dd>
          {t(`content.type.${item.content_type}`)} · {t("content.approval.version", { version: approval.subject.version })}
        </dd>
        {when ? (
          <>
            <dt className="text-slate-600">{t("content.approval.when")}</dt>
            <dd data-testid="approval-when">
              {when} ({timezoneLabel(workspace.timezone, t)})
            </dd>
          </>
        ) : null}
      </dl>
      {stale ? (
        <p role="alert" data-testid="approval-stale" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-400">
          {t("content.approval.stale", { current: item.version, approved: approval.subject.version })}
        </p>
      ) : (
        <ContentPreview
          contentType={item.content_type}
          caption={item.caption}
          overlay={item.overlay_text_suggestions}
          mediaId={item.media_asset_id}
          labels={LABELS}
        />
      )}
      <Link
        to={`/w/${workspace.id}/content/${item.id}`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-indigo-800 underline"
      >
        {t("content.approval.open")}
      </Link>
    </div>
  );
}

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { timezoneLabel } from "./messages";

/** Only an http(s) link is ever an href (the permalink comes from the provider). */
function safeUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/**
 * The plain-language line under the status badge: when it goes out, who has to approve it, why
 * it was turned down or sent back, the link to the post once it is out. Every sentence follows
 * the item's own status (INV-18): "published" appears only for a `published` item.
 */
export function ContentStatusPanel({ item }: { item: ContentItem }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const zone = timezoneLabel(workspace.timezone, t);
  const local = (value: string) =>
    new Date(value).toLocaleString(i18n.language, {
      dateStyle: "long",
      timeStyle: "short",
      timeZone: workspace.timezone,
    });
  const lines: ReactNode[] = [];

  switch (item.status) {
    case "pending_approval":
      if (item.approval) {
        lines.push(
          <p key="pending">
            {t("content.detail.pending", {
              time: new Date(item.approval.expires_at).toLocaleString(i18n.language, {
                dateStyle: "short",
                timeStyle: "short",
                timeZone: workspace.timezone,
              }),
            })}
          </p>,
        );
      }
      if (item.scheduled_at) {
        lines.push(
          <p key="when">{t("content.detail.scheduledFor", { when: local(item.scheduled_at), zone })}</p>,
        );
      }
      break;
    case "scheduled":
    case "retry_scheduled":
      if (item.scheduled_at) {
        lines.push(
          <p key="when">{t("content.detail.scheduledFor", { when: local(item.scheduled_at), zone })}</p>,
        );
      }
      break;
    case "publishing":
      lines.push(<p key="publishing">{t("content.detail.publishing")}</p>);
      break;
    case "published": {
      const permalink = safeUrl(item.external_permalink);
      if (item.published_at) {
        lines.push(<p key="at">{t("content.detail.publishedAt", { when: local(item.published_at), zone })}</p>);
      }
      if (permalink) {
        lines.push(
          <p key="link" className="flex flex-wrap items-center gap-2" data-testid="permalink">
            <span>{t("content.detail.permalink")}:</span>
            <a
              href={permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
            >
              {t("content.detail.permalinkOpen")}
            </a>
            {item.is_simulated ? <SimulatedBadge /> : null}
          </p>,
        );
      }
      break;
    }
    case "rejected":
      lines.push(<p key="rejected">{t("content.detail.rejected")}</p>);
      if (item.approval?.decided_by_name) {
        lines.push(<p key="by">{t("content.detail.rejectedBy", { name: item.approval.decided_by_name })}</p>);
      }
      if (item.rejection_note) {
        lines.push(
          <p key="note" className="break-words whitespace-pre-wrap">
            {t("content.detail.rejectedNote", { note: item.rejection_note })}
          </p>,
        );
      }
      lines.push(<p key="next">{t("content.detail.rejectedNext")}</p>);
      break;
    case "cancelled":
      lines.push(<p key="cancelled">{t("content.detail.cancelled")}</p>);
      break;
    case "draft":
      if (item.hold_reason === "FACT_CHANGED" || item.hold_reason === "APPROVAL_EXPIRED") {
        lines.push(
          <p key="hold" data-testid="draft-hold" data-reason={item.hold_reason}>
            {t(`content.detail.draftHold.${item.hold_reason}`)}
          </p>,
        );
      }
      break;
    default:
      break;
  }

  if (lines.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 text-sm text-slate-800" data-testid="status-panel">
      {lines}
    </div>
  );
}

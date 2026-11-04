import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { contentBadge, isContentStatus } from "@/features/content/status";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const text = (summary: Record<string, unknown>, key: string): string | null => {
  const value = summary[key];
  return typeof value === "string" && value !== "" ? value : null;
};

/**
 * What "cancel this content" would cancel, from the confirmation's summary (`label`,
 * `content_type`, `status`, `when`, `content_id`): the item's name, what kind it is, where it
 * stands now (by the same status mapping as everywhere else, INV-18) and when it was due. The
 * strings are already formatted by the server; nothing here is computed.
 */
export function CancelContentSummary({ summary }: { summary: Record<string, unknown> }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const label = text(summary, "label");
  const type = text(summary, "content_type");
  const status = summary.status;
  const when = text(summary, "when");
  const contentId = text(summary, "content_id");

  return (
    <div
      className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-4 shadow-xs"
      data-testid="cancel-content-summary"
    >
      {label ? <p className="text-base font-heading font-semibold text-primary break-words">{label}</p> : null}
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 text-sm rounded-control border border-border bg-surface-subtle p-3.5">
        {type === "feed_image" || type === "story_image" ? (
          <>
            <dt className="text-secondary font-medium">{t("command.confirm.cancelContent.type")}</dt>
            <dd className="text-primary font-medium">{t(`content.type.${type}`)}</dd>
          </>
        ) : null}
        {isContentStatus(status) ? (
          <>
            <dt className="text-secondary font-medium">{t("command.confirm.cancelContent.status")}</dt>
            <dd>
              {(() => {
                const badge = contentBadge({ status, operation: null }, t, i18n.language, workspace.timezone);
                return <StatusBadge status={badge.status} params={badge.params} />;
              })()}
            </dd>
          </>
        ) : null}
        {when ? (
          <>
            <dt className="text-secondary font-medium">{t("command.confirm.cancelContent.when")}</dt>
            <dd data-testid="cancel-content-when" className="font-medium text-primary">{when}</dd>
          </>
        ) : null}
      </dl>
      <div className="rounded-control border border-danger/30 bg-danger-subtle p-3 text-sm text-danger">
        <p>{t("command.confirm.cancelContent.consequence")}</p>
      </div>
      {contentId ? (
        <div>
          <Link
            to={`/w/${workspace.id}/content/${contentId}`}
            className="inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          >
            {t("command.confirm.cancelContent.open")}
          </Link>
        </div>
      ) : null}
    </div>
  );
}

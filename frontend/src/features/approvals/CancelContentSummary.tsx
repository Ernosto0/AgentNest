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
    <div className="flex flex-col gap-2" data-testid="cancel-content-summary">
      {label ? <p className="text-lg font-semibold break-words">{label}</p> : null}
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1 text-sm">
        {type === "feed_image" || type === "story_image" ? (
          <>
            <dt className="text-slate-600">{t("command.confirm.cancelContent.type")}</dt>
            <dd>{t(`content.type.${type}`)}</dd>
          </>
        ) : null}
        {isContentStatus(status) ? (
          <>
            <dt className="text-slate-600">{t("command.confirm.cancelContent.status")}</dt>
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
            <dt className="text-slate-600">{t("command.confirm.cancelContent.when")}</dt>
            <dd data-testid="cancel-content-when">{when}</dd>
          </>
        ) : null}
      </dl>
      <p className="text-sm text-slate-700">{t("command.confirm.cancelContent.consequence")}</p>
      {contentId ? (
        <Link
          to={`/w/${workspace.id}/content/${contentId}`}
          className="inline-flex min-h-11 items-center text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
        >
          {t("command.confirm.cancelContent.open")}
        </Link>
      ) : null}
    </div>
  );
}

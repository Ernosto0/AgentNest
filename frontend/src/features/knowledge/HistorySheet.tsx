import { useTranslation } from "react-i18next";
import type { Fact } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useFactVersions } from "./hooks";
import { pickLabel } from "./labels";

/** Immutable version history of one fact (INV-17): what it was, who changed it, from where. */
export function HistorySheet({
  workspaceId,
  fact,
  timezone,
  onClose,
}: {
  workspaceId: string;
  fact: Fact;
  timezone: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const versions = useFactVersions(workspaceId, fact.id);
  const when = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  });

  return (
    <BottomSheet title={t("knowledge.history.title", { name: pickLabel(fact.label, i18n.language) })} onClose={onClose}>
      {versions.isPending ? <p className="text-secondary">{t("common.loading")}</p> : null}
      {versions.isError ? <ErrorMessage error={versions.error} /> : null}
      {versions.data ? (
        <ol className="relative flex flex-col gap-4 pl-4 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-0.5 before:bg-border">
          {versions.data.map((version) => (
            <li key={version.version} className="relative flex flex-col gap-2 rounded-panel border border-border bg-surface p-4 shadow-xs">
              <span className="absolute -left-[13px] top-4 h-2.5 w-2.5 rounded-full bg-action ring-4 ring-surface" />
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2">
                <span className="inline-flex items-center rounded-control bg-surface-subtle px-2 py-0.5 text-xs font-semibold text-primary border border-border">
                  {t("knowledge.history.version", { version: version.version })}
                </span>
                <p className="text-xs text-secondary">{when.format(new Date(version.created_at))}</p>
              </div>
              <p className="text-xs font-semibold text-action uppercase tracking-wide">
                {t(`knowledge.history.change.${version.change_kind}`)}
              </p>
              <div className="rounded-control bg-surface-subtle p-3 text-sm font-medium text-primary break-words border border-border/60">
                {version.display}
              </div>
              <p className="text-xs text-secondary">
                {t(`knowledge.source.${version.source_type}`, { defaultValue: version.source_type })}
                {version.actor_name ? ` · ${version.actor_name}` : ""}
              </p>
              {version.reason ? <p className="text-xs text-secondary italic">"{version.reason}"</p> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </BottomSheet>
  );
}

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
        <ol className="flex flex-col gap-3">
          {versions.data.map((version) => (
            <li key={version.version} className="rounded-card p-3.5 border border-border bg-surface shadow-xs">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold text-primary">{t("knowledge.history.version", { version: version.version })}</p>
                <p className="text-sm text-secondary">{when.format(new Date(version.created_at))}</p>
              </div>
              <p className="mt-1 text-sm font-medium text-primary">
                {t(`knowledge.history.change.${version.change_kind}`)}
              </p>
              <p className="mt-1 text-primary break-words">{version.display}</p>
              <p className="mt-1 text-sm text-secondary">
                {t(`knowledge.source.${version.source_type}`, { defaultValue: version.source_type })}
                {version.actor_name ? ` · ${version.actor_name}` : ""}
              </p>
              {version.reason ? <p className="mt-1 text-sm text-secondary italic">{version.reason}</p> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </BottomSheet>
  );
}

import { useTranslation } from "react-i18next";
import { ChangeSummary } from "./ChangeSummary";

export function ManagementSummary({ action, summary }: { action: string; summary: Record<string, unknown> }) {
  const { t } = useTranslation();
  return <div className="flex flex-col gap-3">
    {action === "command.pause_agent" ? <p>{t("command.confirm.pauseUntil", { when: String(summary.resume_at ?? "") })}</p> :
      <ChangeSummary summary={summary} fromKey="command.confirm.from" toKey="command.confirm.to" />}
    <p className="text-sm text-secondary">{t("command.confirm.timezone", { timezone: String(summary.timezone ?? "") })}</p>
  </div>;
}

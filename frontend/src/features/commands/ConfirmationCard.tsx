import { useTranslation } from "react-i18next";
import type { Command } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChangeSummary, ImpactSummary } from "@/features/approvals/ChangeSummary";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCancelCommand, useDecideApproval } from "./hooks";

/**
 * The owner's one explicit decision on a state change. It shows exactly what will change and
 * sends back the payload hash it displayed, so a change since then cannot be approved by
 * accident (INV-16). Nothing here is approved by anything but this button.
 */
export function ConfirmationCard({ command }: { command: Command }) {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const decide = useDecideApproval(workspace.id);
  const withdraw = useCancelCommand(workspace.id);
  const approval = command.approval;
  if (!approval) return null;

  const expires = new Date(approval.expires_at).toLocaleTimeString(i18n.language, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: workspace.timezone,
  });
  const busy = decide.isPending || withdraw.isPending;
  const error = decide.error ?? withdraw.error;

  return (
    <section
      aria-label={t("command.confirm.title")}
      className="flex flex-col gap-3"
      data-testid="confirmation-card"
      data-payload-hash={approval.payload_hash}
    >
      <h3 className="font-medium">{t("command.confirm.title")}</h3>
      <ChangeSummary summary={approval.summary} fromKey="command.confirm.from" toKey="command.confirm.to" />
      <ImpactSummary
        summary={approval.summary}
        titleKey="command.confirm.impactTitle"
        noneKey="command.confirm.impactNone"
      />
      {role === "staff" ? (
        <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-800">{t("command.confirm.staffNote")}</p>
      ) : null}
      <p className="text-sm text-slate-600">{t("command.confirm.expires", { time: expires })}</p>
      {error ? <ErrorMessage error={error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy || !approval.can_decide}
          onClick={() => decide.mutate({ approval, decision: "approve" })}
        >
          {decide.isPending ? t("command.confirm.deciding") : t("command.confirm.approve")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => withdraw.mutate(command.id)}>
          {t("command.confirm.withdraw")}
        </Button>
      </div>
    </section>
  );
}

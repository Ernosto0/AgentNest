import { useTranslation } from "react-i18next";
import type { Command } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, ClockIcon } from "@/components/icons";
import { CancelContentSummary } from "@/features/approvals/CancelContentSummary";
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
  // The card is generic over the action: a content cancel names an item, not a fact.
  const cancelContent = approval.action === "command.cancel_content";

  const expires = new Date(approval.expires_at).toLocaleTimeString(i18n.language, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: workspace.timezone,
  });
  const busy = decide.isPending || withdraw.isPending;
  const error = decide.error ?? withdraw.error;

  return (
    <section
      aria-label={cancelContent ? t("command.confirm.cancelContent.title") : t("command.confirm.title")}
      className="flex flex-col gap-4 rounded-xl border border-attention/30 bg-attention-subtle/30 p-4 sm:p-5 shadow-2xs"
      data-testid="confirmation-card"
      data-payload-hash={approval.payload_hash}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-attention/20 pb-3">
        <div className="flex items-center gap-2">
          <AlertIcon className="text-lg text-attention shrink-0" />
          <h3 className="font-heading text-base font-bold text-primary">
            {cancelContent ? t("command.confirm.cancelContent.title") : t("command.confirm.title")}
          </h3>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1 text-xs font-medium text-secondary shadow-2xs">
          <ClockIcon className="text-sm text-attention" />
          <span>{t("command.confirm.expires", { time: expires })}</span>
        </div>
      </div>

      {cancelContent ? (
        <CancelContentSummary summary={approval.summary} />
      ) : (
        <>
          <ChangeSummary summary={approval.summary} fromKey="command.confirm.from" toKey="command.confirm.to" />
          <ImpactSummary
            summary={approval.summary}
            titleKey="command.confirm.impactTitle"
            noneKey="command.confirm.impactNone"
          />
        </>
      )}

      {role === "staff" && !cancelContent ? (
        <p className="rounded-xl bg-surface p-3.5 text-body text-primary border border-border shadow-2xs">
          {t("command.confirm.staffNote")}
        </p>
      ) : null}

      {error ? <ErrorMessage error={error} /> : null}

      <div className="flex flex-wrap gap-2.5 pt-1">
        <Button
          disabled={busy || !approval.can_decide}
          onClick={() => decide.mutate({ approval, decision: "approve" })}
          className="rounded-lg shadow-xs font-semibold px-5"
        >
          {decide.isPending
            ? t("command.confirm.deciding")
            : cancelContent
              ? t("command.confirm.cancelContent.approve")
              : t("command.confirm.approve")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => withdraw.mutate(command.id)} className="rounded-lg">
          {t("command.confirm.withdraw")}
        </Button>
      </div>
    </section>
  );
}

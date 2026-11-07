import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReplyDraft } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useDecideApproval } from "@/features/commands/hooks";
import { ApprovalStateNote, DraftText, ReasonChips } from "./DraftParts";
import { useApproval, useCancelDraft, useEditDraft } from "./hooks";

/**
 * The assistant's draft for a conversation: the grounded text with its sources, why it needs
 * you, and the explicit decisions. Approving sends the payload hash shown by the approval.
 */
export function DraftCard({
  workspaceId,
  draft,
  onUseSuggestion,
}: {
  workspaceId: string;
  draft: ReplyDraft;
  onUseSuggestion?: (text: string) => void;
}) {
  const { t } = useTranslation();
  const pending = draft.status === "pending_approval";
  const approval = useApproval(workspaceId, pending ? draft.approval_id : null);
  const decide = useDecideApproval(workspaceId);
  const edit = useEditDraft(workspaceId);
  const cancel = useCancelDraft(workspaceId);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(draft.text ?? "");

  const canDecide = approval.data?.can_decide === true;
  const busy = decide.isPending || edit.isPending || cancel.isPending;

  return (
    <Card
      className="flex min-w-0 flex-col gap-4 bg-assistant p-4"
      data-testid="draft-card"
      data-draft-status={draft.status}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/80 pb-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 shrink-0 rounded-full bg-action" />
          <span className="font-heading font-bold text-primary tracking-tight">{t(`convo.status.${draft.status}`)}</span>
        </div>
        {draft.is_simulated ? <SimulatedBadge /> : null}
      </div>

      {draft.text !== null && !editing ? <DraftText draft={draft} /> : null}
      {draft.text === null && draft.suggestion_text ? (
        <div className="rounded-control bg-surface p-4 border border-border text-body shadow-xs">
          <p className="font-semibold text-primary">{t("convo.draft.suggestionTitle")}</p>
          <p className="mt-1.5 break-words whitespace-pre-wrap text-secondary">{draft.suggestion_text}</p>
          {onUseSuggestion ? (
            <Button variant="secondary" className="mt-3" onClick={() => onUseSuggestion(draft.suggestion_text ?? "")}>
              {t("convo.draft.useSuggestion")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {draft.status === "needs_human" ? (
        <div className="rounded-control bg-attention-subtle p-3 text-body font-semibold text-attention border border-attention/20">
          <p>{t("convo.draft.youMustReply")}</p>
        </div>
      ) : null}
      {draft.status === "outcome_unknown" ? (
        <div className="rounded-control bg-info-subtle p-3 text-body font-medium text-info border border-info/20" role="status">
          <p>{t("convo.draft.checking")}</p>
        </div>
      ) : null}
      {draft.status === "failed" || draft.status === "blocked" ? (
        <div className="rounded-control bg-danger-subtle p-3 text-body font-medium text-danger border border-danger/20" role="alert">
          <p>
            {draft.failure_code && draft.failure_code === "OUTCOME_UNCONFIRMED"
              ? t("convo.draft.unconfirmed")
              : t("convo.draft.failed")}
          </p>
        </div>
      ) : null}

      <ReasonChips reasons={draft.decision_reasons} />

      {draft.validation.issues.length > 0 ? (
        <ul className="rounded-control bg-attention-subtle p-3 text-body text-attention border border-attention/30 flex flex-col gap-1">
          {draft.validation.issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`}>
              {t("convo.composer.warning", { text: issue.text || issue.code })}
            </li>
          ))}
        </ul>
      ) : null}

      {editing ? (
        <div className="flex flex-col gap-2.5">
          <label htmlFor={`edit-${draft.id}`} className="text-form font-medium text-primary">
            {t("convo.draft.editLabel")}
          </label>
          <textarea
            id={`edit-${draft.id}`}
            value={editText}
            onChange={(event) => setEditText(event.target.value)}
            rows={4}
            className="w-full rounded-control border border-control bg-surface p-3 text-form text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          />
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              disabled={busy || !editText.trim()}
              onClick={() =>
                edit.mutate(
                  { draft, text: editText, approve: canDecide },
                  { onSuccess: () => setEditing(false) },
                )
              }
            >
              {canDecide ? t("convo.draft.saveAndSend") : t("convo.draft.save")}
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : null}

      {pending && !editing ? (
        canDecide && approval.data ? (
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              disabled={busy}
              onClick={() => decide.mutate({ approval: approval.data, decision: "approve" })}
            >
              {decide.isPending ? t("convo.draft.sending") : t("convo.draft.approve")}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setEditText(draft.text ?? "");
                setEditing(true);
              }}
            >
              {t("convo.draft.edit")}
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => decide.mutate({ approval: approval.data, decision: "reject" })}
            >
              {t("convo.draft.reject")}
            </Button>
          </div>
        ) : (
          <p className="text-body text-secondary">{t("convo.draft.waitingForOwner")}</p>
        )
      ) : null}
      {draft.approval_state && !editing ? (
        <ApprovalStateNote state={draft.approval_state} showPending={pending && approval.isSuccess && !canDecide} />
      ) : null}
      {draft.status === "queued" ? (
        <Button variant="secondary" disabled={busy} onClick={() => cancel.mutate(draft.id)}>
          {t("convo.draft.cancel")}
        </Button>
      ) : null}
      {decide.error ? <ErrorMessage error={decide.error} /> : null}
      {edit.error ? <ErrorMessage error={edit.error} /> : null}
      {cancel.error ? <ErrorMessage error={cancel.error} /> : null}
    </Card>
  );
}

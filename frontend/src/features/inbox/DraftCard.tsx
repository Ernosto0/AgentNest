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
      className="flex flex-col gap-3.5 border-indigo-200/80 bg-indigo-50/20 shadow-2xs"
      data-testid="draft-card"
      data-draft-status={draft.status}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-indigo-100 pb-2.5">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-900">{t(`convo.status.${draft.status}`)}</span>
        </div>
        {draft.is_simulated ? <SimulatedBadge /> : null}
      </div>

      {draft.text !== null && !editing ? <DraftText draft={draft} /> : null}
      {draft.text === null && draft.suggestion_text ? (
        <div className="rounded-lg bg-white p-3.5 ring-1 ring-slate-200 text-sm">
          <p className="font-semibold text-slate-900">{t("convo.draft.suggestionTitle")}</p>
          <p className="mt-1 break-words whitespace-pre-wrap text-slate-700">{draft.suggestion_text}</p>
          {onUseSuggestion ? (
            <Button variant="secondary" className="mt-2.5" onClick={() => onUseSuggestion(draft.suggestion_text ?? "")}>
              {t("convo.draft.useSuggestion")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {draft.status === "needs_human" ? (
        <p className="text-sm font-semibold text-amber-900">{t("convo.draft.youMustReply")}</p>
      ) : null}
      {draft.status === "outcome_unknown" ? (
        <p className="text-sm font-medium text-slate-700" role="status">
          {t("convo.draft.checking")}
        </p>
      ) : null}
      {draft.status === "failed" || draft.status === "blocked" ? (
        <p className="text-sm font-medium text-red-800" role="alert">
          {draft.failure_code && draft.failure_code === "OUTCOME_UNCONFIRMED"
            ? t("convo.draft.unconfirmed")
            : t("convo.draft.failed")}
        </p>
      ) : null}

      <ReasonChips reasons={draft.decision_reasons} />

      {draft.validation.issues.length > 0 ? (
        <ul className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-300">
          {draft.validation.issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`}>{t("convo.composer.warning", { text: issue.text || issue.code })}</li>
          ))}
        </ul>
      ) : null}

      {editing ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={`edit-${draft.id}`} className="text-sm font-medium text-slate-900">
            {t("convo.draft.editLabel")}
          </label>
          <textarea
            id={`edit-${draft.id}`}
            value={editText}
            onChange={(event) => setEditText(event.target.value)}
            rows={4}
            className="w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
          />
          <div className="flex flex-wrap gap-2">
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
          <p className="text-sm text-slate-700">{t("convo.draft.waitingForOwner")}</p>
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

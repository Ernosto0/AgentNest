import { useDirtyForm } from "@/components/DirtyForms";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ReplyDraft } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, BookIcon, CheckIcon, HandIcon, InfoIcon, PencilIcon, SendIcon, SparkIcon, XIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useDecideApproval } from "@/features/commands/hooks";
import { ApprovalStateNote, DraftText, ReasonChips } from "./DraftParts";
import { useApproval, useCancelDraft, useEditDraft } from "./hooks";

type Status = ReplyDraft["status"];

const STATUS_TONE: Partial<Record<Status, string>> = {
  pending_approval: "bg-attention-subtle text-attention",
  needs_human: "bg-attention-subtle text-attention",
  queued: "bg-info-subtle text-info",
  sending: "bg-info-subtle text-info",
  outcome_unknown: "bg-info-subtle text-info",
  sent: "bg-success-subtle text-success",
  failed: "bg-danger-subtle text-danger",
  blocked: "bg-danger-subtle text-danger",
};

const ORIGIN_ICON: Record<ReplyDraft["source"], ReactNode> = {
  ai: <SparkIcon />,
  approved_answer: <BookIcon />,
  owner: <PencilIcon />,
};

/** A toned line inside the card. `role` is given only where the state itself is news. */
function Notice({ tone, icon, children, role }: { tone: "attention" | "info" | "danger"; icon: ReactNode; children: ReactNode; role?: "status" | "alert" }) {
  const toneClass = {
    attention: "bg-attention-subtle text-attention",
    info: "bg-info-subtle text-info",
    danger: "bg-danger-subtle text-danger",
  }[tone];
  return (
    <div role={role} className={`flex items-start gap-2.5 rounded-xl px-3.5 py-2.5 text-body font-medium ${toneClass}`}>
      <span aria-hidden="true" className="mt-0.5 shrink-0 text-base">{icon}</span>
      <p className="min-w-0">{children}</p>
    </div>
  );
}

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

  useDirtyForm(editing && editText !== (draft.text ?? ""));
  const canDecide = approval.data?.can_decide === true;
  const busy = decide.isPending || edit.isPending || cancel.isPending;

  return (
    <section
      aria-labelledby={`draft-${draft.id}-title`}
      className="flex min-w-0 flex-col gap-3.5 rounded-2xl bg-assistant p-4"
      data-testid="draft-card"
      data-draft-status={draft.status}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-action text-base text-on-action">
            {ORIGIN_ICON[draft.source]}
          </span>
          <h3 id={`draft-${draft.id}-title`} className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {t(`convo.draft.origin.${draft.source}`)}
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs leading-5 font-semibold ${STATUS_TONE[draft.status] ?? "bg-surface text-secondary"}`}>
            {draft.status === "sent" ? <CheckIcon aria-hidden="true" className="text-[0.8125rem]" /> : null}
            {t(`convo.status.${draft.status}`)}
          </span>
          {draft.is_simulated ? <SimulatedBadge compact /> : null}
        </div>
      </div>

      {draft.text !== null && !editing ? (
        <div className="rounded-xl border border-action/10 bg-surface px-4 py-3">
          <DraftText draft={draft} />
        </div>
      ) : null}
      {draft.text === null && draft.suggestion_text ? (
        <div className="rounded-xl border border-dashed border-action/25 bg-surface px-4 py-3">
          <p className="text-xs font-semibold tracking-wide text-secondary uppercase">{t("convo.draft.suggestionTitle")}</p>
          <p className="mt-1.5 text-[0.9375rem] leading-6 break-words whitespace-pre-wrap text-primary">{draft.suggestion_text}</p>
          {onUseSuggestion ? (
            <Button variant="secondary" className="mt-3" onClick={() => onUseSuggestion(draft.suggestion_text ?? "")}>
              <PencilIcon aria-hidden="true" className="text-base text-action" />
              {t("convo.draft.useSuggestion")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {draft.status === "needs_human" ? (
        <Notice tone="attention" icon={<HandIcon />}>{t("convo.draft.youMustReply")}</Notice>
      ) : null}
      {draft.status === "outcome_unknown" ? (
        <Notice tone="info" icon={<InfoIcon />} role="status">{t("convo.draft.checking")}</Notice>
      ) : null}
      {draft.status === "failed" || draft.status === "blocked" ? (
        <Notice tone="danger" icon={<AlertIcon />} role="alert">
          {draft.failure_code && draft.failure_code === "OUTCOME_UNCONFIRMED" ? t("convo.draft.unconfirmed") : t("convo.draft.failed")}
        </Notice>
      ) : null}

      <ReasonChips reasons={draft.decision_reasons} />

      {draft.validation.issues.length > 0 ? (
        <ul className="flex flex-col gap-1 rounded-xl bg-attention-subtle px-3.5 py-2.5 text-body text-attention">
          {draft.validation.issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`} className="flex items-start gap-2">
              <AlertIcon aria-hidden="true" className="mt-1 shrink-0 text-sm" />
              {t("convo.composer.warning", { text: issue.text || issue.code })}
            </li>
          ))}
        </ul>
      ) : null}

      {editing ? (
        <div className="flex flex-col gap-2.5">
          <label htmlFor={`edit-${draft.id}`} className="text-body font-semibold text-primary">
            {t("convo.draft.editLabel")}
          </label>
          <textarea
            id={`edit-${draft.id}`}
            value={editText}
            onChange={(event) => setEditText(event.target.value)}
            rows={4}
            className={`w-full rounded-xl border border-control/60 bg-surface p-3 text-form text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus`}
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
              {canDecide ? <SendIcon aria-hidden="true" className="text-base" /> : null}
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
          <div className="flex flex-wrap items-center gap-2 border-t border-action/10 pt-3.5">
            <Button disabled={busy} onClick={() => decide.mutate({ approval: approval.data, decision: "approve" })}>
              <SendIcon aria-hidden="true" className="text-base" />
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
              <PencilIcon aria-hidden="true" className="text-base" />
              {t("convo.draft.edit")}
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              className="text-secondary enabled:hover:bg-surface/70 enabled:hover:text-danger sm:ml-auto"
              onClick={() => decide.mutate({ approval: approval.data, decision: "reject" })}
            >
              <XIcon aria-hidden="true" className="text-base" />
              {t("convo.draft.reject")}
            </Button>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-body text-secondary">
            <InfoIcon aria-hidden="true" className="shrink-0 text-base" />
            {t("convo.draft.waitingForOwner")}
          </p>
        )
      ) : null}
      {draft.approval_state && !editing ? (
        <ApprovalStateNote state={draft.approval_state} showPending={pending && approval.isSuccess && !canDecide} />
      ) : null}
      {draft.status === "queued" ? (
        <div>
          <Button variant="secondary" disabled={busy} onClick={() => cancel.mutate(draft.id)}>
            {t("convo.draft.cancel")}
          </Button>
        </div>
      ) : null}
      {decide.error ? <ErrorMessage error={decide.error} /> : null}
      {edit.error ? <ErrorMessage error={edit.error} /> : null}
      {cancel.error ? <ErrorMessage error={cancel.error} /> : null}
    </section>
  );
}

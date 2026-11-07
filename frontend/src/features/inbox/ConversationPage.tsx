import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronLeftIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { ConversationAgentWork } from "@/features/agent-work/WorkPages";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { DraftCard } from "./DraftCard";
import { WindowTimer } from "./DraftParts";
import {
  useConversation,
  useEraseConversation,
  useExportConversation,
  useHandlingMode,
  useSaveAsAnswer,
  useSuggestReply,
} from "./hooks";
import { customerLabel } from "./labels";
import { ReplyComposer } from "./ReplyComposer";

function time(value: string, language: string, timezone: string): string {
  return new Date(value).toLocaleString(language, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: timezone,
  });
}

/** One conversation: the messages, the assistant's draft for the last question, and your reply. */
export function ConversationPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { workspace, role } = useCurrentWorkspace();
  const { conversationId = "" } = useParams();
  const detail = useConversation(workspace.id, conversationId);
  const mode = useHandlingMode(workspace.id, conversationId);
  const suggest = useSuggestReply(workspace.id, conversationId);
  const saveAnswer = useSaveAsAnswer(workspace.id);
  const exportConvo = useExportConversation(workspace.id, conversationId);
  const eraseConvo = useEraseConversation(workspace.id, conversationId);
  const [seed, setSeed] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const handleExport = async () => {
    try {
      const data = await exportConvo.mutateAsync();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `conversation-${conversationId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Handled via exportConvo.error display
    }
  };

  const handleErase = async () => {
    if (window.confirm(t("convo.eraseConfirm"))) {
      try {
        await eraseConvo.mutateAsync();
        navigate(`/w/${workspace.id}/inbox`);
      } catch {
        // Handled via eraseConvo.error display
      }
    }
  };

  if (detail.isPending) return <p className="text-body text-secondary">{t("common.loading")}</p>;
  if (detail.isError) return <ErrorMessage error={detail.error} />;
  const { conversation, messages, open_draft: openDraft, recent_drafts: recent } = detail.data;
  const canManage = role === "owner" || role === "manager";
  const lastDraft = openDraft ?? recent[0] ?? null;
  const human = conversation.handling_mode === "human";

  return (
    <div className="flex min-w-0 flex-col gap-5">
      {/* Header with back navigation, customer info, handling mode & window timer */}
      <div className="flex flex-col gap-3.5 border-b border-border pb-4">
        <div>
          <Link
            to={`/w/${workspace.id}/inbox`}
            className="inline-flex items-center gap-1.5 text-body font-semibold text-action hover:text-action-hover underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus rounded-control"
          >
            <ChevronLeftIcon className="text-base" />
            <span>{t("convo.back")}</span>
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="type-page text-primary">{customerLabel(conversation, t)}</h1>
            {conversation.is_simulated ? <SimulatedBadge /> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <WindowTimer endsAt={conversation.window_ends_at} />
            <Button
              variant="secondary"
              disabled={mode.isPending}
              onClick={() => mode.mutate(human ? "release" : "takeover")}
            >
              {human ? t("convo.release") : t("convo.takeover")}
            </Button>
            <Button variant="ghost" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
              {t("convo.suggest")}
            </Button>
            {role === "owner" ? (
              <>
                <Button
                  variant="ghost"
                  disabled={exportConvo.isPending}
                  onClick={handleExport}
                  title={t("convo.exportTooltip")}
                >
                  {exportConvo.isPending ? t("common.loading") : t("convo.export")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={eraseConvo.isPending}
                  onClick={handleErase}
                  className="text-danger hover:bg-danger-subtle hover:text-danger-hover"
                  title={t("convo.eraseTooltip")}
                >
                  {eraseConvo.isPending ? t("common.loading") : t("convo.erase")}
                </Button>
              </>
            ) : null}
          </div>
        </div>
        {human ? (
          <div className="rounded-control bg-attention-subtle px-4 py-2.5 text-body font-medium text-attention">
            <p>{t("convo.humanMode")}</p>
          </div>
        ) : null}
        {mode.error ? <ErrorMessage error={mode.error} /> : null}
        {suggest.error ? <ErrorMessage error={suggest.error} /> : null}
        {exportConvo.error ? <ErrorMessage error={exportConvo.error} /> : null}
        {eraseConvo.error ? <ErrorMessage error={eraseConvo.error} /> : null}
      </div>

      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex min-w-0 flex-col gap-4">
      {/* Message Stream */}
      <div className="flex min-h-64 flex-col justify-end gap-4 rounded-panel border border-border bg-surface-subtle p-4 md:p-6">
        <ol className="flex flex-col gap-3.5" aria-label={t("convo.messages")} data-testid="messages">
          {messages.map((message) => {
            const mine = message.direction === "outbound";
            return (
              <li key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 break-words whitespace-pre-wrap shadow-xs ${
                    mine
                      ? "bg-action text-on-action rounded-br-xs"
                      : "bg-surface border border-border/90 text-primary rounded-bl-xs shadow-2xs"
                  }`}
                >
                  <p className="text-form leading-relaxed font-normal">
                    {message.text ?? (message.attachments.length > 0 ? t("convo.attachment") : "")}
                  </p>
                  <span
                    className={`mt-1.5 flex flex-wrap items-center gap-1.5 text-metadata ${
                      mine ? "text-on-action/80" : "text-secondary"
                    }`}
                  >
                    {mine && message.sender_kind === "business_native" ? <span>{t("convo.sentInApp")} · </span> : null}
                    <span>{time(message.provider_timestamp, i18n.language, workspace.timezone)}</span>
                    {message.is_simulated ? <span> · {t("badge.simulated")}</span> : null}
                  </span>
                  {mine && canManage ? (
                    <button
                      type="button"
                      className="mt-2.5 block text-metadata underline font-medium text-on-action/90 hover:text-on-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-inverse"
                      disabled={saveAnswer.isPending}
                      onClick={() =>
                        saveAnswer.mutate(message.id, { onSuccess: () => setSaved(message.id) })
                      }
                    >
                      {saved === message.id ? t("convo.savedAsAnswer") : t("convo.saveAsAnswer")}
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
      {saveAnswer.error ? <ErrorMessage error={saveAnswer.error} /> : null}

      </div>
      <aside className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-24 xl:col-start-2 xl:row-start-1 xl:row-span-2">
        {conversation.social_account_id ? (
          <ConversationAgentWork account={conversation.social_account_id} conversation={conversationId} />
        ) : null}
        {lastDraft ? (
          <DraftCard workspaceId={workspace.id} draft={lastDraft} onUseSuggestion={setSeed} />
        ) : null}
      </aside>
      <div className="min-w-0 xl:col-start-1">
        <ReplyComposer
          key={seed ?? "none"}
          workspaceId={workspace.id}
          conversationId={conversationId}
          seed={seed}
          fromDraftId={lastDraft?.status === "needs_human" ? lastDraft.id : undefined}
        />
      </div>
      </div>
    </div>
  );
}

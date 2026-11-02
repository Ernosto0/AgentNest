import { ConversationAgentWork } from "@/features/agent-work/WorkPages";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronLeftIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { DraftCard } from "./DraftCard";
import { WindowTimer } from "./DraftParts";
import {
  useConversation,
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
  const { workspace, role } = useCurrentWorkspace();
  const { conversationId = "" } = useParams();
  const detail = useConversation(workspace.id, conversationId);
  const mode = useHandlingMode(workspace.id, conversationId);
  const suggest = useSuggestReply(workspace.id, conversationId);
  const saveAnswer = useSaveAsAnswer(workspace.id);
  const exportConvo = useExportConversation(workspace.id, conversationId);
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

  if (detail.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (detail.isError) return <ErrorMessage error={detail.error} />;
  const { conversation, messages, open_draft: openDraft, recent_drafts: recent } = detail.data;
  const canManage = role === "owner" || role === "manager";
  const lastDraft = openDraft ?? recent[0] ?? null;
  const human = conversation.handling_mode === "human";

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      {/* Header with back navigation, customer info, handling mode & window timer */}
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200/90 bg-white p-4 shadow-2xs">
        <div>
          <Link
            to={`/w/${workspace.id}/inbox`}
            className="inline-flex items-center gap-1 text-sm font-medium text-indigo-700 hover:text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            <ChevronLeftIcon className="text-base" />
            <span>{t("convo.back")}</span>
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">{customerLabel(conversation, t)}</h1>
            {conversation.is_simulated ? <SimulatedBadge /> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
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
              <Button
                variant="ghost"
                disabled={exportConvo.isPending}
                onClick={handleExport}
                title={t("convo.exportTooltip")}
              >
                {exportConvo.isPending ? t("common.loading") : t("convo.export")}
              </Button>
            ) : null}
          </div>
        </div>
        {human ? <p className="text-sm font-medium text-amber-900">{t("convo.humanMode")}</p> : null}
        {mode.error ? <ErrorMessage error={mode.error} /> : null}
        {suggest.error ? <ErrorMessage error={suggest.error} /> : null}
        {exportConvo.error ? <ErrorMessage error={exportConvo.error} /> : null}
      </div>

      {conversation.social_account_id ? (
        <ConversationAgentWork account={conversation.social_account_id} conversation={conversationId} />
      ) : null}

      {/* Message Stream */}
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200/90 bg-slate-50/60 p-4">
        <ol className="flex flex-col gap-3" aria-label={t("convo.messages")} data-testid="messages">
          {messages.map((message) => {
            const mine = message.direction === "outbound";
            return (
              <li key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 break-words whitespace-pre-wrap shadow-2xs ${
                    mine
                      ? "bg-indigo-600 text-white rounded-br-xs"
                      : "bg-white ring-1 ring-slate-200 text-slate-900 rounded-bl-xs"
                  }`}
                >
                  <p className="text-base leading-relaxed">
                    {message.text ?? (message.attachments.length > 0 ? t("convo.attachment") : "")}
                  </p>
                  <span className={`mt-1.5 flex flex-wrap items-center gap-1.5 text-xs ${mine ? "text-indigo-100" : "text-slate-500"}`}>
                    {mine && message.sender_kind === "business_native" ? <span>{t("convo.sentInApp")} · </span> : null}
                    <span>{time(message.provider_timestamp, i18n.language, workspace.timezone)}</span>
                    {message.is_simulated ? <span> · {t("badge.simulated")}</span> : null}
                  </span>
                  {mine && canManage ? (
                    <button
                      type="button"
                      className={`mt-2 block text-xs underline font-medium opacity-90 hover:opacity-100 focus-visible:outline-2 ${mine ? "text-primary-contrast focus-visible:outline-primary-contrast" : "text-action focus-visible:outline-focus"}`}
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

      {/* Grounded draft suggestion area */}
      {lastDraft ? (
        <DraftCard workspaceId={workspace.id} draft={lastDraft} onUseSuggestion={setSeed} />
      ) : null}

      {/* Manual reply composer */}
      <ReplyComposer
        key={seed ?? "none"}
        workspaceId={workspace.id}
        conversationId={conversationId}
        seed={seed}
        fromDraftId={lastDraft?.status === "needs_human" ? lastDraft.id : undefined}
      />
    </div>
  );
}

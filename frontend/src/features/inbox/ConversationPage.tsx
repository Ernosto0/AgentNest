import { ConversationAgentWork } from "@/features/agent-work/WorkPages";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { DraftCard } from "./DraftCard";
import { WindowTimer } from "./DraftParts";
import { useConversation, useHandlingMode, useSaveAsAnswer, useSuggestReply } from "./hooks";
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
  const [seed, setSeed] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  if (detail.isPending) return <p>{t("common.loading")}</p>;
  if (detail.isError) return <ErrorMessage error={detail.error} />;
  const { conversation, messages, open_draft: openDraft, recent_drafts: recent } = detail.data;
  const canManage = role === "owner" || role === "manager";
  const lastDraft = openDraft ?? recent[0] ?? null;
  const human = conversation.handling_mode === "human";

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link to={`/w/${workspace.id}/inbox`} className="text-sm font-medium text-indigo-800 underline">
          {t("convo.back")}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold">{customerLabel(conversation, t)}</h1>
          {conversation.is_simulated ? <SimulatedBadge /> : null}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-3">
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
        </div>
        {human ? <p className="mt-1 text-sm text-slate-700">{t("convo.humanMode")}</p> : null}
        {mode.error ? <ErrorMessage error={mode.error} /> : null}
        {suggest.error ? <ErrorMessage error={suggest.error} /> : null}
      </div>

      {conversation.social_account_id ? <ConversationAgentWork account={conversation.social_account_id} conversation={conversationId} /> : null}
      <ol className="flex flex-col gap-2" aria-label={t("convo.messages")} data-testid="messages">
        {messages.map((message) => {
          const mine = message.direction === "outbound";
          return (
            <li key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 break-words whitespace-pre-wrap ${
                  mine ? "bg-indigo-700 text-white" : "bg-white ring-1 ring-slate-200"
                }`}
              >
                {message.text ?? (message.attachments.length > 0 ? t("convo.attachment") : "")}
                <span className={`mt-1 block text-xs ${mine ? "text-indigo-100" : "text-slate-600"}`}>
                  {mine && message.sender_kind === "business_native" ? `${t("convo.sentInApp")} · ` : ""}
                  {time(message.provider_timestamp, i18n.language, workspace.timezone)}
                  {message.is_simulated ? ` · ${t("badge.simulated")}` : ""}
                </span>
                {mine && canManage ? (
                  <button
                    type="button"
                    className="mt-1 block text-xs underline"
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
      {saveAnswer.error ? <ErrorMessage error={saveAnswer.error} /> : null}

      {lastDraft ? (
        <DraftCard workspaceId={workspace.id} draft={lastDraft} onUseSuggestion={setSeed} />
      ) : null}

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

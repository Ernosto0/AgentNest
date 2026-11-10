import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ConversationDetail } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronLeftIcon, ClockIcon, HandIcon, ImageIcon, MoreIcon, PencilIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { SkeletonRows } from "@/features/home/DashboardPanel";
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
  useSocialAccounts,
  useSuggestReply,
  useWindowMinutes,
} from "./hooks";
import { CustomerAvatar, FOCUS, PANE } from "./InboxParts";
import { customerLabel, daysAgo } from "./labels";
import { ReplyComposer } from "./ReplyComposer";

type Message = ConversationDetail["messages"][number];

/** "Today", "Yesterday" or the date, in the workspace time zone. */
function dayLabel(value: string, language: string, timeZone: string): string {
  const days = daysAgo(value, timeZone);
  if (days === 0 || days === 1) return new Intl.RelativeTimeFormat(language, { numeric: "auto" }).format(-days, "day");
  return new Date(value).toLocaleDateString(language, { weekday: "long", day: "numeric", month: "long", timeZone });
}

/**
 * The message history, oldest first, grouped by day. On wide screens it scrolls inside its own
 * region and opens at the newest message; it follows new messages only while you are at the bottom.
 */
function Thread({ messages, canManage }: { messages: Message[]; canManage: boolean }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const saveAnswer = useSaveAsAnswer(workspace.id);
  const [saved, setSaved] = useState<string | null>(null);
  const region = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const count = messages.length;
  useLayoutEffect(() => {
    const el = region.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [count]);

  const tz = workspace.timezone;
  const dayOf = (value: string) => new Date(value).toLocaleDateString("en-CA", { timeZone: tz });
  const clock = (value: string) => new Date(value).toLocaleTimeString(i18n.language, { hour: "2-digit", minute: "2-digit", timeZone: tz });
  const full = (value: string) => new Date(value).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short", timeZone: tz });

  return (
    <div
      ref={region}
      role="region"
      aria-label={t("convo.messages")}
      tabIndex={0}
      onScroll={(event) => {
        const el = event.currentTarget;
        atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className="bg-canvas/70 px-3 py-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus sm:px-5 lg:max-h-[min(58dvh,620px)] lg:min-h-48 lg:overflow-y-auto"
    >
      {count === 0 ? (
        <p className="py-8 text-center text-metadata text-secondary">{t("convo.noPreview")}</p>
      ) : null}
      <ol className="flex flex-col" data-testid="messages">
        {messages.map((message, index) => {
          const mine = message.direction === "outbound";
          const native = mine && message.sender_kind === "business_native";
          const previous = messages[index - 1];
          const newDay = !previous || dayOf(previous.provider_timestamp) !== dayOf(message.provider_timestamp);
          const grouped = !newDay && previous?.direction === message.direction;
          const removed = message.text === null && message.attachments.length === 0;
          return (
            <li key={message.id} className={`flex flex-col ${grouped ? "mt-1.5" : newDay ? "" : "mt-4"} ${mine ? "items-end" : "items-start"}`}>
              {newDay ? (
                <p className={`flex w-full items-center gap-3 text-xs font-semibold text-secondary ${index === 0 ? "mb-4" : "my-4"}`}>
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                  <span className="first-letter:uppercase">{dayLabel(message.provider_timestamp, i18n.language, tz)}</span>
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                </p>
              ) : null}
              <div
                className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 break-words whitespace-pre-wrap sm:max-w-[78%] ${
                  native
                    ? "rounded-br-md border border-action/20 bg-assistant text-primary"
                    : mine
                      ? "rounded-br-md bg-action text-on-action"
                      : "rounded-bl-md border border-border bg-surface text-primary"
                }`}
              >
                {message.text !== null ? (
                  <p className="text-[0.9375rem] leading-6">{message.text}</p>
                ) : message.attachments.length > 0 ? (
                  <p className="inline-flex items-center gap-2 text-[0.9375rem] leading-6">
                    <ImageIcon aria-hidden="true" className="shrink-0" />
                    {t("convo.attachment")}
                  </p>
                ) : (
                  <p className="text-[0.9375rem] leading-6 italic opacity-80">{t("convo.removed")}</p>
                )}
              </div>
              <p className={`mt-1 flex flex-wrap items-center gap-x-1.5 px-1 text-xs text-secondary ${mine ? "justify-end" : ""}`}>
                {native ? <span>{t("convo.sentInApp")} ·</span> : null}
                <time dateTime={message.provider_timestamp} title={full(message.provider_timestamp)} className="tabular-nums">
                  {clock(message.provider_timestamp)}
                </time>
                {message.is_simulated ? <span>· {t("badge.simulated")}</span> : null}
                {mine && canManage && !removed ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <button
                      type="button"
                      className={`rounded font-semibold text-action underline-offset-2 hover:underline disabled:opacity-60 ${FOCUS}`}
                      disabled={saveAnswer.isPending || saved === message.id}
                      onClick={() => saveAnswer.mutate(message.id, { onSuccess: () => setSaved(message.id) })}
                    >
                      {saved === message.id ? t("convo.savedAsAnswer") : t("convo.saveAsAnswer")}
                    </button>
                  </>
                ) : null}
              </p>
            </li>
          );
        })}
      </ol>
      {saveAnswer.error ? <div className="mt-3"><ErrorMessage error={saveAnswer.error} /></div> : null}
    </div>
  );
}

/** Owner-only data rights: export and erase, behind a quiet overflow menu. */
function MoreActions({ conversationId }: { conversationId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { workspace } = useCurrentWorkspace();
  const exportConvo = useExportConversation(workspace.id, conversationId);
  const eraseConvo = useEraseConversation(workspace.id, conversationId);
  const menu = useRef<HTMLDetailsElement>(null);

  // Close the menu on an outside click or Escape, like any other menu.
  useEffect(() => {
    const close = (event: Event) => {
      const el = menu.current;
      if (!el?.open) return;
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !el.contains(event.target as Node)) el.open = false;
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, []);

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
      // Shown through exportConvo.error.
    }
  };

  const handleErase = async () => {
    if (window.confirm(t("convo.eraseConfirm"))) {
      try {
        await eraseConvo.mutateAsync();
        navigate(`/w/${workspace.id}/inbox`);
      } catch {
        // Shown through eraseConvo.error.
      }
    }
  };

  return (
    <>
      <details ref={menu} className="relative">
        <summary
          title={t("core.moreActions")}
          className={`flex size-11 cursor-pointer list-none items-center justify-center rounded-control border border-border bg-surface text-lg text-secondary transition-colors hover:bg-surface-subtle hover:text-primary [&::-webkit-details-marker]:hidden ${FOCUS}`}
        >
          <MoreIcon aria-hidden="true" />
          <span className="sr-only">{t("core.moreActions")}</span>
        </summary>
        <div className="absolute right-0 z-20 mt-1.5 flex w-60 flex-col gap-0.5 rounded-xl border border-border bg-surface p-1.5 shadow-float">
          <Button variant="ghost" className="justify-start" disabled={exportConvo.isPending} onClick={handleExport} title={t("convo.exportTooltip")}>
            {exportConvo.isPending ? t("common.loading") : t("convo.export")}
          </Button>
          <Button
            variant="ghost"
            disabled={eraseConvo.isPending}
            onClick={handleErase}
            className="justify-start text-danger hover:bg-danger-subtle hover:text-danger-hover"
            title={t("convo.eraseTooltip")}
          >
            {eraseConvo.isPending ? t("common.loading") : t("convo.erase")}
          </Button>
        </div>
      </details>
      {exportConvo.error ? <div className="basis-full"><ErrorMessage error={exportConvo.error} /></div> : null}
      {eraseConvo.error ? <div className="basis-full"><ErrorMessage error={eraseConvo.error} /></div> : null}
    </>
  );
}

/** One conversation: the messages, the assistant's draft for the last question, and your reply. */
export function ConversationPage() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const { conversationId = "" } = useParams();
  const detail = useConversation(workspace.id, conversationId);
  const accounts = useSocialAccounts(workspace.id);
  const mode = useHandlingMode(workspace.id, conversationId);
  const suggest = useSuggestReply(workspace.id, conversationId);
  const [params] = useSearchParams();
  const [composing, setComposing] = useState(false);
  const [seed, setSeed] = useState<string | null>(null);
  const windowMinutes = useWindowMinutes(detail.data?.conversation.window_ends_at ?? null);

  const back = (
    <Link
      to={`/w/${workspace.id}/inbox${params.size ? `?${params}` : ""}`}
      className={`-ml-1 inline-flex min-h-11 w-fit items-center gap-1 rounded-control px-1 text-body font-semibold text-action hover:text-action-hover lg:hidden ${FOCUS}`}
    >
      <ChevronLeftIcon aria-hidden="true" className="text-lg" />
      <span>{t("convo.back")}</span>
    </Link>
  );

  if (detail.isPending) {
    return (
      <div className={`${PANE} flex flex-col gap-3 p-5`}>
        {back}
        <SkeletonRows label={t("common.loading")} rows={4} />
      </div>
    );
  }
  if (detail.isError) {
    return (
      <div className={`${PANE} flex flex-col gap-3 p-5`}>
        {back}
        <ErrorMessage error={detail.error} />
      </div>
    );
  }
  const { conversation, messages, open_draft: openDraft, recent_drafts: recent } = detail.data;
  const canManage = role === "owner" || role === "manager";
  const lastDraft = openDraft ?? recent[0] ?? null;
  const human = conversation.handling_mode === "human";
  const label = customerLabel(conversation, t);
  const accountName =
    accounts.data && accounts.data.length > 1
      ? accounts.data.find((a) => a.id === conversation.social_account_id)?.username ?? null
      : null;
  const windowClosed = windowMinutes !== null && windowMinutes <= 0;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <section aria-labelledby="conversation-title" className={`${PANE} overflow-hidden`}>
        {/* Who, how it is being handled, and the decisions about the conversation itself. */}
        <header className="flex flex-col gap-3 border-b border-border px-4 pt-3 pb-4 sm:px-5 lg:pt-4">
          {back}
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
            <div className="flex min-w-0 flex-1 basis-56 items-center gap-3">
              <CustomerAvatar label={label} size="lg" />
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <h2 id="conversation-title" title={label} className="truncate font-heading text-lg leading-snug font-semibold tracking-tight text-primary">
                    {label}
                  </h2>
                  {conversation.is_simulated ? <SimulatedBadge compact /> : null}
                </div>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-metadata text-secondary">
                  <span className={`inline-flex items-center gap-1.5 font-medium ${human ? "text-attention" : "text-action"}`}>
                    {human ? <HandIcon aria-hidden="true" className="text-sm" /> : <SparkIcon aria-hidden="true" className="text-sm" />}
                    {human ? t("convo.handledByYou") : t("convo.assistantHandles")}
                  </span>
                  {accountName ? <span className="truncate">@{accountName}</span> : null}
                  <WindowTimer endsAt={conversation.window_ends_at} />
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="ghost" disabled={suggest.isPending} onClick={() => suggest.mutate()} className="text-action">
                <SparkIcon aria-hidden="true" className="text-base" />
                {t("convo.suggest")}
              </Button>
              <Button variant="secondary" disabled={mode.isPending} onClick={() => mode.mutate(human ? "release" : "takeover")}>
                {human ? <SparkIcon aria-hidden="true" className="text-base text-action" /> : <HandIcon aria-hidden="true" className="text-base" />}
                {human ? t("convo.release") : t("convo.takeover")}
              </Button>
              {role === "owner" ? <MoreActions conversationId={conversationId} /> : null}
            </div>
          </div>
          {human ? (
            <p className="flex items-start gap-2.5 rounded-xl bg-attention-subtle px-3.5 py-2.5 text-metadata text-primary">
              <HandIcon aria-hidden="true" className="mt-0.5 shrink-0 text-base text-attention" />
              {t("convo.humanMode")}
            </p>
          ) : null}
          {mode.error ? <ErrorMessage error={mode.error} /> : null}
          {suggest.error ? <ErrorMessage error={suggest.error} /> : null}
        </header>

        <Thread messages={messages} canManage={canManage} />

        {lastDraft ? (
          <div className="border-t border-border p-3 sm:p-4">
            <DraftCard
              workspaceId={workspace.id}
              draft={lastDraft}
              onUseSuggestion={(text) => {
                setSeed(text);
                setComposing(true);
              }}
            />
          </div>
        ) : null}

        {/* Your own reply is a separate action from approving the assistant's. */}
        <div className="flex flex-col gap-3 border-t border-border p-3 sm:p-4">
          {windowClosed ? (
            <p className="flex items-start gap-2.5 rounded-xl bg-surface-subtle px-3.5 py-2.5 text-metadata text-secondary">
              <ClockIcon aria-hidden="true" className="mt-0.5 shrink-0 text-base text-danger" />
              <span>
                <strong className="font-semibold text-primary">{t("convo.window.closed")}.</strong> {t("convo.window.closedHint")}
              </span>
            </p>
          ) : null}
          {composing ? (
            <ReplyComposer
              key={seed ?? "none"}
              workspaceId={workspace.id}
              conversationId={conversationId}
              seed={seed}
              fromDraftId={lastDraft?.status === "needs_human" ? lastDraft.id : undefined}
            />
          ) : (
            <button
              type="button"
              onClick={() => setComposing(true)}
              className={`group flex min-h-12 w-full items-center gap-3 rounded-xl border border-border bg-surface px-4 text-left text-body text-secondary transition-colors hover:border-control/50 hover:bg-surface-subtle hover:text-primary ${FOCUS}`}
            >
              <PencilIcon aria-hidden="true" className="shrink-0 text-base text-action" />
              <span className="font-medium">{t("core.manualReply")}</span>
            </button>
          )}
        </div>
      </section>

      {conversation.social_account_id ? (
        <ConversationAgentWork account={conversation.social_account_id} conversation={conversationId} />
      ) : null}
    </div>
  );
}

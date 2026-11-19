import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AppError } from "@/api/errors";
import type { Workspace } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FactsUsed } from "@/components/FactsUsed";
import { Notice } from "@/components/Feedback";
import { SpinnerIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { TextAreaField } from "@/components/FormFields";
import { useFacts } from "@/features/knowledge/hooks";
import {
  MAX_MESSAGE_CHARS,
  hasPending,
  useResetTestChat,
  useSendTestMessage,
  useTestChat,
  type TestChatDraft,
  type TestChatTurn,
} from "./hooks";
import { buildSuggestions } from "./suggestions";

const DECISION_TONE = {
  auto: "success",
  automatic: "success",
  approval_required: "info",
  ask: "info",
  human_required: "attention",
  blocked: "danger",
} as const;
/** Say so when only a few test messages are left; stay quiet while there are plenty. */
const LOW_QUOTA = 5;

export function ControllerBadge({ mode, compact = false }: { mode?: "legacy" | "agent"; compact?: boolean }) {
  const { t } = useTranslation();
  const isAgent = mode === "agent";
  const size = compact ? "px-1.5 py-px text-[11px] leading-4" : "px-2 py-1 text-metadata";
  return (
    <span
      data-testid="controller-badge"
      data-controller={mode || "legacy"}
      className={`inline-flex shrink-0 items-center rounded-full font-semibold tracking-wide ring-1 ring-inset ${size} ${
        isAgent
          ? "bg-action/10 text-action ring-action/30"
          : "bg-surface-subtle text-secondary ring-border"
      }`}
    >
      {isAgent ? t("testChat.controller.agent") : t("testChat.controller.legacy")}
    </span>
  );
}

export function DecisionBadge({ decision }: { decision: TestChatDraft["decision"] }) {
  const { t } = useTranslation();
  const isAuto = decision === "auto" || decision === "automatic";
  const isBlocked = decision === "blocked" || decision === "human_required";
  const style = isAuto
    ? "bg-success-subtle text-success ring-success/30"
    : isBlocked
      ? "bg-danger-subtle text-danger ring-danger/30"
      : "bg-info-subtle text-info ring-info/30";

  const labelKey = isAuto
    ? "testChat.badge.autoSend"
    : isBlocked
      ? "testChat.badge.blocked"
      : "testChat.badge.needsApproval";

  return (
    <span
      data-testid="decision-badge"
      data-decision={decision}
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-metadata font-semibold tracking-wide ring-1 ring-inset ${style}`}
    >
      {t(labelKey)}
    </span>
  );
}

/** The draft text, with the ⟦ ⟧ markers the server puts around unverified values shown as highlights. */
function MarkedText({ text }: { text: string }) {
  const parts = text.split(/(⟦[^⟧]*⟧)/);
  return (
    <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">
      {parts.map((part, index) =>
        part.startsWith("⟦") ? (
          <mark key={index} className="rounded-sm bg-attention-subtle px-1 font-semibold text-attention">
            {part.slice(1, part.endsWith("⟧") ? -1 : undefined)}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </p>
  );
}

/** Plain-language sentences for the policy reason codes, each once, with a generic fallback for a new code. */
function useReasonSentences(reasons: readonly string[]): string[] {
  const { t, i18n } = useTranslation();
  const sentences = reasons.map((code) => (i18n.exists(`testChat.reason.${code}`) ? t(`testChat.reason.${code}`) : t("testChat.reasonFallback")));
  return [...new Set(sentences)];
}

function DecisionNote({ draft }: { draft: TestChatDraft }) {
  const { t } = useTranslation();
  const sentences = useReasonSentences(draft.reasons);
  return (
    <div data-testid="decision" data-decision={draft.decision} className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <DecisionBadge decision={draft.decision} />
      </div>
      <Notice title={t(`testChat.decision.${draft.decision}.title`)} tone={DECISION_TONE[draft.decision]}>
        <p>{t(`testChat.decision.${draft.decision}.detail`)}</p>
        {sentences.length > 0 ? (
          <div className="mt-2">
            <p className="text-metadata font-semibold">{t("testChat.reasonsTitle")}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {sentences.map((sentence) => (
                <li key={sentence}>{sentence}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </Notice>
    </div>
  );
}

function Reply({ turn, timeZone }: { turn: TestChatTurn; timeZone: string }) {
  const { t } = useTranslation();
  const draft = turn.draft;
  return (
    <div className="flex w-full min-w-0 max-w-[96%] flex-col gap-3 self-start rounded-2xl rounded-bl-md border border-border bg-surface p-3.5" data-testid="assistant-reply">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-metadata font-semibold text-secondary">{t("testChat.assistantLabel")}</span>
        <ControllerBadge mode={turn.controller_mode} compact />
        <SimulatedBadge compact />
      </div>
      {draft === null ? (
        <p role="status" className="flex items-center gap-2 text-body text-secondary">
          <SpinnerIcon className="shrink-0 motion-safe:animate-spin" />
          {t("testChat.writing")}
        </p>
      ) : (
        <>
          {draft.text ? (
            <p className="whitespace-pre-wrap text-body text-primary [overflow-wrap:anywhere]" data-testid="reply-text">{draft.text}</p>
          ) : (
            <p className="text-body text-secondary">{t("testChat.noReply")}</p>
          )}
          <DecisionNote draft={draft} />
          {!draft.text && draft.suggestion_text ? (
            <div className="rounded-control border border-dashed border-border bg-surface-subtle p-3" data-testid="suggestion">
              <p className="text-metadata font-semibold text-secondary">{t("testChat.suggestionTitle")}</p>
              <div className="mt-1 text-body text-primary">
                <MarkedText text={draft.suggestion_text} />
              </div>
              {draft.suggestion_text.includes("⟦") ? <p className="mt-1 text-metadata text-secondary">{t("testChat.suggestionHint")}</p> : null}
            </div>
          ) : null}
          <FactsUsed facts={draft.facts_used} timeZone={timeZone} />
        </>
      )}
    </div>
  );
}

function Turn({ turn, timeZone }: { turn: TestChatTurn; timeZone: string }) {
  const { t } = useTranslation();
  return (
    <li className="flex min-w-0 flex-col gap-2" data-testid="turn">
      <div className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-action px-3.5 py-2.5 text-body text-on-action [overflow-wrap:anywhere]">
        <span className="sr-only">{t("testChat.customerLabel")}: </span>
        {turn.customer_text}
      </div>
      <Reply turn={turn} timeZone={timeZone} />
    </li>
  );
}

function RateLimited({ error }: { error: AppError }) {
  const { t } = useTranslation();
  const seconds = Number(error.params.retry_after);
  const minutes = Number.isFinite(seconds) && seconds > 0 ? Math.max(1, Math.ceil(seconds / 60)) : null;
  return (
    <Notice title={t("testChat.rateLimited.title")} tone="attention" live="polite">
      <p>{t("testChat.rateLimited.body")}</p>
      {minutes ? <p>{t("testChat.rateLimited.retry", { minutes })}</p> : null}
    </Notice>
  );
}

/**
 * "Try your assistant": the owner types as a customer and sees the reply the assistant would
 * give, the decision with a plain reason, and the facts it used. Everything shown is simulated and
 * nothing is sent. Takes the workspace as a prop so the wizard can use it before the workspace
 * context exists.
 */
export function TestChat({ workspace }: { workspace: Workspace }) {
  const { t, i18n } = useTranslation();
  const chat = useTestChat(workspace.id);
  const facts = useFacts(workspace.id);
  const send = useSendTestMessage(workspace.id);
  const reset = useResetTestChat(workspace.id);
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const seen = useRef<number | null>(null);

  const items = useMemo(() => chat.data?.items ?? [], [chat.data]);
  const pending = hasPending(chat.data);
  const remaining = chat.data ? Math.min(chat.data.remaining_this_hour, chat.data.remaining_today) : null;
  const outOfMessages = remaining === 0;
  const suggestions = useMemo(
    () =>
      buildSuggestions({
        category: workspace.business_category,
        locale: workspace.default_locale,
        facts: facts.data ?? [],
        t: i18n.getFixedT(workspace.default_locale),
      }),
    [workspace.business_category, workspace.default_locale, facts.data, i18n],
  );
  const busy = pending || send.isPending || outOfMessages;

  // Bring a new message into view, but not when the existing chat first loads.
  useEffect(() => {
    if (!chat.data) return;
    const count = items.length + (pending ? 1 : 0);
    if (seen.current !== null && count > seen.current) end.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
    seen.current = count;
  }, [chat.data, items.length, pending]);

  function submit(message: string) {
    const body = message.trim();
    if (!body || body.length > MAX_MESSAGE_CHARS || busy) return;
    send.mutate(body, { onSuccess: () => setText("") });
  }
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(text);
  }

  const rateLimited = send.error instanceof AppError && send.error.code === "TEST_CHAT_RATE_LIMITED" ? send.error : null;
  const quotaNote =
    remaining === null
      ? null
      : outOfMessages
        ? t("testChat.quota.none")
        : chat.data && remaining <= LOW_QUOTA
          ? chat.data.remaining_this_hour <= chat.data.remaining_today
            ? t("testChat.quota.hour", { count: chat.data.remaining_this_hour })
            : t("testChat.quota.day", { count: chat.data.remaining_today })
          : null;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Notice title={t("testChat.simulatedNote")} tone="info">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <ControllerBadge mode={chat.data?.controller_mode} />
          <SimulatedBadge />
        </div>
        <p>{t("testChat.intro")}</p>
      </Notice>

      {chat.error ? (
        <div className="flex min-w-0 flex-col items-start gap-3">
          <ErrorMessage error={chat.error} />
          <Button variant="secondary" onClick={() => void chat.refetch()}>{t("testChat.retry")}</Button>
        </div>
      ) : chat.isPending ? (
        <p role="status" className="text-body text-secondary">{t("testChat.loading")}</p>
      ) : (
        <section aria-label={t("testChat.title")} className="flex min-w-0 flex-col gap-4 rounded-panel border border-border bg-surface-subtle p-3 sm:p-4">
          {items.length === 0 ? (
            <div className="flex min-w-0 flex-col gap-3 px-1 py-3 text-center" data-testid="test-chat-empty">
              <h3 className="text-section font-bold tracking-tight text-primary">{t("testChat.emptyTitle")}</h3>
              <p className="text-body text-secondary">{t("testChat.emptyHint")}</p>
            </div>
          ) : (
            <ol aria-live="polite" className="flex min-w-0 flex-col gap-5">
              {items.map((turn) => (
                <Turn key={turn.id} turn={turn} timeZone={workspace.timezone} />
              ))}
            </ol>
          )}
          <div ref={end} />

          {items.length === 0 ? (
            <div data-testid="suggestions">
              <p className="mb-2 text-metadata font-semibold text-secondary">{t("testChat.suggestionsTitle")}</p>
              <ul className="flex min-w-0 flex-col gap-2">
                {suggestions.map((question) => (
                  <li key={question}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => submit(question)}
                      className="min-h-11 w-full rounded-control border border-border bg-surface px-3.5 py-2 text-left text-body text-primary transition-colors enabled:hover:bg-assistant focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {question}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {rateLimited ? <RateLimited error={rateLimited} /> : send.error ? <ErrorMessage error={send.error} /> : null}
          {reset.error ? <ErrorMessage error={reset.error} /> : null}

          <form onSubmit={onSubmit} className="flex min-w-0 flex-col gap-2" noValidate>
            <TextAreaField
              label={t("testChat.messageLabel")}
              name="test_message"
              rows={2}
              maxLength={MAX_MESSAGE_CHARS}
              placeholder={t("testChat.placeholder")}
              hint={t("testChat.counter", { count: text.length, max: MAX_MESSAGE_CHARS })}
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  submit(text);
                }
              }}
            />
            {quotaNote ? <p role="status" data-testid="quota" className="text-metadata text-secondary">{quotaNote}</p> : null}
            <div className="flex flex-wrap gap-3">
              <Button type="submit" className="min-w-0 flex-1" pending={send.isPending} disabled={busy || text.trim().length === 0}>
                {send.isPending ? t("testChat.sending") : t("testChat.send")}
              </Button>
              {items.length > 0 ? (
                <Button variant="secondary" pending={reset.isPending} onClick={() => reset.mutate()}>
                  {reset.isPending ? t("testChat.resetting") : t("testChat.reset")}
                </Button>
              ) : null}
            </div>
          </form>
        </section>
      )}
    </div>
  );
}

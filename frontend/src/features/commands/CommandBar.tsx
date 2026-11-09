import { useDirtyForm } from "@/components/DirtyForms";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SendIcon, SparkIcon, SpinnerIcon, XIcon } from "@/components/icons";
import { useMeta } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ClarificationChips } from "./ClarificationChips";
import { CommandResultCard } from "./CommandResultCard";
import { ConfirmationCard } from "./ConfirmationCard";
import { useCommand, useSubmitCommand } from "./hooks";

const MAX_CHARS = 1000;

function CommandPanel({ commandId, onDismiss }: { commandId: string; onDismiss: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const command = useCommand(workspace.id, commandId);
  const data = command.data;

  let body: ReactNode;
  if (command.isError) {
    body = <ErrorMessage error={command.error} />;
  } else if (!data || data.status === "interpreting" || data.status === "executing") {
    body = (
      <div role="status" className="flex flex-col gap-3 py-1">
        <div className="inline-flex items-center gap-2.5 font-medium text-primary">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-action/10 text-action">
            <SpinnerIcon className="animate-spin text-lg" />
          </div>
          <span className="font-heading text-sm font-semibold text-primary">{t("command.interpreting")}</span>
        </div>
        <div className="flex flex-col gap-2 max-w-md pt-0.5">
          <div className="h-2.5 w-3/4 rounded-full bg-surface-subtle animate-pulse" />
          <div className="h-2.5 w-1/2 rounded-full bg-surface-subtle animate-pulse" />
        </div>
      </div>
    );
  } else if (data.status === "needs_clarification") {
    body = <ClarificationChips command={data} />;
  } else if (data.status === "awaiting_confirmation" && data.approval?.status === "pending") {
    body = <ConfirmationCard command={data} />;
  } else if (data.status === "awaiting_confirmation") {
    // The approval is no longer pending (expired a moment ago): the next poll shows the result.
    body = (
      <div role="status" className="inline-flex items-center gap-2.5 font-medium text-primary">
        <SpinnerIcon className="animate-spin text-lg text-action" />
        <span>{t("command.interpreting")}</span>
      </div>
    );
  } else {
    body = <CommandResultCard command={data} />;
  }

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-action/20 bg-gradient-to-b from-surface via-surface to-surface-subtle/30 p-5 sm:p-6 shadow-sm border-l-4 border-l-action transition-all"
      data-testid="command-panel"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border/70 pb-3.5 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold uppercase tracking-wider text-secondary shrink-0">
            {t("command.yourCommand")}:
          </span>
          <span className="rounded-lg bg-surface-subtle border border-border/80 px-2.5 py-1 text-sm font-semibold text-primary break-words truncate max-w-md sm:max-w-xl">
            {data?.raw_text ?? ""}
          </span>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="inline-flex min-h-9 items-center gap-1.5 shrink-0 rounded-lg border border-border/80 bg-surface px-3 py-1 text-xs font-semibold text-secondary transition-all hover:bg-surface-subtle hover:text-primary hover:border-border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus cursor-pointer"
        >
          <XIcon className="text-sm" />
          <span>{t("command.dismiss")}</span>
        </button>
      </div>
      <div aria-live="polite">{body}</div>
    </div>
  );
}

/**
 * The natural-language command center on Home.
 * Layout: The modern input bar stays on TOP; the assistant answer appears at the BOTTOM.
 */
export function CommandBar() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const meta = useMeta();
  const submit = useSubmitCommand(workspace.id);
  const [text, setText] = useState("");
  useDirtyForm(text.trim().length > 0);
  const [activeId, setActiveId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || submit.isPending) return;
    try {
      const command = await submit.mutateAsync(trimmed);
      setActiveId(command.id);
      setText("");
    } catch {
      // The error is shown below; the text stays so the owner can retry.
    }
  };

  const handleSuggestionClick = (query: string) => {
    setText(query);
    inputRef.current?.focus();
  };

  const suggestions = [
    t("command.suggest.update_price"),
    t("command.suggest.ask_price"),
    t("command.suggest.activity"),
  ]
    .map((s) => s.replace(/^[“”"']+|[“”"']+$/g, "").trim())
    .filter(Boolean);

  return (
    <div className="flex flex-col gap-4" data-testid="assistant-module">
      {/* 1. TOP: Elegant Assistant Command Center & Input Bar */}
      <form
        onSubmit={onSubmit}
        className="relative overflow-hidden rounded-2xl border border-action/20 bg-gradient-to-b from-surface via-surface to-surface-subtle/40 p-5 sm:p-6 shadow-sm transition-all"
      >
        {/* Soft decorative background ambient glow */}
        <div
          className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-action/5 blur-3xl"
          aria-hidden="true"
        />

        {/* Header row: Sparkle emblem badge, Title, Status pill, Keyboard hint */}
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-action/10 text-action ring-1 ring-action/20 shadow-2xs">
              <SparkIcon className="text-xl" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-heading text-base sm:text-lg font-bold text-primary tracking-tight">
                  {t("core.requestTitle")}
                </h2>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-action/10 px-2.5 py-0.5 text-2xs font-semibold text-action">
                  <span className="h-1.5 w-1.5 rounded-full bg-action animate-pulse" />
                  {meta.data?.llm_mode === "fake" ? t("aiMode.offline") : "AI Assistant"}
                </span>
              </div>
            </div>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1 rounded-md border border-border/80 bg-surface-subtle px-2 py-0.5 text-2xs font-medium text-secondary">
            <span>{t("common.enter")}</span>
          </span>
        </div>

        {/* Input container */}
        <div className="flex flex-col gap-2.5">
          <div className="group relative flex items-center rounded-xl border border-border bg-surface px-3 py-1 shadow-2xs transition-all duration-200 focus-within:border-action focus-within:ring-2 focus-within:ring-action/15 hover:border-action/40">
            <label htmlFor="command-input" className="sr-only">
              {t("command.label")}
            </label>
            <input
              ref={inputRef}
              id="command-input"
              value={text}
              onChange={(event) => setText(event.target.value)}
              maxLength={MAX_CHARS}
              placeholder={t("command.placeholder")}
              enterKeyHint="send"
              autoComplete="off"
              className="min-h-12 min-w-0 flex-1 bg-transparent px-2 py-2 text-form text-primary placeholder:text-secondary/70 focus:outline-none"
            />
            {text ? (
              <button
                type="button"
                onClick={() => {
                  setText("");
                  inputRef.current?.focus();
                }}
                className="p-1.5 text-secondary hover:text-primary transition-colors rounded-md mr-1.5 cursor-pointer"
                aria-label={t("common.clear")}
              >
                <XIcon className="text-sm" />
              </button>
            ) : null}
            <Button
              type="submit"
              disabled={!text.trim() || submit.isPending}
              aria-label={t("command.send")}
              className="min-h-10 shrink-0 rounded-lg px-4 shadow-xs font-semibold text-sm transition-all active:scale-95 disabled:opacity-40"
            >
              <SendIcon className="text-base" />
              <span className="hidden sm:inline">{t("command.send")}</span>
            </Button>
          </div>

          {/* Quick Suggestions Chips */}
          {suggestions.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <span className="text-2xs font-semibold uppercase tracking-wider text-secondary/80 mr-1 hidden sm:inline">
                {t("command.unsupported.suggestionsTitle")}
              </span>
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => handleSuggestionClick(suggestion)}
                  className="inline-flex items-center rounded-full border border-border/80 bg-surface px-2.5 py-1 text-2xs font-medium text-secondary transition-all hover:border-action/40 hover:bg-action/5 hover:text-action cursor-pointer active:scale-95"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}

          {/* Helper hint */}
          <p className="px-1 text-metadata text-secondary">
            {t("command.hint")}
            {meta.data?.llm_mode === "fake" ? ` · ${t("aiMode.offline")}` : ""}
          </p>
        </div>
      </form>

      {/* 2. Error message if sending fails */}
      {submit.error ? <ErrorMessage error={submit.error} /> : null}

      {/* 3. BOTTOM: Elegant Assistant Response & Status Panel */}
      {activeId ? (
        <CommandPanel key={activeId} commandId={activeId} onDismiss={() => setActiveId(null)} />
      ) : null}
    </div>
  );
}

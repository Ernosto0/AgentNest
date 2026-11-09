import { useDirtyForm } from "@/components/DirtyForms";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SendIcon, SparkIcon, SpinnerIcon, XIcon } from "@/components/icons";
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
    <div className="rounded-xl border border-border bg-surface p-4 sm:p-5" data-testid="command-panel">
      <div className="mb-3 flex items-start justify-between gap-3 border-b border-border pb-3">
        <p className="min-w-0 text-metadata text-secondary">
          <span className="font-semibold uppercase tracking-wider">{t("command.yourCommand")}:</span>{" "}
          <span className="font-medium text-primary [overflow-wrap:anywhere]">{data?.raw_text ?? ""}</span>
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="-my-2 inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-control px-2.5 text-metadata font-semibold text-secondary transition-colors hover:bg-surface-subtle hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
 * The natural-language request entry, embedded in the assistant panel on Today.
 * The input stays on top; the interpreted command and its result appear below it.
 */
export function CommandBar() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
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
    <div className="flex flex-col gap-3" data-testid="assistant-module">
      <form onSubmit={onSubmit} className="flex flex-col gap-2">
        <div className="flex items-center gap-1 rounded-2xl border border-action/15 bg-surface p-1.5 pl-2.5 shadow-[0_1px_2px_rgb(18_31_24/0.05),0_4px_16px_-8px_rgb(23_83_56/0.18)] transition-[border-color,box-shadow] duration-150 hover:border-action/35 focus-within:border-action focus-within:ring-4 focus-within:ring-action/10">
          <label htmlFor="command-input" className="sr-only">
            {t("command.label")}
          </label>
          <SparkIcon aria-hidden="true" className="shrink-0 text-lg text-action" />
          <input
            ref={inputRef}
            id="command-input"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={MAX_CHARS}
            placeholder={t("command.placeholder")}
            enterKeyHint="send"
            autoComplete="off"
            aria-describedby="command-hint"
            className="min-h-11 min-w-0 flex-1 bg-transparent px-2 text-form text-primary placeholder:text-secondary/70 focus:outline-none"
          />
          {text ? (
            <button
              type="button"
              onClick={() => {
                setText("");
                inputRef.current?.focus();
              }}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-surface-subtle hover:text-primary focus-visible:outline-2 focus-visible:outline-focus"
              aria-label={t("common.clear")}
            >
              <XIcon className="text-sm" />
            </button>
          ) : null}
          <Button
            type="submit"
            variant={text.trim() ? "primary" : "secondary"}
            disabled={!text.trim() || submit.isPending}
            aria-label={t("command.send")}
            className="shrink-0 rounded-xl px-3 sm:px-4"
          >
            {submit.isPending ? <SpinnerIcon className="motion-safe:animate-spin" /> : <SendIcon className="text-base" />}
            <span className="hidden sm:inline">{t("command.send")}</span>
          </Button>
        </div>

        {suggestions.length > 0 ? (
          <div role="group" aria-label={t("command.unsupported.suggestionsTitle")} className="flex flex-wrap items-center gap-1.5 px-0.5">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => handleSuggestionClick(suggestion)}
                className="inline-flex min-h-10 items-center rounded-full bg-surface/55 px-3 text-xs font-medium text-primary/85 ring-1 ring-action/10 transition-colors ring-inset hover:bg-surface hover:text-action hover:ring-action/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-[0.98] sm:min-h-8"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}

        <p id="command-hint" className="sr-only">
          {t("command.hint")}
        </p>
      </form>

      {submit.error ? <ErrorMessage error={submit.error} /> : null}

      {activeId ? <CommandPanel key={activeId} commandId={activeId} onDismiss={() => setActiveId(null)} /> : null}
    </div>
  );
}

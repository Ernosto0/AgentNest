import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ValidationIssue } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useSubmitReply } from "./hooks";

const MAX_REPLY_CHARS = 1000;

/** Write your own reply. Numbers that are not verified values come back as warnings, never blocks. */
export function ReplyComposer({
  workspaceId,
  conversationId,
  seed,
  fromDraftId,
  disabled,
}: {
  workspaceId: string;
  conversationId: string;
  /** Text to start from (the assistant's suggestion for a conversation handed over to you). */
  seed?: string | null;
  fromDraftId?: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(seed ?? "");
  const [warnings, setWarnings] = useState<ValidationIssue[]>([]);
  const submit = useSubmitReply(workspaceId, conversationId);

  const send = () =>
    submit.mutate(
      { text, fromDraftId },
      {
        onSuccess: (result) => {
          setWarnings(result.warnings);
          setText("");
        },
      },
    );

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (!disabled && !submit.isPending && text.trim()) {
        send();
      }
    }
  };

  return (
    <form
      className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-4 md:p-5 shadow-xs"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim()) send();
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <label htmlFor="reply-text" className="text-form font-semibold text-primary">
          {t("convo.composer.label")}
        </label>
        <span
          className={`text-metadata tabular-nums font-mono ${
            text.length >= MAX_REPLY_CHARS
              ? "text-danger font-semibold"
              : text.length > MAX_REPLY_CHARS * 0.9
                ? "text-attention font-medium"
                : "text-secondary"
          }`}
        >
          {text.length} / {MAX_REPLY_CHARS}
        </span>
      </div>
      <textarea
        id="reply-text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={3}
        maxLength={MAX_REPLY_CHARS}
        disabled={disabled}
        className="min-h-28 w-full rounded-control border border-control bg-surface p-3 text-form text-primary placeholder:text-secondary/60 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-60"
      />
      {warnings.length > 0 ? (
        <ul
          className="rounded-control bg-attention-subtle p-3 text-body text-attention border border-attention/30"
          data-testid="reply-warnings"
        >
          {warnings.map((issue, index) => (
            <li key={`${issue.code}-${index}`}>
              {issue.matches_verified
                ? t("convo.composer.warningVerified", { text: issue.text })
                : t("convo.composer.warning", { text: issue.text })}
            </li>
          ))}
        </ul>
      ) : null}
      {submit.error ? <ErrorMessage error={submit.error} /> : null}
      <div className="flex flex-wrap items-center justify-end gap-3 pt-1">
        <Button type="submit" disabled={disabled || submit.isPending || !text.trim()}>
          {submit.isPending ? t("convo.composer.sending") : t("convo.composer.send")}
        </Button>
      </div>
    </form>
  );
}

import { useDirtyForm } from "@/components/DirtyForms";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ValidationIssue } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, SendIcon } from "@/components/icons";
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
  useDirtyForm(text.trim().length > 0);
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

  const hasText = text.trim().length > 0;
  return (
    <form
      className="flex flex-col gap-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        if (hasText) send();
      }}
    >
      <label htmlFor="reply-text" className="text-body font-semibold text-primary">
        {t("convo.composer.label")}
      </label>
      {/* One framed field: the text, then its limit and the send action on the same surface. */}
      <div className="flex flex-col rounded-xl border border-control/50 bg-surface transition-colors focus-within:border-action focus-within:ring-2 focus-within:ring-action/15 has-[textarea:disabled]:opacity-60">
        <textarea
          id="reply-text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          maxLength={MAX_REPLY_CHARS}
          disabled={disabled}
          aria-describedby="reply-limit"
          className="min-h-24 w-full resize-y rounded-t-xl border-0 bg-transparent px-3.5 pt-3 pb-1 text-form text-primary placeholder:text-secondary/60 focus:outline-none disabled:cursor-not-allowed"
        />
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-2 pt-1 pb-2 pl-3.5">
          <span id="reply-limit" className="flex items-center gap-3 text-xs text-secondary">
            <span
              className={`tabular-nums ${
                text.length >= MAX_REPLY_CHARS
                  ? "font-semibold text-danger"
                  : text.length > MAX_REPLY_CHARS * 0.9
                    ? "font-medium text-attention"
                    : ""
              }`}
            >
              {text.length} / {MAX_REPLY_CHARS}
            </span>
            {hasText ? <span className="hidden sm:inline">{t("convo.composer.shortcut")}</span> : null}
          </span>
          <Button type="submit" variant={hasText ? "primary" : "secondary"} disabled={disabled || submit.isPending || !hasText} className="min-h-10">
            <SendIcon aria-hidden="true" className="text-base" />
            {submit.isPending ? t("convo.composer.sending") : t("convo.composer.send")}
          </Button>
        </div>
      </div>
      {warnings.length > 0 ? (
        <ul className="flex flex-col gap-1 rounded-xl bg-attention-subtle px-3.5 py-2.5 text-body text-attention" data-testid="reply-warnings">
          {warnings.map((issue, index) => (
            <li key={`${issue.code}-${index}`} className="flex items-start gap-2">
              <AlertIcon aria-hidden="true" className="mt-1 shrink-0 text-sm" />
              {issue.matches_verified
                ? t("convo.composer.warningVerified", { text: issue.text })
                : t("convo.composer.warning", { text: issue.text })}
            </li>
          ))}
        </ul>
      ) : null}
      {submit.error ? <ErrorMessage error={submit.error} /> : null}
    </form>
  );
}

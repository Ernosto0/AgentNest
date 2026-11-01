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

  return (
    <form
      className="flex flex-col gap-2.5 rounded-xl border border-slate-200/90 bg-white p-4 shadow-2xs"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim()) send();
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <label htmlFor="reply-text" className="text-sm font-semibold text-slate-900">
          {t("convo.composer.label")}
        </label>
        <span className="text-xs text-slate-500">
          {text.length} / {MAX_REPLY_CHARS}
        </span>
      </div>
      <textarea
        id="reply-text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={3}
        maxLength={MAX_REPLY_CHARS}
        disabled={disabled}
        className="min-h-24 w-full rounded-lg border border-slate-300 p-3 text-base text-slate-900 placeholder-slate-400 focus-visible:outline-2 focus-visible:outline-indigo-600"
      />
      {warnings.length > 0 ? (
        <ul className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-300" data-testid="reply-warnings">
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
      <div className="flex items-center justify-end">
        <Button type="submit" disabled={disabled || submit.isPending || !text.trim()}>
          {submit.isPending ? t("convo.composer.sending") : t("convo.composer.send")}
        </Button>
      </div>
    </form>
  );
}

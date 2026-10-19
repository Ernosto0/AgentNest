import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ValidationIssue } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useSubmitReply } from "./hooks";

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
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim()) send();
      }}
    >
      <label htmlFor="reply-text" className="text-sm font-medium">
        {t("convo.composer.label")}
      </label>
      <textarea
        id="reply-text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={3}
        maxLength={1000}
        disabled={disabled}
        className="min-h-24 w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
      />
      {warnings.length > 0 ? (
        <ul className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" data-testid="reply-warnings">
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
      <div>
        <Button type="submit" disabled={disabled || submit.isPending || !text.trim()}>
          {submit.isPending ? t("convo.composer.sending") : t("convo.composer.send")}
        </Button>
      </div>
    </form>
  );
}

import { useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SendIcon, SpinnerIcon } from "@/components/icons";
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
      <p role="status" className="inline-flex items-center gap-2 font-medium text-slate-700">
        <SpinnerIcon className="animate-spin text-xl" />
        {t("command.interpreting")}
      </p>
    );
  } else if (data.status === "needs_clarification") {
    body = <ClarificationChips command={data} />;
  } else if (data.status === "awaiting_confirmation" && data.approval?.status === "pending") {
    body = <ConfirmationCard command={data} />;
  } else if (data.status === "awaiting_confirmation") {
    // The approval is no longer pending (expired a moment ago): the next poll shows the result.
    body = <p role="status">{t("command.interpreting")}</p>;
  } else {
    body = <CommandResultCard command={data} />;
  }

  return (
    <Card className="flex flex-col gap-3" data-testid="command-panel">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-sm text-slate-600">
          {t("command.yourCommand")}:{" "}
          <span className="font-medium break-words text-slate-900">{data?.raw_text ?? ""}</span>
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="min-h-11 shrink-0 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600"
        >
          {t("command.dismiss")}
        </button>
      </div>
      <div aria-live="polite">{body}</div>
    </Card>
  );
}

/**
 * The natural-language command bar on Home. On phones it sticks above the tab bar so it stays
 * in reach; the answer, question or confirmation appears above it.
 */
export function CommandBar() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const meta = useMeta();
  const submit = useSubmitCommand(workspace.id);
  const [text, setText] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);

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

  return (
    <>
      {activeId ? <CommandPanel key={activeId} commandId={activeId} onDismiss={() => setActiveId(null)} /> : null}
      {submit.error ? <ErrorMessage error={submit.error} /> : null}
      {/* Fixed above the tab bar on phones (3.5rem tall); an ordinary block on desktop. */}
      <form
        onSubmit={onSubmit}
        className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-10 border-t border-slate-200 bg-white/95 px-4 py-2 backdrop-blur md:static md:z-auto md:border-0 md:bg-transparent md:p-0"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-1">
          <div className="flex items-center gap-2">
            <label htmlFor="command-input" className="sr-only">
              {t("command.label")}
            </label>
            <input
              id="command-input"
              value={text}
              onChange={(event) => setText(event.target.value)}
              maxLength={MAX_CHARS}
              placeholder={t("command.placeholder")}
              enterKeyHint="send"
              autoComplete="off"
              className="min-h-11 min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
            />
            <Button type="submit" disabled={!text.trim() || submit.isPending} aria-label={t("command.send")}>
              <SendIcon className="text-xl" />
              <span className="hidden sm:inline">{t("command.send")}</span>
            </Button>
          </div>
          <p className="text-xs text-slate-600">
            {t("command.hint")}
            {meta.data?.llm_mode === "fake" ? ` · ${t("aiMode.offline")}` : ""}
          </p>
        </div>
      </form>
    </>
  );
}

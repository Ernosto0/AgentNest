import { useTranslation } from "react-i18next";
import type { Command } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useAnswerClarification, useCancelCommand } from "./hooks";
import { messageSuffix } from "./messages";

/**
 * "Which one did you mean?" as tappable chips. Only the options the server offered can be
 * chosen; nothing changes until a choice and then a confirmation.
 */
export function ClarificationChips({ command }: { command: Command }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const answer = useAnswerClarification(workspace.id);
  const cancel = useCancelCommand(workspace.id);
  const clarification = command.clarification;
  if (!clarification) return null;

  const params = clarification.params as { raw?: string | null; label?: string; count?: number };
  const question = messageSuffix(clarification.question_key); // "command.clarify.which_fact"
  const key = question.replace(/^clarify\./, "");
  const asked = t(`command.clarify.${key === "which_fact" && params.raw ? "which_fact_value" : key}`, {
    raw: params.raw ?? "",
    label: params.label ?? "",
    count: params.count ?? 0,
  });
  const busy = answer.isPending || cancel.isPending;

  return (
    <section
      aria-label={asked}
      className="flex flex-col gap-3.5 rounded-xl border border-action/20 bg-surface p-4 sm:p-5 shadow-2xs"
      data-testid="clarification"
    >
      <div className="flex items-center gap-2">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-action/10 text-action text-xs font-bold">
          ?
        </div>
        <p className="font-heading font-semibold text-primary">{asked}</p>
      </div>
      <ul className="flex flex-wrap gap-2">
        {clarification.options.map((option) => (
          <li key={option.id}>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => answer.mutate({ commandId: command.id, optionId: option.id })}
              data-option={option.id}
              className="rounded-lg border border-border bg-surface hover:border-action hover:bg-action/5 hover:text-action transition-all cursor-pointer font-medium"
            >
              {option.label}
            </Button>
          </li>
        ))}
      </ul>
      {answer.error ? <ErrorMessage error={answer.error} /> : null}
      <div className="pt-0.5">
        <Button variant="ghost" disabled={busy} onClick={() => cancel.mutate(command.id)} className="text-secondary hover:text-primary">
          {t("command.clarify.cancel")}
        </Button>
      </div>
    </section>
  );
}

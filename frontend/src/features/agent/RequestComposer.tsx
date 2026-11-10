import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { useDirtyForm } from "@/components/DirtyForms";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CheckIcon, InfoIcon, SendIcon, SparkIcon } from "@/components/icons";
import { newRequestId } from "@/features/commands/hooks";
import { FOCUS } from "./AgentParts";
import { useSubmitAgentTask, type Schema } from "./hooks";

const MAX = 4000;
const SUGGESTIONS = ["post", "story", "faq"] as const;

/**
 * The owner's command surface. A request is recorded and queued, never answered inline: the
 * assistant works asynchronously, so feedback is "recorded", with a link to the request's progress.
 */
export function RequestComposer({
  ws,
  accountId,
  data,
  connected,
  onSubmitted,
}: {
  ws: string;
  accountId: string;
  data: Schema<"AgentOverview">;
  connected: boolean;
  onSubmitted?: (taskId: string) => void;
}) {
  const { t } = useTranslation();
  const submit = useSubmitAgentTask(ws, accountId);
  const [text, setText] = useState("");
  const [requestId, setRequestId] = useState(newRequestId);
  const input = useRef<HTMLTextAreaElement>(null);
  const inputId = useId();
  const hintId = useId();
  const blockedId = useId();
  useDirtyForm(text.trim().length > 0);

  const blocked = !connected
    ? "connection"
    : data.controller_mode !== "agent"
      ? "legacy"
      : data.state !== "active"
        ? data.state === "paused"
          ? "paused"
          : "inactive"
        : null;
  const canSend = !blocked && text.trim().length > 0 && !submit.isPending;

  const edit = (value: string) => {
    if (submit.isSuccess || submit.isError) submit.reset();
    setText(value);
    setRequestId(newRequestId());
  };
  const send = () => {
    if (!canSend) return;
    submit.mutate(
      { text, client_request_id: requestId },
      {
        onSuccess: (task) => {
          setText("");
          setRequestId(newRequestId());
          onSubmitted?.(task.id);
        },
      },
    );
  };

  return (
    <section aria-labelledby="agent-composer-title" className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-surface p-4 sm:p-5">
      <div className="flex min-w-0 items-start gap-3">
        <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-action text-base text-on-action">
          <SparkIcon />
        </span>
        <div className="min-w-0">
          <h2 id="agent-composer-title" className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {t("core.requestTitle")}
          </h2>
          <p id={hintId} className="text-metadata text-secondary">{t("agent.taskHint")}</p>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className={`flex min-w-0 flex-col rounded-xl border bg-surface transition-[border-color,box-shadow] duration-150 focus-within:border-action focus-within:shadow-[0_0_0_3px_rgb(23_83_56/0.12)] ${
          submit.isError ? "border-danger" : "border-control/50 hover:border-control"
        }`}
      >
        <label htmlFor={inputId} className="sr-only">{t("agent.taskText")}</label>
        <textarea
          ref={input}
          id={inputId}
          aria-describedby={[hintId, blocked ? blockedId : ""].filter(Boolean).join(" ")}
          className="field-sizing-content max-h-72 min-h-24 w-full resize-none rounded-t-xl bg-transparent px-4 pt-3.5 pb-2 text-primary placeholder:text-secondary/80 focus:outline-none"
          rows={3}
          value={text}
          maxLength={MAX}
          disabled={submit.isPending}
          placeholder={t("agent.composer.placeholder")}
          onChange={(e) => edit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2 px-3 pb-3 pl-4">
          <div className="flex min-w-0 flex-1 basis-40 items-center gap-3 text-xs text-secondary">
            {blocked ? (
              <span id={blockedId} className="inline-flex items-start gap-1.5 font-medium text-attention">
                <InfoIcon aria-hidden="true" className="mt-0.5 shrink-0" />
                {t(`agent.composer.blocked.${blocked}`)}
              </span>
            ) : (
              <span className="hidden pointer-fine:inline">{t("agent.composer.shortcut")}</span>
            )}
            {text.length > 0 ? (
              <span className={`ml-auto tabular-nums ${text.length > MAX * 0.9 ? "font-semibold text-attention" : ""}`}>
                {t("agent.composer.count", { count: text.length, max: MAX })}
              </span>
            ) : null}
          </div>
          <Button type="submit" disabled={!canSend} pending={submit.isPending} className="w-full sm:w-auto">
            {submit.isPending ? null : <SendIcon aria-hidden="true" />}
            {submit.isPending ? t("agent.composer.sending") : t("agent.submitTask")}
          </Button>
        </div>
      </form>

      {submit.error ? <ErrorMessage error={submit.error} /> : null}
      {submit.isSuccess ? (
        <p role="status" className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-success-subtle px-3.5 py-2.5 text-body text-success">
          <span className="inline-flex items-center gap-2 font-semibold">
            <CheckIcon aria-hidden="true" className="shrink-0" />
            {t("agent.taskAccepted")}
          </span>
          <Link
            to={`/w/${ws}/more/agent/tasks/${submit.data.id}?account=${accountId}`}
            className={`rounded-sm font-semibold underline underline-offset-2 hover:text-primary ${FOCUS}`}
          >
            {t("agent.composer.follow")}
          </Link>
        </p>
      ) : null}

      {!text && !blocked && !submit.isSuccess ? (
        <div className="flex min-w-0 flex-wrap items-center gap-2" role="group" aria-label={t("agent.composer.suggestionsLabel")}>
          <span className="text-xs font-medium text-secondary">{t("agent.composer.suggestionsLabel")}</span>
          {SUGGESTIONS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                edit(t(`agent.composer.suggestions.${key}`));
                input.current?.focus();
              }}
              className={`inline-flex min-h-9 items-center rounded-full bg-surface-subtle px-3 text-xs font-medium text-primary ring-1 ring-border/80 transition-colors ring-inset hover:bg-assistant pointer-coarse:min-h-11 ${FOCUS}`}
            >
              {t(`agent.composer.suggestions.${key}`)}
            </button>
          ))}
        </div>
      ) : null}

      <ol className="grid min-w-0 gap-2 border-t border-border pt-3 sm:grid-cols-3" aria-label={t("agent.composer.stepsLabel")}>
        {(["recorded", "works", "control"] as const).map((step, index) => (
          <li key={step} className="flex min-w-0 items-start gap-2.5">
            <span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded-full bg-assistant text-[11px] font-bold text-action tabular-nums">
              {index + 1}
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-primary">{t(`agent.composer.steps.${step}.title`)}</p>
              <p className="text-xs leading-snug text-secondary">{t(`agent.composer.steps.${step}.body`)}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
